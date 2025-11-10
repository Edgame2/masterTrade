"""
Production-grade rate limiting system with multiple algorithms and Redis backend.

Provides comprehensive rate limiting capabilities including token bucket,
sliding window, fixed window, and leaky bucket algorithms with distributed
Redis-based storage for scalable multi-instance deployments.
"""

import asyncio
import time
import json
import logging
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import math

try:
    import redis.asyncio as redis
    from redis.asyncio import Redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logging.warning("Redis not available for rate limiting")

logger = logging.getLogger(__name__)

class RateLimitType(Enum):
    """Rate limiting algorithm types"""
    TOKEN_BUCKET = "token_bucket"
    SLIDING_WINDOW = "sliding_window"  
    FIXED_WINDOW = "fixed_window"
    LEAKY_BUCKET = "leaky_bucket"

class RateLimitStatus(Enum):
    """Rate limit check status"""
    ALLOWED = "allowed"
    DENIED = "denied"
    ERROR = "error"

@dataclass
class RateLimitRule:
    """Rate limiting rule configuration"""
    name: str
    limit_type: RateLimitType
    requests_per_second: int
    burst_size: int
    window_size: int  # seconds
    paths: List[str]
    methods: List[str]
    priority: int = 1
    enabled: bool = True
    
    def matches_request(self, path: str, method: str) -> bool:
        """Check if rule matches request"""
        if not self.enabled:
            return False
            
        # Check method
        if self.methods and method.upper() not in [m.upper() for m in self.methods]:
            return False
            
        # Check path patterns
        if not self.paths:
            return True
            
        for pattern in self.paths:
            if self._match_pattern(pattern, path):
                return True
                
        return False
    
    def _match_pattern(self, pattern: str, path: str) -> bool:
        """Match path pattern with wildcards"""
        import fnmatch
        return fnmatch.fnmatch(path.lower(), pattern.lower())

@dataclass
class RateLimitStatus:
    """Rate limit check result"""
    status: RateLimitStatus
    rule_name: str
    requests_remaining: int
    reset_time: datetime
    retry_after: Optional[int] = None
    message: str = ""

class RateLimitException(Exception):
    """Rate limit exceeded exception"""
    
    def __init__(self, status: RateLimitStatus):
        self.status = status
        super().__init__(status.message)

class TokenBucket:
    """
    Token bucket rate limiting algorithm
    
    Allows burst of requests up to bucket capacity, then enforces
    steady rate based on token refill rate.
    """
    
    def __init__(self, redis_client: Redis, key_prefix: str):
        self.redis = redis_client
        self.key_prefix = key_prefix
    
    async def check_rate_limit(
        self,
        identifier: str,
        requests_per_second: int,
        burst_size: int,
        window_size: int = 60
    ) -> Tuple[bool, int, datetime]:
        """
        Check if request is allowed under token bucket algorithm
        
        Args:
            identifier: Unique identifier for rate limiting
            requests_per_second: Token refill rate
            burst_size: Maximum bucket capacity
            window_size: Not used in token bucket
            
        Returns:
            Tuple of (allowed, tokens_remaining, reset_time)
        """
        
        key = f"{self.key_prefix}:token_bucket:{identifier}"
        current_time = time.time()
        
        # Lua script for atomic token bucket operations
        lua_script = """
        local key = KEYS[1]
        local capacity = tonumber(ARGV[1])
        local refill_rate = tonumber(ARGV[2])
        local current_time = tonumber(ARGV[3])
        local requested_tokens = tonumber(ARGV[4])
        
        -- Get current state
        local bucket_data = redis.call('HMGET', key, 'tokens', 'last_refill')
        local tokens = tonumber(bucket_data[1]) or capacity
        local last_refill = tonumber(bucket_data[2]) or current_time
        
        -- Calculate tokens to add based on elapsed time
        local elapsed = current_time - last_refill
        local tokens_to_add = elapsed * refill_rate
        tokens = math.min(capacity, tokens + tokens_to_add)
        
        -- Check if request can be satisfied
        local allowed = 0
        if tokens >= requested_tokens then
            tokens = tokens - requested_tokens
            allowed = 1
        end
        
        -- Update bucket state
        redis.call('HMSET', key, 'tokens', tokens, 'last_refill', current_time)
        redis.call('EXPIRE', key, 3600)  -- 1 hour expiration
        
        return {allowed, tokens, capacity}
        """
        
        try:
            result = await self.redis.eval(
                lua_script,
                1,  # number of keys
                key,  # key
                burst_size,  # capacity
                requests_per_second,  # refill_rate
                current_time,  # current_time
                1  # requested_tokens
            )
            
            allowed = bool(result[0])
            tokens_remaining = int(result[1])
            capacity = int(result[2])
            
            # Calculate reset time (when bucket will be full)
            if tokens_remaining < capacity:
                time_to_full = (capacity - tokens_remaining) / requests_per_second
                reset_time = datetime.fromtimestamp(current_time + time_to_full)
            else:
                reset_time = datetime.fromtimestamp(current_time)
            
            return allowed, tokens_remaining, reset_time
            
        except Exception as e:
            logger.error(f"Token bucket rate limit check failed: {e}")
            return True, burst_size, datetime.now()  # Fail open

