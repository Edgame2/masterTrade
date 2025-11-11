# Enhanced MasterTrade System — Focused TODO

This document provides a detailed, actionable TODO list for enhancing the MasterTrade system. This plan builds on **existing infrastructure** (PostgreSQL, RabbitMQ, FastAPI microservices) and focuses on high-impact additions.

---

## Executive Summary

**Goal**: Enhance the existing MasterTrade platform with:

1. **Data source expansion**: On-chain analytics, social sentiment, institutional flow data (40+ sources).
2. **Goal-oriented trading**: Position sizing and risk management targeting 10% monthly gain, €4k monthly income, €1M portfolio.
3. **Enhanced Monitor UI**: Data source management, alpha attribution, advanced analytics.
4. **ML enhancements**: Feature store, AutoML optimization, explainability.
5. **Redis caching layer**: Query cache, signal buffer, session management.

**Architecture**: Build on existing PostgreSQL + RabbitMQ foundation. No database replacement required.

---

## Critical Integration Points

### Existing Services to Extend:
1. **`market_data_service/main.py`** (line 86+) - `MarketDataService` class
   - Add new collectors: on-chain, social, institutional
   - Integrate with existing `Database` class from `database.py`
   - Follow pattern: `self.sentiment_collector`, `self.stock_index_collector`

2. **`risk_manager/position_sizing.py`** (line 53+) - `PositionSizingEngine` class
   - Integrate goal-oriented sizing module
   - Extend `calculate_position_size()` method (line 78+)
   - Use existing `RiskPostgresDatabase` for goal tracking

3. **`strategy_service/main.py`** (line 1+) - Strategy service orchestration
   - Add feature store integration
   - Consume new RabbitMQ messages (whale alerts, social sentiment)
   - Use existing `Database` and RabbitMQ connections

4. **`docker-compose.yml`** (line 1+) - Service orchestration
   - Add Redis service (after line 315)
   - Update service environment variables
   - Maintain existing network: `mastertrade_network`

5. **`monitoring_ui/`** - Next.js monitoring application
   - Add new pages: data-sources, goals, alpha-attribution
   - Use existing app router structure
   - Connect to existing API Gateway (port 8090)

### Database Integration:
- **`market_data_service/database.py`** - `Database` class (line 47+)
  - Add methods for on-chain, social, institutional data
  - Use existing `shared/postgres_manager.py` PostgresManager
  - Follow pattern: `@ensure_connection` decorator

- **`risk_manager/database.py`** - `RiskPostgresDatabase` class
  - Add goal tracking methods
  - Cache integration with Redis
  - Extend existing connection pooling

### Message Queue Integration:
- Create `shared/message_schemas.py` for new message types
- Follow existing RabbitMQ usage pattern in `market_data_service/main.py` (line 500+)
- Use `aio_pika` library consistently across all services

---

## Priority Matrix

* **P0** (Critical): Must-have for core functionality enhancement.
* **P1** (High): Important for competitive edge.
* **P2** (Medium): Nice-to-have enhancements.
* **P3** (Low): Future improvements.

---

## Phased Roadmap

### Phase 1 (Weeks 1–2) — Data Source Expansion
* Implement on-chain data collectors (Moralis, Glassnode).
* Implement social sentiment collectors (Twitter/X, Reddit, LunarCrush).
* Add Redis caching layer for API responses and real-time signals.
* Enhance existing `MacroEconomicCollector` with additional indicators.

### Phase 2 (Weeks 3–4) — Goal-Oriented System
* Implement goal-oriented position sizing module.
* Add financial target tracking system (monthly returns, income, portfolio value).
* Implement adaptive risk management based on goal progress.
* Create goal-oriented backtesting evaluation framework.

### Phase 3 (Weeks 5–6) — ML & Intelligence
* Implement feature store (Feast or custom PostgreSQL-based).
* Integrate AutoML (Optuna) for hyperparameter optimization.
* Add SHAP/LIME explainability for model decisions.
* Implement online learning with concept drift detection.

### Phase 4 (Weeks 7–8) — Monitor UI & Operations
* Build data source management UI (enable/disable sources, rate limits, costs).
* Implement alpha attribution dashboard (performance by data source).
* Add RBAC user management with audit logs.
* Enhanced alerting with Slack, email, webhook integrations.

---

# Detailed TODO List

---

## A. Data Sources & Collectors (NEW)

### A.1. On-Chain Data Collectors (NEW)

**Integration Point**: Extend `MarketDataService` class in `market_data_service/main.py` (line 86+)

* **Task**: Implement `onchain_collector.py` base class with rate limiting and retry logic. — *Backend* — P0
  * Location: `market_data_service/collectors/onchain_collector.py`
  * Inherit pattern from existing `market_data_service/sentiment_data_collector.py`
  * Use existing `Database` class from `market_data_service/database.py`
  * Integrate with `MarketDataService` initialization (similar to `self.sentiment_collector`)
  * Support multiple on-chain data providers with circuit breaker pattern

* **Task**: Integrate Moralis API for whale transactions and DEX trade data. — *Data Team* — P0
  * File: `market_data_service/collectors/moralis_collector.py`
  * Class: `MoralisCollector` (similar to `SentimentDataCollector` structure)
  * Endpoints: `/wallets/{address}/history`, `/tokens/{address}/transfers`
  * Track wallets with >1000 BTC/ETH, store in `whale_transactions` table
  * Add to `MarketDataService.__init__()`: `self.moralis_collector = MoralisCollector(self.database)`
  * Start collection in `MarketDataService._start_onchain_collection()` method
  * Cost: ~$300/month for Pro plan

* **Task**: Integrate Glassnode for on-chain metrics (NVT, MVRV, exchange flows). — *Data Team* — P1
  * File: `market_data_service/collectors/glassnode_collector.py`
  * Class: `GlassnodeCollector`
  * Metrics: Net Unrealized Profit/Loss, Exchange NetFlow, Active Addresses
  * Store via `Database.store_onchain_metrics()` method (to be added)
  * Integration: Add scheduler similar to `macro_economic_scheduler.py` pattern
  * Cost: ~$500/month for Advanced plan

* **Task**: Integrate Nansen for smart money tracking and wallet labels. — *Data Team* — P1
  * File: `market_data_service/collectors/nansen_collector.py`
  * Class: `NansenCollector`
  * Track "Smart Money" wallet movements
  * Store wallet labels in `wallet_labels` table via `Database.store_wallet_label()`
  * Cost: ~$150/month for Lite plan

* **Task**: Add on-chain data methods to `Database` class. — *Backend* — P0
  * File: `market_data_service/database.py` (add to existing Database class at line 47+)
  * Methods to add:
    ```python
    @ensure_connection
    async def store_whale_transaction(self, tx_data: Dict) -> bool
    
    @ensure_connection
    async def store_onchain_metrics(self, metrics: List[Dict]) -> bool
    
    @ensure_connection
    async def store_wallet_label(self, address: str, label: str, category: str) -> bool
    
    @ensure_connection
    async def get_whale_transactions(self, symbol: str, hours: int = 24) -> List[Dict]
    ```

* **Task**: Create PostgreSQL schema for on-chain data. — *DBA* — P0
  * Execute via `shared/postgres_manager.py` PostgresManager class
  * Add schema initialization to `Database._ensure_tables()` method in `market_data_service/database.py`
  ```sql
  -- Tables: whale_transactions, onchain_metrics, wallet_labels, dex_trades
  -- See Section C.1 for full schema
  ```

### A.2. Social Sentiment Collectors (NEW)

**Integration Point**: Extend existing `SentimentDataCollector` pattern in `market_data_service/mock_components.py`

* **Task**: Implement `social_collector.py` base class with NLP sentiment pipeline. — *Backend/ML* — P0
  * Location: `market_data_service/collectors/social_collector.py`
  * Base class pattern similar to `market_data_service/sentiment_data_collector.py`
  * Use VADER or FinBERT for sentiment scoring
  * Store via `Database.store_social_sentiment()` method (to be added)
  * Integrate with existing `Database` class from `market_data_service/database.py`

* **Task**: Integrate Twitter/X API v2 for real-time crypto sentiment. — *Data Team* — P0
  * File: `market_data_service/collectors/twitter_collector.py`
  * Class: `TwitterCollector(SocialCollector)`
  * Track: @APompliano, @100trillionUSD, @cz_binance, #Bitcoin, #Crypto
  * Streaming endpoint for real-time tweets
  * Add to `MarketDataService.__init__()`: `self.twitter_collector = TwitterCollector(self.database)`
  * Start in `_start_social_collection()` method (similar to `_start_sentiment_collection()` at line 816)
  * Cost: ~$100/month for Basic tier

* **Task**: Integrate Reddit API for r/cryptocurrency and r/bitcoin sentiment. — *Data Team* — P0
  * File: `market_data_service/collectors/reddit_collector.py`
  * Class: `RedditCollector(SocialCollector)`
  * Track: Post sentiment, upvotes, comment sentiment
  * Store in `social_sentiment` table with reddit-specific metadata
  * Use same integration pattern as Twitter collector
  * Cost: Free (rate limited to 60 requests/minute)

