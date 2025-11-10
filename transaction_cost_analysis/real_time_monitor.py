"""
Real-time TCA Monitor

Real-time transaction cost analysis monitoring:
- Live execution monitoring
- Cost threshold alerts
- Performance degradation detection
- Market impact tracking
- Execution quality scoring
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Callable
import logging
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import asyncio
from collections import deque, defaultdict

logger = logging.getLogger(__name__)


class AlertType(Enum):
    """TCA alert types"""
    HIGH_MARKET_IMPACT = "high_market_impact"
    EXCESSIVE_SLIPPAGE = "excessive_slippage"
    POOR_EXECUTION_QUALITY = "poor_execution_quality"
    HIGH_PARTICIPATION_RATE = "high_participation_rate"
    COST_THRESHOLD_EXCEEDED = "cost_threshold_exceeded"
    UNUSUAL_FILL_PATTERN = "unusual_fill_pattern"
    MARKET_CONDITION_CHANGE = "market_condition_change"


@dataclass
class TCAAlert:
    """Transaction cost analysis alert"""
    alert_type: AlertType
    severity: str               # "low", "medium", "high", "critical"
    symbol: str
    order_id: str
    timestamp: datetime
    
    # Alert details
    message: str
    current_value: float
    threshold_value: float
    
    # Context
    market_conditions: Dict
    execution_context: Dict
    
    # Recommendations
    recommendations: List[str]
    
    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "alert_type": self.alert_type.value,
            "severity": self.severity,
            "symbol": self.symbol,
            "order_id": self.order_id,
            "timestamp": self.timestamp.isoformat(),
            "message": self.message,
            "current_value": self.current_value,
            "threshold_value": self.threshold_value,
            "market_conditions": self.market_conditions,
            "execution_context": self.execution_context,
            "recommendations": self.recommendations,
        }


@dataclass
class ExecutionAlert:
    """Real-time execution alert"""
    order_id: str
    symbol: str
    alert_message: str
    recommended_action: str
    urgency: str                # "low", "medium", "high"
    timestamp: datetime


@dataclass
class MonitoringMetrics:
    """Real-time monitoring metrics"""
    # Execution metrics
    current_fill_rate: float           # Fills per minute
    cumulative_quantity: float         # Total filled
    remaining_quantity: float          # Still to fill
    avg_fill_price: float             # Volume-weighted avg price
    
    # Cost metrics
    realized_market_impact: float      # Actual market impact (bps)
    estimated_total_cost: float        # Projected total cost (bps)
    slippage_vs_arrival: float        # Slippage from arrival price (bps)
    
    # Performance metrics
    execution_efficiency: float        # Current efficiency score (0-100)
    benchmark_performance: Dict[str, float]  # vs TWAP, VWAP, etc.
    
    # Market metrics
    current_volatility: float          # Real-time volatility
    participation_rate: float          # Current participation rate
    market_impact_estimate: float      # Estimated ongoing impact
    
    # Timing metrics
    execution_progress: float          # % of time elapsed
    quantity_progress: float           # % of quantity filled
    
    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "current_fill_rate": self.current_fill_rate,
            "cumulative_quantity": self.cumulative_quantity,
            "remaining_quantity": self.remaining_quantity,
            "avg_fill_price": self.avg_fill_price,
            "realized_market_impact": self.realized_market_impact,
            "estimated_total_cost": self.estimated_total_cost,
            "slippage_vs_arrival": self.slippage_vs_arrival,
            "execution_efficiency": self.execution_efficiency,
            "benchmark_performance": self.benchmark_performance,
            "current_volatility": self.current_volatility,
            "participation_rate": self.participation_rate,
            "market_impact_estimate": self.market_impact_estimate,
            "execution_progress": self.execution_progress,
            "quantity_progress": self.quantity_progress,
        }


class RealTimeTCAMonitor:
    """
    Real-time transaction cost analysis monitor.
    
    Monitors live trade executions and provides:
    - Real-time cost analysis
    - Performance alerts
    - Execution recommendations
    - Market condition monitoring
    """
    
    def __init__(
        self,
        alert_thresholds: Optional[Dict] = None,
        monitoring_interval: int = 5,  # seconds
        history_window: int = 300      # seconds
    ):
        # Alert thresholds
        self.alert_thresholds = alert_thresholds or {
            "market_impact_bps": 25.0,
            "slippage_bps": 15.0,
            "participation_rate": 0.25,
            "execution_efficiency": 60.0,
            "cost_threshold_bps": 50.0,
        }
        
        self.monitoring_interval = monitoring_interval
        self.history_window = history_window
        
        # Monitoring state
        self.active_orders: Dict[str, Dict] = {}
        self.alerts_history: deque = deque(maxlen=1000)
        self.metrics_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=100))
        
        # Market data cache
        self.market_data_cache: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        
        # Alert callbacks
        self.alert_callbacks: List[Callable[[TCAAlert], None]] = []
        
        # Monitoring task
        self._monitoring_task: Optional[asyncio.Task] = None
        self._is_monitoring = False
    
    def register_alert_callback(self, callback: Callable[[TCAAlert], None]):
        """Register callback for alerts"""
        self.alert_callbacks.append(callback)
    
    async def start_monitoring(self):
        """Start real-time monitoring"""
        if self._is_monitoring:
            logger.warning("Monitoring already started")
            return
        
        self._is_monitoring = True
        self._monitoring_task = asyncio.create_task(self._monitoring_loop())
        logger.info("Real-time TCA monitoring started")
    
    async def stop_monitoring(self):
        """Stop real-time monitoring"""
        if not self._is_monitoring:
            return
        
        self._is_monitoring = False
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Real-time TCA monitoring stopped")
    
    def add_order_for_monitoring(
        self,
        order_id: str,
        symbol: str,
        side: str,
        target_quantity: float,
        arrival_price: float,
        start_time: datetime,
        expected_end_time: datetime,
        strategy: str = "unknown"
    ):
        """Add order to monitoring"""
        self.active_orders[order_id] = {
            "symbol": symbol,
            "side": side,
            "target_quantity": target_quantity,
            "arrival_price": arrival_price,
            "start_time": start_time,
            "expected_end_time": expected_end_time,
            "strategy": strategy,
            "fills": [],
            "cumulative_quantity": 0.0,
            "cumulative_value": 0.0,
            "last_update": start_time,
        }
        
        logger.info(f"Added order {order_id} for monitoring: {symbol} {side} {target_quantity}")
    
    def update_order_fill(
        self,
        order_id: str,
        fill_price: float,
        fill_quantity: float,
        fill_time: datetime,
        market_price: Optional[float] = None
    ):
        """Update order with new fill"""
        if order_id not in self.active_orders:
            logger.warning(f"Order {order_id} not found in monitoring")
            return
        
        order = self.active_orders[order_id]
        
        # Add fill to history
        fill_data = {
            "price": fill_price,
            "quantity": fill_quantity,
            "timestamp": fill_time,
            "market_price": market_price,
        }
        order["fills"].append(fill_data)
        
        # Update cumulative metrics
        order["cumulative_quantity"] += fill_quantity
        order["cumulative_value"] += fill_price * fill_quantity
        order["last_update"] = fill_time
        
        # Calculate current metrics
        metrics = self._calculate_current_metrics(order_id)
        
        # Store metrics
        self.metrics_history[order_id].append({
            "timestamp": fill_time,
            "metrics": metrics
        })
        
        # Check for alerts
        alerts = self._check_alerts(order_id, metrics)
        
        # Send alerts
        for alert in alerts:
            self._send_alert(alert)
        
        logger.debug(f"Updated order {order_id} with fill: {fill_quantity} @ {fill_price}")
    
    def update_market_data(
        self,
        symbol: str,
        timestamp: datetime,
        price: float,
        volume: float,
        bid: Optional[float] = None,
        ask: Optional[float] = None
    ):
        """Update market data for symbol"""
        market_point = {
            "timestamp": timestamp,
            "price": price,
            "volume": volume,
            "bid": bid,
            "ask": ask,
        }
        
        self.market_data_cache[symbol].append(market_point)
    
    def _calculate_current_metrics(self, order_id: str) -> MonitoringMetrics:
        """Calculate current monitoring metrics for order"""
        order = self.active_orders[order_id]
        fills = order["fills"]
        
        if not fills:
            return MonitoringMetrics(
                current_fill_rate=0.0,
                cumulative_quantity=0.0,
                remaining_quantity=order["target_quantity"],
                avg_fill_price=order["arrival_price"],
                realized_market_impact=0.0,
                estimated_total_cost=0.0,
                slippage_vs_arrival=0.0,
                execution_efficiency=100.0,
                benchmark_performance={},
                current_volatility=0.0,
                participation_rate=0.0,
                market_impact_estimate=0.0,
                execution_progress=0.0,
                quantity_progress=0.0,
            )
        
        # Basic metrics
        cumulative_quantity = order["cumulative_quantity"]
        remaining_quantity = order["target_quantity"] - cumulative_quantity
        
        # Average fill price
        if cumulative_quantity > 0:
            avg_fill_price = order["cumulative_value"] / cumulative_quantity
        else:
            avg_fill_price = order["arrival_price"]
        
        # Fill rate (fills per minute)
        time_elapsed = (order["last_update"] - order["start_time"]).total_seconds() / 60
        current_fill_rate = len(fills) / max(time_elapsed, 1)
        
        # Slippage vs arrival price
        arrival_price = order["arrival_price"]
        if order["side"].lower() == "buy":
            slippage_vs_arrival = (avg_fill_price - arrival_price) / arrival_price * 10000
        else:  # sell
            slippage_vs_arrival = (arrival_price - avg_fill_price) / arrival_price * 10000
        
        # Market impact (simplified)
        realized_market_impact = abs(slippage_vs_arrival) * 0.6  # Assume 60% is market impact
        
        # Estimated total cost
        spread_cost = 5.0  # Assume 5 bps spread cost
        commission_cost = 1.0  # Assume 1 bp commission
        estimated_total_cost = realized_market_impact + spread_cost + commission_cost
        
        # Execution progress
        expected_duration = (order["expected_end_time"] - order["start_time"]).total_seconds()
        elapsed_duration = (order["last_update"] - order["start_time"]).total_seconds()
        execution_progress = min(elapsed_duration / max(expected_duration, 1), 1.0) * 100
        
        quantity_progress = cumulative_quantity / order["target_quantity"] * 100
        
        # Execution efficiency (simplified scoring)
        efficiency_score = 100 - min(abs(slippage_vs_arrival) * 2, 50)  # Penalize slippage
        if quantity_progress < execution_progress * 0.8:  # Behind schedule
            efficiency_score -= 20
        
        # Market volatility (from recent market data)
        symbol = order["symbol"]
        current_volatility = self._estimate_current_volatility(symbol)
        
        # Participation rate (simplified)
        participation_rate = 0.1  # Default estimate
        
        # Benchmark performance (simplified)
        benchmark_performance = {
            "arrival_price": slippage_vs_arrival,
            "twap": slippage_vs_arrival * 0.8,  # Assume TWAP is slightly better
            "vwap": slippage_vs_arrival * 0.9,  # Assume VWAP is closer
        }
        
        return MonitoringMetrics(
            current_fill_rate=current_fill_rate,
            cumulative_quantity=cumulative_quantity,
            remaining_quantity=remaining_quantity,
            avg_fill_price=avg_fill_price,
            realized_market_impact=realized_market_impact,
            estimated_total_cost=estimated_total_cost,
            slippage_vs_arrival=slippage_vs_arrival,
            execution_efficiency=efficiency_score,
            benchmark_performance=benchmark_performance,
            current_volatility=current_volatility,
            participation_rate=participation_rate,
            market_impact_estimate=realized_market_impact,
            execution_progress=execution_progress,
            quantity_progress=quantity_progress,
        )
    
    def _estimate_current_volatility(self, symbol: str) -> float:
        """Estimate current volatility from recent market data"""
        market_data = list(self.market_data_cache[symbol])
        
        if len(market_data) < 10:
            return 0.2  # Default volatility
        
        # Use last 50 data points
        recent_data = market_data[-50:]
        prices = [point["price"] for point in recent_data]
        
        # Calculate returns
        returns = []
        for i in range(1, len(prices)):
            ret = (prices[i] - prices[i-1]) / prices[i-1]
            returns.append(ret)
        
        if not returns:
            return 0.2
        
        # Annualized volatility (assuming 5-minute intervals)
        vol = np.std(returns) * np.sqrt(252 * 78)  # 78 5-minute intervals per day
        
        return vol
    
    def _check_alerts(self, order_id: str, metrics: MonitoringMetrics) -> List[TCAAlert]:
        """Check for alert conditions"""
        alerts = []
        order = self.active_orders[order_id]
        
        # High market impact alert
        if metrics.realized_market_impact > self.alert_thresholds["market_impact_bps"]:
            alerts.append(TCAAlert(
                alert_type=AlertType.HIGH_MARKET_IMPACT,
                severity="high" if metrics.realized_market_impact > 40 else "medium",
                symbol=order["symbol"],
                order_id=order_id,
                timestamp=datetime.utcnow(),
                message=f"High market impact detected: {metrics.realized_market_impact:.1f} bps",
                current_value=metrics.realized_market_impact,
                threshold_value=self.alert_thresholds["market_impact_bps"],
                market_conditions={"volatility": metrics.current_volatility},
                execution_context={"strategy": order["strategy"], "progress": metrics.quantity_progress},
                recommendations=[
                    "Consider reducing order size",
                    "Slow down execution pace",
                    "Check market conditions"
                ]
            ))
        
        # Excessive slippage alert
        if abs(metrics.slippage_vs_arrival) > self.alert_thresholds["slippage_bps"]:
            alerts.append(TCAAlert(
                alert_type=AlertType.EXCESSIVE_SLIPPAGE,
                severity="medium",
                symbol=order["symbol"],
                order_id=order_id,
                timestamp=datetime.utcnow(),
                message=f"Excessive slippage: {metrics.slippage_vs_arrival:.1f} bps vs arrival",
                current_value=abs(metrics.slippage_vs_arrival),
                threshold_value=self.alert_thresholds["slippage_bps"],
                market_conditions={"volatility": metrics.current_volatility},
                execution_context={"avg_price": metrics.avg_fill_price, "arrival_price": order["arrival_price"]},
                recommendations=[
                    "Review execution strategy",
                    "Consider market timing",
                    "Check for news events"
                ]
            ))
        
        # Poor execution quality alert
        if metrics.execution_efficiency < self.alert_thresholds["execution_efficiency"]:
            alerts.append(TCAAlert(
                alert_type=AlertType.POOR_EXECUTION_QUALITY,
                severity="medium",
                symbol=order["symbol"],
                order_id=order_id,
                timestamp=datetime.utcnow(),
                message=f"Poor execution quality: {metrics.execution_efficiency:.1f}% efficiency",
                current_value=metrics.execution_efficiency,
                threshold_value=self.alert_thresholds["execution_efficiency"],
                market_conditions={"volatility": metrics.current_volatility},
                execution_context={"total_cost": metrics.estimated_total_cost},
                recommendations=[
                    "Pause execution and reassess",
                    "Consider alternative venues",
                    "Adjust execution parameters"
                ]
            ))
        
        # High participation rate alert
        if metrics.participation_rate > self.alert_thresholds["participation_rate"]:
            alerts.append(TCAAlert(
                alert_type=AlertType.HIGH_PARTICIPATION_RATE,
                severity="low",
                symbol=order["symbol"],
                order_id=order_id,
                timestamp=datetime.utcnow(),
                message=f"High participation rate: {metrics.participation_rate:.1%}",
                current_value=metrics.participation_rate,
                threshold_value=self.alert_thresholds["participation_rate"],
                market_conditions={},
                execution_context={"fill_rate": metrics.current_fill_rate},
                recommendations=[
                    "Reduce order aggressiveness",
                    "Spread execution over longer period"
                ]
            ))
        
        # Total cost threshold alert
        if metrics.estimated_total_cost > self.alert_thresholds["cost_threshold_bps"]:
            alerts.append(TCAAlert(
                alert_type=AlertType.COST_THRESHOLD_EXCEEDED,
                severity="high",
                symbol=order["symbol"],
                order_id=order_id,
                timestamp=datetime.utcnow(),
                message=f"Cost threshold exceeded: {metrics.estimated_total_cost:.1f} bps",
                current_value=metrics.estimated_total_cost,
                threshold_value=self.alert_thresholds["cost_threshold_bps"],
                market_conditions={"volatility": metrics.current_volatility},
                execution_context={"remaining": metrics.remaining_quantity},
                recommendations=[
                    "Consider stopping execution",
                    "Reassess cost-benefit",
                    "Wait for better market conditions"
                ]
            ))
        
        return alerts
    
    def _send_alert(self, alert: TCAAlert):
        """Send alert to registered callbacks"""
        self.alerts_history.append(alert)
        
        for callback in self.alert_callbacks:
            try:
                callback(alert)
            except Exception as e:
                logger.error(f"Error in alert callback: {str(e)}")
    
    async def _monitoring_loop(self):
        """Main monitoring loop"""
        while self._is_monitoring:
            try:
                # Update metrics for all active orders
                current_time = datetime.utcnow()
                
                for order_id in list(self.active_orders.keys()):
                    order = self.active_orders[order_id]
                    
                    # Check if order is completed or expired
                    if (order["cumulative_quantity"] >= order["target_quantity"] or
                        current_time > order["expected_end_time"] + timedelta(hours=1)):
                        
                        logger.info(f"Removing completed/expired order {order_id} from monitoring")
                        del self.active_orders[order_id]
                        continue
                    
                    # Calculate and store periodic metrics
                    if order["fills"]:  # Only if there are fills
                        metrics = self._calculate_current_metrics(order_id)
                        
                        # Store periodic metrics
                        self.metrics_history[order_id].append({
                            "timestamp": current_time,
                            "metrics": metrics
                        })
                
                await asyncio.sleep(self.monitoring_interval)
                
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Error in monitoring loop: {str(e)}")
                await asyncio.sleep(self.monitoring_interval)
    
    def get_order_metrics(self, order_id: str) -> Optional[MonitoringMetrics]:
        """Get current metrics for order"""
        if order_id not in self.active_orders:
            return None
        
        return self._calculate_current_metrics(order_id)
    
    def get_recent_alerts(self, limit: int = 10) -> List[TCAAlert]:
        """Get recent alerts"""
        return list(self.alerts_history)[-limit:]
    
    def get_order_history(self, order_id: str) -> List[Dict]:
        """Get metrics history for order"""
        return list(self.metrics_history[order_id])
    
    def generate_execution_report(self, order_id: str) -> Dict:
        """Generate execution report for completed order"""
        if order_id not in self.active_orders:
            # Try to get from history
            history = self.get_order_history(order_id)
            if not history:
                return {"error": f"Order {order_id} not found"}
        
        order = self.active_orders.get(order_id, {})
        history = self.get_order_history(order_id)
        alerts = [alert for alert in self.alerts_history if alert.order_id == order_id]
        
        # Calculate summary metrics
        if history:
            final_metrics = history[-1]["metrics"]
            
            return {
                "order_id": order_id,
                "symbol": order.get("symbol", "unknown"),
                "execution_summary": {
                    "total_quantity": order.get("target_quantity", 0),
                    "filled_quantity": final_metrics.cumulative_quantity,
                    "fill_rate": final_metrics.quantity_progress,
                    "avg_fill_price": final_metrics.avg_fill_price,
                    "total_cost_bps": final_metrics.estimated_total_cost,
                    "market_impact_bps": final_metrics.realized_market_impact,
                    "execution_efficiency": final_metrics.execution_efficiency,
                },
                "benchmark_performance": final_metrics.benchmark_performance,
                "alerts_count": len(alerts),
                "alerts": [alert.to_dict() for alert in alerts],
                "metrics_timeline": [
                    {
                        "timestamp": entry["timestamp"].isoformat(),
                        "metrics": entry["metrics"].to_dict()
                    }
                    for entry in history
                ]
            }
        else:
            return {
                "order_id": order_id,
                "status": "no_execution_data",
                "alerts_count": len(alerts),
                "alerts": [alert.to_dict() for alert in alerts]
            }