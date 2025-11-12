# MasterTrade API Documentation

## Overview

Comprehensive OpenAPI/Swagger documentation for all MasterTrade services.

## Access Points

### Swagger UI (Interactive)
- **API Gateway**: http://localhost:8000/docs
- **Market Data Service**: http://localhost:8001/docs
- **Strategy Service**: http://localhost:8002/docs
- **Risk Manager**: http://localhost:8003/docs
- **Order Executor**: http://localhost:8004/docs
- **Arbitrage Service**: http://localhost:8005/docs
- **Alert System**: http://localhost:8007/docs

### ReDoc (Alternative Documentation)
- **API Gateway**: http://localhost:8000/redoc
- **Market Data Service**: http://localhost:8001/redoc
- (Similar pattern for all services)

### OpenAPI JSON Schema
- **API Gateway**: http://localhost:8000/openapi.json
- **Market Data Service**: http://localhost:8001/openapi.json
- (Similar pattern for all services)

---

## Documentation Structure

Each service includes:

1. **Operation Summaries**: Brief description of what each endpoint does
2. **Request Schemas**: Detailed models for request bodies
3. **Response Schemas**: Detailed models for response bodies
4. **Error Codes**: HTTP status codes and error responses
5. **Authentication**: Required headers and API keys
6. **Examples**: Sample requests and responses
7. **Tags**: Organized by functionality

---

## API Gateway Endpoints

Base URL: `http://localhost:8000`

### Health & Monitoring

