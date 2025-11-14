-- Migration: Add DeFi Protocol Metrics Table
-- Created: 2025-11-14
-- Description: Store DeFi protocol metrics (TVL, volume, fees, etc.) from TheGraph and Dune Analytics

-- Create defi_protocol_metrics table
CREATE TABLE IF NOT EXISTS defi_protocol_metrics (
    id VARCHAR(255) PRIMARY KEY,
    partition_key VARCHAR(50) NOT NULL,  -- category (dex, lending, staking, etc.)
    data JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Create indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_defi_protocol_metrics_partition 
    ON defi_protocol_metrics(partition_key);
    
CREATE INDEX IF NOT EXISTS idx_defi_protocol_metrics_protocol 
    ON defi_protocol_metrics((data->>'protocol'));
    
CREATE INDEX IF NOT EXISTS idx_defi_protocol_metrics_timestamp 
    ON defi_protocol_metrics((data->>'timestamp'));
    
CREATE INDEX IF NOT EXISTS idx_defi_protocol_metrics_created 
    ON defi_protocol_metrics(created_at DESC);

-- Create GIN index for JSONB data queries
CREATE INDEX IF NOT EXISTS idx_defi_protocol_metrics_data 
    ON defi_protocol_metrics USING GIN(data);

COMMENT ON TABLE defi_protocol_metrics IS 'DeFi protocol metrics collected from TheGraph and Dune Analytics';
COMMENT ON COLUMN defi_protocol_metrics.id IS 'Unique identifier: defi_{protocol}_{timestamp}';
COMMENT ON COLUMN defi_protocol_metrics.partition_key IS 'Protocol category: dex, lending, staking, stablecoin';
COMMENT ON COLUMN defi_protocol_metrics.data IS 'JSONB containing protocol, tvl_usd, volume_usd, fees_usd, and other metrics';