* **Task**: Integrate LunarCrush for aggregated social metrics. — *Data Team* — P1
  * File: `market_data_service/collectors/lunarcrush_collector.py`
  * Class: `LunarCrushCollector`
  * Metrics: AltRank, Galaxy Score, social volume, sentiment
  * Store in `social_metrics_aggregated` table
  * Create scheduler: `market_data_service/social_metrics_scheduler.py` (pattern from `macro_economic_scheduler.py`)
  * Cost: ~$200/month for Pro plan

* **Task**: Add social sentiment methods to `Database` class. — *Backend* — P0
  * File: `market_data_service/database.py` (extend existing Database class)
  * Add methods after existing sentiment methods (around line 800+):
    ```python
    @ensure_connection
    async def store_social_sentiment(self, sentiment_data: Dict) -> bool
    
    @ensure_connection
    async def store_social_metrics_aggregated(self, metrics: Dict) -> bool
    
    @ensure_connection
    async def get_social_sentiment(self, symbol: str, hours: int = 24, source: str = None) -> List[Dict]
    
    @ensure_connection
    async def get_trending_topics(self, limit: int = 10) -> List[Dict]
    ```

### A.3. Institutional Flow Data (NEW)

* **Task**: Integrate Kaiko for institutional order book and trade data. — *Data Team* — P1
  * File: `market_data_service/collectors/kaiko_collector.py`
  * Data: Order book snapshots (every 1s), trade ticks, VWAP
  * Detect large block trades (>$100k) as institutional signals
  * Store in `institutional_trades` table
  * Cost: ~$1,000/month for Professional tier

* **Task**: Integrate CoinMetrics for market and on-chain institutional data. — *Data Team* — P1
  * File: `market_data_service/collectors/coinmetrics_collector.py`
  * Metrics: Network value, realized cap, Coinbase premium
  * Cost: ~$500/month for Pro plan

* **Task**: Implement whale alert detection system. — *Backend* — P0
  * File: `market_data_service/whale_alert_detector.py`
  * Detect: Transactions >$1M, large exchange inflows/outflows
  * Publish alerts to RabbitMQ for real-time strategy consumption
  * Store in `whale_alerts` table

### A.4. Enhance Existing Collectors

* **Task**: Expand `MacroEconomicCollector` with additional FRED indicators. — *Data Team* — P1
  * Add: M2 Money Supply, Consumer Credit, Fed Balance Sheet
  * File: `market_data_service/macro_economic_collector.py` (EXISTING)

* **Task**: Add real-time forex data (DXY, EUR/USD, JPY/USD). — *Data Team* — P1
  * File: `market_data_service/collectors/forex_collector.py`
  * Use Alpha Vantage or Twelve Data API
  * Cost: ~$50/month

---

## B. Data Ingestion & Processing (ENHANCEMENT)

### B.1. Base Collector Framework (ENHANCEMENT)

**Integration Point**: Extend existing collector pattern in `market_data_service/`

* **Task**: Implement adaptive rate limiter for API calls. — *Backend* — P0
  * File: `market_data_service/utils/adaptive_rate_limiter.py`
  * Track API response times, adjust request rate dynamically
  * Support per-source rate limits (configurable via `Database.get_collector_config()`)
  * Use pattern similar to existing retry logic in collectors

* **Task**: Implement circuit breaker pattern for collector failures. — *Backend* — P0
  * File: `market_data_service/utils/circuit_breaker.py`
  * Auto-disable collectors after 5 consecutive failures
  * Auto-recovery after cooldown period (5 minutes)
  * Log failures via `Database.log_collector_health()` method
  * Integrate with existing collectors by wrapping collection methods

* **Task**: Add collector health monitoring to `Database` class. — *Backend* — P0
  * File: `market_data_service/database.py` (extend Database class)
  * Add methods:
    ```python
    @ensure_connection
    async def log_collector_health(self, collector_name: str, status: str, error_msg: str = None)
    
    @ensure_connection
    async def get_collector_health(self, collector_name: str = None) -> List[Dict]
    
    @ensure_connection
    async def update_collector_metrics(self, collector_name: str, metric_name: str, value: float)
    ```

* **Task**: Add health check endpoints to `MarketDataService`. — *Backend* — P0
  * File: `market_data_service/main.py`
  * Add HTTP endpoints to existing service (after line 1000+):
    ```python
    @app.get("/health/collectors")
    async def get_collectors_health():
        return await database.get_collector_health()
    
    @app.get("/health/collectors/{collector_name}")
    async def get_collector_health(collector_name: str):
        return await database.get_collector_health(collector_name)
    ```


### B.2. Real-Time Data Processing (ENHANCEMENT)

**Integration Point**: Extend existing RabbitMQ messaging in all services

* **Task**: Define message schemas for new data sources. — *Backend* — P0
  * File: `shared/message_schemas.py` (create new file, pattern from existing RabbitMQ usage)
  * Define schemas:
    ```python
    from pydantic import BaseModel
    from typing import Optional, List
    from datetime import datetime
    
    class WhaleAlertMessage(BaseModel):
        alert_id: str
        alert_type: str  # large_transfer, exchange_inflow, exchange_outflow
        symbol: str
        amount_usd: float
        from_entity: Optional[str]
        to_entity: Optional[str]
        significance_score: float
        timestamp: datetime
    
    class SocialSentimentUpdate(BaseModel):
        symbol: str
        source: str
        sentiment_score: float
        social_volume: int
        timestamp: datetime
    
    class InstitutionalFlowSignal(BaseModel):
        symbol: str
        flow_type: str  # block_trade, unusual_volume
        size_usd: float
        exchange: str
        timestamp: datetime
    ```

* **Task**: Enhance RabbitMQ publishing in collectors. — *Backend* — P0
  * Update collectors to publish to RabbitMQ using existing pattern
  * Example in `market_data_service/collectors/moralis_collector.py`:
    ```python
    # Use existing RabbitMQ connection from MarketDataService
    await self.service.rabbitmq_channel.default_exchange.publish(
        aio_pika.Message(body=json.dumps(whale_alert).encode()),
        routing_key='whale_alerts'
    )
    ```
  * Follow pattern from existing `MarketDataService._publish_to_rabbitmq()` method (line 500+)

* **Task**: Create real-time signal aggregation service. — *Backend* — P0
  * File: `market_data_service/signal_aggregator.py`
  * Class: `SignalAggregator`
  * Combine: price data, sentiment, on-chain signals, institutional flow
  * Publish composite signals to RabbitMQ exchange `market_signals`
  * Add to `MarketDataService.__init__()`: `self.signal_aggregator = SignalAggregator(self.database, self.rabbitmq_channel)`
  * Start in background task: `asyncio.create_task(self.signal_aggregator.run())`
  * Update every 1 minute

* **Task**: Add message consumers in `strategy_service`. — *Backend* — P0
  * File: `strategy_service/main.py`
  * Add RabbitMQ consumers for new message types (follow existing pattern around line 200+)
  * Subscribe to queues: `whale_alerts`, `social_sentiment_updates`, `institutional_flow_signals`
  * Process messages in strategy evaluation logic

### B.3. Redis Caching Layer (NEW)

**Integration Point**: Add Redis service and client library to all services

* **Task**: Deploy Redis instance for caching. — *Infra* — P0
  * File: `docker-compose.yml` (add to existing services after line 315)
  * Add service:
    ```yaml
    redis:
      image: redis:7-alpine
      container_name: mastertrade_redis
      ports:
        - "6379:6379"
      volumes:
        - redis_data:/data
      networks:
        - mastertrade_network
      command: redis-server --appendonly yes --maxmemory 2gb --maxmemory-policy allkeys-lru
      healthcheck:
        test: ["CMD", "redis-cli", "ping"]
        interval: 10s
        timeout: 3s
        retries: 3
      restart: unless-stopped
    ```
  * Add volume: `redis_data:` to volumes section

* **Task**: Implement Redis cache client. — *Backend* — P0
  * File: `shared/redis_client.py` (new file in shared directory)
  * Use `aioredis` library for async operations
  * Class: `RedisCacheManager`
  * Methods: `get()`, `set()`, `delete()`, `exists()`, `expire()`
  * Connection pooling with retry logic
  * Example:
    ```python
    import aioredis
    from typing import Optional, Any
    import json
    
    class RedisCacheManager:
        def __init__(self, redis_url: str = "redis://localhost:6379"):
            self.redis_url = redis_url
            self.redis: Optional[aioredis.Redis] = None
        
        async def connect(self):
            self.redis = await aioredis.from_url(self.redis_url, encoding="utf-8", decode_responses=True)
        
        async def get(self, key: str) -> Optional[Any]:
            value = await self.redis.get(key)
            return json.loads(value) if value else None
        
        async def set(self, key: str, value: Any, ttl: int = 3600):
            await self.redis.setex(key, ttl, json.dumps(value))
    ```

