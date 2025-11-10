"""
Market Depth Analyzer

Analyzes order book depth and imbalances:
- Depth imbalance ratio
- Cumulative depth analysis
- Depth slope (price impact per unit)
- Market resilience
"""

from dataclasses import dataclass
from datetime import datetime
from typing import List, Dict, Optional, Tuple
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
class DepthImbalance:
    """Order book depth imbalance"""
    symbol: str
    timestamp: datetime
    
    # Imbalance ratio: (bid_depth - ask_depth) / (bid_depth + ask_depth)
    imbalance_ratio: float  # -1 to 1
    
    # Depth by levels
    bid_depth_l1: float  # Best level only
    ask_depth_l1: float
    bid_depth_l5: float  # Top 5 levels
    ask_depth_l5: float
    bid_depth_l10: float  # Top 10 levels
    ask_depth_l10: float
    
    # Total depth
    total_bid_depth: float
    total_ask_depth: float
    
    # Slope (liquidity per price level)
    bid_slope: float
    ask_slope: float
    
    def is_bullish(self, threshold: float = 0.1) -> bool:
        """Bullish if more bids than asks"""
        return self.imbalance_ratio > threshold
    
    def is_bearish(self, threshold: float = 0.1) -> bool:
        """Bearish if more asks than bids"""
        return self.imbalance_ratio < -threshold


@dataclass
class DepthMetrics:
    """Comprehensive depth metrics"""
    symbol: str
    timestamp: datetime
    
    # Imbalance
    depth_imbalance: DepthImbalance
    
    # Market impact (estimated)
    buy_market_impact_bps: float  # For $10k buy
    sell_market_impact_bps: float  # For $10k sell
    
    # Resilience (how fast depth replenishes)
    resilience_score: float  # 0-100
    
    # Depth quality
    depth_concentration: float  # How concentrated at top levels
    depth_diversity: int  # Number of unique price levels


