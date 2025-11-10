# Automatic Strategy Activation System

## Overview

The Automatic Strategy Activation System is an intelligent component of the MasterTrade platform that manages which trading strategies are actively running based on their performance metrics. The system ensures only the best-performing strategies are active while maintaining optimal resource utilization.

## Key Features

### 1. Dynamic Strategy Management
- **Automatic Activation**: Continuously evaluates all strategies and activates the best performers
- **Smart Deactivation**: Automatically deactivates underperforming strategies
- **Performance-Based Selection**: Uses comprehensive scoring to rank strategies
- **Stability Controls**: Prevents frequent switching with configurable stability periods

### 2. Configurable Limits
- **MAX_ACTIVE_STRATEGIES Setting**: Database-driven configuration for maximum concurrent active strategies
- **Default Value**: 2 active strategies (if setting is undefined)
- **Runtime Updates**: Setting can be updated via API without service restart
- **Immediate Response**: Reduces active strategies immediately when limit is decreased

### 3. Comprehensive Evaluation Metrics
- **Performance Score** (40%): Recent trading performance and returns
- **Backtest Quality** (25%): Historical backtest results and reliability
- **Market Alignment** (20%): Adaptation to current market conditions
- **Risk Management** (15%): Risk-adjusted performance and stability

### 4. Intelligent Selection Criteria
- **Minimum Sharpe Ratio**: 0.5 (configurable)
- **Maximum Drawdown**: -30% (configurable)
- **Minimum Trades**: 5 trades in evaluation period
- **Activity Requirement**: Must have traded within last 14 days
- **Positive Overall Score**: Must have positive composite score

## System Architecture

### Components

1. **AutomaticStrategyActivationManager**
   - Core activation logic and decision engine
   - Performance evaluation and scoring
   - Database integration for settings and logging

2. **Database Extensions**
   - Strategy retrieval methods
   - Trade history analysis
   - Backtest results integration
   - Activation logging

3. **API Endpoints**
   - Manual activation triggers
   - Status monitoring
   - Configuration management
   - Audit log access

4. **Scheduler Integration**
   - Automatic checks every 4 hours
   - Daily comprehensive review at 2:00 AM UTC
   - Stability period enforcement

### Database Containers

```
settings
├── MAX_ACTIVE_STRATEGIES (default: 2)
└── Other system settings

strategy_activation_log
├── Activation/deactivation events
├── Timestamps and reasons
└── Strategy performance snapshots

strategies
├── Strategy definitions
├── Current status (active/inactive/paused)
└── Performance metadata

trades
├── Historical trading data
├── Performance metrics
└── Strategy attribution
```

## Configuration

### Database Setting: MAX_ACTIVE_STRATEGIES

The system reads the maximum number of active strategies from the `settings` container:

```json
{
  "id": "MAX_ACTIVE_STRATEGIES",
  "key": "MAX_ACTIVE_STRATEGIES", 
  "value": "2",
  "description": "Maximum number of active trading strategies",
  "type": "integer"
}
```

### Activation Criteria

```python
# Minimum requirements for strategy activation
MIN_SHARPE_RATIO = 0.5
MAX_DRAWDOWN_THRESHOLD = -0.30  # Max 30% drawdown
MIN_TRADES = 5
MAX_DAYS_INACTIVE = 14
MIN_STABILITY_HOURS = 4
```

### Scoring Weights

```python
# Overall score calculation weights
PERFORMANCE_WEIGHT = 0.40    # Recent performance
BACKTEST_WEIGHT = 0.25       # Backtest quality  
MARKET_ALIGNMENT_WEIGHT = 0.20  # Current market fit
RISK_WEIGHT = 0.15           # Risk management
```

## API Endpoints

### Get Activation Status
```http
GET /api/v1/strategy/activation/status
```

Returns current activation status, active strategies, and top candidates.

### Trigger Manual Check
```http
POST /api/v1/strategy/activation/check
```

Manually triggers an activation evaluation cycle.

### Get/Update MAX_ACTIVE_STRATEGIES
```http
GET /api/v1/strategy/activation/max-active
PUT /api/v1/strategy/activation/max-active
```

Retrieve or update the maximum active strategies setting.

### View Activation Log
```http
GET /api/v1/strategy/activation/log?limit=20
```

Access historical activation/deactivation events.

## Operation Schedule

### Automatic Checks
- **Every 4 hours**: Lightweight activation check
- **Daily at 2:00 AM UTC**: Comprehensive strategy review + activation
- **On demand**: Manual triggers via API

### Check Process
1. **Load Setting**: Read MAX_ACTIVE_STRATEGIES from database
2. **Evaluate Candidates**: Score all eligible strategies
3. **Select Optimal**: Choose top N strategies meeting criteria
4. **Calculate Changes**: Determine activation/deactivation needs
5. **Apply Changes**: Update strategy status in database
6. **Log Results**: Record changes for audit trail

## Performance Impact

### Expected Improvements
- **15-25% Sharpe Ratio Improvement**: From automatic optimization
- **Reduced Risk**: Through continuous performance monitoring
- **Better Resource Utilization**: Only best strategies consume resources
- **Adaptive Performance**: Automatically adjusts to market conditions

