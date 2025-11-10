"""
Email Sender

Email notification system for database alerts, reports, and system notifications
with support for HTML templates and attachment handling.
"""

import logging
import smtplib
import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, field
from enum import Enum
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path
import json

try:
    import aiosmtplib
    from jinja2 import Environment, FileSystemLoader, Template
    EMAIL_LIBS_AVAILABLE = True
except ImportError:
    EMAIL_LIBS_AVAILABLE = False
    logging.warning("Email libraries not available")

logger = logging.getLogger(__name__)


class EmailPriority(Enum):
    """Email priority levels"""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class EmailTemplate(Enum):
    """Built-in email templates"""
    PERFORMANCE_ALERT = "performance_alert"
    DATABASE_REPORT = "database_report"
    OPTIMIZATION_SUMMARY = "optimization_summary"
    SYSTEM_NOTIFICATION = "system_notification"


@dataclass
class EmailConfig:
    """Email server configuration"""
    smtp_host: str
    smtp_port: int = 587
    username: str = ""
    password: str = ""
    use_tls: bool = True
    use_ssl: bool = False
    timeout: int = 30
    
    def validate(self) -> bool:
        """Validate email configuration"""
        if not self.smtp_host:
            return False
        
        if self.smtp_port not in [25, 465, 587, 993, 995]:
            logger.warning(f"Unusual SMTP port: {self.smtp_port}")
        
        return True


@dataclass
class EmailAttachment:
    """Email attachment information"""
    filename: str
    content: bytes
    content_type: str = "application/octet-stream"
    
    @classmethod
    def from_file(cls, file_path: str, content_type: Optional[str] = None):
        """Create attachment from file"""
        path = Path(file_path)
        
        if not path.exists():
            raise FileNotFoundError(f"Attachment file not found: {file_path}")
        
        with open(path, 'rb') as f:
            content = f.read()
        
        # Guess content type if not provided
        if content_type is None:
            extension = path.suffix.lower()
            content_type_map = {
                '.pdf': 'application/pdf',
                '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                '.csv': 'text/csv',
                '.json': 'application/json',
                '.txt': 'text/plain',
                '.html': 'text/html',
                '.png': 'image/png',
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg'
            }
            content_type = content_type_map.get(extension, "application/octet-stream")
        
        return cls(
            filename=path.name,
            content=content,
            content_type=content_type
        )


@dataclass
class EmailMessage:
    """Email message container"""
    to_addresses: List[str]
    subject: str
    body: str
    from_address: Optional[str] = None
    cc_addresses: List[str] = field(default_factory=list)
    bcc_addresses: List[str] = field(default_factory=list)
    reply_to: Optional[str] = None
    priority: EmailPriority = EmailPriority.NORMAL
    is_html: bool = False
    attachments: List[EmailAttachment] = field(default_factory=list)
    headers: Dict[str, str] = field(default_factory=dict)
    template_data: Dict[str, Any] = field(default_factory=dict)
    
    def add_attachment(self, attachment: EmailAttachment):
        """Add attachment to email"""
        self.attachments.append(attachment)
    
    def add_file_attachment(self, file_path: str, content_type: Optional[str] = None):
        """Add file as attachment"""
        attachment = EmailAttachment.from_file(file_path, content_type)
        self.add_attachment(attachment)
    
    def validate(self) -> bool:
        """Validate email message"""
        if not self.to_addresses:
            return False
        
        if not self.subject or not self.body:
            return False
        
        # Validate email addresses (basic check)
        all_addresses = self.to_addresses + self.cc_addresses + self.bcc_addresses
        if self.from_address:
            all_addresses.append(self.from_address)
        if self.reply_to:
            all_addresses.append(self.reply_to)
        
        for addr in all_addresses:
            if '@' not in addr or '.' not in addr:
                logger.warning(f"Invalid email address: {addr}")
                return False
        
        return True


