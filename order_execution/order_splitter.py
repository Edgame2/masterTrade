"""
Order Splitter

Intelligent order splitting strategies:
- Fixed slices
- Iceberg orders
- Time-based splitting
- Volume-based splitting
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional
import numpy as np
import logging

logger = logging.getLogger(__name__)


class SplitStrategy(Enum):
    """Order splitting strategies"""
    EQUAL = "equal"  # Equal-sized slices
    RANDOM = "random"  # Randomized sizes
    EXPONENTIAL = "exponential"  # Decreasing sizes
    ICEBERG = "iceberg"  # Show small tip, hide bulk


@dataclass
class OrderSlice:
    """A slice of a larger order"""
    slice_id: str
    parent_order_id: str
    symbol: str
    side: str
    quantity: float
    limit_price: Optional[float] = None
    is_hidden: bool = False  # For iceberg orders
    created_at: datetime = field(default_factory=datetime.utcnow)
    status: str = "pending"


class OrderSplitter:
    """Splits large orders into smaller slices"""
    
    def __init__(self, strategy: SplitStrategy = SplitStrategy.EQUAL):
        self.strategy = strategy
        logger.info(f"OrderSplitter initialized with {strategy.value} strategy")
    
    def split_order(
        self,
        order_id: str,
        symbol: str,
        side: str,
        total_quantity: float,
        num_slices: int,
        randomize: bool = False,
    ) -> List[OrderSlice]:
        """Split order into slices"""
        
        if self.strategy == SplitStrategy.EQUAL:
            quantities = self._equal_split(total_quantity, num_slices)
        elif self.strategy == SplitStrategy.RANDOM:
            quantities = self._random_split(total_quantity, num_slices)
        elif self.strategy == SplitStrategy.EXPONENTIAL:
            quantities = self._exponential_split(total_quantity, num_slices)
        else:
            quantities = self._equal_split(total_quantity, num_slices)
        
        # Create slices
        slices = []
        for i, qty in enumerate(quantities):
            slice_obj = OrderSlice(
                slice_id=f"{order_id}_slice_{i}",
                parent_order_id=order_id,
                symbol=symbol,
                side=side,
                quantity=qty,
            )
            slices.append(slice_obj)
        
        logger.info(f"Split order {order_id} into {len(slices)} slices")
        return slices
    
    def _equal_split(self, total: float, n: int) -> List[float]:
        """Equal-sized slices"""
        size = total / n
        return [size] * n
    
    def _random_split(self, total: float, n: int) -> List[float]:
        """Random-sized slices"""
        # Generate random proportions
        random_props = np.random.random(n)
        random_props = random_props / np.sum(random_props)
        
        quantities = total * random_props
        return quantities.tolist()
    
    def _exponential_split(self, total: float, n: int) -> List[float]:
        """Exponentially decreasing slices"""
        # Larger slices first, smaller later
        weights = np.array([2 ** -i for i in range(n)])
        weights = weights / np.sum(weights)
        
        quantities = total * weights
        return quantities.tolist()


class IcebergOrder:
    """
    Iceberg order: shows small visible quantity, hides bulk.
    
    Prevents revealing full order size to market.
    """
    
    def __init__(
        self,
        symbol: str,
        side: str,
        total_quantity: float,
        visible_quantity: float,
        limit_price: Optional[float] = None,
    ):
        self.symbol = symbol
        self.side = side
        self.total_quantity = total_quantity
        self.visible_quantity = visible_quantity
        self.limit_price = limit_price
        
        self.hidden_quantity = total_quantity - visible_quantity
        self.filled_quantity = 0.0
        
        logger.info(f"Iceberg: {symbol} {side} total={total_quantity}, visible={visible_quantity}")
    
    def get_visible_slice(self) -> Optional[OrderSlice]:
        """Get next visible slice"""
        if self.filled_quantity >= self.total_quantity:
            return None
        
        remaining = self.total_quantity - self.filled_quantity
        slice_qty = min(self.visible_quantity, remaining)
        
        slice_obj = OrderSlice(
            slice_id=f"iceberg_{self.symbol}_{int(datetime.utcnow().timestamp())}",
            parent_order_id=f"iceberg_{self.symbol}",
            symbol=self.symbol,
            side=self.side,
            quantity=slice_qty,
            limit_price=self.limit_price,
            is_hidden=False,
        )
        
        return slice_obj
    
    def mark_filled(self, quantity: float):
        """Mark quantity as filled"""
        self.filled_quantity += quantity
        logger.debug(f"Iceberg filled: {self.filled_quantity}/{self.total_quantity}")
    
    def is_complete(self) -> bool:
        """Check if order complete"""
        return self.filled_quantity >= self.total_quantity
