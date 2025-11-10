"""
Advanced caching system with multiple strategies and Redis backend.

Provides comprehensive caching capabilities including TTL, LRU, LFU, and FIFO
strategies with compression, statistics, and distributed Redis storage.
"""

import asyncio
import time
import json
import logging
import gzip
import pickle
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union, Tuple, Callable
from dataclasses import dataclass, asdict
from enum import Enum
import threading
from collections import OrderedDict, defaultdict

try:
    import redis.asyncio as redis
    from redis.asyncio import Redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logging.warning("Redis not available for caching")

logger = logging.getLogger(__name__)

class CacheStrategy(Enum):
    """Cache eviction strategies"""
    TTL = "ttl"  # Time To Live
    LRU = "lru"  # Least Recently Used
    LFU = "lfu"  # Least Frequently Used
    FIFO = "fifo"  # First In First Out

@dataclass
class CacheEntry:
    """Cache entry with metadata"""
    key: str
    value: Any
    created_at: datetime
    accessed_at: datetime
    access_count: int
    ttl: Optional[int] = None
    compressed: bool = False
    size_bytes: int = 0
    
    def is_expired(self) -> bool:
        """Check if entry has expired"""
        if self.ttl is None:
            return False
        
        age = (datetime.now() - self.created_at).total_seconds()
        return age > self.ttl
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization"""
        return {
            "key": self.key,
            "created_at": self.created_at.isoformat(),
            "accessed_at": self.accessed_at.isoformat(),
            "access_count": self.access_count,
            "ttl": self.ttl,
            "compressed": self.compressed,
            "size_bytes": self.size_bytes
        }

@dataclass
class CacheStats:
    """Cache performance statistics"""
    hits: int = 0
    misses: int = 0
    sets: int = 0
    deletes: int = 0
    evictions: int = 0
    total_size_bytes: int = 0
    memory_usage_mb: float = 0.0
    
    @property
    def hit_rate(self) -> float:
        """Calculate hit rate percentage"""
        total = self.hits + self.misses
        return (self.hits / total * 100) if total > 0 else 0.0
    
    @property
    def miss_rate(self) -> float:
        """Calculate miss rate percentage"""
        return 100.0 - self.hit_rate
    
    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            **asdict(self),
            "hit_rate": self.hit_rate,
            "miss_rate": self.miss_rate
        }

class TTLCache:
    """
    Time-to-Live cache implementation
    
    Entries expire after specified TTL and are automatically cleaned up.
    """
    
    def __init__(self, default_ttl: int = 300, max_size: int = 1000):
        self.default_ttl = default_ttl
        self.max_size = max_size
        self.data: Dict[str, CacheEntry] = {}
        self.lock = threading.RLock()
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        with self.lock:
            entry = self.data.get(key)
            if entry is None:
                return None
            
            if entry.is_expired():
                del self.data[key]
                return None
            
            # Update access time and count
            entry.accessed_at = datetime.now()
            entry.access_count += 1
            
            return entry.value
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set value in cache"""
        with self.lock:
            if len(self.data) >= self.max_size and key not in self.data:
                # Cache full, evict expired entries first
                self._cleanup_expired()
                
                if len(self.data) >= self.max_size:
                    # Still full, evict oldest entry
                    oldest_key = min(self.data.keys(), key=lambda k: self.data[k].created_at)
                    del self.data[oldest_key]
            
            now = datetime.now()
            size_bytes = len(pickle.dumps(value)) if value is not None else 0
            
            entry = CacheEntry(
                key=key,
                value=value,
                created_at=now,
                accessed_at=now,
                access_count=1,
                ttl=ttl or self.default_ttl,
                size_bytes=size_bytes
            )
            
            self.data[key] = entry
            return True
    
    def delete(self, key: str) -> bool:
        """Delete entry from cache"""
        with self.lock:
            return self.data.pop(key, None) is not None
    
    def _cleanup_expired(self):
        """Remove expired entries"""
        expired_keys = [key for key, entry in self.data.items() if entry.is_expired()]
        for key in expired_keys:
            del self.data[key]
    
    def clear(self):
        """Clear all entries"""
        with self.lock:
            self.data.clear()
    
    def size(self) -> int:
        """Get number of entries"""
        return len(self.data)
    
    def keys(self) -> List[str]:
        """Get all keys"""
        return list(self.data.keys())