#### GET /health
**Summary**: Health check endpoint  
**Description**: Returns service health status and version information  
**Tags**: `Health`  
**Response**: 200 OK
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "timestamp": "2025-11-12T10:00:00Z"
}
```

#### GET /metrics
**Summary**: Prometheus metrics  
**Description**: Returns metrics in Prometheus format  
**Tags**: `Monitoring`  
**Response**: 200 OK (text/plain)

---

### Dashboard

#### GET /api/dashboard/overview
**Summary**: Get dashboard overview  
**Description**: Returns comprehensive dashboard data including portfolio, active strategies, recent trades  
**Tags**: `Dashboard`  
**Response**: 200 OK
```json
{
  "portfolio": {
    "total_value": 100000.00,
    "available_balance": 50000.00,
    "positions": []
  },
  "active_strategies": [],
  "recent_trades": [],
  "market_summary": {}
}
```

---

### Portfolio

#### GET /api/portfolio/balance
**Summary**: Get portfolio balance  
**Description**: Returns current portfolio balance and positions  
**Tags**: `Portfolio`  
**Response**: 200 OK
```json
{
  "total_usd": 100000.00,
  "available_usd": 50000.00,
  "positions": [
    {
      "symbol": "BTC/USD",
      "quantity": 0.5,
      "avg_entry_price": 45000.00,
      "current_price": 50000.00,
      "pnl": 2500.00,
      "pnl_percent": 5.56
    }
  ],
  "updated_at": "2025-11-12T10:00:00Z"
}
```

---

### Strategies

#### GET /api/strategies
**Summary**: List all strategies  
**Description**: Returns list of all trading strategies with their current status  
**Tags**: `Strategies`  
**Query Parameters**:
- `status` (optional): Filter by status (active, paused, stopped)
- `limit` (optional): Max results (default: 100)
- `offset` (optional): Pagination offset (default: 0)

**Response**: 200 OK
```json
{
  "strategies": [
    {
      "id": "strat-001",
      "name": "BTC Momentum Strategy",
      "status": "active",
      "environment": "paper",
      "symbol": "BTC/USD",
      "timeframe": "1h",
      "pnl": 1500.00,
      "win_rate": 0.65,
      "created_at": "2025-11-01T00:00:00Z",
      "updated_at": "2025-11-12T10:00:00Z"
    }
  ],
  "total": 1,
  "limit": 100,
  "offset": 0
}
```

#### POST /api/strategies/generate
**Summary**: Generate new strategies  
**Description**: Triggers automatic strategy generation based on market conditions  
**Tags**: `Strategies`  
**Request Body**:
```json
{
  "count": 10,
  "symbols": ["BTC/USD", "ETH/USD"],
  "timeframes": ["1h", "4h"],
  "indicators": ["rsi", "macd", "bollinger_bands"],
  "risk_level": "medium"
}
```

**Response**: 200 OK
```json
{
  "status": "queued",
  "job_id": "gen-12345",
  "estimated_completion": "2025-11-12T10:05:00Z",
  "strategies_requested": 10
}
```

---

### Orders

#### GET /api/orders/active
**Summary**: Get active orders  
**Description**: Returns list of currently active orders  
**Tags**: `Orders`  
**Response**: 200 OK
```json
{
  "orders": [
    {
      "id": "order-001",
      "strategy_id": "strat-001",
      "symbol": "BTC/USD",
      "side": "buy",
      "type": "limit",
      "quantity": 0.1,
      "price": 49000.00,
      "status": "open",
      "filled_quantity": 0.0,
      "created_at": "2025-11-12T09:55:00Z"
    }
  ],
  "total": 1
}
```

#### GET /api/orders/recent
**Summary**: Get recent orders  
**Description**: Returns list of recently completed orders  
**Tags**: `Orders`  
**Query Parameters**:
- `limit` (optional): Max results (default: 50)
- `since` (optional): ISO timestamp to filter orders after this time

**Response**: 200 OK

---

### Trades

#### GET /api/trades/recent
**Summary**: Get recent trades  
**Description**: Returns list of recent executed trades  
**Tags**: `Trades`  
**Query Parameters**:
- `limit` (optional): Max results (default: 50)
- `symbol` (optional): Filter by trading pair

**Response**: 200 OK
```json
{
  "trades": [
    {
      "id": "trade-001",
      "order_id": "order-001",
      "strategy_id": "strat-001",
      "symbol": "BTC/USD",
      "side": "buy",
      "quantity": 0.1,
      "price": 49500.00,
      "commission": 4.95,
      "pnl": 0.0,
      "timestamp": "2025-11-12T10:00:00Z"
    }
  ],
  "total": 1
}
```

---

### Signals

#### GET /api/signals/recent
**Summary**: Get recent trading signals  
**Description**: Returns list of recent trading signals generated by strategies  
**Tags**: `Signals`  
**Response**: 200 OK
```json
{
  "signals": [
    {
      "id": "sig-001",
      "strategy_id": "strat-001",
      "symbol": "BTC/USD",
      "signal_type": "buy",
      "strength": 0.85,
      "indicators": {
        "rsi": 35.5,
        "macd": 0.025,
        "volume_surge": 1.45
      },
      "timestamp": "2025-11-12T09:58:00Z"
    }
  ]
}
```

---

### Market Data

#### GET /api/market-data/{symbol}
**Summary**: Get market data for symbol  
**Description**: Returns current market data and recent price history  
**Tags**: `Market Data`  
**Path Parameters**:
- `symbol` (required): Trading pair symbol (e.g., BTC/USD)

**Response**: 200 OK
```json
{
  "symbol": "BTC/USD",
  "current_price": 50000.00,
  "24h_change": 1250.00,
  "24h_change_percent": 2.56,
  "24h_volume": 1500000000.00,
  "24h_high": 50500.00,
  "24h_low": 48500.00,
  "timestamp": "2025-11-12T10:00:00Z",
  "ohlcv": [
    {
      "timestamp": "2025-11-12T09:00:00Z",
      "open": 49000.00,
      "high": 50200.00,
      "low": 48800.00,
      "close": 50000.00,
      "volume": 50000000.00
    }
  ]
}
```

---

### Symbols

#### GET /api/symbols
**Summary**: List all tracked symbols  
**Description**: Returns list of all cryptocurrency trading pairs being tracked  
**Tags**: `Symbols`  
**Response**: 200 OK
```json
{
  "symbols": [
    {
      "symbol": "BTC/USD",
      "base": "BTC",
      "quote": "USD",
      "is_active": true,
      "tracking_enabled": true,
      "exchanges": ["binance", "coinbase"],
      "last_updated": "2025-11-12T10:00:00Z"
    }
  ],
  "total": 1
}
```

#### GET /api/symbols/{symbol}
**Summary**: Get symbol details  
**Description**: Returns detailed information about a specific trading pair  
**Tags**: `Symbols`  
**Path Parameters**:
- `symbol` (required): Trading pair symbol

**Response**: 200 OK

#### GET /api/symbols/{symbol}/historical-data
**Summary**: Get historical data  
**Description**: Returns historical OHLCV data for a symbol  
**Tags**: `Symbols`  
**Path Parameters**:
- `symbol` (required): Trading pair symbol

**Query Parameters**:
- `timeframe` (required): Candle timeframe (1m, 5m, 15m, 1h, 4h, 1d)
- `start` (optional): Start timestamp (ISO format)
- `end` (optional): End timestamp (ISO format)
- `limit` (optional): Max candles to return (default: 500)

**Response**: 200 OK
```json
{
  "symbol": "BTC/USD",
  "timeframe": "1h",
  "data": [
    {
      "timestamp": "2025-11-12T09:00:00Z",
      "open": 49000.00,
      "high": 50200.00,
      "low": 48800.00,
      "close": 50000.00,
      "volume": 50000000.00
    }
  ],
  "count": 1
}
```

#### POST /api/symbols/{symbol}/toggle-tracking
**Summary**: Toggle symbol tracking  
**Description**: Enable or disable tracking for a trading pair  
**Tags**: `Symbols`  
**Path Parameters**:
- `symbol` (required): Trading pair symbol

**Request Body**:
```json
{
  "enabled": true
}
```

**Response**: 200 OK
```json
{
  "symbol": "BTC/USD",
  "tracking_enabled": true,
  "message": "Symbol tracking enabled"
}
```

#### PUT /api/symbols/{symbol}
**Summary**: Update symbol configuration  
**Description**: Update tracking configuration for a symbol  
**Tags**: `Symbols`  
**Path Parameters**:
- `symbol` (required): Trading pair symbol

**Request Body**:
```json
{
  "tracking_enabled": true,
  "exchanges": ["binance", "coinbase"],
  "update_frequency": 60,
  "historical_data_enabled": true
}
```

**Response**: 200 OK

---

### Strategy Environments

#### GET /api/strategy-environments
**Summary**: List strategy environments  
**Description**: Returns list of all strategy deployment environments  
**Tags**: `Strategy Environments`  
**Response**: 200 OK
```json
{
  "environments": [
    {
      "id": "env-001",
      "strategy_id": "strat-001",
      "type": "paper",
      "status": "active",
      "performance": {
        "pnl": 1500.00,
        "win_rate": 0.65,
        "sharpe_ratio": 1.85
      }
    }
  ]
}
```

#### POST /api/strategy-environments/{strategy_id}
**Summary**: Deploy strategy to environment  
**Description**: Creates a new strategy environment deployment  
**Tags**: `Strategy Environments`  
**Path Parameters**:
- `strategy_id` (required): Strategy identifier

**Request Body**:
```json
{
  "environment_type": "paper",
  "initial_capital": 10000.00,
  "risk_parameters": {
    "max_position_size": 0.1,
    "stop_loss_percent": 0.02,
    "take_profit_percent": 0.05
  }
}
```

**Response**: 201 Created

#### GET /api/strategy-environments/{strategy_id}
**Summary**: Get strategy environment details  
**Description**: Returns detailed information about a strategy environment  
**Tags**: `Strategy Environments`  
**Response**: 200 OK

---

### Exchange Environments

#### GET /api/exchange-environments/status
**Summary**: Get exchange environment statuses  
**Description**: Returns connection and health status for all exchange environments  
**Tags**: `Exchange Environments`  
**Response**: 200 OK
```json
{
  "environments": {
    "binance": {
      "status": "connected",
      "latency_ms": 45,
      "last_heartbeat": "2025-11-12T10:00:00Z"
    },
    "coinbase": {
      "status": "connected",
      "latency_ms": 52,
      "last_heartbeat": "2025-11-12T10:00:00Z"
    }
  }
}
```

---

## Market Data Service Endpoints

Base URL: `http://localhost:8001`

