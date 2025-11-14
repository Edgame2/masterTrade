-- Migration to fix schema issues identified by test suite
-- Date: 2025-11-14
-- Issues fixed:
--   1. Add 'state' column to strategies (alias for status)
--   2. Add 'performance_metrics' column to strategies
--   3. Add missing columns to learning_insights
--   4. Add missing columns to trades table
--   5. Create positions table
--   6. Create on_chain_data table

-- ============================================================================
-- 1. Add state column to strategies (computed column based on status)
-- ============================================================================
ALTER TABLE strategies ADD COLUMN IF NOT EXISTS state TEXT;

-- Update state to match status initially
UPDATE strategies SET state = status WHERE state IS NULL;

-- Create trigger to keep state in sync with status
CREATE OR REPLACE FUNCTION sync_strategy_state()
RETURNS TRIGGER AS $$
BEGIN
    NEW.state := NEW.status;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_sync_strategy_state ON strategies;
CREATE TRIGGER trigger_sync_strategy_state
    BEFORE INSERT OR UPDATE ON strategies
    FOR EACH ROW
    EXECUTE FUNCTION sync_strategy_state();

-- ============================================================================
-- 2. Add performance_metrics column to strategies
-- ============================================================================
ALTER TABLE strategies ADD COLUMN IF NOT EXISTS performance_metrics JSONB DEFAULT '{}'::JSONB;

COMMENT ON COLUMN strategies.performance_metrics IS 'Real-time performance metrics including sharpe_ratio, total_return, win_rate, etc.';

-- ============================================================================
-- 3. Fix learning_insights table schema
-- ============================================================================
-- Add missing columns
ALTER TABLE learning_insights ADD COLUMN IF NOT EXISTS generation INTEGER;
ALTER TABLE learning_insights ADD COLUMN IF NOT EXISTS data JSONB DEFAULT '{}'::JSONB;

-- Update existing records if needed
UPDATE learning_insights SET generation = 0 WHERE generation IS NULL;
UPDATE learning_insights SET data = '{}'::JSONB WHERE data IS NULL;

-- Add index on generation for faster queries
CREATE INDEX IF NOT EXISTS idx_learning_insights_generation ON learning_insights(generation);

COMMENT ON COLUMN learning_insights.generation IS 'Strategy generation number for genetic algorithm tracking';
COMMENT ON COLUMN learning_insights.data IS 'Detailed insight data including patterns, correlations, and metrics';

-- ============================================================================
-- 4. Fix trades table - add missing columns
-- ============================================================================
ALTER TABLE trades ADD COLUMN IF NOT EXISTS strategy_id INTEGER;
ALTER TABLE trades ADD COLUMN IF NOT EXISTS executed_at TIMESTAMPTZ DEFAULT NOW();
ALTER TABLE trades ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'filled';
ALTER TABLE trades ADD COLUMN IF NOT EXISTS executed_quantity NUMERIC(20,8);
ALTER TABLE trades ADD COLUMN IF NOT EXISTS executed_price NUMERIC(20,8);

-- Migrate existing data
UPDATE trades SET executed_quantity = quantity WHERE executed_quantity IS NULL;
UPDATE trades SET executed_price = price WHERE executed_price IS NULL;
UPDATE trades SET executed_at = trade_time WHERE executed_at IS NULL;

-- Add indexes for performance
CREATE INDEX IF NOT EXISTS idx_trades_strategy_id ON trades(strategy_id);
CREATE INDEX IF NOT EXISTS idx_trades_executed_at ON trades(executed_at DESC);
CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status);

COMMENT ON COLUMN trades.strategy_id IS 'Reference to the strategy that generated this trade';
COMMENT ON COLUMN trades.executed_at IS 'Timestamp when the trade was executed';
COMMENT ON COLUMN trades.status IS 'Trade status: filled, partially_filled, cancelled';
COMMENT ON COLUMN trades.executed_quantity IS 'Quantity that was actually executed';
COMMENT ON COLUMN trades.executed_price IS 'Actual execution price';

-- ============================================================================
-- 5. Create positions table
-- ============================================================================
CREATE TABLE IF NOT EXISTS positions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    strategy_id INTEGER NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL CHECK (side IN ('long', 'short', 'neutral')),
    quantity NUMERIC(20, 8) NOT NULL,
    entry_price NUMERIC(20, 8),
    current_price NUMERIC(20, 8),
    unrealized_pnl NUMERIC(20, 8) DEFAULT 0,
    realized_pnl NUMERIC(20, 8) DEFAULT 0,
    fees NUMERIC(20, 8) DEFAULT 0,
    status VARCHAR(20) DEFAULT 'open' CHECK (status IN ('open', 'closed', 'partial')),
    environment VARCHAR(20) DEFAULT 'paper' CHECK (environment IN ('paper', 'testnet', 'live')),
    metadata JSONB DEFAULT '{}'::JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    closed_at TIMESTAMPTZ
);

