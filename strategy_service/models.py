"""
Pydantic models for Strategy Service
"""

from datetime import datetime
from typing import Dict, List, Optional, Any

from pydantic import BaseModel, Field


class MarketData(BaseModel):
    """Market data model"""
    symbol: str
    timestamp: datetime
    open_price: float = Field(ge=0)
    high_price: float = Field(ge=0)
    low_price: float = Field(ge=0)
    close_price: float = Field(ge=0)
    volume: float = Field(ge=0)
    quote_volume: float = Field(ge=0)
    trades_count: int = Field(ge=0)
    interval: str = Field(default="1m")


class Strategy(BaseModel):
    """Trading strategy model"""
    id: str
    name: str
    type: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True
    symbols: List[Dict[str, Any]] = Field(default_factory=list)


class Signal(BaseModel):
    """Trading signal model"""
    strategy_id: str
    symbol: str
    signal_type: str  # BUY, SELL, HOLD
    confidence: float = Field(ge=0, le=100)
    price: float = Field(ge=0)
    quantity: Optional[float] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime


class StrategyResult(BaseModel):
    """Strategy execution result"""
    strategy_id: str
    symbol: str
    signals: List[Signal]
    execution_time: float
    error: Optional[str] = None


class StrategyConfig(BaseModel):
    """Strategy configuration"""
    name: str
    type: str
    parameters: Dict[str, Any]
    symbols: List[str]
    is_active: bool = True