* **Task**: Integrate Redis caching in `market_data_service`. — *Backend* — P0
  * File: `market_data_service/database.py`
  * Add `RedisCacheManager` instance to `Database.__init__()`
  * Wrap expensive queries with cache checks:
    ```python
    async def get_onchain_metrics(self, symbol: str):
        cache_key = f"onchain_metrics:{symbol}"
        cached = await self.cache.get(cache_key)
        if cached:
            return cached
        
        # Fetch from database
        result = await self._fetch_from_db(symbol)
        await self.cache.set(cache_key, result, ttl=300)  # 5 min TTL
        return result
    ```

* **Task**: Integrate Redis caching in `risk_manager`. — *Backend* — P0
  * File: `risk_manager/database.py`
  * Add `RedisCacheManager` to `RiskPostgresDatabase` class (around line 50+)
  * Cache backtest results with 24-hour TTL
  * Cache position sizing calculations with 1-minute TTL

* **Task**: Implement signal buffer in Redis. — *Backend* — P0
  * File: `market_data_service/signal_aggregator.py`
  * Store last 1000 signals in Redis sorted set
  * Key: `signals:recent`, Score: timestamp
  * TTL: 24 hours
  * Use Redis ZADD and ZRANGE commands

* **Task**: Add Redis environment variables to services. — *DevOps* — P0
  * File: `docker-compose.yml`
  * Add to all services:
    ```yaml
    environment:
      - REDIS_URL=redis://redis:6379
    ```
  * Update `.env.example` with `REDIS_URL=redis://localhost:6379`

---

## C. Storage Layer (POSTGRESQL ENHANCEMENT)

**Note**: Keep existing PostgreSQL as primary database. No MongoDB, Neo4j, or TimescaleDB needed.

### C.1. PostgreSQL Schema Extensions

* **Task**: Create schema for on-chain data. — *DBA* — P0
  ```sql
  CREATE TABLE whale_transactions (
    id SERIAL PRIMARY KEY,
    tx_hash VARCHAR(66) UNIQUE NOT NULL,
    from_address VARCHAR(42),
    to_address VARCHAR(42),
    symbol VARCHAR(20),
    amount_usd DECIMAL(20,2),
    timestamp TIMESTAMP NOT NULL,
    chain VARCHAR(20),
    created_at TIMESTAMP DEFAULT NOW()
  );
  CREATE INDEX idx_whale_timestamp ON whale_transactions(timestamp DESC);
  CREATE INDEX idx_whale_symbol ON whale_transactions(symbol);

  CREATE TABLE onchain_metrics (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    metric_name VARCHAR(50) NOT NULL,
    metric_value DECIMAL(20,8),
    timestamp TIMESTAMP NOT NULL,
    source VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(symbol, metric_name, timestamp, source)
  );
  CREATE INDEX idx_onchain_metrics ON onchain_metrics(symbol, metric_name, timestamp DESC);

  CREATE TABLE wallet_labels (
    id SERIAL PRIMARY KEY,
    address VARCHAR(42) UNIQUE NOT NULL,
    label VARCHAR(100),
    category VARCHAR(50), -- exchange, whale, smart_money, institution
    last_seen TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
  );
  ```

* **Task**: Create schema for social sentiment data. — *DBA* — P0
  ```sql
  CREATE TABLE social_sentiment (
    id SERIAL PRIMARY KEY,
    source VARCHAR(50) NOT NULL, -- twitter, reddit, lunarcrush
    symbol VARCHAR(20) NOT NULL,
    text TEXT,
    sentiment_score DECIMAL(5,4), -- -1.0 to 1.0
    engagement_count INT, -- likes, upvotes, retweets
    author VARCHAR(100),
    url TEXT,
    timestamp TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
  );
  CREATE INDEX idx_social_sentiment ON social_sentiment(symbol, timestamp DESC);
  CREATE INDEX idx_social_source ON social_sentiment(source, timestamp DESC);

  CREATE TABLE social_metrics_aggregated (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    social_volume INT,
    social_sentiment DECIMAL(5,4),
    altrank INT,
    galaxy_score DECIMAL(10,2),
    timestamp TIMESTAMP NOT NULL,
    source VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(symbol, timestamp, source)
  );
  CREATE INDEX idx_social_metrics ON social_metrics_aggregated(symbol, timestamp DESC);
  ```

* **Task**: Create schema for institutional flow data. — *DBA* — P1
  ```sql
  CREATE TABLE institutional_trades (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    trade_size_usd DECIMAL(20,2),
    price DECIMAL(20,8),
    side VARCHAR(10), -- buy, sell
    exchange VARCHAR(50),
    timestamp TIMESTAMP NOT NULL,
    is_block_trade BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
  );
  CREATE INDEX idx_institutional_trades ON institutional_trades(symbol, timestamp DESC);
  CREATE INDEX idx_block_trades ON institutional_trades(is_block_trade, timestamp DESC);

  CREATE TABLE whale_alerts (
    id SERIAL PRIMARY KEY,
    alert_type VARCHAR(50), -- large_transfer, exchange_inflow, exchange_outflow
    symbol VARCHAR(20) NOT NULL,
    amount_usd DECIMAL(20,2),
    from_entity VARCHAR(100),
    to_entity VARCHAR(100),
    significance_score DECIMAL(5,2), -- 0-100
    timestamp TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
  );
  CREATE INDEX idx_whale_alerts ON whale_alerts(symbol, timestamp DESC);
  ```

* **Task**: Create schema for collector health monitoring. — *DBA* — P0
  ```sql
  CREATE TABLE collector_health (
    id SERIAL PRIMARY KEY,
    collector_name VARCHAR(100) NOT NULL,
    status VARCHAR(20), -- healthy, degraded, failed
    last_success TIMESTAMP,
    last_failure TIMESTAMP,
    error_message TEXT,
    response_time_ms INT,
    requests_count INT DEFAULT 0,
    errors_count INT DEFAULT 0,
    updated_at TIMESTAMP DEFAULT NOW()
  );
  CREATE UNIQUE INDEX idx_collector_name ON collector_health(collector_name);

  CREATE TABLE collector_metrics (
    id SERIAL PRIMARY KEY,
    collector_name VARCHAR(100) NOT NULL,
    metric_name VARCHAR(50),
    metric_value DECIMAL(20,4),
    timestamp TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
  );
  CREATE INDEX idx_collector_metrics ON collector_metrics(collector_name, timestamp DESC);
  ```

### C.2. PostgreSQL Optimization

* **Task**: Implement table partitioning for large tables. — *DBA* — P1
  * Partition `whale_transactions`, `social_sentiment`, `onchain_metrics` by month
  * Use native PostgreSQL partitioning (declarative partitioning)
  * Automated partition creation for future months

* **Task**: Implement data retention policies. — *DBA* — P1
  * High-frequency data (1m, 5m): Keep 90 days
  * Daily data: Keep 2 years
  * Aggregated data: Keep indefinitely
  * Automated cleanup job (cron or pg_cron extension)

* **Task**: Add PostgreSQL connection pooling optimization. — *Backend* — P0
  * Use PgBouncer for connection pooling
  * Configuration: Pool size = 20, max connections = 100
  * Add to `docker-compose.yml`

---

## D. APIs & WebSocket Interfaces (ENHANCEMENT)

### D.1. REST API Extensions

**Note**: Extend existing FastAPI endpoints in `market_data_service/main.py`.

* **Task**: Add data source management endpoints. — *Backend* — P0
  ```python
  GET /api/v1/data-sources - List all data sources with status
  POST /api/v1/data-sources/{source_id}/enable - Enable data source
  POST /api/v1/data-sources/{source_id}/disable - Disable data source
  PUT /api/v1/data-sources/{source_id}/config - Update rate limits, priority
  GET /api/v1/data-sources/{source_id}/metrics - Get source performance metrics
  ```

* **Task**: Add on-chain data query endpoints. — *Backend* — P0
  ```python
  GET /api/v1/onchain/whale-transactions - Query whale transactions
  GET /api/v1/onchain/metrics/{symbol} - Get on-chain metrics for symbol
  GET /api/v1/onchain/wallet/{address} - Get wallet information
  ```

* **Task**: Add social sentiment query endpoints. — *Backend* — P0
  ```python
  GET /api/v1/social/sentiment/{symbol} - Get aggregated sentiment
  GET /api/v1/social/trending - Get trending topics
  GET /api/v1/social/influencers - Get influencer sentiment
  ```

* **Task**: Add institutional flow endpoints. — *Backend* — P1
  ```python
  GET /api/v1/institutional/block-trades - Query block trades
  GET /api/v1/institutional/flow/{symbol} - Get institutional flow for symbol
  ```

### D.2. WebSocket Real-Time Streams (NEW)

