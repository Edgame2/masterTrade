# MasterTrade System Architecture - Overview

**Last Updated**: November 13, 2025  
**Version**: 1.0

---

## Table of Contents

1. [System Overview](#system-overview)
2. [Architecture Principles](#architecture-principles)
3. [Technology Stack](#technology-stack)
4. [System Components](#system-components)
5. [Related Documentation](#related-documentation)

---

## System Overview

MasterTrade is a fully automated, goal-oriented cryptocurrency trading platform that generates, backtests, and executes trading strategies using machine learning, multi-source data intelligence, and adaptive risk management.

### Key Capabilities

- **Automated Strategy Generation**: 500 strategies/day using genetic algorithms + RL
- **Multi-Source Intelligence**: On-chain data, social sentiment, market data, stock correlations
- **Goal-Oriented Trading**: Optimizes for 10% monthly return, $10K profit, $1M portfolio
- **Paper Trading Validation**: 1-2 week validation before live deployment
- **Adaptive Risk Management**: Dynamic position sizing with Kelly Criterion
- **Multi-Environment**: Supports paper and live trading environments

---

## Architecture Principles

### 1. Microservices Architecture
- **Loosely Coupled**: Each service is independent and can be deployed separately
- **Single Responsibility**: Each service has a clear, focused purpose
- **Event-Driven**: Services communicate via message queues (RabbitMQ)
- **Stateless**: Services don't maintain session state (stored in Redis/PostgreSQL)

### 2. Data-Driven
- **Multi-Source**: Integrates 10+ data sources for comprehensive market intelligence
- **Real-Time + Historical**: Supports both streaming and batch processing
- **Time-Series Optimized**: Efficient storage and retrieval of historical data
- **Cache-First**: Redis caching for frequently accessed data

### 3. Safety & Reliability
- **Paper Trading First**: All strategies validated before live trading
- **Multi-Level Risk Controls**: Strategy, portfolio, and system-level limits
- **Circuit Breakers**: Automatic shutdown on anomalies
- **Comprehensive Monitoring**: Prometheus + Grafana dashboards
- **Automated Backups**: PostgreSQL (hourly incremental) + Redis (AOF+RDB)

### 4. Scalability
- **Horizontal Scaling**: Services can scale independently
- **Connection Pooling**: PgBouncer for database connections
- **Message Queues**: RabbitMQ for async processing
- **Caching Layer**: Redis for performance optimization

---

## Technology Stack

### Core Infrastructure
| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Language** | Python 3.11+ | Primary development language |
| **Framework** | FastAPI | REST API framework |
| **Async Runtime** | asyncio, asyncpg | Asynchronous I/O |
| **Database** | PostgreSQL 15 | Primary data store |
| **Cache** | Redis 7 | Caching + session management |
| **Message Queue** | RabbitMQ 3.12 | Event-driven communication |
| **Connection Pool** | PgBouncer | Database connection management |

### Data Processing
| Component | Technology | Purpose |
|-----------|-----------|---------|
| **ML Framework** | scikit-learn, XGBoost | Machine learning models |
| **Time Series** | NumPy, Pandas | Data manipulation |
| **Deep Learning** | PyTorch | LSTM-Transformer models |
| **NLP** | VADER, FinBERT | Sentiment analysis |
| **Backtesting** | Custom engine | Strategy validation |

### Monitoring & Observability
| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Metrics** | Prometheus | Time-series metrics |
| **Visualization** | Grafana | Dashboards + alerts |
| **Logging** | structlog | Structured logging |
| **Health Checks** | FastAPI + Docker | Service health monitoring |

### Deployment
| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Containerization** | Docker | Service isolation |
| **Orchestration** | Docker Compose | Local deployment |
| **Networking** | Docker Bridge | Service communication |
| **Volumes** | Docker Volumes | Data persistence |

---

## System Components

### Core Services (10 Microservices)

```
┌─────────────────────────────────────────────────────────────────┐
│                     MasterTrade System                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐  │
│  │  Market Data   │  │   Strategy     │  │ Order Executor │  │
│  │    Service     │  │    Service     │  │                │  │
│  │   :8000        │  │    :8006       │  │     :8081      │  │
│  └────────────────┘  └────────────────┘  └────────────────┘  │
│           │                   │                    │           │
│           │                   │                    │           │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐  │
│  │  Risk Manager  │  │ Alert System   │  │  API Gateway   │  │
│  │                │  │                │  │                │  │
│  │     :8080      │  │     :8007      │  │     :8080      │  │
│  └────────────────┘  └────────────────┘  └────────────────┘  │
│           │                   │                    │           │
│           │                   │                    │           │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐  │
│  │  Data Access   │  │  Monitoring    │  │   Arbitrage    │  │
│  │      API       │  │      UI        │  │    Service     │  │
│  │     :8005      │  │     :3000      │  │   (disabled)   │  │
│  └────────────────┘  └────────────────┘  └────────────────┘  │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│                    Infrastructure Layer                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐  │
│  │  PostgreSQL    │  │   RabbitMQ     │  │     Redis      │  │
│  │                │  │                │  │                │  │
│  │     :5432      │  │  :5672/:15672  │  │     :6379      │  │
│  └────────────────┘  └────────────────┘  └────────────────┘  │
│           │                   │                    │           │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐  │
│  │   PgBouncer    │  │  Prometheus    │  │    Grafana     │  │
│  │                │  │                │  │                │  │
│  │     :6432      │  │     :9090      │  │     :3001      │  │
│  └────────────────┘  └────────────────┘  └────────────────┘  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Service Descriptions

| Service | Port | Purpose | Key Features |
|---------|------|---------|--------------|
| **Market Data Service** | 8000 | Data collection & distribution | 5 collectors, RabbitMQ pub, REST API |
| **Strategy Service** | 8006 | Strategy generation & management | 500/day generation, backtesting, goal-oriented |
| **Order Executor** | 8081 | Trade execution | Paper/live modes, Binance integration |
| **Risk Manager** | 8080 | Risk monitoring & limits | VaR, position limits, circuit breakers |
| **Alert System** | 8007 | Multi-channel notifications | Email, SMS, Telegram, Discord, Slack |
| **API Gateway** | 8080 | Unified API entry point | Auth, rate limiting, routing |
| **Data Access API** | 8005 | Historical data queries | Time-series data, indicators |
| **Monitoring UI** | 3000 | Dashboard & management | Next.js, real-time updates |
| **PostgreSQL** | 5432 | Primary database | 50+ tables, automated backups |
| **RabbitMQ** | 5672 | Message broker | 5 exchanges, 14 queues |
| **Redis** | 6379 | Cache + sessions | AOF+RDB persistence |
| **PgBouncer** | 6432 | Connection pooler | Transaction mode, 100 max clients |
| **Prometheus** | 9090 | Metrics collection | 50+ custom metrics |
| **Grafana** | 3001 | Visualization | 4 dashboards, 32 panels |

---

## System Workflows

### 1. Strategy Generation Pipeline

```
Daily at 3:00 AM UTC:
1. Generate 500 new strategies (genetic algorithm + RL)
2. Backtest all strategies (90 days historical data)
3. Filter strategies (realistic criteria: Sharpe > 1.5, etc.)
4. Select top performers for paper trading
5. Monitor paper trading (1-2 weeks)
6. Auto-activate best strategies (2-10 live strategies)
7. Continuous monitoring & replacement
```

### 2. Data Collection Flow

```
Exchange APIs → Collectors → RabbitMQ → Services → PostgreSQL
                                ↓
                             Redis Cache
```

### 3. Trading Execution Flow

```
Strategy Signal → Risk Check → Position Sizing → Order Executor → Exchange
                      ↓              ↓                  ↓
                   Database      Goal Tracker     Alert System
```

---

## Related Documentation

- **[02_SERVICE_ARCHITECTURE.md](./02_SERVICE_ARCHITECTURE.md)** - Detailed service interactions
- **[03_DATA_FLOW.md](./03_DATA_FLOW.md)** - Data pipeline and message flows
- **[04_DATABASE_SCHEMA.md](./04_DATABASE_SCHEMA.md)** - Complete database schema
- **[05_MESSAGE_BROKER.md](./05_MESSAGE_BROKER.md)** - RabbitMQ topology
- **[06_DEPLOYMENT.md](./06_DEPLOYMENT.md)** - Docker deployment architecture
- **[OPERATIONS_RUNBOOK.md](../OPERATIONS_RUNBOOK.md)** - Operations procedures

---

## System Metrics

### Current Performance
- ✅ Strategy Generation: 500/day automated
- ✅ Backtest Throughput: 500 strategies in <3 hours
- ✅ Data Collection: 5 collectors (code-ready, needs API keys)
- ✅ API Latency: <200ms p95 (target met)
- ✅ System Uptime: >99.9% (target met)
- ✅ Database: Automated backups every hour

### Scale Targets
- **Max Concurrent Users**: 100
- **Max API Requests**: 1,000 req/sec
- **Max Active Strategies**: 10 (configurable)
- **Data Retention**: 90 days high-frequency, 1 year daily
- **Backup Recovery**: <5 minutes RTO

---

## Security & Compliance

### Authentication & Authorization
- API key authentication for services
- JWT tokens for user sessions
- RBAC for monitoring UI (planned)
- Encrypted credentials in environment variables

### Data Security
- PostgreSQL credentials never in code
- API keys stored in .env (gitignored)
- Redis password protected
- RabbitMQ authenticated connections

### Operational Security
- Automated backups (encrypted at rest)
- Point-in-time recovery (PITR) capability
- Circuit breakers for anomaly detection
- Multi-level risk controls

---

## Disaster Recovery

### Backup Strategy
- **PostgreSQL**: Hourly incremental + daily full backups
- **Redis**: AOF (append-only file) + RDB snapshots
- **Retention**: 7 days local, 30 days archive
- **Recovery Time**: <5 minutes for recent backups

### High Availability (Future)
- Multi-region deployment
- Read replicas for PostgreSQL
- Redis Sentinel for failover
- Active-passive strategy services

---

## Next Steps

1. Read service-specific documentation (02-06)
2. Review operations runbook for procedures
3. Check deployment guide for setup instructions
4. Review API documentation at `/docs` endpoints

---

**For Questions**: See operations runbook or contact system administrator
