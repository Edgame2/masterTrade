# Stock Market Indices Collection & Correlation Analysis System

## Overview

This system provides comprehensive stock market indices data collection and advanced correlation analysis between traditional markets and cryptocurrency markets. It's designed to enhance trading strategies by identifying market relationships and generating correlation-based signals.

## Components

### 1. Stock Index Data Collector (`stock_index_collector.py`)

**Purpose**: Collects real-time and historical data for major global stock indices

**Features**:
- Multi-source data collection (Yahoo Finance, Alpha Vantage)
- Support for major global indices (S&P 500, NASDAQ, DOW, VIX, CAC 40, FTSE 100, Nikkei 225, etc.)
- Real-time current values with market state
- Historical data collection (daily and intraday)
- Dynamic index management (add/remove indices from database)
- Category-based organization (US, European, Asian, Volatility indices)

**Key Methods**:
```python
# Fetch current values for all tracked indices
current_data = await collector.fetch_current_index_values()

# Collect historical data for specific index
record_count = await collector.collect_historical_index_data("^GSPC", days_back=90)

# Get all index data
results = await collector.collect_all_index_data()
```

**Tracked Indices** (configurable in `config.py`):
- **US Major**: ^GSPC (S&P 500), ^IXIC (NASDAQ), ^DJI (DOW), ^RUT (Russell 2000)
- **Volatility**: ^VIX (CBOE Volatility Index)
- **European**: ^FTSE (FTSE 100), ^GDAXI (DAX), ^FCHI (CAC 40)
- **Asian**: ^N225 (Nikkei 225), ^HSI (Hang Seng), 000001.SS (Shanghai Composite)

### 2. Correlation Analyzer (`stock_index_correlation_analyzer.py`)

**Purpose**: Advanced statistical correlation analysis between stock indices and crypto markets

**Features**:
- Multiple correlation methods (Pearson, Spearman, Kendall)
- Rolling correlation detection (identify changing relationships)
- Market regime classification (Bull, Bear, Sideways, High/Low Volatility)
- Cross-market correlation analysis
- Correlation-based trading signal generation
- Statistical significance testing

**Correlation Types**:

1. **Pearson Correlation**: Linear relationship between assets
   ```python
   corr = await analyzer.calculate_price_correlation(
       "^GSPC",
       "BTCUSDT",
       hours_back=168,
       method=CorrelationType.PEARSON
   )
   ```

2. **Spearman Correlation**: Rank-based (non-linear) relationships
   ```python
   corr = await analyzer.calculate_price_correlation(
       "^VIX",
       "BTCUSDT",
       hours_back=168,
       method=CorrelationType.SPEARMAN
   )
   ```

3. **Rolling Correlation**: Detect changing relationships over time
   ```python
   rolling = await analyzer.calculate_rolling_correlation(
       "^GSPC",
       "BTCUSDT",
       hours_back=720,  # 30 days
       window_hours=168  # 7-day rolling window
   )
   ```

**Market Regime Detection**:
```python
regime = await analyzer.analyze_market_regime(
    "BTCUSDT",
    hours_back=168
)
# Returns: primary_regime, volatility, price_change, mean_return
```

**Correlation Strength Classification**:
- Very Strong: |r| ≥ 0.7
- Strong: |r| ≥ 0.5
- Moderate: |r| ≥ 0.3
- Weak: |r| ≥ 0.1
- Very Weak: |r| < 0.1

**Trading Signal Generation**:
```python
signals = await analyzer.get_correlation_based_signals(
    "BTCUSDT",
    hours_back=168
)
# Returns: overall_signal (bullish/bearish/neutral), confidence, contributing_factors
```

**Signal Logic**:
- High positive correlation with rising indices → Bullish signal
- High positive correlation with falling indices → Bearish signal
- Negative correlation with bearish markets → Contrarian bullish signal
- Confidence based on number of significant correlations

### 3. Stock Index Scheduler (`stock_index_scheduler.py`)

**Purpose**: Automated periodic execution of data collection and analysis tasks

**Scheduled Tasks**:

