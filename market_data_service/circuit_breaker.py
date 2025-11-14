"""
Circuit Breaker Pattern Implementation

Implements the circuit breaker pattern for resilient collector failure handling.
Extracted from onchain_collector.py to provide reusable circuit breaker functionality
for all data collectors in the system.

Features:
- Three states: closed (normal), open (blocking), half-open (testing recovery)
- Configurable failure thresholds and timeouts
- Gradual recovery with success tracking in half-open state
- Health metrics and statistics
- Automatic recovery strategies with exponential backoff
- Redis state persistence for durability across restarts

Usage:
    from circuit_breaker import CircuitBreaker
    
    cb = CircuitBreaker(
        failure_threshold=5,
        timeout_seconds=300,
        collector_name="my_collector",
        redis_cache=redis_client
    )
    
    if cb.can_attempt():
        try:
            result = await make_api_call()
            cb.record_success()
        except Exception:
            cb.record_failure()
"""

import asyncio
from datetime import datetime, timezone
from typing import Dict, Optional, Any
from enum import Enum
import structlog

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
    
    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Blocking all requests due to failures
    - HALF-OPEN: Testing recovery with limited requests
    
    Transitions:
    - CLOSED -> OPEN: When failure_threshold is reached
    - OPEN -> HALF-OPEN: After timeout_seconds cooldown
    - HALF-OPEN -> CLOSED: When half_open_success_threshold is reached
    - HALF-OPEN -> OPEN: On any failure or insufficient success rate
    
    Attributes:
        failure_threshold: Failures needed to open circuit
        timeout_seconds: Cooldown before entering half-open (auto-increases on failed recovery)
        half_open_max_calls: Test calls allowed in half-open state
        half_open_success_threshold: Successes needed to close circuit
        collector_name: Identifier for logging and metrics
        redis_cache: Optional Redis client for state persistence
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
        Initialize circuit breaker
        
        Args:
            failure_threshold: Number of consecutive failures before opening circuit (default: 5)
            timeout_seconds: Cooldown period before attempting recovery in seconds (default: 300)
            half_open_max_calls: Maximum test calls in half-open state (default: 3)
            half_open_success_threshold: Successes needed in half-open to close (default: 2)
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
        
        Behavior by state:
        - CLOSED: Reset failure count, continue normal operation
        - HALF-OPEN: Track success, may close circuit if threshold reached
        - OPEN: Log unexpected success (shouldn't happen)
        """
        self.consecutive_successes += 1
        self.failure_count = 0
        self.stats["total_successes"] += 1
        
        if self.state == "closed":
            # Normal operation - nothing special to do
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
                if success_rate < 0.5:  # Less than 50% success rate
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
                    # Good enough success rate, close circuit
                    self._close_circuit()
                    self.stats["successful_recoveries"] += 1
                    
        elif self.state == "open":
            # Unexpected success while circuit is open
            logger.warning(
                "Unexpected success while circuit open",
                collector=self.collector_name
            )
        
    def record_failure(self):
        """
        Record failed operation
        
        Behavior by state:
        - CLOSED: Increment failure count, may open circuit if threshold reached
        - HALF-OPEN: Reopen circuit immediately (recovery failed)
        - OPEN: Already open, just track statistics
        """
        self.failure_count += 1
        self.consecutive_successes = 0
        self.last_failure_time = datetime.now(timezone.utc)
        self.stats["total_failures"] += 1
        
        if self.state == "closed":
            # Check if failure threshold reached
            if self.failure_count >= self.failure_threshold:
                self._open_circuit()
                logger.warning(
                    "Circuit breaker opened due to failures",
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
            # Already open, just track the failure
            pass
            
    def can_attempt(self) -> bool:
        """
        Check if operation can be attempted
        
        Returns:
            True if request should proceed, False if blocked by circuit breaker
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
            # Allow limited attempts for testing recovery
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
        """Reopen circuit after failed recovery attempt (with exponential backoff)"""
        self.state = "open"
        self.last_state_change = datetime.now(timezone.utc)
        self.last_failure_time = datetime.now(timezone.utc)
        self.half_open_attempts = 0
        self.half_open_successes = 0
        self.stats["last_open_time"] = self.last_state_change.isoformat()
        
        # Increase timeout for next attempt (exponential backoff)
        # Cap at 1 hour to prevent indefinite blocking
        self.timeout_seconds = min(self.timeout_seconds * 1.5, 3600)
        
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
        """
        Get comprehensive circuit breaker status
        
        Returns:
            Dict with state, statistics, and health metrics
        """
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
        
        # Calculate health score (0.0 to 1.0)
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
            logger.debug("Saved circuit breaker state to Redis", collector=self.collector_name)
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
