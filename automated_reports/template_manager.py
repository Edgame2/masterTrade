"""
Template Manager

Report template management and customization system for flexible report generation
with support for custom branding, layouts, and content organization.
"""

import logging
import json
import yaml
from datetime import datetime
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import re

try:
    from jinja2 import Environment, FileSystemLoader, Template, select_autoescape
    from jinja2.exceptions import TemplateError
    JINJA2_AVAILABLE = True
except ImportError:
    JINJA2_AVAILABLE = False
    logging.warning("Jinja2 not available for template processing")

logger = logging.getLogger(__name__)


class TemplateType(Enum):
    """Types of report templates"""
    DAILY_PERFORMANCE = "daily_performance"
    WEEKLY_SUMMARY = "weekly_summary"
    MONTHLY_REPORT = "monthly_report"
    QUARTERLY_REVIEW = "quarterly_review"
    EXECUTIVE_SUMMARY = "executive_summary"
    DETAILED_ANALYSIS = "detailed_analysis"
    CUSTOM = "custom"


class OutputFormat(Enum):
    """Supported output formats for templates"""
    HTML = "html"
    PDF = "pdf"
    EMAIL = "email"
    MARKDOWN = "markdown"
    JSON = "json"


class SectionLayout(Enum):
    """Section layout options"""
    FULL_WIDTH = "full_width"
    TWO_COLUMN = "two_column"
    THREE_COLUMN = "three_column"
    GRID = "grid"
    TABBED = "tabbed"
    ACCORDION = "accordion"


@dataclass
class TemplateVariable:
    """Template variable definition"""
    name: str
    variable_type: str  # string, number, boolean, date, list, dict
    default_value: Any = None
    description: str = ""
    required: bool = True
    validation_pattern: Optional[str] = None
    choices: Optional[List[str]] = None
    
    def validate_value(self, value: Any) -> bool:
        """Validate value against variable constraints"""
        try:
            if self.required and value is None:
                return False
            
            if value is None:
                return not self.required
            
            # Type validation
            if self.variable_type == "string" and not isinstance(value, str):
                return False
            elif self.variable_type == "number" and not isinstance(value, (int, float)):
                return False
            elif self.variable_type == "boolean" and not isinstance(value, bool):
                return False
            elif self.variable_type == "list" and not isinstance(value, list):
                return False
            elif self.variable_type == "dict" and not isinstance(value, dict):
                return False
            
            # Pattern validation
            if self.validation_pattern and isinstance(value, str):
                if not re.match(self.validation_pattern, value):
                    return False
            
            # Choices validation
            if self.choices and value not in self.choices:
                return False
            
            return True
        
        except Exception as e:
            logger.warning(f"Variable validation error for {self.name}: {e}")
            return False
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "name": self.name,
            "type": self.variable_type,
            "default_value": self.default_value,
            "description": self.description,
            "required": self.required,
            "validation_pattern": self.validation_pattern,
            "choices": self.choices
        }