### Indicators

#### GET /api/indicators
**Summary**: List available indicators  
**Description**: Returns list of all available technical indicators  
**Tags**: `Indicators`

#### POST /api/indicators/calculate
**Summary**: Calculate indicators  
**Description**: Calculate technical indicators for given market data  
**Tags**: `Indicators`  
**Request Body**:
```json
{
  "symbol": "BTC/USD",
  "indicators": ["rsi", "macd", "bollinger_bands"],
  "timeframe": "1h",
  "period": 100
}
```

### Historical Data

#### GET /api/historical-data/{symbol}
**Summary**: Get historical OHLCV data  
**Description**: Returns historical candle data for analysis  
**Tags**: `Historical Data`

---

## Strategy Service Endpoints

Base URL: `http://localhost:8002`

### Strategy Management

#### POST /api/strategies
**Summary**: Create new strategy  
**Description**: Creates a new trading strategy  
**Tags**: `Strategies`

#### GET /api/strategies/{strategy_id}
**Summary**: Get strategy details  
**Description**: Returns detailed information about a strategy  
**Tags**: `Strategies`

#### PUT /api/strategies/{strategy_id}
**Summary**: Update strategy  
**Description**: Updates strategy configuration  
**Tags**: `Strategies`

#### DELETE /api/strategies/{strategy_id}
**Summary**: Delete strategy  
**Description**: Deletes a strategy and its associated data  
**Tags**: `Strategies`

