# Automatic Historical Data Collection System

## Overview

The MasterTrade system now automatically downloads and stores historical market data in Azure Cosmos DB when the Strategy Service selects cryptocurrencies for trading. This ensures that sufficient historical data is always available for backtesting, technical analysis, and strategy execution.

## Architecture

```
┌─────────────────────┐
│  Strategy Service   │
│                     │
│  Crypto Selection   │
│      Engine         │
└──────────┬──────────┘
           │
           │ 1. Selects best cryptos
           │
           ▼
    ┌──────────────────────┐
    │ Market Data Client   │
    └──────────┬───────────┘
               │
               │ 2. Requests historical data
               │
               ▼
    ┌──────────────────────────┐
    │  Market Data Service     │
    │                          │
    │  Data Access API         │
    └──────────┬───────────────┘
               │
               │ 3. Triggers collection
               │
               ▼
    ┌──────────────────────────┐
    │ Historical Data          │
    │     Collector            │
    └──────────┬───────────────┘
               │
               │ 4. Downloads from Binance
               │
               ▼
    ┌──────────────────────────┐
    │      Binance API         │
    └──────────┬───────────────┘
               │
               │ 5. Stores in database
               │
               ▼
    ┌──────────────────────────┐
    │   Azure Cosmos DB        │
    │                          │
    │   market_data container  │
    └──────────────────────────┘
```

## Components

### 1. Strategy Service - Crypto Selection Engine
**File:** `strategy_service/crypto_selection_engine.py`

**New Method:** `_ensure_historical_data_for_selections()`

When the daily crypto selection process completes:
1. Extracts symbols from selected cryptocurrencies
2. Calls Market Data Client to ensure historical data availability
3. Logs collection results for monitoring

**Configuration:**
- Timeframes: `['1m', '5m', '15m', '1h', '4h', '1d']`
- Days back: `90 days` of historical data
- Collection mode: Smart (only collects if data is missing)

### 2. Market Data Client
**File:** `strategy_service/market_data_client.py`

**Key Methods:**

#### `ensure_historical_data_available()`
- Checks if historical data exists for each symbol
- Only triggers collection if data is missing or insufficient
- Returns detailed status for each symbol and timeframe

#### `trigger_historical_data_collection()`
- Sends POST request to Market Data Service
- Specifies symbols, timeframes, and date range
- Handles timeouts (5-minute timeout for large collections)

#### `check_historical_data_status()`
- Queries Cosmos DB to verify data availability
- Checks record count and date coverage
- Determines if data is sufficient for trading

### 3. Market Data Service - Data Access API
**File:** `market_data_service/data_access_api.py`

**New Endpoints:**

#### `POST /api/collect-historical-data`
Triggers historical data collection for specified symbols.

**Parameters:**
```python
symbols: List[str]        # Trading symbols to collect
timeframes: List[str]     # Timeframes (default: ['1h', '4h', '1d'])
days_back: int            # Days of history (default: 30)
```

**Response:**
```json
{
  "status": "completed",
  "total_records": 5040,
  "symbols_processed": 3,
  "timeframes_processed": 3,
  "results": {
    "BTCUSDC": {
      "1h": {"status": "success", "records_collected": 720},
      "4h": {"status": "success", "records_collected": 180},
      "1d": {"status": "success", "records_collected": 30}
    }
  },
  "timestamp": "2025-11-08T10:30:00Z"
}
```

#### `GET /api/historical-data-status/{symbol}`
Checks if sufficient historical data exists.

**Parameters:**
```python
symbol: str         # Trading symbol
timeframe: str      # Timeframe to check (default: '1h')
```

**Response:**
```json
{
  "symbol": "BTCUSDC",
  "timeframe": "1h",
  "has_sufficient_data": true,
  "record_count": 720,
  "earliest_data": "2025-10-09T00:00:00Z",
  "latest_data": "2025-11-08T00:00:00Z",
  "days_covered": 30
}
```

### 4. Historical Data Collector
**File:** `market_data_service/historical_data_collector.py`

Downloads data from Binance API and stores in Cosmos DB:
- Uses Binance `/api/v3/klines` endpoint
- Handles rate limiting (0.2s between requests)
- Implements retry logic for failed requests
- Batches data for efficient Cosmos DB insertion
- Handles timezone conversions properly

## Data Flow

### Daily Selection Process

1. **Strategy Service** runs daily cryptocurrency selection:
   ```python
   selected_cryptos = await engine.run_daily_selection()
   ```

2. **For each selected crypto**, the system:
   - Checks if 90 days of historical data exists
   - Calculates required data points per timeframe:
     * 1m: ~129,600 records
     * 5m: ~25,920 records
     * 15m: ~8,640 records
     * 1h: ~2,160 records
     * 4h: ~540 records
     * 1d: ~90 records

3. **If data is missing**, triggers collection:
   - Downloads from Binance in batches
   - Stores each candle with full OHLCV data
   - Indexes by symbol, timestamp, and interval

4. **Data stored in Cosmos DB** with structure:
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
     "data_source": "binance_api"
   }
   ```

## Configuration

### Environment Variables

**Market Data Service** (`market_data_service/.env`):
```bash
# Azure Cosmos DB
COSMOS_ENDPOINT=https://your-cosmos.documents.azure.com:443/
COSMOS_KEY=your-cosmos-key
COSMOS_DATABASE=masterTrade
COSMOS_CONTAINER=market_data