@dataclass
class TemplateSection:
    """Template section definition"""
    section_id: str
    title: str
    template_content: str
    layout: SectionLayout = SectionLayout.FULL_WIDTH
    order: int = 0
    required: bool = True
    conditional_logic: Optional[str] = None
    variables: List[TemplateVariable] = field(default_factory=list)
    css_classes: List[str] = field(default_factory=list)
    
    def render(self, context: Dict[str, Any], jinja_env: Environment) -> str:
        """Render section with provided context"""
        try:
            # Check conditional logic
            if self.conditional_logic:
                if not self._evaluate_condition(self.conditional_logic, context):
                    return ""
            
            # Validate required variables
            for variable in self.variables:
                if variable.required and variable.name not in context:
                    if variable.default_value is not None:
                        context[variable.name] = variable.default_value
                    else:
                        logger.warning(f"Required variable {variable.name} missing for section {self.section_id}")
            
            # Render template
            template = jinja_env.from_string(self.template_content)
            rendered_content = template.render(**context)
            
            return rendered_content
        
        except Exception as e:
            logger.error(f"Section rendering failed for {self.section_id}: {e}")
            return f"<div class='error'>Error rendering section {self.title}</div>"
    
    def _evaluate_condition(self, condition: str, context: Dict[str, Any]) -> bool:
        """Evaluate conditional logic for section inclusion"""
        try:
            # Simple condition evaluation (can be expanded)
            # Supports: variable_name == value, variable_name != value, variable_name > value, etc.
            
            # Replace variable names with values
            for key, value in context.items():
                condition = condition.replace(key, str(value))
            
            # Evaluate simple expressions
            return eval(condition)
        
        except Exception as e:
            logger.warning(f"Condition evaluation failed: {e}")
            return True  # Default to including section
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "section_id": self.section_id,
            "title": self.title,
            "template_content": self.template_content,
            "layout": self.layout.value,
            "order": self.order,
            "required": self.required,
            "conditional_logic": self.conditional_logic,
            "variables": [var.to_dict() for var in self.variables],
            "css_classes": self.css_classes
        }


@dataclass
class CustomBranding:
    """Custom branding configuration"""
    company_name: str = "MasterTrade"
    logo_url: Optional[str] = None
    primary_color: str = "#2E86AB"
    secondary_color: str = "#4ECDC4"
    accent_color: str = "#FF6B6B"
    font_family: str = "Arial, sans-serif"
    header_font_size: str = "24px"
    body_font_size: str = "14px"
    custom_css: Optional[str] = None
    footer_text: Optional[str] = None
    
    def to_css_variables(self) -> str:
        """Generate CSS variables from branding"""
        css_vars = f"""
        :root {{
            --primary-color: {self.primary_color};
            --secondary-color: {self.secondary_color};
            --accent-color: {self.accent_color};
            --font-family: {self.font_family};
            --header-font-size: {self.header_font_size};
            --body-font-size: {self.body_font_size};
        }}
        """
        
        if self.custom_css:
            css_vars += f"\n{self.custom_css}"
        
        return css_vars
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "company_name": self.company_name,
            "logo_url": self.logo_url,
            "primary_color": self.primary_color,
            "secondary_color": self.secondary_color,
            "accent_color": self.accent_color,
            "font_family": self.font_family,
            "header_font_size": self.header_font_size,
            "body_font_size": self.body_font_size,
            "custom_css": self.custom_css,
            "footer_text": self.footer_text
        }


