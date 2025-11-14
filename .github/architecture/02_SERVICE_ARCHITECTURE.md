# Service Architecture - Detailed Component Documentation

**Last Updated**: November 13, 2025

---

## Service Interaction Map

```
┌─────────────────────────────────────────────────────────────────┐
│                    External Data Sources                        │
├─────────────────────────────────────────────────────────────────┤
│  Binance API │ Moralis │ Glassnode │ Twitter │ Reddit │ etc.   │
└──────┬──────────────────────────────────────────────────────────┘
       │
       ↓
┌─────────────────────────────────────────────────────────────────┐
│              Market Data Service (:8000)                        │
│  • 5 Data Collectors (on-chain, social, market)                │
│  • RabbitMQ Publisher                                           │
│  • REST API for historical data                                 │
│  • Technical indicator calculator                               │
└──────┬──────────────────────────────────────────────────────────┘
       │
       ↓ (publishes to RabbitMQ)
┌─────────────────────────────────────────────────────────────────┐
│                    RabbitMQ Message Broker                      │
│  Exchanges: market_data, trading, orders, risk, system         │
│  Queues: 14 queues with routing                                │
└──────┬──────────────────────────────────────────────────────────┘
       │
       ↓ (consumes from queues)
┌─────────────────────────────────────────────────────────────────┐
│               Strategy Service (:8006)                          │
│  • Consumes market data from RabbitMQ                          │
│  • Generates 500 strategies/day                                 │
│  • Backtests strategies                                         │
│  • Manages strategy lifecycle                                   │
│  • Goal-oriented position sizing                                │
└──────┬──────────────────────────────────────────────────────────┘
       │
       ↓ (sends signals)
┌─────────────────────────────────────────────────────────────────┐
│               Risk Manager (:8080)                              │
│  • Validates trading signals                                    │
│  • Enforces position limits                                     │
│  • Portfolio risk monitoring                                    │
│  • Circuit breaker logic                                        │
└──────┬──────────────────────────────────────────────────────────┘
       │
       ↓ (approved orders)
┌─────────────────────────────────────────────────────────────────┐
│               Order Executor (:8081)                            │
│  • Paper/Live trading environments                              │
│  • Binance API integration                                      │
│  • Order management                                             │
│  • Trade execution                                              │
└──────┬──────────────────────────────────────────────────────────┘
       │
       ↓ (execution results)
┌─────────────────────────────────────────────────────────────────┐
│               Alert System (:8007)                              │
│  • Multi-channel notifications                                  │
│  • Email, SMS, Telegram, Discord, Slack                        │
│  • Configurable alert conditions                                │
└─────────────────────────────────────────────────────────────────┘
```

---

## 1. Market Data Service

### Purpose
Central hub for collecting, processing, and distributing market intelligence from multiple sources.

### Responsibilities
- Collect data from 10+ external sources
- Calculate technical indicators in real-time
- Publish data to RabbitMQ for consumers
- Provide REST API for historical queries
- Monitor collector health

### Key Components

#### Data Collectors
```python
collectors/
├── moralis_collector.py          # On-chain whale transactions
├── glassnode_collector.py        # On-chain metrics (NVT, MVRV)
├── twitter_collector.py          # Social sentiment from Twitter
├── reddit_collector.py           # Social sentiment from Reddit
├── lunarcrush_collector.py       # Aggregated social metrics
└── stock_index_collector.py      # S&P 500, NASDAQ, VIX
```

#### Technical Indicators
- SMA, EMA, RSI, MACD, Bollinger Bands
- ATR, Stochastic Oscillator
- Volume indicators (OBV, VWAP)
- Custom indicators

### API Endpoints
```
GET  /health                 # Service health
GET  /health/collectors      # Collector status
GET  /api/v1/market-data     # Historical market data
GET  /api/v1/indicators      # Technical indicators
POST /api/v1/collectors/start # Start collector
POST /api/v1/collectors/stop  # Stop collector
```

### Dependencies
- **Upstream**: External APIs (Binance, Moralis, Twitter, etc.)
- **Downstream**: RabbitMQ (publisher), PostgreSQL (storage), Redis (cache)

### Configuration
```yaml
Environment Variables:
  - POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB
  - RABBITMQ_URL
  - REDIS_URL
  - MORALIS_API_KEY, GLASSNODE_API_KEY
  - TWITTER_BEARER_TOKEN, REDDIT_CLIENT_ID
  - LUNARCRUSH_API_KEY
  - ONCHAIN_COLLECTION_ENABLED=true/false
  - SOCIAL_COLLECTION_ENABLED=true/false
```

