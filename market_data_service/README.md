# Enhanced Market Data Service - Real-time, Historical & Sentiment Analysis

The Enhanced Market Data Service is a comprehensive solution for cryptocurrency data collection and analysis, featuring:

🏛️ **Historical Data Collection** - Binance REST API integration for complete market history  
📡 **Real-time Streaming** - WebSocket connections for live market data  
🧠 **Sentiment Analysis** - Multi-source sentiment tracking (news, social media, market indicators)  
☁️ **Azure Cosmos DB** - Scalable cloud database with optimized indexing  
🔄 **Data Access API** - Unified REST API for all data consumption  

## 🚀 Key Features

- **Multi-timeframe Data**: 1m, 5m, 15m, 1h, 4h, 1d intervals
- **15+ Trading Pairs**: All major cryptocurrencies paired with USDC
- **Sentiment Tracking**: Fear & Greed Index, news sentiment, social media analysis  
- **Real-time Updates**: Sub-second market data via WebSocket
- **Gap Detection**: Automatic backfill of missing historical data
- **Performance Optimized**: Cosmos DB partitioning and composite indexing

## Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Binance WSS   │───▶│  Market Data     │───▶│  Azure Cosmos   │
│   (Real-time)   │    │   Service        │    │      DB         │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                │
                                ▼
                       ┌──────────────────┐    ┌─────────────────┐
                       │  Data Access     │───▶│  Other Services │
                       │     API          │    │  (Strategy,     │
                       └──────────────────┘    │  Arbitrage)     │
                                               └─────────────────┘
```

## Components

### 1. Market Data Collector (`market_data_service.py`)
- Connects to Binance WebSocket streams
- Processes real-time kline (candlestick) data
- Stores aggregated data in Azure Cosmos DB
- Publishes updates to RabbitMQ for real-time notifications

### 2. Data Access API (`data_access_api.py`)
- FastAPI-based REST API
- Provides endpoints for querying historical and real-time data
- Implements caching for improved performance
- Exposes Prometheus metrics

### 3. Market Data Consumer (`market_data_consumer.py`)
- Python client library for other services
- Abstracts API calls with convenient methods
- Includes trend analysis and price monitoring utilities

## Azure Cosmos DB Configuration

### Database Structure
```
Database: mastertrade
Container: market_data
Partition Key: /symbol
```

### Indexing Policy
```json
{
  "indexingMode": "consistent",
  "automatic": true,
  "includedPaths": [
    {
      "path": "/*"
    }
  ],
  "excludedPaths": [
    {
      "path": "/\"_etag\"/?"
    }
  ],
  "compositeIndexes": [
    [
      {
        "path": "/symbol",
        "order": "ascending"
      },
      {
        "path": "/interval",
        "order": "ascending"
      },
      {
        "path": "/timestamp",
        "order": "descending"
      }
    ]
  ]
}
```

### TTL Policy
- **Default TTL**: 2,592,000 seconds (30 days)
- Automatic cleanup of old data to manage storage costs
- Configurable via `TTL_SECONDS` environment variable

## Environment Variables

```bash
# Azure Cosmos DB Configuration
COSMOS_ENDPOINT=https://your-account.documents.azure.com:443/
COSMOS_DATABASE=mastertrade
COSMOS_CONTAINER=market_data
MANAGED_IDENTITY_CLIENT_ID=your-managed-identity-client-id

# Message Queue
RABBITMQ_URL=amqp://admin:password123@rabbitmq:5672/

# API Configuration
BINANCE_WSS_URL=wss://stream.binance.com:9443/ws/
LOG_LEVEL=INFO

# Data Retention
TTL_SECONDS=2592000  # 30 days
```

## Data Schema

### Market Data Document
```json
{
  "id": "BTCUSDC_1m_1704110400",
  "symbol": "BTCUSDC",
  "interval": "1m",
  "timestamp": "2024-01-01T12:00:00Z",
  "open_price": "42000.50",
  "high_price": "42100.75",
  "low_price": "41950.25",
  "close_price": "42050.00",
  "volume": "125.45",
  "number_of_trades": 1250,
  "taker_buy_base_asset_volume": "62.75",
  "taker_buy_quote_asset_volume": "2640512.50",
  "_ts": 1704110400
}
```

## API Endpoints

### Health Check
```http
GET /health
```

### Market Data
```http
GET /api/market-data/{symbol}
?interval=1m&limit=100&hours_back=24
```

### Latest Price
```http
GET /api/latest-price/{symbol}
```

### OHLCV Data (Charting)
```http
GET /api/ohlcv/{symbol}
?interval=1m&limit=500
```

### Symbol Statistics
```http
GET /api/stats/{symbol}
```

### Metrics (Prometheus)
```http
GET /metrics
```

## Usage Examples

### Using the Market Data Consumer

```python
from market_data_consumer import MarketDataConsumer

