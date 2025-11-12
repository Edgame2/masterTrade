"""
Shared Prometheus Metrics Module

Provides standardized metrics collection for all MasterTrade services.
Includes custom metrics for trading, data collection, and ML operations.
"""

from prometheus_client import Counter, Histogram, Gauge, Info, Summary
from prometheus_fastapi_instrumentator import Instrumentator
from prometheus_fastapi_instrumentator.metrics import Info as MetricInfo
from typing import Callable, Optional
import time
from functools import wraps
from datetime import datetime
import structlog

logger = structlog.get_logger(__name__)


# ============================================================================
# Standard HTTP Metrics (automatically collected by instrumentator)
# ============================================================================
# - http_requests_total
# - http_request_duration_seconds
# - http_request_size_bytes
# - http_response_size_bytes


# ============================================================================
# Custom Application Metrics
# ============================================================================

# Service Health
service_info = Info(
    'service',
    'Service information'
)

service_up = Gauge(
    'service_up',
    'Service availability (1 = up, 0 = down)',
    ['service_name']
)

service_start_time = Gauge(
    'service_start_time_seconds',
    'Service start time in Unix epoch seconds',
    ['service_name']
)

# Database Metrics
db_connections_total = Gauge(
    'db_connections_total',
    'Total database connections',
    ['service_name', 'database']
)

db_query_duration_seconds = Histogram(
    'db_query_duration_seconds',
    'Database query duration in seconds',
    ['service_name', 'query_type'],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
)

db_query_errors_total = Counter(
    'db_query_errors_total',
    'Total database query errors',
    ['service_name', 'error_type']
)

# RabbitMQ Metrics
rabbitmq_messages_published_total = Counter(
    'rabbitmq_messages_published_total',
    'Total RabbitMQ messages published',
    ['service_name', 'queue']
)

rabbitmq_messages_consumed_total = Counter(
    'rabbitmq_messages_consumed_total',
    'Total RabbitMQ messages consumed',
    ['service_name', 'queue']
)

rabbitmq_message_processing_duration_seconds = Histogram(
    'rabbitmq_message_processing_duration_seconds',
    'RabbitMQ message processing duration',
    ['service_name', 'queue'],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
)

# Redis Cache Metrics
redis_cache_hits_total = Counter(
    'redis_cache_hits_total',
    'Total Redis cache hits',
    ['service_name', 'cache_key']
)

redis_cache_misses_total = Counter(
    'redis_cache_misses_total',
    'Total Redis cache misses',
    ['service_name', 'cache_key']
)

redis_operations_duration_seconds = Histogram(
    'redis_operations_duration_seconds',
    'Redis operation duration',
    ['service_name', 'operation'],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5)
)

# Data Collection Metrics
data_collector_health = Gauge(
    'data_collector_health',
    'Data collector health status (1 = healthy, 0 = unhealthy)',
    ['collector_name', 'source']
)

data_collector_last_success_timestamp = Gauge(
    'data_collector_last_success_timestamp',
    'Last successful data collection timestamp',
    ['collector_name', 'source']
)

data_points_collected_total = Counter(
    'data_points_collected_total',
    'Total data points collected',
    ['collector_name', 'source', 'data_type']
)

data_collection_errors_total = Counter(
    'data_collection_errors_total',
    'Total data collection errors',
    ['collector_name', 'source', 'error_type']
)

data_collection_duration_seconds = Histogram(
    'data_collection_duration_seconds',
    'Data collection duration',
    ['collector_name', 'source'],
    buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0)
)

# Trading Metrics
strategy_signals_total = Counter(
    'strategy_signals_total',
    'Total trading signals generated',
    ['strategy_id', 'signal_type', 'symbol']
)

orders_placed_total = Counter(
    'orders_placed_total',
    'Total orders placed',
    ['order_type', 'symbol', 'side']
)

orders_filled_total = Counter(
    'orders_filled_total',
    'Total orders filled',
    ['order_type', 'symbol', 'side']
)

orders_cancelled_total = Counter(
    'orders_cancelled_total',
    'Total orders cancelled',
    ['order_type', 'symbol', 'reason']
)

order_execution_duration_seconds = Histogram(
    'order_execution_duration_seconds',
    'Order execution duration from signal to fill',
    ['order_type', 'symbol'],
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0)
)

active_positions_count = Gauge(
    'active_positions_count',
    'Number of active trading positions',
    ['symbol']
)

position_pnl_usd = Gauge(
    'position_pnl_usd',
    'Position profit/loss in USD',
    ['position_id', 'symbol', 'strategy_id']
)

portfolio_value_usd = Gauge(
    'portfolio_value_usd',
    'Total portfolio value in USD',
    ['account_id']
)

