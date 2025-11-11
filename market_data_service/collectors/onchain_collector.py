"""
Base On-Chain Data Collector for Market Data Service

This module provides a base class for collecting on-chain data from various providers:
- Moralis (whale transactions, DEX trades)
- Glassnode (on-chain metrics: NVT, MVRV, exchange flows)
- Nansen (smart money tracking, wallet labels)

Features:
- Rate limiting with adaptive backoff
- Circuit breaker pattern for failure handling
- Retry logic with exponential backoff
- Connection pooling for HTTP requests
"""

import asyncio
import aiohttp
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Any, List
from enum import Enum
import structlog

from database import Database

logger = structlog.get_logger()


class CollectorStatus(Enum):
    """Collector health status"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"
    CIRCUIT_OPEN = "circuit_open"


class CircuitBreaker:
    """
    Enhanced circuit breaker pattern for collector failure handling
    
    Features:
    - Three states: closed (normal), open (blocking), half-open (testing recovery)
    - Configurable thresholds per collector
    - Gradual recovery with success tracking in half-open state
    - Health metric integration
    - Automatic recovery strategies
    - Redis state persistence (optional)
    """
    
    def __init__(
        self, 
        failure_threshold: int = 5,
        timeout_seconds: int = 300,
        half_open_max_calls: int = 3,
        half_open_success_threshold: int = 2,
        collector_name: str = "unknown",
        redis_cache=None
    ):
        """
        Initialize enhanced circuit breaker
        
        Args:
            failure_threshold: Number of consecutive failures before opening circuit
            timeout_seconds: Cooldown period before attempting recovery (half-open)
            half_open_max_calls: Maximum test calls allowed in half-open state
            half_open_success_threshold: Successes needed in half-open to close circuit
            collector_name: Name for logging and Redis keys
            redis_cache: Optional Redis cache for state persistence
        """
        self.collector_name = collector_name
        self.failure_threshold = failure_threshold
        self.timeout_seconds = timeout_seconds
        self.half_open_max_calls = half_open_max_calls
        self.half_open_success_threshold = half_open_success_threshold
        self.redis_cache = redis_cache
        
        # State tracking
        self.state = "closed"  # closed, open, half-open
        self.failure_count = 0
        self.consecutive_successes = 0
        self.last_failure_time: Optional[datetime] = None
        self.last_state_change: Optional[datetime] = None
        
        # Half-open state tracking
        self.half_open_attempts = 0
        self.half_open_successes = 0
        
        # Statistics
        self.stats = {
            "total_failures": 0,
            "total_successes": 0,
            "circuit_opens": 0,
            "successful_recoveries": 0,
            "failed_recoveries": 0,
            "time_in_open_state": 0.0,  # seconds
            "last_open_time": None
        }
        
    def record_success(self):
        """
        Record successful operation
        
        Behavior depends on current state:
        - closed: Reset failure count
        - half-open: Track success, may close circuit if threshold reached
        - open: Should not be called (but handles gracefully)
        """
        self.consecutive_successes += 1
        self.failure_count = 0
        self.stats["total_successes"] += 1
        
        if self.state == "closed":
            # Normal operation
            pass
            
        elif self.state == "half-open":
            # Track success in recovery phase
            self.half_open_successes += 1
            self.half_open_attempts += 1
            
            logger.debug(
                "Circuit breaker half-open success",
                collector=self.collector_name,
                successes=f"{self.half_open_successes}/{self.half_open_success_threshold}",
                attempts=f"{self.half_open_attempts}/{self.half_open_max_calls}"
            )
            
            # Check if we've reached success threshold
            if self.half_open_successes >= self.half_open_success_threshold:
                self._close_circuit()
                self.stats["successful_recoveries"] += 1
                logger.info(
                    "Circuit breaker closed - recovery successful",
                    collector=self.collector_name,
                    successes=self.half_open_successes,
                    attempts=self.half_open_attempts
                )
            # Check if we've exhausted attempts without enough successes
            elif self.half_open_attempts >= self.half_open_max_calls:
                success_rate = self.half_open_successes / self.half_open_attempts
                if success_rate < 0.5:  # Less than 50% success
                    self._reopen_circuit()
                    self.stats["failed_recoveries"] += 1
                    logger.warning(
                        "Circuit breaker reopened - recovery failed",
                        collector=self.collector_name,
                        successes=self.half_open_successes,
                        attempts=self.half_open_attempts,
                        success_rate=f"{success_rate:.2%}"
                    )
                else:
                    # Good enough, close circuit
                    self._close_circuit()
                    self.stats["successful_recoveries"] += 1
                    
        elif self.state == "open":
            # Unexpected success while open (shouldn't happen)
            logger.warning(
                "Unexpected success while circuit open",
                collector=self.collector_name
            )
        
    def record_failure(self):
        """
        Record failed operation
        
        Behavior depends on current state:
        - closed: Increment failure count, may open circuit
        - half-open: Reopen circuit immediately (recovery failed)
        - open: Already open, just track stats
        """
        self.failure_count += 1
        self.consecutive_successes = 0
        self.last_failure_time = datetime.now(timezone.utc)
        self.stats["total_failures"] += 1
        
        if self.state == "closed":
            # Check if threshold reached
            if self.failure_count >= self.failure_threshold:
                self._open_circuit()
                logger.warning(
                    "Circuit breaker opened",
                    collector=self.collector_name,
                    failure_count=self.failure_count,
                    threshold=self.failure_threshold,
                    timeout_seconds=self.timeout_seconds
                )
                
        elif self.state == "half-open":
            # Failure during recovery - reopen immediately
            self._reopen_circuit()
            self.stats["failed_recoveries"] += 1
            logger.warning(
                "Circuit breaker reopened - failure during recovery",
                collector=self.collector_name,
                attempts=self.half_open_attempts,
                successes=self.half_open_successes
            )
            
        elif self.state == "open":
            # Already open, just track
            pass
            
    def can_attempt(self) -> bool:
        """
        Check if operation can be attempted
        
        Returns:
            True if request should be attempted, False if blocked
        """
        if self.state == "closed":
            return True
            
        if self.state == "open":
            # Check if cooldown period has elapsed
            if self.last_failure_time:
                elapsed = (datetime.now(timezone.utc) - self.last_failure_time).total_seconds()
                if elapsed >= self.timeout_seconds:
                    self._enter_half_open()
                    logger.info(
                        "Circuit breaker entering half-open state",
                        collector=self.collector_name,
                        cooldown_elapsed=f"{elapsed:.1f}s"
                    )
                    return True
            return False
            
        if self.state == "half-open":
            # Allow limited attempts for testing
            if self.half_open_attempts < self.half_open_max_calls:
                return True
            else:
                # Exhausted test attempts, block further calls
                logger.debug(
                    "Circuit breaker half-open - max attempts reached",
                    collector=self.collector_name,
                    attempts=self.half_open_attempts
                )
                return False
        
        return True
    
    def _open_circuit(self):
        """Open the circuit (block all requests)"""
        old_state = self.state
        self.state = "open"
        self.last_state_change = datetime.now(timezone.utc)
        self.stats["circuit_opens"] += 1
        self.stats["last_open_time"] = self.last_state_change.isoformat()
        
        if old_state != "open":
            logger.warning(
                "Circuit state changed to OPEN",
                collector=self.collector_name,
                previous_state=old_state,
                failure_count=self.failure_count
            )
    
    def _enter_half_open(self):
        """Enter half-open state (testing recovery)"""
        self.state = "half-open"
        self.last_state_change = datetime.now(timezone.utc)
        self.half_open_attempts = 0
        self.half_open_successes = 0
        
        # Update time spent in open state
        if self.stats.get("last_open_time"):
            try:
                open_time = datetime.fromisoformat(self.stats["last_open_time"])
                time_open = (self.last_state_change - open_time).total_seconds()
                self.stats["time_in_open_state"] += time_open
            except:
                pass
        
        logger.info(
            "Circuit state changed to HALF-OPEN",
            collector=self.collector_name,
            max_test_calls=self.half_open_max_calls,
            success_threshold=self.half_open_success_threshold
        )
    
    def _close_circuit(self):
        """Close the circuit (resume normal operation)"""
        old_state = self.state
        self.state = "closed"
        self.last_state_change = datetime.now(timezone.utc)
        self.failure_count = 0
        self.half_open_attempts = 0
        self.half_open_successes = 0
        
        logger.info(
            "Circuit state changed to CLOSED",
            collector=self.collector_name,
            previous_state=old_state,
            consecutive_successes=self.consecutive_successes
        )
    
    def _reopen_circuit(self):
        """Reopen circuit after failed recovery attempt"""
        self.state = "open"
        self.last_state_change = datetime.now(timezone.utc)
        self.last_failure_time = datetime.now(timezone.utc)
        self.half_open_attempts = 0
        self.half_open_successes = 0
        self.stats["last_open_time"] = self.last_state_change.isoformat()
        
        # Increase timeout for next attempt (exponential backoff)
        self.timeout_seconds = min(self.timeout_seconds * 1.5, 3600)  # Max 1 hour
        
        logger.warning(
            "Circuit reopened after failed recovery",
            collector=self.collector_name,
            new_timeout=f"{self.timeout_seconds:.0f}s"
        )
    
    def force_open(self):
        """Manually open the circuit (for maintenance/testing)"""
        logger.warning(
            "Circuit breaker manually opened",
            collector=self.collector_name
        )
        self._open_circuit()
    
    def force_close(self):
        """Manually close the circuit (override failure state)"""
        logger.warning(
            "Circuit breaker manually closed",
            collector=self.collector_name
        )
        self._close_circuit()
    
    def reset(self):
        """Reset circuit breaker to initial state"""
        self.state = "closed"
        self.failure_count = 0
        self.consecutive_successes = 0
        self.last_failure_time = None
        self.last_state_change = None
        self.half_open_attempts = 0
        self.half_open_successes = 0
        
        logger.info(
            "Circuit breaker reset",
            collector=self.collector_name
        )
        
    def get_status(self) -> Dict[str, Any]:
        """Get comprehensive circuit breaker status"""
        status = {
            "state": self.state,
            "collector_name": self.collector_name,
            "failure_count": self.failure_count,
            "consecutive_successes": self.consecutive_successes,
            "failure_threshold": self.failure_threshold,
            "timeout_seconds": self.timeout_seconds,
            "last_failure_time": self.last_failure_time.isoformat() if self.last_failure_time else None,
            "last_state_change": self.last_state_change.isoformat() if self.last_state_change else None,
        }
        
        # Add half-open specific info
        if self.state == "half-open":
            status["half_open"] = {
                "attempts": self.half_open_attempts,
                "successes": self.half_open_successes,
                "max_calls": self.half_open_max_calls,
                "success_threshold": self.half_open_success_threshold,
                "success_rate": self.half_open_successes / max(self.half_open_attempts, 1)
            }
        
        # Add statistics
        status["statistics"] = self.stats.copy()
        
        # Calculate health score
        total_calls = self.stats["total_successes"] + self.stats["total_failures"]
        if total_calls > 0:
            status["health_score"] = self.stats["total_successes"] / total_calls
        else:
            status["health_score"] = 1.0
        
        return status
    
    async def save_state_to_redis(self):
        """Save circuit breaker state to Redis for persistence"""
        if not self.redis_cache:
            return
        
        try:
            key = f"circuit_breaker:{self.collector_name}"
            state = {
                "state": self.state,
                "failure_count": self.failure_count,
                "consecutive_successes": self.consecutive_successes,
                "timeout_seconds": self.timeout_seconds,
                "last_failure_time": self.last_failure_time.isoformat() if self.last_failure_time else None,
                "last_state_change": self.last_state_change.isoformat() if self.last_state_change else None,
                "stats": self.stats
            }
            await self.redis_cache.set(key, state, ttl=86400)  # 24 hour TTL
        except Exception as e:
            logger.warning("Failed to save circuit breaker state to Redis", error=str(e))
    
    async def load_state_from_redis(self):
        """Load circuit breaker state from Redis"""
        if not self.redis_cache:
            return
        
        try:
            key = f"circuit_breaker:{self.collector_name}"
            state = await self.redis_cache.get(key)
            
            if state:
                self.state = state.get("state", "closed")
                self.failure_count = state.get("failure_count", 0)
                self.consecutive_successes = state.get("consecutive_successes", 0)
                self.timeout_seconds = state.get("timeout_seconds", self.timeout_seconds)
                
                if state.get("last_failure_time"):
                    self.last_failure_time = datetime.fromisoformat(state["last_failure_time"])
                
                if state.get("last_state_change"):
                    self.last_state_change = datetime.fromisoformat(state["last_state_change"])
                
                if state.get("stats"):
                    self.stats.update(state["stats"])
                
                logger.info(
                    "Loaded circuit breaker state from Redis",
                    state=self.state,
                    failure_count=self.failure_count,
                    collector=self.collector_name
                )
        except Exception as e:
            logger.warning("Failed to load circuit breaker state from Redis", error=str(e))


class RateLimiter:
    """
    Adaptive rate limiter for API calls with intelligent backoff and header parsing
    
    Features:
    - Dynamic rate adjustment based on API response headers
    - Exponential backoff on 429 (rate limit) errors
    - Per-endpoint rate limit tracking
    - Automatic recovery from rate limit violations
    - Redis-based state persistence (optional)
    """
    
    def __init__(
        self, 
        max_requests_per_second: float = 5.0,
        redis_cache=None,
        collector_name: str = "unknown"
    ):
        """
        Initialize adaptive rate limiter
        
        Args:
            max_requests_per_second: Initial maximum requests per second
            redis_cache: Optional Redis cache for state persistence
            collector_name: Name for logging and Redis keys
        """
        self.collector_name = collector_name
        self.max_requests_per_second = max_requests_per_second
        self.min_interval = 1.0 / max_requests_per_second
        self.last_request_time: Optional[datetime] = None
        self.request_count = 0
        self.total_wait_time = 0.0
        self.redis_cache = redis_cache
        
        # Per-endpoint tracking
        self.endpoint_limits: Dict[str, Dict[str, Any]] = {}  # endpoint -> {limit, remaining, reset_time}
        
        # 429 error handling
        self.rate_limit_violations = 0
        self.last_violation_time: Optional[datetime] = None
        self.backoff_multiplier = 1.0  # Increases on violations
        self.max_backoff_multiplier = 16.0  # Max 16x slowdown
        
        # Statistics
        self.stats = {
            "total_requests": 0,
            "rate_limit_hits": 0,
            "adaptive_adjustments_up": 0,
            "adaptive_adjustments_down": 0,
            "current_rate": max_requests_per_second,
            "backoff_multiplier": 1.0
        }
        
    async def wait(self, endpoint: Optional[str] = None):
        """
        Wait if necessary to respect rate limit
        
        Args:
            endpoint: Optional endpoint path for per-endpoint tracking
        """
        # Check per-endpoint limit if available
        if endpoint and endpoint in self.endpoint_limits:
            endpoint_info = self.endpoint_limits[endpoint]
            if endpoint_info['remaining'] <= 0 and endpoint_info['reset_time']:
                # Wait until reset time
                now = datetime.now(timezone.utc)
                if endpoint_info['reset_time'] > now:
                    wait_time = (endpoint_info['reset_time'] - now).total_seconds()
                    logger.info(
                        "Waiting for endpoint rate limit reset",
                        endpoint=endpoint,
                        wait_time=wait_time,
                        collector=self.collector_name
                    )
                    await asyncio.sleep(wait_time)
                    # Reset counter after wait
                    endpoint_info['remaining'] = endpoint_info['limit']
        
        # Apply global rate limit with backoff multiplier
        if self.last_request_time:
            elapsed = (datetime.now(timezone.utc) - self.last_request_time).total_seconds()
            adjusted_interval = self.min_interval * self.backoff_multiplier
            
            if elapsed < adjusted_interval:
                wait_time = adjusted_interval - elapsed
                self.total_wait_time += wait_time
                await asyncio.sleep(wait_time)
                
        self.last_request_time = datetime.now(timezone.utc)
        self.request_count += 1
        self.stats["total_requests"] += 1
        
        # Decrease remaining count for endpoint
        if endpoint and endpoint in self.endpoint_limits:
            self.endpoint_limits[endpoint]['remaining'] -= 1
    
    def parse_rate_limit_headers(self, headers: Dict[str, str], endpoint: Optional[str] = None):
        """
        Parse rate limit information from API response headers
        
        Supports common header formats:
        - X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset
        - X-Rate-Limit-Limit, X-Rate-Limit-Remaining, X-Rate-Limit-Reset
        - RateLimit-Limit, RateLimit-Remaining, RateLimit-Reset
        - Retry-After (for 429 responses)
        
        Args:
            headers: Response headers dict
            endpoint: Optional endpoint path for per-endpoint tracking
        """
        # Normalize header keys to lowercase for case-insensitive matching
        headers_lower = {k.lower(): v for k, v in headers.items()}
        
        # Try different header formats
        limit_keys = ['x-ratelimit-limit', 'x-rate-limit-limit', 'ratelimit-limit']
        remaining_keys = ['x-ratelimit-remaining', 'x-rate-limit-remaining', 'ratelimit-remaining']
        reset_keys = ['x-ratelimit-reset', 'x-rate-limit-reset', 'ratelimit-reset']
        retry_after_keys = ['retry-after']
        
        limit = None
        remaining = None
        reset_time = None
        retry_after = None
        
        # Extract values
        for key in limit_keys:
            if key in headers_lower:
                try:
                    limit = int(headers_lower[key])
                    break
                except ValueError:
                    pass
        
        for key in remaining_keys:
            if key in headers_lower:
                try:
                    remaining = int(headers_lower[key])
                    break
                except ValueError:
                    pass
        
        for key in reset_keys:
            if key in headers_lower:
                try:
                    reset_timestamp = int(headers_lower[key])
                    reset_time = datetime.fromtimestamp(reset_timestamp, tz=timezone.utc)
                    break
                except (ValueError, OSError):
                    pass
        
        for key in retry_after_keys:
            if key in headers_lower:
                try:
                    retry_after = int(headers_lower[key])
                    break
                except ValueError:
                    pass
        
        # Store per-endpoint limits if we have data
        if endpoint and limit is not None and remaining is not None:
            if endpoint not in self.endpoint_limits:
                self.endpoint_limits[endpoint] = {}
            
            self.endpoint_limits[endpoint].update({
                'limit': limit,
                'remaining': remaining,
                'reset_time': reset_time,
                'last_updated': datetime.now(timezone.utc)
            })
            
            logger.debug(
                "Updated endpoint rate limits",
                endpoint=endpoint,
                limit=limit,
                remaining=remaining,
                reset_time=reset_time.isoformat() if reset_time else None,
                collector=self.collector_name
            )
            
            # Adjust global rate if we're approaching endpoint limit
            if remaining is not None and limit is not None:
                usage_percent = (limit - remaining) / limit if limit > 0 else 1.0
                if usage_percent > 0.8:  # More than 80% used
                    usage_pct = int(usage_percent * 100)
                    self._adjust_rate_down(f"Endpoint limit approaching ({usage_pct}%)")
        
        # Handle retry-after for 429 responses
        if retry_after is not None:
            self._handle_rate_limit_violation(retry_after)
            
    def _handle_rate_limit_violation(self, retry_after_seconds: int):
        """
        Handle 429 rate limit error with exponential backoff
        
        Args:
            retry_after_seconds: Seconds to wait before retry (from Retry-After header)
        """
        self.rate_limit_violations += 1
        self.last_violation_time = datetime.now(timezone.utc)
        self.stats["rate_limit_hits"] += 1
        
        # Exponential backoff: double the backoff multiplier
        self.backoff_multiplier = min(self.backoff_multiplier * 2.0, self.max_backoff_multiplier)
        self.stats["backoff_multiplier"] = self.backoff_multiplier
        
        # Also reduce base rate
        self.max_requests_per_second *= 0.5
        self.min_interval = 1.0 / max(self.max_requests_per_second, 0.1)  # Minimum 0.1 req/s
        self.stats["current_rate"] = self.max_requests_per_second
        
        logger.warning(
            "Rate limit violation detected - applying exponential backoff",
            retry_after=retry_after_seconds,
            backoff_multiplier=self.backoff_multiplier,
            new_rate=self.max_requests_per_second,
            violations_count=self.rate_limit_violations,
            collector=self.collector_name
        )
        
    def adjust_rate(self, response_time: float, status_code: int = 200):
        """
        Dynamically adjust rate based on response time and status code
        
        Args:
            response_time: API response time in seconds
            status_code: HTTP status code
        """
        # Handle 429 errors
        if status_code == 429:
            self._handle_rate_limit_violation(60)  # Default 60s retry
            return
        
        # Gradually recover from backoff if no recent violations
        if self.backoff_multiplier > 1.0 and self.last_violation_time:
            time_since_violation = (datetime.now(timezone.utc) - self.last_violation_time).total_seconds()
            if time_since_violation > 300:  # 5 minutes without violations
                self.backoff_multiplier = max(1.0, self.backoff_multiplier * 0.9)
                self.stats["backoff_multiplier"] = self.backoff_multiplier
                logger.info(
                    "Reducing backoff multiplier - no recent violations",
                    backoff_multiplier=self.backoff_multiplier,
                    collector=self.collector_name
                )
        
        # Adjust rate based on response time (only if not in backoff)
        if self.backoff_multiplier <= 1.1:  # Only adjust if near normal operation
            if response_time > 2.0:
                self._adjust_rate_down(f"High response time: {response_time:.2f}s")
            elif response_time < 0.5 and self.max_requests_per_second < 10.0:
                self._adjust_rate_up(f"Low response time: {response_time:.2f}s")
    
    def _adjust_rate_down(self, reason: str):
        """Reduce request rate"""
        old_rate = self.max_requests_per_second
        self.max_requests_per_second *= 0.8
        self.min_interval = 1.0 / self.max_requests_per_second
        self.stats["adaptive_adjustments_down"] += 1
        self.stats["current_rate"] = self.max_requests_per_second
        
        logger.info(
            "Rate limit adjusted down",
            reason=reason,
            old_rate=f"{old_rate:.2f}",
            new_rate=f"{self.max_requests_per_second:.2f}",
            collector=self.collector_name
        )
    
    def _adjust_rate_up(self, reason: str):
        """Increase request rate"""
        old_rate = self.max_requests_per_second
        self.max_requests_per_second *= 1.1
        self.min_interval = 1.0 / self.max_requests_per_second
        self.stats["adaptive_adjustments_up"] += 1
        self.stats["current_rate"] = self.max_requests_per_second
        
        logger.info(
            "Rate limit adjusted up",
            reason=reason,
            old_rate=f"{old_rate:.2f}",
            new_rate=f"{self.max_requests_per_second:.2f}",
            collector=self.collector_name
        )
            
    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive rate limiter statistics"""
        stats = self.stats.copy()
        stats.update({
            "max_requests_per_second": self.max_requests_per_second,
            "request_count": self.request_count,
            "total_wait_time": self.total_wait_time,
            "avg_wait_time": self.total_wait_time / max(self.request_count, 1),
            "backoff_multiplier": self.backoff_multiplier,
            "rate_limit_violations": self.rate_limit_violations,
            "last_violation": self.last_violation_time.isoformat() if self.last_violation_time else None,
            "endpoint_limits": {
                ep: {
                    'limit': info['limit'],
                    'remaining': info['remaining'],
                    'reset_time': info['reset_time'].isoformat() if info.get('reset_time') else None
                }
                for ep, info in self.endpoint_limits.items()
            }
        })
        return stats
    
    async def save_state_to_redis(self):
        """Save rate limiter state to Redis for persistence across restarts"""
        if not self.redis_cache:
            return
        
        try:
            key = f"rate_limiter:{self.collector_name}"
            state = {
                "max_requests_per_second": self.max_requests_per_second,
                "backoff_multiplier": self.backoff_multiplier,
                "rate_limit_violations": self.rate_limit_violations,
                "last_violation_time": self.last_violation_time.isoformat() if self.last_violation_time else None,
                "stats": self.stats
            }
            await self.redis_cache.set(key, state, ttl=86400)  # 24 hour TTL
        except Exception as e:
            logger.warning("Failed to save rate limiter state to Redis", error=str(e))
    
    async def load_state_from_redis(self):
        """Load rate limiter state from Redis"""
        if not self.redis_cache:
            return
        
        try:
            key = f"rate_limiter:{self.collector_name}"
            state = await self.redis_cache.get(key)
            
            if state:
                self.max_requests_per_second = state.get("max_requests_per_second", self.max_requests_per_second)
                self.min_interval = 1.0 / self.max_requests_per_second
                self.backoff_multiplier = state.get("backoff_multiplier", 1.0)
                self.rate_limit_violations = state.get("rate_limit_violations", 0)
                
                if state.get("last_violation_time"):
                    self.last_violation_time = datetime.fromisoformat(state["last_violation_time"])
                
                if state.get("stats"):
                    self.stats.update(state["stats"])
                
                logger.info(
                    "Loaded rate limiter state from Redis",
                    rate=self.max_requests_per_second,
                    backoff=self.backoff_multiplier,
                    collector=self.collector_name
                )
        except Exception as e:
            logger.warning("Failed to load rate limiter state from Redis", error=str(e))


