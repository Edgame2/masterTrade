"""
Pydantic models for Order Executor Service
"""

from datetime import datetime
from typing import Dict, Optional, Any
import uuid

from pydantic import BaseModel, Field


class Signal(BaseModel):
    """Trading signal model"""
    id: Optional[int] = None
    strategy_id: int
    symbol: str
    signal_type: str  # BUY, SELL, HOLD
    confidence: float = Field(ge=0, le=100)
    price: float = Field(ge=0)
    quantity: Optional[float] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime


class OrderRequest(BaseModel):
    """Order request model"""
    client_order_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    strategy_id: int
    symbol: str
    side: str  # BUY, SELL
    order_type: str = "MARKET"  # MARKET, LIMIT, STOP_LOSS, TAKE_PROFIT
    quantity: float = Field(gt=0)
    price: Optional[float] = Field(default=None, ge=0)
    stop_price: Optional[float] = Field(default=None, ge=0)
    signal_id: Optional[int] = None
    environment: str = "testnet"  # testnet or production
    metadata: Dict[str, Any] = Field(default_factory=dict)


class Order(BaseModel):
    """Order model"""
    id: uuid.UUID
    strategy_id: int
    symbol: str
    signal_id: Optional[int] = None
    exchange_order_id: Optional[str] = None
    client_order_id: str
    order_type: str
    side: str
    quantity: float = Field(gt=0)
    price: Optional[float] = Field(default=None, ge=0)
    stop_price: Optional[float] = Field(default=None, ge=0)
    status: str = "NEW"
    filled_quantity: float = Field(default=0, ge=0)
    avg_fill_price: Optional[float] = Field(default=None, ge=0)
    commission: float = Field(default=0, ge=0)
    commission_asset: Optional[str] = None
    environment: str = "testnet"  # testnet or production
    order_time: datetime
    update_time: Optional[datetime] = None


class Trade(BaseModel):
    """Trade execution model"""
    id: Optional[int] = None
    order_id: uuid.UUID
    exchange_trade_id: str
    symbol: str
    side: str
    quantity: float = Field(gt=0)
    price: float = Field(gt=0)
    commission: float = Field(default=0, ge=0)
    commission_asset: Optional[str] = None
    is_maker: bool = False
    trade_time: datetime


class Balance(BaseModel):
    """Account balance model"""
    asset: str
    free_balance: float = Field(ge=0)
    locked_balance: float = Field(ge=0)
    
    @property
    def total_balance(self) -> float:
        return self.free_balance + self.locked_balance


class Position(BaseModel):
    """Position model"""
    id: Optional[int] = None
    symbol: str
    strategy_id: int
    quantity: float = 0.0
    avg_entry_price: Optional[float] = None
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    is_long: bool = True
    entry_time: Optional[datetime] = None
    exit_time: Optional[datetime] = None