### System Efficiency
- **Minimal Overhead**: Lightweight checks every 4 hours
- **Smart Caching**: Reuses performance calculations
- **Stability Controls**: Prevents excessive strategy switching
- **Scalable Design**: Handles hundreds of strategies efficiently

## Logging and Monitoring

### Activation Events
```json
{
  "id": "activation_1730678400",
  "timestamp": "2024-11-04T02:00:00Z",
  "activated_strategies": ["strategy_123", "strategy_456"],
  "deactivated_strategies": ["strategy_789"],
  "max_active_strategies": 2,
  "activation_reason": "automatic_optimization"
}
```

### Performance Metrics
- **Activation frequency**: How often strategies are changed
- **Performance distribution**: Grades and scores of active strategies
- **Stability metrics**: Time between activation changes
- **Success rates**: Performance after activation

## Integration Points

### With Daily Strategy Review
- Combined daily review at 2:00 AM UTC
- Shared performance evaluation logic
- Coordinated improvement decisions
- Unified logging and notifications

### With Market Data Service
- Real-time performance tracking
- Market condition analysis
- Strategy-specific data requests
- Performance attribution

### With Monitoring Service
- Prometheus metrics export
- Alert generation for significant changes
- Dashboard visualization
- Performance trend analysis

## Error Handling

### Graceful Degradation
- **Database Unavailable**: Uses cached settings and logs errors
- **Invalid Settings**: Falls back to default value (2)
- **Strategy Evaluation Errors**: Skips problematic strategies
- **Partial Failures**: Continues with successful evaluations

### Recovery Mechanisms
- **Automatic Retry**: For transient database errors
- **Default Fallback**: When settings cannot be loaded
- **Consistency Checks**: Validates activation state periodically
- **Manual Override**: API endpoints for emergency intervention

## Security Considerations

### Access Control
- API endpoints require proper authentication
- Database access uses least-privilege principle
- Setting updates logged for audit trail
- Strategy modifications tracked with timestamps

### Data Integrity
- Atomic updates for strategy status changes
- Validation of setting values before application
- Backup of previous activation state
- Recovery procedures for data corruption

## Deployment Guide

### 1. Initialize Database Containers
```bash
./setup_strategy_activation.sh
```

### 2. Verify Settings
```bash
# Check MAX_ACTIVE_STRATEGIES setting exists
az cosmosdb sql item read \
  --account-name <account> \
  --database-name mastertrade \
  --container-name settings \
  --partition-key-value "MAX_ACTIVE_STRATEGIES" \
  --item-id "MAX_ACTIVE_STRATEGIES"
```

### 3. Start Strategy Service
The activation manager initializes automatically when the strategy service starts.

### 4. Monitor Activation
```bash
# Check activation status
curl -X GET http://localhost:8000/api/v1/strategy/activation/status

# View recent activation log  
curl -X GET http://localhost:8000/api/v1/strategy/activation/log
```

## Troubleshooting

### Common Issues

#### No Strategies Being Activated
- **Cause**: No strategies meet minimum criteria
- **Solution**: Lower criteria thresholds or improve strategy performance
- **Check**: Review candidate evaluation in status endpoint

#### Too Frequent Activation Changes
- **Cause**: Stability period too short
- **Solution**: Increase `min_stability_hours` setting
- **Check**: Review activation log frequency

#### Database Connection Errors
- **Cause**: Invalid Cosmos DB credentials or network issues
- **Solution**: Verify connection settings and network connectivity
- **Check**: Service logs for detailed error messages

#### Setting Not Updating
- **Cause**: Invalid value or database write permissions
- **Solution**: Check value format and database access permissions
- **Check**: Database container permissions and connection status

### Debug Commands

```bash
# Check activation manager status
curl -X GET http://localhost:8000/api/v1/strategy/activation/status | jq

# Trigger manual activation check
curl -X POST http://localhost:8000/api/v1/strategy/activation/check

# View activation criteria and current candidates
curl -X GET http://localhost:8000/api/v1/strategy/activation/status | jq '.activation_criteria'
```

## Future Enhancements

### Planned Features
- **Machine Learning Selection**: AI-powered strategy selection optimization
- **Market Regime Detection**: Adapt activation based on market conditions
- **Risk Budgeting**: Allocate strategies based on risk contribution
- **Multi-Objective Optimization**: Balance multiple performance objectives

### Potential Integrations
- **Portfolio Optimization**: Consider correlation between active strategies
- **Risk Management**: Dynamic risk limits based on market volatility
- **Performance Attribution**: Detailed analysis of activation decisions
- **Predictive Analytics**: Forecast strategy performance for better selection

## Conclusion

The Automatic Strategy Activation System provides intelligent, data-driven management of active trading strategies. By continuously evaluating performance and automatically selecting the best strategies, the system ensures optimal resource utilization while maximizing trading performance.

The system's configurability, comprehensive evaluation metrics, and robust error handling make it suitable for production trading environments where reliability and performance are critical.