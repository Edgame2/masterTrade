"""
Adaptive Rate Limiter Implementation

Intelligent rate limiting for API data collectors with automatic adaptation to rate limit headers.
Extracted from onchain_collector.py to provide reusable rate limiting functionality
for all data collectors in the system.

Features:
- Adaptive rate adjustment based on API headers (X-RateLimit-*, Retry-After)
- Per-endpoint rate tracking and management
- Exponential backoff for 429 (Too Many Requests) responses
- Configurable rate windows (per second, minute, hour, day)
- Automatic rate recovery after cooldown periods
- Redis state persistence for coordinated rate limiting across instances
- Detailed statistics and health metrics

Usage:
    from adaptive_limiter import RateLimiter
    
    limiter = RateLimiter(
        name="my_api",
        default_rate=10.0,  # 10 requests per second
        redis_cache=redis_client
    )
    
    await limiter.wait(endpoint="/api/data")
    # Make API call
    
    # After getting response with rate limit headers:
    limiter.parse_rate_limit_headers(response.headers, endpoint="/api/data")
"""

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, Any
from collections import deque
import structlog

logger = structlog.get_logger()


class RateLimiter:
    """
    Adaptive rate limiter with automatic adjustment based on API feedback
    
    Tracks request timing per endpoint and automatically adjusts rates based on:
    - X-RateLimit-* headers (standard rate limit info)
    - Retry-After headers (explicit cooldown directives)
    - 429 responses (exponential backoff)
    - Successful requests (gradual rate recovery)
    
    Attributes:
        name: Identifier for logging and Redis keys
        default_rate: Base requests per second (can be adjusted dynamically)
        window_size: Size of sliding window for rate calculation (seconds)
        redis_cache: Optional Redis client for distributed rate limit coordination
        endpoints: Per-endpoint tracking with individual rates and request history
    """
    
    def __init__(
        self,
        name: str = "unknown",
        default_rate: float = 10.0,  # requests per second
        window_size: int = 60,  # 1 minute sliding window
        max_rate: float = 100.0,  # Maximum requests per second
        min_rate: float = 0.1,  # Minimum requests per second (aggressive throttle)
        redis_cache=None
    ):
        """
        Initialize adaptive rate limiter
        
        Args:
            name: Identifier for this rate limiter (API name, collector name, etc.)
            default_rate: Initial requests per second (default: 10.0)
            window_size: Sliding window size in seconds (default: 60)
            max_rate: Maximum allowed rate (default: 100.0 req/s)
            min_rate: Minimum rate during aggressive throttling (default: 0.1 req/s)
            redis_cache: Optional Redis cache for distributed coordination
        """
        self.name = name
        self.default_rate = default_rate
        self.current_rate = default_rate
        self.window_size = window_size
        self.max_rate = max_rate
        self.min_rate = min_rate
        self.redis_cache = redis_cache
        
        # Per-endpoint tracking
        self.endpoints: Dict[str, Dict[str, Any]] = {}
        
        # Global request history (for fallback when endpoint not specified)
        self.request_times = deque(maxlen=1000)
        
        # Rate limit violation tracking
        self.violations = 0
        self.last_violation: Optional[datetime] = None
        self.backoff_until: Optional[datetime] = None
        self.backoff_multiplier = 1.0
        
        # Statistics
        self.stats = {
            "total_requests": 0,
            "total_violations": 0,
            "total_wait_time": 0.0,  # seconds
            "rate_adjustments": 0,
            "min_rate_seen": default_rate,
            "max_rate_seen": default_rate,
            "endpoints_tracked": 0
        }
        
    def _get_endpoint_data(self, endpoint: Optional[str] = None) -> Dict[str, Any]:
        """
        Get or create endpoint tracking data
        
        Args:
            endpoint: API endpoint path (default: None for global tracking)
            
        Returns:
            Endpoint data dict with rate, history, and metadata
        """
        if endpoint is None:
            endpoint = "__global__"
        
        if endpoint not in self.endpoints:
            self.endpoints[endpoint] = {
                "rate": self.default_rate,
                "request_times": deque(maxlen=1000),
                "last_request": None,
                "rate_limit_remaining": None,
                "rate_limit_reset": None,
                "violations": 0,
                "last_violation": None,
                "backoff_until": None,
                "requests_made": 0
            }
            self.stats["endpoints_tracked"] = len(self.endpoints)
        
        return self.endpoints[endpoint]
    
    async def wait(self, endpoint: Optional[str] = None):
        """
        Wait if necessary to respect rate limits
        
        Checks both endpoint-specific and global rate limits, enforces backoff periods,
        and tracks request timing for adaptive adjustment.
        
        Args:
            endpoint: API endpoint for endpoint-specific rate limiting (optional)
        """
        ep_data = self._get_endpoint_data(endpoint)
        now = datetime.now(timezone.utc)
        
        # Check if we're in a backoff period
        if ep_data["backoff_until"] and now < ep_data["backoff_until"]:
            wait_seconds = (ep_data["backoff_until"] - now).total_seconds()
            logger.info(
                "Rate limiter in backoff period",
                limiter=self.name,
                endpoint=endpoint,
                wait_seconds=f"{wait_seconds:.1f}s"
            )
            await asyncio.sleep(wait_seconds)
            ep_data["backoff_until"] = None
            now = datetime.now(timezone.utc)
        
        # Check if rate limit reset time has passed
        if ep_data["rate_limit_reset"] and now >= ep_data["rate_limit_reset"]:
            # Reset time passed, clear remaining count
            ep_data["rate_limit_remaining"] = None
            ep_data["rate_limit_reset"] = None
        
        # If we know we've hit the limit, wait until reset
        if ep_data["rate_limit_remaining"] is not None and ep_data["rate_limit_remaining"] <= 0:
            if ep_data["rate_limit_reset"]:
                wait_seconds = (ep_data["rate_limit_reset"] - now).total_seconds()
                if wait_seconds > 0:
                    logger.info(
                        "Rate limit exhausted, waiting for reset",
                        limiter=self.name,
                        endpoint=endpoint,
                        wait_seconds=f"{wait_seconds:.1f}s"
                    )
                    self.stats["total_wait_time"] += wait_seconds
                    await asyncio.sleep(wait_seconds)
        
        # Calculate time since last request
        if ep_data["last_request"]:
            elapsed = (now - ep_data["last_request"]).total_seconds()
            min_interval = 1.0 / ep_data["rate"]  # seconds between requests
            
            if elapsed < min_interval:
                wait_time = min_interval - elapsed
                logger.debug(
                    "Rate limiting request",
                    limiter=self.name,
                    endpoint=endpoint,
                    wait_time=f"{wait_time:.3f}s",
                    current_rate=f"{ep_data['rate']:.2f} req/s"
                )
                self.stats["total_wait_time"] += wait_time
                await asyncio.sleep(wait_time)
        
        # Record request
        now = datetime.now(timezone.utc)
        ep_data["last_request"] = now
        ep_data["request_times"].append(now)
        ep_data["requests_made"] += 1
        self.request_times.append(now)
        self.stats["total_requests"] += 1
    
    def parse_rate_limit_headers(self, headers: Dict[str, str], endpoint: Optional[str] = None):
        """
        Parse rate limit information from API response headers
        
        Supports multiple header formats:
        - X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset (most common)
        - RateLimit-Limit, RateLimit-Remaining, RateLimit-Reset (alternative)
        - Retry-After (explicit wait time in seconds or HTTP date)
        
        Automatically adjusts rates based on headers and tracks reset times.
        
        Args:
            headers: HTTP response headers dict
            endpoint: Endpoint that generated this response (for endpoint-specific tracking)
        """
        ep_data = self._get_endpoint_data(endpoint)
        
        # Parse X-RateLimit-* headers (most common format)
        if "X-RateLimit-Limit" in headers or "x-ratelimit-limit" in headers:
            try:
                limit = int(headers.get("X-RateLimit-Limit") or headers.get("x-ratelimit-limit"))
                remaining = int(headers.get("X-RateLimit-Remaining") or headers.get("x-ratelimit-remaining", 0))
                reset = int(headers.get("X-RateLimit-Reset") or headers.get("x-ratelimit-reset", 0))
                
                ep_data["rate_limit_remaining"] = remaining
                
                if reset > 0:
                    # Reset is typically a Unix timestamp
                    ep_data["rate_limit_reset"] = datetime.fromtimestamp(reset, tz=timezone.utc)
                
                # Adjust rate based on remaining quota
                if limit > 0:
                    # Calculate optimal rate to spread requests evenly
                    if ep_data["rate_limit_reset"]:
                        window_seconds = (ep_data["rate_limit_reset"] - datetime.now(timezone.utc)).total_seconds()
                        if window_seconds > 0:
                            optimal_rate = remaining / window_seconds
                            # Use conservative rate (70% of optimal to leave buffer)
                            new_rate = max(self.min_rate, min(optimal_rate * 0.7, self.max_rate))
                            
                            if abs(new_rate - ep_data["rate"]) > 0.1:  # Only adjust if significant change
                                old_rate = ep_data["rate"]
                                ep_data["rate"] = new_rate
                                self.stats["rate_adjustments"] += 1
                                self.stats["min_rate_seen"] = min(self.stats["min_rate_seen"], new_rate)
                                self.stats["max_rate_seen"] = max(self.stats["max_rate_seen"], new_rate)
                                
                                logger.debug(
                                    "Adjusted rate based on headers",
                                    limiter=self.name,
                                    endpoint=endpoint,
                                    old_rate=f"{old_rate:.2f}",
                                    new_rate=f"{new_rate:.2f}",
                                    remaining=remaining,
                                    limit=limit
                                )
            except (ValueError, TypeError) as e:
                logger.warning("Failed to parse rate limit headers", error=str(e))
        
        # Parse RateLimit-* headers (alternative format)
        elif "RateLimit-Limit" in headers or "ratelimit-limit" in headers:
            try:
                limit = int(headers.get("RateLimit-Limit") or headers.get("ratelimit-limit"))
                remaining = int(headers.get("RateLimit-Remaining") or headers.get("ratelimit-remaining", 0))
                reset = headers.get("RateLimit-Reset") or headers.get("ratelimit-reset")
                
                ep_data["rate_limit_remaining"] = remaining
                
                if reset:
                    # Parse reset time (could be timestamp or seconds)
                    try:
                        reset_ts = int(reset)
                        ep_data["rate_limit_reset"] = datetime.fromtimestamp(reset_ts, tz=timezone.utc)
                    except ValueError:
                        # Might be seconds from now
                        ep_data["rate_limit_reset"] = datetime.now(timezone.utc) + timedelta(seconds=int(reset))
                        
            except (ValueError, TypeError) as e:
                logger.warning("Failed to parse RateLimit headers", error=str(e))
        
        # Parse Retry-After header (explicit wait time)
        if "Retry-After" in headers or "retry-after" in headers:
            retry_after = headers.get("Retry-After") or headers.get("retry-after")
            try:
                # Could be seconds or HTTP date
                wait_seconds = int(retry_after)
                ep_data["backoff_until"] = datetime.now(timezone.utc) + timedelta(seconds=wait_seconds)
                
                logger.info(
                    "Retry-After header received",
                    limiter=self.name,
                    endpoint=endpoint,
                    wait_seconds=wait_seconds
                )
            except ValueError:
                # Try parsing as HTTP date
                try:
                    from email.utils import parsedate_to_datetime
                    retry_time = parsedate_to_datetime(retry_after)
                    ep_data["backoff_until"] = retry_time
                except:
                    logger.warning("Failed to parse Retry-After header", value=retry_after)
    
    def adjust_rate(self, factor: float, endpoint: Optional[str] = None):
        """
        Manually adjust rate by a multiplicative factor
        
        Args:
            factor: Multiplier for current rate (e.g., 0.5 for half speed, 2.0 for double)
            endpoint: Endpoint to adjust (None for all endpoints)
        """
        if endpoint:
            ep_data = self._get_endpoint_data(endpoint)
            old_rate = ep_data["rate"]
            ep_data["rate"] = max(self.min_rate, min(ep_data["rate"] * factor, self.max_rate))
            
            logger.info(
                "Manually adjusted endpoint rate",
                limiter=self.name,
                endpoint=endpoint,
                old_rate=f"{old_rate:.2f}",
                new_rate=f"{ep_data['rate']:.2f}",
                factor=factor
            )
        else:
            # Adjust all endpoints
            for ep, ep_data in self.endpoints.items():
                old_rate = ep_data["rate"]
                ep_data["rate"] = max(self.min_rate, min(ep_data["rate"] * factor, self.max_rate))
                
            logger.info(
                "Manually adjusted all endpoint rates",
                limiter=self.name,
                factor=factor,
                endpoints_affected=len(self.endpoints)
            )
        
        self.stats["rate_adjustments"] += 1
    
    def _handle_rate_limit_violation(self, endpoint: Optional[str] = None, backoff_seconds: Optional[int] = None):
        """
        Handle 429 (Too Many Requests) or similar rate limit violation
        
        Implements exponential backoff with configurable multiplier.
        
        Args:
            endpoint: Endpoint that triggered violation (None for global)
            backoff_seconds: Explicit backoff time from Retry-After header (optional)
        """
        ep_data = self._get_endpoint_data(endpoint)
        now = datetime.now(timezone.utc)
        
        ep_data["violations"] += 1
        ep_data["last_violation"] = now
        self.violations += 1
        self.last_violation = now
        self.stats["total_violations"] += 1
        
        # Calculate backoff time
        if backoff_seconds:
            # Use explicit backoff from Retry-After
            wait_seconds = backoff_seconds
        else:
            # Exponential backoff: 2^violations seconds, capped at 1 hour
            wait_seconds = min(2 ** ep_data["violations"], 3600)
        
        ep_data["backoff_until"] = now + timedelta(seconds=wait_seconds)
        
        # Reduce rate aggressively (to 10% of current)
        old_rate = ep_data["rate"]
        ep_data["rate"] = max(self.min_rate, ep_data["rate"] * 0.1)
        self.stats["rate_adjustments"] += 1
        self.stats["min_rate_seen"] = min(self.stats["min_rate_seen"], ep_data["rate"])
        
        logger.warning(
            "Rate limit violation detected",
            limiter=self.name,
            endpoint=endpoint,
            violations=ep_data["violations"],
            backoff_seconds=wait_seconds,
            old_rate=f"{old_rate:.2f}",
            new_rate=f"{ep_data['rate']:.2f}"
        )
    
    def record_429(self, endpoint: Optional[str] = None, retry_after: Optional[int] = None):
        """
        Record a 429 (Too Many Requests) response
        
        Args:
            endpoint: Endpoint that returned 429
            retry_after: Value from Retry-After header (seconds)
        """
        self._handle_rate_limit_violation(endpoint, retry_after)
    
    def get_current_rate(self, endpoint: Optional[str] = None) -> float:
        """
        Get current rate limit for endpoint
        
        Args:
            endpoint: Endpoint to check (None for global)
            
        Returns:
            Current requests per second rate
        """
        ep_data = self._get_endpoint_data(endpoint)
        return ep_data["rate"]
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get comprehensive rate limiter statistics
        
        Returns:
            Dict with rates, usage, violations, and per-endpoint breakdown
        """
        stats = {
            "limiter_name": self.name,
            "default_rate": self.default_rate,
            "current_global_rate": self.current_rate,
            "total_requests": self.stats["total_requests"],
            "total_violations": self.stats["total_violations"],
            "total_wait_time": f"{self.stats['total_wait_time']:.2f}s",
            "rate_adjustments": self.stats["rate_adjustments"],
            "min_rate_seen": f"{self.stats['min_rate_seen']:.2f} req/s",
            "max_rate_seen": f"{self.stats['max_rate_seen']:.2f} req/s",
            "endpoints_tracked": len(self.endpoints),
            "endpoints": {}
        }
        
        # Add per-endpoint stats
        for endpoint, ep_data in self.endpoints.items():
            if endpoint == "__global__":
                endpoint_name = "global"
            else:
                endpoint_name = endpoint
            
            stats["endpoints"][endpoint_name] = {
                "rate": f"{ep_data['rate']:.2f} req/s",
                "requests_made": ep_data["requests_made"],
                "violations": ep_data["violations"],
                "rate_limit_remaining": ep_data["rate_limit_remaining"],
                "in_backoff": ep_data["backoff_until"] is not None and datetime.now(timezone.utc) < ep_data["backoff_until"]
            }
            
            if ep_data["backoff_until"]:
                stats["endpoints"][endpoint_name]["backoff_until"] = ep_data["backoff_until"].isoformat()
        
        return stats
    
    async def save_state_to_redis(self):
        """Save rate limiter state to Redis for distributed coordination"""
        if not self.redis_cache:
            return
        
        try:
            key = f"rate_limiter:{self.name}"
            state = {
                "current_rate": self.current_rate,
                "violations": self.violations,
                "last_violation": self.last_violation.isoformat() if self.last_violation else None,
                "backoff_until": self.backoff_until.isoformat() if self.backoff_until else None,
                "stats": self.stats,
                "endpoints": {}
            }
            
            # Save per-endpoint state
            for endpoint, ep_data in self.endpoints.items():
                state["endpoints"][endpoint] = {
                    "rate": ep_data["rate"],
                    "requests_made": ep_data["requests_made"],
                    "violations": ep_data["violations"],
                    "last_violation": ep_data["last_violation"].isoformat() if ep_data["last_violation"] else None,
                    "backoff_until": ep_data["backoff_until"].isoformat() if ep_data["backoff_until"] else None,
                    "rate_limit_remaining": ep_data["rate_limit_remaining"],
                    "rate_limit_reset": ep_data["rate_limit_reset"].isoformat() if ep_data["rate_limit_reset"] else None
                }
            
            await self.redis_cache.set(key, state, ttl=3600)  # 1 hour TTL
            logger.debug("Saved rate limiter state to Redis", limiter=self.name)
        except Exception as e:
            logger.warning("Failed to save rate limiter state to Redis", error=str(e))
    
    async def load_state_from_redis(self):
        """Load rate limiter state from Redis"""
        if not self.redis_cache:
            return
        
        try:
            key = f"rate_limiter:{self.name}"
            state = await self.redis_cache.get(key)
            
            if state:
                self.current_rate = state.get("current_rate", self.default_rate)
                self.violations = state.get("violations", 0)
                
                if state.get("last_violation"):
                    self.last_violation = datetime.fromisoformat(state["last_violation"])
                
                if state.get("backoff_until"):
                    self.backoff_until = datetime.fromisoformat(state["backoff_until"])
                
                if state.get("stats"):
                    self.stats.update(state["stats"])
                
                # Load per-endpoint state
                for endpoint, ep_state in state.get("endpoints", {}).items():
                    ep_data = self._get_endpoint_data(endpoint)
                    ep_data["rate"] = ep_state.get("rate", self.default_rate)
                    ep_data["requests_made"] = ep_state.get("requests_made", 0)
                    ep_data["violations"] = ep_state.get("violations", 0)
                    ep_data["rate_limit_remaining"] = ep_state.get("rate_limit_remaining")
                    
                    if ep_state.get("last_violation"):
                        ep_data["last_violation"] = datetime.fromisoformat(ep_state["last_violation"])
                    
                    if ep_state.get("backoff_until"):
                        ep_data["backoff_until"] = datetime.fromisoformat(ep_state["backoff_until"])
                    
                    if ep_state.get("rate_limit_reset"):
                        ep_data["rate_limit_reset"] = datetime.fromisoformat(ep_state["rate_limit_reset"])
                
                logger.info(
                    "Loaded rate limiter state from Redis",
                    limiter=self.name,
                    current_rate=f"{self.current_rate:.2f}",
                    violations=self.violations,
                    endpoints=len(self.endpoints)
                )
        except Exception as e:
            logger.warning("Failed to load rate limiter state from Redis", error=str(e))
