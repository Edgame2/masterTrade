"""
Portfolio Rebalancer

Handles portfolio rebalancing logic including:
- Rebalancing triggers (time-based, drift-based, volatility-based)
- Transaction cost-aware rebalancing
- Tax-efficient rebalancing
- Rebalancing frequency optimization
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Tuple
import logging
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class RebalancingFrequency(Enum):
    """Rebalancing frequency options"""
    DAILY = "daily"
    WEEKLY = "weekly" 
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    SEMI_ANNUALLY = "semi_annually"
    ANNUALLY = "annually"
    CUSTOM = "custom"


class RebalancingTrigger(Enum):
    """Rebalancing trigger types"""
    TIME_BASED = "time_based"           # Fixed schedule
    DRIFT_BASED = "drift_based"         # Weight drift threshold
    VOLATILITY_BASED = "volatility_based"  # Volatility regime change
    CORRELATION_BASED = "correlation_based"  # Correlation change
    COMBINED = "combined"               # Multiple criteria


@dataclass
class RebalancingDecision:
    """Rebalancing decision with recommended trades"""
    should_rebalance: bool
    trigger_reason: str
    
    # Current vs target weights
    current_weights: Dict[str, float]
    target_weights: Dict[str, float]
    weight_drifts: Dict[str, float]
    
    # Trade recommendations
    trades: Dict[str, float]  # Positive = buy, negative = sell
    turnover: float          # Total portfolio turnover
    
    # Cost estimates
    estimated_transaction_costs: float
    estimated_tax_impact: Optional[float] = None
    
    # Metrics
    max_drift: float = 0.0
    avg_drift: float = 0.0
    drift_score: float = 0.0  # 0-100
    
    # Timing
    last_rebalance_date: Optional[datetime] = None
    days_since_rebalance: Optional[int] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "should_rebalance": self.should_rebalance,
            "trigger_reason": self.trigger_reason,
            "current_weights": self.current_weights,
            "target_weights": self.target_weights,
            "weight_drifts": self.weight_drifts,
            "trades": self.trades,
            "turnover": self.turnover,
            "estimated_transaction_costs": self.estimated_transaction_costs,
            "estimated_tax_impact": self.estimated_tax_impact,
            "max_drift": self.max_drift,
            "avg_drift": self.avg_drift,
            "drift_score": self.drift_score,
            "last_rebalance_date": self.last_rebalance_date.isoformat() if self.last_rebalance_date else None,
            "days_since_rebalance": self.days_since_rebalance,
        }


@dataclass
class RebalancingConstraints:
    """Constraints for rebalancing"""
    # Drift thresholds
    max_absolute_drift: float = 0.05      # 5% absolute drift
    max_relative_drift: float = 0.20      # 20% relative drift
    
    # Minimum trade sizes
    min_trade_size: float = 0.01          # 1% minimum trade
    min_trade_value: float = 100.0        # $100 minimum trade value
    
    # Transaction costs
    transaction_cost_bps: float = 5.0     # 5 bps transaction cost
    max_transaction_cost_pct: float = 0.5 # Max 0.5% of portfolio in costs
    
    # Tax considerations
    enable_tax_optimization: bool = False
    short_term_tax_rate: float = 0.37     # 37% short-term gains tax
    long_term_tax_rate: float = 0.20      # 20% long-term gains tax
    
    # Timing constraints
    min_days_between_rebalance: int = 7   # Minimum 1 week between rebalances
    
    # No-trade zones (avoid rebalancing around these dates)
    no_trade_periods: List[Tuple[datetime, datetime]] = field(default_factory=list)


class PortfolioRebalancer:
    """
    Portfolio rebalancing engine.
    
    Determines when and how to rebalance portfolios based on:
    - Weight drift from targets
    - Time-based schedules  
    - Market regime changes
    - Transaction cost considerations
    - Tax implications
    """
    
    def __init__(
        self,
        frequency: RebalancingFrequency = RebalancingFrequency.MONTHLY,
        trigger: RebalancingTrigger = RebalancingTrigger.COMBINED,
        constraints: Optional[RebalancingConstraints] = None
    ):
        self.frequency = frequency
        self.trigger = trigger
        self.constraints = constraints or RebalancingConstraints()
        
        # Rebalancing history
        self.rebalance_history: List[RebalancingDecision] = []
    
    def check_rebalancing_needed(
        self,
        current_weights: Dict[str, float],
        target_weights: Dict[str, float],
        current_date: datetime,
        last_rebalance_date: Optional[datetime] = None,
        portfolio_value: float = 100000.0,
        **kwargs
    ) -> RebalancingDecision:
        """
        Check if portfolio rebalancing is needed.
        
        Args:
            current_weights: Current portfolio weights
            target_weights: Target portfolio weights
            current_date: Current date
            last_rebalance_date: Date of last rebalance
            portfolio_value: Total portfolio value
            **kwargs: Additional parameters (volatilities, correlations, etc.)
            
        Returns:
            Rebalancing decision with trade recommendations
        """
        # Calculate weight drifts
        weight_drifts = self._calculate_weight_drifts(current_weights, target_weights)
        
        # Calculate drift metrics
        drift_metrics = self._calculate_drift_metrics(weight_drifts, current_weights)
        
        # Days since last rebalance
        days_since_rebalance = None
        if last_rebalance_date:
            days_since_rebalance = (current_date - last_rebalance_date).days
        
        # Check triggers
        should_rebalance, trigger_reason = self._check_triggers(
            weight_drifts,
            drift_metrics,
            current_date,
            last_rebalance_date,
            **kwargs
        )
        
        # Calculate trades if rebalancing
        if should_rebalance:
            trades = self._calculate_optimal_trades(
                current_weights,
                target_weights,
                portfolio_value,
                weight_drifts
            )
        else:
            trades = {asset: 0.0 for asset in current_weights.keys()}
        
        # Calculate costs
        transaction_costs = self._estimate_transaction_costs(trades, portfolio_value)
        tax_impact = self._estimate_tax_impact(trades, portfolio_value) if self.constraints.enable_tax_optimization else None
        
        # Calculate turnover
        turnover = sum(abs(trade) for trade in trades.values())
        
        decision = RebalancingDecision(
            should_rebalance=should_rebalance,
            trigger_reason=trigger_reason,
            current_weights=current_weights.copy(),
            target_weights=target_weights.copy(),
            weight_drifts=weight_drifts,
            trades=trades,
            turnover=turnover,
            estimated_transaction_costs=transaction_costs,
            estimated_tax_impact=tax_impact,
            max_drift=drift_metrics["max_drift"],
            avg_drift=drift_metrics["avg_drift"],
            drift_score=drift_metrics["drift_score"],
            last_rebalance_date=last_rebalance_date,
            days_since_rebalance=days_since_rebalance,
        )
        
        # Store in history
        if should_rebalance:
            self.rebalance_history.append(decision)
        
        return decision
    
    def _calculate_weight_drifts(
        self,
        current_weights: Dict[str, float],
        target_weights: Dict[str, float]
    ) -> Dict[str, float]:
        """Calculate weight drifts (current - target)"""
        all_assets = set(current_weights.keys()) | set(target_weights.keys())
        
        drifts = {}
        for asset in all_assets:
            current = current_weights.get(asset, 0.0)
            target = target_weights.get(asset, 0.0)
            drifts[asset] = current - target
        
        return drifts
    
    def _calculate_drift_metrics(
        self,
        weight_drifts: Dict[str, float],
        current_weights: Dict[str, float]
    ) -> Dict[str, float]:
        """Calculate drift metrics"""
        absolute_drifts = [abs(drift) for drift in weight_drifts.values()]
        
        max_drift = max(absolute_drifts) if absolute_drifts else 0.0
        avg_drift = np.mean(absolute_drifts) if absolute_drifts else 0.0
        
        # Drift score (0-100): weighted by current portfolio weights
        weighted_drift = 0.0
        total_weight = sum(current_weights.values())
        
        if total_weight > 0:
            for asset, drift in weight_drifts.items():
                weight = current_weights.get(asset, 0.0)
                weighted_drift += abs(drift) * (weight / total_weight)
        
        # Scale to 0-100
        drift_score = min(weighted_drift * 1000, 100.0)  # Scale by 1000, cap at 100
        
        return {
            "max_drift": max_drift,
            "avg_drift": avg_drift,
            "drift_score": drift_score,
        }
    
    def _check_triggers(
        self,
        weight_drifts: Dict[str, float],
        drift_metrics: Dict[str, float],
        current_date: datetime,
        last_rebalance_date: Optional[datetime],
        **kwargs
    ) -> Tuple[bool, str]:
        """Check if any rebalancing triggers are activated"""
        reasons = []
        
        # Check minimum time constraint
        if last_rebalance_date:
            days_since = (current_date - last_rebalance_date).days
            if days_since < self.constraints.min_days_between_rebalance:
                return False, f"Too soon since last rebalance ({days_since} days < {self.constraints.min_days_between_rebalance})"
        
        # Check no-trade periods
        for start_date, end_date in self.constraints.no_trade_periods:
            if start_date <= current_date <= end_date:
                return False, f"No-trade period: {start_date.date()} to {end_date.date()}"
        
        # Time-based trigger
        if self.trigger in [RebalancingTrigger.TIME_BASED, RebalancingTrigger.COMBINED]:
            time_triggered = self._check_time_trigger(current_date, last_rebalance_date)
            if time_triggered:
                reasons.append("scheduled_rebalance")
        
        # Drift-based trigger  
        if self.trigger in [RebalancingTrigger.DRIFT_BASED, RebalancingTrigger.COMBINED]:
            drift_triggered, drift_reason = self._check_drift_trigger(weight_drifts, drift_metrics)
            if drift_triggered:
                reasons.append(drift_reason)
        
        # Volatility-based trigger
        if self.trigger in [RebalancingTrigger.VOLATILITY_BASED, RebalancingTrigger.COMBINED]:
            vol_triggered = self._check_volatility_trigger(**kwargs)
            if vol_triggered:
                reasons.append("volatility_regime_change")
        
        # Correlation-based trigger
        if self.trigger in [RebalancingTrigger.CORRELATION_BASED, RebalancingTrigger.COMBINED]:
            corr_triggered = self._check_correlation_trigger(**kwargs)
            if corr_triggered:
                reasons.append("correlation_change")
        
        # Decision logic
        if self.trigger == RebalancingTrigger.TIME_BASED:
            should_rebalance = "scheduled_rebalance" in reasons
        elif self.trigger == RebalancingTrigger.DRIFT_BASED:
            should_rebalance = any("drift" in reason for reason in reasons)
        elif self.trigger == RebalancingTrigger.COMBINED:
            # Rebalance if any trigger is activated
            should_rebalance = len(reasons) > 0
        else:
            should_rebalance = len(reasons) > 0
        
        trigger_reason = "; ".join(reasons) if reasons else "no_triggers"
        
        return should_rebalance, trigger_reason
    
    def _check_time_trigger(
        self,
        current_date: datetime,
        last_rebalance_date: Optional[datetime]
    ) -> bool:
        """Check time-based rebalancing trigger"""
        if last_rebalance_date is None:
            return True  # First rebalance
        
        days_since = (current_date - last_rebalance_date).days
        
        frequency_days = {
            RebalancingFrequency.DAILY: 1,
            RebalancingFrequency.WEEKLY: 7,
            RebalancingFrequency.MONTHLY: 30,
            RebalancingFrequency.QUARTERLY: 90,
            RebalancingFrequency.SEMI_ANNUALLY: 180,
            RebalancingFrequency.ANNUALLY: 365,
        }
        
        required_days = frequency_days.get(self.frequency, 30)
        return days_since >= required_days
    
    def _check_drift_trigger(
        self,
        weight_drifts: Dict[str, float],
        drift_metrics: Dict[str, float]
    ) -> Tuple[bool, str]:
        """Check drift-based rebalancing trigger"""
        max_drift = drift_metrics["max_drift"]
        
        # Check absolute drift threshold
        if max_drift > self.constraints.max_absolute_drift:
            return True, f"absolute_drift_exceeded_{max_drift:.1%}"
        
        # Check relative drift threshold  
        # TODO: Implement relative drift check
        # (drift relative to target weight)
        
        return False, "no_drift_trigger"
    
    def _check_volatility_trigger(self, **kwargs) -> bool:
        """Check volatility-based rebalancing trigger"""
        current_vol = kwargs.get("current_volatility")
        baseline_vol = kwargs.get("baseline_volatility")
        vol_threshold = kwargs.get("volatility_threshold", 0.5)  # 50% vol change
        
        if current_vol is None or baseline_vol is None:
            return False
        
        vol_change = abs(current_vol - baseline_vol) / baseline_vol
        return vol_change > vol_threshold
    
    def _check_correlation_trigger(self, **kwargs) -> bool:
        """Check correlation-based rebalancing trigger"""
        current_corr = kwargs.get("current_correlation")
        baseline_corr = kwargs.get("baseline_correlation")
        corr_threshold = kwargs.get("correlation_threshold", 0.3)  # 30% corr change
        
        if current_corr is None or baseline_corr is None:
            return False
        
        corr_change = abs(current_corr - baseline_corr)
        return corr_change > corr_threshold
    
    def _calculate_optimal_trades(
        self,
        current_weights: Dict[str, float],
        target_weights: Dict[str, float],
        portfolio_value: float,
        weight_drifts: Dict[str, float]
    ) -> Dict[str, float]:
        """
        Calculate optimal trades considering transaction costs.
        
        Uses a simple threshold-based approach:
        - Only trade if drift exceeds minimum trade size
        - Proportionally reduce trades if total cost is too high
        """
        trades = {}
        
        for asset in set(current_weights.keys()) | set(target_weights.keys()):
            target_weight = target_weights.get(asset, 0.0)
            current_weight = current_weights.get(asset, 0.0)
            drift = weight_drifts.get(asset, 0.0)
            
            # Calculate required trade
            required_trade = target_weight - current_weight
            
            # Apply minimum trade size filter
            trade_value = abs(required_trade) * portfolio_value
            
            if abs(required_trade) < self.constraints.min_trade_size:
                trades[asset] = 0.0
            elif trade_value < self.constraints.min_trade_value:
                trades[asset] = 0.0
            else:
                trades[asset] = required_trade
        
        # Check total transaction cost constraint
        total_turnover = sum(abs(trade) for trade in trades.values())
        total_cost_pct = (total_turnover * self.constraints.transaction_cost_bps) / 10000
        
        if total_cost_pct > self.constraints.max_transaction_cost_pct:
            # Scale down trades proportionally
            scale_factor = self.constraints.max_transaction_cost_pct / total_cost_pct
            trades = {asset: trade * scale_factor for asset, trade in trades.items()}
        
        return trades
    
    def _estimate_transaction_costs(
        self,
        trades: Dict[str, float],
        portfolio_value: float
    ) -> float:
        """Estimate transaction costs in dollar terms"""
        total_turnover = sum(abs(trade) for trade in trades.values())
        cost_rate = self.constraints.transaction_cost_bps / 10000  # Convert bps to decimal
        return total_turnover * portfolio_value * cost_rate
    
    def _estimate_tax_impact(
        self,
        trades: Dict[str, float],
        portfolio_value: float,
        # TODO: Add position tracking for tax calculations
    ) -> Optional[float]:
        """Estimate tax impact of trades"""
        # This is a simplified implementation
        # In practice, would need detailed position tracking with:
        # - Purchase dates and prices (for holding period)
        # - Cost basis tracking  
        # - Tax lot management
        
        if not self.constraints.enable_tax_optimization:
            return None
        
        # Simplified: assume 50% of sales are long-term, 50% short-term
        total_sales = sum(abs(trade) for trade in trades.values() if trade < 0)
        
        if total_sales == 0:
            return 0.0
        
        # Assume 20% average gain on sales
        avg_gain_rate = 0.20
        total_gains = total_sales * portfolio_value * avg_gain_rate
        
        # Split between short-term and long-term
        short_term_gains = total_gains * 0.5
        long_term_gains = total_gains * 0.5
        
        tax_impact = (
            short_term_gains * self.constraints.short_term_tax_rate +
            long_term_gains * self.constraints.long_term_tax_rate
        )
        
        return tax_impact
    
    def optimize_rebalancing_frequency(
        self,
        returns_data: pd.DataFrame,
        target_weights: Dict[str, float],
        frequencies_to_test: Optional[List[RebalancingFrequency]] = None
    ) -> Dict[RebalancingFrequency, Dict[str, float]]:
        """
        Optimize rebalancing frequency based on historical performance.
        
        Tests different frequencies and returns performance metrics.
        """
        if frequencies_to_test is None:
            frequencies_to_test = [
                RebalancingFrequency.WEEKLY,
                RebalancingFrequency.MONTHLY,
                RebalancingFrequency.QUARTERLY
            ]
        
        results = {}
        
        for frequency in frequencies_to_test:
            # Simulate rebalancing with this frequency
            performance = self._simulate_rebalancing_performance(
                returns_data, target_weights, frequency
            )
            results[frequency] = performance
        
        return results
    
    def _simulate_rebalancing_performance(
        self,
        returns_data: pd.DataFrame,
        target_weights: Dict[str, float],
        frequency: RebalancingFrequency
    ) -> Dict[str, float]:
        """Simulate portfolio performance with given rebalancing frequency"""
        # This is a simplified simulation
        # In practice, would need more sophisticated backtesting
        
        # Calculate rebalancing dates
        start_date = returns_data.index[0]
        end_date = returns_data.index[-1]
        
        frequency_days = {
            RebalancingFrequency.WEEKLY: 7,
            RebalancingFrequency.MONTHLY: 30,
            RebalancingFrequency.QUARTERLY: 90,
        }
        
        rebalance_interval = frequency_days.get(frequency, 30)
        
        # Simple simulation metrics
        num_rebalances = len(returns_data) // rebalance_interval
        avg_transaction_costs = num_rebalances * 0.001  # 0.1% per rebalance
        
        # Estimate drift-based metrics (simplified)
        portfolio_returns = returns_data.mean(axis=1)  # Equal weight for simplicity
        portfolio_vol = portfolio_returns.std() * np.sqrt(252)
        portfolio_return = portfolio_returns.mean() * 252
        
        # Adjust for transaction costs
        net_return = portfolio_return - avg_transaction_costs
        
        return {
            "annualized_return": net_return,
            "annualized_volatility": portfolio_vol,
            "sharpe_ratio": net_return / portfolio_vol if portfolio_vol > 0 else 0,
            "num_rebalances": num_rebalances,
            "total_transaction_costs": avg_transaction_costs,
        }