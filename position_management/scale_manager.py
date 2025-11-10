"""
Scale Manager - Scale-in and scale-out strategies

Implements various approaches to building and reducing positions gradually:
- Dollar-cost averaging (DCA)
- Price-level based scaling
- Volatility-adjusted scaling
- Profit-target based scaling
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional, Callable
import numpy as np
import logging

logger = logging.getLogger(__name__)


class ScaleStrategy(Enum):
    """Scaling strategy types"""
    EQUAL = "equal"  # Equal sizes
    INCREASING = "increasing"  # Larger sizes as you scale
    DECREASING = "decreasing"  # Smaller sizes as you scale
    PYRAMID = "pyramid"  # Larger at bottom, smaller at top
    INVERSE_PYRAMID = "inverse_pyramid"  # Smaller at bottom, larger at top


@dataclass
class ScaleLevel:
    """A single scale level"""
    level_id: str
    price_trigger: float
    size: float
    filled: bool = False
    fill_price: Optional[float] = None
    fill_time: Optional[datetime] = None
    fill_id: Optional[str] = None


@dataclass
class ScaleConfig:
    """Configuration for scaling"""
    
    # Total position size
    total_size: float
    
    # Number of scale levels
    num_levels: int
    
    # Strategy
    strategy: ScaleStrategy
    
    # Price spacing
    price_spacing_pct: float  # % between levels
    
    # Or explicit price levels
    price_levels: Optional[List[float]] = None
    
    # Size distribution (overrides strategy if provided)
    size_distribution: Optional[List[float]] = None
    
    # Time constraints
    max_time_between_levels_hours: Optional[float] = None
    
    # Adaptive scaling
    adjust_for_volatility: bool = False
    volatility_window: int = 20


class ScaleInStrategy:
    """
    Scale-in strategy - build position gradually
    
    Use cases:
    - DCA into position
    - Add on dips (long) or rallies (short)
    - Build position as conviction increases
    """
    
    def __init__(self, config: ScaleConfig, entry_price: float, is_long: bool = True):
        self.config = config
        self.entry_price = entry_price
        self.is_long = is_long
        self.levels: List[ScaleLevel] = []
        self.logger = logging.getLogger(__name__)
        
        self._initialize_levels()
    
    def _initialize_levels(self):
        """Initialize scale levels based on config"""
        
        # Determine price levels
        if self.config.price_levels:
            price_levels = self.config.price_levels
        else:
            price_levels = self._calculate_price_levels()
        
        # Determine size distribution
        if self.config.size_distribution:
            sizes = self.config.size_distribution
        else:
            sizes = self._calculate_size_distribution()
        
        # Normalize sizes to match total
        size_sum = sum(sizes)
        sizes = [s / size_sum * self.config.total_size for s in sizes]
        
        # Create levels
        for i, (price, size) in enumerate(zip(price_levels, sizes)):
            self.levels.append(ScaleLevel(
                level_id=f"scale_in_{i}",
                price_trigger=price,
                size=size
            ))
        
        self.logger.info(
            f"Initialized {len(self.levels)} scale-in levels: "
            f"prices={[l.price_trigger for l in self.levels]}, "
            f"sizes={[l.size for l in self.levels]}"
        )
    
    def _calculate_price_levels(self) -> List[float]:
        """Calculate price levels based on spacing"""
        levels = []
        current_price = self.entry_price
        
        for i in range(self.config.num_levels):
            levels.append(current_price)
            
            # Move to next level
            if self.is_long:
                # Scale in on dips (lower prices)
                current_price *= (1 - self.config.price_spacing_pct)
            else:
                # Scale in on rallies (higher prices) for shorts
                current_price *= (1 + self.config.price_spacing_pct)
        
        return levels
    
    def _calculate_size_distribution(self) -> List[float]:
        """Calculate size distribution based on strategy"""
        
        n = self.config.num_levels
        
        if self.config.strategy == ScaleStrategy.EQUAL:
            return [1.0] * n
        
        elif self.config.strategy == ScaleStrategy.INCREASING:
            # Linear increase: 1, 2, 3, ..., n
            return list(range(1, n + 1))
        
        elif self.config.strategy == ScaleStrategy.DECREASING:
            # Linear decrease: n, n-1, ..., 2, 1
            return list(range(n, 0, -1))
        
        elif self.config.strategy == ScaleStrategy.PYRAMID:
            # Pyramid: larger at bottom (lower prices for long)
            if self.is_long:
                return list(range(n, 0, -1))  # First level largest
            else:
                return list(range(1, n + 1))  # Last level largest
        
        elif self.config.strategy == ScaleStrategy.INVERSE_PYRAMID:
            # Inverse pyramid: smaller at bottom
            if self.is_long:
                return list(range(1, n + 1))
            else:
                return list(range(n, 0, -1))
        
        return [1.0] * n
    
    def check_triggers(
        self,
        current_price: float,
        current_time: datetime
    ) -> List[ScaleLevel]:
        """
        Check if any scale levels should be triggered
        
        Returns:
            List of levels to execute
        """
        triggered = []
        
        for level in self.levels:
            if level.filled:
                continue
            
            # Check price trigger
            if self.is_long:
                # For longs, trigger when price drops to level
                if current_price <= level.price_trigger:
                    triggered.append(level)
            else:
                # For shorts, trigger when price rises to level
                if current_price >= level.price_trigger:
                    triggered.append(level)
        
        return triggered
    
    def mark_filled(
        self,
        level_id: str,
        fill_price: float,
        fill_time: datetime,
        fill_id: str
    ):
        """Mark a level as filled"""
        for level in self.levels:
            if level.level_id == level_id:
                level.filled = True
                level.fill_price = fill_price
                level.fill_time = fill_time
                level.fill_id = fill_id
                
                self.logger.info(
                    f"Filled scale-in level {level_id} @ {fill_price}"
                )
                break
    
    def get_average_entry_price(self) -> float:
        """Calculate average entry price of filled levels"""
        filled = [l for l in self.levels if l.filled]
        if not filled:
            return 0.0
        
        total_cost = sum(l.fill_price * l.size for l in filled)
        total_size = sum(l.size for l in filled)
        
        return total_cost / total_size if total_size > 0 else 0.0
    
    def get_filled_size(self) -> float:
        """Get total filled size"""
        return sum(l.size for l in self.levels if l.filled)
    
    def is_complete(self) -> bool:
        """Check if all levels are filled"""
        return all(l.filled for l in self.levels)
    
    def get_remaining_levels(self) -> List[ScaleLevel]:
        """Get unfilled levels"""
        return [l for l in self.levels if not l.filled]


class ScaleOutStrategy:
    """
    Scale-out strategy - reduce position gradually
    
    Use cases:
    - Take profits in stages
    - Reduce as price moves away from optimal
    - Lock in profits while maintaining exposure
    """
    
    def __init__(
        self,
        config: ScaleConfig,
        entry_price: float,
        current_size: float,
        is_long: bool = True
    ):
        self.config = config
        self.entry_price = entry_price
        self.current_size = current_size
        self.is_long = is_long
        self.levels: List[ScaleLevel] = []
        self.logger = logging.getLogger(__name__)
        
        self._initialize_levels()
    
    def _initialize_levels(self):
        """Initialize scale-out levels"""
        
        # Price levels (profit targets)
        if self.config.price_levels:
            price_levels = self.config.price_levels
        else:
            price_levels = self._calculate_profit_targets()
        
        # Size distribution
        if self.config.size_distribution:
            sizes = self.config.size_distribution
        else:
            sizes = self._calculate_size_distribution()
        
        # Normalize
        size_sum = sum(sizes)
        sizes = [s / size_sum * self.config.total_size for s in sizes]
        
        # Create levels
        for i, (price, size) in enumerate(zip(price_levels, sizes)):
            self.levels.append(ScaleLevel(
                level_id=f"scale_out_{i}",
                price_trigger=price,
                size=size
            ))
        
        self.logger.info(
            f"Initialized {len(self.levels)} scale-out levels: "
            f"prices={[l.price_trigger for l in self.levels]}, "
            f"sizes={[l.size for l in self.levels]}"
        )
    
    def _calculate_profit_targets(self) -> List[float]:
        """Calculate profit target prices"""
        levels = []
        current_price = self.entry_price
        
        for i in range(self.config.num_levels):
            # Move to profit target
            if self.is_long:
                # Scale out higher (profits for longs)
                current_price *= (1 + self.config.price_spacing_pct)
            else:
                # Scale out lower (profits for shorts)
                current_price *= (1 - self.config.price_spacing_pct)
            
            levels.append(current_price)
        
        return levels
    
    def _calculate_size_distribution(self) -> List[float]:
        """Calculate how much to sell at each level"""
        
        # Common strategies:
        # - Equal: Take equal amounts at each level
        # - Decreasing: Take more early, less later (lock in profits)
        # - Increasing: Take less early, more later (let winners run)
        
        n = self.config.num_levels
        
        if self.config.strategy == ScaleStrategy.EQUAL:
            return [1.0] * n
        
        elif self.config.strategy == ScaleStrategy.DECREASING:
            # Take more at early profit targets
            return list(range(n, 0, -1))
        
        elif self.config.strategy == ScaleStrategy.INCREASING:
            # Take more at later profit targets
            return list(range(1, n + 1))
        
        return [1.0] * n
    
    def check_triggers(
        self,
        current_price: float,
        current_time: datetime
    ) -> List[ScaleLevel]:
        """Check if any profit targets hit"""
        triggered = []
        
        for level in self.levels:
            if level.filled:
                continue
            
            # Check price trigger
            if self.is_long:
                # For longs, trigger when price rises to target
                if current_price >= level.price_trigger:
                    triggered.append(level)
            else:
                # For shorts, trigger when price falls to target
                if current_price <= level.price_trigger:
                    triggered.append(level)
        
        return triggered
    
    def mark_filled(
        self,
        level_id: str,
        fill_price: float,
        fill_time: datetime,
        fill_id: str
    ):
        """Mark a level as filled"""
        for level in self.levels:
            if level.level_id == level_id:
                level.filled = True
                level.fill_price = fill_price
                level.fill_time = fill_time
                level.fill_id = fill_id
                
                self.logger.info(
                    f"Filled scale-out level {level_id} @ {fill_price}"
                )
                break
    
    def get_average_exit_price(self) -> float:
        """Calculate average exit price"""
        filled = [l for l in self.levels if l.filled]
        if not filled:
            return 0.0
        
        total_value = sum(l.fill_price * l.size for l in filled)
        total_size = sum(l.size for l in filled)
        
        return total_value / total_size if total_size > 0 else 0.0
    
    def get_exited_size(self) -> float:
        """Get total exited size"""
        return sum(l.size for l in self.levels if l.filled)
    
    def is_complete(self) -> bool:
        """Check if fully exited"""
        return all(l.filled for l in self.levels)


class ScaleManager:
    """
    Manages scale-in and scale-out strategies for positions
    """
    
    def __init__(self):
        self.scale_in_strategies: Dict[str, ScaleInStrategy] = {}
        self.scale_out_strategies: Dict[str, ScaleOutStrategy] = {}
        self.logger = logging.getLogger(__name__)
    
    def create_scale_in(
        self,
        position_id: str,
        config: ScaleConfig,
        entry_price: float,
        is_long: bool = True
    ) -> ScaleInStrategy:
        """Create a scale-in strategy for a position"""
        
        strategy = ScaleInStrategy(config, entry_price, is_long)
        self.scale_in_strategies[position_id] = strategy
        
        self.logger.info(
            f"Created scale-in strategy for {position_id}: "
            f"{config.num_levels} levels, {config.strategy.value}"
        )
        
        return strategy
    
    def create_scale_out(
        self,
        position_id: str,
        config: ScaleConfig,
        entry_price: float,
        current_size: float,
        is_long: bool = True
    ) -> ScaleOutStrategy:
        """Create a scale-out strategy for a position"""
        
        strategy = ScaleOutStrategy(config, entry_price, current_size, is_long)
        self.scale_out_strategies[position_id] = strategy
        
        self.logger.info(
            f"Created scale-out strategy for {position_id}: "
            f"{config.num_levels} levels, {config.strategy.value}"
        )
        
        return strategy
    
    def check_scale_in_triggers(
        self,
        position_id: str,
        current_price: float,
        current_time: datetime
    ) -> List[ScaleLevel]:
        """Check scale-in triggers for a position"""
        if position_id not in self.scale_in_strategies:
            return []
        
        strategy = self.scale_in_strategies[position_id]
        return strategy.check_triggers(current_price, current_time)
    
    def check_scale_out_triggers(
        self,
        position_id: str,
        current_price: float,
        current_time: datetime
    ) -> List[ScaleLevel]:
        """Check scale-out triggers for a position"""
        if position_id not in self.scale_out_strategies:
            return []
        
        strategy = self.scale_out_strategies[position_id]
        return strategy.check_triggers(current_price, current_time)
    
    def get_scale_in_strategy(self, position_id: str) -> Optional[ScaleInStrategy]:
        """Get scale-in strategy for position"""
        return self.scale_in_strategies.get(position_id)
    
    def get_scale_out_strategy(self, position_id: str) -> Optional[ScaleOutStrategy]:
        """Get scale-out strategy for position"""
        return self.scale_out_strategies.get(position_id)
