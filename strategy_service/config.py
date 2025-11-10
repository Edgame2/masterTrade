"""
Configuration settings for Strategy Service
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
    
    # PostgreSQL Configuration (primary datastore)
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "mastertrade"
    POSTGRES_PASSWORD: str = "mastertrade"
    POSTGRES_DB: str = "mastertrade"
    POSTGRES_POOL_MIN_SIZE: int = 1
    POSTGRES_POOL_MAX_SIZE: int = 20
    POSTGRES_SSL_MODE: str = "disable"
    POSTGRES_APPLICATION_NAME: str = "strategy_service"

    # Legacy Cosmos DB configuration retained for backward compatibility only
    MANAGED_IDENTITY_CLIENT_ID: str = ""

    @property

    @property
    def USE_MANAGED_IDENTITY(self) -> bool:
        """Maintain backwards compatibility with legacy configuration."""
        return False
    
    # RabbitMQ
    RABBITMQ_URL: str = "amqp://mastertrade:password@localhost:5672/"
    
    # Logging
    LOG_LEVEL: str = "INFO"
    
    # Service configuration
    SERVICE_NAME: str = "strategy_service"
    PROMETHEUS_PORT: int = 8001
    
    # Strategy configuration
    DEFAULT_LOOKBACK_PERIOD: int = 100
    MIN_DATA_POINTS: int = 20
    SIGNAL_COOLDOWN_SECONDS: int = 300  # 5 minutes
    
    # AI/ML Configuration
    # Model Configuration
    TRANSFORMER_MODEL_DIM: int = 512
    TRANSFORMER_NUM_HEADS: int = 8
    TRANSFORMER_NUM_LAYERS: int = 6
    TRANSFORMER_SEQUENCE_LENGTH: int = 128
    PREDICTION_HORIZON: int = 24  # hours
    
    # Training Configuration  
    BATCH_SIZE: int = 64
    LEARNING_RATE: float = 3e-4
    NUM_EPOCHS: int = 100
    EARLY_STOPPING_PATIENCE: int = 10
    GRADIENT_CLIP_NORM: float = 1.0
    
    # RL Agent Configuration
    RL_BUFFER_SIZE: int = 100000
    RL_UPDATE_FREQUENCY: int = 4
    RL_TARGET_UPDATE_FREQUENCY: int = 1000
    RL_EPSILON_DECAY: float = 0.995
    RL_GAMMA: float = 0.99
    
    # Strategy Generation
    GP_POPULATION_SIZE: int = 200
    GP_GENERATIONS: int = 50
    GP_MUTATION_RATE: float = 0.1
    GP_CROSSOVER_RATE: float = 0.8
    MAX_WORKERS: int = 8
    
    # Optimization
    OPTIMIZATION_TRIALS_PER_STRATEGY: int = 100
    MAX_OPTIMIZATION_CONCURRENT: int = 4
    BAYESIAN_OPT_N_INITIAL_POINTS: int = 20
    
    # Performance Thresholds
    MIN_STRATEGY_SHARPE_RATIO: float = 1.2
    MAX_STRATEGY_DRAWDOWN: float = 0.15
    MIN_STRATEGY_TRADES: int = 50
    MIN_ACTIVE_STRATEGIES: int = 1000
    MIN_SIGNAL_STRENGTH: float = 0.6
    
    # Model Paths
    MODEL_SAVE_PATH: str = "/app/models"
    CHECKPOINT_FREQUENCY: int = 100  # episodes
    
    # Data Configuration
    FEATURE_LOOKBACK_PERIODS: int = 252  # trading days
    TECHNICAL_INDICATORS_COUNT: int = 50
    SENTIMENT_DATA_SOURCES: list = ["twitter", "reddit", "news"]
    MACRO_INDICATORS: list = ["DXY", "VIX", "TNX", "GLD"]
    
    class Config:
        env_file = "/home/neodyme/Documents/Projects/masterTrade/.env"  # Absolute path to .env
        extra = "ignore"  # Ignore extra fields from .env

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


settings = Settings()