"""
Real-Time Signal Aggregation Service

This module aggregates signals from multiple data sources:
- Price action and technical indicators
- Social sentiment (Twitter, Reddit, LunarCrush)
- On-chain metrics (Glassnode, Moralis)
- Institutional flow signals (whale alerts, unusual volume)

Combines all signals into MarketSignalAggregate messages for strategy consumption.
Publishes aggregated signals every 1 minute to RabbitMQ.
"""

import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import structlog
import aio_pika

# Import message schemas
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from shared.message_schemas import (
    MarketSignalAggregate,
    TrendDirection,
    SignalStrength,
    serialize_message,
    RoutingKeys
)
from shared.cache_decorators import cached, simple_key

logger = structlog.get_logger()


class SignalAggregator:
    """
    Aggregates signals from multiple data sources into unified market signals
    
    Signal Sources:
    1. Price Action: Technical indicators (RSI, MACD, moving averages)
    2. Social Sentiment: Twitter/Reddit sentiment scores
    3. On-Chain: NVT, MVRV, exchange flows
    4. Institutional: Whale alerts, block trades
    
    Output: MarketSignalAggregate published every 60 seconds
    """
    
    def __init__(self, database, rabbitmq_channel: aio_pika.Channel, redis_cache=None):
        self.database = database
        self.rabbitmq_channel = rabbitmq_channel
        self.redis_cache = redis_cache
        self.logger = logger.bind(component="signal_aggregator")
        
        # Configuration
        self.update_interval = 60  # seconds
        self.lookback_minutes = 15  # How far back to look for signals
        
        # Signal weights (must sum to 1.0)
        self.weights = {
            "price": 0.35,      # Technical analysis
            "sentiment": 0.25,  # Social sentiment
            "onchain": 0.20,    # On-chain metrics
            "flow": 0.20        # Institutional flow
        }
        
        # Running state
        self.running = False
        self.task: Optional[asyncio.Task] = None
        
        # Cache for recent signals
        self.recent_whale_alerts: Dict[str, List] = {}  # symbol -> alerts
        self.recent_sentiment: Dict[str, dict] = {}     # symbol -> latest sentiment
        self.recent_onchain: Dict[str, dict] = {}       # symbol -> latest metrics
        self.cache_hits = 0
        self.cache_misses = 0
        
        self.logger.info("Signal aggregator initialized", 
                        update_interval=self.update_interval,
                        weights=self.weights)
    
    async def start(self):
        """Start the signal aggregation background task"""
        if self.running:
            self.logger.warning("Signal aggregator already running")
            return
        
        self.running = True
        self.task = asyncio.create_task(self._aggregation_loop())
        self.logger.info("Signal aggregator started")
    
    async def stop(self):
        """Stop the signal aggregation task"""
        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        self.logger.info("Signal aggregator stopped")
    
    async def _aggregation_loop(self):
        """Main aggregation loop - runs every minute"""
        while self.running:
            try:
                # Get active symbols from database
                symbols = await self._get_active_symbols()
                
                # Aggregate signals for each symbol
                for symbol in symbols:
                    try:
                        signal = await self._aggregate_signal_for_symbol(symbol)
                        if signal:
                            await self._publish_signal(signal)
                    except Exception as e:
                        self.logger.error("Error aggregating signal", 
                                        symbol=symbol, error=str(e))
                
                # Wait before next update
                await asyncio.sleep(self.update_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error("Error in aggregation loop", error=str(e))
                await asyncio.sleep(5)  # Brief pause before retry
    
    async def _get_active_symbols(self) -> List[str]:
        """Get list of active trading symbols"""
        try:
            # Try to get from database symbols table (JSONB structure)
            query = "SELECT data->>'symbol' as symbol FROM symbols WHERE (data->>'tracking')::boolean = true"
            rows = await self.database._postgres.fetch(query)
            symbols = [row['symbol'] for row in rows]
            
            if not symbols:
                # Fallback to default symbols
                symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]
                self.logger.warning("No symbols in database, using defaults", 
                                  symbols=symbols)
            
            return symbols
        except Exception as e:
            self.logger.error("Error getting active symbols", error=str(e))
            return ["BTCUSDT", "ETHUSDT"]  # Minimal fallback
    
    async def _aggregate_signal_for_symbol(self, symbol: str) -> Optional[MarketSignalAggregate]:
        """
        Aggregate all signals for a specific symbol
        
        Returns MarketSignalAggregate or None if insufficient data
        """
        try:
            # Gather component signals
            price_signal = await self._get_price_signal(symbol)
            sentiment_signal = await self._get_sentiment_signal(symbol)
            onchain_signal = await self._get_onchain_signal(symbol)
            flow_signal = await self._get_flow_signal(symbol)
            
            # Calculate overall signal
            overall_signal, overall_strength, confidence = self._calculate_overall_signal(
                price_signal, sentiment_signal, onchain_signal, flow_signal
            )
            
            # Determine recommended action
            recommended_action = self._determine_action(overall_signal, overall_strength, confidence)
            position_size_modifier = self._calculate_position_modifier(overall_strength, confidence)
            
            # Calculate volatility and risk
            volatility = await self._get_current_volatility(symbol)
            risk_level = self._assess_risk_level(volatility, overall_strength)
            
            # Build aggregate signal
            signal = MarketSignalAggregate(
                signal_id=f"agg_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{symbol.lower()}",
                symbol=symbol,
                overall_signal=overall_signal,
                signal_strength=overall_strength,
                confidence=confidence,
                
                # Component signals
                price_signal=price_signal.get('direction') if price_signal else None,
                price_strength=price_signal.get('strength') if price_signal else None,
                sentiment_signal=sentiment_signal.get('direction') if sentiment_signal else None,
                sentiment_strength=sentiment_signal.get('strength') if sentiment_signal else None,
                onchain_signal=onchain_signal.get('direction') if onchain_signal else None,
                onchain_strength=onchain_signal.get('strength') if onchain_signal else None,
                flow_signal=flow_signal.get('direction') if flow_signal else None,
                flow_strength=flow_signal.get('strength') if flow_signal else None,
                
                # Weights
                component_weights=self.weights.copy(),
                
                # Risk indicators
                volatility=volatility,
                risk_level=risk_level,
                
                # Trading recommendation
                recommended_action=recommended_action,
                position_size_modifier=position_size_modifier,
                
                timestamp=datetime.utcnow()
            )
            
            return signal
            
        except Exception as e:
            self.logger.error("Error aggregating signal for symbol", 
                            symbol=symbol, error=str(e))
            return None
    
    @cached(prefix='price_signal', ttl=45, key_func=simple_key(0))  # Cache for 45 seconds
    async def _get_price_signal(self, symbol: str) -> Optional[dict]:
        """
        Get price action signal from technical indicators
        
        Returns: {'direction': TrendDirection, 'strength': float, 'indicators': dict}
        """
        try:
            # Get recent indicators from database (JSONB structure in indicator_results table)
            query = """
                SELECT 
                    data->>'indicator_name' as indicator_name,
                    (data->>'value')::float as value,
                    (data->>'timestamp')::timestamp as timestamp
                FROM indicator_results
                WHERE data->>'symbol' = $1 AND (data->>'timestamp')::timestamp > $2
                ORDER BY (data->>'timestamp')::timestamp DESC
            """
            cutoff = datetime.utcnow() - timedelta(minutes=self.lookback_minutes)
            rows = await self.database._postgres.fetch(query, symbol, cutoff)
            
            if not rows:
                return None
            
            # Extract key indicators
            indicators = {}
            for row in rows:
                name = row['indicator_name']
                if name not in indicators:  # Take most recent
                    indicators[name] = row['value']
            
            # Analyze indicators
            bullish_signals = 0
            bearish_signals = 0
            total_signals = 0
            
            # RSI analysis
            if 'rsi' in indicators:
                rsi = indicators['rsi']
                total_signals += 1
                if rsi < 30:
                    bullish_signals += 1  # Oversold
                elif rsi > 70:
                    bearish_signals += 1  # Overbought
                elif 40 <= rsi <= 60:
                    bullish_signals += 0.5
                    bearish_signals += 0.5  # Neutral
            
            # MACD analysis
            if 'macd' in indicators and 'macd_signal' in indicators:
                total_signals += 1
                if indicators['macd'] > indicators['macd_signal']:
                    bullish_signals += 1
                else:
                    bearish_signals += 1
            
            # Moving average analysis
            if 'sma_20' in indicators and 'sma_50' in indicators:
                total_signals += 1
                if indicators['sma_20'] > indicators['sma_50']:
                    bullish_signals += 1  # Golden cross tendency
                else:
                    bearish_signals += 1  # Death cross tendency
            
            # Bollinger Bands analysis
            if all(k in indicators for k in ['bb_upper', 'bb_lower', 'close']):
                total_signals += 1
                close = indicators['close']
                bb_upper = indicators['bb_upper']
                bb_lower = indicators['bb_lower']
                bb_range = bb_upper - bb_lower
                
                if close < bb_lower + (bb_range * 0.2):
                    bullish_signals += 1  # Near lower band
                elif close > bb_upper - (bb_range * 0.2):
                    bearish_signals += 1  # Near upper band
            
            if total_signals == 0:
                return None
            
            # Calculate direction and strength
            bullish_ratio = bullish_signals / total_signals
            bearish_ratio = bearish_signals / total_signals
            
            if bullish_ratio > bearish_ratio + 0.2:
                direction = TrendDirection.BULLISH
                strength = min(bullish_ratio, 1.0)
            elif bearish_ratio > bullish_ratio + 0.2:
                direction = TrendDirection.BEARISH
                strength = min(bearish_ratio, 1.0)
            else:
                direction = TrendDirection.NEUTRAL
                strength = 0.5
            
            return {
                'direction': direction,
                'strength': strength,
                'indicators': indicators,
                'analysis': {
                    'bullish_signals': bullish_signals,
                    'bearish_signals': bearish_signals,
                    'total_signals': total_signals
                }
            }
            
        except Exception as e:
            self.logger.error("Error getting price signal", symbol=symbol, error=str(e))
            return None
    
    @cached(prefix='sentiment_signal', ttl=60, key_func=simple_key(0))
    async def _get_sentiment_signal(self, symbol: str) -> Optional[dict]:
        """
        Get social sentiment signal
        
        Returns: {'direction': TrendDirection, 'strength': float, 'sources': dict}
        """
        try:
            # Get recent sentiment data (JSONB structure)
            query = """
                SELECT 
                    data->>'source' as source,
                    (data->>'sentiment_score')::float as sentiment_score,
                    (data->>'social_volume')::float as social_volume,
                    (data->>'timestamp')::timestamp as timestamp
                FROM sentiment_data
                WHERE data->>'symbol' = $1 AND (data->>'timestamp')::timestamp > $2
                ORDER BY (data->>'timestamp')::timestamp DESC
                LIMIT 10
            """
            cutoff = datetime.utcnow() - timedelta(hours=1)
            rows = await self.database._postgres.fetch(query, symbol, cutoff)
            
            if not rows:
                return None
            
            # Aggregate sentiment by source
            sentiment_by_source = {}
            for row in rows:
                source = row['source']
                if source not in sentiment_by_source:
                    sentiment_by_source[source] = {
                        'score': row['sentiment_score'],
                        'volume': row['social_volume']
                    }
            
            if not sentiment_by_source:
                return None
            
            # Calculate weighted average sentiment
            total_volume = sum(s['volume'] for s in sentiment_by_source.values())
            if total_volume == 0:
                # Equal weight if no volume data
                avg_sentiment = sum(s['score'] for s in sentiment_by_source.values()) / len(sentiment_by_source)
            else:
                # Volume-weighted average
                avg_sentiment = sum(
                    s['score'] * s['volume'] for s in sentiment_by_source.values()
                ) / total_volume
            
            # Determine direction and strength
            if avg_sentiment > 0.2:
                direction = TrendDirection.BULLISH
                strength = min(abs(avg_sentiment), 1.0)
            elif avg_sentiment < -0.2:
                direction = TrendDirection.BEARISH
                strength = min(abs(avg_sentiment), 1.0)
            else:
                direction = TrendDirection.NEUTRAL
                strength = 0.5
            
            return {
                'direction': direction,
                'strength': strength,
                'avg_sentiment': avg_sentiment,
                'sources': sentiment_by_source
            }
            
        except Exception as e:
            self.logger.error("Error getting sentiment signal", symbol=symbol, error=str(e))
            return None
    
    async def _get_onchain_signal(self, symbol: str) -> Optional[dict]:
        """
        Get on-chain metrics signal
        
        Returns: {'direction': TrendDirection, 'strength': float, 'metrics': dict}
        """
        try:
            # Only applicable to crypto with on-chain data
            if not symbol.endswith('USDT'):
                return None
            
            base_symbol = symbol.replace('USDT', '').replace('USDC', '')
            
            # Get recent on-chain metrics (JSONB structure)
            query = """
                SELECT 
                    data->>'metric_name' as metric_name,
                    (data->>'value')::float as value,
                    data->>'signal' as signal,
                    (data->>'timestamp')::timestamp as timestamp
                FROM onchain_metrics
                WHERE data->>'symbol' = $1 AND (data->>'timestamp')::timestamp > $2
                ORDER BY (data->>'timestamp')::timestamp DESC
            """
            cutoff = datetime.utcnow() - timedelta(hours=4)
            rows = await self.database._postgres.fetch(query, base_symbol, cutoff)
            
            if not rows:
                return None
            
            # Extract metrics
            metrics = {}
            signals = []
            for row in rows:
                name = row['metric_name']
                if name not in metrics:
                    metrics[name] = row['value']
                    if row['signal']:
                        signals.append(row['signal'])
            
            if not signals:
                return None
            
            # Count signal directions
            bullish = sum(1 for s in signals if s.lower() == 'bullish')
            bearish = sum(1 for s in signals if s.lower() == 'bearish')
            neutral = sum(1 for s in signals if s.lower() == 'neutral')
            total = len(signals)
            
            # Determine overall direction
            if bullish > bearish + 1:
                direction = TrendDirection.BULLISH
                strength = bullish / total
            elif bearish > bullish + 1:
                direction = TrendDirection.BEARISH
                strength = bearish / total
            else:
                direction = TrendDirection.NEUTRAL
                strength = 0.5
            
            return {
                'direction': direction,
                'strength': strength,
                'metrics': metrics,
                'signal_counts': {
                    'bullish': bullish,
                    'bearish': bearish,
                    'neutral': neutral
                }
            }
            
        except Exception as e:
            self.logger.error("Error getting on-chain signal", symbol=symbol, error=str(e))
            return None
    
    async def _get_flow_signal(self, symbol: str) -> Optional[dict]:
        """
        Get institutional flow signal from whale alerts
        
        Returns: {'direction': TrendDirection, 'strength': float, 'alerts': list}
        """
        try:
            # Get recent whale alerts
            query = """
                SELECT alert_type, amount_usd, significance_score, timestamp
                FROM whale_alerts
                WHERE symbol = $1 AND timestamp > $2
                ORDER BY timestamp DESC
                LIMIT 20
            """
            cutoff = datetime.utcnow() - timedelta(hours=2)
            rows = await self.database._postgres.fetch(query, symbol, cutoff)
            
            if not rows:
                return None
            
            # Analyze whale activity
            bullish_flow = 0.0
            bearish_flow = 0.0
            
            for row in rows:
                alert_type = row['alert_type']
                significance = row['significance_score']
                
                if alert_type == 'exchange_outflow':
                    # Outflow = accumulation (bullish)
                    bullish_flow += significance
                elif alert_type == 'exchange_inflow':
                    # Inflow = potential selling (bearish)
                    bearish_flow += significance
                elif alert_type == 'whale_accumulation':
                    bullish_flow += significance * 1.2
                elif alert_type == 'whale_distribution':
                    bearish_flow += significance * 1.2
            
            if bullish_flow == 0 and bearish_flow == 0:
                return None
            
            # Determine direction
            total_flow = bullish_flow + bearish_flow
            bullish_ratio = bullish_flow / total_flow
            bearish_ratio = bearish_flow / total_flow
            
            if bullish_ratio > 0.6:
                direction = TrendDirection.BULLISH
                strength = min(bullish_ratio, 1.0)
            elif bearish_ratio > 0.6:
                direction = TrendDirection.BEARISH
                strength = min(bearish_ratio, 1.0)
            else:
                direction = TrendDirection.NEUTRAL
                strength = 0.5
            
            return {
                'direction': direction,
                'strength': strength,
                'bullish_flow': bullish_flow,
                'bearish_flow': bearish_flow,
                'alert_count': len(rows)
            }
            
        except Exception as e:
            self.logger.error("Error getting flow signal", symbol=symbol, error=str(e))
            return None
    
    def _calculate_overall_signal(
        self, 
        price_signal: Optional[dict],
        sentiment_signal: Optional[dict],
        onchain_signal: Optional[dict],
        flow_signal: Optional[dict]
    ) -> tuple[TrendDirection, SignalStrength, float]:
        """
        Calculate overall signal from component signals
        
        Returns: (overall_direction, signal_strength, confidence)
        """
        # Calculate weighted scores
        bullish_score = 0.0
        bearish_score = 0.0
        total_weight = 0.0
        
        signals = {
            'price': price_signal,
            'sentiment': sentiment_signal,
            'onchain': onchain_signal,
            'flow': flow_signal
        }
        
        for name, signal in signals.items():
            if signal:
                weight = self.weights[name]
                strength = signal['strength']
                direction = signal['direction']
                
                if direction == TrendDirection.BULLISH:
                    bullish_score += weight * strength
                elif direction == TrendDirection.BEARISH:
                    bearish_score += weight * strength
                else:  # NEUTRAL
                    bullish_score += weight * strength * 0.5
                    bearish_score += weight * strength * 0.5
                
                total_weight += weight
        
        if total_weight == 0:
            return TrendDirection.NEUTRAL, SignalStrength.WEAK, 0.0
        
        # Normalize scores
        bullish_score /= total_weight
        bearish_score /= total_weight
        
        # Determine overall direction
        diff = abs(bullish_score - bearish_score)
        
        if bullish_score > bearish_score:
            direction = TrendDirection.BULLISH
            raw_strength = bullish_score
        elif bearish_score > bullish_score:
            direction = TrendDirection.BEARISH
            raw_strength = bearish_score
        else:
            direction = TrendDirection.NEUTRAL
            raw_strength = 0.5
        
        # Determine signal strength category
        if diff < 0.15:
            strength_category = SignalStrength.WEAK
        elif diff < 0.35:
            strength_category = SignalStrength.MODERATE
        elif diff < 0.55:
            strength_category = SignalStrength.STRONG
        else:
            strength_category = SignalStrength.VERY_STRONG
        
        # Confidence based on signal agreement
        available_signals = sum(1 for s in signals.values() if s is not None)
        confidence = (total_weight / sum(self.weights.values())) * min(raw_strength * 1.2, 1.0)
        
        return direction, strength_category, confidence
    
    def _determine_action(
        self, 
        direction: TrendDirection, 
        strength: SignalStrength,
        confidence: float
    ) -> str:
        """Determine recommended trading action"""
        if confidence < 0.5:
            return "wait"
        
        if direction == TrendDirection.BULLISH:
            if strength in [SignalStrength.STRONG, SignalStrength.VERY_STRONG]:
                return "buy"
            elif strength == SignalStrength.MODERATE and confidence > 0.65:
                return "buy"
            else:
                return "hold"
        elif direction == TrendDirection.BEARISH:
            if strength in [SignalStrength.STRONG, SignalStrength.VERY_STRONG]:
                return "sell"
            elif strength == SignalStrength.MODERATE and confidence > 0.65:
                return "sell"
            else:
                return "hold"
        else:
            return "hold"
    
    def _calculate_position_modifier(self, strength: SignalStrength, confidence: float) -> float:
        """
        Calculate position size modifier
        
        Returns multiplier between 0.5 and 1.5
        """
        base_modifier = 1.0
        
        # Strength adjustment
        if strength == SignalStrength.VERY_STRONG:
            base_modifier = 1.3
        elif strength == SignalStrength.STRONG:
            base_modifier = 1.15
        elif strength == SignalStrength.MODERATE:
            base_modifier = 1.0
        else:  # WEAK
            base_modifier = 0.8
        
        # Confidence adjustment
        confidence_modifier = 0.5 + (confidence * 0.5)  # Range: 0.5 to 1.0
        
        # Combined modifier
        final_modifier = base_modifier * confidence_modifier
        
        # Clamp to reasonable range
        return max(0.5, min(1.5, final_modifier))
    
    async def _get_current_volatility(self, symbol: str) -> Optional[float]:
        """Get current volatility estimate"""
        try:
            # Query indicator_results JSONB table
            query = """
                SELECT (data->>'value')::float as value 
                FROM indicator_results
                WHERE data->>'symbol' = $1 AND data->>'indicator_name' = 'atr'
                ORDER BY (data->>'timestamp')::timestamp DESC LIMIT 1
            """
            row = await self.database._postgres.fetchrow(query, symbol)
            if row:
                return float(row['value'])
            return None
        except Exception:
            return None
    
    def _assess_risk_level(self, volatility: Optional[float], strength: SignalStrength) -> str:
        """Assess overall risk level"""
        if volatility is None:
            return "medium"
        
        # Volatility thresholds (ATR as percentage)
        if volatility > 0.05:  # 5% ATR
            risk = "high"
        elif volatility > 0.03:  # 3% ATR
            risk = "medium"
        else:
            risk = "low"
        
        # Adjust for signal strength
        if strength in [SignalStrength.VERY_STRONG, SignalStrength.STRONG]:
            # Strong signals reduce perceived risk
            if risk == "high":
                risk = "medium"
            elif risk == "medium":
                risk = "low"
        
        return risk
    
    async def _publish_signal(self, signal: MarketSignalAggregate):
        """Publish aggregated signal to RabbitMQ and store in Redis buffer"""
        try:
            # Determine routing key based on strength
            if signal.signal_strength in [SignalStrength.STRONG, SignalStrength.VERY_STRONG]:
                routing_key = RoutingKeys.MARKET_SIGNAL_STRONG
            else:
                routing_key = RoutingKeys.MARKET_SIGNAL
            
            # Serialize and publish
            message = aio_pika.Message(
                body=serialize_message(signal).encode(),
                content_type="application/json",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT
            )
            
            await self.rabbitmq_channel.default_exchange.publish(
                message,
                routing_key=routing_key
            )
            
            # Store signal in Redis buffer for fast retrieval
            await self._buffer_signal_in_redis(signal)
            
            self.logger.info(
                "Published market signal",
                symbol=signal.symbol,
                direction=signal.overall_signal.value,
                strength=signal.signal_strength.value,
                confidence=f"{signal.confidence:.2f}",
                action=signal.recommended_action
            )
            
        except Exception as e:
            self.logger.error("Error publishing signal", 
                            symbol=signal.symbol, error=str(e))
    
    async def _buffer_signal_in_redis(self, signal: MarketSignalAggregate):
        """
        Store signal in Redis sorted set for fast retrieval
        
        Maintains last 1000 signals with 24-hour TTL
        Uses timestamp as score for chronological ordering
        """
        if not self.redis_cache:
            return  # Redis not available
        
        try:
            # Serialize signal to JSON
            signal_json = serialize_message(signal)
            
            # Use timestamp as score for sorting
            score = signal.timestamp.timestamp()
            
            # Add to sorted set
            redis_key = "signals:recent"
            await self.redis_cache.zadd(
                redis_key,
                {signal_json: score}
            )
            
            # Keep only last 1000 signals (remove oldest)
            count = await self.redis_cache.zcard(redis_key)
            if count > 1000:
                # Remove oldest signals beyond 1000
                remove_count = count - 1000
                await self.redis_cache.zremrangebyrank(redis_key, 0, remove_count - 1)
            
            # Set TTL to 24 hours
            await self.redis_cache.expire(redis_key, 86400)  # 24 hours
            
            self.logger.debug(
                "Signal buffered in Redis",
                signal_id=signal.signal_id,
                symbol=signal.symbol,
                buffer_size=count
            )
            
        except Exception as e:
            # Don't fail if Redis buffering fails
            self.logger.warning("Failed to buffer signal in Redis", 
                              signal_id=signal.signal_id, error=str(e))
    
    async def get_recent_signals(
        self, 
        symbol: Optional[str] = None,
        limit: int = 100,
        hours_back: Optional[int] = None
    ) -> List[MarketSignalAggregate]:
        """
        Retrieve recent signals from Redis buffer
        
        Args:
            symbol: Filter by symbol (None = all symbols)
            limit: Maximum number of signals to return
            hours_back: Only return signals from last N hours (None = no time filter)
        
        Returns:
            List of MarketSignalAggregate objects (most recent first)
        """
        if not self.redis_cache:
            self.logger.warning("Redis cache not available for signal retrieval")
            return []
        
        try:
            redis_key = "signals:recent"
            
            # Calculate time filter if needed
            min_score = 0
            if hours_back:
                cutoff_time = datetime.utcnow() - timedelta(hours=hours_back)
                min_score = cutoff_time.timestamp()
            
            # Get signals from sorted set (most recent first)
            # zrange with negative indices gets from end (most recent)
            if min_score > 0:
                # Use zrangebyscore for time filtering
                signals_json = await self.redis_cache.redis.zrangebyscore(
                    redis_key,
                    min_score,
                    '+inf',
                    start=0,
                    num=limit
                )
            else:
                # Get last N signals
                signals_json = await self.redis_cache.zrange(
                    redis_key,
                    -limit,  # From end
                    -1       # To end
                )
            
            # Deserialize signals
            signals = []
            for signal_json in reversed(signals_json):  # Reverse to get newest first
                try:
                    signal_dict = json.loads(signal_json) if isinstance(signal_json, str) else signal_json
                    
                    # Filter by symbol if specified
                    if symbol and signal_dict.get('symbol') != symbol:
                        continue
                    
                    # Parse back to MarketSignalAggregate
                    signal = MarketSignalAggregate(**signal_dict)
                    signals.append(signal)
                    
                except Exception as e:
                    self.logger.warning("Failed to deserialize signal", error=str(e))
                    continue
            
            self.logger.debug(
                "Retrieved signals from Redis",
                count=len(signals),
                symbol=symbol,
                limit=limit
            )
            
            return signals[:limit]  # Ensure we don't exceed limit
            
        except Exception as e:
            self.logger.error("Error retrieving signals from Redis", error=str(e))
            return []
    
    async def get_signal_statistics(self, symbol: str, hours: int = 24) -> Dict[str, Any]:
        """
        Get statistics about recent signals for a symbol
        
        Args:
            symbol: Trading pair symbol
            hours: Number of hours to analyze
        
        Returns:
            Dictionary with signal statistics
        """
        signals = await self.get_recent_signals(symbol=symbol, hours_back=hours, limit=1000)
        
        if not signals:
            return {
                'symbol': symbol,
                'period_hours': hours,
                'total_signals': 0,
                'error': 'No signals found'
            }
        
        # Calculate statistics
        total = len(signals)
        bullish = sum(1 for s in signals if s.overall_signal == TrendDirection.BULLISH)
        bearish = sum(1 for s in signals if s.overall_signal == TrendDirection.BEARISH)
        neutral = sum(1 for s in signals if s.overall_signal == TrendDirection.NEUTRAL)
        
        avg_confidence = sum(s.confidence for s in signals) / total
        
        strong_signals = sum(1 for s in signals if s.signal_strength in [
            SignalStrength.STRONG, SignalStrength.VERY_STRONG
        ])
        
        # Action distribution
        actions = {}
        for s in signals:
            action = s.recommended_action or 'unknown'
            actions[action] = actions.get(action, 0) + 1
        
        return {
            'symbol': symbol,
            'period_hours': hours,
            'total_signals': total,
            'bullish_count': bullish,
            'bearish_count': bearish,
            'neutral_count': neutral,
            'bullish_percent': (bullish / total * 100) if total > 0 else 0,
            'bearish_percent': (bearish / total * 100) if total > 0 else 0,
            'average_confidence': round(avg_confidence, 3),
            'strong_signals_count': strong_signals,
            'strong_signals_percent': (strong_signals / total * 100) if total > 0 else 0,
            'action_distribution': actions,
            'latest_signal': {
                'direction': signals[0].overall_signal.value,
                'strength': signals[0].signal_strength.value,
                'confidence': signals[0].confidence,
                'action': signals[0].recommended_action,
                'timestamp': signals[0].timestamp.isoformat()
            } if signals else None
        }