* **Task**: Implement WebSocket endpoint for whale alerts. — *Backend* — P0
  * Endpoint: `ws://market_data_service:8000/ws/whale-alerts`
  * Push notifications when whale transactions detected (>$1M)
  * Authentication required (API key in query params)

* **Task**: Implement WebSocket endpoint for sentiment spikes. — *Backend* — P1
  * Endpoint: `ws://market_data_service:8000/ws/sentiment-alerts`
  * Push when sentiment changes >20% in 5 minutes
  * Include symbol, old sentiment, new sentiment, source

* **Task**: Implement WebSocket endpoint for institutional flow alerts. — *Backend* — P1
  * Endpoint: `ws://market_data_service:8000/ws/institutional-flow`
  * Push when large block trades detected (>$100k)

---

## E. Goal-Oriented Trading System (NEW)

### E.1. Financial Target Tracking

* **Task**: Create financial goals configuration table. — *DBA* — P0
  ```sql
  CREATE TABLE financial_goals (
    id SERIAL PRIMARY KEY,
    goal_type VARCHAR(50), -- monthly_return, monthly_income, portfolio_value
    target_value DECIMAL(20,2),
    current_value DECIMAL(20,2),
    progress_percent DECIMAL(5,2),
    target_date DATE,
    status VARCHAR(20), -- on_track, at_risk, achieved
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
  );

  CREATE TABLE goal_progress_history (
    id SERIAL PRIMARY KEY,
    goal_id INT REFERENCES financial_goals(id),
    snapshot_date DATE,
    actual_value DECIMAL(20,2),
    target_value DECIMAL(20,2),
    variance_percent DECIMAL(5,2),
    created_at TIMESTAMP DEFAULT NOW()
  );
  ```

* **Task**: Implement goal tracking service. — *Backend* — P0
  * File: `strategy_service/goal_tracking_service.py`
  * Calculate daily progress toward goals
  * Store snapshots in `goal_progress_history`
  * Alert when goals are at risk (>20% below target)

### E.2. Goal-Oriented Position Sizing (NEW)

**Integration Point**: Extend existing `PositionSizingEngine` in `risk_manager/position_sizing.py`

* **Task**: Implement goal-based position sizing algorithm. — *Quant* — P0
  * File: `risk_manager/goal_oriented_sizing.py` (new module)
  * Class: `GoalOrientedSizingModule`
  * Integrate with existing `PositionSizingEngine` class (line 53+)
  * Methods:
    ```python
    class GoalOrientedSizingModule:
        def __init__(self, database: RiskPostgresDatabase):
            self.database = database
        
        async def calculate_goal_adjustment_factor(
            self, 
            current_portfolio_value: float,
            monthly_return_progress: float,
            monthly_income_progress: float
        ) -> float:
            """
            Calculate position size adjustment based on goal progress
            
            Returns: multiplier between 0.7 and 1.3
            - Behind on goals: 1.1 to 1.3 (increase size)
            - On track: 1.0 (normal size)
            - Ahead: 0.7 to 0.9 (reduce size, protect gains)
            - Near €1M: 0.5 to 0.7 (capital preservation mode)
            """
            # Implementation logic
            pass
    ```

* **Task**: Integrate goal adjustment into `PositionSizingEngine`. — *Quant* — P0
  * File: `risk_manager/position_sizing.py`
  * Modify `calculate_position_size()` method (line 78+)
  * Add after line 139 (after portfolio constraints):
    ```python
    # Apply goal-based adjustment
    if hasattr(self, 'goal_sizing_module'):
        goals_data = await self.database.get_current_goal_progress()
        goal_factor = await self.goal_sizing_module.calculate_goal_adjustment_factor(
            portfolio_value=available_balance,
            monthly_return_progress=goals_data['monthly_return_progress'],
            monthly_income_progress=goals_data['monthly_income_progress']
        )
        portfolio_adjusted_size *= goal_factor
        logger.info(f"Applied goal adjustment factor: {goal_factor}")
    ```

* **Task**: Add goal sizing module initialization to `PositionSizingEngine`. — *Backend* — P0
  * File: `risk_manager/position_sizing.py`
  * Modify `__init__()` method (line 64+):
    ```python
    def __init__(
        self,
        database: RiskPostgresDatabase,
        price_prediction_client: Optional[PricePredictionClient] = None,
        enable_goal_sizing: bool = True  # NEW PARAMETER
    ):
        self.database = database
        self.price_prediction_client = price_prediction_client
        
        # NEW: Initialize goal-oriented sizing module
        if enable_goal_sizing:
            from goal_oriented_sizing import GoalOrientedSizingModule
            self.goal_sizing_module = GoalOrientedSizingModule(database)
    ```

* **Task**: Implement goal-based strategy selection. — *Quant* — P0
  * File: `strategy_service/goal_based_selector.py` (new module)
  * Class: `GoalBasedStrategySelector`
  * Integrate with `AdvancedStrategyOrchestrator` in `strategy_service/core/orchestrator.py`
  * Methods:
    ```python
    async def select_strategies_for_goal(
        self, 
        goal_type: str,  # monthly_return, monthly_income, portfolio_value
        current_progress: float,
        available_strategies: List[Dict]
    ) -> List[str]:
        """
        Select strategies based on current goal requirements
        
        - Monthly return goal: Prefer high Sharpe ratio strategies
        - Monthly income goal: Prefer high win-rate, frequent trading strategies  
        - Portfolio value goal: Prefer capital preservation, low drawdown strategies
        """
        pass
    ```

* **Task**: Add goal progress methods to `RiskPostgresDatabase`. — *Backend* — P0
  * File: `risk_manager/database.py`
  * Add methods to `RiskPostgresDatabase` class (after line 1000+):
    ```python
    @ensure_connection
    async def get_current_goal_progress(self) -> Dict[str, float]:
        """Get current progress toward all financial goals"""
        pass
    
    @ensure_connection
    async def update_goal_progress(self, goal_type: str, current_value: float):
        """Update goal progress and calculate status"""
        pass
    ```

### E.3. Adaptive Risk Management

* **Task**: Implement dynamic risk limits based on goal progress. — *Risk* — P0
  * File: `risk_manager/adaptive_risk_limits.py`
  * Adjust `MAX_PORTFOLIO_RISK_PERCENT` based on:
    - If behind on goals: Allow 12-15% portfolio risk (from default 10%)
    - If ahead on goals: Reduce to 5-8% portfolio risk
    - If near €1M: Reduce to 3-5% portfolio risk

* **Task**: Implement goal-based drawdown protection. — *Risk* — P0
  * Add to existing `RiskManagementDatabase` class
  * If monthly drawdown > 5%: Pause new positions, reduce existing by 50%
  * If approaching €1M: Implement 2% monthly drawdown limit

### E.4. Goal-Oriented Backtesting

* **Task**: Add goal evaluation to backtest metrics. — *Quant* — P1
  * File: `strategy_service/backtesting/goal_evaluator.py`
  * Calculate: Probability of achieving 10% monthly return
  * Calculate: Average monthly income generated
  * Calculate: Time to reach €1M portfolio
  * Add to backtest report

---

## F. Machine Learning Integration (ENHANCEMENT)

### F.1. Feature Store Implementation

**Integration Point**: Extend PostgreSQL database and create feature pipeline

* **Task**: Implement PostgreSQL-based feature store. — *ML/Backend* — P0
  * File: `ml_adaptation/feature_store.py` (new file)
  * Class: `PostgreSQLFeatureStore`
  * Use `shared/postgres_manager.py` PostgresManager for connections
  * Methods:
    ```python
    class PostgreSQLFeatureStore:
        def __init__(self, postgres_manager: PostgresManager):
            self.db = postgres_manager
        
        async def register_feature(self, feature_name: str, feature_type: str, 
                                   data_sources: List[str], computation_logic: str):
            """Register a new feature definition"""
            pass
        
        async def store_feature_values(self, feature_id: int, symbol: str, 
                                       values: List[Dict], timestamp: datetime):
            """Store computed feature values"""
            pass
        
        async def get_features(self, feature_ids: List[int], symbol: str, 
                              as_of_time: datetime) -> Dict[int, float]:
            """Get point-in-time feature values"""
            pass
    ```

* **Task**: Implement feature computation pipeline. — *ML* — P0
  * File: `ml_adaptation/feature_pipeline.py` (new file)
  * Class: `FeatureComputationPipeline`
  * Integrate with existing data services:
    - Market data: `shared/market_data_indicator_client.py`
    - On-chain metrics: `market_data_service/database.py`
    - Social sentiment: `market_data_service/database.py`
    - Macro data: `market_data_service/macro_economic_collector.py`
  * Methods:
    ```python
    async def compute_all_features(self, symbol: str, timestamp: datetime) -> Dict[str, float]:
        """
        Compute all features for a symbol at a specific time
        Returns: Dict of feature_name -> value
        """
        features = {}
        
        # Technical features from market data service
        market_client = MarketDataIndicatorClient()
        features.update(await market_client.get_indicators(symbol))
        
        # On-chain features
        onchain_data = await self.market_db.get_onchain_metrics(symbol)
        features['nvt_ratio'] = onchain_data.get('nvt')
        features['exchange_netflow'] = onchain_data.get('netflow')
        
        # Social features
        social_data = await self.market_db.get_social_sentiment(symbol)
        features['social_sentiment'] = social_data.get('sentiment_score')
        
        # Macro features
        macro_data = await self.market_db.get_macro_indicators()
        features['vix'] = macro_data.get('VIX')
        features['dxy'] = macro_data.get('DXY')
        
        return features
    ```

