# Enhanced Dynamic Strategy Activation System - Task #11

## Overview

The Enhanced Dynamic Strategy Activation System is an intelligent, regime-aware strategy management system that automatically activates and deactivates trading strategies based on current market conditions and historical performance in similar environments.

## Key Features

### 1. Market Regime Detection
- **7 Market Regimes**: BULL_TRENDING, BEAR_TRENDING, SIDEWAYS_RANGE, HIGH_VOLATILITY, LOW_VOLATILITY, CRISIS, RECOVERY
- **Real-time Classification**: Continuous market condition monitoring
- **Multi-Factor Analysis**: Combines volatility, trend strength, sentiment, volume, and macro indicators
- **Confidence Scoring**: Each regime detection includes confidence level

### 2. Historical Condition Matching
- **Similarity Search**: Uses Euclidean distance in normalized feature space
- **Machine Learning**: StandardScaler for feature normalization
- **Top-K Matching**: Finds 10 most similar historical periods
- **Feature Vector**: 8-dimensional market state representation:
  - Volatility (annualized)
  - Trend strength (-1 to 1)
  - Volume trend
  - Sentiment score (-1 to 1)
  - Fear & Greed Index (0-100)
  - BTC correlation
  - Liquidity score (0-1)
  - Macro-economic score (-1 to 1)

### 3. Strategy Performance Evaluation
Evaluates strategies based on historical performance in similar conditions:
- **Sharpe Ratio**: Risk-adjusted returns
- **Total Return**: Cumulative profitability
- **Win Rate**: Percentage of winning trades
- **Maximum Drawdown**: Worst peak-to-trough decline
- **Profit Factor**: Gross profit / gross loss
- **Consistency Score**: Distribution quality of returns
- **Condition Similarity**: How closely past matches current conditions
- **Trade Count**: Statistical significance check

### 4. Regime Suitability Matrix
Strategy types matched to optimal market regimes:

| Strategy Type | Best Regimes | Worst Regimes |
|--------------|--------------|---------------|
| **Momentum** | Bull Trending (0.9), Recovery (0.8) | Crisis (0.2), Sideways (0.3) |
| **Mean Reversion** | Sideways (0.9), Low Vol (0.8) | Bull/Bear Trending (0.4) |
| **Breakout** | High Vol (0.8), Recovery (0.9) | Low Vol (0.4) |
| **Trend Following** | Bull (0.9), Bear (0.8) | Sideways (0.2) |
| **Scalping** | High Vol (0.8), Sideways (0.7) | Low Vol (0.5) |
| **Swing** | Bull (0.8), Low Vol (0.7) | Crisis (0.4) |
| **Arbitrage** | High Vol (0.9), Crisis (0.8) | Low Vol (0.5) |
| **Hybrid** | All regimes (0.7) | Balanced performance |

### 5. Automatic Activation Logic

**Activation Criteria:**
- Expected Sharpe Ratio > 1.5
- Risk Score < 0.6
- Condition Similarity > 0.7
- Minimum 20 historical trades
- Regime suitability > 0.5
- Within max_active_strategies limit

**Deactivation Triggers:**
- Poor expected performance (Sharpe < 1.0)
- High risk score (> 0.7)
- Low condition similarity (< 0.7)
- Insufficient historical data
- Regime mismatch (suitability < 0.5)

**Cooldown Period:**
- Minimum 2 hours between activation checks
- Prevents excessive strategy switching
- Can be bypassed with force_check parameter

### 6. Regime Change Detection
When market regime changes:
1. **Immediate Detection**: Real-time regime monitoring
2. **Confidence Validation**: Requires confidence > threshold
3. **Trigger Identification**: Records what caused the change
4. **Affected Strategies**: Tracks impact on active strategies
5. **Automatic Re-evaluation**: Forces immediate activation check
6. **Historical Recording**: Logs regime change events

## Integration Points

