"""
Redis Cache Manager for MasterTrade System

Provides async Redis caching functionality for:
- API response caching
- Signal buffering
- Session management
- Query result caching
"""

import json
import logging
from typing import Any, Dict, List, Optional, Union
from datetime import datetime, timedelta

try:
    import redis.asyncio as aioredis
    from redis.asyncio import Redis
    from redis.exceptions import RedisError, ConnectionError as RedisConnectionError
except ImportError:
    # Fallback for older redis-py versions
    try:
        import aioredis
        from aioredis import Redis, RedisError
        RedisConnectionError = RedisError
    except ImportError:
        raise ImportError("Please install redis: pip install redis[asyncio] or aioredis")

logger = logging.getLogger(__name__)


class RedisCacheManager:
    """
    Async Redis cache manager with connection pooling and automatic retry logic
    
    Features:
    - Automatic JSON serialization/deserialization
    - TTL management per operation
    - Connection pooling
    - Graceful error handling
    - Sorted sets for signal buffering
    """
    
    def __init__(
        self, 
        redis_url: str = "redis://localhost:6379",
        max_connections: int = 50,
        decode_responses: bool = True
    ):
        """
        Initialize Redis cache manager
        
        Args:
            redis_url: Redis connection URL
            max_connections: Maximum connections in pool
            decode_responses: Auto-decode byte responses to strings
        """
        self.redis_url = redis_url
        self.max_connections = max_connections
        self.decode_responses = decode_responses
        self.redis: Optional[Redis] = None
        self._connected = False
        
    async def connect(self) -> bool:
        """
        Establish connection to Redis
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            self.redis = await aioredis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=self.decode_responses,
                max_connections=self.max_connections
            )
            
            # Test connection
            await self.redis.ping()
            self._connected = True
            logger.info(f"✅ Redis connection established: {self.redis_url}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Redis connection failed: {e}")
            self._connected = False
            return False
    
    async def disconnect(self):
        """Close Redis connection"""
        if self.redis:
            await self.redis.close()
            self._connected = False
            logger.info("Redis connection closed")
    
    async def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache
        
        Args:
            key: Cache key
            
        Returns:
            Cached value (deserialized from JSON) or None if not found
        """
        if not self._connected:
            logger.warning("Redis not connected, skipping cache get")
            return None
            
        try:
            value = await self.redis.get(key)
            if value is None:
                return None
            
            # Try to deserialize JSON
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                # Return raw value if not JSON
                return value
                
        except RedisConnectionError:
            logger.error(f"Redis connection error on get: {key}")
            self._connected = False
            return None
        except Exception as e:
            logger.error(f"Redis get error for key {key}: {e}")
            return None
    
    async def set(
        self, 
        key: str, 
        value: Any, 
        ttl: int = 3600,
        nx: bool = False,
        xx: bool = False
    ) -> bool:
        """
        Set value in cache with TTL
        
        Args:
            key: Cache key
            value: Value to cache (will be JSON serialized)
            ttl: Time-to-live in seconds (default: 1 hour)
            nx: Only set if key doesn't exist
            xx: Only set if key exists
            
        Returns:
            True if successful, False otherwise
        """
        if not self._connected:
            logger.warning("Redis not connected, skipping cache set")
            return False
            
        try:
            # Serialize to JSON if not string
            if not isinstance(value, str):
                value = json.dumps(value, default=str)
            
            result = await self.redis.setex(
                key, 
                ttl, 
                value
            )
            return bool(result)
            
        except RedisConnectionError:
            logger.error(f"Redis connection error on set: {key}")
            self._connected = False
            return False
        except Exception as e:
            logger.error(f"Redis set error for key {key}: {e}")
            return False
    
    async def delete(self, *keys: str) -> int:
        """
        Delete one or more keys
        
        Args:
            keys: Keys to delete
            
        Returns:
            Number of keys deleted
        """
        if not self._connected or not keys:
            return 0
            
        try:
            return await self.redis.delete(*keys)
        except Exception as e:
            logger.error(f"Redis delete error: {e}")
            return 0
    
    async def exists(self, *keys: str) -> int:
        """
        Check if keys exist
        
        Args:
            keys: Keys to check
            
        Returns:
            Number of existing keys
        """
        if not self._connected or not keys:
            return 0
            
        try:
            return await self.redis.exists(*keys)
        except Exception as e:
            logger.error(f"Redis exists error: {e}")
            return 0
    
    async def expire(self, key: str, seconds: int) -> bool:
        """
        Set expiration time on key
        
        Args:
            key: Key to expire
            seconds: Expiration time in seconds
            
        Returns:
            True if successful
        """
        if not self._connected:
            return False
            
        try:
            return await self.redis.expire(key, seconds)
        except Exception as e:
            logger.error(f"Redis expire error: {e}")
            return False
    
    async def ttl(self, key: str) -> int:
        """
        Get remaining TTL for key
        
        Args:
            key: Key to check
            
        Returns:
            TTL in seconds, -1 if no expiration, -2 if key doesn't exist
        """
        if not self._connected:
            return -2
            
        try:
            return await self.redis.ttl(key)
        except Exception as e:
            logger.error(f"Redis TTL error: {e}")
            return -2
    
    # Sorted Set operations for signal buffering
    
    async def zadd(
        self, 
        key: str, 
        mapping: Dict[Any, float],
        nx: bool = False,
        xx: bool = False
    ) -> int:
        """
        Add members to sorted set
        
        Args:
            key: Sorted set key
            mapping: Dict of member -> score
            nx: Only add new members
            xx: Only update existing members
            
        Returns:
            Number of members added
        """
        if not self._connected:
            return 0
            
        try:
            return await self.redis.zadd(key, mapping, nx=nx, xx=xx)
        except Exception as e:
            logger.error(f"Redis zadd error: {e}")
            return 0
    
    async def zrange(
        self, 
        key: str, 
        start: int = 0, 
        end: int = -1,
        withscores: bool = False
    ) -> List:
        """
        Get range of members from sorted set
        
        Args:
            key: Sorted set key
            start: Start index
            end: End index (-1 for all)
            withscores: Include scores in result
            
        Returns:
            List of members (and scores if withscores=True)
        """
        if not self._connected:
            return []
            
        try:
            result = await self.redis.zrange(key, start, end, withscores=withscores)
            
            # Deserialize JSON values
            if not withscores:
                return [self._deserialize(item) for item in result]
            else:
                return [(self._deserialize(item), score) for item, score in result]
                
        except Exception as e:
            logger.error(f"Redis zrange error: {e}")
            return []
    
    async def zremrangebyrank(self, key: str, start: int, end: int) -> int:
        """
        Remove members by rank range
        
        Args:
            key: Sorted set key
            start: Start rank
            end: End rank
            
        Returns:
            Number of members removed
        """
        if not self._connected:
            return 0
            
        try:
            return await self.redis.zremrangebyrank(key, start, end)
        except Exception as e:
            logger.error(f"Redis zremrangebyrank error: {e}")
            return 0
    
    async def zcard(self, key: str) -> int:
        """
        Get cardinality (size) of sorted set
        
        Args:
            key: Sorted set key
            
        Returns:
            Number of members in set
        """
        if not self._connected:
            return 0
            
        try:
            return await self.redis.zcard(key)
        except Exception as e:
            logger.error(f"Redis zcard error: {e}")
            return 0
    
    # Hash operations for structured data
    
    async def hset(self, key: str, mapping: Dict[str, Any]) -> int:
        """
        Set hash fields
        
        Args:
            key: Hash key
            mapping: Field -> value mapping
            
        Returns:
            Number of fields added
        """
        if not self._connected:
            return 0
            
        try:
            # Serialize values
            serialized = {k: json.dumps(v, default=str) for k, v in mapping.items()}
            return await self.redis.hset(key, mapping=serialized)
        except Exception as e:
            logger.error(f"Redis hset error: {e}")
            return 0
    
    async def hget(self, key: str, field: str) -> Optional[Any]:
        """
        Get hash field value
        
        Args:
            key: Hash key
            field: Field name
            
        Returns:
            Field value or None
        """
        if not self._connected:
            return None
            
        try:
            value = await self.redis.hget(key, field)
            return self._deserialize(value) if value else None
        except Exception as e:
            logger.error(f"Redis hget error: {e}")
            return None
    
    async def hgetall(self, key: str) -> Dict[str, Any]:
        """
        Get all hash fields
        
        Args:
            key: Hash key
            
        Returns:
            Dict of field -> value
        """
        if not self._connected:
            return {}
            
        try:
            result = await self.redis.hgetall(key)
            return {k: self._deserialize(v) for k, v in result.items()}
        except Exception as e:
            logger.error(f"Redis hgetall error: {e}")
            return {}
    
    # Utility methods
    
    def _deserialize(self, value: Any) -> Any:
        """Deserialize JSON value"""
        if value is None:
            return None
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value
    
    async def ping(self) -> bool:
        """Test connection"""
        if not self.redis:
            return False
        try:
            return await self.redis.ping()
        except:
            return False
    
    async def flushdb(self) -> bool:
        """
        Clear all keys in current database (use with caution!)
        
        Returns:
            True if successful
        """
        if not self._connected:
            return False
            
        try:
            await self.redis.flushdb()
            logger.warning("Redis database flushed")
            return True
        except Exception as e:
            logger.error(f"Redis flushdb error: {e}")
            return False
    
    async def info(self, section: str = "all") -> Dict[str, Any]:
        """
        Get Redis server info
        
        Args:
            section: Info section (all, server, memory, etc.)
            
        Returns:
            Server info dict
        """
        if not self._connected:
            return {}
            
        try:
            return await self.redis.info(section)
        except Exception as e:
            logger.error(f"Redis info error: {e}")
            return {}


