-- TimescaleDB Setup for MasterTrade System
-- High-performance time-series storage for market data, sentiment, and on-chain metrics
-- 
-- Features:
-- - Automatic time-based partitioning (hypertables)
-- - Continuous aggregates for real-time analytics
-- - Compression policies (90%+ storage reduction)
-- - Retention policies for automatic data cleanup
-- - Optimized indexes for time-range queries

-- ============================================================================
-- 1. ENABLE TIMESCALEDB EXTENSION
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

-- ============================================================================
-- 2. PRICE DATA (OHLCV) - High-frequency market data
-- ============================================================================

-- Main price data table (raw tick/1m data)
CREATE TABLE IF NOT EXISTS price_data (
    time TIMESTAMPTZ NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    exchange VARCHAR(50) NOT NULL,
    open DECIMAL(20, 8) NOT NULL,
    high DECIMAL(20, 8) NOT NULL,
    low DECIMAL(20, 8) NOT NULL,
    close DECIMAL(20, 8) NOT NULL,
    volume DECIMAL(30, 8) NOT NULL,
    quote_volume DECIMAL(30, 8),
    trades_count INTEGER,
    metadata JSONB,
    PRIMARY KEY (time, symbol, exchange)
);

-- Convert to hypertable (automatic time-based partitioning)
SELECT create_hypertable('price_data', 'time', 
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);

-- Indexes for efficient queries
CREATE INDEX IF NOT EXISTS idx_price_data_symbol_time ON price_data (symbol, time DESC);
CREATE INDEX IF NOT EXISTS idx_price_data_exchange_time ON price_data (exchange, time DESC);
CREATE INDEX IF NOT EXISTS idx_price_data_metadata ON price_data USING GIN (metadata);

-- Compression policy (compress data older than 7 days)
ALTER TABLE price_data SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'symbol,exchange',
    timescaledb.compress_orderby = 'time DESC'
);

SELECT add_compression_policy('price_data', INTERVAL '7 days', if_not_exists => TRUE);

-- Retention policy (keep 1 year of minute data)
SELECT add_retention_policy('price_data', INTERVAL '365 days', if_not_exists => TRUE);

-- ============================================================================
-- 3. CONTINUOUS AGGREGATES - Pre-computed aggregations for fast queries
-- ============================================================================

-- 5-minute OHLCV aggregate
CREATE MATERIALIZED VIEW IF NOT EXISTS price_data_5m
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('5 minutes', time) AS bucket,
    symbol,
    exchange,
    FIRST(open, time) AS open,
    MAX(high) AS high,
    MIN(low) AS low,
    LAST(close, time) AS close,
    SUM(volume) AS volume,
    SUM(quote_volume) AS quote_volume,
    SUM(trades_count) AS trades_count
FROM price_data
GROUP BY bucket, symbol, exchange
WITH NO DATA;

-- 15-minute OHLCV aggregate
CREATE MATERIALIZED VIEW IF NOT EXISTS price_data_15m
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('15 minutes', time) AS bucket,
    symbol,
    exchange,
    FIRST(open, time) AS open,
    MAX(high) AS high,
    MIN(low) AS low,
    LAST(close, time) AS close,
    SUM(volume) AS volume,
    SUM(quote_volume) AS quote_volume,
    SUM(trades_count) AS trades_count
FROM price_data
GROUP BY bucket, symbol, exchange
WITH NO DATA;

-- 1-hour OHLCV aggregate
CREATE MATERIALIZED VIEW IF NOT EXISTS price_data_1h
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', time) AS bucket,
    symbol,
    exchange,
    FIRST(open, time) AS open,
    MAX(high) AS high,
    MIN(low) AS low,
    LAST(close, time) AS close,
    SUM(volume) AS volume,
    SUM(quote_volume) AS quote_volume,
    SUM(trades_count) AS trades_count
FROM price_data
GROUP BY bucket, symbol, exchange
WITH NO DATA;

-- 4-hour OHLCV aggregate
CREATE MATERIALIZED VIEW IF NOT EXISTS price_data_4h
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('4 hours', time) AS bucket,
    symbol,
    exchange,
    FIRST(open, time) AS open,
    MAX(high) AS high,
    MIN(low) AS low,
    LAST(close, time) AS close,
    SUM(volume) AS volume,
    SUM(quote_volume) AS quote_volume,
    SUM(trades_count) AS trades_count
