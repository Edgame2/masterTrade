"""
Order Execution Optimization System

Provides institutional-grade order execution:
- TWAP (Time-Weighted Average Price)
- VWAP (Volume-Weighted Average Price)
- Smart order splitting
- Liquidity analysis
- Exchange routing
- Slippage minimization
"""

from .execution_algorithms import (
    ExecutionAlgorithm,
    TWAPAlgorithm,
    VWAPAlgorithm,
    POVAlgorithm,
    AdaptiveAlgorithm,
)

from .order_splitter import (
    OrderSplitter,
    SplitStrategy,
    IcebergOrder,
    OrderSlice,
)

from .liquidity_analyzer import (
    LiquidityAnalyzer,
    LiquidityScore,
    OrderBookAnalyzer,
    VolumeProfileAnalyzer,
)

from .exchange_router import (
    ExchangeRouter,
    RoutingStrategy,
    ExchangeSelector,
    SmartOrderRouter,
)

from .slippage_tracker import (
    SlippageTracker,
    SlippageMetrics,
    ExecutionQuality,
)

from .api import execution_router

__all__ = [
    # Execution Algorithms
    "ExecutionAlgorithm",
    "TWAPAlgorithm",
    "VWAPAlgorithm",
    "POVAlgorithm",
    "AdaptiveAlgorithm",
    
    # Order Splitting
    "OrderSplitter",
    "SplitStrategy",
    "IcebergOrder",
    "OrderSlice",
    
    # Liquidity Analysis
    "LiquidityAnalyzer",
    "LiquidityScore",
    "OrderBookAnalyzer",
    "VolumeProfileAnalyzer",
    
    # Exchange Routing
    "ExchangeRouter",
    "RoutingStrategy",
    "ExchangeSelector",
    "SmartOrderRouter",
    
    # Slippage Tracking
    "SlippageTracker",
    "SlippageMetrics",
    "ExecutionQuality",
    
    # API
    "execution_router",
]