---

## 2. Strategy Service

### Purpose
Automated strategy generation, backtesting, and lifecycle management with goal-oriented optimization.

### Responsibilities
- Generate 500 strategies daily using genetic algorithms
- Backtest strategies with 90 days historical data
- Select best strategies for paper trading
- Auto-activate top performers to live trading
- Monitor strategy performance
- Goal-oriented position sizing
- Crypto pair selection

### Key Components

#### Strategy Generation
```python
core/
├── strategy_generator.py          # Genetic algorithm + RL
├── backtest_engine.py             # Comprehensive backtesting
├── price_prediction_service.py    # LSTM-Transformer predictor
└── evaluation_metrics.py          # Sharpe, CAGR, drawdown, etc.
```

#### Automation
```python
automation/
├── automatic_pipeline.py          # Daily 3 AM UTC generation
├── automatic_strategy_activation.py # Auto-activation logic
├── daily_strategy_reviewer.py     # Performance review
└── crypto_selection_engine.py     # Automated pair selection
```

#### Goal-Oriented Trading
```python
goal_oriented/
├── position_sizing_engine.py      # Adaptive position sizing
├── goal_tracker.py                # Progress monitoring
└── goal_oriented_schema.sql       # Database schema
```

### API Endpoints
```
GET  /api/v1/strategies              # List all strategies
POST /api/v1/strategies              # Create strategy
GET  /api/v1/strategies/{id}         # Get strategy details
PUT  /api/v1/strategies/{id}         # Update strategy
DELETE /api/v1/strategies/{id}       # Delete strategy
POST /api/v1/strategies/{id}/backtest # Run backtest
GET  /api/v1/goals/summary           # Goal progress
POST /api/v1/position-sizing/calculate # Calculate position size
```

### Dependencies
- **Upstream**: RabbitMQ (consumer), Market Data Service (data)
- **Downstream**: PostgreSQL (strategies), Redis (cache), Order Executor (signals)

### Automated Workflows
```
Daily at 3:00 AM UTC:
1. Generate 500 new strategies
2. Backtest all strategies (3-hour window)
3. Filter by performance criteria
4. Top ~28-35% enter paper trading
5. Monitor paper trading 1-2 weeks
6. Activate 2-10 best strategies to live
```

---

## 3. Order Executor

### Purpose
Execute trading orders in paper and live environments with multi-exchange support.

### Responsibilities
- Execute buy/sell orders
- Manage order lifecycle (pending → filled → closed)
- Track positions and P&L
- Support paper trading mode
- Binance API integration
- Order history and reporting

### Key Components

#### Environment Management
```python
strategy_environment_manager.py    # Paper/live environment control
order_executor.py                  # Order execution logic
position_manager.py                # Position tracking
```

### API Endpoints
```
POST /api/v1/orders              # Create order
GET  /api/v1/orders              # List orders
GET  /api/v1/orders/{id}         # Order details
DELETE /api/v1/orders/{id}       # Cancel order
GET  /api/v1/positions           # Current positions
GET  /api/v1/trades              # Trade history
```

### Dependencies
- **Upstream**: Strategy Service (signals), Risk Manager (approval)
- **Downstream**: Binance API, PostgreSQL (orders/trades)

### Trading Modes
- **Paper Trading**: Simulated execution, no real money
- **Live Trading**: Real execution on exchange

---

## 4. Risk Manager

### Purpose
Multi-level risk controls to protect capital and enforce trading limits.

### Responsibilities
- Validate trading signals before execution
- Enforce position size limits
- Monitor portfolio exposure
- Calculate VaR and CVaR
- Circuit breaker on drawdown
- Real-time risk metrics

### Key Components

#### Risk Controls
```python
portfolio_risk_controller.py      # Portfolio-level limits
position_sizing.py                # Position size validation
stop_loss_manager.py              # Stop-loss enforcement
```

### Risk Levels
```
1. Strategy Level: Max 20% position size, 5% risk per trade
2. Portfolio Level: Max 15% drawdown, correlation limits
3. System Level: Circuit breaker on anomalies
```

### API Endpoints
```
POST /api/v1/risk/check          # Validate trade
GET  /api/v1/risk/metrics        # Current risk metrics
GET  /api/v1/risk/limits         # Risk limits
PUT  /api/v1/risk/limits         # Update limits
```

### Dependencies
- **Upstream**: Strategy Service (signals)
- **Downstream**: PostgreSQL (risk metrics), Order Executor (approval)

