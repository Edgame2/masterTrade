# Macro-Economic Data Collection System

## Overview

This system provides comprehensive macro-economic data collection to enhance trading strategies with fundamental market context. It collects critical economic indicators, commodity prices, currency movements, and market sentiment data from multiple free and paid sources.

## Components

### 1. Macro-Economic Data Collector (`macro_economic_collector.py`)

**Purpose**: Collects macro-economic indicators from multiple sources

**Data Categories**:

#### A. Commodities (Yahoo Finance)
- **Gold (GC=F)**: Safe haven asset, inflation hedge
- **Silver (SI=F)**: Industrial and precious metal
- **Crude Oil WTI (CL=F)**: Energy benchmark
- **Brent Crude (BZ=F)**: International oil benchmark
- **Natural Gas (NG=F)**: Energy commodity
- **Copper (HG=F)**: Industrial demand indicator

**Updates**: Every 15 minutes during market hours, hourly off-hours

#### B. Currency Indices & Pairs (Yahoo Finance)
- **DXY (DX-Y.NYB)**: US Dollar Index - critical for crypto correlation
- **EUR/USD (EURUSD=X)**: Most liquid currency pair
- **GBP/USD (GBPUSD=X)**: British Pound
- **USD/JPY (USDJPY=X)**: Risk sentiment indicator
- **AUD/USD, USD/CAD, USD/CHF**: Additional major pairs

**Updates**: Every 15 minutes (24/7 market)

#### C. Treasury Yields (Yahoo Finance)
- **13-Week Treasury (^IRX)**: Short-term rates
- **5-Year Treasury (^FVX)**: Medium-term rates
- **10-Year Treasury (^TNX)**: Benchmark yield
- **30-Year Treasury (^TYX)**: Long-term rates

**Updates**: Daily at 21:00 UTC (after US market close)

#### D. FRED Economic Indicators (Federal Reserve)

