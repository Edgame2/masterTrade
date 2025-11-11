-- Migration: Create feature store tables for ML feature management
-- Date: 2025-11-11
-- Description: PostgreSQL-based feature store for ML model features

-- Feature definitions table
CREATE TABLE IF NOT EXISTS feature_definitions (
    id SERIAL PRIMARY KEY,
    feature_name VARCHAR(100) UNIQUE NOT NULL,
    feature_type VARCHAR(50) NOT NULL,  -- technical, onchain, social, macro, composite
    description TEXT,
    data_sources TEXT[],  -- Array of data source names
    computation_logic TEXT,  -- Description or code for computing the feature
    version INT DEFAULT 1,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Index for active features lookup
CREATE INDEX IF NOT EXISTS idx_feature_definitions_active ON feature_definitions(is_active, feature_type);

-- Index for feature name lookup
CREATE INDEX IF NOT EXISTS idx_feature_definitions_name ON feature_definitions(feature_name) WHERE is_active = TRUE;

-- Feature values table (time-series storage)
CREATE TABLE IF NOT EXISTS feature_values (
    id BIGSERIAL PRIMARY KEY,
    feature_id INT NOT NULL REFERENCES feature_definitions(id) ON DELETE CASCADE,
    symbol VARCHAR(20) NOT NULL,
    value DECIMAL(20,8),
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(feature_id, symbol, timestamp)
);

-- Index for time-series queries
CREATE INDEX IF NOT EXISTS idx_feature_values_lookup ON feature_values(feature_id, symbol, timestamp DESC);

-- Index for symbol-based queries
CREATE INDEX IF NOT EXISTS idx_feature_values_symbol ON feature_values(symbol, timestamp DESC);

-- Index for recent features (simplified without NOW() function)
CREATE INDEX IF NOT EXISTS idx_feature_values_recent ON feature_values(timestamp DESC);

-- Feature metadata table (for storing additional context)
CREATE TABLE IF NOT EXISTS feature_metadata (
    id SERIAL PRIMARY KEY,
    feature_id INT NOT NULL REFERENCES feature_definitions(id) ON DELETE CASCADE,
    metadata_key VARCHAR(100) NOT NULL,
    metadata_value TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(feature_id, metadata_key)
);

-- Index for metadata lookup
CREATE INDEX IF NOT EXISTS idx_feature_metadata_lookup ON feature_metadata(feature_id, metadata_key);

-- Comments for documentation
COMMENT ON TABLE feature_definitions IS 'Registry of all ML features with their definitions and computation logic';
COMMENT ON TABLE feature_values IS 'Time-series storage of computed feature values for each symbol';
COMMENT ON TABLE feature_metadata IS 'Additional metadata and configuration for features';

COMMENT ON COLUMN feature_definitions.feature_name IS 'Unique identifier for the feature (e.g., rsi_14, nvt_ratio)';
COMMENT ON COLUMN feature_definitions.feature_type IS 'Category: technical, onchain, social, macro, composite';
COMMENT ON COLUMN feature_definitions.data_sources IS 'Array of source services (market_data, onchain, social, etc.)';
COMMENT ON COLUMN feature_definitions.computation_logic IS 'Description of how the feature is computed';
COMMENT ON COLUMN feature_definitions.version IS 'Version number for feature definition changes';

COMMENT ON COLUMN feature_values.feature_id IS 'Reference to feature definition';
COMMENT ON COLUMN feature_values.symbol IS 'Trading symbol (e.g., BTCUSDT)';
COMMENT ON COLUMN feature_values.value IS 'Computed feature value at this timestamp';
COMMENT ON COLUMN feature_values.timestamp IS 'Time when the feature value was computed';
