"""
Automated Report Generation Module

Comprehensive reporting system for masterTrade platform including:
- Multi-format report generation (PDF, HTML, Excel, CSV)
- Scheduled reporting with email delivery
- Interactive dashboards and visualizations  
- Custom report templates and branding
- Performance summary reports integrating all systems
- Real-time report updates and notifications

Components:
- ReportGenerator: Core report generation engine
- TemplateManager: Report template management and customization
- ReportScheduler: Automated scheduling and delivery system
- VisualizationEngine: Chart and graph generation
- EmailSender: Email delivery and notification system
- API: REST endpoints for report management

Key Features:
- Integration with all masterTrade systems (strategy, portfolio, TCA, correlation analysis)
- Multiple output formats with consistent styling
- Automated report scheduling (daily, weekly, monthly, custom)
- Email delivery with attachments and inline content
- Interactive web-based reports with drill-down capabilities
- Custom branding and white-label support
- Report performance optimization and caching
- Audit trail and report versioning
"""

from .report_generator import (
    ReportGenerator,
    ReportType,
    ReportFormat,
    ReportData,
    GeneratedReport,
    ReportSection
)

from .template_manager import (
    TemplateManager,
    ReportTemplate,
    TemplateSection,
    TemplateVariable,
    CustomBranding,
    TemplateEngine
)

from .scheduler import (
    ReportScheduler,
    ScheduledReport,
    ScheduleFrequency,
    DeliveryMethod,
    ReportSubscription,
    ScheduleManager
)

from .visualization_engine import (
    VisualizationEngine,
    ChartType,
    ChartConfiguration,
    Dashboard,
    InteractiveChart,
    DataVisualization
)

from .email_sender import (
    EmailSender,
    EmailTemplate,
    EmailConfiguration,
    DeliveryReport,
    NotificationManager
)

__all__ = [
    # Core Report Generation
    'ReportGenerator',
    'ReportType',
    'ReportFormat', 
    'ReportData',
    'GeneratedReport',
    'ReportSection',
    
    # Template Management
    'TemplateManager',
    'ReportTemplate',
    'TemplateSection',
    'TemplateVariable',
    'CustomBranding',
    'TemplateEngine',
    
    # Scheduling System
    'ReportScheduler',
    'ScheduledReport',
    'ScheduleFrequency',
    'DeliveryMethod',
    'ReportSubscription',
    'ScheduleManager',
    
    # Visualization Engine
    'VisualizationEngine',
    'ChartType',
    'ChartConfiguration',
    'Dashboard',
    'InteractiveChart',
    'DataVisualization',
    
    # Email Delivery
    'EmailSender',
    'EmailTemplate',
    'EmailConfiguration',
    'DeliveryReport',
    'NotificationManager'
]

# Module metadata
__version__ = "1.0.0"
__author__ = "MasterTrade Automated Reporting Team"
__description__ = "Comprehensive automated report generation and delivery system"