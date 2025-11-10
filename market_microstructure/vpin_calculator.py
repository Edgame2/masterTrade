"""
VPIN (Volume-Synchronized Probability of Informed Trading) Calculator

VPIN is a measure of order flow toxicity and informed trading.

High VPIN → High probability of informed traders → Adverse selection risk
Low VPIN → Mostly liquidity traders → Safe to provide liquidity

Based on Easley, López de Prado, and O'Hara (2012)
"""

from dataclasses import dataclass
from datetime import datetime
from typing import List, Dict, Optional
from enum import Enum
import numpy as np
import logging

logger = logging.getLogger(__name__)


class ToxicityLevel(Enum):
    """Order flow toxicity levels"""
    LOW = "low"  # VPIN < 0.3
    MODERATE = "moderate"  # 0.3 <= VPIN < 0.5
    HIGH = "high"  # 0.5 <= VPIN < 0.7
    CRITICAL = "critical"  # VPIN >= 0.7


@dataclass
class VolumeBar:
    """Volume bucket for VPIN calculation"""
    timestamp: datetime
    buy_volume: float
    sell_volume: float
    total_volume: float
    
    @property
    def order_imbalance(self) -> float:
        """Absolute order imbalance"""
        return abs(self.buy_volume - self.sell_volume)


@dataclass
class VPINMetrics:
    """VPIN calculation results"""
    symbol: str
    timestamp: datetime
    
    # VPIN value (0-1)
    vpin: float
    
    # Toxicity level
    toxicity_level: ToxicityLevel
    
    # Components
    avg_order_imbalance: float
    total_volume: float
    num_buckets: int
    
    # Trend
    vpin_trend: str  # "increasing", "decreasing", "stable"
    
    # Risk assessment
    is_toxic: bool
    adverse_selection_risk: float  # 0-100
    
    def get_toxicity_description(self) -> str:
        """Get human-readable toxicity description"""
        descriptions = {
            ToxicityLevel.LOW: "Low toxicity - Safe liquidity provision",
            ToxicityLevel.MODERATE: "Moderate toxicity - Exercise caution",
            ToxicityLevel.HIGH: "High toxicity - Reduce liquidity provision",
            ToxicityLevel.CRITICAL: "Critical toxicity - Avoid providing liquidity",
        }
        return descriptions[self.toxicity_level]


