-- Goal-Oriented Trading Database Schema
-- Tracks financial goals, progress, and adjustments for adaptive position sizing

-- Financial Goals Table
-- Stores user-defined trading goals (monthly return %, profit $, portfolio target)
CREATE TABLE IF NOT EXISTS financial_goals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    goal_type VARCHAR(50) NOT NULL, -- 'monthly_return_pct', 'monthly_profit_usd', 'portfolio_target_usd'
    target_value DECIMAL(20, 6) NOT NULL, -- Target value (0.10 for 10%, 10000 for $10K, 1000000 for $1M)
    current_value DECIMAL(20, 6) DEFAULT 0, -- Current achieved value
    start_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    target_date TIMESTAMP WITH TIME ZONE, -- When goal should be achieved (NULL for ongoing)
    status VARCHAR(20) NOT NULL DEFAULT 'active', -- 'active', 'achieved', 'missed', 'paused'
    priority INTEGER DEFAULT 1, -- 1=highest priority
    risk_tolerance DECIMAL(5, 4) DEFAULT 0.02, -- Max risk per trade (2% default)
    max_drawdown_pct DECIMAL(5, 4) DEFAULT 0.15, -- Max acceptable drawdown (15% default)
    metadata JSONB DEFAULT '{}', -- Additional goal parameters
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    achieved_at TIMESTAMP WITH TIME ZONE, -- When goal was achieved
    CONSTRAINT valid_goal_type CHECK (goal_type IN ('monthly_return_pct', 'monthly_profit_usd', 'portfolio_target_usd')),
    CONSTRAINT valid_status CHECK (status IN ('active', 'achieved', 'missed', 'paused', 'archived')),
    CONSTRAINT valid_priority CHECK (priority >= 1 AND priority <= 10),
    CONSTRAINT positive_target CHECK (target_value > 0)
);

-- Goal Progress Tracking Table
-- Daily/hourly snapshots of progress towards each goal
CREATE TABLE IF NOT EXISTS goal_progress (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    goal_id UUID NOT NULL REFERENCES financial_goals(id) ON DELETE CASCADE,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    current_value DECIMAL(20, 6) NOT NULL, -- Current progress value
    progress_pct DECIMAL(6, 3) NOT NULL, -- Percentage towards goal (current/target * 100)
    portfolio_value DECIMAL(20, 6) NOT NULL, -- Total portfolio value at this time
    realized_pnl DECIMAL(20, 6) DEFAULT 0, -- Realized P&L for period
    unrealized_pnl DECIMAL(20, 6) DEFAULT 0, -- Unrealized P&L for period
    active_positions INTEGER DEFAULT 0, -- Number of active positions
    win_rate DECIMAL(5, 4), -- Win rate for period
    sharpe_ratio DECIMAL(10, 6), -- Risk-adjusted return metric
    days_remaining INTEGER, -- Days until target date (NULL for ongoing)
    required_daily_return DECIMAL(10, 6), -- Required daily return to reach goal
    on_track BOOLEAN DEFAULT TRUE, -- Whether currently on track to achieve goal
    metadata JSONB DEFAULT '{}', -- Additional metrics
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Goal Adjustments Table
-- Tracks automatic adjustments made to achieve goals
CREATE TABLE IF NOT EXISTS goal_adjustments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    goal_id UUID NOT NULL REFERENCES financial_goals(id) ON DELETE CASCADE,
    adjustment_type VARCHAR(50) NOT NULL, -- 'risk_increase', 'risk_decrease', 'position_size_up', 'position_size_down', 'strategy_change'
    reason VARCHAR(255) NOT NULL, -- Why adjustment was made
    previous_value DECIMAL(20, 6), -- Previous parameter value
    new_value DECIMAL(20, 6), -- New parameter value
    impact_expected DECIMAL(10, 6), -- Expected impact on goal achievement
    impact_actual DECIMAL(10, 6), -- Actual measured impact (updated later)
    applied_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    effective_until TIMESTAMP WITH TIME ZONE, -- When adjustment expires (NULL for permanent)
    status VARCHAR(20) DEFAULT 'active', -- 'active', 'expired', 'reverted'
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CONSTRAINT valid_adjustment_type CHECK (adjustment_type IN (
        'risk_increase', 'risk_decrease', 'position_size_up', 'position_size_down',
        'strategy_change', 'allocation_shift', 'leverage_increase', 'leverage_decrease'
    )),
    CONSTRAINT valid_status CHECK (status IN ('active', 'expired', 'reverted'))
);

