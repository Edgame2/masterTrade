"""
Database Optimization & Archival System

Comprehensive database performance optimization with intelligent archival,
data compression, and high-performance querying capabilities for MasterTrade.
"""

from .archival_manager import (
    ArchivalManager,
    ArchivalPolicy,
    ArchivalRule,
    CompressionType,
    ArchivalStatus
)

from .query_optimizer import (
    QueryOptimizer,
    QueryAnalyzer,
    IndexManager,
    QueryPlan,
    OptimizationStrategy
)

from .performance_monitor import (
    PerformanceMonitor,
    DatabaseMetrics,
    SlowQueryAnalyzer,
    ConnectionPoolMonitor,
    PerformanceThreshold
)

from .data_partitioner import (
    DataPartitioner,
    PartitioningStrategy,
    PartitionConfig,
    TimeBasedPartitioner,
    HashBasedPartitioner
)

from .compression_engine import (
    CompressionEngine,
    CompressionResult,
    CompressionAlgorithm,
    DataCompressor
)

from .cache_manager import (
    CacheManager,
    CachePolicy,
    CacheEntry,
    DistributedCache,
    QueryCache
)

__version__ = "1.0.0"
__author__ = "MasterTrade Development Team"

# Export all components
__all__ = [
    # Archival Management
    "ArchivalManager",
    "ArchivalPolicy", 
    "ArchivalRule",
    "CompressionType",
    "ArchivalStatus",
    
    # Query Optimization
    "QueryOptimizer",
    "QueryAnalyzer",
    "IndexManager",
    "QueryPlan",
    "OptimizationStrategy",
    
    # Performance Monitoring
    "PerformanceMonitor",
    "DatabaseMetrics",
    "SlowQueryAnalyzer", 
    "ConnectionPoolMonitor",
    "PerformanceThreshold",
    
    # Data Partitioning
    "DataPartitioner",
    "PartitioningStrategy",
    "PartitionConfig",
    "TimeBasedPartitioner",
    "HashBasedPartitioner",
    
    # Compression
    "CompressionEngine",
    "CompressionResult",
    "CompressionAlgorithm", 
    "DataCompressor",
    
    # Caching
    "CacheManager",
    "CachePolicy",
    "CacheEntry",
    "DistributedCache",
    "QueryCache"
]

# Module configuration
DEFAULT_CONFIG = {
    "archival": {
        "enabled": True,
        "default_retention_days": 365,
        "compression_threshold_mb": 100,
        "archive_frequency_hours": 24
    },
    
    "query_optimization": {
        "enabled": True,
        "auto_index_creation": True,
        "query_analysis_threshold_ms": 1000,
        "optimization_interval_hours": 6
    },
    
    "performance_monitoring": {
        "enabled": True,
        "metrics_collection_interval_seconds": 30,
        "slow_query_threshold_ms": 5000,
        "alert_thresholds": {
            "cpu_usage_percent": 80,
            "memory_usage_percent": 85,
            "connection_pool_usage_percent": 90
        }
    },
    
    "partitioning": {
        "enabled": True,
        "default_strategy": "time_based",
        "partition_size_mb": 1000,
        "auto_partition_creation": True
    },
    
    "compression": {
        "enabled": True,
        "default_algorithm": "lz4",
        "compression_level": 6,
        "parallel_compression": True
    },
    
    "caching": {
        "enabled": True,
        "default_ttl_seconds": 3600,
        "max_cache_size_mb": 512,
        "cache_eviction_policy": "lru"
    }
}

def get_config():
    """Get default configuration for database optimization system"""
    return DEFAULT_CONFIG.copy()

def validate_config(config: dict) -> bool:
    """Validate configuration dictionary"""
    required_sections = [
        "archival", "query_optimization", "performance_monitoring",
        "partitioning", "compression", "caching"
    ]
    
    for section in required_sections:
        if section not in config:
            return False
    
    return True