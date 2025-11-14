# MasterTrade Architecture Documentation

**Complete System Architecture Documentation**  
**Last Updated**: November 13, 2025  
**Version**: 1.0

---

## 📚 Documentation Index

This directory contains comprehensive architecture documentation for the MasterTrade cryptocurrency trading system. The documentation is organized into focused modules for easy navigation and maintenance.

---

## 📖 Documentation Files

### 1. [System Overview](./01_SYSTEM_OVERVIEW.md)
**High-level system architecture and principles**

- System capabilities and features
- Architecture principles (microservices, data-driven, safety-first)
- Complete technology stack
- Service component diagram
- System workflows
- Performance metrics and targets
- Security and compliance

**Recommended for**: New team members, stakeholders, high-level understanding

---

### 2. [Service Architecture](./02_SERVICE_ARCHITECTURE.md)
**Detailed service-by-service documentation**

- Service interaction map
- 8 core services documented in detail:
  - Market Data Service (:8000)
  - Strategy Service (:8006)
  - Order Executor (:8081)
  - Risk Manager (:8080)
  - Alert System (:8007)
  - API Gateway (:8080)
  - Data Access API (:8005)
  - Monitoring UI (:3000)
- Service responsibilities and components
- API endpoints for each service
- Communication patterns
- Health check architecture
- Scaling strategy

**Recommended for**: Developers, DevOps, service integration

---

### 3. [Data Flow Architecture](./03_DATA_FLOW.md)
**Complete data pipeline and message routing**

- End-to-end data flow diagrams
- RabbitMQ message routing
- Real-time data pipeline (market data, on-chain, sentiment)
- Strategy generation pipeline
- Trading signal flow
- Goal-oriented position sizing flow
- Message formats (JSON schemas)
- Caching strategy (Redis)
- Database write patterns
- Data retention policies
- Data quality checks

**Recommended for**: Data engineers, backend developers, system architects

---

### 4. [Database Schema](./04_DATABASE_SCHEMA.md)
**Complete database documentation (50+ tables)**

- Market Data tables (OHLCV, indicators, whale alerts, sentiment)
- Strategy Management tables (strategies, backtest results, goals)
- Order & Execution tables (orders, trades, positions, balances)
- Risk Management tables (metrics, circuit breakers)
- Alert System tables (alerts, history, suppressions)
- User Management tables (users, audit logs)
- Entity relationships and foreign keys
- Indexes and performance optimization
- Partitioning strategy (TimescaleDB migration plan)
- Backup and maintenance procedures

**Recommended for**: Database administrators, backend developers, data analysts

---

### 5. [Message Broker Architecture](./05_MESSAGE_BROKER.md)
**RabbitMQ topology and message routing**

- Exchange topology (5 exchanges)
- Queue configuration (14 queues)
- Routing keys and bindings
- Message formats (JSON schemas)
- Consumer groups and concurrency
- Dead letter queues (DLQ)
- Performance metrics and scaling
- Monitoring and troubleshooting

**Recommended for**: Backend developers, DevOps, system architects

---

### 6. [Deployment Architecture](./06_DEPLOYMENT.md)
**Docker deployment and operations**

- Container overview (14 containers)
- Container specifications
- Network architecture
- Volume mounts (persistent storage)
- Environment variables (API keys, configuration)
- Health checks
- Resource limits (CPU, memory)
- Deployment procedures:
  - Initial deployment
  - Update deployment
  - Scaling services
  - Backup and restore
- Troubleshooting guide
- Logging and monitoring

**Recommended for**: DevOps, system administrators, deployment engineers

---

## 🚀 Quick Start

### For New Developers
1. Read [01_SYSTEM_OVERVIEW.md](./01_SYSTEM_OVERVIEW.md) for high-level understanding
2. Read [02_SERVICE_ARCHITECTURE.md](./02_SERVICE_ARCHITECTURE.md) for service details
3. Read [04_DATABASE_SCHEMA.md](./04_DATABASE_SCHEMA.md) for data structures
4. Refer to [06_DEPLOYMENT.md](./06_DEPLOYMENT.md) for local setup

### For DevOps Engineers
1. Read [06_DEPLOYMENT.md](./06_DEPLOYMENT.md) for deployment procedures
2. Read [05_MESSAGE_BROKER.md](./05_MESSAGE_BROKER.md) for RabbitMQ setup
3. Read [03_DATA_FLOW.md](./03_DATA_FLOW.md) for data pipeline
4. Read [02_SERVICE_ARCHITECTURE.md](./02_SERVICE_ARCHITECTURE.md) for scaling

### For Data Engineers
1. Read [04_DATABASE_SCHEMA.md](./04_DATABASE_SCHEMA.md) for schema design
2. Read [03_DATA_FLOW.md](./03_DATA_FLOW.md) for data pipeline
3. Read [05_MESSAGE_BROKER.md](./05_MESSAGE_BROKER.md) for message routing

### For System Architects
1. Read [01_SYSTEM_OVERVIEW.md](./01_SYSTEM_OVERVIEW.md) for architecture
2. Read [02_SERVICE_ARCHITECTURE.md](./02_SERVICE_ARCHITECTURE.md) for microservices design
3. Read [03_DATA_FLOW.md](./03_DATA_FLOW.md) for event-driven architecture
4. Read [05_MESSAGE_BROKER.md](./05_MESSAGE_BROKER.md) for messaging patterns

---

