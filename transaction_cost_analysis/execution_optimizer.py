"""
Execution Optimizer

Optimizes trade execution strategies to minimize transaction costs:
- Optimal execution scheduling (Almgren-Chriss framework)
- TWAP/VWAP strategy optimization
- Participation rate optimization
- Market impact minimization
- Cost-aware execution algorithms
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple, Callable
import logging
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from scipy.optimize import minimize, differential_evolution
import math

logger = logging.getLogger(__name__)


class ExecutionStrategy(Enum):
    """Execution strategy types"""
    TWAP = "twap"                    # Time-Weighted Average Price
    VWAP = "vwap"                    # Volume-Weighted Average Price
    IMPLEMENTATION_SHORTFALL = "implementation_shortfall"  # Almgren-Chriss
    PARTICIPATE = "participate"       # Participation rate strategy
    ARRIVAL_PRICE = "arrival_price"   # Immediate execution
    CLOSE = "close"                  # Market-on-close
    ICEBERG = "iceberg"              # Iceberg orders
    ADAPTIVE = "adaptive"            # Adaptive algorithm


@dataclass
class TradingConstraints:
    """Trading constraints and parameters"""
    # Time constraints
    start_time: datetime
    end_time: datetime
    max_execution_time: Optional[int] = None  # Max time in minutes
    
    # Size constraints
    min_order_size: float = 100              # Minimum order size
    max_order_size: Optional[float] = None   # Maximum order size
    max_participation_rate: float = 0.20     # Max 20% of volume
    min_participation_rate: float = 0.01     # Min 1% of volume
    
    # Cost constraints
    max_market_impact_bps: float = 50        # Max 50 bps market impact
    max_total_cost_bps: float = 100          # Max 100 bps total cost
    
    # Risk constraints
    risk_aversion: float = 1e-6              # Risk aversion parameter
    volatility_limit: Optional[float] = None  # Max volatility exposure
    
    # Market constraints
    avoid_market_open: bool = False          # Avoid first 30 minutes
    avoid_market_close: bool = False         # Avoid last 30 minutes
    blackout_periods: List[Tuple[datetime, datetime]] = None


@dataclass
class OptimalSchedule:
    """Optimal execution schedule"""
    strategy: ExecutionStrategy
    total_quantity: float
    
    # Schedule details
    time_schedule: List[datetime]            # Execution times
    quantity_schedule: List[float]           # Quantities at each time
    participation_schedule: List[float]      # Participation rates
    
    # Expected costs
    expected_market_impact: float            # Expected market impact (bps)
    expected_timing_risk: float              # Expected timing risk (bps)
    expected_total_cost: float               # Expected total cost (bps)
    
    # Risk metrics
    execution_risk: float                    # Execution shortfall risk
    cost_variance: float                     # Cost variance
    
    # Performance metrics
    efficiency_score: float                  # 0-100 efficiency score
    
    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "strategy": self.strategy.value,
            "total_quantity": self.total_quantity,
            "time_schedule": [t.isoformat() for t in self.time_schedule],
            "quantity_schedule": self.quantity_schedule,
            "participation_schedule": self.participation_schedule,
            "expected_market_impact": self.expected_market_impact,
            "expected_timing_risk": self.expected_timing_risk,
            "expected_total_cost": self.expected_total_cost,
            "execution_risk": self.execution_risk,
            "cost_variance": self.cost_variance,
            "efficiency_score": self.efficiency_score,
        }


class ScheduleOptimizer:
    """
    Almgren-Chriss optimal execution schedule optimizer.
    
    Minimizes expected transaction costs while managing execution risk
    based on the seminal Almgren-Chriss framework.
    """
    
    def __init__(
        self,
        risk_aversion: float = 1e-6,
        temporary_impact_coef: float = 0.5,
        permanent_impact_coef: float = 0.1,
        volatility: float = 0.3
    ):
        self.risk_aversion = risk_aversion
        self.temporary_impact_coef = temporary_impact_coef  # η
        self.permanent_impact_coef = permanent_impact_coef  # γ  
        self.volatility = volatility  # σ
        
    def optimize_schedule(
        self,
        total_quantity: float,
        execution_horizon: int,  # Number of time intervals
        average_daily_volume: float,
        constraints: TradingConstraints
    ) -> OptimalSchedule:
        """
        Calculate optimal execution schedule using Almgren-Chriss framework.
        
        Args:
            total_quantity: Total shares to execute
            execution_horizon: Number of execution intervals
            average_daily_volume: Average daily volume
            constraints: Trading constraints
            
        Returns:
            Optimal execution schedule
        """
        # Time setup
        T = execution_horizon  # Total time intervals
        dt = 1.0  # Time interval (normalized)
        
        # Market impact parameters (normalized by ADV and volatility)
        eta = self.temporary_impact_coef / (average_daily_volume * self.volatility)
        gamma = self.permanent_impact_coef / (average_daily_volume * self.volatility)
        
        # Risk aversion
        lambda_risk = self.risk_aversion
        
        # Solve optimal trajectory using closed-form solution
        kappa = 2 * lambda_risk * self.volatility**2
        
        if kappa > 0:
            # With risk aversion
            sinh_val = np.sinh(0.5 * np.sqrt(kappa * eta / gamma) * T)
            cosh_val = np.cosh(0.5 * np.sqrt(kappa * eta / gamma) * T)
            
            # Optimal trajectory parameters
            if sinh_val != 0:
                tau = 2 * sinh_val / (T * (cosh_val + np.sqrt(kappa * gamma / eta) * sinh_val))
            else:
                tau = 2 / T  # Linear trajectory fallback
        else:
            # No risk aversion (linear trajectory)
            tau = 2 / T
        
        # Generate optimal schedule
        time_schedule = []
        quantity_schedule = []
        participation_schedule = []
        
        execution_start = constraints.start_time
        execution_end = constraints.end_time
        total_duration = (execution_end - execution_start).total_seconds() / 3600  # Hours
        
        interval_duration = total_duration / execution_horizon
        
        remaining_quantity = total_quantity
        
        for i in range(execution_horizon):
            # Time for this interval
            interval_time = execution_start + timedelta(hours=i * interval_duration)
            time_schedule.append(interval_time)
            
            # Optimal quantity for this interval
            if i < execution_horizon - 1:
                # Use Almgren-Chriss optimal trajectory
                t_normalized = (i + 1) / execution_horizon
                
                if kappa > 0:
                    # Exponential trajectory
                    target_remaining = total_quantity * np.exp(-tau * t_normalized)
                else:
                    # Linear trajectory
                    target_remaining = total_quantity * (1 - t_normalized)
                
                interval_quantity = max(0, remaining_quantity - target_remaining)
            else:
                # Execute all remaining quantity in final interval
                interval_quantity = remaining_quantity
            
            quantity_schedule.append(interval_quantity)
            
            # Calculate participation rate
            # Estimate market volume for this interval (simplified)
            interval_market_volume = average_daily_volume * (interval_duration / 6.5)  # Assuming 6.5 hour trading day
            participation_rate = interval_quantity / interval_market_volume if interval_market_volume > 0 else 0
            
            # Apply participation rate constraints
            participation_rate = min(participation_rate, constraints.max_participation_rate)
            participation_rate = max(participation_rate, constraints.min_participation_rate)
            
            participation_schedule.append(participation_rate)
            
            remaining_quantity -= interval_quantity
            
            if remaining_quantity <= 0:
                break
        
        # Calculate expected costs
        expected_costs = self._calculate_expected_costs(
            quantity_schedule, participation_schedule, average_daily_volume
        )
        
        # Calculate risk metrics
        risk_metrics = self._calculate_risk_metrics(
            quantity_schedule, self.volatility, total_duration
        )
        
        # Calculate efficiency score
        efficiency_score = self._calculate_efficiency_score(
            expected_costs["total_cost"], risk_metrics["execution_risk"]
        )
        
        return OptimalSchedule(
            strategy=ExecutionStrategy.IMPLEMENTATION_SHORTFALL,
            total_quantity=total_quantity,
            time_schedule=time_schedule,
            quantity_schedule=quantity_schedule,
            participation_schedule=participation_schedule,
            expected_market_impact=expected_costs["market_impact"],
            expected_timing_risk=expected_costs["timing_risk"],
            expected_total_cost=expected_costs["total_cost"],
            execution_risk=risk_metrics["execution_risk"],
            cost_variance=risk_metrics["cost_variance"],
            efficiency_score=efficiency_score,
        )
    
    def _calculate_expected_costs(
        self,
        quantity_schedule: List[float],
        participation_schedule: List[float],
        average_daily_volume: float
    ) -> Dict[str, float]:
        """Calculate expected execution costs"""
        # Market impact cost (temporary + permanent)
        market_impact_cost = 0
        for quantity, participation in zip(quantity_schedule, participation_schedule):
            # Temporary impact (reverts)
            temp_impact = self.temporary_impact_coef * participation * self.volatility
            
            # Permanent impact (persists) 
            perm_impact = self.permanent_impact_coef * participation * self.volatility
            
            market_impact_cost += (temp_impact + perm_impact) * quantity
        
        market_impact_bps = market_impact_cost / sum(quantity_schedule) * 10000 if sum(quantity_schedule) > 0 else 0
        
        # Timing risk (price volatility during execution)
        total_execution_time = len(quantity_schedule)  # Intervals
        timing_risk_bps = self.volatility * np.sqrt(total_execution_time) * 10000 * 0.5  # Simplified
        
        total_cost_bps = market_impact_bps + timing_risk_bps
        
        return {
            "market_impact": market_impact_bps,
            "timing_risk": timing_risk_bps,
            "total_cost": total_cost_bps,
        }
    
    def _calculate_risk_metrics(
        self,
        quantity_schedule: List[float],
        volatility: float,
        total_duration: float
    ) -> Dict[str, float]:
        """Calculate execution risk metrics"""
        # Execution shortfall risk (variance)
        total_quantity = sum(quantity_schedule)
        
        if total_quantity == 0:
            return {"execution_risk": 0, "cost_variance": 0}
        
        # Simplified risk calculation
        # Risk increases with execution time and quantity concentration
        execution_intervals = len(quantity_schedule)
        
        # Variance of execution cost
        cost_variance = volatility**2 * total_duration * (total_quantity**2 / execution_intervals)
        
        # Risk measure (standard deviation in bps)
        execution_risk = np.sqrt(cost_variance) * 10000
        
        return {
            "execution_risk": execution_risk,
            "cost_variance": cost_variance,
        }
    
    def _calculate_efficiency_score(
        self,
        expected_cost: float,
        execution_risk: float
    ) -> float:
        """Calculate execution efficiency score (0-100)"""
        base_score = 100
        
        # Penalty for high expected cost
        cost_penalty = min(expected_cost * 0.5, 40)
        
        # Penalty for high execution risk
        risk_penalty = min(execution_risk * 0.3, 30)
        
        efficiency = base_score - cost_penalty - risk_penalty
        
        return max(0, min(100, efficiency))


class ExecutionOptimizer:
    """
    Comprehensive execution optimizer supporting multiple strategies.
    
    Optimizes execution based on different objectives:
    - Minimize market impact
    - Minimize implementation shortfall
    - Track TWAP/VWAP benchmarks
    - Maximize participation
    """
    
    def __init__(self):
        self.schedule_optimizer = ScheduleOptimizer()
        self.strategy_cache = {}
    
    def optimize_execution(
        self,
        symbol: str,
        total_quantity: float,
        side: str,  # "buy" or "sell"
        strategy: ExecutionStrategy,
        market_data: Dict,
        constraints: TradingConstraints,
        **kwargs
    ) -> OptimalSchedule:
        """
        Optimize execution for given strategy and constraints.
        
        Args:
            symbol: Asset symbol
            total_quantity: Total quantity to execute
            side: "buy" or "sell"
            strategy: Execution strategy
            market_data: Market data dict (ADV, volatility, etc.)
            constraints: Trading constraints
            **kwargs: Strategy-specific parameters
            
        Returns:
            Optimal execution schedule
        """
        # Extract market data
        average_daily_volume = market_data.get("average_daily_volume", 1000000)
        volatility = market_data.get("volatility", 0.3)
        current_price = market_data.get("current_price", 100.0)
        
        # Update optimizer parameters
        self.schedule_optimizer.volatility = volatility
        
        # Calculate execution horizon
        execution_duration = (constraints.end_time - constraints.start_time).total_seconds() / 3600
        execution_horizon = max(1, int(execution_duration * 4))  # 15-minute intervals
        
        if strategy == ExecutionStrategy.IMPLEMENTATION_SHORTFALL:
            return self._optimize_implementation_shortfall(
                total_quantity, execution_horizon, average_daily_volume, constraints
            )
        elif strategy == ExecutionStrategy.TWAP:
            return self._optimize_twap_strategy(
                total_quantity, execution_horizon, constraints, market_data
            )
        elif strategy == ExecutionStrategy.VWAP:
            return self._optimize_vwap_strategy(
                total_quantity, execution_horizon, constraints, market_data
            )
        elif strategy == ExecutionStrategy.PARTICIPATE:
            target_participation = kwargs.get("target_participation_rate", 0.10)
            return self._optimize_participation_strategy(
                total_quantity, execution_horizon, constraints, market_data, target_participation
            )
        else:
            # Default to implementation shortfall
            return self._optimize_implementation_shortfall(
                total_quantity, execution_horizon, average_daily_volume, constraints
            )
    
    def _optimize_implementation_shortfall(
        self,
        total_quantity: float,
        execution_horizon: int,
        average_daily_volume: float,
        constraints: TradingConstraints
    ) -> OptimalSchedule:
        """Optimize using Almgren-Chriss implementation shortfall framework"""
        return self.schedule_optimizer.optimize_schedule(
            total_quantity, execution_horizon, average_daily_volume, constraints
        )
    
    def _optimize_twap_strategy(
        self,
        total_quantity: float,
        execution_horizon: int,
        constraints: TradingConstraints,
        market_data: Dict
    ) -> OptimalSchedule:
        """Optimize for TWAP execution (equal time intervals)"""
        # TWAP: equal quantities over equal time intervals
        quantity_per_interval = total_quantity / execution_horizon
        
        time_schedule = []
        quantity_schedule = []
        participation_schedule = []
        
        execution_start = constraints.start_time
        execution_end = constraints.end_time
        total_duration = (execution_end - execution_start).total_seconds() / 3600
        
        interval_duration = total_duration / execution_horizon
        average_daily_volume = market_data.get("average_daily_volume", 1000000)
        
        for i in range(execution_horizon):
            # Time for this interval
            interval_time = execution_start + timedelta(hours=i * interval_duration)
            time_schedule.append(interval_time)
            
            # Equal quantity distribution
            quantity_schedule.append(quantity_per_interval)
            
            # Calculate participation rate
            interval_market_volume = average_daily_volume * (interval_duration / 6.5)
            participation_rate = quantity_per_interval / interval_market_volume if interval_market_volume > 0 else 0
            
            # Apply constraints
            participation_rate = min(participation_rate, constraints.max_participation_rate)
            participation_schedule.append(participation_rate)
        
        # Calculate costs (simplified for TWAP)
        expected_costs = self.schedule_optimizer._calculate_expected_costs(
            quantity_schedule, participation_schedule, average_daily_volume
        )
        
        risk_metrics = self.schedule_optimizer._calculate_risk_metrics(
            quantity_schedule, market_data.get("volatility", 0.3), total_duration
        )
        
        efficiency_score = 75.0  # Fixed TWAP efficiency (reasonable but not optimal)
        
        return OptimalSchedule(
            strategy=ExecutionStrategy.TWAP,
            total_quantity=total_quantity,
            time_schedule=time_schedule,
            quantity_schedule=quantity_schedule,
            participation_schedule=participation_schedule,
            expected_market_impact=expected_costs["market_impact"],
            expected_timing_risk=expected_costs["timing_risk"],
            expected_total_cost=expected_costs["total_cost"],
            execution_risk=risk_metrics["execution_risk"],
            cost_variance=risk_metrics["cost_variance"],
            efficiency_score=efficiency_score,
        )
    
    def _optimize_vwap_strategy(
        self,
        total_quantity: float,
        execution_horizon: int,
        constraints: TradingConstraints,
        market_data: Dict
    ) -> OptimalSchedule:
        """Optimize for VWAP execution (volume-weighted intervals)"""
        # VWAP: quantities proportional to expected volume
        
        # Get historical volume pattern (simplified - use flat distribution)
        volume_pattern = market_data.get("volume_pattern", [1.0] * execution_horizon)
        
        # Normalize volume pattern
        total_volume_weight = sum(volume_pattern)
        volume_weights = [v / total_volume_weight for v in volume_pattern]
        
        time_schedule = []
        quantity_schedule = []
        participation_schedule = []
        
        execution_start = constraints.start_time
        execution_end = constraints.end_time
        total_duration = (execution_end - execution_start).total_seconds() / 3600
        
        interval_duration = total_duration / execution_horizon
        average_daily_volume = market_data.get("average_daily_volume", 1000000)
        
        for i in range(execution_horizon):
            # Time for this interval
            interval_time = execution_start + timedelta(hours=i * interval_duration)
            time_schedule.append(interval_time)
            
            # Volume-weighted quantity distribution
            interval_quantity = total_quantity * volume_weights[i]
            quantity_schedule.append(interval_quantity)
            
            # Calculate participation rate
            interval_market_volume = average_daily_volume * (interval_duration / 6.5) * volume_weights[i]
            participation_rate = interval_quantity / interval_market_volume if interval_market_volume > 0 else 0
            
            # Apply constraints
            participation_rate = min(participation_rate, constraints.max_participation_rate)
            participation_schedule.append(participation_rate)
        
        # Calculate costs
        expected_costs = self.schedule_optimizer._calculate_expected_costs(
            quantity_schedule, participation_schedule, average_daily_volume
        )
        
        risk_metrics = self.schedule_optimizer._calculate_risk_metrics(
            quantity_schedule, market_data.get("volatility", 0.3), total_duration
        )
        
        efficiency_score = 80.0  # VWAP typically more efficient than TWAP
        
        return OptimalSchedule(
            strategy=ExecutionStrategy.VWAP,
            total_quantity=total_quantity,
            time_schedule=time_schedule,
            quantity_schedule=quantity_schedule,
            participation_schedule=participation_schedule,
            expected_market_impact=expected_costs["market_impact"],
            expected_timing_risk=expected_costs["timing_risk"],
            expected_total_cost=expected_costs["total_cost"],
            execution_risk=risk_metrics["execution_risk"],
            cost_variance=risk_metrics["cost_variance"],
            efficiency_score=efficiency_score,
        )
    
    def _optimize_participation_strategy(
        self,
        total_quantity: float,
        execution_horizon: int,
        constraints: TradingConstraints,
        market_data: Dict,
        target_participation_rate: float
    ) -> OptimalSchedule:
        """Optimize for constant participation rate strategy"""
        
        time_schedule = []
        quantity_schedule = []
        participation_schedule = []
        
        execution_start = constraints.start_time
        execution_end = constraints.end_time
        total_duration = (execution_end - execution_start).total_seconds() / 3600
        
        interval_duration = total_duration / execution_horizon
        average_daily_volume = market_data.get("average_daily_volume", 1000000)
        
        remaining_quantity = total_quantity
        
        for i in range(execution_horizon):
            # Time for this interval
            interval_time = execution_start + timedelta(hours=i * interval_duration)
            time_schedule.append(interval_time)
            
            # Calculate quantity based on participation rate
            interval_market_volume = average_daily_volume * (interval_duration / 6.5)
            target_quantity = interval_market_volume * target_participation_rate
            
            # Don't exceed remaining quantity
            interval_quantity = min(target_quantity, remaining_quantity)
            quantity_schedule.append(interval_quantity)
            
            # Actual participation rate
            actual_participation = interval_quantity / interval_market_volume if interval_market_volume > 0 else 0
            participation_schedule.append(actual_participation)
            
            remaining_quantity -= interval_quantity
            
            if remaining_quantity <= 0:
                break
        
        # Calculate costs
        expected_costs = self.schedule_optimizer._calculate_expected_costs(
            quantity_schedule, participation_schedule, average_daily_volume
        )
        
        risk_metrics = self.schedule_optimizer._calculate_risk_metrics(
            quantity_schedule, market_data.get("volatility", 0.3), total_duration
        )
        
        # Efficiency depends on participation rate
        participation_penalty = abs(target_participation_rate - 0.1) * 100  # Optimal around 10%
        efficiency_score = max(50, 90 - participation_penalty)
        
        return OptimalSchedule(
            strategy=ExecutionStrategy.PARTICIPATE,
            total_quantity=total_quantity,
            time_schedule=time_schedule,
            quantity_schedule=quantity_schedule,
            participation_schedule=participation_schedule,
            expected_market_impact=expected_costs["market_impact"],
            expected_timing_risk=expected_costs["timing_risk"],
            expected_total_cost=expected_costs["total_cost"],
            execution_risk=risk_metrics["execution_risk"],
            cost_variance=risk_metrics["cost_variance"],
            efficiency_score=efficiency_score,
        )
    
    def compare_strategies(
        self,
        symbol: str,
        total_quantity: float,
        side: str,
        market_data: Dict,
        constraints: TradingConstraints,
        strategies: List[ExecutionStrategy] = None
    ) -> Dict[str, OptimalSchedule]:
        """
        Compare multiple execution strategies and return results.
        
        Args:
            symbol: Asset symbol
            total_quantity: Total quantity to execute
            side: "buy" or "sell" 
            market_data: Market data dict
            constraints: Trading constraints
            strategies: List of strategies to compare (default: all)
            
        Returns:
            Dictionary mapping strategy names to optimal schedules
        """
        if strategies is None:
            strategies = [
                ExecutionStrategy.IMPLEMENTATION_SHORTFALL,
                ExecutionStrategy.TWAP,
                ExecutionStrategy.VWAP,
                ExecutionStrategy.PARTICIPATE
            ]
        
        results = {}
        
        for strategy in strategies:
            try:
                optimal_schedule = self.optimize_execution(
                    symbol=symbol,
                    total_quantity=total_quantity,
                    side=side,
                    strategy=strategy,
                    market_data=market_data,
                    constraints=constraints
                )
                
                results[strategy.value] = optimal_schedule
                
            except Exception as e:
                logger.error(f"Error optimizing {strategy.value} strategy: {str(e)}")
                continue
        
        return results
    
    def recommend_strategy(
        self,
        symbol: str,
        total_quantity: float,
        side: str,
        market_data: Dict,
        constraints: TradingConstraints,
        objective: str = "minimize_cost"  # "minimize_cost", "minimize_risk", "track_benchmark"
    ) -> Tuple[ExecutionStrategy, OptimalSchedule]:
        """
        Recommend best execution strategy based on objective.
        
        Args:
            symbol: Asset symbol
            total_quantity: Total quantity
            side: "buy" or "sell"
            market_data: Market data
            constraints: Trading constraints
            objective: Optimization objective
            
        Returns:
            Tuple of (recommended_strategy, optimal_schedule)
        """
        # Compare all strategies
        strategy_results = self.compare_strategies(
            symbol, total_quantity, side, market_data, constraints
        )
        
        if not strategy_results:
            raise ValueError("No valid execution strategies found")
        
        # Select best strategy based on objective
        if objective == "minimize_cost":
            best_strategy = min(
                strategy_results.items(),
                key=lambda x: x[1].expected_total_cost
            )
        elif objective == "minimize_risk":
            best_strategy = min(
                strategy_results.items(),
                key=lambda x: x[1].execution_risk
            )
        elif objective == "track_benchmark":
            # Prefer TWAP/VWAP for benchmark tracking
            twap_result = strategy_results.get("twap")
            vwap_result = strategy_results.get("vwap")
            
            if twap_result and vwap_result:
                if twap_result.efficiency_score >= vwap_result.efficiency_score:
                    best_strategy = ("twap", twap_result)
                else:
                    best_strategy = ("vwap", vwap_result)
            elif twap_result:
                best_strategy = ("twap", twap_result)
            elif vwap_result:
                best_strategy = ("vwap", vwap_result)
            else:
                # Fallback to best overall
                best_strategy = max(
                    strategy_results.items(),
                    key=lambda x: x[1].efficiency_score
                )
        else:
            # Default: maximize efficiency score
            best_strategy = max(
                strategy_results.items(),
                key=lambda x: x[1].efficiency_score
            )
        
        strategy_name = best_strategy[0]
        optimal_schedule = best_strategy[1]
        
        # Convert string back to enum
        strategy_enum = ExecutionStrategy(strategy_name)
        
        return strategy_enum, optimal_schedule