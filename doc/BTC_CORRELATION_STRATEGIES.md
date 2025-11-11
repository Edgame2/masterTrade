# Bitcoin Correlation Trading Strategies

**Generated:** November 9, 2025  
**Total Strategies:** 8  
**Status:** Ready for Import  
**File:** `strategy_service/btc_correlation_strategies.json`

## Overview

This document describes 8 automated trading strategies that focus on Bitcoin price correlation for altcoin trading. Each strategy uses different correlation patterns and market conditions to generate trading signals.

## Strategy Summary

### 1. **BTC Momentum Follower** 🚀
- **Type:** High Positive Correlation (0.7+)
- **Approach:** Trades altcoins that move strongly with BTC during momentum phases
- **Entry:** Strong BTC uptrend (>2% in 4h)
- **Position Size:** 2% per trade
- **Risk/Reward:** 3% stop loss / 6% take profit (1:2 ratio)
- **Max Positions:** 3 concurrent
- **Symbols:** ETH, BNB, ADA, SOL, DOT, AVAX, MATIC, LINK, ATOM
- **Best For:** Trending markets with clear BTC direction

### 2. **BTC Inverse Trader** 🔄
- **Type:** Negative Correlation (-0.5)
- **Approach:** Counter-trend trading and portfolio hedging
- **Entry:** BTC downtrend with negative correlation confirmation
- **Position Size:** 1.5% per trade
- **Risk/Reward:** 4% stop loss / 8% take profit (1:2 ratio)
- **Max Positions:** 2 concurrent
- **Symbols:** ETH, BNB, XRP, ADA, DOGE
- **Best For:** Market diversification and BTC hedge

### 3. **BTC Correlation Divergence** 📊
- **Type:** Mean Reversion (0.6+ baseline)
- **Approach:** Trades when short-term correlation diverges from long-term baseline
- **Entry:** 30% deviation from 30-day correlation baseline
- **Position Size:** 2.5% per trade
- **Risk/Reward:** 3.5% stop loss / 7% take profit (1:2 ratio)
- **Max Positions:** 4 concurrent
- **Symbols:** ETH, BNB, SOL, AVAX, LINK, UNI, AAVE, DOT
- **Best For:** Range-bound markets with temporary dislocations

### 4. **BTC Beta Amplifier** 💪
- **Type:** High Beta (1.5x+ BTC volatility)
- **Approach:** Amplifies BTC movements with high-volatility altcoins
- **Entry:** Strong BTC trend + high correlation (0.8+)
- **Position Size:** 3% per trade
- **Risk/Reward:** 5% stop loss / 10% take profit (1:2 ratio)
- **Max Positions:** 2 concurrent
- **Symbols:** SOL, AVAX, LINK, AAVE, UNI, SUSHI
- **Best For:** Strong trending markets, higher risk/reward
- **Special:** 3% trailing stop to lock in profits

### 5. **BTC Stable Correlator** 🎯
- **Type:** Stable Correlation (0.65+, low variance)
- **Approach:** Trades assets with consistent BTC correlation across timeframes
- **Entry:** Stable correlation across 1d, 7d, 30d periods
- **Position Size:** 2% per trade
- **Risk/Reward:** 2.5% stop loss / 5% take profit (1:2 ratio)
- **Max Positions:** 5 concurrent
- **Symbols:** ETH, BNB, ADA, DOT, MATIC, ATOM, LTC
- **Best For:** Lower-risk steady trading, portfolio core

### 6. **BTC Breakout Correlator** 🎆
- **Type:** Breakout Trading (0.75+ correlation)
- **Approach:** Trades correlated altcoins during BTC breakouts
- **Entry:** BTC breaks resistance with 1.5x volume surge
- **Position Size:** 3.5% per trade
- **Risk/Reward:** 4% stop loss / 8% take profit (1:2 ratio)
- **Max Positions:** 3 concurrent
- **Symbols:** ETH, SOL, AVAX, LINK, UNI
- **Best For:** Breakout events, momentum trading
- **Special:** Requires 2 candles confirmation

### 7. **BTC Low Correlation Hedge** 🛡️
- **Type:** Portfolio Diversification (0.3-0.5 correlation)
- **Approach:** Maintains positions in low-correlation assets
- **Entry:** Low correlation maintained, rebalanced daily
- **Position Size:** 4% per trade (20% total allocation target)
- **Risk/Reward:** 6% stop loss / 12% take profit (1:2 ratio)
- **Max Positions:** 5 concurrent
- **Symbols:** ETH, XRP, ADA, LTC, DOGE
- **Best For:** Portfolio hedging and diversification

### 8. **BTC Correlation Mean Reversion** 🔁
- **Type:** Statistical Mean Reversion
- **Approach:** Trades when short-term correlation deviates 40%+ from 90-day baseline
- **Entry:** Significant deviation from long-term correlation mean
- **Position Size:** 2% per trade
- **Risk/Reward:** 4% stop loss / 6% take profit (1:1.5 ratio)
- **Max Positions:** 4 concurrent
- **Symbols:** ETH, BNB, SOL, AVAX, DOT, LINK
- **Best For:** Statistical arbitrage, mean reversion trading

