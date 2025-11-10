# Advanced Risk Management System Documentation

## Overview

The Advanced Risk Management System provides comprehensive portfolio-level risk controls, correlation-based position sizing, dynamic stop-loss management based on volatility regimes, maximum drawdown controls with circuit breakers, and asset class/sector exposure limits.

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│              Advanced Risk Management System                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │          Advanced Risk Controller (Core)                    │ │
│  │  - Trade approval orchestration                            │ │
│  │  - Portfolio-level limit enforcement                       │ │
│  │  - Risk regime determination                               │ │
│  │  - Circuit breaker management                              │ │
│  └────────────┬───────────────────────────────┬───────────────┘ │
│               │                               │                  │
│    ┌──────────▼──────────┐         ┌─────────▼────────┐        │
│    │  Correlation Risk   │         │  Drawdown        │        │
│    │  Assessment         │         │  Control         │        │
│    │  - Matrix analysis  │         │  - Circuit       │        │
│    │  - Cluster detect   │         │    breakers      │        │
│    │  - Diversification  │         │  - Position      │        │
│    └──────────┬──────────┘         │    restrictions  │        │
│               │                     └─────────┬────────┘        │
│               │                               │                  │
│    ┌──────────▼──────────────────────────────▼────────┐        │
│    │         Dynamic Stop-Loss Calculator             │        │
│    │  - Volatility regime-based                       │        │
│    │  - ATR multipliers                               │        │
│    │  - Time decay & breakeven triggers               │        │
│    └──────────┬───────────────────────────────────────┘        │
│               │                                                  │
│    ┌──────────▼──────────────────────────────────────┐         │
│    │       Position Adjustment Engine                 │         │
│    │  - Periodic review (5 minutes)                  │         │
│    │  - Stop-loss tightening                         │         │
│    │  - Position reduction                           │         │
│    │  - Emergency liquidation                        │         │
│    └──────────┬──────────────────────────────────────┘         │
│               │                                                  │
└───────────────┼──────────────────────────────────────────────────┘
                │
    ┌───────────▼──────────────┐
    │  Existing Risk Components │
    │  - Position Sizing Engine │
    │  - Stop-Loss Manager      │
    │  - Portfolio Controller   │
    └────────────────────────────┘
