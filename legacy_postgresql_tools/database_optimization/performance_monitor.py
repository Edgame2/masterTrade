"""
Performance Monitor

Real-time database performance monitoring with metrics collection,
alerting, and performance trend analysis.
"""

import logging
import asyncio
import json
import psutil
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable, Union
from dataclasses import dataclass, field
from enum import Enum
from collections import deque
import statistics

try:
    import asyncpg
    import psycopg2
    POSTGRESQL_AVAILABLE = True
except ImportError:
    POSTGRESQL_AVAILABLE = False
    logging.warning("PostgreSQL libraries not available")

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logging.warning("Redis not available for caching metrics")

logger = logging.getLogger(__name__)


class MetricType(Enum):
    """Types of database metrics"""
    CONNECTION_COUNT = "connection_count"
    ACTIVE_QUERIES = "active_queries"
    QUERY_DURATION = "query_duration"
    CPU_USAGE = "cpu_usage"
    MEMORY_USAGE = "memory_usage"
    DISK_IO = "disk_io"
    BUFFER_CACHE_HIT_RATIO = "buffer_cache_hit_ratio"
    DEADLOCKS = "deadlocks"
    LOCK_WAITS = "lock_waits"
    CHECKPOINT_ACTIVITY = "checkpoint_activity"
    WAL_ACTIVITY = "wal_activity"
    REPLICATION_LAG = "replication_lag"


class AlertSeverity(Enum):
    """Alert severity levels"""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    FATAL = "fatal"


class PerformanceThreshold(Enum):
    """Pre-defined performance thresholds"""
    CPU_WARNING = 70.0
    CPU_CRITICAL = 85.0
    MEMORY_WARNING = 75.0
    MEMORY_CRITICAL = 90.0
    CONNECTION_WARNING = 80.0
    CONNECTION_CRITICAL = 95.0
    QUERY_DURATION_WARNING = 5000.0  # 5 seconds
    QUERY_DURATION_CRITICAL = 10000.0  # 10 seconds
    CACHE_HIT_RATIO_WARNING = 90.0
    CACHE_HIT_RATIO_CRITICAL = 85.0


@dataclass
class MetricValue:
    """Single metric measurement"""
    timestamp: datetime
    metric_type: MetricType
    value: float
    unit: str = ""
    tags: Dict[str, str] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "timestamp": self.timestamp.isoformat(),
            "metric_type": self.metric_type.value,
            "value": self.value,
            "unit": self.unit,
            "tags": self.tags
        }


@dataclass
class DatabaseMetrics:
    """Comprehensive database metrics snapshot"""
    timestamp: datetime
    connection_count: int = 0
    active_queries: int = 0
    cpu_usage_percent: float = 0.0
    memory_usage_percent: float = 0.0
    memory_usage_mb: float = 0.0
    disk_read_bytes_per_sec: float = 0.0
    disk_write_bytes_per_sec: float = 0.0
    buffer_cache_hit_ratio: float = 0.0
    deadlock_count: int = 0
    lock_wait_count: int = 0
    checkpoint_count: int = 0
    wal_bytes_per_sec: float = 0.0
    replication_lag_seconds: float = 0.0
    slow_query_count: int = 0
    average_query_duration_ms: float = 0.0
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "timestamp": self.timestamp.isoformat(),
            "connection_count": self.connection_count,
            "active_queries": self.active_queries,
            "cpu_usage_percent": self.cpu_usage_percent,
            "memory_usage_percent": self.memory_usage_percent,
            "memory_usage_mb": self.memory_usage_mb,
            "disk_read_bytes_per_sec": self.disk_read_bytes_per_sec,
            "disk_write_bytes_per_sec": self.disk_write_bytes_per_sec,
            "buffer_cache_hit_ratio": self.buffer_cache_hit_ratio,
            "deadlock_count": self.deadlock_count,
            "lock_wait_count": self.lock_wait_count,
            "checkpoint_count": self.checkpoint_count,
            "wal_bytes_per_sec": self.wal_bytes_per_sec,
            "replication_lag_seconds": self.replication_lag_seconds,
            "slow_query_count": self.slow_query_count,
            "average_query_duration_ms": self.average_query_duration_ms
        }
    
    def get_health_score(self) -> float:
        """Calculate overall database health score (0-100)"""
        
        scores = []
        
        # CPU score (lower is better)
        cpu_score = max(0, 100 - (self.cpu_usage_percent / 100 * 100))
        scores.append(cpu_score)
        
        # Memory score (lower is better)
        memory_score = max(0, 100 - (self.memory_usage_percent / 100 * 100))
        scores.append(memory_score)
        
        # Cache hit ratio score (higher is better)
        cache_score = self.buffer_cache_hit_ratio
        scores.append(cache_score)
        
        # Query performance score (lower average duration is better)
        if self.average_query_duration_ms > 0:
            # Normalize to 0-100 scale (assuming 10s is very poor performance)
            query_score = max(0, 100 - (self.average_query_duration_ms / 10000 * 100))
        else:
            query_score = 100
        scores.append(query_score)
        
        # Connection usage score
        # This would need max_connections info, simplified for now
        connection_score = 100  # Placeholder
        scores.append(connection_score)
        
        return statistics.mean(scores)


