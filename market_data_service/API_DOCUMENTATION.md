# Database-Driven Symbol & Stock Index Management API

The Market Data Service now supports dynamic management of both cryptocurrency symbols and stock indices through a database-driven approach. All symbols and indices can be managed via REST API without code changes or service restarts.

## Overview

- **Crypto Symbols**: Trading pairs like BTCUSDC, ETHUSDC with tracking flags
- **Stock Indices**: Major global indices like ^GSPC, ^IXIC with regional categorization
- **Dynamic Configuration**: Add/remove/modify symbols and indices at runtime
- **Priority Management**: Control collection order and resource allocation
- **Regional/Category Filtering**: Organize by asset types and geographical regions

## Crypto Symbol Management

### Get Tracked Symbols
```bash
GET /api/symbols/tracked?asset_type=crypto&exchange=binance
```

### Get All Symbols (including inactive)
```bash
GET /api/symbols/all?include_inactive=true
```

### Add New Crypto Symbol
```bash
POST /api/symbols
Content-Type: application/json

{
  "symbol": "ADAUSDC",
  "base_asset": "ADA", 
  "quote_asset": "USDC",
  "tracking": true,
  "asset_type": "crypto",
  "exchange": "binance",
  "priority": 1,
  "intervals": ["1m", "5m", "15m", "1h", "4h", "1d"],
  "notes": "Cardano trading pair"
}
```

### Update Symbol Configuration
```bash
PUT /api/symbols/ADAUSDC
Content-Type: application/json

{
  "tracking": true,
  "priority": 2,
  "intervals": ["5m", "1h", "1d"],
  "notes": "Updated priority and intervals"
}
```

### Toggle Symbol Tracking
```bash
PUT /api/symbols/ADAUSDC/tracking?tracking=false
```

### Remove Symbol
```bash
DELETE /api/symbols/ADAUSDC
```

## Stock Index Management

### Get Tracked Stock Indices
```bash
# All tracked indices
GET /api/stock-indices/tracked

# Filter by region
GET /api/stock-indices/tracked?region=us

# Filter by category  
GET /api/stock-indices/tracked?category=volatility
```

### Get Indices by Category
```bash
GET /api/stock-indices/categories
```
Returns indices organized by category:
```json
{
  "categories": {
    "us_major": ["^GSPC", "^IXIC", "^DJI"],
    "us_indicators": ["^VIX", "^TNX"],
    "international": ["^FTSE", "^GDAXI", "^N225"],
    "volatility": ["^VIX"],
    "bonds": ["^TNX"]
  }
}
```

### Add New Stock Index
```bash
POST /api/stock-indices
Content-Type: application/json

{
  "symbol": "^KOSPI",
  "full_name": "Korea Composite Stock Price Index",
  "region": "south_korea", 
  "category": "major",
  "tracking": true,
  "priority": 1,
  "intervals": ["1d", "1h"],
  "notes": "South Korean stock market index"
}
```

### Update Stock Index
```bash
PUT /api/stock-indices/^KOSPI
Content-Type: application/json

{
  "tracking": true,
  "priority": 2,
  "category": "international",
  "region": "asia",
  "notes": "Updated categorization"
}
```

### Toggle Index Tracking
```bash
PUT /api/stock-indices/^KOSPI/tracking?tracking=false
```

### Remove Stock Index
```bash
DELETE /api/stock-indices/^KOSPI
```

## Data Model

### Crypto Symbol Structure
```json
{
  "id": "BTCUSDC",
  "symbol": "BTCUSDC",
  "base_asset": "BTC",
  "quote_asset": "USDC", 
  "tracking": true,
  "asset_type": "crypto",
  "exchange": "binance",
  "priority": 1,
  "intervals": ["1m", "5m", "15m", "1h", "4h", "1d"],
  "created_at": "2025-11-04T...",
  "updated_at": "2025-11-04T...",
  "notes": "Bitcoin trading pair"
}
```

### Stock Index Structure  
```json
{
  "id": "^GSPC",
  "symbol": "^GSPC", 
  "base_asset": "S&P 500",
  "quote_asset": "US",
  "tracking": true,
  "asset_type": "stock_index",
  "exchange": "global_markets",
  "priority": 1,
  "intervals": ["1d", "1h"],
  "created_at": "2025-11-04T...",
  "updated_at": "2025-11-04T...",
  "notes": "major us index - Standard & Poor's 500"
}
```

## Migration & Initialization

The system automatically migrates from hardcoded configuration:

1. **First Startup**: If database is empty, populates with DEFAULT_SYMBOLS and STOCK_INDICES from config
2. **Dynamic Loading**: Service loads only symbols/indices with `tracking: true`
3. **Fallback**: If database is unavailable, falls back to configuration
4. **Runtime Updates**: Use `reload_symbols()` and `reload_indices()` methods for dynamic updates

## Service Integration

The collectors automatically use database-driven symbols:

```python
# Crypto symbols
crypto_service.symbols  # Loaded from database
await crypto_service.reload_symbols()  # Reload at runtime

# Stock indices  
index_collector.tracked_indices  # Loaded from database
await index_collector.reload_indices()  # Reload at runtime
```

## Benefits

- ✅ **Zero Downtime Updates**: Add/remove symbols without restarts
- ✅ **Granular Control**: Individual symbol/index enable/disable
- ✅ **Priority Management**: Control resource allocation
- ✅ **Regional Organization**: Filter by geographical regions
- ✅ **Category Classification**: Organize by market types
- ✅ **Audit Trail**: Track changes with timestamps
- ✅ **API Integration**: Full REST API for external systems
- ✅ **Fallback Safety**: Graceful degradation to config