---

## 5. Alert System

### Purpose
Multi-channel notification system for critical events and performance updates.

### Responsibilities
- Send alerts via 6 channels (Email, SMS, Telegram, Discord, Slack, Webhook)
- Configurable alert conditions
- Alert history and delivery tracking
- Alert suppression (avoid spam)
- Priority-based routing

### Notification Channels
```python
notification_channels.py
├── EmailNotifier          # SMTP email
├── SMSNotifier            # Twilio SMS
├── TelegramNotifier       # Telegram bot
├── DiscordNotifier        # Discord webhook
├── SlackNotifier          # Slack webhook
└── WebhookNotifier        # Custom webhooks
```

### Alert Types
- **System**: Service down, high CPU, memory alerts
- **Trading**: Strategy activated, large loss, goal milestone
- **Risk**: Drawdown exceeded, position limit breached
- **Data**: Collector failure, stale data

### API Endpoints
```
POST /api/v1/alerts              # Create alert
GET  /api/v1/alerts              # List alerts
GET  /api/v1/alerts/{id}         # Alert details
PUT  /api/v1/alerts/{id}         # Update alert
DELETE /api/v1/alerts/{id}       # Delete alert
GET  /api/v1/alerts/history      # Alert history
```

### Dependencies
- **Upstream**: All services (alert triggers)
- **Downstream**: External notification services, PostgreSQL (history)

---

## 6. API Gateway

### Purpose
Unified entry point for external API access with authentication and rate limiting.

### Responsibilities
- Route requests to appropriate services
- API key authentication
- Rate limiting and quota management
- Request/response logging
- CORS handling

### API Endpoints
```
/*                               # Proxy to backend services
GET /health                      # Gateway health
GET /metrics                     # Prometheus metrics
```

### Dependencies
- **Upstream**: External clients
- **Downstream**: All backend services

---

## 7. Data Access API

### Purpose
Specialized API for efficient historical data queries and indicator calculations.

### Responsibilities
- Time-series data queries
- Technical indicator lookups
- Optimized bulk data retrieval
- Data aggregation

### API Endpoints
```
GET /api/v1/historical/{symbol}  # Historical price data
GET /api/v1/indicators/{symbol}  # Technical indicators
GET /api/v1/bulk                 # Bulk data export
```

### Dependencies
- **Upstream**: External clients, Strategy Service
- **Downstream**: PostgreSQL (read-only queries)

---

## 8. Monitoring UI

### Purpose
Web-based dashboard for system monitoring and management.

### Responsibilities
- Real-time system status
- Strategy performance visualization
- Goal progress tracking
- Alert configuration
- Data source management

### Technology
- **Framework**: Next.js (React)
- **API**: REST + WebSocket
- **Charts**: Recharts, Chart.js
- **State**: React Context + hooks

### Pages
```
/dashboard            # System overview
/strategies           # Strategy management
/goals                # Goal tracking
/alerts               # Alert configuration
/data-sources         # Data source CRUD
```

### Dependencies
- **Upstream**: Browser clients
- **Downstream**: API Gateway, WebSocket server

---

## Service Communication Patterns

### Synchronous (REST)
```
Client → API Gateway → Backend Service → Response
```

### Asynchronous (Message Queue)
```
Publisher → RabbitMQ Exchange → Queue → Consumer
```

### Caching Pattern
```
Request → Check Redis → If miss, query DB → Cache result → Response
```

### Event Flow
```
Market Data → RabbitMQ → Strategy Service → Signal → Risk Manager
→ Order Executor → Trade Result → Alert System → Notification
```

---

## Health Check Architecture

Each service exposes `/health` endpoint:

```json
{
  "status": "healthy",
  "service": "strategy_service",
  "version": "1.0.0",
  "uptime_seconds": 86400,
  "dependencies": {
    "postgres": "connected",
    "rabbitmq": "connected",
    "redis": "connected"
  }
}
```

Docker health checks restart unhealthy containers automatically.

---

## Service Scaling Strategy

### Current (Single Instance)
- All services: 1 instance each
- Suitable for: <100 concurrent users, <1000 strategies

### Future (Horizontal Scaling)
- **Stateless Services**: Can scale to N instances (Strategy, Market Data)
- **Stateful Services**: Require coordination (Order Executor - 1 instance per environment)
- **Database**: Read replicas for queries, single primary for writes
- **Message Queue**: RabbitMQ clustering

---

**Next**: [03_DATA_FLOW.md](./03_DATA_FLOW.md) - Data pipeline details
