-- Migration: Add collector_metrics table for tracking collector performance metrics over time
-- Date: 2025-11-11
-- Description: Stores time-series metrics for data collectors (response times, success rates, etc.)

CREATE TABLE IF NOT EXISTS collector_metrics (
    id SERIAL PRIMARY KEY,
    collector_name VARCHAR(100) NOT NULL,
    metric_name VARCHAR(50),
    metric_value DECIMAL(20,4),
    timestamp TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Index for efficient time-series queries by collector
CREATE INDEX IF NOT EXISTS idx_collector_metrics ON collector_metrics(collector_name, timestamp DESC);

-- Index for querying specific metrics
CREATE INDEX IF NOT EXISTS idx_collector_metric_name ON collector_metrics(collector_name, metric_name, timestamp DESC);

-- Comment on table
COMMENT ON TABLE collector_metrics IS 'Time-series metrics for data collector performance monitoring';
COMMENT ON COLUMN collector_metrics.collector_name IS 'Name of the data collector (e.g., historical_data, sentiment, onchain)';
COMMENT ON COLUMN collector_metrics.metric_name IS 'Type of metric (e.g., response_time_ms, success_rate, api_calls_per_min)';
COMMENT ON COLUMN collector_metrics.metric_value IS 'Numeric value of the metric';
COMMENT ON COLUMN collector_metrics.timestamp IS 'Time when the metric was recorded';