```

## Core Components

### 1. Advanced Risk Controller (`advanced_risk_controller.py`)

**Purpose**: Orchestrates all risk management decisions with portfolio-level awareness

**Key Classes**:

#### `PortfolioLimits`
Comprehensive portfolio-level risk limits:

```python
PortfolioLimits(
    max_portfolio_leverage=2.0,              # Max 2x leverage
    max_portfolio_var_percent=5.0,           # Max 5% 1-day VaR
    max_drawdown_percent=15.0,               # Max 15% drawdown
    min_cash_reserve_percent=10.0,           # Keep 10% cash
    max_single_position_percent=10.0,        # Max 10% per position
    max_correlated_exposure_percent=25.0,    # Max 25% in correlated assets
    max_sector_exposure_percent=30.0,        # Max 30% per sector
    max_crypto_exposure_percent=80.0,        # Max 80% in crypto
    max_defi_exposure_percent=20.0,          # Max 20% in DeFi
    max_altcoin_exposure_percent=40.0,       # Max 40% in altcoins
    max_single_strategy_percent=40.0,        # Max 40% to one strategy
    max_short_exposure_percent=20.0,         # Max 20% short exposure
    high_vol_position_reduction=0.5,         # Reduce by 50% in high vol
    extreme_vol_position_reduction=0.25      # Reduce by 75% in extreme vol
)
```

#### `RiskRegime` Enum
Market condition classification:

```python
RiskRegime.LOW_VOL_BULLISH      # Low volatility, positive trend
RiskRegime.LOW_VOL_BEARISH      # Low volatility, negative trend
RiskRegime.HIGH_VOL_BULLISH     # High volatility, positive trend
RiskRegime.HIGH_VOL_BEARISH     # High volatility, negative trend
RiskRegime.EXTREME_VOLATILITY   # Extreme market volatility
RiskRegime.CRISIS               # Market crisis conditions
```

#### `CircuitBreakerLevel` Enum
Progressive risk controls based on drawdown:

```python
CircuitBreakerLevel.NONE         # < 5% drawdown: Normal operations
CircuitBreakerLevel.WARNING      # 5-10% drawdown: Monitor closely, 75% position sizes
CircuitBreakerLevel.LEVEL_1      # 10-15% drawdown: Reduce sizes 50%, tighten stops
CircuitBreakerLevel.LEVEL_2      # 15-20% drawdown: No new positions
CircuitBreakerLevel.LEVEL_3      # >= 20% drawdown: Close all positions, stop trading
```

**Key Methods**:

```python
async def approve_new_position(
    symbol: str,
    strategy_id: str,
    signal_strength: float,
    requested_size_usd: float,
    current_price: float,
    volatility: Optional[float] = None
) -> RiskApprovalResult
```
Comprehensive trade approval with:
- Circuit breaker checks
- Portfolio limit validation
- Correlation risk assessment
- Sector/asset class exposure checks
- Volatility regime analysis
- Dynamic position sizing
- Stop-loss calculation

```python
async def adjust_existing_positions() -> Dict[str, any]
```
Periodic position adjustment based on:
- Portfolio drawdown
- Volatility regime changes
- Correlation shifts
- Exposure limit breaches

### 2. Correlation Risk Assessment

**Metrics Calculated**:

- **Portfolio Correlation**: Average pairwise correlation
- **Diversification Ratio**: Portfolio vol / weighted avg vol
- **Effective Assets**: Number of independent bets (`n / (1 + (n-1) * avg_corr)`)
- **Correlation Risk Score**: 0-100, higher = more risk
- **Correlation Clusters**: Groups of highly correlated assets (>0.7)

**Example Output**:
```python
CorrelationRiskMetrics(
    portfolio_correlation=0.62,          # High correlation
    diversification_ratio=0.45,          # Low diversification
    effective_assets=2.3,                # Acts like 2-3 assets
    correlation_risk_score=75.0,         # High risk
    correlation_clusters={
        'BTCUSDT': ['ETHUSDT', 'BNBUSDT'],
        'ETHUSDT': ['BTCUSDT', 'LINKUSDT']
    },
    recommendations=[
        "Very high correlation - consider different asset class",
        "Low diversification - portfolio acts like 2-3 assets"
    ]
)
```

### 3. Dynamic Stop-Loss Parameters

Stop-loss parameters adapt to market regime:

| Regime | Stop % | Trailing | ATR Mult | Reasoning |
|--------|--------|----------|----------|-----------|
| Low Vol Bullish | 1.0x | 2% | 2.0x | Standard stops |
| Low Vol Bearish | 0.8x | 1.5% | 1.5x | Tighter stops |
| High Vol Bullish | 1.5x | 4% | 3.0x | Wider to avoid whipsaw |
| High Vol Bearish | 1.2x | 3% | 2.5x | Moderate stops |
| Extreme Volatility | 2.0x | 6% | 4.0x | Very wide stops |
| Crisis | 0.5x | 1% | 1.0x | Very tight for capital preservation |

**Example**:
```python
DynamicStopLossParams(
    regime=RiskRegime.HIGH_VOL_BULLISH,
    base_stop_percent=0.03,              # 3% base
    adjusted_stop_percent=0.045,         # 4.5% adjusted (1.5x)
    trailing_distance_percent=0.04,      # 4% trailing
    atr_multiplier=3.0,
    time_decay_rate=0.05,
    breakeven_trigger_percent=0.03,
    volatility_multiplier=1.2,
    reasoning="High volatility bullish market - wider stops to avoid whipsaw"
)
```

### 4. Drawdown Control & Circuit Breakers

**Circuit Breaker Triggers**:

```
Portfolio Drawdown:
├─ 0-5%:  NONE - Normal operations
│         ├─ Position size: 100%
│         └─ New positions: Allowed
│
├─ 5-10%: WARNING - Monitor closely
│         ├─ Position size: 75%
│         ├─ New positions: Allowed
│         └─ Action: Consider reducing risk
│
├─ 10-15%: LEVEL 1 - Reduce risk
│          ├─ Position size: 50%
│          ├─ New positions: Allowed (reduced)
│          └─ Actions: Reduce sizes, tighten stops
│
├─ 15-20%: LEVEL 2 - No new positions
│          ├─ Position size: 0%
│          ├─ New positions: BLOCKED
│          └─ Actions: No new positions, review strategy
│
└─ >= 20%: LEVEL 3 - EMERGENCY STOP
           ├─ Position size: 0%
           ├─ New positions: BLOCKED
           └─ Actions: CLOSE ALL POSITIONS, STOP TRADING