### Backtesting

#### POST /api/backtest
**Summary**: Run backtest  
**Description**: Executes a backtest for a strategy  
**Tags**: `Backtesting`  
**Request Body**:
```json
{
  "strategy_id": "strat-001",
  "start_date": "2025-01-01T00:00:00Z",
  "end_date": "2025-11-01T00:00:00Z",
  "initial_capital": 10000.00,
  "commission": 0.001
}
```

**Response**: 200 OK
```json
{
  "backtest_id": "bt-12345",
  "status": "running",
  "estimated_completion": "2025-11-12T10:05:00Z"
}
```

#### GET /api/backtest/{backtest_id}/results
**Summary**: Get backtest results  
**Description**: Returns results from a completed backtest  
**Tags**: `Backtesting`

---

## Risk Manager Endpoints

Base URL: `http://localhost:8003`

### Risk Checks

#### POST /api/risk/check-order
**Summary**: Check order risk  
**Description**: Validates if an order meets risk management criteria  
**Tags**: `Risk Management`  
**Request Body**:
```json
{
  "strategy_id": "strat-001",
  "symbol": "BTC/USD",
  "side": "buy",
  "quantity": 0.1,
  "price": 50000.00
}
```

**Response**: 200 OK
```json
{
  "approved": true,
  "risk_score": 0.35,
  "warnings": [],
  "constraints": {
    "max_position_size": 0.1,
    "current_exposure": 0.05
  }
}
```

### Portfolio Risk

#### GET /api/risk/portfolio-metrics
**Summary**: Get portfolio risk metrics  
**Description**: Returns current portfolio risk metrics and exposure  
**Tags**: `Risk Management`

---

## Order Executor Endpoints

Base URL: `http://localhost:8004`

### Order Management

#### POST /api/orders
**Summary**: Submit new order  
**Description**: Submits a new order for execution  
**Tags**: `Orders`  
**Request Body**:
```json
{
  "strategy_id": "strat-001",
  "symbol": "BTC/USD",
  "side": "buy",
  "type": "limit",
  "quantity": 0.1,
  "price": 49000.00,
  "time_in_force": "GTC"
}
```

#### GET /api/orders/{order_id}
**Summary**: Get order status  
**Description**: Returns current status of an order  
**Tags**: `Orders`

#### DELETE /api/orders/{order_id}
**Summary**: Cancel order  
**Description**: Cancels an active order  
**Tags**: `Orders`

---

## Alert System Endpoints

Base URL: `http://localhost:8007`

### Alert Configuration

#### GET /api/alerts
**Summary**: List all alerts  
**Description**: Returns list of all configured alerts  
**Tags**: `Alerts`

#### POST /api/alerts
**Summary**: Create new alert  
**Description**: Creates a new alert configuration  
**Tags**: `Alerts`  
**Request Body**:
```json
{
  "service_name": "strategy_service",
  "health_metric": "strategy_pnl",
  "operator": "<",
  "threshold": -1000.00,
  "priority": "high",
  "channels": ["email", "slack"],
  "consecutive_failures": 1
}
```

#### PUT /api/alerts/{alert_id}
**Summary**: Update alert  
**Description**: Updates an existing alert configuration  
**Tags**: `Alerts`

#### DELETE /api/alerts/{alert_id}
**Summary**: Delete alert  
**Description**: Deletes an alert configuration  
**Tags**: `Alerts`

### Alert History

#### GET /api/alerts/history
**Summary**: Get alert history  
**Description**: Returns history of triggered alerts  
**Tags**: `Alerts`

---

## Common Response Schemas

### Error Response
```json
{
  "error": {
    "code": "INVALID_REQUEST",
    "message": "Invalid request parameters",
    "details": {
      "field": "quantity",
      "issue": "Must be greater than 0"
    },
    "timestamp": "2025-11-12T10:00:00Z"
  }
}
```

