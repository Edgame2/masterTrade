-- Signal Aggregation Database Tables
-- These tables store signals used by the signal aggregator

-- Social Sentiment Table
CREATE TABLE IF NOT EXISTS social_sentiment (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    source VARCHAR(50) NOT NULL,  -- twitter, reddit, lunarcrush, etc.
    sentiment_score FLOAT NOT NULL,  -- -1 to 1
    sentiment_label VARCHAR(50),
    social_volume INTEGER DEFAULT 0,
    engagement_count INTEGER DEFAULT 0,
    influencer_sentiment FLOAT,
    sentiment_change_24h FLOAT,
    trending BOOLEAN DEFAULT FALSE,
    viral_coefficient FLOAT,
    top_keywords TEXT[],
    timestamp TIMESTAMP NOT NULL,
    collected_at TIMESTAMP DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_social_sentiment_symbol_time ON social_sentiment(symbol, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_social_sentiment_source ON social_sentiment(source);
CREATE INDEX IF NOT EXISTS idx_social_sentiment_trending ON social_sentiment(trending) WHERE trending = TRUE;

-- On-Chain Metrics Table
CREATE TABLE IF NOT EXISTS onchain_metrics (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    metric_name VARCHAR(100) NOT NULL,
    value FLOAT NOT NULL,
    
    -- Common metrics
    nvt_ratio FLOAT,
    mvrv_ratio FLOAT,
    exchange_netflow FLOAT,
    active_addresses INTEGER,
    transaction_volume FLOAT,
    exchange_reserves FLOAT,
    exchange_inflow FLOAT,
    exchange_outflow FLOAT,
    hash_rate FLOAT,
    difficulty FLOAT,
    
    -- Statistical context
    percentile_rank FLOAT,  -- 0-100
    z_score FLOAT,
    
    -- Interpretation
    interpretation TEXT,
    signal VARCHAR(20),  -- bullish, bearish, neutral
    
    timestamp TIMESTAMP NOT NULL,
    source VARCHAR(50) NOT NULL,  -- glassnode, moralis, nansen, etc.
    metadata JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_onchain_metrics_symbol_time ON onchain_metrics(symbol, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_onchain_metrics_name ON onchain_metrics(metric_name);
CREATE INDEX IF NOT EXISTS idx_onchain_metrics_signal ON onchain_metrics(signal);

-- Whale Alerts Table
CREATE TABLE IF NOT EXISTS whale_alerts (
    id SERIAL PRIMARY KEY,
    alert_id VARCHAR(100) UNIQUE NOT NULL,
    alert_type VARCHAR(50) NOT NULL,  -- large_transfer, exchange_inflow, exchange_outflow, etc.
    symbol VARCHAR(20) NOT NULL,
    amount FLOAT NOT NULL,
    amount_usd FLOAT NOT NULL,
    
    from_address VARCHAR(255),
    to_address VARCHAR(255),
    from_entity VARCHAR(255),
    to_entity VARCHAR(255),
    
    transaction_hash VARCHAR(255),
    blockchain VARCHAR(50) NOT NULL,
    
    significance_score FLOAT NOT NULL,  -- 0-1
    market_impact_estimate FLOAT,  -- percentage
    
    timestamp TIMESTAMP NOT NULL,
    detected_at TIMESTAMP DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_whale_alerts_symbol_time ON whale_alerts(symbol, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_whale_alerts_type ON whale_alerts(alert_type);
CREATE INDEX IF NOT EXISTS idx_whale_alerts_significance ON whale_alerts(significance_score DESC);
CREATE INDEX IF NOT EXISTS idx_whale_alerts_amount ON whale_alerts(amount_usd DESC);

-- Institutional Flow Signals Table
CREATE TABLE IF NOT EXISTS institutional_flow_signals (
    id SERIAL PRIMARY KEY,
    signal_id VARCHAR(100) UNIQUE NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    flow_type VARCHAR(50) NOT NULL,  -- block_trade, unusual_volume, dark_pool, etc.
    
    size_usd FLOAT NOT NULL,
    price FLOAT NOT NULL,
    side VARCHAR(10) NOT NULL,  -- buy, sell
    
    exchange VARCHAR(50) NOT NULL,
    is_block_trade BOOLEAN DEFAULT FALSE,
    is_unusual_volume BOOLEAN DEFAULT FALSE,
    
    volume_ratio FLOAT,  -- ratio to average volume
    price_impact FLOAT,  -- percentage
    
    confidence_score FLOAT NOT NULL,  -- 0-1
    urgency VARCHAR(20) NOT NULL,  -- weak, moderate, strong, very_strong
    
    timestamp TIMESTAMP NOT NULL,
    detected_at TIMESTAMP DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_inst_flow_symbol_time ON institutional_flow_signals(symbol, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_inst_flow_type ON institutional_flow_signals(flow_type);
CREATE INDEX IF NOT EXISTS idx_inst_flow_confidence ON institutional_flow_signals(confidence_score DESC);

-- Market Signal Aggregates Table (Published Signals Log)
CREATE TABLE IF NOT EXISTS market_signal_aggregates (
    id SERIAL PRIMARY KEY,
    signal_id VARCHAR(100) UNIQUE NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    
    -- Overall signal
    overall_signal VARCHAR(20) NOT NULL,  -- bullish, bearish, neutral
    signal_strength VARCHAR(20) NOT NULL,  -- weak, moderate, strong, very_strong
    confidence FLOAT NOT NULL,  -- 0-1
    
    -- Component signals
    price_signal VARCHAR(20),
    price_strength FLOAT,
    sentiment_signal VARCHAR(20),
    sentiment_strength FLOAT,
    onchain_signal VARCHAR(20),
    onchain_strength FLOAT,
    flow_signal VARCHAR(20),
    flow_strength FLOAT,
    
    -- Component weights
    component_weights JSONB,
    
    -- Risk indicators
    volatility FLOAT,
    risk_level VARCHAR(20),
    
    -- Trading recommendation
    recommended_action VARCHAR(20),
    position_size_modifier FLOAT,
    
    timestamp TIMESTAMP NOT NULL,
    expires_at TIMESTAMP,
    
    contributing_alerts TEXT[],
    contributing_updates TEXT[],
    metadata JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_market_signals_symbol_time ON market_signal_aggregates(symbol, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_market_signals_strength ON market_signal_aggregates(signal_strength);
CREATE INDEX IF NOT EXISTS idx_market_signals_confidence ON market_signal_aggregates(confidence DESC);
CREATE INDEX IF NOT EXISTS idx_market_signals_action ON market_signal_aggregates(recommended_action);

-- Strategy Signals Table (Strategy → Order Executor)
CREATE TABLE IF NOT EXISTS strategy_signals (
    id SERIAL PRIMARY KEY,
    signal_id VARCHAR(100) UNIQUE NOT NULL,
    strategy_id VARCHAR(100) NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    
    action VARCHAR(50) NOT NULL,  -- ENTER_LONG, ENTER_SHORT, EXIT, CLOSE_ALL
    signal_strength FLOAT NOT NULL,  -- 0-1
    
    entry_price FLOAT,
    stop_loss FLOAT,
    take_profit FLOAT,
    position_size_usd FLOAT,
    leverage FLOAT,
    
    confidence FLOAT NOT NULL,  -- 0-1
    urgency VARCHAR(20) NOT NULL,  -- weak, moderate, strong, very_strong
    
    reasoning TEXT,
    contributing_signals TEXT[],
    
    timestamp TIMESTAMP NOT NULL,
    valid_until TIMESTAMP,
    
    -- Execution tracking
    executed BOOLEAN DEFAULT FALSE,
    executed_at TIMESTAMP,
    execution_price FLOAT,
    execution_status VARCHAR(50),
    
    metadata JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_strategy_signals_symbol_time ON strategy_signals(symbol, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_strategy_signals_strategy ON strategy_signals(strategy_id);
CREATE INDEX IF NOT EXISTS idx_strategy_signals_executed ON strategy_signals(executed);
CREATE INDEX IF NOT EXISTS idx_strategy_signals_action ON strategy_signals(action);

-- Add comments for documentation
COMMENT ON TABLE social_sentiment IS 'Social media sentiment data from Twitter, Reddit, LunarCrush, etc.';
COMMENT ON TABLE onchain_metrics IS 'On-chain blockchain metrics like NVT, MVRV, exchange flows';
COMMENT ON TABLE whale_alerts IS 'Large cryptocurrency transaction alerts from Moralis, Glassnode';
COMMENT ON TABLE institutional_flow_signals IS 'Institutional trading activity: block trades, unusual volume';
COMMENT ON TABLE market_signal_aggregates IS 'Aggregated signals combining all data sources for strategy consumption';
COMMENT ON TABLE strategy_signals IS 'Trading signals generated by strategies for order execution';

-- Create function to auto-delete old data (TTL)
CREATE OR REPLACE FUNCTION cleanup_old_signals()
RETURNS void AS $$
BEGIN
    -- Delete social sentiment older than 7 days
    DELETE FROM social_sentiment WHERE timestamp < NOW() - INTERVAL '7 days';
    
    -- Delete on-chain metrics older than 30 days
    DELETE FROM onchain_metrics WHERE timestamp < NOW() - INTERVAL '30 days';
    
    -- Delete whale alerts older than 14 days
    DELETE FROM whale_alerts WHERE timestamp < NOW() - INTERVAL '14 days';
    
    -- Delete institutional flow older than 7 days
    DELETE FROM institutional_flow_signals WHERE timestamp < NOW() - INTERVAL '7 days';
    
    -- Delete market signals older than 7 days
    DELETE FROM market_signal_aggregates WHERE timestamp < NOW() - INTERVAL '7 days';
    
    -- Delete executed strategy signals older than 30 days
    DELETE FROM strategy_signals WHERE executed = TRUE AND timestamp < NOW() - INTERVAL '30 days';
    
    -- Delete old unexecuted signals (expired)
    DELETE FROM strategy_signals WHERE executed = FALSE AND valid_until < NOW() - INTERVAL '1 day';
END;
$$ LANGUAGE plpgsql;

-- Grant permissions
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO mastertrade;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO mastertrade;