| Task | Frequency | Description |
|------|-----------|-------------|
| Current Data Collection | 15 min (market hours) / 60 min (off hours) | Real-time index values |
| Intraday Data Collection | 15 min (market hours) | 5-minute candle data |
| Correlation Analysis | 60 min | Cross-market correlation matrix |
| Market Regime Detection | 30 min | Classify market states |
| Signal Generation | 60 min | Correlation-based trade signals |
| Historical Backfill | Daily at 2 AM UTC | Fill data gaps |
| Index Reload | Hourly | Check for new tracked indices |

**Market Hours Detection**:
- US Markets: 14:30 - 21:00 UTC (9:30 AM - 4:00 PM EST)
- European Markets: 07:00 - 15:30 UTC
- Asian Markets: 00:00 - 06:00 UTC

**Statistics Tracking**:
```python
stats = scheduler.get_stats()
# Returns: collection_runs, correlation_runs, errors, last_collection, etc.
```

## Installation

1. **Install Dependencies**:
```bash
cd market_data_service
pip install -r requirements.txt
```

Required packages:
- `yfinance==0.2.28` - Yahoo Finance data
- `scipy==1.11.4` - Statistical analysis
- `pandas==2.1.4` - Data manipulation
- `numpy==1.26.2` - Numerical computing

2. **Configure Environment Variables**:
```bash
# Azure Cosmos DB (required)
export COSMOS_ENDPOINT=<your-endpoint>
export COSMOS_KEY=<your-key>
export COSMOS_DATABASE_NAME=trading_bot

# Optional API keys for additional data sources
export ALPHA_VANTAGE_API_KEY=<your-key>
export FINNHUB_API_KEY=<your-key>
```

3. **Configure Stock Indices** (in `config.py`):
```python
STOCK_INDEX_ENABLED = True
STOCK_INDEX_HISTORICAL_DAYS = 365

STOCK_INDICES = [
    "^GSPC",  # S&P 500
    "^IXIC",  # NASDAQ
    "^DJI",   # DOW
    "^VIX",   # Volatility
    # Add more...
]

STOCK_INDEX_CATEGORIES = {
    "us_major": ["^GSPC", "^IXIC", "^DJI"],
    "volatility": ["^VIX"],
    "european": ["^FTSE", "^FCHI", "^GDAXI"],
    "asian": ["^N225", "^HSI"]
}
```

## Usage

### Standalone Data Collection

```bash
# Collect data for all configured indices
cd market_data_service
python stock_index_collector.py
```

### Run Correlation Analysis

```bash
# Run correlation analysis
python stock_index_correlation_analyzer.py
```

### Start Automated Scheduler

```bash
# Start the scheduler service
./start_stock_index_scheduler.sh
```

The scheduler will:
- Initialize database connection
- Load tracked indices
- Start periodic data collection
- Run correlation analysis every hour
- Detect market regimes every 30 minutes
- Generate trading signals

### Programmatic Usage

```python
from database import Database
from stock_index_collector import StockIndexDataCollector
from stock_index_correlation_analyzer import StockIndexCorrelationAnalyzer

async def main():
    database = Database()
    
    async with database:
        # Initialize collector
        collector = StockIndexDataCollector(database)
        await collector.connect()
        
        # Collect data
        results = await collector.collect_all_index_data()
        
        # Initialize analyzer
        analyzer = StockIndexCorrelationAnalyzer(database)
        
        # Run comprehensive analysis
        correlations = await analyzer.analyze_cross_market_correlations(
            stock_indices=["^GSPC", "^IXIC", "^VIX"],
            crypto_symbols=["BTC", "ETH", "BNB"],
            hours_back=168,
            interval="1h"
        )
        
        # Get trading signals for Bitcoin
        signals = await analyzer.get_correlation_based_signals("BTCUSDT")
        
        print(f"BTC Signal: {signals['overall_signal']}")
        print(f"Confidence: {signals['confidence']:.2%}")
        
        await collector.disconnect()
```

## Database Schema

### Market Data Documents

