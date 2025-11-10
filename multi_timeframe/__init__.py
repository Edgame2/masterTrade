"""
Multi-Timeframe Analysis Module

Provides comprehensive analysis across multiple timeframes for:
- Timeframe synchronization and alignment
- Trend consistency analysis
- Signal confluence detection
- Divergence identification
- Entry/exit timing optimization
"""

from .timeframe_synchronizer import (
    Timeframe,
    TimeframeBar,
    TimeframeSynchronizer,
)
from .trend_analyzer import (
    TrendDirection,
    TrendStrength,
    TimeframeTrend,
    TrendAnalyzer,
)
from .confluence_detector import (
    ConfluenceLevel,
    ConfluenceSignal,
    ConfluenceDetector,
)
from .divergence_detector import (
    DivergenceType,
    Divergence,
    DivergenceDetector,
)
from .signal_aggregator import (
    AggregatedSignal,
    SignalAggregator,
)

__all__ = [
    # Timeframe synchronization
    "Timeframe",
    "TimeframeBar",
    "TimeframeSynchronizer",
    
    # Trend analysis
    "TrendDirection",
    "TrendStrength",
    "TimeframeTrend",
    "TrendAnalyzer",
    
    # Confluence detection
    "ConfluenceLevel",
    "ConfluenceSignal",
    "ConfluenceDetector",
    
    # Divergence detection
    "DivergenceType",
    "Divergence",
    "DivergenceDetector",
    
    # Signal aggregation
    "AggregatedSignal",
    "SignalAggregator",
]