FROM price_data
GROUP BY bucket, symbol, exchange
WITH NO DATA;

-- 1-day OHLCV aggregate
CREATE MATERIALIZED VIEW IF NOT EXISTS price_data_1d
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 day', time) AS bucket,
    symbol,
    exchange,
    FIRST(open, time) AS open,
    MAX(high) AS high,
    MIN(low) AS low,
    LAST(close, time) AS close,
    SUM(volume) AS volume,
    SUM(quote_volume) AS quote_volume,
    SUM(trades_count) AS trades_count
FROM price_data
GROUP BY bucket, symbol, exchange
WITH NO DATA;

-- Refresh policies for continuous aggregates (automatic updates)
SELECT add_continuous_aggregate_policy('price_data_5m',
    start_offset => INTERVAL '1 hour',
    end_offset => INTERVAL '1 minute',
    schedule_interval => INTERVAL '1 minute',
    if_not_exists => TRUE
);

SELECT add_continuous_aggregate_policy('price_data_15m',
    start_offset => INTERVAL '3 hours',
    end_offset => INTERVAL '5 minutes',
    schedule_interval => INTERVAL '5 minutes',
    if_not_exists => TRUE
);

SELECT add_continuous_aggregate_policy('price_data_1h',
    start_offset => INTERVAL '12 hours',
    end_offset => INTERVAL '15 minutes',
    schedule_interval => INTERVAL '15 minutes',
    if_not_exists => TRUE
);

SELECT add_continuous_aggregate_policy('price_data_4h',
    start_offset => INTERVAL '2 days',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour',
    if_not_exists => TRUE
);

SELECT add_continuous_aggregate_policy('price_data_1d',
    start_offset => INTERVAL '7 days',
    end_offset => INTERVAL '4 hours',
    schedule_interval => INTERVAL '4 hours',
    if_not_exists => TRUE
);

-- ============================================================================
-- 4. SENTIMENT DATA - Social media, news, and market sentiment
-- ============================================================================

CREATE TABLE IF NOT EXISTS sentiment_data (
    time TIMESTAMPTZ NOT NULL,
    asset VARCHAR(20) NOT NULL,
    source VARCHAR(50) NOT NULL,  -- twitter, reddit, news, lunarcrush
    sentiment_score DECIMAL(5, 4) NOT NULL,  -- -1.0 to 1.0
    sentiment_label VARCHAR(20),  -- bearish, neutral, bullish
    volume INTEGER,  -- number of mentions/posts
    engagement_score DECIMAL(10, 2),  -- likes, retweets, comments
    entities JSONB,  -- mentioned entities, hashtags
    metadata JSONB,
    PRIMARY KEY (time, asset, source)
);

SELECT create_hypertable('sentiment_data', 'time',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);

CREATE INDEX IF NOT EXISTS idx_sentiment_asset_time ON sentiment_data (asset, time DESC);
CREATE INDEX IF NOT EXISTS idx_sentiment_source_time ON sentiment_data (source, time DESC);
CREATE INDEX IF NOT EXISTS idx_sentiment_label ON sentiment_data (sentiment_label, time DESC);

-- Compression for sentiment data
ALTER TABLE sentiment_data SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'asset,source',
    timescaledb.compress_orderby = 'time DESC'
);

SELECT add_compression_policy('sentiment_data', INTERVAL '7 days', if_not_exists => TRUE);
SELECT add_retention_policy('sentiment_data', INTERVAL '180 days', if_not_exists => TRUE);

-- Hourly sentiment aggregates
CREATE MATERIALIZED VIEW IF NOT EXISTS sentiment_hourly
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', time) AS bucket,
    asset,
    source,
    AVG(sentiment_score) AS avg_sentiment,
    STDDEV(sentiment_score) AS sentiment_volatility,
    SUM(volume) AS total_mentions,
    SUM(engagement_score) AS total_engagement,
    COUNT(*) AS data_points
FROM sentiment_data
GROUP BY bucket, asset, source
WITH NO DATA;

