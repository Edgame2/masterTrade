"""
Cache Decorators for MasterTrade System

Provides async caching decorators for various data access patterns.
"""

import functools
import hashlib
import json
import structlog
from typing import Any, Callable, Optional

logger = structlog.get_logger()


def cache_key_generator(*args, **kwargs) -> str:
    """
    Generate cache key from function arguments
    
    Args:
        args: Positional arguments
        kwargs: Keyword arguments
        
    Returns:
        MD5 hash of serialized arguments
    """
    try:
        # Create deterministic string from args/kwargs
        key_data = {
            'args': [str(arg) for arg in args if not hasattr(arg, '__self__')],  # Skip self
            'kwargs': {k: str(v) for k, v in sorted(kwargs.items())}
        }
        key_str = json.dumps(key_data, sort_keys=True)
        return hashlib.md5(key_str.encode()).hexdigest()
    except Exception as e:
        logger.warning(f"Error generating cache key: {e}")
        return hashlib.md5(str(args).encode()).hexdigest()


def cached(
    prefix: str,
    ttl: int = 60,
    key_func: Optional[Callable] = None
):
    """
    Decorator for caching async function results in Redis
    
    Args:
        prefix: Cache key prefix (e.g., 'api_response', 'indicator')
        ttl: Time-to-live in seconds
        key_func: Optional custom key generation function
        
    Usage:
        @cached(prefix='price_data', ttl=30)
        async def get_price(self, symbol: str):
            return await self.api.fetch_price(symbol)
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(self, *args, **kwargs):
            # Check if redis_cache is available
            if not hasattr(self, 'redis_cache') or not self.redis_cache:
                # No cache available, call function directly
                return await func(self, *args, **kwargs)
            
            # Generate cache key
            if key_func:
                cache_key_suffix = key_func(*args, **kwargs)
            else:
                cache_key_suffix = cache_key_generator(*args, **kwargs)
            
            cache_key = f"{prefix}:{cache_key_suffix}"
            
            # Try to get from cache
            try:
                cached_value = await self.redis_cache.get(cache_key)
                if cached_value is not None:
                    logger.debug(f"Cache hit: {cache_key}")
                    # Track cache hits if metrics available
                    if hasattr(self, 'cache_hits'):
                        self.cache_hits += 1
                    return cached_value
            except Exception as e:
                logger.warning(f"Cache get error for {cache_key}: {e}")
            
            # Cache miss - call original function
            logger.debug(f"Cache miss: {cache_key}")
            if hasattr(self, 'cache_misses'):
                self.cache_misses += 1
            
            result = await func(self, *args, **kwargs)
            
            # Store in cache (don't fail if cache write fails)
            if result is not None:
                try:
                    await self.redis_cache.set(cache_key, result, ttl=ttl)
                except Exception as e:
                    logger.warning(f"Cache set error for {cache_key}: {e}")
            
            return result
        
        return wrapper
    return decorator


def cache_invalidate(prefix: str, key_func: Optional[Callable] = None):
    """
    Decorator to invalidate cache after function execution
    
    Args:
        prefix: Cache key prefix to invalidate
        key_func: Optional custom key generation function
        
    Usage:
        @cache_invalidate(prefix='price_data')
        async def update_price(self, symbol: str, price: float):
            await self.db.update(symbol, price)
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(self, *args, **kwargs):
            # Execute original function
            result = await func(self, *args, **kwargs)
            
            # Invalidate cache
            if hasattr(self, 'redis_cache') and self.redis_cache:
                try:
                    if key_func:
                        cache_key_suffix = key_func(*args, **kwargs)
                    else:
                        cache_key_suffix = cache_key_generator(*args, **kwargs)
                    
                    cache_key = f"{prefix}:{cache_key_suffix}"
                    await self.redis_cache.delete(cache_key)
                    logger.debug(f"Cache invalidated: {cache_key}")
                except Exception as e:
                    logger.warning(f"Cache invalidation error: {e}")
            
            return result
        
        return wrapper
    return decorator


def simple_key(*arg_indices):
    """
    Simple key generator using specific argument indices
    
    Args:
        arg_indices: Indices of arguments to use for key
        
    Example:
        @cached(prefix='user', ttl=300, key_func=simple_key(0))
        async def get_user(self, user_id: int):
            ...
    """
    def key_generator(*args, **kwargs):
        parts = [str(args[i]) for i in arg_indices if i < len(args)]
        return ':'.join(parts)
    return key_generator


class CacheStats:
    """
    Track cache statistics for monitoring
    """
    def __init__(self):
        self.hits = 0
        self.misses = 0
        self.errors = 0
        self.invalidations = 0
    
    @property
    def hit_rate(self) -> float:
        """Calculate cache hit rate"""
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0
    
    def to_dict(self) -> dict:
        """Convert stats to dictionary"""
        return {
            'hits': self.hits,
            'misses': self.misses,
            'errors': self.errors,
            'invalidations': self.invalidations,
            'hit_rate': self.hit_rate,
            'total_requests': self.hits + self.misses
        }
    
    def reset(self):
        """Reset all counters"""
        self.hits = 0
        self.misses = 0
        self.errors = 0
        self.invalidations = 0