* **Task**: Integrate feature store with strategy service. — *ML/Backend* — P0
  * File: `strategy_service/main.py`
  * Add feature store initialization after database setup (around line 50+):
    ```python
    # Initialize feature store
    from ml_adaptation.feature_store import PostgreSQLFeatureStore
    from ml_adaptation.feature_pipeline import FeatureComputationPipeline
    
    feature_store = PostgreSQLFeatureStore(postgres_manager)
    feature_pipeline = FeatureComputationPipeline(database, feature_store)
    
    # Make available to orchestrator
    orchestrator.set_feature_pipeline(feature_pipeline)
    ```

* **Task**: Add feature retrieval to strategy evaluation. — *ML* — P0
  * File: `strategy_service/core/orchestrator.py`
  * Modify strategy evaluation method (around line 200+) to use features:
    ```python
    async def evaluate_strategy_with_features(self, strategy_id: str, symbol: str):
        # Get current features
        features = await self.feature_pipeline.compute_all_features(symbol, datetime.now())
        
        # Use features in strategy decision
        signal = await self.strategy.evaluate(features)
        return signal
    ```

* **Task**: Create feature schema in PostgreSQL. — *DBA* — P0
  ```sql
  CREATE TABLE feature_definitions (
    id SERIAL PRIMARY KEY,
    feature_name VARCHAR(100) UNIQUE NOT NULL,
    feature_type VARCHAR(50), -- technical, onchain, social, macro
    data_sources TEXT[], -- array of source tables
    computation_logic TEXT,
    version INT DEFAULT 1,
    created_at TIMESTAMP DEFAULT NOW()
  );

  CREATE TABLE feature_values (
    id SERIAL PRIMARY KEY,
    feature_id INT REFERENCES feature_definitions(id),
    symbol VARCHAR(20),
    feature_value DECIMAL(20,8),
    timestamp TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(feature_id, symbol, timestamp)
  );
  CREATE INDEX idx_feature_values ON feature_values(feature_id, symbol, timestamp DESC);
  ```

### F.2. AutoML Integration (Optuna)

**Integration Point**: Extend existing strategy optimization in `strategy_service/`

* **Task**: Integrate Optuna for hyperparameter optimization. — *ML* — P1
  * File: `ml_adaptation/automl_optimizer.py` (new file)
  * Use PostgreSQL as Optuna storage backend:
    ```python
    import optuna
    from optuna.storages import RDBStorage
    
    class AutoMLOptimizer:
        def __init__(self, database_url: str):
            # Use existing PostgreSQL database for Optuna
            storage = RDBStorage(url=database_url)
            self.study = optuna.create_study(
                study_name="strategy_optimization",
                storage=storage,
                load_if_exists=True,
                direction="maximize"  # Maximize Sharpe ratio
            )
        
        async def optimize_strategy_parameters(
            self, 
            strategy_class: str,
            n_trials: int = 100,
            n_jobs: int = 4
        ) -> Dict[str, Any]:
            """Optimize hyperparameters for a strategy"""
            
            def objective(trial):
                # Suggest hyperparameters
                params = {
                    'lookback_period': trial.suggest_int('lookback_period', 5, 50),
                    'threshold': trial.suggest_float('threshold', 0.01, 0.1),
                    'stop_loss': trial.suggest_float('stop_loss', 0.01, 0.05)
                }
                
                # Backtest with these parameters
                results = self.backtest(strategy_class, params)
                return results['sharpe_ratio']
            
            # Run optimization
            self.study.optimize(objective, n_trials=n_trials, n_jobs=n_jobs)
            return self.study.best_params
    ```

* **Task**: Integrate with existing strategy generator. — *ML* — P1
  * File: `strategy_service/core/strategy_generator.py`
  * Modify `AdvancedStrategyGenerator` class (if exists)
  * Add Optuna optimization after strategy generation:
    ```python
    from ml_adaptation.automl_optimizer import AutoMLOptimizer
    
    class AdvancedStrategyGenerator:
        def __init__(self, database):
            self.database = database
            self.automl = AutoMLOptimizer(database_url=settings.DATABASE_URL)
        
        async def generate_and_optimize_strategy(self):
            # Generate base strategy
            strategy = await self.generate_base_strategy()
            
            # Optimize parameters with Optuna
            best_params = await self.automl.optimize_strategy_parameters(
                strategy_class=strategy['type'],
                n_trials=50
            )
            
            # Update strategy with optimized parameters
            strategy['parameters'] = best_params
            return strategy
    ```

* **Task**: Add Optuna optimization to backtesting pipeline. — *ML* — P1
  * File: `strategy_service/backtesting/` (extend existing backtest framework)
  * Add optimization mode to backtest executor
  * Store optimization history in database for analysis

* **Task**: Implement automated model selection. — *ML* — P1
  * File: `ml_adaptation/model_selector.py` (new file)
  * Test multiple model types: XGBoost, LightGBM, Neural Networks
  * Use Optuna to select best model architecture
  * Integrate with `strategy_service/core/orchestrator.py`

### F.3. Model Explainability (SHAP/LIME)

* **Task**: Integrate SHAP for model explainability. — *ML* — P1
  * File: `ml_adaptation/explainability.py`
  * Generate SHAP values for each trade decision
  * Store top 5 feature importances per trade
  * Add to trade execution logs

* **Task**: Create explainability visualization API. — *ML/Backend* — P2
  * Endpoint: `GET /api/v1/ml/explain/{trade_id}`
  * Return: Feature importances, SHAP values, decision tree visualization
  * Integrate with Monitor UI

### F.4. Online Learning & Concept Drift

* **Task**: Implement concept drift detection. — *ML* — P1
  * File: `ml_adaptation/drift_detector.py`
  * Monitor: Model prediction accuracy, feature distribution shifts
  * Detect drift using Page-Hinkley test or ADWIN
  * Alert when drift detected (trigger retraining)

* **Task**: Implement online learning pipeline. — *ML* — P1
  * File: `ml_adaptation/online_learner.py`
  * Update models incrementally with new data (daily)
  * Use techniques: Incremental learning, transfer learning
  * Validate before deploying updated models

---

## G. Enhanced Monitoring UI (ENHANCEMENT)

### G.1. Data Source Management View (NEW)

**Integration Point**: Add new page to existing `monitoring_ui` Next.js application

* **Task**: Build Data Sources page in Monitor UI. — *Frontend* — P0
  * Location: `monitoring_ui/src/app/data-sources/page.tsx` (new file)
  * Use existing Next.js app router structure (follow pattern from existing pages)
  * API Integration: Connect to `market_data_service` REST API endpoints
  * Display components:
    ```typescript
    // monitoring_ui/src/app/data-sources/page.tsx
    import { useEffect, useState } from 'react';
    
    interface DataSource {
      id: string;
      name: string;
      type: 'onchain' | 'social' | 'macro' | 'institutional';
      status: 'active' | 'inactive' | 'error';
      health: 'healthy' | 'degraded' | 'failed';
      last_update: string;
      error_rate: number;
      monthly_cost: number;
    }
    
    export default function DataSourcesPage() {
      const [sources, setSources] = useState<DataSource[]>([]);
      
      useEffect(() => {
        // Fetch from market_data_service API
        fetch('http://localhost:8000/api/v1/data-sources')
          .then(res => res.json())
          .then(data => setSources(data));
      }, []);
      
      // Render data source cards with status, health indicators, actions
      return (
        <div className="data-sources-grid">
          {sources.map(source => (
            <DataSourceCard key={source.id} source={source} />
          ))}
        </div>
      );
    }
    ```

* **Task**: Implement data source configuration modal. — *Frontend* — P0
  * Component: `monitoring_ui/src/components/DataSourceConfigModal.tsx`
  * Use existing UI component library (Shadcn UI or similar)
  * Form fields: Rate limit, priority, API key configuration
  * Save via PUT request to `/api/v1/data-sources/{id}/config`

* **Task**: Add data source navigation to existing sidebar. — *Frontend* — P0
  * File: `monitoring_ui/src/components/Sidebar.tsx` (or similar navigation component)
  * Add menu item: "Data Sources" with icon
  * Follow existing navigation pattern in monitoring UI

* **Task**: Add data freshness indicators. — *Frontend* — P0
  * Component: `monitoring_ui/src/components/FreshnessIndicator.tsx`
  * Visual indicator colors:
    - Green: < 5 min old
    - Yellow: 5-15 min old
    - Red: > 15 min old
  * Use in data source cards and main dashboard

