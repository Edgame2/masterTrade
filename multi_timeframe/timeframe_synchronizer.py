"""
Timeframe Synchronizer

Synchronizes and aligns data across multiple timeframes.
Handles different bar sizes and ensures consistent timestamps.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class Timeframe(Enum):
    """Standard timeframes"""
    M1 = "1m"      # 1 minute
    M5 = "5m"      # 5 minutes
    M15 = "15m"    # 15 minutes
    M30 = "30m"    # 30 minutes
    H1 = "1h"      # 1 hour
    H4 = "4h"      # 4 hours
    D1 = "1d"      # 1 day
    W1 = "1w"      # 1 week
    
    @property
    def minutes(self) -> int:
        """Convert timeframe to minutes"""
        mapping = {
            "1m": 1,
            "5m": 5,
            "15m": 15,
            "30m": 30,
            "1h": 60,
            "4h": 240,
            "1d": 1440,
            "1w": 10080,
        }
        return mapping[self.value]
    
    @property
    def seconds(self) -> int:
        """Convert timeframe to seconds"""
        return self.minutes * 60
    
    def is_higher_than(self, other: 'Timeframe') -> bool:
        """Check if this timeframe is higher than another"""
        return self.minutes > other.minutes
    
    def is_lower_than(self, other: 'Timeframe') -> bool:
        """Check if this timeframe is lower than another"""
        return self.minutes < other.minutes


@dataclass
class TimeframeBar:
    """OHLCV bar for a specific timeframe"""
    symbol: str
    timeframe: Timeframe
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    
    @property
    def body_size(self) -> float:
        """Size of candle body"""
        return abs(self.close - self.open)
    
    @property
    def range(self) -> float:
        """Full range (high - low)"""
        return self.high - self.low
    
    @property
    def is_bullish(self) -> bool:
        """Check if bar is bullish"""
        return self.close > self.open
    
    @property
    def is_bearish(self) -> bool:
        """Check if bar is bearish"""
        return self.close < self.open
    
    @property
    def upper_wick(self) -> float:
        """Upper wick size"""
        return self.high - max(self.open, self.close)
    
    @property
    def lower_wick(self) -> float:
        """Lower wick size"""
        return min(self.open, self.close) - self.low


class TimeframeSynchronizer:
    """
    Synchronizes data across multiple timeframes.
    
    Key features:
    - Timestamp alignment
    - Higher timeframe aggregation from lower
    - Missing bar detection
    - Data consistency validation
    """
    
    def __init__(self):
        # Storage: {symbol: {timeframe: [bars]}}
        self.bars: Dict[str, Dict[Timeframe, List[TimeframeBar]]] = {}
        self.max_bars_per_timeframe = 1000  # Memory limit
    
    def add_bar(self, bar: TimeframeBar):
        """Add a bar to the synchronized storage"""
        symbol = bar.symbol
        timeframe = bar.timeframe
        
        # Initialize storage
        if symbol not in self.bars:
            self.bars[symbol] = {}
        if timeframe not in self.bars[symbol]:
            self.bars[symbol][timeframe] = []
        
        # Add bar (maintain chronological order)
        bars = self.bars[symbol][timeframe]
        
        # Check if bar already exists (update) or insert
        existing_idx = None
        for i, existing_bar in enumerate(bars):
            if existing_bar.timestamp == bar.timestamp:
                existing_idx = i
                break
        
        if existing_idx is not None:
            # Update existing bar
            bars[existing_idx] = bar
        else:
            # Insert new bar in chronological order
            bars.append(bar)
            bars.sort(key=lambda b: b.timestamp)
        
        # Limit memory usage
        if len(bars) > self.max_bars_per_timeframe:
            self.bars[symbol][timeframe] = bars[-self.max_bars_per_timeframe:]
    
    def get_bars(
        self,
        symbol: str,
        timeframe: Timeframe,
        count: Optional[int] = None
    ) -> List[TimeframeBar]:
        """Get bars for a symbol and timeframe"""
        if symbol not in self.bars or timeframe not in self.bars[symbol]:
            return []
        
        bars = self.bars[symbol][timeframe]
        if count is None:
            return bars
        return bars[-count:]
    
    def get_latest_bar(
        self,
        symbol: str,
        timeframe: Timeframe
    ) -> Optional[TimeframeBar]:
        """Get the most recent bar"""
        bars = self.get_bars(symbol, timeframe, count=1)
        return bars[0] if bars else None
    
    def aggregate_to_higher_timeframe(
        self,
        symbol: str,
        from_timeframe: Timeframe,
        to_timeframe: Timeframe,
        count: int = 100
    ) -> List[TimeframeBar]:
        """
        Aggregate lower timeframe bars to higher timeframe.
        
        Example: Aggregate 5m bars to 1h bars (12 bars = 1 hour)
        """
        if not to_timeframe.is_higher_than(from_timeframe):
            raise ValueError(
                f"Target timeframe {to_timeframe.value} must be higher "
                f"than source {from_timeframe.value}"
            )
        
        # Get source bars
        source_bars = self.get_bars(symbol, from_timeframe)
        if not source_bars:
            return []
        
        # Calculate how many source bars make one target bar
        ratio = to_timeframe.minutes // from_timeframe.minutes
        
        # Group bars by target timeframe periods
        aggregated = []
        current_group = []
        current_period_start = None
        
        for bar in source_bars:
            # Align to target timeframe period
            period_start = self._align_timestamp(bar.timestamp, to_timeframe)
            
            if current_period_start is None:
                current_period_start = period_start
            
            if period_start == current_period_start:
                current_group.append(bar)
            else:
                # Complete previous period
                if current_group:
                    agg_bar = self._aggregate_bars(
                        symbol, to_timeframe, current_period_start, current_group
                    )
                    aggregated.append(agg_bar)
                
                # Start new period
                current_group = [bar]
                current_period_start = period_start
        
        # Complete last period
        if current_group:
            agg_bar = self._aggregate_bars(
                symbol, to_timeframe, current_period_start, current_group
            )
            aggregated.append(agg_bar)
        
        return aggregated[-count:] if count else aggregated
    
    def _align_timestamp(self, timestamp: datetime, timeframe: Timeframe) -> datetime:
        """Align timestamp to timeframe period start"""
        if timeframe == Timeframe.M1:
            return timestamp.replace(second=0, microsecond=0)
        elif timeframe == Timeframe.M5:
            minute = (timestamp.minute // 5) * 5
            return timestamp.replace(minute=minute, second=0, microsecond=0)
        elif timeframe == Timeframe.M15:
            minute = (timestamp.minute // 15) * 15
            return timestamp.replace(minute=minute, second=0, microsecond=0)
        elif timeframe == Timeframe.M30:
            minute = (timestamp.minute // 30) * 30
            return timestamp.replace(minute=minute, second=0, microsecond=0)
        elif timeframe == Timeframe.H1:
            return timestamp.replace(minute=0, second=0, microsecond=0)
        elif timeframe == Timeframe.H4:
            hour = (timestamp.hour // 4) * 4
            return timestamp.replace(hour=hour, minute=0, second=0, microsecond=0)
        elif timeframe == Timeframe.D1:
            return timestamp.replace(hour=0, minute=0, second=0, microsecond=0)
        elif timeframe == Timeframe.W1:
            # Align to Monday
            days_since_monday = timestamp.weekday()
            start_of_week = timestamp - timedelta(days=days_since_monday)
            return start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
        
        return timestamp
    
    def _aggregate_bars(
        self,
        symbol: str,
        timeframe: Timeframe,
        period_start: datetime,
        bars: List[TimeframeBar]
    ) -> TimeframeBar:
        """Aggregate multiple bars into one"""
        if not bars:
            raise ValueError("Cannot aggregate empty bar list")
        
        return TimeframeBar(
            symbol=symbol,
            timeframe=timeframe,
            timestamp=period_start,
            open=bars[0].open,
            high=max(bar.high for bar in bars),
            low=min(bar.low for bar in bars),
            close=bars[-1].close,
            volume=sum(bar.volume for bar in bars),
        )
    
    def get_synchronized_bars(
        self,
        symbol: str,
        timeframes: List[Timeframe],
        reference_time: Optional[datetime] = None
    ) -> Dict[Timeframe, TimeframeBar]:
        """
        Get synchronized bars across timeframes at a specific time.
        
        Returns the most recent complete bar for each timeframe
        that aligns with or precedes the reference time.
        """
        if reference_time is None:
            reference_time = datetime.utcnow()
        
        result = {}
        
        for timeframe in timeframes:
            bars = self.get_bars(symbol, timeframe)
            if not bars:
                continue
            
            # Find most recent bar before reference time
            for bar in reversed(bars):
                if bar.timestamp <= reference_time:
                    result[timeframe] = bar
                    break
        
        return result
    
    def detect_missing_bars(
        self,
        symbol: str,
        timeframe: Timeframe,
        lookback_periods: int = 100
    ) -> List[datetime]:
        """Detect missing bars in the sequence"""
        bars = self.get_bars(symbol, timeframe, count=lookback_periods)
        if len(bars) < 2:
            return []
        
        missing = []
        expected_interval = timedelta(minutes=timeframe.minutes)
        
        for i in range(1, len(bars)):
            prev_bar = bars[i - 1]
            current_bar = bars[i]
            
            expected_time = prev_bar.timestamp + expected_interval
            
            # Check if there's a gap
            while expected_time < current_bar.timestamp:
                missing.append(expected_time)
                expected_time += expected_interval
        
        return missing
    
    def get_timeframe_alignment_quality(
        self,
        symbol: str,
        timeframes: List[Timeframe]
    ) -> Dict[str, float]:
        """
        Calculate alignment quality across timeframes.
        
        Returns:
            - completeness: % of expected bars present
            - synchronization: How well timeframes align
            - quality_score: Overall quality (0-100)
        """
        if not timeframes:
            return {"completeness": 0.0, "synchronization": 0.0, "quality_score": 0.0}
        
        # Check completeness for each timeframe
        completeness_scores = []
        
        for timeframe in timeframes:
            bars = self.get_bars(symbol, timeframe, count=100)
            if not bars:
                completeness_scores.append(0.0)
                continue
            
            missing = self.detect_missing_bars(symbol, timeframe, lookback_periods=100)
            expected_count = len(bars) + len(missing)
            
            if expected_count > 0:
                completeness = len(bars) / expected_count
                completeness_scores.append(completeness)
            else:
                completeness_scores.append(0.0)
        
        avg_completeness = sum(completeness_scores) / len(completeness_scores)
        
        # Check synchronization (all timeframes have data at similar times)
        sync_bars = self.get_synchronized_bars(symbol, timeframes)
        synchronization = len(sync_bars) / len(timeframes) if timeframes else 0.0
        
        # Overall quality score
        quality_score = (avg_completeness * 0.6 + synchronization * 0.4) * 100
        
        return {
            "completeness": avg_completeness,
            "synchronization": synchronization,
            "quality_score": quality_score,
        }