@dataclass
class ReportTemplate:
    """Complete report template definition"""
    template_id: str
    name: str
    description: str
    template_type: TemplateType
    output_format: OutputFormat
    sections: List[TemplateSection] = field(default_factory=list)
    global_variables: List[TemplateVariable] = field(default_factory=list)
    branding: Optional[CustomBranding] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    version: str = "1.0.0"
    
    def render_report(self, context: Dict[str, Any], jinja_env: Environment) -> str:
        """Render complete report using template"""
        try:
            # Add branding to context
            if self.branding:
                context['branding'] = self.branding.to_dict()
            
            # Add global variables defaults
            for variable in self.global_variables:
                if variable.name not in context and variable.default_value is not None:
                    context[variable.name] = variable.default_value
            
            # Sort sections by order
            sorted_sections = sorted(self.sections, key=lambda s: s.order)
            
            # Render each section
            rendered_sections = []
            for section in sorted_sections:
                rendered_content = section.render(context, jinja_env)
                if rendered_content:  # Only include non-empty sections
                    rendered_sections.append({
                        "id": section.section_id,
                        "title": section.title,
                        "content": rendered_content,
                        "layout": section.layout.value,
                        "css_classes": " ".join(section.css_classes)
                    })
            
            # Create complete report context
            report_context = {
                **context,
                "template": {
                    "id": self.template_id,
                    "name": self.name,
                    "type": self.template_type.value,
                    "format": self.output_format.value
                },
                "sections": rendered_sections,
                "generated_at": datetime.utcnow().isoformat(),
                "branding_css": self.branding.to_css_variables() if self.branding else ""
            }
            
            # Render master template
            master_template = self._get_master_template(self.output_format)
            template = jinja_env.from_string(master_template)
            
            return template.render(**report_context)
        
        except Exception as e:
            logger.error(f"Report rendering failed for template {self.template_id}: {e}")
            raise
    
    def _get_master_template(self, output_format: OutputFormat) -> str:
        """Get master template for output format"""
        
        if output_format == OutputFormat.HTML:
            return self._get_html_master_template()
        elif output_format == OutputFormat.EMAIL:
            return self._get_email_master_template()
        elif output_format == OutputFormat.MARKDOWN:
            return self._get_markdown_master_template()
        elif output_format == OutputFormat.JSON:
            return self._get_json_master_template()
        else:
            return self._get_html_master_template()  # Default
    
    def _get_html_master_template(self) -> str:
        """HTML master template"""
        return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ template.name }} - {{ branding.company_name if branding else 'MasterTrade' }}</title>
    
    <style>
        {{ branding_css }}
        
        body {
            font-family: var(--font-family, Arial, sans-serif);
            font-size: var(--body-font-size, 14px);
            line-height: 1.6;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
        }
        
        .report-container {
            max-width: 1200px;
            margin: 0 auto;
            background-color: white;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            overflow: hidden;
        }
        
        .report-header {
            background: linear-gradient(135deg, var(--primary-color, #2E86AB), var(--secondary-color, #4ECDC4));
            color: white;
            padding: 30px;
            text-align: center;
        }
        
        .report-header h1 {
            margin: 0;
            font-size: var(--header-font-size, 24px);
            font-weight: bold;
        }
        
        .report-meta {
            margin-top: 10px;
            opacity: 0.9;
        }
        
        .report-content {
            padding: 30px;
        }
        
        .section {
            margin-bottom: 40px;
            border-bottom: 1px solid #eee;
            padding-bottom: 30px;
        }
        
        .section:last-child {
            border-bottom: none;
        }
        
        .section-title {
            color: var(--primary-color, #2E86AB);
            font-size: 20px;
            font-weight: bold;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 2px solid var(--secondary-color, #4ECDC4);
        }
        
        .section-content {
            line-height: 1.8;
        }
        
        .full_width {
            width: 100%;
        }
        
        .two_column {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 30px;
        }
        
        .three_column {
            display: grid;
            grid-template-columns: 1fr 1fr 1fr;
            gap: 20px;
        }
        
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
        }
        
        .chart-container {
            text-align: center;
            margin: 20px 0;
        }
        
        .chart-container img {
            max-width: 100%;
            height: auto;
            border-radius: 4px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }
        
        .metric-card {
            background: #f8f9fa;
            border-left: 4px solid var(--accent-color, #FF6B6B);
            padding: 15px;
            margin: 10px 0;
            border-radius: 4px;
        }
        
        .metric-value {
            font-size: 24px;
            font-weight: bold;
            color: var(--primary-color, #2E86AB);
        }
        
        .metric-label {
            font-size: 12px;
            color: #666;
            text-transform: uppercase;
        }
        
        .report-footer {
            background-color: #f8f9fa;
            padding: 20px;
            text-align: center;
            color: #666;
            font-size: 12px;
            border-top: 1px solid #eee;
        }
        
        @media (max-width: 768px) {
            .two_column,
            .three_column,
            .grid {
                grid-template-columns: 1fr;
            }
            
            .report-container {
                margin: 10px;
                border-radius: 0;
            }
            
            .report-content {
                padding: 20px;
            }
        }
    </style>
</head>
<body>
    <div class="report-container">
        <div class="report-header">
            {% if branding and branding.logo_url %}
            <img src="{{ branding.logo_url }}" alt="Logo" style="max-height: 50px; margin-bottom: 10px;">
            {% endif %}
            
            <h1>{{ template.name }}</h1>
            <div class="report-meta">
                Generated on {{ generated_at[:19] }} UTC
                {% if template.type != 'custom' %}
                | {{ template.type|title|replace('_', ' ') }} Report
                {% endif %}
            </div>
        </div>
        
        <div class="report-content">
            {% for section in sections %}
            <div class="section {{ section.css_classes }}">
                <h2 class="section-title">{{ section.title }}</h2>
                <div class="section-content {{ section.layout }}">
                    {{ section.content|safe }}
                </div>
            </div>
            {% endfor %}
        </div>
        
        <div class="report-footer">
            {% if branding and branding.footer_text %}
                {{ branding.footer_text }}
            {% else %}
                Generated by MasterTrade Reporting System
            {% endif %}
        </div>
    </div>
</body>
</html>
        """
    
    def _get_email_master_template(self) -> str:
        """Email-optimized HTML template"""
        return """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ template.name }}</title>
    <style>
        /* Email-safe CSS */
        body { 
            font-family: Arial, sans-serif; 
            margin: 0; 
            padding: 20px; 
            background-color: #f5f5f5; 
        }
        .email-container { 
            max-width: 600px; 
            margin: 0 auto; 
            background-color: white; 
            border-radius: 8px; 
        }
        .header { 
            background-color: {{ branding.primary_color if branding else '#2E86AB' }}; 
            color: white; 
            padding: 20px; 
            text-align: center; 
        }
        .content { 
            padding: 20px; 
        }
        .section { 
            margin-bottom: 20px; 
            padding: 15px; 
            border-left: 3px solid {{ branding.secondary_color if branding else '#4ECDC4' }}; 
        }
        .footer { 
            background-color: #f8f9fa; 
            padding: 15px; 
            text-align: center; 
            font-size: 12px; 
            color: #666; 
        }
    </style>
</head>
<body>
    <div class="email-container">
        <div class="header">
            <h1>{{ template.name }}</h1>
            <p>{{ generated_at[:19] }} UTC</p>
        </div>
        
        <div class="content">
            {% for section in sections %}
            <div class="section">
                <h2>{{ section.title }}</h2>
                <div>{{ section.content|safe }}</div>
            </div>
            {% endfor %}
        </div>
        
        <div class="footer">
            {% if branding and branding.footer_text %}
                {{ branding.footer_text }}
            {% else %}
                Generated by MasterTrade
            {% endif %}
        </div>
    </div>
</body>
</html>
        """
    
    def _get_markdown_master_template(self) -> str:
        """Markdown master template"""
        return """
# {{ template.name }}

**Generated:** {{ generated_at[:19] }} UTC  
**Type:** {{ template.type|title|replace('_', ' ') }} Report

---

{% for section in sections %}
## {{ section.title }}

{{ section.content }}

---

{% endfor %}

*Generated by {{ branding.company_name if branding else 'MasterTrade' }}*
        """
    
    def _get_json_master_template(self) -> str:
        """JSON master template"""
        return """
{
    "template": {{ template|tojson }},
    "generated_at": "{{ generated_at }}",
    "branding": {{ branding|tojson if branding else 'null' }},
    "sections": {{ sections|tojson }}
}
        """
    
    def validate_context(self, context: Dict[str, Any]) -> Dict[str, List[str]]:
        """Validate context against template requirements"""
        errors = {"missing_variables": [], "invalid_values": []}
        
        # Check global variables
        for variable in self.global_variables:
            if variable.name not in context:
                if variable.required:
                    errors["missing_variables"].append(variable.name)
            else:
                if not variable.validate_value(context[variable.name]):
                    errors["invalid_values"].append(f"{variable.name}: {context[variable.name]}")
        
        # Check section variables
        for section in self.sections:
            for variable in section.variables:
                if variable.name not in context:
                    if variable.required:
                        errors["missing_variables"].append(f"{section.section_id}.{variable.name}")
                else:
                    if not variable.validate_value(context[variable.name]):
                        errors["invalid_values"].append(f"{section.section_id}.{variable.name}: {context[variable.name]}")
        
        return errors
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "template_id": self.template_id,
            "name": self.name,
            "description": self.description,
            "template_type": self.template_type.value,
            "output_format": self.output_format.value,
            "sections": [section.to_dict() for section in self.sections],
            "global_variables": [var.to_dict() for var in self.global_variables],
            "branding": self.branding.to_dict() if self.branding else None,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "version": self.version
        }


class TemplateEngine:
    """Template rendering engine wrapper"""
    
    def __init__(self, template_dir: Optional[str] = None):
        if not JINJA2_AVAILABLE:
            raise ImportError("Jinja2 is required for template processing")
        
        self.template_dir = Path(template_dir) if template_dir else Path("templates")
        
        # Initialize Jinja2 environment
        if self.template_dir.exists():
            self.env = Environment(
                loader=FileSystemLoader(str(self.template_dir)),
                autoescape=select_autoescape(['html', 'xml'])
            )
        else:
            self.env = Environment(autoescape=select_autoescape(['html', 'xml']))
        
        # Add custom filters
        self.env.filters['percentage'] = lambda x: f"{x:.2%}" if isinstance(x, (int, float)) else x
        self.env.filters['currency'] = lambda x: f"${x:,.2f}" if isinstance(x, (int, float)) else x
        self.env.filters['number'] = lambda x: f"{x:,.2f}" if isinstance(x, (int, float)) else x
    
    def render_template(self, template: ReportTemplate, context: Dict[str, Any]) -> str:
        """Render template with context"""
        return template.render_report(context, self.env)
    
    def render_string(self, template_string: str, context: Dict[str, Any]) -> str:
        """Render template string with context"""
        template = self.env.from_string(template_string)
        return template.render(**context)


class TemplateManager:
    """
    Template management system for report generation
    
    Manages report templates, custom branding, and template variables
    with support for multiple output formats and dynamic content.
    """
    
    def __init__(self, templates_dir: str = "templates", cache_templates: bool = True):
        self.templates_dir = Path(templates_dir)
        self.templates_dir.mkdir(exist_ok=True)
        
        self.cache_templates = cache_templates
        self.template_cache: Dict[str, ReportTemplate] = {}
        self.template_engine = TemplateEngine(str(self.templates_dir)) if JINJA2_AVAILABLE else None
        
        # Load built-in templates
        self._load_builtin_templates()
    
    def _load_builtin_templates(self):
        """Load built-in report templates"""
        
        # Daily Performance Template
        daily_template = self._create_daily_performance_template()
        self.save_template(daily_template)
        
        # Weekly Summary Template
        weekly_template = self._create_weekly_summary_template()
        self.save_template(weekly_template)
        
        # Executive Summary Template
        executive_template = self._create_executive_summary_template()
        self.save_template(executive_template)
    
    def _create_daily_performance_template(self) -> ReportTemplate:
        """Create built-in daily performance template"""
        
        # Executive Summary Section
        exec_section = TemplateSection(
            section_id="executive_summary",
            title="Executive Summary",
            template_content="""
<div class="metric-card">
    <div class="metric-value">{{ performance.total_return|percentage }}</div>
    <div class="metric-label">Total Return</div>
</div>

<div class="metric-card">
    <div class="metric-value">{{ performance.sharpe_ratio|number }}</div>
    <div class="metric-label">Sharpe Ratio</div>
</div>

<div class="metric-card">
    <div class="metric-value">{{ performance.max_drawdown|percentage }}</div>
    <div class="metric-label">Max Drawdown</div>
</div>

<p>Portfolio performance for {{ report_date.strftime('%B %d, %Y') }}:</p>
<ul>
<li>Daily return: {{ performance.daily_return|percentage }}</li>
<li>Risk-adjusted performance: {{ 'Strong' if performance.sharpe_ratio > 1 else 'Moderate' if performance.sharpe_ratio > 0.5 else 'Weak' }}</li>
<li>Portfolio volatility: {{ performance.volatility|percentage }}</li>
</ul>
            """,
            layout=SectionLayout.THREE_COLUMN,
            order=1,
            variables=[
                TemplateVariable("performance", "dict", required=True),
                TemplateVariable("report_date", "date", required=True)
            ]
        )
        
        # Performance Chart Section
        chart_section = TemplateSection(
            section_id="performance_chart",
            title="Performance Chart",
            template_content="""
{% if charts.performance_chart %}
<div class="chart-container">
    <img src="{{ charts.performance_chart }}" alt="Performance Chart">
</div>
{% endif %}

<p>The chart above shows the cumulative performance over the reporting period.</p>
            """,
            layout=SectionLayout.FULL_WIDTH,
            order=2,
            variables=[
                TemplateVariable("charts", "dict", required=False, default_value={})
            ]
        )
        
        return ReportTemplate(
            template_id="daily_performance_html",
            name="Daily Performance Report",
            description="Comprehensive daily performance report with key metrics and charts",
            template_type=TemplateType.DAILY_PERFORMANCE,
            output_format=OutputFormat.HTML,
            sections=[exec_section, chart_section],
            global_variables=[
                TemplateVariable("report_title", "string", "Daily Performance Report"),
                TemplateVariable("company_name", "string", "MasterTrade"),
                TemplateVariable("report_date", "date", required=True)
            ]
        )
    
    def _create_weekly_summary_template(self) -> ReportTemplate:
        """Create built-in weekly summary template"""
        
        summary_section = TemplateSection(
            section_id="weekly_summary",
            title="Weekly Performance Summary",
            template_content="""
<h3>Performance Highlights</h3>
<ul>
<li>Weekly Return: {{ performance.weekly_return|percentage }}</li>
<li>Volatility: {{ performance.weekly_volatility|percentage }}</li>
<li>Best Day: {{ performance.best_day|percentage }} ({{ performance.best_date }})</li>
<li>Worst Day: {{ performance.worst_day|percentage }} ({{ performance.worst_date }})</li>
</ul>

<h3>Strategy Performance</h3>
{% if strategy_performance %}
<table border="1" style="width:100%; border-collapse:collapse;">
<tr>
    <th>Strategy</th>
    <th>Return</th>
    <th>Volatility</th>
    <th>Sharpe Ratio</th>
</tr>
{% for strategy, metrics in strategy_performance.items() %}
<tr>
    <td>{{ strategy }}</td>
    <td>{{ metrics.return|percentage }}</td>
    <td>{{ metrics.volatility|percentage }}</td>
    <td>{{ metrics.sharpe_ratio|number }}</td>
</tr>
{% endfor %}
</table>
{% endif %}
            """,
            layout=SectionLayout.FULL_WIDTH,
            order=1
        )
        
        return ReportTemplate(
            template_id="weekly_summary_html",
            name="Weekly Summary Report",
            description="Weekly performance summary with strategy breakdown",
            template_type=TemplateType.WEEKLY_SUMMARY,
            output_format=OutputFormat.HTML,
            sections=[summary_section]
        )
    
    def _create_executive_summary_template(self) -> ReportTemplate:
        """Create built-in executive summary template"""
        
        exec_section = TemplateSection(
            section_id="executive_overview",
            title="Executive Overview",
            template_content="""
<h3>Key Performance Indicators</h3>

<div class="two_column">
    <div>
        <div class="metric-card">
            <div class="metric-value">{{ portfolio.total_value|currency }}</div>
            <div class="metric-label">Portfolio Value</div>
        </div>
        
        <div class="metric-card">
            <div class="metric-value">{{ performance.ytd_return|percentage }}</div>
            <div class="metric-label">YTD Return</div>
        </div>
    </div>
    
    <div>
        <div class="metric-card">
            <div class="metric-value">{{ risk.sharpe_ratio|number }}</div>
            <div class="metric-label">Sharpe Ratio</div>
        </div>
        
        <div class="metric-card">
            <div class="metric-value">{{ risk.max_drawdown|percentage }}</div>
            <div class="metric-label">Max Drawdown</div>
        </div>
    </div>
</div>

<h3>Executive Summary</h3>
<p>
The portfolio has {{ 'outperformed' if performance.alpha > 0 else 'underperformed' }} 
expectations during the reporting period, generating a 
{{ performance.total_return|percentage }} return with a Sharpe ratio of {{ risk.sharpe_ratio|number }}.
</p>

<p>
Risk management has been {{ 'effective' if risk.max_drawdown < 0.1 else 'challenging' }}, 
with maximum drawdown of {{ risk.max_drawdown|percentage }}.
</p>
            """,
            layout=SectionLayout.FULL_WIDTH,
            order=1
        )
        
        return ReportTemplate(
            template_id="executive_summary_html",
            name="Executive Summary Report",
            description="High-level executive summary for senior management",
            template_type=TemplateType.EXECUTIVE_SUMMARY,
            output_format=OutputFormat.HTML,
            sections=[exec_section]
        )
    
    def create_template(
        self,
        template_id: str,
        name: str,
        description: str,
        template_type: TemplateType,
        output_format: OutputFormat,
        sections: List[TemplateSection],
        global_variables: Optional[List[TemplateVariable]] = None,
        branding: Optional[CustomBranding] = None
    ) -> ReportTemplate:
        """Create a new report template"""
        
        template = ReportTemplate(
            template_id=template_id,
            name=name,
            description=description,
            template_type=template_type,
            output_format=output_format,
            sections=sections,
            global_variables=global_variables or [],
            branding=branding
        )
        
        return template
    
    def save_template(self, template: ReportTemplate) -> bool:
        """Save template to storage"""
        try:
            # Save to cache
            if self.cache_templates:
                self.template_cache[template.template_id] = template
            
            # Save to file
            template_file = self.templates_dir / f"{template.template_id}.json"
            with open(template_file, 'w') as f:
                json.dump(template.to_dict(), f, indent=2, default=str)
            
            logger.info(f"Template {template.template_id} saved successfully")
            return True
        
        except Exception as e:
            logger.error(f"Failed to save template {template.template_id}: {e}")
            return False
    
    def load_template(self, template_id: str) -> Optional[ReportTemplate]:
        """Load template from storage"""
        try:
            # Check cache first
            if self.cache_templates and template_id in self.template_cache:
                return self.template_cache[template_id]
            
            # Load from file
            template_file = self.templates_dir / f"{template_id}.json"
            if not template_file.exists():
                logger.warning(f"Template file not found: {template_id}")
                return None
            
            with open(template_file, 'r') as f:
                template_dict = json.load(f)
            
            template = self._dict_to_template(template_dict)
            
            # Cache if enabled
            if self.cache_templates:
                self.template_cache[template_id] = template
            
            return template
        
        except Exception as e:
            logger.error(f"Failed to load template {template_id}: {e}")
            return None
    
    def _dict_to_template(self, template_dict: Dict) -> ReportTemplate:
        """Convert dictionary to ReportTemplate object"""
        
        # Convert sections
        sections = []
        for section_dict in template_dict.get("sections", []):
            variables = [
                TemplateVariable(**var_dict) 
                for var_dict in section_dict.get("variables", [])
            ]
            
            section = TemplateSection(
                section_id=section_dict["section_id"],
                title=section_dict["title"],
                template_content=section_dict["template_content"],
                layout=SectionLayout(section_dict.get("layout", "full_width")),
                order=section_dict.get("order", 0),
                required=section_dict.get("required", True),
                conditional_logic=section_dict.get("conditional_logic"),
                variables=variables,
                css_classes=section_dict.get("css_classes", [])
            )
            sections.append(section)
        
        # Convert global variables
        global_variables = [
            TemplateVariable(**var_dict)
            for var_dict in template_dict.get("global_variables", [])
        ]
        
        # Convert branding
        branding = None
        if template_dict.get("branding"):
            branding = CustomBranding(**template_dict["branding"])
        
        return ReportTemplate(
            template_id=template_dict["template_id"],
            name=template_dict["name"],
            description=template_dict["description"],
            template_type=TemplateType(template_dict["template_type"]),
            output_format=OutputFormat(template_dict["output_format"]),
            sections=sections,
            global_variables=global_variables,
            branding=branding,
            metadata=template_dict.get("metadata", {}),
            created_at=datetime.fromisoformat(template_dict.get("created_at", datetime.utcnow().isoformat())),
            updated_at=datetime.fromisoformat(template_dict.get("updated_at", datetime.utcnow().isoformat())),
            version=template_dict.get("version", "1.0.0")
        )
    
    def list_templates(self) -> List[Dict[str, str]]:
        """List all available templates"""
        templates = []
        
        # From cache
        for template_id, template in self.template_cache.items():
            templates.append({
                "template_id": template_id,
                "name": template.name,
                "type": template.template_type.value,
                "format": template.output_format.value,
                "description": template.description
            })
        
        # From files (if not in cache)
        for template_file in self.templates_dir.glob("*.json"):
            template_id = template_file.stem
            if not self.cache_templates or template_id not in self.template_cache:
                try:
                    with open(template_file, 'r') as f:
                        template_dict = json.load(f)
                    
                    templates.append({
                        "template_id": template_id,
                        "name": template_dict.get("name", template_id),
                        "type": template_dict.get("template_type", "custom"),
                        "format": template_dict.get("output_format", "html"),
                        "description": template_dict.get("description", "")
                    })
                except Exception as e:
                    logger.warning(f"Failed to read template file {template_file}: {e}")
        
        return templates
    
    def delete_template(self, template_id: str) -> bool:
        """Delete template"""
        try:
            # Remove from cache
            if template_id in self.template_cache:
                del self.template_cache[template_id]
            
            # Remove file
            template_file = self.templates_dir / f"{template_id}.json"
            if template_file.exists():
                template_file.unlink()
            
            logger.info(f"Template {template_id} deleted successfully")
            return True
        
        except Exception as e:
            logger.error(f"Failed to delete template {template_id}: {e}")
            return False
    
    def render_template(
        self, 
        template_id: str, 
        context: Dict[str, Any]
    ) -> Optional[str]:
        """Render template with context"""
        
        if not self.template_engine:
            raise RuntimeError("Template engine not available")
        
        template = self.load_template(template_id)
        if not template:
            return None
        
        try:
            # Validate context
            validation_errors = template.validate_context(context)
            if validation_errors["missing_variables"] or validation_errors["invalid_values"]:
                logger.warning(f"Template validation errors: {validation_errors}")
            
            # Render template
            return self.template_engine.render_template(template, context)
        
        except Exception as e:
            logger.error(f"Template rendering failed: {e}")
            return None
    
    def clone_template(self, source_template_id: str, new_template_id: str, new_name: str) -> Optional[ReportTemplate]:
        """Clone existing template with new ID and name"""
        
        source_template = self.load_template(source_template_id)
        if not source_template:
            return None
        
        # Create cloned template
        cloned_template = ReportTemplate(
            template_id=new_template_id,
            name=new_name,
            description=f"Cloned from {source_template.name}",
            template_type=source_template.template_type,
            output_format=source_template.output_format,
            sections=source_template.sections.copy(),
            global_variables=source_template.global_variables.copy(),
            branding=source_template.branding,
            metadata=source_template.metadata.copy()
        )
        
        # Save cloned template
        if self.save_template(cloned_template):
            return cloned_template
        
        return None