class EmailTemplateManager:
    """Email template management system"""
    
    def __init__(self, templates_dir: str = "email_templates"):
        self.templates_dir = Path(templates_dir)
        self.templates_dir.mkdir(exist_ok=True)
        
        self.jinja_env = None
        if EMAIL_LIBS_AVAILABLE:
            self.jinja_env = Environment(
                loader=FileSystemLoader(str(self.templates_dir)),
                autoescape=True
            )
        
        # Create built-in templates
        self._create_builtin_templates()
    
    def _create_builtin_templates(self):
        """Create built-in email templates"""
        
        templates = {
            EmailTemplate.PERFORMANCE_ALERT: {
                "subject": "⚠️ Database Performance Alert - {{ alert.severity|title }}",
                "body": """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .alert-critical { border-left: 5px solid #dc3545; background-color: #f8d7da; }
        .alert-warning { border-left: 5px solid #ffc107; background-color: #fff3cd; }
        .alert-info { border-left: 5px solid #17a2b8; background-color: #d1ecf1; }
        .alert-box { padding: 15px; margin: 10px 0; border-radius: 4px; }
        .metric-value { font-weight: bold; font-size: 1.2em; color: #dc3545; }
        .timestamp { color: #6c757d; font-size: 0.9em; }
    </style>
</head>
<body>
    <h2>Database Performance Alert</h2>
    
    <div class="alert-box alert-{{ alert.severity }}">
        <h3>{{ alert.message }}</h3>
        <p><strong>Severity:</strong> {{ alert.severity|title }}</p>
        <p><strong>Metric:</strong> {{ alert.metric_type|replace('_', ' ')|title }}</p>
        <p><strong>Current Value:</strong> <span class="metric-value">{{ alert.current_value }}</span></p>
        <p><strong>Threshold:</strong> {{ alert.threshold_value }}</p>
        <p class="timestamp"><strong>Time:</strong> {{ alert.timestamp }}</p>
    </div>
    
    {% if recent_metrics %}
    <h3>Recent Performance Metrics</h3>
    <ul>
        <li>CPU Usage: {{ recent_metrics.cpu_usage_percent }}%</li>
        <li>Memory Usage: {{ recent_metrics.memory_usage_percent }}%</li>
        <li>Active Connections: {{ recent_metrics.connection_count }}</li>
        <li>Cache Hit Ratio: {{ recent_metrics.buffer_cache_hit_ratio }}%</li>
    </ul>
    {% endif %}
    
    <p><em>This is an automated alert from the MasterTrade Database Monitoring System.</em></p>
</body>
</html>
                """
            },
            
            EmailTemplate.DATABASE_REPORT: {
                "subject": "📊 Database Performance Report - {{ report_date }}",
                "body": """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .summary-box { background-color: #f8f9fa; padding: 15px; border-radius: 8px; margin: 10px 0; }
        .metric-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; }
        .metric-card { background: white; padding: 15px; border: 1px solid #dee2e6; border-radius: 6px; }
        .metric-value { font-size: 1.5em; font-weight: bold; color: #28a745; }
        .metric-label { color: #6c757d; font-size: 0.9em; }
        .health-score { font-size: 2em; font-weight: bold; }
        .health-excellent { color: #28a745; }
        .health-good { color: #ffc107; }
        .health-poor { color: #dc3545; }
    </style>
</head>
<body>
    <h1>Database Performance Report</h1>
    <p><strong>Period:</strong> {{ report_date }}</p>
    
    <div class="summary-box">
        <h2>Overall Health Score</h2>
        <div class="health-score {% if health_score >= 80 %}health-excellent{% elif health_score >= 60 %}health-good{% else %}health-poor{% endif %}">
            {{ "%.1f"|format(health_score) }}/100
        </div>
    </div>
    
    <h2>Key Metrics</h2>
    <div class="metric-grid">
        {% if metrics %}
        <div class="metric-card">
            <div class="metric-value">{{ "%.1f"|format(metrics.avg_cpu_usage) }}%</div>
            <div class="metric-label">Average CPU Usage</div>
        </div>
        
        <div class="metric-card">
            <div class="metric-value">{{ "%.1f"|format(metrics.avg_memory_usage) }}%</div>
            <div class="metric-label">Average Memory Usage</div>
        </div>
        
        <div class="metric-card">
            <div class="metric-value">{{ metrics.avg_connections|int }}</div>
            <div class="metric-label">Average Connections</div>
        </div>
        
        <div class="metric-card">
            <div class="metric-value">{{ "%.1f"|format(metrics.cache_hit_ratio) }}%</div>
            <div class="metric-label">Cache Hit Ratio</div>
        </div>
        {% endif %}
    </div>
    
    {% if alerts_summary %}
    <h2>Alerts Summary</h2>
    <ul>
        <li>Total Alerts: {{ alerts_summary.total }}</li>
        <li>Critical: {{ alerts_summary.critical }}</li>
        <li>Warning: {{ alerts_summary.warning }}</li>
    </ul>
    {% endif %}
    
    {% if slow_queries %}
    <h2>Top Slow Query Patterns</h2>
    <ol>
    {% for query in slow_queries[:5] %}
        <li>{{ query.pattern[:100] }}... ({{ query.frequency }} occurrences, avg {{ "%.0f"|format(query.avg_duration_ms) }}ms)</li>
    {% endfor %}
    </ol>
    {% endif %}
    
    <p><em>Generated by MasterTrade Database Optimization System</em></p>
</body>
</html>
                """
            },
            
            EmailTemplate.OPTIMIZATION_SUMMARY: {
                "subject": "🔧 Database Optimization Summary - {{ optimization_date }}",
                "body": """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .success-box { background-color: #d4edda; border: 1px solid #c3e6cb; padding: 15px; border-radius: 4px; }
        .info-box { background-color: #d1ecf1; border: 1px solid #bee5eb; padding: 15px; border-radius: 4px; }
        .optimization-item { margin: 10px 0; padding: 10px; background-color: #f8f9fa; border-radius: 4px; }
    </style>
</head>
<body>
    <h1>Database Optimization Summary</h1>
    <p><strong>Date:</strong> {{ optimization_date }}</p>
    
    {% if optimizations_performed %}
    <div class="success-box">
        <h2>✅ Optimizations Performed</h2>
        <p>{{ optimizations_performed|length }} optimization(s) completed successfully.</p>
    </div>
    
    {% for optimization in optimizations_performed %}
    <div class="optimization-item">
        <h3>{{ optimization.type|title }}</h3>
        <p><strong>Description:</strong> {{ optimization.description }}</p>
        <p><strong>Estimated Benefit:</strong> {{ optimization.estimated_benefit }}</p>
        {% if optimization.execution_time %}
        <p><strong>Execution Time:</strong> {{ optimization.execution_time }}ms</p>
        {% endif %}
    </div>
    {% endfor %}
    {% endif %}
    
    {% if recommendations %}
    <div class="info-box">
        <h2>💡 Additional Recommendations</h2>
        <ul>
        {% for rec in recommendations %}
            <li>{{ rec.description }} (Priority: {{ rec.priority }})</li>
        {% endfor %}
        </ul>
    </div>
    {% endif %}
    
    <p><em>Generated by MasterTrade Database Optimization System</em></p>
</body>
</html>
                """
            }
        }
        
        # Save templates to files
        for template_type, template_data in templates.items():
            self._save_template(template_type, template_data)
    
    def _save_template(self, template_type: EmailTemplate, template_data: Dict[str, str]):
        """Save template to file"""
        
        template_file = self.templates_dir / f"{template_type.value}.html"
        
        try:
            with open(template_file, 'w', encoding='utf-8') as f:
                f.write(template_data["body"])
            
            # Save subject template separately
            subject_file = self.templates_dir / f"{template_type.value}_subject.txt"
            with open(subject_file, 'w', encoding='utf-8') as f:
                f.write(template_data["subject"])
        
        except Exception as e:
            logger.error(f"Failed to save template {template_type.value}: {e}")
    
    def render_template(self, template_type: EmailTemplate, data: Dict[str, Any]) -> tuple[str, str]:
        """Render email template with data"""
        
        if not self.jinja_env:
            return "Template Error", "Template rendering not available"
        
        try:
            # Render body
            body_template = self.jinja_env.get_template(f"{template_type.value}.html")
            body = body_template.render(**data)
            
            # Render subject
            subject_file = self.templates_dir / f"{template_type.value}_subject.txt"
            if subject_file.exists():
                with open(subject_file, 'r', encoding='utf-8') as f:
                    subject_template_str = f.read()
                
                subject_template = Template(subject_template_str)
                subject = subject_template.render(**data)
            else:
                subject = f"Notification - {template_type.value}"
            
            return subject, body
        
        except Exception as e:
            logger.error(f"Failed to render template {template_type.value}: {e}")
            return "Template Error", f"Failed to render template: {e}"


