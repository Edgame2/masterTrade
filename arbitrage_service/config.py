"""
Configuration settings for Arbitrage Service
"""

import os
from typing import List
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
    POSTGRES_POOL_MAX_SIZE: int = 10
    POSTGRES_SSL_MODE: str = "disable"
    POSTGRES_APPLICATION_NAME: str = "arbitrage_service"

    # Legacy Cosmos DB Configuration
    MANAGED_IDENTITY_CLIENT_ID: str = ""

    # Computed Cosmos DB properties retained for compatibility
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
    
    # Blockchain RPC URLs
    GNOSIS_RPC_URL: str = "https://rpc.gnosischain.com"
    ETHEREUM_RPC_URL: str = "https://mainnet.infura.io/v3/YOUR_PROJECT_ID"
    POLYGON_RPC_URL: str = "https://polygon-rpc.com"
    ARBITRUM_RPC_URL: str = "https://arb1.arbitrum.io/rpc"
    BSC_RPC_URL: str = "https://bsc-dataseed1.binance.org"
    
    # Exchange API Keys
    BINANCE_API_KEY: str = ""
    BINANCE_API_SECRET: str = ""
    COINBASE_API_KEY: str = ""
    COINBASE_API_SECRET: str = ""
    COINBASE_PASSPHRASE: str = ""
    KRAKEN_API_KEY: str = ""
    KRAKEN_API_SECRET: str = ""
    
    # DEX Contract Addresses
    # Gnosis Chain
    HONEYSWAP_FACTORY_ADDRESS: str = "0xA818b4F111Ccac7AA31D0BCc0806d64F2E0737D7"
    SUSHISWAP_GNOSIS_FACTORY: str = "0xc35DADB65012eC5796536bD9864eD8773aBc74C4"
    
    # Ethereum
    UNISWAP_V2_FACTORY: str = "0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f"
    UNISWAP_V3_FACTORY: str = "0x1F98431c8aD98523631AE4a59f267346ea31F984"
    SUSHISWAP_FACTORY: str = "0xC0AEe478e3658e2610c5F7A4A2E1777cE9e4f2Ac"
    
    # Polygon
    QUICKSWAP_FACTORY: str = "0x5757371414417b8C6CAad45bAeF941aBc7d3Ab32"
    SUSHISWAP_POLYGON_FACTORY: str = "0xc35DADB65012eC5796536bD9864eD8773aBc74C4"
    
    # Wallet Configuration
    PRIVATE_KEY: str = ""  # For executing transactions
    WALLET_ADDRESS: str = ""
    
    # Arbitrage Parameters
    ARBITRAGE_PAIRS: List[str] = [
        "WETH/USDC", "WETH/USDC", "WETH/DAI",
        "WBTC/USDC", "WBTC/USDC", "WBTC/WETH",
        "GNO/WETH", "GNO/USDC",  # Gnosis specific
        "MATIC/USDC", "MATIC/WETH",
    ]
    
    # Profit Thresholds
    MIN_ARBITRAGE_PROFIT_PERCENT: float = 0.5  # Minimum 0.5% profit
    MIN_ARBITRAGE_PROFIT_USD: float = 10.0  # Minimum $10 profit after costs
    AUTO_EXECUTE_MIN_PROFIT: float = 50.0  # Auto-execute if profit > $50
    AUTO_EXECUTE_MIN_PERCENT: float = 1.0  # Auto-execute if > 1% profit
    
    # Update Intervals
    CEX_PRICE_UPDATE_INTERVAL: int = 5  # seconds
    DEX_PRICE_UPDATE_INTERVAL: int = 10  # seconds
    GAS_PRICE_UPDATE_INTERVAL: int = 30  # seconds
    
    # Transaction Limits
    MAX_TRADE_AMOUNT_USD: float = 10000.0
    MAX_GAS_PRICE_GWEI: float = 50.0
    SLIPPAGE_TOLERANCE: float = 0.5  # 0.5%
    
    # Flash Loan Settings
    AAVE_POOL_ADDRESS: str = "0x794a61358D6845594F94dc1DB02A252b5b4814aD"  # Mainnet
    DYDX_SOLO_MARGIN: str = "0x1E0447b19BB6EcFdAe1e4AE1694b0C3659614e4e"  # Mainnet
    
    # Service Configuration
    SERVICE_NAME: str = "arbitrage_service"
    PROMETHEUS_PORT: int = 8004
    LOG_LEVEL: str = "INFO"
    EXCHANGE_SANDBOX: bool = True
    
    # Risk Management
    MAX_CONCURRENT_ARBITRAGES: int = 5
    EMERGENCY_STOP_LOSS_PERCENT: float = 5.0
    
    class Config:
        env_file = ".env"


settings = Settings()