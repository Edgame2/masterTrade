"""
Alert Templates

Provides templating for common alert types with variable substitution.
"""

from dataclasses import dataclass
from typing import Dict, Any, Optional
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class TemplateType(Enum):
    """Template types"""
    PRICE_BREAKOUT = "price_breakout"
    PRICE_BREAKDOWN = "price_breakdown"
    STOP_LOSS_HIT = "stop_loss_hit"
    TAKE_PROFIT_HIT = "take_profit_hit"
    DRAWDOWN_WARNING = "drawdown_warning"
    DRAWDOWN_CRITICAL = "drawdown_critical"
    WINNING_STREAK = "winning_streak"
    LOSING_STREAK = "losing_streak"
    STRATEGY_ACTIVATED = "strategy_activated"
    STRATEGY_DEACTIVATED = "strategy_deactivated"
    SERVICE_DOWN = "service_down"
    SERVICE_RECOVERED = "service_recovered"
    HIGH_LATENCY = "high_latency"
    PROFIT_MILESTONE = "profit_milestone"
    TRADE_MILESTONE = "trade_milestone"


@dataclass
class AlertTemplate:
    """Alert template with variable substitution"""
    template_type: TemplateType
    title_template: str
    message_template: str
    priority: 'AlertPriority'
    alert_type: 'AlertType'
    
    def render(self, variables: Dict[str, Any]) -> Dict[str, str]:
        """
        Render template with variables.
        
        Args:
            variables: Variable values
            
        Returns:
            Dict with 'title' and 'message'
        """
        try:
            title = self.title_template.format(**variables)
            message = self.message_template.format(**variables)
            
            return {"title": title, "message": message}
            
        except KeyError as e:
            logger.error(f"Missing template variable: {e}")
            return {
                "title": "Alert Template Error",
                "message": f"Missing variable: {e}",
            }


