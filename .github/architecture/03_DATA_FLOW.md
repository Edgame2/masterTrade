# Data Flow Architecture

**Last Updated**: November 13, 2025

---

## Complete Data Pipeline

```
┌──────────────────────────────────────────────────────────────────────┐
│                        EXTERNAL DATA SOURCES                          │
├──────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  ┌─────────┐  ┌──────────┐  ┌─────────┐  ┌────────┐  ┌──────────┐ │
│  │ Binance │  │ Moralis  │  │Glassnode│  │Twitter │  │  Reddit  │ │
│  │   API   │  │   API    │  │   API   │  │  API   │  │   API    │ │
│  └────┬────┘  └─────┬────┘  └────┬────┘  └───┬────┘  └─────┬────┘ │
│       │            │              │            │             │       │
└───────┼────────────┼──────────────┼────────────┼─────────────┼───────┘
        │            │              │            │             │
        ↓            ↓              ↓            ↓             ↓
┌──────────────────────────────────────────────────────────────────────┐
│                     MARKET DATA SERVICE :8000                         │
├──────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  Collectors:                                                          │
│  • BinanceCollector      → market_data table                         │
│  • MoralisCollector      → whale_transactions                        │
│  • GlassnodeCollector    → onchain_metrics                           │
│  • TwitterCollector      → social_sentiment                          │
│  • RedditCollector       → social_sentiment                          │
│  • LunarCrushCollector   → social_metrics_aggregated                 │
│  • StockIndexCollector   → stock_indices                             │
│                                                                       │
│  Processing:                                                          │
│  • TechnicalIndicatorCalculator → technical_indicators               │
│  • SentimentAnalyzer (VADER/FinBERT) → sentiment scores             │
│                                                                       │
└───────────┬──────────────────────────────────────────────┬───────────┘
            │                                              │
            ↓ (writes)                                     ↓ (publishes)
┌──────────────────────┐                      ┌────────────────────────┐
│   POSTGRESQL :5432   │                      │   RABBITMQ :5672       │
│                      │                      │                        │
│  50+ Tables:         │                      │  5 Exchanges:          │
│  • market_data       │                      │  • market_data (topic) │
│  • whale_transactions│                      │  • trading (topic)     │
│  • onchain_metrics   │                      │  • orders (topic)      │
│  • social_sentiment  │                      │  • risk (topic)        │
│  • technical_indicat.│                      │  • system (topic)      │
│  • strategies        │                      │                        │
│  • orders, trades    │                      │  14 Queues             │
│  • financial_goals   │                      │                        │
└──────────┬───────────┘                      └────────┬───────────────┘
           │                                           │
           │ (read/write)                              │ (consume)
           │                                           │
           ↓                                           ↓
┌──────────────────────────────────────────────────────────────────────┐
│                      STRATEGY SERVICE :8006                           │
├──────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  Consumes from RabbitMQ:                                             │
│  • strategy_market_data queue                                         │
│  • strategy_onchain_metrics queue                                     │
│  • strategy_social_sentiment queue                                    │
│  • strategy_whale_alerts queue                                        │
│                                                                       │
│  Processing:                                                          │
│  • StrategyGenerator (genetic algorithm + RL)                        │
│  • BacktestEngine (90 days historical)                               │
│  • PricePredictionService (LSTM-Transformer)                         │
│  • GoalOrientedPositionSizer (Kelly Criterion)                       │
│  • CryptoSelectionEngine                                              │
│                                                                       │
│  Outputs:                                                             │
│  • Trading signals → RabbitMQ (trading exchange)                     │
│  • Backtest results → PostgreSQL                                     │
│  • Strategy metadata → PostgreSQL                                     │
│                                                                       │
└───────────────────────────────┬──────────────────────────────────────┘
                                │
                                ↓ (signals via RabbitMQ)
┌──────────────────────────────────────────────────────────────────────┐
│                       RISK MANAGER :8080                              │
├──────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  Consumes:                                                            │
│  • risk_checks queue (from trading exchange)                         │
│                                                                       │
│  Validation:                                                          │
│  • Position size limits (max 20% portfolio)                          │
│  • Portfolio risk (max 15% drawdown)                                 │
│  • Correlation checks                                                 │
│  • Circuit breaker logic                                              │
│                                                                       │
│  Outputs:                                                             │
│  • Approved orders → order_requests queue                            │
│  • Rejected signals → alerts                                          │
│  • Risk metrics → PostgreSQL                                          │
│                                                                       │
└───────────────────────────────┬──────────────────────────────────────┘
                                │
                                ↓ (approved orders)
┌──────────────────────────────────────────────────────────────────────┐
│                      ORDER EXECUTOR :8081                             │
├──────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  Consumes:                                                            │
│  • order_requests queue                                               │
│                                                                       │
│  Execution:                                                           │
│  • Paper Trading: Simulated execution                                │
│  • Live Trading: Binance API calls                                   │
│                                                                       │
│  Tracking:                                                            │
│  • Order status updates                                               │
│  • Position tracking                                                  │
│  • P&L calculation                                                    │
│                                                                       │
│  Outputs:                                                             │
│  • Order updates → order_updates queue                               │
│  • Execution results → PostgreSQL (orders, trades)                   │
│  • Alerts on fills/failures → Alert System                           │
│                                                                       │
└───────────────────────────────┬──────────────────────────────────────┘
                                │
                                ↓
┌──────────────────────────────────────────────────────────────────────┐
│                       BINANCE EXCHANGE                                │
├──────────────────────────────────────────────────────────────────────┤
│  • Market orders, Limit orders                                        │
│  • Real-time fills                                                    │
│  • Account balances                                                   │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Data Flow Patterns

### 1. Real-Time Market Data Flow

```
Binance WebSocket → Market Data Service → RabbitMQ → Strategy Service
                         ↓
                   PostgreSQL
                         ↓
                    Redis Cache
