"""
Alert Conditions

Defines various types of alert conditions that are monitored continuously.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional, Any, List
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class ComparisonOperator(Enum):
    """Comparison operators for conditions"""
    GREATER_THAN = ">"
    LESS_THAN = "<"
    GREATER_EQUAL = ">="
    LESS_EQUAL = "<="
    EQUAL = "=="
    NOT_EQUAL = "!="
    CROSSES_ABOVE = "crosses_above"
    CROSSES_BELOW = "crosses_below"


@dataclass
class AlertCondition(ABC):
    """
    Base class for alert conditions.
    
    Conditions are monitored continuously and trigger alerts when met.
    """
    condition_id: str
    enabled: bool = True
    last_check_time: Optional[datetime] = None
    last_value: Optional[float] = None
    
    @abstractmethod
    def check(self, data: Dict[str, Any]) -> bool:
        """
        Check if condition is met.
        
        Args:
            data: Current market/system data
            
        Returns:
            bool: True if condition met
        """
        pass
    
    @abstractmethod
    def get_description(self) -> str:
        """Get human-readable condition description"""
        pass


@dataclass
class PriceAlertCondition(AlertCondition):
    """
    Price-based alert conditions.
    
    Triggers on:
    - Price above/below threshold
    - Price crosses level
    - Percentage change
    - Volatility spikes
    """
    symbol: str
    operator: ComparisonOperator
    threshold: float
    
    # For percentage change alerts
    percentage_change: Optional[float] = None
    timeframe_minutes: Optional[int] = None
    
    # For volatility alerts
    volatility_threshold: Optional[float] = None
    
    # Previous value for cross detection
    previous_value: Optional[float] = None
    
    def check(self, data: Dict[str, Any]) -> bool:
        """
        Check if price condition is met.
        
        Args:
            data: {"symbol": str, "price": float, "timestamp": datetime, 
                   "volume": float, "volatility": float}
        """
        if data.get("symbol") != self.symbol:
            return False
        
        current_price = data.get("price")
        if current_price is None:
            return False
        
        # Store for cross detection
        prev_value = self.previous_value
        self.previous_value = current_price
        self.last_value = current_price
        self.last_check_time = datetime.utcnow()
        
        # Check percentage change
        if self.percentage_change is not None and self.timeframe_minutes:
            # Would need historical data - simplified here
            # In production, query price from X minutes ago
            pass
        
        # Check volatility
        if self.volatility_threshold is not None:
            volatility = data.get("volatility", 0)
            if volatility > self.volatility_threshold:
                logger.info(f"Volatility alert: {self.symbol} volatility {volatility:.2f} > {self.volatility_threshold:.2f}")
                return True
        
        # Check price condition
        if self.operator == ComparisonOperator.GREATER_THAN:
            return current_price > self.threshold
        elif self.operator == ComparisonOperator.LESS_THAN:
            return current_price < self.threshold
        elif self.operator == ComparisonOperator.GREATER_EQUAL:
            return current_price >= self.threshold
        elif self.operator == ComparisonOperator.LESS_EQUAL:
            return current_price <= self.threshold
        elif self.operator == ComparisonOperator.EQUAL:
            return abs(current_price - self.threshold) < 0.01  # Epsilon comparison
        elif self.operator == ComparisonOperator.CROSSES_ABOVE:
            if prev_value is not None:
                return prev_value <= self.threshold < current_price
        elif self.operator == ComparisonOperator.CROSSES_BELOW:
            if prev_value is not None:
                return prev_value >= self.threshold > current_price
        
        return False
    
    def get_description(self) -> str:
        """Get description"""
        if self.volatility_threshold:
            return f"{self.symbol} volatility > {self.volatility_threshold:.2f}"
        
        return f"{self.symbol} price {self.operator.value} {self.threshold:.2f}"


@dataclass
class PerformanceAlertCondition(AlertCondition):
    """
    Strategy performance alert conditions.
    
    Triggers on:
    - Win rate above/below threshold
    - Profit/loss above/below threshold
    - Drawdown exceeds limit
    - Winning/losing streak
    """
    strategy_id: str
    metric: str  # "win_rate", "pnl", "drawdown", "sharpe_ratio", "streak"
    operator: ComparisonOperator
    threshold: float
    
    # For streak detection
    streak_type: Optional[str] = None  # "winning" or "losing"
    streak_length: Optional[int] = None
    
    def check(self, data: Dict[str, Any]) -> bool:
        """
        Check if performance condition is met.
        
        Args:
            data: {"strategy_id": str, "win_rate": float, "pnl": float,
                   "drawdown": float, "sharpe_ratio": float, "recent_trades": List}
        """
        if data.get("strategy_id") != self.strategy_id:
            return False
        
        self.last_check_time = datetime.utcnow()
        
        # Check streak
        if self.metric == "streak" and self.streak_type:
            recent_trades = data.get("recent_trades", [])
            if not recent_trades:
                return False
            
            # Count consecutive wins/losses
            streak = 0
            for trade in recent_trades:
                if self.streak_type == "winning" and trade.get("pnl", 0) > 0:
                    streak += 1
                elif self.streak_type == "losing" and trade.get("pnl", 0) < 0:
                    streak += 1
                else:
                    break
            
            self.last_value = streak
            return streak >= (self.streak_length or 5)
        
        # Get metric value
        value = data.get(self.metric)
        if value is None:
            return False
        
        self.last_value = value
        
        # Check condition
        if self.operator == ComparisonOperator.GREATER_THAN:
            return value > self.threshold
        elif self.operator == ComparisonOperator.LESS_THAN:
            return value < self.threshold
        elif self.operator == ComparisonOperator.GREATER_EQUAL:
            return value >= self.threshold
        elif self.operator == ComparisonOperator.LESS_EQUAL:
            return value <= self.threshold
        
        return False
    
    def get_description(self) -> str:
        """Get description"""
        if self.metric == "streak":
            return f"{self.strategy_id} {self.streak_type} streak >= {self.streak_length}"
        
        return f"{self.strategy_id} {self.metric} {self.operator.value} {self.threshold:.2f}"


@dataclass
class RiskAlertCondition(AlertCondition):
    """
    Risk management alert conditions.
    
    Triggers on:
    - Portfolio drawdown exceeds limit
    - Position size exceeds limit
    - Leverage exceeds limit
    - Margin level critical
    - Stop loss hit
    - Risk limit breach
    """
    risk_metric: str  # "drawdown", "position_size", "leverage", "margin", "exposure"
    operator: ComparisonOperator
    threshold: float
    
    # Optional filters
    symbol: Optional[str] = None
    position_id: Optional[str] = None
    
    def check(self, data: Dict[str, Any]) -> bool:
        """
        Check if risk condition is met.
        
        Args:
            data: {"drawdown": float, "position_size": float, "leverage": float,
                   "margin_level": float, "exposure": float, "symbol": str}
        """
        # Apply filters
        if self.symbol and data.get("symbol") != self.symbol:
            return False
        if self.position_id and data.get("position_id") != self.position_id:
            return False
        
        self.last_check_time = datetime.utcnow()
        
        # Get metric value
        value = data.get(self.risk_metric)
        if value is None:
            return False
        
        self.last_value = value
        
        # Check condition
        if self.operator == ComparisonOperator.GREATER_THAN:
            result = value > self.threshold
        elif self.operator == ComparisonOperator.LESS_THAN:
            result = value < self.threshold
        elif self.operator == ComparisonOperator.GREATER_EQUAL:
            result = value >= self.threshold
        elif self.operator == ComparisonOperator.LESS_EQUAL:
            result = value <= self.threshold
        else:
            result = False
        
        if result:
            logger.warning(f"Risk alert: {self.risk_metric} = {value:.2f} {self.operator.value} {self.threshold:.2f}")
        
        return result
    
    def get_description(self) -> str:
        """Get description"""
        desc = f"{self.risk_metric} {self.operator.value} {self.threshold:.2f}"
        if self.symbol:
            desc = f"{self.symbol} {desc}"
        return desc


@dataclass
class SystemHealthAlertCondition(AlertCondition):
    """
    System health alert conditions.
    
    Triggers on:
    - Service downtime
    - API errors
    - Connection issues
    - Database errors
    - High latency
    - Resource usage (CPU, memory)
    """
    service_name: str
    health_metric: str  # "uptime", "error_rate", "latency", "cpu", "memory"
    operator: ComparisonOperator
    threshold: float
    
    # Consecutive failures before alerting
    consecutive_failures: int = 3
    failure_count: int = 0
    
    def check(self, data: Dict[str, Any]) -> bool:
        """
        Check if health condition is met.
        
        Args:
            data: {"service": str, "uptime": float, "error_rate": float,
                   "latency_ms": float, "cpu_percent": float, "memory_percent": float}
        """
        if data.get("service") != self.service_name:
            return False
        
        self.last_check_time = datetime.utcnow()
        
        # Get metric value
        value = data.get(self.health_metric)
        if value is None:
            return False
        
        self.last_value = value
        
        # Check condition
        condition_met = False
        if self.operator == ComparisonOperator.GREATER_THAN:
            condition_met = value > self.threshold
        elif self.operator == ComparisonOperator.LESS_THAN:
            condition_met = value < self.threshold
        elif self.operator == ComparisonOperator.GREATER_EQUAL:
            condition_met = value >= self.threshold
        elif self.operator == ComparisonOperator.LESS_EQUAL:
            condition_met = value <= self.threshold
        
        # Track consecutive failures
        if condition_met:
            self.failure_count += 1
        else:
            self.failure_count = 0
        
        # Alert only after consecutive failures
        if self.failure_count >= self.consecutive_failures:
            logger.error(f"System health alert: {self.service_name} {self.health_metric} = {value:.2f}")
            return True
        
        return False
    
    def get_description(self) -> str:
        """Get description"""
        return f"{self.service_name} {self.health_metric} {self.operator.value} {self.threshold:.2f}"


@dataclass
class MilestoneAlertCondition(AlertCondition):
    """
    Performance milestone alert conditions.
    
    Triggers on:
    - Total profit milestone reached
    - Win rate milestone
    - Number of trades milestone
    - ROI milestone
    - New equity high
    """
    milestone_type: str  # "total_profit", "win_rate", "trade_count", "roi", "equity_high"
    threshold: float
    
    # Track if already triggered (one-time alerts)
    triggered_once: bool = False
    
    def check(self, data: Dict[str, Any]) -> bool:
        """
        Check if milestone is reached.
        
        Args:
            data: {"total_profit": float, "win_rate": float, "trade_count": int,
                   "roi": float, "equity": float, "equity_high": float}
        """
        # Don't trigger again if already triggered
        if self.triggered_once:
            return False
        
        self.last_check_time = datetime.utcnow()
        
        # Get value
        value = data.get(self.milestone_type)
        if value is None:
            return False
        
        self.last_value = value
        
        # Check if milestone reached
        if value >= self.threshold:
            self.triggered_once = True
            logger.info(f"Milestone reached: {self.milestone_type} = {value:.2f} >= {self.threshold:.2f}")
            return True
        
        return False
    
    def get_description(self) -> str:
        """Get description"""
        return f"{self.milestone_type} reaches {self.threshold:.2f}"
