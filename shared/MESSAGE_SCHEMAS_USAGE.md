# Message Schemas Usage Guide

## Overview

The `message_schemas.py` module provides type-safe Pydantic models for all RabbitMQ messages in the MasterTrade system. These schemas ensure data validation, consistency, and clear contracts between microservices.

## Quick Start

```python
from shared.message_schemas import (
    WhaleAlertMessage,
    SocialSentimentUpdate,
    OnChainMetricUpdate,
    InstitutionalFlowSignal,
    MarketSignalAggregate,
    StrategySignal,
    serialize_message,
    deserialize_message,
    RoutingKeys
)
```

## Message Types

### 1. WhaleAlertMessage

Large cryptocurrency transaction notifications.

**When to use**: Detected large transfers (>$1M), exchange flows, whale accumulation/distribution

**Example - Publishing:**
```python
from datetime import datetime
import aio_pika
from shared.message_schemas import WhaleAlertMessage, AlertType, serialize_message, RoutingKeys

# Create whale alert
alert = WhaleAlertMessage(
    alert_id="whale_20251111_001",
    alert_type=AlertType.EXCHANGE_OUTFLOW,
    symbol="BTC",
    amount=1000.5,
    amount_usd=50_025_000.0,
    from_entity="Binance",
    to_entity="Unknown Wallet",
    blockchain="ethereum",
    significance_score=0.85,
    market_impact_estimate=-0.5,
    timestamp=datetime.utcnow()
)

# Publish to RabbitMQ
message = aio_pika.Message(
    body=serialize_message(alert).encode(),
    content_type="application/json"
)
await channel.default_exchange.publish(
    message,
    routing_key=RoutingKeys.WHALE_ALERT_HIGH_PRIORITY
)
```

**Example - Consuming:**
```python
async def on_whale_alert(message: aio_pika.IncomingMessage):
    async with message.process():
        alert = deserialize_message(WhaleAlertMessage, message.body.decode())
        
        if alert.significance_score > 0.8:
            logger.info(
                "High-significance whale alert",
                alert_type=alert.alert_type.value,
                amount_usd=alert.amount_usd,
                symbol=alert.symbol
            )
            # Trigger strategy re-evaluation
            await strategy_service.process_whale_alert(alert)
```

---

### 2. SocialSentimentUpdate

Social media sentiment analysis updates.

**When to use**: Twitter/Reddit sentiment changes, trending topics, viral posts

**Example - Publishing:**
```python
from shared.message_schemas import SocialSentimentUpdate, SentimentSource

sentiment = SocialSentimentUpdate(
    update_id="sentiment_20251111_twitter_001",
    source=SentimentSource.TWITTER,
    symbol="BTC",
    sentiment_score=0.65,  # -1 (bearish) to 1 (bullish)
    sentiment_label="Bullish",
    social_volume=15234,
    engagement_count=45678,
    influencer_sentiment=0.72,
    sentiment_change_24h=0.15,
    trending=True,
    viral_coefficient=2.3,
    top_keywords=["breakout", "ATH", "bullrun"],
    timestamp=datetime.utcnow()
)

message = aio_pika.Message(body=serialize_message(sentiment).encode())
await channel.default_exchange.publish(
    message,
    routing_key=RoutingKeys.SENTIMENT_TWITTER
)
```

**Example - Consuming:**
```python
async def on_sentiment_update(message: aio_pika.IncomingMessage):
    async with message.process():
        sentiment = deserialize_message(SocialSentimentUpdate, message.body.decode())
        
        # Detect sentiment shifts
        if abs(sentiment.sentiment_change_24h) > 0.2:
            logger.warning(
                "Major sentiment shift detected",
                symbol=sentiment.symbol,
                change=sentiment.sentiment_change_24h,
                current=sentiment.sentiment_score
            )
            # Adjust risk parameters
            await risk_manager.adjust_sentiment_risk(sentiment)
```

---

### 3. OnChainMetricUpdate

Blockchain fundamental metrics updates.

**When to use**: NVT ratio changes, MVRV updates, exchange flows, network health

**Example - Publishing:**
```python
from shared.message_schemas import OnChainMetricUpdate, TrendDirection

metric = OnChainMetricUpdate(
    metric_id="onchain_20251111_btc_nvt",
    symbol="BTC",
    metric_name="NVT",
    metric_value=45.2,
    nvt_ratio=45.2,
    mvrv_ratio=2.1,
    exchange_netflow=-15000.0,  # Negative = outflow (bullish)
    active_addresses=950000,
    exchange_reserves=2_500_000_000,
    percentile_rank=35.5,  # Below average
    z_score=-0.8,
    interpretation="NVT below average - potential accumulation phase",
    signal=TrendDirection.BULLISH,
    timestamp=datetime.utcnow(),
    source="glassnode"
)

message = aio_pika.Message(body=serialize_message(metric).encode())
await channel.default_exchange.publish(
    message,
    routing_key=RoutingKeys.ONCHAIN_EXCHANGE_FLOW
)
```