## Key Features

### Correlation Analysis
- **Real-time correlation tracking** with BTC across multiple timeframes
- **Multiple correlation periods:** 3d, 7d, 14d, 30d, 90d
- **Update intervals:** 30min to 12h depending on strategy
- **Deviation detection** for divergence trading

### Risk Management
- **Position sizing:** 1.5% to 4% per trade
- **Stop losses:** 2.5% to 6% depending on strategy volatility
- **Take profits:** 5% to 12% with 1.5:1 to 2:1 risk/reward ratios
- **Max concurrent positions:** 2 to 5 per strategy
- **Trailing stops:** Available on high-volatility strategies

### Market Conditions
- **Volume filters:** Minimum $500K to $3M daily volume
- **Trend strength:** Filters for strong vs weak trends
- **Volatility analysis:** Beta calculations for amplification strategies
- **Momentum indicators:** 4h to 1d momentum periods

## Implementation Status

✅ **Generated:** All 8 strategies defined  
⏸️ **Status:** Inactive (ready for testing)  
📄 **Storage:** JSON format in `btc_correlation_strategies.json`  
🔌 **Import:** Ready for Strategy Service database import

## Next Steps

### 1. Review & Validate
```bash
cd strategy_service
cat btc_correlation_strategies.json | jq '.strategies[] | {name, type, symbols}'
```

### 2. Import to Database
- Import strategies via Strategy Service API
- Or use database script to load from JSON
- Verify in Cosmos DB `strategies` container

### 3. Backtest
- Test each strategy against historical data
- Validate correlation calculations
- Measure performance metrics

### 4. Activate Best Performers
```bash
# Via API
curl -X POST http://localhost:8001/api/v1/strategy/{strategy_id}/resume
```

### 5. Monitor Performance
- Track via Strategy Service API
- View in monitoring dashboard (port 3000)
- Review daily performance reports

## Strategy Selection Guide

**For Trending Markets:**
- ✅ BTC Momentum Follower
- ✅ BTC Beta Amplifier
- ✅ BTC Breakout Correlator

**For Range-Bound Markets:**
- ✅ BTC Correlation Divergence
- ✅ BTC Correlation Mean Reversion
- ✅ BTC Stable Correlator

**For Risk Management:**
- ✅ BTC Inverse Trader (hedge)
- ✅ BTC Low Correlation Hedge (diversification)

**For Conservative Trading:**
- ✅ BTC Stable Correlator (lower risk)
- ✅ BTC Momentum Follower (clear signals)

**For Aggressive Trading:**
- ✅ BTC Beta Amplifier (high volatility)
- ✅ BTC Breakout Correlator (momentum plays)

## Technical Requirements

### Data Requirements
- Bitcoin price data (BTCUSDC) - real-time
- Altcoin price data - 1m, 5m, 1h, 4h, 1d intervals
- Volume data - 24h rolling
- Correlation calculations - rolling windows
- Market Data Service must be operational

### Calculation Requirements
- Pearson correlation coefficient
- Rolling correlation windows
- Beta calculations (volatility ratio)
- Moving averages and momentum indicators
- Volume surge detection

### System Integration
- ✅ Market Data Service (port 8000) - collecting BTC + altcoin data
- ✅ Strategy Service (port 8001) - strategy execution
- ✅ Order Executor (port 8081) - trade execution
- ✅ Risk Manager - position sizing and limits
- ✅ Cosmos DB - data storage

## Performance Expectations

Based on correlation trading best practices:

- **Win Rate:** 50-60% (with 2:1 R/R ratio)
- **Average Profit per Trade:** 4-8%
- **Average Loss per Trade:** 2-4%
- **Expected Monthly Return:** 5-15% (varies by strategy)
- **Maximum Drawdown:** <20% with proper risk management

## Important Notes

⚠️ **All strategies start INACTIVE** for safety  
📊 **Requires sufficient historical data** for correlation calculations  
🔄 **Correlation updates automatically** at specified intervals  
💰 **Position sizing adapts** to portfolio size  
🛡️ **Stop losses are mandatory** for all positions  
📈 **Performance tracking** via Strategy Service  

## Files Generated

1. **btc_correlation_strategies.json** - Strategy definitions
2. **generate_btc_strategies_api.py** - Generator script
3. **BTC_CORRELATION_STRATEGIES.md** - This documentation (create separately)

## Support

For questions or issues:
- Check Strategy Service logs: `/tmp/strategy_service.log`
- Review API documentation: http://localhost:8001/docs
- Monitor dashboard: http://localhost:3000

---

**Ready to revolutionize your Bitcoin correlation trading! 🚀**
