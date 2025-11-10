"""
Performance Attribution System - Task #13

Provides factor-based return decomposition, alpha vs beta separation,
trade-level attribution, and comprehensive benchmarking capabilities.
"""

from .attribution_engine import (
    AttributionEngine,
    AttributionConfig,
    AttributionResult,
    FactorExposure,
    AlphaBetaDecomposition
)

from .factor_models import (
    FactorModel,
    FactorType,
    MultiFactorModel,
    FamaFrenchCrypto,
    MomentumReversal,
    VolatilityCarry
)

from .benchmark_manager import (
    BenchmarkManager,
    Benchmark,
    BenchmarkType,
    BenchmarkComparison
)

from .trade_attribution import (
    TradeAttributor,
    TradeAttribution,
    AttributionCategory,
    ComponentContribution
)

from .api import router as attribution_router

__all__ = [
    # Core engine
    "AttributionEngine",
    "AttributionConfig",
    "AttributionResult",
    "FactorExposure",
    "AlphaBetaDecomposition",
    
    # Factor models
    "FactorModel",
    "FactorType",
    "MultiFactorModel",
    "FamaFrenchCrypto",
    "MomentumReversal",
    "VolatilityCarry",
    
    # Benchmarks
    "BenchmarkManager",
    "Benchmark",
    "BenchmarkType",
    "BenchmarkComparison",
    
    # Trade attribution
    "TradeAttributor",
    "TradeAttribution",
    "AttributionCategory",
    "ComponentContribution",
    
    # API
    "attribution_router",
]
