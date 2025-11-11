# Quick Reference: Automatic Historical Data Collection

## System Overview
✓ When Strategy Service selects the best cryptocurrencies for trading
✓ Historical data is automatically downloaded from Binance
✓ All data is stored in Azure Cosmos DB
✓ No manual intervention required

## How It Works

### Automatic Trigger
```
Daily Crypto Selection → Historical Data Check → Download if Missing → Store in Cosmos DB
```

### Data Collected
- **Timeframes**: 1m, 5m, 15m, 1h, 4h, 1d
- **History**: 90 days per cryptocurrency
- **Source**: Binance REST API
- **Storage**: Azure Cosmos DB (market_data container)

## API Endpoints

### Trigger Collection
```bash
POST http://localhost:8000/api/collect-historical-data
```

**Example:**
```bash
curl -X POST "http://localhost:8000/api/collect-historical-data?symbols=BTCUSDC&symbols=ETHUSDC&timeframes=1h&timeframes=4h&days_back=30"
```

### Check Status
```bash
GET http://localhost:8000/api/historical-data-status/{symbol}
```

**Example:**
```bash
curl "http://localhost:8000/api/historical-data-status/BTCUSDC?timeframe=1h"
```

## Configuration Files

### Market Data Service
`market_data_service/.env`
```bash
COSMOS_ENDPOINT=https://your-cosmos.documents.azure.com:443/
COSMOS_KEY=your-cosmos-key
COSMOS_DATABASE=masterTrade
COSMOS_CONTAINER=market_data
```

### Strategy Service
`strategy_service/crypto_selection_engine.py`
```python
# Configured to collect:
timeframes = ['1m', '5m', '15m', '1h', '4h', '1d']
days_back = 90
force_refresh = False  # Only collect if missing
```

## Testing

### Test Binance Connectivity
```bash
cd market_data_service
./venv/bin/python test_historical_download.py
```

### Test Full Download
```bash
./venv/bin/python test_historical_download.py --full
```

### Test Client Integration
```bash
cd ../strategy_service
./venv/bin/python market_data_client.py
```

## Monitoring

### Check Service Status
```bash
./status.sh
```

### View Logs
```bash
# Market Data Service
tail -f /tmp/market_data.log

# Strategy Service
tail -f /tmp/strategy_service.log

# Watch for collection events
tail -f /tmp/market_data.log | grep -i "historical"
```

### Check Data in Cosmos DB
```sql
SELECT COUNT(1) as count, c.symbol, c.interval 
FROM c 
WHERE c.symbol = 'BTCUSDC'
GROUP BY c.symbol, c.interval
```

## Typical Collection Times

| Timeframe | Days | Records | Time     |
|-----------|------|---------|----------|
| 1m        | 90   | 129,600 | 2-3 min  |
| 5m        | 90   | 25,920  | 30-45 sec|
| 15m       | 90   | 8,640   | 15-20 sec|
| 1h        | 90   | 2,160   | 3-5 sec  |
| 4h        | 90   | 540     | 1-2 sec  |
| 1d        | 90   | 90      | 1 sec    |

**Total per symbol (all timeframes):** ~4-5 minutes

## Data Structure in Cosmos DB

```json
{
  "id": "uuid",
  "symbol": "BTCUSDC",
  "interval": "1h",
  "timestamp": "2025-11-08T10:00:00Z",
  "open_price": 102311.12,
  "high_price": 102536.84,
  "low_price": 102118.03,
  "close_price": 102427.82,
  "volume": 112.15862,
  "quote_volume": 11483385.95,
  "trades_count": 12203,
  "taker_buy_base": 81.12965,
  "taker_buy_quote": 8308175.08,
  "data_source": "binance_api",
  "created_at": "2025-11-08T10:30:00Z"
}
```

## Troubleshooting

### No Data Collected
```bash
# Check Binance API
curl https://api.binance.com/api/v3/ping

# Verify service running
curl http://localhost:8000/health

# Check Cosmos DB connection
# Look for connection errors in logs
```

### Rate Limit Errors
```python
# Increase delay in historical_data_collector.py
self.rate_limit_delay = 0.3  # Increase from 0.1 to 0.3
```

### Timeout Errors
```python
# Increase timeout in market_data_client.py
timeout = aiohttp.ClientTimeout(total=600)  # 10 minutes
```

## Common Commands

```bash
# Restart all services
./restart.sh

# Stop all services
./stop.sh

# Check service status
./status.sh

# Test historical download
cd market_data_service && ./venv/bin/python test_historical_download.py

# Manually trigger collection for specific symbols
curl -X POST "http://localhost:8000/api/collect-historical-data?symbols=BTCUSDC&timeframes=1h&days_back=7"
```

## Key Features

✓ **Smart Collection**: Only downloads data if missing
✓ **Automatic**: Triggered by crypto selection process
✓ **Comprehensive**: All supported timeframes
✓ **Reliable**: Retry logic and error handling
✓ **Efficient**: Rate limiting and batch processing
✓ **Monitored**: Detailed logging and status checks

## Support

📖 Full Documentation: `AUTOMATIC_HISTORICAL_DATA_COLLECTION.md`
🔍 Logs: `/tmp/market_data.log` and `/tmp/strategy_service.log`
✅ Health Check: `http://localhost:8000/health`
📊 Status: `http://localhost:8000/api/historical-data-status/{symbol}`
