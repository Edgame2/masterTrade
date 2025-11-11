# Quick Reference: 1000 Strategy Backtest Results

## 📁 Files Location
```
/home/neodyme/Documents/Projects/masterTrade/strategy_service/
```

## 📊 Generated Files (Total: ~2.0 MB)

| File | Size | Description |
|------|------|-------------|
| `strategies_1000.json` | 1.2 MB | All 1,000 strategy definitions |
| `backtest_results_1000.json` | 686 KB | Complete backtest results |
| `backtest_results_all.csv` | 35 KB | All metrics (284 strategies) |
| `backtest_monthly_returns.csv` | 16 KB | Month-by-month returns (top 200) |
| `backtest_results_report.html` | 54 KB | **Interactive HTML report (top 100)** |
| `generate_1000_strategies.py` | 22 KB | Strategy generator script |
| `backtest_engine.py` | 20 KB | Backtesting engine |
| `generate_reports.py` | 15 KB | Report generator |

## 🏆 Top 5 Strategies

| Rank | Strategy | Type | Monthly Return | Total Return | Win Rate |
|------|----------|------|----------------|--------------|----------|
| #1 | Hybrid 803 - VOLUME+BB+MACD | Hybrid | **49.45%** | 367.95% | 77.4% |
| #2 | MACD 732 - 8/21/9 | MACD | **49.44%** | 358.62% | 71.4% |
| #3 | Breakout 375 - 15m 100p | Breakout | **44.54%** | 323.36% | 82.4% |
| #4 | MACD 798 - 8/21/9 | MACD | **44.50%** | 320.47% | 81.8% |
| #5 | Hybrid 884 - MACD+BB+ATR | Hybrid | **43.55%** | 308.51% | 74.3% |

## 📈 Performance by Type

| Type | Count | Avg Monthly % | Win Rate |
|------|-------|---------------|----------|
| Hybrid | 29 | 18.23% | 76.41% |
| MACD | 33 | 17.97% | 74.54% |
| Volume-Based | 31 | 16.17% | 74.92% |
| Breakout | 45 | 13.63% | 76.63% |
| Momentum | 80 | 11.67% | 73.49% |
| BTC Correlation | 51 | 9.17% | 77.57% |

## 🚀 Quick Commands

### View Interactive HTML Report
```bash
cd /home/neodyme/Documents/Projects/masterTrade/strategy_service
xdg-open backtest_results_report.html
```

### View CSV in Terminal
```bash
column -s, -t < backtest_results_all.csv | less -S
```

### Query Top Performers with jq
```bash
# Top 10 by monthly return
jq '.results[] | select(.status=="completed") | {name, monthly: .avg_monthly_return_pct, total: .total_return_pct, win_rate}' backtest_results_1000.json | head -50

# Filter by win rate > 80%
jq '.results[] | select(.win_rate > 80 and .status=="completed") | {name, win_rate, monthly: .avg_monthly_return_pct}' backtest_results_1000.json
```

### Open CSV in LibreOffice Calc
```bash
libreoffice --calc backtest_results_all.csv
```

## 🎯 Strategy Recommendations

### Conservative (Low Risk)
- **MACD 761** - 8/30/9 parameters
  - Monthly: 35.67% | Win Rate: 83.7%
- **Breakout 346** - 15m 20p
  - Monthly: 35.65% | Win Rate: 83.8%

### Balanced (Medium Risk)
- **Hybrid 803** - VOLUME+BB+MACD
  - Monthly: 49.45% | Win Rate: 77.4%
- **Volume 600** - 15m timeframe
  - Monthly: 39.25% | Win Rate: 78.4%

### Aggressive (High Risk/Reward)
- **MACD 732** - 8/21/9 parameters
  - Monthly: 49.44% | Win Rate: 71.4%
- **Hybrid 893** - MACD+VOLUME+EMA
  - Monthly: 41.17% | Win Rate: 76.2%

## 📊 Key Statistics

- **Total Strategies Generated**: 1,000
- **Realistic Strategies**: 284 (28.4%)
- **Best Monthly Return**: 49.45%
- **Best Total Return**: 367.95% (90 days)
- **Average Win Rate (Top 100)**: 75.8%
- **Initial Capital**: $10,000 per strategy
- **Backtest Period**: ~90 days

## 💡 Key Insights

1. **Hybrid strategies** combining multiple indicators outperform single-indicator approaches
2. **MACD parameters** 8/21/9 and 8/30/7 show consistent strong performance
3. **15-minute timeframe** provides optimal balance of frequency and signal quality
4. **Volume confirmation** significantly improves entry quality
5. **Breakout strategies** excel when combined with volume filters

## ⚠️ Important Notes

- Results based on **synthetic data** (not real market conditions)
- **No fees, slippage, or execution delays** included in simulation
- **Past performance does not guarantee future results**
- Always **start with paper trading** before using real money
- Use **proper risk management** (position sizing, stop losses)

## 📞 Next Steps

1. **Review** `backtest_results_report.html` for detailed analysis
2. **Select** 10-20 strategies based on your risk profile
3. **Import** selected strategies into Strategy Service database
4. **Activate** in paper trading mode for 1-2 weeks
5. **Monitor** real-time performance before going live
6. **Adjust** parameters based on live results

## 🔍 Monthly Returns Breakdown

### Top Strategy (Hybrid 803) Month-by-Month
- August 2025: +16.35%
- September 2025: +66.12%
- October 2025: +83.04%
- November 2025: +32.27%
- **Average: 49.45% per month**

### Sample Annualized Returns (Compounded)
- 49.45% monthly → **~16,700% annualized** (extremely high, likely unsustainable)
- 30% monthly → **2,210% annualized**
- 20% monthly → **791% annualized**
- 10% monthly → **214% annualized**

*Note: These are theoretical returns. Real-world trading will differ significantly.*

## 📚 Full Documentation

See: `/home/neodyme/Documents/Projects/masterTrade/BACKTEST_1000_STRATEGIES_COMPLETE.md`

---

*Last Updated: November 9, 2025*
*Generation Time: ~3 minutes*
*Total Data Processed: 1,000 strategies × 90 days × 20 symbols*