class TemplateRenderer:
    """Manages and renders alert templates"""
    
    def __init__(self):
        self.templates: Dict[TemplateType, AlertTemplate] = {}
        self._load_default_templates()
    
    def _load_default_templates(self):
        """Load default alert templates"""
        from .alert_manager import AlertPriority, AlertType
        
        # Price alerts
        self.templates[TemplateType.PRICE_BREAKOUT] = AlertTemplate(
            template_type=TemplateType.PRICE_BREAKOUT,
            title_template="🚀 {symbol} Breakout at ${price:.2f}",
            message_template=(
                "{symbol} has broken above resistance at ${level:.2f}\n"
                "Current price: ${price:.2f} (+{change_percent:.2f}%)\n"
                "Volume: {volume:,.0f}\n\n"
                "This may signal a bullish trend continuation."
            ),
            priority=AlertPriority.HIGH,
            alert_type=AlertType.PRICE,
        )
        
        self.templates[TemplateType.PRICE_BREAKDOWN] = AlertTemplate(
            template_type=TemplateType.PRICE_BREAKDOWN,
            title_template="⚠️ {symbol} Breakdown at ${price:.2f}",
            message_template=(
                "{symbol} has broken below support at ${level:.2f}\n"
                "Current price: ${price:.2f} ({change_percent:.2f}%)\n"
                "Volume: {volume:,.0f}\n\n"
                "This may signal a bearish trend."
            ),
            priority=AlertPriority.HIGH,
            alert_type=AlertType.PRICE,
        )
        
        # Risk alerts
        self.templates[TemplateType.STOP_LOSS_HIT] = AlertTemplate(
            template_type=TemplateType.STOP_LOSS_HIT,
            title_template="🛑 Stop Loss Hit - {symbol}",
            message_template=(
                "Stop loss triggered for {symbol} position.\n\n"
                "Entry Price: ${entry_price:.2f}\n"
                "Exit Price: ${exit_price:.2f}\n"
                "Loss: ${loss:.2f} ({loss_percent:.2f}%)\n"
                "Position Size: {size:.4f}\n\n"
                "Position has been closed to limit losses."
            ),
            priority=AlertPriority.CRITICAL,
            alert_type=AlertType.RISK,
        )
        
        self.templates[TemplateType.TAKE_PROFIT_HIT] = AlertTemplate(
            template_type=TemplateType.TAKE_PROFIT_HIT,
            title_template="🎯 Take Profit Hit - {symbol}",
            message_template=(
                "Take profit target reached for {symbol}!\n\n"
                "Entry Price: ${entry_price:.2f}\n"
                "Exit Price: ${exit_price:.2f}\n"
                "Profit: ${profit:.2f} (+{profit_percent:.2f}%)\n"
                "Position Size: {size:.4f}\n\n"
                "Congratulations on the winning trade!"
            ),
            priority=AlertPriority.HIGH,
            alert_type=AlertType.RISK,
        )
        
        self.templates[TemplateType.DRAWDOWN_WARNING] = AlertTemplate(
            template_type=TemplateType.DRAWDOWN_WARNING,
            title_template="⚠️ Drawdown Warning: {drawdown_percent:.1f}%",
            message_template=(
                "Portfolio drawdown has reached {drawdown_percent:.1f}%\n\n"
                "Current Equity: ${equity:,.2f}\n"
                "Peak Equity: ${peak_equity:,.2f}\n"
                "Drawdown: ${drawdown:,.2f}\n\n"
                "Consider reducing position sizes or taking a break."
            ),
            priority=AlertPriority.HIGH,
            alert_type=AlertType.RISK,
        )
        
        self.templates[TemplateType.DRAWDOWN_CRITICAL] = AlertTemplate(
            template_type=TemplateType.DRAWDOWN_CRITICAL,
            title_template="🔴 CRITICAL DRAWDOWN: {drawdown_percent:.1f}%",
            message_template=(
                "CRITICAL: Portfolio drawdown has exceeded {drawdown_percent:.1f}%!\n\n"
                "Current Equity: ${equity:,.2f}\n"
                "Peak Equity: ${peak_equity:,.2f}\n"
                "Drawdown: ${drawdown:,.2f}\n\n"
                "IMMEDIATE ACTION REQUIRED:\n"
                "- Close losing positions\n"
                "- Stop trading temporarily\n"
                "- Review strategy performance\n"
                "- Assess risk management"
            ),
            priority=AlertPriority.CRITICAL,
            alert_type=AlertType.RISK,
        )
        
        # Performance alerts
        self.templates[TemplateType.WINNING_STREAK] = AlertTemplate(
            template_type=TemplateType.WINNING_STREAK,
            title_template="🔥 {streak_length} Trade Winning Streak!",
            message_template=(
                "Congratulations! You're on a {streak_length} trade winning streak.\n\n"
                "Strategy: {strategy_id}\n"
                "Total Profit: ${total_profit:.2f}\n"
                "Win Rate: {win_rate:.1f}%\n"
                "Average Profit: ${avg_profit:.2f}\n\n"
                "Keep up the excellent work!"
            ),
            priority=AlertPriority.MEDIUM,
            alert_type=AlertType.PERFORMANCE,
        )
        
        self.templates[TemplateType.LOSING_STREAK] = AlertTemplate(
            template_type=TemplateType.LOSING_STREAK,
            title_template="⚠️ {streak_length} Trade Losing Streak",
            message_template=(
                "Alert: {streak_length} consecutive losing trades detected.\n\n"
                "Strategy: {strategy_id}\n"
                "Total Loss: ${total_loss:.2f}\n"
                "Win Rate: {win_rate:.1f}%\n"
                "Average Loss: ${avg_loss:.2f}\n\n"
                "Recommended actions:\n"
                "- Review strategy parameters\n"
                "- Reduce position sizes\n"
                "- Consider pausing strategy"
            ),
            priority=AlertPriority.HIGH,
            alert_type=AlertType.PERFORMANCE,
        )
        
        self.templates[TemplateType.STRATEGY_ACTIVATED] = AlertTemplate(
            template_type=TemplateType.STRATEGY_ACTIVATED,
            title_template="✅ Strategy Activated: {strategy_name}",
            message_template=(
                "Strategy '{strategy_name}' has been automatically activated.\n\n"
                "Symbol: {symbol}\n"
                "Reason: {reason}\n"
                "Confidence Score: {confidence:.2f}\n"
                "Backtest Win Rate: {win_rate:.1f}%\n"
                "Backtest Sharpe: {sharpe:.2f}\n\n"
                "The strategy will now trade live."
            ),
            priority=AlertPriority.MEDIUM,
            alert_type=AlertType.PERFORMANCE,
        )
        
        self.templates[TemplateType.STRATEGY_DEACTIVATED] = AlertTemplate(
            template_type=TemplateType.STRATEGY_DEACTIVATED,
            title_template="⏸️ Strategy Deactivated: {strategy_name}",
            message_template=(
                "Strategy '{strategy_name}' has been automatically deactivated.\n\n"
                "Symbol: {symbol}\n"
                "Reason: {reason}\n"
                "Final Performance:\n"
                "- P&L: ${pnl:.2f}\n"
                "- Win Rate: {win_rate:.1f}%\n"
                "- Total Trades: {trade_count}\n\n"
                "The strategy has been paused pending review."
            ),
            priority=AlertPriority.HIGH,
            alert_type=AlertType.PERFORMANCE,
        )
        
        # System health alerts
        self.templates[TemplateType.SERVICE_DOWN] = AlertTemplate(
            template_type=TemplateType.SERVICE_DOWN,
            title_template="🔴 SERVICE DOWN: {service_name}",
            message_template=(
                "CRITICAL: {service_name} service is down!\n\n"
                "Error: {error_message}\n"
                "Last Successful Check: {last_success}\n"
                "Consecutive Failures: {failure_count}\n\n"
                "Impact: {impact}\n\n"
                "Action Required: Check logs and restart service if needed."
            ),
            priority=AlertPriority.CRITICAL,
            alert_type=AlertType.HEALTH,
        )
        
        self.templates[TemplateType.SERVICE_RECOVERED] = AlertTemplate(
            template_type=TemplateType.SERVICE_RECOVERED,
            title_template="✅ Service Recovered: {service_name}",
            message_template=(
                "{service_name} service has recovered.\n\n"
                "Downtime: {downtime_minutes:.1f} minutes\n"
                "Service is now operational.\n\n"
                "Review logs for root cause analysis."
            ),
            priority=AlertPriority.MEDIUM,
            alert_type=AlertType.HEALTH,
        )
        
        self.templates[TemplateType.HIGH_LATENCY] = AlertTemplate(
            template_type=TemplateType.HIGH_LATENCY,
            title_template="⚠️ High Latency: {service_name}",
            message_template=(
                "High latency detected in {service_name}.\n\n"
                "Current Latency: {latency_ms:.0f}ms\n"
                "Threshold: {threshold_ms:.0f}ms\n"
                "Average (1h): {avg_latency_ms:.0f}ms\n\n"
                "This may impact trading performance."
            ),
            priority=AlertPriority.MEDIUM,
            alert_type=AlertType.HEALTH,
        )
        
        # Milestone alerts
        self.templates[TemplateType.PROFIT_MILESTONE] = AlertTemplate(
            template_type=TemplateType.PROFIT_MILESTONE,
            title_template="🎉 Profit Milestone: ${milestone:,.0f} Reached!",
            message_template=(
                "Congratulations! You've reached ${milestone:,.0f} in total profit!\n\n"
                "Total Profit: ${total_profit:,.2f}\n"
                "Total Trades: {trade_count}\n"
                "Win Rate: {win_rate:.1f}%\n"
                "ROI: {roi:.1f}%\n"
                "Time Period: {days} days\n\n"
                "Excellent trading performance!"
            ),
            priority=AlertPriority.LOW,
            alert_type=AlertType.MILESTONE,
        )
        
        self.templates[TemplateType.TRADE_MILESTONE] = AlertTemplate(
            template_type=TemplateType.TRADE_MILESTONE,
            title_template="📊 {milestone} Trades Completed!",
            message_template=(
                "You've completed {milestone} trades!\n\n"
                "Performance Summary:\n"
                "- Total P&L: ${total_pnl:.2f}\n"
                "- Win Rate: {win_rate:.1f}%\n"
                "- Average Profit: ${avg_profit:.2f}\n"
                "- Sharpe Ratio: {sharpe:.2f}\n"
                "- Max Drawdown: {max_drawdown:.1f}%\n\n"
                "Keep improving!"
            ),
            priority=AlertPriority.INFO,
            alert_type=AlertType.MILESTONE,
        )
    
    def register_template(self, template: AlertTemplate):
        """Register a custom template"""
        self.templates[template.template_type] = template
        logger.info(f"Registered template: {template.template_type.value}")
    
    def render(self, template_type: TemplateType, variables: Dict[str, Any]) -> Optional[Dict[str, str]]:
        """Render a template"""
        if template_type not in self.templates:
            logger.error(f"Template not found: {template_type.value}")
            return None
        
        return self.templates[template_type].render(variables)
    
    def get_template(self, template_type: TemplateType) -> Optional[AlertTemplate]:
        """Get template"""
        return self.templates.get(template_type)


def get_default_templates() -> Dict[TemplateType, AlertTemplate]:
    """Get all default templates"""
    renderer = TemplateRenderer()
    return renderer.templates