```

**DrawdownControl Data Structure**:
```python
DrawdownControl(
    current_portfolio_value=95000.0,
    peak_portfolio_value=105000.0,
    current_drawdown_percent=9.52,
    circuit_breaker_level=CircuitBreakerLevel.WARNING,
    positions_allowed=True,
    position_size_multiplier=0.75,
    time_until_reset=None,
    actions_taken=["MONITOR_CLOSELY", "CONSIDER_REDUCING_RISK"],
    last_updated=datetime.utcnow()
)
```

### 5. Risk Approval Flow

```
Trade Request
    │
    ▼
┌──────────────────────┐
│ 1. Circuit Breaker   │
│    Check             │◄── Drawdown > 15%? → REJECT
└────────┬─────────────┘
         │ Passed
         ▼
┌──────────────────────┐
│ 2. Portfolio Metrics │
│    - Leverage        │◄── Leverage > 2x? → REJECT
│    - VaR             │◄── VaR > 5%? → REJECT
└────────┬─────────────┘
         │ Passed
         ▼
┌──────────────────────┐
│ 3. Risk Regime       │
│    Determination     │◄── High vol? → Reduce 50%
└────────┬─────────────┘     Extreme? → Reduce 75%
         │
         ▼
┌──────────────────────┐
│ 4. Correlation       │
│    Analysis          │◄── Corr > 0.7? → Reduce 50%
└────────┬─────────────┘     Corr > 0.8? → REJECT
         │
         ▼
┌──────────────────────┐
│ 5. Concentration     │
│    Limits            │◄── Single pos > 10%? → Reduce
└────────┬─────────────┘     Strategy > 40%? → Reduce
         │
         ▼
┌──────────────────────┐
│ 6. Asset Class       │
│    Exposure          │◄── Crypto > 80%? → REJECT
└────────┬─────────────┘     DeFi > 20%? → REJECT
         │
         ▼
┌──────────────────────┐
│ 7. Calculate         │
│    Final Size &      │
│    Stop-Loss         │
└────────┬─────────────┘
         │
         ▼
