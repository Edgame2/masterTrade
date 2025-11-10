"""
Benchmark Analysis

Comprehensive TWAP, VWAP, and other execution benchmark analysis:
- TWAP (Time-Weighted Average Price) calculation and analysis
- VWAP (Volume-Weighted Average Price) calculation and analysis
- Participation rate analysis
- Execution quality metrics vs benchmarks
- Market timing analysis
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple
import logging
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class BenchmarkType(Enum):
    """Types of execution benchmarks"""
    TWAP = "twap"                    # Time-Weighted Average Price
    VWAP = "vwap"                    # Volume-Weighted Average Price
    ARRIVAL_PRICE = "arrival_price"   # Decision/arrival price
    OPEN = "open"                    # Opening price
    CLOSE = "close"                  # Closing price
    HIGH = "high"                    # High of day
    LOW = "low"                      # Low of day
    MID_POINT = "mid_point"          # Bid-ask midpoint


@dataclass
class ParticipationRate:
    """Participation rate statistics"""
    average_rate: float              # Average participation rate
    peak_rate: float                 # Maximum participation rate
    participation_profile: List[float]  # Rate over time
    total_market_volume: float       # Total market volume during period
    executed_volume: float           # Volume executed
    market_share_pct: float         # Percentage of market volume


@dataclass
class BenchmarkResult:
    """Execution benchmark analysis result"""
    # Basic info
    symbol: str
    execution_period: str
    benchmark_type: BenchmarkType
    
    # Prices
    benchmark_price: float
    execution_price: float           # Volume-weighted execution price
    
    # Performance vs benchmark
    performance_bps: float           # Execution vs benchmark in bps
    slippage: float                 # Slippage from benchmark
    
    # Market context
    market_volatility: float         # Market volatility during period
    market_trend: str               # "up", "down", "sideways"
    liquidity_conditions: str       # "high", "normal", "low"
    
    # Execution quality
    participation_rate: ParticipationRate
    execution_efficiency: float      # 0-100 score
    timing_quality: float           # Market timing score
    
    # Detailed analysis
    price_evolution: List[Dict]      # Price evolution during execution
    benchmark_evolution: List[Dict]  # Benchmark evolution
    
    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "symbol": self.symbol,
            "execution_period": self.execution_period,
            "benchmark_type": self.benchmark_type.value,
            "benchmark_price": self.benchmark_price,
            "execution_price": self.execution_price,
            "performance_bps": self.performance_bps,
            "slippage": self.slippage,
            "market_volatility": self.market_volatility,
            "market_trend": self.market_trend,
            "liquidity_conditions": self.liquidity_conditions,
            "participation_rate": self.participation_rate.__dict__,
            "execution_efficiency": self.execution_efficiency,
            "timing_quality": self.timing_quality,
            "price_evolution": self.price_evolution,
            "benchmark_evolution": self.benchmark_evolution,
        }


class TWAPAnalyzer:
    """
    Time-Weighted Average Price (TWAP) analyzer.
    
    TWAP is the average price of a security over a specified time period,
    with equal weight given to each time interval.
    """
    
    def __init__(self):
        self.cache = {}
    
    def calculate_twap(
        self,
        market_data: pd.DataFrame,
        start_time: datetime,
        end_time: datetime,
        price_column: str = "close"
    ) -> float:
        """
        Calculate TWAP for specified period.
        
        Args:
            market_data: Market data with timestamps
            start_time: Period start
            end_time: Period end
            price_column: Price column to use
            
        Returns:
            TWAP value
        """
        # Filter data for the period
        period_data = market_data[
            (market_data.index >= start_time) & 
            (market_data.index <= end_time)
        ]
        
        if period_data.empty:
            logger.warning(f"No market data available for TWAP calculation between {start_time} and {end_time}")
            return 0.0
        
        # Simple TWAP - equal weight to each observation
        twap = period_data[price_column].mean()
        
        return twap
    
    def calculate_dynamic_twap(
        self,
        market_data: pd.DataFrame,
        execution_times: List[datetime],
        price_column: str = "close"
    ) -> List[float]:
        """
        Calculate TWAP dynamically as execution progresses.
        
        Args:
            market_data: Market data
            execution_times: List of execution timestamps
            price_column: Price column to use
            
        Returns:
            List of TWAP values at each execution time
        """
        twap_values = []
        start_time = execution_times[0]
        
        for exec_time in execution_times:
            twap = self.calculate_twap(market_data, start_time, exec_time, price_column)
            twap_values.append(twap)
        
        return twap_values
    
    def analyze_vs_twap(
        self,
        executions: List[Dict],
        market_data: pd.DataFrame,
        target_duration_minutes: int = 60
    ) -> BenchmarkResult:
        """
        Analyze execution performance vs TWAP benchmark.
        
        Args:
            executions: List of execution fills
            market_data: Market data during execution
            target_duration_minutes: Target execution duration for TWAP
            
        Returns:
            Benchmark analysis result
        """
        if not executions:
            raise ValueError("No executions provided")
        
        # Sort executions by timestamp
        executions = sorted(executions, key=lambda x: x["timestamp"])
        
        # Execution period
        start_time = pd.to_datetime(executions[0]["timestamp"])
        end_time = pd.to_datetime(executions[-1]["timestamp"])
        
        # Calculate volume-weighted execution price
        total_quantity = sum(fill["quantity"] for fill in executions)
        execution_price = sum(
            fill["price"] * fill["quantity"] for fill in executions
        ) / total_quantity
        
        # Calculate TWAP for the execution period
        twap_price = self.calculate_twap(market_data, start_time, end_time)
        
        # Performance vs TWAP in basis points
        performance_bps = (execution_price - twap_price) / twap_price * 10000
        slippage = abs(performance_bps)
        
        # Market context analysis
        market_context = self._analyze_market_context(market_data, start_time, end_time)
        
        # Participation rate analysis
        participation_rate = self._calculate_participation_rate(
            executions, market_data, start_time, end_time
        )
        
        # Execution efficiency score
        execution_efficiency = self._calculate_twap_efficiency(
            performance_bps, market_context["volatility"], participation_rate.average_rate
        )
        
        # Timing quality analysis
        timing_quality = self._analyze_timing_quality(
            executions, market_data, twap_price
        )
        
        # Price evolution
        price_evolution = self._get_price_evolution(market_data, start_time, end_time)
        benchmark_evolution = self._get_benchmark_evolution(
            market_data, start_time, end_time, BenchmarkType.TWAP
        )
        
        return BenchmarkResult(
            symbol=executions[0].get("symbol", "UNKNOWN"),
            execution_period=f"{start_time} to {end_time}",
            benchmark_type=BenchmarkType.TWAP,
            benchmark_price=twap_price,
            execution_price=execution_price,
            performance_bps=performance_bps,
            slippage=slippage,
            market_volatility=market_context["volatility"],
            market_trend=market_context["trend"],
            liquidity_conditions=market_context["liquidity"],
            participation_rate=participation_rate,
            execution_efficiency=execution_efficiency,
            timing_quality=timing_quality,
            price_evolution=price_evolution,
            benchmark_evolution=benchmark_evolution,
        )
    
    def _analyze_market_context(
        self,
        market_data: pd.DataFrame,
        start_time: datetime,
        end_time: datetime
    ) -> Dict:
        """Analyze market conditions during execution"""
        period_data = market_data[
            (market_data.index >= start_time) & 
            (market_data.index <= end_time)
        ]
        
        if period_data.empty:
            return {
                "volatility": 0.0,
                "trend": "unknown",
                "liquidity": "unknown"
            }
        
        # Volatility (rolling std of returns)
        if len(period_data) > 1:
            returns = period_data["close"].pct_change().dropna()
            volatility = returns.std() * np.sqrt(252 * 390)  # Annualized intraday vol
        else:
            volatility = 0.0
        
        # Trend analysis
        start_price = period_data["close"].iloc[0]
        end_price = period_data["close"].iloc[-1]
        price_change = (end_price - start_price) / start_price
        
        if price_change > 0.001:  # > 0.1%
            trend = "up"
        elif price_change < -0.001:  # < -0.1%
            trend = "down"
        else:
            trend = "sideways"
        
        # Liquidity assessment (based on volume)
        if "volume" in period_data.columns:
            avg_volume = period_data["volume"].mean()
            # Simple heuristic: high volume = good liquidity
            if avg_volume > period_data["volume"].quantile(0.8):
                liquidity = "high"
            elif avg_volume < period_data["volume"].quantile(0.2):
                liquidity = "low"
            else:
                liquidity = "normal"
        else:
            liquidity = "unknown"
        
        return {
            "volatility": volatility,
            "trend": trend,
            "liquidity": liquidity
        }
    
    def _calculate_participation_rate(
        self,
        executions: List[Dict],
        market_data: pd.DataFrame,
        start_time: datetime,
        end_time: datetime
    ) -> ParticipationRate:
        """Calculate participation rate statistics"""
        # Total executed volume
        executed_volume = sum(fill["quantity"] for fill in executions)
        
        # Market volume during execution period
        period_data = market_data[
            (market_data.index >= start_time) & 
            (market_data.index <= end_time)
        ]
        
        if period_data.empty or "volume" not in period_data.columns:
            return ParticipationRate(
                average_rate=0.0,
                peak_rate=0.0,
                participation_profile=[],
                total_market_volume=0.0,
                executed_volume=executed_volume,
                market_share_pct=0.0
            )
        
        total_market_volume = period_data["volume"].sum()
        
        # Average participation rate
        average_rate = executed_volume / total_market_volume if total_market_volume > 0 else 0.0
        
        # Calculate participation profile (simplified)
        # In practice, would need tick-by-tick data
        participation_profile = []
        peak_rate = 0.0
        
        if len(period_data) > 1:
            # Approximate participation by time intervals
            for i, (timestamp, row) in enumerate(period_data.iterrows()):
                interval_volume = row["volume"]
                # Find executions in this interval
                interval_executions = [
                    ex for ex in executions 
                    if abs((pd.to_datetime(ex["timestamp"]) - timestamp).total_seconds()) < 60
                ]
                interval_executed = sum(ex["quantity"] for ex in interval_executions)
                
                if interval_volume > 0:
                    rate = interval_executed / interval_volume
                    participation_profile.append(rate)
                    peak_rate = max(peak_rate, rate)
                else:
                    participation_profile.append(0.0)
        
        market_share_pct = average_rate * 100
        
        return ParticipationRate(
            average_rate=average_rate,
            peak_rate=peak_rate,
            participation_profile=participation_profile,
            total_market_volume=total_market_volume,
            executed_volume=executed_volume,
            market_share_pct=market_share_pct
        )
    
    def _calculate_twap_efficiency(
        self,
        performance_bps: float,
        volatility: float,
        participation_rate: float
    ) -> float:
        """Calculate TWAP execution efficiency score (0-100)"""
        base_score = 100
        
        # Penalty for deviation from TWAP
        deviation_penalty = min(abs(performance_bps) * 2, 50)
        
        # Adjustment for market conditions
        volatility_adjustment = min(volatility * 100, 20)  # More lenient in volatile markets
        
        # Participation rate factor (very high participation can be costly)
        participation_penalty = 0
        if participation_rate > 0.2:  # > 20% participation
            participation_penalty = (participation_rate - 0.2) * 100
        
        efficiency = base_score - deviation_penalty + volatility_adjustment - participation_penalty
        
        return max(0, min(100, efficiency))
    
    def _analyze_timing_quality(
        self,
        executions: List[Dict],
        market_data: pd.DataFrame,
        benchmark_price: float
    ) -> float:
        """Analyze quality of execution timing (0-100 score)"""
        if market_data.empty:
            return 50.0  # Neutral score
        
        # Calculate price trend during execution
        start_time = pd.to_datetime(executions[0]["timestamp"])
        end_time = pd.to_datetime(executions[-1]["timestamp"])
        
        period_data = market_data[
            (market_data.index >= start_time) & 
            (market_data.index <= end_time)
        ]
        
        if len(period_data) < 2:
            return 50.0
        
        # Analyze if execution was well-timed relative to price movement
        start_price = period_data["close"].iloc[0]
        end_price = period_data["close"].iloc[-1]
        price_trend = (end_price - start_price) / start_price
        
        # Get average execution price
        avg_exec_price = sum(ex["price"] * ex["quantity"] for ex in executions) / sum(ex["quantity"] for ex in executions)
        
        # Good timing = executing when prices are favorable
        # For buys: good timing if bought before price went up
        # For sells: good timing if sold before price went down
        
        timing_score = 50.0  # Base neutral score
        
        if price_trend > 0.001:  # Price went up
            # If our execution price was below the trend, that's good timing for buys
            relative_price = (avg_exec_price - start_price) / start_price
            if relative_price < price_trend * 0.5:  # Executed in lower half of range
                timing_score += 30
            else:
                timing_score -= 15
        elif price_trend < -0.001:  # Price went down
            # If our execution price was above the trend, that's good timing for sells
            relative_price = (avg_exec_price - start_price) / start_price
            if relative_price > price_trend * 0.5:  # Executed in upper half of range
                timing_score += 30
            else:
                timing_score -= 15
        
        return max(0, min(100, timing_score))
    
    def _get_price_evolution(
        self,
        market_data: pd.DataFrame,
        start_time: datetime,
        end_time: datetime
    ) -> List[Dict]:
        """Get price evolution during execution period"""
        period_data = market_data[
            (market_data.index >= start_time) & 
            (market_data.index <= end_time)
        ]
        
        evolution = []
        for timestamp, row in period_data.iterrows():
            evolution.append({
                "timestamp": timestamp.isoformat(),
                "price": row["close"],
                "volume": row.get("volume", 0),
                "high": row.get("high", row["close"]),
                "low": row.get("low", row["close"])
            })
        
        return evolution
    
    def _get_benchmark_evolution(
        self,
        market_data: pd.DataFrame,
        start_time: datetime,
        end_time: datetime,
        benchmark_type: BenchmarkType
    ) -> List[Dict]:
        """Get benchmark evolution during execution period"""
        period_data = market_data[
            (market_data.index >= start_time) & 
            (market_data.index <= end_time)
        ]
        
        evolution = []
        cumulative_twap_sum = 0
        cumulative_vwap_sum = 0
        cumulative_volume = 0
        
        for i, (timestamp, row) in enumerate(period_data.iterrows(), 1):
            cumulative_twap_sum += row["close"]
            twap = cumulative_twap_sum / i
            
            if "volume" in period_data.columns and row["volume"] > 0:
                cumulative_vwap_sum += row["close"] * row["volume"]
                cumulative_volume += row["volume"]
                vwap = cumulative_vwap_sum / cumulative_volume if cumulative_volume > 0 else row["close"]
            else:
                vwap = twap
            
            benchmark_price = twap if benchmark_type == BenchmarkType.TWAP else vwap
            
            evolution.append({
                "timestamp": timestamp.isoformat(),
                "benchmark_price": benchmark_price,
                "twap": twap,
                "vwap": vwap
            })
        
        return evolution


class VWAPAnalyzer:
    """
    Volume-Weighted Average Price (VWAP) analyzer.
    
    VWAP is the average price weighted by volume, giving more importance
    to prices at which more volume was traded.
    """
    
    def __init__(self):
        self.cache = {}
    
    def calculate_vwap(
        self,
        market_data: pd.DataFrame,
        start_time: datetime,
        end_time: datetime,
        price_column: str = "close",
        volume_column: str = "volume"
    ) -> float:
        """
        Calculate VWAP for specified period.
        
        Args:
            market_data: Market data with timestamps, prices, and volumes
            start_time: Period start
            end_time: Period end  
            price_column: Price column to use
            volume_column: Volume column to use
            
        Returns:
            VWAP value
        """
        # Filter data for the period
        period_data = market_data[
            (market_data.index >= start_time) & 
            (market_data.index <= end_time)
        ]
        
        if period_data.empty or volume_column not in period_data.columns:
            logger.warning(f"No market data or volume data available for VWAP calculation")
            return 0.0
        
        # Calculate VWAP
        total_value = (period_data[price_column] * period_data[volume_column]).sum()
        total_volume = period_data[volume_column].sum()
        
        if total_volume == 0:
            return 0.0
        
        vwap = total_value / total_volume
        
        return vwap
    
    def analyze_vs_vwap(
        self,
        executions: List[Dict],
        market_data: pd.DataFrame
    ) -> BenchmarkResult:
        """
        Analyze execution performance vs VWAP benchmark.
        
        Similar to TWAP analysis but uses volume-weighted benchmark.
        """
        if not executions:
            raise ValueError("No executions provided")
        
        # Sort executions by timestamp
        executions = sorted(executions, key=lambda x: x["timestamp"])
        
        # Execution period
        start_time = pd.to_datetime(executions[0]["timestamp"])
        end_time = pd.to_datetime(executions[-1]["timestamp"])
        
        # Calculate volume-weighted execution price
        total_quantity = sum(fill["quantity"] for fill in executions)
        execution_price = sum(
            fill["price"] * fill["quantity"] for fill in executions
        ) / total_quantity
        
        # Calculate VWAP for the execution period
        vwap_price = self.calculate_vwap(market_data, start_time, end_time)
        
        # Performance vs VWAP in basis points
        performance_bps = (execution_price - vwap_price) / vwap_price * 10000
        slippage = abs(performance_bps)
        
        # Use TWAPAnalyzer methods for common analysis
        twap_analyzer = TWAPAnalyzer()
        
        # Market context analysis
        market_context = twap_analyzer._analyze_market_context(market_data, start_time, end_time)
        
        # Participation rate analysis
        participation_rate = twap_analyzer._calculate_participation_rate(
            executions, market_data, start_time, end_time
        )
        
        # VWAP-specific efficiency calculation
        execution_efficiency = self._calculate_vwap_efficiency(
            performance_bps, market_context["volatility"], participation_rate.average_rate
        )
        
        # Timing quality analysis
        timing_quality = twap_analyzer._analyze_timing_quality(
            executions, market_data, vwap_price
        )
        
        # Price evolution
        price_evolution = twap_analyzer._get_price_evolution(market_data, start_time, end_time)
        benchmark_evolution = twap_analyzer._get_benchmark_evolution(
            market_data, start_time, end_time, BenchmarkType.VWAP
        )
        
        return BenchmarkResult(
            symbol=executions[0].get("symbol", "UNKNOWN"),
            execution_period=f"{start_time} to {end_time}",
            benchmark_type=BenchmarkType.VWAP,
            benchmark_price=vwap_price,
            execution_price=execution_price,
            performance_bps=performance_bps,
            slippage=slippage,
            market_volatility=market_context["volatility"],
            market_trend=market_context["trend"],
            liquidity_conditions=market_context["liquidity"],
            participation_rate=participation_rate,
            execution_efficiency=execution_efficiency,
            timing_quality=timing_quality,
            price_evolution=price_evolution,
            benchmark_evolution=benchmark_evolution,
        )
    
    def _calculate_vwap_efficiency(
        self,
        performance_bps: float,
        volatility: float,
        participation_rate: float
    ) -> float:
        """Calculate VWAP execution efficiency score (0-100)"""
        base_score = 100
        
        # Penalty for deviation from VWAP
        deviation_penalty = min(abs(performance_bps) * 1.5, 40)  # Slightly more lenient than TWAP
        
        # Adjustment for market conditions
        volatility_adjustment = min(volatility * 80, 15)
        
        # VWAP is more forgiving of higher participation rates
        participation_penalty = 0
        if participation_rate > 0.3:  # > 30% participation
            participation_penalty = (participation_rate - 0.3) * 80
        
        efficiency = base_score - deviation_penalty + volatility_adjustment - participation_penalty
        
        return max(0, min(100, efficiency))


def analyze_multiple_benchmarks(
    executions: List[Dict],
    market_data: pd.DataFrame
) -> Dict[str, BenchmarkResult]:
    """
    Analyze execution against multiple benchmarks.
    
    Args:
        executions: List of execution fills
        market_data: Market data during execution period
        
    Returns:
        Dictionary of benchmark results
    """
    results = {}
    
    # TWAP analysis
    try:
        twap_analyzer = TWAPAnalyzer()
        results["twap"] = twap_analyzer.analyze_vs_twap(executions, market_data)
    except Exception as e:
        logger.error(f"TWAP analysis failed: {str(e)}")
    
    # VWAP analysis
    try:
        vwap_analyzer = VWAPAnalyzer()
        results["vwap"] = vwap_analyzer.analyze_vs_vwap(executions, market_data)
    except Exception as e:
        logger.error(f"VWAP analysis failed: {str(e)}")
    
    # Arrival price analysis
    try:
        if executions and market_data is not None:
            start_time = pd.to_datetime(executions[0]["timestamp"])
            
            # Find closest market price to arrival time
            closest_data = market_data.iloc[market_data.index.get_indexer([start_time], method="nearest")]
            if not closest_data.empty:
                arrival_price = closest_data["close"].iloc[0]
                
                # Calculate execution vs arrival price
                total_quantity = sum(fill["quantity"] for fill in executions)
                execution_price = sum(
                    fill["price"] * fill["quantity"] for fill in executions
                ) / total_quantity
                
                performance_bps = (execution_price - arrival_price) / arrival_price * 10000
                
                # Create simplified result for arrival price
                results["arrival_price"] = {
                    "benchmark_type": "arrival_price",
                    "benchmark_price": arrival_price,
                    "execution_price": execution_price,
                    "performance_bps": performance_bps,
                    "slippage": abs(performance_bps)
                }
    
    except Exception as e:
        logger.error(f"Arrival price analysis failed: {str(e)}")
    
    return results