# Binance API
BINANCE_REST_API_URL=https://api.binance.com
BINANCE_API_KEY=optional-for-higher-limits
BINANCE_API_SECRET=optional-for-higher-limits

# Historical Data
HISTORICAL_DATA_DAYS=365
HISTORICAL_INTERVALS=["1m","5m","15m","1h","4h","1d"]
HISTORICAL_BATCH_SIZE=1000
```

**Strategy Service** Configuration:
```python
# market_data_client.py
MARKET_DATA_SERVICE_URL = "http://localhost:8000"
COLLECTION_TIMEOUT = 300  # seconds (5 minutes)
```

## Usage Examples

### Manual Historical Data Collection

Test the collection manually:

```bash
cd /home/neodyme/Documents/Projects/masterTrade/market_data_service
./venv/bin/python test_historical_download.py --full
```

### Programmatic Collection

```python
from market_data_client import MarketDataClient

async def collect_data_for_symbols():
    async with MarketDataClient() as client:
        result = await client.ensure_historical_data_available(
            symbols=['BTCUSDC', 'ETHUSDC', 'ADAUSDC'],
            timeframes=['1h', '4h', '1d'],
            days_back=90
        )
        print(f"Collected: {result}")
```

### Check Data Availability

```python
async def check_data():
    async with MarketDataClient() as client:
        status = await client.check_historical_data_status('BTCUSDC', '1h')
        print(f"Has data: {status['has_sufficient_data']}")
        print(f"Records: {status['record_count']}")
```

## Monitoring

### Logs to Monitor

**Strategy Service:**
```
INFO: Ensuring historical data availability for selected cryptocurrencies
INFO: Historical data collected for BTCUSDC
INFO: Sufficient historical data exists for ETHUSDC
```

**Market Data Service:**
```
INFO: Historical data collection requested
INFO: Collecting BTCUSDC - 1h (days_back=90)
INFO: Collected 2160 records for BTCUSDC - 1h
```

### Health Checks

Check if services are running:
```bash
# Market Data Service
curl http://localhost:8000/health

# Check data status
curl "http://localhost:8000/api/historical-data-status/BTCUSDC?timeframe=1h"
```

## Performance

### Collection Times (Approximate)

Per symbol, per timeframe:
- 1m (90 days): ~2-3 minutes (129,600 records)
- 5m (90 days): ~30-45 seconds (25,920 records)
- 15m (90 days): ~15-20 seconds (8,640 records)
- 1h (90 days): ~3-5 seconds (2,160 records)
- 4h (90 days): ~1-2 seconds (540 records)
- 1d (90 days): ~1 second (90 records)

**Total for 1 symbol, all timeframes:** ~4-5 minutes

### Cosmos DB RU Consumption

Estimated Request Units per collection:
- Insert: ~10 RU per document
- Query (check status): ~2-3 RU
- Per symbol collection: ~1,500-2,000 RU

## Error Handling

The system gracefully handles:
1. **Binance API rate limits** - Automatic delays between requests
2. **Network timeouts** - Retry logic with exponential backoff
3. **Cosmos DB throttling** - Batch insertion with RU management
4. **Missing data** - Logs warnings but continues
5. **Service unavailability** - Selection process continues even if collection fails

## Troubleshooting

### Issue: No data collected
**Check:**
1. Binance API connectivity: `curl https://api.binance.com/api/v3/ping`
2. Market Data Service running: `./status.sh`
3. Cosmos DB connection: Check logs for connection errors

### Issue: Incomplete data
**Check:**
1. Rate limiting - increase delays if getting 429 errors
2. Timeouts - increase client timeout if collections fail
3. Symbol validity - ensure symbols exist on Binance

### Issue: Slow collection
**Optimize:**
1. Reduce `days_back` parameter
2. Collect fewer timeframes initially
3. Use parallel collection for multiple symbols

## Future Enhancements

1. **Incremental Updates**: Only fetch new data since last collection
2. **Parallel Collection**: Download multiple symbols simultaneously
3. **Data Validation**: Verify data quality after collection
4. **Automatic Backfill**: Detect and fill gaps in historical data
5. **Caching**: Cache frequently accessed historical data
6. **Compression**: Store older data in compressed format

## Related Files

- `strategy_service/crypto_selection_engine.py` - Triggers collection
- `strategy_service/market_data_client.py` - HTTP client
- `market_data_service/data_access_api.py` - REST API endpoints
- `market_data_service/historical_data_collector.py` - Binance downloader
- `market_data_service/test_historical_download.py` - Test script
- `market_data_service/database.py` - Cosmos DB operations

## Testing

Run the test suite:
```bash
# Test Binance connectivity
cd market_data_service
./venv/bin/python test_historical_download.py

# Test client
cd ../strategy_service
./venv/bin/python market_data_client.py
```

## Support

For issues or questions:
1. Check logs: `tail -f /tmp/market_data.log /tmp/strategy_service.log`
2. Verify services: `./status.sh`
3. Test connectivity: See troubleshooting section above
