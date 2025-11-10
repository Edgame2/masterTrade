"""
API Rate Limiting & Caching System

Production-grade rate limiting and caching implementation for masterTrade platform
with Redis-based distributed management and comprehensive performance optimization.
"""

from .rate_limiter import (
    RateLimiter,
    RateLimitRule,
    RateLimitType,
    RateLimitStatus,
    RateLimitException,
    TokenBucket,
    SlidingWindow,
    FixedWindow,
    LeakyBucket
)

from .cache_manager import (
    CacheManager,
    CacheStrategy,
    CacheEntry,
    CacheStats,
    TTLCache,
    LRUCache,
    LFUCache,
    FIFOCache
)

from .api_middleware import (
    RateLimitMiddleware,
    CacheMiddleware,
    CompressionMiddleware,
    APISecurityMiddleware
)

from .performance_optimizer import (
    PerformanceOptimizer,
    RequestOptimizer,
    ResponseOptimizer,
    BatchProcessor
)

from .monitoring import (
    RateLimitMonitor,
    CacheMonitor,
    PerformanceMonitor,
    AlertManager
)

__version__ = "1.0.0"

# Default configuration for rate limiting and caching
DEFAULT_CONFIG = {
    "rate_limiting": {
        "enabled": True,
        "default_rules": [
            {
                "name": "general_api",
                "limit_type": "token_bucket",
                "requests_per_second": 100,
                "burst_size": 200,
                "window_size": 60,
                "paths": ["/*"],
                "methods": ["GET", "POST", "PUT", "DELETE"]
            },
            {
                "name": "market_data",
                "limit_type": "sliding_window", 
                "requests_per_second": 500,
                "burst_size": 1000,
                "window_size": 60,
                "paths": ["/api/v1/market/*"],
                "methods": ["GET"]
            },
            {
                "name": "trading_operations",
                "limit_type": "fixed_window",
                "requests_per_second": 50,
                "burst_size": 100,
                "window_size": 60,
                "paths": ["/api/v1/orders/*", "/api/v1/portfolio/*"],
                "methods": ["POST", "PUT", "DELETE"]
            }
        ],
        "redis_config": {
            "host": "localhost",
            "port": 6379,
            "db": 0,
            "password": None,
            "socket_timeout": 5,
            "socket_connect_timeout": 5,
            "retry_on_timeout": True,
            "health_check_interval": 30,
            "connection_pool": {
                "max_connections": 20,
                "retry_on_timeout": True
            }
        },
        "monitoring": {
            "enabled": True,
            "metrics_retention_days": 7,
            "alert_thresholds": {
                "high_rejection_rate": 0.1,
                "high_latency": 1000,
                "redis_connection_failure": 0.05
            }
        }
    },
    
    "caching": {
        "enabled": True,
        "default_strategy": "lru",
        "max_memory_mb": 512,
        "compression_enabled": True,
        "compression_threshold": 1024,
        "default_ttl": 300,
        "cache_strategies": {
            "market_data": {
                "strategy": "ttl",
                "ttl": 1,
                "max_size": 10000,
                "compression": False
            },
            "static_data": {
                "strategy": "lru", 
                "ttl": 3600,
                "max_size": 1000,
                "compression": True
            },
            "user_sessions": {
                "strategy": "lfu",
                "ttl": 1800,
                "max_size": 5000,
                "compression": False
            },
            "analytics": {
                "strategy": "fifo",
                "ttl": 300,
                "max_size": 2000,
                "compression": True
            }
        },
        "redis_config": {
            "host": "localhost",
            "port": 6379,
            "db": 1,
            "password": None,
            "socket_timeout": 5,
            "socket_connect_timeout": 5,
            "retry_on_timeout": True,
            "health_check_interval": 30,
            "connection_pool": {
                "max_connections": 50,
                "retry_on_timeout": True
            }
        },
        "monitoring": {
            "enabled": True,
            "metrics_retention_days": 7,
            "alert_thresholds": {
                "low_hit_rate": 0.8,
                "high_memory_usage": 0.9,
                "redis_connection_failure": 0.05
            }
        }
    },
    
    "performance": {
        "compression": {
            "enabled": True,
            "algorithms": ["gzip", "brotli", "deflate"],
            "threshold": 1024,
            "level": 6
        },
        "batching": {
            "enabled": True,
            "max_batch_size": 100,
            "max_wait_time": 50,
            "batch_strategies": ["market_data", "analytics"]
        },
        "connection_pooling": {
            "enabled": True,
            "max_pool_size": 100,
            "min_pool_size": 10,
            "pool_timeout": 30
        },
        "request_optimization": {
            "enabled": True,
            "async_processing": True,
            "parallel_requests": 10,
            "timeout": 30
        }
    },
    
    "security": {
        "api_key_validation": True,
        "rate_limit_by_ip": True,
        "rate_limit_by_user": True,
        "ddos_protection": True,
        "request_validation": True,
        "response_sanitization": True
    }
}

def create_rate_limiter(config: dict = None) -> RateLimiter:
    """
    Create a configured rate limiter instance
    
    Args:
        config: Rate limiter configuration
        
    Returns:
        Configured RateLimiter instance
    """
    if config is None:
        config = DEFAULT_CONFIG["rate_limiting"]
    
    return RateLimiter(config)

def create_cache_manager(config: dict = None) -> CacheManager:
    """
    Create a configured cache manager instance
    
    Args:
        config: Cache manager configuration
        
    Returns:
        Configured CacheManager instance
    """
    if config is None:
        config = DEFAULT_CONFIG["caching"]
    
    return CacheManager(config)

def create_performance_optimizer(config: dict = None) -> PerformanceOptimizer:
    """
    Create a configured performance optimizer instance
    
    Args:
        config: Performance optimizer configuration
        
    Returns:
        Configured PerformanceOptimizer instance
    """
    if config is None:
        config = DEFAULT_CONFIG["performance"]
    
    return PerformanceOptimizer(config)

# Export all components for easy access
__all__ = [
    # Rate Limiting
    "RateLimiter",
    "RateLimitRule", 
    "RateLimitType",
    "RateLimitStatus",
    "RateLimitException",
    "TokenBucket",
    "SlidingWindow", 
    "FixedWindow",
    "LeakyBucket",
    
    # Caching
    "CacheManager",
    "CacheStrategy",
    "CacheEntry",
    "CacheStats", 
    "TTLCache",
    "LRUCache",
    "LFUCache",
    "FIFOCache",
    
    # Middleware
    "RateLimitMiddleware",
    "CacheMiddleware",
    "CompressionMiddleware", 
    "APISecurityMiddleware",
    
    # Performance
    "PerformanceOptimizer",
    "RequestOptimizer",
    "ResponseOptimizer",
    "BatchProcessor",
    
    # Monitoring
    "RateLimitMonitor",
    "CacheMonitor", 
    "PerformanceMonitor",
    "AlertManager",
    
    # Factory functions
    "create_rate_limiter",
    "create_cache_manager",
    "create_performance_optimizer",
    
    # Configuration
    "DEFAULT_CONFIG"
]