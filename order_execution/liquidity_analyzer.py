"""
Liquidity Analyzer

Analyzes market liquidity from order book data:
- Order book depth
- Bid-ask spread
- Volume profiles
- Market impact estimation
"""

from dataclasses import dataclass
from datetime import datetime
from typing import List, Dict, Optional
import numpy as np
import logging

logger = logging.getLogger(__name__)


@dataclass
class OrderBookLevel:
    """Single level in order book"""
    price: float
    quantity: float
    num_orders: int = 1


@dataclass
class LiquidityScore:
    """Overall liquidity assessment"""
    symbol: str
    depth_score: float  # 0-100
    spread_score: float  # 0-100
    volume_score: float  # 0-100
    overall_score: float  # 0-100
    bid_ask_spread_bps: float
    market_impact_bps: float  # For typical order size
    timestamp: datetime
    
    def is_liquid(self) -> bool:
        """Check if market is sufficiently liquid"""
        return self.overall_score >= 60.0


class OrderBookAnalyzer:
    """Analyzes order book depth and liquidity"""
    
    def __init__(self):
        self.order_books: Dict[str, Dict] = {}
        logger.info("OrderBookAnalyzer initialized")
    
    def update_order_book(
        self,
        symbol: str,
        bids: List[OrderBookLevel],
        asks: List[OrderBookLevel],
    ):
        """Update order book snapshot"""
        self.order_books[symbol] = {
            "bids": sorted(bids, key=lambda x: x.price, reverse=True),
            "asks": sorted(asks, key=lambda x: x.price),
            "timestamp": datetime.utcnow(),
        }
    
    def analyze_liquidity(
        self,
        symbol: str,
        typical_order_size: float = 10000.0,  # USD
    ) -> Optional[LiquidityScore]:
        """Comprehensive liquidity analysis"""
        
        if symbol not in self.order_books:
            return None
        
        book = self.order_books[symbol]
        bids = book["bids"]
        asks = book["asks"]
        
        if not bids or not asks:
            return None
        
        # Calculate metrics
        spread_bps = self._calculate_spread(bids[0].price, asks[0].price)
        depth_score = self._calculate_depth_score(bids, asks)
        spread_score = self._calculate_spread_score(spread_bps)
        volume_score = self._calculate_volume_score(bids, asks)
        impact_bps = self._estimate_market_impact(bids, asks, typical_order_size)
        
        overall = (depth_score + spread_score + volume_score) / 3.0
        
        score = LiquidityScore(
            symbol=symbol,
            depth_score=depth_score,
            spread_score=spread_score,
            volume_score=volume_score,
            overall_score=overall,
            bid_ask_spread_bps=spread_bps,
            market_impact_bps=impact_bps,
            timestamp=datetime.utcnow(),
        )
        
        logger.debug(f"Liquidity {symbol}: {overall:.1f}/100, spread={spread_bps:.1f}bps")
        return score
    
    def _calculate_spread(self, best_bid: float, best_ask: float) -> float:
        """Calculate bid-ask spread in basis points"""
        mid = (best_bid + best_ask) / 2.0
        spread_bps = ((best_ask - best_bid) / mid) * 10000
        return spread_bps
    
    def _calculate_depth_score(
        self,
        bids: List[OrderBookLevel],
        asks: List[OrderBookLevel],
    ) -> float:
        """Score based on order book depth"""
        # Total quantity in top 5 levels
        bid_depth = sum(level.quantity for level in bids[:5])
        ask_depth = sum(level.quantity for level in asks[:5])
        total_depth = bid_depth + ask_depth
        
        # More depth = higher score
        # Assume 100+ BTC is excellent
        score = min(100.0, (total_depth / 100.0) * 100)
        return score
    
    def _calculate_spread_score(self, spread_bps: float) -> float:
        """Score based on spread (lower is better)"""
        # <5 bps = 100, >50 bps = 0
        if spread_bps <= 5:
            return 100.0
        elif spread_bps >= 50:
            return 0.0
        else:
            return 100.0 - ((spread_bps - 5) / 45) * 100
    
    def _calculate_volume_score(
        self,
        bids: List[OrderBookLevel],
        asks: List[OrderBookLevel],
    ) -> float:
        """Score based on number of orders"""
        total_orders = sum(level.num_orders for level in bids[:10])
        total_orders += sum(level.num_orders for level in asks[:10])
        
        # More orders = more liquidity
        score = min(100.0, (total_orders / 50.0) * 100)
        return score
    
    def _estimate_market_impact(
        self,
        bids: List[OrderBookLevel],
        asks: List[OrderBookLevel],
        order_size_usd: float,
    ) -> float:
        """Estimate market impact in bps"""
        # For buy orders, consume ask side
        best_ask = asks[0].price
        remaining_usd = order_size_usd
        weighted_price = 0.0
        total_qty = 0.0
        
        for level in asks:
            level_value = level.price * level.quantity
            
            if remaining_usd <= 0:
                break
            
            consumed_value = min(remaining_usd, level_value)
            consumed_qty = consumed_value / level.price
            
            weighted_price += level.price * consumed_qty
            total_qty += consumed_qty
            remaining_usd -= consumed_value
        
        if total_qty == 0:
            return 999.9  # Can't fill order
        
        avg_price = weighted_price / total_qty
        impact_bps = ((avg_price - best_ask) / best_ask) * 10000
        
        return impact_bps