┌──────────────────────┐
│ Approval Result      │
│ - Approved/Rejected  │
│ - Size adjustment    │
│ - Stop-loss params   │
│ - Risk score         │
│ - Warnings           │
│ - Recommendations    │
└──────────────────────┘
```

## API Endpoints

### Trade Approval

**POST** `/api/v1/advanced-risk/approve-trade`

Comprehensive trade approval with all risk checks.

**Request**:
```json
{
  "symbol": "BTCUSDT",
  "strategy_id": "momentum_btc_1",
  "signal_strength": 0.85,
  "requested_size_usd": 10000.0,
  "current_price": 45000.0,
  "volatility": 0.35
}
```

**Response**:
```json
{
  "approved": true,
  "position_size_adjustment": 0.75,
  "adjusted_size_usd": 7500.0,
  "stop_loss_percent": 0.035,
  "stop_loss_price": 43425.0,
  "risk_score": 45.2,
  "risk_level": "medium",
  "risk_factors": {
    "regime": 0.4,
    "correlation": 0.62,
    "drawdown": 0.05
  },
  "warnings": [
    "Portfolio leverage at 1.85x (limit 2.0x)",
    "High correlation with existing positions"
  ],
  "rejections": [],
  "recommendations": [
    "Position approved with 75% of requested size",
    "Stop-loss: 3.50% (High volatility bullish market - wider stops)"
  ],
  "metadata": {
    "regime": "high_vol_bullish",
    "drawdown": 5.2,
    "leverage": 1.85,
    "var_1d": 4.1,
    "correlation_score": 62.0
  }
}
```

### Position Size Recommendation

**POST** `/api/v1/advanced-risk/position-size-recommendation`

Get position size recommendation without full approval.

**Request**:
```json
{
  "symbol": "ETHUSDT",
  "strategy_id": "mean_reversion_eth",
  "signal_strength": 0.7,
  "current_price": 3000.0
}
```

**Response**:
```json
{
  "symbol": "ETHUSDT",
  "base_size_usd": 5000.0,
  "base_quantity": 1.667,
  "adjustment_factor": 0.8,
  "final_size_usd": 4000.0,
  "final_quantity": 1.333,
  "stop_loss_percent": 0.025,
  "stop_loss_price": 2925.0,
  "max_loss_usd": 100.0,
  "risk_score": 38.5,
  "approved": true,
  "warnings": ["Moderate correlation with BTC position"],
  "recommendations": ["Position size reduced by 20% due to portfolio correlation"],
  "regime": "low_vol_bullish"
}
```

### Risk Status Dashboard

**GET** `/api/v1/advanced-risk/risk-status`

Get comprehensive risk status for monitoring.

**Response**:
```json
{
  "success": true,
  "data": {
    "timestamp": "2024-01-15T14:30:00Z",
    "circuit_breaker": {
      "level": "warning",
      "drawdown_percent": 7.2,
      "positions_allowed": true,
      "size_multiplier": 0.75,
      "actions": ["MONITOR_CLOSELY", "CONSIDER_REDUCING_RISK"]
    },
    "risk_regime": "high_vol_bearish",
    "portfolio_metrics": {
      "total_value": 98500.0,
      "leverage": 1.65,
      "var_1d": 4.2,
      "var_5d": 9.1,
      "drawdown": 7.2,
      "risk_score": 52.3,
      "risk_level": "medium"
    },
    "correlation_metrics": {
      "avg_correlation": 0.58,
      "diversification_ratio": 0.52,
      "effective_assets": 3.2,
      "correlation_risk_score": 68.0
    },
    "limits": {
      "max_leverage": 2.0,
      "max_var": 5.0,
      "max_drawdown": 15.0,
      "max_single_position": 10.0,
      "max_sector": 30.0
    },
    "active_positions": 8
  }
}
```

### Update Portfolio Limits

**POST** `/api/v1/advanced-risk/update-limits`

Update portfolio risk limits (admin only).

**Request**:
```json
{
  "max_portfolio_leverage": 2.5,
  "max_portfolio_var_percent": 6.0,
  "max_drawdown_percent": 18.0
}
```

**Response**:
```json
{
  "success": true,
  "message": "Portfolio limits updated",
  "new_limits": {
    "max_leverage": 2.5,
    "max_var": 6.0,
    "max_drawdown": 18.0,
    "max_single_position": 10.0,
    "max_correlated_exposure": 25.0,
    "max_sector_exposure": 30.0
  }
}
```

### Force Adjustment Check

**POST** `/api/v1/advanced-risk/force-adjustment-check`

Manually trigger position adjustment check.

**Response**:
```json
{
  "success": true,
  "adjustments": {
    "timestamp": "2024-01-15T14:35:00Z",
    "stops_tightened": [
      {
        "symbol": "BTCUSDT",
        "old_stop": 43000.0,
        "new_stop": 43500.0,
        "reason": "Regime change to high_vol_bearish"
      }
    ],
    "positions_reduced": [
      {
        "symbol": "ETHUSDT",
        "reduction_percent": 30.0,
        "reason": "Portfolio VaR exceeded - reducing positions"
      }
    ],
    "positions_closed": [],
    "warnings_issued": [
      {
        "level": "high",
        "message": "Portfolio risk level: high",
        "risk_score": 68.5
      }
    ]
  }
}
```

### Correlation Analysis

**GET** `/api/v1/advanced-risk/correlation-analysis?symbols=BTCUSDT,ETHUSDT,BNBUSDT`

Get correlation analysis for specific symbols or entire portfolio.

**Response**:
```json
{
  "success": true,
  "symbols": ["BTCUSDT", "ETHUSDT", "BNBUSDT"],
  "avg_correlation": 0.72,
  "diversification_ratio": 0.41,
  "effective_assets": 1.8,
  "correlation_risk_score": 78.0,
  "correlation_clusters": {
    "BTCUSDT": ["ETHUSDT", "BNBUSDT"],
    "ETHUSDT": ["BTCUSDT", "LINKUSDT"]
  },
  "recommendations": [
    "Very high correlation - consider different asset class",
    "Low diversification - portfolio acts like 1-2 assets",
    "Found 2 correlation clusters"
  ]
}
```

## Integration Examples

### Strategy Service Integration

```python
from aiohttp import ClientSession

