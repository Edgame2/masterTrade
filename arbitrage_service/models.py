"""
Pydantic models for Arbitrage Service
"""

from datetime import datetime
from typing import Dict, List, Optional, Any
from decimal import Decimal

from pydantic import BaseModel, Field


class DEXPrice(BaseModel):
    """DEX price information"""
    pair: str
    dex: str
    chain: str
    price: float = Field(gt=0)
    liquidity: float = Field(ge=0)
    reserve0: Optional[float] = None
    reserve1: Optional[float] = None
    timestamp: datetime


class ArbitrageOpportunity(BaseModel):
    """Arbitrage opportunity model"""
    id: Optional[int] = None
    pair: str
    buy_venue: Dict[str, Any]
    sell_venue: Dict[str, Any]
    buy_price: float = Field(gt=0)
    sell_price: float = Field(gt=0)
    profit_percent: float = Field(ge=0)
    estimated_profit_usd: float
    trade_amount: float = Field(gt=0)
    gas_cost: float = Field(ge=0)
    arbitrage_type: str  # 'cex_dex', 'intra_chain', 'cross_chain', 'triangular'
    timestamp: datetime
    executed: bool = False
    execution_id: Optional[str] = None


class CrossChainRoute(BaseModel):
    """Cross-chain arbitrage route"""
    source_chain: str
    target_chain: str
    bridge_protocol: str
    bridge_fee_percent: float
    estimated_time_minutes: int
    source_token: str
    target_token: str
    route_data: Dict[str, Any]


class FlashLoanOpportunity(BaseModel):
    """Flash loan arbitrage opportunity"""
    id: Optional[int] = None
    protocol: str  # 'aave', 'dydx', 'balancer'
    token: str
    amount: float = Field(gt=0)
    fee_percent: float = Field(ge=0)
    arbitrage_path: List[Dict[str, Any]]
    estimated_profit: float
    gas_estimate: int
    timestamp: datetime


class TriangularArbitrageOpportunity(BaseModel):
    """Triangular arbitrage opportunity within single exchange/DEX"""
    id: Optional[int] = None
    exchange: str
    chain: Optional[str] = None
    path: List[str]  # e.g., ['USDC', 'BTC', 'ETH', 'USDC']
    prices: List[float]
    profit_percent: float = Field(ge=0)
    estimated_profit_usd: float
    base_amount: float = Field(gt=0)
    timestamp: datetime


class ArbitrageExecution(BaseModel):
    """Arbitrage execution record"""
    id: Optional[str] = None
    opportunity_id: int
    execution_type: str
    start_time: datetime
    end_time: Optional[datetime] = None
    status: str = "pending"  # pending, success, failed, partial
    transactions: List[Dict[str, Any]] = Field(default_factory=list)
    actual_profit_usd: Optional[float] = None
    gas_used: Optional[int] = None
    error_message: Optional[str] = None


class GasPrice(BaseModel):
    """Gas price information for different chains"""
    chain: str
    standard_gwei: float = Field(gt=0)
    fast_gwei: float = Field(gt=0)
    instant_gwei: float = Field(gt=0)
    timestamp: datetime


class LiquidityPool(BaseModel):
    """DEX liquidity pool information"""
    address: str
    dex: str
    chain: str
    token0: str
    token1: str
    reserve0: float = Field(ge=0)
    reserve1: float = Field(ge=0)
    total_liquidity_usd: float = Field(ge=0)
    fee_percent: float = Field(ge=0)
    last_updated: datetime


class ArbitrageStats(BaseModel):
    """Arbitrage statistics and performance metrics"""
    total_opportunities: int = 0
    successful_executions: int = 0
    failed_executions: int = 0
    total_profit_usd: float = 0.0
    avg_profit_percent: float = 0.0
    best_opportunity_profit: float = 0.0
    worst_execution_loss: float = 0.0
    success_rate: float = 0.0
    avg_execution_time_seconds: float = 0.0
    total_gas_used: int = 0
    period_start: datetime
    period_end: datetime


class BridgeInfo(BaseModel):
    """Cross-chain bridge information"""
    name: str
    source_chain: str
    target_chain: str
    supported_tokens: List[str]
    fee_percent: float = Field(ge=0)
    min_amount: float = Field(gt=0)
    max_amount: float = Field(gt=0)
    estimated_time_minutes: int = Field(gt=0)
    reliability_score: float = Field(ge=0, le=1)  # 0-1 reliability score


class MEVOpportunity(BaseModel):
    """Miner Extractable Value opportunity"""
    id: Optional[int] = None
    opportunity_type: str  # 'sandwich', 'arbitrage', 'liquidation'
    target_tx_hash: Optional[str] = None
    block_number: Optional[int] = None
    estimated_profit: float
    gas_bid: int
    priority_fee: float
    execution_strategy: Dict[str, Any]
    timestamp: datetime
    executed: bool = False