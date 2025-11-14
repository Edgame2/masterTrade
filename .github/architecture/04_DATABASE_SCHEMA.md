# Database Schema Documentation

**Last Updated**: November 13, 2025  
**Database**: PostgreSQL 15  
**Total Tables**: 50+

---

## Table of Contents

1. [Market Data Tables](#market-data-tables)
2. [Strategy Management Tables](#strategy-management-tables)
3. [Order & Execution Tables](#order--execution-tables)
4. [Risk Management Tables](#risk-management-tables)
5. [Alert System Tables](#alert-system-tables)
6. [User Management Tables](#user-management-tables)
7. [Relationships & Foreign Keys](#relationships--foreign-keys)
8. [Indexes & Performance](#indexes--performance)
9. [Partitioning Strategy](#partitioning-strategy)

---

## Market Data Tables

### `market_data`
Primary table for OHLCV candlestick data.

```sql
CREATE TABLE market_data (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    interval VARCHAR(10) NOT NULL,  -- '1m', '5m', '15m', '1h', '4h', '1d'
    open DECIMAL(20, 8) NOT NULL,
    high DECIMAL(20, 8) NOT NULL,
    low DECIMAL(20, 8) NOT NULL,
    close DECIMAL(20, 8) NOT NULL,
    volume DECIMAL(20, 8) NOT NULL,
    quote_volume DECIMAL(20, 8),
    trades_count INTEGER,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(symbol, timestamp, interval)
);

CREATE INDEX idx_market_data_symbol_timestamp ON market_data(symbol, timestamp DESC);
CREATE INDEX idx_market_data_interval ON market_data(interval, timestamp DESC);
```

**Retention**: 90 days  
**Rows**: ~10M (100 symbols × 1440 1m candles/day × 90 days)  
**Size**: ~5GB

---

### `technical_indicators`
Computed technical indicators (SMA, EMA, RSI, etc.).

```sql
CREATE TABLE technical_indicators (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    interval VARCHAR(10) NOT NULL,
    indicator_name VARCHAR(50) NOT NULL,  -- 'SMA_20', 'RSI_14', etc.
    value DECIMAL(20, 8),
    metadata JSONB,  -- Additional indicator-specific data
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(symbol, timestamp, interval, indicator_name)
);

CREATE INDEX idx_indicators_lookup ON technical_indicators(symbol, interval, indicator_name, timestamp DESC);
```

**Retention**: 90 days  
**Rows**: ~50M (100 symbols × 20 indicators × 1440/day × 90 days)  
**Size**: ~15GB

---

### `whale_transactions`
Large on-chain transactions (>$1M USD).

```sql
CREATE TABLE whale_transactions (
    id SERIAL PRIMARY KEY,
    transaction_hash VARCHAR(100) UNIQUE NOT NULL,
    blockchain VARCHAR(20) NOT NULL,  -- 'ethereum', 'bitcoin', etc.
    token_symbol VARCHAR(20) NOT NULL,
    from_address VARCHAR(100) NOT NULL,
    to_address VARCHAR(100) NOT NULL,
    from_label VARCHAR(100),  -- 'binance_exchange', 'unknown_wallet'
    to_label VARCHAR(100),
    amount_token DECIMAL(30, 8) NOT NULL,
    amount_usd DECIMAL(20, 2) NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    alert_level VARCHAR(10),  -- 'low', 'medium', 'high', 'critical'
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_whale_timestamp ON whale_transactions(timestamp DESC);
CREATE INDEX idx_whale_token ON whale_transactions(token_symbol, timestamp DESC);
CREATE INDEX idx_whale_amount ON whale_transactions(amount_usd DESC);
```

**Retention**: 365 days  
**Rows**: ~100K (sparse data)  
**Size**: ~50MB

---

### `onchain_metrics`
On-chain metrics (active addresses, transaction count, hash rate, etc.).

```sql
CREATE TABLE onchain_metrics (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    metric_name VARCHAR(50) NOT NULL,  -- 'active_addresses', 'hash_rate', etc.
    value DECIMAL(30, 8) NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    source VARCHAR(50),  -- 'glassnode', 'moralis'
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(symbol, metric_name, timestamp)
);

CREATE INDEX idx_onchain_lookup ON onchain_metrics(symbol, metric_name, timestamp DESC);
```

**Retention**: 365 days  
**Rows**: ~10M (100 symbols × 20 metrics × 288/day × 365 days)  
**Size**: ~2GB

---

### `social_sentiment`
Social media sentiment scores.

```sql
CREATE TABLE social_sentiment (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    platform VARCHAR(20) NOT NULL,  -- 'twitter', 'reddit', 'telegram'
    post_id VARCHAR(100) UNIQUE NOT NULL,
    post_text TEXT,
    sentiment_score DECIMAL(5, 4),  -- -1.0 to 1.0
    sentiment_label VARCHAR(20),  -- 'positive', 'neutral', 'negative'
    author VARCHAR(100),
    timestamp TIMESTAMP NOT NULL,
    engagement_score INTEGER,  -- likes + retweets + comments
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_sentiment_symbol_timestamp ON social_sentiment(symbol, timestamp DESC);
CREATE INDEX idx_sentiment_score ON social_sentiment(sentiment_score, timestamp DESC);
```

**Retention**: 90 days  
**Rows**: ~5M (100 symbols × 500 posts/day × 90 days)  
**Size**: ~5GB (large TEXT fields)

---

### `stock_indices`
Stock market indices (S&P 500, NASDAQ, VIX, etc.).

```sql
CREATE TABLE stock_indices (
    id SERIAL PRIMARY KEY,
    index_name VARCHAR(20) NOT NULL,  -- 'SPX', 'NASDAQ', 'VIX'
    timestamp TIMESTAMP NOT NULL,
    open DECIMAL(12, 2),
    high DECIMAL(12, 2),
    low DECIMAL(12, 2),
    close DECIMAL(12, 2),
    volume BIGINT,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(index_name, timestamp)
);

CREATE INDEX idx_stock_index_lookup ON stock_indices(index_name, timestamp DESC);
```

**Retention**: 365 days  
**Rows**: ~500K (5 indices × 288/day × 365 days)  
**Size**: ~50MB

---

## Strategy Management Tables

### `strategies`
Generated trading strategies.

```sql
CREATE TABLE strategies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    strategy_type VARCHAR(50),  -- 'momentum', 'mean_reversion', 'arbitrage'
    symbol VARCHAR(20) NOT NULL,
    interval VARCHAR(10) NOT NULL,
    parameters JSONB NOT NULL,  -- Strategy-specific parameters
    entry_conditions JSONB,
    exit_conditions JSONB,
    risk_params JSONB,  -- stop_loss, take_profit, position_size
    status VARCHAR(20) DEFAULT 'draft',  -- 'draft', 'backtested', 'paper', 'active', 'paused', 'archived'
    version INTEGER DEFAULT 1,
    parent_strategy_id UUID,  -- For genetic algorithm evolution
    generation INTEGER,  -- Generation number in GA
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    activated_at TIMESTAMP,
    archived_at TIMESTAMP,
    FOREIGN KEY (parent_strategy_id) REFERENCES strategies(id)
);

CREATE INDEX idx_strategies_status ON strategies(status, created_at DESC);
CREATE INDEX idx_strategies_symbol ON strategies(symbol, status);
CREATE INDEX idx_strategies_generation ON strategies(generation DESC);
```

**Rows**: ~50K (500/day × 100 days retention)  
**Size**: ~500MB (large JSONB fields)

---

### `backtest_results`
Results from strategy backtests.

```sql
CREATE TABLE backtest_results (
    id SERIAL PRIMARY KEY,
    strategy_id UUID NOT NULL,
    start_date TIMESTAMP NOT NULL,
    end_date TIMESTAMP NOT NULL,
    initial_capital DECIMAL(20, 2) DEFAULT 10000,
    final_capital DECIMAL(20, 2),
    total_return_pct DECIMAL(10, 4),
    cagr DECIMAL(10, 4),
    sharpe_ratio DECIMAL(10, 4),
    sortino_ratio DECIMAL(10, 4),
    max_drawdown_pct DECIMAL(10, 4),
    win_rate DECIMAL(5, 4),
    profit_factor DECIMAL(10, 4),
    total_trades INTEGER,
    winning_trades INTEGER,
    losing_trades INTEGER,
    avg_win DECIMAL(20, 2),
    avg_loss DECIMAL(20, 2),
    largest_win DECIMAL(20, 2),
    largest_loss DECIMAL(20, 2),
    monthly_returns JSONB,  -- Array of monthly return percentages
    trade_log JSONB,  -- Full trade history
    created_at TIMESTAMP DEFAULT NOW(),
    FOREIGN KEY (strategy_id) REFERENCES strategies(id) ON DELETE CASCADE
);

CREATE INDEX idx_backtest_strategy ON backtest_results(strategy_id);
CREATE INDEX idx_backtest_sharpe ON backtest_results(sharpe_ratio DESC);
CREATE INDEX idx_backtest_return ON backtest_results(total_return_pct DESC);
```

**Rows**: ~50K (1 backtest per strategy)  
**Size**: ~5GB (trade_log JSONB is large)

---

### `strategy_versions`
Version history for strategies.

```sql
CREATE TABLE strategy_versions (
    id SERIAL PRIMARY KEY,
    strategy_id UUID NOT NULL,
    version INTEGER NOT NULL,
    parameters JSONB NOT NULL,
    change_description TEXT,
    created_by VARCHAR(100),
    created_at TIMESTAMP DEFAULT NOW(),
    FOREIGN KEY (strategy_id) REFERENCES strategies(id) ON DELETE CASCADE,
    UNIQUE(strategy_id, version)
);

CREATE INDEX idx_strategy_versions ON strategy_versions(strategy_id, version DESC);
```

**Rows**: ~200K (multiple versions per strategy)  
**Size**: ~200MB

---

### `financial_goals`
User-defined financial goals.

```sql
CREATE TABLE financial_goals (
    id SERIAL PRIMARY KEY,
    goal_type VARCHAR(50) UNIQUE NOT NULL,  -- 'monthly_return_pct', 'monthly_profit_usd', 'portfolio_target_usd'
    target_value DECIMAL(20, 2) NOT NULL,
    priority INTEGER DEFAULT 1,  -- 1=highest priority
    risk_tolerance DECIMAL(5, 4) DEFAULT 0.02,  -- 2% per trade
    max_drawdown_pct DECIMAL(5, 4) DEFAULT 0.15,  -- 15% max drawdown
    status VARCHAR(20) DEFAULT 'active',  -- 'active', 'paused', 'achieved', 'cancelled'
    start_date TIMESTAMP DEFAULT NOW(),
    achieved_at TIMESTAMP,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Default goals:
-- 1. Monthly Return: 10% (priority 1)
-- 2. Monthly Profit: $10,000 (priority 2)
-- 3. Portfolio Target: $1,000,000 (priority 3)
```

**Rows**: <100 (small static table)  
**Size**: <1MB

---

### `goal_progress`
Historical goal progress tracking.

```sql
CREATE TABLE goal_progress (
    id SERIAL PRIMARY KEY,
    goal_id INTEGER NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    current_value DECIMAL(20, 2) NOT NULL,
    target_value DECIMAL(20, 2) NOT NULL,
    progress_pct DECIMAL(5, 2),  -- % completion
    gap DECIMAL(20, 2),  -- target - current
    status VARCHAR(20),  -- 'behind', 'on_track', 'ahead'
    created_at TIMESTAMP DEFAULT NOW(),
    FOREIGN KEY (goal_id) REFERENCES financial_goals(id) ON DELETE CASCADE
);

CREATE INDEX idx_goal_progress ON goal_progress(goal_id, timestamp DESC);
```

**Rows**: ~100K (hourly updates × 3 goals × 1 year)  
**Size**: ~10MB

---

### `goal_adjustments`
Automatic goal-based adjustments.

```sql
CREATE TABLE goal_adjustments (
    id SERIAL PRIMARY KEY,
    goal_id INTEGER NOT NULL,
    adjustment_type VARCHAR(50) NOT NULL,  -- 'increase_risk', 'decrease_risk', etc.
    old_value DECIMAL(10, 4),
    new_value DECIMAL(10, 4),
    reason TEXT,
    applied_at TIMESTAMP DEFAULT NOW(),
    FOREIGN KEY (goal_id) REFERENCES financial_goals(id) ON DELETE CASCADE
);

CREATE INDEX idx_goal_adjustments ON goal_adjustments(goal_id, applied_at DESC);
```

**Rows**: ~10K (sparse, only when adjustments made)  
**Size**: ~5MB

---

## Order & Execution Tables

### `orders`
All order records (paper + live).

```sql
CREATE TABLE orders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    strategy_id UUID NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL,  -- 'BUY', 'SELL'
    order_type VARCHAR(20) NOT NULL,  -- 'MARKET', 'LIMIT', 'STOP_LOSS', 'TAKE_PROFIT'
    quantity DECIMAL(20, 8) NOT NULL,
    price DECIMAL(20, 8),  -- NULL for market orders
    stop_loss DECIMAL(20, 8),
    take_profit DECIMAL(20, 8),
    environment VARCHAR(10) NOT NULL,  -- 'paper', 'live'
    status VARCHAR(20) DEFAULT 'pending',  -- 'pending', 'open', 'filled', 'partially_filled', 'cancelled', 'rejected'
    exchange_order_id VARCHAR(100),  -- Binance order ID
    filled_quantity DECIMAL(20, 8) DEFAULT 0,
    average_fill_price DECIMAL(20, 8),
    commission DECIMAL(20, 8),
    commission_asset VARCHAR(10),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    filled_at TIMESTAMP,
    FOREIGN KEY (strategy_id) REFERENCES strategies(id)
);

CREATE INDEX idx_orders_strategy ON orders(strategy_id, created_at DESC);
CREATE INDEX idx_orders_status ON orders(status, created_at DESC);
CREATE INDEX idx_orders_symbol ON orders(symbol, created_at DESC);
CREATE INDEX idx_orders_environment ON orders(environment, status);
```

**Rows**: ~1M (permanent storage)  
**Size**: ~500MB

---

### `trades`
Executed trades (filled orders).

```sql
CREATE TABLE trades (
    id SERIAL PRIMARY KEY,
    order_id UUID NOT NULL,
    strategy_id UUID NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL,
    quantity DECIMAL(20, 8) NOT NULL,
    price DECIMAL(20, 8) NOT NULL,
    commission DECIMAL(20, 8),
    commission_asset VARCHAR(10),
    realized_pnl DECIMAL(20, 2),  -- For closing trades
    environment VARCHAR(10) NOT NULL,
    exchange_trade_id VARCHAR(100),
    executed_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    FOREIGN KEY (order_id) REFERENCES orders(id),
    FOREIGN KEY (strategy_id) REFERENCES strategies(id)
);

CREATE INDEX idx_trades_order ON trades(order_id);
CREATE INDEX idx_trades_strategy ON trades(strategy_id, executed_at DESC);
CREATE INDEX idx_trades_symbol ON trades(symbol, executed_at DESC);
```

**Rows**: ~1M (permanent storage)  
**Size**: ~400MB

---

### `positions`
Current open positions.

```sql
CREATE TABLE positions (
    id SERIAL PRIMARY KEY,
    strategy_id UUID NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL,  -- 'LONG', 'SHORT'
    quantity DECIMAL(20, 8) NOT NULL,
    entry_price DECIMAL(20, 8) NOT NULL,
    current_price DECIMAL(20, 8),
    stop_loss DECIMAL(20, 8),
    take_profit DECIMAL(20, 8),
    unrealized_pnl DECIMAL(20, 2),
    unrealized_pnl_pct DECIMAL(10, 4),
    environment VARCHAR(10) NOT NULL,
    opened_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    FOREIGN KEY (strategy_id) REFERENCES strategies(id),
    UNIQUE(strategy_id, symbol, environment)
);

CREATE INDEX idx_positions_strategy ON positions(strategy_id);
CREATE INDEX idx_positions_symbol ON positions(symbol);
```

**Rows**: ~100 (active positions only)  
**Size**: <1MB

---

### `portfolio_balances`
Account balances (paper + live).

```sql
CREATE TABLE portfolio_balances (
    id SERIAL PRIMARY KEY,
    environment VARCHAR(10) NOT NULL,
    asset VARCHAR(10) NOT NULL,  -- 'USDT', 'BTC', etc.
    free_balance DECIMAL(20, 8) NOT NULL,
    locked_balance DECIMAL(20, 8) DEFAULT 0,
    total_balance DECIMAL(20, 8) NOT NULL,
    usd_value DECIMAL(20, 2),
    timestamp TIMESTAMP DEFAULT NOW(),
    UNIQUE(environment, asset, timestamp)
);

CREATE INDEX idx_portfolio_env ON portfolio_balances(environment, timestamp DESC);
```

**Rows**: ~1M (snapshots every hour)  
**Size**: ~50MB

---

## Risk Management Tables

### `risk_metrics`
Portfolio-level risk calculations.

```sql
CREATE TABLE risk_metrics (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT NOW(),
    environment VARCHAR(10) NOT NULL,
    total_portfolio_value DECIMAL(20, 2) NOT NULL,
    var_95 DECIMAL(20, 2),  -- Value at Risk (95% confidence)
    cvar_95 DECIMAL(20, 2),  -- Conditional VaR
    portfolio_volatility DECIMAL(10, 4),
    sharpe_ratio DECIMAL(10, 4),
    max_drawdown DECIMAL(10, 4),
    correlation_btc DECIMAL(5, 4),  -- Correlation with BTC
    diversification_score DECIMAL(5, 4),  -- 0-1
    position_count INTEGER,
    largest_position_pct DECIMAL(5, 4)
);

CREATE INDEX idx_risk_timestamp ON risk_metrics(timestamp DESC);
```

**Rows**: ~10K (hourly snapshots)  
**Size**: ~5MB

---

### `circuit_breaker_events`
Circuit breaker trigger history.

```sql
CREATE TABLE circuit_breaker_events (
    id SERIAL PRIMARY KEY,
    trigger_type VARCHAR(50) NOT NULL,  -- 'drawdown', 'loss_streak', 'volatility_spike'
    threshold_value DECIMAL(10, 4) NOT NULL,
    actual_value DECIMAL(10, 4) NOT NULL,
    triggered_at TIMESTAMP DEFAULT NOW(),
    resolved_at TIMESTAMP,
    actions_taken JSONB,  -- e.g., ['pause_trading', 'close_positions']
    metadata JSONB
);

CREATE INDEX idx_circuit_breaker_time ON circuit_breaker_events(triggered_at DESC);
```

**Rows**: <1K (rare events)  
**Size**: <5MB

---

## Alert System Tables

### `alerts`
Active and historical alerts.

```sql
CREATE TABLE alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    alert_type VARCHAR(50) NOT NULL,  -- 'price_movement', 'order_filled', 'risk_threshold', etc.
    severity VARCHAR(10) NOT NULL,  -- 'info', 'warning', 'error', 'critical'
    title VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,
    entity_type VARCHAR(50),  -- 'strategy', 'order', 'position', 'system'
    entity_id VARCHAR(100),
    metadata JSONB,
    status VARCHAR(20) DEFAULT 'active',  -- 'active', 'acknowledged', 'resolved'
    created_at TIMESTAMP DEFAULT NOW(),
    acknowledged_at TIMESTAMP,
    resolved_at TIMESTAMP
);

CREATE INDEX idx_alerts_status ON alerts(status, created_at DESC);
CREATE INDEX idx_alerts_severity ON alerts(severity, created_at DESC);
CREATE INDEX idx_alerts_type ON alerts(alert_type, created_at DESC);
```

**Rows**: ~100K (retained for 90 days)  
**Size**: ~100MB

---

### `alert_history`
Notification delivery history.

```sql
CREATE TABLE alert_history (
    id SERIAL PRIMARY KEY,
    alert_id UUID NOT NULL,
    channel VARCHAR(20) NOT NULL,  -- 'email', 'sms', 'telegram', 'discord', 'slack', 'webhook'
    recipient VARCHAR(255),
    status VARCHAR(20) NOT NULL,  -- 'sent', 'failed', 'pending'
    error_message TEXT,
    sent_at TIMESTAMP DEFAULT NOW(),
    FOREIGN KEY (alert_id) REFERENCES alerts(id) ON DELETE CASCADE
);

CREATE INDEX idx_alert_history ON alert_history(alert_id);
```

**Rows**: ~500K (multiple channels per alert)  
**Size**: ~50MB

---

### `alert_suppressions`
Alert suppression rules.

```sql
CREATE TABLE alert_suppressions (
    id SERIAL PRIMARY KEY,
    alert_type VARCHAR(50) NOT NULL,
    entity_type VARCHAR(50),
    entity_id VARCHAR(100),
    reason TEXT,
    suppressed_until TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    created_by VARCHAR(100)
);

CREATE INDEX idx_suppressions ON alert_suppressions(alert_type, suppressed_until);
```

**Rows**: <1K (small static table)  
**Size**: <1MB

---

## User Management Tables

### `users`
User accounts (for future multi-user support).

```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(100) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) DEFAULT 'user',  -- 'admin', 'trader', 'viewer'
    api_key_hash VARCHAR(255),  -- For API authentication
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW(),
    last_login TIMESTAMP
);

CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_api_key ON users(api_key_hash);
```

**Rows**: <100 (small)  
**Size**: <1MB

---

### `audit_logs`
System activity audit trail.

```sql
CREATE TABLE audit_logs (
    id SERIAL PRIMARY KEY,
    user_id UUID,
    action VARCHAR(100) NOT NULL,  -- 'create_strategy', 'execute_order', 'update_goal'
    entity_type VARCHAR(50),
    entity_id VARCHAR(100),
    old_value JSONB,
    new_value JSONB,
    ip_address INET,
    user_agent TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX idx_audit_user ON audit_logs(user_id, created_at DESC);
CREATE INDEX idx_audit_action ON audit_logs(action, created_at DESC);
```

**Rows**: ~1M (retained for 1 year)  
**Size**: ~500MB

---

## Relationships & Foreign Keys

### Entity Relationship Diagram (Simplified)

```
users
  ↓ (creates)
strategies ──→ strategy_versions
  ↓                 ↓ (evolves from)
  ├───────────→ parent_strategy (genetic algorithm)
  ↓
backtest_results
  ↓
orders ──→ trades
  ↓         ↓
positions   ↓
           (calculates)
         risk_metrics
            ↓
      circuit_breaker_events
            ↓
         alerts ──→ alert_history
```

### Key Relationships

1. **Strategy → Orders → Trades**
   - One strategy generates many orders
   - Each order may result in multiple trades (partial fills)
   
2. **Strategy → Backtest Results**
   - One-to-one relationship
   - Cascade delete: Delete strategy → Delete backtest
   
3. **Financial Goals → Goal Progress/Adjustments**
   - One-to-many relationships
   - Cascade delete: Delete goal → Delete progress/adjustments
   
4. **Orders → Positions**
   - Orders create/modify positions
   - Position tracking is real-time (not historical)
   
5. **Alerts → Alert History**
   - One alert → Many delivery attempts (multiple channels)
   - Cascade delete: Delete alert → Delete history

---

## Indexes & Performance

### High-Performance Indexes

```sql
-- Most critical queries
CREATE INDEX idx_market_data_symbol_timestamp ON market_data(symbol, timestamp DESC);
CREATE INDEX idx_orders_strategy_status ON orders(strategy_id, status, created_at DESC);
CREATE INDEX idx_trades_strategy_executed ON trades(strategy_id, executed_at DESC);
CREATE INDEX idx_backtest_sharpe_return ON backtest_results(sharpe_ratio DESC, total_return_pct DESC);

-- Composite indexes for common filters
CREATE INDEX idx_strategies_status_symbol ON strategies(status, symbol, created_at DESC);
CREATE INDEX idx_positions_strategy_symbol ON positions(strategy_id, symbol);
```

### Query Optimization Examples

```sql
-- Slow query (before index):
SELECT * FROM market_data WHERE symbol = 'BTCUSDT' AND timestamp > NOW() - INTERVAL '7 days';
-- Query time: ~500ms

-- After index `idx_market_data_symbol_timestamp`:
-- Query time: ~5ms (100x improvement)

-- Slow query (before composite index):
SELECT * FROM strategies WHERE status = 'active' AND symbol = 'BTCUSDT';
-- Query time: ~200ms (full table scan)

-- After index `idx_strategies_status_symbol`:
-- Query time: ~2ms
```

---

## Partitioning Strategy

### Time-Series Tables (Future Enhancement)

**Target for TimescaleDB Migration**:

```sql
-- Convert market_data to hypertable
SELECT create_hypertable('market_data', 'timestamp', chunk_time_interval => INTERVAL '7 days');

-- Automatic data retention
SELECT add_retention_policy('market_data', INTERVAL '90 days');

-- Compression for old data
ALTER TABLE market_data SET (timescaledb.compress, timescaledb.compress_segmentby = 'symbol');
SELECT add_compression_policy('market_data', INTERVAL '30 days');
```

**Benefits**:
- 10-100x faster time-series queries
- Automatic partitioning by time
- Compression reduces storage by 90%
- Built-in retention policies

### Range Partitioning (Current)

```sql
-- Manually partition large tables by month (if needed)
CREATE TABLE backtest_results_2025_11 PARTITION OF backtest_results
FOR VALUES FROM ('2025-11-01') TO ('2025-12-01');

CREATE TABLE backtest_results_2025_12 PARTITION OF backtest_results
FOR VALUES FROM ('2025-12-01') TO ('2026-01-01');
```

---

## Database Maintenance

### Vacuum & Analyze Schedule

```sql
-- Daily vacuum analyze (automated via cron)
VACUUM ANALYZE market_data;
VACUUM ANALYZE technical_indicators;
VACUUM ANALYZE orders;
VACUUM ANALYZE trades;

-- Weekly full vacuum
VACUUM FULL ANALYZE backtest_results;
```

### Backup Strategy

- **Frequency**: Daily at 2:00 AM UTC
- **Method**: `pg_dump` with compression
- **Retention**: 30 daily, 12 weekly, 12 monthly
- **Storage**: Local disk + S3 (future)

```bash
# Example backup command (executed by cron)
pg_dump -U mastertrade -d mastertrade -F c -f /backups/mastertrade_$(date +%Y%m%d).dump
```

### Monitoring Queries

```sql
-- Table sizes
SELECT 
    schemaname, 
    tablename, 
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;

-- Index usage
SELECT 
    schemaname, 
    tablename, 
    indexname, 
    idx_scan AS index_scans,
    pg_size_pretty(pg_relation_size(indexrelid)) AS index_size
FROM pg_stat_user_indexes
ORDER BY idx_scan ASC;

-- Slow queries (enable pg_stat_statements extension)
SELECT 
    query, 
    calls, 
    mean_exec_time, 
    max_exec_time
FROM pg_stat_statements
ORDER BY mean_exec_time DESC
LIMIT 20;
```

---

**Next**: [05_MESSAGE_BROKER.md](./05_MESSAGE_BROKER.md) - RabbitMQ topology and message routing
