"""
Alert & Notification System for masterTrade

Provides comprehensive alerting capabilities:
- Price alerts (breakouts, support/resistance)
- Strategy performance alerts
- Risk breach alerts
- System health alerts
- Performance milestones
- Multi-channel delivery (email, SMS, Telegram, Discord)
"""

from .alert_manager import (
    AlertManager,
    Alert,
    AlertType,
    AlertPriority,
    AlertStatus,
    AlertChannel,
)

from .alert_conditions import (
    AlertCondition,
    PriceAlertCondition,
    PerformanceAlertCondition,
    RiskAlertCondition,
    SystemHealthAlertCondition,
    MilestoneAlertCondition,
)

from .notification_channels import (
    NotificationChannel,
    EmailNotificationChannel,
    SMSNotificationChannel,
    TelegramNotificationChannel,
    DiscordNotificationChannel,
    NotificationResult,
)

from .alert_templates import (
    AlertTemplate,
    TemplateRenderer,
    get_default_templates,
)

from .api import alert_router

__all__ = [
    # Core
    "AlertManager",
    "Alert",
    "AlertType",
    "AlertPriority",
    "AlertStatus",
    "AlertChannel",
    
    # Conditions
    "AlertCondition",
    "PriceAlertCondition",
    "PerformanceAlertCondition",
    "RiskAlertCondition",
    "SystemHealthAlertCondition",
    "MilestoneAlertCondition",
    
    # Channels
    "NotificationChannel",
    "EmailNotificationChannel",
    "SMSNotificationChannel",
    "TelegramNotificationChannel",
    "DiscordNotificationChannel",
    "NotificationResult",
    
    # Templates
    "AlertTemplate",
    "TemplateRenderer",
    "get_default_templates",
    
    # API
    "alert_router",
]
