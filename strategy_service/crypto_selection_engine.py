"""
Crypto Selection Engine

This module analyzes market data to identify the best cryptocurrencies for daily trading.
It uses comprehensive scoring based on volatility, volume, momentum, technical indicators,
and market conditions to select optimal trading pairs.
"""

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
import structlog
import numpy as np
from statistics import mean, stdev

from postgres_database import Database

logger = structlog.get_logger()

@dataclass
class CryptoCandidate:
    """Represents a cryptocurrency candidate for selection"""
    symbol: str
    base_asset: str
    score: float
    volatility_score: float
    volume_score: float
    momentum_score: float
    technical_score: float
    market_cap_score: float
    trend_strength: float
    risk_score: float
    sentiment_score: float
    selection_reason: str
    metadata: Dict[str, Any]

class CryptoSelectionEngine:
    """
    Advanced cryptocurrency selection engine
    
    Features:
    - Multi-factor analysis (volatility, volume, momentum, technicals)
    - Market condition adaptation
    - Risk assessment and scoring
    - Daily selection optimization
    - Database integration for persistence
    """
    
    def __init__(self, database: Database):
        self.database = database
        
        # Selection configuration
        self.max_selections = 10  # Maximum cryptocurrencies to select daily
        self.min_volume_24h = 1000000  # Minimum 24h volume (USD)
        self.lookback_days = 7  # Days of historical data for analysis
        self.min_data_points = 100  # Minimum data points required
        self.sentiment_hours_back = 24  # Hours of sentiment history to inspect
        self.min_sentiment_score = 4.5  # Minimum sentiment score to pass filters
        self.global_sentiment_types = (
            "global_crypto_sentiment",
            "global_market_sentiment",
            "market_sentiment",
        )
        
        # Scoring weights
        self.scoring_weights = {
            'volatility': 0.20,     # Trading opportunity from price movement
            'volume': 0.17,         # Liquidity and market interest
            'momentum': 0.17,       # Trend strength and direction
            'technical': 0.13,      # Technical indicator signals
            'market_cap': 0.08,     # Market stability and size
            'risk': 0.10,           # Risk-adjusted attractiveness
            'sentiment': 0.15       # Market sentiment alignment
        }
        
        # Risk thresholds
        self.risk_thresholds = {
            'max_volatility': 0.15,    # Max 15% daily volatility
            'min_volume_consistency': 0.7,  # Volume consistency score
            'max_drawdown_7d': 0.25,   # Max 25% drawdown in 7 days
        }
        
    async def run_daily_selection(self) -> List[CryptoCandidate]:
        """
        Run daily cryptocurrency selection process
        
        Returns:
            List of selected cryptocurrency candidates with scores and metadata
        """
        try:
            logger.info("Starting daily cryptocurrency selection process")
            
            # Get all available cryptocurrencies
            available_cryptos = await self._get_available_cryptocurrencies()
            logger.info(f"Analyzing {len(available_cryptos)} available cryptocurrencies")
            
            # Analyze each cryptocurrency
            candidates = []
            
            for crypto in available_cryptos:
                try:
                    candidate = await self._analyze_cryptocurrency(crypto)
                    if candidate and self._passes_selection_criteria(candidate):
                        candidates.append(candidate)
                except Exception as e:
                    logger.warning(f"Error analyzing {crypto['symbol']}: {e}")
                    continue
            
            # Rank and select top cryptocurrencies
            selected_cryptos = self._select_top_cryptocurrencies(candidates)
            
            # Trigger historical data collection for selected cryptos
            if selected_cryptos:
                await self._ensure_historical_data_for_selections(selected_cryptos)
            
            # Store selections in database
            await self._store_daily_selections(selected_cryptos)
            
            logger.info(
                f"Daily cryptocurrency selection completed",
                total_analyzed=len(available_cryptos),
                candidates_found=len(candidates),
                final_selections=len(selected_cryptos)
            )
            
            return selected_cryptos
            
        except Exception as e:
            logger.error(f"Error in daily crypto selection: {e}")
            return []
    
    async def _get_available_cryptocurrencies(self) -> List[Dict[str, Any]]:
        """Get list of available cryptocurrencies for analysis"""
        try:
            # Get all tracked crypto symbols from database
            tracked_symbols = await self.database.get_tracked_symbols(
                asset_type="crypto",
                exchange="binance"
            )
            
            # Add some popular cryptos if not already tracked
            popular_cryptos = [
                'BTCUSDC', 'ETHUSDC', 'ADAUSDC', 'SOLUSDC', 'DOTUSDC',
                'LINKUSDC', 'AVAXUSDC', 'MATICUSDC', 'ATOMUSDC', 'LTCUSDC',
                'XRPUSDC', 'BNBUSDC', 'DOGEUSDC', 'TRXUSDC', 'UNIUSDC'
            ]
            
            # Merge tracked symbols with popular ones
            all_symbols = set()
            
            # Add tracked symbols
            for symbol_data in tracked_symbols:
                all_symbols.add(symbol_data['symbol'])
            
            # Add popular symbols
            for symbol in popular_cryptos:
                all_symbols.add(symbol)
            
            # Convert back to list of dictionaries
            crypto_list = []
            for symbol in all_symbols:
                # Parse symbol to get base asset
                if symbol.endswith('USDC'):
                    base_asset = symbol[:-4]
                elif symbol.endswith('USDT'):
                    base_asset = symbol[:-4]
                else:
                    base_asset = symbol[:-4] if len(symbol) > 4 else symbol
                
                crypto_list.append({
                    'symbol': symbol,
                    'base_asset': base_asset,
                    'quote_asset': 'USDC' if symbol.endswith('USDC') else 'USDT'
                })
            
            return crypto_list
            
        except Exception as e:
            logger.error(f"Error getting available cryptocurrencies: {e}")
            return []
    
    async def _analyze_cryptocurrency(self, crypto: Dict[str, Any]) -> Optional[CryptoCandidate]:
        """
        Analyze a single cryptocurrency and generate candidate with scores
        
        Args:
            crypto: Dictionary with symbol, base_asset, quote_asset
            
        Returns:
            CryptoCandidate with comprehensive scoring or None if insufficient data
        """
        try:
            symbol = crypto['symbol']
            base_asset = crypto['base_asset']
            
            # Get historical market data
            end_date = datetime.now(timezone.utc)
            start_date = end_date - timedelta(days=self.lookback_days)
            
            market_data = await self._get_market_data_for_analysis(symbol, start_date, end_date)
            
            if not market_data or len(market_data) < self.min_data_points:
                logger.debug(f"Insufficient data for {symbol}: {len(market_data) if market_data else 0} points")
                return None
            
            # Calculate scoring components
            volatility_score = await self._calculate_volatility_score(market_data)
            volume_score = await self._calculate_volume_score(market_data)
            momentum_score = await self._calculate_momentum_score(market_data)
            technical_score = await self._calculate_technical_score(market_data)
            market_cap_score = await self._calculate_market_cap_score(symbol, base_asset)
            risk_score = await self._calculate_risk_score(market_data)
            sentiment_score, sentiment_metadata = await self._calculate_sentiment_score(symbol, base_asset)
            
            # Calculate overall score
            overall_score = (
                volatility_score * self.scoring_weights['volatility'] +
                volume_score * self.scoring_weights['volume'] +
                momentum_score * self.scoring_weights['momentum'] +
                technical_score * self.scoring_weights['technical'] +
                market_cap_score * self.scoring_weights['market_cap'] +
                risk_score * self.scoring_weights['risk'] +
                sentiment_score * self.scoring_weights['sentiment']
            )
            
            # Calculate trend strength
            trend_strength = await self._calculate_trend_strength(market_data)
            
            # Generate selection reason
            selection_reason = self._generate_selection_reason(
                volatility_score,
                volume_score,
                momentum_score,
                technical_score,
                market_cap_score,
                risk_score,
                sentiment_score
            )
            
            # Create metadata
            metadata = {
                'analysis_date': datetime.now(timezone.utc).isoformat(),
                'data_points': len(market_data),
                'lookback_days': self.lookback_days,
                'latest_price': market_data[-1]['close_price'] if market_data else 0,
                'price_change_7d': ((float(market_data[-1]['close_price']) - float(market_data[0]['close_price'])) / float(market_data[0]['close_price']) * 100) if len(market_data) >= 2 else 0,
                'avg_volume_7d': mean([float(d['volume']) for d in market_data[-7*24:]]) if len(market_data) >= 7*24 else 0,  # Last 7 days hourly
                'scoring_weights': self.scoring_weights,
                'sentiment': sentiment_metadata,
                'sentiment_score': sentiment_score
            }
            
            return CryptoCandidate(
                symbol=symbol,
                base_asset=base_asset,
                score=overall_score,
                volatility_score=volatility_score,
                volume_score=volume_score,
                momentum_score=momentum_score,
                technical_score=technical_score,
                market_cap_score=market_cap_score,
                trend_strength=trend_strength,
                risk_score=risk_score,
                sentiment_score=sentiment_score,
                selection_reason=selection_reason,
                metadata=metadata
            )
            
        except Exception as e:
            logger.error(f"Error analyzing cryptocurrency {crypto.get('symbol', 'unknown')}: {e}")
            return None
    
    async def _get_market_data_for_analysis(self, symbol: str, start_date: datetime, end_date: datetime) -> List[Dict[str, Any]]:
        """Get market data for cryptocurrency analysis"""
        try:
            # Get hourly data for detailed analysis
            market_data = await self.database.get_market_data_for_analysis(
                symbol=symbol,
                interval="1h",
                hours_back=self.lookback_days * 24
            )
            
            # Filter data within date range and sort by timestamp
            filtered_data = []
            for data in market_data:
                timestamp = data.get('timestamp')
                if isinstance(timestamp, str):
                    timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                
                if start_date <= timestamp <= end_date:
                    filtered_data.append(data)
            
            # Sort by timestamp
            filtered_data.sort(key=lambda x: x.get('timestamp', datetime.min.replace(tzinfo=timezone.utc)))
            
            return filtered_data
            
        except Exception as e:
            logger.error(f"Error getting market data for {symbol}: {e}")
            return []
    
    async def _calculate_volatility_score(self, market_data: List[Dict]) -> float:
        """
        Calculate volatility score (0-10 scale)
        Higher volatility = higher trading opportunity = higher score
        """
        try:
            if len(market_data) < 24:  # Need at least 24 hours of data
                return 0.0
            
            # Calculate hourly returns
            returns = []
            for i in range(1, len(market_data)):
                prev_close = float(market_data[i-1]['close_price'])
                curr_close = float(market_data[i]['close_price'])
                
                if prev_close > 0:
                    hourly_return = (curr_close - prev_close) / prev_close
                    returns.append(hourly_return)
            
            if not returns:
                return 0.0
            
            # Calculate volatility metrics
            volatility = stdev(returns) if len(returns) > 1 else 0
            avg_abs_return = mean([abs(r) for r in returns])
            
            # Normalize volatility to 0-10 scale
            # Target range: 0.005 (low) to 0.05 (high) hourly volatility
            normalized_vol = min(10, max(0, (volatility / 0.05) * 10))
            normalized_abs = min(10, max(0, (avg_abs_return / 0.03) * 10))
            
            # Combine metrics (favor consistent movement)
            volatility_score = (normalized_vol * 0.7 + normalized_abs * 0.3)
            
            # Apply risk threshold check
            daily_volatility = volatility * np.sqrt(24)  # Convert to daily
            if daily_volatility > self.risk_thresholds['max_volatility']:
                volatility_score *= 0.5  # Penalize excessive volatility
            
            return min(10.0, max(0.0, volatility_score))
            
        except Exception as e:
            logger.error(f"Error calculating volatility score: {e}")
            return 0.0
    
    async def _calculate_volume_score(self, market_data: List[Dict]) -> float:
        """
        Calculate volume score (0-10 scale)
        Higher volume = better liquidity = higher score
        """
        try:
            if len(market_data) < 24:
                return 0.0
            
            # Calculate volume metrics
            volumes = [float(d['volume']) for d in market_data[-24:]]  # Last 24 hours
            quote_volumes = [float(d.get('quote_volume', 0)) for d in market_data[-24:]]
            
            if not volumes:
                return 0.0
            
            # Average daily volume (in quote asset - USD)
            avg_volume = mean(quote_volumes) if quote_volumes else mean(volumes)
            
            # Volume consistency (standard deviation)
            volume_std = stdev(volumes) if len(volumes) > 1 else 0
            volume_consistency = 1 - min(1, volume_std / (mean(volumes) + 1e-8))
            
            # Normalize volume to score
            # Target: $1M+ daily volume gets high score
            volume_score_raw = min(10, max(0, np.log10(avg_volume + 1) / np.log10(10000000) * 10))
            
            # Apply consistency bonus
            consistency_bonus = volume_consistency * 2
            volume_score = min(10, volume_score_raw + consistency_bonus)
            
            # Check minimum volume threshold
            if avg_volume < self.min_volume_24h:
                volume_score *= 0.3  # Heavy penalty for low volume
            
            return volume_score
            
        except Exception as e:
            logger.error(f"Error calculating volume score: {e}")
            return 0.0
    
    async def _calculate_momentum_score(self, market_data: List[Dict]) -> float:
        """
        Calculate momentum score (0-10 scale)
        Strong trend in either direction = higher score
        """
        try:
            if len(market_data) < 24:
                return 0.0
            
            prices = [float(d['close_price']) for d in market_data]
            
            # Calculate multiple momentum indicators
            # 1. Price change over different periods
            price_changes = {}
            periods = [6, 12, 24, 48]  # 6h, 12h, 24h, 48h
            
            for period in periods:
                if len(prices) >= period:
                    price_change = (prices[-1] - prices[-period]) / prices[-period]
                    price_changes[f'{period}h'] = price_change
            
            # 2. Moving average trends
            ma_scores = []
            if len(prices) >= 20:
                ma_short = mean(prices[-12:])  # 12h MA
                ma_long = mean(prices[-24:])   # 24h MA
                
                ma_trend = (ma_short - ma_long) / ma_long if ma_long > 0 else 0
                ma_scores.append(abs(ma_trend))
            
            # 3. Trend consistency (count of positive/negative moves)
            recent_moves = []
            for i in range(1, min(25, len(prices))):  # Last 24 hours
                move = (prices[-i] - prices[-i-1]) / prices[-i-1] if prices[-i-1] > 0 else 0
                recent_moves.append(move)
            
            if recent_moves:
                positive_moves = len([m for m in recent_moves if m > 0])
                trend_consistency = abs(positive_moves / len(recent_moves) - 0.5) * 2  # 0 = no trend, 1 = strong trend
            else:
                trend_consistency = 0
            
            # Combine momentum indicators
            momentum_components = []
            
            # Add price change scores
            for period, change in price_changes.items():
                # Score based on absolute change magnitude
                change_score = min(5, abs(change) * 100)  # 1% change = 1 point
                momentum_components.append(change_score)
            
            # Add MA trend score
            if ma_scores:
                momentum_components.extend([score * 100 for score in ma_scores])
            
            # Add trend consistency score
            momentum_components.append(trend_consistency * 10)
            
            # Calculate final momentum score
            if momentum_components:
                momentum_score = mean(momentum_components)
            else:
                momentum_score = 0
            
            return min(10.0, max(0.0, momentum_score))
            
        except Exception as e:
            logger.error(f"Error calculating momentum score: {e}")
            return 0.0
    
    async def _calculate_technical_score(self, market_data: List[Dict]) -> float:
        """
        Calculate technical analysis score (0-10 scale)
        Strong technical signals = higher score
        """
        try:
            if len(market_data) < 50:  # Need sufficient data for technical analysis
                return 5.0  # Neutral score if insufficient data
            
            prices = [float(d['close_price']) for d in market_data]
            volumes = [float(d['volume']) for d in market_data]
            
            technical_signals = []
            
            # 1. RSI (Relative Strength Index)
            rsi = self._calculate_rsi(prices, period=14)
            if rsi is not None:
                # Score based on RSI extremes (oversold/overbought conditions)
                if 20 <= rsi <= 30 or 70 <= rsi <= 80:  # Good entry points
                    rsi_score = 8
                elif 30 < rsi < 70:  # Neutral zone
                    rsi_score = 5
                else:  # Extreme zones
                    rsi_score = 3
                technical_signals.append(rsi_score)
            
            # 2. MACD Signal
            macd_line, macd_signal = self._calculate_macd(prices)
            if macd_line is not None and macd_signal is not None:
                macd_histogram = macd_line - macd_signal
                # Score based on MACD momentum
                if abs(macd_histogram) > 0.01:  # Strong signal
                    macd_score = 8
                elif abs(macd_histogram) > 0.005:  # Moderate signal
                    macd_score = 6
                else:  # Weak signal
                    macd_score = 4
                technical_signals.append(macd_score)
            
            # 3. Bollinger Bands
            bb_upper, bb_lower, bb_middle = self._calculate_bollinger_bands(prices)
            if bb_upper is not None and bb_lower is not None:
                current_price = prices[-1]
                bb_position = (current_price - bb_lower) / (bb_upper - bb_lower) if bb_upper != bb_lower else 0.5
                
                # Score based on position in bands
                if bb_position < 0.2 or bb_position > 0.8:  # Near bands (potential reversal)
                    bb_score = 7
                elif 0.3 <= bb_position <= 0.7:  # Middle area
                    bb_score = 5
                else:  # Moderate positions
                    bb_score = 6
                technical_signals.append(bb_score)
            
            # 4. Volume Analysis
            if len(volumes) >= 20:
                avg_volume = mean(volumes[-20:])
                recent_volume = mean(volumes[-5:])
                volume_ratio = recent_volume / avg_volume if avg_volume > 0 else 1
                
                # Higher recent volume = higher score
                if volume_ratio > 1.5:  # High volume
                    volume_score = 8
                elif volume_ratio > 1.2:  # Moderate volume increase
                    volume_score = 6
                elif volume_ratio > 0.8:  # Normal volume
                    volume_score = 5
                else:  # Low volume
                    volume_score = 3
                technical_signals.append(volume_score)
            
            # 5. Price Pattern Analysis
            pattern_score = self._analyze_price_patterns(prices[-50:])  # Last 50 data points
            technical_signals.append(pattern_score)
            
            # Calculate final technical score
            if technical_signals:
                technical_score = mean(technical_signals)
            else:
                technical_score = 5.0  # Neutral
            
            return min(10.0, max(0.0, technical_score))
            
        except Exception as e:
            logger.error(f"Error calculating technical score: {e}")
            return 5.0  # Return neutral score on error
    
    def _calculate_rsi(self, prices: List[float], period: int = 14) -> Optional[float]:
        """Calculate RSI (Relative Strength Index)"""
        try:
            if len(prices) < period + 1:
                return None
            
            # Calculate price changes
            changes = [prices[i] - prices[i-1] for i in range(1, len(prices))]
            
            # Separate gains and losses
            gains = [max(0, change) for change in changes]
            losses = [max(0, -change) for change in changes]
            
            # Calculate average gains and losses
            if len(gains) >= period and len(losses) >= period:
                avg_gain = mean(gains[-period:])
                avg_loss = mean(losses[-period:])
                
                if avg_loss == 0:
                    return 100  # No losses = RSI = 100
                
                rs = avg_gain / avg_loss
                rsi = 100 - (100 / (1 + rs))
                return rsi
            
            return None
            
        except Exception as e:
            logger.error(f"Error calculating RSI: {e}")
            return None
    
    def _calculate_macd(self, prices: List[float], fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[Optional[float], Optional[float]]:
        """Calculate MACD (Moving Average Convergence Divergence)"""
        try:
            if len(prices) < slow + signal:
                return None, None
            
            # Calculate EMAs
            ema_fast = self._calculate_ema(prices, fast)
            ema_slow = self._calculate_ema(prices, slow)
            
            if ema_fast is None or ema_slow is None:
                return None, None
            
            # MACD line
            macd_line = ema_fast - ema_slow
            
            # Need to calculate signal line (EMA of MACD line)
            # For simplicity, return current MACD line and approximate signal
            signal_line = macd_line * 0.9  # Simplified signal approximation
            
            return macd_line, signal_line
            
        except Exception as e:
            logger.error(f"Error calculating MACD: {e}")
            return None, None
    
    def _calculate_ema(self, prices: List[float], period: int) -> Optional[float]:
        """Calculate Exponential Moving Average"""
        try:
            if len(prices) < period:
                return None
            
            # Start with SMA
            sma = mean(prices[:period])
            multiplier = 2 / (period + 1)
            
            ema = sma
            for price in prices[period:]:
                ema = (price * multiplier) + (ema * (1 - multiplier))
            
            return ema
            
        except Exception as e:
            logger.error(f"Error calculating EMA: {e}")
            return None
    
    def _calculate_bollinger_bands(self, prices: List[float], period: int = 20, std_dev: float = 2.0) -> Tuple[Optional[float], Optional[float], Optional[float]]:
        """Calculate Bollinger Bands"""
        try:
            if len(prices) < period:
                return None, None, None
            
            # Middle band (SMA)
            sma = mean(prices[-period:])
            
            # Standard deviation
            variance = sum((p - sma) ** 2 for p in prices[-period:]) / period
            std = variance ** 0.5
            
            # Upper and lower bands
            upper_band = sma + (std_dev * std)
            lower_band = sma - (std_dev * std)
            
            return upper_band, lower_band, sma
            
        except Exception as e:
            logger.error(f"Error calculating Bollinger Bands: {e}")
            return None, None, None
    
    def _analyze_price_patterns(self, prices: List[float]) -> float:
        """Analyze price patterns for trading signals"""
        try:
            if len(prices) < 20:
                return 5.0
            
            pattern_score = 5.0  # Start with neutral
            
            # Check for breakouts
            recent_high = max(prices[-10:])
            recent_low = min(prices[-10:])
            historical_high = max(prices[:-10]) if len(prices) > 10 else recent_high
            historical_low = min(prices[:-10]) if len(prices) > 10 else recent_low
            
            current_price = prices[-1]
            
            # Breakout detection
            if current_price > historical_high * 1.02:  # 2% above historical high
                pattern_score += 2  # Bullish breakout
            elif current_price < historical_low * 0.98:  # 2% below historical low
                pattern_score += 2  # Bearish breakout (still trading opportunity)
            
            # Support/Resistance levels
            price_range = max(prices) - min(prices)
            if price_range > 0:
                current_position = (current_price - min(prices)) / price_range
                
                # Near support or resistance
                if current_position < 0.1 or current_position > 0.9:
                    pattern_score += 1
            
            # Trend consistency
            short_trend = (prices[-1] - prices[-5]) / prices[-5] if len(prices) >= 5 and prices[-5] > 0 else 0
            medium_trend = (prices[-1] - prices[-10]) / prices[-10] if len(prices) >= 10 and prices[-10] > 0 else 0
            
            if short_trend * medium_trend > 0 and abs(short_trend) > 0.01:  # Consistent trend
                pattern_score += 1
            
            return min(10.0, max(0.0, pattern_score))
            
        except Exception as e:
            logger.error(f"Error analyzing price patterns: {e}")
            return 5.0
    
    async def _calculate_market_cap_score(self, symbol: str, base_asset: str) -> float:
        """
        Calculate market cap score (0-10 scale)
        Larger market cap = more stable = higher score (but diminishing returns)
        """
        try:
            # Market cap ranking based on common knowledge
            # This could be enhanced with real-time market cap data
            market_cap_rankings = {
                'BTC': 10.0,  # Bitcoin
                'ETH': 9.5,   # Ethereum
                'BNB': 8.5,   # Binance Coin
                'XRP': 8.0,   # Ripple
                'ADA': 7.5,   # Cardano
                'SOL': 7.5,   # Solana
                'DOT': 7.0,   # Polkadot
                'DOGE': 6.5,  # Dogecoin
                'AVAX': 6.5,  # Avalanche
                'MATIC': 6.0, # Polygon
                'LINK': 6.0,  # Chainlink
                'UNI': 5.5,   # Uniswap
                'LTC': 5.5,   # Litecoin
                'ATOM': 5.0,  # Cosmos
                'TRX': 4.5,   # TRON
                'VET': 4.0,   # VeChain
                'FTT': 3.5,   # FTX Token
                'ALGO': 3.0,  # Algorand
            }
            
            # Get base market cap score
            market_cap_score = market_cap_rankings.get(base_asset, 2.0)  # Default for unknown assets
            
            # Adjust based on recent performance and stability
            # This is a placeholder - could be enhanced with real market cap data
            
            return min(10.0, max(0.0, market_cap_score))
            
        except Exception as e:
            logger.error(f"Error calculating market cap score for {base_asset}: {e}")
            return 5.0  # Default neutral score
    
    async def _calculate_risk_score(self, market_data: List[Dict]) -> float:
        """
        Calculate risk score (0-10 scale)
        Lower risk = higher score
        """
        try:
            if len(market_data) < 24:
                return 5.0
            
            prices = [float(d['close_price']) for d in market_data]
            volumes = [float(d['volume']) for d in market_data]
            
            risk_components = []
            
            # 1. Price volatility risk
            if len(prices) >= 24:
                returns = [(prices[i] - prices[i-1]) / prices[i-1] for i in range(1, min(25, len(prices))) if prices[i-1] > 0]
                if returns:
                    volatility = stdev(returns) if len(returns) > 1 else 0
                    # Lower volatility = higher risk score
                    vol_risk_score = max(0, 10 - (volatility / 0.02) * 10)  # 2% hourly vol = 0 score
                    risk_components.append(vol_risk_score)
            
            # 2. Volume consistency risk
            if len(volumes) >= 24:
                volume_std = stdev(volumes[-24:]) if len(volumes) >= 2 else 0
                volume_mean = mean(volumes[-24:])
                volume_cv = volume_std / (volume_mean + 1e-8)  # Coefficient of variation
                
                # Lower coefficient of variation = higher risk score
                volume_risk_score = max(0, 10 - volume_cv * 5)
                risk_components.append(volume_risk_score)
            
            # 3. Maximum drawdown risk
            if len(prices) >= 24:
                running_max = prices[0]
                max_drawdown = 0
                
                for price in prices:
                    running_max = max(running_max, price)
                    drawdown = (running_max - price) / running_max if running_max > 0 else 0
                    max_drawdown = max(max_drawdown, drawdown)
                
                # Lower drawdown = higher risk score
                drawdown_risk_score = max(0, 10 - max_drawdown * 40)  # 25% drawdown = 0 score
                risk_components.append(drawdown_risk_score)
            
            # 4. Price stability risk (recent price changes)
            if len(prices) >= 12:
                recent_changes = []
                for i in range(-12, -1):  # Last 12 hours
                    if abs(i) < len(prices) and prices[i-1] > 0:
                        change = abs((prices[i] - prices[i-1]) / prices[i-1])
                        recent_changes.append(change)
                
                if recent_changes:
                    avg_change = mean(recent_changes)
                    # Lower average change = higher stability = higher risk score
                    stability_risk_score = max(0, 10 - avg_change * 200)  # 5% avg change = 0 score
                    risk_components.append(stability_risk_score)
            
            # Calculate final risk score
            if risk_components:
                risk_score = mean(risk_components)
            else:
                risk_score = 5.0
            
            return min(10.0, max(0.0, risk_score))
            
        except Exception as e:
            logger.error(f"Error calculating risk score: {e}")
            return 5.0
    
    async def _calculate_trend_strength(self, market_data: List[Dict]) -> float:
        """Calculate trend strength (0-1 scale)"""
        try:
            if len(market_data) < 20:
                return 0.5
            
            prices = [float(d['close_price']) for d in market_data[-20:]]  # Last 20 data points
            
            # Linear regression to find trend
            n = len(prices)
            x_vals = list(range(n))
            
            # Calculate slope using linear regression
            x_mean = mean(x_vals)
            y_mean = mean(prices)
            
            numerator = sum((x_vals[i] - x_mean) * (prices[i] - y_mean) for i in range(n))
            denominator = sum((x_vals[i] - x_mean) ** 2 for i in range(n))
            
            if denominator == 0:
                return 0.5
            
            slope = numerator / denominator
            
            # Normalize slope to 0-1 scale
            # Consider the price range to normalize slope
            price_range = max(prices) - min(prices)
            if price_range > 0:
                normalized_slope = abs(slope) / (price_range / n)
                trend_strength = min(1.0, normalized_slope * 10)
            else:
                trend_strength = 0.5
            
            return trend_strength
            
        except Exception as e:
            logger.error(f"Error calculating trend strength: {e}")
            return 0.5

    async def _calculate_sentiment_score(self, symbol: str, base_asset: str) -> Tuple[float, Dict[str, Any]]:
        """Calculate sentiment score (0-10 scale) using symbol and global sentiment feeds."""
        try:
            symbol_key = base_asset.upper() if base_asset else symbol.upper()
            symbol_entries = await self.database.get_sentiment_entries(
                symbol=symbol_key,
                hours_back=self.sentiment_hours_back,
                limit=75,
            )

            if not symbol_entries and symbol_key != symbol.upper():
                symbol_entries = await self.database.get_sentiment_entries(
                    symbol=symbol.upper(),
                    hours_back=self.sentiment_hours_back,
                    limit=75,
                )

            global_entries = await self.database.get_sentiment_entries(
                sentiment_types=list(self.global_sentiment_types),
                hours_back=self.sentiment_hours_back,
                limit=75,
            )

            symbol_polarities: List[float] = []
            symbol_classes: List[str] = []
            symbol_samples: List[Dict[str, Any]] = []
            latest_symbol_ts: Optional[datetime] = None

            for entry in symbol_entries:
                polarity = self._extract_sentiment_polarity(entry)
                if polarity is not None:
                    symbol_polarities.append(polarity)

                classification = self._extract_sentiment_classification(entry)
                if classification:
                    symbol_classes.append(classification)

                timestamp = entry.get('timestamp')
                parsed_ts = self._parse_iso_timestamp(timestamp)
                if parsed_ts and (latest_symbol_ts is None or parsed_ts > latest_symbol_ts):
                    latest_symbol_ts = parsed_ts

                symbol_samples.append({
                    'source': entry.get('source'),
                    'type': entry.get('type'),
                    'classification': classification,
                    'timestamp': timestamp,
                })

            global_polarities: List[float] = []
            global_classes: List[str] = []
            global_samples: List[Dict[str, Any]] = []
            latest_global_ts: Optional[datetime] = None

            for entry in global_entries:
                polarity = self._extract_sentiment_polarity(entry)
                if polarity is None and entry.get('value') is not None:
                    polarity = self._fear_greed_to_polarity(entry.get('value'))
                if polarity is not None:
                    global_polarities.append(polarity)

                classification = self._extract_sentiment_classification(entry)
                if classification:
                    global_classes.append(classification)

                timestamp = entry.get('timestamp')
                parsed_ts = self._parse_iso_timestamp(timestamp)
                if parsed_ts and (latest_global_ts is None or parsed_ts > latest_global_ts):
                    latest_global_ts = parsed_ts

                global_samples.append({
                    'source': entry.get('source'),
                    'type': entry.get('type'),
                    'classification': classification,
                    'timestamp': timestamp,
                    'value': entry.get('value'),
                })

            avg_symbol_polarity = mean(symbol_polarities) if symbol_polarities else 0.0
            avg_global_polarity = mean(global_polarities) if global_polarities else 0.0

            if symbol_polarities and global_polarities:
                combined_polarity = avg_symbol_polarity * 0.6 + avg_global_polarity * 0.4
            elif symbol_polarities:
                combined_polarity = avg_symbol_polarity
            elif global_polarities:
                combined_polarity = avg_global_polarity
            else:
                combined_polarity = 0.0

            sentiment_score = self._polarity_to_score(combined_polarity)

            if any(cls in {"extremely_bullish", "bullish"} for cls in symbol_classes):
                sentiment_score = min(10.0, sentiment_score + 0.5)
            if any(cls in {"extremely_bearish", "bearish"} for cls in symbol_classes):
                sentiment_score = max(0.0, sentiment_score - 1.5)

            metadata = {
                'avg_symbol_polarity': avg_symbol_polarity,
                'avg_global_polarity': avg_global_polarity,
                'combined_polarity': combined_polarity,
                'symbol_sample_count': len(symbol_entries),
                'global_sample_count': len(global_entries),
                'latest_symbol_timestamp': latest_symbol_ts.isoformat() if latest_symbol_ts else None,
                'latest_global_timestamp': latest_global_ts.isoformat() if latest_global_ts else None,
                'symbol_samples': symbol_samples[:5],
                'global_samples': global_samples[:5],
                'classifications': {
                    'symbol': symbol_classes[:5],
                    'global': global_classes[:5],
                }
            }

            return sentiment_score, metadata

        except Exception as e:
            logger.error(
                "Error calculating sentiment score",
                symbol=symbol,
                base_asset=base_asset,
                error=str(e)
            )
            return 5.0, {
                'avg_symbol_polarity': 0.0,
                'avg_global_polarity': 0.0,
                'combined_polarity': 0.0,
                'error': str(e)
            }

    @staticmethod
    def _polarity_to_score(polarity: float) -> float:
        """Convert polarity in [-1, 1] to score in [0, 10]."""
        return min(10.0, max(0.0, (polarity + 1.0) * 5.0))

    @staticmethod
    def _extract_sentiment_polarity(entry: Dict[str, Any]) -> Optional[float]:
        if not entry:
            return None

        if entry.get('aggregated_score') is not None:
            try:
                return float(entry['aggregated_score'])
            except (TypeError, ValueError):
                return None

        aggregated = entry.get('aggregated_sentiment')
        if isinstance(aggregated, dict):
            for key in ('average_polarity', 'polarity', 'aggregated_score'):
                value = aggregated.get(key)
                if value is not None:
                    try:
                        return float(value)
                    except (TypeError, ValueError):
                        continue

        for key in ('polarity', 'sentiment_score', 'score'):
            value = entry.get(key)
            if value is not None:
                try:
                    value_float = float(value)
                except (TypeError, ValueError):
                    continue
                if key in {'sentiment_score', 'score'} and abs(value_float) > 1.0:
                    value_float = max(-1.0, min(1.0, value_float / 100.0))
                return value_float

        metadata = entry.get('metadata')
        if isinstance(metadata, dict):
            meta_value = metadata.get('polarity') or metadata.get('average_polarity')
            if meta_value is not None:
                try:
                    return float(meta_value)
                except (TypeError, ValueError):
                    return None

        return None

    @staticmethod
    def _extract_sentiment_classification(entry: Dict[str, Any]) -> Optional[str]:
        if not entry:
            return None

        classification = entry.get('classification')
        if classification:
            return classification

        aggregated = entry.get('aggregated_sentiment')
        if isinstance(aggregated, dict):
            aggregated_class = aggregated.get('overall_category') or aggregated.get('classification')
            if aggregated_class:
                return aggregated_class

        metadata = entry.get('metadata')
        if isinstance(metadata, dict):
            meta_class = metadata.get('classification')
            if meta_class:
                return meta_class

        return None

    @staticmethod
    def _parse_iso_timestamp(value: Any) -> Optional[datetime]:
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace('Z', '+00:00'))
            except ValueError:
                return None
        return None

    @staticmethod
    def _fear_greed_to_polarity(value: Any) -> Optional[float]:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return None
        polarity = (numeric - 50.0) / 50.0
        return max(-1.0, min(1.0, polarity))
    
    def _generate_selection_reason(
        self,
        vol_score: float,
        volume_score: float,
        momentum_score: float,
        technical_score: float,
        market_cap_score: float,
        risk_score: float,
        sentiment_score: float,
    ) -> str:
        """Generate human-readable selection reason"""
        try:
            reasons = []
            
            # Identify strongest factors
            scores = {
                'high volatility': vol_score,
                'strong volume': volume_score,
                'momentum signals': momentum_score,
                'technical indicators': technical_score,
                'market stability': market_cap_score,
                'risk profile': risk_score,
                'bullish sentiment': sentiment_score
            }
            
            # Get top 2-3 factors
            sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
            
            for factor, score in sorted_scores[:3]:
                if score >= 7.0:
                    reasons.append(factor)
            
            if not reasons:
                reasons.append("balanced metrics")
            
            return f"Selected for {', '.join(reasons[:2])}"
            
        except Exception as e:
            logger.error(f"Error generating selection reason: {e}")
            return "comprehensive analysis"
    
    def _passes_selection_criteria(self, candidate: CryptoCandidate) -> bool:
        """Check if candidate passes minimum selection criteria"""
        try:
            # Minimum overall score
            if candidate.score < 5.0:
                return False
            
            # Risk threshold checks
            if candidate.risk_score < 3.0:  # Too risky
                return False
            
            # Require minimum sentiment alignment to avoid negative regimes
            if candidate.sentiment_score < self.min_sentiment_score:
                return False

            # Volume threshold (checked in metadata)
            if 'avg_volume_7d' in candidate.metadata:
                if candidate.metadata['avg_volume_7d'] < self.min_volume_24h * 0.1:  # Very low volume
                    return False
            
            # Exclude stablecoins and similar
            excluded_assets = {'USDT', 'USDC', 'BUSD', 'DAI', 'TUSD', 'PAX'}
            if candidate.base_asset in excluded_assets:
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error checking selection criteria: {e}")
            return False
    
    def _select_top_cryptocurrencies(self, candidates: List[CryptoCandidate]) -> List[CryptoCandidate]:
        """Select top cryptocurrencies from candidates"""
        try:
            # Sort by overall score (descending)
            sorted_candidates = sorted(candidates, key=lambda x: x.score, reverse=True)
            
            # Select top N, ensuring diversity
            selected = []
            selected_base_assets = set()
            
            for candidate in sorted_candidates:
                # Avoid duplicate base assets (e.g., both BTCUSDT and BTCUSDC)
                if candidate.base_asset not in selected_base_assets:
                    selected.append(candidate)
                    selected_base_assets.add(candidate.base_asset)
                    
                    if len(selected) >= self.max_selections:
                        break
            
            return selected
            
        except Exception as e:
            logger.error(f"Error selecting top cryptocurrencies: {e}")
            return candidates[:self.max_selections] if candidates else []
    
    async def _store_daily_selections(self, selected_cryptos: List[CryptoCandidate]) -> bool:
        """Store daily selections in database for market_data_service access"""
        try:
            if not selected_cryptos:
                logger.warning("No cryptocurrencies selected to store")
                return False
            
            # Create selection document
            selection_document = {
                'id': f"crypto_selection_{int(datetime.now(timezone.utc).timestamp())}",
                'selection_date': datetime.now(timezone.utc).date().isoformat(),
                'selection_timestamp': datetime.now(timezone.utc).isoformat(),
                'total_analyzed': len(selected_cryptos),  # This should be total candidates analyzed
                'total_selected': len(selected_cryptos),
                'selection_criteria': {
                    'max_selections': self.max_selections,
                    'min_volume_24h': self.min_volume_24h,
                    'lookback_days': self.lookback_days,
                    'scoring_weights': self.scoring_weights,
                    'risk_thresholds': self.risk_thresholds
                },
                'selected_cryptos': [
                    {
                        'symbol': crypto.symbol,
                        'base_asset': crypto.base_asset,
                        'overall_score': crypto.score,
                        'volatility_score': crypto.volatility_score,
                        'volume_score': crypto.volume_score,
                        'momentum_score': crypto.momentum_score,
                        'technical_score': crypto.technical_score,
                        'market_cap_score': crypto.market_cap_score,
                        'risk_score': crypto.risk_score,
                        'sentiment_score': crypto.sentiment_score,
                        'trend_strength': crypto.trend_strength,
                        'selection_reason': crypto.selection_reason,
                        'metadata': crypto.metadata
                    }
                    for crypto in selected_cryptos
                ]
            }
            
            # Store in crypto_selections container
            container = self.database.db.get_container_client('crypto_selections')
            await container.create_item(selection_document)
            
            # Update symbol tracking for market data collection
            await self._update_symbol_tracking_for_selections(selected_cryptos)
            
            logger.info(
                f"Daily crypto selections stored successfully",
                selected_count=len(selected_cryptos),
                symbols=[c.symbol for c in selected_cryptos]
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Error storing daily selections: {e}")
            return False
    
    async def _ensure_historical_data_for_selections(self, selected_cryptos: List[CryptoCandidate]):
        """
        Ensure sufficient historical data is available in Cosmos DB for selected cryptocurrencies
        
        Args:
            selected_cryptos: List of selected cryptocurrency candidates
        """
        try:
            from market_data_client import MarketDataClient
            
            # Extract symbols from selected cryptos
            symbols = [crypto.symbol for crypto in selected_cryptos]
            
            logger.info(
                "Ensuring historical data availability for selected cryptocurrencies",
                symbols=symbols,
                count=len(symbols)
            )
            
            # Initialize market data client
            async with MarketDataClient(base_url="http://localhost:8000") as client:
                # Ensure historical data is available (will collect if missing)
                result = await client.ensure_historical_data_available(
                    symbols=symbols,
                    timeframes=['1m', '5m', '15m', '1h', '4h', '1d'],  # All supported timeframes
                    days_back=90,  # Get 90 days of historical data
                    force_refresh=False  # Only collect if data is missing
                )
                
                # Log results
                if result.get('status') == 'completed':
                    logger.info(
                        "Historical data availability ensured",
                        symbols_checked=result.get('symbols_checked', 0),
                        symbols_collected=result.get('symbols_collected', 0),
                        details=result.get('results', {})
                    )
                    
                    # Log individual symbol status
                    for symbol, symbol_result in result.get('results', {}).items():
                        if 'collection_result' in symbol_result:
                            logger.info(
                                f"Historical data collected for {symbol}",
                                timeframes=symbol_result.get('collection_result', {})
                            )
                        elif symbol_result.get('has_sufficient_data'):
                            logger.info(
                                f"Sufficient historical data exists for {symbol}",
                                records=symbol_result.get('record_count', 0)
                            )
                else:
                    logger.warning(
                        "Historical data collection completed with issues",
                        result=result
                    )
                    
        except ImportError:
            logger.warning("MarketDataClient not available, skipping historical data collection")
        except Exception as e:
            logger.error(f"Error ensuring historical data availability: {e}", exc_info=True)
            # Don't fail the selection process if data collection fails
    
    async def _update_symbol_tracking_for_selections(self, selected_cryptos: List[CryptoCandidate]):
        """Update symbol tracking to prioritize selected cryptocurrencies"""
        try:
            selected_symbols = {crypto.symbol for crypto in selected_cryptos}
            
            # Get current tracked symbols
            all_symbols = await self.database.get_all_symbols(include_inactive=True)
            
            for symbol_data in all_symbols:
                symbol = symbol_data['symbol']
                
                # Update priority and tracking status
                if symbol in selected_symbols:
                    # High priority for selected cryptos
                    updates = {
                        'tracking': True,
                        'priority': 1,  # Highest priority
                        'last_selected': datetime.now(timezone.utc).isoformat(),
                        'selected_for_trading': True
                    }
                else:
                    # Lower priority for non-selected
                    current_priority = symbol_data.get('priority', 2)
                    updates = {
                        'priority': max(2, current_priority),  # At least medium priority
                        'selected_for_trading': False
                    }
                
                # Update symbol tracking
                await self.database.update_symbol_tracking(symbol, updates)
            
            logger.info(f"Updated symbol tracking priorities for {len(selected_symbols)} selected cryptos")
            
        except Exception as e:
            logger.error(f"Error updating symbol tracking for selections: {e}")
    
    async def get_current_selections(self) -> Optional[Dict]:
        """Get current day's cryptocurrency selections"""
        try:
            container = self.database.db.get_container_client('crypto_selections')
            
            today = datetime.now(timezone.utc).date().isoformat()
            
            query = """
            SELECT * FROM c 
            WHERE c.selection_date = @date 
            ORDER BY c.selection_timestamp DESC 
            OFFSET 0 LIMIT 1
            """
            
            parameters = [{"name": "@date", "value": today}]
            
            async for item in container.query_items(
                query=query,
                parameters=parameters,
                enable_cross_partition_query=True
            ):
                return item
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting current selections: {e}")
            return None
    
    async def get_selection_history(self, days_back: int = 7) -> List[Dict]:
        """Get historical cryptocurrency selections"""
        try:
            container = self.database.db.get_container_client('crypto_selections')
            
            start_date = (datetime.now(timezone.utc) - timedelta(days=days_back)).date().isoformat()
            
            query = """
            SELECT * FROM c 
            WHERE c.selection_date >= @start_date 
            ORDER BY c.selection_timestamp DESC
            """
            
            parameters = [{"name": "@start_date", "value": start_date}]
            
            selections = []
            async for item in container.query_items(
                query=query,
                parameters=parameters,
                enable_cross_partition_query=True
            ):
                selections.append(item)
            
            return selections
            
        except Exception as e:
            logger.error(f"Error getting selection history: {e}")
            return []


# Convenience function for creating crypto selection engine
async def create_crypto_selection_engine(database: Database) -> CryptoSelectionEngine:
    """Create and initialize crypto selection engine"""
    engine = CryptoSelectionEngine(database)
    return engine