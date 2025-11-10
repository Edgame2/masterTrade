"""
Notification Channels

Multi-channel notification delivery system supporting:
- Email (SMTP)
- SMS (Twilio)
- Telegram
- Discord
- Webhooks
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Dict, Any
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class NotificationResult:
    """Result of a notification attempt"""
    success: bool
    channel: str
    timestamp: datetime
    message_id: Optional[str] = None
    error: Optional[str] = None


class NotificationChannel(ABC):
    """Base class for notification channels"""
    
    def __init__(self, name: str):
        self.name = name
        self.enabled = True
        self.sent_count = 0
        self.error_count = 0
    
    @abstractmethod
    def send(self, alert: 'Alert') -> NotificationResult:
        """
        Send notification.
        
        Args:
            alert: Alert to send
            
        Returns:
            NotificationResult: Delivery result
        """
        pass
    
    def _format_message(self, alert: 'Alert') -> Dict[str, str]:
        """
        Format alert for delivery.
        
        Returns:
            Dict with 'subject' and 'body'
        """
        # Priority emoji
        priority_emoji = {
            1: "🔴",  # CRITICAL
            2: "🟠",  # HIGH
            3: "🟡",  # MEDIUM
            4: "🟢",  # LOW
            5: "ℹ️",   # INFO
        }
        
        emoji = priority_emoji.get(alert.priority.value, "")
        
        subject = f"{emoji} {alert.title}"
        
        body = f"""
{alert.message}

