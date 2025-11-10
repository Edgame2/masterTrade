"""
Signal Aggregator

Aggregates signals from multiple timeframes into unified trading signals.
Combines trend, confluence, and divergence analysis.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional
import logging

from .timeframe_synchronizer import Timeframe, TimeframeSynchronizer
from .trend_analyzer import TrendAnalyzer, TrendDirection, TimeframeTrend
from .confluence_detector import ConfluenceDetector, ConfluenceSignal, ConfluenceLevel
from .divergence_detector import DivergenceDetector, Divergence, DivergenceType

logger = logging.getLogger(__name__)


class SignalStrength(Enum):
    """Overall signal strength"""
    VERY_WEAK = "very_weak"
    WEAK = "weak"
    MODERATE = "moderate"
    STRONG = "strong"
    VERY_STRONG = "very_strong"


@dataclass
class AggregatedSignal:
    """Comprehensive multi-timeframe signal"""
    symbol: str
    timestamp: datetime
    
    # Overall signal
    direction: TrendDirection
    signal_strength: SignalStrength
    confidence: float  # 0-1
    
    # Component signals
    confluence_signal: Optional[ConfluenceSignal]
    divergences: List[Divergence]
    trends: Dict[Timeframe, TimeframeTrend]
    
    # Trading recommendations
    is_entry_signal: bool
    is_exit_signal: bool
    recommended_action: str  # BUY/SELL/HOLD/REDUCE
    
    # Risk assessment
    risk_level: str  # HIGH/MEDIUM/LOW
    risk_factors: List[str]
    
    # Entry/exit levels
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit_1: Optional[float] = None
    take_profit_2: Optional[float] = None
    
    # Additional context
    notes: List[str] = None
    
    def __post_init__(self):
        if self.notes is None:
            self.notes = []
    
    def to_dict(self) -> dict:
        """Convert to dictionary for API"""
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp.isoformat(),
            "direction": self.direction.value,
            "signal_strength": self.signal_strength.value,
            "confidence": self.confidence,
            "is_entry_signal": self.is_entry_signal,
            "is_exit_signal": self.is_exit_signal,
            "recommended_action": self.recommended_action,
            "risk_level": self.risk_level,
            "risk_factors": self.risk_factors,
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "take_profit_1": self.take_profit_1,
            "take_profit_2": self.take_profit_2,
            "confluence": self.confluence_signal.to_dict() if self.confluence_signal else None,
            "divergences": [d.to_dict() for d in self.divergences],
            "trends": {
                tf.value: {
                    "direction": trend.direction.value,
                    "strength": trend.strength.value,
                    "strength_score": trend.strength_score,
                }
                for tf, trend in self.trends.items()
            },
            "notes": self.notes,
        }


class SignalAggregator:
    """
    Aggregates signals from all multi-timeframe components.
    
    Strategy:
    1. Analyze trends across all timeframes
    2. Detect confluence
    3. Identify divergences
    4. Combine into unified signal
    5. Generate trading recommendations
    """
    
    def __init__(
        self,
        synchronizer: TimeframeSynchronizer,
        trend_analyzer: TrendAnalyzer,
        confluence_detector: ConfluenceDetector,
        divergence_detector: DivergenceDetector
    ):
        self.synchronizer = synchronizer
        self.trend_analyzer = trend_analyzer
        self.confluence_detector = confluence_detector
        self.divergence_detector = divergence_detector
        
        # Default timeframes for analysis
        self.default_timeframes = [
            Timeframe.M15,
            Timeframe.H1,
            Timeframe.H4,
            Timeframe.D1,
        ]
        
        # Signal thresholds
        self.entry_confidence_threshold = 0.70
        self.exit_confidence_threshold = 0.30
    
    def generate_signal(
        self,
        symbol: str,
        timeframes: Optional[List[Timeframe]] = None
    ) -> AggregatedSignal:
        """Generate comprehensive multi-timeframe signal"""
        if timeframes is None:
            timeframes = self.default_timeframes
        
        # Analyze trends
        trends = self.trend_analyzer.analyze_multiple_timeframes(symbol, timeframes)
        
        if not trends:
            return self._create_no_signal(symbol)
        
        # Detect confluence
        confluence = self.confluence_detector.detect_confluence(symbol, timeframes)
        
        # Detect divergences
        divergences = self.divergence_detector.detect_all_divergences(
            symbol, timeframes
        )
        
        # Aggregate into unified signal
        return self._aggregate_signals(
            symbol, trends, confluence, divergences
        )
    
    def generate_entry_signal(
        self,
        symbol: str,
        higher_timeframes: Optional[List[Timeframe]] = None,
        lower_timeframes: Optional[List[Timeframe]] = None
    ) -> Optional[AggregatedSignal]:
        """
        Generate entry signal using multi-timeframe strategy.
        
        Higher timeframes define trend, lower timeframes provide timing.
        """
        if higher_timeframes is None:
            higher_timeframes = [Timeframe.H4, Timeframe.D1]
        
        if lower_timeframes is None:
            lower_timeframes = [Timeframe.M15, Timeframe.H1]
        
        # Get higher timeframe direction
        higher_trends = self.trend_analyzer.analyze_multiple_timeframes(
            symbol, higher_timeframes
        )
        
        if not higher_trends:
            return None
        
        # Check higher timeframe alignment
        higher_alignment = self.trend_analyzer.check_trend_alignment(
            symbol, higher_timeframes
        )
        
        # Need strong alignment on higher timeframes
        if higher_alignment["alignment_score"] < 70:
            return None
        
        # Get confluence on lower timeframes
        confluence = self.confluence_detector.detect_multi_timeframe_entry(
            symbol, higher_timeframes, lower_timeframes
        )
        
        if not confluence or not confluence.is_entry_signal:
            return None
        
        # Generate full signal
        all_timeframes = higher_timeframes + lower_timeframes
        signal = self.generate_signal(symbol, all_timeframes)
        
        # Only return if it's a strong entry signal
        if signal.is_entry_signal and signal.confidence >= self.entry_confidence_threshold:
            return signal
        
        return None
    
    def _aggregate_signals(
        self,
        symbol: str,
        trends: Dict[Timeframe, TimeframeTrend],
        confluence: ConfluenceSignal,
        divergences: List[Divergence]
    ) -> AggregatedSignal:
        """Aggregate all signals into unified signal"""
        # Determine overall direction
        direction = confluence.direction
        
        # Calculate overall confidence
        confidence = self._calculate_overall_confidence(
            trends, confluence, divergences
        )
        
        # Classify signal strength
        signal_strength = self._classify_signal_strength(confluence, confidence)
        
        # Determine if entry/exit signal
        is_entry = confidence >= self.entry_confidence_threshold
        is_exit = confidence < self.exit_confidence_threshold
        
        # Generate recommendation
        recommended_action = self._generate_recommendation(
            direction, confluence, divergences, confidence
        )
        
        # Assess risk
        risk_level, risk_factors = self._assess_risk(
            trends, confluence, divergences
        )
        
        # Calculate entry/exit levels
        entry_price = self._calculate_entry_price(trends, direction)
        stop_loss = self._calculate_stop_loss(trends, direction, entry_price)
        tp1, tp2 = self._calculate_take_profits(trends, direction, entry_price)
        
        # Generate notes
        notes = self._generate_notes(trends, confluence, divergences)
        
        return AggregatedSignal(
            symbol=symbol,
            timestamp=datetime.utcnow(),
            direction=direction,
            signal_strength=signal_strength,
            confidence=confidence,
            confluence_signal=confluence,
            divergences=divergences,
            trends=trends,
            is_entry_signal=is_entry,
            is_exit_signal=is_exit,
            recommended_action=recommended_action,
            risk_level=risk_level,
            risk_factors=risk_factors,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit_1=tp1,
            take_profit_2=tp2,
            notes=notes,
        )
    
    def _calculate_overall_confidence(
        self,
        trends: Dict[Timeframe, TimeframeTrend],
        confluence: ConfluenceSignal,
        divergences: List[Divergence]
    ) -> float:
        """
        Calculate overall confidence (0-1).
        
        Factors:
        - Confluence confidence (50%)
        - Average trend strength (30%)
        - Divergence penalty (20%)
        """
        # Confluence confidence
        confluence_conf = confluence.confidence * 0.5
        
        # Average trend strength
        if trends:
            avg_strength = sum(t.strength_score for t in trends.values()) / len(trends)
            trend_conf = (avg_strength / 100) * 0.3
        else:
            trend_conf = 0.0
        
        # Divergence penalty
        significant_divergences = [d for d in divergences if d.is_significant]
        if significant_divergences:
            # More significant divergences = lower confidence
            divergence_penalty = len(significant_divergences) * 0.05
            divergence_conf = max(0, 0.2 - divergence_penalty)
        else:
            divergence_conf = 0.2
        
        return min(confluence_conf + trend_conf + divergence_conf, 1.0)
    
    def _classify_signal_strength(
        self,
        confluence: ConfluenceSignal,
        confidence: float
    ) -> SignalStrength:
        """Classify overall signal strength"""
        if confidence >= 0.8 and confluence.confluence_level == ConfluenceLevel.VERY_STRONG:
            return SignalStrength.VERY_STRONG
        elif confidence >= 0.7:
            return SignalStrength.STRONG
        elif confidence >= 0.5:
            return SignalStrength.MODERATE
        elif confidence >= 0.3:
            return SignalStrength.WEAK
        else:
            return SignalStrength.VERY_WEAK
    
    def _generate_recommendation(
        self,
        direction: TrendDirection,
        confluence: ConfluenceSignal,
        divergences: List[Divergence],
        confidence: float
    ) -> str:
        """Generate trading recommendation"""
        if confidence < 0.3:
            return "HOLD - Low confidence, wait for clearer signal"
        
        # Check for exit signals
        if confidence < self.exit_confidence_threshold:
            return "REDUCE - Consider reducing exposure"
        
        # Check for entry signals
        if confidence >= self.entry_confidence_threshold:
            if direction == TrendDirection.UP:
                return "BUY - Strong bullish signal across timeframes"
            elif direction == TrendDirection.DOWN:
                return "SELL - Strong bearish signal across timeframes"
        
        # Check divergences
        bullish_div = any(
            d.divergence_type == DivergenceType.BULLISH_REVERSAL
            for d in divergences if d.is_significant
        )
        bearish_div = any(
            d.divergence_type == DivergenceType.BEARISH_REVERSAL
            for d in divergences if d.is_significant
        )
        
        if bullish_div:
            return "BUY - Bullish divergence detected"
        elif bearish_div:
            return "SELL - Bearish divergence detected"
        
        return "HOLD - Wait for better entry"
    
    def _assess_risk(
        self,
        trends: Dict[Timeframe, TimeframeTrend],
        confluence: ConfluenceSignal,
        divergences: List[Divergence]
    ) -> tuple[str, List[str]]:
        """Assess overall risk level and identify risk factors"""
        risk_factors = []
        risk_score = 0
        
        # Check confluence
        if confluence.confluence_level in [ConfluenceLevel.NONE, ConfluenceLevel.WEAK]:
            risk_factors.append("Weak confluence across timeframes")
            risk_score += 30
        
        # Check divergences
        significant_divs = [d for d in divergences if d.is_significant]
        if significant_divs:
            risk_factors.append(f"{len(significant_divs)} significant divergence(s) detected")
            risk_score += len(significant_divs) * 15
        
        # Check trend consistency
        weak_trends = [t for t in trends.values() if t.strength_score < 40]
        if len(weak_trends) > len(trends) / 2:
            risk_factors.append("Majority of trends are weak")
            risk_score += 20
        
        # Classify risk level
        if risk_score >= 60:
            risk_level = "HIGH"
        elif risk_score >= 30:
            risk_level = "MEDIUM"
        else:
            risk_level = "LOW"
        
        if not risk_factors:
            risk_factors.append("No major risk factors identified")
        
        return risk_level, risk_factors
    
    def _calculate_entry_price(
        self,
        trends: Dict[Timeframe, TimeframeTrend],
        direction: TrendDirection
    ) -> Optional[float]:
        """Calculate suggested entry price"""
        if not trends:
            return None
        
        # Use current price from highest timeframe
        highest_tf = max(trends.keys(), key=lambda tf: tf.minutes)
        return trends[highest_tf].current_price
    
    def _calculate_stop_loss(
        self,
        trends: Dict[Timeframe, TimeframeTrend],
        direction: TrendDirection,
        entry_price: Optional[float]
    ) -> Optional[float]:
        """Calculate stop loss level"""
        if not trends or entry_price is None:
            return None
        
        # Use support/resistance from highest timeframe
        highest_tf = max(trends.keys(), key=lambda tf: tf.minutes)
        trend = trends[highest_tf]
        
        if direction == TrendDirection.UP:
            # For long, use support
            if trend.support_level:
                # Place stop slightly below support
                return trend.support_level * 0.99
            else:
                # Use 2% stop
                return entry_price * 0.98
        
        elif direction == TrendDirection.DOWN:
            # For short, use resistance
            if trend.resistance_level:
                # Place stop slightly above resistance
                return trend.resistance_level * 1.01
            else:
                # Use 2% stop
                return entry_price * 1.02
        
        return None
    
    def _calculate_take_profits(
        self,
        trends: Dict[Timeframe, TimeframeTrend],
        direction: TrendDirection,
        entry_price: Optional[float]
    ) -> tuple[Optional[float], Optional[float]]:
        """Calculate take profit levels"""
        if not trends or entry_price is None:
            return None, None
        
        # Use resistance/support from highest timeframe
        highest_tf = max(trends.keys(), key=lambda tf: tf.minutes)
        trend = trends[highest_tf]
        
        if direction == TrendDirection.UP:
            # For long, use resistance as TP
            if trend.resistance_level:
                tp1 = trend.resistance_level * 0.99  # Conservative
                tp2 = trend.resistance_level * 1.02  # Extended
            else:
                # Use 3% and 5%
                tp1 = entry_price * 1.03
                tp2 = entry_price * 1.05
        
        elif direction == TrendDirection.DOWN:
            # For short, use support as TP
            if trend.support_level:
                tp1 = trend.support_level * 1.01  # Conservative
                tp2 = trend.support_level * 0.98  # Extended
            else:
                # Use 3% and 5%
                tp1 = entry_price * 0.97
                tp2 = entry_price * 0.95
        else:
            return None, None
        
        return tp1, tp2
    
    def _generate_notes(
        self,
        trends: Dict[Timeframe, TimeframeTrend],
        confluence: ConfluenceSignal,
        divergences: List[Divergence]
    ) -> List[str]:
        """Generate additional notes about the signal"""
        notes = []
        
        # Confluence notes
        if confluence.confluence_level == ConfluenceLevel.VERY_STRONG:
            notes.append("Excellent confluence across all timeframes")
        elif confluence.confluence_level in [ConfluenceLevel.NONE, ConfluenceLevel.WEAK]:
            notes.append("Weak confluence - exercise caution")
        
        # Divergence notes
        for div in divergences:
            if div.is_significant:
                notes.append(
                    f"{div.divergence_type.value} between "
                    f"{div.higher_timeframe.value} and {div.lower_timeframe.value}"
                )
        
        # Trend strength notes
        very_strong_trends = [
            tf.value for tf, t in trends.items()
            if t.strength_score >= 80
        ]
        if very_strong_trends:
            notes.append(f"Very strong trends on: {', '.join(very_strong_trends)}")
        
        return notes
    
    def _create_no_signal(self, symbol: str) -> AggregatedSignal:
        """Create signal when no data available"""
        return AggregatedSignal(
            symbol=symbol,
            timestamp=datetime.utcnow(),
            direction=TrendDirection.UNKNOWN,
            signal_strength=SignalStrength.VERY_WEAK,
            confidence=0.0,
            confluence_signal=None,
            divergences=[],
            trends={},
            is_entry_signal=False,
            is_exit_signal=False,
            recommended_action="HOLD - Insufficient data",
            risk_level="HIGH",
            risk_factors=["No data available for analysis"],
            notes=["Unable to generate signal - check data availability"],
        )
