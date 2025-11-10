"""
Machine Learning Strategy Adaptation System

Provides ML-based adaptive trading capabilities:
- Regime detection (bull/bear/sideways markets)
- Online learning for parameter optimization
- Reinforcement learning for strategy selection
- Strategy ensemble weighting
- Performance prediction
"""

from .regime_detector import (
    RegimeDetector,
    MarketRegime,
    RegimeFeatures,
    HMMRegimeDetector,
    GMMRegimeDetector,
)

from .online_learning import (
    OnlineLearner,
    ParameterOptimizer,
    AdaptiveParameter,
    UpdateRule,
)

from .rl_strategy_selector import (
    RLStrategySelector,
    StrategyEnvironment,
    QLearningSelector,
    DQNSelector,
)

from .ensemble_manager import (
    EnsembleManager,
    EnsembleWeightingMethod,
    PerformanceBasedWeighting,
    SharpeWeighting,
    AdaptiveWeighting,
)

from .performance_predictor import (
    PerformancePredictor,
    PredictionModel,
    TimeSeriesPredictor,
    ClassificationPredictor,
)

from .api import ml_router

__all__ = [
    # Regime Detection
    "RegimeDetector",
    "MarketRegime",
    "RegimeFeatures",
    "HMMRegimeDetector",
    "GMMRegimeDetector",
    
    # Online Learning
    "OnlineLearner",
    "ParameterOptimizer",
    "AdaptiveParameter",
    "UpdateRule",
    
    # Reinforcement Learning
    "RLStrategySelector",
    "StrategyEnvironment",
    "QLearningSelector",
    "DQNSelector",
    
    # Ensemble Management
    "EnsembleManager",
    "EnsembleWeightingMethod",
    "PerformanceBasedWeighting",
    "SharpeWeighting",
    "AdaptiveWeighting",
    
    # Performance Prediction
    "PerformancePredictor",
    "PredictionModel",
    "TimeSeriesPredictor",
    "ClassificationPredictor",
    
    # API
    "ml_router",
]
