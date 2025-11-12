"""
Notification Service

Orchestrates multi-channel notification delivery for alerts.
Manages channel configuration, delivery routing, retry logic, and delivery tracking.
"""

import os
import asyncio
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field
from datetime import datetime
import logging

from notification_channels import (
    NotificationChannel,
    NotificationResult,
    EmailNotificationChannel,
    SMSNotificationChannel,
    TelegramNotificationChannel,
    DiscordNotificationChannel,
    WebhookNotificationChannel,
    SlackNotificationChannel,
)
from alert_manager import Alert, AlertChannel

logger = logging.getLogger(__name__)


@dataclass
class NotificationConfig:
    """Configuration for notification channels"""
    
    # Email
    email_enabled: bool = False
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    email_to: List[str] = field(default_factory=list)
    
    # SMS (Twilio)
    sms_enabled: bool = False
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from: str = ""
    sms_to: List[str] = field(default_factory=list)
    
    # Telegram
    telegram_enabled: bool = False
    telegram_bot_token: str = ""
    telegram_chat_ids: List[str] = field(default_factory=list)
    
    # Discord
    discord_enabled: bool = False
    discord_webhook_urls: List[str] = field(default_factory=list)
    
    # Slack
    slack_enabled: bool = False
    slack_webhook_urls: List[str] = field(default_factory=list)
    slack_bot_token: str = ""
    slack_channel_ids: List[str] = field(default_factory=list)
    
    # Generic Webhooks
    webhook_enabled: bool = False
    webhook_urls: List[str] = field(default_factory=list)
    webhook_headers: Dict[str, str] = field(default_factory=dict)
    
    # Retry configuration
    max_retries: int = 3
    retry_delay_seconds: int = 5
    
    # Delivery options
    parallel_delivery: bool = True  # Send to all channels in parallel
    fail_fast: bool = False  # Stop on first failure (if False, try all channels)
    
    @classmethod
    def from_env(cls) -> 'NotificationConfig':
        """Load configuration from environment variables"""
        return cls(
            # Email
            email_enabled=os.getenv('EMAIL_NOTIFICATIONS_ENABLED', 'false').lower() == 'true',
            smtp_host=os.getenv('SMTP_HOST', ''),
            smtp_port=int(os.getenv('SMTP_PORT', '587')),
            smtp_username=os.getenv('SMTP_USERNAME', ''),
            smtp_password=os.getenv('SMTP_PASSWORD', ''),
            smtp_from=os.getenv('SMTP_FROM_EMAIL', ''),
            email_to=os.getenv('EMAIL_TO', '').split(',') if os.getenv('EMAIL_TO') else [],
            
            # SMS
            sms_enabled=os.getenv('SMS_NOTIFICATIONS_ENABLED', 'false').lower() == 'true',
            twilio_account_sid=os.getenv('TWILIO_ACCOUNT_SID', ''),
            twilio_auth_token=os.getenv('TWILIO_AUTH_TOKEN', ''),
            twilio_from=os.getenv('TWILIO_FROM_NUMBER', ''),
            sms_to=os.getenv('SMS_TO', '').split(',') if os.getenv('SMS_TO') else [],
            
            # Telegram
            telegram_enabled=os.getenv('TELEGRAM_NOTIFICATIONS_ENABLED', 'false').lower() == 'true',
            telegram_bot_token=os.getenv('TELEGRAM_BOT_TOKEN', ''),
            telegram_chat_ids=os.getenv('TELEGRAM_CHAT_IDS', '').split(',') if os.getenv('TELEGRAM_CHAT_IDS') else [],
            
            # Discord
            discord_enabled=os.getenv('DISCORD_NOTIFICATIONS_ENABLED', 'false').lower() == 'true',
            discord_webhook_urls=os.getenv('DISCORD_WEBHOOK_URLS', '').split(',') if os.getenv('DISCORD_WEBHOOK_URLS') else [],
            
            # Slack
            slack_enabled=os.getenv('SLACK_NOTIFICATIONS_ENABLED', 'false').lower() == 'true',
            slack_webhook_urls=os.getenv('SLACK_WEBHOOK_URLS', '').split(',') if os.getenv('SLACK_WEBHOOK_URLS') else [],
            slack_bot_token=os.getenv('SLACK_BOT_TOKEN', ''),
            slack_channel_ids=os.getenv('SLACK_CHANNEL_IDS', '').split(',') if os.getenv('SLACK_CHANNEL_IDS') else [],
            
            # Webhooks
            webhook_enabled=os.getenv('WEBHOOK_NOTIFICATIONS_ENABLED', 'false').lower() == 'true',
            webhook_urls=os.getenv('WEBHOOK_URLS', '').split(',') if os.getenv('WEBHOOK_URLS') else [],
            
            # Retry
            max_retries=int(os.getenv('NOTIFICATION_MAX_RETRIES', '3')),
            retry_delay_seconds=int(os.getenv('NOTIFICATION_RETRY_DELAY', '5')),
            
            # Options
            parallel_delivery=os.getenv('NOTIFICATION_PARALLEL_DELIVERY', 'true').lower() == 'true',
            fail_fast=os.getenv('NOTIFICATION_FAIL_FAST', 'false').lower() == 'true',
        )


