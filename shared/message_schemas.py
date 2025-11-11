"""
Message Schemas for MasterTrade System

This module defines Pydantic models for all RabbitMQ messages exchanged between services.
These schemas ensure type safety, validation, and consistent data structures across the system.

Message Types:
- Whale Alerts: Large transaction notifications
- Social Sentiment: Twitter/Reddit sentiment updates
- On-Chain Metrics: NVT, MVRV, exchange flows
- Institutional Flow: Block trades, unusual volume
- Market Signals: Aggregated signals for strategy decisions
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field, validator


# ============================================================================
# Enums for Message Types
# ============================================================================

class AlertType(str, Enum):
    """Types of whale alerts"""
    LARGE_TRANSFER = "large_transfer"
    EXCHANGE_INFLOW = "exchange_inflow"
    EXCHANGE_OUTFLOW = "exchange_outflow"
    WHALE_ACCUMULATION = "whale_accumulation"
    WHALE_DISTRIBUTION = "whale_distribution"
    SMART_MONEY_MOVE = "smart_money_move"


class SentimentSource(str, Enum):
    """Sources of sentiment data"""
    TWITTER = "twitter"
    REDDIT = "reddit"
    LUNARCRUSH = "lunarcrush"
    NEWS = "news"
    FEAR_GREED_INDEX = "fear_greed_index"


class FlowType(str, Enum):
    """Types of institutional flow"""
    BLOCK_TRADE = "block_trade"
    UNUSUAL_VOLUME = "unusual_volume"
    DARK_POOL = "dark_pool"
    LARGE_SWEEP = "large_sweep"


class SignalStrength(str, Enum):
    """Signal strength levels"""
    WEAK = "weak"
    MODERATE = "moderate"
    STRONG = "strong"
    VERY_STRONG = "very_strong"


class TrendDirection(str, Enum):
    """Trend direction"""
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


# ============================================================================
# Whale Alert Messages
# ============================================================================

class WhaleAlertMessage(BaseModel):
    """
    Whale alert notification for large cryptocurrency transactions
    
    Triggered when:
    - Transaction > $1M USD
    - Wallet with > 1000 BTC/10000 ETH moves funds
    - Exchange inflows/outflows exceeding thresholds
    """
    alert_id: str = Field(..., description="Unique alert identifier")
    alert_type: AlertType = Field(..., description="Type of whale alert")
    symbol: str = Field(..., description="Cryptocurrency symbol (e.g., BTC, ETH)")
    amount: float = Field(..., description="Amount in native currency")
    amount_usd: float = Field(..., description="Amount in USD")
    
    from_address: Optional[str] = Field(None, description="Source wallet address")
    to_address: Optional[str] = Field(None, description="Destination wallet address")
    from_entity: Optional[str] = Field(None, description="Source entity (e.g., Binance, Unknown)")
    to_entity: Optional[str] = Field(None, description="Destination entity")
    
    transaction_hash: Optional[str] = Field(None, description="Blockchain transaction hash")
    blockchain: str = Field(..., description="Blockchain network (e.g., ethereum, bitcoin)")
    
    significance_score: float = Field(..., ge=0, le=1, description="Alert significance (0-1)")
    market_impact_estimate: Optional[float] = Field(None, description="Estimated price impact percentage")
    
    timestamp: datetime = Field(..., description="Transaction timestamp")
    detected_at: datetime = Field(default_factory=datetime.utcnow, description="Detection timestamp")
    
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional metadata")
    
    class Config:
        json_schema_extra = {
            "example": {
                "alert_id": "whale_20251111_001",
                "alert_type": "exchange_outflow",
                "symbol": "BTC",
                "amount": 1000.5,
                "amount_usd": 50025000.0,
                "from_address": "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb",
                "to_address": "0x8315177aB297bA92A06054cE80a67Ed4DBd7ed3a",
                "from_entity": "Binance",
                "to_entity": "Unknown Wallet",
                "transaction_hash": "0x1234567890abcdef",
                "blockchain": "ethereum",
                "significance_score": 0.85,
                "market_impact_estimate": -0.5,
                "timestamp": "2025-11-11T10:30:00Z"
            }
        }


# ============================================================================
# Social Sentiment Messages
# ============================================================================

class SocialSentimentUpdate(BaseModel):
    """
    Social sentiment update from Twitter, Reddit, or aggregators
    
    Provides real-time sentiment analysis for cryptocurrency discussions
    """
    update_id: str = Field(..., description="Unique update identifier")
    source: SentimentSource = Field(..., description="Sentiment data source")
    symbol: str = Field(..., description="Cryptocurrency symbol")
    
    sentiment_score: float = Field(..., ge=-1, le=1, description="Sentiment score (-1 to 1)")
    sentiment_label: str = Field(..., description="Human-readable label (e.g., 'Very Bullish')")
    
    social_volume: int = Field(..., ge=0, description="Number of mentions/posts")
    engagement_count: int = Field(default=0, description="Likes, retweets, upvotes, etc.")
    
    influencer_sentiment: Optional[float] = Field(None, description="Weighted sentiment from key influencers")
    sentiment_change_24h: Optional[float] = Field(None, description="24h sentiment change")
    
    trending: bool = Field(default=False, description="Is currently trending")
    viral_coefficient: Optional[float] = Field(None, ge=0, description="Virality metric")
    
    top_keywords: Optional[List[str]] = Field(default_factory=list, description="Most mentioned keywords")
    sample_posts: Optional[List[str]] = Field(default_factory=list, description="Sample posts/tweets")
    
    timestamp: datetime = Field(..., description="Data timestamp")
    collected_at: datetime = Field(default_factory=datetime.utcnow, description="Collection timestamp")
    
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional metadata")
    
    @validator('sentiment_score')
    def validate_sentiment(cls, v):
        if not -1 <= v <= 1:
            raise ValueError('Sentiment score must be between -1 and 1')
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "update_id": "sentiment_20251111_twitter_001",
                "source": "twitter",
                "symbol": "BTC",
                "sentiment_score": 0.65,
                "sentiment_label": "Bullish",
                "social_volume": 15234,
                "engagement_count": 45678,
                "influencer_sentiment": 0.72,
                "sentiment_change_24h": 0.15,
                "trending": True,
                "viral_coefficient": 2.3,
                "top_keywords": ["breakout", "ATH", "bullrun"],
                "timestamp": "2025-11-11T10:30:00Z"
            }
        }


# ============================================================================
# On-Chain Metrics Messages
# ============================================================================

class OnChainMetricUpdate(BaseModel):
    """
    On-chain metric update from Glassnode, Nansen, or similar providers
    
    Provides fundamental blockchain metrics for analysis
    """
    metric_id: str = Field(..., description="Unique metric identifier")
    symbol: str = Field(..., description="Cryptocurrency symbol")
    metric_name: str = Field(..., description="Metric name (e.g., 'NVT', 'MVRV')")
    metric_value: float = Field(..., description="Metric value")
    
    # Common on-chain metrics
    nvt_ratio: Optional[float] = Field(None, description="Network Value to Transactions ratio")
    mvrv_ratio: Optional[float] = Field(None, description="Market Value to Realized Value ratio")
    exchange_netflow: Optional[float] = Field(None, description="Net exchange flow (inflow - outflow)")
    active_addresses: Optional[int] = Field(None, description="Number of active addresses")
    transaction_volume: Optional[float] = Field(None, description="24h transaction volume")
    
    # Exchange metrics
    exchange_reserves: Optional[float] = Field(None, description="Total exchange reserves")
    exchange_inflow: Optional[float] = Field(None, description="24h exchange inflow")
    exchange_outflow: Optional[float] = Field(None, description="24h exchange outflow")
    
    # Network health
    hash_rate: Optional[float] = Field(None, description="Network hash rate")
    difficulty: Optional[float] = Field(None, description="Mining difficulty")
    
    percentile_rank: Optional[float] = Field(None, ge=0, le=100, description="Historical percentile (0-100)")
    z_score: Optional[float] = Field(None, description="Z-score relative to historical average")
    
    interpretation: Optional[str] = Field(None, description="Human-readable interpretation")
    signal: Optional[TrendDirection] = Field(None, description="Bullish/Bearish/Neutral signal")
    
    timestamp: datetime = Field(..., description="Metric timestamp")
    source: str = Field(..., description="Data source (e.g., 'glassnode', 'nansen')")
    
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional metadata")
    
    class Config:
        json_schema_extra = {
            "example": {
                "metric_id": "onchain_20251111_btc_nvt",
                "symbol": "BTC",
                "metric_name": "NVT",
                "metric_value": 45.2,
                "nvt_ratio": 45.2,
                "mvrv_ratio": 2.1,
                "exchange_netflow": -15000.0,
                "active_addresses": 950000,
                "percentile_rank": 35.5,
                "z_score": -0.8,
                "interpretation": "NVT below average - potential accumulation phase",
                "signal": "bullish",
                "timestamp": "2025-11-11T10:00:00Z",
                "source": "glassnode"
            }
        }


# ============================================================================
# Institutional Flow Messages
# ============================================================================

class InstitutionalFlowSignal(BaseModel):
    """
    Institutional flow signal for large trades and unusual activity
    
    Detects professional/institutional trading activity
    """
    signal_id: str = Field(..., description="Unique signal identifier")
    symbol: str = Field(..., description="Trading pair (e.g., 'BTCUSDT')")
    flow_type: FlowType = Field(..., description="Type of institutional flow")
    
    size_usd: float = Field(..., description="Trade size in USD")
    price: float = Field(..., description="Execution price")
    side: str = Field(..., description="Trade side (buy/sell)")
    
    exchange: str = Field(..., description="Exchange where trade occurred")
    is_block_trade: bool = Field(default=False, description="Classified as block trade")
    is_unusual_volume: bool = Field(default=False, description="Unusual volume detected")
    
    volume_ratio: Optional[float] = Field(None, description="Ratio to average volume")
    price_impact: Optional[float] = Field(None, description="Price impact percentage")
    
    confidence_score: float = Field(..., ge=0, le=1, description="Signal confidence (0-1)")
    urgency: SignalStrength = Field(..., description="Signal urgency level")
    
    timestamp: datetime = Field(..., description="Trade timestamp")
    detected_at: datetime = Field(default_factory=datetime.utcnow, description="Detection timestamp")
    
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional metadata")
    
    class Config:
        json_schema_extra = {
            "example": {
                "signal_id": "instflow_20251111_001",
                "symbol": "BTCUSDT",
                "flow_type": "block_trade",
                "size_usd": 5000000.0,
                "price": 50000.0,
                "side": "buy",
                "exchange": "Binance",
                "is_block_trade": True,
                "volume_ratio": 8.5,
                "price_impact": 0.3,
                "confidence_score": 0.92,
                "urgency": "strong",
                "timestamp": "2025-11-11T10:30:00Z"
            }
        }


# ============================================================================
# Market Signal Aggregate Messages
# ============================================================================

class MarketSignalAggregate(BaseModel):
    """
    Aggregated market signal combining multiple data sources
    
    Used by strategy service for decision-making
    Combines: price action, sentiment, on-chain, institutional flow
    """
    signal_id: str = Field(..., description="Unique aggregate signal identifier")
    symbol: str = Field(..., description="Trading pair")
    
    # Overall signal
    overall_signal: TrendDirection = Field(..., description="Combined signal direction")
    signal_strength: SignalStrength = Field(..., description="Overall signal strength")
    confidence: float = Field(..., ge=0, le=1, description="Signal confidence (0-1)")
    
    # Component signals
    price_signal: Optional[TrendDirection] = Field(None, description="Technical analysis signal")
    price_strength: Optional[float] = Field(None, ge=0, le=1)
    
    sentiment_signal: Optional[TrendDirection] = Field(None, description="Social sentiment signal")
    sentiment_strength: Optional[float] = Field(None, ge=0, le=1)
    
    onchain_signal: Optional[TrendDirection] = Field(None, description="On-chain metrics signal")
    onchain_strength: Optional[float] = Field(None, ge=0, le=1)
    
    flow_signal: Optional[TrendDirection] = Field(None, description="Institutional flow signal")
    flow_strength: Optional[float] = Field(None, ge=0, le=1)
    
    # Signal weights (how much each component contributed)
    component_weights: Dict[str, float] = Field(
        default_factory=dict,
        description="Weight of each component in final signal"
    )
    
    # Risk indicators
    volatility: Optional[float] = Field(None, description="Current volatility estimate")
    risk_level: Optional[str] = Field(None, description="Risk assessment (low/medium/high)")
    
    # Trading recommendation
    recommended_action: Optional[str] = Field(None, description="Suggested action (buy/sell/hold/wait)")
    position_size_modifier: Optional[float] = Field(None, description="Position size adjustment (0.5-1.5)")
    
    # Metadata
    timestamp: datetime = Field(..., description="Signal generation timestamp")
    expires_at: Optional[datetime] = Field(None, description="Signal expiration time")
    
    contributing_alerts: List[str] = Field(
        default_factory=list,
        description="IDs of whale alerts that contributed"
    )
    contributing_updates: List[str] = Field(
        default_factory=list,
        description="IDs of other updates that contributed"
    )
    
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional metadata")
    
    class Config:
        json_schema_extra = {
            "example": {
                "signal_id": "agg_20251111_btcusdt_001",
                "symbol": "BTCUSDT",
                "overall_signal": "bullish",
                "signal_strength": "strong",
                "confidence": 0.82,
                "price_signal": "bullish",
                "price_strength": 0.75,
                "sentiment_signal": "bullish",
                "sentiment_strength": 0.85,
                "onchain_signal": "neutral",
                "onchain_strength": 0.50,
                "flow_signal": "bullish",
                "flow_strength": 0.90,
                "component_weights": {
                    "price": 0.3,
                    "sentiment": 0.25,
                    "onchain": 0.20,
                    "flow": 0.25
                },
                "volatility": 0.035,
                "risk_level": "medium",
                "recommended_action": "buy",
                "position_size_modifier": 1.2,
                "timestamp": "2025-11-11T10:30:00Z"
            }
        }


# ============================================================================
# Strategy Execution Messages
# ============================================================================

class StrategySignal(BaseModel):
    """
    Strategy execution signal for order placement
    
    Sent from strategy service to order executor
    """
    signal_id: str = Field(..., description="Unique signal identifier")
    strategy_id: str = Field(..., description="Strategy that generated signal")
    symbol: str = Field(..., description="Trading pair")
    
    action: str = Field(..., description="Action (ENTER_LONG, ENTER_SHORT, EXIT, CLOSE_ALL)")
    signal_strength: float = Field(..., ge=0, le=1, description="Signal strength (0-1)")
    
    entry_price: Optional[float] = Field(None, description="Suggested entry price")
    stop_loss: Optional[float] = Field(None, description="Stop loss price")
    take_profit: Optional[float] = Field(None, description="Take profit price")
    
    position_size_usd: Optional[float] = Field(None, description="Suggested position size in USD")
    leverage: Optional[float] = Field(None, ge=1, le=125, description="Leverage (1-125x)")
    
    confidence: float = Field(..., ge=0, le=1, description="Signal confidence")
    urgency: SignalStrength = Field(..., description="Signal urgency")
    
    reasoning: Optional[str] = Field(None, description="Human-readable reasoning")
    contributing_signals: List[str] = Field(
        default_factory=list,
        description="Market signal IDs that contributed"
    )
    
    timestamp: datetime = Field(..., description="Signal generation time")
    valid_until: Optional[datetime] = Field(None, description="Signal expiration time")
    
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional metadata")
    
    class Config:
        json_schema_extra = {
            "example": {
                "signal_id": "strat_signal_20251111_001",
                "strategy_id": "momentum_strategy_v2",
                "symbol": "BTCUSDT",
                "action": "ENTER_LONG",
                "signal_strength": 0.85,
                "entry_price": 50000.0,
                "stop_loss": 49000.0,
                "take_profit": 52000.0,
                "position_size_usd": 10000.0,
                "confidence": 0.82,
                "urgency": "strong",
                "reasoning": "Strong bullish confluence: positive sentiment, whale accumulation, technical breakout",
                "timestamp": "2025-11-11T10:30:00Z"
            }
        }


# ============================================================================
# Utility Functions
# ============================================================================

def serialize_message(message: BaseModel) -> str:
    """Serialize Pydantic model to JSON string for RabbitMQ"""
    return message.model_dump_json()


def deserialize_message(message_class: type[BaseModel], json_str: str) -> BaseModel:
    """Deserialize JSON string to Pydantic model"""
    return message_class.model_validate_json(json_str)


# ============================================================================
# Message Routing Keys
# ============================================================================

class RoutingKeys:
    """Standard RabbitMQ routing keys for message publishing"""
    
    # Whale alerts
    WHALE_ALERT = "whale.alert"
    WHALE_ALERT_HIGH_PRIORITY = "whale.alert.high"
    
    # Social sentiment
    SENTIMENT_UPDATE = "sentiment.update"
    SENTIMENT_TWITTER = "sentiment.twitter"
    SENTIMENT_REDDIT = "sentiment.reddit"
    SENTIMENT_AGGREGATED = "sentiment.aggregated"
    
    # On-chain metrics
    ONCHAIN_METRIC = "onchain.metric"
    ONCHAIN_NVT = "onchain.nvt"
    ONCHAIN_MVRV = "onchain.mvrv"
    ONCHAIN_EXCHANGE_FLOW = "onchain.exchange_flow"
    
    # Institutional flow
    INSTITUTIONAL_FLOW = "institutional.flow"
    INSTITUTIONAL_BLOCK_TRADE = "institutional.block_trade"
    INSTITUTIONAL_UNUSUAL_VOLUME = "institutional.unusual_volume"
    
    # Aggregated signals
    MARKET_SIGNAL = "market.signal"
    MARKET_SIGNAL_STRONG = "market.signal.strong"
    
    # Strategy signals
    STRATEGY_SIGNAL = "strategy.signal"
    STRATEGY_SIGNAL_URGENT = "strategy.signal.urgent"