---

### 4. InstitutionalFlowSignal

Professional/institutional trading activity detection.

**When to use**: Block trades detected, unusual volume spikes, dark pool activity

**Example - Publishing:**
```python
from shared.message_schemas import InstitutionalFlowSignal, FlowType, SignalStrength

flow = InstitutionalFlowSignal(
    signal_id="instflow_20251111_001",
    symbol="BTCUSDT",
    flow_type=FlowType.BLOCK_TRADE,
    size_usd=5_000_000.0,
    price=50000.0,
    side="buy",
    exchange="Binance",
    is_block_trade=True,
    volume_ratio=8.5,  # 8.5x average volume
    price_impact=0.3,  # 0.3% price impact
    confidence_score=0.92,
    urgency=SignalStrength.STRONG,
    timestamp=datetime.utcnow()
)

message = aio_pika.Message(body=serialize_message(flow).encode())
await channel.default_exchange.publish(
    message,
    routing_key=RoutingKeys.INSTITUTIONAL_BLOCK_TRADE
)
```

---

### 5. MarketSignalAggregate

Combined signal from all data sources for strategy decisions.

**When to use**: Signal aggregation service outputs, strategy evaluation inputs

**Example - Publishing:**
```python
from shared.message_schemas import MarketSignalAggregate, TrendDirection, SignalStrength

aggregate = MarketSignalAggregate(
    signal_id="agg_20251111_btcusdt_001",
    symbol="BTCUSDT",
    overall_signal=TrendDirection.BULLISH,
    signal_strength=SignalStrength.STRONG,
    confidence=0.82,
    
    # Component signals
    price_signal=TrendDirection.BULLISH,
    price_strength=0.75,
    sentiment_signal=TrendDirection.BULLISH,
    sentiment_strength=0.85,
    onchain_signal=TrendDirection.NEUTRAL,
    onchain_strength=0.50,
    flow_signal=TrendDirection.BULLISH,
    flow_strength=0.90,
    
    # Component weights
    component_weights={
        "price": 0.3,
        "sentiment": 0.25,
        "onchain": 0.20,
        "flow": 0.25
    },
    
    # Risk assessment
    volatility=0.035,
    risk_level="medium",
    
    # Trading recommendation
    recommended_action="buy",
    position_size_modifier=1.2,  # 20% larger position
    
    timestamp=datetime.utcnow(),
    contributing_alerts=["whale_20251111_001"],
    contributing_updates=["sentiment_20251111_twitter_001"]
)

message = aio_pika.Message(body=serialize_message(aggregate).encode())
await channel.default_exchange.publish(
    message,
    routing_key=RoutingKeys.MARKET_SIGNAL_STRONG
)
```

**Example - Strategy Service Consuming:**
```python
async def on_market_signal(message: aio_pika.IncomingMessage):
    async with message.process():
        signal = deserialize_message(MarketSignalAggregate, message.body.decode())
        
        # Evaluate if signal meets strategy criteria
        if signal.confidence > 0.75 and signal.signal_strength == SignalStrength.STRONG:
            # Generate strategy signal
            strategy_signal = StrategySignal(
                signal_id=f"strat_signal_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
                strategy_id="momentum_strategy_v2",
                symbol=signal.symbol,
                action="ENTER_LONG",
                signal_strength=signal.confidence,
                entry_price=None,  # Market order
                confidence=signal.confidence,
                urgency=signal.signal_strength,
                reasoning=f"Strong bullish confluence: {signal.overall_signal}",
                contributing_signals=[signal.signal_id],
                timestamp=datetime.utcnow()
            )
            
            # Publish to order executor
            await publish_strategy_signal(strategy_signal)
```

---

### 6. StrategySignal

Strategy execution signals for order placement.

**When to use**: Strategy generates trading signal, send to order executor

**Example - Publishing:**
```python
from shared.message_schemas import StrategySignal, SignalStrength

signal = StrategySignal(
    signal_id="strat_signal_20251111_001",
    strategy_id="momentum_strategy_v2",
    symbol="BTCUSDT",
    action="ENTER_LONG",
    signal_strength=0.85,
    entry_price=50000.0,
    stop_loss=49000.0,
    take_profit=52000.0,
    position_size_usd=10000.0,
    leverage=2.0,
    confidence=0.82,
    urgency=SignalStrength.STRONG,
    reasoning="Strong bullish confluence: positive sentiment, whale accumulation, technical breakout",
    timestamp=datetime.utcnow(),
    valid_until=datetime.utcnow() + timedelta(minutes=5)
)

message = aio_pika.Message(body=serialize_message(signal).encode())
await channel.default_exchange.publish(
    message,
    routing_key=RoutingKeys.STRATEGY_SIGNAL_URGENT
)
```