@dataclass
class DeliveryReport:
    """Report of notification delivery across channels"""
    alert_id: str
    total_channels: int
    successful_channels: int
    failed_channels: int
    results: Dict[str, NotificationResult] = field(default_factory=dict)
    delivered_at: datetime = field(default_factory=datetime.utcnow)
    
    @property
    def success_rate(self) -> float:
        """Calculate delivery success rate"""
        if self.total_channels == 0:
            return 0.0
        return (self.successful_channels / self.total_channels) * 100
    
    @property
    def is_successful(self) -> bool:
        """Check if delivery was successful (at least one channel)"""
        return self.successful_channels > 0
    
    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "alert_id": self.alert_id,
            "total_channels": self.total_channels,
            "successful_channels": self.successful_channels,
            "failed_channels": self.failed_channels,
            "success_rate": self.success_rate,
            "is_successful": self.is_successful,
            "delivered_at": self.delivered_at.isoformat(),
            "results": {
                channel: {
                    "success": result.success,
                    "error": result.error,
                    "timestamp": result.timestamp.isoformat(),
                }
                for channel, result in self.results.items()
            }
        }


class NotificationService:
    """
    Multi-channel notification delivery service.
    
    Manages:
    - Channel initialization from configuration
    - Notification routing based on alert channels
    - Retry logic for failed deliveries
    - Delivery tracking and reporting
    - Channel health monitoring
    """
    
    def __init__(self, config: Optional[NotificationConfig] = None):
        """
        Initialize notification service.
        
        Args:
            config: Notification configuration (loads from env if not provided)
        """
        self.config = config or NotificationConfig.from_env()
        self.channels: Dict[str, NotificationChannel] = {}
        self.delivery_history: List[DeliveryReport] = []
        
        # Statistics
        self.total_alerts_sent = 0
        self.total_deliveries_attempted = 0
        self.total_deliveries_successful = 0
        self.total_deliveries_failed = 0
        
        # Initialize channels
        self._initialize_channels()
        
        logger.info(f"NotificationService initialized with {len(self.channels)} channels")
    
    def _initialize_channels(self):
        """Initialize notification channels based on configuration"""
        
        # Email
        if self.config.email_enabled and self.config.email_to:
            try:
                self.channels['email'] = EmailNotificationChannel(
                    smtp_host=self.config.smtp_host,
                    smtp_port=self.config.smtp_port,
                    username=self.config.smtp_username,
                    password=self.config.smtp_password,
                    from_address=self.config.smtp_from,
                    to_addresses=self.config.email_to,
                )
                logger.info(f"Email channel initialized: {len(self.config.email_to)} recipients")
            except Exception as e:
                logger.error(f"Failed to initialize email channel: {e}")
        
        # SMS
        if self.config.sms_enabled and self.config.sms_to:
            try:
                self.channels['sms'] = SMSNotificationChannel(
                    account_sid=self.config.twilio_account_sid,
                    auth_token=self.config.twilio_auth_token,
                    from_number=self.config.twilio_from,
                    to_numbers=self.config.sms_to,
                )
                logger.info(f"SMS channel initialized: {len(self.config.sms_to)} recipients")
            except Exception as e:
                logger.error(f"Failed to initialize SMS channel: {e}")
        
        # Telegram
        if self.config.telegram_enabled and self.config.telegram_chat_ids:
            try:
                self.channels['telegram'] = TelegramNotificationChannel(
                    bot_token=self.config.telegram_bot_token,
                    chat_ids=self.config.telegram_chat_ids,
                )
                logger.info(f"Telegram channel initialized: {len(self.config.telegram_chat_ids)} chats")
            except Exception as e:
                logger.error(f"Failed to initialize Telegram channel: {e}")
        
        # Discord
        if self.config.discord_enabled and self.config.discord_webhook_urls:
            try:
                self.channels['discord'] = DiscordNotificationChannel(
                    webhook_urls=self.config.discord_webhook_urls,
                )
                logger.info(f"Discord channel initialized: {len(self.config.discord_webhook_urls)} webhooks")
            except Exception as e:
                logger.error(f"Failed to initialize Discord channel: {e}")
        
        # Slack
        if self.config.slack_enabled:
            try:
                self.channels['slack'] = SlackNotificationChannel(
                    webhook_urls=self.config.slack_webhook_urls if self.config.slack_webhook_urls else None,
                    bot_token=self.config.slack_bot_token if self.config.slack_bot_token else None,
                    channel_ids=self.config.slack_channel_ids if self.config.slack_channel_ids else None,
                )
                logger.info(f"Slack channel initialized")
            except Exception as e:
                logger.error(f"Failed to initialize Slack channel: {e}")
        
        # Generic Webhooks
        if self.config.webhook_enabled and self.config.webhook_urls:
            try:
                self.channels['webhook'] = WebhookNotificationChannel(
                    webhook_urls=self.config.webhook_urls,
                    headers=self.config.webhook_headers,
                )
                logger.info(f"Webhook channel initialized: {len(self.config.webhook_urls)} endpoints")
            except Exception as e:
                logger.error(f"Failed to initialize webhook channel: {e}")
    
    def send_notification(self, alert: Alert) -> DeliveryReport:
        """
        Send notification for an alert.
        
        Args:
            alert: Alert to send
            
        Returns:
            DeliveryReport: Delivery status for all channels
        """
        self.total_alerts_sent += 1
        
        # Determine which channels to use
        target_channels = self._get_target_channels(alert)
        
        if not target_channels:
            logger.warning(f"No target channels for alert {alert.alert_id}")
            return DeliveryReport(
                alert_id=alert.alert_id,
                total_channels=0,
                successful_channels=0,
                failed_channels=0,
            )
        
        logger.info(f"Sending alert {alert.alert_id} to {len(target_channels)} channels: {list(target_channels.keys())}")
        
        # Send to channels
        if self.config.parallel_delivery:
            results = self._send_parallel(alert, target_channels)
        else:
            results = self._send_sequential(alert, target_channels)
        
        # Create delivery report
        successful = sum(1 for r in results.values() if r.success)
        failed = len(results) - successful
        
        self.total_deliveries_attempted += len(results)
        self.total_deliveries_successful += successful
        self.total_deliveries_failed += failed
        
        report = DeliveryReport(
            alert_id=alert.alert_id,
            total_channels=len(results),
            successful_channels=successful,
            failed_channels=failed,
            results=results,
        )
        
        self.delivery_history.append(report)
        
        # Update alert delivery status
        for channel_name, result in results.items():
            channel_enum = self._channel_name_to_enum(channel_name)
            if channel_enum:
                alert.mark_sent(channel_enum, result.success)
        
        logger.info(
            f"Alert {alert.alert_id} delivery complete: "
            f"{successful}/{len(results)} successful ({report.success_rate:.1f}%)"
        )
        
        return report
    
    def _get_target_channels(self, alert: Alert) -> Dict[str, NotificationChannel]:
        """Determine which channels to send alert to"""
        target_channels = {}
        
        # If alert specifies channels, use those
        if alert.channels:
            for alert_channel in alert.channels:
                channel_name = alert_channel.value
                if channel_name in self.channels:
                    target_channels[channel_name] = self.channels[channel_name]
        else:
            # Otherwise, use all available channels
            target_channels = self.channels.copy()
        
        return target_channels
    
    def _send_parallel(
        self, 
        alert: Alert, 
        channels: Dict[str, NotificationChannel]
    ) -> Dict[str, NotificationResult]:
        """Send notification to all channels in parallel"""
        results = {}
        
        # Use concurrent execution for parallel sends
        import concurrent.futures
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(channels)) as executor:
            future_to_channel = {
                executor.submit(self._send_with_retry, channel, alert): channel_name
                for channel_name, channel in channels.items()
            }
            
            for future in concurrent.futures.as_completed(future_to_channel):
                channel_name = future_to_channel[future]
                try:
                    result = future.result()
                    results[channel_name] = result
                    
                    if not result.success and self.config.fail_fast:
                        logger.warning(f"Fail-fast enabled, stopping after {channel_name} failure")
                        # Cancel remaining futures
                        for f in future_to_channel:
                            f.cancel()
                        break
                except Exception as e:
                    logger.error(f"Exception sending to {channel_name}: {e}")
                    results[channel_name] = NotificationResult(
                        success=False,
                        channel=channel_name,
                        timestamp=datetime.utcnow(),
                        error=str(e),
                    )
        
        return results
    
    def _send_sequential(
        self, 
        alert: Alert, 
        channels: Dict[str, NotificationChannel]
    ) -> Dict[str, NotificationResult]:
        """Send notification to channels sequentially"""
        results = {}
        
        for channel_name, channel in channels.items():
            result = self._send_with_retry(channel, alert)
            results[channel_name] = result
            
            if not result.success and self.config.fail_fast:
                logger.warning(f"Fail-fast enabled, stopping after {channel_name} failure")
                break
        
        return results
    
    def _send_with_retry(
        self, 
        channel: NotificationChannel, 
        alert: Alert
    ) -> NotificationResult:
        """Send notification with retry logic"""
        import time
        
        for attempt in range(self.config.max_retries):
            try:
                result = channel.send(alert)
                
                if result.success:
                    return result
                
                # Retry on failure
                if attempt < self.config.max_retries - 1:
                    logger.warning(
                        f"Retry {attempt + 1}/{self.config.max_retries} for {channel.name} "
                        f"after {self.config.retry_delay_seconds}s"
                    )
                    time.sleep(self.config.retry_delay_seconds)
                else:
                    logger.error(f"All retries exhausted for {channel.name}")
                    return result
            
            except Exception as e:
                logger.error(f"Exception on attempt {attempt + 1} for {channel.name}: {e}")
                if attempt < self.config.max_retries - 1:
                    time.sleep(self.config.retry_delay_seconds)
                else:
                    return NotificationResult(
                        success=False,
                        channel=channel.name,
                        timestamp=datetime.utcnow(),
                        error=str(e),
                    )
        
        # Should not reach here
        return NotificationResult(
            success=False,
            channel=channel.name,
            timestamp=datetime.utcnow(),
            error="Max retries reached",
        )
    
    def _channel_name_to_enum(self, channel_name: str) -> Optional[AlertChannel]:
        """Convert channel name to AlertChannel enum"""
        mapping = {
            'email': AlertChannel.EMAIL,
            'sms': AlertChannel.SMS,
            'telegram': AlertChannel.TELEGRAM,
            'discord': AlertChannel.DISCORD,
            'slack': AlertChannel.WEBHOOK,  # Slack uses webhook under the hood
            'webhook': AlertChannel.WEBHOOK,
        }
        return mapping.get(channel_name)
    
    def get_channel_health(self) -> Dict[str, dict]:
        """Get health status of all channels"""
        health = {}
        
        for name, channel in self.channels.items():
            health[name] = {
                "enabled": channel.enabled,
                "sent_count": channel.sent_count,
                "error_count": channel.error_count,
                "success_rate": (
                    (channel.sent_count / (channel.sent_count + channel.error_count) * 100)
                    if (channel.sent_count + channel.error_count) > 0 else 0.0
                ),
            }
        
        return health
    
    def get_statistics(self) -> dict:
        """Get service statistics"""
        return {
            "total_alerts_sent": self.total_alerts_sent,
            "total_deliveries_attempted": self.total_deliveries_attempted,
            "total_deliveries_successful": self.total_deliveries_successful,
            "total_deliveries_failed": self.total_deliveries_failed,
            "overall_success_rate": (
                (self.total_deliveries_successful / self.total_deliveries_attempted * 100)
                if self.total_deliveries_attempted > 0 else 0.0
            ),
            "active_channels": len(self.channels),
            "channel_health": self.get_channel_health(),
        }
    
    def get_recent_deliveries(self, limit: int = 10) -> List[DeliveryReport]:
        """Get recent delivery reports"""
        return self.delivery_history[-limit:]
    
    def test_channel(self, channel_name: str) -> NotificationResult:
        """Test a specific channel with a test alert"""
        if channel_name not in self.channels:
            return NotificationResult(
                success=False,
                channel=channel_name,
                timestamp=datetime.utcnow(),
                error=f"Channel '{channel_name}' not configured",
            )
        
        # Create test alert
        from alert_manager import AlertType, AlertPriority
        
        test_alert = Alert(
            alert_id="test_" + datetime.utcnow().strftime("%Y%m%d_%H%M%S"),
            alert_type=AlertType.CUSTOM,
            priority=AlertPriority.INFO,
            title="Test Notification",
            message="This is a test notification from MasterTrade Alert System.",
            data={"test": True, "timestamp": datetime.utcnow().isoformat()},
        )
        
        channel = self.channels[channel_name]
        return channel.send(test_alert)