**Requires**: FRED API key (free from https://fred.stlouisfed.org/docs/api/api_key.html)

**Interest Rates**:
- **DFF**: Federal Funds Rate (Target)
- **FEDFUNDS**: Effective Federal Funds Rate

**Inflation**:
- **CPIAUCSL**: Consumer Price Index
- **CPILFESL**: Core CPI (ex Food & Energy)
- **PPIACO**: Producer Price Index

**GDP**:
- **GDP**: Gross Domestic Product
- **A191RL1Q225SBEA**: Real GDP Growth Rate

**Employment**:
- **UNRATE**: Unemployment Rate
- **PAYEMS**: Nonfarm Payrolls
- **ICSA**: Initial Jobless Claims

**Volatility**:
- **VIXCLS**: VIX Volatility Index

**Updates**: Daily at 08:00 UTC (FRED updates overnight)

#### E. Market Sentiment
- **Crypto Fear & Greed Index**: 0-100 scale from alternative.me
  - 0-25: Extreme Fear
  - 26-45: Fear
  - 46-55: Neutral
  - 56-75: Greed
  - 76-100: Extreme Greed

**Updates**: Every 6 hours

### 2. Macro-Economic Scheduler (`macro_economic_scheduler.py`)

**Purpose**: Automated periodic data collection

**Schedule**:
| Data Type | Frequency | Time (UTC) | Notes |
|-----------|-----------|------------|-------|
| Commodities | 15 min / 60 min | Market hours / Off-hours | Adaptive frequency |
| Currencies | 15 min | 24/7 | Forex market never closes |
| Treasury Yields | Daily | 21:00 | After US market close |
| FRED Indicators | Daily | 08:00 | After overnight updates |
| Fear & Greed | 6 hours | - | Updated daily by source |
| Macro Summary | 1 hour | - | Aggregates all data |

**Market Hours Detection**:
- Commodity markets: 00:00 - 21:00 UTC (most active)
- Currencies: 24/7
- FRED: Data released typically overnight

### 3. Macro Summary Generator

**Purpose**: Aggregate macro-economic conditions into actionable insights

**Outputs**:
```python
{
    "risk_environment": "low_risk" | "moderate_risk" | "high_risk",
    "inflation_trend": "rising" | "falling" | "stable",
    "growth_outlook": "expanding" | "contracting" | "stable",
    "market_sentiment": "extreme_fear" | "fear" | "neutral" | "greed" | "extreme_greed",
    "key_indicators": {
        "VIX": 15.2,
        "DXY": {"value": 103.5, "trend": "strengthening"},
        "Gold": {"value": 2050.0, "trend": "rising"},
        "Fear_Greed": 65
    }
}
```

**Risk Environment Classification**:
- **Low Risk**: VIX < 15
- **Moderate Risk**: VIX 15-25
- **High Risk**: VIX > 25

## Installation

1. **Install Dependencies** (already in requirements.txt):
```bash
cd market_data_service
pip install -r requirements.txt
```

Dependencies:
- `yfinance==0.2.28` - Yahoo Finance data
- `aiohttp==3.9.1` - Async HTTP client
- `pandas==2.1.4` - Data manipulation

2. **Configure Environment Variables**:

**Required**:
```bash
export COSMOS_ENDPOINT=<your-cosmos-endpoint>
export COSMOS_KEY=<your-cosmos-key>
export COSMOS_DATABASE_NAME=trading_bot
```

**Optional (but recommended)**:
```bash
# FRED API (free, highly recommended)
export FRED_API_KEY=<your-fred-api-key>

# Alpha Vantage (optional, for additional data)
export ALPHA_VANTAGE_API_KEY=<your-alpha-vantage-key>
```

3. **Get FRED API Key** (Free):
   - Go to https://fred.stlouisfed.org/
   - Create free account
   - Go to https://fredaccount.stlouisfed.org/apikeys
   - Request API key
   - Add to environment: `export FRED_API_KEY=your_key_here`

## Usage

### Start Automated Scheduler

```bash
cd market_data_service
./start_macro_scheduler.sh
```

The scheduler will:
- Initialize database connection
- Start periodic data collection
- Generate hourly macro summaries
- Log all activities

### Run One-Time Collection

```bash
cd market_data_service
python macro_economic_collector.py
```

### Test the System

```bash
cd market_data_service
python test_macro_collector.py
```

Sample output:
```
============================================================
Testing Macro-Economic Data Collector
============================================================

✓ Database and collector initialized

Testing Commodities Collection...
  ✓ Collected 6 commodity prices
    Example: Gold = $2050.45

Testing Currencies Collection...
  ✓ Collected 7 currency pairs
    Example: US Dollar Index (DXY) = 103.4567

Testing Treasury Yields Collection...
  ✓ Collected 4 treasury yields
    Example: 10 Year Treasury = 4.250%

Testing FRED Indicators Collection...
  ✓ Collected 11 FRED indicators
    Example: Consumer Price Index (CPI) = 314.875

Testing Fear & Greed Index Collection...
  ✓ Fear & Greed Index: 65 (Greed)

Generating Macro-Economic Summary...
  ✓ Risk Environment: moderate_risk
  ✓ Market Sentiment: greed
  ✓ Key Indicators:
    - VIX: 18.5
    - DXY: 103.45 (strengthening)
    - Gold: 2050.45 (rising)
    - Fear_Greed: 65
```

### Programmatic Usage

```python
from database import Database
from macro_economic_collector import MacroEconomicCollector

async def get_macro_data():
    database = Database()
    
    async with database, MacroEconomicCollector(database) as collector:
        # Collect all data
        results = await collector.collect_all_macro_data()
        
        print(f"Commodities: {len(results['commodities'])}")
        print(f"Currencies: {len(results['currencies'])}")
        print(f"Total indicators: {results['total_indicators']}")
        
        # Get macro summary
        summary = await collector.get_macro_summary()
        print(f"Risk Environment: {summary['risk_environment']}")
        print(f"Market Sentiment: {summary['market_sentiment']}")
        
        return summary

# Run
import asyncio
summary = asyncio.run(get_macro_data())
```

## Database Schema

### Commodity Data
```json
{
  "id": "commodity_GC_F_1234567890",
  "doc_type": "macro_economic_data",
  "category": "commodity",
  "symbol": "GC=F",
  "name": "Gold",
  "unit": "USD/oz",
  "current_value": 2050.45,
  "previous_value": 2045.30,
  "change": 5.15,
  "change_percent": 0.25,
  "day_high": 2055.00,
  "day_low": 2042.00,
  "volume": 150000,
  "timestamp": "2024-01-01T12:00:00Z",
  "source": "yahoo_finance"
}
```

### Currency Data
```json
{
  "id": "currency_DX_Y_NYB_1234567890",
  "doc_type": "macro_economic_data",
  "category": "currency",
  "symbol": "DX-Y.NYB",
  "name": "US Dollar Index (DXY)",
  "type": "index",
  "current_value": 103.45,
  "previous_value": 103.20,
  "change": 0.25,
  "change_percent": 0.24,
  "timestamp": "2024-01-01T12:00:00Z",
  "source": "yahoo_finance"
}
```

### Treasury Yield Data
```json
{
  "id": "treasury_TNX_1234567890",
  "doc_type": "macro_economic_data",
  "category": "treasury_yield",
  "symbol": "^TNX",
  "name": "10 Year Treasury",
  "maturity": "10Y",
  "current_yield": 4.250,
  "previous_yield": 4.225,
  "change_bps": 2.5,
  "importance": "high",
  "timestamp": "2024-01-01T12:00:00Z",
  "source": "yahoo_finance"
}
```

### FRED Indicator Data
```json
{
  "id": "fred_CPIAUCSL_1234567890",
  "doc_type": "macro_economic_data",
  "category": "inflation",
  "series_id": "CPIAUCSL",
  "name": "Consumer Price Index (CPI)",
  "current_value": 314.875,
  "previous_value": 314.120,
  "change": 0.755,
  "change_percent": 0.24,
  "observation_date": "2024-01-01",
  "importance": "high",
  "timestamp": "2024-01-01T12:00:00Z",
  "source": "fred"
}
```

### Fear & Greed Index
```json
{
  "id": "fear_greed_1234567890",
  "doc_type": "macro_economic_data",
  "category": "sentiment",
  "name": "Crypto Fear & Greed Index",
  "value": 65,
  "classification": "Greed",
  "importance": "high",
  "timestamp": "2024-01-01T12:00:00Z",
  "source": "alternative.me"
}
```

### Macro Summary
```json
{
  "id": "macro_summary_1234567890",
  "doc_type": "macro_summary",
  "timestamp": "2024-01-01T12:00:00Z",
  "risk_environment": "moderate_risk",
  "inflation_trend": "stable",
  "growth_outlook": "expanding",
  "market_sentiment": "greed",
  "key_indicators": {
    "VIX": 18.5,
    "DXY": {"value": 103.45, "change_percent": 0.24, "trend": "strengthening"},
    "Gold": {"value": 2050.45, "change_percent": 0.25, "trend": "rising"},
    "Fear_Greed": 65
  }
}
```

## Integration with Trading Strategies

### 1. Risk Environment-Based Position Sizing

```python
async def adjust_position_for_macro_risk(self, base_size: float) -> float:
    """Adjust position size based on macro risk environment"""
    
    # Get latest macro summary
    query = """
    SELECT * FROM c 
    WHERE c.doc_type = 'macro_summary' 
    ORDER BY c.timestamp DESC 
    OFFSET 0 LIMIT 1
    """
    
    results = list(self.container.query_items(
        query=query,
        enable_cross_partition_query=True
    ))
    
    if not results:
        return base_size
    
    summary = results[0]
    risk_env = summary.get('risk_environment')
    
    # Adjust position size
    if risk_env == 'high_risk':
        return base_size * 0.5  # Reduce by 50%
    elif risk_env == 'low_risk':
        return base_size * 1.2  # Increase by 20%
    else:
        return base_size  # Keep unchanged
```

### 2. Dollar Strength Correlation

```python
async def check_dollar_impact(self, crypto_symbol: str) -> Dict:
    """Check if dollar strength affects crypto"""
    
    # Get latest DXY data
    query = """
    SELECT * FROM c 
    WHERE c.doc_type = 'macro_economic_data' 
    AND c.category = 'currency'
    AND CONTAINS(c.symbol, 'DX-Y')
    ORDER BY c.timestamp DESC 
    OFFSET 0 LIMIT 1
    """
    
    results = list(self.container.query_items(
        query=query,
        enable_cross_partition_query=True
    ))
    
    if results:
        dxy_data = results[0]
        change_percent = dxy_data.get('change_percent', 0)
        
        # Strong dollar typically negative for crypto
        if change_percent > 0.5:  # Dollar strengthening
            return {
                "signal": "bearish",
                "reason": f"DXY strengthening by {change_percent:.2f}%",
                "confidence": 0.6
            }
        elif change_percent < -0.5:  # Dollar weakening
            return {
                "signal": "bullish",
                "reason": f"DXY weakening by {abs(change_percent):.2f}%",
                "confidence": 0.6
            }
    
    return {"signal": "neutral"}
```

### 3. Fear & Greed Strategy Adjustment

```python
async def get_sentiment_multiplier(self) -> float:
    """Get position size multiplier based on Fear & Greed"""
    
    query = """
    SELECT * FROM c 
    WHERE c.doc_type = 'macro_economic_data' 
    AND c.category = 'sentiment'
    ORDER BY c.timestamp DESC 
    OFFSET 0 LIMIT 1
    """
    
    results = list(self.container.query_items(
        query=query,
        enable_cross_partition_query=True
    ))
    
    if results:
        fg_value = results[0].get('value', 50)
        
        # Contrarian approach
        if fg_value < 20:  # Extreme fear - good buying opportunity
            return 1.3
        elif fg_value > 80:  # Extreme greed - be cautious
            return 0.7
        elif fg_value < 40:  # Fear
            return 1.1
        elif fg_value > 60:  # Greed
            return 0.9
    
    return 1.0  # Neutral
```

### 4. Commodity Correlation Signals

```python
async def get_commodity_signals(self) -> Dict:
    """Get trading signals from commodity prices"""
    
    query = """
    SELECT * FROM c 
    WHERE c.doc_type = 'macro_economic_data' 
    AND c.category = 'commodity'
    AND c.timestamp > @since
    """
    
    one_hour_ago = (datetime.utcnow() - timedelta(hours=1)).isoformat() + "Z"
    
    results = list(self.container.query_items(
        query=query,
        parameters=[{"name": "@since", "value": one_hour_ago}],
        enable_cross_partition_query=True
    ))
    
    signals = []
    
    for item in results:
        if item.get('name') == 'Gold':
            change = item.get('change_percent', 0)
            if abs(change) > 1:  # Significant gold move
                # Gold up = risk-off (bearish for risky assets)
                signals.append({
                    "asset": "Gold",
                    "signal": "bearish" if change > 0 else "bullish",
                    "reason": f"Gold {'+' if change > 0 else ''}{change:.2f}%",
                    "weight": 0.3
                })
        
        elif item.get('name') == 'Crude Oil WTI':
            change = item.get('change_percent', 0)
            if abs(change) > 2:  # Significant oil move
                # Oil up can be inflationary (mixed for crypto)
                signals.append({
                    "asset": "Oil",
                    "signal": "neutral" if change > 0 else "bearish",
                    "reason": f"Oil {'+' if change > 0 else ''}{change:.2f}%",
                    "weight": 0.2
                })
    
    return {"signals": signals}
```

### 5. Treasury Yield Impact

```python
async def check_treasury_yield_impact(self) -> Dict:
    """Check if treasury yields affect risk appetite"""
    
    query = """
    SELECT * FROM c 
    WHERE c.doc_type = 'macro_economic_data' 
    AND c.category = 'treasury_yield'
    AND c.maturity = '10Y'
    ORDER BY c.timestamp DESC 
    OFFSET 0 LIMIT 1
    """
    
    results = list(self.container.query_items(
        query=query,
        enable_cross_partition_query=True
    ))
    
    if results:
        yield_data = results[0]
        change_bps = yield_data.get('change_bps', 0)
        current_yield = yield_data.get('current_yield', 4.0)
        
        # Rising yields = money flows to bonds (bearish for risky assets)
        if change_bps > 10:  # Significant yield increase
            return {
                "signal": "bearish",
                "reason": f"10Y Treasury yield up {change_bps} bps to {current_yield:.2f}%",
                "confidence": 0.5
            }
        elif change_bps < -10:  # Significant yield decrease
            return {
                "signal": "bullish",
                "reason": f"10Y Treasury yield down {abs(change_bps)} bps to {current_yield:.2f}%",
                "confidence": 0.5
            }
    
    return {"signal": "neutral"}
```

## Performance Considerations

### Data Collection Efficiency
1. **Concurrent Collection**: All sources fetched in parallel
2. **Rate Limiting**: 0.5-1 second delays between requests
3. **Batch Storage**: 50 records per batch insert
4. **Adaptive Frequency**: More frequent during market hours

### Resource Usage
- **Memory**: ~100-200 MB
- **CPU**: Very low (mostly I/O bound)
- **Network**: Moderate (requests every 15-60 minutes)
- **Database**: ~50-100 documents per day

### API Limits
- **Yahoo Finance**: ~2000 requests/hour (unofficial)
- **FRED**: 120 requests/minute
- **Alternative.me**: No documented limits

## Monitoring & Debugging

### Check Scheduler Status

```python
from macro_economic_scheduler import MacroEconomicScheduler

scheduler = MacroEconomicScheduler()
await scheduler.initialize()

stats = scheduler.get_stats()
print(f"Running: {stats['running']}")
print(f"Commodity runs: {stats['stats']['commodity_runs']}")
print(f"Currency runs: {stats['stats']['currency_runs']}")
print(f"Errors: {stats['stats']['errors']}")
```

### View Recent Data

```python
# Query commodities
query = """
SELECT * FROM c 
WHERE c.doc_type = 'macro_economic_data' 
AND c.category = 'commodity'
ORDER BY c.timestamp DESC 
OFFSET 0 LIMIT 10
"""

results = container.query_items(query=query, enable_cross_partition_query=True)
for item in results:
    print(f"{item['name']}: ${item['current_value']:.2f} ({item['change_percent']:+.2f}%)")
```

### Logs

Structured logging with `structlog`:
```
2024-01-01 12:00:00 [info] Fetching commodity prices
2024-01-01 12:00:01 [info] Commodity data fetched symbol=GC=F name=Gold price=2050.45 change_percent=0.25
2024-01-01 12:00:05 [info] Commodity data collection completed records=6 total_runs=42
2024-01-01 13:00:00 [info] Macro summary generated risk_environment=moderate_risk market_sentiment=greed
```

## Troubleshooting

### Common Issues

**1. No FRED data collected**:
- Check if FRED_API_KEY is set
- Verify API key is valid
- Check FRED API status

**2. Yahoo Finance timeouts**:
- Increase timeout in aiohttp.ClientTimeout
- Reduce collection frequency
- Check internet connection

**3. Fear & Greed Index not updating**:
- alternative.me API may be down
- Check API endpoint: https://api.alternative.me/fng/
- Data only updates once daily

**4. High error count**:
- Check logs for specific errors
- Verify API keys
- Check network connectivity

## Future Enhancements

1. **Additional Data Sources**:
   - Bloomberg Terminal data (if available)
   - Quandl economic data
   - Trading Economics API
   - Central bank statements parsing

2. **Enhanced Analysis**:
   - Correlation with crypto prices
   - Predictive modeling
   - Anomaly detection
   - Trend analysis

3. **More Indicators**:
   - PMI (Manufacturing)
   - Retail sales
   - Housing data
   - Consumer confidence
   - Central bank balance sheets

4. **Real-time Alerts**:
   - Significant indicator changes
   - Fed announcements
   - Unusual market conditions

## References

- **FRED API**: https://fred.stlouisfed.org/docs/api/
- **Yahoo Finance**: https://pypi.org/project/yfinance/
- **Fear & Greed Index**: https://alternative.me/crypto/fear-and-greed-index/
- **Economic Calendar**: https://www.investing.com/economic-calendar/

---

**Status**: ✅ Complete and Production-Ready

**Last Updated**: 2024-01-01

**Version**: 1.0.0
