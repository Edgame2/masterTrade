"""
Trend Analyzer

Analyzes trends across multiple timeframes to identify:
- Trend direction (up/down/sideways)
- Trend strength
- Trend consistency across timeframes
- Trend alignment and confluence
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional
import logging
import numpy as np

from .timeframe_synchronizer import Timeframe, TimeframeBar, TimeframeSynchronizer

logger = logging.getLogger(__name__)


class TrendDirection(Enum):
    """Trend direction"""
    UP = "up"
    DOWN = "down"
    SIDEWAYS = "sideways"
    UNKNOWN = "unknown"


class TrendStrength(Enum):
    """Trend strength levels"""
    VERY_WEAK = "very_weak"
    WEAK = "weak"
    MODERATE = "moderate"
    STRONG = "strong"
    VERY_STRONG = "very_strong"


@dataclass
class TimeframeTrend:
    """Trend information for a specific timeframe"""
    symbol: str
    timeframe: Timeframe
    timestamp: datetime
    
    # Trend characteristics
    direction: TrendDirection
    strength: TrendStrength
    strength_score: float  # 0-100
    
    # Technical indicators
    ema_short: float  # Short-term EMA (8 periods)
    ema_long: float   # Long-term EMA (21 periods)
    slope: float      # Trend line slope
    r_squared: float  # Trend line fit quality
    
    # Price levels
    current_price: float
    support_level: Optional[float] = None
    resistance_level: Optional[float] = None
    
    # Momentum
    momentum_score: float = 0.0  # -100 to +100
    
    def is_bullish(self) -> bool:
        """Check if trend is bullish"""
        return self.direction == TrendDirection.UP
    
    def is_bearish(self) -> bool:
        """Check if trend is bearish"""
        return self.direction == TrendDirection.DOWN
    
    def is_sideways(self) -> bool:
        """Check if trend is sideways"""
        return self.direction == TrendDirection.SIDEWAYS
    
    def is_strong_trend(self) -> bool:
        """Check if trend is strong"""
        return self.strength in [TrendStrength.STRONG, TrendStrength.VERY_STRONG]


class TrendAnalyzer:
    """
    Analyzes trends across multiple timeframes.
    
    Uses multiple methods:
    - Moving average crossovers (EMA 8/21)
    - Linear regression (slope and R²)
    - Price action (higher highs/lows)
    - Momentum indicators
    """
    
    def __init__(self, synchronizer: TimeframeSynchronizer):
        self.synchronizer = synchronizer
        
        # EMA periods
        self.ema_short_period = 8
        self.ema_long_period = 21
        
        # Trend detection parameters
        self.slope_threshold = 0.001  # Minimum slope for trending
        self.r_squared_threshold = 0.7  # Minimum R² for valid trend
    
    def analyze_trend(
        self,
        symbol: str,
        timeframe: Timeframe,
        lookback_periods: int = 50
    ) -> Optional[TimeframeTrend]:
        """Analyze trend for a single timeframe"""
        bars = self.synchronizer.get_bars(symbol, timeframe, count=lookback_periods)
        
        if len(bars) < self.ema_long_period:
            logger.warning(
                f"Insufficient bars for {symbol} {timeframe.value}: "
                f"{len(bars)} < {self.ema_long_period}"
            )
            return None
        
        latest_bar = bars[-1]
        
        # Calculate EMAs
        closes = [bar.close for bar in bars]
        ema_short = self._calculate_ema(closes, self.ema_short_period)
        ema_long = self._calculate_ema(closes, self.ema_long_period)
        
        # Calculate trend line (linear regression)
        slope, r_squared = self._calculate_trend_line(closes)
        
        # Determine direction
        direction = self._determine_direction(ema_short, ema_long, slope)
        
        # Calculate strength
        strength_score = self._calculate_strength_score(
            ema_short, ema_long, slope, r_squared, closes
        )
        strength = self._classify_strength(strength_score)
        
        # Find support/resistance
        support, resistance = self._find_support_resistance(bars)
        
        # Calculate momentum
        momentum_score = self._calculate_momentum(closes)
        
        return TimeframeTrend(
            symbol=symbol,
            timeframe=timeframe,
            timestamp=latest_bar.timestamp,
            direction=direction,
            strength=strength,
            strength_score=strength_score,
            ema_short=ema_short,
            ema_long=ema_long,
            slope=slope,
            r_squared=r_squared,
            current_price=latest_bar.close,
            support_level=support,
            resistance_level=resistance,
            momentum_score=momentum_score,
        )
    
    def analyze_multiple_timeframes(
        self,
        symbol: str,
        timeframes: List[Timeframe]
    ) -> Dict[Timeframe, TimeframeTrend]:
        """Analyze trends across multiple timeframes"""
        results = {}
        
        for timeframe in timeframes:
            trend = self.analyze_trend(symbol, timeframe)
            if trend:
                results[timeframe] = trend
        
        return results
    
    def check_trend_alignment(
        self,
        symbol: str,
        timeframes: List[Timeframe]
    ) -> Dict[str, any]:
        """
        Check if trends are aligned across timeframes.
        
        Returns:
            - alignment_score: 0-100 (100 = all aligned)
            - aligned_direction: Direction if aligned, None otherwise
            - bullish_count: Number of bullish timeframes
            - bearish_count: Number of bearish timeframes
            - sideways_count: Number of sideways timeframes
        """
        trends = self.analyze_multiple_timeframes(symbol, timeframes)
        
        if not trends:
            return {
                "alignment_score": 0.0,
                "aligned_direction": None,
                "bullish_count": 0,
                "bearish_count": 0,
                "sideways_count": 0,
            }
        
        # Count directions
        bullish_count = sum(1 for t in trends.values() if t.is_bullish())
        bearish_count = sum(1 for t in trends.values() if t.is_bearish())
        sideways_count = sum(1 for t in trends.values() if t.is_sideways())
        
        total = len(trends)
        
        # Determine alignment
        if bullish_count == total:
            alignment_score = 100.0
            aligned_direction = TrendDirection.UP
        elif bearish_count == total:
            alignment_score = 100.0
            aligned_direction = TrendDirection.DOWN
        elif sideways_count == total:
            alignment_score = 100.0
            aligned_direction = TrendDirection.SIDEWAYS
        else:
            # Partial alignment
            max_count = max(bullish_count, bearish_count, sideways_count)
            alignment_score = (max_count / total) * 100
            
            if max_count == bullish_count:
                aligned_direction = TrendDirection.UP
            elif max_count == bearish_count:
                aligned_direction = TrendDirection.DOWN
            else:
                aligned_direction = TrendDirection.SIDEWAYS
        
        return {
            "alignment_score": alignment_score,
            "aligned_direction": aligned_direction,
            "bullish_count": bullish_count,
            "bearish_count": bearish_count,
            "sideways_count": sideways_count,
            "trends": trends,
        }
    
    def _calculate_ema(self, values: List[float], period: int) -> float:
        """Calculate Exponential Moving Average"""
        if len(values) < period:
            return values[-1] if values else 0.0
        
        multiplier = 2 / (period + 1)
        ema = values[0]  # Start with first value
        
        for value in values[1:]:
            ema = (value * multiplier) + (ema * (1 - multiplier))
        
        return ema
    
    def _calculate_trend_line(self, values: List[float]) -> tuple[float, float]:
        """
        Calculate trend line using linear regression.
        
        Returns: (slope, r_squared)
        """
        if len(values) < 2:
            return 0.0, 0.0
        
        x = np.arange(len(values))
        y = np.array(values)
        
        # Linear regression
        coeffs = np.polyfit(x, y, 1)
        slope = coeffs[0]
        
        # Calculate R²
        y_pred = np.polyval(coeffs, x)
        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - np.mean(y)) ** 2)
        
        r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0.0
        
        return float(slope), float(r_squared)
    
    def _determine_direction(
        self,
        ema_short: float,
        ema_long: float,
        slope: float
    ) -> TrendDirection:
        """Determine trend direction from indicators"""
        # EMA crossover
        ema_bullish = ema_short > ema_long
        ema_bearish = ema_short < ema_long
        
        # Slope direction
        slope_bullish = slope > self.slope_threshold
        slope_bearish = slope < -self.slope_threshold
        
        # Combine signals
        if ema_bullish and slope_bullish:
            return TrendDirection.UP
        elif ema_bearish and slope_bearish:
            return TrendDirection.DOWN
        elif abs(slope) <= self.slope_threshold:
            return TrendDirection.SIDEWAYS
        else:
            # Mixed signals
            return TrendDirection.SIDEWAYS
    
    def _calculate_strength_score(
        self,
        ema_short: float,
        ema_long: float,
        slope: float,
        r_squared: float,
        closes: List[float]
    ) -> float:
        """
        Calculate trend strength score (0-100).
        
        Factors:
        - EMA separation (20%)
        - Slope magnitude (30%)
        - R² (trend consistency) (30%)
        - Recent momentum (20%)
        """
        if not closes:
            return 0.0
        
        # EMA separation (normalized)
        avg_price = np.mean(closes)
        ema_separation = abs(ema_short - ema_long) / avg_price if avg_price > 0 else 0
        ema_score = min(ema_separation * 100, 100) * 0.2
        
        # Slope magnitude (normalized)
        slope_score = min(abs(slope) * 1000, 100) * 0.3
        
        # R² score
        r_squared_score = r_squared * 100 * 0.3
        
        # Momentum (rate of change over last 10 periods)
        if len(closes) >= 10:
            recent_closes = closes[-10:]
            momentum = (recent_closes[-1] - recent_closes[0]) / recent_closes[0]
            momentum_score = min(abs(momentum) * 100, 100) * 0.2
        else:
            momentum_score = 0.0
        
        total_score = ema_score + slope_score + r_squared_score + momentum_score
        return min(max(total_score, 0.0), 100.0)
    
    def _classify_strength(self, strength_score: float) -> TrendStrength:
        """Classify strength score into categories"""
        if strength_score >= 80:
            return TrendStrength.VERY_STRONG
        elif strength_score >= 60:
            return TrendStrength.STRONG
        elif strength_score >= 40:
            return TrendStrength.MODERATE
        elif strength_score >= 20:
            return TrendStrength.WEAK
        else:
            return TrendStrength.VERY_WEAK
    
    def _find_support_resistance(
        self,
        bars: List[TimeframeBar]
    ) -> tuple[Optional[float], Optional[float]]:
        """Find recent support and resistance levels"""
        if len(bars) < 10:
            return None, None
        
        # Use last 20 bars for S/R
        recent_bars = bars[-20:]
        
        highs = [bar.high for bar in recent_bars]
        lows = [bar.low for bar in recent_bars]
        
        # Support: recent swing low
        support = min(lows)
        
        # Resistance: recent swing high
        resistance = max(highs)
        
        return support, resistance
    
    def _calculate_momentum(self, closes: List[float]) -> float:
        """
        Calculate momentum score (-100 to +100).
        
        Based on rate of change over multiple periods.
        """
        if len(closes) < 10:
            return 0.0
        
        # Calculate ROC for different periods
        roc_10 = (closes[-1] - closes[-10]) / closes[-10] if len(closes) >= 10 else 0
        roc_5 = (closes[-1] - closes[-5]) / closes[-5] if len(closes) >= 5 else 0
        
        # Weighted average (recent has more weight)
        momentum = (roc_5 * 0.6 + roc_10 * 0.4) * 100
        
        # Clamp to -100 to +100
        return max(min(momentum, 100.0), -100.0)