@dataclass
class PerformanceAlert:
    """Performance alert information"""
    alert_id: str
    severity: AlertSeverity
    metric_type: MetricType
    message: str
    current_value: float
    threshold_value: float
    timestamp: datetime
    resolved: bool = False
    resolved_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "alert_id": self.alert_id,
            "severity": self.severity.value,
            "metric_type": self.metric_type.value,
            "message": self.message,
            "current_value": self.current_value,
            "threshold_value": self.threshold_value,
            "timestamp": self.timestamp.isoformat(),
            "resolved": self.resolved,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None
        }


class SlowQueryAnalyzer:
    """Analyzer for slow query detection and analysis"""
    
    def __init__(self, threshold_ms: float = 1000):
        self.threshold_ms = threshold_ms
        self.slow_queries: deque = deque(maxlen=1000)  # Keep last 1000 slow queries
        self.query_patterns: Dict[str, int] = {}
        
    def analyze_slow_query(self, query: str, duration_ms: float, timestamp: datetime) -> Dict[str, Any]:
        """Analyze slow query and extract patterns"""
        
        if duration_ms < self.threshold_ms:
            return {}
        
        # Normalize query for pattern detection
        normalized_query = self._normalize_query(query)
        
        # Track pattern frequency
        if normalized_query in self.query_patterns:
            self.query_patterns[normalized_query] += 1
        else:
            self.query_patterns[normalized_query] = 1
        
        # Store slow query info
        slow_query_info = {
            "query": query[:500],  # Truncate long queries
            "normalized_query": normalized_query,
            "duration_ms": duration_ms,
            "timestamp": timestamp.isoformat(),
            "pattern_frequency": self.query_patterns[normalized_query]
        }
        
        self.slow_queries.append(slow_query_info)
        
        return slow_query_info
    
    def _normalize_query(self, query: str) -> str:
        """Normalize query for pattern detection"""
        
        import re
        
        # Convert to lowercase
        normalized = query.lower().strip()
        
        # Remove extra whitespace
        normalized = re.sub(r'\s+', ' ', normalized)
        
        # Replace string literals
        normalized = re.sub(r"'[^']*'", "'?'", normalized)
        
        # Replace numeric literals
        normalized = re.sub(r'\b\d+\b', '?', normalized)
        
        # Replace IN clauses with parameters
        normalized = re.sub(r'in\s*\([^)]+\)', 'in (?)', normalized)
        
        return normalized
    
    def get_slow_query_patterns(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get most frequent slow query patterns"""
        
        patterns = []
        
        # Sort by frequency
        sorted_patterns = sorted(
            self.query_patterns.items(),
            key=lambda x: x[1],
            reverse=True
        )[:limit]
        
        for pattern, frequency in sorted_patterns:
            # Find recent examples
            recent_examples = [
                sq for sq in list(self.slow_queries)[-100:]  # Last 100
                if sq["normalized_query"] == pattern
            ]
            
            if recent_examples:
                avg_duration = statistics.mean(sq["duration_ms"] for sq in recent_examples)
                max_duration = max(sq["duration_ms"] for sq in recent_examples)
                
                patterns.append({
                    "pattern": pattern,
                    "frequency": frequency,
                    "avg_duration_ms": avg_duration,
                    "max_duration_ms": max_duration,
                    "recent_examples": len(recent_examples)
                })
        
        return patterns
    
    def get_recent_slow_queries(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent slow queries"""
        
        return list(self.slow_queries)[-limit:]


class ConnectionPoolMonitor:
    """Monitor database connection pool metrics"""
    
    def __init__(self):
        self.connection_history: deque = deque(maxlen=1000)
        self.pool_metrics: Dict[str, Any] = {}
        
    def record_connection_metrics(self, active_connections: int, idle_connections: int, max_connections: int):
        """Record connection pool metrics"""
        
        timestamp = datetime.utcnow()
        total_connections = active_connections + idle_connections
        usage_percent = (total_connections / max_connections) * 100 if max_connections > 0 else 0
        
        metrics = {
            "timestamp": timestamp.isoformat(),
            "active_connections": active_connections,
            "idle_connections": idle_connections,
            "total_connections": total_connections,
            "max_connections": max_connections,
            "usage_percent": usage_percent
        }
        
        self.connection_history.append(metrics)
        self.pool_metrics = metrics
        
    def get_connection_trends(self, hours: int = 24) -> Dict[str, Any]:
        """Get connection usage trends over time"""
        
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        
        recent_metrics = [
            m for m in self.connection_history
            if datetime.fromisoformat(m["timestamp"]) >= cutoff_time
        ]
        
        if not recent_metrics:
            return {}
        
        usage_values = [m["usage_percent"] for m in recent_metrics]
        active_values = [m["active_connections"] for m in recent_metrics]
        
        return {
            "avg_usage_percent": statistics.mean(usage_values),
            "max_usage_percent": max(usage_values),
            "min_usage_percent": min(usage_values),
            "avg_active_connections": statistics.mean(active_values),
            "max_active_connections": max(active_values),
            "samples_count": len(recent_metrics),
            "time_period_hours": hours
        }


class PerformanceMonitor:
    """
    Real-time database performance monitoring system
    
    Monitors database metrics, detects performance issues,
    and provides alerting and trend analysis capabilities.
    """
    
    def __init__(
        self,
        db_connection_string: str,
        collection_interval_seconds: int = 30,
        redis_url: Optional[str] = None
    ):
        self.db_connection_string = db_connection_string
        self.collection_interval_seconds = collection_interval_seconds
        
        # Components
        self.slow_query_analyzer = SlowQueryAnalyzer()
        self.connection_pool_monitor = ConnectionPoolMonitor()
        
        # Redis for metrics storage (optional)
        self.redis_client = None
        if redis_url and REDIS_AVAILABLE:
            try:
                self.redis_client = redis.from_url(redis_url)
            except Exception:
                logger.warning("Failed to connect to Redis")
        
        # Metrics storage
        self.metrics_history: deque = deque(maxlen=2880)  # 24 hours at 30-second intervals
        self.current_metrics: Optional[DatabaseMetrics] = None
        self.active_alerts: Dict[str, PerformanceAlert] = {}
        self.alert_history: deque = deque(maxlen=1000)
        
        # Alert callbacks
        self.alert_callbacks: List[Callable[[PerformanceAlert], None]] = []
        
        # Monitoring state
        self._running = False
        self._monitor_task: Optional[asyncio.Task] = None
        
        # Thresholds
        self.thresholds = {
            MetricType.CPU_USAGE: {
                AlertSeverity.WARNING: PerformanceThreshold.CPU_WARNING.value,
                AlertSeverity.CRITICAL: PerformanceThreshold.CPU_CRITICAL.value
            },
            MetricType.MEMORY_USAGE: {
                AlertSeverity.WARNING: PerformanceThreshold.MEMORY_WARNING.value,
                AlertSeverity.CRITICAL: PerformanceThreshold.MEMORY_CRITICAL.value
            },
            MetricType.CONNECTION_COUNT: {
                AlertSeverity.WARNING: PerformanceThreshold.CONNECTION_WARNING.value,
                AlertSeverity.CRITICAL: PerformanceThreshold.CONNECTION_CRITICAL.value
            },
            MetricType.QUERY_DURATION: {
                AlertSeverity.WARNING: PerformanceThreshold.QUERY_DURATION_WARNING.value,
                AlertSeverity.CRITICAL: PerformanceThreshold.QUERY_DURATION_CRITICAL.value
            },
            MetricType.BUFFER_CACHE_HIT_RATIO: {
                AlertSeverity.WARNING: PerformanceThreshold.CACHE_HIT_RATIO_WARNING.value,
                AlertSeverity.CRITICAL: PerformanceThreshold.CACHE_HIT_RATIO_CRITICAL.value
            }
        }
    
    async def start_monitoring(self):
        """Start performance monitoring"""
        
        if self._running:
            logger.warning("Performance monitor already running")
            return
        
        self._running = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        
        logger.info("Performance monitoring started")
    
    async def stop_monitoring(self):
        """Stop performance monitoring"""
        
        self._running = False
        
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Performance monitoring stopped")
    
    async def _monitor_loop(self):
        """Main monitoring loop"""
        
        while self._running:
            try:
                # Collect metrics
                metrics = await self._collect_database_metrics()
                
                if metrics:
                    self.current_metrics = metrics
                    self.metrics_history.append(metrics)
                    
                    # Store in Redis if available
                    if self.redis_client:
                        await self._store_metrics_in_redis(metrics)
                    
                    # Check for alerts
                    await self._check_performance_alerts(metrics)
                
                # Sleep for collection interval
                await asyncio.sleep(self.collection_interval_seconds)
            
            except Exception as e:
                logger.error(f"Monitoring loop error: {e}")
                await asyncio.sleep(self.collection_interval_seconds)
    
    async def _collect_database_metrics(self) -> Optional[DatabaseMetrics]:
        """Collect comprehensive database metrics"""
        
        if not POSTGRESQL_AVAILABLE:
            return None
        
        try:
            conn = await asyncpg.connect(self.db_connection_string)
            
            timestamp = datetime.utcnow()
            metrics = DatabaseMetrics(timestamp=timestamp)
            
            # Connection metrics
            connection_stats = await conn.fetchrow("""
                SELECT 
                    (SELECT count(*) FROM pg_stat_activity) as total_connections,
                    (SELECT count(*) FROM pg_stat_activity WHERE state = 'active') as active_queries
            """)
            
            if connection_stats:
                metrics.connection_count = connection_stats['total_connections']
                metrics.active_queries = connection_stats['active_queries']
            
            # Buffer cache hit ratio
            cache_stats = await conn.fetchrow("""
                SELECT 
                    round((blks_hit * 100.0) / (blks_hit + blks_read), 2) as cache_hit_ratio
                FROM pg_stat_database 
                WHERE datname = current_database()
                AND blks_read > 0
            """)
            
            if cache_stats and cache_stats['cache_hit_ratio']:
                metrics.buffer_cache_hit_ratio = float(cache_stats['cache_hit_ratio'])
            
            # Lock and deadlock metrics
            lock_stats = await conn.fetchrow("""
                SELECT 
                    (SELECT count(*) FROM pg_locks WHERE granted = false) as lock_waits,
                    (SELECT deadlocks FROM pg_stat_database WHERE datname = current_database()) as deadlocks
            """)
            
            if lock_stats:
                metrics.lock_wait_count = lock_stats['lock_waits'] or 0
                metrics.deadlock_count = lock_stats['deadlocks'] or 0
            
            # WAL and checkpoint metrics
            wal_stats = await conn.fetchrow("""
                SELECT 
                    checkpoints_timed + checkpoints_req as total_checkpoints
                FROM pg_stat_bgwriter
            """)
            
            if wal_stats:
                metrics.checkpoint_count = wal_stats['total_checkpoints'] or 0
            
            await conn.close()
            
            # System metrics (CPU, Memory, Disk)
            await self._collect_system_metrics(metrics)
            
            return metrics
        
        except Exception as e:
            logger.error(f"Failed to collect database metrics: {e}")
            return None
    
    async def _collect_system_metrics(self, metrics: DatabaseMetrics):
        """Collect system-level metrics"""
        
        try:
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)
            metrics.cpu_usage_percent = cpu_percent
            
            # Memory usage
            memory = psutil.virtual_memory()
            metrics.memory_usage_percent = memory.percent
            metrics.memory_usage_mb = memory.used / (1024 * 1024)
            
            # Disk I/O
            disk_io = psutil.disk_io_counters()
            if disk_io:
                # These would be rates if we tracked previous values
                metrics.disk_read_bytes_per_sec = disk_io.read_bytes
                metrics.disk_write_bytes_per_sec = disk_io.write_bytes
        
        except Exception as e:
            logger.warning(f"Failed to collect system metrics: {e}")
    
    async def _store_metrics_in_redis(self, metrics: DatabaseMetrics):
        """Store metrics in Redis for persistence"""
        
        try:
            # Store current metrics
            await self.redis_client.set(
                "db_metrics:current",
                json.dumps(metrics.to_dict()),
                ex=3600  # 1 hour expiry
            )
            
            # Store in time series (simplified)
            timestamp_key = metrics.timestamp.strftime("%Y%m%d_%H%M")
            await self.redis_client.hset(
                "db_metrics:timeseries",
                timestamp_key,
                json.dumps(metrics.to_dict())
            )
            
            # Keep only last 24 hours
            await self.redis_client.expire("db_metrics:timeseries", 86400)
        
        except Exception as e:
            logger.warning(f"Failed to store metrics in Redis: {e}")
    
    async def _check_performance_alerts(self, metrics: DatabaseMetrics):
        """Check metrics against thresholds and generate alerts"""
        
        current_time = datetime.utcnow()
        
        # Check CPU usage
        await self._check_metric_threshold(
            MetricType.CPU_USAGE,
            metrics.cpu_usage_percent,
            current_time,
            "CPU usage is {}%"
        )
        
        # Check memory usage
        await self._check_metric_threshold(
            MetricType.MEMORY_USAGE,
            metrics.memory_usage_percent,
            current_time,
            "Memory usage is {}%"
        )
        
        # Check buffer cache hit ratio (inverted - lower is worse)
        await self._check_metric_threshold(
            MetricType.BUFFER_CACHE_HIT_RATIO,
            metrics.buffer_cache_hit_ratio,
            current_time,
            "Buffer cache hit ratio is {}%",
            inverted=True
        )
        
        # Check for slow queries
        if metrics.average_query_duration_ms > 0:
            await self._check_metric_threshold(
                MetricType.QUERY_DURATION,
                metrics.average_query_duration_ms,
                current_time,
                "Average query duration is {}ms"
            )
    
    async def _check_metric_threshold(
        self,
        metric_type: MetricType,
        current_value: float,
        timestamp: datetime,
        message_template: str,
        inverted: bool = False
    ):
        """Check individual metric against thresholds"""
        
        if metric_type not in self.thresholds:
            return
        
        thresholds = self.thresholds[metric_type]
        
        # Determine severity
        severity = None
        threshold_value = None
        
        if inverted:
            # For metrics where lower values are worse (like cache hit ratio)
            if current_value < thresholds[AlertSeverity.CRITICAL]:
                severity = AlertSeverity.CRITICAL
                threshold_value = thresholds[AlertSeverity.CRITICAL]
            elif current_value < thresholds[AlertSeverity.WARNING]:
                severity = AlertSeverity.WARNING
                threshold_value = thresholds[AlertSeverity.WARNING]
        else:
            # For metrics where higher values are worse (like CPU usage)
            if current_value > thresholds[AlertSeverity.CRITICAL]:
                severity = AlertSeverity.CRITICAL
                threshold_value = thresholds[AlertSeverity.CRITICAL]
            elif current_value > thresholds[AlertSeverity.WARNING]:
                severity = AlertSeverity.WARNING
                threshold_value = thresholds[AlertSeverity.WARNING]
        
        alert_key = f"{metric_type.value}_{severity.value}" if severity else None
        
        if severity:
            # Check if alert already exists
            if alert_key not in self.active_alerts:
                # Create new alert
                alert = PerformanceAlert(
                    alert_id=f"{alert_key}_{int(timestamp.timestamp())}",
                    severity=severity,
                    metric_type=metric_type,
                    message=message_template.format(current_value),
                    current_value=current_value,
                    threshold_value=threshold_value,
                    timestamp=timestamp
                )
                
                self.active_alerts[alert_key] = alert
                self.alert_history.append(alert)
                
                # Trigger alert callbacks
                for callback in self.alert_callbacks:
                    try:
                        callback(alert)
                    except Exception as e:
                        logger.error(f"Alert callback failed: {e}")
                
                logger.warning(f"Performance alert: {alert.message}")
        else:
            # Check if we need to resolve existing alert
            if alert_key in self.active_alerts:
                alert = self.active_alerts[alert_key]
                alert.resolved = True
                alert.resolved_at = timestamp
                
                del self.active_alerts[alert_key]
                
                logger.info(f"Performance alert resolved: {alert.message}")
    
    def add_alert_callback(self, callback: Callable[[PerformanceAlert], None]):
        """Add alert notification callback"""
        self.alert_callbacks.append(callback)
    
    def get_current_metrics(self) -> Optional[DatabaseMetrics]:
        """Get current database metrics"""
        return self.current_metrics
    
    def get_metrics_history(self, hours: int = 24) -> List[DatabaseMetrics]:
        """Get metrics history for specified time period"""
        
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        
        return [
            metrics for metrics in self.metrics_history
            if metrics.timestamp >= cutoff_time
        ]
    
    def get_active_alerts(self) -> List[PerformanceAlert]:
        """Get currently active alerts"""
        return list(self.active_alerts.values())
    
    def get_alert_history(self, hours: int = 24) -> List[PerformanceAlert]:
        """Get alert history for specified time period"""
        
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        
        return [
            alert for alert in self.alert_history
            if alert.timestamp >= cutoff_time
        ]
    
    def get_performance_summary(self, hours: int = 24) -> Dict[str, Any]:
        """Get performance summary for specified time period"""
        
        recent_metrics = self.get_metrics_history(hours)
        
        if not recent_metrics:
            return {"error": "No metrics available"}
        
        # Calculate averages
        avg_cpu = statistics.mean(m.cpu_usage_percent for m in recent_metrics)
        avg_memory = statistics.mean(m.memory_usage_percent for m in recent_metrics)
        avg_connections = statistics.mean(m.connection_count for m in recent_metrics)
        avg_cache_hit_ratio = statistics.mean(m.buffer_cache_hit_ratio for m in recent_metrics if m.buffer_cache_hit_ratio > 0)
        
        # Get current health score
        current_health = recent_metrics[-1].get_health_score() if recent_metrics else 0
        
        # Alert statistics
        recent_alerts = self.get_alert_history(hours)
        alert_counts = {
            "total": len(recent_alerts),
            "critical": len([a for a in recent_alerts if a.severity == AlertSeverity.CRITICAL]),
            "warning": len([a for a in recent_alerts if a.severity == AlertSeverity.WARNING]),
            "active": len(self.active_alerts)
        }
        
        return {
            "time_period_hours": hours,
            "current_health_score": current_health,
            "averages": {
                "cpu_usage_percent": avg_cpu,
                "memory_usage_percent": avg_memory,
                "connection_count": avg_connections,
                "cache_hit_ratio_percent": avg_cache_hit_ratio
            },
            "alerts": alert_counts,
            "slow_queries": {
                "patterns": len(self.slow_query_analyzer.query_patterns),
                "recent_count": len(self.slow_query_analyzer.get_recent_slow_queries())
            },
            "samples_collected": len(recent_metrics)
        }
    
    def update_thresholds(self, metric_type: MetricType, thresholds: Dict[AlertSeverity, float]):
        """Update alert thresholds for metric type"""
        self.thresholds[metric_type] = thresholds
        logger.info(f"Updated thresholds for {metric_type.value}")
    
    def analyze_slow_query(self, query: str, duration_ms: float) -> Dict[str, Any]:
        """Analyze slow query"""
        return self.slow_query_analyzer.analyze_slow_query(
            query, duration_ms, datetime.utcnow()
        )
    
    def record_connection_metrics(self, active: int, idle: int, max_conn: int):
        """Record connection pool metrics"""
        self.connection_pool_monitor.record_connection_metrics(active, idle, max_conn)