### HTTP Status Codes

- **200 OK**: Request successful
- **201 Created**: Resource created successfully
- **400 Bad Request**: Invalid request parameters
- **401 Unauthorized**: Authentication required
- **403 Forbidden**: Insufficient permissions
- **404 Not Found**: Resource not found
- **409 Conflict**: Resource conflict (e.g., duplicate)
- **422 Unprocessable Entity**: Validation error
- **429 Too Many Requests**: Rate limit exceeded
- **500 Internal Server Error**: Server error
- **503 Service Unavailable**: Service temporarily unavailable

---

## Authentication

### API Key Authentication

Include API key in request headers:
```
X-API-Key: your_api_key_here
```

### JWT Token Authentication

For user-based authentication:
```
Authorization: Bearer <jwt_token>
```

---

## Rate Limiting

- **Default Limit**: 100 requests per minute per IP
- **Authenticated**: 1000 requests per minute per API key
- **Headers**:
  - `X-RateLimit-Limit`: Request limit
  - `X-RateLimit-Remaining`: Remaining requests
  - `X-RateLimit-Reset`: Reset timestamp

---

## WebSocket Endpoints

### Real-time Updates

Connect to WebSocket for real-time data streams:

```javascript
const ws = new WebSocket('ws://localhost:8000/ws');

// Subscribe to market data
ws.send(JSON.stringify({
  action: 'subscribe',
  channel: 'market_data',
  symbol: 'BTC/USD'
}));

// Subscribe to trade updates
ws.send(JSON.stringify({
  action: 'subscribe',
  channel: 'trades',
  strategy_id: 'strat-001'
}));
```

### Available Channels

- `market_data`: Real-time price updates
- `trades`: Trade execution updates
- `orders`: Order status updates
- `signals`: Trading signal alerts
- `portfolio`: Portfolio balance updates

---

## Code Examples

### Python

```python
import requests

# Get dashboard overview
response = requests.get('http://localhost:8000/api/dashboard/overview')
data = response.json()
print(data)

# Submit new order
order = {
    "strategy_id": "strat-001",
    "symbol": "BTC/USD",
    "side": "buy",
    "type": "limit",
    "quantity": 0.1,
    "price": 49000.00
}
response = requests.post('http://localhost:8004/api/orders', json=order)
print(response.json())
```

### JavaScript

```javascript
// Fetch market data
fetch('http://localhost:8000/api/market-data/BTC/USD')
  .then(response => response.json())
  .then(data => console.log(data));

// Create alert
const alert = {
  service_name: 'strategy_service',
  health_metric: 'strategy_pnl',
  operator: '<',
  threshold: -1000.00,
  priority: 'high',
  channels: ['email']
};

fetch('http://localhost:8007/api/alerts', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(alert)
})
.then(response => response.json())
.then(data => console.log(data));
```

### cURL

```bash
# Health check
curl http://localhost:8000/health

# Get strategies
curl http://localhost:8000/api/strategies

# Submit order with authentication
curl -X POST http://localhost:8004/api/orders \
  -H "X-API-Key: your_api_key" \
  -H "Content-Type: application/json" \
  -d '{
    "strategy_id": "strat-001",
    "symbol": "BTC/USD",
    "side": "buy",
    "type": "limit",
    "quantity": 0.1,
    "price": 49000.00
  }'
```

---

## Testing

### Swagger UI Testing

1. Navigate to `http://localhost:8000/docs`
2. Click on any endpoint
3. Click "Try it out"
4. Fill in parameters
5. Click "Execute"
6. View response

### Postman Collection

Import the OpenAPI schema into Postman:

1. Open Postman
2. Click Import
3. Enter URL: `http://localhost:8000/openapi.json`
4. Click Import
5. All endpoints will be available in Postman

---

## Changelog

### Version 1.0.0 (2025-11-12)

Initial API documentation release covering:
- API Gateway endpoints
- Market Data Service endpoints
- Strategy Service endpoints
- Risk Manager endpoints
- Order Executor endpoints
- Alert System endpoints
- WebSocket real-time updates
- Authentication and rate limiting
- Error handling
- Code examples

---

## Support

For API support:
- Documentation: http://localhost:8000/docs
- Issues: GitHub Issues
- Email: dev@mastertrade.com

---

**Last Updated**: 2025-11-12  
**API Version**: 1.0.0  
**Documentation Version**: 1.0.0