class LRUCache:
    """
    Least Recently Used cache implementation
    
    Evicts least recently accessed entries when cache is full.
    """
    
    def __init__(self, max_size: int = 1000, default_ttl: Optional[int] = None):
        self.max_size = max_size
        self.default_ttl = default_ttl
        self.data: OrderedDict[str, CacheEntry] = OrderedDict()
        self.lock = threading.RLock()
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        with self.lock:
            entry = self.data.get(key)
            if entry is None:
                return None
            
            if self.default_ttl and entry.is_expired():
                del self.data[key]
                return None
            
            # Move to end (mark as recently used)
            self.data.move_to_end(key)
            
            # Update access metadata
            entry.accessed_at = datetime.now()
            entry.access_count += 1
            
            return entry.value
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set value in cache"""
        with self.lock:
            if key in self.data:
                # Update existing entry
                entry = self.data[key]
                entry.value = value
                entry.accessed_at = datetime.now()
                entry.access_count += 1
                if ttl is not None:
                    entry.ttl = ttl
                
                # Move to end
                self.data.move_to_end(key)
                return True
            
            # Check capacity
            if len(self.data) >= self.max_size:
                # Remove least recently used (first item)
                self.data.popitem(last=False)
            
            # Add new entry
            now = datetime.now()
            size_bytes = len(pickle.dumps(value)) if value is not None else 0
            
            entry = CacheEntry(
                key=key,
                value=value,
                created_at=now,
                accessed_at=now,
                access_count=1,
                ttl=ttl or self.default_ttl,
                size_bytes=size_bytes
            )
            
            self.data[key] = entry
            return True
    
    def delete(self, key: str) -> bool:
        """Delete entry from cache"""
        with self.lock:
            return self.data.pop(key, None) is not None
    
    def clear(self):
        """Clear all entries"""
        with self.lock:
            self.data.clear()
    
    def size(self) -> int:
        """Get number of entries"""
        return len(self.data)
    
    def keys(self) -> List[str]:
        """Get all keys"""
        return list(self.data.keys())

class LFUCache:
    """
    Least Frequently Used cache implementation
    
    Evicts least frequently accessed entries when cache is full.
    """
    
    def __init__(self, max_size: int = 1000, default_ttl: Optional[int] = None):
        self.max_size = max_size
        self.default_ttl = default_ttl
        self.data: Dict[str, CacheEntry] = {}
        self.frequency: Dict[str, int] = defaultdict(int)
        self.lock = threading.RLock()
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        with self.lock:
            entry = self.data.get(key)
            if entry is None:
                return None
            
            if self.default_ttl and entry.is_expired():
                del self.data[key]
                del self.frequency[key]
                return None
            
            # Update frequency and access metadata
            self.frequency[key] += 1
            entry.accessed_at = datetime.now()
            entry.access_count += 1
            
            return entry.value
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set value in cache"""
        with self.lock:
            if key in self.data:
                # Update existing entry
                entry = self.data[key]
                entry.value = value
                entry.accessed_at = datetime.now()
                entry.access_count += 1
                if ttl is not None:
                    entry.ttl = ttl
                
                self.frequency[key] += 1
                return True
            
            # Check capacity
            if len(self.data) >= self.max_size:
                # Remove least frequently used
                lfu_key = min(self.frequency.keys(), key=lambda k: self.frequency[k])
                del self.data[lfu_key]
                del self.frequency[lfu_key]
            
            # Add new entry
            now = datetime.now()
            size_bytes = len(pickle.dumps(value)) if value is not None else 0
            
            entry = CacheEntry(
                key=key,
                value=value,
                created_at=now,
                accessed_at=now,
                access_count=1,
                ttl=ttl or self.default_ttl,
                size_bytes=size_bytes
            )
            
            self.data[key] = entry
            self.frequency[key] = 1
            return True
    
    def delete(self, key: str) -> bool:
        """Delete entry from cache"""
        with self.lock:
            if key in self.data:
                del self.data[key]
                del self.frequency[key]
                return True
            return False
    
    def clear(self):
        """Clear all entries"""
        with self.lock:
            self.data.clear()
            self.frequency.clear()
    
    def size(self) -> int:
        """Get number of entries"""
        return len(self.data)
    
    def keys(self) -> List[str]:
        """Get all keys"""
        return list(self.data.keys())