**Current Index Values**:
```json
{
  "id": "GSPC_current_1234567890",
  "symbol": "^GSPC",
  "normalized_symbol": "GSPC",
  "asset_type": "stock_index_current",
  "timestamp": "2024-01-01T12:00:00Z",
  "current_price": 4500.00,
  "previous_close": 4480.00,
  "change": 20.00,
  "change_percent": 0.45,
  "volume": 1000000000,
  "day_high": 4510.00,
  "day_low": 4475.00,
  "metadata": {
    "full_name": "S&P 500",
    "currency": "USD",
    "exchange": "SNP",
    "market_state": "REGULAR"
  }
}
```

**Historical Index Data**:
```json
{
  "id": "GSPC_1h_1234567890",
  "symbol": "^GSPC",
  "asset_type": "stock_index",
  "interval": "1h",
  "timestamp": "2024-01-01T12:00:00Z",
  "open_price": "4480.00",
  "high_price": "4490.00",
  "low_price": "4475.00",
  "close_price": "4485.00",
  "volume": "50000000",
  "source": "yahoo_finance"
}
```

**Correlation Results**:
```json
{
  "id": "corr_^GSPC_BTCUSDT_1234567890",
  "doc_type": "significant_correlation",
  "symbol1": "^GSPC",
  "symbol2": "BTCUSDT",
  "correlation_coefficient": 0.65,
  "p_value": 0.001,
  "strength": "strong",
  "significance": "significant",
  "method": "pearson",
  "data_points": 168,
  "time_period_hours": 168,
  "interval": "1h"
}
```

**Market Regime**:
```json
{
  "id": "regime_BTCUSDT_1234567890",
  "doc_type": "market_regime",
  "symbol": "BTCUSDT",
  "primary_regime": "bull",
  "all_regimes": ["bull", "high_volatility"],
  "price_change": 0.085,
  "volatility": 0.032,
  "mean_return": 0.0012,
  "current_price": 45000.00
}
```

**Correlation Signals**:
```json
{
  "id": "corr_signal_BTCUSDT_1234567890",
  "doc_type": "correlation_signal",
  "symbol": "BTCUSDT",
  "overall_signal": "bullish",
  "confidence": 0.75,
  "contributing_factors": [
    {
      "factor": "High correlation with bullish ^GSPC",
      "direction": "bullish",
      "weight": 0.65
    },
    {
      "factor": "Negative correlation with bearish ^VIX",
      "direction": "bullish",
      "weight": 0.32
    }
  ]
}
```

## Integration with Trading Strategies

### Using Correlation Signals in Strategy Service

```python
# In strategy_service/enhanced_market_data_consumer.py

async def get_correlation_signals(self, symbol: str) -> Dict:
    """Get latest correlation-based signals"""
    query = """
    SELECT * FROM c 
    WHERE c.doc_type = 'correlation_signal' 
    AND c.symbol = @symbol 
    ORDER BY c.timestamp DESC 
    OFFSET 0 LIMIT 1
    """
    
    results = list(self.container.query_items(
        query=query,
        parameters=[{"name": "@symbol", "value": symbol}],
        enable_cross_partition_query=True
    ))
    
    return results[0] if results else None

# In strategy execution
correlation_signal = await market_data.get_correlation_signals("BTCUSDT")

if correlation_signal:
    if correlation_signal['overall_signal'] == 'bullish' and correlation_signal['confidence'] > 0.6:
        # Increase position size or confidence
        strategy_confidence *= 1.2
    elif correlation_signal['overall_signal'] == 'bearish' and correlation_signal['confidence'] > 0.6:
        # Reduce position or skip trade
        strategy_confidence *= 0.8
```

### Market Regime-Based Strategy Adjustment

```python
async def adjust_strategy_for_regime(self, symbol: str):
    """Adjust strategy parameters based on market regime"""
    regime_data = await self.get_latest_market_regime(symbol)
    
    if regime_data:
        if regime_data['primary_regime'] == 'high_volatility':
            # Widen stop loss, reduce position size
            self.stop_loss_percent *= 1.5
            self.position_size_percent *= 0.7
        elif regime_data['primary_regime'] == 'low_volatility':
            # Tighter stops, can increase size
            self.stop_loss_percent *= 0.8
            self.position_size_percent *= 1.2
```