async def main():
    async with MarketDataConsumer("http://localhost:8005") as consumer:
        # Get latest BTC price
        btc_price = await consumer.get_latest_price("BTCUSDC")
        print(f"BTC: ${btc_price['price']}")
        
        # Get historical data
        history = await consumer.get_market_data("BTCUSDC", "1h", 24)
        print(f"Got {len(history)} hours of data")
        
        # Analyze trend
        trend = await consumer.get_price_trend("BTCUSDC", "5m", 20)
        print(f"Trend: {trend['trend_direction']}")
```

### Direct API Usage

```python
import aiohttp

async def get_btc_price():
    async with aiohttp.ClientSession() as session:
        async with session.get("http://localhost:8005/api/latest-price/BTCUSDC") as resp:
            data = await resp.json()
            return data['price']
```

## Deployment

### Docker Compose
The service is configured in `docker-compose.yml` with two containers:

1. **market_data_service**: Data collector
2. **data_access_api**: REST API (port 8005)

### Authentication
Uses Azure Managed Identity for Cosmos DB authentication. In production:

1. Assign a managed identity to your compute resource
2. Grant the identity appropriate permissions on Cosmos DB
3. Set `MANAGED_IDENTITY_CLIENT_ID` environment variable

### Local Development
For local development without managed identity:

```python
# In database.py, uncomment the connection string method:
# self.client = CosmosClient.from_connection_string(connection_string)
```

## Performance Considerations

### Query Optimization
- Queries are optimized using composite indexes
- Partition key (`/symbol`) is always included in queries
- Time-based queries use the timestamp field efficiently

### Caching Strategy
- In-memory cache with 60-second TTL
- Cache keys include all query parameters
- Separate cache metrics for monitoring hit rates

### Scaling
- Cosmos DB auto-scales based on Request Units (RU/s)
- Consider partitioning strategy for high-volume symbols
- Monitor RU consumption and adjust accordingly

## Monitoring

### Prometheus Metrics
- `market_data_requests_total`: Total API requests by endpoint
- `market_data_response_time_seconds`: Response time histogram
- `market_data_cache_hits_total`: Cache hit counters
- `cosmos_operations_total`: Database operations (from database.py)
- `cosmos_response_time_seconds`: Database response times

### Logging
Structured logging with JSON format:
- Request/response logging
- Error tracking with context
- Performance metrics
- Database operation logs

### Health Checks
- Service health endpoints for container orchestration
- Database connectivity checks
- WebSocket connection status

## Troubleshooting

### Common Issues

1. **Connection Errors**
   - Verify Cosmos DB endpoint and credentials
   - Check managed identity permissions
   - Validate network connectivity

2. **Performance Issues**
   - Monitor RU consumption in Azure Portal
   - Check index usage with query metrics
   - Verify partition key distribution

3. **Data Inconsistencies**
   - Check WebSocket reconnection logic
   - Verify error handling in data processing
   - Monitor RabbitMQ message delivery

### Debugging Commands

```bash
# Check service logs
docker logs mastertrade_market_data
docker logs mastertrade_data_api

# Test API endpoints
curl http://localhost:8005/health
curl http://localhost:8005/api/latest-price/BTCUSDC

# Monitor metrics
curl http://localhost:8005/metrics
```

## Security

### Best Practices
- Use managed identity for authentication
- Implement proper CORS settings for production
- Monitor access patterns for anomalies
- Regular security updates for dependencies

### Network Security
- Configure appropriate firewall rules
- Use private endpoints for Cosmos DB in production
- Implement rate limiting for public APIs

## Contributing

When modifying the market data service:

1. Update indexes if changing query patterns
2. Test with realistic data volumes
3. Monitor RU consumption impact
4. Update API documentation for new endpoints
5. Add appropriate tests and metrics