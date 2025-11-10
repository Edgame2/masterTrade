"""
Online Learning for Parameter Optimization

Continuously adapts strategy parameters based on recent performance:
- Gradient-based parameter updates
- Bayesian optimization
- Adaptive learning rates
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Callable, Any
import numpy as np
import logging

logger = logging.getLogger(__name__)


class UpdateRule(Enum):
    """Parameter update rules"""
    GRADIENT_DESCENT = "gradient_descent"
    ADAM = "adam"  # Adaptive Moment Estimation
    BAYESIAN = "bayesian"
    BANDIT = "bandit"  # Multi-armed bandit


@dataclass
class AdaptiveParameter:
    """
    A strategy parameter that adapts based on performance.
    
    Examples:
    - RSI threshold: adapts to market volatility
    - Stop loss percentage: adapts to recent drawdowns
    - Position size: adapts to win rate
    """
    name: str
    current_value: float
    min_value: float
    max_value: float
    
    # Learning configuration
    learning_rate: float = 0.01
    update_rule: UpdateRule = UpdateRule.GRADIENT_DESCENT
    
    # History
    value_history: List[float] = field(default_factory=list)
    performance_history: List[float] = field(default_factory=list)
    
    # ADAM parameters (if using ADAM)
    m: float = 0  # First moment
    v: float = 0  # Second moment
    t: int = 0    # Time step
    beta1: float = 0.9
    beta2: float = 0.999
    epsilon: float = 1e-8
    
    # Bayesian parameters
    prior_mean: Optional[float] = None
    prior_std: Optional[float] = None
    
    def __post_init__(self):
        if self.prior_mean is None:
            self.prior_mean = self.current_value
        if self.prior_std is None:
            self.prior_std = (self.max_value - self.min_value) / 6
    
    def update(self, performance: float, gradient: Optional[float] = None):
        """
        Update parameter value based on performance.
        
        Args:
            performance: Performance metric (e.g., Sharpe ratio, profit)
            gradient: Optional explicit gradient (∂performance/∂parameter)
        """
        self.value_history.append(self.current_value)
        self.performance_history.append(performance)
        
        if self.update_rule == UpdateRule.GRADIENT_DESCENT:
            self._update_gradient_descent(performance, gradient)
        elif self.update_rule == UpdateRule.ADAM:
            self._update_adam(performance, gradient)
        elif self.update_rule == UpdateRule.BAYESIAN:
            self._update_bayesian(performance)
        elif self.update_rule == UpdateRule.BANDIT:
            self._update_bandit(performance)
        
        # Clip to bounds
        self.current_value = np.clip(self.current_value, self.min_value, self.max_value)
        
        logger.debug(f"Updated {self.name}: {self.value_history[-1]:.4f} -> {self.current_value:.4f} (perf: {performance:.4f})")
    
    def _update_gradient_descent(self, performance: float, gradient: Optional[float]):
        """Standard gradient descent update"""
        if gradient is None:
            # Estimate gradient using finite differences
            if len(self.value_history) >= 2 and len(self.performance_history) >= 2:
                delta_perf = self.performance_history[-1] - self.performance_history[-2]
                delta_param = self.value_history[-1] - self.value_history[-2]
                gradient = delta_perf / delta_param if delta_param != 0 else 0
            else:
                gradient = 0
        
        # Update: param = param + learning_rate * gradient
        self.current_value += self.learning_rate * gradient
    
    def _update_adam(self, performance: float, gradient: Optional[float]):
        """ADAM optimizer update"""
        if gradient is None:
            # Estimate gradient
            if len(self.value_history) >= 2 and len(self.performance_history) >= 2:
                delta_perf = self.performance_history[-1] - self.performance_history[-2]
                delta_param = self.value_history[-1] - self.value_history[-2]
                gradient = delta_perf / delta_param if delta_param != 0 else 0
            else:
                gradient = 0
        
        self.t += 1
        
        # Update biased first moment estimate
        self.m = self.beta1 * self.m + (1 - self.beta1) * gradient
        
        # Update biased second moment estimate
        self.v = self.beta2 * self.v + (1 - self.beta2) * (gradient ** 2)
        
        # Compute bias-corrected estimates
        m_hat = self.m / (1 - self.beta1 ** self.t)
        v_hat = self.v / (1 - self.beta2 ** self.t)
        
        # Update parameter
        self.current_value += self.learning_rate * m_hat / (np.sqrt(v_hat) + self.epsilon)
    
    def _update_bayesian(self, performance: float):
        """Bayesian optimization update"""
        # Simple Bayesian update: update posterior based on observed performance
        # Higher performance -> move toward current value
        # Lower performance -> move toward prior
        
        if len(self.performance_history) < 2:
            return
        
        # Normalize performance to [0, 1]
        perf_min = min(self.performance_history)
        perf_max = max(self.performance_history)
        normalized_perf = (performance - perf_min) / (perf_max - perf_min) if perf_max > perf_min else 0.5
        
        # Weight between prior and current value
        weight_current = normalized_perf
        weight_prior = 1 - normalized_perf
        
        new_value = weight_current * self.current_value + weight_prior * self.prior_mean
        
        # Move slowly toward new value
        self.current_value += self.learning_rate * (new_value - self.current_value)
    
    def _update_bandit(self, performance: float):
        """Multi-armed bandit approach: epsilon-greedy exploration"""
        epsilon = 0.1  # Exploration rate
        
        if np.random.random() < epsilon:
            # Explore: random value
            self.current_value = np.random.uniform(self.min_value, self.max_value)
        else:
            # Exploit: move toward best historical value
            if len(self.value_history) >= 2:
                best_idx = np.argmax(self.performance_history)
                best_value = self.value_history[best_idx]
                
                # Move toward best value
                self.current_value += self.learning_rate * (best_value - self.current_value)
    
    def get_statistics(self) -> Dict[str, float]:
        """Get parameter statistics"""
        if not self.value_history:
            return {}
        
        return {
            "current_value": self.current_value,
            "mean_value": np.mean(self.value_history),
            "std_value": np.std(self.value_history),
            "min_value": np.min(self.value_history),
            "max_value": np.max(self.value_history),
            "mean_performance": np.mean(self.performance_history) if self.performance_history else 0,
            "updates": len(self.value_history),
        }


class ParameterOptimizer:
    """
    Manages multiple adaptive parameters for a strategy.
    
    Coordinates parameter updates based on overall strategy performance.
    """
    
    def __init__(self, strategy_id: str):
        self.strategy_id = strategy_id
        self.parameters: Dict[str, AdaptiveParameter] = {}
        self.update_count = 0
        
        logger.info(f"ParameterOptimizer initialized for strategy: {strategy_id}")
    
    def add_parameter(
        self,
        name: str,
        initial_value: float,
        min_value: float,
        max_value: float,
        learning_rate: float = 0.01,
        update_rule: UpdateRule = UpdateRule.ADAM,
    ):
        """Add a parameter to optimize"""
        param = AdaptiveParameter(
            name=name,
            current_value=initial_value,
            min_value=min_value,
            max_value=max_value,
            learning_rate=learning_rate,
            update_rule=update_rule,
        )
        
        self.parameters[name] = param
        logger.info(f"Added parameter: {name} = {initial_value} [{min_value}, {max_value}]")
    
    def update_parameters(self, performance_metrics: Dict[str, float]):
        """
        Update all parameters based on performance.
        
        Args:
            performance_metrics: Dict of performance metrics (e.g., {"sharpe": 1.5, "profit": 1000})
        """
        # Use primary metric (e.g., Sharpe ratio)
        primary_metric = performance_metrics.get("sharpe_ratio") or performance_metrics.get("profit", 0)
        
        # Update each parameter
        for param in self.parameters.values():
            param.update(performance=primary_metric)
        
        self.update_count += 1
        
        if self.update_count % 10 == 0:
            logger.info(f"Parameter update #{self.update_count} for {self.strategy_id}")
            for name, param in self.parameters.items():
                logger.info(f"  {name}: {param.current_value:.4f}")
    
    def get_parameters(self) -> Dict[str, float]:
        """Get current parameter values"""
        return {name: param.current_value for name, param in self.parameters.items()}
    
    def get_parameter_statistics(self) -> Dict[str, Dict[str, float]]:
        """Get statistics for all parameters"""
        return {name: param.get_statistics() for name, param in self.parameters.items()}
    
    def reset_parameter(self, name: str, value: Optional[float] = None):
        """Reset a parameter to initial or specific value"""
        if name in self.parameters:
            param = self.parameters[name]
            if value is not None:
                param.current_value = np.clip(value, param.min_value, param.max_value)
            else:
                param.current_value = param.prior_mean
            
            logger.info(f"Reset parameter {name} to {param.current_value:.4f}")


class OnlineLearner:
    """
    Online learning system for strategy adaptation.
    
    Continuously learns from live trading results to improve strategy parameters.
    """
    
    def __init__(self, strategy_id: str, update_frequency: int = 10):
        """
        Args:
            strategy_id: Strategy identifier
            update_frequency: Update parameters every N trades
        """
        self.strategy_id = strategy_id
        self.update_frequency = update_frequency
        
        self.optimizer = ParameterOptimizer(strategy_id)
        
        # Performance tracking
        self.trade_count = 0
        self.recent_trades: List[Dict[str, Any]] = []
        self.performance_window = 50  # Calculate performance over last N trades
        
        logger.info(f"OnlineLearner initialized for {strategy_id}")
    
    def add_parameter(
        self,
        name: str,
        initial_value: float,
        min_value: float,
        max_value: float,
        learning_rate: float = 0.01,
        update_rule: UpdateRule = UpdateRule.ADAM,
    ):
        """Add parameter to learn"""
        self.optimizer.add_parameter(
            name=name,
            initial_value=initial_value,
            min_value=min_value,
            max_value=max_value,
            learning_rate=learning_rate,
            update_rule=update_rule,
        )
    
    def record_trade(self, trade_result: Dict[str, Any]):
        """
        Record a trade result.
        
        Args:
            trade_result: Dict with trade details (pnl, return, duration, etc.)
        """
        self.recent_trades.append(trade_result)
        self.trade_count += 1
        
        # Keep only recent trades
        if len(self.recent_trades) > self.performance_window:
            self.recent_trades = self.recent_trades[-self.performance_window:]
        
        # Update parameters periodically
        if self.trade_count % self.update_frequency == 0:
            self._update_parameters()
    
    def _update_parameters(self):
        """Update parameters based on recent performance"""
        if not self.recent_trades:
            return
        
        # Calculate performance metrics
        returns = [t.get("return", 0) for t in self.recent_trades]
        pnls = [t.get("pnl", 0) for t in self.recent_trades]
        
        win_rate = sum(1 for r in returns if r > 0) / len(returns)
        avg_return = np.mean(returns)
        sharpe_ratio = np.mean(returns) / np.std(returns) if np.std(returns) > 0 else 0
        total_pnl = sum(pnls)
        
        performance_metrics = {
            "win_rate": win_rate,
            "avg_return": avg_return,
            "sharpe_ratio": sharpe_ratio,
            "total_pnl": total_pnl,
        }
        
        # Update parameters
        self.optimizer.update_parameters(performance_metrics)
        
        logger.info(f"Updated parameters for {self.strategy_id} after {self.trade_count} trades")
        logger.info(f"  Performance: Sharpe={sharpe_ratio:.2f}, WinRate={win_rate:.2%}, AvgReturn={avg_return:.4f}")
    
    def get_current_parameters(self) -> Dict[str, float]:
        """Get current parameter values"""
        return self.optimizer.get_parameters()
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get learning statistics"""
        return {
            "strategy_id": self.strategy_id,
            "trade_count": self.trade_count,
            "update_count": self.optimizer.update_count,
            "parameters": self.optimizer.get_parameter_statistics(),
        }
