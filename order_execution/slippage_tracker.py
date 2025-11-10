"""
Slippage Tracker

Tracks execution quality and slippage:
- Absolute slippage
- Percentage slippage
- Benchmarking (VWAP, arrival price, mid-price)
- Market impact analysis
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Optional
import numpy as np
import logging

logger = logging.getLogger(__name__)


@dataclass
class SlippageMetrics:
    """Slippage metrics for an execution"""
    order_id: str
    symbol: str
    side: str
    
    # Prices
    arrival_price: float  # Price when order placed
    average_execution_price: float  # Actual average fill price
    benchmark_vwap: Optional[float] = None
    benchmark_mid_price: Optional[float] = None
    
    # Slippage
    absolute_slippage: float = 0.0  # In price units
    percentage_slippage: float = 0.0  # As %
    slippage_bps: float = 0.0  # In basis points
    
    # Additional metrics
    total_quantity: float = 0.0
    filled_quantity: float = 0.0
    total_cost: float = 0.0
    market_impact_bps: float = 0.0
    
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    def calculate_slippage(self):
        """Calculate all slippage metrics"""
        if self.side == "BUY":
            # For buys, higher price = worse
            self.absolute_slippage = self.average_execution_price - self.arrival_price
        else:
            # For sells, lower price = worse
            self.absolute_slippage = self.arrival_price - self.average_execution_price
        
        self.percentage_slippage = (self.absolute_slippage / self.arrival_price) * 100
        self.slippage_bps = self.percentage_slippage * 100


@dataclass
class ExecutionQuality:
    """Overall execution quality assessment"""
    order_id: str
    symbol: str
    
    # Quality scores (0-100, higher is better)
    price_quality: float = 0.0
    speed_quality: float = 0.0
    fill_quality: float = 0.0
    overall_quality: float = 0.0
    
    # Benchmarks
    beat_arrival_price: bool = False
    beat_vwap: bool = False
    
    timestamp: datetime = field(default_factory=datetime.utcnow)


class SlippageTracker:
    """Tracks and analyzes execution slippage"""
    
    def __init__(self):
        self.executions: Dict[str, SlippageMetrics] = {}
        self.quality_assessments: Dict[str, ExecutionQuality] = {}
        logger.info("SlippageTracker initialized")
    
    def record_execution(
        self,
        order_id: str,
        symbol: str,
        side: str,
        arrival_price: float,
        fills: List[Dict],  # List of {price, quantity, timestamp}
    ) -> SlippageMetrics:
        """Record execution and calculate slippage"""
        
        # Calculate VWAP of fills
        total_value = sum(fill["price"] * fill["quantity"] for fill in fills)
        total_quantity = sum(fill["quantity"] for fill in fills)
        
        if total_quantity == 0:
            logger.warning(f"No fills for order {order_id}")
            return None
        
        avg_price = total_value / total_quantity
        
        # Create metrics
        metrics = SlippageMetrics(
            order_id=order_id,
            symbol=symbol,
            side=side,
            arrival_price=arrival_price,
            average_execution_price=avg_price,
            total_quantity=total_quantity,
            filled_quantity=total_quantity,
            total_cost=total_value,
        )
        
        metrics.calculate_slippage()
        
        self.executions[order_id] = metrics
        logger.info(f"Slippage {order_id}: {metrics.slippage_bps:.2f}bps")
        
        return metrics
    
    def add_benchmark(
        self,
        order_id: str,
        vwap: Optional[float] = None,
        mid_price: Optional[float] = None,
    ):
        """Add benchmark prices for comparison"""
        if order_id not in self.executions:
            return
        
        metrics = self.executions[order_id]
        metrics.benchmark_vwap = vwap
        metrics.benchmark_mid_price = mid_price
        
        # Recalculate market impact if we have benchmarks
        if vwap:
            if metrics.side == "BUY":
                impact = ((metrics.average_execution_price - vwap) / vwap) * 10000
            else:
                impact = ((vwap - metrics.average_execution_price) / vwap) * 10000
            
            metrics.market_impact_bps = impact
    
    def assess_quality(
        self,
        order_id: str,
        expected_duration_seconds: float,
        actual_duration_seconds: float,
    ) -> ExecutionQuality:
        """Assess overall execution quality"""
        
        if order_id not in self.executions:
            logger.warning(f"No execution data for {order_id}")
            return None
        
        metrics = self.executions[order_id]
        
        # Price quality (0-100, based on slippage)
        # <5 bps = 100, >50 bps = 0
        price_quality = max(0.0, min(100.0, 100.0 - (metrics.slippage_bps / 50.0) * 100))
        
        # Speed quality (based on duration vs expected)
        speed_ratio = actual_duration_seconds / expected_duration_seconds
        if speed_ratio <= 1.0:
            speed_quality = 100.0
        elif speed_ratio >= 2.0:
            speed_quality = 0.0
        else:
            speed_quality = 100.0 - ((speed_ratio - 1.0) * 100)
        
        # Fill quality (fill rate)
        fill_rate = metrics.filled_quantity / metrics.total_quantity if metrics.total_quantity > 0 else 0.0
        fill_quality = fill_rate * 100
        
        # Overall (weighted average)
        overall = 0.5 * price_quality + 0.3 * speed_quality + 0.2 * fill_quality
        
        # Benchmark comparisons
        beat_arrival = metrics.absolute_slippage <= 0  # Negative slippage = better than arrival
        beat_vwap = False
        if metrics.benchmark_vwap:
            if metrics.side == "BUY":
                beat_vwap = metrics.average_execution_price <= metrics.benchmark_vwap
            else:
                beat_vwap = metrics.average_execution_price >= metrics.benchmark_vwap
        
        quality = ExecutionQuality(
            order_id=order_id,
            symbol=metrics.symbol,
            price_quality=price_quality,
            speed_quality=speed_quality,
            fill_quality=fill_quality,
            overall_quality=overall,
            beat_arrival_price=beat_arrival,
            beat_vwap=beat_vwap,
        )
        
        self.quality_assessments[order_id] = quality
        logger.info(f"Quality {order_id}: {overall:.1f}/100")
        
        return quality
    
    def get_statistics(
        self,
        symbol: Optional[str] = None,
        lookback_hours: int = 24,
    ) -> Dict:
        """Get aggregate slippage statistics"""
        
        cutoff = datetime.utcnow().timestamp() - (lookback_hours * 3600)
        
        # Filter executions
        filtered = [
            m for m in self.executions.values()
            if m.timestamp.timestamp() > cutoff
            and (symbol is None or m.symbol == symbol)
        ]
        
        if not filtered:
            return {
                "num_executions": 0,
                "avg_slippage_bps": 0.0,
                "median_slippage_bps": 0.0,
                "max_slippage_bps": 0.0,
                "avg_market_impact_bps": 0.0,
            }
        
        slippages = [m.slippage_bps for m in filtered]
        impacts = [m.market_impact_bps for m in filtered if m.market_impact_bps != 0.0]
        
        stats = {
            "num_executions": len(filtered),
            "avg_slippage_bps": np.mean(slippages),
            "median_slippage_bps": np.median(slippages),
            "max_slippage_bps": np.max(slippages),
            "min_slippage_bps": np.min(slippages),
            "std_slippage_bps": np.std(slippages),
            "avg_market_impact_bps": np.mean(impacts) if impacts else 0.0,
        }
        
        return stats
    
    def get_quality_statistics(
        self,
        lookback_hours: int = 24,
    ) -> Dict:
        """Get aggregate quality statistics"""
        
        cutoff = datetime.utcnow().timestamp() - (lookback_hours * 3600)
        
        filtered = [
            q for q in self.quality_assessments.values()
            if q.timestamp.timestamp() > cutoff
        ]
        
        if not filtered:
            return {
                "num_assessments": 0,
                "avg_overall_quality": 0.0,
            }
        
        qualities = [q.overall_quality for q in filtered]
        beat_arrival_rate = sum(1 for q in filtered if q.beat_arrival_price) / len(filtered)
        beat_vwap_rate = sum(1 for q in filtered if q.beat_vwap) / len(filtered)
        
        stats = {
            "num_assessments": len(filtered),
            "avg_overall_quality": np.mean(qualities),
            "avg_price_quality": np.mean([q.price_quality for q in filtered]),
            "avg_speed_quality": np.mean([q.speed_quality for q in filtered]),
            "avg_fill_quality": np.mean([q.fill_quality for q in filtered]),
            "beat_arrival_rate": beat_arrival_rate * 100,
            "beat_vwap_rate": beat_vwap_rate * 100,
        }
        
        return stats
