# Data Source Management API Documentation

## Overview
HTTP REST API for managing data collectors in the Market Data Service. Provides operational control over collectors including enable/disable, rate limit configuration, circuit breaker management, and cost monitoring.

**Base URL**: `http://localhost:8000`

## Endpoints

### 1. List All Collectors
Get a list of all data collectors with their current status and metrics.

**Endpoint**: `GET /collectors`

**Response**:
```json
{
  "success": true,
  "collectors": {
    "moralis": {
      "name": "moralis",
      "type": "onchain",
      "enabled": true,
      "connected": true,
      "rate_limiter": {
        "current_rate": 5.0,
        "backoff_multiplier": 2.0,
        "total_requests": 1234,
        "total_throttles": 5,
        "total_backoffs": 2
      },
      "circuit_breaker": {
        "state": "closed",
        "failure_count": 0,
        "failure_threshold": 5,
        "health_score": 0.98
      }
    },
    "historical": {
      "name": "historical",
      "type": "market_data",
      "enabled": true,
      "connected": true
    }
  },
  "total_count": 2,
  "timestamp": "2025-11-11T13:00:00Z"
}
```

### 2. Get Collector Status
Get detailed status information for a specific collector.

**Endpoint**: `GET /collectors/{name}`

**Path Parameters**:
- `name` (string, required): Collector name (e.g., `moralis`, `glassnode`, `twitter`, `reddit`, `lunarcrush`, `historical`)

**Response**:
```json
{
  "success": true,
  "collector": {
    "name": "moralis",
    "enabled": true,
    "connected": true,
    "timestamp": "2025-11-11T13:00:00Z",
    "rate_limiter": {
      "current_rate": 5.0,
      "initial_rate": 10.0,
      "backoff_multiplier": 2.0,
      "max_backoff": 16.0,
      "statistics": {
        "total_requests": 1234,
        "total_throttles": 5,
        "total_backoffs": 2,
        "total_429_errors": 3,
        "total_adjustments": 10
      },
      "endpoint_details": {
        "/v2/api": {
          "requests": 500,
          "rate_limit": 3000,
          "remaining": 2500,
          "reset_time": "2025-11-11T14:00:00Z"
        }
      }
    },
    "circuit_breaker": {
      "state": "closed",
      "failure_count": 0,
      "failure_threshold": 5,
      "health_score": 0.98,
      "statistics": {
        "total_failures": 10,
        "total_successes": 1224,
        "circuit_opens": 0,
        "successful_recoveries": 0,
        "failed_recoveries": 0
      }
    }
  }
}
```

### 3. Enable Collector
Enable a data collector.

**Endpoint**: `POST /collectors/{name}/enable`

**Path Parameters**:
- `name` (string, required): Collector name

**Response**:
```json
{
  "success": true,
  "message": "Collector moralis is enabled",
  "collector": "moralis"
}
```

### 4. Disable Collector
Disable a data collector (disconnects the collector).

**Endpoint**: `POST /collectors/{name}/disable`

**Path Parameters**:
- `name` (string, required): Collector name

**Response**:
```json
{
  "success": true,
  "message": "Collector moralis has been disabled",
  "collector": "moralis"
}
```

### 5. Restart Collector
Restart a collector (disconnect and reconnect).

**Endpoint**: `POST /collectors/{name}/restart`

**Path Parameters**:
- `name` (string, required): Collector name

**Response**:
```json
{
  "success": true,
  "message": "Collector moralis has been restarted",
  "collector": "moralis"
}
```

### 6. Configure Rate Limit
Update rate limit configuration for a collector.

**Endpoint**: `PUT /collectors/{name}/rate-limit`

**Path Parameters**:
- `name` (string, required): Collector name

**Request Body**:
```json
{
  "max_requests_per_second": 10.0,
  "backoff_multiplier": 2.0,
  "max_backoff": 16.0
}
```

**Fields** (all optional):
- `max_requests_per_second` (float): New rate limit in requests per second
- `backoff_multiplier` (float): Multiplier for exponential backoff (≥ 1.0)
- `max_backoff` (float): Maximum backoff multiplier (≥ 1.0)

**Response**:
```json
{
  "success": true,
  "message": "Rate limit configuration updated for moralis",
  "collector": "moralis",
  "updated_config": {
    "max_requests_per_second": 10.0,
    "backoff_multiplier": 2.0,
    "max_backoff": 16.0
  }
}
```

### 7. Reset Circuit Breaker
Reset circuit breaker state for a collector (clears all counters and statistics).

**Endpoint**: `POST /collectors/{name}/circuit-breaker/reset`

**Path Parameters**:
- `name` (string, required): Collector name