-- Goal Milestones Table
-- Track intermediate milestones towards larger goals
CREATE TABLE IF NOT EXISTS goal_milestones (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    goal_id UUID NOT NULL REFERENCES financial_goals(id) ON DELETE CASCADE,
    milestone_name VARCHAR(100) NOT NULL, -- e.g., "First $1K profit", "10 consecutive wins"
    milestone_value DECIMAL(20, 6) NOT NULL, -- Threshold value
    achieved BOOLEAN DEFAULT FALSE,
    achieved_at TIMESTAMP WITH TIME ZONE,
    reward_action VARCHAR(100), -- Action to take when achieved (e.g., "increase_allocation")
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Position Sizing Recommendations Table
-- Stores calculated position sizes based on goal progress
CREATE TABLE IF NOT EXISTS position_sizing_recommendations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    goal_id UUID NOT NULL REFERENCES financial_goals(id) ON DELETE CASCADE,
    strategy_id UUID REFERENCES strategies(id) ON DELETE CASCADE,
    symbol VARCHAR(20) NOT NULL,
    recommended_size DECIMAL(20, 8) NOT NULL, -- Recommended position size in base currency
    recommended_allocation DECIMAL(5, 4) NOT NULL, -- % of portfolio to allocate
    risk_amount DECIMAL(20, 6) NOT NULL, -- Dollar risk for this position
    confidence_score DECIMAL(5, 4), -- Model confidence (0-1)
    reasoning TEXT, -- Why this size was recommended
    calculated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    valid_until TIMESTAMP WITH TIME ZONE DEFAULT NOW() + INTERVAL '1 hour',
    used BOOLEAN DEFAULT FALSE, -- Whether recommendation was used
    actual_size DECIMAL(20, 8), -- Actual position size taken (if used)
    outcome VARCHAR(20), -- 'win', 'loss', 'breakeven' (updated after close)
    pnl DECIMAL(20, 6), -- Actual P&L from position (updated after close)
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CONSTRAINT valid_outcome CHECK (outcome IS NULL OR outcome IN ('win', 'loss', 'breakeven', 'open'))
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_financial_goals_status ON financial_goals(status, priority);
CREATE INDEX IF NOT EXISTS idx_financial_goals_type ON financial_goals(goal_type, status);
CREATE INDEX IF NOT EXISTS idx_goal_progress_goal_timestamp ON goal_progress(goal_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_goal_progress_timestamp ON goal_progress(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_goal_adjustments_goal ON goal_adjustments(goal_id, applied_at DESC);
CREATE INDEX IF NOT EXISTS idx_goal_adjustments_status ON goal_adjustments(status, applied_at DESC);
CREATE INDEX IF NOT EXISTS idx_goal_milestones_goal ON goal_milestones(goal_id, achieved);
CREATE INDEX IF NOT EXISTS idx_position_sizing_goal_valid ON position_sizing_recommendations(goal_id, valid_until DESC);
CREATE INDEX IF NOT EXISTS idx_position_sizing_used ON position_sizing_recommendations(used, calculated_at DESC);

-- Insert default goals: 10% monthly return, $10K monthly profit, $1M portfolio target
INSERT INTO financial_goals (goal_type, target_value, priority, risk_tolerance, max_drawdown_pct, metadata)
VALUES 
    ('monthly_return_pct', 0.10, 1, 0.02, 0.15, '{"description": "Achieve 10% monthly return", "aggressive_mode": false}'),
    ('monthly_profit_usd', 10000.00, 2, 0.02, 0.15, '{"description": "Generate $10,000 monthly profit", "compounding": true}'),
    ('portfolio_target_usd', 1000000.00, 3, 0.02, 0.15, '{"description": "Reach $1 million portfolio value", "timeline_months": 24}')
ON CONFLICT DO NOTHING;

-- Create view for current goal status
CREATE OR REPLACE VIEW v_current_goal_status AS
SELECT 
    g.id,
    g.goal_type,
    g.target_value,
    g.current_value,
    (g.current_value / NULLIF(g.target_value, 0) * 100) AS progress_pct,
    g.status,
    g.priority,
    g.risk_tolerance,
    g.max_drawdown_pct,
    COALESCE(gp.portfolio_value, 0) AS latest_portfolio_value,
    COALESCE(gp.realized_pnl, 0) AS latest_realized_pnl,
    COALESCE(gp.unrealized_pnl, 0) AS latest_unrealized_pnl,
    COALESCE(gp.win_rate, 0) AS latest_win_rate,
    COALESCE(gp.sharpe_ratio, 0) AS latest_sharpe_ratio,
    COALESCE(gp.on_track, TRUE) AS on_track,
    COALESCE(gp.required_daily_return, 0) AS required_daily_return,
    g.start_date,
    g.target_date,
    EXTRACT(EPOCH FROM (COALESCE(g.target_date, NOW() + INTERVAL '1 year') - NOW())) / 86400 AS days_remaining,
    g.created_at,
    g.updated_at
FROM financial_goals g
LEFT JOIN LATERAL (
    SELECT *
    FROM goal_progress
    WHERE goal_id = g.id
    ORDER BY timestamp DESC
    LIMIT 1
) gp ON TRUE
WHERE g.status = 'active'
ORDER BY g.priority, g.created_at;

COMMENT ON TABLE financial_goals IS 'User-defined financial trading goals with targets and constraints';
COMMENT ON TABLE goal_progress IS 'Time-series tracking of progress towards each financial goal';
COMMENT ON TABLE goal_adjustments IS 'Automatic adjustments made to trading parameters to achieve goals';
COMMENT ON TABLE goal_milestones IS 'Intermediate milestones towards achieving larger goals';
COMMENT ON TABLE position_sizing_recommendations IS 'AI-calculated position sizes optimized for goal achievement';
COMMENT ON VIEW v_current_goal_status IS 'Real-time view of all active goals with latest metrics';
