# Deployment Architecture (Docker)

**Last Updated**: November 13, 2025  
**Docker Compose Version**: 3.8  
**Total Containers**: 14

---

## Table of Contents

1. [Container Overview](#container-overview)
2. [Network Architecture](#network-architecture)
3. [Volume Mounts](#volume-mounts)
4. [Environment Variables](#environment-variables)
5. [Health Checks](#health-checks)
6. [Resource Limits](#resource-limits)
7. [Deployment Procedures](#deployment-procedures)
8. [Troubleshooting](#troubleshooting)

---

## Container Overview

### All Containers

```
┌──────────────────────────────────────────────────────────────┐
│                    MASTERTRADE DEPLOYMENT                     │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│  Infrastructure (3):                                          │
│  • postgres:15-alpine        :5432  [Database]               │
│  • rabbitmq:3.12-management  :5672, :15672 [Message Broker]  │
│  • redis:7-alpine            :6379  [Cache]                  │
│                                                               │
│  Core Services (8):                                           │
│  • market_data_service       :8000  [Data Collection]        │
│  • strategy_service          :8006  [Strategy Generation]    │
│  • order_executor            :8081  [Order Execution]        │
│  • risk_manager              :8080  [Risk Management]        │
│  • alert_system              :8007  [Alerts & Notifications] │
│  • api_gateway               :8080  [API Gateway]            │
│  • data_access_api           :8005  [Historical Data API]    │
│  • arbitrage_service         :8002  [Arbitrage Detection]    │
│                                                               │
│  Monitoring (3):                                              │
│  • prometheus                :9090  [Metrics Collection]     │
│  • grafana                   :3001  [Visualization]          │
│  • monitoring_ui             :3000  [Dashboard UI]           │
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

---

## Container Specifications

### Infrastructure Containers

#### 1. PostgreSQL Database

```yaml
postgres:
  container_name: mastertrade_postgres
  image: postgres:15-alpine
  restart: always
  environment:
    POSTGRES_DB: mastertrade
    POSTGRES_USER: mastertrade
    POSTGRES_PASSWORD: mastertrade123
    PGDATA: /var/lib/postgresql/data/pgdata
  ports:
    - "5432:5432"
  volumes:
    - postgres_data:/var/lib/postgresql/data
  networks:
    - mastertrade_network
  healthcheck:
    test: ["CMD-SHELL", "pg_isready -U mastertrade"]
    interval: 10s
    timeout: 5s
    retries: 5
```

**Purpose**: Primary data store  
**Storage**: 50GB persistent volume  
**Backup**: Daily at 2:00 AM UTC

---

#### 2. RabbitMQ Message Broker

```yaml
rabbitmq:
  container_name: mastertrade_rabbitmq
  image: rabbitmq:3.12-management
  restart: always
  environment:
    RABBITMQ_DEFAULT_USER: mastertrade
    RABBITMQ_DEFAULT_PASS: mastertrade123
    RABBITMQ_DEFAULT_VHOST: /
  ports:
    - "5672:5672"    # AMQP
    - "15672:15672"  # Management UI
  volumes:
    - rabbitmq_data:/var/lib/rabbitmq
    - ./rabbitmq/rabbitmq.config:/etc/rabbitmq/rabbitmq.config
    - ./rabbitmq/definitions.json:/etc/rabbitmq/definitions.json
  networks:
    - mastertrade_network
  healthcheck:
    test: ["CMD", "rabbitmq-diagnostics", "ping"]
    interval: 30s
    timeout: 10s
    retries: 5
```

**Purpose**: Asynchronous message broker  
**Management UI**: http://localhost:15672  
**Storage**: 10GB persistent volume

---

#### 3. Redis Cache

```yaml
redis:
  container_name: mastertrade_redis
  image: redis:7-alpine
  restart: always
  command: redis-server --appendonly yes --maxmemory 2gb --maxmemory-policy allkeys-lru
  ports:
    - "6379:6379"
  volumes:
    - redis_data:/data
  networks:
    - mastertrade_network
  healthcheck:
    test: ["CMD", "redis-cli", "ping"]
    interval: 10s
    timeout: 3s
    retries: 5
```

**Purpose**: High-speed cache  
**Memory**: 2GB max (LRU eviction)  
**Persistence**: AOF (Append-Only File)

---

### Core Service Containers

#### 4. Market Data Service

```yaml
market_data_service:
  container_name: mastertrade_market_data
  build:
    context: ./market_data_service
    dockerfile: Dockerfile
  restart: always
  environment:
    DATABASE_URL: postgresql://mastertrade:mastertrade123@postgres:5432/mastertrade
    RABBITMQ_URL: amqp://mastertrade:mastertrade123@rabbitmq:5672/
    REDIS_URL: redis://redis:6379/0
    BINANCE_API_KEY: ${BINANCE_API_KEY}
    BINANCE_API_SECRET: ${BINANCE_API_SECRET}
    MORALIS_API_KEY: ${MORALIS_API_KEY}
    GLASSNODE_API_KEY: ${GLASSNODE_API_KEY}
    TWITTER_BEARER_TOKEN: ${TWITTER_BEARER_TOKEN}
    REDDIT_CLIENT_ID: ${REDDIT_CLIENT_ID}
    REDDIT_CLIENT_SECRET: ${REDDIT_CLIENT_SECRET}
  ports:
    - "8000:8000"
  depends_on:
    - postgres
    - rabbitmq
    - redis
  networks:
    - mastertrade_network
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
    interval: 30s
    timeout: 10s
    retries: 3
```

**Purpose**: Collect market data, sentiment, on-chain metrics  
**Dependencies**: PostgreSQL, RabbitMQ, Redis  
**External APIs**: Binance, Moralis, Glassnode, Twitter, Reddit

---

#### 5. Strategy Service

```yaml
strategy_service:
  container_name: mastertrade_strategy
  build:
    context: ./strategy_service
    dockerfile: Dockerfile
  restart: always
  environment:
    DATABASE_URL: postgresql://mastertrade:mastertrade123@postgres:5432/mastertrade
    RABBITMQ_URL: amqp://mastertrade:mastertrade123@rabbitmq:5672/
    REDIS_URL: redis://redis:6379/0
    MAX_ACTIVE_STRATEGIES: 10
    DAILY_GENERATION_COUNT: 500
    GENERATION_TIME: "03:00"  # 3:00 AM UTC
  ports:
    - "8006:8006"
  depends_on:
    - postgres
    - rabbitmq
    - redis
    - market_data_service
  networks:
    - mastertrade_network
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:8006/health"]
    interval: 30s
    timeout: 10s
    retries: 3
```

**Purpose**: Generate strategies, backtest, goal tracking  
**Daily Tasks**: 500 strategy generation at 3:00 AM UTC  
**Dependencies**: PostgreSQL, RabbitMQ, Redis, Market Data

---

#### 6. Order Executor

```yaml
order_executor:
  container_name: mastertrade_executor
  build:
    context: ./order_executor
    dockerfile: Dockerfile
  restart: always
  environment:
    DATABASE_URL: postgresql://mastertrade:mastertrade123@postgres:5432/mastertrade
    RABBITMQ_URL: amqp://mastertrade:mastertrade123@rabbitmq:5672/
    BINANCE_API_KEY: ${BINANCE_API_KEY}
    BINANCE_API_SECRET: ${BINANCE_API_SECRET}
    TRADING_ENVIRONMENT: paper  # or 'live'
    PAPER_TRADING_INITIAL_BALANCE: 10000
  ports:
    - "8081:8081"
  depends_on:
    - postgres
    - rabbitmq
  networks:
    - mastertrade_network
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:8081/health"]
    interval: 30s
    timeout: 10s
    retries: 3
```

**Purpose**: Execute orders (paper/live)  
**Modes**: Paper trading (default), Live trading  
**Critical**: Financial transactions

---

#### 7. Risk Manager

```yaml
risk_manager:
  container_name: mastertrade_risk
  build:
    context: ./risk_manager
    dockerfile: Dockerfile
  restart: always
  environment:
    DATABASE_URL: postgresql://mastertrade:mastertrade123@postgres:5432/mastertrade
    RABBITMQ_URL: amqp://mastertrade:mastertrade123@rabbitmq:5672/
    MAX_POSITION_SIZE_PCT: 0.20  # 20% max
    MAX_PORTFOLIO_DRAWDOWN_PCT: 0.15  # 15% max
    CIRCUIT_BREAKER_ENABLED: true
  ports:
    - "8080:8080"
  depends_on:
    - postgres
    - rabbitmq
  networks:
    - mastertrade_network
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
    interval: 30s
    timeout: 10s
    retries: 3
```

**Purpose**: Risk validation, circuit breakers  
**Critical**: Prevents excessive losses

---

#### 8. Alert System

```yaml
alert_system:
  container_name: mastertrade_alerts
  build:
    context: ./alert_system
    dockerfile: Dockerfile
  restart: always
  environment:
    DATABASE_URL: postgresql://mastertrade:mastertrade123@postgres:5432/mastertrade
    RABBITMQ_URL: amqp://mastertrade:mastertrade123@rabbitmq:5672/
    EMAIL_HOST: smtp.gmail.com
    EMAIL_PORT: 587
    EMAIL_USER: ${EMAIL_USER}
    EMAIL_PASSWORD: ${EMAIL_PASSWORD}
    TELEGRAM_BOT_TOKEN: ${TELEGRAM_BOT_TOKEN}
    DISCORD_WEBHOOK_URL: ${DISCORD_WEBHOOK_URL}
    SLACK_WEBHOOK_URL: ${SLACK_WEBHOOK_URL}
  ports:
    - "8007:8007"
  depends_on:
    - postgres
    - rabbitmq
  networks:
    - mastertrade_network
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:8007/health"]
    interval: 30s
    timeout: 10s
    retries: 3
```

**Purpose**: Multi-channel notifications  
**Channels**: Email, SMS, Telegram, Discord, Slack, Webhook

---

### Monitoring Containers

#### 9. Prometheus

```yaml
prometheus:
  container_name: mastertrade_prometheus
  image: prom/prometheus:latest
  restart: always
  command:
    - '--config.file=/etc/prometheus/prometheus.yml'
    - '--storage.tsdb.path=/prometheus'
    - '--storage.tsdb.retention.time=30d'
  ports:
    - "9090:9090"
  volumes:
    - ./monitoring/prometheus/prometheus.yml:/etc/prometheus/prometheus.yml
    - prometheus_data:/prometheus
  networks:
    - mastertrade_network
  healthcheck:
    test: ["CMD", "wget", "--spider", "-q", "http://localhost:9090/-/healthy"]
    interval: 30s
    timeout: 10s
    retries: 3
```

**Purpose**: Metrics collection and storage  
**Retention**: 30 days  
**Scrape Interval**: 15 seconds

---

#### 10. Grafana

```yaml
grafana:
  container_name: mastertrade_grafana
  image: grafana/grafana:latest
  restart: always
  environment:
    GF_SECURITY_ADMIN_USER: admin
    GF_SECURITY_ADMIN_PASSWORD: admin123
    GF_INSTALL_PLUGINS: grafana-piechart-panel
  ports:
    - "3001:3000"
  volumes:
    - grafana_data:/var/lib/grafana
    - ./monitoring/grafana/provisioning:/etc/grafana/provisioning
  depends_on:
    - prometheus
  networks:
    - mastertrade_network
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:3000/api/health"]
    interval: 30s
    timeout: 10s
    retries: 3
```

**Purpose**: Metrics visualization  
**Dashboards**: Pre-configured for system metrics  
**URL**: http://localhost:3001

---

#### 11. Monitoring UI

```yaml
monitoring_ui:
  container_name: mastertrade_ui
  build:
    context: ./monitoring_ui
    dockerfile: Dockerfile
  restart: always
  environment:
    API_GATEWAY_URL: http://api_gateway:8080
    DATA_ACCESS_API_URL: http://data_access_api:8005
  ports:
    - "3000:3000"
  depends_on:
    - api_gateway
    - data_access_api
  networks:
    - mastertrade_network
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:3000/api/health"]
    interval: 30s
    timeout: 10s
    retries: 3
```

**Purpose**: Web dashboard for monitoring  
**Framework**: Next.js  
**URL**: http://localhost:3000

---

## Network Architecture

### Docker Network

```yaml
networks:
  mastertrade_network:
    driver: bridge
    ipam:
      config:
        - subnet: 172.20.0.0/16
```

**Network Name**: `mastertrade_network`  
**Type**: Bridge  
**Subnet**: 172.20.0.0/16  
**DNS**: Automatic container name resolution

### Internal Communication

All containers communicate via container names:
- `postgres:5432` (not `localhost:5432`)
- `rabbitmq:5672`
- `redis:6379`
- `market_data_service:8000`

### External Access

Only exposed ports accessible from host:
- PostgreSQL: `localhost:5432`
- RabbitMQ: `localhost:5672`, `localhost:15672`
- Redis: `localhost:6379`
- Services: `localhost:8000-8081`
- Monitoring: `localhost:3000-3001`, `localhost:9090`

---

## Volume Mounts

### Persistent Volumes

```yaml
volumes:
  postgres_data:
    driver: local
  rabbitmq_data:
    driver: local
  redis_data:
    driver: local
  prometheus_data:
    driver: local
  grafana_data:
    driver: local
```

### Volume Locations

```bash
# Docker default volume location
/var/lib/docker/volumes/

# Project volumes:
mastertrade_postgres_data/_data       # ~50GB (database)
mastertrade_rabbitmq_data/_data       # ~10GB (message queues)
mastertrade_redis_data/_data          # ~2GB (cache)
mastertrade_prometheus_data/_data     # ~5GB (metrics, 30 days)
mastertrade_grafana_data/_data        # ~100MB (dashboards)
```

### Bind Mounts (Configuration)

```yaml
# Service-specific config files
./rabbitmq/rabbitmq.config → /etc/rabbitmq/rabbitmq.config
./rabbitmq/definitions.json → /etc/rabbitmq/definitions.json
./monitoring/prometheus/prometheus.yml → /etc/prometheus/prometheus.yml
./monitoring/grafana/provisioning → /etc/grafana/provisioning
```

---

## Environment Variables

### Required Environment Variables

Create `.env` file in project root:

```bash
# Binance API (Required for market data + trading)
BINANCE_API_KEY=your_binance_api_key
BINANCE_API_SECRET=your_binance_api_secret

# On-Chain Data (Required for whale alerts, on-chain metrics)
MORALIS_API_KEY=your_moralis_api_key
GLASSNODE_API_KEY=your_glassnode_api_key

# Social Sentiment (Required for sentiment analysis)
TWITTER_BEARER_TOKEN=your_twitter_bearer_token
REDDIT_CLIENT_ID=your_reddit_client_id
REDDIT_CLIENT_SECRET=your_reddit_client_secret
LUNARCRUSH_API_KEY=your_lunarcrush_api_key

# Alert Channels (Optional, for notifications)
EMAIL_USER=your_email@gmail.com
EMAIL_PASSWORD=your_email_app_password
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
DISCORD_WEBHOOK_URL=your_discord_webhook_url
SLACK_WEBHOOK_URL=your_slack_webhook_url

# SMS (Optional, for SMS alerts)
TWILIO_ACCOUNT_SID=your_twilio_sid
TWILIO_AUTH_TOKEN=your_twilio_token
TWILIO_PHONE_NUMBER=your_twilio_number
```

### Loading Environment Variables

```yaml
# In docker-compose.yml
services:
  market_data_service:
    env_file:
      - .env
    environment:
      DATABASE_URL: postgresql://mastertrade:mastertrade123@postgres:5432/mastertrade
      RABBITMQ_URL: amqp://mastertrade:mastertrade123@rabbitmq:5672/
      # .env variables automatically loaded
```

---

## Health Checks

### Health Check Endpoints

All services expose `/health` endpoint:

```json
{
  "status": "healthy",
  "service": "market_data_service",
  "version": "1.0.0",
  "uptime": 3600,
  "checks": {
    "database": "ok",
    "rabbitmq": "ok",
    "redis": "ok"
  }
}
```

### Docker Health Check Commands

```bash
# Check all container health status
docker ps --format "table {{.Names}}\t{{.Status}}"

# Check specific service
docker inspect --format='{{.State.Health.Status}}' mastertrade_strategy

# View health check logs
docker inspect --format='{{json .State.Health}}' mastertrade_strategy | jq
```

### Health Check Configuration

```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
  interval: 30s      # Check every 30 seconds
  timeout: 10s       # Timeout after 10 seconds
  retries: 3         # Retry 3 times before marking unhealthy
  start_period: 60s  # Grace period for startup
```

---

## Resource Limits

### Container Resource Allocation

```yaml
# Example: Strategy Service with resource limits
strategy_service:
  deploy:
    resources:
      limits:
        cpus: '2.0'
        memory: 4G
      reservations:
        cpus: '1.0'
        memory: 2G
```

### Recommended Resource Limits

| Service | CPU Limit | Memory Limit | CPU Reserve | Memory Reserve |
|---------|-----------|--------------|-------------|----------------|
| postgres | 2.0 | 4G | 1.0 | 2G |
| rabbitmq | 1.0 | 2G | 0.5 | 1G |
| redis | 1.0 | 2G | 0.5 | 1G |
| market_data_service | 2.0 | 4G | 1.0 | 2G |
| strategy_service | 4.0 | 8G | 2.0 | 4G |
| order_executor | 1.0 | 2G | 0.5 | 1G |
| risk_manager | 1.0 | 2G | 0.5 | 1G |
| alert_system | 0.5 | 1G | 0.25 | 512M |

**Total System Requirements**: 16 CPU cores, 32GB RAM (recommended)

---

## Deployment Procedures

### Initial Deployment

```bash
# 1. Clone repository
git clone https://github.com/your-org/mastertrade.git
cd mastertrade

# 2. Create .env file with API keys
cp .env.example .env
nano .env  # Add your API keys

# 3. Build all images
docker-compose build

# 4. Start infrastructure first
docker-compose up -d postgres rabbitmq redis

# 5. Wait for infrastructure to be healthy (30 seconds)
sleep 30

# 6. Initialize database schema
docker exec mastertrade_postgres psql -U mastertrade -d mastertrade -f /docker-entrypoint-initdb.d/init.sql

# 7. Start all services
docker-compose up -d

# 8. Check health status
docker ps --format "table {{.Names}}\t{{.Status}}"

# 9. View logs
docker-compose logs -f
```

### Using start.sh Script

```bash
# Automated startup script
chmod +x start.sh
./start.sh
```

**start.sh** performs:
1. Environment check (.env file)
2. Docker availability check
3. Infrastructure startup
4. Database initialization
5. Service startup
6. Health check validation

---

### Update Deployment

```bash
# 1. Pull latest changes
git pull origin main

# 2. Rebuild changed services
docker-compose build <service_name>

# 3. Restart specific service (zero-downtime)
docker-compose up -d --no-deps <service_name>

# Example: Update strategy service
docker-compose build strategy_service
docker-compose up -d --no-deps strategy_service
```

---

### Full System Restart

```bash
# Stop all services
docker-compose down

# Start all services
docker-compose up -d

# Or use start.sh
./start.sh
```

---

### Scaling Services

```bash
# Scale strategy service to 5 instances
docker-compose up -d --scale strategy_service=5

# Scale market data service to 3 instances
docker-compose up -d --scale market_data_service=3

# Verify scaling
docker ps | grep strategy_service
```

---

### Backup Procedures

```bash
# 1. Backup PostgreSQL database
docker exec mastertrade_postgres pg_dump -U mastertrade -d mastertrade -F c -f /backups/mastertrade_$(date +%Y%m%d).dump

# 2. Backup volumes
docker run --rm -v mastertrade_postgres_data:/data -v $(pwd)/backups:/backup alpine tar czf /backup/postgres_data_$(date +%Y%m%d).tar.gz /data

# 3. Backup RabbitMQ definitions
curl -u mastertrade:mastertrade123 http://localhost:15672/api/definitions > backups/rabbitmq_definitions_$(date +%Y%m%d).json
```

---

### Restore Procedures

```bash
# 1. Stop services
docker-compose down

# 2. Restore PostgreSQL database
docker exec mastertrade_postgres pg_restore -U mastertrade -d mastertrade -c /backups/mastertrade_20251113.dump

# 3. Restore volumes
docker run --rm -v mastertrade_postgres_data:/data -v $(pwd)/backups:/backup alpine tar xzf /backup/postgres_data_20251113.tar.gz -C /

# 4. Start services
docker-compose up -d
```

---

## Troubleshooting

### Common Issues

#### 1. Container Won't Start

```bash
# Check logs
docker-compose logs <service_name>

# Check health status
docker inspect --format='{{json .State.Health}}' <container_name> | jq

# Restart container
docker-compose restart <service_name>
```

---

#### 2. Database Connection Errors

```bash
# Check if postgres is running
docker ps | grep postgres

# Test connection from container
docker exec mastertrade_strategy psql -h postgres -U mastertrade -d mastertrade -c "SELECT 1;"

# Check postgres logs
docker logs mastertrade_postgres
```

---

#### 3. RabbitMQ Connection Errors

```bash
# Check RabbitMQ status
docker exec mastertrade_rabbitmq rabbitmqctl status

# Check connections
docker exec mastertrade_rabbitmq rabbitmqctl list_connections

# Reset RabbitMQ
docker-compose restart rabbitmq
```

---

#### 4. High Memory Usage

```bash
# Check container resource usage
docker stats

# Identify memory hog
docker stats --no-stream --format "table {{.Container}}\t{{.MemUsage}}" | sort -k 2 -h

# Restart high-memory container
docker-compose restart <service_name>
```

---

#### 5. Disk Space Issues

```bash
# Check Docker disk usage
docker system df

# Remove unused images
docker image prune -a

# Remove unused volumes (CAREFUL!)
docker volume prune

# Remove stopped containers
docker container prune
```

---

### Logging

```bash
# View logs for specific service
docker-compose logs -f <service_name>

# View logs for all services
docker-compose logs -f

# View last 100 lines
docker-compose logs --tail=100 <service_name>

# Save logs to file
docker-compose logs <service_name> > logs/service_$(date +%Y%m%d).log
```

---

### Performance Monitoring

```bash
# Real-time resource usage
docker stats

# Container inspect
docker inspect <container_name>

# Network inspection
docker network inspect mastertrade_network

# Volume inspection
docker volume inspect mastertrade_postgres_data
```

---

**Previous**: [05_MESSAGE_BROKER.md](./05_MESSAGE_BROKER.md) - RabbitMQ topology  
**Architecture Index**: [README.md](./README.md) - Documentation index