Priority: {alert.priority.name}
Type: {alert.alert_type.name}
Time: {alert.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}
"""
        
        if alert.symbol:
            body += f"Symbol: {alert.symbol}\n"
        
        if alert.strategy_id:
            body += f"Strategy: {alert.strategy_id}\n"
        
        if alert.position_id:
            body += f"Position: {alert.position_id}\n"
        
        if alert.data:
            body += "\nDetails:\n"
            for key, value in alert.data.items():
                body += f"  {key}: {value}\n"
        
        body += f"\nAlert ID: {alert.alert_id}\n"
        
        return {"subject": subject, "body": body}


class EmailNotificationChannel(NotificationChannel):
    """
    Email notification via SMTP.
    
    Requires SMTP configuration:
    - SMTP server (smtp.gmail.com)
    - Port (587 for TLS)
    - Username/password
    - From address
    - To addresses
    """
    
    def __init__(
        self,
        smtp_host: str,
        smtp_port: int,
        username: str,
        password: str,
        from_address: str,
        to_addresses: list[str],
        use_tls: bool = True,
    ):
        super().__init__("email")
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.username = username
        self.password = password
        self.from_address = from_address
        self.to_addresses = to_addresses
        self.use_tls = use_tls
    
    def send(self, alert: 'Alert') -> NotificationResult:
        """Send email notification"""
        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
            
            message = self._format_message(alert)
            
            # Create email
            msg = MIMEMultipart()
            msg['From'] = self.from_address
            msg['To'] = ", ".join(self.to_addresses)
            msg['Subject'] = message['subject']
            
            # HTML body
            html_body = f"""
            <html>
            <body>
                <h2 style="color: #333;">{alert.title}</h2>
                <p><strong>Priority:</strong> {alert.priority.name}</p>
                <p><strong>Type:</strong> {alert.alert_type.name}</p>
                <p><strong>Time:</strong> {alert.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}</p>
                <hr>
                <pre>{alert.message}</pre>
            """
            
            if alert.symbol:
                html_body += f"<p><strong>Symbol:</strong> {alert.symbol}</p>"
            
            if alert.data:
                html_body += "<h3>Details:</h3><ul>"
                for key, value in alert.data.items():
                    html_body += f"<li><strong>{key}:</strong> {value}</li>"
                html_body += "</ul>"
            
            html_body += f"""
                <hr>
                <p style="color: #666; font-size: 12px;">Alert ID: {alert.alert_id}</p>
            </body>
            </html>
            """
            
            msg.attach(MIMEText(html_body, 'html'))
            
            # Send
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                if self.use_tls:
                    server.starttls()
                server.login(self.username, self.password)
                server.send_message(msg)
            
            self.sent_count += 1
            logger.info(f"Email sent to {len(self.to_addresses)} recipients: {alert.alert_id}")
            
            return NotificationResult(
                success=True,
                channel="email",
                timestamp=datetime.utcnow(),
                message_id=alert.alert_id,
            )
            
        except Exception as e:
            self.error_count += 1
            logger.error(f"Failed to send email: {e}")
            return NotificationResult(
                success=False,
                channel="email",
                timestamp=datetime.utcnow(),
                error=str(e),
            )


class SMSNotificationChannel(NotificationChannel):
    """
    SMS notification via Twilio.
    
    Requires Twilio credentials:
    - Account SID
    - Auth token
    - From phone number
    - To phone numbers
    """
    
    def __init__(
        self,
        account_sid: str,
        auth_token: str,
        from_number: str,
        to_numbers: list[str],
    ):
        super().__init__("sms")
        self.account_sid = account_sid
        self.auth_token = auth_token
        self.from_number = from_number
        self.to_numbers = to_numbers
        self.client = None
    
    def _init_client(self):
        """Initialize Twilio client lazily"""
        if self.client is None:
            try:
                from twilio.rest import Client
                self.client = Client(self.account_sid, self.auth_token)
            except ImportError:
                logger.error("Twilio library not installed. Install with: pip install twilio")
                raise
    
    def send(self, alert: 'Alert') -> NotificationResult:
        """Send SMS notification"""
        try:
            self._init_client()
            
            message = self._format_message(alert)
            
            # SMS is limited, keep it short
            sms_body = f"{message['subject']}\n\n{alert.message[:100]}"
            if len(alert.message) > 100:
                sms_body += "..."
            
            # Send to all numbers
            for to_number in self.to_numbers:
                self.client.messages.create(
                    body=sms_body,
                    from_=self.from_number,
                    to=to_number
                )
            
            self.sent_count += 1
            logger.info(f"SMS sent to {len(self.to_numbers)} recipients: {alert.alert_id}")
            
            return NotificationResult(
                success=True,
                channel="sms",
                timestamp=datetime.utcnow(),
                message_id=alert.alert_id,
            )
            
        except Exception as e:
            self.error_count += 1
            logger.error(f"Failed to send SMS: {e}")
            return NotificationResult(
                success=False,
                channel="sms",
                timestamp=datetime.utcnow(),
                error=str(e),
            )


class TelegramNotificationChannel(NotificationChannel):
    """
    Telegram notification via Bot API.
    
    Requires:
    - Bot token (from @BotFather)
    - Chat IDs (can be user IDs or group IDs)
    """
    
    def __init__(
        self,
        bot_token: str,
        chat_ids: list[str],
    ):
        super().__init__("telegram")
        self.bot_token = bot_token
        self.chat_ids = chat_ids
        self.api_url = f"https://api.telegram.org/bot{bot_token}"
    
    def send(self, alert: 'Alert') -> NotificationResult:
        """Send Telegram notification"""
        try:
            import requests
            
            message = self._format_message(alert)
            
            # Telegram supports Markdown
            telegram_message = f"""
*{message['subject']}*

{alert.message}

