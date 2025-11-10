"""
Microstructure Signal Generator

Generates trading signals from microstructure analysis:
- Order flow signals
- Spread signals
- Depth imbalance signals
- Toxicity signals
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional
from enum import Enum
import logging

from .order_flow_analyzer import OrderFlowAnalyzer, OrderFlowMetrics
from .bid_ask_analyzer import BidAskAnalyzer, BidAskMetrics
from .market_depth_analyzer import MarketDepthAnalyzer, DepthMetrics
from .vpin_calculator import VPINCalculator, VPINMetrics

logger = logging.getLogger(__name__)


class SignalType(Enum):
    """Microstructure signal types"""
    BUY = "buy"
    SELL = "sell"
    NEUTRAL = "neutral"


@dataclass
class MicrostructureSignal:
    """Combined microstructure signal"""
    symbol: str
    timestamp: datetime
    
    # Overall signal
    signal: SignalType
    confidence: float  # 0-1
    
    # Component signals
    order_flow_signal: SignalType
    depth_signal: SignalType
    spread_signal: SignalType
    toxicity_signal: SignalType
    
    # Metrics
    order_flow_strength: float  # 0-1
    depth_imbalance: float  # -1 to 1
    spread_quality: float  # 0-1
    toxicity_risk: float  # 0-1
    
    # Recommendation
    recommended_action: str
    risk_level: str  # "low", "medium", "high"
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp.isoformat(),
            "signal": self.signal.value,
            "confidence": self.confidence,
            "order_flow_signal": self.order_flow_signal.value,
            "depth_signal": self.depth_signal.value,
            "spread_signal": self.spread_signal.value,
            "toxicity_signal": self.toxicity_signal.value,
            "order_flow_strength": self.order_flow_strength,
            "depth_imbalance": self.depth_imbalance,
            "spread_quality": self.spread_quality,
            "toxicity_risk": self.toxicity_risk,
            "recommended_action": self.recommended_action,
            "risk_level": self.risk_level,
        }


class MicrostructureSignalGenerator:
    """
    Generates trading signals from microstructure analysis.
    
    Combines:
    - Order flow (buy/sell pressure)
    - Depth imbalance (order book skew)
    - Spread quality (transaction costs)
    - Toxicity (informed trading risk)
    """
    
    def __init__(self):
        self.order_flow_analyzer = OrderFlowAnalyzer(window_size=100)
        self.bid_ask_analyzer = BidAskAnalyzer(window_size=100)
        self.depth_analyzer = MarketDepthAnalyzer()
        self.vpin_calculator = VPINCalculator(bucket_size=50.0, num_buckets=50)
        
        logger.info("MicrostructureSignalGenerator initialized")
    
    def generate_signal(self, symbol: str) -> Optional[MicrostructureSignal]:
        """Generate comprehensive microstructure signal"""
        
        # Get metrics from all analyzers
        order_flow = self.order_flow_analyzer.calculate_metrics(symbol)
        bid_ask = self.bid_ask_analyzer.calculate_metrics(symbol)
        depth = self.depth_analyzer.calculate_metrics(symbol)
        vpin = self.vpin_calculator.calculate_vpin(symbol)
        
        # Need at least some data
        if not order_flow and not depth:
            return None
        
        # Order flow signal
        if order_flow:
            if order_flow.is_bullish():
                of_signal = SignalType.BUY
            elif order_flow.is_bearish():
                of_signal = SignalType.SELL
            else:
                of_signal = SignalType.NEUTRAL
            
            of_strength = abs(order_flow.ofi)
        else:
            of_signal = SignalType.NEUTRAL
            of_strength = 0.0
        
        # Depth signal
        if depth:
            imbalance = depth.depth_imbalance
            if imbalance.is_bullish():
                depth_signal = SignalType.BUY
            elif imbalance.is_bearish():
                depth_signal = SignalType.SELL
            else:
                depth_signal = SignalType.NEUTRAL
            
            depth_imbalance_val = imbalance.imbalance_ratio
        else:
            depth_signal = SignalType.NEUTRAL
            depth_imbalance_val = 0.0
        
        # Spread signal (tight spread = good for trading)
        if bid_ask:
            if bid_ask.is_tight(threshold_bps=10.0):
                spread_signal = SignalType.BUY if of_signal == SignalType.BUY else SignalType.NEUTRAL
            else:
                spread_signal = SignalType.NEUTRAL  # Wide spread = avoid
            
            spread_quality = bid_ask.tightness_score / 100.0
        else:
            spread_signal = SignalType.NEUTRAL
            spread_quality = 0.5
        
        # Toxicity signal (high toxicity = avoid)
        if vpin:
            if vpin.is_toxic:
                toxicity_signal = SignalType.NEUTRAL  # High toxicity = don't trade
            else:
                toxicity_signal = SignalType.BUY if of_signal == SignalType.BUY else SignalType.NEUTRAL
            
            toxicity_risk = vpin.vpin
        else:
            toxicity_signal = SignalType.NEUTRAL
            toxicity_risk = 0.5
        
        # Combine signals
        buy_votes = sum([
            of_signal == SignalType.BUY,
            depth_signal == SignalType.BUY,
            spread_signal == SignalType.BUY,
            toxicity_signal == SignalType.BUY,
        ])
        
        sell_votes = sum([
            of_signal == SignalType.SELL,
            depth_signal == SignalType.SELL,
            spread_signal == SignalType.SELL,
            toxicity_signal == SignalType.SELL,
        ])
        
        # Overall signal
        if buy_votes >= 2:
            overall_signal = SignalType.BUY
            confidence = buy_votes / 4.0
        elif sell_votes >= 2:
            overall_signal = SignalType.SELL
            confidence = sell_votes / 4.0
        else:
            overall_signal = SignalType.NEUTRAL
            confidence = 0.5
        
        # Adjust confidence by toxicity
        if toxicity_risk > 0.6:
            confidence *= 0.5  # Reduce confidence in toxic environment
        
        # Risk level
        if toxicity_risk > 0.6 or spread_quality < 0.3:
            risk_level = "high"
        elif toxicity_risk > 0.4 or spread_quality < 0.5:
            risk_level = "medium"
        else:
            risk_level = "low"
        
        # Recommendation
        if overall_signal == SignalType.BUY and confidence > 0.6:
            recommendation = f"BUY - Strong microstructure support (confidence: {confidence:.1%})"
        elif overall_signal == SignalType.SELL and confidence > 0.6:
            recommendation = f"SELL - Strong microstructure pressure (confidence: {confidence:.1%})"
        elif toxicity_risk > 0.6:
            recommendation = "HOLD - High toxicity detected, avoid trading"
        elif spread_quality < 0.3:
            recommendation = "HOLD - Poor spread quality, high transaction costs"
        else:
            recommendation = "NEUTRAL - Mixed microstructure signals"
        
        signal = MicrostructureSignal(
            symbol=symbol,
            timestamp=datetime.utcnow(),
            signal=overall_signal,
            confidence=confidence,
            order_flow_signal=of_signal,
            depth_signal=depth_signal,
            spread_signal=spread_signal,
            toxicity_signal=toxicity_signal,
            order_flow_strength=of_strength,
            depth_imbalance=depth_imbalance_val,
            spread_quality=spread_quality,
            toxicity_risk=toxicity_risk,
            recommended_action=recommendation,
            risk_level=risk_level,
        )
        
        logger.info(f"Microstructure signal {symbol}: {overall_signal.value} (confidence: {confidence:.1%})")
        return signal
    
    def get_order_flow_analyzer(self) -> OrderFlowAnalyzer:
        """Get order flow analyzer instance"""
        return self.order_flow_analyzer
    
    def get_bid_ask_analyzer(self) -> BidAskAnalyzer:
        """Get bid-ask analyzer instance"""
        return self.bid_ask_analyzer
    
    def get_depth_analyzer(self) -> MarketDepthAnalyzer:
        """Get depth analyzer instance"""
        return self.depth_analyzer
    
    def get_vpin_calculator(self) -> VPINCalculator:
        """Get VPIN calculator instance"""
        return self.vpin_calculator
