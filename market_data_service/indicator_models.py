"""
Technical Indicator Configuration Models for Market Data Service

These models define the structure for dynamic technical indicator calculations
requested by the strategy service.
"""

from datetime import datetime
from typing import Dict, List, Optional, Any, Union
from enum import Enum
from pydantic import BaseModel, Field, validator


class IndicatorType(str, Enum):
    """Supported technical indicators"""
    SMA = "sma"
    EMA = "ema" 
    RSI = "rsi"
    MACD = "macd"
    BOLLINGER_BANDS = "bollinger_bands"
    STOCHASTIC = "stochastic"
    WILLIAMS_R = "williams_r"
    CCI = "cci"
    ATR = "atr"
    MOMENTUM = "momentum"
    ROC = "roc"  # Rate of Change
    CUSTOM = "custom"


class IndicatorParameter(BaseModel):
    """Individual indicator parameter"""
    name: str = Field(description="Parameter name (e.g., 'period', 'fast_period')")
    value: Union[int, float, str] = Field(description="Parameter value")
    data_type: str = Field(default="int", description="Data type: int, float, string")


class IndicatorConfiguration(BaseModel):
    """Configuration for a single technical indicator"""
    id: str = Field(description="Unique identifier for this indicator configuration")
    indicator_type: IndicatorType = Field(description="Type of technical indicator")
    parameters: List[IndicatorParameter] = Field(description="Indicator-specific parameters")
    symbol: str = Field(description="Trading symbol (e.g., BTCUSDC)")
    interval: str = Field(description="Time interval (1m, 5m, 15m, 1h, 4h, 1d)")
    periods_required: int = Field(description="Minimum periods of data needed")
    
    # Calculation settings
    output_fields: List[str] = Field(description="Fields to output (e.g., ['sma_20', 'sma_50'])")
    cache_duration_minutes: int = Field(default=5, description="How long to cache results")
    
    # Metadata
    strategy_id: str = Field(description="Strategy that requested this indicator")
    priority: int = Field(default=1, description="Calculation priority (1=high, 5=low)")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    @validator('parameters')
    def validate_parameters(cls, v, values):
        """Validate indicator parameters based on type"""
        indicator_type = values.get('indicator_type')
        
        # Define required parameters for each indicator type
        required_params = {
            IndicatorType.SMA: ['period'],
            IndicatorType.EMA: ['period'],
            IndicatorType.RSI: ['period'],
            IndicatorType.MACD: ['fast_period', 'slow_period', 'signal_period'],
            IndicatorType.BOLLINGER_BANDS: ['period', 'std_dev'],
            IndicatorType.STOCHASTIC: ['k_period', 'd_period'],
            IndicatorType.WILLIAMS_R: ['period'],
            IndicatorType.CCI: ['period'],
            IndicatorType.ATR: ['period'],
            IndicatorType.MOMENTUM: ['period'],
            IndicatorType.ROC: ['period']
        }
        
        if indicator_type in required_params:
            param_names = [p.name for p in v]
            for required in required_params[indicator_type]:
                if required not in param_names:
                    raise ValueError(f"Missing required parameter '{required}' for {indicator_type}")
        
        return v


class IndicatorRequest(BaseModel):
    """Request to calculate indicators for a strategy"""
    strategy_id: str = Field(description="Requesting strategy ID")
    indicators: List[IndicatorConfiguration] = Field(description="List of indicators to calculate")
    symbols: List[str] = Field(description="Symbols to calculate indicators for")
    intervals: List[str] = Field(description="Time intervals to use")
    
    # Request settings
    continuous_calculation: bool = Field(default=True, description="Keep calculating continuously")
    update_frequency_minutes: int = Field(default=1, description="How often to recalculate")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() + "Z"
        }


class IndicatorResult(BaseModel):
    """Result of indicator calculation"""
    configuration_id: str = Field(description="ID of the indicator configuration")
    symbol: str = Field(description="Trading symbol")
    interval: str = Field(description="Time interval")
    timestamp: datetime = Field(description="Calculation timestamp")
    
    # Calculated values
    values: Dict[str, float] = Field(description="Calculated indicator values")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional calculation metadata")
    
    # Status information
    data_points_used: int = Field(description="Number of data points used in calculation")
    calculation_time_ms: float = Field(description="Time taken to calculate in milliseconds")
    cache_hit: bool = Field(default=False, description="Whether result came from cache")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() + "Z"
        }


class BulkIndicatorRequest(BaseModel):
    """Request for multiple indicators across multiple symbols/intervals"""
    strategy_id: str = Field(description="Requesting strategy ID")
    requests: List[IndicatorRequest] = Field(description="List of indicator requests")
    
    # Batch settings
    batch_size: int = Field(default=10, description="Number of calculations per batch")
    parallel_execution: bool = Field(default=True, description="Execute calculations in parallel")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() + "Z"
        }


class IndicatorSubscription(BaseModel):
    """Subscription for continuous indicator updates"""
    subscription_id: str = Field(description="Unique subscription ID")
    strategy_id: str = Field(description="Strategy requesting updates")
    indicators: List[IndicatorConfiguration] = Field(description="Indicators to calculate")
    
    # Delivery settings
    delivery_method: str = Field(default="rabbitmq", description="How to deliver updates (rabbitmq, webhook)")
    delivery_target: str = Field(description="RabbitMQ queue or webhook URL")
    update_frequency_seconds: int = Field(default=60, description="Update frequency")
    
    # Subscription lifecycle
    active: bool = Field(default=True, description="Whether subscription is active")
    expires_at: Optional[datetime] = Field(description="When subscription expires")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() + "Z"
        }


class IndicatorPerformanceMetrics(BaseModel):
    """Performance metrics for indicator calculations"""
    indicator_type: str = Field(description="Type of indicator")
    symbol: str = Field(description="Trading symbol")
    interval: str = Field(description="Time interval")
    
    # Performance data
    avg_calculation_time_ms: float = Field(description="Average calculation time")
    calculations_per_minute: float = Field(description="Calculation throughput")
    cache_hit_ratio: float = Field(description="Percentage of cache hits")
    error_rate: float = Field(description="Percentage of failed calculations")
    
    # Resource usage
    memory_usage_mb: float = Field(description="Memory usage for calculations")
    cpu_usage_percent: float = Field(description="CPU usage percentage")
    
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() + "Z"
        }