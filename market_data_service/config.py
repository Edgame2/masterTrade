"""
Configuration settings for Market Data Service with Historical Data, Real-time Data, and Sentiment Analysis

Enhanced with Azure Key Vault integration for secure secret management
"""

import os
import asyncio
from typing import List, Dict, Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings with Azure Key Vault integration"""
    
    # Azure Key Vault Configuration
    AZURE_KEY_VAULT_URL: str = ""  # Key Vault URL for secret management
    AZURE_KEY_VAULT_NAME: str = ""  # Key Vault name (alternative to URL)
    USE_KEY_VAULT: bool = False  # Disable Key Vault for local development
    
    # PostgreSQL Configuration (Local default overrides legacy Cosmos settings)
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "mastertrade"
    POSTGRES_PASSWORD: str = "mastertrade"
    POSTGRES_DB: str = "mastertrade"
    POSTGRES_POOL_MIN_SIZE: int = 1
    POSTGRES_POOL_MAX_SIZE: int = 20
    POSTGRES_SSL_MODE: str = "disable"
    POSTGRES_APPLICATION_NAME: str = "market_data_service"

    # Legacy Cosmos DB Configuration (kept for backward compatibility only)
    COSMOS_CONTAINER: str = "market_data"
    USE_MANAGED_IDENTITY: bool = False  # Use key-based auth for development
    MANAGED_IDENTITY_CLIENT_ID: str = ""  # Use Managed Identity in production
    TTL_SECONDS: int = 2592000  # 30 days data retention
    
    # RabbitMQ Configuration
    RABBITMQ_URL: str = "amqp://admin:password123@rabbitmq:5672/"
    
    # Binance API Configuration
    BINANCE_API_KEY: str = ""
    BINANCE_API_SECRET: str = ""
    BINANCE_WSS_URL: str = "wss://stream.binance.com:9443/ws/"
    BINANCE_REST_API_URL: str = "https://api.binance.com"
    
    # Historical Data Configuration
    HISTORICAL_DATA_DAYS: int = 365  # Days of historical data to fetch initially
    HISTORICAL_INTERVALS: List[str] = ["1m", "5m", "15m", "1h", "4h", "1d"]
    HISTORICAL_BATCH_SIZE: int = 1000  # Records per batch for historical import
    
    # Trading Symbols Configuration
    DEFAULT_SYMBOLS: List[str] = [
        "BTCUSDC", "ETHUSDC", "ADAUSDC", "SOLUSDC", "DOTUSDC",
        "LINKUSDC", "AVAXUSDC", "MATICUSDC", "ATOMUSDC", "LTCUSDC",
        "BNBUSDC", "XRPUSDC", "UNIUSDC", "AAVEUSDC", "SUSHIUSDC"
    ]
    
    # Real-time WebSocket Configuration
    WS_RECONNECT_INTERVAL: int = 5  # seconds
    WS_MAX_RECONNECT_ATTEMPTS: int = 10
    WS_PING_INTERVAL: int = 30  # seconds
    WS_STREAM_TYPES: List[str] = ["kline", "ticker", "depth", "trades"]
    
    # Stock Index Data Configuration
    STOCK_INDEX_ENABLED: bool = True
    STOCK_INDEX_UPDATE_INTERVAL: int = 900  # seconds (15 minutes during market hours)
    STOCK_INDEX_HISTORICAL_DAYS: int = 365
    
    # Stock Index Data Sources
    ALPHA_VANTAGE_API_KEY: str = ""  # Alpha Vantage API key for stock data
    YAHOO_FINANCE_ENABLED: bool = True  # Yahoo Finance as backup/primary source
    FINNHUB_API_KEY: str = ""  # Finnhub API key for additional data
    
    # Macro Economic Data Sources
    FRED_API_KEY: str = ""
    FRED_API_URL: str = "https://api.stlouisfed.org/fred"
    
    # On-Chain Data Sources
    MORALIS_API_KEY: str = ""
    MORALIS_API_URL: str = "https://deep-index.moralis.io/api/v2.2"
    MORALIS_RATE_LIMIT: float = 3.0  # requests per second (free tier: 3 req/s)
    
    GLASSNODE_API_KEY: str = ""
    GLASSNODE_API_URL: str = "https://api.glassnode.com"
    GLASSNODE_RATE_LIMIT: float = 1.0  # requests per second (varies by tier)
    
    NANSEN_API_KEY: str = ""
    NANSEN_API_URL: str = "https://api.nansen.ai"
    NANSEN_RATE_LIMIT: float = 2.0  # requests per second
    
    # On-Chain Collection Configuration
    ONCHAIN_COLLECTION_ENABLED: bool = False  # Enable on-chain data collection
    ONCHAIN_COLLECTION_INTERVAL: int = 3600  # Collection interval in seconds (1 hour)
    ONCHAIN_WHALE_THRESHOLD_BTC: float = 1000.0  # BTC threshold for whale detection
    ONCHAIN_WHALE_THRESHOLD_ETH: float = 10000.0  # ETH threshold for whale detection
    ONCHAIN_WHALE_THRESHOLD_USD: float = 1000000.0  # USD threshold for whale detection
    
    # Social Media Data Sources
    TWITTER_API_KEY: str = ""
    TWITTER_API_SECRET: str = ""
    TWITTER_BEARER_TOKEN: str = ""
    TWITTER_RATE_LIMIT: float = 1.0  # requests per second (Basic tier: 300/15min = 0.33/s)
    
    REDDIT_CLIENT_ID: str = ""
    REDDIT_CLIENT_SECRET: str = ""
    REDDIT_USER_AGENT: str = "MasterTrade/1.0"
    REDDIT_RATE_LIMIT: float = 0.5  # requests per second (60/min = 1/s, we use 0.5 to be safe)
    
    LUNARCRUSH_API_KEY: str = ""
    LUNARCRUSH_API_URL: str = "https://api.lunarcrush.com/v2"
    LUNARCRUSH_RATE_LIMIT: float = 0.2  # requests per second (free tier limited)
    
    # Social Collection Configuration
    SOCIAL_COLLECTION_ENABLED: bool = False  # Enable social sentiment collection
    SOCIAL_COLLECTION_INTERVAL: int = 3600  # Collection interval in seconds (1 hour)
    SOCIAL_USE_FINBERT: bool = False  # Use FinBERT for sentiment analysis (requires transformers)
    SOCIAL_MIN_ENGAGEMENT: int = 10  # Minimum engagement score to store post
    
    # Redis Configuration
    REDIS_URL: str = "redis://localhost:6379"
    REDIS_MAX_CONNECTIONS: int = 50
    
    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"  # Ignore extra fields from .env
    
    # Major Stock Indices to Track
    STOCK_INDICES: List[str] = [
        "^GSPC",    # S&P 500
        "^IXIC",    # NASDAQ Composite
        "^DJI",     # Dow Jones Industrial Average
        "^RUT",     # Russell 2000
        "^VIX",     # CBOE Volatility Index
        "^TNX",     # 10-Year Treasury Yield
        "^FTSE",    # FTSE 100 (UK)
        "^GDAXI",   # DAX (Germany)
        "^N225",    # Nikkei 225 (Japan)
        "^HSI",     # Hang Seng Index (Hong Kong)
        "000001.SS", # Shanghai Composite (China)
        "^BVSP"     # Bovespa (Brazil)
    ]
    
    # Index Categories for Analysis
    STOCK_INDEX_CATEGORIES: Dict[str, List[str]] = {
        "us_major": ["^GSPC", "^IXIC", "^DJI", "^RUT"],
        "us_indicators": ["^VIX", "^TNX"],
        "international": ["^FTSE", "^GDAXI", "^N225", "^HSI", "000001.SS", "^BVSP"],
        "volatility": ["^VIX"],
        "bonds": ["^TNX"]
    }
    
    # Sentiment Analysis Configuration
    SENTIMENT_ENABLED: bool = True
    SENTIMENT_UPDATE_INTERVAL: int = 3600  # seconds (1 hour)
    
    # News and Social Media APIs for Sentiment
    NEWS_API_KEY: str = ""  # NewsAPI.org key
    TWITTER_BEARER_TOKEN: str = ""  # Twitter API v2 Bearer token
    REDDIT_CLIENT_ID: str = ""  # Reddit API credentials
    REDDIT_CLIENT_SECRET: str = ""
    REDDIT_USER_AGENT: str = "TradingBotSentiment/1.0"  # Reddit API user agent
    FEAR_GREED_API_URL: str = "https://api.alternative.me/fng/"
    
    # Sentiment Data Sources
    SENTIMENT_SOURCES: Dict[str, bool] = {
        "fear_greed_index": True,  # Crypto Fear & Greed Index
        "news_sentiment": True,   # Financial news sentiment
        "social_sentiment": True, # Twitter/Reddit sentiment
        "market_sentiment": True  # Overall market indicators
    }
    
    # Sentiment Keywords for Crypto Analysis
    CRYPTO_SENTIMENT_KEYWORDS: Dict[str, List[str]] = {
        "BTC": ["bitcoin", "btc", "$btc", "cryptocurrency", "digital gold"],
        "ETH": ["ethereum", "eth", "$eth", "smart contracts", "defi"],
        "ADA": ["cardano", "ada", "$ada", "proof of stake"],
        "SOL": ["solana", "sol", "$sol", "web3", "nft"],
        "DOT": ["polkadot", "dot", "$dot", "parachain"],
        "LINK": ["chainlink", "link", "$link", "oracle"],
        "AVAX": ["avalanche", "avax", "$avax"],
        "MATIC": ["polygon", "matic", "$matic", "layer 2"],
        "ATOM": ["cosmos", "atom", "$atom"],
        "LTC": ["litecoin", "ltc", "$ltc"]
    }
    
    # Logging Configuration
    LOG_LEVEL: str = "INFO"
    
    # Service Configuration
    SERVICE_NAME: str = "market_data_service"
    PROMETHEUS_PORT: int = 9001  # Changed from 8001 to avoid conflict with strategy service
    DATA_ACCESS_API_PORT: int = 8005
    
    class Config:
        env_file = "/home/neodyme/Documents/Projects/masterTrade/.env"  # Absolute path to .env
        extra = "ignore"  # Ignore extra fields from .env
        
    @property
    def POSTGRES_DSN(self) -> str:
        """Build the PostgreSQL DSN using current configuration."""
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

    async def load_from_keyvault(self):
        """Load configuration from Azure Key Vault if enabled"""
        if not self.USE_KEY_VAULT:
            return
            
        try:
            from key_vault_config import load_secrets_from_keyvault
            
            # Load secrets from Key Vault
            kv_secrets = await load_secrets_from_keyvault()
            
            # Update configuration with Key Vault values
            if kv_secrets:
                for key, value in kv_secrets.items():
                    if hasattr(self, key) and value:  # Only update if we have a value
                        setattr(self, key, value)
                        
                print(f"✅ Loaded {len(kv_secrets)} configuration values from Key Vault")
            else:
                print("⚠️  Key Vault not available, using environment variables")
                
        except Exception as e:
            print(f"❌ Error loading from Key Vault: {e}")
            print("📝 Falling back to environment variables")


# Create settings instance
settings = Settings()

# Function to initialize settings with Key Vault
async def initialize_settings():
    """Initialize settings with Key Vault integration"""
    await settings.load_from_keyvault()
    return settings