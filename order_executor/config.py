"""
Configuration settings for Order Executor Service
"""

import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings"""
    
    # Azure Key Vault Configuration
    AZURE_KEY_VAULT_URL: str = ""
    USE_KEY_VAULT: bool = True
    
    # Azure Authentication
    AZURE_CLIENT_ID: str = ""
    AZURE_CLIENT_SECRET: str = ""
    AZURE_TENANT_ID: str = ""
    
    # PostgreSQL Configuration
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "mastertrade"
    POSTGRES_PASSWORD: str = "mastertrade"
    POSTGRES_DB: str = "mastertrade"
    POSTGRES_POOL_MIN_SIZE: int = 1
    POSTGRES_POOL_MAX_SIZE: int = 20
    POSTGRES_SSL_MODE: str = "disable"
    POSTGRES_APPLICATION_NAME: str = "order_executor"

    # Legacy Cosmos DB Configuration (retained for compatibility only)
    MANAGED_IDENTITY_CLIENT_ID: str = ""

    @property

    @property
    def USE_MANAGED_IDENTITY(self) -> bool:
        return False
    
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
    
    # RabbitMQ
    RABBITMQ_URL: str = "amqp://mastertrade:password@localhost:5672/"
    
    # Binance Production API
    BINANCE_API_KEY: str = ""
    BINANCE_API_SECRET: str = ""
    
    # Binance Testnet API
    BINANCE_TESTNET_API_KEY: str = ""
    BINANCE_TESTNET_API_SECRET: str = ""
    
    # Exchange Configuration
    EXCHANGE_SANDBOX: bool = True  # Default to sandbox for testing
    DEFAULT_EXCHANGE_ENVIRONMENT: str = "testnet"  # testnet or production
    
    # Logging
    LOG_LEVEL: str = "INFO"
    
    # Service configuration
    SERVICE_NAME: str = "order_executor"
    PROMETHEUS_PORT: int = 8002
    STRATEGY_SERVICE_URL: str = "http://localhost:8001"
    
    # Order management
    ORDER_MONITOR_INTERVAL: int = 5  # seconds
    MAX_RETRY_ATTEMPTS: int = 3
    ORDER_TIMEOUT_MINUTES: int = 30
    
    # Risk limits
    MAX_ORDER_SIZE: float = 1000.0
    MIN_ORDER_SIZE: float = 10.0
    
    class Config:
        env_file = ".env"
        extra = "ignore"  # Ignore extra fields from .env


settings = Settings()