class AdvancedTradingStrategy:
    def __init__(self):
        self.risk_api_url = "http://risk-manager:8001/api/v1/advanced-risk"
    
    async def execute_trade(self, symbol: str, signal_strength: float):
        # Request trade approval from advanced risk management
        async with ClientSession() as session:
            approval_request = {
                "symbol": symbol,
                "strategy_id": self.strategy_id,
                "signal_strength": signal_strength,
                "requested_size_usd": self.calculate_ideal_size(),
                "current_price": await self.get_current_price(symbol),
                "volatility": await self.get_volatility(symbol)
            }
            
            async with session.post(
                f"{self.risk_api_url}/approve-trade",
                json=approval_request
            ) as resp:
                approval = await resp.json()
            
            if not approval['approved']:
                logger.warning(
                    f"Trade rejected: {symbol}",
                    rejections=approval['rejections']
                )
                return None
            
            # Execute trade with approved size and stop-loss
            position_size = approval['adjusted_size_usd']
            stop_loss = approval['stop_loss_price']
            
            logger.info(
                f"Trade approved: {symbol}",
                size=position_size,
                stop_loss=stop_loss,
                warnings=approval['warnings']
            )
            
            return await self.place_order(
                symbol=symbol,
                size_usd=position_size,
                stop_loss_price=stop_loss
            )
```

### Monitoring Dashboard Integration

```typescript
// React component for risk status monitoring
const RiskDashboard = () => {
  const [riskStatus, setRiskStatus] = useState(null);
  
  useEffect(() => {
    const fetchRiskStatus = async () => {
      const response = await fetch(
        'http://risk-manager:8001/api/v1/advanced-risk/risk-status'
      );
      const data = await response.json();
      setRiskStatus(data.data);
    };
    
    // Fetch every 10 seconds
    const interval = setInterval(fetchRiskStatus, 10000);
    fetchRiskStatus();
    
    return () => clearInterval(interval);
  }, []);
  
  return (
    <div className="risk-dashboard">
      <CircuitBreakerWidget 
        level={riskStatus?.circuit_breaker.level}
        drawdown={riskStatus?.circuit_breaker.drawdown_percent}
      />
      
      <RiskRegimeWidget 
        regime={riskStatus?.risk_regime}
      />
      
      <PortfolioMetricsWidget 
        metrics={riskStatus?.portfolio_metrics}
        limits={riskStatus?.limits}
      />
      
      <CorrelationHeatmap 
        correlations={riskStatus?.correlation_metrics}
      />
    </div>
  );
};
```

## Configuration

### Environment Variables

```bash
# Advanced Risk Management Configuration
ADVANCED_RISK_ENABLED=true

# Portfolio Limits
MAX_PORTFOLIO_LEVERAGE=2.0
MAX_PORTFOLIO_VAR_PERCENT=5.0
MAX_DRAWDOWN_PERCENT=15.0
MAX_SINGLE_POSITION_PERCENT=10.0
MAX_CORRELATED_EXPOSURE_PERCENT=25.0
MAX_SECTOR_EXPOSURE_PERCENT=30.0

# Asset Class Limits
MAX_CRYPTO_EXPOSURE_PERCENT=80.0
MAX_DEFI_EXPOSURE_PERCENT=20.0
MAX_ALTCOIN_EXPOSURE_PERCENT=40.0

# Volatility Adjustments
HIGH_VOL_POSITION_REDUCTION=0.5
EXTREME_VOL_POSITION_REDUCTION=0.25

# Adjustment Schedule
POSITION_ADJUSTMENT_INTERVAL=300  # 5 minutes

