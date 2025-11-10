"""
Report Generator

Core report generation engine that integrates with all masterTrade systems
to create comprehensive performance and analysis reports.
"""

import logging
import io
import base64
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Union, Any
from dataclasses import dataclass, field
from enum import Enum
import asyncio
import pandas as pd
import numpy as np
from pathlib import Path

# Report generation libraries
try:
    import matplotlib
    matplotlib.use('Agg')  # Use non-interactive backend
    import matplotlib.pyplot as plt
    import seaborn as sns
    from matplotlib.backends.backend_pdf import PdfPages
    import plotly.graph_objects as go
    import plotly.express as px
    from plotly.subplots import make_subplots
    import plotly.io as pio
    
    # Document generation
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from jinja2 import Template, Environment, FileSystemLoader
    
    DEPENDENCIES_AVAILABLE = True
except ImportError as e:
    logging.warning(f"Report generation dependencies not available: {e}")
    DEPENDENCIES_AVAILABLE = False

logger = logging.getLogger(__name__)


class ReportType(Enum):
    """Types of reports available"""
    DAILY_PERFORMANCE = "daily_performance"
    WEEKLY_SUMMARY = "weekly_summary"
    MONTHLY_REPORT = "monthly_report"
    QUARTERLY_REVIEW = "quarterly_review"
    STRATEGY_ANALYSIS = "strategy_analysis"
    PORTFOLIO_SUMMARY = "portfolio_summary"
    RISK_ASSESSMENT = "risk_assessment"
    TRANSACTION_COST_ANALYSIS = "transaction_cost_analysis"
    CORRELATION_ANALYSIS = "correlation_analysis"
    CUSTOM_REPORT = "custom_report"


class ReportFormat(Enum):
    """Available report formats"""
    PDF = "pdf"
    HTML = "html"
    EXCEL = "excel"
    CSV = "csv"
    JSON = "json"
    INTERACTIVE_HTML = "interactive_html"


class SectionType(Enum):
    """Report section types"""
    EXECUTIVE_SUMMARY = "executive_summary"
    PERFORMANCE_OVERVIEW = "performance_overview"
    STRATEGY_BREAKDOWN = "strategy_breakdown"
    RISK_METRICS = "risk_metrics"
    PORTFOLIO_ALLOCATION = "portfolio_allocation"
    TRANSACTION_COSTS = "transaction_costs"
    CORRELATION_ANALYSIS = "correlation_analysis"
    MARKET_COMMENTARY = "market_commentary"
    RECOMMENDATIONS = "recommendations"
    APPENDIX = "appendix"
    CHARTS_VISUALIZATIONS = "charts_visualizations"


@dataclass
class ReportSection:
    """Individual report section"""
    section_type: SectionType
    title: str
    content: str
    data: Optional[Dict] = None
    charts: Optional[List[str]] = None  # Chart file paths or base64 data
    tables: Optional[List[pd.DataFrame]] = None
    order: int = 0
    include_in_summary: bool = True
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "section_type": self.section_type.value,
            "title": self.title,
            "content": self.content,
            "data": self.data,
            "charts": self.charts,
            "tables": [df.to_dict() if df is not None else None for df in (self.tables or [])],
            "order": self.order,
            "include_in_summary": self.include_in_summary
        }


@dataclass
class ReportData:
    """Data container for report generation"""
    start_date: datetime
    end_date: datetime
    strategies: List[str]
    portfolio_data: Dict[str, Any] = field(default_factory=dict)
    performance_data: Dict[str, Any] = field(default_factory=dict)
    risk_data: Dict[str, Any] = field(default_factory=dict)
    transaction_data: Dict[str, Any] = field(default_factory=dict)
    correlation_data: Dict[str, Any] = field(default_factory=dict)
    market_data: Dict[str, Any] = field(default_factory=dict)
    custom_data: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "strategies": self.strategies,
            "portfolio_data": self.portfolio_data,
            "performance_data": self.performance_data,
            "risk_data": self.risk_data,
            "transaction_data": self.transaction_data,
            "correlation_data": self.correlation_data,
            "market_data": self.market_data,
            "custom_data": self.custom_data
        }