**Response**:
```json
{
  "success": true,
  "message": "Circuit breaker reset for moralis",
  "collector": "moralis",
  "new_state": {
    "state": "closed",
    "failure_count": 0,
    "health_score": 1.0
  }
}
```

### 8. Force Circuit Breaker State
Manually force circuit breaker to open or closed state.

**Endpoint**: `PUT /collectors/{name}/circuit-breaker/state`

**Path Parameters**:
- `name` (string, required): Collector name

**Request Body**:
```json
{
  "state": "open"
}
```

**Fields**:
- `state` (string, required): Target state - either `"open"` or `"closed"`

**Response**:
```json
{
  "success": true,
  "message": "Circuit breaker forced to open for moralis",
  "collector": "moralis",
  "new_state": {
    "state": "open",
    "failure_count": 0
  }
}
```

### 9. Get Collector Costs
Get cost and quota information for all collectors.

**Endpoint**: `GET /collectors/costs`

**Response**:
```json
{
  "success": true,
  "collectors": {
    "moralis": {
      "tier": "Pro",
      "monthly_quota": 3000000,
      "cost_per_call": 0.00001,
      "quota_unit": "compute_units",
      "current_usage": {
        "api_calls": 1234,
        "estimated_cost": 0.01234
      },
      "quota_remaining": null
    },
    "glassnode": {
      "tier": "Professional",
      "daily_quota": 10000,
      "cost_per_call": 0.001,
      "quota_unit": "requests",
      "current_usage": {
        "api_calls": 500,
        "estimated_cost": 0.50
      }
    }
  },
  "totals": {
    "total_api_calls": 1734,
    "total_estimated_cost": 0.51
  },
  "timestamp": "2025-11-11T13:00:00Z"
}
```

## Error Responses

All endpoints return errors in the following format:

```json
{
  "success": false,
  "error": "Error message description"
}
```

**Common HTTP Status Codes**:
- `200` - Success
- `400` - Bad Request (invalid parameters)
- `404` - Not Found (collector doesn't exist)
- `500` - Internal Server Error

## Usage Examples

### Enable and Configure a Collector

```bash
# 1. Check current status
curl http://localhost:8000/collectors/moralis

# 2. Configure rate limit
curl -X PUT http://localhost:8000/collectors/moralis/rate-limit \
  -H "Content-Type: application/json" \
  -d '{"max_requests_per_second": 15.0}'

# 3. Reset circuit breaker if needed
curl -X POST http://localhost:8000/collectors/moralis/circuit-breaker/reset

# 4. Verify configuration
curl http://localhost:8000/collectors/moralis
```

### Monitor Costs

```bash
# Get cost summary
curl http://localhost:8000/collectors/costs | jq '.totals'

# Get specific collector cost
curl http://localhost:8000/collectors/costs | jq '.collectors.moralis'
```

### Emergency Operations

```bash
# Force circuit breaker open (emergency stop)
curl -X PUT http://localhost:8000/collectors/moralis/circuit-breaker/state \
  -H "Content-Type: application/json" \
  -d '{"state": "open"}'

# Restart collector
curl -X POST http://localhost:8000/collectors/moralis/restart

# Force circuit breaker closed (resume operations)
curl -X PUT http://localhost:8000/collectors/moralis/circuit-breaker/state \
  -H "Content-Type: application/json" \
  -d '{"state": "closed"}'
```

## Supported Collectors

### On-Chain Data Collectors
- `moralis` - Moralis blockchain data API
- `glassnode` - Glassnode on-chain metrics

### Social Media Collectors
- `twitter` - Twitter/X sentiment analysis
- `reddit` - Reddit cryptocurrency discussions
- `lunarcrush` - LunarCrush social analytics

### Market Data Collectors
- `historical` - Historical price data from Binance
- `sentiment` - Aggregated sentiment data
- `stock_index` - Stock market indices (S&P 500, NASDAQ, VIX)

## Rate Limiter Features

The adaptive rate limiter automatically:
- Parses rate limit headers from API responses
- Applies exponential backoff on 429 errors
- Tracks per-endpoint rate limits
- Persists state to Redis
- Adjusts rates based on response times

## Circuit Breaker Features

The enhanced circuit breaker provides:
- Three states: closed, open, half-open
- Gradual recovery with success tracking
- Configurable failure thresholds
- Manual override capabilities
- Redis state persistence
- Health score calculation
- Comprehensive statistics

## Integration with Monitoring

All collector operations are:
- Logged with structured logging
- Tracked in Prometheus metrics (port 9001)
- Stored in PostgreSQL database
- Cached in Redis for performance

## Notes

- All timestamps are in ISO 8601 format with UTC timezone
- Rate limits are requests per second (floating point)
- Circuit breaker health scores range from 0.0 (all failures) to 1.0 (all successes)
- Configuration changes are persisted to Redis automatically
- Costs are estimates based on API tier pricing
