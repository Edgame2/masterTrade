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
import structlog

from database import Database
from circuit_breaker import CircuitBreaker, CollectorStatus
from adaptive_limiter import RateLimiter

logger = structlog.get_logger()

# CircuitBreaker and RateLimiter classes have been extracted to standalone modules
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
