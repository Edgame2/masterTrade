"""
Feature Computation Pipeline

Computes ML features from various data sources (market data, on-chain, social, macro)
and stores them in the PostgreSQL feature store.
"""

import asyncio
import traceback
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Tuple
from statistics import mean, stdev

import structlog

from ml_adaptation.feature_store import PostgreSQLFeatureStore, FeatureDefinition
from shared.postgres_manager import PostgresManager

logger = structlog.get_logger()


class FeatureComputationPipeline:
    """
    Pipeline for computing ML features from multiple data sources
    
    Features are organized into 5 types:
    - technical: Technical indicators (RSI, MACD, moving averages, etc.)
    - onchain: On-chain metrics (NVT ratio, MVRV, exchange flows, etc.)
    - social: Social sentiment from Twitter, Reddit, LunarCrush
    - macro: Macro-economic indicators (VIX, DXY, stock indices, etc.)
    - composite: Derived features combining multiple sources
    """
    
    def __init__(
        self,
        market_data_db,  # Database instance from market_data_service
        feature_store: PostgreSQLFeatureStore,
        enable_auto_registration: bool = True
    ):
        """
        Initialize feature computation pipeline
        
        Args:
            market_data_db: Database instance with access to market data
            feature_store: PostgreSQLFeatureStore instance
            enable_auto_registration: Auto-register features on first computation
        """
        self.market_db = market_data_db
        self.feature_store = feature_store
        self.enable_auto_registration = enable_auto_registration
        
        # Track registered features to avoid repeated registrations
        self.registered_features: Dict[str, int] = {}  # name -> feature_id
        
    async def initialize(self):
        """Initialize pipeline and load existing feature definitions"""
        try:
            # Load existing feature definitions
            features = await self.feature_store.list_features(active_only=True)
            self.registered_features = {f.feature_name: f.id for f in features}
            
            logger.info(
                "Feature pipeline initialized",
                registered_features=len(self.registered_features)
            )
            
        except Exception as e:
            logger.error("Error initializing feature pipeline", error=str(e))
            raise
    
    async def compute_all_features(
        self,
        symbol: str,
        timestamp: Optional[datetime] = None
    ) -> Dict[str, float]:
        """
        Compute all features for a symbol at a specific time
        
        Args:
            symbol: Cryptocurrency symbol (e.g., 'BTCUSDT')
            timestamp: Timestamp for feature computation (default: now)
            
        Returns:
            Dict mapping feature_name to computed value
        """
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)
        
        features = {}
        
        try:
            # Compute all feature types
            technical = await self.compute_technical_features(symbol, timestamp)
            onchain = await self.compute_onchain_features(symbol, timestamp)
            social = await self.compute_social_features(symbol, timestamp)
            macro = await self.compute_macro_features(timestamp)
            composite = await self.compute_composite_features(
                symbol, technical, onchain, social, macro
            )
            
            # Combine all features
            features.update(technical)
            features.update(onchain)
            features.update(social)
            features.update(macro)
            features.update(composite)
            
            logger.info(
                "Computed all features",
                symbol=symbol,
                feature_count=len(features),
                timestamp=timestamp.isoformat()
            )
            
        except Exception as e:
            logger.error(
                "Error computing features",
                symbol=symbol,
                error=str(e),
                traceback=traceback.format_exc()
            )
        
        return features
    
    async def compute_and_store_features(
        self,
        symbol: str,
        timestamp: Optional[datetime] = None
    ) -> int:
        """
        Compute features and store them in the feature store
        
        Args:
            symbol: Cryptocurrency symbol
            timestamp: Timestamp for features
            
        Returns:
            Number of features stored
        """
        features = await self.compute_all_features(symbol, timestamp)
        
        if not features:
            logger.warning("No features computed", symbol=symbol)
            return 0
        
        # Auto-register features if enabled
        if self.enable_auto_registration:
            await self._auto_register_features(features)
        
        # Store features in bulk
        feature_values = []
        for feature_name, value in features.items():
            if feature_name not in self.registered_features:
                logger.warning(
                    "Feature not registered, skipping",
                    feature_name=feature_name
                )
                continue
            
            feature_id = self.registered_features[feature_name]
            feature_values.append({
                'feature_id': feature_id,
                'symbol': symbol,
                'value': value,
                'timestamp': timestamp or datetime.now(timezone.utc)
            })
        
        if feature_values:
            await self.feature_store.store_feature_values_bulk(feature_values)
            logger.info(
                "Stored features",
                symbol=symbol,
                count=len(feature_values)
            )
        
        return len(feature_values)
    
    async def compute_technical_features(
        self,
        symbol: str,
        timestamp: datetime
    ) -> Dict[str, float]:
        """
        Compute technical indicator features
        
        Features:
        - RSI (14-period)
        - MACD components (line, signal, histogram)
        - Moving averages (SMA 20, 50, 200; EMA 12, 26)
        - Bollinger Bands width
        - Volume indicators
        
        Args:
            symbol: Cryptocurrency symbol
            timestamp: Timestamp for feature computation
            
        Returns:
            Dict of technical features
        """
        features = {}
        
        try:
            # Get indicator results from last hour
            results = await self.market_db.get_indicator_results(
                symbol=symbol,
                hours=1,
                limit=100
            )
            
            if not results:
                logger.warning("No indicator results found", symbol=symbol)
                return features
            
            # Extract latest indicator values
            indicator_map = {}
            for result in results:
                indicator_type = result.get('indicator_type')
                values = result.get('values', {})
                
                # Keep most recent value for each indicator
                if indicator_type not in indicator_map:
                    indicator_map[indicator_type] = values
            
            # RSI
            if 'rsi' in indicator_map:
                rsi_value = indicator_map['rsi'].get('rsi_14')
                if rsi_value is not None:
                    features['rsi_14'] = float(rsi_value)
            
            # MACD
            if 'macd' in indicator_map:
                macd_vals = indicator_map['macd']
                if 'macd_line' in macd_vals:
                    features['macd_line'] = float(macd_vals['macd_line'])
                if 'macd_signal' in macd_vals:
                    features['macd_signal'] = float(macd_vals['macd_signal'])
                if 'macd_histogram' in macd_vals:
                    features['macd_histogram'] = float(macd_vals['macd_histogram'])
            
            # Moving Averages
            for indicator in ['sma', 'ema']:
                if indicator in indicator_map:
                    vals = indicator_map[indicator]
                    for key, value in vals.items():
                        if value is not None:
                            features[key] = float(value)
            
            # Bollinger Bands
            if 'bollinger_bands' in indicator_map:
                bb_vals = indicator_map['bollinger_bands']
                if 'bb_upper' in bb_vals and 'bb_lower' in bb_vals:
                    upper = float(bb_vals['bb_upper'])
                    lower = float(bb_vals['bb_lower'])
                    middle = float(bb_vals.get('bb_middle', (upper + lower) / 2))
                    
                    features['bb_upper'] = upper
                    features['bb_middle'] = middle
                    features['bb_lower'] = lower
                    
                    # BB width as percentage
                    if middle > 0:
                        features['bb_width_pct'] = ((upper - lower) / middle) * 100
            
            logger.debug(
                "Computed technical features",
                symbol=symbol,
                count=len(features)
            )
            
        except Exception as e:
            logger.error(
                "Error computing technical features",
                symbol=symbol,
                error=str(e)
            )
        
        return features
    
    async def compute_onchain_features(
        self,
        symbol: str,
        timestamp: datetime
    ) -> Dict[str, float]:
        """
        Compute on-chain metric features
        
        Features:
        - NVT ratio (Network Value to Transactions)
        - MVRV ratio (Market Value to Realized Value)
        - Exchange net flow (24h)
        - Active addresses
        - Hash rate
        - Transaction count
        
        Args:
            symbol: Cryptocurrency symbol
            timestamp: Timestamp for feature computation
            
        Returns:
            Dict of on-chain features
        """
        features = {}
        
        try:
            # Get recent on-chain metrics (last 24 hours)
            metrics = await self.market_db.get_onchain_metrics(
                symbol=symbol,
                hours=24,
                limit=200
            )
            
            if not metrics:
                logger.debug("No on-chain metrics found", symbol=symbol)
                return features
            
            # Group by metric name and get latest value
            metric_map: Dict[str, List[float]] = {}
            for metric in metrics:
                metric_name = metric.get('metric_name')
                value = metric.get('value')
                
                if metric_name and value is not None:
                    if metric_name not in metric_map:
                        metric_map[metric_name] = []
                    metric_map[metric_name].append(float(value))
            
            # Extract features
            for metric_name, values in metric_map.items():
                if values:
                    # Use latest value
                    features[f'onchain_{metric_name}'] = values[0]
                    
                    # Add 24h change if we have historical data
                    if len(values) >= 2:
                        change = ((values[0] - values[-1]) / values[-1]) * 100
                        features[f'onchain_{metric_name}_24h_change'] = change
            
            logger.debug(
                "Computed on-chain features",
                symbol=symbol,
                count=len(features)
            )
            
        except Exception as e:
            logger.error(
                "Error computing on-chain features",
                symbol=symbol,
                error=str(e)
            )
        
        return features
    
    async def compute_social_features(
        self,
        symbol: str,
        timestamp: datetime
    ) -> Dict[str, float]:
        """
        Compute social sentiment features
        
        Features:
        - Average sentiment score (Twitter, Reddit, aggregated)
        - Sentiment momentum (1h, 4h, 24h changes)
        - Social volume (mention count)
        - Engagement rate
        - Influencer sentiment
        
        Args:
            symbol: Cryptocurrency symbol
            timestamp: Timestamp for feature computation
            
        Returns:
            Dict of social sentiment features
        """
        features = {}
        
        try:
            # Get recent sentiment data (last 24 hours)
            sentiment_data = await self.market_db.get_social_sentiment(
                symbol=symbol,
                hours=24,
                limit=500
            )
            
            if not sentiment_data:
                logger.debug("No social sentiment found", symbol=symbol)
                return features
            
            # Group by source
            twitter_scores = []
            reddit_scores = []
            all_scores = []
            
            for item in sentiment_data:
                score = item.get('sentiment_score')
                source = item.get('source', '').lower()
                
                if score is not None:
                    score_float = float(score)
                    all_scores.append(score_float)
                    
                    if 'twitter' in source:
                        twitter_scores.append(score_float)
                    elif 'reddit' in source:
                        reddit_scores.append(score_float)
            
            # Average sentiment by source
            if twitter_scores:
                features['social_sentiment_twitter'] = mean(twitter_scores)
            if reddit_scores:
                features['social_sentiment_reddit'] = mean(reddit_scores)
            if all_scores:
                features['social_sentiment_avg'] = mean(all_scores)
                
                # Sentiment standard deviation (volatility)
                if len(all_scores) > 1:
                    features['social_sentiment_volatility'] = stdev(all_scores)
            
            # Social volume (mention count in last 24h)
            features['social_volume_24h'] = float(len(sentiment_data))
            
            # Sentiment momentum (compare recent vs older)
            if len(sentiment_data) >= 10:
                recent_scores = [float(item['sentiment_score']) 
                               for item in sentiment_data[:len(sentiment_data)//2]
                               if item.get('sentiment_score') is not None]
                older_scores = [float(item['sentiment_score']) 
                              for item in sentiment_data[len(sentiment_data)//2:]
                              if item.get('sentiment_score') is not None]
                
                if recent_scores and older_scores:
                    recent_avg = mean(recent_scores)
                    older_avg = mean(older_scores)
                    features['social_sentiment_momentum'] = recent_avg - older_avg
            
            logger.debug(
                "Computed social features",
                symbol=symbol,
                count=len(features)
            )
            
        except Exception as e:
            logger.error(
                "Error computing social features",
                symbol=symbol,
                error=str(e)
            )
        
        return features
    
    async def compute_macro_features(
        self,
        timestamp: datetime
    ) -> Dict[str, float]:
        """
        Compute macro-economic features
        
        Features:
        - VIX (volatility index)
        - DXY (US Dollar index)
        - Stock market indices (S&P 500, NASDAQ, Dow Jones)
        - Fear & Greed Index
        
        Args:
            timestamp: Timestamp for feature computation
            
        Returns:
            Dict of macro features
        """
        features = {}
        
        try:
            # Get current stock indices
            indices = await self.market_db.get_all_current_stock_indices()
            
            # Extract key indices
            index_map = {
                '^GSPC': 'sp500',
                '^IXIC': 'nasdaq',
                '^DJI': 'dow',
                '^VIX': 'vix',
                'DX-Y.NYB': 'dxy'
            }
            
            for index in indices:
                symbol = index.get('symbol')
                if symbol in index_map:
                    feature_name = f'macro_{index_map[symbol]}'
                    current_price = index.get('current_price')
                    change_percent = index.get('change_percent')
                    
                    if current_price is not None:
                        features[feature_name] = float(current_price)
                    if change_percent is not None:
                        features[f'{feature_name}_change'] = float(change_percent)
            
            # Get market sentiment
            market_summary = await self.market_db.get_stock_market_summary()
            sentiment = market_summary.get('market_sentiment', 'neutral')
            
            # Convert sentiment to numeric
            sentiment_map = {
                'bullish': 1.0,
                'neutral': 0.0,
                'bearish': -1.0
            }
            features['macro_market_sentiment'] = sentiment_map.get(sentiment, 0.0)
            
            # Get Fear & Greed Index if available
            sentiment_data = await self.market_db.get_sentiment_data(hours=24, limit=1)
            if sentiment_data:
                latest = sentiment_data[0]
                if 'fear_greed_index' in latest:
                    features['macro_fear_greed'] = float(latest['fear_greed_index'])
            
            logger.debug(
                "Computed macro features",
                count=len(features)
            )
            
        except Exception as e:
            logger.error(
                "Error computing macro features",
                error=str(e)
            )
        
        return features
    
    async def compute_composite_features(
        self,
        symbol: str,
        technical: Dict[str, float],
        onchain: Dict[str, float],
        social: Dict[str, float],
        macro: Dict[str, float]
    ) -> Dict[str, float]:
        """
        Compute composite features combining multiple data sources
        
        Features:
        - Risk score (volatility + VIX)
        - Sentiment alignment (technical + social)
        - Market strength (price action + on-chain)
        
        Args:
            symbol: Cryptocurrency symbol
            technical: Technical features dict
            onchain: On-chain features dict
            social: Social features dict
            macro: Macro features dict
            
        Returns:
            Dict of composite features
        """
        features = {}
        
        try:
            # Risk score: Combine BB width + VIX
            bb_width = technical.get('bb_width_pct')
            vix = macro.get('macro_vix')
            
            if bb_width is not None and vix is not None:
                # Normalize and combine (0-100 scale)
                risk_score = (bb_width * 0.6) + (vix * 0.4)
                features['composite_risk_score'] = min(100.0, risk_score)
            
            # Sentiment alignment: RSI + social sentiment
            rsi = technical.get('rsi_14')
            sentiment = social.get('social_sentiment_avg')
            
            if rsi is not None and sentiment is not None:
                # Convert RSI to -1 to 1 scale (oversold to overbought)
                rsi_normalized = (rsi - 50) / 50
                # Alignment: both positive or both negative = aligned
                alignment = rsi_normalized * sentiment
                features['composite_sentiment_alignment'] = alignment
            
            # Market strength: MACD + exchange flows
            macd_hist = technical.get('macd_histogram')
            exchange_flow = onchain.get('onchain_exchange_netflow')
            
            if macd_hist is not None and exchange_flow is not None:
                # Positive MACD + negative flow (leaving exchanges) = bullish
                # Negative MACD + positive flow (entering exchanges) = bearish
                strength = macd_hist - (exchange_flow * 0.01)  # Scale flow
                features['composite_market_strength'] = strength
            
            # Fear/Greed vs Social Sentiment divergence
            fear_greed = macro.get('macro_fear_greed')
            if fear_greed is not None and sentiment is not None:
                # Convert fear/greed to -1 to 1 scale
                fg_normalized = (fear_greed - 50) / 50
                # Divergence: difference between macro sentiment and social
                divergence = fg_normalized - sentiment
                features['composite_sentiment_divergence'] = divergence
            
            logger.debug(
                "Computed composite features",
                symbol=symbol,
                count=len(features)
            )
            
        except Exception as e:
            logger.error(
                "Error computing composite features",
                symbol=symbol,
                error=str(e)
            )
        
        return features
    
    async def _auto_register_features(self, features: Dict[str, float]):
        """
        Automatically register features that don't exist yet
        
        Args:
            features: Dict of feature_name -> value
        """
        for feature_name in features.keys():
            if feature_name in self.registered_features:
                continue
            
            # Determine feature type from name
            if feature_name.startswith('rsi') or feature_name.startswith('macd') or \
               feature_name.startswith('sma') or feature_name.startswith('ema') or \
               feature_name.startswith('bb_'):
                feature_type = 'technical'
                data_sources = ['indicator_results']
                description = f"Technical indicator: {feature_name}"
                
            elif feature_name.startswith('onchain_'):
                feature_type = 'onchain'
                data_sources = ['onchain_metrics']
                description = f"On-chain metric: {feature_name}"
                
            elif feature_name.startswith('social_'):
                feature_type = 'social'
                data_sources = ['social_sentiment']
                description = f"Social sentiment metric: {feature_name}"
                
            elif feature_name.startswith('macro_'):
                feature_type = 'macro'
                data_sources = ['market_data', 'sentiment_data']
                description = f"Macro-economic indicator: {feature_name}"
                
            elif feature_name.startswith('composite_'):
                feature_type = 'composite'
                data_sources = ['indicator_results', 'onchain_metrics', 
                              'social_sentiment', 'market_data']
                description = f"Composite feature: {feature_name}"
                
            else:
                logger.warning(f"Unknown feature type for {feature_name}, skipping")
                continue
            
            try:
                # Register feature
                feature_id = await self.feature_store.register_feature(
                    feature_name=feature_name,
                    feature_type=feature_type,
                    description=description,
                    data_sources=data_sources,
                    computation_logic="Computed by FeatureComputationPipeline",
                    version=1
                )
                
                self.registered_features[feature_name] = feature_id
                
                logger.info(
                    "Auto-registered feature",
                    feature_name=feature_name,
                    feature_id=feature_id,
                    feature_type=feature_type
                )
                
            except Exception as e:
                logger.error(
                    "Error auto-registering feature",
                    feature_name=feature_name,
                    error=str(e)
                )
    
    async def compute_features_for_backtest(
        self,
        symbol: str,
        start_time: datetime,
        end_time: datetime,
        interval_hours: int = 1
    ) -> List[Tuple[datetime, Dict[str, float]]]:
        """
        Compute features for a time range (useful for backtesting)
        
        Args:
            symbol: Cryptocurrency symbol
            start_time: Start of time range
            end_time: End of time range
            interval_hours: Hours between feature computations
            
        Returns:
            List of (timestamp, features_dict) tuples
        """
        results = []
        current_time = start_time
        
        while current_time <= end_time:
            features = await self.compute_all_features(symbol, current_time)
            results.append((current_time, features))
            
            current_time += timedelta(hours=interval_hours)
            
            # Avoid overwhelming the system
            await asyncio.sleep(0.1)
        
        logger.info(
            "Computed features for backtest",
            symbol=symbol,
            start_time=start_time.isoformat(),
            end_time=end_time.isoformat(),
            count=len(results)
        )
        
        return results
    
    async def get_feature_summary(self) -> Dict[str, Any]:
        """
        Get summary of available features
        
        Returns:
            Dict with feature counts by type and other statistics
        """
        try:
            stats = await self.feature_store.get_statistics()
            
            return {
                'total_features': len(self.registered_features),
                'features_by_type': stats.get('features_by_type', {}),
                'total_feature_values': stats.get('total_values', 0),
                'recent_values_24h': stats.get('recent_values_24h', 0),
                'unique_symbols': stats.get('unique_symbols', 0),
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            logger.error("Error getting feature summary", error=str(e))
            return {}
