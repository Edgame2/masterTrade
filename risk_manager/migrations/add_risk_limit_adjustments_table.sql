-- Migration: Add Risk Limit Adjustments Table
-- Created: November 11, 2025
-- Purpose: Track adaptive risk limit adjustments for audit trail

-- Create risk_limit_adjustments table
CREATE TABLE IF NOT EXISTS risk_limit_adjustments (
    id SERIAL PRIMARY KEY,
    stance VARCHAR(20) NOT NULL,  -- protective, conservative, balanced, moderate, aggressive
    risk_limit_percent DECIMAL(5,2) NOT NULL,  -- Adjusted risk limit percentage
    base_limit_percent DECIMAL(5,2) NOT NULL,  -- Base risk limit (usually 10.0)
    adjustment_factor DECIMAL(5,3) NOT NULL,   -- Multiplier applied
    reason TEXT NOT NULL,                       -- Human-readable reason
    goal_progress TEXT,                          -- JSON string of goal progress
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create index for time-based queries
CREATE INDEX idx_risk_adjustments_created ON risk_limit_adjustments(created_at DESC);

-- Create index for stance queries
CREATE INDEX idx_risk_adjustments_stance ON risk_limit_adjustments(stance, created_at DESC);

-- Add comment
COMMENT ON TABLE risk_limit_adjustments IS 'Audit trail of adaptive risk limit adjustments based on goal progress';
COMMENT ON COLUMN risk_limit_adjustments.stance IS 'Risk management stance: protective, conservative, balanced, moderate, aggressive';
COMMENT ON COLUMN risk_limit_adjustments.risk_limit_percent IS 'Calculated portfolio risk limit percentage (3-15%)';
COMMENT ON COLUMN risk_limit_adjustments.adjustment_factor IS 'Multiplier applied to base limit (0.3 to 1.5)';
COMMENT ON COLUMN risk_limit_adjustments.goal_progress IS 'Snapshot of goal progress at time of adjustment';