---

## Routing Keys

Use standardized routing keys from `RoutingKeys` class:

```python
from shared.message_schemas import RoutingKeys

# Whale alerts
RoutingKeys.WHALE_ALERT                 # Regular whale alerts
RoutingKeys.WHALE_ALERT_HIGH_PRIORITY   # High-priority alerts (>$10M)

# Social sentiment
RoutingKeys.SENTIMENT_UPDATE            # All sentiment updates
RoutingKeys.SENTIMENT_TWITTER           # Twitter-specific
RoutingKeys.SENTIMENT_REDDIT            # Reddit-specific
RoutingKeys.SENTIMENT_AGGREGATED        # Aggregated from multiple sources

# On-chain metrics
RoutingKeys.ONCHAIN_METRIC              # All on-chain metrics
RoutingKeys.ONCHAIN_NVT                 # NVT ratio updates
RoutingKeys.ONCHAIN_MVRV                # MVRV ratio updates
RoutingKeys.ONCHAIN_EXCHANGE_FLOW       # Exchange flow updates

# Institutional flow
RoutingKeys.INSTITUTIONAL_FLOW          # All institutional flows
RoutingKeys.INSTITUTIONAL_BLOCK_TRADE   # Block trades only
RoutingKeys.INSTITUTIONAL_UNUSUAL_VOLUME # Unusual volume only

# Aggregated signals
RoutingKeys.MARKET_SIGNAL               # All market signals
RoutingKeys.MARKET_SIGNAL_STRONG        # Strong signals only

# Strategy signals
RoutingKeys.STRATEGY_SIGNAL             # All strategy signals
RoutingKeys.STRATEGY_SIGNAL_URGENT      # Urgent signals
```

---

## Integration Examples

### Market Data Service - Publishing Whale Alerts

```python
# market_data_service/collectors/moralis_collector.py
from shared.message_schemas import WhaleAlertMessage, AlertType, serialize_message, RoutingKeys

async def process_large_transaction(self, tx_data: dict):
    """Process and publish large transaction as whale alert"""
    alert = WhaleAlertMessage(
        alert_id=f"whale_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
        alert_type=AlertType.LARGE_TRANSFER,
        symbol=tx_data['symbol'],
        amount=tx_data['amount'],
        amount_usd=tx_data['amount_usd'],
        from_address=tx_data['from'],
        to_address=tx_data['to'],
        blockchain=tx_data['blockchain'],
        significance_score=self.calculate_significance(tx_data),
        timestamp=datetime.fromtimestamp(tx_data['timestamp'])
    )
    
    # Publish to RabbitMQ
    message = aio_pika.Message(
        body=serialize_message(alert).encode(),
        content_type="application/json"
    )
    
    routing_key = (
        RoutingKeys.WHALE_ALERT_HIGH_PRIORITY 
        if alert.amount_usd > 10_000_000 
        else RoutingKeys.WHALE_ALERT
    )
    
    await self.rabbitmq_channel.default_exchange.publish(
        message,
        routing_key=routing_key
    )
```

### Strategy Service - Consuming Market Signals

```python
# strategy_service/main.py
from shared.message_schemas import MarketSignalAggregate, deserialize_message

async def setup_message_consumers(self):
    """Setup RabbitMQ consumers for market signals"""
    
    # Create queue
    queue = await self.rabbitmq_channel.declare_queue(
        "strategy_service_market_signals",
        durable=True
    )
    
    # Bind to market signals
    await queue.bind(exchange="", routing_key=RoutingKeys.MARKET_SIGNAL)
    
    # Start consuming
    await queue.consume(self.on_market_signal)

async def on_market_signal(self, message: aio_pika.IncomingMessage):
    """Handle incoming market signal"""
    async with message.process():
        try:
            signal = deserialize_message(MarketSignalAggregate, message.body.decode())
            
            # Evaluate signal against active strategies
            for strategy in self.active_strategies:
                if strategy.should_trade(signal):
                    await strategy.execute_trade(signal)
                    
        except Exception as e:
            self.logger.error("Error processing market signal", error=str(e))
```

### Risk Manager - Consuming Whale Alerts

