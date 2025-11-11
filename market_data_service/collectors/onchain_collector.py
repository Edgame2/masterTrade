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
    """Circuit breaker pattern for collector failure handling"""
    
    def __init__(self, failure_threshold: int = 5, timeout_seconds: int = 300):
        """
        Initialize circuit breaker
        
        Args:
            failure_threshold: Number of failures before opening circuit
            timeout_seconds: Cooldown period before attempting recovery
        """
        self.failure_threshold = failure_threshold
        self.timeout_seconds = timeout_seconds
        self.failure_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.state = "closed"  # closed, open, half-open
        
    def record_success(self):
        """Record successful operation"""
        self.failure_count = 0
        self.state = "closed"
        
    def record_failure(self):
        """Record failed operation"""
        self.failure_count += 1
        self.last_failure_time = datetime.now(timezone.utc)
        
        if self.failure_count >= self.failure_threshold:
            self.state = "open"
            logger.warning(
                "Circuit breaker opened",
                failure_count=self.failure_count,
                timeout_seconds=self.timeout_seconds
            )
            
    def can_attempt(self) -> bool:
        """Check if operation can be attempted"""
        if self.state == "closed":
            return True
            
        if self.state == "open":
            # Check if cooldown period has elapsed
            if self.last_failure_time:
                elapsed = (datetime.now(timezone.utc) - self.last_failure_time).total_seconds()
                if elapsed >= self.timeout_seconds:
                    self.state = "half-open"
                    logger.info("Circuit breaker entering half-open state")
                    return True
            return False
            
        # half-open state - allow attempt
        return True
        
    def get_status(self) -> Dict[str, Any]:
        """Get circuit breaker status"""
        return {
            "state": self.state,
            "failure_count": self.failure_count,
            "last_failure_time": self.last_failure_time.isoformat() if self.last_failure_time else None,
            "timeout_seconds": self.timeout_seconds
        }


class RateLimiter:
    """Adaptive rate limiter for API calls"""
    
    def __init__(self, max_requests_per_second: float = 5.0):
        """
        Initialize rate limiter
        
        Args:
            max_requests_per_second: Maximum requests per second
        """
        self.max_requests_per_second = max_requests_per_second
        self.min_interval = 1.0 / max_requests_per_second
        self.last_request_time: Optional[datetime] = None
        self.request_count = 0
        self.total_wait_time = 0.0
        
    async def wait(self):
        """Wait if necessary to respect rate limit"""
        if self.last_request_time:
            elapsed = (datetime.now(timezone.utc) - self.last_request_time).total_seconds()
            if elapsed < self.min_interval:
                wait_time = self.min_interval - elapsed
                self.total_wait_time += wait_time
                await asyncio.sleep(wait_time)
                
        self.last_request_time = datetime.now(timezone.utc)
        self.request_count += 1
        
    def adjust_rate(self, response_time: float):
        """
        Adjust rate based on response time
        
        Args:
            response_time: API response time in seconds
        """
        # If response time is high, reduce rate
        if response_time > 2.0:
            self.max_requests_per_second *= 0.8
            self.min_interval = 1.0 / self.max_requests_per_second
            logger.info(
                "Rate limit adjusted down",
                new_rate=self.max_requests_per_second,
                response_time=response_time
            )
        # If response time is low and we have capacity, increase rate
        elif response_time < 0.5 and self.max_requests_per_second < 10.0:
            self.max_requests_per_second *= 1.1
            self.min_interval = 1.0 / self.max_requests_per_second
            logger.info(
                "Rate limit adjusted up",
                new_rate=self.max_requests_per_second,
                response_time=response_time
            )
            
    def get_stats(self) -> Dict[str, Any]:
        """Get rate limiter statistics"""
        return {
            "max_requests_per_second": self.max_requests_per_second,
            "request_count": self.request_count,
            "total_wait_time": self.total_wait_time,
            "avg_wait_time": self.total_wait_time / max(self.request_count, 1)
        }


class OnChainCollector:
    """Base class for on-chain data collectors"""
    
    def __init__(
        self,
        database: Database,
        api_key: str,
        api_url: str,
        collector_name: str,
        rate_limit: float = 5.0,
        timeout: int = 30
    ):
        """
        Initialize on-chain collector
        
        Args:
            database: Database instance for storage
            api_key: API key for the provider
            api_url: Base URL for the API
            collector_name: Name of the collector (for logging/monitoring)
            rate_limit: Maximum requests per second
            timeout: Request timeout in seconds
        """
        self.database = database
        self.api_key = api_key
        self.api_url = api_url.rstrip('/')
        self.collector_name = collector_name
        self.session: Optional[aiohttp.ClientSession] = None
        
        # Initialize rate limiter and circuit breaker
        self.rate_limiter = RateLimiter(rate_limit)
        self.circuit_breaker = CircuitBreaker()
        
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
        """Initialize HTTP session"""
        if not self.session:
            self.session = aiohttp.ClientSession(timeout=self.timeout)
            logger.info(f"{self.collector_name} collector connected")
            
    async def disconnect(self):
        """Close HTTP session"""
        if self.session:
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
        Make HTTP request with rate limiting, retry logic, and circuit breaker
        
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
            
        # Apply rate limiting
        await self.rate_limiter.wait()
        
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
                    
                    # Adjust rate based on response time
                    self.rate_limiter.adjust_rate(response_time)
                    
                    self.stats["requests_total"] += 1
                    
                    if response.status == 200:
                        data = await response.json()
                        
                        # Record success
                        self.circuit_breaker.record_success()
                        self.stats["requests_success"] += 1
                        
                        logger.debug(
                            f"{self.collector_name} request successful",
                            endpoint=endpoint,
                            status=response.status,
                            response_time=response_time
                        )
                        
                        return data
                        
                    elif response.status == 429:
                        # Rate limit hit - back off
                        retry_after = int(response.headers.get("Retry-After", 60))
                        logger.warning(
                            f"{self.collector_name} rate limit hit",
                            endpoint=endpoint,
                            retry_after=retry_after
                        )
                        await asyncio.sleep(retry_after)
                        
                    else:
                        error_text = await response.text()
                        logger.error(
                            f"{self.collector_name} request failed",
                            endpoint=endpoint,
                            status=response.status,
                            error=error_text
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
