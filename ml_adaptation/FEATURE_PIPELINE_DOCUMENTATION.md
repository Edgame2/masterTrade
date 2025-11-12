# Feature Computation Pipeline

## Overview

The Feature Computation Pipeline is a comprehensive system for computing ML features from multiple data sources and storing them in the PostgreSQL feature store for model training and strategy evaluation.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│         FeatureComputationPipeline                  │
├─────────────────────────────────────────────────────┤
│                                                      │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────┐ │
│  │  Technical   │  │  On-Chain    │  │  Social   │ │
│  │  Features    │  │  Features    │  │  Features │ │
│  └──────────────┘  └──────────────┘  └───────────┘ │
│                                                      │
│  ┌──────────────┐  ┌──────────────────────────────┐ │
│  │   Macro      │  │    Composite Features        │ │
│  │  Features    │  │  (Derived from above)        │ │
│  └──────────────┘  └──────────────────────────────┘ │
│                                                      │
│  ┌──────────────────────────────────────────────┐   │
│  │      Auto-Registration & Storage             │   │
│  └──────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
                        │
                        ▼
           ┌─────────────────────────┐
           │  PostgreSQLFeatureStore │
           └─────────────────────────┘
```

## Feature Types

### 1. Technical Features (from market data)
- **RSI (14-period)**: Relative Strength Index
- **MACD**: Line, signal, histogram components
- **Moving Averages**: SMA 20/50/200, EMA 12/26
- **Bollinger Bands**: Upper, middle, lower, width percentage

### 2. On-Chain Features (from blockchain data)
- **NVT Ratio**: Network Value to Transactions
- **MVRV Ratio**: Market Value to Realized Value
- **Exchange Flows**: Net inflow/outflow to exchanges
- **Active Addresses**: Number of unique active addresses
- **Hash Rate**: Network computational power
- **Transaction Count**: Daily transaction volume

### 3. Social Features (from Twitter/Reddit)
- **Sentiment Score**: Average sentiment by source (-1 to +1)
- **Social Volume**: Total mentions in 24h
- **Sentiment Volatility**: Standard deviation of sentiment
- **Sentiment Momentum**: Recent vs older sentiment comparison
- **Engagement Rate**: Total engagement count

### 4. Macro Features (from traditional markets)
- **VIX**: Volatility Index
- **DXY**: US Dollar Index
- **Stock Indices**: S&P 500, NASDAQ, Dow Jones
- **Market Sentiment**: Bullish/Neutral/Bearish
- **Fear & Greed Index**: Market sentiment indicator (0-100)

### 5. Composite Features (derived)
- **Risk Score**: Combined BB width + VIX (0-100)
- **Sentiment Alignment**: RSI + social sentiment correlation
- **Market Strength**: MACD + exchange flows indicator
- **Sentiment Divergence**: Macro vs social sentiment difference

## Usage

### Basic Usage

```python
from ml_adaptation.feature_pipeline import FeatureComputationPipeline
from ml_adaptation.feature_store import PostgreSQLFeatureStore
from shared.postgres_manager import PostgresManager
from market_data_service.database import Database

# Initialize
postgres_manager = PostgresManager(db_config)
await postgres_manager.initialize()

market_db = Database(postgres_manager)
feature_store = PostgreSQLFeatureStore(postgres_manager)

pipeline = FeatureComputationPipeline(
    market_data_db=market_db,
    feature_store=feature_store,
    enable_auto_registration=True
)

await pipeline.initialize()

# Compute and store features
symbol = "BTCUSDT"
feature_count = await pipeline.compute_and_store_features(symbol)
print(f"Stored {feature_count} features for {symbol}")
```

### Compute Without Storing

```python
# Get features dict without storing
features = await pipeline.compute_all_features("BTCUSDT")

print(f"RSI: {features.get('rsi_14')}")
print(f"Social Sentiment: {features.get('social_sentiment_avg')}")
print(f"Risk Score: {features.get('composite_risk_score')}")
```

### Compute Individual Feature Types

```python
# Technical features only
technical = await pipeline.compute_technical_features("BTCUSDT", datetime.now())

# On-chain features only
onchain = await pipeline.compute_onchain_features("BTCUSDT", datetime.now())

# Social features only
social = await pipeline.compute_social_features("BTCUSDT", datetime.now())

