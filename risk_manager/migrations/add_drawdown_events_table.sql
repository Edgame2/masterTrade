-- Migration: Add drawdown_events table for tracking drawdown breaches
-- Date: 2025-11-11
-- Description: Logs all drawdown protection events including breaches and actions taken

CREATE TABLE IF NOT EXISTS drawdown_events (
    id SERIAL PRIMARY KEY,
    stance VARCHAR(20) NOT NULL,  -- normal, protective, breached
    monthly_limit_percent DECIMAL(5,2) NOT NULL,
    actual_drawdown_percent DECIMAL(5,2) NOT NULL,
    portfolio_value DECIMAL(20,2) NOT NULL,
    peak_value DECIMAL(20,2) NOT NULL,
    actions_taken TEXT NOT NULL,  -- Comma-separated list of actions
    reason TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Index for querying recent events
CREATE INDEX IF NOT EXISTS idx_drawdown_events_created ON drawdown_events(created_at DESC);

-- Index for querying by stance
CREATE INDEX IF NOT EXISTS idx_drawdown_events_stance ON drawdown_events(stance, created_at DESC);

-- Comments
COMMENT ON TABLE drawdown_events IS 'Audit log of all drawdown protection events and breaches';
COMMENT ON COLUMN drawdown_events.stance IS 'Protection stance at time of event (normal, protective, breached)';
COMMENT ON COLUMN drawdown_events.monthly_limit_percent IS 'Monthly drawdown limit that was in effect';
COMMENT ON COLUMN drawdown_events.actual_drawdown_percent IS 'Actual monthly drawdown percentage at time of event';
COMMENT ON COLUMN drawdown_events.portfolio_value IS 'Portfolio value at time of event';
COMMENT ON COLUMN drawdown_events.peak_value IS 'Monthly peak portfolio value';
COMMENT ON COLUMN drawdown_events.actions_taken IS 'Actions triggered by event (pause_new, reduce_positions, close_all)';
COMMENT ON COLUMN drawdown_events.reason IS 'Human-readable explanation of the event';
