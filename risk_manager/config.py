"""
Risk Management Service Configuration

This module defines configuration settings for the risk management service
including position sizing, stop-loss parameters, and portfolio limits.
"""

import os
from typing import Optional, List
from pydantic_settings import BaseSettings
from pydantic import validator
import structlog

logger = structlog.get_logger()

class RiskManagementSettings(BaseSettings):
    """Risk Management Service Configuration"""
    
    # Service Configuration
    SERVICE_NAME: str = "risk_manager"
    HOST: str = "0.0.0.0"
    PORT: int = 8003
    STRATEGY_SERVICE_URL: str = "http://localhost:8001"
    
    # PostgreSQL Configuration (primary datastore)
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "mastertrade"
    POSTGRES_PASSWORD: str = "mastertrade"
    POSTGRES_DB: str = "mastertrade"
    POSTGRES_POOL_MIN_SIZE: int = 1
    POSTGRES_POOL_MAX_SIZE: int = 20
    POSTGRES_SSL_MODE: str = "disable"
    POSTGRES_APPLICATION_NAME: str = "risk_manager"

    # Legacy Cosmos DB Configuration (retained for compatibility)
    
    # Azure Key Vault Configuration (for secure secret management)
    AZURE_KEY_VAULT_URL: str = ""
    USE_KEY_VAULT: bool = True
    AZURE_CLIENT_ID: str = ""
    AZURE_CLIENT_SECRET: str = ""
    AZURE_TENANT_ID: str = ""
    
    # RabbitMQ Configuration
    RABBITMQ_URL: str = "amqp://guest:guest@localhost:5672/"
    RABBITMQ_EXCHANGE: str = "mastertrade.risk"
    
    # Portfolio Risk Settings
    MAX_PORTFOLIO_RISK_PERCENT: float = 10.0  # Maximum portfolio risk exposure
    MAX_SINGLE_POSITION_PERCENT: float = 5.0  # Maximum single position size
    MAX_SECTOR_EXPOSURE_PERCENT: float = 25.0  # Maximum sector concentration
    MAX_CORRELATION_EXPOSURE: float = 0.7     # Maximum correlation between positions
    
    # Position Sizing Settings
    DEFAULT_RISK_PER_TRADE: float = 2.0       # Default risk per trade (% of account)
    MIN_POSITION_SIZE_USD: float = 10.0       # Minimum position size
    MAX_POSITION_SIZE_USD: float = 10000.0    # Maximum position size
    VOLATILITY_LOOKBACK_DAYS: int = 20        # Days for volatility calculation
    
    # Stop-Loss Settings
    DEFAULT_STOP_LOSS_PERCENT: float = 2.0    # Default stop-loss percentage
    MAX_STOP_LOSS_PERCENT: float = 10.0       # Maximum allowed stop-loss
    MIN_STOP_LOSS_PERCENT: float = 0.5        # Minimum stop-loss
    TRAILING_STOP_ACTIVATION: float = 1.5     # Activation threshold for trailing stops
    TRAILING_STOP_DISTANCE: float = 1.0       # Trailing stop distance
    
    # Risk Assessment Settings
    RISK_SCORE_THRESHOLD: float = 7.0         # Risk score threshold for approval
    VOLATILITY_RISK_MULTIPLIER: float = 1.5   # Volatility risk adjustment
    LIQUIDITY_RISK_MULTIPLIER: float = 1.2    # Liquidity risk adjustment
    
    # Account Balance Settings (will be fetched from exchange)
    MIN_ACCOUNT_BALANCE: float = 1000.0       # Minimum account balance to trade
    RESERVE_BALANCE_PERCENT: float = 10.0     # Reserve balance percentage
    
    # Risk Monitoring Settings
    PORTFOLIO_CHECK_INTERVAL: int = 300       # Portfolio check interval in seconds
    RISK_ALERT_THRESHOLD: float = 8.0         # Risk alert threshold
    MAX_DAILY_LOSS_PERCENT: float = 5.0       # Maximum daily loss threshold
    MAX_DRAWDOWN_PERCENT: float = 15.0        # Maximum drawdown threshold
    
    # Market Conditions Adjustments
    HIGH_VOLATILITY_THRESHOLD: float = 0.05   # High volatility threshold (5%)
    LOW_LIQUIDITY_THRESHOLD: float = 100000   # Low liquidity threshold (USD)
    MARKET_HOURS_RISK_REDUCTION: float = 0.8  # Risk reduction during off-hours
    
    # Advanced Risk Features
    ENABLE_CORRELATION_LIMITS: bool = True    # Enable correlation-based limits
    ENABLE_VAR_CALCULATION: bool = True       # Enable Value at Risk calculation
    VAR_CONFIDENCE_LEVEL: float = 0.95        # VaR confidence level
    VAR_LOOKBACK_DAYS: int = 252              # VaR calculation lookback period
    
    # Emergency Controls
    EMERGENCY_STOP_ENABLED: bool = True       # Enable emergency stop functionality
    MAX_CONSECUTIVE_LOSSES: int = 5           # Maximum consecutive losses before pause
    CIRCUIT_BREAKER_LOSS_PERCENT: float = 3.0 # Circuit breaker activation threshold
    
    # Logging and Monitoring
    LOG_LEVEL: str = "INFO"
    ENABLE_RISK_METRICS: bool = True
    RISK_REPORT_INTERVAL: int = 3600          # Risk report interval in seconds
    
    # Exchange Integration
    EXCHANGE_TYPE: str = "binance"            # Primary exchange for balance checks
    ENABLE_MULTI_EXCHANGE_RISK: bool = False  # Multi-exchange risk management
    
    # Position Limits by Asset Class
    CRYPTO_MAX_POSITION_PERCENT: float = 5.0
    STABLECOIN_MAX_POSITION_PERCENT: float = 20.0
    DEFI_MAX_POSITION_PERCENT: float = 3.0
    
    # Risk Model Configuration
    RISK_MODEL_TYPE: str = "advanced"         # "simple", "intermediate", "advanced"
    ENABLE_MACHINE_LEARNING_RISK: bool = False # ML-based risk assessment
    RISK_MODEL_UPDATE_INTERVAL: int = 86400   # Risk model update interval
    
    class Config:
        env_file = ".env"
        case_sensitive = True

    @property
    def POSTGRES_DSN(self) -> str:
        base = (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )
        params = []
        if self.POSTGRES_SSL_MODE and self.POSTGRES_SSL_MODE.lower() != "disable":
            params.append(f"sslmode={self.POSTGRES_SSL_MODE}")
        if self.POSTGRES_APPLICATION_NAME:
            params.append(f"application_name={self.POSTGRES_APPLICATION_NAME}")
        if params:
            return f"{base}?{'&'.join(params)}"
        return base
    
    @validator('MAX_PORTFOLIO_RISK_PERCENT')
    def validate_portfolio_risk(cls, v):
        if v <= 0 or v > 50:
            raise ValueError('Portfolio risk must be between 0 and 50%')
        return v
    
    @validator('DEFAULT_RISK_PER_TRADE')
    def validate_trade_risk(cls, v):
        if v <= 0 or v > 10:
            raise ValueError('Risk per trade must be between 0 and 10%')
        return v
    
    @validator('VAR_CONFIDENCE_LEVEL')
    def validate_var_confidence(cls, v):
        if v <= 0 or v >= 1:
            raise ValueError('VaR confidence level must be between 0 and 1')
        return v

