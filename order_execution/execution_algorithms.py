"""
Execution Algorithms

Implements institutional-grade execution strategies:
- TWAP: Time-Weighted Average Price
- VWAP: Volume-Weighted Average Price  
- POV: Percentage of Volume
- Adaptive: Adjusts to market conditions
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import List, Optional, Callable
import numpy as np
import logging

logger = logging.getLogger(__name__)


class OrderSide(Enum):
    """Order side"""
    BUY = "buy"
    SELL = "sell"


@dataclass
class ExecutionSlice:
    """A single slice of a parent order"""
    slice_id: str
    symbol: str
    side: OrderSide
    quantity: float
    target_price: Optional[float] = None
    scheduled_time: Optional[datetime] = None
    executed_time: Optional[datetime] = None
    executed_price: Optional[float] = None
    executed_quantity: float = 0.0
    status: str = "pending"  # pending, executing, completed, failed
    
    def is_complete(self) -> bool:
        return self.status == "completed"
    
    def mark_executed(self, price: float, quantity: float):
        """Mark slice as executed"""
        self.executed_price = price
        self.executed_quantity = quantity
        self.executed_time = datetime.utcnow()
        self.status = "completed"


class ExecutionAlgorithm:
    """
    Base class for execution algorithms.
    
    An execution algorithm splits a large order into smaller slices
    to minimize market impact and achieve better average price.
    """
    
    def __init__(self, symbol: str, side: OrderSide, total_quantity: float):
        self.symbol = symbol
        self.side = side
        self.total_quantity = total_quantity
        self.slices: List[ExecutionSlice] = []
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        
    def generate_slices(self) -> List[ExecutionSlice]:
        """Generate execution slices"""
        raise NotImplementedError
    
    def get_average_price(self) -> float:
        """Calculate volume-weighted average execution price"""
        executed_slices = [s for s in self.slices if s.is_complete()]
        if not executed_slices:
            return 0.0
        
        total_value = sum(s.executed_price * s.executed_quantity for s in executed_slices)
        total_quantity = sum(s.executed_quantity for s in executed_slices)
        
        return total_value / total_quantity if total_quantity > 0 else 0.0
    
    def get_completion_rate(self) -> float:
        """Get percentage of order completed"""
        executed_quantity = sum(s.executed_quantity for s in self.slices if s.is_complete())
        return executed_quantity / self.total_quantity if self.total_quantity > 0 else 0.0


class TWAPAlgorithm(ExecutionAlgorithm):
    """
    Time-Weighted Average Price (TWAP) execution.
    
    Splits order into equal-sized slices over a time period.
    Executes slices at regular intervals regardless of market conditions.
    
    Best for: Low-urgency orders where minimizing market impact is key.
    """
    
    def __init__(
        self,
        symbol: str,
        side: OrderSide,
        total_quantity: float,
        duration_minutes: int,
        num_slices: Optional[int] = None,
    ):
        super().__init__(symbol, side, total_quantity)
        self.duration_minutes = duration_minutes
        self.num_slices = num_slices or max(5, duration_minutes // 5)  # Default: 1 slice per 5 min
        
        logger.info(f"TWAP: {symbol} {side.value} {total_quantity} over {duration_minutes}min in {self.num_slices} slices")
    
    def generate_slices(self) -> List[ExecutionSlice]:
        """Generate equal-sized slices at regular intervals"""
        self.start_time = datetime.utcnow()
        self.end_time = self.start_time + timedelta(minutes=self.duration_minutes)
        
        # Equal-sized slices
        slice_quantity = self.total_quantity / self.num_slices
        
        # Equal time intervals
        interval_minutes = self.duration_minutes / self.num_slices
        
        self.slices = []
        for i in range(self.num_slices):
            scheduled_time = self.start_time + timedelta(minutes=i * interval_minutes)
            
            slice_obj = ExecutionSlice(
                slice_id=f"twap_{self.symbol}_{i}_{int(scheduled_time.timestamp())}",
                symbol=self.symbol,
                side=self.side,
                quantity=slice_quantity,
                scheduled_time=scheduled_time,
            )
            
            self.slices.append(slice_obj)
        
        logger.info(f"Generated {len(self.slices)} TWAP slices: {slice_quantity:.4f} every {interval_minutes:.1f}min")
        return self.slices


class VWAPAlgorithm(ExecutionAlgorithm):
    """
    Volume-Weighted Average Price (VWAP) execution.
    
    Splits order proportionally to expected volume distribution throughout the day.
    Aims to match the market's natural volume pattern.
    
    Best for: Achieving execution prices close to the day's VWAP benchmark.
    """
    
    def __init__(
        self,
        symbol: str,
        side: OrderSide,
        total_quantity: float,
        duration_minutes: int,
        volume_profile: Optional[List[float]] = None,
        num_slices: Optional[int] = None,
    ):
        super().__init__(symbol, side, total_quantity)
        self.duration_minutes = duration_minutes
        self.num_slices = num_slices or max(5, duration_minutes // 5)
        
        # Volume profile: expected volume distribution (higher = more volume expected)
        # If not provided, use U-shaped pattern (high at open/close, low mid-day)
        if volume_profile is None:
            volume_profile = self._generate_default_volume_profile()
        
        self.volume_profile = np.array(volume_profile[:self.num_slices])
        
        # Normalize to sum to 1
        self.volume_profile = self.volume_profile / np.sum(self.volume_profile)
        
        logger.info(f"VWAP: {symbol} {side.value} {total_quantity} over {duration_minutes}min following volume profile")
    
    def _generate_default_volume_profile(self) -> List[float]:
        """Generate U-shaped volume profile"""
        # U-shaped: high at start and end, lower in middle
        profile = []
        for i in range(self.num_slices):
            # Distance from center (0 = center, 1 = edge)
            distance_from_center = abs(2 * i / self.num_slices - 1)
            
            # Higher volume at edges (U-shape)
            volume_weight = 0.5 + 0.5 * distance_from_center
            
            profile.append(volume_weight)
        
        return profile
    
    def generate_slices(self) -> List[ExecutionSlice]:
        """Generate slices proportional to volume profile"""
        self.start_time = datetime.utcnow()
        self.end_time = self.start_time + timedelta(minutes=self.duration_minutes)
        
        # Slice quantities proportional to volume profile
        slice_quantities = self.total_quantity * self.volume_profile
        
        # Equal time intervals
        interval_minutes = self.duration_minutes / self.num_slices
        
        self.slices = []
        for i in range(self.num_slices):
            scheduled_time = self.start_time + timedelta(minutes=i * interval_minutes)
            
            slice_obj = ExecutionSlice(
                slice_id=f"vwap_{self.symbol}_{i}_{int(scheduled_time.timestamp())}",
                symbol=self.symbol,
                side=self.side,
                quantity=slice_quantities[i],
                scheduled_time=scheduled_time,
            )
            
            self.slices.append(slice_obj)
        
        logger.info(f"Generated {len(self.slices)} VWAP slices following volume profile")
        return self.slices


class POVAlgorithm(ExecutionAlgorithm):
    """
    Percentage of Volume (POV) execution.
    
    Executes slices as a fixed percentage of market volume.
    Adapts execution rate to market activity.
    
    Best for: Maintaining low market impact while following market liquidity.
    """
    
    def __init__(
        self,
        symbol: str,
        side: OrderSide,
        total_quantity: float,
        target_participation_rate: float = 0.10,  # 10% of market volume
        duration_minutes: int = 60,
    ):
        super().__init__(symbol, side, total_quantity)
        self.target_participation_rate = target_participation_rate
        self.duration_minutes = duration_minutes
        
        logger.info(f"POV: {symbol} {side.value} {total_quantity} at {target_participation_rate:.1%} participation")
    
    def generate_slices(
        self,
        expected_market_volumes: List[float],  # Expected volume per period
    ) -> List[ExecutionSlice]:
        """
        Generate slices based on expected market volume.
        
        Args:
            expected_market_volumes: Forecasted market volume for each period
        """
        self.start_time = datetime.utcnow()
        self.end_time = self.start_time + timedelta(minutes=self.duration_minutes)
        
        num_periods = len(expected_market_volumes)
        
        # Calculate slice quantities as percentage of market volume
        slice_quantities = []
        for market_volume in expected_market_volumes:
            slice_qty = market_volume * self.target_participation_rate
            slice_quantities.append(slice_qty)
        
        # Scale to match total quantity
        total_generated = sum(slice_quantities)
        if total_generated > 0:
            scaling_factor = self.total_quantity / total_generated
            slice_quantities = [q * scaling_factor for q in slice_quantities]
        
        # Generate slices
        interval_minutes = self.duration_minutes / num_periods
        
        self.slices = []
        for i in range(num_periods):
            scheduled_time = self.start_time + timedelta(minutes=i * interval_minutes)
            
            slice_obj = ExecutionSlice(
                slice_id=f"pov_{self.symbol}_{i}_{int(scheduled_time.timestamp())}",
                symbol=self.symbol,
                side=self.side,
                quantity=slice_quantities[i],
                scheduled_time=scheduled_time,
            )
            
            self.slices.append(slice_obj)
        
        logger.info(f"Generated {len(self.slices)} POV slices at {self.target_participation_rate:.1%} participation")
        return self.slices


class AdaptiveAlgorithm(ExecutionAlgorithm):
    """
    Adaptive execution algorithm.
    
    Dynamically adjusts execution based on:
    - Market conditions (volatility, spread, depth)
    - Urgency (how quickly order needs to be filled)
    - Performance (actual vs expected execution)
    
    Best for: Complex orders requiring intelligent adaptation.
    """
    
    def __init__(
        self,
        symbol: str,
        side: OrderSide,
        total_quantity: float,
        duration_minutes: int,
        urgency: float = 0.5,  # 0 = patient, 1 = aggressive
        initial_num_slices: int = 10,
    ):
        super().__init__(symbol, side, total_quantity)
        self.duration_minutes = duration_minutes
        self.urgency = urgency
        self.initial_num_slices = initial_num_slices
        
        # Adaptive parameters
        self.current_slice_size = total_quantity / initial_num_slices
        self.adjustment_factor = 1.0
        
        logger.info(f"Adaptive: {symbol} {side.value} {total_quantity} with urgency={urgency}")
    
    def generate_slices(self) -> List[ExecutionSlice]:
        """Generate initial slices (will adapt during execution)"""
        self.start_time = datetime.utcnow()
        self.end_time = self.start_time + timedelta(minutes=self.duration_minutes)
        
        # Initial equal-weighted slices
        slice_quantity = self.total_quantity / self.initial_num_slices
        interval_minutes = self.duration_minutes / self.initial_num_slices
        
        self.slices = []
        for i in range(self.initial_num_slices):
            scheduled_time = self.start_time + timedelta(minutes=i * interval_minutes)
            
            slice_obj = ExecutionSlice(
                slice_id=f"adaptive_{self.symbol}_{i}_{int(scheduled_time.timestamp())}",
                symbol=self.symbol,
                side=self.side,
                quantity=slice_quantity,
                scheduled_time=scheduled_time,
            )
            
            self.slices.append(slice_obj)
        
        return self.slices
    
    def adapt_to_market_conditions(
        self,
        current_volatility: float,
        current_spread: float,
        execution_shortfall: float,  # Difference from benchmark
    ):
        """
        Adapt execution parameters based on market conditions.
        
        Args:
            current_volatility: Current market volatility
            current_spread: Current bid-ask spread (basis points)
            execution_shortfall: How far off target we are
        """
        # Increase urgency if we're behind schedule
        if execution_shortfall < -0.05:  # 5% behind
            self.urgency = min(1.0, self.urgency + 0.1)
            logger.info(f"Increased urgency to {self.urgency:.2f} due to execution shortfall")
        
        # Adjust slice size based on volatility
        if current_volatility > 0.03:  # High volatility
            # Smaller slices in high volatility
            self.adjustment_factor = 0.8
        elif current_volatility < 0.01:  # Low volatility
            # Larger slices in low volatility
            self.adjustment_factor = 1.2
        
        # Adjust based on spread
        if current_spread > 50:  # Wide spread (>50bps)
            # More patient execution
            self.urgency = max(0.0, self.urgency - 0.1)
        
        logger.debug(f"Adapted: urgency={self.urgency:.2f}, adjustment={self.adjustment_factor:.2f}")
    
    def get_next_slice_size(self) -> float:
        """Calculate next slice size based on adaptive parameters"""
        remaining_quantity = self.total_quantity - sum(s.executed_quantity for s in self.slices if s.is_complete())
        remaining_slices = sum(1 for s in self.slices if not s.is_complete())
        
        if remaining_slices == 0:
            return 0.0
        
        # Base size
        base_size = remaining_quantity / remaining_slices
        
        # Adjust based on urgency and market conditions
        adjusted_size = base_size * self.urgency * self.adjustment_factor
        
        # Ensure we don't exceed remaining quantity
        adjusted_size = min(adjusted_size, remaining_quantity)
        
        return adjusted_size


def select_execution_algorithm(
    order_size_usd: float,
    daily_volume_usd: float,
    urgency: float,
    duration_minutes: int,
) -> str:
    """
    Recommend execution algorithm based on order characteristics.
    
    Args:
        order_size_usd: Order size in USD
        daily_volume_usd: Average daily volume in USD
        urgency: Urgency score (0-1)
        duration_minutes: Desired execution duration
        
    Returns:
        Recommended algorithm name
    """
    # Calculate order size as % of daily volume
    order_pct = (order_size_usd / daily_volume_usd) if daily_volume_usd > 0 else 1.0
    
    # Small orders (<1% of volume) - use simple TWAP
    if order_pct < 0.01:
        return "TWAP"
    
    # Medium orders (1-5% of volume)
    elif order_pct < 0.05:
        if urgency > 0.7:
            return "POV"  # More aggressive
        else:
            return "VWAP"  # Follow market volume
    
    # Large orders (>5% of volume)
    else:
        if urgency > 0.5:
            return "Adaptive"  # Need intelligent execution
        else:
            return "VWAP"  # Spread out over volume