### Data Sources
1. **Market Data Service** (`market_data_service`)
   - Real-time price data
   - Volatility calculations
   - Volume trends
   - Liquidity metrics
   - BTC correlation

2. **Sentiment Analysis** (Task #7)
   - Reddit sentiment
   - Twitter sentiment
   - News sentiment
   - Fear & Greed Index
   - Aggregated scores

3. **Macro Indicators** (Task #5)
   - 28 economic indicators
   - Market health scores
   - Central bank data
   - Inflation metrics

4. **Risk Manager** (Task #8)
   - Current risk regime
   - Portfolio limits
   - Circuit breaker status
   - Drawdown levels

5. **Stock Indices** (Task #6)
   - Correlation analysis
   - Market alignment
   - Index trends

### Database Storage
```
Cosmos DB Containers:
- strategies: Strategy configurations and status
- market_conditions: Historical condition snapshots
- regime_detections: Regime classification history
- regime_changes: Regime change events
- activation_decisions: Audit trail of activations/deactivations
- strategy_performance_by_regime: Performance tracking per regime
```

## API Endpoints

### 1. GET `/api/strategy-activation/status`
**Current System Status**
```json
{
  "current_regime": "bull_trending",
  "regime_confidence": 0.85,
  "active_strategies": ["strategy_1", "strategy_2"],
  "active_count": 2,
  "max_active": 3,
  "last_regime_check": "2024-01-15T10:30:00Z",
  "last_activation_check": "2024-01-15T10:00:00Z",
  "market_conditions": {
    "volatility": 0.35,
    "trend_strength": 0.6,
    "sentiment_score": 0.4,
    "fear_greed_index": 65
  }
}
```

### 2. GET `/api/strategy-activation/regime`
**Current Market Regime**
```json
{
  "regime": "bull_trending",
  "confidence": "0.85",
  "timestamp": "2024-01-15T10:30:00Z"
}
```

### 3. POST `/api/strategy-activation/check`
**Trigger Activation Check**

Request:
```json
{
  "strategy_ids": null,  // null = all strategies
  "force_check": false
}
```

Response:
```json
{
  "timestamp": "2024-01-15T10:30:00Z",
  "regime": "bull_trending",
  "activated": [
    {
      "strategy_id": "strategy_3",
      "strategy_name": "Momentum Pro",
      "action": "activate",
      "confidence": 0.92,
      "reasoning": [
        "Strong historical performance (Sharpe: 2.1)",
        "Suitable for bull_trending regime"
      ],
      "expected_sharpe": 2.1,
      "expected_return": 0.15,
      "risk_score": 0.45,
      "performance": {
        "condition_similarity": 0.85,
        "historical_sharpe": 2.2,
        "historical_win_rate": 0.68,
        "trade_count": 45
      }
    }
  ],
  "deactivated": [
    {
      "strategy_id": "strategy_1",
      "strategy_name": "Mean Reversion Basic",
      "action": "deactivate",
      "reasoning": [
        "Strategy type not suitable for bull_trending",
        "Expected Sharpe below threshold (0.8)"
      ]
    }
  ],
  "total_active": 2
}
```

### 4. GET `/api/strategy-activation/candidates`
**Evaluate All Strategies** (without changing status)

Returns evaluation scores for all strategies in current conditions.

### 5. GET `/api/strategy-activation/performance/{strategy_id}`
**Strategy Performance in Current Conditions**

```json
{
  "strategy_id": "strategy_123",
  "condition_similarity": 0.82,
  "historical_sharpe": 1.8,
  "historical_return": 0.12,
  "historical_win_rate": 0.65,
  "historical_max_drawdown": 0.08,
  "trade_count": 38,
  "profit_factor": 2.1,
  "consistency_score": 0.75
}
```

### 6. GET `/api/strategy-activation/regime-suitability`
**Strategy Type Suitability Matrix**

Returns suitability scores for all strategy types across all regimes.

### 7. GET `/api/strategy-activation/market-conditions`
**Detailed Market Snapshot**

Current market conditions including all 8 feature dimensions.

### 8. POST `/api/strategy-activation/activate/{strategy_id}`
**Manual Activation** (bypasses automatic evaluation)

### 9. POST `/api/strategy-activation/deactivate/{strategy_id}`
**Manual Deactivation**

### 10. GET `/api/strategy-activation/health`
**Health Check**

```json
{
  "status": "healthy",
  "regime": "bull_trending",
  "active_strategies": 2,
  "timestamp": "2024-01-15T10:30:00Z"
}
```

## Configuration

### Settings (config.py)
```python
MAX_ACTIVE_STRATEGIES = 3
MIN_CONDITION_SIMILARITY = 0.7
MIN_HISTORICAL_TRADES = 20
REGIME_CHANGE_THRESHOLD = 0.15
ACTIVATION_COOLDOWN_HOURS = 2
```

### Strategy Metadata Required
Each strategy must have:
- `strategy_type`: One of StrategyType enum values
- `status`: 'active' or 'inactive'
- Historical trade data with:
  - timestamp
  - pnl_percent
  - duration_hours

## Machine Learning Components

### 1. Feature Scaling
- **StandardScaler**: Normalizes all 8 features to zero mean, unit variance
- **Fit on Historical**: Trained on all historical conditions
- **Transform Current**: Applied to current conditions for similarity matching

### 2. Similarity Matching
- **Distance Metric**: Euclidean distance in normalized feature space
- **Top-K Selection**: Returns 10 most similar periods
- **Similarity Score**: Converted from distance (1 - normalized_distance)

### 3. Consistency Scoring
- **Distribution Analysis**: Quality of return distribution
- **Positive Ratio**: Percentage of positive returns
- **Volatility Penalty**: Higher volatility reduces consistency
- **Combined Score**: positive_ratio * (1 - min(1, volatility / 0.1))

## Performance Metrics

### System Metrics
- Regime detection accuracy
- Activation decision quality
- Strategy performance improvement
- False activation rate
- Average active strategy count

### Strategy Metrics
- Performance in detected regime vs actual
- Activation timing quality
- Deactivation timing quality
- Risk-adjusted returns improvement
- Drawdown reduction

## Workflow Example

```python
# 1. System continuously monitors market
await activation_system.detect_market_regime()
# Detected: BULL_TRENDING with 0.85 confidence

# 2. Collect current conditions
conditions = await activation_system._collect_current_conditions()
# volatility=0.35, trend_strength=0.6, sentiment=0.4

# 3. Find similar historical periods
similar = activation_system._find_similar_conditions(conditions, top_k=10)
# Found 10 periods with avg similarity 0.82

# 4. Evaluate each strategy
for strategy in all_strategies:
    performance = await activation_system._evaluate_strategy_in_conditions(
        strategy_id, similar
    )
    # Momentum strategy: Sharpe 2.1, Return 15%, WinRate 68%
    
    suitability = activation_system._check_regime_suitability(
        strategy_type, current_regime
    )
    # Momentum + Bull Trending: 0.9 suitability

# 5. Make activation decisions
decisions = activation_system._select_strategies_to_activate(evaluations)
# Top 3 strategies selected

# 6. Apply changes
await activation_system._apply_activation_decisions(decisions)
# 1 activated, 1 deactivated, 1 kept

# 7. Monitor for regime change
# If regime changes → immediate re-evaluation triggered
```

## Error Handling

### Graceful Degradation
- Missing data sources → safe defaults
- API failures → cached data
- Insufficient historical data → skip evaluation
- Database errors → retry with exponential backoff

### Logging
- Structured logging with contextual information
- Regime changes → WARNING level
- Activation/deactivation → INFO level
- Errors → ERROR level with stack traces

## Testing Recommendations

### Unit Tests
1. Regime classification with various conditions
2. Similarity matching accuracy
3. Performance metric calculations
4. Suitability matrix correctness
5. Activation logic edge cases

### Integration Tests
1. End-to-end activation flow
2. Regime change handling
3. Database operations
4. API endpoint responses
5. Multi-strategy coordination

### Performance Tests
1. Large strategy pool (100+ strategies)
2. Extensive historical data (1M+ conditions)
3. Concurrent API requests
4. Memory usage under load
5. Response time benchmarks

## Future Enhancements

### Phase 2 (Potential)
1. **Multi-Asset Regime Detection**: Separate regimes per asset class
2. **Strategy Clustering**: Group similar strategies for better diversity
3. **Ensemble Activation**: Activate complementary strategy combinations
4. **Adaptive Thresholds**: Machine learning for dynamic threshold optimization
5. **Regime Prediction**: Forecast regime changes before they occur
6. **Performance Attribution**: Decompose returns by market factors
7. **Risk Budgeting**: Allocate risk across activated strategies
8. **Meta-Learning**: Learn which activation decisions work best

### Integration Opportunities
- **Portfolio Optimizer**: Coordinate with position sizing
- **Risk Manager**: Real-time risk regime alignment
- **Backtesting Framework**: Simulate activation decisions historically
- **Alert System**: Notify on regime changes and activations
- **Monitoring Dashboard**: Real-time visualization

## Completion Checklist

- [x] Core activation system implementation
- [x] Market regime detection (7 regimes)
- [x] Historical condition matching (ML-based)
- [x] Strategy performance evaluation
- [x] Regime suitability matrix (8 types x 7 regimes)
- [x] Automatic activation/deactivation logic
- [x] Regime change detection and response
- [x] 10 comprehensive API endpoints
- [x] Integration with risk_manager (Task #8)
- [x] Integration with sentiment data (Task #7)
- [x] Integration with macro indicators (Task #5)
- [x] Integration with correlation analysis (Task #6)
- [x] Database storage structure
- [x] Error handling and logging
- [x] Configuration management
- [x] Documentation

## Files Created/Modified

### New Files
1. `enhanced_strategy_activation.py` (1,150 lines)
   - EnhancedStrategyActivationSystem class
   - Market regime detection
   - Historical condition matching
   - Performance evaluation
   - Activation logic

2. `strategy_activation_api.py` (550 lines)
   - 10 REST API endpoints
   - Request/response models
   - Error handling
   - Health checks

### Modified Files
1. `strategy_service/main.py`
   - Added enhanced_activation_system initialization
   - Integrated with existing components

2. `strategy_service/api_endpoints.py`
   - Added activation router import
   - Included activation endpoints in API

## Dependencies

### Python Packages
- numpy: Array operations
- scipy: Distance calculations
- sklearn: Feature scaling
- pandas: Data manipulation (optional)
- structlog: Structured logging
- fastapi: REST API
- pydantic: Data validation

### Internal Services
- database: Cosmos DB interface
- market_data_service: Market data API
- risk_manager: Risk regime detection
- config: Settings management

## Monitoring

### Key Metrics to Track
1. **Regime Detection Rate**: Changes per day
2. **Activation Frequency**: Changes per day
3. **Strategy Performance**: Sharpe ratio improvement
4. **System Latency**: API response times
5. **Error Rate**: Failed operations percentage
6. **Data Freshness**: Age of market data
7. **Cache Hit Rate**: Historical condition reuse
8. **Database Load**: Query counts and latency

### Alerts
- Regime changes (always notify)
- High activation frequency (> 5 per hour)
- System errors (any exception)
- Data staleness (> 5 minutes old)
- Performance degradation (response time > 2s)

## Conclusion

The Enhanced Dynamic Strategy Activation System provides intelligent, data-driven strategy management that adapts to changing market conditions. By leveraging historical performance in similar environments and regime-specific strategy suitability, it maximizes the probability of activating strategies best suited for current market conditions while minimizing exposure to poorly-matched strategies.

The system is fully integrated with the existing masterTrade infrastructure, including risk management, sentiment analysis, macro indicators, and correlation data, providing a comprehensive view of market conditions for optimal strategy selection.
