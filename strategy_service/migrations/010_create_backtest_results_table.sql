-- Migration: Create backtest_results table
-- Purpose: Store strategy backtest results for learning and optimization
-- Date: 2025-11-12

-- Drop table if exists (for development/testing)
DROP TABLE IF EXISTS backtest_results CASCADE;

-- Create backtest_results table
CREATE TABLE backtest_results (
    id SERIAL PRIMARY KEY,
    strategy_id UUID NOT NULL,
    backtest_id VARCHAR(100),
    metrics JSONB NOT NULL DEFAULT '{}',
    parameters JSONB NOT NULL DEFAULT '{}',
    period_start TIMESTAMPTZ,
    period_end TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create indexes for efficient queries
CREATE INDEX idx_backtest_results_strategy_id ON backtest_results(strategy_id);
CREATE INDEX idx_backtest_results_created_at ON backtest_results(created_at DESC);
CREATE INDEX idx_backtest_results_backtest_id ON backtest_results(backtest_id);

-- Create GIN index for JSONB metrics queries (allows fast JSON queries)
CREATE INDEX idx_backtest_results_metrics ON backtest_results USING GIN (metrics);

-- Create partial index for high-performing strategies (Sharpe > 1.0)
CREATE INDEX idx_backtest_results_high_sharpe ON backtest_results((metrics->>'sharpe_ratio'))
    WHERE (metrics->>'sharpe_ratio')::float > 1.0;

-- Add foreign key constraint to strategies table
ALTER TABLE backtest_results 
    ADD CONSTRAINT fk_backtest_results_strategy 
    FOREIGN KEY (strategy_id) 
    REFERENCES strategies(id) 
    ON DELETE CASCADE;

-- Create trigger for updated_at timestamp
CREATE OR REPLACE FUNCTION update_backtest_results_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_backtest_results_timestamp
    BEFORE UPDATE ON backtest_results
    FOR EACH ROW
    EXECUTE FUNCTION update_backtest_results_updated_at();

-- Add comments for documentation
COMMENT ON TABLE backtest_results IS 'Stores strategy backtest results for learning and optimization';
COMMENT ON COLUMN backtest_results.strategy_id IS 'Foreign key to strategies table';
COMMENT ON COLUMN backtest_results.backtest_id IS 'Unique identifier for this backtest run';
COMMENT ON COLUMN backtest_results.metrics IS 'JSONB containing performance metrics (sharpe_ratio, win_rate, max_drawdown, etc.)';
COMMENT ON COLUMN backtest_results.parameters IS 'JSONB containing strategy parameters used in backtest';
COMMENT ON COLUMN backtest_results.period_start IS 'Start date of backtest period';
COMMENT ON COLUMN backtest_results.period_end IS 'End date of backtest period';

-- Example metrics structure:
-- {
--   "sharpe_ratio": 1.5,
--   "sortino_ratio": 1.8,
--   "cagr": 0.25,
--   "max_drawdown": -0.15,
--   "win_rate": 0.55,
--   "profit_factor": 1.8,
--   "total_trades": 150,
--   "avg_trade_duration_hours": 48.5,
--   "total_return_pct": 45.2,
--   "monthly_returns": [...]
-- }

-- Grant permissions
GRANT SELECT, INSERT, UPDATE, DELETE ON backtest_results TO mastertrade;
GRANT USAGE, SELECT ON SEQUENCE backtest_results_id_seq TO mastertrade;
