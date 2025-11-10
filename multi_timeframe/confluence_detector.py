"""
Confluence Detector

Detects when multiple timeframes agree on direction or signals.
High confluence = higher probability trades.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional
import logging

from .timeframe_synchronizer import Timeframe
from .trend_analyzer import TrendAnalyzer, TrendDirection, TimeframeTrend

logger = logging.getLogger(__name__)


class ConfluenceLevel(Enum):
    """Confluence strength levels"""
    NONE = "none"           # No agreement
    WEAK = "weak"           # 2/5 or less agree
    MODERATE = "moderate"   # 3/5 agree
    STRONG = "strong"       # 4/5 agree
    VERY_STRONG = "very_strong"  # All agree


@dataclass
class ConfluenceSignal:
    """Signal with confluence across timeframes"""
    symbol: str
    timestamp: datetime
    
    # Confluence metrics
    direction: TrendDirection
    confluence_level: ConfluenceLevel
    confluence_score: float  # 0-100
    
    # Participating timeframes
    agreeing_timeframes: List[Timeframe]
    disagreeing_timeframes: List[Timeframe]
    
    # Strength metrics
    avg_trend_strength: float  # Average strength of agreeing trends
    weight_score: float  # Weighted by timeframe importance (higher TF = more weight)
    
    # Entry/exit recommendations
    is_entry_signal: bool
    is_exit_signal: bool
    confidence: float  # 0-1
    
    # Supporting data
    trends: Dict[Timeframe, TimeframeTrend]
    
    def to_dict(self) -> dict:
        """Convert to dictionary for API responses"""
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp.isoformat(),
            "direction": self.direction.value,
            "confluence_level": self.confluence_level.value,
            "confluence_score": self.confluence_score,
            "agreeing_timeframes": [tf.value for tf in self.agreeing_timeframes],
            "disagreeing_timeframes": [tf.value for tf in self.disagreeing_timeframes],
            "avg_trend_strength": self.avg_trend_strength,
            "weight_score": self.weight_score,
            "is_entry_signal": self.is_entry_signal,
            "is_exit_signal": self.is_exit_signal,
            "confidence": self.confidence,
            "trends": {
                tf.value: {
                    "direction": trend.direction.value,
                    "strength": trend.strength.value,
                    "strength_score": trend.strength_score,
                    "momentum": trend.momentum_score,
                }
                for tf, trend in self.trends.items()
            },
        }


class ConfluenceDetector:
    """
    Detects confluence across multiple timeframes.
    
    Confluence types:
    - Directional: Multiple timeframes agree on trend direction
    - Strength: Multiple strong trends in same direction
    - Momentum: Accelerating momentum across timeframes
    """
    
    def __init__(self, trend_analyzer: TrendAnalyzer):
        self.trend_analyzer = trend_analyzer
        
        # Timeframe weights (higher timeframes more important)
        self.timeframe_weights = {
            Timeframe.M1: 1.0,
            Timeframe.M5: 1.5,
            Timeframe.M15: 2.0,
            Timeframe.M30: 2.5,
            Timeframe.H1: 3.0,
            Timeframe.H4: 4.0,
            Timeframe.D1: 5.0,
            Timeframe.W1: 6.0,
        }
        
        # Confluence thresholds
        self.entry_confluence_threshold = 70.0  # Minimum for entry signal
        self.exit_confluence_threshold = 40.0   # Below this = exit
    
    def detect_confluence(
        self,
        symbol: str,
        timeframes: List[Timeframe],
        reference_direction: Optional[TrendDirection] = None
    ) -> ConfluenceSignal:
        """
        Detect confluence across timeframes.
        
        Args:
            symbol: Trading symbol
            timeframes: Timeframes to analyze
            reference_direction: If provided, check confluence for this direction
        """
        # Analyze trends
        trends = self.trend_analyzer.analyze_multiple_timeframes(symbol, timeframes)
        
        if not trends:
            return self._create_empty_signal(symbol, timeframes)
        
        # Determine primary direction (or use reference)
        if reference_direction:
            primary_direction = reference_direction
        else:
            primary_direction = self._determine_primary_direction(trends)
        
        # Find agreeing and disagreeing timeframes
        agreeing = []
        disagreeing = []
        
        for tf, trend in trends.items():
            if trend.direction == primary_direction:
                agreeing.append(tf)
            else:
                disagreeing.append(tf)
        
        # Calculate confluence metrics
        confluence_score = self._calculate_confluence_score(
            agreeing, disagreeing, trends, primary_direction
        )
        
        confluence_level = self._classify_confluence_level(
            len(agreeing), len(trends)
        )
        
        # Calculate average strength of agreeing trends
        if agreeing:
            avg_strength = sum(
                trends[tf].strength_score for tf in agreeing
            ) / len(agreeing)
        else:
            avg_strength = 0.0
        
        # Calculate weighted score
        weight_score = self._calculate_weight_score(agreeing, trends)
        
        # Determine if entry/exit signal
        is_entry = confluence_score >= self.entry_confluence_threshold
        is_exit = confluence_score < self.exit_confluence_threshold
        
        # Calculate confidence
        confidence = self._calculate_confidence(
            confluence_score, avg_strength, weight_score
        )
        
        latest_timestamp = max(trend.timestamp for trend in trends.values())
        
        return ConfluenceSignal(
            symbol=symbol,
            timestamp=latest_timestamp,
            direction=primary_direction,
            confluence_level=confluence_level,
            confluence_score=confluence_score,
            agreeing_timeframes=agreeing,
            disagreeing_timeframes=disagreeing,
            avg_trend_strength=avg_strength,
            weight_score=weight_score,
            is_entry_signal=is_entry,
            is_exit_signal=is_exit,
            confidence=confidence,
            trends=trends,
        )
    
    def detect_multi_timeframe_entry(
        self,
        symbol: str,
        higher_timeframes: List[Timeframe],
        lower_timeframes: List[Timeframe]
    ) -> Optional[ConfluenceSignal]:
        """
        Detect entry using multi-timeframe analysis.
        
        Strategy:
        - Higher timeframes define trend direction
        - Lower timeframes provide entry timing
        - Entry when both align
        """
        # Get higher timeframe trend
        higher_trends = self.trend_analyzer.analyze_multiple_timeframes(
            symbol, higher_timeframes
        )
        
        if not higher_trends:
            return None
        
        # Determine higher timeframe direction
        higher_direction = self._determine_primary_direction(higher_trends)
        
        if higher_direction == TrendDirection.SIDEWAYS:
            return None  # No clear higher TF trend
        
        # Check lower timeframe confluence with higher timeframe direction
        confluence = self.detect_confluence(
            symbol, lower_timeframes, reference_direction=higher_direction
        )
        
        # Only return if confluence is strong enough
        if confluence.confluence_score >= self.entry_confluence_threshold:
            return confluence
        
        return None
    
    def _determine_primary_direction(
        self,
        trends: Dict[Timeframe, TimeframeTrend]
    ) -> TrendDirection:
        """Determine primary direction from trends"""
        if not trends:
            return TrendDirection.UNKNOWN
        
        # Count directions with weighting
        direction_scores = {
            TrendDirection.UP: 0.0,
            TrendDirection.DOWN: 0.0,
            TrendDirection.SIDEWAYS: 0.0,
        }
        
        for tf, trend in trends.items():
            weight = self.timeframe_weights.get(tf, 1.0)
            direction_scores[trend.direction] += weight
        
        # Return direction with highest score
        primary = max(direction_scores.items(), key=lambda x: x[1])
        return primary[0]
    
    def _calculate_confluence_score(
        self,
        agreeing: List[Timeframe],
        disagreeing: List[Timeframe],
        trends: Dict[Timeframe, TimeframeTrend],
        direction: TrendDirection
    ) -> float:
        """
        Calculate confluence score (0-100).
        
        Factors:
        - Percentage of agreeing timeframes (40%)
        - Weighted agreement (higher TF weight more) (30%)
        - Average trend strength (30%)
        """
        total = len(agreeing) + len(disagreeing)
        
        if total == 0:
            return 0.0
        
        # Agreement percentage
        agreement_pct = len(agreeing) / total
        agreement_score = agreement_pct * 40
        
        # Weighted agreement
        agreeing_weight = sum(
            self.timeframe_weights.get(tf, 1.0) for tf in agreeing
        )
        total_weight = sum(
            self.timeframe_weights.get(tf, 1.0) 
            for tf in agreeing + disagreeing
        )
        
        weighted_agreement = (agreeing_weight / total_weight) if total_weight > 0 else 0
        weighted_score = weighted_agreement * 30
        
        # Average strength
        if agreeing:
            avg_strength = sum(
                trends[tf].strength_score for tf in agreeing
            ) / len(agreeing)
            strength_score = (avg_strength / 100) * 30
        else:
            strength_score = 0.0
        
        return agreement_score + weighted_score + strength_score
    
    def _classify_confluence_level(
        self,
        agreeing_count: int,
        total_count: int
    ) -> ConfluenceLevel:
        """Classify confluence into levels"""
        if total_count == 0:
            return ConfluenceLevel.NONE
        
        ratio = agreeing_count / total_count
        
        if ratio == 1.0:
            return ConfluenceLevel.VERY_STRONG
        elif ratio >= 0.8:
            return ConfluenceLevel.STRONG
        elif ratio >= 0.6:
            return ConfluenceLevel.MODERATE
        elif ratio >= 0.4:
            return ConfluenceLevel.WEAK
        else:
            return ConfluenceLevel.NONE
    
    def _calculate_weight_score(
        self,
        agreeing: List[Timeframe],
        trends: Dict[Timeframe, TimeframeTrend]
    ) -> float:
        """Calculate weighted score (0-100) based on timeframe importance"""
        if not agreeing:
            return 0.0
        
        # Sum of weighted strengths
        weighted_sum = sum(
            self.timeframe_weights.get(tf, 1.0) * trends[tf].strength_score
            for tf in agreeing
        )
        
        # Normalize by maximum possible weight
        max_weight = sum(self.timeframe_weights.get(tf, 1.0) for tf in agreeing)
        
        return (weighted_sum / (max_weight * 100)) * 100 if max_weight > 0 else 0.0
    
    def _calculate_confidence(
        self,
        confluence_score: float,
        avg_strength: float,
        weight_score: float
    ) -> float:
        """Calculate overall confidence (0-1)"""
        # Combine metrics
        confidence = (
            confluence_score * 0.5 +
            avg_strength * 0.3 +
            weight_score * 0.2
        ) / 100
        
        return max(min(confidence, 1.0), 0.0)
    
    def _create_empty_signal(
        self,
        symbol: str,
        timeframes: List[Timeframe]
    ) -> ConfluenceSignal:
        """Create empty signal when no data available"""
        return ConfluenceSignal(
            symbol=symbol,
            timestamp=datetime.utcnow(),
            direction=TrendDirection.UNKNOWN,
            confluence_level=ConfluenceLevel.NONE,
            confluence_score=0.0,
            agreeing_timeframes=[],
            disagreeing_timeframes=timeframes,
            avg_trend_strength=0.0,
            weight_score=0.0,
            is_entry_signal=False,
            is_exit_signal=False,
            confidence=0.0,
            trends={},
        )
