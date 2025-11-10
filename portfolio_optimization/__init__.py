"""
Portfolio Optimization Module

Provides comprehensive portfolio optimization capabilities including:
- Modern Portfolio Theory (MPT)
- Efficient Frontier optimization
- Risk Parity allocation
- Black-Litterman model
- Factor-based allocation
- Portfolio rebalancing
- Performance attribution
"""

from .portfolio_optimizer import (
    OptimizationMethod,
    OptimizationObjective,
    PortfolioConstraints,
    PortfolioOptimizer,
)
from .efficient_frontier import (
    EfficientFrontier,
    FrontierPoint,
    OptimalPortfolios,
)
from .risk_models import (
    RiskModel,
    CovarianceEstimator,
    RiskModelType,
    FactorRiskModel,
)
from .black_litterman import (
    BlackLittermanModel,
    ViewSpecification,
    MarketCapWeights,
)
from .rebalancer import (
    RebalancingFrequency,
    RebalancingTrigger,
    PortfolioRebalancer,
    RebalancingDecision,
)
from .performance_attribution import (
    AttributionMethod,
    PerformanceAttribution,
    AttributionResult,
)

__all__ = [
    # Core optimization
    "OptimizationMethod",
    "OptimizationObjective", 
    "PortfolioConstraints",
    "PortfolioOptimizer",
    
    # Efficient frontier
    "EfficientFrontier",
    "FrontierPoint",
    "OptimalPortfolios",
    
    # Risk models
    "RiskModel",
    "CovarianceEstimator",
    "RiskModelType",
    "FactorRiskModel",
    
    # Black-Litterman
    "BlackLittermanModel",
    "ViewSpecification",
    "MarketCapWeights",
    
    # Rebalancing
    "RebalancingFrequency",
    "RebalancingTrigger",
    "PortfolioRebalancer",
    "RebalancingDecision",
    
    # Performance attribution
    "AttributionMethod",
    "PerformanceAttribution",
    "AttributionResult",
]