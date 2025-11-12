# Prometheus Metrics Documentation

**Created**: January 2025  
**Status**: ✅ Implemented  
**Services**: All 6 core services  

## Overview

This document describes the comprehensive Prometheus metrics implementation across all MasterTrade services. The system exposes 50+ metrics covering service health, infrastructure, data collection, trading operations, ML models, and alerting.

## Architecture

### Centralized Metrics Module

All metrics are defined in `shared/prometheus_metrics.py` to ensure consistency across services:

- **Location**: `/shared/prometheus_metrics.py`
- **Lines**: 580+ lines
- **Metrics**: 50+ metrics
- **Utilities**: Decorators and helper functions for easy integration

### Service Integration

| Service | Integration Method | Port | Metrics Endpoint |
|---------|-------------------|------|------------------|
| `strategy_service` | FastAPI Instrumentator | 8003 | `http://localhost:8003/metrics` |
| `risk_manager` | FastAPI Instrumentator | 8002 | `http://localhost:8002/metrics` |
| `alert_system` | FastAPI Instrumentator | 8007 | `http://localhost:8007/metrics` |
| `api_gateway` | FastAPI Instrumentator | 8080 | `http://localhost:8080/metrics` |
| `market_data_service` | prometheus_client (standalone) | 9001 | `http://localhost:9001/metrics` |
| `order_executor` | aiohttp + prometheus_client | 9002 | `http://localhost:9002/metrics` |

## Metrics Categories

### 1. HTTP Metrics (Automatic via Instrumentator)

These metrics are automatically collected by `prometheus-fastapi-instrumentator` for all FastAPI services:

```prometheus
# Total HTTP requests
http_requests_total{method="GET", path="/api/v1/strategies", status="200"}

# Request duration histogram
http_request_duration_seconds_bucket{method="POST", path="/api/v1/orders", le="0.1"}

# Request size
http_request_size_bytes_sum{method="POST", path="/api/v1/signals"}

# Response size
http_response_size_bytes_sum{method="GET", path="/api/v1/positions"}
```

**Histogram Buckets**: `[0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 7.5, 10.0]`

### 2. Service Health Metrics

Track overall service availability and lifecycle:

```prometheus
# Service uptime (1 = up, 0 = down)
service_up{service_name="strategy_service"}

# Service start time (Unix timestamp)
service_start_time{service_name="strategy_service"}

# Service metadata
service_info{service_name="strategy_service", version="2.0.0", environment="production"}
```

**Usage**:
```python
from shared.prometheus_metrics import mark_service_up, mark_service_down

# On startup
mark_service_up("strategy_service")

# On error/shutdown
mark_service_down("strategy_service")
```

### 3. Database Metrics

Monitor database performance and issues:

```prometheus
# Active database connections
db_connections_total{service_name="strategy_service"}

# Query duration histogram
db_query_duration_seconds_bucket{service_name="risk_manager", query_type="select", le="0.1"}

# Query errors
db_query_errors_total{service_name="alert_system", error_type="timeout"}
```

**Histogram Buckets**: `[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]`

**Usage**:
```python
from shared.prometheus_metrics import track_db_query

@track_db_query("strategy_service", "select")
async def fetch_strategies():
    # Query execution automatically tracked
    return await db.execute(query)
```

### 4. RabbitMQ Metrics

Track message queue operations:

```prometheus
# Messages published
rabbitmq_messages_published_total{service_name="order_executor", exchange="trading_signals"}

# Messages consumed
rabbitmq_messages_consumed_total{service_name="strategy_service", queue="market_data"}

# Message processing duration
rabbitmq_message_processing_duration_seconds_bucket{service_name="order_executor", le="0.5"}
```

**Histogram Buckets**: `[0.001, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 10.0]`

### 5. Redis Cache Metrics

Monitor caching effectiveness:

```prometheus
# Cache hits
redis_cache_hits_total{service_name="strategy_service", operation="get"}

# Cache misses
redis_cache_misses_total{service_name="strategy_service", operation="get"}

# Operation duration
redis_operations_duration_seconds_bucket{service_name="strategy_service", operation="set", le="0.01"}
```

**Histogram Buckets**: `[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5]`

**Usage**:
```python
from shared.prometheus_metrics import track_cache_operation

@track_cache_operation("strategy_service")
async def get_cached_data(key):
    # Automatically tracks hits/misses and duration
    return await redis.get(key)
```

### 6. Data Collection Metrics

Monitor data collection health and performance:

