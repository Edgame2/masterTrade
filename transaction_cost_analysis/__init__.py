"""
Transaction Cost Analysis (TCA) Module

Comprehensive transaction cost analysis system for masterTrade including:
- Market impact models (linear, square-root, power law)
- Implementation shortfall analysis
- TWAP/VWAP benchmark analysis
- Cost-aware execution optimization
- Real-time TCA monitoring
- Historical cost attribution
"""

from .cost_models import (
    MarketImpactModel,
    LinearImpactModel,
    SquareRootImpactModel,
    PowerLawImpactModel,
    CostComponent,
    TransactionCost
)

from .implementation_shortfall import (
    ImplementationShortfall,
    ShortfallComponent,
    ShortfallAnalysis,
    ExecutionBenchmark
)

from .benchmark_analysis import (
    TWAPAnalyzer,
    VWAPAnalyzer,
    BenchmarkResult,
    BenchmarkType,
    ParticipationRate
)

from .execution_optimizer import (
    ExecutionOptimizer,
    OptimalSchedule,
    ExecutionStrategy,
    ScheduleOptimizer,
    TradingConstraints
)

from .real_time_monitor import (
    RealTimeTCAMonitor,
    TCAAlert,
    AlertType,
    MonitoringMetrics,
    ExecutionAlert
)

from .cost_attribution import (
    CostAttribution,
    AttributionBreakdown,
    CostDriver,
    AttributionResult,
    CostAnalyzer
)

from .api import router as tca_router

__all__ = [
    # Cost Models
    "MarketImpactModel",
    "LinearImpactModel", 
    "SquareRootImpactModel",
    "PowerLawImpactModel",
    "CostComponent",
    "TransactionCost",
    
    # Implementation Shortfall
    "ImplementationShortfall",
    "ShortfallComponent",
    "ShortfallAnalysis", 
    "ExecutionBenchmark",
    
    # Benchmark Analysis
    "TWAPAnalyzer",
    "VWAPAnalyzer",
    "BenchmarkResult",
    "BenchmarkType",
    "ParticipationRate",
    
    # Execution Optimization
    "ExecutionOptimizer",
    "OptimalSchedule",
    "ExecutionStrategy",
    "ScheduleOptimizer", 
    "TradingConstraints",
    
    # Real-time Monitoring
    "RealTimeTCAMonitor",
    "TCAAlert",
    "AlertType",
    "MonitoringMetrics",
    "ExecutionAlert",
    
    # Cost Attribution
    "CostAttribution",
    "AttributionBreakdown",
    "CostDriver",
    "AttributionResult",
    "CostAnalyzer",
    
    # API
    "tca_router",
]

__version__ = "1.0.0"