"""
Configuration for API Gateway
"""

import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings"""
    
    # Server
    PORT: int = 8080
    HOST: str = "0.0.0.0"
    
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
    POSTGRES_POOL_MAX_SIZE: int = 10
    POSTGRES_SSL_MODE: str = "disable"
    POSTGRES_APPLICATION_NAME: str = "api_gateway"

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
    
    # Security
    JWT_SECRET: str = "your_jwt_secret_key_here"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # Logging
    LOG_LEVEL: str = "INFO"
    
    # Service configuration
    SERVICE_NAME: str = "api_gateway"
    
    class Config:
        env_file = ".env"
        extra = "ignore"  # Ignore extra fields from .env


settings = Settings()