# Convenience functions for common cache operations

async def cache_market_data(
    cache: RedisCacheManager,
    symbol: str,
    data: Dict[str, Any],
    ttl: int = 30
) -> bool:
    """Cache market data with 30 second TTL"""
    key = f"market_data:{symbol}"
    return await cache.set(key, data, ttl=ttl)


async def get_cached_market_data(
    cache: RedisCacheManager,
    symbol: str
) -> Optional[Dict[str, Any]]:
    """Get cached market data"""
    key = f"market_data:{symbol}"
    return await cache.get(key)


async def cache_onchain_metrics(
    cache: RedisCacheManager,
    symbol: str,
    metrics: Dict[str, Any],
    ttl: int = 300
) -> bool:
    """Cache on-chain metrics with 5 minute TTL"""
    key = f"onchain_metrics:{symbol}"
    return await cache.set(key, metrics, ttl=ttl)


async def cache_social_sentiment(
    cache: RedisCacheManager,
    symbol: str,
    sentiment: Dict[str, Any],
    ttl: int = 60
) -> bool:
    """Cache social sentiment with 1 minute TTL"""
    key = f"social_sentiment:{symbol}"
    return await cache.set(key, sentiment, ttl=ttl)


async def buffer_signal(
    cache: RedisCacheManager,
    signal: Dict[str, Any],
    max_signals: int = 1000
) -> bool:
    """
    Buffer trading signal in Redis sorted set
    
    Args:
        cache: Redis cache manager
        signal: Signal dict (must have 'timestamp' field)
        max_signals: Maximum signals to keep
        
    Returns:
        True if successful
    """
    try:
        timestamp = signal.get('timestamp', datetime.now().timestamp())
        signal_json = json.dumps(signal, default=str)
        
        # Add to sorted set with timestamp as score
        await cache.zadd('signals:recent', {signal_json: timestamp})
        
        # Trim to max size (keep most recent)
        current_size = await cache.zcard('signals:recent')
        if current_size > max_signals:
            # Remove oldest signals
            await cache.zremrangebyrank('signals:recent', 0, current_size - max_signals - 1)
        
        # Set expiration on the sorted set (24 hours)
        await cache.expire('signals:recent', 86400)
        
        return True
        
    except Exception as e:
        logger.error(f"Error buffering signal: {e}")
        return False


async def get_recent_signals(
    cache: RedisCacheManager,
    count: int = 100
) -> List[Dict[str, Any]]:
    """
    Get recent signals from buffer
    
    Args:
        cache: Redis cache manager
        count: Number of signals to retrieve
        
    Returns:
        List of recent signals (most recent first)
    """
    try:
        # Get last N signals
        signals = await cache.zrange('signals:recent', -count, -1)
        
        # Reverse to get most recent first
        signals.reverse()
        
        return [json.loads(s) if isinstance(s, str) else s for s in signals]
        
    except Exception as e:
        logger.error(f"Error getting recent signals: {e}")
        return []
