"""
Hedge Manager - Position hedging strategies

Implements various hedging approaches:
- Simple hedge (opposite position)
- Delta hedging
- Pairs hedging
- Options-style hedging
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class HedgeType(Enum):
    """Types of hedges"""
    FULL = "full"  # 100% hedge
    PARTIAL = "partial"  # Partial hedge
    DELTA = "delta"  # Delta-neutral hedge
    PAIRS = "pairs"  # Pairs trading hedge
    CROSS_ASSET = "cross_asset"  # Hedge with correlated asset


@dataclass
class HedgePosition:
    """A hedge position"""
    hedge_id: str
    original_position_id: str
    hedge_symbol: str
    hedge_side: str  # opposite of original
    hedge_size: float
    hedge_entry_price: float
    hedge_entry_time: datetime
    hedge_type: HedgeType
    hedge_ratio: float  # What % of original position
    is_active: bool = True
    exit_time: Optional[datetime] = None
    exit_price: Optional[float] = None


class HedgeStrategy:
    """Base hedge strategy"""
    
    def __init__(
        self,
        position_id: str,
        symbol: str,
        size: float,
        side: str,
        hedge_type: HedgeType
    ):
        self.position_id = position_id
        self.symbol = symbol
        self.size = size
        self.side = side
        self.hedge_type = hedge_type
        self.hedge_positions: List[HedgePosition] = []
        self.logger = logging.getLogger(__name__)
    
    def calculate_hedge_size(self, hedge_ratio: float = 1.0) -> float:
        """Calculate hedge size"""
        return self.size * hedge_ratio
    
    def calculate_hedge_symbol(self) -> str:
        """Determine which symbol to hedge with"""
        # Same symbol by default
        return self.symbol
    
    def calculate_hedge_side(self) -> str:
        """Determine hedge side (opposite of original)"""
        return "short" if self.side == "long" else "long"


class SimpleHedge(HedgeStrategy):
    """Simple opposite position hedge"""
    
    def __init__(
        self,
        position_id: str,
        symbol: str,
        size: float,
        side: str,
        hedge_ratio: float = 1.0
    ):
        super().__init__(position_id, symbol, size, side, HedgeType.FULL if hedge_ratio == 1.0 else HedgeType.PARTIAL)
        self.hedge_ratio = hedge_ratio
    
    def create_hedge(
        self,
        current_price: float,
        current_time: datetime
    ) -> HedgePosition:
        """Create simple hedge"""
        
        hedge_size = self.calculate_hedge_size(self.hedge_ratio)
        hedge_side = self.calculate_hedge_side()
        
        hedge = HedgePosition(
            hedge_id=f"{self.position_id}_hedge_{len(self.hedge_positions)}",
            original_position_id=self.position_id,
            hedge_symbol=self.symbol,
            hedge_side=hedge_side,
            hedge_size=hedge_size,
            hedge_entry_price=current_price,
            hedge_entry_time=current_time,
            hedge_type=self.hedge_type,
            hedge_ratio=self.hedge_ratio
        )
        
        self.hedge_positions.append(hedge)
        
        self.logger.info(
            f"Created {self.hedge_ratio:.1%} hedge for {self.position_id}: "
            f"{hedge_side} {hedge_size} {self.symbol} @ {current_price:.2f}"
        )
        
        return hedge


class PairsHedge(HedgeStrategy):
    """Pairs trading hedge with correlated asset"""
    
    def __init__(
        self,
        position_id: str,
        symbol: str,
        size: float,
        side: str,
        hedge_symbol: str,
        correlation: float,
        hedge_ratio: float = 1.0
    ):
        super().__init__(position_id, symbol, size, side, HedgeType.PAIRS)
        self.hedge_symbol_name = hedge_symbol
        self.correlation = correlation
        self.hedge_ratio = hedge_ratio
    
    def calculate_hedge_symbol(self) -> str:
        """Use specified correlated symbol"""
        return self.hedge_symbol_name
    
    def calculate_hedge_size(self, hedge_ratio: float = 1.0) -> float:
        """Adjust hedge size based on correlation"""
        # Stronger correlation = less hedge needed
        base_size = super().calculate_hedge_size(hedge_ratio)
        return base_size * abs(self.correlation)
    
    def create_hedge(
        self,
        current_price: float,
        hedge_asset_price: float,
        current_time: datetime
    ) -> HedgePosition:
        """Create pairs hedge"""
        
        hedge_size = self.calculate_hedge_size(self.hedge_ratio)
        hedge_side = self.calculate_hedge_side()
        hedge_symbol = self.calculate_hedge_symbol()
        
        hedge = HedgePosition(
            hedge_id=f"{self.position_id}_pairs_hedge",
            original_position_id=self.position_id,
            hedge_symbol=hedge_symbol,
            hedge_side=hedge_side,
            hedge_size=hedge_size,
            hedge_entry_price=hedge_asset_price,
            hedge_entry_time=current_time,
            hedge_type=HedgeType.PAIRS,
            hedge_ratio=self.hedge_ratio
        )
        
        self.hedge_positions.append(hedge)
        
        self.logger.info(
            f"Created pairs hedge: {self.symbol} vs {hedge_symbol} "
            f"(correlation={self.correlation:.2f})"
        )
        
        return hedge


class HedgeManager:
    """
    Manages hedging strategies for positions
    """
    
    def __init__(self):
        self.hedges: Dict[str, List[HedgePosition]] = {}
        self.strategies: Dict[str, HedgeStrategy] = {}
        self.logger = logging.getLogger(__name__)
    
    def create_simple_hedge(
        self,
        position_id: str,
        symbol: str,
        size: float,
        side: str,
        current_price: float,
        hedge_ratio: float = 1.0
    ) -> HedgePosition:
        """Create simple hedge"""
        
        strategy = SimpleHedge(position_id, symbol, size, side, hedge_ratio)
        hedge = strategy.create_hedge(current_price, datetime.now())
        
        if position_id not in self.hedges:
            self.hedges[position_id] = []
        self.hedges[position_id].append(hedge)
        
        self.strategies[position_id] = strategy
        
        return hedge
    
    def create_pairs_hedge(
        self,
        position_id: str,
        symbol: str,
        size: float,
        side: str,
        hedge_symbol: str,
        correlation: float,
        current_price: float,
        hedge_asset_price: float,
        hedge_ratio: float = 1.0
    ) -> HedgePosition:
        """Create pairs hedge"""
        
        strategy = PairsHedge(
            position_id, symbol, size, side,
            hedge_symbol, correlation, hedge_ratio
        )
        hedge = strategy.create_hedge(current_price, hedge_asset_price, datetime.now())
        
        if position_id not in self.hedges:
            self.hedges[position_id] = []
        self.hedges[position_id].append(hedge)
        
        self.strategies[position_id] = strategy
        
        return hedge
    
    def close_hedge(
        self,
        hedge_id: str,
        exit_price: float,
        exit_time: datetime
    ):
        """Close a hedge"""
        for position_hedges in self.hedges.values():
            for hedge in position_hedges:
                if hedge.hedge_id == hedge_id:
                    hedge.is_active = False
                    hedge.exit_price = exit_price
                    hedge.exit_time = exit_time
                    
                    self.logger.info(
                        f"Closed hedge {hedge_id} @ {exit_price:.2f}"
                    )
                    return
    
    def get_active_hedges(self, position_id: str) -> List[HedgePosition]:
        """Get active hedges for position"""
        if position_id not in self.hedges:
            return []
        return [h for h in self.hedges[position_id] if h.is_active]
    
    def calculate_net_exposure(
        self,
        position_id: str,
        position_size: float
    ) -> float:
        """Calculate net exposure after hedges"""
        active_hedges = self.get_active_hedges(position_id)
        hedge_size = sum(h.hedge_size * h.hedge_ratio for h in active_hedges)
        return position_size - hedge_size