class SlidingWindow:
    """
    Sliding window rate limiting algorithm
    
    Maintains a sliding time window and counts requests
    within that window for precise rate limiting.
    """
    
    def __init__(self, redis_client: Redis, key_prefix: str):
        self.redis = redis_client
        self.key_prefix = key_prefix
    
    async def check_rate_limit(
        self,
        identifier: str,
        requests_per_second: int,
        burst_size: int,
        window_size: int = 60
    ) -> Tuple[bool, int, datetime]:
        """
        Check if request is allowed under sliding window algorithm
        
        Args:
            identifier: Unique identifier for rate limiting
            requests_per_second: Maximum requests per second
            burst_size: Maximum requests in burst
            window_size: Window size in seconds
            
        Returns:
            Tuple of (allowed, requests_remaining, reset_time)
        """
        
        key = f"{self.key_prefix}:sliding_window:{identifier}"
        current_time = time.time()
        window_start = current_time - window_size
        
        # Maximum requests in window
        max_requests = min(requests_per_second * window_size, burst_size)
        
        # Lua script for atomic sliding window operations
        lua_script = """
        local key = KEYS[1]
        local window_start = tonumber(ARGV[1])
        local current_time = tonumber(ARGV[2])
        local max_requests = tonumber(ARGV[3])
        
        -- Remove expired entries
        redis.call('ZREMRANGEBYSCORE', key, '-inf', window_start)
        
        -- Count current requests in window
        local current_count = redis.call('ZCARD', key)
        
        -- Check if request is allowed
        local allowed = 0
        if current_count < max_requests then
            -- Add current request
            redis.call('ZADD', key, current_time, current_time)
            current_count = current_count + 1
            allowed = 1
        end
        
        -- Set expiration
        redis.call('EXPIRE', key, 3600)
        
        return {allowed, current_count, max_requests}
        """
        
        try:
            result = await self.redis.eval(
                lua_script,
                1,  # number of keys
                key,  # key
                window_start,  # window_start
                current_time,  # current_time
                max_requests  # max_requests
            )
            
            allowed = bool(result[0])
            current_count = int(result[1])
            max_requests = int(result[2])
            
            requests_remaining = max(0, max_requests - current_count)
            
            # Reset time is when oldest request expires
            reset_time = datetime.fromtimestamp(current_time + window_size)
            
            return allowed, requests_remaining, reset_time
            
        except Exception as e:
            logger.error(f"Sliding window rate limit check failed: {e}")
            return True, max_requests, datetime.now()  # Fail open