```

**Frequency**: 1 message/second (1m candles)  
**Latency**: <100ms end-to-end  
**Volume**: ~86,400 messages/day/symbol

### 2. On-Chain Data Flow

```
Moralis/Glassnode API → Market Data Service → PostgreSQL
                              ↓
                         RabbitMQ → Strategy Service
```

**Frequency**: Every 5 minutes (configurable)  
**Latency**: <5 seconds  
**Volume**: ~288 updates/day/metric

### 3. Social Sentiment Flow

```
Twitter/Reddit API → Market Data Service → NLP Pipeline (VADER/FinBERT)
                           ↓
                    sentiment_score
                           ↓
                    PostgreSQL + RabbitMQ → Strategy Service
```

**Frequency**: Every 15 minutes  
**Latency**: <10 seconds (including NLP)  
**Volume**: ~96 sentiment scores/day/symbol

### 4. Strategy Generation Flow

```
Daily at 3:00 AM UTC:
PostgreSQL (historical data) → Strategy Service
                                    ↓
                              Generate 500 strategies
                                    ↓
                              Backtest each (90 days)
                                    ↓
                              Filter by criteria
                                    ↓
                              Save to PostgreSQL
                                    ↓
                              Top performers → Paper Trading
```

**Duration**: ~3 hours for 500 strategies  
**Data Volume**: 90 days × 500 strategies = 45,000 backtest runs

### 5. Trading Signal Flow

```
Strategy Service → Trading Signal → RabbitMQ (trading exchange)
                                         ↓
                                    Risk Manager
                                         ↓
                           [Approved?] Yes → Order Executor → Exchange
                                  No ↓
                                 Alert System
```

**Latency**: <500ms (signal to exchange order)  
**Approval Rate**: ~70-80% (Risk Manager filters risky trades)

### 6. Goal-Oriented Position Sizing Flow

```
Trading Signal → GoalOrientedPositionSizer
                        ↓
                Get current goal progress from PostgreSQL
                        ↓
                Calculate Kelly fraction
                        ↓
                Adjust for goal (ahead/behind schedule)
                        ↓
                Apply confidence score
                        ↓
                Return position size (1-20% of portfolio)
                        ↓
                Save recommendation to PostgreSQL
                        ↓
                Use in order execution
```

**Calculation Time**: <50ms  
**Recalculation**: Every signal (dynamic sizing)

---

## RabbitMQ Message Routing

### Exchange: `market_data` (topic)

| Routing Key | Queue | Consumer | Purpose |
|-------------|-------|----------|---------|
| `market.data.*` | `market_data` | Multiple | General market data |
| `ticker.*` | `ticker_updates` | Strategy Service | Real-time price updates |
| `market.data.orderbook` | `orderbook_updates` | Strategy Service | Order book depth |
| `market.data.trade` | `trade_updates` | Strategy Service | Trade stream |
| `sentiment.*` | `sentiment_data` | Strategy Service | Social sentiment |
| `stock.*` | `stock_index_data` | Strategy Service | Stock correlations |
| `onchain.*` | `strategy_service_onchain_metrics` | Strategy Service | On-chain metrics |
| `whale.alert.*` | `strategy_service_whale_alerts` | Strategy Service | Whale movements |
| `market.#` | `strategy_market_data` | Strategy Service | All market data |
| `market.#` | `executor_market_data` | Order Executor | All market data |

### Exchange: `trading` (topic)

| Routing Key | Queue | Consumer | Purpose |
|-------------|-------|----------|---------|
| `signal.*` | `trading_signals` | Risk Manager | Trading signals |

### Exchange: `orders` (topic)

| Routing Key | Queue | Consumer | Purpose |
|-------------|-------|----------|---------|
| `order.request` | `order_requests` | Order Executor | New order requests |
| `order.update.*` | `order_updates` | Multiple | Order status updates |

### Exchange: `risk` (topic)

| Routing Key | Queue | Consumer | Purpose |
|-------------|-------|----------|---------|
| `risk.check` | `risk_checks` | Risk Manager | Risk validation |

### Exchange: `system` (topic)

| Routing Key | Queue | Consumer | Purpose |
|-------------|-------|----------|---------|
| `system.*` | `system_notifications` | Alert System | System events |

---

## Message Formats