@dataclass
class GeneratedReport:
    """Generated report container"""
    report_id: str
    report_type: ReportType
    report_format: ReportFormat
    generated_at: datetime
    data_period: tuple
    content: bytes
    metadata: Dict[str, Any] = field(default_factory=dict)
    file_size: int = 0
    sections: List[ReportSection] = field(default_factory=list)
    
    def save_to_file(self, file_path: str):
        """Save report content to file"""
        with open(file_path, 'wb') as f:
            f.write(self.content)
    
    def get_base64_content(self) -> str:
        """Get report content as base64 string"""
        return base64.b64encode(self.content).decode('utf-8')
    
    def to_dict(self) -> Dict:
        """Convert to dictionary (excluding binary content)"""
        return {
            "report_id": self.report_id,
            "report_type": self.report_type.value,
            "report_format": self.report_format.value,
            "generated_at": self.generated_at.isoformat(),
            "data_period": [self.data_period[0].isoformat(), self.data_period[1].isoformat()],
            "metadata": self.metadata,
            "file_size": self.file_size,
            "sections_count": len(self.sections),
            "sections": [section.to_dict() for section in self.sections]
        }


class ReportGenerator:
    """
    Core report generation engine
    
    Integrates with all masterTrade systems to generate comprehensive reports
    in multiple formats with customizable templates and visualizations.
    """
    
    def __init__(self, template_dir: str = "templates", output_dir: str = "reports"):
        self.template_dir = Path(template_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
        # Initialize Jinja2 environment
        if self.template_dir.exists():
            self.jinja_env = Environment(loader=FileSystemLoader(str(self.template_dir)))
        else:
            self.jinja_env = Environment(loader=FileSystemLoader("."))
        
        # Report generation statistics
        self.generation_stats = {
            "reports_generated": 0,
            "total_generation_time": 0,
            "format_counts": {},
            "type_counts": {}
        }
    
    async def generate_report(
        self,
        report_type: ReportType,
        report_format: ReportFormat,
        report_data: ReportData,
        template_name: Optional[str] = None,
        custom_sections: Optional[List[ReportSection]] = None,
        branding: Optional[Dict] = None
    ) -> GeneratedReport:
        """
        Generate a comprehensive report
        """
        start_time = datetime.utcnow()
        
        try:
            # Generate unique report ID
            report_id = f"{report_type.value}_{report_format.value}_{int(start_time.timestamp())}"
            
            # Collect and process data
            processed_data = await self._process_report_data(report_data, report_type)
            
            # Generate report sections
            sections = await self._generate_report_sections(
                report_type, processed_data, custom_sections
            )
            
            # Generate visualizations
            charts = await self._generate_visualizations(processed_data, sections)
            
            # Create report content based on format
            if report_format == ReportFormat.PDF:
                content = await self._generate_pdf_report(sections, charts, branding)
            elif report_format == ReportFormat.HTML:
                content = await self._generate_html_report(sections, charts, template_name, branding)
            elif report_format == ReportFormat.INTERACTIVE_HTML:
                content = await self._generate_interactive_html_report(sections, charts, branding)
            elif report_format == ReportFormat.EXCEL:
                content = await self._generate_excel_report(sections, processed_data)
            elif report_format == ReportFormat.CSV:
                content = await self._generate_csv_report(processed_data)
            elif report_format == ReportFormat.JSON:
                content = await self._generate_json_report(sections, processed_data)
            else:
                raise ValueError(f"Unsupported report format: {report_format}")
            
            # Create generated report
            generated_report = GeneratedReport(
                report_id=report_id,
                report_type=report_type,
                report_format=report_format,
                generated_at=start_time,
                data_period=(report_data.start_date, report_data.end_date),
                content=content,
                metadata={
                    "strategies": report_data.strategies,
                    "generation_time_seconds": (datetime.utcnow() - start_time).total_seconds(),
                    "template_used": template_name,
                    "custom_branding": branding is not None
                },
                file_size=len(content),
                sections=sections
            )
            
            # Update statistics
            self._update_generation_stats(report_type, report_format, start_time)
            
            logger.info(f"Generated report {report_id} in {(datetime.utcnow() - start_time).total_seconds():.2f}s")
            
            return generated_report
        
        except Exception as e:
            logger.error(f"Report generation failed: {str(e)}")
            raise
    
    async def _process_report_data(self, report_data: ReportData, report_type: ReportType) -> Dict[str, Any]:
        """
        Process and aggregate data for report generation
        """
        processed_data = {
            "report_metadata": {
                "start_date": report_data.start_date,
                "end_date": report_data.end_date,
                "period_days": (report_data.end_date - report_data.start_date).days,
                "strategies": report_data.strategies,
                "report_type": report_type.value
            }
        }
        
        # Process performance data
        if report_data.performance_data:
            processed_data["performance_summary"] = self._process_performance_data(
                report_data.performance_data
            )
        
        # Process portfolio data
        if report_data.portfolio_data:
            processed_data["portfolio_summary"] = self._process_portfolio_data(
                report_data.portfolio_data
            )
        
        # Process risk data
        if report_data.risk_data:
            processed_data["risk_summary"] = self._process_risk_data(
                report_data.risk_data
            )
        
        # Process transaction cost data
        if report_data.transaction_data:
            processed_data["transaction_summary"] = self._process_transaction_data(
                report_data.transaction_data
            )
        
        # Process correlation data
        if report_data.correlation_data:
            processed_data["correlation_summary"] = self._process_correlation_data(
                report_data.correlation_data
            )
        
        # Process market data
        if report_data.market_data:
            processed_data["market_summary"] = self._process_market_data(
                report_data.market_data
            )
        
        return processed_data
    
    def _process_performance_data(self, performance_data: Dict) -> Dict:
        """Process performance data for reporting"""
        try:
            summary = {
                "total_return": performance_data.get("total_return", 0.0),
                "annualized_return": performance_data.get("annualized_return", 0.0),
                "volatility": performance_data.get("volatility", 0.0),
                "sharpe_ratio": performance_data.get("sharpe_ratio", 0.0),
                "max_drawdown": performance_data.get("max_drawdown", 0.0),
                "win_rate": performance_data.get("win_rate", 0.0),
                "total_trades": performance_data.get("total_trades", 0),
                "profit_factor": performance_data.get("profit_factor", 0.0)
            }
            
            # Add strategy-specific performance if available
            if "strategy_performance" in performance_data:
                summary["strategy_breakdown"] = performance_data["strategy_performance"]
            
            # Add time series data if available
            if "returns_series" in performance_data:
                returns = performance_data["returns_series"]
                if isinstance(returns, (list, pd.Series)):
                    summary["cumulative_returns"] = np.cumprod(1 + np.array(returns)).tolist()
            
            return summary
        
        except Exception as e:
            logger.warning(f"Performance data processing failed: {e}")
            return {"error": str(e)}
    
    def _process_portfolio_data(self, portfolio_data: Dict) -> Dict:
        """Process portfolio data for reporting"""
        try:
            summary = {
                "total_value": portfolio_data.get("total_value", 0.0),
                "cash_balance": portfolio_data.get("cash_balance", 0.0),
                "positions_count": portfolio_data.get("positions_count", 0),
                "allocation": portfolio_data.get("allocation", {}),
                "concentration_risk": portfolio_data.get("concentration_risk", 0.0),
                "diversification_score": portfolio_data.get("diversification_score", 0.0)
            }
            
            # Add position details if available
            if "positions" in portfolio_data:
                positions = portfolio_data["positions"]
                summary["top_positions"] = sorted(
                    positions.items(), 
                    key=lambda x: abs(x[1].get("value", 0)), 
                    reverse=True
                )[:10]  # Top 10 positions
            
            return summary
        
        except Exception as e:
            logger.warning(f"Portfolio data processing failed: {e}")
            return {"error": str(e)}
    
    def _process_risk_data(self, risk_data: Dict) -> Dict:
        """Process risk data for reporting"""
        try:
            summary = {
                "portfolio_var": risk_data.get("portfolio_var", 0.0),
                "component_var": risk_data.get("component_var", {}),
                "expected_shortfall": risk_data.get("expected_shortfall", 0.0),
                "beta": risk_data.get("beta", 0.0),
                "correlation_risk": risk_data.get("correlation_risk", 0.0),
                "concentration_risk": risk_data.get("concentration_risk", 0.0)
            }
            
            # Add risk attribution if available
            if "risk_attribution" in risk_data:
                summary["risk_contributions"] = risk_data["risk_attribution"]
            
            return summary
        
        except Exception as e:
            logger.warning(f"Risk data processing failed: {e}")
            return {"error": str(e)}
    
    def _process_transaction_data(self, transaction_data: Dict) -> Dict:
        """Process transaction cost data for reporting"""
        try:
            summary = {
                "total_transaction_costs": transaction_data.get("total_costs", 0.0),
                "cost_per_share": transaction_data.get("cost_per_share", 0.0),
                "market_impact": transaction_data.get("market_impact", 0.0),
                "implementation_shortfall": transaction_data.get("implementation_shortfall", 0.0),
                "execution_efficiency": transaction_data.get("execution_efficiency", 0.0)
            }
            
            # Add cost breakdown if available
            if "cost_breakdown" in transaction_data:
                summary["cost_components"] = transaction_data["cost_breakdown"]
            
            return summary
        
        except Exception as e:
            logger.warning(f"Transaction data processing failed: {e}")
            return {"error": str(e)}
    
    def _process_correlation_data(self, correlation_data: Dict) -> Dict:
        """Process correlation data for reporting"""
        try:
            summary = {
                "average_correlation": correlation_data.get("average_correlation", 0.0),
                "correlation_range": correlation_data.get("correlation_range", [0.0, 0.0]),
                "highly_correlated_pairs": correlation_data.get("highly_correlated_pairs", []),
                "diversification_benefit": correlation_data.get("diversification_benefit", 0.0)
            }
            
            # Add correlation matrix if available
            if "correlation_matrix" in correlation_data:
                summary["correlation_matrix"] = correlation_data["correlation_matrix"]
            
            return summary
        
        except Exception as e:
            logger.warning(f"Correlation data processing failed: {e}")
            return {"error": str(e)}
    
    def _process_market_data(self, market_data: Dict) -> Dict:
        """Process market data for reporting"""
        try:
            summary = {
                "market_return": market_data.get("market_return", 0.0),
                "market_volatility": market_data.get("market_volatility", 0.0),
                "market_trend": market_data.get("market_trend", "neutral"),
                "sector_performance": market_data.get("sector_performance", {}),
                "economic_indicators": market_data.get("economic_indicators", {})
            }
            
            return summary
        
        except Exception as e:
            logger.warning(f"Market data processing failed: {e}")
            return {"error": str(e)}
    
    async def _generate_report_sections(
        self,
        report_type: ReportType,
        processed_data: Dict,
        custom_sections: Optional[List[ReportSection]] = None
    ) -> List[ReportSection]:
        """
        Generate report sections based on report type and data
        """
        sections = []
        
        if custom_sections:
            sections.extend(custom_sections)
        
        # Generate standard sections based on report type
        if report_type in [ReportType.DAILY_PERFORMANCE, ReportType.WEEKLY_SUMMARY, ReportType.MONTHLY_REPORT]:
            sections.extend(await self._generate_performance_sections(processed_data))
        
        if report_type == ReportType.STRATEGY_ANALYSIS:
            sections.extend(await self._generate_strategy_sections(processed_data))
        
        if report_type == ReportType.PORTFOLIO_SUMMARY:
            sections.extend(await self._generate_portfolio_sections(processed_data))
        
        if report_type == ReportType.RISK_ASSESSMENT:
            sections.extend(await self._generate_risk_sections(processed_data))
        
        if report_type == ReportType.TRANSACTION_COST_ANALYSIS:
            sections.extend(await self._generate_transaction_sections(processed_data))
        
        if report_type == ReportType.CORRELATION_ANALYSIS:
            sections.extend(await self._generate_correlation_sections(processed_data))
        
        # Sort sections by order
        sections.sort(key=lambda x: x.order)
        
        return sections
    
    async def _generate_performance_sections(self, data: Dict) -> List[ReportSection]:
        """Generate performance-related sections"""
        sections = []
        
        if "performance_summary" in data:
            perf_data = data["performance_summary"]
            
            # Executive Summary
            summary_content = f"""
            Portfolio Performance Summary
            
            Total Return: {perf_data.get('total_return', 0):.2%}
            Annualized Return: {perf_data.get('annualized_return', 0):.2%}
            Volatility: {perf_data.get('volatility', 0):.2%}
            Sharpe Ratio: {perf_data.get('sharpe_ratio', 0):.2f}
            Maximum Drawdown: {perf_data.get('max_drawdown', 0):.2%}
            
            The portfolio demonstrated {'strong' if perf_data.get('sharpe_ratio', 0) > 1 else 'moderate' if perf_data.get('sharpe_ratio', 0) > 0.5 else 'weak'} 
            risk-adjusted performance during the reporting period.
            """
            
            sections.append(ReportSection(
                section_type=SectionType.EXECUTIVE_SUMMARY,
                title="Executive Summary",
                content=summary_content,
                data=perf_data,
                order=1
            ))
            
            # Performance Overview
            overview_content = f"""
            Detailed Performance Analysis
            
            Trading Activity:
            - Total Trades: {perf_data.get('total_trades', 0):,}
            - Win Rate: {perf_data.get('win_rate', 0):.1%}
            - Profit Factor: {perf_data.get('profit_factor', 0):.2f}
            
            Risk Metrics:
            - Volatility: {perf_data.get('volatility', 0):.2%}
            - Maximum Drawdown: {perf_data.get('max_drawdown', 0):.2%}
            
            The portfolio's risk-return profile indicates {'excellent' if perf_data.get('sharpe_ratio', 0) > 1.5 else 'good' if perf_data.get('sharpe_ratio', 0) > 1.0 else 'acceptable'} 
            performance relative to the risk taken.
            """
            
            sections.append(ReportSection(
                section_type=SectionType.PERFORMANCE_OVERVIEW,
                title="Performance Overview",
                content=overview_content,
                data=perf_data,
                order=2
            ))
        
        return sections
    
    async def _generate_strategy_sections(self, data: Dict) -> List[ReportSection]:
        """Generate strategy analysis sections"""
        sections = []
        
        if "performance_summary" in data and "strategy_breakdown" in data["performance_summary"]:
            strategy_data = data["performance_summary"]["strategy_breakdown"]
            
            content = "Strategy Performance Breakdown\n\n"
            for strategy, metrics in strategy_data.items():
                content += f"{strategy}:\n"
                content += f"  - Return: {metrics.get('return', 0):.2%}\n"
                content += f"  - Sharpe: {metrics.get('sharpe', 0):.2f}\n"
                content += f"  - Max DD: {metrics.get('max_drawdown', 0):.2%}\n\n"
            
            sections.append(ReportSection(
                section_type=SectionType.STRATEGY_BREAKDOWN,
                title="Strategy Analysis",
                content=content,
                data=strategy_data,
                order=3
            ))
        
        return sections
    
    async def _generate_portfolio_sections(self, data: Dict) -> List[ReportSection]:
        """Generate portfolio-related sections"""
        sections = []
        
        if "portfolio_summary" in data:
            portfolio_data = data["portfolio_summary"]
            
            content = f"""
            Portfolio Composition and Risk
            
            Total Portfolio Value: ${portfolio_data.get('total_value', 0):,.2f}
            Cash Balance: ${portfolio_data.get('cash_balance', 0):,.2f}
            Number of Positions: {portfolio_data.get('positions_count', 0)}
            
            Risk Metrics:
            - Concentration Risk: {portfolio_data.get('concentration_risk', 0):.2f}
            - Diversification Score: {portfolio_data.get('diversification_score', 0):.2f}
            
            The portfolio shows {'high' if portfolio_data.get('concentration_risk', 0) > 0.5 else 'moderate' if portfolio_data.get('concentration_risk', 0) > 0.3 else 'low'} concentration risk.
            """
            
            sections.append(ReportSection(
                section_type=SectionType.PORTFOLIO_ALLOCATION,
                title="Portfolio Analysis",
                content=content,
                data=portfolio_data,
                order=2
            ))
        
        return sections
    
    async def _generate_risk_sections(self, data: Dict) -> List[ReportSection]:
        """Generate risk assessment sections"""
        sections = []
        
        if "risk_summary" in data:
            risk_data = data["risk_summary"]
            
            content = f"""
            Risk Assessment
            
            Value at Risk (95%): {risk_data.get('portfolio_var', 0):.2%}
            Expected Shortfall: {risk_data.get('expected_shortfall', 0):.2%}
            Portfolio Beta: {risk_data.get('beta', 0):.2f}
            
            Risk Decomposition:
            - Correlation Risk: {risk_data.get('correlation_risk', 0):.2%}
            - Concentration Risk: {risk_data.get('concentration_risk', 0):.2%}
            
            The portfolio's risk profile is {'conservative' if risk_data.get('portfolio_var', 0) < 0.02 else 'moderate' if risk_data.get('portfolio_var', 0) < 0.05 else 'aggressive'}.
            """
            
            sections.append(ReportSection(
                section_type=SectionType.RISK_METRICS,
                title="Risk Assessment",
                content=content,
                data=risk_data,
                order=4
            ))
        
        return sections
    
    async def _generate_transaction_sections(self, data: Dict) -> List[ReportSection]:
        """Generate transaction cost analysis sections"""
        sections = []
        
        if "transaction_summary" in data:
            tca_data = data["transaction_summary"]
            
            content = f"""
            Transaction Cost Analysis
            
            Total Transaction Costs: {tca_data.get('total_transaction_costs', 0):.2%}
            Cost per Share: ${tca_data.get('cost_per_share', 0):.4f}
            Market Impact: {tca_data.get('market_impact', 0):.2%}
            Implementation Shortfall: {tca_data.get('implementation_shortfall', 0):.2%}
            Execution Efficiency: {tca_data.get('execution_efficiency', 0):.1%}
            
            Transaction cost efficiency is {'excellent' if tca_data.get('execution_efficiency', 0) > 90 else 'good' if tca_data.get('execution_efficiency', 0) > 80 else 'needs improvement'}.
            """
            
            sections.append(ReportSection(
                section_type=SectionType.TRANSACTION_COSTS,
                title="Transaction Cost Analysis",
                content=content,
                data=tca_data,
                order=5
            ))
        
        return sections
    
    async def _generate_correlation_sections(self, data: Dict) -> List[ReportSection]:
        """Generate correlation analysis sections"""
        sections = []
        
        if "correlation_summary" in data:
            corr_data = data["correlation_summary"]
            
            content = f"""
            Strategy Correlation Analysis
            
            Average Correlation: {corr_data.get('average_correlation', 0):.2f}
            Correlation Range: {corr_data.get('correlation_range', [0, 0])[0]:.2f} to {corr_data.get('correlation_range', [0, 0])[1]:.2f}
            Diversification Benefit: {corr_data.get('diversification_benefit', 0):.2%}
            
            High Correlation Pairs: {len(corr_data.get('highly_correlated_pairs', []))}
            
            The portfolio shows {'excellent' if corr_data.get('average_correlation', 1) < 0.3 else 'good' if corr_data.get('average_correlation', 1) < 0.5 else 'limited'} diversification.
            """
            
            sections.append(ReportSection(
                section_type=SectionType.CORRELATION_ANALYSIS,
                title="Correlation Analysis",
                content=content,
                data=corr_data,
                order=6
            ))
        
        return sections
    
    async def _generate_visualizations(self, data: Dict, sections: List[ReportSection]) -> Dict[str, str]:
        """
        Generate charts and visualizations for the report
        """
        charts = {}
        
        if not DEPENDENCIES_AVAILABLE:
            logger.warning("Visualization libraries not available, skipping chart generation")
            return charts
        
        try:
            # Performance chart
            if "performance_summary" in data:
                perf_data = data["performance_summary"]
                if "cumulative_returns" in perf_data:
                    chart_path = await self._create_performance_chart(perf_data["cumulative_returns"])
                    charts["performance_chart"] = chart_path
            
            # Portfolio allocation chart
            if "portfolio_summary" in data:
                portfolio_data = data["portfolio_summary"]
                if "allocation" in portfolio_data:
                    chart_path = await self._create_allocation_chart(portfolio_data["allocation"])
                    charts["allocation_chart"] = chart_path
            
            # Risk metrics chart
            if "risk_summary" in data:
                risk_data = data["risk_summary"]
                chart_path = await self._create_risk_chart(risk_data)
                charts["risk_chart"] = chart_path
            
            # Correlation heatmap
            if "correlation_summary" in data:
                corr_data = data["correlation_summary"]
                if "correlation_matrix" in corr_data:
                    chart_path = await self._create_correlation_heatmap(corr_data["correlation_matrix"])
                    charts["correlation_heatmap"] = chart_path
        
        except Exception as e:
            logger.error(f"Chart generation failed: {e}")
        
        return charts
    
    async def _create_performance_chart(self, cumulative_returns: List[float]) -> str:
        """Create cumulative performance chart"""
        plt.figure(figsize=(10, 6))
        plt.plot(cumulative_returns, linewidth=2, color='#2E86AB')
        plt.title('Cumulative Performance', fontsize=16, fontweight='bold')
        plt.xlabel('Time Period')
        plt.ylabel('Cumulative Return')
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        
        # Save to base64
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', dpi=300, bbox_inches='tight')
        buffer.seek(0)
        chart_base64 = base64.b64encode(buffer.getvalue()).decode()
        plt.close()
        
        return f"data:image/png;base64,{chart_base64}"
    
    async def _create_allocation_chart(self, allocation: Dict[str, float]) -> str:
        """Create portfolio allocation pie chart"""
        if not allocation:
            return ""
        
        plt.figure(figsize=(8, 8))
        labels = list(allocation.keys())
        sizes = list(allocation.values())
        colors = plt.cm.Set3(np.linspace(0, 1, len(labels)))
        
        plt.pie(sizes, labels=labels, colors=colors, autopct='%1.1f%%', startangle=90)
        plt.title('Portfolio Allocation', fontsize=16, fontweight='bold')
        plt.axis('equal')
        
        # Save to base64
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', dpi=300, bbox_inches='tight')
        buffer.seek(0)
        chart_base64 = base64.b64encode(buffer.getvalue()).decode()
        plt.close()
        
        return f"data:image/png;base64,{chart_base64}"
    
    async def _create_risk_chart(self, risk_data: Dict) -> str:
        """Create risk metrics bar chart"""
        plt.figure(figsize=(10, 6))
        
        metrics = ['VaR', 'Expected Shortfall', 'Beta', 'Correlation Risk']
        values = [
            abs(risk_data.get('portfolio_var', 0)) * 100,
            abs(risk_data.get('expected_shortfall', 0)) * 100,
            abs(risk_data.get('beta', 0)),
            abs(risk_data.get('correlation_risk', 0)) * 100
        ]
        
        colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4']
        bars = plt.bar(metrics, values, color=colors)
        
        plt.title('Risk Metrics', fontsize=16, fontweight='bold')
        plt.ylabel('Value')
        plt.xticks(rotation=45)
        
        # Add value labels on bars
        for bar, value in zip(bars, values):
            plt.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.1,
                    f'{value:.2f}', ha='center', va='bottom')
        
        plt.tight_layout()
        
        # Save to base64
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', dpi=300, bbox_inches='tight')
        buffer.seek(0)
        chart_base64 = base64.b64encode(buffer.getvalue()).decode()
        plt.close()
        
        return f"data:image/png;base64,{chart_base64}"
    
    async def _create_correlation_heatmap(self, correlation_matrix: Dict) -> str:
        """Create correlation heatmap"""
        if not correlation_matrix:
            return ""
        
        # Convert to DataFrame if needed
        if isinstance(correlation_matrix, dict):
            df = pd.DataFrame(correlation_matrix)
        else:
            df = correlation_matrix
        
        plt.figure(figsize=(10, 8))
        sns.heatmap(df, annot=True, cmap='RdYlBu_r', center=0, 
                   square=True, cbar_kws={"shrink": .8})
        plt.title('Strategy Correlation Matrix', fontsize=16, fontweight='bold')
        plt.tight_layout()
        
        # Save to base64
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', dpi=300, bbox_inches='tight')
        buffer.seek(0)
        chart_base64 = base64.b64encode(buffer.getvalue()).decode()
        plt.close()
        
        return f"data:image/png;base64,{chart_base64}"
    
    async def _generate_pdf_report(
        self, 
        sections: List[ReportSection], 
        charts: Dict[str, str],
        branding: Optional[Dict] = None
    ) -> bytes:
        """Generate PDF report"""
        if not DEPENDENCIES_AVAILABLE:
            raise ValueError("PDF generation dependencies not available")
        
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        story = []
        styles = getSampleStyleSheet()
        
        # Custom styles
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            spaceAfter=30,
            textColor=colors.HexColor('#2E86AB') if not branding else colors.HexColor(branding.get('primary_color', '#2E86AB'))
        )
        
        # Add title
        story.append(Paragraph("Portfolio Performance Report", title_style))
        story.append(Spacer(1, 20))
        
        # Add sections
        for section in sections:
            # Section title
            story.append(Paragraph(section.title, styles['Heading2']))
            story.append(Spacer(1, 12))
            
            # Section content
            content_paragraphs = section.content.split('\n\n')
            for para in content_paragraphs:
                if para.strip():
                    story.append(Paragraph(para.strip().replace('\n', '<br/>'), styles['Normal']))
                    story.append(Spacer(1, 6))
            
            # Add charts if available
            if section.charts:
                for chart_key in section.charts:
                    if chart_key in charts:
                        # For PDF, we would need to convert base64 to image
                        # This is a simplified version
                        story.append(Spacer(1, 12))
            
            story.append(Spacer(1, 20))
        
        # Build PDF
        doc.build(story)
        buffer.seek(0)
        
        return buffer.getvalue()
    
    async def _generate_html_report(
        self,
        sections: List[ReportSection],
        charts: Dict[str, str],
        template_name: Optional[str] = None,
        branding: Optional[Dict] = None
    ) -> bytes:
        """Generate HTML report"""
        
        # Default HTML template
        html_template = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>{{ title }}</title>
            <style>
                body { 
                    font-family: Arial, sans-serif; 
                    margin: 40px; 
                    color: #333;
                    line-height: 1.6;
                }
                .header { 
                    color: {{ primary_color }}; 
                    border-bottom: 3px solid {{ primary_color }};
                    padding-bottom: 10px;
                    margin-bottom: 30px;
                }
                .section { 
                    margin-bottom: 30px; 
                    padding: 20px;
                    border-left: 4px solid {{ accent_color }};
                    background-color: #f9f9f9;
                }
                .chart { 
                    text-align: center; 
                    margin: 20px 0; 
                }
                .chart img { 
                    max-width: 100%; 
                    height: auto; 
                }
                pre { 
                    background-color: #f5f5f5; 
                    padding: 15px; 
                    border-radius: 5px;
                    white-space: pre-wrap;
                }
            </style>
        </head>
        <body>
            <div class="header">
                <h1>{{ title }}</h1>
                <p>Generated on {{ generated_at }}</p>
            </div>
            
            {% for section in sections %}
            <div class="section">
                <h2>{{ section.title }}</h2>
                <pre>{{ section.content }}</pre>
                
                {% if section.charts %}
                    {% for chart_key in section.charts %}
                        {% if chart_key in charts %}
                        <div class="chart">
                            <img src="{{ charts[chart_key] }}" alt="{{ chart_key }}">
                        </div>
                        {% endif %}
                    {% endfor %}
                {% endif %}
            </div>
            {% endfor %}
        </body>
        </html>
        """
        
        template = self.jinja_env.from_string(html_template)
        
        # Template variables
        template_vars = {
            "title": "Portfolio Performance Report",
            "generated_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
            "sections": sections,
            "charts": charts,
            "primary_color": branding.get('primary_color', '#2E86AB') if branding else '#2E86AB',
            "accent_color": branding.get('accent_color', '#4ECDC4') if branding else '#4ECDC4'
        }
        
        html_content = template.render(**template_vars)
        return html_content.encode('utf-8')
    
    async def _generate_interactive_html_report(
        self,
        sections: List[ReportSection],
        charts: Dict[str, str],
        branding: Optional[Dict] = None
    ) -> bytes:
        """Generate interactive HTML report with JavaScript charts"""
        
        # This would use Plotly for interactive charts
        # Simplified version for now
        html_content = await self._generate_html_report(sections, charts, None, branding)
        return html_content
    
    async def _generate_excel_report(
        self,
        sections: List[ReportSection],
        processed_data: Dict
    ) -> bytes:
        """Generate Excel report"""
        
        buffer = io.BytesIO()
        
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            # Summary sheet
            summary_data = []
            for section in sections:
                if section.data:
                    summary_data.append({
                        "Section": section.title,
                        "Type": section.section_type.value,
                        "Order": section.order
                    })
            
            if summary_data:
                summary_df = pd.DataFrame(summary_data)
                summary_df.to_excel(writer, sheet_name='Summary', index=False)
            
            # Data sheets
            for key, data in processed_data.items():
                if isinstance(data, dict) and data:
                    try:
                        df = pd.DataFrame([data])
                        sheet_name = key.replace('_', ' ').title()[:31]  # Excel sheet name limit
                        df.to_excel(writer, sheet_name=sheet_name, index=False)
                    except Exception as e:
                        logger.warning(f"Failed to create Excel sheet for {key}: {e}")
        
        buffer.seek(0)
        return buffer.getvalue()
    
    async def _generate_csv_report(self, processed_data: Dict) -> bytes:
        """Generate CSV report"""
        
        # Flatten all data into a single DataFrame
        flattened_data = {}
        
        for category, data in processed_data.items():
            if isinstance(data, dict):
                for key, value in data.items():
                    flattened_data[f"{category}_{key}"] = value
        
        if flattened_data:
            df = pd.DataFrame([flattened_data])
            return df.to_csv(index=False).encode('utf-8')
        
        return b"No data available for CSV export"
    
    async def _generate_json_report(
        self,
        sections: List[ReportSection],
        processed_data: Dict
    ) -> bytes:
        """Generate JSON report"""
        
        report_json = {
            "generated_at": datetime.utcnow().isoformat(),
            "sections": [section.to_dict() for section in sections],
            "processed_data": processed_data
        }
        
        return json.dumps(report_json, indent=2, default=str).encode('utf-8')
    
    def _update_generation_stats(self, report_type: ReportType, report_format: ReportFormat, start_time: datetime):
        """Update report generation statistics"""
        generation_time = (datetime.utcnow() - start_time).total_seconds()
        
        self.generation_stats["reports_generated"] += 1
        self.generation_stats["total_generation_time"] += generation_time
        
        # Format counts
        format_key = report_format.value
        self.generation_stats["format_counts"][format_key] = self.generation_stats["format_counts"].get(format_key, 0) + 1
        
        # Type counts
        type_key = report_type.value
        self.generation_stats["type_counts"][type_key] = self.generation_stats["type_counts"].get(type_key, 0) + 1
    
    def get_generation_statistics(self) -> Dict[str, Any]:
        """Get report generation statistics"""
        avg_generation_time = (
            self.generation_stats["total_generation_time"] / self.generation_stats["reports_generated"]
            if self.generation_stats["reports_generated"] > 0 else 0
        )
        
        return {
            **self.generation_stats,
            "average_generation_time": avg_generation_time
        }