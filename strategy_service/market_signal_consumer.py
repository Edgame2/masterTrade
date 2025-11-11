"""
Market Signal Consumer for Strategy Service

Consumes market signals from RabbitMQ and triggers strategy evaluation/execution.
Processes: MarketSignalAggregate, WhaleAlertMessage, SocialSentimentUpdate
"""

import asyncio
from datetime import datetime
from typing import Dict, Optional
import structlog
import aio_pika

# Import message schemas
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from shared.message_schemas import (
    MarketSignalAggregate,
    WhaleAlertMessage,
    SocialSentimentUpdate,
    OnChainMetricUpdate,
    InstitutionalFlowSignal,
    deserialize_message,
    RoutingKeys
)

logger = structlog.get_logger()


class MarketSignalConsumer:
    """
    Consumes market signals and triggers strategy actions
    
    Subscribed to:
    - market.signal.* - Aggregated market signals
    - whale.alert.* - Large transaction alerts
    - sentiment.* - Social sentiment updates
    - onchain.* - On-chain metrics
    - institutional.* - Institutional flow signals
    """
    
    def __init__(
        self,
        rabbitmq_channel: aio_pika.Channel,
        strategy_service: 'StrategyService'
    ):
        """
        Initialize market signal consumer
        
        Args:
            rabbitmq_channel: RabbitMQ channel for consuming
            strategy_service: Reference to strategy service for triggering actions
        """
        self.channel = rabbitmq_channel
        self.strategy_service = strategy_service
        self.logger = logger.bind(component="market_signal_consumer")
        
        # Consumer queues
        self.queues = {}
        self.consumer_tags = {}
        
        # Signal statistics
        self.stats = {
            "market_signals_received": 0,
            "whale_alerts_received": 0,
            "sentiment_updates_received": 0,
            "onchain_updates_received": 0,
            "institutional_signals_received": 0,
            "strategy_triggers": 0,
            "last_signal_time": None
        }
        
        self.running = False
    
    async def start(self):
        """Start consuming messages from all queues"""
        if self.running:
            self.logger.warning("Market signal consumer already running")
            return
        
        self.running = True
        
        try:
            # Declare and bind queues
            await self._setup_queues()
            
            # Start consuming
            await self._start_consumers()
            
            self.logger.info("Market signal consumer started successfully")
            
        except Exception as e:
            self.logger.error("Failed to start market signal consumer", error=str(e))
            self.running = False
            raise
    
    async def stop(self):
        """Stop consuming messages"""
        self.running = False
        
        try:
            # Cancel all consumers
            for queue_name, consumer_tag in self.consumer_tags.items():
                if consumer_tag and queue_name in self.queues:
                    await self.queues[queue_name].cancel(consumer_tag)
                    self.logger.info(f"Cancelled consumer for {queue_name}")
            
            self.logger.info("Market signal consumer stopped")
            
        except Exception as e:
            self.logger.error("Error stopping market signal consumer", error=str(e))
    
    async def _setup_queues(self):
        """Declare and bind queues for different message types"""
        
        # Declare the exchange (should already exist from market_data_service)
        exchange = await self.channel.declare_exchange(
            "mastertrade.market",
            aio_pika.ExchangeType.TOPIC,
            durable=True
        )
        
        # Market signals queue (aggregated signals)
        market_queue = await self.channel.declare_queue(
            "strategy_service_market_signals",
            durable=True,
            arguments={"x-message-ttl": 300000}  # 5 minutes TTL
        )
        await market_queue.bind(exchange, routing_key=RoutingKeys.MARKET_SIGNAL)
        await market_queue.bind(exchange, routing_key=RoutingKeys.MARKET_SIGNAL_STRONG)
        self.queues["market_signals"] = market_queue
        self.logger.info("Market signals queue configured")
        
        # Whale alerts queue
        whale_queue = await self.channel.declare_queue(
            "strategy_service_whale_alerts",
            durable=True,
            arguments={"x-message-ttl": 600000}  # 10 minutes TTL
        )
        await whale_queue.bind(exchange, routing_key=RoutingKeys.WHALE_ALERT)
        await whale_queue.bind(exchange, routing_key=RoutingKeys.WHALE_ALERT_HIGH_PRIORITY)
        self.queues["whale_alerts"] = whale_queue
        self.logger.info("Whale alerts queue configured")
        
        # Social sentiment queue
        sentiment_queue = await self.channel.declare_queue(
            "strategy_service_sentiment_updates",
            durable=True,
            arguments={"x-message-ttl": 300000}  # 5 minutes TTL
        )
        await sentiment_queue.bind(exchange, routing_key=RoutingKeys.SENTIMENT_UPDATE)
        await sentiment_queue.bind(exchange, routing_key=RoutingKeys.SENTIMENT_AGGREGATED)
        self.queues["sentiment_updates"] = sentiment_queue
        self.logger.info("Social sentiment queue configured")
        
        # On-chain metrics queue
        onchain_queue = await self.channel.declare_queue(
            "strategy_service_onchain_metrics",
            durable=True,
            arguments={"x-message-ttl": 600000}  # 10 minutes TTL
        )
        await onchain_queue.bind(exchange, routing_key=RoutingKeys.ONCHAIN_METRIC)
        await onchain_queue.bind(exchange, routing_key=RoutingKeys.ONCHAIN_EXCHANGE_FLOW)
        self.queues["onchain_metrics"] = onchain_queue
        self.logger.info("On-chain metrics queue configured")
        
        # Institutional flow queue
        institutional_queue = await self.channel.declare_queue(
            "strategy_service_institutional_flow",
            durable=True,
            arguments={"x-message-ttl": 300000}  # 5 minutes TTL
        )
        await institutional_queue.bind(exchange, routing_key=RoutingKeys.INSTITUTIONAL_FLOW)
        await institutional_queue.bind(exchange, routing_key=RoutingKeys.INSTITUTIONAL_BLOCK_TRADE)
        self.queues["institutional_flow"] = institutional_queue
        self.logger.info("Institutional flow queue configured")
    
    async def _start_consumers(self):
        """Start consuming from all queues"""
        
        # Market signals consumer
        self.consumer_tags["market_signals"] = await self.queues["market_signals"].consume(
            self._on_market_signal
        )
        
        # Whale alerts consumer
        self.consumer_tags["whale_alerts"] = await self.queues["whale_alerts"].consume(
            self._on_whale_alert
        )
        
        # Sentiment updates consumer
        self.consumer_tags["sentiment_updates"] = await self.queues["sentiment_updates"].consume(
            self._on_sentiment_update
        )
        
        # On-chain metrics consumer
        self.consumer_tags["onchain_metrics"] = await self.queues["onchain_metrics"].consume(
            self._on_onchain_metric
        )
        
        # Institutional flow consumer
        self.consumer_tags["institutional_flow"] = await self.queues["institutional_flow"].consume(
            self._on_institutional_flow
        )
        
        self.logger.info("All message consumers started")
    
    async def _on_market_signal(self, message: aio_pika.IncomingMessage):
        """Handle incoming market signal aggregates"""
        async with message.process():
            try:
                # Deserialize message
                signal = deserialize_message(MarketSignalAggregate, message.body.decode())
                
                self.stats["market_signals_received"] += 1
                self.stats["last_signal_time"] = datetime.utcnow()
                
                self.logger.info(
                    "Received market signal",
                    symbol=signal.symbol,
                    direction=signal.overall_signal.value,
                    strength=signal.signal_strength.value,
                    confidence=f"{signal.confidence:.2f}",
                    action=signal.recommended_action
                )
                
                # Update strategy service cache
                if hasattr(self.strategy_service, 'market_signals_cache'):
                    if signal.symbol not in self.strategy_service.market_signals_cache:
                        self.strategy_service.market_signals_cache[signal.symbol] = []
                    self.strategy_service.market_signals_cache[signal.symbol].append({
                        "signal": signal,
                        "received_at": datetime.utcnow()
                    })
                    # Keep only last 10 signals per symbol
                    self.strategy_service.market_signals_cache[signal.symbol] = \
                        self.strategy_service.market_signals_cache[signal.symbol][-10:]
                
                # Trigger strategy evaluation for this signal
                if signal.confidence > 0.65:  # Only process high-confidence signals
                    await self._trigger_strategy_evaluation(signal)
                    self.stats["strategy_triggers"] += 1
                
            except Exception as e:
                self.logger.error("Error processing market signal", error=str(e))
    
    async def _on_whale_alert(self, message: aio_pika.IncomingMessage):
        """Handle incoming whale alerts"""
        async with message.process():
            try:
                alert = deserialize_message(WhaleAlertMessage, message.body.decode())
                
                self.stats["whale_alerts_received"] += 1
                
                self.logger.info(
                    "Received whale alert",
                    symbol=alert.symbol,
                    alert_type=alert.alert_type.value,
                    amount_usd=f"${alert.amount_usd:,.0f}",
                    significance=alert.significance_score
                )
                
                # Store in strategy service cache for strategy context
                if hasattr(self.strategy_service, 'whale_alerts_cache'):
                    if alert.symbol not in self.strategy_service.whale_alerts_cache:
                        self.strategy_service.whale_alerts_cache[alert.symbol] = []
                    self.strategy_service.whale_alerts_cache[alert.symbol].append({
                        "alert": alert,
                        "received_at": datetime.utcnow()
                    })
                    # Keep only last 20 alerts per symbol
                    self.strategy_service.whale_alerts_cache[alert.symbol] = \
                        self.strategy_service.whale_alerts_cache[alert.symbol][-20:]
                
                # High-significance alerts trigger immediate evaluation
                if alert.significance_score > 0.8:
                    self.logger.warning(
                        "High-significance whale alert detected",
                        symbol=alert.symbol,
                        amount_usd=f"${alert.amount_usd:,.0f}"
                    )
                    # Could trigger risk adjustment or strategy re-evaluation here
                
            except Exception as e:
                self.logger.error("Error processing whale alert", error=str(e))
    
    async def _on_sentiment_update(self, message: aio_pika.IncomingMessage):
        """Handle incoming sentiment updates"""
        async with message.process():
            try:
                update = deserialize_message(SocialSentimentUpdate, message.body.decode())
                
                self.stats["sentiment_updates_received"] += 1
                
                self.logger.debug(
                    "Received sentiment update",
                    symbol=update.symbol,
                    source=update.source.value,
                    score=f"{update.sentiment_score:.2f}",
                    volume=update.social_volume
                )
                
                # Update sentiment cache in strategy service
                if hasattr(self.strategy_service, 'sentiment_cache'):
                    if update.symbol not in self.strategy_service.sentiment_cache:
                        self.strategy_service.sentiment_cache[update.symbol] = {}
                    self.strategy_service.sentiment_cache[update.symbol][update.source.value] = {
                        "update": update,
                        "received_at": datetime.utcnow()
                    }
                
            except Exception as e:
                self.logger.error("Error processing sentiment update", error=str(e))
    
    async def _on_onchain_metric(self, message: aio_pika.IncomingMessage):
        """Handle incoming on-chain metrics"""
        async with message.process():
            try:
                metric = deserialize_message(OnChainMetricUpdate, message.body.decode())
                
                self.stats["onchain_updates_received"] += 1
                
                self.logger.debug(
                    "Received on-chain metric",
                    symbol=metric.symbol,
                    metric_name=metric.metric_name,
                    value=f"{metric.metric_value:.2f}",
                    signal=metric.signal.value if metric.signal else "none"
                )
                
                # Store in on-chain metrics cache
                if hasattr(self.strategy_service, 'onchain_metrics_cache'):
                    if metric.symbol not in self.strategy_service.onchain_metrics_cache:
                        self.strategy_service.onchain_metrics_cache[metric.symbol] = {}
                    self.strategy_service.onchain_metrics_cache[metric.symbol][metric.metric_name] = {
                        "metric": metric,
                        "received_at": datetime.utcnow()
                    }
                
            except Exception as e:
                self.logger.error("Error processing on-chain metric", error=str(e))
    
    async def _on_institutional_flow(self, message: aio_pika.IncomingMessage):
        """Handle incoming institutional flow signals"""
        async with message.process():
            try:
                flow = deserialize_message(InstitutionalFlowSignal, message.body.decode())
                
                self.stats["institutional_signals_received"] += 1
                
                self.logger.info(
                    "Received institutional flow signal",
                    symbol=flow.symbol,
                    flow_type=flow.flow_type.value,
                    size_usd=f"${flow.size_usd:,.0f}",
                    side=flow.side,
                    confidence=f"{flow.confidence_score:.2f}"
                )
                
                # Store in institutional flow cache
                if hasattr(self.strategy_service, 'institutional_flow_cache'):
                    if flow.symbol not in self.strategy_service.institutional_flow_cache:
                        self.strategy_service.institutional_flow_cache[flow.symbol] = []
                    self.strategy_service.institutional_flow_cache[flow.symbol].append({
                        "flow": flow,
                        "received_at": datetime.utcnow()
                    })
                    # Keep only last 10 flows per symbol
                    self.strategy_service.institutional_flow_cache[flow.symbol] = \
                        self.strategy_service.institutional_flow_cache[flow.symbol][-10:]
                
            except Exception as e:
                self.logger.error("Error processing institutional flow signal", error=str(e))
    
    async def _trigger_strategy_evaluation(self, signal: MarketSignalAggregate):
        """
        Trigger strategy evaluation based on market signal
        
        Args:
            signal: Market signal aggregate to evaluate
        """
        try:
            self.logger.info(
                "Triggering strategy evaluation",
                symbol=signal.symbol,
                action=signal.recommended_action,
                confidence=f"{signal.confidence:.2f}"
            )
            
            # Get active strategies for this symbol
            if hasattr(self.strategy_service, 'strategy_manager'):
                active_strategies = await self.strategy_service.strategy_manager.get_active_strategies_for_symbol(
                    signal.symbol
                )
                
                for strategy in active_strategies:
                    try:
                        # Evaluate if strategy should trade based on signal
                        should_trade = await self._evaluate_strategy_conditions(strategy, signal)
                        
                        if should_trade:
                            self.logger.info(
                                "Strategy conditions met - would execute trade",
                                strategy_id=strategy.get('id'),
                                symbol=signal.symbol,
                                action=signal.recommended_action
                            )
                            # In production, this would trigger actual trade execution
                            # await self.strategy_service.execute_trade(strategy, signal)
                        
                    except Exception as e:
                        self.logger.error(
                            "Error evaluating strategy",
                            strategy_id=strategy.get('id'),
                            error=str(e)
                        )
            
        except Exception as e:
            self.logger.error("Error triggering strategy evaluation", error=str(e))
    
    async def _evaluate_strategy_conditions(self, strategy: Dict, signal: MarketSignalAggregate) -> bool:
        """
        Evaluate if strategy conditions are met for trading
        
        Args:
            strategy: Strategy configuration
            signal: Market signal to evaluate
            
        Returns:
            True if should trade, False otherwise
        """
        try:
            # Basic evaluation logic (would be much more sophisticated in production)
            
            # Check signal confidence threshold
            confidence_threshold = strategy.get('min_confidence', 0.7)
            if signal.confidence < confidence_threshold:
                return False
            
            # Check signal strength
            required_strength = strategy.get('min_signal_strength', 'moderate')
            strength_levels = {'weak': 1, 'moderate': 2, 'strong': 3, 'very_strong': 4}
            
            signal_strength_value = strength_levels.get(signal.signal_strength.value, 0)
            required_strength_value = strength_levels.get(required_strength, 2)
            
            if signal_strength_value < required_strength_value:
                return False
            
            # Check signal direction matches strategy direction
            strategy_direction = strategy.get('direction', 'both')
            if strategy_direction != 'both':
                if strategy_direction == 'long' and signal.overall_signal.value != 'bullish':
                    return False
                if strategy_direction == 'short' and signal.overall_signal.value != 'bearish':
                    return False
            
            # All conditions met
            return True
            
        except Exception as e:
            self.logger.error("Error evaluating strategy conditions", error=str(e))
            return False
    
    def get_stats(self) -> Dict:
        """Get consumer statistics"""
        return self.stats.copy()
