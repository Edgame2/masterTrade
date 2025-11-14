# Message Broker Architecture (RabbitMQ)

**Last Updated**: November 13, 2025  
**RabbitMQ Version**: 3.12  
**Management UI**: http://localhost:15672

---

## Table of Contents

1. [Overview](#overview)
2. [Exchange Topology](#exchange-topology)
3. [Queue Configuration](#queue-configuration)
4. [Routing Keys & Bindings](#routing-keys--bindings)
5. [Message Formats](#message-formats)
6. [Consumer Groups](#consumer-groups)
7. [Dead Letter Queues](#dead-letter-queues)
8. [Performance & Scaling](#performance--scaling)

---

## Overview

### RabbitMQ Role
RabbitMQ serves as the central message broker for asynchronous communication between microservices in the MasterTrade system.

### Key Features
- **Decoupling**: Services communicate without direct dependencies
- **Reliability**: Message persistence and acknowledgments
- **Scalability**: Multiple consumers per queue
- **Flexibility**: Topic-based routing for complex patterns

### Connection Details
```yaml
Host: localhost (or host.docker.internal from containers)
Port: 5672 (AMQP)
Management UI: 15672
Username: mastertrade
Password: mastertrade123
Virtual Host: /
```

---

## Exchange Topology

### Exchange Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                      RABBITMQ EXCHANGES                          │
└─────────────────────────────────────────────────────────────────┘

┌────────────────────┐
│  market_data       │  Type: topic
│  (mastertrade.     │  Durable: true
│   market)          │  Auto-delete: false
└──────┬─────────────┘
       │
       ├──→ market.data.*           → market_data queue
       ├──→ ticker.*                → ticker_updates queue
       ├──→ market.data.orderbook   → orderbook_updates queue
       ├──→ market.data.trade       → trade_updates queue
       ├──→ sentiment.*             → sentiment_data queue
       ├──→ stock.*                 → stock_index_data queue
       ├──→ onchain.*               → strategy_service_onchain_metrics queue
       ├──→ whale.alert.*           → strategy_service_whale_alerts queue
       ├──→ market.#                → strategy_market_data queue
       └──→ market.#                → executor_market_data queue

┌────────────────────┐
│  trading           │  Type: topic
│  (mastertrade.     │  Durable: true
│   trading)         │  Auto-delete: false
└──────┬─────────────┘
       │
       └──→ signal.*                → trading_signals queue

┌────────────────────┐
│  orders            │  Type: topic
│  (mastertrade.     │  Durable: true
│   orders)          │  Auto-delete: false
└──────┬─────────────┘
       │
       ├──→ order.request           → order_requests queue
       └──→ order.update.*          → order_updates queue

┌────────────────────┐
│  risk              │  Type: topic
│  (mastertrade.     │  Durable: true
│   risk)            │  Auto-delete: false
└──────┬─────────────┘
       │
       └──→ risk.check              → risk_checks queue

┌────────────────────┐
│  system            │  Type: topic
│  (mastertrade.     │  Durable: true
│   system)          │  Auto-delete: false
└──────┬─────────────┘
       │
       └──→ system.*                → system_notifications queue
```

---

## Exchange Configuration

### 1. `mastertrade.market` (Market Data Exchange)

```python
# Exchange declaration
channel.exchange_declare(
    exchange='mastertrade.market',
    exchange_type='topic',
    durable=True,
    auto_delete=False
)
```

**Purpose**: Distribute market data, on-chain metrics, sentiment, and whale alerts

**Routing Key Patterns**:
- `market.data.{symbol}.{interval}` - OHLCV candles
- `ticker.{symbol}` - Real-time price tickers
- `market.data.orderbook.{symbol}` - Order book snapshots
- `market.data.trade.{symbol}` - Individual trades
- `sentiment.{symbol}.{platform}` - Social sentiment
- `stock.{index_name}` - Stock market indices
- `onchain.{metric_name}.{symbol}` - On-chain metrics
- `whale.alert.{token}.{level}` - Whale transaction alerts

**Publishers**: Market Data Service  
**Consumers**: Strategy Service, Order Executor, Alert System

---

### 2. `mastertrade.trading` (Trading Exchange)

```python
channel.exchange_declare(
    exchange='mastertrade.trading',
    exchange_type='topic',
    durable=True,
    auto_delete=False
)
```

**Purpose**: Distribute trading signals from strategies

**Routing Key Patterns**:
- `signal.{symbol}.{strategy_id}` - Trading signals
- `signal.backtest.{strategy_id}` - Backtest signals (not executed)

**Publishers**: Strategy Service  
**Consumers**: Risk Manager

---

### 3. `mastertrade.orders` (Orders Exchange)

```python
channel.exchange_declare(
    exchange='mastertrade.orders',
    exchange_type='topic',
    durable=True,
    auto_delete=False
)
```

**Purpose**: Order lifecycle management

**Routing Key Patterns**:
- `order.request.{symbol}` - New order requests
- `order.update.filled.{order_id}` - Order filled
- `order.update.cancelled.{order_id}` - Order cancelled
- `order.update.rejected.{order_id}` - Order rejected
- `order.update.partial.{order_id}` - Partial fill

**Publishers**: Risk Manager (requests), Order Executor (updates)  
**Consumers**: Order Executor (requests), Strategy Service (updates), Alert System (updates)

---

### 4. `mastertrade.risk` (Risk Exchange)

```python
channel.exchange_declare(
    exchange='mastertrade.risk',
    exchange_type='topic',
    durable=True,
    auto_delete=False
)
```

**Purpose**: Risk validation and circuit breaker events

**Routing Key Patterns**:
- `risk.check.{strategy_id}` - Risk validation requests
- `risk.breach.{metric}` - Risk threshold breaches
- `risk.circuit_breaker.{trigger}` - Circuit breaker activations

**Publishers**: Strategy Service (checks), Risk Manager (breaches)  
**Consumers**: Risk Manager (checks), Alert System (breaches)

---

### 5. `mastertrade.system` (System Exchange)

```python
channel.exchange_declare(
    exchange='mastertrade.system',
    exchange_type='topic',
    durable=True,
    auto_delete=False
)
```

**Purpose**: System-wide notifications and health checks

**Routing Key Patterns**:
- `system.health.{service_name}` - Health check updates
- `system.alert.{severity}` - System alerts
- `system.config.{change_type}` - Configuration changes

**Publishers**: All services  
**Consumers**: Alert System, Monitoring UI

---

## Queue Configuration

### Market Data Queues

#### `market_data`
```python
channel.queue_declare(
    queue='market_data',
    durable=True,
    arguments={
        'x-message-ttl': 60000,  # 60 seconds
        'x-max-length': 100000,  # Max 100K messages
        'x-overflow': 'drop-head'  # Drop oldest on overflow
    }
)
channel.queue_bind(
    exchange='mastertrade.market',
    queue='market_data',
    routing_key='market.data.*'
)
```

**Purpose**: General market data (OHLCV)  
**Consumers**: Multiple strategy instances  
**Message Rate**: ~100 msg/sec  
**TTL**: 60 seconds (stale data useless)

---

#### `ticker_updates`
```python
channel.queue_declare(
    queue='ticker_updates',
    durable=True,
    arguments={
        'x-message-ttl': 10000,  # 10 seconds
        'x-max-length': 50000
    }
)
channel.queue_bind(
    exchange='mastertrade.market',
    queue='ticker_updates',
    routing_key='ticker.*'
)
```

**Purpose**: Real-time price tickers  
**Consumers**: Monitoring UI, Order Executor  
**Message Rate**: ~500 msg/sec  
**TTL**: 10 seconds (extremely time-sensitive)

---

#### `sentiment_data`
```python
channel.queue_declare(
    queue='sentiment_data',
    durable=True,
    arguments={
        'x-message-ttl': 300000,  # 5 minutes
        'x-max-length': 10000
    }
)
channel.queue_bind(
    exchange='mastertrade.market',
    queue='sentiment_data',
    routing_key='sentiment.*'
)
```

**Purpose**: Social sentiment scores  
**Consumers**: Strategy Service  
**Message Rate**: ~10 msg/min  
**TTL**: 5 minutes

---

#### `stock_index_data`
```python
channel.queue_declare(
    queue='stock_index_data',
    durable=True,
    arguments={
        'x-message-ttl': 300000,  # 5 minutes
        'x-max-length': 1000
    }
)
channel.queue_bind(
    exchange='mastertrade.market',
    queue='stock_index_data',
    routing_key='stock.*'
)
```

**Purpose**: Stock market correlation data  
**Consumers**: Strategy Service  
**Message Rate**: ~5 msg/min  
**TTL**: 5 minutes

---

#### `strategy_service_onchain_metrics`
```python
channel.queue_declare(
    queue='strategy_service_onchain_metrics',
    durable=True,
    arguments={'x-message-ttl': 300000}
)
channel.queue_bind(
    exchange='mastertrade.market',
    queue='strategy_service_onchain_metrics',
    routing_key='onchain.*'
)
```

**Purpose**: On-chain metrics for strategy decisions  
**Consumers**: Strategy Service  
**Message Rate**: ~20 msg/min

---

#### `strategy_service_whale_alerts`
```python
channel.queue_declare(
    queue='strategy_service_whale_alerts',
    durable=True,
    arguments={'x-message-ttl': 600000}  # 10 minutes
)
channel.queue_bind(
    exchange='mastertrade.market',
    queue='strategy_service_whale_alerts',
    routing_key='whale.alert.*'
)
```

**Purpose**: Large transaction alerts  
**Consumers**: Strategy Service, Alert System  
**Message Rate**: ~1 msg/min (sparse)

---

### Trading & Order Queues

#### `trading_signals`
```python
channel.queue_declare(
    queue='trading_signals',
    durable=True,
    arguments={
        'x-message-ttl': 30000,  # 30 seconds
        'x-max-length': 10000,
        'x-dead-letter-exchange': 'mastertrade.dlx',
        'x-dead-letter-routing-key': 'dlq.trading_signals'
    }
)
channel.queue_bind(
    exchange='mastertrade.trading',
    queue='trading_signals',
    routing_key='signal.*'
)
```

**Purpose**: Trading signals from strategies  
**Consumers**: Risk Manager  
**Message Rate**: ~50 msg/hour  
**Critical**: Yes (must not lose signals)

---

#### `order_requests`
```python
channel.queue_declare(
    queue='order_requests',
    durable=True,
    arguments={
        'x-message-ttl': 60000,  # 1 minute
        'x-max-length': 5000,
        'x-dead-letter-exchange': 'mastertrade.dlx',
        'x-dead-letter-routing-key': 'dlq.order_requests'
    }
)
channel.queue_bind(
    exchange='mastertrade.orders',
    queue='order_requests',
    routing_key='order.request.*'
)
```

**Purpose**: Risk-approved order requests  
**Consumers**: Order Executor  
**Message Rate**: ~30 msg/hour  
**Critical**: Yes (financial transactions)

---

#### `order_updates`
```python
channel.queue_declare(
    queue='order_updates',
    durable=True,
    arguments={'x-message-ttl': 300000}  # 5 minutes
)
channel.queue_bind(
    exchange='mastertrade.orders',
    queue='order_updates',
    routing_key='order.update.#'
)
```

**Purpose**: Order status updates  
**Consumers**: Strategy Service, Alert System, Monitoring UI  
**Message Rate**: ~50 msg/hour

---

### System Queues

#### `risk_checks`
```python
channel.queue_declare(
    queue='risk_checks',
    durable=True,
    arguments={
        'x-message-ttl': 30000,  # 30 seconds
        'x-max-length': 5000
    }
)
channel.queue_bind(
    exchange='mastertrade.risk',
    queue='risk_checks',
    routing_key='risk.check.*'
)
```

**Purpose**: Risk validation requests  
**Consumers**: Risk Manager  
**Message Rate**: ~50 msg/hour

---

#### `system_notifications`
```python
channel.queue_declare(
    queue='system_notifications',
    durable=True,
    arguments={'x-message-ttl': 600000}  # 10 minutes
)
channel.queue_bind(
    exchange='mastertrade.system',
    queue='system_notifications',
    routing_key='system.#'
)
```

**Purpose**: System-wide notifications  
**Consumers**: Alert System, Monitoring UI  
**Message Rate**: ~10 msg/hour

---

## Routing Keys & Bindings

### Routing Key Hierarchy

```
Exchange: mastertrade.market
├── market.data.BTCUSDT.1m       → market_data, strategy_market_data
├── market.data.ETHUSDT.5m       → market_data, strategy_market_data
├── ticker.BTCUSDT               → ticker_updates
├── ticker.ETHUSDT               → ticker_updates
├── market.data.orderbook.BTCUSDT → orderbook_updates
├── market.data.trade.BTCUSDT    → trade_updates
├── sentiment.BTCUSDT.twitter    → sentiment_data
├── sentiment.ETHUSDT.reddit     → sentiment_data
├── stock.SPX                    → stock_index_data
├── stock.VIX                    → stock_index_data
├── onchain.active_addresses.BTC → strategy_service_onchain_metrics
├── whale.alert.BTC.high         → strategy_service_whale_alerts
└── whale.alert.ETH.critical     → strategy_service_whale_alerts

Exchange: mastertrade.trading
├── signal.BTCUSDT.uuid-1234     → trading_signals
└── signal.backtest.uuid-5678    → (no binding, dropped)

Exchange: mastertrade.orders
├── order.request.BTCUSDT        → order_requests
├── order.update.filled.order-123 → order_updates
├── order.update.cancelled.order-456 → order_updates
└── order.update.partial.order-789 → order_updates

Exchange: mastertrade.risk
├── risk.check.strategy-uuid     → risk_checks
├── risk.breach.drawdown         → (Alert System)
└── risk.circuit_breaker.loss_streak → (Alert System)

Exchange: mastertrade.system
├── system.health.market_data    → system_notifications
├── system.alert.critical        → system_notifications
└── system.config.api_key_update → system_notifications
```

---

## Message Formats

### Market Data Message
```json
{
  "type": "market_data",
  "symbol": "BTCUSDT",
  "interval": "1m",
  "timestamp": "2025-11-13T10:30:00Z",
  "open": 45000.00,
  "high": 45500.00,
  "low": 44800.00,
  "close": 45200.00,
  "volume": 1234.56,
  "quote_volume": 55776000.00,
  "trades_count": 8765
}
```

### Trading Signal Message
```json
{
  "type": "trading_signal",
  "strategy_id": "550e8400-e29b-41d4-a716-446655440000",
  "symbol": "BTCUSDT",
  "action": "BUY",
  "confidence": 0.85,
  "entry_price": 45200.00,
  "stop_loss": 44300.00,
  "take_profit": 46500.00,
  "position_size_pct": 0.05,
  "reasoning": "Strong momentum + positive sentiment",
  "indicators": {
    "RSI": 65,
    "MACD": 150.5,
    "sentiment_score": 0.72
  },
  "timestamp": "2025-11-13T10:30:00Z"
}
```

### Order Request Message
```json
{
  "type": "order_request",
  "request_id": "req-1234567890",
  "strategy_id": "550e8400-e29b-41d4-a716-446655440000",
  "symbol": "BTCUSDT",
  "side": "BUY",
  "order_type": "MARKET",
  "quantity": 0.5,
  "price": null,
  "stop_loss": 44300.00,
  "take_profit": 46500.00,
  "environment": "paper",
  "risk_approved": true,
  "timestamp": "2025-11-13T10:30:05Z"
}
```

### Order Update Message
```json
{
  "type": "order_update",
  "order_id": "order-1234567890",
  "exchange_order_id": "1234567890",
  "status": "filled",
  "filled_quantity": 0.5,
  "average_fill_price": 45205.50,
  "commission": 0.00075,
  "commission_asset": "BNB",
  "filled_at": "2025-11-13T10:30:08Z"
}
```

### Risk Check Message
```json
{
  "type": "risk_check",
  "check_id": "risk-1234567890",
  "strategy_id": "550e8400-e29b-41d4-a716-446655440000",
  "symbol": "BTCUSDT",
  "proposed_position_size": 0.05,
  "current_portfolio_value": 50000.00,
  "current_positions": 5,
  "max_drawdown_current": 0.08,
  "timestamp": "2025-11-13T10:30:03Z"
}
```

### Whale Alert Message
```json
{
  "type": "whale_alert",
  "transaction_hash": "0x1234567890abcdef",
  "blockchain": "ethereum",
  "token": "BTC",
  "from_address": "0xabcd...",
  "to_address": "0xefgh...",
  "from_label": "unknown_wallet",
  "to_label": "binance_exchange",
  "amount_token": 100.0,
  "amount_usd": 4520000.00,
  "alert_level": "high",
  "timestamp": "2025-11-13T10:29:45Z"
}
```

---

## Consumer Groups

### Concurrent Consumers

```python
# Strategy Service - Multiple consumers for market data
for i in range(5):  # 5 concurrent workers
    channel.basic_consume(
        queue='market_data',
        on_message_callback=handle_market_data,
        auto_ack=False  # Manual acknowledgment
    )

# Prefetch count to limit unacknowledged messages
channel.basic_qos(prefetch_count=10)
```

### Consumer Configuration

| Service | Queue | Consumers | Prefetch | Auto-Ack |
|---------|-------|-----------|----------|----------|
| Strategy Service | `strategy_market_data` | 5 | 10 | No |
| Strategy Service | `sentiment_data` | 2 | 5 | No |
| Order Executor | `order_requests` | 3 | 1 | No |
| Risk Manager | `trading_signals` | 3 | 5 | No |
| Alert System | `order_updates` | 2 | 10 | No |

---

## Dead Letter Queues (DLQ)

### DLQ Exchange

```python
channel.exchange_declare(
    exchange='mastertrade.dlx',
    exchange_type='direct',
    durable=True
)
```

### DLQ Configuration

```python
# Dead letter queue for trading signals
channel.queue_declare(
    queue='dlq.trading_signals',
    durable=True,
    arguments={
        'x-message-ttl': 86400000  # 24 hours
    }
)
channel.queue_bind(
    exchange='mastertrade.dlx',
    queue='dlq.trading_signals',
    routing_key='dlq.trading_signals'
)
```

### DLQ Monitoring

Messages enter DLQ when:
- Message TTL expires
- Consumer rejects message (basic_nack with requeue=False)
- Message delivery fails after max retries

**Alert on DLQ depth > 10**: Indicates systematic processing failures

---

## Performance & Scaling

### Current Throughput

| Exchange | Messages/sec | Peak | Consumers |
|----------|--------------|------|-----------|
| `mastertrade.market` | 100 | 500 | 15 |
| `mastertrade.trading` | 1 | 10 | 3 |
| `mastertrade.orders` | 1 | 5 | 5 |
| `mastertrade.risk` | 1 | 10 | 3 |
| `mastertrade.system` | 0.1 | 5 | 2 |

### Scaling Strategies

#### Horizontal Scaling (Consumer Count)
```python
# Increase consumers for high-load queues
# Example: Scale strategy service from 5 to 10 workers
docker-compose up --scale strategy_service=10
```

#### Queue Sharding
```python
# Split high-traffic queue by symbol
channel.queue_declare(queue='market_data_btc')
channel.queue_declare(queue='market_data_eth')
channel.queue_bind(exchange='mastertrade.market', queue='market_data_btc', routing_key='market.data.BTC*')
channel.queue_bind(exchange='mastertrade.market', queue='market_data_eth', routing_key='market.data.ETH*')
```

#### Message Batching
```python
# Batch small messages to reduce overhead
messages = []
while len(messages) < 100 and time_elapsed < 1:
    messages.append(channel.basic_get(queue='market_data'))

process_batch(messages)
```

### Performance Monitoring

```bash
# Check queue depths
rabbitmqctl list_queues name messages consumers

# Check message rates
rabbitmqctl list_queues name messages_ready messages_unacknowledged message_stats

# Check connection count
rabbitmqctl list_connections name state

# Check channel count
rabbitmqctl list_channels connection name number
```

---

**Next**: [06_DEPLOYMENT.md](./06_DEPLOYMENT.md) - Docker deployment architecture
