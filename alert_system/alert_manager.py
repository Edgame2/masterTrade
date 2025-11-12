"""
Core Alert Manager

Manages alert lifecycle, conditions monitoring, and notification delivery.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Set, Any
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)


class AlertType(Enum):
    """Types of alerts"""
    PRICE = "price"
    PERFORMANCE = "performance"
    RISK = "risk"
    HEALTH = "health"
    MILESTONE = "milestone"
    CUSTOM = "custom"


class AlertPriority(Enum):
    """Alert priority levels"""
    CRITICAL = 1  # Immediate action required
    HIGH = 2      # Important, needs attention
    MEDIUM = 3    # Normal alert
    LOW = 4       # Informational
    INFO = 5      # Just FYI


class AlertStatus(Enum):
    """Alert lifecycle status"""
    PENDING = "pending"
    TRIGGERED = "triggered"
    SENT = "sent"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    EXPIRED = "expired"
    SUPPRESSED = "suppressed"


class AlertChannel(Enum):
    """Notification delivery channels"""
    EMAIL = "email"
    SMS = "sms"
    TELEGRAM = "telegram"
    DISCORD = "discord"
    WEBHOOK = "webhook"
    IN_APP = "in_app"


@dataclass
class Alert:
    """Represents a single alert"""
    alert_id: str
    alert_type: AlertType
    priority: AlertPriority
    title: str
    message: str
    
    # Context
    symbol: Optional[str] = None
    strategy_id: Optional[str] = None
    position_id: Optional[str] = None
    
    # Data
    data: Dict[str, Any] = field(default_factory=dict)
    
    # Delivery
    channels: List[AlertChannel] = field(default_factory=list)
    
    # Status
    status: AlertStatus = AlertStatus.PENDING
    created_at: datetime = field(default_factory=datetime.utcnow)
    triggered_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None
    acknowledged_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    
    # Tracking
    trigger_count: int = 0
    last_trigger_time: Optional[datetime] = None
    
    # Configuration
    throttle_minutes: int = 5  # Min time between repeated alerts
    max_triggers: int = 10  # Max times this alert can trigger
    expires_at: Optional[datetime] = None
    
    # Delivery status
    delivery_results: Dict[AlertChannel, bool] = field(default_factory=dict)
    
    def trigger(self) -> bool:
        """
        Trigger the alert if not throttled.
        
        Returns:
            bool: True if triggered, False if throttled
        """
        now = datetime.utcnow()
        
        # Check if expired
        if self.expires_at and now > self.expires_at:
            self.status = AlertStatus.EXPIRED
            return False
        
        # Check max triggers
        if self.trigger_count >= self.max_triggers:
            logger.warning(f"Alert {self.alert_id} reached max triggers ({self.max_triggers})")
            return False
        
        # Check throttle
        if self.last_trigger_time:
            time_since_last = (now - self.last_trigger_time).total_seconds() / 60
            if time_since_last < self.throttle_minutes:
                logger.debug(f"Alert {self.alert_id} throttled ({time_since_last:.1f} < {self.throttle_minutes} min)")
                return False
        
        # Trigger the alert
        self.status = AlertStatus.TRIGGERED
        self.triggered_at = now
        self.last_trigger_time = now
        self.trigger_count += 1
        
        logger.info(f"Alert triggered: {self.alert_id} ({self.title}) - trigger {self.trigger_count}/{self.max_triggers}")
        return True
    
    def mark_sent(self, channel: AlertChannel, success: bool):
        """Mark alert as sent via a channel"""
        self.delivery_results[channel] = success
        if success and self.status == AlertStatus.TRIGGERED:
            self.status = AlertStatus.SENT
            self.sent_at = datetime.utcnow()
    
    def acknowledge(self):
        """Acknowledge the alert"""
        self.status = AlertStatus.ACKNOWLEDGED
        self.acknowledged_at = datetime.utcnow()
    
    def resolve(self):
        """Resolve the alert"""
        self.status = AlertStatus.RESOLVED
        self.resolved_at = datetime.utcnow()
    
    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "alert_id": self.alert_id,
            "alert_type": self.alert_type.value,
            "priority": self.priority.value,
            "title": self.title,
            "message": self.message,
            "symbol": self.symbol,
            "strategy_id": self.strategy_id,
            "position_id": self.position_id,
            "data": self.data,
            "channels": [c.value for c in self.channels],
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "triggered_at": self.triggered_at.isoformat() if self.triggered_at else None,
            "sent_at": self.sent_at.isoformat() if self.sent_at else None,
            "acknowledged_at": self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "trigger_count": self.trigger_count,
            "throttle_minutes": self.throttle_minutes,
            "max_triggers": self.max_triggers,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "delivery_results": {k.value: v for k, v in self.delivery_results.items()},
        }


class AlertManager:
    """
    Central alert management system.
    
    Manages alert lifecycle:
    - Alert creation and storage
    - Condition monitoring
    - Throttling and suppression
    - Multi-channel delivery via NotificationService
    - Alert history and acknowledgment
    """
    
    def __init__(self, notification_service=None):
        self.alerts: Dict[str, Alert] = {}
        
        # Alert conditions (monitored continuously)
        from alert_conditions import AlertCondition
        self.conditions: Dict[str, AlertCondition] = {}
        
        # Notification service (manages all channels)
        if notification_service is None:
            from notification_service import NotificationService
            self.notification_service = NotificationService()
        else:
            self.notification_service = notification_service
        
        # Legacy channel support (for backwards compatibility)
        from notification_channels import NotificationChannel
        self.channels: Dict[AlertChannel, NotificationChannel] = {}
        
        # Suppression rules (symbol -> until_time)
        self.suppressions: Dict[str, datetime] = {}
        
        # Statistics
        self.stats = {
            "total_alerts": 0,
            "triggered_today": 0,
            "sent_today": 0,
            "acknowledged_today": 0,
            "by_type": defaultdict(int),
            "by_priority": defaultdict(int),
            "by_channel": defaultdict(int),
        }
        
        logger.info("AlertManager initialized with NotificationService")
    
    def register_channel(self, channel_type: AlertChannel, channel: 'NotificationChannel'):
        """Register a notification channel"""
        self.channels[channel_type] = channel
        logger.info(f"Registered notification channel: {channel_type.value}")
    
    def create_alert(
        self,
        alert_type: AlertType,
        priority: AlertPriority,
        title: str,
        message: str,
        channels: List[AlertChannel],
        symbol: Optional[str] = None,
        strategy_id: Optional[str] = None,
        position_id: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
        throttle_minutes: int = 5,
        max_triggers: int = 10,
        expires_in_hours: Optional[int] = None,
    ) -> Alert:
        """
        Create a new alert.
        
        Args:
            alert_type: Type of alert
            priority: Priority level
            title: Alert title
            message: Alert message
            channels: Delivery channels
            symbol: Associated symbol
            strategy_id: Associated strategy
            position_id: Associated position
            data: Additional data
            throttle_minutes: Min minutes between repeats
            max_triggers: Max times this can trigger
            expires_in_hours: Hours until expiration
            
        Returns:
            Alert: Created alert
        """
        alert_id = f"{alert_type.value}_{self.stats['total_alerts'] + 1}_{int(datetime.utcnow().timestamp())}"
        
        expires_at = None
        if expires_in_hours:
            expires_at = datetime.utcnow() + timedelta(hours=expires_in_hours)
        
        alert = Alert(
            alert_id=alert_id,
            alert_type=alert_type,
            priority=priority,
            title=title,
            message=message,
            channels=channels,
            symbol=symbol,
            strategy_id=strategy_id,
            position_id=position_id,
            data=data or {},
            throttle_minutes=throttle_minutes,
            max_triggers=max_triggers,
            expires_at=expires_at,
        )
        
        self.alerts[alert_id] = alert
        self.stats["total_alerts"] += 1
        self.stats["by_type"][alert_type.value] += 1
        self.stats["by_priority"][priority.value] += 1
        
        logger.info(f"Created alert: {alert_id} - {title}")
        return alert
    
    def trigger_alert(self, alert_id: str) -> bool:
        """
        Trigger an alert.
        
        Args:
            alert_id: Alert to trigger
            
        Returns:
            bool: True if triggered and sent, False if throttled/failed
        """
        if alert_id not in self.alerts:
            logger.error(f"Alert not found: {alert_id}")
            return False
        
        alert = self.alerts[alert_id]
        
        # Check suppression
        if alert.symbol and alert.symbol in self.suppressions:
            if datetime.utcnow() < self.suppressions[alert.symbol]:
                logger.debug(f"Alert suppressed for symbol: {alert.symbol}")
                alert.status = AlertStatus.SUPPRESSED
                return False
        
        # Try to trigger
        if not alert.trigger():
            return False
        
        self.stats["triggered_today"] += 1
        
        # Send via all channels
        success = self._send_alert(alert)
        
        if success:
            self.stats["sent_today"] += 1
        
        return success
    
    def _send_alert(self, alert: Alert) -> bool:
        """
        Send alert via NotificationService.
        
        Args:
            alert: Alert to send
            
        Returns:
            bool: True if sent via at least one channel
        """
        try:
            # Use NotificationService for delivery
            delivery_report = self.notification_service.send_notification(alert)
            
            # Update statistics
            if delivery_report.is_successful:
                logger.info(
                    f"Alert sent via NotificationService: {alert.alert_id} "
                    f"({delivery_report.successful_channels}/{delivery_report.total_channels} channels)"
                )
                return True
            else:
                logger.error(
                    f"Failed to send alert via any channel: {alert.alert_id}"
                )
                return False
                
        except Exception as e:
            logger.error(f"Error sending alert via NotificationService: {e}")
            
            # Fallback to legacy channel delivery if NotificationService fails
            return self._send_alert_legacy(alert)
    
    def _send_alert_legacy(self, alert: Alert) -> bool:
        """
        Legacy method: Send alert via directly configured channels.
        Used as fallback if NotificationService fails.
        
        Args:
            alert: Alert to send
            
        Returns:
            bool: True if sent via at least one channel
        """
        any_success = False
        
        for channel_type in alert.channels:
            if channel_type not in self.channels:
                logger.warning(f"Channel not configured: {channel_type.value}")
                alert.mark_sent(channel_type, False)
                continue
            
            try:
                channel = self.channels[channel_type]
                result = channel.send(alert)
                
                alert.mark_sent(channel_type, result.success)
                
                if result.success:
                    any_success = True
                    self.stats["by_channel"][channel_type.value] += 1
                    logger.info(f"Alert sent via {channel_type.value}: {alert.alert_id}")
                else:
                    logger.error(f"Failed to send alert via {channel_type.value}: {result.error}")
                    
            except Exception as e:
                logger.error(f"Error sending alert via {channel_type.value}: {e}")
                alert.mark_sent(channel_type, False)
        
        return any_success
    
    def acknowledge_alert(self, alert_id: str):
        """Acknowledge an alert"""
        if alert_id in self.alerts:
            self.alerts[alert_id].acknowledge()
            self.stats["acknowledged_today"] += 1
            logger.info(f"Alert acknowledged: {alert_id}")
    
    def resolve_alert(self, alert_id: str):
        """Resolve an alert"""
        if alert_id in self.alerts:
            self.alerts[alert_id].resolve()
            logger.info(f"Alert resolved: {alert_id}")
    
    def suppress_alerts(self, symbol: str, duration_minutes: int):
        """
        Suppress all alerts for a symbol temporarily.
        
        Args:
            symbol: Symbol to suppress
            duration_minutes: Suppression duration
        """
        until = datetime.utcnow() + timedelta(minutes=duration_minutes)
        self.suppressions[symbol] = until
        logger.info(f"Alerts suppressed for {symbol} until {until}")
    
    def get_alerts(
        self,
        alert_type: Optional[AlertType] = None,
        priority: Optional[AlertPriority] = None,
        status: Optional[AlertStatus] = None,
        symbol: Optional[str] = None,
        strategy_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Alert]:
        """
        Query alerts with filters.
        
        Args:
            alert_type: Filter by type
            priority: Filter by priority
            status: Filter by status
            symbol: Filter by symbol
            strategy_id: Filter by strategy
            limit: Max results
            
        Returns:
            List of matching alerts
        """
        results = []
        
        for alert in self.alerts.values():
            if alert_type and alert.alert_type != alert_type:
                continue
            if priority and alert.priority != priority:
                continue
            if status and alert.status != status:
                continue
            if symbol and alert.symbol != symbol:
                continue
            if strategy_id and alert.strategy_id != strategy_id:
                continue
            
            results.append(alert)
            
            if len(results) >= limit:
                break
        
        # Sort by priority and created time
        results.sort(key=lambda a: (a.priority.value, a.created_at), reverse=True)
        
        return results
    
    def get_alert(self, alert_id: str) -> Optional[Alert]:
        """Get specific alert"""
        return self.alerts.get(alert_id)
    
    def get_active_alerts(self) -> List[Alert]:
        """Get all active (pending or triggered) alerts"""
        return [
            alert for alert in self.alerts.values()
            if alert.status in [AlertStatus.PENDING, AlertStatus.TRIGGERED, AlertStatus.SENT]
        ]
    
    def get_statistics(self) -> dict:
        """Get alert statistics including NotificationService stats"""
        active_alerts = self.get_active_alerts()
        
        stats = {
            "total_alerts": self.stats["total_alerts"],
            "active_alerts": len(active_alerts),
            "triggered_today": self.stats["triggered_today"],
            "sent_today": self.stats["sent_today"],
            "acknowledged_today": self.stats["acknowledged_today"],
            "by_type": dict(self.stats["by_type"]),
            "by_priority": dict(self.stats["by_priority"]),
            "by_channel": dict(self.stats["by_channel"]),
            "suppressions": len(self.suppressions),
        }
        
        # Add NotificationService statistics
        if hasattr(self, 'notification_service') and self.notification_service:
            stats["notification_service"] = self.notification_service.get_statistics()
        
        return stats
    
    def get_channel_health(self) -> dict:
        """Get notification channel health status"""
        if hasattr(self, 'notification_service') and self.notification_service:
            return self.notification_service.get_channel_health()
        return {}
    
    def test_notification_channel(self, channel_name: str):
        """
        Test a notification channel.
        
        Args:
            channel_name: Name of channel to test (email, slack, telegram, etc.)
            
        Returns:
            NotificationResult: Test result
        """
        if hasattr(self, 'notification_service') and self.notification_service:
            return self.notification_service.test_channel(channel_name)
        else:
            raise RuntimeError("NotificationService not initialized")
    
    def cleanup_old_alerts(self, days: int = 7):
        """
        Clean up resolved/expired alerts older than X days.
        
        Args:
            days: Age threshold in days
        """
        cutoff = datetime.utcnow() - timedelta(days=days)
        
        to_remove = []
        for alert_id, alert in self.alerts.items():
            if alert.status in [AlertStatus.RESOLVED, AlertStatus.EXPIRED]:
                if alert.created_at < cutoff:
                    to_remove.append(alert_id)
        
        for alert_id in to_remove:
            del self.alerts[alert_id]
        
        logger.info(f"Cleaned up {len(to_remove)} old alerts")
