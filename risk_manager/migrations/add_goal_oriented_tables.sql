-- Goal-Oriented Trading System Database Schema
-- This migration adds tables for tracking financial goals and position sizing adjustments

-- Financial goals configuration table
CREATE TABLE IF NOT EXISTS financial_goals (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    goal_type VARCHAR(50) UNIQUE NOT NULL, -- monthly_return, monthly_income, portfolio_value
    target_value DECIMAL(20,2) NOT NULL,
    current_value DECIMAL(20,2) DEFAULT 0,
    progress_percent DECIMAL(5,2) DEFAULT 0,
    target_date DATE,
    status VARCHAR(20) DEFAULT 'on_track', -- on_track, at_risk, behind, achieved
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_financial_goals_type ON financial_goals(goal_type);
CREATE INDEX IF NOT EXISTS idx_financial_goals_status ON financial_goals(status);

-- Goal progress history for tracking over time
CREATE TABLE IF NOT EXISTS goal_progress_history (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    goal_id UUID REFERENCES financial_goals(id) ON DELETE CASCADE,
    snapshot_date DATE NOT NULL,
    actual_value DECIMAL(20,2) NOT NULL,
    target_value DECIMAL(20,2) NOT NULL,
    variance_percent DECIMAL(5,2),
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(goal_id, snapshot_date)
);

CREATE INDEX IF NOT EXISTS idx_goal_history_date ON goal_progress_history(goal_id, snapshot_date DESC);

-- Goal adjustment log for audit trail
CREATE TABLE IF NOT EXISTS goal_adjustment_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
    portfolio_value DECIMAL(20,2) NOT NULL,
    adjustment_factor DECIMAL(5,4) NOT NULL,
    reason TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_goal_adjustment_timestamp ON goal_adjustment_log(timestamp DESC);

-- Portfolio positions table (if not exists)
CREATE TABLE IF NOT EXISTS portfolio_positions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    symbol VARCHAR(20) NOT NULL,
    quantity DECIMAL(20,8) NOT NULL,
    entry_price DECIMAL(20,8) NOT NULL,
    current_price DECIMAL(20,8),
    current_value DECIMAL(20,2),
    unrealized_pnl DECIMAL(20,2),
    status VARCHAR(20) DEFAULT 'open', -- open, closed
    opened_at TIMESTAMP NOT NULL DEFAULT NOW(),
    closed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_portfolio_positions_symbol ON portfolio_positions(symbol);
CREATE INDEX IF NOT EXISTS idx_portfolio_positions_status ON portfolio_positions(status);

-- Trades table for realized P&L tracking (if not exists)
CREATE TABLE IF NOT EXISTS trades (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    symbol VARCHAR(20) NOT NULL,
    strategy_id VARCHAR(100),
    entry_price DECIMAL(20,8) NOT NULL,
    exit_price DECIMAL(20,8),
    quantity DECIMAL(20,8) NOT NULL,
    realized_pnl DECIMAL(20,2),
    entry_timestamp TIMESTAMP NOT NULL,
    exit_timestamp TIMESTAMP,
    status VARCHAR(20) DEFAULT 'open', -- open, closed
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_trades_exit_timestamp ON trades(exit_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_trades_realized_pnl ON trades(realized_pnl DESC) WHERE realized_pnl IS NOT NULL;

-- Insert default financial goals
INSERT INTO financial_goals (goal_type, target_value, target_date, status)
VALUES 
    ('monthly_return', 10.0, NULL, 'on_track'),  -- 10% monthly return
    ('monthly_income', 4000.0, NULL, 'on_track'),  -- €4,000 monthly income
    ('portfolio_value', 1000000.0, NULL, 'on_track')  -- €1M portfolio target
ON CONFLICT (goal_type) DO NOTHING;

-- Create function to automatically update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create triggers for updated_at columns
DROP TRIGGER IF EXISTS update_financial_goals_updated_at ON financial_goals;
CREATE TRIGGER update_financial_goals_updated_at
    BEFORE UPDATE ON financial_goals
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_portfolio_positions_updated_at ON portfolio_positions;
CREATE TRIGGER update_portfolio_positions_updated_at
    BEFORE UPDATE ON portfolio_positions
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_trades_updated_at ON trades;
CREATE TRIGGER update_trades_updated_at
    BEFORE UPDATE ON trades
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Grant permissions (adjust role name as needed)
-- GRANT ALL ON financial_goals TO mastertrade_user;
-- GRANT ALL ON goal_progress_history TO mastertrade_user;
-- GRANT ALL ON goal_adjustment_log TO mastertrade_user;
-- GRANT ALL ON portfolio_positions TO mastertrade_user;
-- GRANT ALL ON trades TO mastertrade_user;
