"""
Report Scheduler

Automated scheduling and delivery system for generating and distributing reports
on predefined schedules with support for multiple delivery methods.
"""

import logging
import asyncio
import json
from datetime import datetime, timedelta, time
from typing import Dict, List, Optional, Any, Callable, Union
from dataclasses import dataclass, field
from enum import Enum
import schedule
import threading
from pathlib import Path

try:
    import croniter
    CRONITER_AVAILABLE = True
except ImportError:
    CRONITER_AVAILABLE = False
    logging.warning("croniter not available for advanced scheduling")

logger = logging.getLogger(__name__)


class ScheduleFrequency(Enum):
    """Schedule frequency options"""
    ONCE = "once"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"
    CUSTOM_CRON = "custom_cron"


class DeliveryMethod(Enum):
    """Report delivery methods"""
    EMAIL = "email"
    FILE_SYSTEM = "file_system"
    FTP = "ftp"
    SFTP = "sftp"
    S3 = "s3"
    API_WEBHOOK = "api_webhook"
    DATABASE = "database"


class ScheduleStatus(Enum):
    """Schedule status"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    PAUSED = "paused"
    ERROR = "error"
    COMPLETED = "completed"


@dataclass
class DeliveryConfig:
    """Delivery configuration for different methods"""
    method: DeliveryMethod
    config: Dict[str, Any] = field(default_factory=dict)
    
    def validate(self) -> bool:
        """Validate delivery configuration"""
        try:
            if self.method == DeliveryMethod.EMAIL:
                required = ["recipients", "smtp_host", "smtp_port"]
                return all(key in self.config for key in required)
            
            elif self.method == DeliveryMethod.FILE_SYSTEM:
                return "output_path" in self.config
            
            elif self.method == DeliveryMethod.FTP:
                required = ["host", "username", "password", "remote_path"]
                return all(key in self.config for key in required)
            
            elif self.method == DeliveryMethod.SFTP:
                required = ["host", "username", "remote_path"]
                return all(key in self.config for key in required)
            
            elif self.method == DeliveryMethod.S3:
                required = ["bucket", "key_prefix"]
                return all(key in self.config for key in required)
            
            elif self.method == DeliveryMethod.API_WEBHOOK:
                return "webhook_url" in self.config
            
            elif self.method == DeliveryMethod.DATABASE:
                required = ["connection_string", "table_name"]
                return all(key in self.config for key in required)
            
            return False
        
        except Exception as e:
            logger.error(f"Delivery config validation error: {e}")
            return False


@dataclass
class ScheduleConfig:
    """Schedule configuration"""
    frequency: ScheduleFrequency
    start_date: datetime
    end_date: Optional[datetime] = None
    time_of_day: Optional[time] = None
    day_of_week: Optional[int] = None  # 0=Monday, 6=Sunday
    day_of_month: Optional[int] = None
    cron_expression: Optional[str] = None
    timezone: str = "UTC"
    
    def validate(self) -> bool:
        """Validate schedule configuration"""
        try:
            if self.frequency == ScheduleFrequency.CUSTOM_CRON:
                if not self.cron_expression or not CRONITER_AVAILABLE:
                    return False
                # Validate cron expression
                croniter.croniter(self.cron_expression)
            
            if self.frequency == ScheduleFrequency.WEEKLY and self.day_of_week is None:
                return False
            
            if self.frequency == ScheduleFrequency.MONTHLY and self.day_of_month is None:
                return False
            
            if self.end_date and self.end_date <= self.start_date:
                return False
            
            return True
        
        except Exception as e:
            logger.error(f"Schedule config validation error: {e}")
            return False
    
    def get_next_run_time(self, from_time: Optional[datetime] = None) -> Optional[datetime]:
        """Calculate next run time"""
        try:
            base_time = from_time or datetime.utcnow()
            
            if self.frequency == ScheduleFrequency.ONCE:
                return self.start_date if self.start_date > base_time else None
            
            elif self.frequency == ScheduleFrequency.CUSTOM_CRON:
                if not CRONITER_AVAILABLE:
                    return None
                
                cron = croniter.croniter(self.cron_expression, base_time)
                next_run = cron.get_next(datetime)
                
                if self.end_date and next_run > self.end_date:
                    return None
                
                return next_run
            
            else:
                # Calculate based on frequency
                next_run = self._calculate_next_standard_run(base_time)
                
                if self.end_date and next_run and next_run > self.end_date:
                    return None
                
                return next_run
        
        except Exception as e:
            logger.error(f"Next run time calculation error: {e}")
            return None
    
    def _calculate_next_standard_run(self, from_time: datetime) -> Optional[datetime]:
        """Calculate next run for standard frequencies"""
        
        # Set time of day
        target_time = self.time_of_day or time(9, 0)  # Default 9 AM
        
        if self.frequency == ScheduleFrequency.DAILY:
            next_date = from_time.date()
            if from_time.time() >= target_time:
                next_date += timedelta(days=1)
            
            return datetime.combine(next_date, target_time)
        
        elif self.frequency == ScheduleFrequency.WEEKLY:
            if self.day_of_week is None:
                return None
            
            days_ahead = self.day_of_week - from_time.weekday()
            if days_ahead <= 0:  # Target day already happened this week
                days_ahead += 7
            
            next_date = from_time.date() + timedelta(days=days_ahead)
            return datetime.combine(next_date, target_time)
        
        elif self.frequency == ScheduleFrequency.MONTHLY:
            if self.day_of_month is None:
                return None
            
            # Try current month first
            try:
                next_date = from_time.replace(day=self.day_of_month)
                if next_date <= from_time:
                    # Move to next month
                    if from_time.month == 12:
                        next_date = next_date.replace(year=from_time.year + 1, month=1)
                    else:
                        next_date = next_date.replace(month=from_time.month + 1)
            except ValueError:
                # Day doesn't exist in month, move to next month
                if from_time.month == 12:
                    next_date = datetime(from_time.year + 1, 1, min(self.day_of_month, 28))
                else:
                    next_date = datetime(from_time.year, from_time.month + 1, min(self.day_of_month, 28))
            
            return datetime.combine(next_date.date(), target_time)
        
        elif self.frequency == ScheduleFrequency.QUARTERLY:
            # Find next quarter
            current_quarter = (from_time.month - 1) // 3 + 1
            next_quarter_month = (current_quarter % 4) * 3 + 1
            
            if next_quarter_month <= from_time.month:
                year = from_time.year + 1
            else:
                year = from_time.year
            
            next_date = datetime(year, next_quarter_month, self.day_of_month or 1)
            return datetime.combine(next_date.date(), target_time)
        
        elif self.frequency == ScheduleFrequency.YEARLY:
            next_year = from_time.year
            if from_time.month > 1 or (from_time.month == 1 and from_time.day > (self.day_of_month or 1)):
                next_year += 1
            
            next_date = datetime(next_year, 1, self.day_of_month or 1)
            return datetime.combine(next_date.date(), target_time)
        
        return None


@dataclass
class ReportExecution:
    """Report execution record"""
    execution_id: str
    schedule_id: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    status: str = "running"
    error_message: Optional[str] = None
    output_files: List[str] = field(default_factory=list)
    execution_time_seconds: Optional[float] = None
    context_used: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "execution_id": self.execution_id,
            "schedule_id": self.schedule_id,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "status": self.status,
            "error_message": self.error_message,
            "output_files": self.output_files,
            "execution_time_seconds": self.execution_time_seconds,
            "context_used": self.context_used
        }


@dataclass 
class ScheduledReport:
    """Scheduled report configuration"""
    schedule_id: str
    name: str
    description: str
    template_id: str
    schedule_config: ScheduleConfig
    delivery_configs: List[DeliveryConfig]
    context_generator: Optional[str] = None  # Function name or callable
    context_params: Dict[str, Any] = field(default_factory=dict)
    status: ScheduleStatus = ScheduleStatus.ACTIVE
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    last_execution: Optional[datetime] = None
    next_execution: Optional[datetime] = None
    execution_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "schedule_id": self.schedule_id,
            "name": self.name,
            "description": self.description,
            "template_id": self.template_id,
            "schedule_config": {
                "frequency": self.schedule_config.frequency.value,
                "start_date": self.schedule_config.start_date.isoformat(),
                "end_date": self.schedule_config.end_date.isoformat() if self.schedule_config.end_date else None,
                "time_of_day": self.schedule_config.time_of_day.isoformat() if self.schedule_config.time_of_day else None,
                "day_of_week": self.schedule_config.day_of_week,
                "day_of_month": self.schedule_config.day_of_month,
                "cron_expression": self.schedule_config.cron_expression,
                "timezone": self.schedule_config.timezone
            },
            "delivery_configs": [
                {
                    "method": config.method.value,
                    "config": config.config
                }
                for config in self.delivery_configs
            ],
            "context_generator": self.context_generator,
            "context_params": self.context_params,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "last_execution": self.last_execution.isoformat() if self.last_execution else None,
            "next_execution": self.next_execution.isoformat() if self.next_execution else None,
            "execution_count": self.execution_count,
            "metadata": self.metadata
        }


class ReportDelivery:
    """Report delivery handler"""
    
    def __init__(self):
        self.delivery_handlers: Dict[DeliveryMethod, Callable] = {
            DeliveryMethod.EMAIL: self._deliver_email,
            DeliveryMethod.FILE_SYSTEM: self._deliver_file_system,
            DeliveryMethod.FTP: self._deliver_ftp,
            DeliveryMethod.SFTP: self._deliver_sftp,
            DeliveryMethod.S3: self._deliver_s3,
            DeliveryMethod.API_WEBHOOK: self._deliver_webhook,
            DeliveryMethod.DATABASE: self._deliver_database
        }
    
    async def deliver_report(
        self,
        report_content: str,
        delivery_config: DeliveryConfig,
        report_metadata: Dict[str, Any]
    ) -> bool:
        """Deliver report using specified method"""
        
        try:
            handler = self.delivery_handlers.get(delivery_config.method)
            if not handler:
                logger.error(f"No handler for delivery method: {delivery_config.method}")
                return False
            
            return await handler(report_content, delivery_config.config, report_metadata)
        
        except Exception as e:
            logger.error(f"Report delivery failed: {e}")
            return False
    
    async def _deliver_email(self, content: str, config: Dict, metadata: Dict) -> bool:
        """Deliver report via email"""
        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
            from email.mime.application import MIMEApplication
            
            # Create message
            msg = MIMEMultipart()
            msg['From'] = config.get('sender', 'noreply@mastertrade.com')
            msg['To'] = ', '.join(config['recipients'])
            msg['Subject'] = config.get('subject', f"Report: {metadata.get('report_name', 'Automated Report')}")
            
            # Add body
            body = config.get('body_template', 'Please find the attached report.')
            msg.attach(MIMEText(body, 'plain'))
            
            # Add report as attachment or inline
            if config.get('inline', False):
                msg.attach(MIMEText(content, 'html'))
            else:
                attachment = MIMEApplication(content.encode())
                attachment.add_header(
                    'Content-Disposition', 
                    'attachment', 
                    filename=f"{metadata.get('report_name', 'report')}.html"
                )
                msg.attach(attachment)
            
            # Send email
            with smtplib.SMTP(config['smtp_host'], config['smtp_port']) as server:
                if config.get('use_tls', True):
                    server.starttls()
                
                if 'username' in config and 'password' in config:
                    server.login(config['username'], config['password'])
                
                server.send_message(msg)
            
            logger.info(f"Email delivered to {len(config['recipients'])} recipients")
            return True
        
        except Exception as e:
            logger.error(f"Email delivery failed: {e}")
            return False
    
    async def _deliver_file_system(self, content: str, config: Dict, metadata: Dict) -> bool:
        """Save report to file system"""
        try:
            output_path = Path(config['output_path'])
            output_path.mkdir(parents=True, exist_ok=True)
            
            # Generate filename
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            filename = config.get('filename_template', f"report_{timestamp}.html")
            filename = filename.format(**metadata, timestamp=timestamp)
            
            filepath = output_path / filename
            
            # Write content
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            
            logger.info(f"Report saved to: {filepath}")
            return True
        
        except Exception as e:
            logger.error(f"File system delivery failed: {e}")
            return False
    
    async def _deliver_ftp(self, content: str, config: Dict, metadata: Dict) -> bool:
        """Deliver report via FTP"""
        try:
            import ftplib
            from io import BytesIO
            
            # Connect to FTP
            with ftplib.FTP(config['host']) as ftp:
                ftp.login(config['username'], config['password'])
                ftp.cwd(config['remote_path'])
                
                # Generate filename
                timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
                filename = config.get('filename_template', f"report_{timestamp}.html")
                filename = filename.format(**metadata, timestamp=timestamp)
                
                # Upload file
                file_data = BytesIO(content.encode())
                ftp.storbinary(f'STOR {filename}', file_data)
            
            logger.info(f"Report uploaded via FTP: {filename}")
            return True
        
        except Exception as e:
            logger.error(f"FTP delivery failed: {e}")
            return False
    
    async def _deliver_sftp(self, content: str, config: Dict, metadata: Dict) -> bool:
        """Deliver report via SFTP"""
        try:
            import paramiko
            from io import BytesIO
            
            # Connect via SFTP
            with paramiko.SSHClient() as ssh:
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                
                if 'password' in config:
                    ssh.connect(
                        config['host'],
                        username=config['username'],
                        password=config['password']
                    )
                else:
                    ssh.connect(
                        config['host'],
                        username=config['username'],
                        key_filename=config.get('private_key_file')
                    )
                
                with ssh.open_sftp() as sftp:
                    # Generate filename
                    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
                    filename = config.get('filename_template', f"report_{timestamp}.html")
                    filename = filename.format(**metadata, timestamp=timestamp)
                    
                    remote_path = f"{config['remote_path']}/{filename}"
                    
                    # Upload file
                    file_data = BytesIO(content.encode())
                    sftp.putfo(file_data, remote_path)
            
            logger.info(f"Report uploaded via SFTP: {remote_path}")
            return True
        
        except Exception as e:
            logger.error(f"SFTP delivery failed: {e}")
            return False
    
    async def _deliver_s3(self, content: str, config: Dict, metadata: Dict) -> bool:
        """Deliver report to AWS S3"""
        try:
            import boto3
            
            # Initialize S3 client
            s3_client = boto3.client(
                's3',
                aws_access_key_id=config.get('access_key_id'),
                aws_secret_access_key=config.get('secret_access_key'),
                region_name=config.get('region', 'us-east-1')
            )
            
            # Generate key
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            key_template = config.get('key_template', f"{config['key_prefix']}/report_{timestamp}.html")
            key = key_template.format(**metadata, timestamp=timestamp)
            
            # Upload to S3
            s3_client.put_object(
                Bucket=config['bucket'],
                Key=key,
                Body=content.encode(),
                ContentType='text/html'
            )
            
            logger.info(f"Report uploaded to S3: s3://{config['bucket']}/{key}")
            return True
        
        except Exception as e:
            logger.error(f"S3 delivery failed: {e}")
            return False
    
    async def _deliver_webhook(self, content: str, config: Dict, metadata: Dict) -> bool:
        """Deliver report via webhook"""
        try:
            import aiohttp
            
            # Prepare payload
            payload = {
                'report_content': content,
                'metadata': metadata,
                'timestamp': datetime.utcnow().isoformat()
            }
            
            # Send webhook
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    config['webhook_url'],
                    json=payload,
                    headers=config.get('headers', {}),
                    timeout=config.get('timeout', 30)
                ) as response:
                    if response.status == 200:
                        logger.info("Report delivered via webhook")
                        return True
                    else:
                        logger.error(f"Webhook delivery failed with status: {response.status}")
                        return False
        
        except Exception as e:
            logger.error(f"Webhook delivery failed: {e}")
            return False
    
    async def _deliver_database(self, content: str, config: Dict, metadata: Dict) -> bool:
        """Store report in database"""
        try:
            import asyncpg
            
            # Connect to database
            conn = await asyncpg.connect(config['connection_string'])
            
            try:
                # Insert report
                await conn.execute(
                    f"""
                    INSERT INTO {config['table_name']} 
                    (report_content, metadata, created_at)
                    VALUES ($1, $2, $3)
                    """,
                    content,
                    json.dumps(metadata),
                    datetime.utcnow()
                )
                
                logger.info("Report stored in database")
                return True
            
            finally:
                await conn.close()
        
        except Exception as e:
            logger.error(f"Database delivery failed: {e}")
            return False


class ReportScheduler:
    """
    Report scheduling and execution system
    
    Manages automated report generation, scheduling, and delivery
    with support for multiple frequencies and delivery methods.
    """
    
    def __init__(self, schedules_dir: str = "schedules", max_concurrent_reports: int = 5):
        self.schedules_dir = Path(schedules_dir)
        self.schedules_dir.mkdir(exist_ok=True)
        
        self.max_concurrent_reports = max_concurrent_reports
        self.scheduled_reports: Dict[str, ScheduledReport] = {}
        self.execution_history: List[ReportExecution] = []
        self.context_generators: Dict[str, Callable] = {}
        self.delivery_handler = ReportDelivery()
        
        # Scheduler state
        self._running = False
        self._scheduler_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        
        # Load existing schedules
        self._load_schedules()
    
    def _load_schedules(self):
        """Load scheduled reports from storage"""
        try:
            for schedule_file in self.schedules_dir.glob("*.json"):
                with open(schedule_file, 'r') as f:
                    schedule_dict = json.load(f)
                
                schedule = self._dict_to_scheduled_report(schedule_dict)
                self.scheduled_reports[schedule.schedule_id] = schedule
                
                logger.info(f"Loaded schedule: {schedule.schedule_id}")
        
        except Exception as e:
            logger.error(f"Failed to load schedules: {e}")
    
    def _dict_to_scheduled_report(self, schedule_dict: Dict) -> ScheduledReport:
        """Convert dictionary to ScheduledReport"""
        
        # Parse schedule config
        sc = schedule_dict["schedule_config"]
        schedule_config = ScheduleConfig(
            frequency=ScheduleFrequency(sc["frequency"]),
            start_date=datetime.fromisoformat(sc["start_date"]),
            end_date=datetime.fromisoformat(sc["end_date"]) if sc["end_date"] else None,
            time_of_day=time.fromisoformat(sc["time_of_day"]) if sc["time_of_day"] else None,
            day_of_week=sc["day_of_week"],
            day_of_month=sc["day_of_month"],
            cron_expression=sc["cron_expression"],
            timezone=sc["timezone"]
        )
        
        # Parse delivery configs
        delivery_configs = [
            DeliveryConfig(
                method=DeliveryMethod(dc["method"]),
                config=dc["config"]
            )
            for dc in schedule_dict["delivery_configs"]
        ]
        
        return ScheduledReport(
            schedule_id=schedule_dict["schedule_id"],
            name=schedule_dict["name"],
            description=schedule_dict["description"],
            template_id=schedule_dict["template_id"],
            schedule_config=schedule_config,
            delivery_configs=delivery_configs,
            context_generator=schedule_dict.get("context_generator"),
            context_params=schedule_dict.get("context_params", {}),
            status=ScheduleStatus(schedule_dict["status"]),
            created_at=datetime.fromisoformat(schedule_dict["created_at"]),
            updated_at=datetime.fromisoformat(schedule_dict["updated_at"]),
            last_execution=datetime.fromisoformat(schedule_dict["last_execution"]) if schedule_dict["last_execution"] else None,
            next_execution=datetime.fromisoformat(schedule_dict["next_execution"]) if schedule_dict["next_execution"] else None,
            execution_count=schedule_dict["execution_count"],
            metadata=schedule_dict["metadata"]
        )
    
    def register_context_generator(self, name: str, generator: Callable) -> None:
        """Register context generator function"""
        self.context_generators[name] = generator
        logger.info(f"Registered context generator: {name}")
    
    def create_schedule(
        self,
        schedule_id: str,
        name: str,
        template_id: str,
        schedule_config: ScheduleConfig,
        delivery_configs: List[DeliveryConfig],
        description: str = "",
        context_generator: Optional[str] = None,
        context_params: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Create new scheduled report"""
        
        try:
            # Validate inputs
            if not schedule_config.validate():
                logger.error("Invalid schedule configuration")
                return False
            
            for delivery_config in delivery_configs:
                if not delivery_config.validate():
                    logger.error(f"Invalid delivery configuration: {delivery_config.method}")
                    return False
            
            # Calculate next execution
            next_execution = schedule_config.get_next_run_time()
            
            # Create scheduled report
            scheduled_report = ScheduledReport(
                schedule_id=schedule_id,
                name=name,
                description=description,
                template_id=template_id,
                schedule_config=schedule_config,
                delivery_configs=delivery_configs,
                context_generator=context_generator,
                context_params=context_params or {},
                next_execution=next_execution
            )
            
            # Save schedule
            return self._save_schedule(scheduled_report)
        
        except Exception as e:
            logger.error(f"Failed to create schedule {schedule_id}: {e}")
            return False
    
    def _save_schedule(self, scheduled_report: ScheduledReport) -> bool:
        """Save scheduled report to storage"""
        try:
            self.scheduled_reports[scheduled_report.schedule_id] = scheduled_report
            
            # Save to file
            schedule_file = self.schedules_dir / f"{scheduled_report.schedule_id}.json"
            with open(schedule_file, 'w') as f:
                json.dump(scheduled_report.to_dict(), f, indent=2, default=str)
            
            logger.info(f"Schedule saved: {scheduled_report.schedule_id}")
            return True
        
        except Exception as e:
            logger.error(f"Failed to save schedule: {e}")
            return False
    
    def update_schedule_status(self, schedule_id: str, status: ScheduleStatus) -> bool:
        """Update schedule status"""
        try:
            if schedule_id not in self.scheduled_reports:
                return False
            
            schedule = self.scheduled_reports[schedule_id]
            schedule.status = status
            schedule.updated_at = datetime.utcnow()
            
            return self._save_schedule(schedule)
        
        except Exception as e:
            logger.error(f"Failed to update schedule status: {e}")
            return False
    
    def delete_schedule(self, schedule_id: str) -> bool:
        """Delete scheduled report"""
        try:
            if schedule_id in self.scheduled_reports:
                del self.scheduled_reports[schedule_id]
            
            # Remove file
            schedule_file = self.schedules_dir / f"{schedule_id}.json"
            if schedule_file.exists():
                schedule_file.unlink()
            
            logger.info(f"Schedule deleted: {schedule_id}")
            return True
        
        except Exception as e:
            logger.error(f"Failed to delete schedule: {e}")
            return False
    
    def start_scheduler(self):
        """Start the report scheduler"""
        if self._running:
            logger.warning("Scheduler already running")
            return
        
        self._running = True
        self._stop_event.clear()
        
        # Start scheduler thread
        self._scheduler_thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self._scheduler_thread.start()
        
        logger.info("Report scheduler started")
    
    def stop_scheduler(self):
        """Stop the report scheduler"""
        if not self._running:
            return
        
        self._running = False
        self._stop_event.set()
        
        if self._scheduler_thread:
            self._scheduler_thread.join(timeout=10)
        
        logger.info("Report scheduler stopped")
    
    def _scheduler_loop(self):
        """Main scheduler loop"""
        while self._running and not self._stop_event.is_set():
            try:
                # Check for reports to execute
                self._check_and_execute_reports()
                
                # Sleep for 60 seconds
                self._stop_event.wait(60)
            
            except Exception as e:
                logger.error(f"Scheduler loop error: {e}")
                self._stop_event.wait(60)
    
    def _check_and_execute_reports(self):
        """Check and execute due reports"""
        current_time = datetime.utcnow()
        
        for schedule_id, schedule in self.scheduled_reports.items():
            try:
                if (schedule.status == ScheduleStatus.ACTIVE and 
                    schedule.next_execution and 
                    schedule.next_execution <= current_time):
                    
                    # Execute report asynchronously
                    asyncio.run_coroutine_threadsafe(
                        self._execute_scheduled_report(schedule),
                        asyncio.get_event_loop()
                    )
            
            except Exception as e:
                logger.error(f"Error checking schedule {schedule_id}: {e}")
    
    async def _execute_scheduled_report(self, schedule: ScheduledReport):
        """Execute a scheduled report"""
        execution_id = f"{schedule.schedule_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        
        execution = ReportExecution(
            execution_id=execution_id,
            schedule_id=schedule.schedule_id,
            started_at=datetime.utcnow()
        )
        
        try:
            logger.info(f"Executing scheduled report: {schedule.schedule_id}")
            
            # Generate context
            context = await self._generate_report_context(schedule)
            execution.context_used = context
            
            # Import here to avoid circular imports
            from .template_manager import TemplateManager
            from .report_generator import ReportGenerator
            
            # Generate report
            template_manager = TemplateManager()
            report_generator = ReportGenerator()
            
            # Render template
            report_content = template_manager.render_template(schedule.template_id, context)
            
            if not report_content:
                raise Exception("Failed to generate report content")
            
            # Deliver report
            delivery_success = True
            for delivery_config in schedule.delivery_configs:
                success = await self.delivery_handler.deliver_report(
                    report_content,
                    delivery_config,
                    {
                        "report_name": schedule.name,
                        "schedule_id": schedule.schedule_id,
                        "execution_id": execution_id
                    }
                )
                
                if not success:
                    delivery_success = False
                    logger.error(f"Delivery failed for {delivery_config.method}")
            
            # Update execution
            execution.completed_at = datetime.utcnow()
            execution.execution_time_seconds = (execution.completed_at - execution.started_at).total_seconds()
            execution.status = "completed" if delivery_success else "partial_failure"
            
            # Update schedule
            schedule.last_execution = execution.started_at
            schedule.execution_count += 1
            schedule.next_execution = schedule.schedule_config.get_next_run_time()
            
            if schedule.next_execution is None:
                schedule.status = ScheduleStatus.COMPLETED
            
            self._save_schedule(schedule)
            
            logger.info(f"Report execution completed: {execution_id}")
        
        except Exception as e:
            execution.completed_at = datetime.utcnow()
            execution.status = "error"
            execution.error_message = str(e)
            
            logger.error(f"Report execution failed: {execution_id} - {e}")
        
        finally:
            self.execution_history.append(execution)
            
            # Keep only last 1000 executions
            if len(self.execution_history) > 1000:
                self.execution_history = self.execution_history[-1000:]
    
    async def _generate_report_context(self, schedule: ScheduledReport) -> Dict[str, Any]:
        """Generate context for report execution"""
        
        context = {
            "report_date": datetime.utcnow(),
            "schedule_id": schedule.schedule_id,
            "schedule_name": schedule.name
        }
        
        # Add context parameters
        context.update(schedule.context_params)
        
        # Execute context generator if specified
        if schedule.context_generator and schedule.context_generator in self.context_generators:
            try:
                generator = self.context_generators[schedule.context_generator]
                
                if asyncio.iscoroutinefunction(generator):
                    additional_context = await generator(schedule.context_params)
                else:
                    additional_context = generator(schedule.context_params)
                
                context.update(additional_context)
            
            except Exception as e:
                logger.error(f"Context generator failed: {e}")
        
        return context
    
    def get_schedule_status(self, schedule_id: str) -> Optional[Dict[str, Any]]:
        """Get status of scheduled report"""
        
        if schedule_id not in self.scheduled_reports:
            return None
        
        schedule = self.scheduled_reports[schedule_id]
        
        # Get recent executions
        recent_executions = [
            exec.to_dict() for exec in self.execution_history
            if exec.schedule_id == schedule_id
        ][-10:]  # Last 10 executions
        
        return {
            "schedule": schedule.to_dict(),
            "recent_executions": recent_executions,
            "is_due": schedule.next_execution <= datetime.utcnow() if schedule.next_execution else False
        }
    
    def list_schedules(self) -> List[Dict[str, Any]]:
        """List all scheduled reports"""
        
        schedules = []
        for schedule in self.scheduled_reports.values():
            schedules.append({
                "schedule_id": schedule.schedule_id,
                "name": schedule.name,
                "template_id": schedule.template_id,
                "status": schedule.status.value,
                "frequency": schedule.schedule_config.frequency.value,
                "next_execution": schedule.next_execution.isoformat() if schedule.next_execution else None,
                "last_execution": schedule.last_execution.isoformat() if schedule.last_execution else None,
                "execution_count": schedule.execution_count
            })
        
        return schedules
    
    def execute_now(self, schedule_id: str) -> bool:
        """Execute scheduled report immediately"""
        
        if schedule_id not in self.scheduled_reports:
            return False
        
        schedule = self.scheduled_reports[schedule_id]
        
        # Execute asynchronously
        try:
            asyncio.run_coroutine_threadsafe(
                self._execute_scheduled_report(schedule),
                asyncio.get_event_loop()
            )
            return True
        
        except Exception as e:
            logger.error(f"Failed to execute report immediately: {e}")
            return False