# Create global settings instance
settings = RiskManagementSettings()

# Asset classification for risk management
ASSET_CLASSES = {
    'CRYPTO': ['BTC', 'ETH', 'BNB', 'ADA', 'DOT', 'LINK', 'UNI', 'AAVE'],
    'STABLECOIN': ['USDT', 'USDC', 'BUSD', 'DAI', 'UST'],
    'DEFI': ['UNI', 'SUSHI', 'COMP', 'AAVE', 'YFI', 'CRV', '1INCH'],
    'LAYER1': ['ETH', 'BNB', 'ADA', 'DOT', 'SOL', 'AVAX', 'NEAR'],
    'LAYER2': ['MATIC', 'LRC', 'IMX', 'METIS'],
    'MEME': ['DOGE', 'SHIB', 'FLOKI', 'PEPE']
}

# Risk multipliers by asset class
RISK_MULTIPLIERS = {
    'CRYPTO': 1.0,
    'STABLECOIN': 0.2,
    'DEFI': 1.5,
    'LAYER1': 1.2,
    'LAYER2': 1.8,
    'MEME': 2.5
}

# Correlation groups for risk management
CORRELATION_GROUPS = {
    'MAJOR_CRYPTO': ['BTC', 'ETH', 'BNB'],
    'DEFI_TOKENS': ['UNI', 'SUSHI', 'AAVE', 'COMP', 'YFI'],
    'LAYER1_ALTS': ['ADA', 'DOT', 'SOL', 'AVAX'],
    'STABLECOINS': ['USDT', 'USDC', 'BUSD', 'DAI']
}

def get_asset_class(symbol: str) -> str:
    """Get asset class for a given symbol"""
    for asset_class, symbols in ASSET_CLASSES.items():
        if symbol in symbols:
            return asset_class
    return 'CRYPTO'  # Default classification

def get_risk_multiplier(symbol: str) -> float:
    """Get risk multiplier for a given symbol"""
    asset_class = get_asset_class(symbol)
    return RISK_MULTIPLIERS.get(asset_class, 1.0)

def get_correlation_group(symbol: str) -> Optional[str]:
    """Get correlation group for a given symbol"""
    for group, symbols in CORRELATION_GROUPS.items():
        if symbol in symbols:
            return group
    return None

# Risk assessment configuration
RISK_FACTORS = {
    'VOLATILITY_WEIGHT': 0.25,
    'LIQUIDITY_WEIGHT': 0.20,
    'CORRELATION_WEIGHT': 0.15,
    'MARKET_CONDITIONS_WEIGHT': 0.15,
    'POSITION_SIZE_WEIGHT': 0.10,
    'TIME_WEIGHT': 0.10,
    'TECHNICAL_WEIGHT': 0.05
}

# Market condition classifications
MARKET_CONDITIONS = {
    'BULL_MARKET': {'risk_multiplier': 0.8, 'max_leverage': 2.0},
    'BEAR_MARKET': {'risk_multiplier': 1.5, 'max_leverage': 1.0},
    'SIDEWAYS': {'risk_multiplier': 1.0, 'max_leverage': 1.5},
    'HIGH_VOLATILITY': {'risk_multiplier': 2.0, 'max_leverage': 1.0},
    'LOW_VOLATILITY': {'risk_multiplier': 0.9, 'max_leverage': 1.8}
}