# Goal Tracking Metrics
goal_progress_percentage = Gauge(
    'goal_progress_percentage',
    'Financial goal progress percentage',
    ['goal_id', 'goal_type', 'user_id']
)

goal_current_value = Gauge(
    'goal_current_value',
    'Current value for goal',
    ['goal_id', 'goal_type', 'user_id']
)

goal_target_value = Gauge(
    'goal_target_value',
    'Target value for goal',
    ['goal_id', 'goal_type', 'user_id']
)

goals_achieved_total = Counter(
    'goals_achieved_total',
    'Total goals achieved',
    ['goal_type', 'user_id']
)

# Risk Management Metrics
risk_limit_breaches_total = Counter(
    'risk_limit_breaches_total',
    'Total risk limit breaches',
    ['limit_type', 'severity']
)

current_risk_exposure = Gauge(
    'current_risk_exposure',
    'Current risk exposure',
    ['risk_type', 'symbol']
)

drawdown_percentage = Gauge(
    'drawdown_percentage',
    'Current drawdown percentage from peak',
    ['account_id', 'timeframe']
)

# ML Model Metrics
ml_model_predictions_total = Counter(
    'ml_model_predictions_total',
    'Total ML model predictions',
    ['model_name', 'model_version', 'prediction_type']
)

ml_model_prediction_duration_seconds = Histogram(
    'ml_model_prediction_duration_seconds',
    'ML model prediction duration',
    ['model_name', 'model_version'],
    buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0)
)

ml_model_accuracy = Gauge(
    'ml_model_accuracy',
    'ML model accuracy score',
    ['model_name', 'model_version', 'metric_type']
)

ml_model_drift_score = Gauge(
    'ml_model_drift_score',
    'ML model drift detection score',
    ['model_name', 'model_version', 'drift_type']
)

ml_model_training_duration_seconds = Histogram(
    'ml_model_training_duration_seconds',
    'ML model training duration',
    ['model_name', 'model_version'],
    buckets=(10, 60, 300, 600, 1800, 3600)
)

# Alert Metrics
alerts_triggered_total = Counter(
    'alerts_triggered_total',
    'Total alerts triggered',
    ['alert_type', 'priority', 'channel']
)

alert_delivery_success_total = Counter(
    'alert_delivery_success_total',
    'Total successful alert deliveries',
    ['alert_type', 'channel']
)

alert_delivery_failures_total = Counter(
    'alert_delivery_failures_total',
    'Total failed alert deliveries',
    ['alert_type', 'channel', 'error_type']
)

alert_delivery_duration_seconds = Histogram(
    'alert_delivery_duration_seconds',
    'Alert delivery duration',
    ['alert_type', 'channel'],
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0)
)


# ============================================================================
# Utility Functions
# ============================================================================

def create_instrumentator(
    service_name: str,
    service_version: str = "1.0.0",
    custom_metrics: bool = True
) -> Instrumentator:
    """
    Create a FastAPI Prometheus instrumentator.
    
    Args:
        service_name: Name of the service
        service_version: Version of the service
        custom_metrics: Whether to enable custom metrics
        
    Returns:
        Configured Instrumentator instance
    """
    instrumentator = Instrumentator(
        should_group_status_codes=True,
        should_ignore_untemplated=True,
        should_respect_env_var=True,
        should_instrument_requests_inprogress=True,
        excluded_handlers=["/metrics", "/health", "/docs", "/redoc", "/openapi.json"],
        inprogress_name="http_requests_inprogress",
        inprogress_labels=True,
    )
    
    # Set service info
    service_info.info({
        'service_name': service_name,
        'version': service_version,
    })
    
    # Mark service as up
    service_up.labels(service_name=service_name).set(1)
    service_start_time.labels(service_name=service_name).set(time.time())
    
    logger.info(f"Prometheus metrics initialized for {service_name} v{service_version}")
    
    return instrumentator


def track_db_query(service_name: str, query_type: str):
    """
    Decorator to track database query metrics.
    
    Usage:
        @track_db_query("market_data_service", "select")
        async def get_data():
            ...
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                duration = time.time() - start_time
                db_query_duration_seconds.labels(
                    service_name=service_name,
                    query_type=query_type
                ).observe(duration)
                return result
            except Exception as e:
                db_query_errors_total.labels(
                    service_name=service_name,
                    error_type=type(e).__name__
                ).inc()
                raise
        return wrapper
    return decorator


def track_cache_operation(service_name: str):
    """
    Decorator to track Redis cache operations.
    
    Usage:
        @track_cache_operation("strategy_service")
        async def get_from_cache(key):
            ...
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            cache_key = kwargs.get('key') or (args[0] if args else 'unknown')
            
            try:
                result = await func(*args, **kwargs)
                duration = time.time() - start_time
                
                redis_operations_duration_seconds.labels(
                    service_name=service_name,
                    operation=func.__name__
                ).observe(duration)
                
                if result is not None:
                    redis_cache_hits_total.labels(
                        service_name=service_name,
                        cache_key=str(cache_key)[:50]  # Truncate long keys
                    ).inc()
                else:
                    redis_cache_misses_total.labels(
                        service_name=service_name,
                        cache_key=str(cache_key)[:50]
                    ).inc()
                
                return result
            except Exception as e:
                logger.error(f"Redis operation failed: {e}")
                raise
        return wrapper
    return decorator


