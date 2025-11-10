"""
Bid-Ask Spread Analyzer

Analyzes bid-ask spread dynamics:
- Spread width and volatility
- Quoted spread vs effective spread
- Price improvement
- Spread decomposition (adverse selection, order processing, inventory)
"""

from dataclasses import dataclass
from datetime import datetime
from typing import List, Dict, Optional
import numpy as np
import logging

logger = logging.getLogger(__name__)


@dataclass
class Quote:
    """Market quote (bid/ask)"""
    timestamp: datetime
    bid: float
    ask: float
    bid_size: float
    ask_size: float
    
    @property
    def spread(self) -> float:
        """Absolute spread"""
        return self.ask - self.bid
    
    @property
    def spread_bps(self) -> float:
        """Spread in basis points"""
        mid = (self.bid + self.ask) / 2.0
        return (self.spread / mid) * 10000 if mid > 0 else 0.0
    
    @property
    def mid_price(self) -> float:
        """Mid-price"""
        return (self.bid + self.ask) / 2.0


@dataclass
class SpreadAnalysis:
    """Spread analysis results"""
    symbol: str
    timestamp: datetime
    
    # Spread metrics
    quoted_spread: float  # Current spread
    effective_spread: float  # Actual execution spread
    realized_spread: float  # Post-trade spread
    
    # Spread components (in bps)
    quoted_spread_bps: float
    effective_spread_bps: float
    
    # Statistics
    avg_spread: float
    spread_volatility: float
    
    # Price improvement
    price_improvement: float  # How much better than quoted
    
    def has_price_improvement(self) -> bool:
        """Check if there's price improvement"""
        return self.price_improvement > 0


@dataclass
class BidAskMetrics:
    """Comprehensive bid-ask metrics"""
    symbol: str
    timestamp: datetime
    
    # Current quote
    current_bid: float
    current_ask: float
    current_spread: float
    current_spread_bps: float
    
    # Historical stats (rolling window)
    avg_spread: float
    min_spread: float
    max_spread: float
    spread_std: float
    
    # Spread as % of price
    spread_pct: float
    
    # Liquidity (size at best)
    bid_size: float
    ask_size: float
    total_size: float
    size_imbalance: float  # (ask_size - bid_size) / total
    
    # Spread tightness score (0-100)
    tightness_score: float
    
    def is_tight(self, threshold_bps: float = 10.0) -> bool:
        """Check if spread is tight"""
        return self.current_spread_bps < threshold_bps