## Performance Considerations

### Data Collection Efficiency

1. **Batch Processing**: Data stored in batches of 100-500 records
2. **Rate Limiting**: 0.5-2 second delays between API calls
3. **Market Hours Optimization**: More frequent collection during trading hours
4. **Caching**: Current values cached for 5 minutes

### Correlation Analysis Optimization

1. **Minimum Data Points**: Requires 20+ data points for reliable correlations
2. **Parallel Processing**: Multiple correlations calculated concurrently
3. **Rolling Windows**: Efficient pandas rolling calculations
4. **Storage Optimization**: Only significant correlations stored (|r| > 0.3, p < 0.05)

### Resource Usage

- **Memory**: ~200-500 MB (depending on data volume)
- **CPU**: Low (mostly I/O bound with periodic analysis spikes)
- **Network**: Moderate (API calls every 15-60 minutes)
- **Database**: ~10-50 documents per hour per index

## Monitoring & Debugging

### Check Scheduler Status

```python
from stock_index_scheduler import StockIndexScheduler

scheduler = StockIndexScheduler()
await scheduler.initialize()

stats = scheduler.get_stats()
print(f"Running: {stats['running']}")
print(f"Collection runs: {stats['stats']['collection_runs']}")
print(f"Correlation runs: {stats['stats']['correlation_runs']}")
print(f"Errors: {stats['stats']['errors']}")
print(f"Last collection: {stats['stats']['last_collection']}")
```

### View Recent Correlations

```python
# Query database for recent correlations
query = """
SELECT * FROM c 
WHERE c.doc_type = 'significant_correlation' 
AND c.timestamp > @since 
ORDER BY c.timestamp DESC
"""

results = container.query_items(
    query=query,
    parameters=[{"name": "@since", "value": one_hour_ago}],
    enable_cross_partition_query=True
)
```

### Logs

Structured logging with `structlog`:
```
2024-01-01 12:00:00 [info] Stock index data collection completed records=15 total_runs=42
2024-01-01 13:00:00 [info] Correlation analysis completed stock_crypto_pairs=120 significant_correlations=35
2024-01-01 13:05:00 [info] Correlation signal generated symbol=BTCUSDT signal=bullish confidence=0.75
```

## Troubleshooting

### Common Issues

**1. No data collected**:
- Check internet connection
- Verify Yahoo Finance is accessible
- Check if indices are correctly formatted (e.g., "^GSPC" not "GSPC")

**2. Insufficient data for correlation**:
- Ensure historical data collection has run
- Check database for existing market data
- Verify time ranges align between assets

**3. Scheduler not running during market hours**:
- Check timezone settings (scheduler uses UTC)
- Verify `is_market_hours()` logic
- Ensure system clock is accurate

**4. High error count**:
- Check API rate limits
- Verify database connection
- Review logs for specific error messages

## Future Enhancements

1. **Additional Data Sources**: IEX Cloud, Polygon.io, Finnhub
2. **Machine Learning**: Predict correlation changes, regime transitions
3. **Advanced Signals**: Multi-timeframe correlation, lead-lag analysis
4. **Volatility Clustering**: Detect volatility spillover effects
5. **Sector Analysis**: Track sector-specific indices
6. **Commodity Correlations**: Include gold, oil, currencies
7. **Sentiment Integration**: Combine with social sentiment data
8. **Real-time WebSocket**: Live index updates during market hours

## References

- **Statistical Methods**: [Pearson, Spearman, Kendall Correlations](https://en.wikipedia.org/wiki/Correlation_and_dependence)
- **Yahoo Finance API**: [yfinance Documentation](https://pypi.org/project/yfinance/)
- **Market Regimes**: [Regime Detection in Finance](https://www.investopedia.com/terms/m/market-regime.asp)
- **Correlation Trading**: [Pairs Trading and Correlation Strategies](https://www.investopedia.com/terms/p/pairstrade.asp)

---

**Status**: ✅ Complete and Production-Ready

**Last Updated**: 2024-01-01

**Version**: 1.0.0