class VPINCalculator:
    """
    Calculate VPIN (Volume-Synchronized Probability of Informed Trading).
    
    Algorithm:
    1. Partition volume into equal-sized buckets
    2. For each bucket, calculate order imbalance (|buy_vol - sell_vol|)
    3. VPIN = Average order imbalance / Average total volume
    
    High VPIN indicates informed trading (toxic flow).
    """
    
    def __init__(
        self,
        bucket_size: float = 50.0,  # Volume per bucket
        num_buckets: int = 50,  # Number of buckets for average
    ):
        self.bucket_size = bucket_size
        self.num_buckets = num_buckets
        
        self.volume_bars: Dict[str, List[VolumeBar]] = {}
        self.current_bucket: Dict[str, Dict] = {}
        
        logger.info(f"VPINCalculator initialized: bucket_size={bucket_size}, num_buckets={num_buckets}")
    
    def add_trade(
        self,
        symbol: str,
        timestamp: datetime,
        volume: float,
        is_buy: bool,
    ):
        """Add a trade to VPIN calculation"""
        
        if symbol not in self.current_bucket:
            self.current_bucket[symbol] = {
                "timestamp": timestamp,
                "buy_volume": 0.0,
                "sell_volume": 0.0,
                "total_volume": 0.0,
            }
        
        bucket = self.current_bucket[symbol]
        
        # Add to current bucket
        bucket["total_volume"] += volume
        if is_buy:
            bucket["buy_volume"] += volume
        else:
            bucket["sell_volume"] += volume
        
        # Check if bucket is full
        if bucket["total_volume"] >= self.bucket_size:
            # Create volume bar
            bar = VolumeBar(
                timestamp=bucket["timestamp"],
                buy_volume=bucket["buy_volume"],
                sell_volume=bucket["sell_volume"],
                total_volume=bucket["total_volume"],
            )
            
            # Store bar
            if symbol not in self.volume_bars:
                self.volume_bars[symbol] = []
            self.volume_bars[symbol].append(bar)
            
            # Keep only recent buckets
            if len(self.volume_bars[symbol]) > self.num_buckets * 2:
                self.volume_bars[symbol] = self.volume_bars[symbol][-self.num_buckets * 2:]
            
            # Reset bucket
            self.current_bucket[symbol] = {
                "timestamp": timestamp,
                "buy_volume": 0.0,
                "sell_volume": 0.0,
                "total_volume": 0.0,
            }
            
            logger.debug(f"Completed volume bucket {symbol}: {bar.total_volume} volume")
    
    def calculate_vpin(self, symbol: str) -> Optional[VPINMetrics]:
        """Calculate VPIN for symbol"""
        
        if symbol not in self.volume_bars or len(self.volume_bars[symbol]) < self.num_buckets:
            return None
        
        # Get recent buckets
        recent_bars = self.volume_bars[symbol][-self.num_buckets:]
        
        # Calculate average order imbalance
        imbalances = [bar.order_imbalance for bar in recent_bars]
        avg_imbalance = np.mean(imbalances)
        
        # Calculate average volume
        volumes = [bar.total_volume for bar in recent_bars]
        avg_volume = np.mean(volumes)
        
        # VPIN = Avg Order Imbalance / Avg Volume
        vpin = avg_imbalance / avg_volume if avg_volume > 0 else 0.0
        
        # Determine toxicity level
        if vpin < 0.3:
            toxicity = ToxicityLevel.LOW
        elif vpin < 0.5:
            toxicity = ToxicityLevel.MODERATE
        elif vpin < 0.7:
            toxicity = ToxicityLevel.HIGH
        else:
            toxicity = ToxicityLevel.CRITICAL
        
        # Trend analysis (compare recent vs older)
        if len(self.volume_bars[symbol]) >= self.num_buckets * 2:
            older_bars = self.volume_bars[symbol][-self.num_buckets * 2:-self.num_buckets]
            older_vpin = np.mean([b.order_imbalance for b in older_bars]) / np.mean([b.total_volume for b in older_bars])
            
            if vpin > older_vpin * 1.1:
                trend = "increasing"
            elif vpin < older_vpin * 0.9:
                trend = "decreasing"
            else:
                trend = "stable"
        else:
            trend = "stable"
        
        # Risk assessment
        is_toxic = vpin >= 0.5
        adverse_selection_risk = min(100, vpin * 100)
        
        metrics = VPINMetrics(
            symbol=symbol,
            timestamp=datetime.utcnow(),
            vpin=vpin,
            toxicity_level=toxicity,
            avg_order_imbalance=avg_imbalance,
            total_volume=sum(volumes),
            num_buckets=len(recent_bars),
            vpin_trend=trend,
            is_toxic=is_toxic,
            adverse_selection_risk=adverse_selection_risk,
        )
        
        logger.info(f"VPIN {symbol}: {vpin:.3f} ({toxicity.value}, trend: {trend})")
        return metrics
    
    def get_vpin_history(self, symbol: str, num_points: int = 50) -> List[float]:
        """Get VPIN time series"""
        
        if symbol not in self.volume_bars:
            return []
        
        bars = self.volume_bars[symbol]
        
        # Calculate VPIN for rolling windows
        vpin_values = []
        
        for i in range(self.num_buckets, len(bars) + 1):
            window = bars[i - self.num_buckets:i]
            
            avg_imbalance = np.mean([b.order_imbalance for b in window])
            avg_volume = np.mean([b.total_volume for b in window])
            
            vpin = avg_imbalance / avg_volume if avg_volume > 0 else 0.0
            vpin_values.append(vpin)
        
        # Return recent values
        return vpin_values[-num_points:]
    
    def detect_toxicity_spike(
        self,
        symbol: str,
        threshold: float = 0.6,
    ) -> Dict:
        """Detect sudden spike in toxicity"""
        
        metrics = self.calculate_vpin(symbol)
        if not metrics:
            return {"spike_detected": False}
        
        # Check if VPIN exceeds threshold and is increasing
        is_spike = metrics.vpin >= threshold and metrics.vpin_trend == "increasing"
        
        return {
            "spike_detected": is_spike,
            "current_vpin": metrics.vpin,
            "toxicity_level": metrics.toxicity_level.value,
            "trend": metrics.vpin_trend,
            "recommendation": metrics.get_toxicity_description(),
        }
    
    def estimate_adverse_selection_cost(
        self,
        symbol: str,
        spread_bps: float,
    ) -> Optional[Dict]:
        """
        Estimate adverse selection cost component of spread.
        
        Adverse selection cost ≈ VPIN * Spread
        """
        metrics = self.calculate_vpin(symbol)
        if not metrics:
            return None
        
        # Adverse selection component
        adverse_selection_bps = metrics.vpin * spread_bps
        
        # Order processing cost (residual)
        order_processing_bps = (1 - metrics.vpin) * spread_bps
        
        return {
            "total_spread_bps": spread_bps,
            "adverse_selection_bps": adverse_selection_bps,
            "order_processing_bps": order_processing_bps,
            "vpin": metrics.vpin,
            "adverse_selection_pct": metrics.vpin * 100,
        }