```prometheus
# Collector health (1 = healthy, 0 = unhealthy)
data_collector_health{collector_name="binance", source="binance"}

# Last successful collection timestamp
data_collector_last_success_timestamp{collector_name="binance", source="binance"}

# Data points collected
data_points_collected_total{collector_name="binance", source="binance", data_type="klines"}

# Collection errors
data_collection_errors_total{collector_name="sentiment", source="twitter", error_type="rate_limit"}

# Collection duration
data_collection_duration_seconds_bucket{collector_name="historical", source="binance", le="5.0"}
```

**Histogram Buckets**: `[0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0]`

**Usage**:
```python
from shared.prometheus_metrics import (
    track_data_collection, 
    update_collector_health,
    record_data_points
)

@track_data_collection("binance_collector", "binance")
async def collect_market_data():
    # Automatically tracks duration and health
    data = await fetch_from_binance()
    record_data_points("binance_collector", "binance", "klines", len(data))
    return data

# Manual health update
update_collector_health("binance_collector", "binance", is_healthy=True)
```

### 7. Trading Metrics

Track trading signals, orders, and positions:

```prometheus
# Strategy signals
strategy_signals_total{strategy_id="momentum_v1", symbol="BTCUSDT", signal_type="buy"}

# Orders placed
orders_placed_total{order_type="limit", symbol="ETHUSDT", side="buy"}

# Orders filled
orders_filled_total{order_type="limit", symbol="BTCUSDT"}

# Orders cancelled
orders_cancelled_total{symbol="ETHUSDT", reason="timeout"}

# Order execution duration
order_execution_duration_seconds_bucket{order_type="market", le="0.5"}

# Active positions
active_positions_count{strategy_id="momentum_v1"}

# Position P&L
position_pnl_usd{position_id="pos_123", symbol="BTCUSDT"}

# Portfolio value
portfolio_value_usd{user_id="user_1"}
```

**Histogram Buckets**: `[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0]`

### 8. Goal Tracking Metrics

Monitor user goal progress:

```prometheus
# Goal progress percentage
goal_progress_percentage{goal_id="goal_1", goal_type="daily_profit", user_id="user_1"}

# Current goal value
goal_current_value{goal_id="goal_1", goal_type="daily_profit", user_id="user_1"}

# Target goal value
goal_target_value{goal_id="goal_1", goal_type="daily_profit", user_id="user_1"}

# Goals achieved
goals_achieved_total{goal_type="daily_profit", user_id="user_1"}
```

**Usage**:
```python
from shared.prometheus_metrics import update_goal_metrics, record_goal_achievement

# Update goal progress
update_goal_metrics(
    goal_id="goal_1",
    goal_type="daily_profit",
    user_id="user_1",
    current_value=750.0,
    target_value=1000.0,
    progress_percentage=75.0
)

# Record achievement
record_goal_achievement(goal_type="daily_profit", user_id="user_1")
```

### 9. Risk Management Metrics

Track risk exposures and limit breaches:

```prometheus
# Risk limit breaches
risk_limit_breaches_total{user_id="user_1", limit_type="max_drawdown"}

# Current risk exposure
current_risk_exposure{user_id="user_1", risk_type="portfolio_var"}

# Drawdown percentage
drawdown_percentage{user_id="user_1"}
```

### 10. ML Model Metrics

Monitor machine learning model performance:

```prometheus
# Model predictions
ml_model_predictions_total{model_name="lstm_transformer", model_version="v1"}

# Prediction duration
ml_model_prediction_duration_seconds_bucket{model_name="lstm_transformer", le="1.0"}

# Model accuracy
ml_model_accuracy{model_name="lstm_transformer", model_version="v1"}

# Model drift score
ml_model_drift_score{model_name="lstm_transformer", model_version="v1"}

# Training duration
ml_model_training_duration_seconds_bucket{model_name="lstm_transformer", le="300.0"}
```

**Histogram Buckets** (Prediction): `[0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0]`  
**Histogram Buckets** (Training): `[10.0, 30.0, 60.0, 120.0, 300.0, 600.0, 1800.0]`

**Usage**:
```python
from shared.prometheus_metrics import update_model_metrics

update_model_metrics(
    model_name="lstm_transformer",
    model_version="v1",
    accuracy=0.85,
    drift_score=0.02
)
```

### 11. Alert Metrics

Track alert triggering and delivery:

```prometheus
# Alerts triggered
alerts_triggered_total{alert_type="price_alert", priority="high"}

# Successful deliveries
alert_delivery_success_total{channel="email", alert_type="risk_breach"}

# Failed deliveries
alert_delivery_failures_total{channel="telegram", alert_type="performance", error_type="timeout"}

# Delivery duration
alert_delivery_duration_seconds_bucket{channel="slack", le="2.0"}
```