SELECT add_continuous_aggregate_policy('sentiment_hourly',
    start_offset => INTERVAL '3 hours',
    end_offset => INTERVAL '5 minutes',
    schedule_interval => INTERVAL '5 minutes',
    if_not_exists => TRUE
);

-- Daily sentiment aggregates
CREATE MATERIALIZED VIEW IF NOT EXISTS sentiment_daily
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 day', time) AS bucket,
    asset,
    source,
    AVG(sentiment_score) AS avg_sentiment,
    STDDEV(sentiment_score) AS sentiment_volatility,
    SUM(volume) AS total_mentions,
    SUM(engagement_score) AS total_engagement,
    COUNT(*) AS data_points
FROM sentiment_data
GROUP BY bucket, asset, source
WITH NO DATA;

SELECT add_continuous_aggregate_policy('sentiment_daily',
    start_offset => INTERVAL '7 days',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour',
    if_not_exists => TRUE
);

-- ============================================================================
-- 5. FLOW DATA - On-chain and exchange flows (whale movements, large trades)
-- ============================================================================

CREATE TABLE IF NOT EXISTS flow_data (
    time TIMESTAMPTZ NOT NULL,
    asset VARCHAR(20) NOT NULL,
    flow_type VARCHAR(50) NOT NULL,  -- whale_transaction, exchange_inflow, exchange_outflow, large_trade
    source VARCHAR(50) NOT NULL,  -- moralis, glassnode, binance, coinbase, deribit
    amount DECIMAL(30, 8) NOT NULL,
    amount_usd DECIMAL(20, 2),
    from_address VARCHAR(100),
    to_address VARCHAR(100),
    direction VARCHAR(20),  -- inflow, outflow, transfer
    is_whale BOOLEAN DEFAULT FALSE,
    metadata JSONB,
    PRIMARY KEY (time, asset, flow_type, source)
);

SELECT create_hypertable('flow_data', 'time',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);

CREATE INDEX IF NOT EXISTS idx_flow_asset_time ON flow_data (asset, time DESC);
CREATE INDEX IF NOT EXISTS idx_flow_type_time ON flow_data (flow_type, time DESC);
CREATE INDEX IF NOT EXISTS idx_flow_whale ON flow_data (is_whale, time DESC) WHERE is_whale = TRUE;
CREATE INDEX IF NOT EXISTS idx_flow_direction ON flow_data (direction, time DESC);

-- Compression for flow data
ALTER TABLE flow_data SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'asset,flow_type,source',
    timescaledb.compress_orderby = 'time DESC'
);

SELECT add_compression_policy('flow_data', INTERVAL '14 days', if_not_exists => TRUE);
SELECT add_retention_policy('flow_data', INTERVAL '365 days', if_not_exists => TRUE);

-- Hourly flow aggregates
CREATE MATERIALIZED VIEW IF NOT EXISTS flow_hourly
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', time) AS bucket,
    asset,
    flow_type,
    direction,
    SUM(amount) AS total_amount,
    SUM(amount_usd) AS total_amount_usd,
    COUNT(*) AS flow_count,
    SUM(CASE WHEN is_whale THEN 1 ELSE 0 END) AS whale_count,
    AVG(amount_usd) AS avg_amount_usd
FROM flow_data
GROUP BY bucket, asset, flow_type, direction
WITH NO DATA;

SELECT add_continuous_aggregate_policy('flow_hourly',
    start_offset => INTERVAL '6 hours',
    end_offset => INTERVAL '10 minutes',
    schedule_interval => INTERVAL '10 minutes',
    if_not_exists => TRUE
);

-- Daily flow aggregates
CREATE MATERIALIZED VIEW IF NOT EXISTS flow_daily
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 day', time) AS bucket,
    asset,
    flow_type,
    direction,
    SUM(amount) AS total_amount,
    SUM(amount_usd) AS total_amount_usd,
    COUNT(*) AS flow_count,
    SUM(CASE WHEN is_whale THEN 1 ELSE 0 END) AS whale_count,
    AVG(amount_usd) AS avg_amount_usd,
    MAX(amount_usd) AS max_amount_usd
FROM flow_data
GROUP BY bucket, asset, flow_type, direction
WITH NO DATA;

