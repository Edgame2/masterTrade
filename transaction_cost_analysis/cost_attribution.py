"""
Cost Attribution Analysis

Analyzes and attributes transaction costs to various sources:
- Market impact vs timing effects
- Venue-specific cost analysis
- Strategy effectiveness attribution
- Cost driver identification
- Historical cost pattern analysis
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple
import logging
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class CostDriver(Enum):
    """Transaction cost drivers"""
    MARKET_IMPACT = "market_impact"
    BID_ASK_SPREAD = "bid_ask_spread"
    TIMING_RISK = "timing_risk"
    VENUE_FEES = "venue_fees"
    COMMISSION = "commission"
    OPPORTUNITY_COST = "opportunity_cost"
    VOLATILITY = "volatility"
    LIQUIDITY = "liquidity"
    ORDER_SIZE = "order_size"
    EXECUTION_SPEED = "execution_speed"


@dataclass
class AttributionBreakdown:
    """Cost attribution breakdown for a single driver"""
    driver: CostDriver
    cost_bps: float              # Cost in basis points
    percentage_of_total: float   # Percentage of total cost
    controllable: bool           # Whether trader can control this
    description: str
    
    # Supporting data
    confidence_level: float      # Confidence in attribution (0-1)
    data_quality: str           # "high", "medium", "low"
    
    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "driver": self.driver.value,
            "cost_bps": self.cost_bps,
            "percentage_of_total": self.percentage_of_total,
            "controllable": self.controllable,
            "description": self.description,
            "confidence_level": self.confidence_level,
            "data_quality": self.data_quality,
        }


@dataclass
class AttributionResult:
    """Complete cost attribution result"""
    # Order details
    symbol: str
    order_id: str
    execution_period: str
    total_cost_bps: float
    
    # Attribution breakdown
    cost_drivers: List[AttributionBreakdown]
    
    # Summary metrics
    controllable_cost_pct: float    # % of cost that's controllable
    market_driven_cost_pct: float   # % driven by market conditions
    execution_driven_cost_pct: float # % driven by execution decisions
    
    # Insights
    primary_cost_driver: CostDriver
    improvement_opportunities: List[str]
    cost_efficiency_score: float    # 0-100 score
    
    # Comparative analysis
    peer_comparison: Optional[Dict] = None
    historical_comparison: Optional[Dict] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "symbol": self.symbol,
            "order_id": self.order_id,
            "execution_period": self.execution_period,
            "total_cost_bps": self.total_cost_bps,
            "cost_drivers": [driver.to_dict() for driver in self.cost_drivers],
            "controllable_cost_pct": self.controllable_cost_pct,
            "market_driven_cost_pct": self.market_driven_cost_pct,
            "execution_driven_cost_pct": self.execution_driven_cost_pct,
            "primary_cost_driver": self.primary_cost_driver.value,
            "improvement_opportunities": self.improvement_opportunities,
            "cost_efficiency_score": self.cost_efficiency_score,
            "peer_comparison": self.peer_comparison,
            "historical_comparison": self.historical_comparison,
        }


class CostAnalyzer:
    """
    Advanced cost analyzer using multiple attribution methods.
    
    Decomposes transaction costs using:
    1. Market microstructure analysis
    2. Statistical decomposition
    3. Regime-based analysis
    4. Cross-sectional comparison
    """
    
    def __init__(self):
        self.historical_data = {}
        self.calibration_parameters = {}
    
    def analyze_execution_costs(
        self,
        order_id: str,
        symbol: str,
        executions: List[Dict],
        market_data: pd.DataFrame,
        arrival_price: float,
        venue_data: Optional[Dict] = None,
        strategy_context: Optional[Dict] = None
    ) -> AttributionResult:
        """
        Perform comprehensive cost attribution analysis.
        
        Args:
            order_id: Unique order identifier
            symbol: Asset symbol
            executions: List of execution fills
            market_data: Market data during execution
            arrival_price: Decision/arrival price
            venue_data: Venue-specific data and fees
            strategy_context: Execution strategy context
            
        Returns:
            Complete cost attribution analysis
        """
        if not executions:
            raise ValueError("No executions provided for analysis")
        
        # Sort executions by timestamp
        executions = sorted(executions, key=lambda x: x["timestamp"])
        
        # Calculate total execution metrics
        total_quantity = sum(ex["quantity"] for ex in executions)
        volume_weighted_price = sum(
            ex["price"] * ex["quantity"] for ex in executions
        ) / total_quantity if total_quantity > 0 else arrival_price
        
        # Total cost vs arrival price
        side = strategy_context.get("side", "buy") if strategy_context else "buy"
        if side.lower() == "buy":
            total_cost_pct = (volume_weighted_price - arrival_price) / arrival_price
        else:  # sell
            total_cost_pct = (arrival_price - volume_weighted_price) / arrival_price
        
        total_cost_bps = total_cost_pct * 10000
        
        # Execution period
        start_time = executions[0]["timestamp"]
        end_time = executions[-1]["timestamp"]
        execution_period = f"{start_time} to {end_time}"
        
        # Perform cost attribution
        cost_drivers = self._attribute_cost_drivers(
            executions, market_data, arrival_price, total_cost_bps,
            venue_data, strategy_context
        )
        
        # Calculate summary metrics
        summary_metrics = self._calculate_summary_metrics(cost_drivers)
        
        # Identify primary cost driver
        primary_driver = max(cost_drivers, key=lambda x: abs(x.cost_bps)).driver
        
        # Generate improvement opportunities
        improvement_opportunities = self._generate_improvement_opportunities(cost_drivers)
        
        # Calculate efficiency score
        efficiency_score = self._calculate_efficiency_score(cost_drivers, total_cost_bps)
        
        # Comparative analysis
        peer_comparison = self._perform_peer_comparison(symbol, total_cost_bps, cost_drivers)
        historical_comparison = self._perform_historical_comparison(symbol, total_cost_bps)
        
        return AttributionResult(
            symbol=symbol,
            order_id=order_id,
            execution_period=execution_period,
            total_cost_bps=total_cost_bps,
            cost_drivers=cost_drivers,
            controllable_cost_pct=summary_metrics["controllable_pct"],
            market_driven_cost_pct=summary_metrics["market_driven_pct"],
            execution_driven_cost_pct=summary_metrics["execution_driven_pct"],
            primary_cost_driver=primary_driver,
            improvement_opportunities=improvement_opportunities,
            cost_efficiency_score=efficiency_score,
            peer_comparison=peer_comparison,
            historical_comparison=historical_comparison,
        )
    
    def _attribute_cost_drivers(
        self,
        executions: List[Dict],
        market_data: pd.DataFrame,
        arrival_price: float,
        total_cost_bps: float,
        venue_data: Optional[Dict],
        strategy_context: Optional[Dict]
    ) -> List[AttributionBreakdown]:
        """Attribute costs to specific drivers"""
        drivers = []
        
        # Market Impact Attribution
        market_impact_bps = self._calculate_market_impact_attribution(
            executions, market_data, arrival_price
        )
        
        drivers.append(AttributionBreakdown(
            driver=CostDriver.MARKET_IMPACT,
            cost_bps=market_impact_bps,
            percentage_of_total=(market_impact_bps / total_cost_bps * 100) if total_cost_bps != 0 else 0,
            controllable=True,
            description=f"Price impact from trading activity: {market_impact_bps:.1f} bps",
            confidence_level=0.8,
            data_quality="high"
        ))
        
        # Bid-Ask Spread Attribution
        spread_cost_bps = self._calculate_spread_cost_attribution(
            executions, market_data
        )
        
        drivers.append(AttributionBreakdown(
            driver=CostDriver.BID_ASK_SPREAD,
            cost_bps=spread_cost_bps,
            percentage_of_total=(spread_cost_bps / total_cost_bps * 100) if total_cost_bps != 0 else 0,
            controllable=False,
            description=f"Bid-ask spread cost: {spread_cost_bps:.1f} bps",
            confidence_level=0.9,
            data_quality="high"
        ))
        
        # Timing Risk Attribution
        timing_risk_bps = self._calculate_timing_risk_attribution(
            executions, market_data, arrival_price
        )
        
        drivers.append(AttributionBreakdown(
            driver=CostDriver.TIMING_RISK,
            cost_bps=timing_risk_bps,
            percentage_of_total=(timing_risk_bps / total_cost_bps * 100) if total_cost_bps != 0 else 0,
            controllable=True,
            description=f"Market movement during execution: {timing_risk_bps:.1f} bps",
            confidence_level=0.7,
            data_quality="medium"
        ))
        
        # Venue Fees Attribution
        venue_fees_bps = self._calculate_venue_fees_attribution(
            executions, venue_data
        )
        
        drivers.append(AttributionBreakdown(
            driver=CostDriver.VENUE_FEES,
            cost_bps=venue_fees_bps,
            percentage_of_total=(venue_fees_bps / total_cost_bps * 100) if total_cost_bps != 0 else 0,
            controllable=True,
            description=f"Exchange and venue fees: {venue_fees_bps:.1f} bps",
            confidence_level=1.0,
            data_quality="high"
        ))
        
        # Commission Attribution
        commission_bps = self._calculate_commission_attribution(
            executions, strategy_context
        )
        
        drivers.append(AttributionBreakdown(
            driver=CostDriver.COMMISSION,
            cost_bps=commission_bps,
            percentage_of_total=(commission_bps / total_cost_bps * 100) if total_cost_bps != 0 else 0,
            controllable=True,
            description=f"Brokerage commission: {commission_bps:.1f} bps",
            confidence_level=1.0,
            data_quality="high"
        ))
        
        # Volatility Impact Attribution
        volatility_impact_bps = self._calculate_volatility_impact_attribution(
            executions, market_data
        )
        
        drivers.append(AttributionBreakdown(
            driver=CostDriver.VOLATILITY,
            cost_bps=volatility_impact_bps,
            percentage_of_total=(volatility_impact_bps / total_cost_bps * 100) if total_cost_bps != 0 else 0,
            controllable=False,
            description=f"Volatility-driven cost: {volatility_impact_bps:.1f} bps",
            confidence_level=0.6,
            data_quality="medium"
        ))
        
        # Order Size Attribution
        size_impact_bps = self._calculate_size_impact_attribution(
            executions, market_data
        )
        
        drivers.append(AttributionBreakdown(
            driver=CostDriver.ORDER_SIZE,
            cost_bps=size_impact_bps,
            percentage_of_total=(size_impact_bps / total_cost_bps * 100) if total_cost_bps != 0 else 0,
            controllable=True,
            description=f"Order size impact: {size_impact_bps:.1f} bps",
            confidence_level=0.7,
            data_quality="medium"
        ))
        
        return drivers
    
    def _calculate_market_impact_attribution(
        self,
        executions: List[Dict],
        market_data: pd.DataFrame,
        arrival_price: float
    ) -> float:
        """Calculate market impact component"""
        # Simplified market impact calculation
        # In practice, would use sophisticated models
        
        total_quantity = sum(ex["quantity"] for ex in executions)
        
        # Estimate average daily volume from market data
        if not market_data.empty and "volume" in market_data.columns:
            avg_daily_volume = market_data["volume"].mean() * 78  # Assume 78 5-min intervals per day
        else:
            avg_daily_volume = 1000000  # Default
        
        # Participation rate
        participation_rate = total_quantity / avg_daily_volume
        
        # Square-root market impact model (simplified)
        market_impact_bps = 25 * np.sqrt(participation_rate)  # 25 bps coefficient
        
        return market_impact_bps
    
    def _calculate_spread_cost_attribution(
        self,
        executions: List[Dict],
        market_data: pd.DataFrame
    ) -> float:
        """Calculate bid-ask spread cost component"""
        # Estimate average spread during execution
        if not market_data.empty and "bid" in market_data.columns and "ask" in market_data.columns:
            # Calculate spread from bid-ask data
            spreads = []
            for _, row in market_data.iterrows():
                if pd.notna(row["bid"]) and pd.notna(row["ask"]) and row["ask"] > row["bid"]:
                    mid_price = (row["bid"] + row["ask"]) / 2
                    spread_bps = (row["ask"] - row["bid"]) / mid_price * 10000
                    spreads.append(spread_bps)
            
            if spreads:
                avg_spread_bps = np.mean(spreads)
                # Half-spread cost for market orders
                spread_cost_bps = avg_spread_bps / 2
            else:
                spread_cost_bps = 5.0  # Default 5 bps
        else:
            # Estimate based on price volatility
            if not market_data.empty:
                returns = market_data["close"].pct_change().dropna()
                if len(returns) > 1:
                    volatility = returns.std()
                    # Rough heuristic: spread ≈ 2 * volatility
                    spread_cost_bps = min(volatility * 20000, 20.0)  # Cap at 20 bps
                else:
                    spread_cost_bps = 5.0
            else:
                spread_cost_bps = 5.0
        
        return spread_cost_bps
    
    def _calculate_timing_risk_attribution(
        self,
        executions: List[Dict],
        market_data: pd.DataFrame,
        arrival_price: float
    ) -> float:
        """Calculate timing risk component"""
        if market_data.empty:
            return 0.0
        
        # Get market price movement during execution
        start_time = pd.to_datetime(executions[0]["timestamp"])
        end_time = pd.to_datetime(executions[-1]["timestamp"])
        
        # Find closest market prices
        try:
            start_idx = market_data.index.get_indexer([start_time], method="nearest")[0]
            end_idx = market_data.index.get_indexer([end_time], method="nearest")[0]
            
            start_price = market_data.iloc[start_idx]["close"]
            end_price = market_data.iloc[end_idx]["close"]
            
            # Price drift during execution
            price_drift_pct = (end_price - start_price) / start_price
            timing_risk_bps = abs(price_drift_pct) * 10000 * 0.5  # 50% attribution to timing
            
        except (IndexError, KeyError):
            timing_risk_bps = 0.0
        
        return timing_risk_bps
    
    def _calculate_venue_fees_attribution(
        self,
        executions: List[Dict],
        venue_data: Optional[Dict]
    ) -> float:
        """Calculate venue fees component"""
        if not venue_data:
            return 2.0  # Default 2 bps
        
        # Sum up venue-specific fees
        total_fees = 0.0
        total_value = 0.0
        
        for execution in executions:
            venue = execution.get("venue", "unknown")
            quantity = execution["quantity"]
            price = execution["price"]
            value = quantity * price
            total_value += value
            
            # Get venue fee rate
            venue_fee_rate = venue_data.get(venue, {}).get("fee_rate", 0.0001)  # Default 1 bp
            total_fees += value * venue_fee_rate
        
        venue_fees_bps = (total_fees / total_value * 10000) if total_value > 0 else 0.0
        
        return venue_fees_bps
    
    def _calculate_commission_attribution(
        self,
        executions: List[Dict],
        strategy_context: Optional[Dict]
    ) -> float:
        """Calculate commission component"""
        if strategy_context and "commission_rate" in strategy_context:
            commission_rate = strategy_context["commission_rate"]
        else:
            commission_rate = 0.001  # Default 0.1%
        
        commission_bps = commission_rate * 10000
        
        return commission_bps
    
    def _calculate_volatility_impact_attribution(
        self,
        executions: List[Dict],
        market_data: pd.DataFrame
    ) -> float:
        """Calculate volatility-driven cost component"""
        if market_data.empty:
            return 0.0
        
        # Calculate volatility during execution period
        returns = market_data["close"].pct_change().dropna()
        
        if len(returns) < 2:
            return 0.0
        
        volatility = returns.std()
        execution_duration_hours = len(returns) / 12  # Assuming 5-minute data
        
        # Volatility cost scales with sqrt(time) and volatility
        volatility_cost_bps = volatility * np.sqrt(execution_duration_hours) * 5000  # 50x multiplier
        
        return min(volatility_cost_bps, 15.0)  # Cap at 15 bps
    
    def _calculate_size_impact_attribution(
        self,
        executions: List[Dict],
        market_data: pd.DataFrame
    ) -> float:
        """Calculate order size impact component"""
        total_quantity = sum(ex["quantity"] for ex in executions)
        
        # Estimate typical order size for this stock
        if not market_data.empty and "volume" in market_data.columns:
            avg_interval_volume = market_data["volume"].mean()
            # Typical order might be 1% of interval volume
            typical_order_size = avg_interval_volume * 0.01
        else:
            typical_order_size = 1000  # Default
        
        # Size impact based on ratio to typical size
        size_ratio = total_quantity / max(typical_order_size, 1)
        
        if size_ratio > 5:  # Large order
            size_impact_bps = (size_ratio - 1) * 2  # 2 bps per unit of excess size
        else:
            size_impact_bps = 0.0
        
        return min(size_impact_bps, 20.0)  # Cap at 20 bps
    
    def _calculate_summary_metrics(self, cost_drivers: List[AttributionBreakdown]) -> Dict:
        """Calculate summary attribution metrics"""
        total_cost = sum(abs(driver.cost_bps) for driver in cost_drivers)
        
        controllable_cost = sum(
            abs(driver.cost_bps) for driver in cost_drivers if driver.controllable
        )
        
        market_driven_drivers = [
            CostDriver.BID_ASK_SPREAD, CostDriver.VOLATILITY, CostDriver.TIMING_RISK
        ]
        market_driven_cost = sum(
            abs(driver.cost_bps) for driver in cost_drivers 
            if driver.driver in market_driven_drivers
        )
        
        execution_driven_drivers = [
            CostDriver.MARKET_IMPACT, CostDriver.ORDER_SIZE, CostDriver.EXECUTION_SPEED
        ]
        execution_driven_cost = sum(
            abs(driver.cost_bps) for driver in cost_drivers 
            if driver.driver in execution_driven_drivers
        )
        
        return {
            "controllable_pct": (controllable_cost / total_cost * 100) if total_cost > 0 else 0,
            "market_driven_pct": (market_driven_cost / total_cost * 100) if total_cost > 0 else 0,
            "execution_driven_pct": (execution_driven_cost / total_cost * 100) if total_cost > 0 else 0,
        }
    
    def _generate_improvement_opportunities(
        self, 
        cost_drivers: List[AttributionBreakdown]
    ) -> List[str]:
        """Generate improvement recommendations based on cost drivers"""
        opportunities = []
        
        # Sort drivers by cost magnitude
        sorted_drivers = sorted(cost_drivers, key=lambda x: abs(x.cost_bps), reverse=True)
        
        for driver in sorted_drivers[:3]:  # Top 3 cost drivers
            if driver.controllable and abs(driver.cost_bps) > 5:  # > 5 bps and controllable
                
                if driver.driver == CostDriver.MARKET_IMPACT:
                    opportunities.append("Reduce market impact by using smaller order sizes or longer execution periods")
                
                elif driver.driver == CostDriver.VENUE_FEES:
                    opportunities.append("Optimize venue selection to reduce trading fees")
                
                elif driver.driver == CostDriver.ORDER_SIZE:
                    opportunities.append("Break large orders into smaller chunks to reduce size impact")
                
                elif driver.driver == CostDriver.COMMISSION:
                    opportunities.append("Negotiate lower commission rates with brokers")
                
                elif driver.driver == CostDriver.TIMING_RISK:
                    opportunities.append("Improve execution timing to reduce adverse price movements")
        
        if not opportunities:
            opportunities.append("Execution costs are well-controlled; minor optimizations possible")
        
        return opportunities
    
    def _calculate_efficiency_score(
        self,
        cost_drivers: List[AttributionBreakdown],
        total_cost_bps: float
    ) -> float:
        """Calculate cost efficiency score (0-100)"""
        base_score = 100
        
        # Penalize high total cost
        cost_penalty = min(abs(total_cost_bps) * 1.5, 60)
        
        # Bonus for low controllable costs
        controllable_drivers = [d for d in cost_drivers if d.controllable]
        controllable_cost = sum(abs(d.cost_bps) for d in controllable_drivers)
        
        if controllable_cost < 10:  # < 10 bps controllable cost
            controllable_bonus = 10
        else:
            controllable_bonus = max(0, 10 - controllable_cost * 0.5)
        
        # Penalty for poor execution choices (high market impact)
        market_impact_drivers = [d for d in cost_drivers if d.driver == CostDriver.MARKET_IMPACT]
        if market_impact_drivers:
            market_impact_cost = abs(market_impact_drivers[0].cost_bps)
            if market_impact_cost > 20:  # > 20 bps market impact
                execution_penalty = (market_impact_cost - 20) * 2
            else:
                execution_penalty = 0
        else:
            execution_penalty = 0
        
        efficiency_score = base_score - cost_penalty + controllable_bonus - execution_penalty
        
        return max(0, min(100, efficiency_score))
    
    def _perform_peer_comparison(
        self,
        symbol: str,
        total_cost_bps: float,
        cost_drivers: List[AttributionBreakdown]
    ) -> Dict:
        """Compare against peer executions"""
        # Simplified peer comparison
        # In practice, would use historical database
        
        # Simulate peer statistics
        peer_median_cost = 15.0  # 15 bps median
        peer_75th_percentile = 25.0  # 25 bps 75th percentile
        
        percentile_rank = 50  # Default median
        if total_cost_bps < peer_median_cost:
            percentile_rank = max(0, 50 - (peer_median_cost - total_cost_bps) * 2)
        else:
            percentile_rank = min(100, 50 + (total_cost_bps - peer_median_cost) * 2)
        
        return {
            "peer_median_cost_bps": peer_median_cost,
            "peer_75th_percentile_bps": peer_75th_percentile,
            "percentile_rank": percentile_rank,
            "performance_vs_peers": "above_median" if total_cost_bps < peer_median_cost else "below_median",
        }
    
    def _perform_historical_comparison(self, symbol: str, total_cost_bps: float) -> Dict:
        """Compare against historical performance"""
        # Simplified historical comparison
        
        historical_avg = 20.0  # 20 bps historical average
        historical_std = 8.0   # 8 bps standard deviation
        
        z_score = (total_cost_bps - historical_avg) / historical_std
        
        if z_score < -1:
            performance = "significantly_better"
        elif z_score < 0:
            performance = "better"
        elif z_score < 1:
            performance = "worse"
        else:
            performance = "significantly_worse"
        
        return {
            "historical_avg_cost_bps": historical_avg,
            "historical_std_bps": historical_std,
            "z_score": z_score,
            "performance_vs_history": performance,
        }


class CostAttribution:
    """
    Main cost attribution interface.
    
    Provides high-level interface for cost attribution analysis.
    """
    
    def __init__(self):
        self.analyzer = CostAnalyzer()
    
    def attribute_execution_costs(
        self,
        order_data: Dict,
        market_data: pd.DataFrame,
        **kwargs
    ) -> AttributionResult:
        """
        Main entry point for cost attribution.
        
        Args:
            order_data: Order execution data
            market_data: Market data during execution
            **kwargs: Additional context data
            
        Returns:
            Attribution result
        """
        return self.analyzer.analyze_execution_costs(
            order_id=order_data["order_id"],
            symbol=order_data["symbol"],
            executions=order_data["executions"],
            market_data=market_data,
            arrival_price=order_data["arrival_price"],
            venue_data=kwargs.get("venue_data"),
            strategy_context=kwargs.get("strategy_context")
        )
    
    def batch_attribution_analysis(
        self,
        orders_data: List[Dict],
        market_data_dict: Dict[str, pd.DataFrame]
    ) -> List[AttributionResult]:
        """
        Perform batch cost attribution analysis.
        
        Args:
            orders_data: List of order data dictionaries
            market_data_dict: Dictionary mapping symbols to market data
            
        Returns:
            List of attribution results
        """
        results = []
        
        for order in orders_data:
            try:
                symbol = order["symbol"]
                market_data = market_data_dict.get(symbol, pd.DataFrame())
                
                result = self.attribute_execution_costs(order, market_data)
                results.append(result)
                
            except Exception as e:
                logger.error(f"Error in cost attribution for order {order.get('order_id', 'unknown')}: {str(e)}")
                continue
        
        return results
    
    def generate_attribution_summary(
        self,
        attribution_results: List[AttributionResult],
        period: str = "Daily"
    ) -> Dict:
        """
        Generate summary report from multiple attribution results.
        
        Args:
            attribution_results: List of attribution results
            period: Reporting period
            
        Returns:
            Summary statistics
        """
        if not attribution_results:
            return {"error": "No attribution results provided"}
        
        # Aggregate metrics
        total_costs = [result.total_cost_bps for result in attribution_results]
        efficiency_scores = [result.cost_efficiency_score for result in attribution_results]
        
        # Cost driver aggregation
        driver_totals = defaultdict(list)
        for result in attribution_results:
            for driver in result.cost_drivers:
                driver_totals[driver.driver].append(abs(driver.cost_bps))
        
        # Summary statistics
        summary = {
            "period": period,
            "total_orders": len(attribution_results),
            "cost_metrics": {
                "avg_cost_bps": np.mean(total_costs),
                "median_cost_bps": np.median(total_costs),
                "std_cost_bps": np.std(total_costs),
                "min_cost_bps": np.min(total_costs),
                "max_cost_bps": np.max(total_costs),
            },
            "efficiency_metrics": {
                "avg_efficiency_score": np.mean(efficiency_scores),
                "pct_efficient_executions": sum(1 for score in efficiency_scores if score >= 75) / len(efficiency_scores) * 100,
            },
            "cost_driver_analysis": {
                driver.value: {
                    "avg_cost_bps": np.mean(costs),
                    "frequency_pct": len(costs) / len(attribution_results) * 100,
                    "total_impact_bps": np.sum(costs),
                }
                for driver, costs in driver_totals.items()
            },
            "improvement_opportunities": self._aggregate_improvement_opportunities(attribution_results),
        }
        
        return summary
    
    def _aggregate_improvement_opportunities(
        self, 
        attribution_results: List[AttributionResult]
    ) -> Dict:
        """Aggregate improvement opportunities across results"""
        opportunity_counts = defaultdict(int)
        
        for result in attribution_results:
            for opportunity in result.improvement_opportunities:
                opportunity_counts[opportunity] += 1
        
        # Sort by frequency
        sorted_opportunities = sorted(
            opportunity_counts.items(), 
            key=lambda x: x[1], 
            reverse=True
        )
        
        return {
            "most_common_opportunities": sorted_opportunities[:5],
            "total_unique_opportunities": len(opportunity_counts),
        }