# Bitcoin Correlation Strategies - Quick Start

**Status:** ✅ Generated and Ready  
**Date:** November 9, 2025

## What Was Created

✅ **8 Bitcoin Correlation Trading Strategies**
- All strategies focus on BTC price correlation patterns
- Range from high positive correlation to negative correlation
- Includes momentum, breakout, mean reversion, and hedge strategies
- Position sizes: 1.5% - 4.0% per trade
- Risk/reward ratios: 1.5:1 to 2:1

## Files

```
strategy_service/
  ├── btc_correlation_strategies.json     (7.2KB) - Strategy definitions
  └── generate_btc_strategies_api.py      (12KB)  - Generator script

BTC_CORRELATION_STRATEGIES.md             (8.4KB) - Full documentation
```

## Strategy List

| # | Strategy Name | Type | Symbols | Position | Stop/Take |
|---|---------------|------|---------|----------|-----------|
| 1 | BTC Momentum Follower | High Correlation | 9 | 2.0% | 3%/6% |
| 2 | BTC Inverse Trader | Negative Correlation | 5 | 1.5% | 4%/8% |
| 3 | BTC Correlation Divergence | Mean Reversion | 8 | 2.5% | 3.5%/7% |
| 4 | BTC Beta Amplifier | High Beta | 6 | 3.0% | 5%/10% |
| 5 | BTC Stable Correlator | Stable | 7 | 2.0% | 2.5%/5% |
| 6 | BTC Breakout Correlator | Breakout | 5 | 3.5% | 4%/8% |
| 7 | BTC Low Correlation Hedge | Hedge | 5 | 4.0% | 6%/12% |
| 8 | BTC Correlation Mean Reversion | Statistical | 6 | 2.0% | 4%/6% |

## Quick Commands

### View Strategies
```bash
cd /home/neodyme/Documents/Projects/masterTrade/strategy_service
cat btc_correlation_strategies.json | jq '.strategies[] | {name, type, symbols}'
```

### Review Documentation
```bash
cd /home/neodyme/Documents/Projects/masterTrade
cat BTC_CORRELATION_STRATEGIES.md | less
```

### Check System Status
```bash
./status.sh
curl http://localhost:8001/health
```

## Next Actions

1. **Review** - Read `BTC_CORRELATION_STRATEGIES.md` for details
2. **Import** - Load strategies into Strategy Service database
3. **Test** - Start with conservative strategies (BTC Stable Correlator)
4. **Monitor** - Track performance via dashboard (port 3000)
5. **Activate** - Enable best performers gradually

## Key Requirements

- ✅ Market Data Service collecting BTC + altcoin prices
- ✅ Sufficient historical data for correlation calculations
- ✅ Strategy Service operational
- ⚠️ Strategies start INACTIVE by default (safety first!)

## Strategy Highlights

**Most Conservative:**
- BTC Stable Correlator (2% position, 2.5% stop loss)

**Most Aggressive:**
- BTC Beta Amplifier (3% position, 5% stop loss, 10% target)

**Best for Hedging:**
- BTC Inverse Trader (negative correlation)
- BTC Low Correlation Hedge (portfolio diversification)

**Best for Trending Markets:**
- BTC Momentum Follower
- BTC Breakout Correlator

**Best for Range Markets:**
- BTC Correlation Divergence
- BTC Correlation Mean Reversion

## Support

- **Logs:** `/tmp/strategy_service.log`
- **API:** http://localhost:8001/docs
- **Dashboard:** http://localhost:3000
- **Documentation:** `BTC_CORRELATION_STRATEGIES.md`

---

🚀 **Ready to start Bitcoin correlation trading!**
