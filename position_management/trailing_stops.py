"""
Trailing Stops - Multiple trailing stop implementations

Types:
- Percentage trailing stop
- ATR-based trailing stop
- Chandelier stop
- Parabolic SAR stop
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional, List
from abc import ABC, abstractmethod
import numpy as np
import pandas as pd
import logging

logger = logging.getLogger(__name__)


class TrailingStopType(Enum):
    """Types of trailing stops"""
    PERCENTAGE = "percentage"
    ATR = "atr"
    CHANDELIER = "chandelier"
    PARABOLIC_SAR = "parabolic_sar"
    HIGHEST_HIGH = "highest_high"  # Trail highest high since entry
    LOWEST_LOW = "lowest_low"  # Trail lowest low since entry


@dataclass
class TrailingStopState:
    """Current state of a trailing stop"""
    stop_type: TrailingStopType
    current_stop_price: float
    highest_price: float  # Highest since entry (for longs)
    lowest_price: float  # Lowest since entry (for shorts)
    last_update_time: datetime
    triggered: bool = False
    trigger_time: Optional[datetime] = None


class TrailingStop(ABC):
    """Base class for trailing stops"""
    
    def __init__(self, stop_type: TrailingStopType, is_long: bool = True):
        self.stop_type = stop_type
        self.is_long = is_long
        self.logger = logging.getLogger(__name__)
    
    @abstractmethod
    def calculate_stop(
        self,
        current_price: float,
        current_time: datetime,
        market_data: Optional[pd.DataFrame] = None
    ) -> float:
        """Calculate current stop price"""
        pass
    
    @abstractmethod
    def should_trigger(self, current_price: float) -> bool:
        """Check if stop should trigger"""
        pass


class PercentageTrailingStop(TrailingStop):
    """
    Simple percentage trailing stop
    
    For longs: Stop trails price up by X%
    For shorts: Stop trails price down by X%
    """
    
    def __init__(
        self,
        trail_percent: float,
        entry_price: float,
        is_long: bool = True
    ):
        super().__init__(TrailingStopType.PERCENTAGE, is_long)
        self.trail_percent = trail_percent
        self.entry_price = entry_price
        
        # Initialize
        if is_long:
            self.stop_price = entry_price * (1 - trail_percent)
            self.highest_price = entry_price
        else:
            self.stop_price = entry_price * (1 + trail_percent)
            self.lowest_price = entry_price
    
    def calculate_stop(
        self,
        current_price: float,
        current_time: datetime,
        market_data: Optional[pd.DataFrame] = None
    ) -> float:
        """Calculate stop based on highest/lowest price"""
        
        if self.is_long:
            # Update highest
            if current_price > self.highest_price:
                self.highest_price = current_price
                # Trail stop up
                new_stop = self.highest_price * (1 - self.trail_percent)
                if new_stop > self.stop_price:
                    self.stop_price = new_stop
                    self.logger.debug(
                        f"Percentage trailing stop updated: {self.stop_price:.2f} "
                        f"(highest={self.highest_price:.2f})"
                    )
        else:
            # Update lowest
            if current_price < self.lowest_price:
                self.lowest_price = current_price
                # Trail stop down
                new_stop = self.lowest_price * (1 + self.trail_percent)
                if new_stop < self.stop_price:
                    self.stop_price = new_stop
                    self.logger.debug(
                        f"Percentage trailing stop updated: {self.stop_price:.2f} "
                        f"(lowest={self.lowest_price:.2f})"
                    )
        
        return self.stop_price
    
    def should_trigger(self, current_price: float) -> bool:
        """Check if price hit stop"""
        if self.is_long:
            return current_price <= self.stop_price
        else:
            return current_price >= self.stop_price


class ATRTrailingStop(TrailingStop):
    """
    ATR-based trailing stop
    
    Uses Average True Range to set dynamic stop distance
    More room in volatile markets, tighter in calm markets
    """
    
    def __init__(
        self,
        atr_multiplier: float,
        entry_price: float,
        initial_atr: float,
        is_long: bool = True,
        atr_period: int = 14
    ):
        super().__init__(TrailingStopType.ATR, is_long)
        self.atr_multiplier = atr_multiplier
        self.entry_price = entry_price
        self.current_atr = initial_atr
        self.atr_period = atr_period
        
        # Initialize stop
        if is_long:
            self.stop_price = entry_price - (initial_atr * atr_multiplier)
            self.highest_price = entry_price
        else:
            self.stop_price = entry_price + (initial_atr * atr_multiplier)
            self.lowest_price = entry_price
    
    def calculate_stop(
        self,
        current_price: float,
        current_time: datetime,
        market_data: Optional[pd.DataFrame] = None
    ) -> float:
        """Calculate stop based on ATR"""
        
        # Update ATR if market data provided
        if market_data is not None and len(market_data) >= self.atr_period:
            self.current_atr = self._calculate_atr(market_data)
        
        if self.is_long:
            # Update highest
            if current_price > self.highest_price:
                self.highest_price = current_price
                # Trail stop up
                new_stop = self.highest_price - (self.current_atr * self.atr_multiplier)
                if new_stop > self.stop_price:
                    self.stop_price = new_stop
                    self.logger.debug(
                        f"ATR trailing stop updated: {self.stop_price:.2f} "
                        f"(ATR={self.current_atr:.2f})"
                    )
        else:
            # Update lowest
            if current_price < self.lowest_price:
                self.lowest_price = current_price
                # Trail stop down
                new_stop = self.lowest_price + (self.current_atr * self.atr_multiplier)
                if new_stop < self.stop_price:
                    self.stop_price = new_stop
                    self.logger.debug(
                        f"ATR trailing stop updated: {self.stop_price:.2f} "
                        f"(ATR={self.current_atr:.2f})"
                    )
        
        return self.stop_price
    
    def _calculate_atr(self, market_data: pd.DataFrame) -> float:
        """Calculate ATR from market data"""
        # True Range = max(high-low, abs(high-close_prev), abs(low-close_prev))
        high = market_data['high'].values
        low = market_data['low'].values
        close = market_data['close'].values
        
        tr1 = high - low
        tr2 = np.abs(high - np.roll(close, 1))
        tr3 = np.abs(low - np.roll(close, 1))
        
        tr = np.maximum(tr1, np.maximum(tr2, tr3))
        atr = np.mean(tr[-self.atr_period:])
        
        return atr
    
    def should_trigger(self, current_price: float) -> bool:
        """Check if price hit stop"""
        if self.is_long:
            return current_price <= self.stop_price
        else:
            return current_price >= self.stop_price


class ChandelierTrailingStop(TrailingStop):
    """
    Chandelier Exit trailing stop
    
    Stop = Highest High (or Lowest Low) +/- ATR * multiplier
    Named because it "hangs" from the highest/lowest point
    """
    
    def __init__(
        self,
        atr_multiplier: float,
        entry_price: float,
        initial_atr: float,
        is_long: bool = True,
        lookback_period: int = 22
    ):
        super().__init__(TrailingStopType.CHANDELIER, is_long)
        self.atr_multiplier = atr_multiplier
        self.entry_price = entry_price
        self.current_atr = initial_atr
        self.lookback_period = lookback_period
        
        # Track highs/lows
        self.price_history: List[float] = [entry_price]
        
        # Initialize stop
        if is_long:
            self.stop_price = entry_price - (initial_atr * atr_multiplier)
        else:
            self.stop_price = entry_price + (initial_atr * atr_multiplier)
    
    def calculate_stop(
        self,
        current_price: float,
        current_time: datetime,
        market_data: Optional[pd.DataFrame] = None
    ) -> float:
        """Calculate Chandelier stop"""
        
        # Update price history
        self.price_history.append(current_price)
        if len(self.price_history) > self.lookback_period:
            self.price_history.pop(0)
        
        # Update ATR if available
        if market_data is not None and len(market_data) >= 14:
            self.current_atr = self._calculate_atr(market_data)
        
        # Calculate stop
        if self.is_long:
            # Hang from highest high
            highest_high = max(self.price_history)
            new_stop = highest_high - (self.current_atr * self.atr_multiplier)
            if new_stop > self.stop_price:
                self.stop_price = new_stop
                self.logger.debug(
                    f"Chandelier stop updated: {self.stop_price:.2f} "
                    f"(HH={highest_high:.2f}, ATR={self.current_atr:.2f})"
                )
        else:
            # Hang from lowest low
            lowest_low = min(self.price_history)
            new_stop = lowest_low + (self.current_atr * self.atr_multiplier)
            if new_stop < self.stop_price:
                self.stop_price = new_stop
                self.logger.debug(
                    f"Chandelier stop updated: {self.stop_price:.2f} "
                    f"(LL={lowest_low:.2f}, ATR={self.current_atr:.2f})"
                )
        
        return self.stop_price
    
    def _calculate_atr(self, market_data: pd.DataFrame) -> float:
        """Calculate ATR"""
        high = market_data['high'].values
        low = market_data['low'].values
        close = market_data['close'].values
        
        tr1 = high - low
        tr2 = np.abs(high - np.roll(close, 1))
        tr3 = np.abs(low - np.roll(close, 1))
        
        tr = np.maximum(tr1, np.maximum(tr2, tr3))
        atr = np.mean(tr[-14:])
        
        return atr
    
    def should_trigger(self, current_price: float) -> bool:
        """Check if price hit stop"""
        if self.is_long:
            return current_price <= self.stop_price
        else:
            return current_price >= self.stop_price


class ParabolicSARStop(TrailingStop):
    """
    Parabolic SAR trailing stop
    
    Accelerating trailing stop that gets tighter as trend continues
    """
    
    def __init__(
        self,
        entry_price: float,
        is_long: bool = True,
        initial_af: float = 0.02,
        max_af: float = 0.20,
        af_increment: float = 0.02
    ):
        super().__init__(TrailingStopType.PARABOLIC_SAR, is_long)
        self.entry_price = entry_price
        self.af = initial_af  # Acceleration factor
        self.max_af = max_af
        self.af_increment = af_increment
        
        # Initialize
        if is_long:
            self.sar = entry_price * 0.98  # Start 2% below
            self.extreme_point = entry_price
        else:
            self.sar = entry_price * 1.02  # Start 2% above
            self.extreme_point = entry_price
    
    def calculate_stop(
        self,
        current_price: float,
        current_time: datetime,
        market_data: Optional[pd.DataFrame] = None
    ) -> float:
        """Calculate Parabolic SAR"""
        
        if self.is_long:
            # Update extreme point (highest high)
            if current_price > self.extreme_point:
                self.extreme_point = current_price
                # Increase acceleration factor
                self.af = min(self.af + self.af_increment, self.max_af)
            
            # Calculate new SAR
            new_sar = self.sar + self.af * (self.extreme_point - self.sar)
            
            # SAR should only move up for longs
            if new_sar > self.sar:
                self.sar = new_sar
                self.logger.debug(
                    f"Parabolic SAR updated: {self.sar:.2f} "
                    f"(AF={self.af:.3f}, EP={self.extreme_point:.2f})"
                )
        
        else:
            # Update extreme point (lowest low)
            if current_price < self.extreme_point:
                self.extreme_point = current_price
                # Increase acceleration factor
                self.af = min(self.af + self.af_increment, self.max_af)
            
            # Calculate new SAR
            new_sar = self.sar - self.af * (self.sar - self.extreme_point)
            
            # SAR should only move down for shorts
            if new_sar < self.sar:
                self.sar = new_sar
                self.logger.debug(
                    f"Parabolic SAR updated: {self.sar:.2f} "
                    f"(AF={self.af:.3f}, EP={self.extreme_point:.2f})"
                )
        
        return self.sar
    
    def should_trigger(self, current_price: float) -> bool:
        """Check if price crossed SAR"""
        if self.is_long:
            return current_price <= self.sar
        else:
            return current_price >= self.sar


class TrailingStopManager:
    """
    Manages trailing stops for positions
    
    Supports multiple trailing stop types and updates
    """
    
    def __init__(self):
        self.trailing_stops: Dict[str, TrailingStop] = {}
        self.stop_states: Dict[str, TrailingStopState] = {}
        self.logger = logging.getLogger(__name__)
    
    def create_percentage_stop(
        self,
        position_id: str,
        trail_percent: float,
        entry_price: float,
        is_long: bool = True
    ) -> PercentageTrailingStop:
        """Create percentage trailing stop"""
        
        stop = PercentageTrailingStop(trail_percent, entry_price, is_long)
        self.trailing_stops[position_id] = stop
        
        self.stop_states[position_id] = TrailingStopState(
            stop_type=TrailingStopType.PERCENTAGE,
            current_stop_price=stop.stop_price,
            highest_price=entry_price if is_long else 0,
            lowest_price=entry_price if not is_long else float('inf'),
            last_update_time=datetime.now()
        )
        
        self.logger.info(
            f"Created {trail_percent:.1%} trailing stop for {position_id}"
        )
        
        return stop
    
    def create_atr_stop(
        self,
        position_id: str,
        atr_multiplier: float,
        entry_price: float,
        initial_atr: float,
        is_long: bool = True
    ) -> ATRTrailingStop:
        """Create ATR trailing stop"""
        
        stop = ATRTrailingStop(atr_multiplier, entry_price, initial_atr, is_long)
        self.trailing_stops[position_id] = stop
        
        self.stop_states[position_id] = TrailingStopState(
            stop_type=TrailingStopType.ATR,
            current_stop_price=stop.stop_price,
            highest_price=entry_price if is_long else 0,
            lowest_price=entry_price if not is_long else float('inf'),
            last_update_time=datetime.now()
        )
        
        self.logger.info(
            f"Created {atr_multiplier}x ATR trailing stop for {position_id}"
        )
        
        return stop
    
    def create_chandelier_stop(
        self,
        position_id: str,
        atr_multiplier: float,
        entry_price: float,
        initial_atr: float,
        is_long: bool = True
    ) -> ChandelierTrailingStop:
        """Create Chandelier stop"""
        
        stop = ChandelierTrailingStop(atr_multiplier, entry_price, initial_atr, is_long)
        self.trailing_stops[position_id] = stop
        
        self.stop_states[position_id] = TrailingStopState(
            stop_type=TrailingStopType.CHANDELIER,
            current_stop_price=stop.stop_price,
            highest_price=entry_price if is_long else 0,
            lowest_price=entry_price if not is_long else float('inf'),
            last_update_time=datetime.now()
        )
        
        self.logger.info(
            f"Created Chandelier stop for {position_id}"
        )
        
        return stop
    
    def create_parabolic_sar_stop(
        self,
        position_id: str,
        entry_price: float,
        is_long: bool = True
    ) -> ParabolicSARStop:
        """Create Parabolic SAR stop"""
        
        stop = ParabolicSARStop(entry_price, is_long)
        self.trailing_stops[position_id] = stop
        
        self.stop_states[position_id] = TrailingStopState(
            stop_type=TrailingStopType.PARABOLIC_SAR,
            current_stop_price=stop.sar,
            highest_price=entry_price if is_long else 0,
            lowest_price=entry_price if not is_long else float('inf'),
            last_update_time=datetime.now()
        )
        
        self.logger.info(
            f"Created Parabolic SAR stop for {position_id}"
        )
        
        return stop
    
    def update_stop(
        self,
        position_id: str,
        current_price: float,
        current_time: datetime,
        market_data: Optional[pd.DataFrame] = None
    ) -> Optional[float]:
        """
        Update trailing stop for position
        
        Returns new stop price, or None if no stop exists
        """
        if position_id not in self.trailing_stops:
            return None
        
        stop = self.trailing_stops[position_id]
        state = self.stop_states[position_id]
        
        # Calculate new stop
        new_stop = stop.calculate_stop(current_price, current_time, market_data)
        
        # Update state
        state.current_stop_price = new_stop
        state.last_update_time = current_time
        
        if stop.is_long:
            state.highest_price = max(state.highest_price, current_price)
        else:
            state.lowest_price = min(state.lowest_price, current_price)
        
        return new_stop
    
    def check_trigger(
        self,
        position_id: str,
        current_price: float,
        current_time: datetime
    ) -> bool:
        """Check if trailing stop triggered"""
        if position_id not in self.trailing_stops:
            return False
        
        stop = self.trailing_stops[position_id]
        state = self.stop_states[position_id]
        
        if stop.should_trigger(current_price):
            state.triggered = True
            state.trigger_time = current_time
            
            self.logger.warning(
                f"Trailing stop triggered for {position_id} at {current_price:.2f}"
            )
            
            return True
        
        return False
    
    def get_stop_price(self, position_id: str) -> Optional[float]:
        """Get current stop price"""
        if position_id in self.stop_states:
            return self.stop_states[position_id].current_stop_price
        return None
    
    def remove_stop(self, position_id: str):
        """Remove trailing stop"""
        if position_id in self.trailing_stops:
            del self.trailing_stops[position_id]
        if position_id in self.stop_states:
            del self.stop_states[position_id]
