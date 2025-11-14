-- Exchange Data Tables Migration
-- 
-- Creates tables for multi-exchange data collection:
-- 1. exchange_orderbooks - Order book snapshots from all exchanges
-- 2. large_trades - Significant trades detected across exchanges
-- 3. funding_rates - Funding rates for perpetual contracts (derivatives)
-- 4. open_interest - Open interest tracking for futures/options

-- =====================================================
-- Table: exchange_orderbooks
-- Stores order book snapshots from multiple exchanges
-- =====================================================

CREATE TABLE IF NOT EXISTS exchange_orderbooks (
    id VARCHAR(255) PRIMARY KEY,                 -- {exchange}_{symbol}_{timestamp}
    exchange VARCHAR(50) NOT NULL,                -- Exchange name (binance, coinbase, deribit, cme)
    symbol VARCHAR(50) NOT NULL,                  -- Trading pair/instrument
    bids JSONB NOT NULL,                          -- Array of [price, size] bids
    asks JSONB NOT NULL,                          -- Array of [price, size] asks
    timestamp TIMESTAMP NOT NULL,                 -- Orderbook timestamp
    sequence BIGINT,                              -- Sequence number (if provided by exchange)
    metadata JSONB,                               -- Additional data (spread, depth, etc.)
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_exchange_orderbooks_exchange_symbol ON exchange_orderbooks(exchange, symbol);
CREATE INDEX idx_exchange_orderbooks_timestamp ON exchange_orderbooks(timestamp DESC);
CREATE INDEX idx_exchange_orderbooks_symbol ON exchange_orderbooks(symbol);

COMMENT ON TABLE exchange_orderbooks IS 'Order book snapshots from multiple exchanges';
COMMENT ON COLUMN exchange_orderbooks.bids IS 'Bid side as JSON array [[price, size], ...]';
COMMENT ON COLUMN exchange_orderbooks.asks IS 'Ask side as JSON array [[price, size], ...]';


-- =====================================================
-- Table: large_trades
-- Tracks significant trades across all exchanges
-- =====================================================

CREATE TABLE IF NOT EXISTS large_trades (
    id VARCHAR(255) PRIMARY KEY,                 -- {exchange}_{symbol}_{trade_id}
    exchange VARCHAR(50) NOT NULL,                -- Exchange name
    symbol VARCHAR(50) NOT NULL,                  -- Trading pair/instrument
    side VARCHAR(10) NOT NULL,                    -- 'buy' or 'sell'
    price DECIMAL(20, 8) NOT NULL,                -- Trade price
    size DECIMAL(20, 8) NOT NULL,                 -- Trade size (in base currency)
    value_usd DECIMAL(20, 2) NOT NULL,            -- USD value of trade
    timestamp TIMESTAMP NOT NULL,                 -- Trade timestamp
    trade_id VARCHAR(255),                        -- Exchange trade ID
    is_liquidation BOOLEAN DEFAULT FALSE,         -- True if liquidation
    metadata JSONB,                               -- Additional trade data
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_large_trades_exchange_symbol ON large_trades(exchange, symbol);
CREATE INDEX idx_large_trades_timestamp ON large_trades(timestamp DESC);
CREATE INDEX idx_large_trades_value ON large_trades(value_usd DESC);
CREATE INDEX idx_large_trades_liquidation ON large_trades(is_liquidation) WHERE is_liquidation = TRUE;
CREATE INDEX idx_large_trades_symbol_timestamp ON large_trades(symbol, timestamp DESC);

COMMENT ON TABLE large_trades IS 'Large trades detected across exchanges';
COMMENT ON COLUMN large_trades.value_usd IS 'Trade value in USD for threshold detection';
COMMENT ON COLUMN large_trades.is_liquidation IS 'True for forced liquidations';


-- =====================================================
-- Table: funding_rates
-- Funding rates for perpetual futures contracts
-- =====================================================

CREATE TABLE IF NOT EXISTS funding_rates (
    id VARCHAR(255) PRIMARY KEY,                 -- {exchange}_{symbol}_{timestamp}
    exchange VARCHAR(50) NOT NULL,                -- Exchange name
    symbol VARCHAR(50) NOT NULL,                  -- Perpetual contract symbol
    rate DECIMAL(10, 8) NOT NULL,                 -- Current funding rate (decimal, e.g., 0.0001 = 0.01%)
    predicted_rate DECIMAL(10, 8),                -- Predicted next funding rate
    timestamp TIMESTAMP NOT NULL,                 -- Data timestamp
    next_funding_time TIMESTAMP,                  -- Next funding time
    metadata JSONB,                               -- Additional funding data
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_funding_rates_exchange_symbol ON funding_rates(exchange, symbol);
CREATE INDEX idx_funding_rates_timestamp ON funding_rates(timestamp DESC);
CREATE INDEX idx_funding_rates_symbol_timestamp ON funding_rates(symbol, timestamp DESC);
CREATE INDEX idx_funding_rates_rate ON funding_rates(rate);

COMMENT ON TABLE funding_rates IS 'Funding rates for perpetual futures contracts';
COMMENT ON COLUMN funding_rates.rate IS 'Funding rate as decimal (0.0001 = 0.01%)';
COMMENT ON COLUMN funding_rates.predicted_rate IS 'Predicted rate for next funding period';


-- =====================================================
-- Table: open_interest
-- Open interest tracking for derivatives
-- =====================================================

CREATE TABLE IF NOT EXISTS open_interest (
    id VARCHAR(255) PRIMARY KEY,                 -- {exchange}_{symbol}_{timestamp}
    exchange VARCHAR(50) NOT NULL,                -- Exchange name
    symbol VARCHAR(50) NOT NULL,                  -- Contract symbol
    open_interest DECIMAL(20, 8) NOT NULL,        -- Open interest in contracts
    open_interest_usd DECIMAL(20, 2) NOT NULL,    -- Open interest in USD
    timestamp TIMESTAMP NOT NULL,                 -- Data timestamp
    metadata JSONB,                               -- Additional OI data
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_open_interest_exchange_symbol ON open_interest(exchange, symbol);
CREATE INDEX idx_open_interest_timestamp ON open_interest(timestamp DESC);
CREATE INDEX idx_open_interest_symbol_timestamp ON open_interest(symbol, timestamp DESC);
CREATE INDEX idx_open_interest_value ON open_interest(open_interest_usd DESC);

COMMENT ON TABLE open_interest IS 'Open interest tracking for futures and options';
COMMENT ON COLUMN open_interest.open_interest IS 'OI in number of contracts';
COMMENT ON COLUMN open_interest.open_interest_usd IS 'OI value in USD';


-- =====================================================
-- Optional: Add partitioning for large_trades (time-based)
-- Uncomment if table grows very large
-- =====================================================

-- CREATE TABLE large_trades_2024_q4 PARTITION OF large_trades
--     FOR VALUES FROM ('2024-10-01') TO ('2025-01-01');
-- 
-- CREATE TABLE large_trades_2025_q1 PARTITION OF large_trades
--     FOR VALUES FROM ('2025-01-01') TO ('2025-04-01');