_Priority:_ {alert.priority.name}
_Type:_ {alert.alert_type.name}
_Time:_ {alert.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}
"""
            
            if alert.symbol:
                telegram_message += f"_Symbol:_ {alert.symbol}\n"
            
            if alert.data:
                telegram_message += "\n*Details:*\n"
                for key, value in alert.data.items():
                    telegram_message += f"• {key}: `{value}`\n"
            
            telegram_message += f"\n_Alert ID:_ `{alert.alert_id}`"
            
            # Send to all chats
            for chat_id in self.chat_ids:
                response = requests.post(
                    f"{self.api_url}/sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": telegram_message,
                        "parse_mode": "Markdown",
                    },
                    timeout=10,
                )
                response.raise_for_status()
            
            self.sent_count += 1
            logger.info(f"Telegram sent to {len(self.chat_ids)} chats: {alert.alert_id}")
            
            return NotificationResult(
                success=True,
                channel="telegram",
                timestamp=datetime.utcnow(),
                message_id=alert.alert_id,
            )
            
        except Exception as e:
            self.error_count += 1
            logger.error(f"Failed to send Telegram: {e}")
            return NotificationResult(
                success=False,
                channel="telegram",
                timestamp=datetime.utcnow(),
                error=str(e),
            )


class DiscordNotificationChannel(NotificationChannel):
    """
    Discord notification via Webhooks.
    
    Requires:
    - Webhook URLs (created in Discord channel settings)
    """
    
    def __init__(
        self,
        webhook_urls: list[str],
    ):
        super().__init__("discord")
        self.webhook_urls = webhook_urls
    
    def send(self, alert: 'Alert') -> NotificationResult:
        """Send Discord notification"""
        try:
            import requests
            
            message = self._format_message(alert)
            
            # Discord embed (rich formatting)
            color_map = {
                1: 0xFF0000,  # CRITICAL - Red
                2: 0xFF8800,  # HIGH - Orange
                3: 0xFFFF00,  # MEDIUM - Yellow
                4: 0x00FF00,  # LOW - Green
                5: 0x0088FF,  # INFO - Blue
            }
            
            embed = {
                "title": alert.title,
                "description": alert.message,
                "color": color_map.get(alert.priority.value, 0x808080),
                "timestamp": alert.created_at.isoformat(),
                "fields": [
                    {"name": "Priority", "value": alert.priority.name, "inline": True},
                    {"name": "Type", "value": alert.alert_type.name, "inline": True},
                ],
                "footer": {"text": f"Alert ID: {alert.alert_id}"},
            }
            
            if alert.symbol:
                embed["fields"].append({"name": "Symbol", "value": alert.symbol, "inline": True})
            
            if alert.strategy_id:
                embed["fields"].append({"name": "Strategy", "value": alert.strategy_id, "inline": True})
            
            if alert.data:
                for key, value in list(alert.data.items())[:5]:  # Limit to 5 fields
                    embed["fields"].append({"name": key, "value": str(value), "inline": True})
            
            payload = {
                "embeds": [embed],
            }
            
            # Send to all webhooks
            for webhook_url in self.webhook_urls:
                response = requests.post(
                    webhook_url,
                    json=payload,
                    timeout=10,
                )
                response.raise_for_status()
            
            self.sent_count += 1
            logger.info(f"Discord sent to {len(self.webhook_urls)} webhooks: {alert.alert_id}")
            
            return NotificationResult(
                success=True,
                channel="discord",
                timestamp=datetime.utcnow(),
                message_id=alert.alert_id,
            )
            
        except Exception as e:
            self.error_count += 1
            logger.error(f"Failed to send Discord: {e}")
            return NotificationResult(
                success=False,
                channel="discord",
                timestamp=datetime.utcnow(),
                error=str(e),
            )


class WebhookNotificationChannel(NotificationChannel):
    """
    Generic webhook notification.
    
    Sends alert data as JSON to configured endpoints.
    """
    
    def __init__(
        self,
        webhook_urls: list[str],
        headers: Optional[Dict[str, str]] = None,
    ):
        super().__init__("webhook")
        self.webhook_urls = webhook_urls
        self.headers = headers or {"Content-Type": "application/json"}
    
    def send(self, alert: 'Alert') -> NotificationResult:
        """Send webhook notification"""
        try:
            import requests
            
            # Send full alert as JSON
            payload = alert.to_dict()
            
            # Send to all webhooks
            for webhook_url in self.webhook_urls:
                response = requests.post(
                    webhook_url,
                    json=payload,
                    headers=self.headers,
                    timeout=10,
                )
                response.raise_for_status()
            
            self.sent_count += 1
            logger.info(f"Webhook sent to {len(self.webhook_urls)} endpoints: {alert.alert_id}")
            
            return NotificationResult(
                success=True,
                channel="webhook",
                timestamp=datetime.utcnow(),
                message_id=alert.alert_id,
            )
            
        except Exception as e:
            self.error_count += 1
            logger.error(f"Failed to send webhook: {e}")
            return NotificationResult(
                success=False,
                channel="webhook",
                timestamp=datetime.utcnow(),
                error=str(e),
            )
