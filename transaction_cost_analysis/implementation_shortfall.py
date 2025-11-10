"""
Implementation Shortfall Analysis

Implements implementation shortfall methodology for execution quality analysis:
- Total implementation shortfall decomposition
- Market impact vs timing risk analysis
- Benchmark comparison (TWAP, VWAP, arrival price)
- Execution efficiency measurement
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple
import logging
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class ExecutionBenchmark(Enum):
    """Execution benchmark types"""
    ARRIVAL_PRICE = "arrival_price"        # Decision price
    TWAP = "twap"                         # Time-weighted average price
    VWAP = "vwap"                         # Volume-weighted average price
    OPEN = "open"                         # Opening price
    CLOSE = "close"                       # Closing price
    MID_POINT = "mid_point"               # Mid-point of bid-ask
    IMPLEMENTATION_SHORTFALL = "implementation_shortfall"


@dataclass
class ShortfallComponent:
    """Individual component of implementation shortfall"""
    component_name: str
    value: float                    # In basis points
    percentage: float              # Percentage of total shortfall
    description: str
    is_controllable: bool          # Whether trader can control this component


@dataclass
class ShortfallAnalysis:
    """Complete implementation shortfall analysis"""
    # Order details
    symbol: str
    order_id: str
    side: str                      # "buy" or "sell"
    total_quantity: float
    benchmark_price: float
    execution_period: str          # e.g., "2023-01-15 09:30 to 10:15"
    
    # Shortfall components (in basis points)
    market_impact: ShortfallComponent
    timing_risk: ShortfallComponent  
    opportunity_cost: ShortfallComponent
    total_shortfall: float
    
    # Execution details
    fills: List[Dict]              # Individual fill details
    participation_rate: float      # Average participation rate
    execution_time: float          # Total execution time in minutes
    
    # Performance metrics
    efficiency_score: float        # 0-100 execution efficiency
    benchmark_comparison: Dict[str, float]  # vs different benchmarks
    
    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "symbol": self.symbol,
            "order_id": self.order_id,
            "side": self.side,
            "total_quantity": self.total_quantity,
            "benchmark_price": self.benchmark_price,
            "execution_period": self.execution_period,
            "market_impact": self.market_impact.__dict__,
            "timing_risk": self.timing_risk.__dict__,
            "opportunity_cost": self.opportunity_cost.__dict__,
            "total_shortfall": self.total_shortfall,
            "fills": self.fills,
            "participation_rate": self.participation_rate,
            "execution_time": self.execution_time,
            "efficiency_score": self.efficiency_score,
            "benchmark_comparison": self.benchmark_comparison,
        }


class ImplementationShortfall:
    """
    Implementation Shortfall analyzer.
    
    Decomposes the difference between execution price and benchmark into:
    1. Market Impact: Price movement caused by the trade
    2. Timing Risk: Price movement during execution period
    3. Opportunity Cost: Cost of not trading (if applicable)
    
    Based on Perold (1988) and Almgren-Chriss (2000) frameworks.
    """
    
    def __init__(self):
        self.analysis_cache = {}
    
    def analyze_execution(
        self,
        order_id: str,
        symbol: str,
        side: str,
        target_quantity: float,
        benchmark_price: float,
        executions: List[Dict],
        market_data: pd.DataFrame,
        benchmark_type: ExecutionBenchmark = ExecutionBenchmark.ARRIVAL_PRICE
    ) -> ShortfallAnalysis:
        """
        Perform complete implementation shortfall analysis.
        
        Args:
            order_id: Unique order identifier
            symbol: Asset symbol
            side: "buy" or "sell"
            target_quantity: Original order quantity
            benchmark_price: Benchmark price (arrival, TWAP, etc.)
            executions: List of execution fills
            market_data: Market data during execution period
            benchmark_type: Type of benchmark to use
            
        Returns:
            Complete shortfall analysis
        """
        # Validate inputs
        if not executions:
            raise ValueError("No executions provided")
        
        # Sort executions by timestamp
        executions = sorted(executions, key=lambda x: x["timestamp"])
        
        # Calculate execution metrics
        total_executed = sum(fill["quantity"] for fill in executions)
        volume_weighted_price = sum(
            fill["price"] * fill["quantity"] for fill in executions
        ) / total_executed if total_executed > 0 else benchmark_price
        
        # Calculate shortfall components
        market_impact_comp = self._calculate_market_impact(
            executions, market_data, benchmark_price, side
        )
        
        timing_risk_comp = self._calculate_timing_risk(
            executions, market_data, benchmark_price, side
        )
        
        opportunity_cost_comp = self._calculate_opportunity_cost(
            target_quantity, total_executed, benchmark_price, market_data, side
        )
        
        # Total shortfall
        total_shortfall = (
            market_impact_comp.value + 
            timing_risk_comp.value + 
            opportunity_cost_comp.value
        )
        
        # Execution period
        start_time = executions[0]["timestamp"]
        end_time = executions[-1]["timestamp"]
        execution_period = f"{start_time} to {end_time}"
        
        # Calculate execution time in minutes
        if isinstance(start_time, str):
            start_dt = pd.to_datetime(start_time)
            end_dt = pd.to_datetime(end_time)
        else:
            start_dt = start_time
            end_dt = end_time
        
        execution_time = (end_dt - start_dt).total_seconds() / 60
        
        # Calculate participation rate
        execution_volume = sum(fill["quantity"] for fill in executions)
        
        # Get market volume during execution period
        exec_start = start_dt.strftime("%H:%M:%S")
        exec_end = end_dt.strftime("%H:%M:%S")
        
        market_volume_during_exec = 0
        if not market_data.empty:
            execution_mask = (
                (market_data.index >= start_dt) & 
                (market_data.index <= end_dt)
            )
            market_volume_during_exec = market_data.loc[execution_mask, "volume"].sum()
        
        participation_rate = (
            execution_volume / market_volume_during_exec 
            if market_volume_during_exec > 0 else 0
        )
        
        # Calculate efficiency score (0-100)
        efficiency_score = self._calculate_efficiency_score(
            total_shortfall, market_impact_comp.value, timing_risk_comp.value
        )
        
        # Benchmark comparisons
        benchmark_comparison = self._compare_benchmarks(
            executions, market_data, volume_weighted_price
        )
        
        return ShortfallAnalysis(
            symbol=symbol,
            order_id=order_id,
            side=side,
            total_quantity=target_quantity,
            benchmark_price=benchmark_price,
            execution_period=execution_period,
            market_impact=market_impact_comp,
            timing_risk=timing_risk_comp,
            opportunity_cost=opportunity_cost_comp,
            total_shortfall=total_shortfall,
            fills=executions,
            participation_rate=participation_rate,
            execution_time=execution_time,
            efficiency_score=efficiency_score,
            benchmark_comparison=benchmark_comparison,
        )
    
    def _calculate_market_impact(
        self,
        executions: List[Dict],
        market_data: pd.DataFrame,
        benchmark_price: float,
        side: str
    ) -> ShortfallComponent:
        """
        Calculate market impact component.
        
        Market impact = immediate price movement caused by trades
        """
        total_impact = 0
        total_quantity = 0
        
        for fill in executions:
            quantity = fill["quantity"]
            fill_price = fill["price"]
            
            # Calculate impact for this fill
            if side.lower() == "buy":
                fill_impact = (fill_price - benchmark_price) / benchmark_price
            else:  # sell
                fill_impact = (benchmark_price - fill_price) / benchmark_price
            
            # Weight by quantity
            total_impact += fill_impact * quantity
            total_quantity += quantity
        
        # Average impact in basis points
        avg_impact_bps = (total_impact / total_quantity * 10000) if total_quantity > 0 else 0
        
        return ShortfallComponent(
            component_name="market_impact",
            value=avg_impact_bps,
            percentage=0,  # Will be calculated later
            description=f"Price impact from trading {total_quantity:,.0f} shares",
            is_controllable=True
        )
    
    def _calculate_timing_risk(
        self,
        executions: List[Dict],
        market_data: pd.DataFrame,
        benchmark_price: float,
        side: str
    ) -> ShortfallComponent:
        """
        Calculate timing risk component.
        
        Timing risk = price movement during execution period unrelated to our trades
        """
        if market_data.empty or len(executions) == 0:
            return ShortfallComponent(
                component_name="timing_risk",
                value=0,
                percentage=0,
                description="No market data available for timing risk calculation",
                is_controllable=False
            )
        
        # Get price movement during execution period
        start_time = pd.to_datetime(executions[0]["timestamp"])
        end_time = pd.to_datetime(executions[-1]["timestamp"])
        
        # Find closest market data points
        market_subset = market_data[
            (market_data.index >= start_time - timedelta(minutes=5)) &
            (market_data.index <= end_time + timedelta(minutes=5))
        ]
        
        if market_subset.empty:
            return ShortfallComponent(
                component_name="timing_risk",
                value=0,
                percentage=0,
                description="Insufficient market data for timing risk",
                is_controllable=False
            )
        
        # Calculate price drift
        start_price = market_subset["close"].iloc[0] if len(market_subset) > 0 else benchmark_price
        end_price = market_subset["close"].iloc[-1] if len(market_subset) > 0 else benchmark_price
        
        if side.lower() == "buy":
            price_drift = (end_price - start_price) / start_price
        else:  # sell
            price_drift = (start_price - end_price) / start_price
        
        timing_risk_bps = price_drift * 10000
        
        return ShortfallComponent(
            component_name="timing_risk", 
            value=timing_risk_bps,
            percentage=0,
            description=f"Market movement during execution: {price_drift:.2%}",
            is_controllable=False
        )
    
    def _calculate_opportunity_cost(
        self,
        target_quantity: float,
        executed_quantity: float,
        benchmark_price: float,
        market_data: pd.DataFrame,
        side: str
    ) -> ShortfallComponent:
        """
        Calculate opportunity cost of unexecuted quantity.
        """
        unexecuted_quantity = target_quantity - executed_quantity
        
        if unexecuted_quantity <= 0:
            return ShortfallComponent(
                component_name="opportunity_cost",
                value=0,
                percentage=0,
                description="Order fully executed - no opportunity cost",
                is_controllable=True
            )
        
        # Estimate cost of not trading the remaining quantity
        # This is the price movement on unexecuted shares
        
        if market_data.empty:
            opportunity_cost_bps = 0
        else:
            # Use end-of-period price vs benchmark
            end_price = market_data["close"].iloc[-1] if len(market_data) > 0 else benchmark_price
            
            if side.lower() == "buy":
                price_move = (end_price - benchmark_price) / benchmark_price
            else:  # sell
                price_move = (benchmark_price - end_price) / benchmark_price
            
            # Weight by unexecuted quantity
            quantity_weight = unexecuted_quantity / target_quantity
            opportunity_cost_bps = price_move * quantity_weight * 10000
        
        return ShortfallComponent(
            component_name="opportunity_cost",
            value=opportunity_cost_bps,
            percentage=0,
            description=f"Cost of {unexecuted_quantity:,.0f} unexecuted shares",
            is_controllable=True
        )
    
    def _calculate_efficiency_score(
        self,
        total_shortfall: float,
        market_impact: float,
        timing_risk: float
    ) -> float:
        """
        Calculate execution efficiency score (0-100).
        
        Higher score = better execution
        Based on controllable vs uncontrollable costs
        """
        # Base score starts at 100
        base_score = 100
        
        # Penalize for market impact (controllable)
        impact_penalty = min(abs(market_impact) * 2, 50)  # Max 50 point penalty
        
        # Small penalty for total shortfall magnitude
        shortfall_penalty = min(abs(total_shortfall) * 0.5, 30)  # Max 30 point penalty
        
        # Bonus for low timing risk (shows good timing)
        timing_bonus = max(0, 20 - abs(timing_risk))  # Up to 20 point bonus
        
        efficiency_score = base_score - impact_penalty - shortfall_penalty + timing_bonus
        
        return max(0, min(100, efficiency_score))
    
    def _compare_benchmarks(
        self,
        executions: List[Dict],
        market_data: pd.DataFrame,
        execution_price: float
    ) -> Dict[str, float]:
        """Compare execution against various benchmarks"""
        benchmarks = {}
        
        if market_data.empty:
            return benchmarks
        
        # Get execution period data
        start_time = pd.to_datetime(executions[0]["timestamp"])
        end_time = pd.to_datetime(executions[-1]["timestamp"])
        
        period_data = market_data[
            (market_data.index >= start_time) & 
            (market_data.index <= end_time)
        ]
        
        if period_data.empty:
            return benchmarks
        
        # TWAP (Time-Weighted Average Price)
        twap = period_data["close"].mean()
        benchmarks["twap"] = (execution_price - twap) / twap * 10000
        
        # VWAP (Volume-Weighted Average Price)
        if "volume" in period_data.columns:
            vwap = (period_data["close"] * period_data["volume"]).sum() / period_data["volume"].sum()
            benchmarks["vwap"] = (execution_price - vwap) / vwap * 10000
        
        # Opening price
        if len(period_data) > 0:
            open_price = period_data["open"].iloc[0] if "open" in period_data.columns else period_data["close"].iloc[0]
            benchmarks["open"] = (execution_price - open_price) / open_price * 10000
        
        # Closing price
        if len(period_data) > 0:
            close_price = period_data["close"].iloc[-1]
            benchmarks["close"] = (execution_price - close_price) / close_price * 10000
        
        return benchmarks
    
    def batch_analyze(
        self,
        orders_data: List[Dict],
        market_data_dict: Dict[str, pd.DataFrame]
    ) -> List[ShortfallAnalysis]:
        """
        Analyze multiple orders in batch.
        
        Args:
            orders_data: List of order dictionaries
            market_data_dict: Dict mapping symbols to market data
            
        Returns:
            List of shortfall analyses
        """
        results = []
        
        for order in orders_data:
            try:
                symbol = order["symbol"]
                market_data = market_data_dict.get(symbol, pd.DataFrame())
                
                analysis = self.analyze_execution(
                    order_id=order["order_id"],
                    symbol=symbol,
                    side=order["side"],
                    target_quantity=order["target_quantity"],
                    benchmark_price=order["benchmark_price"],
                    executions=order["executions"],
                    market_data=market_data,
                    benchmark_type=order.get("benchmark_type", ExecutionBenchmark.ARRIVAL_PRICE)
                )
                
                results.append(analysis)
                
            except Exception as e:
                logger.error(f"Error analyzing order {order.get('order_id', 'unknown')}: {str(e)}")
                continue
        
        return results
    
    def generate_summary_report(
        self,
        analyses: List[ShortfallAnalysis],
        period: str = "Daily"
    ) -> Dict:
        """
        Generate summary report from multiple shortfall analyses.
        
        Args:
            analyses: List of shortfall analyses
            period: Reporting period (e.g., "Daily", "Weekly")
            
        Returns:
            Summary statistics dictionary
        """
        if not analyses:
            return {"error": "No analyses provided"}
        
        # Aggregate metrics
        total_shortfalls = [analysis.total_shortfall for analysis in analyses]
        market_impacts = [analysis.market_impact.value for analysis in analyses]
        timing_risks = [analysis.timing_risk.value for analysis in analyses]
        efficiency_scores = [analysis.efficiency_score for analysis in analyses]
        
        # Summary statistics
        summary = {
            "period": period,
            "total_orders": len(analyses),
            "metrics": {
                "avg_shortfall_bps": np.mean(total_shortfalls),
                "median_shortfall_bps": np.median(total_shortfalls),
                "std_shortfall_bps": np.std(total_shortfalls),
                "avg_market_impact_bps": np.mean(market_impacts),
                "avg_timing_risk_bps": np.mean(timing_risks),
                "avg_efficiency_score": np.mean(efficiency_scores),
            },
            "performance_distribution": {
                "excellent_execution_pct": sum(1 for score in efficiency_scores if score >= 80) / len(efficiency_scores) * 100,
                "good_execution_pct": sum(1 for score in efficiency_scores if 60 <= score < 80) / len(efficiency_scores) * 100,
                "poor_execution_pct": sum(1 for score in efficiency_scores if score < 60) / len(efficiency_scores) * 100,
            },
            "cost_breakdown": {
                "avg_market_impact_pct": np.mean([abs(mi) / (abs(ts) + 1e-8) for mi, ts in zip(market_impacts, total_shortfalls)]) * 100,
                "avg_timing_risk_pct": np.mean([abs(tr) / (abs(ts) + 1e-8) for tr, ts in zip(timing_risks, total_shortfalls)]) * 100,
            }
        }
        
        # Best and worst executions
        if efficiency_scores:
            best_idx = np.argmax(efficiency_scores)
            worst_idx = np.argmin(efficiency_scores)
            
            summary["best_execution"] = {
                "order_id": analyses[best_idx].order_id,
                "symbol": analyses[best_idx].symbol,
                "efficiency_score": analyses[best_idx].efficiency_score,
                "total_shortfall": analyses[best_idx].total_shortfall,
            }
            
            summary["worst_execution"] = {
                "order_id": analyses[worst_idx].order_id,
                "symbol": analyses[worst_idx].symbol,
                "efficiency_score": analyses[worst_idx].efficiency_score,
                "total_shortfall": analyses[worst_idx].total_shortfall,
            }
        
        return summary