"""
Divergence Detector

Detects divergences between timeframes that can signal:
- Trend reversals
- Continuation patterns
- False breakouts
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional
import logging

from .timeframe_synchronizer import Timeframe
from .trend_analyzer import TrendAnalyzer, TrendDirection, TimeframeTrend

logger = logging.getLogger(__name__)


class DivergenceType(Enum):
    """Types of timeframe divergences"""
    # Directional divergences
    BULLISH_REVERSAL = "bullish_reversal"  # Lower TF bearish, higher TF bullish
    BEARISH_REVERSAL = "bearish_reversal"  # Lower TF bullish, higher TF bearish
    
    # Momentum divergences
    WEAKENING_UPTREND = "weakening_uptrend"  # Higher TF up, lower TF weakening
    WEAKENING_DOWNTREND = "weakening_downtrend"  # Higher TF down, lower TF weakening
    
    # Strength divergences
    STRENGTH_DIVERGENCE = "strength_divergence"  # Different strength levels
    
    # No divergence
    ALIGNED = "aligned"  # All timeframes agree


@dataclass
class Divergence:
    """Detected divergence between timeframes"""
    symbol: str
    timestamp: datetime
    divergence_type: DivergenceType
    
    # Timeframes involved
    higher_timeframe: Timeframe
    lower_timeframe: Timeframe
    
    # Trend details
    higher_tf_trend: TimeframeTrend
    lower_tf_trend: TimeframeTrend
    
    # Divergence metrics
    severity: float  # 0-100 (how strong the divergence)
    is_significant: bool  # True if divergence is actionable
    
    # Trading implications
    expected_outcome: str  # What this divergence suggests
    recommended_action: str  # Buy/Sell/Wait
    risk_level: str  # High/Medium/Low
    
    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp.isoformat(),
            "divergence_type": self.divergence_type.value,
            "higher_timeframe": self.higher_timeframe.value,
            "lower_timeframe": self.lower_timeframe.value,
            "higher_tf_direction": self.higher_tf_trend.direction.value,
            "lower_tf_direction": self.lower_tf_trend.direction.value,
            "severity": self.severity,
            "is_significant": self.is_significant,
            "expected_outcome": self.expected_outcome,
            "recommended_action": self.recommended_action,
            "risk_level": self.risk_level,
        }


class DivergenceDetector:
    """
    Detects divergences between timeframes.
    
    Key divergence patterns:
    1. Directional: Higher TF bullish, lower TF bearish (pullback opportunity)
    2. Momentum: Diverging momentum across timeframes
    3. Strength: Strong higher TF, weak lower TF
    """
    
    def __init__(self, trend_analyzer: TrendAnalyzer):
        self.trend_analyzer = trend_analyzer
        
        # Significance thresholds
        self.min_severity_threshold = 40.0  # Minimum severity to be significant
        self.strength_difference_threshold = 30.0  # Min strength difference
    
    def detect_divergence(
        self,
        symbol: str,
        higher_timeframe: Timeframe,
        lower_timeframe: Timeframe
    ) -> Optional[Divergence]:
        """Detect divergence between two timeframes"""
        # Analyze both timeframes
        higher_trend = self.trend_analyzer.analyze_trend(symbol, higher_timeframe)
        lower_trend = self.trend_analyzer.analyze_trend(symbol, lower_timeframe)
        
        if not higher_trend or not lower_trend:
            return None
        
        # Determine divergence type
        divergence_type = self._classify_divergence(higher_trend, lower_trend)
        
        if divergence_type == DivergenceType.ALIGNED:
            return None  # No divergence
        
        # Calculate severity
        severity = self._calculate_severity(higher_trend, lower_trend, divergence_type)
        
        # Check significance
        is_significant = severity >= self.min_severity_threshold
        
        # Generate trading implications
        expected_outcome = self._generate_expected_outcome(
            divergence_type, higher_trend, lower_trend
        )
        recommended_action = self._generate_recommendation(
            divergence_type, higher_trend, lower_trend, severity
        )
        risk_level = self._assess_risk_level(divergence_type, severity)
        
        return Divergence(
            symbol=symbol,
            timestamp=datetime.utcnow(),
            divergence_type=divergence_type,
            higher_timeframe=higher_timeframe,
            lower_timeframe=lower_timeframe,
            higher_tf_trend=higher_trend,
            lower_tf_trend=lower_trend,
            severity=severity,
            is_significant=is_significant,
            expected_outcome=expected_outcome,
            recommended_action=recommended_action,
            risk_level=risk_level,
        )
    
    def detect_all_divergences(
        self,
        symbol: str,
        timeframes: List[Timeframe]
    ) -> List[Divergence]:
        """Detect all divergences across multiple timeframes"""
        divergences = []
        
        # Sort timeframes by size
        sorted_tfs = sorted(timeframes, key=lambda tf: tf.minutes)
        
        # Compare each pair of adjacent timeframes
        for i in range(len(sorted_tfs) - 1):
            lower_tf = sorted_tfs[i]
            higher_tf = sorted_tfs[i + 1]
            
            divergence = self.detect_divergence(symbol, higher_tf, lower_tf)
            if divergence:
                divergences.append(divergence)
        
        return divergences
    
    def _classify_divergence(
        self,
        higher_trend: TimeframeTrend,
        lower_trend: TimeframeTrend
    ) -> DivergenceType:
        """Classify the type of divergence"""
        higher_dir = higher_trend.direction
        lower_dir = lower_trend.direction
        
        # Check alignment first
        if higher_dir == lower_dir:
            # Check strength divergence
            strength_diff = abs(
                higher_trend.strength_score - lower_trend.strength_score
            )
            
            if strength_diff > self.strength_difference_threshold:
                return DivergenceType.STRENGTH_DIVERGENCE
            else:
                return DivergenceType.ALIGNED
        
        # Directional divergences
        if higher_dir == TrendDirection.UP and lower_dir == TrendDirection.DOWN:
            # Higher TF bullish, lower TF bearish = pullback in uptrend
            return DivergenceType.BULLISH_REVERSAL
        
        elif higher_dir == TrendDirection.DOWN and lower_dir == TrendDirection.UP:
            # Higher TF bearish, lower TF bullish = rally in downtrend
            return DivergenceType.BEARISH_REVERSAL
        
        # Momentum weakening
        elif higher_dir == TrendDirection.UP and lower_dir == TrendDirection.SIDEWAYS:
            return DivergenceType.WEAKENING_UPTREND
        
        elif higher_dir == TrendDirection.DOWN and lower_dir == TrendDirection.SIDEWAYS:
            return DivergenceType.WEAKENING_DOWNTREND
        
        # Mixed signals
        return DivergenceType.STRENGTH_DIVERGENCE
    
    def _calculate_severity(
        self,
        higher_trend: TimeframeTrend,
        lower_trend: TimeframeTrend,
        divergence_type: DivergenceType
    ) -> float:
        """
        Calculate divergence severity (0-100).
        
        Factors:
        - Direction difference
        - Strength difference
        - Momentum divergence
        """
        # Direction component (40%)
        if higher_trend.direction != lower_trend.direction:
            direction_score = 40.0
        else:
            direction_score = 0.0
        
        # Strength component (30%)
        strength_diff = abs(
            higher_trend.strength_score - lower_trend.strength_score
        )
        strength_score = min(strength_diff, 100) * 0.3
        
        # Momentum component (30%)
        momentum_diff = abs(
            higher_trend.momentum_score - lower_trend.momentum_score
        )
        momentum_score = min(momentum_diff, 100) * 0.3
        
        return direction_score + strength_score + momentum_score
    
    def _generate_expected_outcome(
        self,
        divergence_type: DivergenceType,
        higher_trend: TimeframeTrend,
        lower_trend: TimeframeTrend
    ) -> str:
        """Generate expected outcome description"""
        outcomes = {
            DivergenceType.BULLISH_REVERSAL: (
                "Pullback in uptrend. Lower timeframe correction in higher "
                "timeframe uptrend. Expect resumption of uptrend."
            ),
            DivergenceType.BEARISH_REVERSAL: (
                "Rally in downtrend. Lower timeframe bounce in higher "
                "timeframe downtrend. Expect resumption of downtrend."
            ),
            DivergenceType.WEAKENING_UPTREND: (
                "Uptrend losing momentum. Lower timeframe consolidation "
                "may signal pause or reversal."
            ),
            DivergenceType.WEAKENING_DOWNTREND: (
                "Downtrend losing momentum. Lower timeframe consolidation "
                "may signal pause or reversal."
            ),
            DivergenceType.STRENGTH_DIVERGENCE: (
                "Different trend strengths across timeframes. "
                "Monitor for alignment or further divergence."
            ),
            DivergenceType.ALIGNED: "Timeframes aligned. No divergence.",
        }
        
        return outcomes.get(divergence_type, "Unknown divergence pattern")
    
    def _generate_recommendation(
        self,
        divergence_type: DivergenceType,
        higher_trend: TimeframeTrend,
        lower_trend: TimeframeTrend,
        severity: float
    ) -> str:
        """Generate trading recommendation"""
        if severity < self.min_severity_threshold:
            return "WAIT - Divergence not significant enough"
        
        recommendations = {
            DivergenceType.BULLISH_REVERSAL: (
                "BUY - Enter long on lower timeframe pullback in uptrend"
            ),
            DivergenceType.BEARISH_REVERSAL: (
                "SELL - Enter short on lower timeframe rally in downtrend"
            ),
            DivergenceType.WEAKENING_UPTREND: (
                "CAUTION - Consider taking profits or tightening stops"
            ),
            DivergenceType.WEAKENING_DOWNTREND: (
                "CAUTION - Watch for potential reversal, reduce short exposure"
            ),
            DivergenceType.STRENGTH_DIVERGENCE: (
                "WAIT - Monitor for clearer direction"
            ),
        }
        
        return recommendations.get(
            divergence_type,
            "WAIT - Insufficient data for recommendation"
        )
    
    def _assess_risk_level(
        self,
        divergence_type: DivergenceType,
        severity: float
    ) -> str:
        """Assess risk level of acting on divergence"""
        # High severity divergences are riskier
        if severity >= 70:
            return "HIGH"
        elif severity >= 50:
            return "MEDIUM"
        else:
            return "LOW"


def find_optimal_entry_timeframe(
    divergences: List[Divergence],
    current_position: Optional[str] = None
) -> Optional[Timeframe]:
    """
    Find optimal timeframe for entry based on divergences.
    
    Args:
        divergences: List of detected divergences
        current_position: Current position (long/short/none)
    
    Returns:
        Optimal timeframe for entry, or None if no clear signal
    """
    if not divergences:
        return None
    
    # Filter significant divergences
    significant = [d for d in divergences if d.is_significant]
    
    if not significant:
        return None
    
    # Look for bullish reversal divergences (buy opportunities)
    bullish = [
        d for d in significant
        if d.divergence_type == DivergenceType.BULLISH_REVERSAL
    ]
    
    if bullish:
        # Use lowest timeframe for entry timing
        return min(bullish, key=lambda d: d.lower_timeframe.minutes).lower_timeframe
    
    # Look for bearish reversal divergences (sell opportunities)
    bearish = [
        d for d in significant
        if d.divergence_type == DivergenceType.BEARISH_REVERSAL
    ]
    
    if bearish:
        # Use lowest timeframe for entry timing
        return min(bearish, key=lambda d: d.lower_timeframe.minutes).lower_timeframe
    
    return None