class OnChainCollector:
    """Base class for on-chain data collectors with adaptive rate limiting"""
    
    def __init__(
        self,
        database: Database,
        api_key: str,
        api_url: str,
        collector_name: str,
        rate_limit: float = 5.0,
        timeout: int = 30,
        redis_cache=None
    ):
        """
        Initialize on-chain collector
        
        Args:
            database: Database instance for storage
            api_key: API key for the provider
            api_url: Base URL for the API
            collector_name: Name of the collector (for logging/monitoring)
            rate_limit: Initial maximum requests per second
            timeout: Request timeout in seconds
            redis_cache: Optional Redis cache for rate limiter state persistence
        """
        self.database = database
        self.api_key = api_key
        self.api_url = api_url.rstrip('/')
        self.collector_name = collector_name
        self.session: Optional[aiohttp.ClientSession] = None
        self.redis_cache = redis_cache
        
        # Initialize rate limiter and circuit breaker with Redis support
        self.rate_limiter = RateLimiter(
            max_requests_per_second=rate_limit,
            redis_cache=redis_cache,
            collector_name=collector_name
        )
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=5,
            timeout_seconds=300,
            half_open_max_calls=3,
            half_open_success_threshold=2,
            collector_name=collector_name,
            redis_cache=redis_cache
        )
        
        # Request configuration
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.max_retries = 3
        self.retry_delay = 1.0  # Initial retry delay in seconds
        
        # Statistics
        self.stats = {
            "requests_total": 0,
            "requests_success": 0,
            "requests_failed": 0,
            "data_points_collected": 0,
            "last_collection_time": None,
            "last_error": None
        }
        
    async def __aenter__(self):
        """Async context manager entry"""
        await self.connect()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.disconnect()
        
    async def connect(self):
        """Initialize HTTP session and load rate limiter and circuit breaker state"""
        if not self.session:
            self.session = aiohttp.ClientSession(timeout=self.timeout)
            # Load previous states from Redis if available
            await self.rate_limiter.load_state_from_redis()
            await self.circuit_breaker.load_state_from_redis()
            logger.info(f"{self.collector_name} collector connected")
            
    async def disconnect(self):
        """Close HTTP session and save rate limiter and circuit breaker state"""
        if self.session:
            # Save states to Redis before disconnecting
            await self.rate_limiter.save_state_to_redis()
            await self.circuit_breaker.save_state_to_redis()
            await self.session.close()
            self.session = None
            logger.info(f"{self.collector_name} collector disconnected")
            
    async def _make_request(
        self,
        endpoint: str,
        params: Optional[Dict] = None,
        headers: Optional[Dict] = None,
        method: str = "GET"
    ) -> Optional[Dict]:
        """
        Make HTTP request with adaptive rate limiting, header parsing, retry logic, and circuit breaker
        
        Args:
            endpoint: API endpoint (relative to base URL)
            params: Query parameters
            headers: Request headers
            method: HTTP method
            
        Returns:
            Response data as dict, or None if failed
        """
        # Check circuit breaker
        if not self.circuit_breaker.can_attempt():
            logger.warning(
                f"{self.collector_name} request blocked by circuit breaker",
                endpoint=endpoint
            )
            await self._log_health(CollectorStatus.CIRCUIT_OPEN, "Circuit breaker open")
            return None
            
        if not self.session:
            await self.connect()
            
        # Apply rate limiting with endpoint tracking
        await self.rate_limiter.wait(endpoint=endpoint)
        
        # Build request
        url = f"{self.api_url}/{endpoint.lstrip('/')}"
        headers = headers or {}
        params = params or {}
        
        # Add authentication
        if self.api_key:
            headers["X-API-Key"] = self.api_key
            
        # Retry loop
        for attempt in range(self.max_retries):
            try:
                start_time = datetime.now(timezone.utc)
                
                async with self.session.request(
                    method,
                    url,
                    headers=headers,
                    params=params
                ) as response:
                    response_time = (datetime.now(timezone.utc) - start_time).total_seconds()
                    
                    self.stats["requests_total"] += 1
                    
                    # Parse rate limit headers from response
                    self.rate_limiter.parse_rate_limit_headers(dict(response.headers), endpoint=endpoint)
                    
                    # Adjust rate based on response time and status
                    self.rate_limiter.adjust_rate(response_time, status_code=response.status)
                    
                    if response.status == 200:
                        data = await response.json()
                        
                        # Record success
                        self.circuit_breaker.record_success()
                        self.stats["requests_success"] += 1
                        
                        logger.debug(
                            f"{self.collector_name} request successful",
                            endpoint=endpoint,
                            status=response.status,
                            response_time=f"{response_time:.3f}s"
                        )
                        
                        return data
                        
                    elif response.status == 429:
                        # Rate limit hit - exponential backoff handled by rate limiter
                        retry_after = response.headers.get("Retry-After", "60")
                        try:
                            retry_seconds = int(retry_after)
                        except ValueError:
                            retry_seconds = 60
                        
                        self.rate_limiter._handle_rate_limit_violation(retry_seconds)
                        
                        logger.warning(
                            f"{self.collector_name} rate limit hit - backing off",
                            endpoint=endpoint,
                            retry_after=retry_seconds,
                            attempt=attempt + 1,
                            backoff_multiplier=self.rate_limiter.backoff_multiplier
                        )
                        
                        # Wait before retry
                        await asyncio.sleep(retry_seconds)
                        continue
                        
                    else:
                        error_text = await response.text()
                        logger.error(
                            f"{self.collector_name} request failed",
                            endpoint=endpoint,
                            status=response.status,
                            error=error_text[:200]  # Truncate long errors
                        )
                        
                        # Record failure
                        self.circuit_breaker.record_failure()
                        self.stats["requests_failed"] += 1
                        self.stats["last_error"] = error_text
                        
                        # Don't retry on client errors (4xx except 429)
                        if 400 <= response.status < 500 and response.status != 429:
                            break
                            
            except asyncio.TimeoutError:
                logger.error(
                    f"{self.collector_name} request timeout",
                    endpoint=endpoint,
                    attempt=attempt + 1
                )
                self.circuit_breaker.record_failure()
                self.stats["requests_failed"] += 1
                
            except Exception as e:
                logger.error(
                    f"{self.collector_name} request error",
                    endpoint=endpoint,
                    attempt=attempt + 1,
                    error=str(e)
                )
                self.circuit_breaker.record_failure()
                self.stats["requests_failed"] += 1
                self.stats["last_error"] = str(e)
                
            # Exponential backoff for retries
            if attempt < self.max_retries - 1:
                delay = self.retry_delay * (2 ** attempt)
                await asyncio.sleep(delay)
                
        # All retries exhausted
        await self._log_health(
            CollectorStatus.FAILED,
            f"Request failed after {self.max_retries} attempts"
        )
        return None
        
    async def _log_health(self, status: CollectorStatus, message: str = ""):
        """
        Log collector health status to database
        
        Args:
            status: Collector status
            message: Optional status message
        """
        try:
            await self.database.log_collector_health(
                collector_name=self.collector_name,
                status=status.value,
                error_msg=message if status != CollectorStatus.HEALTHY else None
            )
        except Exception as e:
            logger.error(
                f"Failed to log collector health",
                collector=self.collector_name,
                error=str(e)
            )
            
    async def get_status(self) -> Dict[str, Any]:
        """Get collector status and statistics"""
        return {
            "collector_name": self.collector_name,
            "status": (
                CollectorStatus.CIRCUIT_OPEN.value
                if self.circuit_breaker.state == "open"
                else CollectorStatus.HEALTHY.value
                if self.stats["requests_failed"] == 0 or
                   self.stats["requests_success"] / max(self.stats["requests_total"], 1) > 0.9
                else CollectorStatus.DEGRADED.value
            ),
            "stats": self.stats,
            "rate_limiter": self.rate_limiter.get_stats(),
            "circuit_breaker": self.circuit_breaker.get_status()
        }
        
    async def collect(self, **kwargs) -> bool:
        """
        Collect data from the provider (to be implemented by subclasses)
        
        Returns:
            True if collection successful, False otherwise
        """
        raise NotImplementedError("Subclasses must implement collect() method")