SELECT add_continuous_aggregate_policy('flow_daily',
    start_offset => INTERVAL '7 days',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour',
    if_not_exists => TRUE
);

-- Net flow view (inflows - outflows)
CREATE MATERIALIZED VIEW IF NOT EXISTS net_flow_hourly
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', time) AS bucket,
    asset,
    flow_type,
    SUM(CASE WHEN direction = 'inflow' THEN amount_usd ELSE -amount_usd END) AS net_flow_usd,
    SUM(CASE WHEN direction = 'inflow' THEN 1 ELSE 0 END) AS inflow_count,
    SUM(CASE WHEN direction = 'outflow' THEN 1 ELSE 0 END) AS outflow_count
FROM flow_data
WHERE direction IN ('inflow', 'outflow')
GROUP BY bucket, asset, flow_type
WITH NO DATA;

SELECT add_continuous_aggregate_policy('net_flow_hourly',
    start_offset => INTERVAL '6 hours',
    end_offset => INTERVAL '10 minutes',
    schedule_interval => INTERVAL '10 minutes',
    if_not_exists => TRUE
);

-- ============================================================================
-- 6. TECHNICAL INDICATORS - Pre-calculated indicators
-- ============================================================================

CREATE TABLE IF NOT EXISTS indicator_data (
    time TIMESTAMPTZ NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    indicator_name VARCHAR(50) NOT NULL,
    timeframe VARCHAR(10) NOT NULL,  -- 1m, 5m, 15m, 1h, 4h, 1d
    value DECIMAL(20, 8),
    metadata JSONB,
    PRIMARY KEY (time, symbol, indicator_name, timeframe)
);

SELECT create_hypertable('indicator_data', 'time',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);

CREATE INDEX IF NOT EXISTS idx_indicator_symbol_time ON indicator_data (symbol, indicator_name, timeframe, time DESC);

ALTER TABLE indicator_data SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'symbol,indicator_name,timeframe',
    timescaledb.compress_orderby = 'time DESC'
);

SELECT add_compression_policy('indicator_data', INTERVAL '7 days', if_not_exists => TRUE);
SELECT add_retention_policy('indicator_data', INTERVAL '180 days', if_not_exists => TRUE);

-- ============================================================================
-- 7. PERFORMANCE VIEWS - Useful analytics views
-- ============================================================================

-- Market overview with latest prices
CREATE OR REPLACE VIEW market_overview AS
SELECT DISTINCT ON (symbol, exchange)
    symbol,
    exchange,
    time,
    close AS price,
    volume,
    (close - LAG(close, 1) OVER (PARTITION BY symbol, exchange ORDER BY time)) / 
        NULLIF(LAG(close, 1) OVER (PARTITION BY symbol, exchange ORDER BY time), 0) * 100 AS price_change_pct
FROM price_data
ORDER BY symbol, exchange, time DESC;

-- Sentiment summary by asset
CREATE OR REPLACE VIEW sentiment_summary AS
SELECT
    asset,
    time_bucket('1 hour', time) AS hour,
    AVG(sentiment_score) AS avg_sentiment,
    SUM(volume) AS total_mentions,
    COUNT(DISTINCT source) AS sources_count
FROM sentiment_data
WHERE time > NOW() - INTERVAL '24 hours'
GROUP BY asset, hour
ORDER BY hour DESC;

-- Whale activity summary
CREATE OR REPLACE VIEW whale_activity AS
SELECT
    asset,
    time_bucket('1 hour', time) AS hour,
    COUNT(*) AS whale_transactions,
    SUM(amount_usd) AS total_value_usd,
    AVG(amount_usd) AS avg_value_usd
FROM flow_data
WHERE is_whale = TRUE
    AND time > NOW() - INTERVAL '24 hours'
GROUP BY asset, hour
ORDER BY hour DESC, total_value_usd DESC;

-- ============================================================================
-- 8. HELPER FUNCTIONS
-- ============================================================================

