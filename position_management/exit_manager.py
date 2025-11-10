"""
Exit Manager - Time-based and condition-based exit strategies

Handles:
- Time-based exits (max holding period, specific time)
- Profit target exits (laddered targets)
- Technical condition exits
- Combined exit conditions
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import List, Optional, Callable
import logging

logger = logging.getLogger(__name__)


class ExitType(Enum):
    """Types of exit conditions"""
    TIME_BASED = "time_based"
    PROFIT_TARGET = "profit_target"
    TECHNICAL = "technical"
    COMBINED = "combined"


@dataclass
class ExitCondition:
    """An exit condition"""
    condition_id: str
    exit_type: ExitType
    priority: int  # Lower = higher priority
    size_to_exit: float  # 0-1, fraction of position
    triggered: bool = False
    trigger_time: Optional[datetime] = None


class TimeBasedExit:
    """Time-based exit conditions"""
    
    def __init__(self, position_id: str, entry_time: datetime):
        self.position_id = position_id
        self.entry_time = entry_time
        self.conditions: List[ExitCondition] = []
        self.logger = logging.getLogger(__name__)
    
    def add_max_holding_period(
        self,
        max_hours: float,
        size_to_exit: float = 1.0,
        priority: int = 1
    ):
        """Exit after max holding period"""
        condition = ExitCondition(
            condition_id=f"{self.position_id}_max_hold",
            exit_type=ExitType.TIME_BASED,
            priority=priority,
            size_to_exit=size_to_exit
        )
        self.conditions.append(condition)
        self.logger.info(f"Added max holding period: {max_hours}h")
    
    def add_time_of_day_exit(
        self,
        exit_hour: int,
        exit_minute: int = 0,
        size_to_exit: float = 1.0,
        priority: int = 2
    ):
        """Exit at specific time of day"""
        condition = ExitCondition(
            condition_id=f"{self.position_id}_time_exit",
            exit_type=ExitType.TIME_BASED,
            priority=priority,
            size_to_exit=size_to_exit
        )
        self.conditions.append(condition)
        self.logger.info(f"Added time-of-day exit: {exit_hour}:{exit_minute:02d}")
    
    def check_conditions(self, current_time: datetime) -> List[ExitCondition]:
        """Check which time-based conditions triggered"""
        triggered = []
        
        for condition in self.conditions:
            if condition.triggered:
                continue
            
            # Check condition (simplified)
            hours_held = (current_time - self.entry_time).total_seconds() / 3600
            
            # Placeholder: would check actual conditions
            if "max_hold" in condition.condition_id and hours_held > 24:
                condition.triggered = True
                condition.trigger_time = current_time
                triggered.append(condition)
        
        return triggered


class ProfitTargetExit:
    """Profit target exit (laddered targets)"""
    
    def __init__(
        self,
        position_id: str,
        entry_price: float,
        is_long: bool = True
    ):
        self.position_id = position_id
        self.entry_price = entry_price
        self.is_long = is_long
        self.targets: List[tuple] = []  # (target_price, size_to_exit)
        self.logger = logging.getLogger(__name__)
    
    def add_target(
        self,
        target_price: float,
        size_to_exit: float,
        priority: int = 1
    ):
        """Add profit target"""
        condition = ExitCondition(
            condition_id=f"{self.position_id}_target_{len(self.targets)}",
            exit_type=ExitType.PROFIT_TARGET,
            priority=priority,
            size_to_exit=size_to_exit
        )
        self.targets.append((target_price, condition))
        self.logger.info(
            f"Added profit target: {target_price:.2f} "
            f"({size_to_exit:.1%} of position)"
        )
    
    def add_percentage_targets(
        self,
        target_percentages: List[float],
        size_distribution: List[float]
    ):
        """Add multiple percentage-based targets"""
        for pct, size in zip(target_percentages, size_distribution):
            if self.is_long:
                target_price = self.entry_price * (1 + pct)
            else:
                target_price = self.entry_price * (1 - pct)
            self.add_target(target_price, size)
    
    def check_targets(self, current_price: float) -> List[ExitCondition]:
        """Check which targets hit"""
        triggered = []
        
        for target_price, condition in self.targets:
            if condition.triggered:
                continue
            
            hit = False
            if self.is_long and current_price >= target_price:
                hit = True
            elif not self.is_long and current_price <= target_price:
                hit = True
            
            if hit:
                condition.triggered = True
                condition.trigger_time = datetime.now()
                triggered.append(condition)
                self.logger.info(
                    f"Profit target hit: {target_price:.2f} @ {current_price:.2f}"
                )
        
        return triggered


class TechnicalExit:
    """Technical indicator-based exits"""
    
    def __init__(self, position_id: str):
        self.position_id = position_id
        self.conditions: List[ExitCondition] = []
        self.logger = logging.getLogger(__name__)
    
    def add_rsi_exit(self, rsi_threshold: float, is_overbought: bool = True):
        """Exit on RSI condition"""
        condition = ExitCondition(
            condition_id=f"{self.position_id}_rsi_exit",
            exit_type=ExitType.TECHNICAL,
            priority=2,
            size_to_exit=1.0
        )
        self.conditions.append(condition)
        self.logger.info(f"Added RSI exit: {'overbought' if is_overbought else 'oversold'} @ {rsi_threshold}")
    
    def add_ma_cross_exit(self, fast_period: int, slow_period: int):
        """Exit on moving average cross"""
        condition = ExitCondition(
            condition_id=f"{self.position_id}_ma_cross",
            exit_type=ExitType.TECHNICAL,
            priority=2,
            size_to_exit=1.0
        )
        self.conditions.append(condition)
        self.logger.info(f"Added MA cross exit: {fast_period}/{slow_period}")
    
    def check_conditions(self, market_data) -> List[ExitCondition]:
        """Check technical conditions (placeholder)"""
        # Would implement actual technical indicator checks
        return []


class ExitManager:
    """Manages all exit strategies for positions"""
    
    def __init__(self):
        self.time_exits: Dict[str, TimeBasedExit] = {}
        self.profit_exits: Dict[str, ProfitTargetExit] = {}
        self.technical_exits: Dict[str, TechnicalExit] = {}
        self.logger = logging.getLogger(__name__)
    
    def create_time_exit(
        self,
        position_id: str,
        entry_time: datetime,
        max_holding_hours: Optional[float] = None
    ) -> TimeBasedExit:
        """Create time-based exit"""
        exit_strategy = TimeBasedExit(position_id, entry_time)
        
        if max_holding_hours:
            exit_strategy.add_max_holding_period(max_holding_hours)
        
        self.time_exits[position_id] = exit_strategy
        return exit_strategy
    
    def create_profit_targets(
        self,
        position_id: str,
        entry_price: float,
        targets: List[tuple],  # [(price, size), ...]
        is_long: bool = True
    ) -> ProfitTargetExit:
        """Create laddered profit targets"""
        exit_strategy = ProfitTargetExit(position_id, entry_price, is_long)
        
        for target_price, size in targets:
            exit_strategy.add_target(target_price, size)
        
        self.profit_exits[position_id] = exit_strategy
        return exit_strategy
    
    def create_technical_exit(self, position_id: str) -> TechnicalExit:
        """Create technical exit strategy"""
        exit_strategy = TechnicalExit(position_id)
        self.technical_exits[position_id] = exit_strategy
        return exit_strategy
    
    def check_all_exits(
        self,
        position_id: str,
        current_price: float,
        current_time: datetime
    ) -> List[ExitCondition]:
        """Check all exit conditions for a position"""
        all_triggered = []
        
        # Time-based
        if position_id in self.time_exits:
            triggered = self.time_exits[position_id].check_conditions(current_time)
            all_triggered.extend(triggered)
        
        # Profit targets
        if position_id in self.profit_exits:
            triggered = self.profit_exits[position_id].check_targets(current_price)
            all_triggered.extend(triggered)
        
        # Technical
        if position_id in self.technical_exits:
            triggered = self.technical_exits[position_id].check_conditions(None)
            all_triggered.extend(triggered)
        
        # Sort by priority
        all_triggered.sort(key=lambda x: x.priority)
        
        return all_triggered