def track_data_collection(collector_name: str, source: str):
    """
    Decorator to track data collection metrics.
    
    Usage:
        @track_data_collection("binance_collector", "binance")
        async def collect_data():
            ...
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                duration = time.time() - start_time
                
                data_collection_duration_seconds.labels(
                    collector_name=collector_name,
                    source=source
                ).observe(duration)
                
                data_collector_last_success_timestamp.labels(
                    collector_name=collector_name,
                    source=source
                ).set(time.time())
                
                data_collector_health.labels(
                    collector_name=collector_name,
                    source=source
                ).set(1)
                
                return result
            except Exception as e:
                data_collection_errors_total.labels(
                    collector_name=collector_name,
                    source=source,
                    error_type=type(e).__name__
                ).inc()
                
                data_collector_health.labels(
                    collector_name=collector_name,
                    source=source
                ).set(0)
                
                raise
        return wrapper
    return decorator


def update_collector_health(collector_name: str, source: str, is_healthy: bool):
    """Update collector health status."""
    data_collector_health.labels(
        collector_name=collector_name,
        source=source
    ).set(1 if is_healthy else 0)


def record_data_points(collector_name: str, source: str, data_type: str, count: int):
    """Record number of data points collected."""
    data_points_collected_total.labels(
        collector_name=collector_name,
        source=source,
        data_type=data_type
    ).inc(count)


def update_goal_metrics(goal_id: str, goal_type: str, user_id: str, 
                       current_value: float, target_value: float, progress_pct: float):
    """Update goal tracking metrics."""
    goal_current_value.labels(
        goal_id=goal_id,
        goal_type=goal_type,
        user_id=user_id
    ).set(current_value)
    
    goal_target_value.labels(
        goal_id=goal_id,
        goal_type=goal_type,
        user_id=user_id
    ).set(target_value)
    
    goal_progress_percentage.labels(
        goal_id=goal_id,
        goal_type=goal_type,
        user_id=user_id
    ).set(progress_pct)


def record_goal_achievement(goal_type: str, user_id: str):
    """Record goal achievement."""
    goals_achieved_total.labels(
        goal_type=goal_type,
        user_id=user_id
    ).inc()


def update_model_metrics(model_name: str, model_version: str, 
                        accuracy: float, drift_score: float):
    """Update ML model metrics."""
    ml_model_accuracy.labels(
        model_name=model_name,
        model_version=model_version,
        metric_type="accuracy"
    ).set(accuracy)
    
    ml_model_drift_score.labels(
        model_name=model_name,
        model_version=model_version,
        drift_type="feature"
    ).set(drift_score)


def record_alert_metrics(alert_type: str, priority: str, channel: str, 
                        success: bool, duration: float):
    """Record alert delivery metrics."""
    alerts_triggered_total.labels(
        alert_type=alert_type,
        priority=priority,
        channel=channel
    ).inc()
    
    if success:
        alert_delivery_success_total.labels(
            alert_type=alert_type,
            channel=channel
        ).inc()
    else:
        alert_delivery_failures_total.labels(
            alert_type=alert_type,
            channel=channel,
            error_type="delivery_failed"
        ).inc()
    
    alert_delivery_duration_seconds.labels(
        alert_type=alert_type,
        channel=channel
    ).observe(duration)


# ============================================================================
# Health Check Helpers
# ============================================================================

def get_service_uptime(service_name: str) -> float:
    """Get service uptime in seconds."""
    start_time_metric = service_start_time.labels(service_name=service_name)
    # This is a workaround to get the current value
    # In production, you'd track this separately
    return time.time() - start_time_metric._value.get()


def mark_service_down(service_name: str):
    """Mark service as down."""
    service_up.labels(service_name=service_name).set(0)
    logger.error(f"Service {service_name} marked as down")


def mark_service_up(service_name: str):
    """Mark service as up."""
    service_up.labels(service_name=service_name).set(1)
    logger.info(f"Service {service_name} marked as up")
