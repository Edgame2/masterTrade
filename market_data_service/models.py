"""
Pydantic models for Market Data Service
"""

from datetime import datetime
from typing import List, Tuple, Dict, Any, Optional

from pydantic import BaseModel, Field


class MarketData(BaseModel):
    """Market data model for klines/candlesticks"""
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


class TradeData(BaseModel):
    """Trade data model"""
    symbol: str
    timestamp: datetime
    price: float = Field(ge=0)
    quantity: float = Field(ge=0)
    is_buyer_maker: bool


class OrderBookData(BaseModel):
    """Order book data model"""
    symbol: str
    timestamp: datetime
    bids: List[Tuple[str, str]]  # [price, quantity]
    asks: List[Tuple[str, str]]  # [price, quantity]


class SymbolInfo(BaseModel):
    """Symbol information model"""
    symbol: str
    base_asset: str
    quote_asset: str
    is_active: bool = True
    min_qty: float
    max_qty: float
    step_size: float
    tick_size: float


class SymbolTracking(BaseModel):
    """Symbol tracking configuration model for database-driven symbol management"""
    id: str = Field(description="Unique identifier (same as symbol for partition key)")
    symbol: str = Field(description="Trading symbol (e.g., BTCUSDC)")
    base_asset: str = Field(description="Base asset (e.g., BTC)")
    quote_asset: str = Field(description="Quote asset (e.g., USDC)")
    tracking: bool = Field(default=True, description="Whether to collect data for this symbol")
    asset_type: str = Field(default="crypto", description="Type of asset (crypto, stock, etc.)")
    exchange: str = Field(default="binance", description="Exchange where symbol is traded")
    priority: int = Field(default=1, description="Collection priority (1=high, 2=medium, 3=low)")
    intervals: List[str] = Field(default=["1m", "5m", "15m", "1h", "4h", "1d"], description="Intervals to collect")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="When symbol was added")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="When symbol was last modified")
    notes: str = Field(default="", description="Optional notes about the symbol")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() + "Z"
        }


class IndicatorConfigurationDB(BaseModel):
    """Database model for storing technical indicator configurations"""
    id: str = Field(description="Unique configuration ID (partition key)")
    strategy_id: str = Field(description="Strategy that owns this configuration")
    indicator_type: str = Field(description="Type of indicator (sma, ema, rsi, macd, etc.)")
    
    # Target configuration
    symbol: str = Field(description="Trading symbol")
    interval: str = Field(description="Time interval")
    
    # Indicator parameters (stored as JSON)
    parameters: Dict[str, Any] = Field(description="Indicator-specific parameters")
    
    # Output configuration
    output_fields: List[str] = Field(description="Expected output field names")
    periods_required: int = Field(description="Minimum periods needed for calculation")
    
    # Execution settings
    active: bool = Field(default=True, description="Whether to actively calculate this indicator")
    priority: int = Field(default=1, description="Calculation priority (1=highest)")
    cache_duration_minutes: int = Field(default=5, description="Cache duration")
    update_frequency_seconds: int = Field(default=60, description="Update frequency")
    
    # Subscription settings
    continuous_calculation: bool = Field(default=True, description="Calculate continuously")
    publish_to_rabbitmq: bool = Field(default=True, description="Publish results to RabbitMQ")
    rabbitmq_routing_key: str = Field(default="", description="Custom routing key for results")
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_calculated: Optional[datetime] = Field(default=None, description="Last calculation timestamp")
    calculation_count: int = Field(default=0, description="Total calculations performed")
    
    # Performance tracking
    avg_calculation_time_ms: float = Field(default=0.0, description="Average calculation time")
    last_error: str = Field(default="", description="Last error message if any")
    error_count: int = Field(default=0, description="Total error count")
    
    # Strategy context
    strategy_name: str = Field(default="", description="Human-readable strategy name")
    strategy_version: str = Field(default="1.0", description="Strategy version")
    notes: str = Field(default="", description="Configuration notes")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() + "Z"
        }


class IndicatorCalculationResult(BaseModel):
    """Model for storing indicator calculation results"""
    id: str = Field(description="Unique result ID")
    configuration_id: str = Field(description="Reference to indicator configuration")
    symbol: str = Field(description="Trading symbol")
    interval: str = Field(description="Time interval")
    
    # Calculation data
    timestamp: datetime = Field(description="Calculation timestamp")
    values: Dict[str, float] = Field(description="Calculated indicator values")
    
    # Performance metrics
    calculation_time_ms: float = Field(description="Calculation time")
    data_points_used: int = Field(description="Number of data points used")
    cache_hit: bool = Field(default=False, description="Whether result was cached")
    
    # Quality metrics
    data_quality_score: float = Field(default=1.0, description="Data quality score (0-1)")
    confidence_score: float = Field(default=1.0, description="Calculation confidence (0-1)")
    
    # Metadata
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() + "Z"
        }