class BidAskAnalyzer:
    """
    Analyzes bid-ask spread dynamics.
    
    Features:
    - Quoted spread tracking
    - Effective spread calculation
    - Spread decomposition
    - Price improvement detection
    """
    
    def __init__(self, window_size: int = 100):
        self.window_size = window_size
        self.quotes: Dict[str, List[Quote]] = {}
        logger.info(f"BidAskAnalyzer initialized with window_size={window_size}")
    
    def record_quote(
        self,
        symbol: str,
        timestamp: datetime,
        bid: float,
        ask: float,
        bid_size: float,
        ask_size: float,
    ):
        """Record a new quote"""
        
        if symbol not in self.quotes:
            self.quotes[symbol] = []
        
        quote = Quote(
            timestamp=timestamp,
            bid=bid,
            ask=ask,
            bid_size=bid_size,
            ask_size=ask_size,
        )
        
        self.quotes[symbol].append(quote)
        
        # Keep only recent quotes
        if len(self.quotes[symbol]) > self.window_size:
            self.quotes[symbol] = self.quotes[symbol][-self.window_size:]
        
        logger.debug(f"Recorded quote: {symbol} {bid}/{ask} spread={quote.spread_bps:.2f}bps")
    
    def get_current_quote(self, symbol: str) -> Optional[Quote]:
        """Get most recent quote"""
        if symbol not in self.quotes or not self.quotes[symbol]:
            return None
        return self.quotes[symbol][-1]
    
    def calculate_metrics(self, symbol: str) -> Optional[BidAskMetrics]:
        """Calculate comprehensive bid-ask metrics"""
        
        if symbol not in self.quotes or not self.quotes[symbol]:
            return None
        
        quotes = self.quotes[symbol]
        current = quotes[-1]
        
        # Current metrics
        current_spread = current.spread
        current_spread_bps = current.spread_bps
        
        # Historical statistics
        spreads = [q.spread for q in quotes]
        spread_bps_list = [q.spread_bps for q in quotes]
        
        avg_spread = np.mean(spreads)
        min_spread = np.min(spreads)
        max_spread = np.max(spreads)
        spread_std = np.std(spreads)
        
        # Spread as % of price
        mid = current.mid_price
        spread_pct = (current_spread / mid) * 100 if mid > 0 else 0.0
        
        # Size imbalance
        total_size = current.bid_size + current.ask_size
        size_imbalance = (current.ask_size - current.bid_size) / total_size if total_size > 0 else 0.0
        
        # Tightness score (0-100, based on spread percentile)
        if len(spread_bps_list) > 1:
            percentile = np.searchsorted(sorted(spread_bps_list), current_spread_bps) / len(spread_bps_list)
            tightness_score = (1 - percentile) * 100  # Lower spread = higher score
        else:
            tightness_score = 50.0
        
        metrics = BidAskMetrics(
            symbol=symbol,
            timestamp=datetime.utcnow(),
            current_bid=current.bid,
            current_ask=current.ask,
            current_spread=current_spread,
            current_spread_bps=current_spread_bps,
            avg_spread=avg_spread,
            min_spread=min_spread,
            max_spread=max_spread,
            spread_std=spread_std,
            spread_pct=spread_pct,
            bid_size=current.bid_size,
            ask_size=current.ask_size,
            total_size=total_size,
            size_imbalance=size_imbalance,
            tightness_score=tightness_score,
        )
        
        logger.debug(f"Bid-ask {symbol}: spread={current_spread_bps:.2f}bps, tightness={tightness_score:.1f}")
        return metrics
    
    def analyze_spread(
        self,
        symbol: str,
        trade_price: float,
        trade_side: str,  # "buy" or "sell"
    ) -> Optional[SpreadAnalysis]:
        """
        Analyze spread for a trade.
        
        Calculates:
        - Quoted spread: ask - bid
        - Effective spread: 2 * |trade_price - mid|
        - Price improvement: quoted - effective
        """
        current = self.get_current_quote(symbol)
        if not current:
            return None
        
        # Quoted spread
        quoted_spread = current.spread
        quoted_spread_bps = current.spread_bps
        mid = current.mid_price
        
        # Effective spread (actual execution cost)
        if trade_side == "buy":
            effective_spread = 2 * (trade_price - mid)
        else:  # sell
            effective_spread = 2 * (mid - trade_price)
        
        effective_spread_bps = (effective_spread / mid) * 10000 if mid > 0 else 0.0
        
        # Price improvement (positive = better than quoted)
        if trade_side == "buy":
            price_improvement = current.ask - trade_price
        else:
            price_improvement = trade_price - current.bid
        
        # Historical average spread
        quotes = self.quotes[symbol]
        avg_spread = np.mean([q.spread for q in quotes])
        spread_volatility = np.std([q.spread for q in quotes])
        
        # Realized spread (placeholder - would need future mid-price)
        realized_spread = effective_spread  # Simplified
        
        analysis = SpreadAnalysis(
            symbol=symbol,
            timestamp=datetime.utcnow(),
            quoted_spread=quoted_spread,
            effective_spread=effective_spread,
            realized_spread=realized_spread,
            quoted_spread_bps=quoted_spread_bps,
            effective_spread_bps=effective_spread_bps,
            avg_spread=avg_spread,
            spread_volatility=spread_volatility,
            price_improvement=price_improvement,
        )
        
        logger.debug(f"Spread analysis {symbol}: effective={effective_spread_bps:.2f}bps, improvement={price_improvement:.4f}")
        return analysis
    
    def get_spread_time_series(self, symbol: str) -> List[float]:
        """Get spread time series (in bps)"""
        if symbol not in self.quotes:
            return []
        
        return [q.spread_bps for q in self.quotes[symbol]]
    
    def detect_spread_widening(
        self,
        symbol: str,
        threshold_std: float = 2.0,
    ) -> Dict:
        """
        Detect unusual spread widening.
        
        Returns alert if current spread > mean + threshold_std * std
        """
        if symbol not in self.quotes or len(self.quotes[symbol]) < 10:
            return {"is_widening": False}
        
        spreads = [q.spread_bps for q in self.quotes[symbol]]
        current_spread = spreads[-1]
        
        mean_spread = np.mean(spreads[:-1])  # Exclude current
        std_spread = np.std(spreads[:-1])
        
        threshold = mean_spread + (threshold_std * std_spread)
        is_widening = current_spread > threshold
        
        z_score = (current_spread - mean_spread) / std_spread if std_spread > 0 else 0
        
        return {
            "is_widening": is_widening,
            "current_spread_bps": current_spread,
            "mean_spread_bps": mean_spread,
            "threshold_bps": threshold,
            "z_score": z_score,
        }
    
    def calculate_roll_measure(self, symbol: str) -> Optional[float]:
        """
        Calculate Roll's measure of effective spread.
        
        Roll measure = 2 * sqrt(-Cov(ΔP_t, ΔP_t-1))
        
        Estimates effective spread from price changes.
        """
        if symbol not in self.quotes or len(self.quotes[symbol]) < 20:
            return None
        
        # Get mid-price changes
        quotes = self.quotes[symbol]
        mid_prices = [q.mid_price for q in quotes]
        price_changes = np.diff(mid_prices)
        
        # Calculate autocovariance
        if len(price_changes) < 2:
            return None
        
        cov = np.cov(price_changes[:-1], price_changes[1:])[0, 1]
        
        # Roll measure (only valid if cov is negative)
        if cov < 0:
            roll_measure = 2 * np.sqrt(-cov)
        else:
            roll_measure = 0.0
        
        return roll_measure