### G.2. Alpha Attribution Dashboard (NEW)

* **Task**: Build Alpha Attribution page. — *Frontend/Analytics* — P1
  * Location: `monitoring_ui/src/app/alpha-attribution/page.tsx`
  * Show: Performance contribution by data source
  * Metrics: Trades influenced, average P&L impact, Sharpe improvement
  * Visualizations: Bar charts, time series, correlation heatmap

* **Task**: Implement attribution calculation service. — *Backend/Analytics* — P1
  * File: `strategy_service/attribution_calculator.py`
  * Calculate: Which data sources contributed to winning trades
  * Method: Feature importance analysis, counterfactual analysis
  * Store in `attribution_metrics` table

### G.3. Goal Progress Dashboard (NEW)

* **Task**: Build Goal Progress page. — *Frontend* — P0
  * Location: `monitoring_ui/src/app/goals/page.tsx`
  * Display: Progress toward all financial goals (10% monthly, €4k income, €1M portfolio)
  * Visualizations: Progress bars, line charts, projections
  * Show: Current status, days remaining, required daily return

* **Task**: Add goal alerts and notifications. — *Frontend* — P0
  * Alert when goal is at risk (< 80% of target at 50% of time period)
  * Alert when goal achieved
  * Integrate with Slack/email notifications

### G.4. Enhanced User Management with RBAC (ENHANCEMENT)

* **Task**: Implement RBAC permission system. — *Backend* — P0
  * File: `api_gateway/rbac_middleware.py`
  * Roles: Admin (full access), Operator (manage strategies), Quant (view only), Viewer (dashboard only)
  * Permissions stored in `user_roles` and `role_permissions` tables
  * Enforce at API Gateway level

* **Task**: Add audit logging for user actions. — *Backend* — P0
  * File: `api_gateway/audit_logger.py`
  * Log: Who changed what, when, old value, new value
  * Actions: Strategy enable/disable, data source config, goal changes
  * Store in `audit_logs` table

* **Task**: Build User Management page in Monitor UI. — *Frontend* — P0
  * Location: `monitoring_ui/src/app/users/page.tsx`
  * CRUD operations: Create, read, update, delete users
  * Role assignment dropdown
  * Display recent activity per user

### G.5. Alerting & Notifications (ENHANCEMENT)

* **Task**: Implement multi-channel alert system. — *Backend* — P0
  * File: `alert_system/notification_service.py` (extend existing)
  * Channels: Slack, Email, Webhook, Mobile push (optional)
  * Alert types: Goal at risk, strategy failure, data source down, whale detected

* **Task**: Add alert configuration UI. — *Frontend* — P0
  * Location: `monitoring_ui/src/app/alerts/page.tsx`
  * Configure: Thresholds, channels, escalation rules
  * Test alert delivery
  * Alert history with acknowledge/snooze actions

---

## H. Testing & Validation

### H.1. Unit Tests

* **Task**: Unit tests for all new collectors. — *QA* — P0
  * Test files: `test_onchain_collector.py`, `test_social_collector.py`, etc.
  * Mock API responses, test rate limiting, error handling
  * Coverage target: > 80%

* **Task**: Unit tests for goal-oriented system. — *QA* — P0
  * Test files: `test_goal_tracking.py`, `test_goal_oriented_sizing.py`
  * Test edge cases: goal achieved early, severe underperformance
  * Test risk adjustments based on goal progress

### H.2. Integration Tests

* **Task**: End-to-end tests for data pipeline. — *QA* — P0
  * Test: Ingest (collector) → Process (RabbitMQ) → Store (PostgreSQL) → Query (API)
  * Verify data integrity and latency
  * Test with real API responses (sandboxed)

* **Task**: Integration tests for goal-oriented trading. — *QA* — P0
  * Test: Goal setup → Position sizing → Trade execution → Goal progress update
  * Verify risk adjustments trigger correctly
  * Test strategy selection based on goals

### H.3. Performance Tests

* **Task**: Load testing for API endpoints. — *QA* — P1
  * Use k6 or Locust for load testing
  * Test: Data source management API, WebSocket streams
  * Target: 1000 req/sec, < 200ms p95 latency

* **Task**: Database performance testing. — *DBA* — P1
  * Test query performance on large datasets (millions of rows)
  * Verify index effectiveness
  * Test partition pruning

---

## I. Deployment & Operations

### I.1. Docker Compose Enhancements

* **Task**: Add Redis service to docker-compose.yml. — *DevOps* — P0
  ```yaml
  redis:
    image: redis:7-alpine
    container_name: mastertrade_redis
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    command: redis-server --appendonly yes --maxmemory 2gb
  ```

* **Task**: Add PgBouncer service for PostgreSQL pooling. — *DevOps* — P0
  ```yaml
  pgbouncer:
    image: edoburu/pgbouncer
    container_name: mastertrade_pgbouncer
    environment:
      - DATABASES_HOST=host.docker.internal
      - DATABASES_PORT=5432
      - DATABASES_USER=${POSTGRES_USER}
      - DATABASES_PASSWORD=${POSTGRES_PASSWORD}
      - POOL_MODE=transaction
      - MAX_CLIENT_CONN=100
      - DEFAULT_POOL_SIZE=20
    ports:
      - "6432:5432"
  ```

### I.2. Monitoring & Observability

* **Task**: Add Prometheus metrics to all services. — *DevOps* — P0
  * Metrics: Request count, latency, error rate, collector health
  * Add `/metrics` endpoint to all FastAPI services
  * Use `prometheus-fastapi-instrumentator` library

* **Task**: Create Grafana dashboards. — *DevOps* — P0
  * Dashboard 1: System health (all services, database, RabbitMQ)
  * Dashboard 2: Data sources (health, latency, error rate)
  * Dashboard 3: Trading performance (P&L, positions, goal progress)
  * Dashboard 4: ML models (prediction accuracy, drift detection)

### I.3. Backup & Disaster Recovery

* **Task**: Implement automated PostgreSQL backups. — *DBA/DevOps* — P0
  * Daily full backup, hourly incremental backup
  * Store backups in local storage + cloud backup (optional)
  * Test restore procedure monthly

* **Task**: Implement Redis persistence configuration. — *DevOps* — P0
  * Enable AOF (Append-Only File) and RDB snapshots
  * Backup Redis data daily
  * Test recovery procedure

---

## J. Documentation

### J.1. API Documentation

* **Task**: Generate OpenAPI/Swagger docs for all new endpoints. — *Backend* — P0
  * FastAPI auto-generates Swagger UI
  * Add detailed descriptions, examples, error codes
  * Document authentication requirements

### J.2. System Documentation

* **Task**: Create system architecture document. — *Architect* — P1
  * Document: Service interactions, data flow, database schema
  * Include: Architecture diagrams, sequence diagrams
  * File: `.github/SYSTEM_ARCHITECTURE.md`

* **Task**: Create data source integration guide. — *Data Team* — P1
  * Document: How to add new data sources
  * Include: API integration steps, schema design, testing
  * File: `.github/DATA_SOURCE_INTEGRATION_GUIDE.md`

### J.3. Operations Runbook

* **Task**: Create operations runbook. — *Ops* — P0
  * Document: Common issues, troubleshooting steps, escalation procedures
  * Include: Service restart procedures, backup/restore, failover
  * File: `.github/OPERATIONS_RUNBOOK.md`

---

## K. Success Metrics (KPIs)

* **Data freshness**: Median time from source to database < 60 seconds — P0
* **API latency**: p95 latency < 200ms for all endpoints — P0
* **System uptime**: > 99.9% uptime for production — P0
* **Goal achievement rate**: > 70% of monthly goals achieved — P0
* **Model accuracy**: Strategy win rate > 55% — P1
* **Attribution value**: Data sources show measurable P&L impact — P1

---

# Implementation Checklist (Quick Start)

## Phase 1 (Weeks 1-2): Data Sources
- [x] Deploy Redis instance ✅ **COMPLETED** - Redis service added to docker-compose.yml, RedisCacheManager implemented, tests passing
- [x] Implement on-chain collectors (Moralis, Glassnode) ✅ **COMPLETED** - Base OnChainCollector, MoralisCollector, GlassnodeCollector implemented with rate limiting, circuit breaker, database integration, scheduler, and tests passing
- [x] Integrate on-chain collectors with MarketDataService ✅ **COMPLETED** - Full integration with scheduled tasks, HTTP API endpoints, RabbitMQ publishing, comprehensive testing (5/5 tests passing). See ONCHAIN_INTEGRATION_COMPLETE.md for details.
- [x] Implement social collectors (Twitter, Reddit, LunarCrush) ✅ **COMPLETED** - Base SocialCollector with VADER/FinBERT sentiment, TwitterCollector, RedditCollector, and LunarCrushCollector implemented with full NLP pipeline, database methods, and configuration
- [ ] Integrate social collectors with MarketDataService
- [ ] Create PostgreSQL schemas for new data
- [ ] Implement whale alert detection
- [ ] Add data source management API endpoints
- [ ] Build Data Sources page in Monitor UI

