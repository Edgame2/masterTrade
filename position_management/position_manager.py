"""
Position Manager - Core position tracking and management

Handles:
- Position lifecycle (open, update, partial close, full close)
- Real-time P&L tracking
- Position metadata and history
- Integration with risk management
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Tuple
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)


class PositionSide(Enum):
    """Position side"""
    LONG = "long"
    SHORT = "short"


class PositionStatus(Enum):
    """Position status"""
    OPEN = "open"
    PARTIALLY_CLOSED = "partially_closed"
    CLOSED = "closed"
    LIQUIDATED = "liquidated"


@dataclass
class PositionFill:
    """A fill that contributed to position"""
    fill_id: str
    timestamp: datetime
    price: float
    size: float
    side: str  # buy or sell
    fee: float
    is_closing: bool = False  # True if reducing position


@dataclass
class Position:
    """
    Represents a trading position
    
    Can track partial closes and multiple fills
    """
    
    position_id: str
    symbol: str
    strategy_id: str
    side: PositionSide
    status: PositionStatus
    
    # Entry
    entry_time: datetime
    average_entry_price: float
    initial_size: float
    
    # Current state
    current_size: float
    current_price: float
    last_update_time: datetime
    
    # Exit (if closed)
    exit_time: Optional[datetime] = None
    average_exit_price: Optional[float] = None
    
    # P&L
    unrealized_pnl: float = 0.0
    unrealized_pnl_pct: float = 0.0
    realized_pnl: float = 0.0
    realized_pnl_pct: float = 0.0
    
    # Costs
    total_fees: float = 0.0
    total_funding: float = 0.0
    
    # Stops and targets
    stop_loss_price: Optional[float] = None
    take_profit_price: Optional[float] = None
    trailing_stop_price: Optional[float] = None
    trailing_stop_type: Optional[str] = None
    
    # Risk metrics
    max_adverse_excursion: float = 0.0  # MAE
    max_favorable_excursion: float = 0.0  # MFE
    
    # Fills history
    fills: List[PositionFill] = field(default_factory=list)
    
    # Metadata
    tags: Dict[str, str] = field(default_factory=dict)
    notes: str = ""
    
    def __post_init__(self):
        """Initialize computed fields"""
        if not self.fills:
            # Create initial fill
            self.fills.append(PositionFill(
                fill_id=f"{self.position_id}_0",
                timestamp=self.entry_time,
                price=self.average_entry_price,
                size=self.initial_size,
                side="buy" if self.side == PositionSide.LONG else "sell",
                fee=0.0,
                is_closing=False
            ))
    
    def update_current_price(self, price: float, timestamp: datetime):
        """Update current price and recalculate P&L"""
        self.current_price = price
        self.last_update_time = timestamp
        self._calculate_unrealized_pnl()
        self._update_mae_mfe()
    
    def add_to_position(
        self,
        fill_id: str,
        price: float,
        size: float,
        fee: float,
        timestamp: datetime
    ):
        """
        Add to position (scale in)
        
        Updates average entry price
        """
        # Add fill
        self.fills.append(PositionFill(
            fill_id=fill_id,
            timestamp=timestamp,
            price=price,
            size=size,
            side="buy" if self.side == PositionSide.LONG else "sell",
            fee=fee,
            is_closing=False
        ))
        
        # Update average entry price
        total_cost = self.average_entry_price * self.current_size + price * size
        self.current_size += size
        self.average_entry_price = total_cost / self.current_size
        
        self.total_fees += fee
        self.last_update_time = timestamp
        
        logger.info(
            f"Added to position {self.position_id}: "
            f"+{size} @ {price}, new size={self.current_size}, "
            f"avg entry={self.average_entry_price:.2f}"
        )
    
    def reduce_position(
        self,
        fill_id: str,
        price: float,
        size: float,
        fee: float,
        timestamp: datetime
    ) -> Tuple[float, float]:
        """
        Reduce position (partial close or full close)
        
        Returns:
            (realized_pnl, realized_pnl_pct) for this reduction
        """
        if size > self.current_size:
            raise ValueError(f"Cannot reduce by {size}, current size is {self.current_size}")
        
        # Calculate realized P&L for this reduction
        if self.side == PositionSide.LONG:
            pnl = (price - self.average_entry_price) * size
        else:  # SHORT
            pnl = (self.average_entry_price - price) * size
        
        pnl -= fee  # Deduct fees
        pnl_pct = pnl / (self.average_entry_price * size) if size > 0 else 0
        
        # Add fill
        self.fills.append(PositionFill(
            fill_id=fill_id,
            timestamp=timestamp,
            price=price,
            size=size,
            side="sell" if self.side == PositionSide.LONG else "buy",
            fee=fee,
            is_closing=True
        ))
        
        # Update position
        self.current_size -= size
        self.realized_pnl += pnl
        self.total_fees += fee
        self.last_update_time = timestamp
        
        # Calculate realized pct based on initial size
        self.realized_pnl_pct = self.realized_pnl / (self.average_entry_price * self.initial_size)
        
        # Update status
        if self.current_size == 0:
            self.status = PositionStatus.CLOSED
            self.exit_time = timestamp
            self.average_exit_price = self._calculate_average_exit_price()
        else:
            self.status = PositionStatus.PARTIALLY_CLOSED
        
        logger.info(
            f"Reduced position {self.position_id}: "
            f"-{size} @ {price}, remaining={self.current_size}, "
            f"realized P&L={pnl:.2f} ({pnl_pct:.2%})"
        )
        
        return pnl, pnl_pct
    
    def close_position(
        self,
        fill_id: str,
        price: float,
        fee: float,
        timestamp: datetime
    ) -> Tuple[float, float]:
        """
        Close entire position
        
        Returns:
            (total_realized_pnl, total_realized_pnl_pct)
        """
        return self.reduce_position(fill_id, price, self.current_size, fee, timestamp)
    
    def _calculate_unrealized_pnl(self):
        """Calculate unrealized P&L on open position"""
        if self.current_size == 0:
            self.unrealized_pnl = 0
            self.unrealized_pnl_pct = 0
            return
        
        if self.side == PositionSide.LONG:
            self.unrealized_pnl = (self.current_price - self.average_entry_price) * self.current_size
        else:  # SHORT
            self.unrealized_pnl = (self.average_entry_price - self.current_price) * self.current_size
        
        self.unrealized_pnl_pct = self.unrealized_pnl / (self.average_entry_price * self.current_size)
    
    def _update_mae_mfe(self):
        """Update maximum adverse/favorable excursion"""
        if self.current_size == 0:
            return
        
        if self.side == PositionSide.LONG:
            excursion = (self.current_price - self.average_entry_price) / self.average_entry_price
        else:
            excursion = (self.average_entry_price - self.current_price) / self.average_entry_price
        
        if excursion < 0:
            # Adverse
            self.max_adverse_excursion = min(self.max_adverse_excursion, excursion)
        else:
            # Favorable
            self.max_favorable_excursion = max(self.max_favorable_excursion, excursion)
    
    def _calculate_average_exit_price(self) -> float:
        """Calculate average exit price from closing fills"""
        closing_fills = [f for f in self.fills if f.is_closing]
        if not closing_fills:
            return 0.0
        
        total_value = sum(f.price * f.size for f in closing_fills)
        total_size = sum(f.size for f in closing_fills)
        
        return total_value / total_size if total_size > 0 else 0.0
    
    def get_total_pnl(self) -> float:
        """Get total P&L (realized + unrealized)"""
        return self.realized_pnl + self.unrealized_pnl
    
    def get_holding_time(self) -> float:
        """Get holding time in hours"""
        end_time = self.exit_time if self.exit_time else self.last_update_time
        return (end_time - self.entry_time).total_seconds() / 3600
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "position_id": self.position_id,
            "symbol": self.symbol,
            "strategy_id": self.strategy_id,
            "side": self.side.value,
            "status": self.status.value,
            "entry_time": self.entry_time.isoformat(),
            "exit_time": self.exit_time.isoformat() if self.exit_time else None,
            "average_entry_price": self.average_entry_price,
            "average_exit_price": self.average_exit_price,
            "initial_size": self.initial_size,
            "current_size": self.current_size,
            "current_price": self.current_price,
            "unrealized_pnl": self.unrealized_pnl,
            "unrealized_pnl_pct": self.unrealized_pnl_pct,
            "realized_pnl": self.realized_pnl,
            "realized_pnl_pct": self.realized_pnl_pct,
            "total_pnl": self.get_total_pnl(),
            "total_fees": self.total_fees,
            "total_funding": self.total_funding,
            "stop_loss_price": self.stop_loss_price,
            "take_profit_price": self.take_profit_price,
            "trailing_stop_price": self.trailing_stop_price,
            "mae": self.max_adverse_excursion,
            "mfe": self.max_favorable_excursion,
            "holding_hours": self.get_holding_time(),
            "num_fills": len(self.fills),
            "tags": self.tags,
            "notes": self.notes
        }


class PositionManager:
    """
    Manages all open positions
    
    Provides:
    - Position tracking
    - Partial close operations
    - P&L updates
    - Position queries
    """
    
    def __init__(self):
        self.positions: Dict[str, Position] = {}
        self.closed_positions: List[Position] = []
        self.logger = logging.getLogger(__name__)
    
    def open_position(
        self,
        position_id: str,
        symbol: str,
        strategy_id: str,
        side: PositionSide,
        entry_price: float,
        size: float,
        entry_time: datetime,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        tags: Optional[Dict[str, str]] = None
    ) -> Position:
        """Open a new position"""
        
        position = Position(
            position_id=position_id,
            symbol=symbol,
            strategy_id=strategy_id,
            side=side,
            status=PositionStatus.OPEN,
            entry_time=entry_time,
            average_entry_price=entry_price,
            initial_size=size,
            current_size=size,
            current_price=entry_price,
            last_update_time=entry_time,
            stop_loss_price=stop_loss,
            take_profit_price=take_profit,
            tags=tags or {}
        )
        
        self.positions[position_id] = position
        
        self.logger.info(
            f"Opened position {position_id}: {symbol} {side.value} "
            f"{size} @ {entry_price}"
        )
        
        return position
    
    def update_position_price(
        self,
        position_id: str,
        current_price: float,
        timestamp: datetime
    ):
        """Update position with current market price"""
        if position_id not in self.positions:
            raise ValueError(f"Position {position_id} not found")
        
        position = self.positions[position_id]
        position.update_current_price(current_price, timestamp)
    
    def add_to_position(
        self,
        position_id: str,
        fill_id: str,
        price: float,
        size: float,
        fee: float,
        timestamp: datetime
    ):
        """Add to existing position (scale in)"""
        if position_id not in self.positions:
            raise ValueError(f"Position {position_id} not found")
        
        position = self.positions[position_id]
        position.add_to_position(fill_id, price, size, fee, timestamp)
    
    def reduce_position(
        self,
        position_id: str,
        fill_id: str,
        price: float,
        size: float,
        fee: float,
        timestamp: datetime
    ) -> Tuple[float, float]:
        """Reduce position (partial close)"""
        if position_id not in self.positions:
            raise ValueError(f"Position {position_id} not found")
        
        position = self.positions[position_id]
        pnl, pnl_pct = position.reduce_position(fill_id, price, size, fee, timestamp)
        
        # If fully closed, move to closed positions
        if position.status == PositionStatus.CLOSED:
            self.closed_positions.append(position)
            del self.positions[position_id]
        
        return pnl, pnl_pct
    
    def close_position(
        self,
        position_id: str,
        fill_id: str,
        price: float,
        fee: float,
        timestamp: datetime
    ) -> Tuple[float, float]:
        """Close entire position"""
        if position_id not in self.positions:
            raise ValueError(f"Position {position_id} not found")
        
        return self.reduce_position(
            position_id, fill_id, price,
            self.positions[position_id].current_size,
            fee, timestamp
        )
    
    def get_position(self, position_id: str) -> Optional[Position]:
        """Get position by ID"""
        return self.positions.get(position_id)
    
    def get_open_positions(
        self,
        symbol: Optional[str] = None,
        strategy_id: Optional[str] = None
    ) -> List[Position]:
        """Get open positions with optional filters"""
        positions = list(self.positions.values())
        
        if symbol:
            positions = [p for p in positions if p.symbol == symbol]
        
        if strategy_id:
            positions = [p for p in positions if p.strategy_id == strategy_id]
        
        return positions
    
    def get_closed_positions(
        self,
        symbol: Optional[str] = None,
        strategy_id: Optional[str] = None,
        limit: int = 100
    ) -> List[Position]:
        """Get closed positions"""
        positions = self.closed_positions[-limit:]
        
        if symbol:
            positions = [p for p in positions if p.symbol == symbol]
        
        if strategy_id:
            positions = [p for p in positions if p.strategy_id == strategy_id]
        
        return positions
    
    def get_total_exposure(self, symbol: Optional[str] = None) -> float:
        """Get total position exposure"""
        positions = self.get_open_positions(symbol=symbol)
        return sum(
            p.current_size * p.current_price
            for p in positions
        )
    
    def get_total_unrealized_pnl(self, symbol: Optional[str] = None) -> float:
        """Get total unrealized P&L"""
        positions = self.get_open_positions(symbol=symbol)
        return sum(p.unrealized_pnl for p in positions)
    
    def get_total_realized_pnl(
        self,
        symbol: Optional[str] = None,
        since: Optional[datetime] = None
    ) -> float:
        """Get total realized P&L"""
        positions = self.closed_positions
        
        if symbol:
            positions = [p for p in positions if p.symbol == symbol]
        
        if since:
            positions = [p for p in positions if p.exit_time and p.exit_time >= since]
        
        return sum(p.realized_pnl for p in positions)