class MarketDepthAnalyzer:
    """
    Analyzes order book depth and imbalances.
    
    Features:
    - Depth imbalance detection
    - Market impact estimation
    - Depth slope analysis
    - Resilience tracking
    """
    
    def __init__(self):
        self.order_books: Dict[str, Dict] = {}
        self.depth_history: Dict[str, List[DepthImbalance]] = {}
        logger.info("MarketDepthAnalyzer initialized")
    
    def update_order_book(
        self,
        symbol: str,
        timestamp: datetime,
        bids: List[OrderBookLevel],
        asks: List[OrderBookLevel],
    ):
        """Update order book snapshot"""
        
        # Sort bids descending, asks ascending
        bids = sorted(bids, key=lambda x: x.price, reverse=True)
        asks = sorted(asks, key=lambda x: x.price)
        
        self.order_books[symbol] = {
            "timestamp": timestamp,
            "bids": bids,
            "asks": asks,
        }
        
        logger.debug(f"Updated order book: {symbol} {len(bids)} bids, {len(asks)} asks")
    
    def calculate_depth_imbalance(
        self,
        symbol: str,
        num_levels: int = 10,
    ) -> Optional[DepthImbalance]:
        """Calculate order book depth imbalance"""
        
        if symbol not in self.order_books:
            return None
        
        book = self.order_books[symbol]
        bids = book["bids"]
        asks = book["asks"]
        
        if not bids or not asks:
            return None
        
        # Depth at different levels
        bid_depth_l1 = bids[0].quantity if len(bids) > 0 else 0
        ask_depth_l1 = asks[0].quantity if len(asks) > 0 else 0
        
        bid_depth_l5 = sum(b.quantity for b in bids[:5])
        ask_depth_l5 = sum(a.quantity for a in asks[:5])
        
        bid_depth_l10 = sum(b.quantity for b in bids[:10])
        ask_depth_l10 = sum(a.quantity for a in asks[:10])
        
        # Total depth (up to num_levels)
        total_bid_depth = sum(b.quantity for b in bids[:num_levels])
        total_ask_depth = sum(a.quantity for a in asks[:num_levels])
        
        # Imbalance ratio
        total_depth = total_bid_depth + total_ask_depth
        imbalance_ratio = (
            (total_bid_depth - total_ask_depth) / total_depth
            if total_depth > 0 else 0.0
        )
        
        # Depth slope (quantity per price level)
        if len(bids) > 1:
            bid_price_range = bids[0].price - bids[min(len(bids)-1, num_levels-1)].price
            bid_slope = total_bid_depth / bid_price_range if bid_price_range > 0 else 0
        else:
            bid_slope = 0
        
        if len(asks) > 1:
            ask_price_range = asks[min(len(asks)-1, num_levels-1)].price - asks[0].price
            ask_slope = total_ask_depth / ask_price_range if ask_price_range > 0 else 0
        else:
            ask_slope = 0
        
        imbalance = DepthImbalance(
            symbol=symbol,
            timestamp=book["timestamp"],
            imbalance_ratio=imbalance_ratio,
            bid_depth_l1=bid_depth_l1,
            ask_depth_l1=ask_depth_l1,
            bid_depth_l5=bid_depth_l5,
            ask_depth_l5=ask_depth_l5,
            bid_depth_l10=bid_depth_l10,
            ask_depth_l10=ask_depth_l10,
            total_bid_depth=total_bid_depth,
            total_ask_depth=total_ask_depth,
            bid_slope=bid_slope,
            ask_slope=ask_slope,
        )
        
        # Store in history
        if symbol not in self.depth_history:
            self.depth_history[symbol] = []
        self.depth_history[symbol].append(imbalance)
        
        # Keep last 100
        if len(self.depth_history[symbol]) > 100:
            self.depth_history[symbol] = self.depth_history[symbol][-100:]
        
        logger.debug(f"Depth imbalance {symbol}: {imbalance_ratio:.3f}")
        return imbalance
    
    def estimate_market_impact(
        self,
        symbol: str,
        order_size_usd: float = 10000.0,
        side: str = "buy",
    ) -> Optional[float]:
        """
        Estimate market impact for an order.
        
        Returns: Impact in basis points
        """
        if symbol not in self.order_books:
            return None
        
        book = self.order_books[symbol]
        
        if side == "buy":
            levels = book["asks"]
            best_price = levels[0].price if levels else 0
        else:
            levels = book["bids"]
            best_price = levels[0].price if levels else 0
        
        if best_price == 0 or not levels:
            return None
        
        # Walk through order book
        remaining_usd = order_size_usd
        total_quantity = 0.0
        weighted_price = 0.0
        
        for level in levels:
            level_value = level.price * level.quantity
            
            if remaining_usd <= 0:
                break
            
            consumed_value = min(remaining_usd, level_value)
            consumed_quantity = consumed_value / level.price
            
            weighted_price += level.price * consumed_quantity
            total_quantity += consumed_quantity
            remaining_usd -= consumed_value
        
        if total_quantity == 0:
            return 999.9  # Can't fill
        
        avg_price = weighted_price / total_quantity
        impact_bps = ((avg_price - best_price) / best_price) * 10000
        
        # For sells, impact is negative price movement
        if side == "sell":
            impact_bps = abs(impact_bps)
        
        return impact_bps
    
    def calculate_metrics(
        self,
        symbol: str,
        order_size_usd: float = 10000.0,
    ) -> Optional[DepthMetrics]:
        """Calculate comprehensive depth metrics"""
        
        imbalance = self.calculate_depth_imbalance(symbol)
        if not imbalance:
            return None
        
        # Market impact
        buy_impact = self.estimate_market_impact(symbol, order_size_usd, "buy") or 0
        sell_impact = self.estimate_market_impact(symbol, order_size_usd, "sell") or 0
        
        # Resilience (based on historical depth volatility)
        resilience_score = self._calculate_resilience(symbol)
        
        # Depth concentration (top 5 vs total)
        total_depth = imbalance.total_bid_depth + imbalance.total_ask_depth
        top5_depth = imbalance.bid_depth_l5 + imbalance.ask_depth_l5
        concentration = top5_depth / total_depth if total_depth > 0 else 0
        
        # Depth diversity (unique price levels)
        book = self.order_books[symbol]
        diversity = len(book["bids"]) + len(book["asks"])
        
        metrics = DepthMetrics(
            symbol=symbol,
            timestamp=datetime.utcnow(),
            depth_imbalance=imbalance,
            buy_market_impact_bps=buy_impact,
            sell_market_impact_bps=sell_impact,
            resilience_score=resilience_score,
            depth_concentration=concentration,
            depth_diversity=diversity,
        )
        
        logger.debug(f"Depth metrics {symbol}: impact_buy={buy_impact:.2f}bps, resilience={resilience_score:.1f}")
        return metrics
    
    def _calculate_resilience(self, symbol: str) -> float:
        """
        Calculate market resilience score.
        
        Lower depth volatility = higher resilience
        """
        if symbol not in self.depth_history or len(self.depth_history[symbol]) < 10:
            return 50.0  # Default
        
        history = self.depth_history[symbol]
        
        # Calculate volatility of depth imbalance
        imbalances = [h.imbalance_ratio for h in history]
        imbalance_std = np.std(imbalances)
        
        # Lower std = higher resilience
        # Normalize to 0-100 (assume std > 0.5 is low resilience)
        resilience = max(0, min(100, (1 - imbalance_std * 2) * 100))
        
        return resilience
    
    def detect_depth_cliff(
        self,
        symbol: str,
        side: str = "bid",
        threshold_pct: float = 50.0,
    ) -> Dict:
        """
        Detect depth cliff (sudden drop in liquidity).
        
        A cliff occurs when depth at level N is much less than level N-1.
        """
        if symbol not in self.order_books:
            return {"has_cliff": False}
        
        book = self.order_books[symbol]
        levels = book["bids"] if side == "bid" else book["asks"]
        
        if len(levels) < 2:
            return {"has_cliff": False}
        
        # Check for large drops
        cliffs = []
        for i in range(1, min(len(levels), 10)):
            prev_qty = levels[i-1].quantity
            curr_qty = levels[i].quantity
            
            if prev_qty > 0:
                drop_pct = ((prev_qty - curr_qty) / prev_qty) * 100
                if drop_pct > threshold_pct:
                    cliffs.append({
                        "level": i,
                        "price": levels[i].price,
                        "drop_pct": drop_pct,
                    })
        
        return {
            "has_cliff": len(cliffs) > 0,
            "cliffs": cliffs,
            "side": side,
        }
    
    def get_depth_profile(
        self,
        symbol: str,
        num_levels: int = 10,
    ) -> Optional[Dict]:
        """Get depth profile for visualization"""
        
        if symbol not in self.order_books:
            return None
        
        book = self.order_books[symbol]
        bids = book["bids"][:num_levels]
        asks = book["asks"][:num_levels]
        
        return {
            "symbol": symbol,
            "timestamp": book["timestamp"].isoformat(),
            "bids": [
                {"price": b.price, "quantity": b.quantity, "orders": b.num_orders}
                for b in bids
            ],
            "asks": [
                {"price": a.price, "quantity": a.quantity, "orders": a.num_orders}
                for a in asks
            ],
        }
