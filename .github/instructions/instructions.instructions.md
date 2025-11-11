---
applyTo: '**'
---

# IMPORTANT: 
Do not simplify the projects. Do not remove features or code. Only improve the code as requested.
Keep the code structure clean, organized, and modular.
If you create documentation make sure it is in the ./doc folder.
The system must work perfectly, do not leave anything broken.
The database is Local postgres database. The services are microservices in python using FastAPI. The message broker is RabbitMQ. The system is containerized using Docker. The deployment platform is local. The code uses asyncio for concurrency. 
No need to show me all the details just the most relevant parts.
You can skip: Summarizing conversation history unless specifically asked for it.
Strategy generation must be fully automated as per requirements below. Must have full pipeline for generation, backtesting, learning, filtering, paper trading, activation, monitoring, and replacement of strategies. Must use genetic algorithms, reinforcement learning, statistical analysis, and LSTM-Transformer price predictions as described.


## System Requirements

### Full Automation Requirements
The MasterTrade system must be fully operational with the following capabilities:

1. **Automatic Strategy Discovery and Generation** ✅ IMPLEMENTED
   - System **automatically generates 500 new trading strategies daily** at 3:00 AM UTC
   - System **automatically backtests all new strategies** before activation (within 3-hour window)
   - System automatically finds and evaluates the best trading strategies from the backtest pool
   - System continuously generates new strategies using **genetic algorithm + RL + statistical analysis**
   - Strategies use **1-hour ahead BTCUSDC price predictions** from LSTM-Transformer model
   - Strategy performance continuously monitored and ranked in real-time
   - Underperforming strategies automatically disabled/deactivated
   - New strategies tested in **paper trading mode first** before live trading
   - Strategies automatically find best cryptocurrency pairs to trade daily
   - ** Backtest results stored with detailed metrics** for analysis and learning in the database.
   - **Fully Automated Pipeline:** Generate (500/day) → Backtest (3h) → Learn → Filter Best → Paper Trade → Activate Live
   - **Learning System:** Genetic algorithm combines best strategy features, RL rewards successful patterns, statistical analysis identifies success factors
   - **Self-Improving:** Each generation learns from previous backtest results to create better strategies

2. **Automatic Cryptocurrency Selection**
   - System must automatically identify the best cryptocurrencies to trade
   - Selection criteria: volume, volatility, liquidity, trend strength
   - Daily/periodic re-evaluation of crypto pairs
   - Automatic historical data collection for selected cryptos

3. **Automatic Order Execution**
   - System must place complex orders automatically based on identified strategies
   - Support for: limit orders, stop-loss, take-profit, trailing stops
   - Risk management rules must be enforced automatically
   - Position sizing based on account balance and risk parameters

4. **Automatic Data Collection**
   - Market Data Service must collect all necessary data automatically:
     * Real-time price data (1m, 5m, 15m, 1h, 4h, 1d intervals)
     * Order book depth data
     * Trading volume and liquidity metrics
     * Technical indicators (SMA, EMA, RSI, MACD, Bollinger Bands, etc.)
     * Sentiment data (Fear & Greed Index, social media sentiment)
     * Stock market indices (S&P 500, NASDAQ, VIX, etc.)
   - Historical data must be automatically downloaded for new symbols
   - Data retention: 90 days for high-frequency, 1 year for daily data

6. **Monitoring UI Requirements**
   - Full visibility into all system operations via REST APIs
   - Real-time dashboards showing:
     * Active strategies and their performance
     * Current positions and P&L
     * Selected cryptocurrencies and their metrics
     * Market data collection status
     * System health and errors
     * **Strategy generation status and backtest results**
     * **Automated pipeline status (generation → backtest → activation)**
   - Historical performance charts
   - Ability to manually override automatic decisions
   - Alert system for critical events

7. **Automated Strategy Generation & Backtesting** ✅ IMPLEMENTED
   - System **automatically generates 500 new strategies daily** at 3:00 AM UTC
   - Each generated strategy **automatically backtested** with historical data (90 days)
   - Backtest results stored with comprehensive metrics (Sharpe, CAGR, Drawdown, Win Rate, Profit Factor, Monthly Returns)
   - Best performing strategies from backtests automatically enter **paper trading mode**
   - Paper trading results monitored for 1-2 weeks before live activation
   - System maintains pool of strategies at various stages:
     * Daily generation: 500 new strategies
     * Backtested: All 500 within 3-hour window
     * Filtered: ~28-35% pass realistic criteria
     * Paper trading: Top performers (validation phase)
     * Live active: 2-10 best strategies (configurable via MAX_ACTIVE_STRATEGIES)
     * Paused/retired: Poor performers automatically archived
   - **Fully Automated Process:** Generate (3AM UTC) → Backtest (3h) → Learn → Filter → Paper Trade → Activate → Monitor → Optimize/Replace
   - **Learning Components:**
     * Genetic Algorithm: Crossover and mutation of successful strategy genes
     * Reinforcement Learning: Pattern recognition and reward successful behaviors
     * Statistical Analysis: Correlation analysis to identify success factors
   - **Price Prediction:** 1-hour ahead BTCUSDC predictions using LSTM-Transformer model
   - **Self-Improvement:** System learns from every backtest to generate better strategies
   - **No Manual Intervention Required:** Entire pipeline runs automatically 24/7

6. **Backtesting Framework**
   - Ability to backtest strategies on historical data
   - Support for walk-forward analysis
   - Performance metrics: CAGR, Sharpe Ratio, Max Drawdown, Win Rate
   - Visualization of backtest results
   - Strategy service must integrate with backtesting framework

7. **Logging & Monitoring**
   - Centralized logging for all microservices
   - Real-time monitoring of system health
   - Alerting for failures and performance degradation
   - All logs must be structured and searchable in the database. (Logs for strategy generation, backtesting, order execution, data collection, etc.)

### Data Storage
- All data stored in local PostgreSQL database (running on host machine, not in container)
- Docker containers connect to host PostgreSQL via `host.docker.internal`
- Proper indexing for query performance
- Data retention policies (TTL via scheduled cleanup jobs)
- Backup and disaster recovery procedures
- Connection pooling for optimal performance

### Security
- API keys and secrets stored in environment variables
- Secure password management for database and message broker
- Rate limiting and error handling
- Secure RabbitMQ connections
- Database credentials never committed to version control