## Phase 2 (Weeks 3-4): Goal System
- [ ] Create financial goals tables
- [ ] Implement goal tracking service
- [ ] Implement goal-oriented position sizing
- [ ] Integrate with existing PositionSizingEngine
- [ ] Implement adaptive risk management
- [ ] Build Goal Progress dashboard
- [ ] Add goal alerts and notifications

## Phase 3 (Weeks 5-6): ML & Intelligence
- [ ] Implement PostgreSQL-based feature store
- [ ] Integrate Optuna for AutoML
- [ ] Add SHAP explainability
- [ ] Implement concept drift detection
- [ ] Implement online learning pipeline
- [ ] Build Alpha Attribution dashboard

## Phase 4 (Weeks 7-8): Operations & Polish
- [ ] Implement RBAC and audit logging
- [ ] Build User Management page
- [ ] Add PgBouncer connection pooling
- [ ] Create Prometheus + Grafana dashboards
- [ ] Implement automated backups
- [ ] Write comprehensive tests (unit + integration)
- [ ] Create documentation and runbooks

---

## Cost Estimates

### Monthly Data Source Costs:
- **Free tier**: Reddit API, some macro data (~$0/month)
- **Low tier**: Twitter Basic, LunarCrush, Nansen Lite (~$450/month)
- **Medium tier**: Add Moralis Pro, Glassnode Advanced (~$1,300/month)
- **High tier**: Add Kaiko, CoinMetrics, full coverage (~$2,800/month)

### Infrastructure Costs:
- **Local deployment**: $0/month (using existing hardware)
- **Redis**: $0/month (Docker container)
- **PgBouncer**: $0/month (Docker container)
- **Monitoring**: $0/month (self-hosted Prometheus + Grafana)

**Total Initial Investment**: ~$450-$1,300/month for data sources (scale as needed)

---

## Next Steps

1. **Prioritize Phase 1 tasks**: Focus on high-impact data sources first (on-chain + social)
2. **Start with free/cheap sources**: Reddit, Twitter Basic, test infrastructure
3. **Validate alpha contribution**: Measure if new data sources improve strategy performance
4. **Scale incrementally**: Add expensive data sources only after proving value
5. **Iterate based on results**: Focus on sources with highest attribution value

---

*End of Focused TODO List*

---

## Executive Summary

Goal: Build an institutional-grade, goal-oriented crypto trading platform with multi-source intelligence, automated strategy pipeline, robust ML integration, execution optimization, and a Monitor UI that includes full user CRUD and alert management.

Success metrics: Data freshness <60s, System uptime >99.9%, Alpha attribution measurable by source, Paper->Live promotion success rate, Realized vs expected slippage.

---

## Priority Matrix (Top-level)

* **P0 (Critical)**: Automated strategy pipeline, paper trading validation, data ingestion for on-chain/social/institutional, Monitor UI user CRUD, core storage and streaming.
* **P1 (High)**: ML feature engineering & meta-models, execution engine & smart order routing, advanced risk controls, real-time model governance.
* **P2 (Medium)**: Market microstructure analytics, alternative data integration, explainability (SHAP), portfolio optimization.
* **P3 (Low)**: Regulatory intelligence, satellite/alternative economics, experimental HFT components.

---

## Phased Roadmap (Summary)

* **Phase 1 — Foundation (Weeks 1-2)**: Core collectors (on-chain, social), storage schema, streaming pipeline, basic APIs, automated strategy generation, Monitor UI CRUD.
* **Phase 2 — Validation & Safety (Weeks 3-4)**: Paper trading manager, backtest pipeline automation, advanced position sizing (Kelly), regime detection basics, WebSocket streams.
* **Phase 3 — Optimization & ML (Weeks 5-6)**: Meta-modeling, AutoML retraining, execution router, microstructure analytics, explainability.
* **Phase 4 — Production & Scale (Weeks 7-8)**: Hardening, load testing, colocation options, monitoring, redundancy, user training.

---

# Detailed TODOs

> Each section lists tasks grouped as: **Task** — *Owner* — Priority — Notes / Acceptance Criteria

---

## A. Data Sources & Collectors

### A.1. On-Chain Analytics Collector

* **Task**: Integrate Moralis, Infura/Alchemy, Etherscan, CoinMetrics, Chainalysis (optional). — *Data Team* — P0

  * Configure API keys, rate limits, retry policies.
  * Implement collectors: `onchain_collector.py` with modular provider adapters.
  * Emit standardized events: `whale_transaction`, `exchange_flow`, `bridge_activity`.
  * Acceptance: Normalized events stored in `whale_transactions` table with required fields.

* **Task**: Whale wallet clustering & labeling (batch + streaming). — *Data Scientist* — P1

  * Implement heuristics for address clustering and link to labels (exchange, known entity).
  * Produce `wallet_network_store` entries.

* **Task**: DeFi protocol metrics ingestion (Dune / TheGraph). — *Data Team* — P0

  * Poll TVL, fees, liquidity across major protocols.

### A.2. Social Media Intelligence

* **Task**: Integrate Twitter/X, Reddit, YouTube, Discord, Telegram, LunarCrush. — *Data Team* — P0

  * Streaming ingestion where available, fallback batch polling.
  * Bot filtering pipeline and influencer whitelist.
  * Output: `social_sentiment` aggregates per timeframe.

* **Task**: Emoji & non-text reaction parsing. — *Data Engineer* — P1

### A.3. Institutional Flow & Exchange Data

* **Task**: Integrate exchange REST/WebSocket feeds (Coinbase, Binance, Deribit, CME). — *Execution Team* — P0

  * Collect order book snapshots, trades, funding rates, open interest.
  * Build `large_trades` and `etf_flows` ingestion paths.

* **Task**: Options flow and unusual activity detection. — *Quant* — P1

### A.4. Macro & Alternative Data

* **Task**: FRED, Trading Economics, Yahoo Finance for cross-asset signals. — *Data Team* — P1
* **Task**: Optional alt-data (Google Trends, GitHub activity, satellite proxies). — *Product* — P2

---

## B. Data Ingestion & Stream Processing

### B.1. Collector Framework

* **Task**: Implement `base_collector.py` with common interface (start/stop, backfill, rate-limit). — *Backend* — P0
* **Task**: Adaptive rate limiter and circuit breaker (`adaptive_limiter.py`, `circuit_breaker.py`). — *Backend* — P0

### B.2. Stream Processing Engine

* **Task**: Implement `stream_processor.py` using Kafka/Redpanda. — *Backend* — P0

  * Event handlers: `whale_alert_handler.py`, `sentiment_spike_handler.py`, `flow_anomaly_handler.py`.
  * Aggregators: time-window aggregation for multiple intervals (1m,5m,15m,1h,4h,1d).

* **Task**: Pattern detectors & correlation handler. — *Quant* — P1

### B.3. Alerting & Notification Bus

* **Task**: `notification_service.py` supporting Slack, email, webhook, mobile push. — *Ops* — P0
* **Task**: Alert throttling & escalation rules. — *Ops* — P0

---

## C. Storage Layer

### C.1. Time-Series DB

* **Task**: Deploy TimescaleDB / Influx or optimized PostgreSQL time-series schema. — *Infra* — P0
* **Task**: Implement `price_data_store.py`, `sentiment_store.py`, `flow_data_store.py`. — *Backend* — P0

### C.2. Document DB & Graph DB

* **Task**: MongoDB for social posts and news (`news_article_store.py`, `social_post_store.py`). — *Backend* — P1
* **Task**: Neo4j / Amazon Neptune for `wallet_network_store` and influencer graphs. — *Data Team* — P1

### C.3. Cache Layer

* **Task**: Redis for query cache, session cache, and signal buffer. — *Infra* — P0

### C.4. Retention & Compression Policy

* **Task**: Implement retention rules, partitioning, and compression for older time-series data. — *DBA* — P1

---

## D. APIs & WebSocket Interfaces

### D.1. REST API

* **Task**: Implement endpoints from spec (datasource management, data access, analytics, alerts). — *Backend* — P0

  * Authentication: API keys/OAuth2 + RBAC.
  * Throttling & quota monitoring.

### D.2. WebSocket Streams

* **Task**: Real-time WS endpoints for whales, sentiment spikes, institutional flows, alerts. — *Backend* — P0
* **Task**: Backpressure handling and authentication for WS channels. — *Backend* — P0

---

## E. Automated Strategy Pipeline

### E.1. Strategy Generation & Backtesting

* **Task**: Automated strategy generator (produce N strategies each cycle). — *Quant* — P0

  * Integrate genetic algorithms + transformer feature set.
  * Daily or 3-hour windows for automated generation (configurable).

* **Task**: Backtesting engine — high-fidelity, supports slippage/fees, simulation of exchange latencies. — *Quant/Backend* — P0

  * Integrate vectorized backtest for speed and per-strategy metrics.

