"""
Base Collector Framework

Unified base class for all data collectors in the MasterTrade system.
Provides common functionality for HTTP-based data collection with resilience features.

Features:
- Standardized start/stop/backfill lifecycle management
- Integrated circuit breaker for failure handling
- Adaptive rate limiting with automatic adjustment
- Request retry logic with exponential backoff
- Health check and status reporting
- Statistics tracking
- Redis state persistence
- Async context manager support

Usage:
    from base_collector import BaseCollector
    
    class MyCollector(BaseCollector):
        async def collect_data(self):
            # Implement data collection logic
            data = await self._make_request("/api/endpoint")
            await self.store_data(data)
        
        async def backfill_historical(self, start_time, end_time):
            # Implement historical data backfill
            pass
    
    # Use collector
    async with MyCollector(database, config) as collector:
        await collector.start()
"""

import asyncio
from abc import ABC, abstractmethod
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, Any, List
import aiohttp
import structlog

from circuit_breaker import CircuitBreaker, CollectorStatus
from adaptive_limiter import RateLimiter

logger = structlog.get_logger()


class BaseCollector(ABC):
    """
    Abstract base class for all data collectors
    
    Provides common infrastructure for:
    - HTTP requests with rate limiting and circuit breaking
    - Lifecycle management (start, stop, backfill)
    - Health monitoring and status reporting
    - Statistics tracking
    - Redis state persistence
    
    Subclasses must implement:
    - collect_data(): Main data collection logic
    - backfill_historical(): Historical data retrieval
    - _validate_config(): Configuration validation
    """
    
    def __init__(
        self,
        database: Any,
        collector_name: str,
        api_url: Optional[str] = None,
        api_key: Optional[str] = None,
        rate_limit: float = 10.0,  # requests per second
        timeout: int = 30,
        redis_cache: Optional[Any] = None,
        config: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize base collector
        
        Args:
            database: Database instance for data storage
            collector_name: Unique identifier for this collector
            api_url: Base URL for API requests (optional)
            api_key: API key for authentication (optional)
            rate_limit: Maximum requests per second (default: 10.0)
            timeout: Request timeout in seconds (default: 30)
            redis_cache: Redis client for state persistence (optional)
            config: Additional configuration dict (optional)
        """
        self.database = database
        self.collector_name = collector_name
        self.api_url = api_url.rstrip('/') if api_url else None
        self.api_key = api_key
        self.redis_cache = redis_cache
        self.config = config or {}
        
        # Validate configuration
        self._validate_config()
        
        # HTTP session
        self.session: Optional[aiohttp.ClientSession] = None
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        
        # Resilience components
        self.rate_limiter = RateLimiter(
            name=collector_name,
            default_rate=rate_limit,
            redis_cache=redis_cache
        )
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=self.config.get('circuit_breaker_threshold', 5),
            timeout_seconds=self.config.get('circuit_breaker_timeout', 300),
            collector_name=collector_name,
            redis_cache=redis_cache
        )
        
        # Request retry configuration
        self.max_retries = self.config.get('max_retries', 3)
        self.retry_delay = self.config.get('retry_delay', 1.0)
        
        # State management
        self.is_running = False
        self.collection_task: Optional[asyncio.Task] = None
        self.collection_interval = self.config.get('collection_interval', 60)  # seconds
        
        # Statistics
        self.stats = {
            "collector_name": collector_name,
            "status": CollectorStatus.HEALTHY.value,
            "started_at": None,
            "last_collection": None,
            "last_success": None,
            "last_error": None,
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "data_points_collected": 0,
            "total_runtime": 0.0,  # seconds
            "collections_completed": 0
        }
    
    @abstractmethod
    def _validate_config(self):
        """
        Validate collector-specific configuration
        
        Raise ValueError if configuration is invalid.
        Should check required parameters, API keys, etc.
        """
        pass
    
    @abstractmethod
    async def collect_data(self) -> Dict[str, Any]:
        """
        Main data collection logic
        
        This is called periodically by the collection loop.
        Should fetch data from source and store in database.
        
        Returns:
            Dict with collection results:
            {
                "success": bool,
                "data_points": int,
                "errors": List[str],
                "metadata": Dict[str, Any]
            }
        """
        pass
    
    @abstractmethod
    async def backfill_historical(
        self,
        start_time: datetime,
        end_time: datetime,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Backfill historical data for a time range
        
        Args:
            start_time: Start of time range (inclusive)
            end_time: End of time range (inclusive)
            **kwargs: Additional backfill parameters
        
        Returns:
            Dict with backfill results:
            {
                "success": bool,
                "data_points": int,
                "time_range": {"start": str, "end": str},
                "errors": List[str]
            }
        """
        pass
    
    async def __aenter__(self):
        """Async context manager entry"""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.disconnect()
    
    async def connect(self):
        """
        Initialize HTTP session and load persisted state
        
        Called automatically when entering context manager or calling start().
        Loads circuit breaker and rate limiter state from Redis if available.
        """
        if not self.session:
            self.session = aiohttp.ClientSession(timeout=self.timeout)
            
            # Load previous state from Redis
            await self.rate_limiter.load_state_from_redis()
            await self.circuit_breaker.load_state_from_redis()
            
            logger.info(
                "Collector connected",
                collector=self.collector_name,
                api_url=self.api_url
            )
    
    async def disconnect(self):
        """
        Close HTTP session and save state
        
        Saves circuit breaker and rate limiter state to Redis before closing.
        """
        if self.is_running:
            await self.stop()
        
        if self.session:
            # Save state to Redis
            await self.rate_limiter.save_state_to_redis()
            await self.circuit_breaker.save_state_to_redis()
            
            await self.session.close()
            self.session = None
            
            logger.info(
                "Collector disconnected",
                collector=self.collector_name
            )
    
    async def start(self):
        """
        Start periodic data collection
        
        Launches background task that calls collect_data() at regular intervals.
        Interval configured via 'collection_interval' in config (default: 60 seconds).
        """
        if self.is_running:
            logger.warning(
                "Collector already running",
                collector=self.collector_name
            )
            return
        
        if not self.session:
            await self.connect()
        
        self.is_running = True
        self.stats["started_at"] = datetime.now(timezone.utc).isoformat()
        self.collection_task = asyncio.create_task(self._collection_loop())
        
        logger.info(
            "Collector started",
            collector=self.collector_name,
            interval=f"{self.collection_interval}s"
        )
    
    async def stop(self):
        """
        Stop periodic data collection
        
        Gracefully cancels collection task and waits for completion.
        """
        if not self.is_running:
            logger.warning(
                "Collector not running",
                collector=self.collector_name
            )
            return
        
        self.is_running = False
        
        if self.collection_task:
            self.collection_task.cancel()
            try:
                await self.collection_task
            except asyncio.CancelledError:
                pass
            self.collection_task = None
        
        logger.info(
            "Collector stopped",
            collector=self.collector_name
        )
    
    async def _collection_loop(self):
        """
        Background task for periodic data collection
        
        Runs continuously while is_running is True.
        Handles errors and updates statistics.
        """
        while self.is_running:
            try:
                collection_start = datetime.now(timezone.utc)
                
                # Perform data collection
                result = await self.collect_data()
                
                # Update statistics
                self.stats["last_collection"] = collection_start.isoformat()
                self.stats["collections_completed"] += 1
                
                if result.get("success"):
                    self.stats["last_success"] = collection_start.isoformat()
                    self.stats["data_points_collected"] += result.get("data_points", 0)
                    self.stats["status"] = CollectorStatus.HEALTHY.value
                else:
                    self.stats["last_error"] = result.get("errors", ["Unknown error"])
                    self.stats["status"] = CollectorStatus.DEGRADED.value
                
                # Calculate runtime
                collection_end = datetime.now(timezone.utc)
                duration = (collection_end - collection_start).total_seconds()
                self.stats["total_runtime"] += duration
                
                logger.debug(
                    "Collection completed",
                    collector=self.collector_name,
                    duration=f"{duration:.2f}s",
                    success=result.get("success"),
                    data_points=result.get("data_points", 0)
                )
                
            except Exception as e:
                logger.error(
                    "Collection loop error",
                    collector=self.collector_name,
                    error=str(e),
                    exc_info=True
                )
                self.stats["last_error"] = str(e)
                self.stats["status"] = CollectorStatus.FAILED.value
            
            # Wait for next collection cycle
            await asyncio.sleep(self.collection_interval)
    
    async def _make_request(
        self,
        endpoint: str,
        params: Optional[Dict] = None,
        headers: Optional[Dict] = None,
        method: str = "GET",
        json_data: Optional[Dict] = None
    ) -> Optional[Dict]:
        """
        Make HTTP request with resilience features
        
        Features:
        - Circuit breaker protection
        - Adaptive rate limiting
        - Automatic retry with exponential backoff
        - Rate limit header parsing
        - Statistics tracking
        
        Args:
            endpoint: API endpoint (relative to base URL or absolute)
            params: Query parameters
            headers: Request headers
            method: HTTP method (GET, POST, etc.)
            json_data: JSON body for POST/PUT requests
        
        Returns:
            Response data as dict, or None if failed after retries
        """
        # Check circuit breaker
        if not self.circuit_breaker.can_attempt():
            logger.warning(
                "Circuit breaker open - blocking request",
                collector=self.collector_name,
                endpoint=endpoint
            )
            self.stats["failed_requests"] += 1
            return None
        
        # Construct full URL
        if endpoint.startswith('http'):
            url = endpoint
        elif self.api_url:
            url = f"{self.api_url}/{endpoint.lstrip('/')}"
        else:
            raise ValueError("No API URL configured and endpoint is not absolute")
        
        # Prepare headers
        request_headers = headers or {}
        if self.api_key:
            # Common auth header patterns
            if 'Authorization' not in request_headers:
                request_headers['Authorization'] = f"Bearer {self.api_key}"
        
        # Retry loop with exponential backoff
        for attempt in range(self.max_retries):
            try:
                # Rate limiting
                await self.rate_limiter.wait(endpoint=endpoint)
                
                # Make request
                async with self.session.request(
                    method,
                    url,
                    params=params,
                    headers=request_headers,
                    json=json_data
                ) as response:
                    self.stats["total_requests"] += 1
                    
                    # Parse rate limit headers
                    self.rate_limiter.parse_rate_limit_headers(response.headers, endpoint=endpoint)
                    
                    # Handle rate limiting
                    if response.status == 429:
                        retry_after = response.headers.get('Retry-After')
                        self.rate_limiter.record_429(endpoint=endpoint, retry_after=int(retry_after) if retry_after else None)
                        self.circuit_breaker.record_failure()
                        
                        logger.warning(
                            "Rate limited (429)",
                            collector=self.collector_name,
                            endpoint=endpoint,
                            retry_after=retry_after
                        )
                        
                        # Wait and retry
                        if attempt < self.max_retries - 1:
                            await asyncio.sleep(self.retry_delay * (2 ** attempt))
                            continue
                        else:
                            self.stats["failed_requests"] += 1
                            return None
                    
                    # Raise for other HTTP errors
                    response.raise_for_status()
                    
                    # Parse response
                    data = await response.json()
                    
                    # Record success
                    self.circuit_breaker.record_success()
                    self.stats["successful_requests"] += 1
                    
                    return data
                    
            except aiohttp.ClientError as e:
                logger.warning(
                    "Request failed",
                    collector=self.collector_name,
                    endpoint=endpoint,
                    attempt=attempt + 1,
                    error=str(e)
                )
                
                self.circuit_breaker.record_failure()
                
                # Retry with exponential backoff
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay * (2 ** attempt))
                else:
                    self.stats["failed_requests"] += 1
                    return None
        
        return None
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Check collector health status
        
        Returns:
            Dict with health information:
            {
                "healthy": bool,
                "status": str,  # "healthy", "degraded", "failed", "circuit_open"
                "circuit_breaker": {...},
                "rate_limiter": {...},
                "statistics": {...}
            }
        """
        # Get circuit breaker status
        cb_status = self.circuit_breaker.get_status()
        
        # Determine overall health
        if cb_status["state"] == "open":
            health_status = CollectorStatus.CIRCUIT_OPEN
            is_healthy = False
        elif self.stats["failed_requests"] > self.stats["successful_requests"] * 2:
            # More than 2x failures compared to successes
            health_status = CollectorStatus.FAILED
            is_healthy = False
        elif self.stats["failed_requests"] > 0:
            health_status = CollectorStatus.DEGRADED
            is_healthy = True
        else:
            health_status = CollectorStatus.HEALTHY
            is_healthy = True
        
        return {
            "healthy": is_healthy,
            "status": health_status.value,
            "collector_name": self.collector_name,
            "is_running": self.is_running,
            "circuit_breaker": cb_status,
            "rate_limiter": self.rate_limiter.get_stats(),
            "statistics": self.stats
        }
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get current collector status (synchronous version of health_check)
        
        Returns:
            Dict with basic status information
        """
        return {
            "collector_name": self.collector_name,
            "status": self.stats["status"],
            "is_running": self.is_running,
            "last_collection": self.stats["last_collection"],
            "last_success": self.stats["last_success"],
            "data_points_collected": self.stats["data_points_collected"],
            "collections_completed": self.stats["collections_completed"]
        }