**Histogram Buckets**: `[0.1, 0.5, 1.0, 2.0, 5.0, 10.0]`

**Usage**:
```python
from shared.prometheus_metrics import record_alert_metrics

record_alert_metrics(
    alert_type="price_alert",
    priority="high",
    channel="email",
    success=True,
    duration_seconds=1.2
)
```

## PromQL Query Examples

### Service Health Monitoring

```promql
# Services currently down
service_up == 0

# Service uptime
time() - service_start_time

# Services with high error rates
rate(http_requests_total{status=~"5.."}[5m]) > 0.01
```

### Performance Monitoring

```promql
# 95th percentile request latency
histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))

# Request rate per service
sum(rate(http_requests_total[5m])) by (service_name)

# Database query latency (P99)
histogram_quantile(0.99, rate(db_query_duration_seconds_bucket[5m]))
```

### Data Collection Health

```promql
# Unhealthy collectors
data_collector_health == 0

# Data collection rate
rate(data_points_collected_total[5m])

# Collection error rate
rate(data_collection_errors_total[5m])

# Time since last successful collection
time() - data_collector_last_success_timestamp
```

### Trading Performance

```promql
# Total trading signals
sum(rate(strategy_signals_total[1h])) by (strategy_id)

# Order fill rate
sum(rate(orders_filled_total[5m])) / sum(rate(orders_placed_total[5m]))

# Total portfolio value
sum(portfolio_value_usd) by (user_id)

# Position P&L summary
sum(position_pnl_usd) by (symbol)
```

### Cache Performance

```promql
# Cache hit ratio
sum(rate(redis_cache_hits_total[5m])) / 
  (sum(rate(redis_cache_hits_total[5m])) + sum(rate(redis_cache_misses_total[5m])))

# Cache operations per second
sum(rate(redis_cache_hits_total[5m]) + rate(redis_cache_misses_total[5m]))
```

### ML Model Monitoring

```promql
# Model accuracy trends
ml_model_accuracy{model_name="lstm_transformer"}

# Models with high drift
ml_model_drift_score > 0.1

# Prediction latency
histogram_quantile(0.95, rate(ml_model_prediction_duration_seconds_bucket[5m]))
```

### Alert System Performance

```promql
# Alert delivery success rate
sum(rate(alert_delivery_success_total[5m])) / 
  (sum(rate(alert_delivery_success_total[5m])) + sum(rate(alert_delivery_failures_total[5m])))

# Alerts triggered per hour
sum(increase(alerts_triggered_total[1h])) by (alert_type)

# Slow alert deliveries
histogram_quantile(0.95, rate(alert_delivery_duration_seconds_bucket[5m])) > 5.0
```

## Grafana Dashboard Integration

### Dashboard 1: System Health

**Panels**:
- Service uptime status (gauge)
- HTTP request rate (graph)
- Error rate per service (graph)
- Request latency P95/P99 (graph)
- Database connections (gauge)
- RabbitMQ message rate (graph)

**Example JSON** (simplified):
```json
{
  "dashboard": {
    "title": "MasterTrade System Health",
    "panels": [
      {
        "title": "Service Status",
        "targets": [
          {"expr": "service_up"}
        ],
        "type": "stat"
      },
      {
        "title": "Request Rate",
        "targets": [
          {"expr": "sum(rate(http_requests_total[5m])) by (service_name)"}
        ],
        "type": "graph"
      }
    ]
  }
}
```

### Dashboard 2: Data Collection

**Panels**:
- Collector health status (gauge)
- Data points collected/sec (graph)
- Collection errors (graph)
- Time since last collection (stat)
- Collection duration P95 (graph)

### Dashboard 3: Trading Performance

**Panels**:
- Active positions count (gauge)
- Order fill rate (graph)
- Portfolio value (graph)
- Position P&L (table)
- Signal generation rate (graph)
- Goal progress (bar chart)

### Dashboard 4: ML Models

**Panels**:
- Model accuracy (gauge)
- Drift score (graph)
- Prediction rate (graph)
- Prediction latency (graph)
- Training duration (stat)

## Alerting Rules

Example Prometheus alerting rules:

```yaml
groups:
  - name: mastertrade_alerts
    interval: 30s
    rules:
      # Service down
      - alert: ServiceDown
        expr: service_up == 0
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "Service {{ $labels.service_name }} is down"
          
      # High error rate
      - alert: HighErrorRate
        expr: rate(http_requests_total{status=~"5.."}[5m]) > 0.05
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High error rate on {{ $labels.service_name }}"
          
      # Collector unhealthy
      - alert: DataCollectorDown
        expr: data_collector_health == 0
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Data collector {{ $labels.collector_name }} is unhealthy"
          
      # Model drift
      - alert: ModelDrift
        expr: ml_model_drift_score > 0.15
        for: 30m
        labels:
          severity: warning
        annotations:
          summary: "Model {{ $labels.model_name }} showing drift"
          
      # Risk breach
      - alert: RiskLimitBreach
        expr: rate(risk_limit_breaches_total[5m]) > 0
        labels:
          severity: critical
        annotations:
          summary: "Risk limit breached for user {{ $labels.user_id }}"
```

## Testing Metrics

### Manual Testing

Test each service's metrics endpoint:

```bash
# Strategy Service
curl http://localhost:8003/metrics

# Risk Manager
curl http://localhost:8002/metrics

# Alert System
curl http://localhost:8007/metrics

# API Gateway
curl http://localhost:8080/metrics

# Market Data Service
curl http://localhost:9001/metrics

# Order Executor
curl http://localhost:9002/metrics
```

### Verify Metric Format

All metrics should be in Prometheus text format:

```
# HELP http_requests_total Total HTTP requests
# TYPE http_requests_total counter
http_requests_total{method="GET",path="/health",status="200"} 123.0

# HELP http_request_duration_seconds Request duration
# TYPE http_request_duration_seconds histogram
http_request_duration_seconds_bucket{method="GET",path="/health",le="0.005"} 45.0
http_request_duration_seconds_bucket{method="GET",path="/health",le="0.01"} 78.0
...
```

## Best Practices

### 1. Cardinality Management

**Avoid high cardinality labels**:
- ❌ Don't use: `user_id` with thousands of users
- ✅ Do use: `user_id` with < 100 users, or aggregate
- ❌ Don't use: Unique IDs as labels (position_id, order_id)
- ✅ Do use: Categories, types, statuses

### 2. Label Naming

- Use snake_case: `service_name`, not `serviceName`
- Be descriptive: `error_type`, not `type`
- Avoid redundancy: `alert_type`, not `alert_alert_type`

### 3. Metric Naming

- Counter: `*_total` suffix (e.g., `requests_total`)
- Gauge: No suffix (e.g., `active_connections`)
- Histogram: `*_seconds` or `*_bytes` (e.g., `duration_seconds`)
- Summary: `*_seconds` or `*_bytes`

### 4. Histogram Bucket Selection

Choose buckets that cover expected value ranges:
- **HTTP requests**: 5ms to 10s
- **Database queries**: 1ms to 10s
- **Data collection**: 100ms to 60s
- **ML predictions**: 10ms to 5s

### 5. Performance Considerations

- Metrics collection overhead: < 1% CPU
- Memory per metric: ~1-5 KB
- Use decorators for automatic tracking
- Batch metric updates when possible

## Troubleshooting

### Metrics Not Appearing

1. **Check service is running**: `curl http://localhost:<port>/health`
2. **Verify /metrics endpoint**: `curl http://localhost:<port>/metrics`
3. **Check logs**: `docker logs <service_name>`
4. **Verify dependencies**: Check requirements.txt has `prometheus-fastapi-instrumentator`

### High Memory Usage

1. **Reduce label cardinality**: Avoid unique IDs in labels
2. **Increase scrape interval**: Prometheus scrapes less frequently
3. **Enable metric expiry**: Remove stale metrics

### Duplicate Metrics

1. **Check for multiple registries**: Only use default registry
2. **Verify service restarts**: Old metrics may persist
3. **Clear Prometheus data**: Remove old time series

## Future Enhancements

- [ ] Add custom business metrics (Sharpe ratio, win rate, etc.)
- [ ] Integrate domain-specific metrics into business logic
- [ ] Create automated Grafana dashboard provisioning
- [ ] Add metric exporters for external systems
- [ ] Implement distributed tracing (OpenTelemetry)
- [ ] Add exemplars for linking metrics to traces

## References

- [Prometheus Documentation](https://prometheus.io/docs/)
- [prometheus-fastapi-instrumentator](https://github.com/trallnag/prometheus-fastapi-instrumentator)
- [Prometheus Best Practices](https://prometheus.io/docs/practices/)
- [Grafana Documentation](https://grafana.com/docs/)

---

**Last Updated**: January 2025  
**Maintained By**: MasterTrade DevOps Team