-- Function to get OHLCV for any timeframe
CREATE OR REPLACE FUNCTION get_ohlcv(
    p_symbol VARCHAR,
    p_exchange VARCHAR,
    p_interval VARCHAR,
    p_start TIMESTAMPTZ,
    p_end TIMESTAMPTZ
) RETURNS TABLE (
    time TIMESTAMPTZ,
    open DECIMAL,
    high DECIMAL,
    low DECIMAL,
    close DECIMAL,
    volume DECIMAL
) AS $$
BEGIN
    RETURN QUERY
    CASE p_interval
        WHEN '1m' THEN
            SELECT time, open, high, low, close, volume
            FROM price_data
            WHERE symbol = p_symbol AND exchange = p_exchange
                AND time >= p_start AND time <= p_end
            ORDER BY time;
        WHEN '5m' THEN
            SELECT bucket AS time, open, high, low, close, volume
            FROM price_data_5m
            WHERE symbol = p_symbol AND exchange = p_exchange
                AND bucket >= p_start AND bucket <= p_end
            ORDER BY bucket;
        WHEN '15m' THEN
            SELECT bucket AS time, open, high, low, close, volume
            FROM price_data_15m
            WHERE symbol = p_symbol AND exchange = p_exchange
                AND bucket >= p_start AND bucket <= p_end
            ORDER BY bucket;
        WHEN '1h' THEN
            SELECT bucket AS time, open, high, low, close, volume
            FROM price_data_1h
            WHERE symbol = p_symbol AND exchange = p_exchange
                AND bucket >= p_start AND bucket <= p_end
            ORDER BY bucket;
        WHEN '4h' THEN
            SELECT bucket AS time, open, high, low, close, volume
            FROM price_data_4h
            WHERE symbol = p_symbol AND exchange = p_exchange
                AND bucket >= p_start AND bucket <= p_end
            ORDER BY bucket;
        WHEN '1d' THEN
            SELECT bucket AS time, open, high, low, close, volume
            FROM price_data_1d
            WHERE symbol = p_symbol AND exchange = p_exchange
                AND bucket >= p_start AND bucket <= p_end
            ORDER BY bucket;
        ELSE
            SELECT time, open, high, low, close, volume
            FROM price_data
            WHERE symbol = p_symbol AND exchange = p_exchange
                AND time >= p_start AND time <= p_end
            ORDER BY time;
    END CASE;
END;
$$ LANGUAGE plpgsql;

-- Function to calculate price change
CREATE OR REPLACE FUNCTION price_change_percent(
    p_symbol VARCHAR,
    p_exchange VARCHAR,
    p_hours INTEGER DEFAULT 24
) RETURNS DECIMAL AS $$
DECLARE
    v_current_price DECIMAL;
    v_old_price DECIMAL;
BEGIN
    -- Get current price
    SELECT close INTO v_current_price
    FROM price_data
    WHERE symbol = p_symbol AND exchange = p_exchange
    ORDER BY time DESC
    LIMIT 1;
    
    -- Get price from p_hours ago
    SELECT close INTO v_old_price
    FROM price_data
    WHERE symbol = p_symbol AND exchange = p_exchange
        AND time <= NOW() - (p_hours || ' hours')::INTERVAL
    ORDER BY time DESC
    LIMIT 1;
    
    -- Calculate percentage change
    IF v_old_price IS NULL OR v_old_price = 0 THEN
        RETURN NULL;
    END IF;
    
    RETURN ((v_current_price - v_old_price) / v_old_price) * 100;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- 9. GRANTS (adjust based on your user setup)
-- ============================================================================

-- Grant appropriate permissions
-- GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA public TO mastertrade_app;
-- GRANT SELECT ON ALL MATERIALIZED VIEWS IN SCHEMA public TO mastertrade_app;
-- GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO mastertrade_app;

-- ============================================================================
-- SETUP COMPLETE
-- ============================================================================

-- Verify TimescaleDB is working
SELECT timescaledb_information.hypertable;

-- Show compression stats
SELECT * FROM timescaledb_information.compression_settings;

-- Show continuous aggregate policies
SELECT * FROM timescaledb_information.continuous_aggregates;

COMMENT ON TABLE price_data IS 'High-frequency OHLCV price data with automatic partitioning and compression';
COMMENT ON TABLE sentiment_data IS 'Social media and news sentiment data with aggregation';
COMMENT ON TABLE flow_data IS 'On-chain and exchange flow data (whale movements, large trades)';
COMMENT ON TABLE indicator_data IS 'Pre-calculated technical indicators for multiple timeframes';