```python
# risk_manager/main.py
from shared.message_schemas import WhaleAlertMessage, deserialize_message, AlertType

async def on_whale_alert(self, message: aio_pika.IncomingMessage):
    """Adjust risk parameters based on whale activity"""
    async with message.process():
        alert = deserialize_message(WhaleAlertMessage, message.body.decode())
        
        # Large exchange inflows = potential selling pressure
        if alert.alert_type == AlertType.EXCHANGE_INFLOW and alert.amount_usd > 5_000_000:
            await self.reduce_position_sizes(alert.symbol, factor=0.7)
            self.logger.warning(
                "Large exchange inflow detected - reducing position sizes",
                symbol=alert.symbol,
                amount_usd=alert.amount_usd
            )
        
        # Large exchange outflows = potential accumulation
        elif alert.alert_type == AlertType.EXCHANGE_OUTFLOW and alert.amount_usd > 5_000_000:
            await self.increase_position_sizes(alert.symbol, factor=1.2)
            self.logger.info(
                "Large exchange outflow detected - increasing position sizes",
                symbol=alert.symbol,
                amount_usd=alert.amount_usd
            )
```

---

## Best Practices

### 1. Always Use Type Hints
```python
from shared.message_schemas import WhaleAlertMessage

async def process_alert(alert: WhaleAlertMessage):
    # IDE autocomplete and type checking work perfectly
    print(f"Alert: {alert.symbol} - ${alert.amount_usd:,.0f}")
```

### 2. Validate Data Before Publishing
```python
# Pydantic validates automatically
try:
    alert = WhaleAlertMessage(
        alert_id="test",
        alert_type=AlertType.LARGE_TRANSFER,
        symbol="BTC",
        amount=1000.0,
        amount_usd=50_000_000.0,
        blockchain="bitcoin",
        significance_score=1.5,  # ❌ Invalid: must be 0-1
        timestamp=datetime.utcnow()
    )
except ValidationError as e:
    logger.error("Invalid whale alert data", errors=e.errors())
```

### 3. Use Routing Keys for Filtering
```python
# Consumer only receives high-priority alerts
await queue.bind(exchange="", routing_key=RoutingKeys.WHALE_ALERT_HIGH_PRIORITY)
```

### 4. Handle Deserialization Errors
```python
async def on_message(message: aio_pika.IncomingMessage):
    async with message.process():
        try:
            alert = deserialize_message(WhaleAlertMessage, message.body.decode())
            await process_alert(alert)
        except ValidationError as e:
            logger.error("Invalid message format", errors=e.errors())
        except Exception as e:
            logger.error("Error processing message", error=str(e))
```

### 5. Add Metadata for Debugging
```python
alert = WhaleAlertMessage(
    # ... required fields ...
    metadata={
        "collector_version": "1.0.0",
        "data_source": "moralis",
        "processed_at": datetime.utcnow().isoformat(),
        "confidence": 0.95
    }
)
```

---

## Next Steps

1. **Implement Signal Aggregator** (`market_data_service/signal_aggregator.py`)
   - Consume whale alerts, sentiment updates, on-chain metrics
   - Combine into `MarketSignalAggregate`
   - Publish to strategy service

2. **Add Message Consumers** (`strategy_service/main.py`)
   - Subscribe to `market.signal`, `whale.alert`, `sentiment.update`
   - Integrate with strategy evaluation logic

3. **Enhance Collectors** (market_data_service)
   - Moralis collector → WhaleAlertMessage
   - Twitter/Reddit collectors → SocialSentimentUpdate
   - Glassnode collector → OnChainMetricUpdate

4. **Add Risk Management Integration** (`risk_manager/main.py`)
   - Subscribe to whale alerts and institutional flow
   - Adjust position sizing dynamically

---

## Schema Evolution

When updating schemas:

1. **Add new optional fields** (backward compatible)
2. **Never remove required fields** (breaks consumers)
3. **Use defaults for new required fields**
4. **Version your messages** (add `schema_version` field if major changes)

```python
class WhaleAlertMessage(BaseModel):
    schema_version: str = "2.0"  # Track schema version
    # ... rest of fields ...
```

---

## Performance Tips

1. **Serialize once, publish multiple times**
   ```python
   serialized = serialize_message(alert)
   for routing_key in routing_keys:
       await publish(serialized, routing_key)
   ```

2. **Use message batching** for high-volume data
   ```python
   batch = [alert1, alert2, alert3]
   serialized_batch = [serialize_message(a) for a in batch]
   ```

3. **Cache deserialized messages** if processing multiple times
   ```python
   @lru_cache(maxsize=1000)
   def cached_deserialize(json_str: str):
       return deserialize_message(WhaleAlertMessage, json_str)
   ```
