"""
Advanced Position Management System - Task #14

Provides sophisticated position handling capabilities:
- Partial position closing
- Scale-in/scale-out strategies
- Multiple trailing stop types
- Time-based exits
- Profit-taking ladders
- Position hedging
"""

from .position_manager import (
    PositionManager,
    Position,
    PositionSide,
    PositionStatus
)

from .scale_manager import (
    ScaleManager,
    ScaleInStrategy,
    ScaleOutStrategy,
    ScaleConfig,
    ScaleLevel
)

from .trailing_stops import (
    TrailingStopManager,
    TrailingStopType,
    PercentageTrailingStop,
    ATRTrailingStop,
    ChandelierTrailingStop,
    ParabolicSARStop
)

from .exit_manager import (
    ExitManager,
    ExitCondition,
    ExitType,
    TimeBasedExit,
    ProfitTargetExit,
    TechnicalExit
)

from .hedge_manager import (
    HedgeManager,
    HedgeType,
    HedgeStrategy,
    HedgePosition
)

from .api import router as position_router

__all__ = [
    # Core position management
    "PositionManager",
    "Position",
    "PositionSide",
    "PositionStatus",
    
    # Scale in/out
    "ScaleManager",
    "ScaleInStrategy",
    "ScaleOutStrategy",
    "ScaleConfig",
    "ScaleLevel",
    
    # Trailing stops
    "TrailingStopManager",
    "TrailingStopType",
    "PercentageTrailingStop",
    "ATRTrailingStop",
    "ChandelierTrailingStop",
    "ParabolicSARStop",
    
    # Exit management
    "ExitManager",
    "ExitCondition",
    "ExitType",
    "TimeBasedExit",
    "ProfitTargetExit",
    "TechnicalExit",
    
    # Hedging
    "HedgeManager",
    "HedgeType",
    "HedgeStrategy",
    "HedgePosition",
    
    # API
    "position_router",
]