class EmailSender:
    """
    Email notification system for database monitoring and reporting
    
    Provides email sending capabilities with template support,
    attachment handling, and delivery tracking.
    """
    
    def __init__(self, email_config: EmailConfig, templates_dir: str = "email_templates"):
        self.config = email_config
        self.template_manager = EmailTemplateManager(templates_dir)
        
        # Delivery tracking
        self.sent_emails: List[Dict[str, Any]] = []
        self.failed_emails: List[Dict[str, Any]] = []
        
        # Rate limiting (simple)
        self.last_send_time: Optional[datetime] = None
        self.min_send_interval_seconds = 60  # Minimum 1 minute between sends
        
    async def send_email(self, message: EmailMessage) -> bool:
        """Send email message"""
        
        if not EMAIL_LIBS_AVAILABLE:
            logger.error("Email libraries not available")
            return False
        
        if not self.config.validate():
            logger.error("Invalid email configuration")
            return False
        
        if not message.validate():
            logger.error("Invalid email message")
            return False
        
        # Rate limiting check
        if self._is_rate_limited():
            logger.warning("Email rate limited")
            return False
        
        try:
            # Create MIME message
            mime_message = self._create_mime_message(message)
            
            # Send via SMTP
            if await self._send_via_smtp(mime_message, message):
                self._record_sent_email(message)
                self.last_send_time = datetime.utcnow()
                return True
            else:
                self._record_failed_email(message, "SMTP delivery failed")
                return False
        
        except Exception as e:
            logger.error(f"Email sending failed: {e}")
            self._record_failed_email(message, str(e))
            return False
    
    async def send_performance_alert(self, alert_data: Dict[str, Any], recipients: List[str]) -> bool:
        """Send performance alert email"""
        
        subject, body = self.template_manager.render_template(
            EmailTemplate.PERFORMANCE_ALERT,
            alert_data
        )
        
        message = EmailMessage(
            to_addresses=recipients,
            subject=subject,
            body=body,
            is_html=True,
            priority=EmailPriority.HIGH if alert_data.get('alert', {}).get('severity') == 'critical' else EmailPriority.NORMAL
        )
        
        return await self.send_email(message)
    
    async def send_database_report(self, report_data: Dict[str, Any], recipients: List[str]) -> bool:
        """Send database performance report"""
        
        subject, body = self.template_manager.render_template(
            EmailTemplate.DATABASE_REPORT,
            report_data
        )
        
        message = EmailMessage(
            to_addresses=recipients,
            subject=subject,
            body=body,
            is_html=True,
            priority=EmailPriority.NORMAL
        )
        
        # Add report attachments if available
        if 'attachments' in report_data:
            for attachment_path in report_data['attachments']:
                try:
                    message.add_file_attachment(attachment_path)
                except Exception as e:
                    logger.warning(f"Failed to add attachment {attachment_path}: {e}")
        
        return await self.send_email(message)
    
    async def send_optimization_summary(self, optimization_data: Dict[str, Any], recipients: List[str]) -> bool:
        """Send optimization summary email"""
        
        subject, body = self.template_manager.render_template(
            EmailTemplate.OPTIMIZATION_SUMMARY,
            optimization_data
        )
        
        message = EmailMessage(
            to_addresses=recipients,
            subject=subject,
            body=body,
            is_html=True,
            priority=EmailPriority.NORMAL
        )
        
        return await self.send_email(message)
    
    def _is_rate_limited(self) -> bool:
        """Check if sending is rate limited"""
        
        if not self.last_send_time:
            return False
        
        time_since_last = (datetime.utcnow() - self.last_send_time).total_seconds()
        return time_since_last < self.min_send_interval_seconds
    
    def _create_mime_message(self, message: EmailMessage) -> MIMEMultipart:
        """Create MIME message from EmailMessage"""
        
        mime_message = MIMEMultipart()
        
        # Set headers
        mime_message['To'] = ', '.join(message.to_addresses)
        mime_message['Subject'] = message.subject
        
        if message.from_address:
            mime_message['From'] = message.from_address
        
        if message.cc_addresses:
            mime_message['Cc'] = ', '.join(message.cc_addresses)
        
        if message.reply_to:
            mime_message['Reply-To'] = message.reply_to
        
        # Set priority
        if message.priority == EmailPriority.HIGH:
            mime_message['X-Priority'] = '2'
            mime_message['X-MSMail-Priority'] = 'High'
        elif message.priority == EmailPriority.URGENT:
            mime_message['X-Priority'] = '1'
            mime_message['X-MSMail-Priority'] = 'High'
        elif message.priority == EmailPriority.LOW:
            mime_message['X-Priority'] = '4'
            mime_message['X-MSMail-Priority'] = 'Low'
        
        # Add custom headers
        for key, value in message.headers.items():
            mime_message[key] = value
        
        # Add body
        body_type = 'html' if message.is_html else 'plain'
        body_part = MIMEText(message.body, body_type, 'utf-8')
        mime_message.attach(body_part)
        
        # Add attachments
        for attachment in message.attachments:
            if attachment.content_type.startswith('text/'):
                attach_part = MIMEText(attachment.content.decode('utf-8'))
            else:
                attach_part = MIMEBase('application', 'octet-stream')
                attach_part.set_payload(attachment.content)
                encoders.encode_base64(attach_part)
            
            attach_part.add_header(
                'Content-Disposition',
                f'attachment; filename={attachment.filename}'
            )
            
            mime_message.attach(attach_part)
        
        return mime_message
    
    async def _send_via_smtp(self, mime_message: MIMEMultipart, original_message: EmailMessage) -> bool:
        """Send message via SMTP"""
        
        try:
            # Collect all recipient addresses
            all_recipients = (
                original_message.to_addresses + 
                original_message.cc_addresses + 
                original_message.bcc_addresses
            )
            
            # Use aiosmtplib for async sending
            await aiosmtplib.send(
                mime_message,
                hostname=self.config.smtp_host,
                port=self.config.smtp_port,
                username=self.config.username or None,
                password=self.config.password or None,
                use_tls=self.config.use_tls,
                start_tls=self.config.use_tls and self.config.smtp_port != 465,
                timeout=self.config.timeout,
                recipients=all_recipients
            )
            
            logger.info(f"Email sent successfully to {len(all_recipients)} recipients")
            return True
        
        except Exception as e:
            logger.error(f"SMTP sending failed: {e}")
            return False
    
    def _record_sent_email(self, message: EmailMessage):
        """Record successfully sent email"""
        
        record = {
            "timestamp": datetime.utcnow().isoformat(),
            "to_addresses": message.to_addresses,
            "subject": message.subject,
            "priority": message.priority.value,
            "attachments_count": len(message.attachments)
        }
        
        self.sent_emails.append(record)
        
        # Keep only last 1000 records
        if len(self.sent_emails) > 1000:
            self.sent_emails = self.sent_emails[-1000:]
    
    def _record_failed_email(self, message: EmailMessage, error: str):
        """Record failed email attempt"""
        
        record = {
            "timestamp": datetime.utcnow().isoformat(),
            "to_addresses": message.to_addresses,
            "subject": message.subject,
            "error": error
        }
        
        self.failed_emails.append(record)
        
        # Keep only last 1000 records
        if len(self.failed_emails) > 1000:
            self.failed_emails = self.failed_emails[-1000:]
    
    def get_email_statistics(self) -> Dict[str, Any]:
        """Get email delivery statistics"""
        
        total_sent = len(self.sent_emails)
        total_failed = len(self.failed_emails)
        total_attempts = total_sent + total_failed
        
        success_rate = (total_sent / total_attempts * 100) if total_attempts > 0 else 0
        
        # Get recent statistics (last 24 hours)
        cutoff_time = datetime.utcnow() - timedelta(hours=24)
        
        recent_sent = [
            email for email in self.sent_emails
            if datetime.fromisoformat(email["timestamp"]) >= cutoff_time
        ]
        
        recent_failed = [
            email for email in self.failed_emails
            if datetime.fromisoformat(email["timestamp"]) >= cutoff_time
        ]
        
        return {
            "total": {
                "sent": total_sent,
                "failed": total_failed,
                "attempts": total_attempts,
                "success_rate_percent": success_rate
            },
            "recent_24h": {
                "sent": len(recent_sent),
                "failed": len(recent_failed),
                "success_rate_percent": (len(recent_sent) / (len(recent_sent) + len(recent_failed)) * 100) if (len(recent_sent) + len(recent_failed)) > 0 else 0
            },
            "configuration": {
                "smtp_host": self.config.smtp_host,
                "smtp_port": self.config.smtp_port,
                "use_tls": self.config.use_tls,
                "rate_limit_seconds": self.min_send_interval_seconds
            }
        }
    
    def get_recent_emails(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent email history"""
        
        # Combine sent and failed emails with status
        all_emails = []
        
        for email in self.sent_emails:
            email_copy = email.copy()
            email_copy["status"] = "sent"
            all_emails.append(email_copy)
        
        for email in self.failed_emails:
            email_copy = email.copy()
            email_copy["status"] = "failed"
            all_emails.append(email_copy)
        
        # Sort by timestamp (most recent first)
        all_emails.sort(key=lambda x: x["timestamp"], reverse=True)
        
        return all_emails[:limit]
    
    def test_connection(self) -> bool:
        """Test SMTP connection"""
        
        if not EMAIL_LIBS_AVAILABLE:
            return False
        
        try:
            # Use synchronous SMTP for testing
            if self.config.use_ssl:
                server = smtplib.SMTP_SSL(self.config.smtp_host, self.config.smtp_port, timeout=self.config.timeout)
            else:
                server = smtplib.SMTP(self.config.smtp_host, self.config.smtp_port, timeout=self.config.timeout)
                
                if self.config.use_tls:
                    server.starttls()
            
            if self.config.username and self.config.password:
                server.login(self.config.username, self.config.password)
            
            server.quit()
            
            logger.info("SMTP connection test successful")
            return True
        
        except Exception as e:
            logger.error(f"SMTP connection test failed: {e}")
            return False