-- Add indexes for positions
CREATE INDEX IF NOT EXISTS idx_positions_strategy_id ON positions(strategy_id);
CREATE INDEX IF NOT EXISTS idx_positions_symbol ON positions(symbol);
CREATE INDEX IF NOT EXISTS idx_positions_status ON positions(status);
CREATE INDEX IF NOT EXISTS idx_positions_created_at ON positions(created_at DESC);

-- Add comments
COMMENT ON TABLE positions IS 'Active and historical trading positions for all strategies';
COMMENT ON COLUMN positions.strategy_id IS 'Reference to the strategy holding this position';
COMMENT ON COLUMN positions.symbol IS 'Trading pair symbol (e.g., BTCUSDC)';
COMMENT ON COLUMN positions.side IS 'Position direction: long, short, or neutral';
COMMENT ON COLUMN positions.quantity IS 'Position size in base asset';
COMMENT ON COLUMN positions.entry_price IS 'Average entry price';
COMMENT ON COLUMN positions.current_price IS 'Current market price (updated real-time)';
COMMENT ON COLUMN positions.unrealized_pnl IS 'Unrealized profit/loss';
COMMENT ON COLUMN positions.realized_pnl IS 'Realized profit/loss from partial closes';
COMMENT ON COLUMN positions.environment IS 'Trading environment: paper, testnet, or live';

-- ============================================================================
-- 6. Create on_chain_data table (optional but expected by tests)
-- ============================================================================
CREATE TABLE IF NOT EXISTS on_chain_data (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    metric_type VARCHAR(50) NOT NULL,
    metric_value NUMERIC,
    metadata JSONB DEFAULT '{}'::JSONB,
    source VARCHAR(50),
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Add indexes for on_chain_data
CREATE INDEX IF NOT EXISTS idx_on_chain_data_symbol ON on_chain_data(symbol);
CREATE INDEX IF NOT EXISTS idx_on_chain_data_metric_type ON on_chain_data(metric_type);
CREATE INDEX IF NOT EXISTS idx_on_chain_data_timestamp ON on_chain_data(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_on_chain_data_symbol_timestamp ON on_chain_data(symbol, timestamp DESC);

-- Add comments
COMMENT ON TABLE on_chain_data IS 'On-chain metrics from Glassnode, Moralis, etc.';
COMMENT ON COLUMN on_chain_data.metric_type IS 'Type of metric: active_addresses, transaction_volume, whale_transfers, etc.';
COMMENT ON COLUMN on_chain_data.source IS 'Data source: glassnode, moralis, etc.';

-- ============================================================================
-- 7. Verify and report
-- ============================================================================

-- Create a verification view
CREATE OR REPLACE VIEW schema_verification AS
SELECT
    'strategies.state' AS column_name,
    EXISTS(SELECT 1 FROM information_schema.columns WHERE table_name='strategies' AND column_name='state') AS exists
UNION ALL
SELECT
    'strategies.performance_metrics',
    EXISTS(SELECT 1 FROM information_schema.columns WHERE table_name='strategies' AND column_name='performance_metrics')
UNION ALL
SELECT
    'learning_insights.generation',
    EXISTS(SELECT 1 FROM information_schema.columns WHERE table_name='learning_insights' AND column_name='generation')
UNION ALL
SELECT
    'learning_insights.data',
    EXISTS(SELECT 1 FROM information_schema.columns WHERE table_name='learning_insights' AND column_name='data')
UNION ALL
SELECT
    'trades.strategy_id',
    EXISTS(SELECT 1 FROM information_schema.columns WHERE table_name='trades' AND column_name='strategy_id')
UNION ALL
SELECT
    'trades.executed_at',
    EXISTS(SELECT 1 FROM information_schema.columns WHERE table_name='trades' AND column_name='executed_at')
UNION ALL
SELECT
    'trades.status',
    EXISTS(SELECT 1 FROM information_schema.columns WHERE table_name='trades' AND column_name='status')
UNION ALL
SELECT
    'trades.executed_quantity',
    EXISTS(SELECT 1 FROM information_schema.columns WHERE table_name='trades' AND column_name='executed_quantity')
UNION ALL
SELECT
    'trades.executed_price',
    EXISTS(SELECT 1 FROM information_schema.columns WHERE table_name='trades' AND column_name='executed_price')
UNION ALL
SELECT
    'positions table',
    EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name='positions')
UNION ALL
SELECT
    'on_chain_data table',
    EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name='on_chain_data');

-- Display results
SELECT * FROM schema_verification ORDER BY column_name;

-- Summary
DO $$
DECLARE
    missing_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO missing_count
    FROM schema_verification
    WHERE exists = false;
    
    IF missing_count = 0 THEN
        RAISE NOTICE '✅ All schema fixes applied successfully!';
    ELSE
        RAISE NOTICE '⚠️  % schema issues still remain', missing_count;
    END IF;
END $$;