### Market Data Message
```json
{
  "type": "market_data",
  "symbol": "BTCUSDT",
  "timestamp": "2025-11-13T10:30:00Z",
  "open": 45000.00,
  "high": 45500.00,
  "low": 44800.00,
  "close": 45200.00,
  "volume": 1234.56,
  "interval": "1m"
}
```

### Whale Alert Message
```json
{
  "type": "whale_alert",
  "transaction_hash": "0x1234...",
  "timestamp": "2025-11-13T10:30:00Z",
  "amount_usd": 5000000,
  "token": "BTC",
  "from_label": "unknown_wallet",
  "to_label": "binance_exchange",
  "alert_level": "high"
}
```

### Trading Signal Message
```json
{
  "type": "trading_signal",
  "strategy_id": "uuid",
  "symbol": "BTCUSDT",
  "action": "BUY",
  "confidence": 0.85,
  "entry_price": 45200.00,
  "stop_loss": 44300.00,
  "take_profit": 46500.00,
  "position_size": 0.5,
  "reasoning": "Strong momentum + positive sentiment",
  "timestamp": "2025-11-13T10:30:00Z"
}
```

### Order Request Message
```json
{
  "type": "order_request",
  "strategy_id": "uuid",
  "symbol": "BTCUSDT",
  "side": "BUY",
  "order_type": "MARKET",
  "quantity": 0.5,
  "price": null,
  "stop_loss": 44300.00,
  "take_profit": 46500.00,
  "environment": "paper",
  "timestamp": "2025-11-13T10:30:00Z"
}
```

---

## Caching Strategy (Redis)

### Cache Keys Pattern
```
market_data:{symbol}:{interval}      # TTL: 60s
indicator:{symbol}:{indicator_name}  # TTL: 300s
strategy:{strategy_id}               # TTL: 3600s
goal_progress:{goal_id}              # TTL: 3600s
position_size_rec:{strategy_id}      # TTL: 300s
```

### Cache Hit Rates (Target)
- Market Data: >90% (highly repetitive queries)
- Indicators: >80% (recalculated every 5 min)
- Strategies: >95% (static data)
- Goals: >70% (updated hourly)

### Cache Invalidation
- **Time-based**: TTL expiration
- **Event-based**: Update on data write
- **Manual**: Redis FLUSHDB for emergencies

---

## Database Write Patterns

### High-Frequency Writes (>1/min)
- `market_data` - 1/sec/symbol
- `trades_stream` - Variable
- `order_book` - 1/sec/symbol

**Optimization**: Batch inserts every 10 seconds

### Medium-Frequency Writes (1/min - 1/hour)
- `technical_indicators` - Every 5 min
- `social_sentiment` - Every 15 min
- `onchain_metrics` - Every 5 min
- `goal_progress` - Every hour

**Optimization**: Individual inserts, indexed queries

### Low-Frequency Writes (<1/hour)
- `strategies` - Daily generation
- `backtest_results` - Daily
- `financial_goals` - Manual updates
- `alerts` - Event-driven

**Optimization**: Standard inserts

---

## Data Retention Policies

| Table | Retention | Cleanup Method |
|-------|-----------|----------------|
| `market_data` | 90 days | Daily cron job |
| `trades_stream` | 30 days | Daily cron job |
| `order_book` | 7 days | Daily cron job |
| `technical_indicators` | 90 days | Weekly cron job |
| `social_sentiment` | 90 days | Weekly cron job |
| `onchain_metrics` | 365 days | Monthly cron job |
| `whale_transactions` | 365 days | Monthly cron job |
| `orders` | Forever | Archive to S3 (future) |
| `trades` | Forever | Archive to S3 (future) |
| `backtest_results` | Forever | Compress old data |
| `strategies` | Forever | Soft delete (archived=true) |

---

## Data Flow Monitoring

### Key Metrics
- **Data Freshness**: Time from source to database
  - Target: <60 seconds median
  - Alert: >300 seconds

- **Message Queue Lag**: Messages waiting in queues
  - Target: <100 messages
  - Alert: >1000 messages

- **Database Write Latency**: Time to insert data
  - Target: <10ms p95
  - Alert: >100ms p95

- **Cache Hit Rate**: % of queries served from cache
  - Target: >80%
  - Alert: <50%

### Monitoring Tools
- **Prometheus**: Scrapes metrics from all services
- **Grafana**: Visualizes data flow metrics
- **RabbitMQ Management UI**: Queue depths, rates
- **PostgreSQL pg_stat**: Query performance

---

## Data Quality Checks

### Validation Rules
```python
# Market Data
- price > 0
- volume >= 0
- timestamp within last 5 minutes (not stale)

# On-Chain Data
- transaction_hash unique
- amount_usd > 1000 (whale threshold)
- valid Ethereum address format

# Social Sentiment
- sentiment_score between -1 and 1
- post_text not empty
- author not in bot_list
```

### Error Handling
- **Invalid Data**: Log error, skip record, alert if >10% failure rate
- **API Failures**: Retry with exponential backoff (3 attempts)
- **Database Errors**: Queue for retry, alert on repeated failures

---

**Next**: [04_DATABASE_SCHEMA.md](./04_DATABASE_SCHEMA.md) - Complete database documentation