class FIFOCache:
    """
    First In First Out cache implementation
    
    Evicts oldest entries when cache is full.
    """
    
    def __init__(self, max_size: int = 1000, default_ttl: Optional[int] = None):
        self.max_size = max_size
        self.default_ttl = default_ttl
        self.data: OrderedDict[str, CacheEntry] = OrderedDict()
        self.lock = threading.RLock()
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        with self.lock:
            entry = self.data.get(key)
            if entry is None:
                return None
            
            if self.default_ttl and entry.is_expired():
                del self.data[key]
                return None
            
            # Update access metadata (but don't change order)
            entry.accessed_at = datetime.now()
            entry.access_count += 1
            
            return entry.value
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set value in cache"""
        with self.lock:
            if key in self.data:
                # Update existing entry (maintain order)
                entry = self.data[key]
                entry.value = value
                entry.accessed_at = datetime.now()
                entry.access_count += 1
                if ttl is not None:
                    entry.ttl = ttl
                return True
            
            # Check capacity
            if len(self.data) >= self.max_size:
                # Remove first entry (oldest)
                self.data.popitem(last=False)
            
            # Add new entry
            now = datetime.now()
            size_bytes = len(pickle.dumps(value)) if value is not None else 0
            
            entry = CacheEntry(
                key=key,
                value=value,
                created_at=now,
                accessed_at=now,
                access_count=1,
                ttl=ttl or self.default_ttl,
                size_bytes=size_bytes
            )
            
            self.data[key] = entry
            return True
    
    def delete(self, key: str) -> bool:
        """Delete entry from cache"""
        with self.lock:
            return self.data.pop(key, None) is not None
    
    def clear(self):
        """Clear all entries"""
        with self.lock:
            self.data.clear()
    
    def size(self) -> int:
        """Get number of entries"""
        return len(self.data)
    
    def keys(self) -> List[str]:
        """Get all keys"""
        return list(self.data.keys())

class CacheManager:
    """
    Comprehensive cache manager with multiple strategies and Redis backend
    
    Provides unified caching interface with local and distributed caching,
    compression, statistics, and flexible strategy configuration.
    """
    
    def __init__(self, config: dict):
        self.config = config
        self.redis = None
        self.local_caches: Dict[str, Any] = {}
        self.cache_strategies: Dict[str, dict] = {}
        
        # Statistics tracking
        self.stats = CacheStats()
        self.strategy_stats: Dict[str, CacheStats] = defaultdict(CacheStats)
        
        # Compression settings
        self.compression_enabled = config.get("compression_enabled", True)
        self.compression_threshold = config.get("compression_threshold", 1024)
        
        # Initialize Redis if available
        if REDIS_AVAILABLE:
            self._setup_redis()
        
        # Setup cache strategies
        self._setup_cache_strategies()
        
        # Start background cleanup task
        self._cleanup_task = None
        if config.get("enabled", True):
            self._start_cleanup_task()
    
    def _setup_redis(self):
        """Setup Redis connection for distributed caching"""
        redis_config = self.config.get("redis_config", {})
        
        try:
            self.redis = redis.Redis(
                host=redis_config.get("host", "localhost"),
                port=redis_config.get("port", 6379),
                db=redis_config.get("db", 1),
                password=redis_config.get("password"),
                socket_timeout=redis_config.get("socket_timeout", 5),
                socket_connect_timeout=redis_config.get("socket_connect_timeout", 5),
                retry_on_timeout=redis_config.get("retry_on_timeout", True),
                health_check_interval=redis_config.get("health_check_interval", 30)
            )
            
            logger.info("Redis connection configured for caching")
            
        except Exception as e:
            logger.error(f"Failed to setup Redis connection for caching: {e}")
            self.redis = None
    
    def _setup_cache_strategies(self):
        """Setup local cache instances for different strategies"""
        self.cache_strategies = self.config.get("cache_strategies", {})
        default_strategy = self.config.get("default_strategy", "lru")
        default_ttl = self.config.get("default_ttl", 300)
        max_memory_mb = self.config.get("max_memory_mb", 512)
        
        # Calculate size per strategy
        num_strategies = len(self.cache_strategies) or 1
        size_per_strategy = int((max_memory_mb * 1024 * 1024) / (num_strategies * 100))  # Rough estimate
        
        for strategy_name, strategy_config in self.cache_strategies.items():
            strategy_type = strategy_config.get("strategy", default_strategy)
            ttl = strategy_config.get("ttl", default_ttl)
            max_size = strategy_config.get("max_size", 1000)
            
            # Create appropriate cache instance
            if strategy_type == "ttl":
                cache = TTLCache(default_ttl=ttl, max_size=max_size)
            elif strategy_type == "lru":
                cache = LRUCache(max_size=max_size, default_ttl=ttl if ttl > 0 else None)
            elif strategy_type == "lfu":
                cache = LFUCache(max_size=max_size, default_ttl=ttl if ttl > 0 else None)
            elif strategy_type == "fifo":
                cache = FIFOCache(max_size=max_size, default_ttl=ttl if ttl > 0 else None)
            else:
                # Default to LRU
                cache = LRUCache(max_size=max_size, default_ttl=ttl if ttl > 0 else None)
                logger.warning(f"Unknown cache strategy {strategy_type}, using LRU")
            
            self.local_caches[strategy_name] = cache
            self.strategy_stats[strategy_name] = CacheStats()
        
        # Create default cache if no strategies configured
        if not self.local_caches:
            self.local_caches["default"] = LRUCache(max_size=1000, default_ttl=default_ttl)
            self.strategy_stats["default"] = CacheStats()
        
        logger.info(f"Configured {len(self.local_caches)} cache strategies")
    
    def _get_cache_key(self, key: str, strategy: str = "default") -> str:
        """Generate cache key with strategy prefix"""
        return f"cache:{strategy}:{hashlib.md5(key.encode()).hexdigest()}"
    
    def _compress_value(self, value: Any) -> Tuple[bytes, bool]:
        """Compress value if beneficial"""
        # Serialize value
        serialized = pickle.dumps(value)
        
        # Check if compression is beneficial
        if (self.compression_enabled and 
            len(serialized) > self.compression_threshold):
            
            compressed = gzip.compress(serialized)
            
            # Only use compression if it reduces size
            if len(compressed) < len(serialized):
                return compressed, True
        
        return serialized, False
    
    def _decompress_value(self, data: bytes, compressed: bool) -> Any:
        """Decompress and deserialize value"""
        if compressed:
            data = gzip.decompress(data)
        
        return pickle.loads(data)
    
    async def get(
        self,
        key: str,
        strategy: str = "default",
        use_redis: bool = True
    ) -> Optional[Any]:
        """
        Get value from cache
        
        Args:
            key: Cache key
            strategy: Cache strategy to use
            use_redis: Whether to check Redis if not found locally
            
        Returns:
            Cached value or None if not found
        """
        
        # Try local cache first
        local_cache = self.local_caches.get(strategy)
        if local_cache:
            value = local_cache.get(key)
            if value is not None:
                self.stats.hits += 1
                self.strategy_stats[strategy].hits += 1
                return value
        
        # Try Redis if enabled
        if use_redis and self.redis:
            try:
                cache_key = self._get_cache_key(key, strategy)
                redis_data = await self.redis.hgetall(cache_key)
                
                if redis_data:
                    # Check TTL
                    ttl = await self.redis.ttl(cache_key)
                    if ttl > 0:  # Not expired
                        # Deserialize value
                        value_data = redis_data.get(b'value')
                        compressed = redis_data.get(b'compressed') == b'true'
                        
                        if value_data:
                            value = self._decompress_value(value_data, compressed)
                            
                            # Store in local cache for future hits
                            if local_cache:
                                local_cache.set(key, value)
                            
                            self.stats.hits += 1
                            self.strategy_stats[strategy].hits += 1
                            return value
            
            except Exception as e:
                logger.error(f"Redis cache get failed for key {key}: {e}")
        
        # Cache miss
        self.stats.misses += 1
        self.strategy_stats[strategy].misses += 1
        return None
    
    async def set(
        self,
        key: str,
        value: Any,
        strategy: str = "default",
        ttl: Optional[int] = None,
        use_redis: bool = True
    ) -> bool:
        """
        Set value in cache
        
        Args:
            key: Cache key
            value: Value to cache
            strategy: Cache strategy to use
            ttl: Time to live in seconds
            use_redis: Whether to also store in Redis
            
        Returns:
            True if successful
        """
        
        success = True
        
        # Set in local cache
        local_cache = self.local_caches.get(strategy)
        if local_cache:
            local_success = local_cache.set(key, value, ttl)
            success = success and local_success
        
        # Set in Redis if enabled
        if use_redis and self.redis:
            try:
                cache_key = self._get_cache_key(key, strategy)
                
                # Compress value
                value_data, compressed = self._compress_value(value)
                
                # Prepare Redis data
                redis_data = {
                    'value': value_data,
                    'compressed': str(compressed).lower(),
                    'created_at': datetime.now().isoformat(),
                    'strategy': strategy
                }
                
                # Set with TTL
                strategy_config = self.cache_strategies.get(strategy, {})
                cache_ttl = ttl or strategy_config.get('ttl', self.config.get('default_ttl', 300))
                
                await self.redis.hset(cache_key, mapping=redis_data)
                if cache_ttl > 0:
                    await self.redis.expire(cache_key, cache_ttl)
                
            except Exception as e:
                logger.error(f"Redis cache set failed for key {key}: {e}")
                success = False
        
        if success:
            self.stats.sets += 1
            self.strategy_stats[strategy].sets += 1
        
        return success
    
    async def delete(
        self,
        key: str,
        strategy: str = "default",
        use_redis: bool = True
    ) -> bool:
        """Delete value from cache"""
        
        success = True
        
        # Delete from local cache
        local_cache = self.local_caches.get(strategy)
        if local_cache:
            local_success = local_cache.delete(key)
            success = success and local_success
        
        # Delete from Redis
        if use_redis and self.redis:
            try:
                cache_key = self._get_cache_key(key, strategy)
                redis_success = await self.redis.delete(cache_key)
                success = success and bool(redis_success)
                
            except Exception as e:
                logger.error(f"Redis cache delete failed for key {key}: {e}")
                success = False
        
        if success:
            self.stats.deletes += 1
            self.strategy_stats[strategy].deletes += 1
        
        return success
    
    async def clear(self, strategy: str = None):
        """Clear cache entries"""
        
        if strategy:
            # Clear specific strategy
            local_cache = self.local_caches.get(strategy)
            if local_cache:
                local_cache.clear()
            
            # Clear from Redis
            if self.redis:
                try:
                    pattern = f"cache:{strategy}:*"
                    keys = await self.redis.keys(pattern)
                    if keys:
                        await self.redis.delete(*keys)
                except Exception as e:
                    logger.error(f"Redis cache clear failed for strategy {strategy}: {e}")
        
        else:
            # Clear all caches
            for cache in self.local_caches.values():
                cache.clear()
            
            # Clear Redis
            if self.redis:
                try:
                    keys = await self.redis.keys("cache:*")
                    if keys:
                        await self.redis.delete(*keys)
                except Exception as e:
                    logger.error(f"Redis cache clear failed: {e}")
    
    def get_statistics(self) -> dict:
        """Get comprehensive cache statistics"""
        
        # Calculate total memory usage
        total_size = 0
        strategy_sizes = {}
        
        for strategy_name, cache in self.local_caches.items():
            strategy_size = 0
            if hasattr(cache, 'data'):
                strategy_size = sum(entry.size_bytes for entry in cache.data.values())
            
            strategy_sizes[strategy_name] = strategy_size
            total_size += strategy_size
        
        self.stats.total_size_bytes = total_size
        self.stats.memory_usage_mb = total_size / (1024 * 1024)
        
        return {
            "global_stats": self.stats.to_dict(),
            "strategy_stats": {
                strategy: stats.to_dict() 
                for strategy, stats in self.strategy_stats.items()
            },
            "strategy_sizes": strategy_sizes,
            "redis_available": self.redis is not None,
            "local_cache_counts": {
                strategy: cache.size() 
                for strategy, cache in self.local_caches.items()
            }
        }
    
    def _start_cleanup_task(self):
        """Start background cleanup task for expired entries"""
        
        async def cleanup_loop():
            while True:
                try:
                    await asyncio.sleep(60)  # Run every minute
                    
                    # Cleanup local caches
                    for strategy_name, cache in self.local_caches.items():
                        if hasattr(cache, '_cleanup_expired'):
                            cache._cleanup_expired()
                    
                except Exception as e:
                    logger.error(f"Cache cleanup task failed: {e}")
        
        # Start cleanup task
        try:
            loop = asyncio.get_event_loop()
            self._cleanup_task = loop.create_task(cleanup_loop())
        except RuntimeError:
            # No event loop running, cleanup will be manual
            logger.warning("No event loop running, automatic cache cleanup disabled")
    
    async def health_check(self) -> dict:
        """Check health of cache system"""
        health_status = {
            "healthy": True,
            "redis_connected": False,
            "local_caches": len(self.local_caches),
            "errors": []
        }
        
        # Check Redis connection
        if self.redis:
            try:
                await self.redis.ping()
                health_status["redis_connected"] = True
            except Exception as e:
                health_status["healthy"] = False
                health_status["errors"].append(f"Redis connection failed: {e}")
        
        # Check local cache health
        for strategy_name, cache in self.local_caches.items():
            try:
                cache.size()  # Basic operation check
            except Exception as e:
                health_status["healthy"] = False
                health_status["errors"].append(f"Local cache {strategy_name} error: {e}")
        
        return health_status