# Circuit Breaker Settings
CIRCUIT_BREAKER_WARNING_DRAWDOWN=5.0
CIRCUIT_BREAKER_LEVEL1_DRAWDOWN=10.0
CIRCUIT_BREAKER_LEVEL2_DRAWDOWN=15.0
CIRCUIT_BREAKER_LEVEL3_DRAWDOWN=20.0
```

## Monitoring Metrics

Track these metrics in Grafana/Prometheus:

### Risk Scores
- `advanced_risk_composite_score`: Overall portfolio risk (0-100)
- `advanced_risk_correlation_score`: Correlation risk (0-100)
- `advanced_risk_regime`: Current risk regime (enum)

### Circuit Breaker
- `circuit_breaker_level`: Current level (0-3)
- `portfolio_drawdown_percent`: Current drawdown
- `circuit_breaker_triggers_total`: Total triggers by level

### Position Approvals
- `trade_approvals_total`: Total approvals (approved/rejected)
- `trade_rejection_reasons_total`: Rejections by reason
- `position_size_adjustments`: Size reduction distribution

### Adjustments
- `position_adjustments_total`: Total adjustments by type
- `stops_tightened_total`: Stop-loss tightening events
- `positions_reduced_total`: Position reduction events
- `emergency_closes_total`: Circuit breaker Level 3 closures

### Correlation
- `portfolio_avg_correlation`: Average portfolio correlation
- `portfolio_effective_assets`: Effective number of independent bets
- `correlation_clusters_count`: Number of correlation clusters

## Best Practices

### 1. Regular Limit Reviews
- Review portfolio limits monthly
- Adjust based on market conditions
- Document all limit changes

### 2. Circuit Breaker Testing
- Test circuit breaker logic in simulation
- Have manual override procedures ready
- Train team on emergency protocols

### 3. Correlation Monitoring
- Monitor correlation daily
- Alert on sudden correlation spikes
- Maintain diversification targets

### 4. Regime Adaptation
- Don't fight the regime
- Reduce size in high volatility
- Accept wider stops in volatile markets

### 5. Position Sizing Discipline
- Never override risk system without cause
- Document all manual overrides
- Review rejections for false positives

### 6. Gradual Limit Adjustments
- Change limits gradually (10-20% at a time)
- Test impact before full deployment
- Monitor for unintended consequences

## Troubleshooting

### Issue: Too Many Trade Rejections

**Symptoms**: High rejection rate, strategies unable to execute

**Possible Causes**:
1. Limits too conservative
2. High portfolio correlation
3. Drawdown near circuit breaker level
4. Volatility regime too restrictive

**Solutions**:
1. Review and adjust portfolio limits
2. Add uncorrelated assets
3. Wait for portfolio recovery
4. Consider regime-specific strategies

### Issue: Circuit Breaker Frequently Triggered

**Symptoms**: Circuit breaker WARNING or LEVEL_1 often active

**Possible Causes**:
1. Strategies too aggressive
2. Poor risk/reward ratios
3. Inadequate stop-losses
4. High market volatility

**Solutions**:
1. Review strategy win rates
2. Widen stop-losses
3. Reduce position sizes
4. Pause during high volatility

### Issue: Low Diversification

**Symptoms**: Effective assets < 3, high correlation score

**Possible Causes**:
1. Trading only crypto majors
2. All strategies long-only
3. No cross-asset diversification

**Solutions**:
1. Add strategies for different assets
2. Consider short strategies
3. Add macro hedges (gold, bonds)
4. Trade multiple crypto sectors

## Related Documentation

- `README.md`: Risk Manager overview
- `position_sizing.py`: Position sizing algorithms
- `stop_loss_manager.py`: Stop-loss management
- `portfolio_risk_controller.py`: Portfolio risk monitoring
- `advanced_risk_controller.py`: Advanced risk controller implementation
- `advanced_risk_service.py`: Service integration
- `advanced_risk_api.py`: API endpoints

## Support & Maintenance

### Logging
All risk decisions are logged with structured logging:
```python
logger.info(
    "Trade approved",
    symbol="BTCUSDT",
    approved_size=7500.0,
    risk_score=45.2,
    regime="high_vol_bullish"
)
```

### Audit Trail
- All trade approvals/rejections logged
- Circuit breaker triggers recorded
- Limit changes tracked
- Manual overrides audited

### Health Checks
```bash
# Check service health
curl http://risk-manager:8001/api/v1/advanced-risk/health

# Check risk status
curl http://risk-manager:8001/api/v1/advanced-risk/risk-status

# Check current regime
curl http://risk-manager:8001/api/v1/advanced-risk/risk-regime
```

## Version History

- **v1.0.0** (2024-01-15): Initial release
  - Portfolio-level risk limits
  - Correlation-based position sizing
  - Dynamic stop-loss management
  - Circuit breaker system
  - Asset class exposure limits
  - Risk regime classification
  - Comprehensive API endpoints
