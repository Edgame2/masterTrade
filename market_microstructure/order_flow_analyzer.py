"""
Order Flow Analyzer

Analyzes order flow to identify informed trading and market pressure.

Implements:
- Lee-Ready algorithm for trade classification
- Order flow imbalance (OFI)
- Buy/sell pressure metrics
- Volume-weighted order flow
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Optional
from enum import Enum
import numpy as np
import logging

logger = logging.getLogger(__name__)


class TradeClassification(Enum):
    """Trade classification"""
    BUY = "buy"  # Buyer-initiated
    SELL = "sell"  # Seller-initiated
    UNKNOWN = "unknown"


@dataclass
class Trade:
    """Individual trade"""
    timestamp: datetime
    price: float
    volume: float
    classification: TradeClassification = TradeClassification.UNKNOWN


@dataclass
class OrderFlowMetrics:
    """Order flow metrics for a period"""
    symbol: str
    start_time: datetime
    end_time: datetime
    
    # Volume metrics
    total_volume: float
    buy_volume: float
    sell_volume: float
    
    # Order flow imbalance
    ofi: float  # (buy_volume - sell_volume) / total_volume
    
    # Trade counts
    total_trades: int
    buy_trades: int
    sell_trades: int
    
    # VWAP
    vwap: float
    buy_vwap: float
    sell_vwap: float
    
    # Pressure
    buy_pressure: float  # 0-1
    sell_pressure: float  # 0-1
    net_pressure: float  # -1 to 1
    
    def is_bullish(self, threshold: float = 0.1) -> bool:
        """Check if order flow is bullish"""
        return self.ofi > threshold
    
    def is_bearish(self, threshold: float = 0.1) -> bool:
        """Check if order flow is bearish"""
        return self.ofi < -threshold


class OrderFlowAnalyzer:
    """
    Analyzes order flow to detect buying/selling pressure.
    
    Uses Lee-Ready algorithm for trade classification:
    1. If trade price > mid-price: buyer-initiated (buy)
    2. If trade price < mid-price: seller-initiated (sell)
    3. If trade price = mid-price: use tick rule
    """
    
    def __init__(self, window_size: int = 100):
        self.window_size = window_size
        self.trades: Dict[str, List[Trade]] = {}
        logger.info(f"OrderFlowAnalyzer initialized with window_size={window_size}")
    
    def classify_trade(
        self,
        trade_price: float,
        bid: float,
        ask: float,
        previous_price: Optional[float] = None,
    ) -> TradeClassification:
        """
        Classify trade using Lee-Ready algorithm.
        
        Args:
            trade_price: Execution price
            bid: Best bid price
            ask: Best ask price
            previous_price: Previous trade price (for tick rule)
        """
        mid_price = (bid + ask) / 2.0
        
        # Quote rule
        if trade_price > mid_price:
            return TradeClassification.BUY
        elif trade_price < mid_price:
            return TradeClassification.SELL
        
        # Tick rule (if trade at mid-price)
        if previous_price is not None:
            if trade_price > previous_price:
                return TradeClassification.BUY
            elif trade_price < previous_price:
                return TradeClassification.SELL
        
        return TradeClassification.UNKNOWN
    
    def record_trade(
        self,
        symbol: str,
        timestamp: datetime,
        price: float,
        volume: float,
        bid: float,
        ask: float,
    ):
        """Record and classify a trade"""
        
        if symbol not in self.trades:
            self.trades[symbol] = []
        
        # Get previous price for tick rule
        previous_price = None
        if self.trades[symbol]:
            previous_price = self.trades[symbol][-1].price
        
        # Classify trade
        classification = self.classify_trade(price, bid, ask, previous_price)
        
        # Create trade
        trade = Trade(
            timestamp=timestamp,
            price=price,
            volume=volume,
            classification=classification,
        )
        
        self.trades[symbol].append(trade)
        
        # Keep only recent trades
        if len(self.trades[symbol]) > self.window_size:
            self.trades[symbol] = self.trades[symbol][-self.window_size:]
        
        logger.debug(f"Recorded trade: {symbol} {classification.value} {volume}@{price}")
    
    def calculate_metrics(
        self,
        symbol: str,
        lookback_minutes: Optional[int] = None,
    ) -> Optional[OrderFlowMetrics]:
        """Calculate order flow metrics"""
        
        if symbol not in self.trades or not self.trades[symbol]:
            return None
        
        trades = self.trades[symbol]
        
        # Filter by time if specified
        if lookback_minutes:
            cutoff = datetime.utcnow().timestamp() - (lookback_minutes * 60)
            trades = [t for t in trades if t.timestamp.timestamp() > cutoff]
        
        if not trades:
            return None
        
        # Separate buy and sell trades
        buy_trades = [t for t in trades if t.classification == TradeClassification.BUY]
        sell_trades = [t for t in trades if t.classification == TradeClassification.SELL]
        
        # Volume metrics
        total_volume = sum(t.volume for t in trades)
        buy_volume = sum(t.volume for t in buy_trades)
        sell_volume = sum(t.volume for t in sell_trades)
        
        # Order flow imbalance
        ofi = (buy_volume - sell_volume) / total_volume if total_volume > 0 else 0.0
        
        # VWAP calculations
        total_value = sum(t.price * t.volume for t in trades)
        vwap = total_value / total_volume if total_volume > 0 else 0.0
        
        buy_value = sum(t.price * t.volume for t in buy_trades)
        buy_vwap = buy_value / buy_volume if buy_volume > 0 else 0.0
        
        sell_value = sum(t.price * t.volume for t in sell_trades)
        sell_vwap = sell_value / sell_volume if sell_volume > 0 else 0.0
        
        # Pressure metrics (normalized by volume)
        buy_pressure = buy_volume / total_volume if total_volume > 0 else 0.0
        sell_pressure = sell_volume / total_volume if total_volume > 0 else 0.0
        net_pressure = buy_pressure - sell_pressure
        
        metrics = OrderFlowMetrics(
            symbol=symbol,
            start_time=trades[0].timestamp,
            end_time=trades[-1].timestamp,
            total_volume=total_volume,
            buy_volume=buy_volume,
            sell_volume=sell_volume,
            ofi=ofi,
            total_trades=len(trades),
            buy_trades=len(buy_trades),
            sell_trades=len(sell_trades),
            vwap=vwap,
            buy_vwap=buy_vwap,
            sell_vwap=sell_vwap,
            buy_pressure=buy_pressure,
            sell_pressure=sell_pressure,
            net_pressure=net_pressure,
        )
        
        logger.debug(f"Order flow {symbol}: OFI={ofi:.3f}, net_pressure={net_pressure:.3f}")
        return metrics
    
    def get_rolling_ofi(
        self,
        symbol: str,
        window_size: int = 20,
    ) -> List[float]:
        """Calculate rolling order flow imbalance"""
        
        if symbol not in self.trades or len(self.trades[symbol]) < window_size:
            return []
        
        trades = self.trades[symbol]
        ofi_values = []
        
        for i in range(window_size, len(trades) + 1):
            window = trades[i - window_size:i]
            
            buy_volume = sum(t.volume for t in window if t.classification == TradeClassification.BUY)
            sell_volume = sum(t.volume for t in window if t.classification == TradeClassification.SELL)
            total_volume = sum(t.volume for t in window)
            
            ofi = (buy_volume - sell_volume) / total_volume if total_volume > 0 else 0.0
            ofi_values.append(ofi)
        
        return ofi_values
    
    def detect_toxic_flow(
        self,
        symbol: str,
        threshold: float = 0.3,
    ) -> Dict:
        """
        Detect toxic (informed) order flow.
        
        High absolute OFI with large trades suggests informed trading.
        """
        metrics = self.calculate_metrics(symbol)
        if not metrics:
            return {"is_toxic": False}
        
        # High OFI magnitude
        high_imbalance = abs(metrics.ofi) > threshold
        
        # Large average trade size (proxy for institutional)
        avg_trade_size = metrics.total_volume / metrics.total_trades if metrics.total_trades > 0 else 0
        
        # Price impact (buy VWAP vs sell VWAP)
        if metrics.buy_vwap > 0 and metrics.sell_vwap > 0:
            price_impact = abs(metrics.buy_vwap - metrics.sell_vwap) / metrics.vwap
        else:
            price_impact = 0
        
        # Toxic if high imbalance + large trades + price impact
        is_toxic = high_imbalance and avg_trade_size > metrics.total_volume / metrics.total_trades
        
        return {
            "is_toxic": is_toxic,
            "ofi": metrics.ofi,
            "avg_trade_size": avg_trade_size,
            "price_impact": price_impact,
            "direction": "buy" if metrics.ofi > 0 else "sell",
        }