# Macro features only
macro = await pipeline.compute_macro_features(datetime.now())
```

### Backtest Feature Computation

```python
from datetime import datetime, timedelta

# Compute features for a time range
start_time = datetime.now() - timedelta(days=30)
end_time = datetime.now()

results = await pipeline.compute_features_for_backtest(
    symbol="BTCUSDT",
    start_time=start_time,
    end_time=end_time,
    interval_hours=4  # Compute every 4 hours
)

# results = [(timestamp, features_dict), ...]
for timestamp, features in results:
    print(f"{timestamp}: {len(features)} features")
```

### Feature Summary

```python
# Get statistics on available features
summary = await pipeline.get_feature_summary()

print(f"Total features: {summary['total_features']}")
print(f"By type: {summary['features_by_type']}")
print(f"Total values: {summary['total_feature_values']}")
print(f"Unique symbols: {summary['unique_symbols']}")
```

## Auto-Registration

The pipeline automatically registers new features in the feature store on first computation. Features are categorized by name prefix:

- `rsi_*`, `macd_*`, `sma_*`, `ema_*`, `bb_*` → **technical**
- `onchain_*` → **onchain**
- `social_*` → **social**
- `macro_*` → **macro**
- `composite_*` → **composite**

Registration includes:
- Feature name (unique)
- Feature type
- Description
- Data sources (table names)
- Computation logic reference
- Version number

## Database Integration

### Required Database Methods

The pipeline requires a database instance with these methods:

```python
# Technical indicators
await db.get_indicator_results(symbol, hours, limit)

# On-chain metrics
await db.get_onchain_metrics(symbol, metric_name, hours, limit)

# Social sentiment
await db.get_social_sentiment(symbol, source, hours, limit)

# Stock indices
await db.get_all_current_stock_indices()

# Market summary
await db.get_stock_market_summary()

# Sentiment data
await db.get_sentiment_data(hours, limit)
```

## Error Handling

The pipeline includes comprehensive error handling:

- Graceful degradation: If one feature type fails, others continue
- Logging: All errors logged with context (symbol, feature type, error details)
- Empty results: Returns empty dict rather than failing
- Missing data: Skips features when source data unavailable

## Performance Considerations

### Bulk Operations

The pipeline uses bulk storage for efficiency:

```python
# Single call stores all features for a symbol
await pipeline.compute_and_store_features("BTCUSDT")
# → Computes 50+ features
# → Single bulk INSERT operation
```

### Caching

The pipeline does not cache internally but relies on:
- Database connection pooling (asyncpg)
- Database query caching (PostgreSQL)
- Feature store retrieval optimization (DISTINCT ON queries)

### Concurrent Processing

For multiple symbols:

```python
import asyncio

symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]

# Process concurrently
tasks = [pipeline.compute_and_store_features(s) for s in symbols]
results = await asyncio.gather(*tasks, return_exceptions=True)
```

## Testing

Run the test suite:

```bash
bash ml_adaptation/test_feature_pipeline.sh
```

Tests verify:
1. File and class structure
2. All compute methods exist
3. All feature types implemented
4. Auto-registration functionality
5. Database integration
6. Feature store integration
7. Composite features logic
8. Error handling
9. Logging
10. Bulk operations
11. Backtesting support
12. Python syntax
13. Required imports
14. Code completeness

## Integration with Strategy Service

See next P0 task: "Integrate feature store with strategy service"

The pipeline will be integrated into the strategy service to provide features for:
- Strategy evaluation
- Signal generation
- Model training
- Backtesting

## Future Enhancements

- **Real-time feature updates**: Subscribe to data changes
- **Feature versioning**: Track feature computation changes
- **Feature quality metrics**: Monitor feature value distributions
- **Automated feature engineering**: Generate new composite features
- **Feature importance tracking**: Monitor which features drive performance

## File Locations

- **Implementation**: `ml_adaptation/feature_pipeline.py` (745 lines)
- **Tests**: `ml_adaptation/test_feature_pipeline.sh`
- **Feature Store**: `ml_adaptation/feature_store.py`
- **Database Schema**: `ml_adaptation/migrations/create_feature_store_tables.sql`

## Status

✅ **COMPLETED** - November 11, 2025
- All feature types implemented
- Auto-registration working
- Bulk operations optimized
- Comprehensive testing
- Ready for integration