class VolumeProfileAnalyzer:
    """Analyzes historical volume patterns"""
    
    def __init__(self):
        self.volume_history: Dict[str, List[Dict]] = {}
        logger.info("VolumeProfileAnalyzer initialized")
    
    def record_volume(self, symbol: str, timestamp: datetime, volume: float):
        """Record volume observation"""
        if symbol not in self.volume_history:
            self.volume_history[symbol] = []
        
        self.volume_history[symbol].append({
            "timestamp": timestamp,
            "volume": volume,
        })
        
        # Keep last 24 hours
        cutoff = datetime.utcnow().timestamp() - 86400
        self.volume_history[symbol] = [
            v for v in self.volume_history[symbol]
            if v["timestamp"].timestamp() > cutoff
        ]
    
    def get_typical_volume_profile(
        self,
        symbol: str,
        num_intervals: int = 24,
    ) -> List[float]:
        """Get typical volume distribution over time"""
        
        if symbol not in self.volume_history or not self.volume_history[symbol]:
            # Default U-shaped profile
            return self._default_profile(num_intervals)
        
        # Calculate average volume by hour
        hourly_volumes = [0.0] * 24
        hourly_counts = [0] * 24
        
        for record in self.volume_history[symbol]:
            hour = record["timestamp"].hour
            hourly_volumes[hour] += record["volume"]
            hourly_counts[hour] += 1
        
        # Average
        for i in range(24):
            if hourly_counts[i] > 0:
                hourly_volumes[i] /= hourly_counts[i]
        
        # Normalize to sum=1
        total = sum(hourly_volumes)
        if total > 0:
            hourly_volumes = [v / total for v in hourly_volumes]
        else:
            hourly_volumes = self._default_profile(24)
        
        # Resample to num_intervals if needed
        if num_intervals != 24:
            hourly_volumes = self._resample(hourly_volumes, num_intervals)
        
        return hourly_volumes
    
    def _default_profile(self, n: int) -> List[float]:
        """Default U-shaped volume profile"""
        profile = []
        for i in range(n):
            # Higher at start and end, lower in middle
            normalized_i = i / (n - 1)
            value = 0.5 + 0.5 * abs(2 * normalized_i - 1)
            profile.append(value)
        
        # Normalize
        total = sum(profile)
        return [v / total for v in profile]
    
    def _resample(self, values: List[float], new_size: int) -> List[float]:
        """Resample list to new size"""
        arr = np.array(values)
        indices = np.linspace(0, len(values) - 1, new_size)
        resampled = np.interp(indices, np.arange(len(values)), arr)
        
        # Normalize
        total = np.sum(resampled)
        if total > 0:
            resampled = resampled / total
        
        return resampled.tolist()