## 📊 System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    EXTERNAL DATA SOURCES                         │
│  Binance • Moralis • Glassnode • Twitter • Reddit • LunarCrush  │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ↓
┌─────────────────────────────────────────────────────────────────┐
│                  MARKET DATA SERVICE :8000                       │
│  • Collectors (7)  • Indicators  • Sentiment Analysis           │
└──────────┬──────────────────────────────────────────────────────┘
           │
           ↓ (RabbitMQ + PostgreSQL)
┌─────────────────────────────────────────────────────────────────┐
│                   STRATEGY SERVICE :8006                         │
│  • Generation (500/day)  • Backtesting  • Goal-Oriented         │
└──────────┬──────────────────────────────────────────────────────┘
           │
           ↓ (Trading Signals)
┌─────────────────────────────────────────────────────────────────┐
│                    RISK MANAGER :8080                            │
│  • Position Limits  • Portfolio Risk  • Circuit Breakers        │
└──────────┬──────────────────────────────────────────────────────┘
           │
           ↓ (Approved Orders)
┌─────────────────────────────────────────────────────────────────┐
│                   ORDER EXECUTOR :8081                           │
│  • Paper Trading  • Live Trading  • Position Tracking           │
└──────────┬──────────────────────────────────────────────────────┘
           │
           ↓ (Binance API)
┌─────────────────────────────────────────────────────────────────┐
│                      BINANCE EXCHANGE                            │
└─────────────────────────────────────────────────────────────────┘

Supporting Services:
• Alert System :8007       • API Gateway :8080
• Data Access API :8005    • Monitoring UI :3000
• Prometheus :9090         • Grafana :3001

Infrastructure:
• PostgreSQL :5432   • RabbitMQ :5672   • Redis :6379
```

---

## 🔑 Key System Features

### Automated Strategy Generation
- **500 strategies generated daily** at 3:00 AM UTC
- **Genetic algorithm + reinforcement learning**
- **LSTM-Transformer price predictions** (1-hour ahead)
- **Fully automated pipeline**: Generate → Backtest → Filter → Paper Trade → Activate

### Goal-Oriented Trading
- **3 default goals**: 10% monthly return, $10K monthly profit, $1M portfolio
- **Kelly Criterion position sizing**
- **Adaptive risk management** based on goal progress
- **Automatic adjustments** when behind/ahead schedule

### Real-Time Data Collection
- **7 data collectors**: Binance, Moralis, Glassnode, Twitter, Reddit, LunarCrush, Stock Indices
- **Multi-source sentiment analysis**: VADER + FinBERT
- **Whale transaction alerts**: >$1M movements tracked
- **On-chain metrics**: Active addresses, hash rate, NVT ratio

### Risk Management
- **Position limits**: Max 20% per position
- **Portfolio risk**: Max 15% drawdown
- **Circuit breakers**: Automatic trading pause on anomalies
- **VaR & CVaR** calculations

### Monitoring & Alerts
- **6 notification channels**: Email, SMS, Telegram, Discord, Slack, Webhook
- **Real-time dashboards**: Grafana + Next.js UI
- **Comprehensive logging**: All actions audited
- **Health checks**: All services monitored

---

## 📈 Performance Targets

| Metric | Current | Target |
|--------|---------|--------|
| Data latency | <200ms | <100ms |
| API response time | <100ms | <50ms |
| Strategy generation | 3 hours/500 | 1 hour/500 |
| Backtest throughput | ~170/hour | 500/hour |
| Database query time | <50ms p95 | <20ms p95 |
| Message queue lag | <100 messages | <50 messages |
| System uptime | 99.5% | 99.9% |

---

## 🔧 Technology Stack

### Infrastructure
- **Database**: PostgreSQL 15 (future: TimescaleDB)
- **Message Broker**: RabbitMQ 3.12
- **Cache**: Redis 7
- **Containerization**: Docker + Docker Compose

### Services
- **Backend**: Python 3.11 + FastAPI
- **Async Processing**: asyncio + aiohttp
- **ML/AI**: TensorFlow, scikit-learn, VADER, FinBERT

### Monitoring
- **Metrics**: Prometheus
- **Visualization**: Grafana
- **Dashboard**: Next.js + React

### Deployment
- **Platform**: Local (Docker Compose)
- **Orchestration**: Docker Compose (future: Kubernetes)

---

## 📝 Documentation Maintenance

### Update Frequency
- **After major features**: Update relevant documentation
- **After architecture changes**: Update all affected docs
- **Quarterly review**: Comprehensive review of all docs

### Version Control
- All documentation in Git
- Commit with clear messages
- Link documentation updates to code changes

### Contribution Guidelines
- Keep documentation in sync with code
- Update "Last Updated" dates
- Use consistent formatting
- Include ASCII diagrams where helpful
- Cross-reference related documents

---

## 🆘 Getting Help

### Documentation Issues
If documentation is unclear or outdated:
1. Open GitHub issue with `[docs]` tag
2. Specify which document and section
3. Suggest improvements

### System Questions
1. Check relevant documentation first
2. Search existing issues
3. Ask in team chat
4. Open GitHub issue if unresolved

---

## 📚 Additional Resources

- **Main README**: [/README.md](../../README.md)
- **TODO List**: [/.github/todo.md](../todo.md)
- **Project Plan**: [/Project.txt](../../Project.txt)
- **Implementation Guides**: `/ADVANCED_*.md` files in root

---

## 📄 License

Internal documentation for MasterTrade project.

---

**Questions?** Open an issue or contact the development team.