### E.2. Paper Trading Manager

* **Task**: Paper trading environment manager with 1–2 week validation windows and automatic promotion rules. — *Trading Ops* — P0

  * Performance monitoring vs live; failure detection and auto-pausing.

### E.3. Continuous Learning Loop

* **Task**: Log backtest & live outcomes to enable hyperparameter optimization and meta-learning. — *ML* — P0

---

## F. Machine Learning Integration

### F.1. Feature Engineering & Fusion

* **Task**: Build feature pipelines combining technical, on-chain, social, macro features. — *ML* — P0

  * Implement multi-timeframe aggregates and lagged features.

* **Task**: Feature store implementation (Feast or custom). — *ML/Infra* — P1

### F.2. Model Types & Training

* **Task**: Implement baseline models: XGBoost/LightGBM for tabular; CNN for chart pattern recognition; Transformers for sequence modeling. — *ML* — P0

* **Task**: Meta-model that predicts *which strategy families* will perform next 24–72h. — *ML* — P1

* **Task**: Online learning / concept drift detection and automated retraining triggers. — *ML* — P1

### F.3. AutoML & Hyperparameter Tuning

* **Task**: Integrate Optuna / Ray Tune. — *ML* — P1
* **Task**: Auto-deploy promising models to shadow/live tests with canary routing. — *ML/Infra* — P2

### F.4. Explainability & Governance

* **Task**: SHAP/LIME integration for feature importance per trade. — *ML* — P1
* **Task**: Model registry with metadata, versioning, and performance metrics. — *ML/DevOps* — P1

### F.5. Evaluation & Validation

* **Task**: Metrics: precision/recall for signals, expected vs realized PnL, Sharpe, max drawdown per model. — *Analytics* — P0

---

## G. Execution Engine & Smart Order Routing

### G.1. Execution Optimization

* **Task**: Implement Almgren–Chriss-based scheduler. — *Execution* — P1
* **Task**: Liquidity-aware execution (pause/fragment based on market depth). — *Execution* — P1

### G.2. Smart Router

* **Task**: Real-time routing based on latency/slippage profiles and fees. — *Execution/Infra* — P1
* **Task**: Execution replay system for post-trade analysis. — *Execution* — P1

### G.3. Market Making Module (Optional) — P2

* **Task**: Micro market-making engine with inventory management and rebate harvesting.

---

## H. Risk Management & Position Sizing

### H.1. Hierarchical Risk Controls

* **Task**: Implement strategy-level VaR, portfolio CVaR, system-level drawdown throttle. — *Risk* — P0
* **Task**: Emergency kill-switch / graceful shutdown behavior. — *Risk/DevOps* — P0

### H.2. Adaptive Leverage & Sizing

* **Task**: Kelly criterion module + volatility-adjusted sizing + correlation penalties. — *Quant* — P0

### H.3. Hedging & Auto-hedge Rules

* **Task**: Auto-hedge large exposures via futures/options when risk triggers fire. — *Risk/Execution* — P1

---

## I. Monitoring UI (`monitor_ui`) & User CRUD

### I.1. Monitor UI — Core Views

* **Task**: Dashboard landing with system health, active alerts, data freshness. — *Frontend* — P0
* **Task**: Data Source Management view (toggle, rate-limit, priority). — *Frontend* — P0
* **Task**: Strategy Management view (status, performance, promote/pause). — *Frontend* — P0
* **Task**: Alerts & Notifications configuration UI. — *Frontend* — P0
* **Task**: Alpha Attribution / Analytics panel (by data source). — *Frontend* — P1

### I.2. Monitor UI — User CRUD

> Full user management required for RBAC and operational user flows.

* **Task**: Implement User model: `id, email, name, role, last_seen, status, preferences`. — *Backend* — P0
* **Task**: Register API endpoints for users (REST):

  * `POST /api/v1/users` — create user. — *Backend* — P0
  * `GET /api/v1/users` — list users with pagination and filters. — *Backend* — P0
  * `GET /api/v1/users/{id}` — read user. — *Backend* — P0
  * `PUT /api/v1/users/{id}` — update user (role, status, prefs). — *Backend* — P0
  * `DELETE /api/v1/users/{id}` — soft-delete user. — *Backend* — P0
  * `POST /api/v1/users/{id}/reset-password` — password reset flow. — *Backend* — P0
* **Task**: Frontend CRUD pages with inline validation, role assignment dropdown, activity logs. — *Frontend* — P0
* **Task**: RBAC enforcement middleware across API and UI (roles: admin, operator, quant, viewer). — *Backend* — P0
* **Task**: Audit logs for user actions (who changed config/promoted strategy). — *Security* — P0

### I.3. Monitor UI — Alerts & Escalation

* **Task**: UI for alert rule creation (thresholds, channels, escalation). — *Frontend* — P0
* **Task**: Active alert feed with quick actions (acknowledge, snooze, escalate). — *Frontend* — P0

### I.4. Monitor UI — Notifications & Integrations

* **Task**: Integrate Slack, Email, Webhooks, Mobile Push. — *Backend/Frontend* — P0

---

## J. Configuration Management & Operations

### J.1. Configuration UI & Backend

* **Task**: Central config service with validation (datasource settings, rate limits, processing parameters). — *Backend* — P0
* **Task**: Hot-reload configuration support and audit trail. — *Backend* — P1

### J.2. Secrets & Keys Management

* **Task**: Integrate Azure Key Vault or HashiCorp Vault for API keys and DB creds. — *Infra* — P0

### J.3. Monitoring & Observability

* **Task**: Prometheus + Grafana for infra metrics, ELK for logs, distributed tracing (OpenTelemetry). — *DevOps* — P0
* **Task**: Synthetic monitors for data collectors and WS endpoints. — *QA* — P1

---

## K. Security & Compliance

* **Task**: API auth (OAuth2 client credentials), API key rotation, RBAC. — *Security* — P0
* **Task**: Data anonymization & PII handling. — *Security/Legal* — P1
* **Task**: Regulatory logging and data lineage reporting. — *Legal/Compliance* — P1

---

## L. Testing & Validation

* **Task**: Unit tests for collectors, processors, and storage adapters. — *QA* — P0
* **Task**: Integration tests for pipeline end-to-end (ingest → process → store → API). — *QA* — P0
* **Task**: Backtest validation suite with known benchmarks. — *Quant/QA* — P0
* **Task**: Chaos/failover tests (simulate API downtime, high latency). — *DevOps* — P1

---

## M. Deployment & Scalability

* **Task**: Containerize services and deploy via Kubernetes with autoscaling. — *Infra* — P0
* **Task**: Use managed streaming (Kafka/Redpanda) with multi-AZ for durability. — *Infra* — P0
* **Task**: Load testing and capacity planning for peak data ingestion. — *Infra/QA* — P1

---

## N. Performance, Cost & Resource Planning

* **Task**: Define minimum and recommended infra profiles (CPU, RAM, storage). — *Infra* — P0
* **Task**: Cost model for paid data sources and scaling thresholds. — *Finance/Product* — P1

---

## O. Documentation & Training

* **Task**: API docs (Swagger / OpenAPI), runbooks for on-call, and user guides for Monitor UI. — *Docs* — P0
* **Task**: Training sessions for traders and operators. — *Ops/Product* — P1

---

## P. Metrics & Success Criteria (KPIs)

* Data freshness: median time from source to DB < 60s. — Target P0
* Model decay detection: retrain trigger within 24h of drift detection. — Target P1
* Paper->Live promotion success: >70% after 2-week validation. — Target P1
* System uptime: >99.9% (production). — Target P0
* Execution slippage: VWAP deviation < configurable threshold. — Target P1

---

# Implementation Checklist (Quick-action)

* [ ] Provision infra (k8s cluster, DBs, Kafka) — Infra
* [ ] Implement base collector & adaptive rate limiter — Backend
* [ ] Integrate On-chain & Social sources (Moralis, Twitter) — Data
* [ ] Implement time-series DB schema & caching — DBA
* [ ] Build stream processor and event handlers — Backend
* [ ] Implement REST + WebSocket APIs — Backend
* [ ] Build Monitor UI initial pages and User CRUD — Frontend
* [ ] Implement automated strategy generator + backtest runner — Quant
* [ ] Implement paper trading manager & promotion rules — Trading Ops
* [ ] Implement ML feature pipelines + baseline models — ML
* [ ] Implement execution engine (smart router + Almgren–Chriss) — Execution
* [ ] Setup monitoring, logging, and alerting — DevOps

---

## Notes & Next Steps

1. Start with Phase 1 tasks and complete a minimal end-to-end flow: **ingest → process → store → signal → paper trade → monitor**. Validate data quality before scaling.
2. Track costs for paid data feeds; validate alpha contribution before upgrading to expensive sources.
3. Schedule a 1-week sprint plan with team owners for Phase 1 deliverables.

---

*End of TODO list.*