class FixedWindow:
    """
    Fixed window rate limiting algorithm
    
    Divides time into fixed windows and limits requests
    per window. Simple but can allow bursts at window boundaries.
    """
    
    def __init__(self, redis_client: Redis, key_prefix: str):
        self.redis = redis_client
        self.key_prefix = key_prefix
    
    async def check_rate_limit(
        self,
        identifier: str,
        requests_per_second: int,
        burst_size: int,
        window_size: int = 60
    ) -> Tuple[bool, int, datetime]:
        """
        Check if request is allowed under fixed window algorithm
        
        Args:
            identifier: Unique identifier for rate limiting
            requests_per_second: Maximum requests per second
            burst_size: Maximum requests in burst
            window_size: Window size in seconds
            
        Returns:
            Tuple of (allowed, requests_remaining, reset_time)
        """
        
        current_time = time.time()
        
        # Calculate current window
        window_id = int(current_time // window_size)
        window_start = window_id * window_size
        window_end = window_start + window_size
        
        key = f"{self.key_prefix}:fixed_window:{identifier}:{window_id}"
        
        # Maximum requests in window
        max_requests = min(requests_per_second * window_size, burst_size)
        
        try:
            # Increment counter for current window
            current_count = await self.redis.incr(key)
            
            if current_count == 1:
                # Set expiration on first request in window
                await self.redis.expire(key, window_size + 10)  # Extra buffer
            
            allowed = current_count <= max_requests
            requests_remaining = max(0, max_requests - current_count)
            reset_time = datetime.fromtimestamp(window_end)
            
            return allowed, requests_remaining, reset_time
            
        except Exception as e:
            logger.error(f"Fixed window rate limit check failed: {e}")
            return True, max_requests, datetime.now()  # Fail open

class LeakyBucket:
    """
    Leaky bucket rate limiting algorithm
    
    Requests are added to bucket and processed at steady rate.
    If bucket overflows, requests are rejected.
    """
    
    def __init__(self, redis_client: Redis, key_prefix: str):
        self.redis = redis_client
        self.key_prefix = key_prefix
    
    async def check_rate_limit(
        self,
        identifier: str,
        requests_per_second: int,
        burst_size: int,
        window_size: int = 60
    ) -> Tuple[bool, int, datetime]:
        """
        Check if request is allowed under leaky bucket algorithm
        
        Args:
            identifier: Unique identifier for rate limiting
            requests_per_second: Leak rate (requests processed per second)
            burst_size: Bucket capacity
            window_size: Not used in leaky bucket
            
        Returns:
            Tuple of (allowed, capacity_remaining, next_leak_time)
        """
        
        key = f"{self.key_prefix}:leaky_bucket:{identifier}"
        current_time = time.time()
        
        # Lua script for atomic leaky bucket operations
        lua_script = """
        local key = KEYS[1]
        local capacity = tonumber(ARGV[1])
        local leak_rate = tonumber(ARGV[2])
        local current_time = tonumber(ARGV[3])
        
        -- Get current state
        local bucket_data = redis.call('HMGET', key, 'volume', 'last_leak')
        local volume = tonumber(bucket_data[1]) or 0
        local last_leak = tonumber(bucket_data[2]) or current_time
        
        -- Calculate leakage since last check
        local elapsed = current_time - last_leak
        local leaked_volume = elapsed * leak_rate
        volume = math.max(0, volume - leaked_volume)
        
        -- Check if request can fit in bucket
        local allowed = 0
        if volume < capacity then
            volume = volume + 1
            allowed = 1
        end
        
        -- Update bucket state
        redis.call('HMSET', key, 'volume', volume, 'last_leak', current_time)
        redis.call('EXPIRE', key, 3600)  -- 1 hour expiration
        
        return {allowed, volume, capacity}
        """
        
        try:
            result = await self.redis.eval(
                lua_script,
                1,  # number of keys
                key,  # key
                burst_size,  # capacity
                requests_per_second,  # leak_rate
                current_time  # current_time
            )
            
            allowed = bool(result[0])
            current_volume = int(result[1])
            capacity = int(result[2])
            
            capacity_remaining = capacity - current_volume
            
            # Calculate next leak time
            if current_volume > 0:
                next_leak_time = datetime.fromtimestamp(current_time + (1 / requests_per_second))
            else:
                next_leak_time = datetime.fromtimestamp(current_time)
            
            return allowed, capacity_remaining, next_leak_time
            
        except Exception as e:
            logger.error(f"Leaky bucket rate limit check failed: {e}")
            return True, burst_size, datetime.now()  # Fail open

class RateLimiter:
    """
    Main rate limiter with support for multiple algorithms and rules
    
    Provides comprehensive rate limiting with Redis backend,
    multiple algorithms, and flexible rule configuration.
    """
    
    def __init__(self, config: dict):
        self.config = config
        self.redis = None
        self.rules: List[RateLimitRule] = []
        self.algorithms = {}
        
        # Statistics
        self.stats = {
            "requests_checked": 0,
            "requests_allowed": 0,
            "requests_denied": 0,
            "rules_matched": {},
            "algorithm_usage": {},
            "redis_errors": 0
        }
        
        # Initialize if Redis is available
        if REDIS_AVAILABLE:
            self._setup_redis()
            self._setup_algorithms()
            self._load_rules()
        else:
            logger.warning("Redis not available, rate limiting disabled")
    
    def _setup_redis(self):
        """Setup Redis connection"""
        redis_config = self.config.get("redis_config", {})
        
        try:
            self.redis = redis.Redis(
                host=redis_config.get("host", "localhost"),
                port=redis_config.get("port", 6379),
                db=redis_config.get("db", 0),
                password=redis_config.get("password"),
                socket_timeout=redis_config.get("socket_timeout", 5),
                socket_connect_timeout=redis_config.get("socket_connect_timeout", 5),
                retry_on_timeout=redis_config.get("retry_on_timeout", True),
                health_check_interval=redis_config.get("health_check_interval", 30)
            )
            
            logger.info("Redis connection configured for rate limiting")
            
        except Exception as e:
            logger.error(f"Failed to setup Redis connection: {e}")
            self.redis = None
    
    def _setup_algorithms(self):
        """Initialize rate limiting algorithms"""
        if not self.redis:
            return
        
        key_prefix = "rate_limit"
        
        self.algorithms = {
            RateLimitType.TOKEN_BUCKET: TokenBucket(self.redis, key_prefix),
            RateLimitType.SLIDING_WINDOW: SlidingWindow(self.redis, key_prefix),
            RateLimitType.FIXED_WINDOW: FixedWindow(self.redis, key_prefix),
            RateLimitType.LEAKY_BUCKET: LeakyBucket(self.redis, key_prefix)
        }
    
    def _load_rules(self):
        """Load rate limiting rules from configuration"""
        default_rules = self.config.get("default_rules", [])
        
        for rule_config in default_rules:
            try:
                rule = RateLimitRule(
                    name=rule_config["name"],
                    limit_type=RateLimitType(rule_config["limit_type"]),
                    requests_per_second=rule_config["requests_per_second"],
                    burst_size=rule_config["burst_size"],
                    window_size=rule_config["window_size"],
                    paths=rule_config["paths"],
                    methods=rule_config["methods"],
                    priority=rule_config.get("priority", 1),
                    enabled=rule_config.get("enabled", True)
                )
                
                self.rules.append(rule)
                
                # Initialize statistics
                self.stats["rules_matched"][rule.name] = 0
                self.stats["algorithm_usage"][rule.limit_type.value] = 0
                
            except Exception as e:
                logger.error(f"Failed to load rate limit rule {rule_config.get('name', 'unknown')}: {e}")
        
        # Sort rules by priority (higher priority first)
        self.rules.sort(key=lambda r: r.priority, reverse=True)
        
        logger.info(f"Loaded {len(self.rules)} rate limiting rules")
    
    async def check_rate_limit(
        self,
        identifier: str,
        path: str,
        method: str = "GET",
        additional_identifiers: List[str] = None
    ) -> RateLimitStatus:
        """
        Check if request is allowed under rate limiting rules
        
        Args:
            identifier: Primary identifier (e.g., user ID, IP address)
            path: Request path
            method: HTTP method
            additional_identifiers: Additional identifiers for multi-level limiting
            
        Returns:
            RateLimitStatus indicating if request is allowed
        """
        
        self.stats["requests_checked"] += 1
        
        if not self.redis or not self.rules:
            # No rate limiting configured or Redis unavailable
            return RateLimitStatus(
                status=RateLimitStatus.ALLOWED,
                rule_name="none",
                requests_remaining=999999,
                reset_time=datetime.now() + timedelta(hours=1),
                message="Rate limiting not configured"
            )
        
        # Find matching rule with highest priority
        matching_rule = None
        for rule in self.rules:
            if rule.matches_request(path, method):
                matching_rule = rule
                break
        
        if not matching_rule:
            # No matching rule, allow request
            return RateLimitStatus(
                status=RateLimitStatus.ALLOWED,
                rule_name="no_match",
                requests_remaining=999999,
                reset_time=datetime.now() + timedelta(hours=1),
                message="No matching rate limit rule"
            )
        
        # Update statistics
        self.stats["rules_matched"][matching_rule.name] += 1
        self.stats["algorithm_usage"][matching_rule.limit_type.value] += 1
        
        # Get algorithm implementation
        algorithm = self.algorithms.get(matching_rule.limit_type)
        if not algorithm:
            logger.error(f"Algorithm {matching_rule.limit_type} not available")
            return RateLimitStatus(
                status=RateLimitStatus.ERROR,
                rule_name=matching_rule.name,
                requests_remaining=0,
                reset_time=datetime.now(),
                message="Rate limiting algorithm not available"
            )
        
        # Check all identifiers (support for multi-level rate limiting)
        all_identifiers = [identifier]
        if additional_identifiers:
            all_identifiers.extend(additional_identifiers)
        
        for check_identifier in all_identifiers:
            try:
                # Create composite key for this rule and identifier
                composite_key = f"{matching_rule.name}:{hashlib.md5(check_identifier.encode()).hexdigest()}"
                
                allowed, remaining, reset_time = await algorithm.check_rate_limit(
                    composite_key,
                    matching_rule.requests_per_second,
                    matching_rule.burst_size,
                    matching_rule.window_size
                )
                
                if not allowed:
                    # Rate limit exceeded
                    self.stats["requests_denied"] += 1
                    
                    retry_after = int((reset_time - datetime.now()).total_seconds())
                    
                    return RateLimitStatus(
                        status=RateLimitStatus.DENIED,
                        rule_name=matching_rule.name,
                        requests_remaining=remaining,
                        reset_time=reset_time,
                        retry_after=retry_after,
                        message=f"Rate limit exceeded for rule {matching_rule.name}"
                    )
                
            except Exception as e:
                logger.error(f"Rate limit check failed for {check_identifier}: {e}")
                self.stats["redis_errors"] += 1
                
                # Fail open on errors
                return RateLimitStatus(
                    status=RateLimitStatus.ERROR,
                    rule_name=matching_rule.name,
                    requests_remaining=0,
                    reset_time=datetime.now(),
                    message=f"Rate limiting error: {e}"
                )
        
        # All checks passed
        self.stats["requests_allowed"] += 1
        
        return RateLimitStatus(
            status=RateLimitStatus.ALLOWED,
            rule_name=matching_rule.name,
            requests_remaining=remaining,
            reset_time=reset_time,
            message="Request allowed"
        )
    
    def add_rule(self, rule: RateLimitRule):
        """Add new rate limiting rule"""
        self.rules.append(rule)
        self.rules.sort(key=lambda r: r.priority, reverse=True)
        
        # Initialize statistics
        self.stats["rules_matched"][rule.name] = 0
        self.stats["algorithm_usage"][rule.limit_type.value] = 0
        
        logger.info(f"Added rate limiting rule: {rule.name}")
    
    def remove_rule(self, rule_name: str) -> bool:
        """Remove rate limiting rule"""
        for i, rule in enumerate(self.rules):
            if rule.name == rule_name:
                del self.rules[i]
                
                # Clean up statistics
                if rule_name in self.stats["rules_matched"]:
                    del self.stats["rules_matched"][rule_name]
                
                logger.info(f"Removed rate limiting rule: {rule_name}")
                return True
        
        return False
    
    def get_statistics(self) -> dict:
        """Get rate limiting statistics"""
        return {
            **self.stats,
            "total_rules": len(self.rules),
            "redis_available": self.redis is not None,
            "enabled_rules": [rule.name for rule in self.rules if rule.enabled]
        }
    
    async def reset_limits(self, identifier: str = None, rule_name: str = None):
        """Reset rate limits for identifier or rule"""
        if not self.redis:
            return
        
        try:
            if identifier and rule_name:
                # Reset specific identifier for specific rule
                composite_key = f"{rule_name}:{hashlib.md5(identifier.encode()).hexdigest()}"
                keys = [
                    f"rate_limit:token_bucket:{composite_key}",
                    f"rate_limit:sliding_window:{composite_key}",
                    f"rate_limit:fixed_window:{composite_key}*",
                    f"rate_limit:leaky_bucket:{composite_key}"
                ]
                
                for key_pattern in keys:
                    if "*" in key_pattern:
                        # Delete pattern-matched keys
                        matching_keys = await self.redis.keys(key_pattern)
                        if matching_keys:
                            await self.redis.delete(*matching_keys)
                    else:
                        await self.redis.delete(key_pattern)
            
            elif identifier:
                # Reset all limits for identifier
                pattern = f"rate_limit:*:{hashlib.md5(identifier.encode()).hexdigest()}"
                matching_keys = await self.redis.keys(pattern)
                if matching_keys:
                    await self.redis.delete(*matching_keys)
            
            elif rule_name:
                # Reset all limits for rule
                pattern = f"rate_limit:*:{rule_name}:*"
                matching_keys = await self.redis.keys(pattern)
                if matching_keys:
                    await self.redis.delete(*matching_keys)
            
            else:
                # Reset all limits
                pattern = "rate_limit:*"
                matching_keys = await self.redis.keys(pattern)
                if matching_keys:
                    await self.redis.delete(*matching_keys)
            
            logger.info(f"Reset rate limits for identifier={identifier}, rule={rule_name}")
            
        except Exception as e:
            logger.error(f"Failed to reset rate limits: {e}")
    
    async def health_check(self) -> dict:
        """Check health of rate limiting system"""
        health_status = {
            "healthy": True,
            "redis_connected": False,
            "rules_loaded": len(self.rules),
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
        else:
            health_status["healthy"] = False
            health_status["errors"].append("Redis not configured")
        
        # Check rule configuration
        if not self.rules:
            health_status["errors"].append("No rate limiting rules configured")
        
        return health_status