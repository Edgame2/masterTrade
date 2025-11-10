"""
Strategy Ensemble Manager

Manages multiple strategies with intelligent weighting:
- Performance-based weighting
- Sharpe ratio weighting
- Adaptive weighting based on market regime
- Risk-adjusted allocation
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional
import numpy as np
import logging

logger = logging.getLogger(__name__)


class EnsembleWeightingMethod(Enum):
    """Methods for weighting strategies in ensemble"""
    EQUAL = "equal"                      # Equal weight
    PERFORMANCE = "performance"          # Based on recent returns
    SHARPE = "sharpe"                    # Based on Sharpe ratio
    INVERSE_VARIANCE = "inverse_variance"  # Lower variance = higher weight
    ADAPTIVE = "adaptive"                # Adapt to market regime
    MOMENTUM = "momentum"                # Recent winners get more weight
    MEAN_REVERSION = "mean_reversion"    # Recent losers get more weight


@dataclass
class StrategyWeight:
    """Weight allocation for a strategy"""
    strategy_id: str
    weight: float  # 0-1
    
    # Performance metrics
    recent_return: float = 0.0
    sharpe_ratio: float = 0.0
    volatility: float = 0.0
    win_rate: float = 0.0
    
    # Historical weights
    weight_history: List[float] = field(default_factory=list)
    
    last_updated: datetime = field(default_factory=datetime.utcnow)
    
    def update_weight(self, new_weight: float):
        """Update weight with bounds checking"""
        self.weight_history.append(self.weight)
        self.weight = np.clip(new_weight, 0.0, 1.0)
        self.last_updated = datetime.utcnow()


class PerformanceBasedWeighting:
    """Weight strategies based on recent performance"""
    
    def __init__(self, lookback_window: int = 20):
        self.lookback_window = lookback_window
    
    def calculate_weights(self, strategy_performances: Dict[str, List[float]]) -> Dict[str, float]:
        """
        Calculate weights based on recent returns.
        
        Args:
            strategy_performances: {strategy_id: [recent returns]}
            
        Returns:
            {strategy_id: weight}
        """
        if not strategy_performances:
            return {}
        
        # Calculate cumulative returns
        cumulative_returns = {}
        for strategy_id, returns in strategy_performances.items():
            recent_returns = returns[-self.lookback_window:]
            cum_return = np.prod([1 + r for r in recent_returns]) - 1
            cumulative_returns[strategy_id] = max(0, cum_return)  # No negative weights
        
        # Normalize to sum to 1
        total = sum(cumulative_returns.values())
        if total == 0:
            # Equal weights if all negative
            n = len(strategy_performances)
            return {s: 1/n for s in strategy_performances.keys()}
        
        weights = {s: v/total for s, v in cumulative_returns.items()}
        
        logger.debug(f"Performance-based weights: {weights}")
        return weights


class SharpeWeighting:
    """Weight strategies based on Sharpe ratio"""
    
    def __init__(self, lookback_window: int = 50, min_sharpe: float = 0.0):
        self.lookback_window = lookback_window
        self.min_sharpe = min_sharpe
    
    def calculate_weights(self, strategy_performances: Dict[str, List[float]]) -> Dict[str, float]:
        """
        Calculate weights based on Sharpe ratios.
        
        Args:
            strategy_performances: {strategy_id: [recent returns]}
            
        Returns:
            {strategy_id: weight}
        """
        if not strategy_performances:
            return {}
        
        # Calculate Sharpe ratios
        sharpe_ratios = {}
        for strategy_id, returns in strategy_performances.items():
            recent_returns = returns[-self.lookback_window:]
            if len(recent_returns) < 2:
                sharpe_ratios[strategy_id] = 0
                continue
            
            mean_return = np.mean(recent_returns)
            std_return = np.std(recent_returns)
            
            if std_return > 0:
                sharpe = mean_return / std_return * np.sqrt(252)  # Annualized
            else:
                sharpe = 0
            
            # Apply minimum threshold
            sharpe_ratios[strategy_id] = max(0, sharpe - self.min_sharpe)
        
        # Normalize
        total = sum(sharpe_ratios.values())
        if total == 0:
            n = len(strategy_performances)
            return {s: 1/n for s in strategy_performances.keys()}
        
        weights = {s: v/total for s, v in sharpe_ratios.items()}
        
        logger.debug(f"Sharpe-based weights: {weights}")
        return weights


class AdaptiveWeighting:
    """
    Adaptive weighting based on market regime.
    
    Adjusts strategy weights based on detected market conditions.
    """
    
    def __init__(self):
        # Strategy preferences by regime
        self.regime_preferences = {
            "bull": {},      # Trend-following gets more weight
            "bear": {},      # Short strategies get more weight
            "sideways": {},  # Mean-reversion gets more weight
            "high_vol": {},  # Lower volatility strategies
        }
    
    def set_regime_preference(self, regime: str, strategy_id: str, preference: float):
        """
        Set strategy preference for a regime.
        
        Args:
            regime: Market regime
            strategy_id: Strategy ID
            preference: Preference score (higher = more preferred)
        """
        if regime not in self.regime_preferences:
            self.regime_preferences[regime] = {}
        
        self.regime_preferences[regime][strategy_id] = preference
    
    def calculate_weights(
        self,
        strategy_performances: Dict[str, List[float]],
        current_regime: str,
        regime_confidence: float = 1.0,
    ) -> Dict[str, float]:
        """
        Calculate adaptive weights based on regime.
        
        Args:
            strategy_performances: {strategy_id: [returns]}
            current_regime: Current market regime
            regime_confidence: Confidence in regime detection (0-1)
            
        Returns:
            {strategy_id: weight}
        """
        # Get regime preferences
        preferences = self.regime_preferences.get(current_regime, {})
        
        if not preferences:
            # No preferences set, use equal weights
            n = len(strategy_performances)
            return {s: 1/n for s in strategy_performances.keys()}
        
        # Calculate base weights from performance
        perf_weighter = PerformanceBasedWeighting()
        perf_weights = perf_weighter.calculate_weights(strategy_performances)
        
        # Blend performance weights with regime preferences
        adaptive_weights = {}
        for strategy_id in strategy_performances.keys():
            perf_weight = perf_weights.get(strategy_id, 1/len(strategy_performances))
            pref_weight = preferences.get(strategy_id, 1.0)
            
            # Weighted blend based on regime confidence
            blended = regime_confidence * pref_weight + (1 - regime_confidence) * perf_weight
            adaptive_weights[strategy_id] = blended
        
        # Normalize
        total = sum(adaptive_weights.values())
        if total > 0:
            adaptive_weights = {s: w/total for s, w in adaptive_weights.items()}
        
        logger.debug(f"Adaptive weights for {current_regime}: {adaptive_weights}")
        return adaptive_weights


class EnsembleManager:
    """
    Manages strategy ensemble with dynamic weighting.
    
    Features:
    - Multiple weighting methods
    - Automatic rebalancing
    - Risk-adjusted allocation
    - Performance tracking
    """
    
    def __init__(
        self,
        weighting_method: EnsembleWeightingMethod = EnsembleWeightingMethod.SHARPE,
        rebalance_frequency: int = 10,  # Rebalance every N trades
        min_weight: float = 0.05,       # Minimum weight per strategy
        max_weight: float = 0.5,        # Maximum weight per strategy
    ):
        self.weighting_method = weighting_method
        self.rebalance_frequency = rebalance_frequency
        self.min_weight = min_weight
        self.max_weight = max_weight
        
        # Strategy weights
        self.strategy_weights: Dict[str, StrategyWeight] = {}
        
        # Performance tracking
        self.strategy_performances: Dict[str, List[float]] = {}
        
        # Weighting calculators
        self.performance_weighter = PerformanceBasedWeighting()
        self.sharpe_weighter = SharpeWeighting()
        self.adaptive_weighter = AdaptiveWeighting()
        
        self.trade_count = 0
        self.last_rebalance = datetime.utcnow()
        
        logger.info(f"EnsembleManager initialized with {weighting_method.value} weighting")
    
    def add_strategy(self, strategy_id: str, initial_weight: Optional[float] = None):
        """Add strategy to ensemble"""
        if initial_weight is None:
            # Equal weight
            n = len(self.strategy_weights) + 1
            initial_weight = 1.0 / n
            
            # Rebalance existing strategies
            for weight_obj in self.strategy_weights.values():
                weight_obj.update_weight(1.0 / n)
        
        weight_obj = StrategyWeight(
            strategy_id=strategy_id,
            weight=initial_weight,
        )
        
        self.strategy_weights[strategy_id] = weight_obj
        self.strategy_performances[strategy_id] = []
        
        logger.info(f"Added strategy {strategy_id} with weight {initial_weight:.4f}")
    
    def remove_strategy(self, strategy_id: str):
        """Remove strategy from ensemble"""
        if strategy_id in self.strategy_weights:
            del self.strategy_weights[strategy_id]
            del self.strategy_performances[strategy_id]
            
            # Rebalance remaining strategies
            self.rebalance()
            
            logger.info(f"Removed strategy {strategy_id}")
    
    def record_performance(self, strategy_id: str, return_value: float):
        """Record strategy performance"""
        if strategy_id not in self.strategy_performances:
            return
        
        self.strategy_performances[strategy_id].append(return_value)
        self.trade_count += 1
        
        # Update strategy metrics
        if strategy_id in self.strategy_weights:
            weight_obj = self.strategy_weights[strategy_id]
            recent_returns = self.strategy_performances[strategy_id][-20:]
            
            weight_obj.recent_return = np.mean(recent_returns)
            if len(recent_returns) > 1:
                weight_obj.sharpe_ratio = np.mean(recent_returns) / np.std(recent_returns) * np.sqrt(252)
                weight_obj.volatility = np.std(recent_returns)
            
            weight_obj.win_rate = sum(1 for r in recent_returns if r > 0) / len(recent_returns)
        
        # Periodic rebalancing
        if self.trade_count % self.rebalance_frequency == 0:
            self.rebalance()
    
    def rebalance(self, current_regime: Optional[str] = None, regime_confidence: float = 1.0):
        """
        Rebalance strategy weights.
        
        Args:
            current_regime: Current market regime (for adaptive weighting)
            regime_confidence: Confidence in regime detection
        """
        if not self.strategy_weights:
            return
        
        # Calculate new weights based on method
        if self.weighting_method == EnsembleWeightingMethod.EQUAL:
            n = len(self.strategy_weights)
            new_weights = {s: 1/n for s in self.strategy_weights.keys()}
        
        elif self.weighting_method == EnsembleWeightingMethod.PERFORMANCE:
            new_weights = self.performance_weighter.calculate_weights(self.strategy_performances)
        
        elif self.weighting_method == EnsembleWeightingMethod.SHARPE:
            new_weights = self.sharpe_weighter.calculate_weights(self.strategy_performances)
        
        elif self.weighting_method == EnsembleWeightingMethod.INVERSE_VARIANCE:
            new_weights = self._calculate_inverse_variance_weights()
        
        elif self.weighting_method == EnsembleWeightingMethod.ADAPTIVE:
            if current_regime:
                new_weights = self.adaptive_weighter.calculate_weights(
                    self.strategy_performances,
                    current_regime,
                    regime_confidence,
                )
            else:
                new_weights = self.sharpe_weighter.calculate_weights(self.strategy_performances)
        
        elif self.weighting_method == EnsembleWeightingMethod.MOMENTUM:
            new_weights = self._calculate_momentum_weights()
        
        elif self.weighting_method == EnsembleWeightingMethod.MEAN_REVERSION:
            new_weights = self._calculate_mean_reversion_weights()
        
        else:
            logger.warning(f"Unknown weighting method: {self.weighting_method}")
            return
        
        # Apply min/max constraints
        new_weights = self._apply_constraints(new_weights)
        
        # Update weights
        for strategy_id, weight in new_weights.items():
            if strategy_id in self.strategy_weights:
                self.strategy_weights[strategy_id].update_weight(weight)
        
        self.last_rebalance = datetime.utcnow()
        
        logger.info(f"Rebalanced ensemble: {new_weights}")
    
    def _calculate_inverse_variance_weights(self) -> Dict[str, float]:
        """Calculate inverse variance weights"""
        variances = {}
        for strategy_id, returns in self.strategy_performances.items():
            recent_returns = returns[-50:]
            if len(recent_returns) > 1:
                variances[strategy_id] = np.var(recent_returns)
            else:
                variances[strategy_id] = 1.0
        
        # Inverse variance
        inv_vars = {s: 1/v if v > 0 else 1.0 for s, v in variances.items()}
        
        # Normalize
        total = sum(inv_vars.values())
        weights = {s: v/total for s, v in inv_vars.items()}
        
        return weights
    
    def _calculate_momentum_weights(self) -> Dict[str, float]:
        """Recent winners get more weight"""
        recent_returns = {}
        for strategy_id, returns in self.strategy_performances.items():
            recent = returns[-10:]  # Last 10 trades
            recent_returns[strategy_id] = np.mean(recent) if recent else 0
        
        # Softmax to amplify differences
        exp_returns = {s: np.exp(r * 10) for s, r in recent_returns.items()}
        total = sum(exp_returns.values())
        weights = {s: v/total for s, v in exp_returns.items()}
        
        return weights
    
    def _calculate_mean_reversion_weights(self) -> Dict[str, float]:
        """Recent losers get more weight (contrarian)"""
        recent_returns = {}
        for strategy_id, returns in self.strategy_performances.items():
            recent = returns[-10:]
            recent_returns[strategy_id] = -np.mean(recent) if recent else 0  # Negative = contrarian
        
        # Ensure positive
        min_return = min(recent_returns.values())
        if min_return < 0:
            recent_returns = {s: r - min_return for s, r in recent_returns.items()}
        
        total = sum(recent_returns.values())
        if total == 0:
            n = len(recent_returns)
            return {s: 1/n for s in recent_returns.keys()}
        
        weights = {s: v/total for s, v in recent_returns.items()}
        return weights
    
    def _apply_constraints(self, weights: Dict[str, float]) -> Dict[str, float]:
        """Apply min/max weight constraints"""
        constrained = {}
        
        for strategy_id, weight in weights.items():
            constrained[strategy_id] = np.clip(weight, self.min_weight, self.max_weight)
        
        # Renormalize
        total = sum(constrained.values())
        if total > 0:
            constrained = {s: w/total for s, w in constrained.items()}
        
        return constrained
    
    def get_weights(self) -> Dict[str, float]:
        """Get current strategy weights"""
        return {s: w.weight for s, w in self.strategy_weights.items()}
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get ensemble statistics"""
        stats = {
            "num_strategies": len(self.strategy_weights),
            "weighting_method": self.weighting_method.value,
            "trade_count": self.trade_count,
            "last_rebalance": self.last_rebalance.isoformat(),
            "strategies": {}
        }
        
        for strategy_id, weight_obj in self.strategy_weights.items():
            stats["strategies"][strategy_id] = {
                "weight": weight_obj.weight,
                "recent_return": weight_obj.recent_return,
                "sharpe_ratio": weight_obj.sharpe_ratio,
                "volatility": weight_obj.volatility,
                "win_rate": weight_obj.win_rate,
            }
        
        return stats
