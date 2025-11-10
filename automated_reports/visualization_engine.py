"""
Visualization Engine

Advanced chart and visualization generation system for reports
with support for interactive charts, dashboards, and custom styling.
"""

import logging
import json
import base64
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple, Union
from dataclasses import dataclass, field
from enum import Enum
from io import BytesIO
import numpy as np
import pandas as pd

try:
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    import seaborn as sns
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    logging.warning("Matplotlib/Seaborn not available")

try:
    import plotly.graph_objects as go
    import plotly.express as px
    from plotly.subplots import make_subplots
    import plotly.io as pio
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False
    logging.warning("Plotly not available for interactive charts")

try:
    from bokeh.plotting import figure, output_file, save
    from bokeh.models import HoverTool, ColumnDataSource
    from bokeh.layouts import gridplot, row, column
    from bokeh.embed import json_item
    BOKEH_AVAILABLE = True
except ImportError:
    BOKEH_AVAILABLE = False
    logging.warning("Bokeh not available for interactive charts")

logger = logging.getLogger(__name__)


class ChartType(Enum):
    """Supported chart types"""
    LINE = "line"
    BAR = "bar"
    AREA = "area"
    PIE = "pie"
    SCATTER = "scatter"
    HEATMAP = "heatmap"
    HISTOGRAM = "histogram"
    BOX = "box"
    VIOLIN = "violin"
    CANDLESTICK = "candlestick"
    GAUGE = "gauge"
    TREEMAP = "treemap"
    FUNNEL = "funnel"
    WATERFALL = "waterfall"
    SANKEY = "sankey"


class ChartStyle(Enum):
    """Chart styling themes"""
    DEFAULT = "default"
    CORPORATE = "corporate"
    MODERN = "modern"
    DARK = "dark"
    MINIMAL = "minimal"
    COLORFUL = "colorful"
    PROFESSIONAL = "professional"


class OutputFormat(Enum):
    """Chart output formats"""
    PNG = "png"
    SVG = "svg"
    PDF = "pdf"
    HTML = "html"
    JSON = "json"
    BASE64 = "base64"


@dataclass
class ChartConfig:
    """Chart configuration"""
    chart_type: ChartType
    title: str
    width: int = 800
    height: int = 600
    style: ChartStyle = ChartStyle.DEFAULT
    color_palette: Optional[List[str]] = None
    interactive: bool = False
    show_legend: bool = True
    show_grid: bool = True
    x_axis_label: Optional[str] = None
    y_axis_label: Optional[str] = None
    x_axis_rotation: int = 0
    y_axis_format: Optional[str] = None
    custom_styling: Dict[str, Any] = field(default_factory=dict)
    
    def get_color_palette(self) -> List[str]:
        """Get color palette for the chart"""
        if self.color_palette:
            return self.color_palette
        
        # Default palettes by style
        palettes = {
            ChartStyle.DEFAULT: ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd'],
            ChartStyle.CORPORATE: ['#2E86AB', '#A23B72', '#F18F01', '#C73E1D', '#4B4B4D'],
            ChartStyle.MODERN: ['#4ECDC4', '#44A08D', '#093637', '#C02425', '#F0B27A'],
            ChartStyle.DARK: ['#BB86FC', '#03DAC6', '#CF6679', '#018786', '#3700B3'],
            ChartStyle.MINIMAL: ['#333333', '#666666', '#999999', '#CCCCCC', '#EEEEEE'],
            ChartStyle.COLORFUL: ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7'],
            ChartStyle.PROFESSIONAL: ['#2E86AB', '#4ECDC4', '#FF6B6B', '#F38B4A', '#6A4C93']
        }
        
        return palettes.get(self.style, palettes[ChartStyle.DEFAULT])


@dataclass
class ChartData:
    """Chart data container"""
    data: Dict[str, Any]
    x_column: Optional[str] = None
    y_columns: Optional[List[str]] = None
    category_column: Optional[str] = None
    value_column: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dataframe(self) -> pd.DataFrame:
        """Convert data to pandas DataFrame"""
        if isinstance(self.data, pd.DataFrame):
            return self.data
        elif isinstance(self.data, dict):
            return pd.DataFrame(self.data)
        elif isinstance(self.data, list):
            return pd.DataFrame(self.data)
        else:
            raise ValueError("Unsupported data format")


@dataclass
class GeneratedChart:
    """Generated chart result"""
    chart_id: str
    chart_type: ChartType
    output_format: OutputFormat
    content: str  # Base64, HTML, or file path
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "chart_id": self.chart_id,
            "chart_type": self.chart_type.value,
            "output_format": self.output_format.value,
            "content": self.content,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat()
        }


class MatplotlibChartEngine:
    """Matplotlib-based chart generation engine"""
    
    def __init__(self):
        if not MATPLOTLIB_AVAILABLE:
            raise ImportError("Matplotlib not available")
        
        # Set up styling
        plt.style.use('default')
        sns.set_palette("husl")
    
    def create_chart(
        self, 
        chart_data: ChartData, 
        config: ChartConfig, 
        output_format: OutputFormat = OutputFormat.BASE64
    ) -> GeneratedChart:
        """Create chart using matplotlib"""
        
        df = chart_data.to_dataframe()
        
        # Create figure
        fig = plt.figure(figsize=(config.width/100, config.height/100), dpi=100)
        
        # Apply styling
        self._apply_style(fig, config)
        
        # Generate chart based on type
        if config.chart_type == ChartType.LINE:
            self._create_line_chart(df, config, chart_data)
        elif config.chart_type == ChartType.BAR:
            self._create_bar_chart(df, config, chart_data)
        elif config.chart_type == ChartType.AREA:
            self._create_area_chart(df, config, chart_data)
        elif config.chart_type == ChartType.PIE:
            self._create_pie_chart(df, config, chart_data)
        elif config.chart_type == ChartType.SCATTER:
            self._create_scatter_chart(df, config, chart_data)
        elif config.chart_type == ChartType.HEATMAP:
            self._create_heatmap(df, config, chart_data)
        elif config.chart_type == ChartType.HISTOGRAM:
            self._create_histogram(df, config, chart_data)
        elif config.chart_type == ChartType.BOX:
            self._create_box_plot(df, config, chart_data)
        else:
            raise ValueError(f"Unsupported chart type: {config.chart_type}")
        
        # Set title and labels
        plt.title(config.title, fontsize=16, fontweight='bold')
        
        if config.x_axis_label:
            plt.xlabel(config.x_axis_label)
        if config.y_axis_label:
            plt.ylabel(config.y_axis_label)
        
        # Configure grid and legend
        if config.show_grid:
            plt.grid(True, alpha=0.3)
        
        if config.show_legend:
            plt.legend()
        
        # Adjust layout
        plt.tight_layout()
        
        # Generate output
        content = self._generate_output(fig, output_format)
        
        plt.close(fig)
        
        chart_id = f"chart_{datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')}"
        
        return GeneratedChart(
            chart_id=chart_id,
            chart_type=config.chart_type,
            output_format=output_format,
            content=content,
            metadata={
                "title": config.title,
                "width": config.width,
                "height": config.height,
                "style": config.style.value
            }
        )
    
    def _apply_style(self, fig: Figure, config: ChartConfig):
        """Apply styling to figure"""
        
        colors = config.get_color_palette()
        
        # Set color cycle
        plt.rcParams['axes.prop_cycle'] = plt.cycler(color=colors)
        
        # Style-specific configurations
        if config.style == ChartStyle.DARK:
            fig.patch.set_facecolor('#2E2E2E')
            plt.rcParams['text.color'] = 'white'
            plt.rcParams['axes.labelcolor'] = 'white'
            plt.rcParams['xtick.color'] = 'white'
            plt.rcParams['ytick.color'] = 'white'
            plt.rcParams['axes.facecolor'] = '#3E3E3E'
        elif config.style == ChartStyle.MINIMAL:
            fig.patch.set_facecolor('white')
            plt.rcParams['axes.spines.top'] = False
            plt.rcParams['axes.spines.right'] = False
        
        # Apply custom styling
        for key, value in config.custom_styling.items():
            if key in plt.rcParams:
                plt.rcParams[key] = value
    
    def _create_line_chart(self, df: pd.DataFrame, config: ChartConfig, chart_data: ChartData):
        """Create line chart"""
        
        x_col = chart_data.x_column or df.columns[0]
        y_cols = chart_data.y_columns or [df.columns[1]]
        
        colors = config.get_color_palette()
        
        for i, y_col in enumerate(y_cols):
            plt.plot(
                df[x_col], 
                df[y_col], 
                label=y_col, 
                color=colors[i % len(colors)],
                linewidth=2,
                marker='o',
                markersize=4
            )
        
        # Format x-axis for dates
        if pd.api.types.is_datetime64_any_dtype(df[x_col]):
            plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
            plt.gca().xaxis.set_major_locator(mdates.DayLocator(interval=7))
            plt.xticks(rotation=config.x_axis_rotation)
    
    def _create_bar_chart(self, df: pd.DataFrame, config: ChartConfig, chart_data: ChartData):
        """Create bar chart"""
        
        x_col = chart_data.x_column or df.columns[0]
        y_cols = chart_data.y_columns or [df.columns[1]]
        
        colors = config.get_color_palette()
        
        if len(y_cols) == 1:
            plt.bar(df[x_col], df[y_cols[0]], color=colors[0], alpha=0.8)
        else:
            # Multiple series bar chart
            x_pos = np.arange(len(df[x_col]))
            width = 0.8 / len(y_cols)
            
            for i, y_col in enumerate(y_cols):
                plt.bar(
                    x_pos + i * width, 
                    df[y_col], 
                    width, 
                    label=y_col, 
                    color=colors[i % len(colors)],
                    alpha=0.8
                )
            
            plt.xticks(x_pos + width * (len(y_cols) - 1) / 2, df[x_col])
        
        plt.xticks(rotation=config.x_axis_rotation)
    
    def _create_area_chart(self, df: pd.DataFrame, config: ChartConfig, chart_data: ChartData):
        """Create area chart"""
        
        x_col = chart_data.x_column or df.columns[0]
        y_cols = chart_data.y_columns or [df.columns[1]]
        
        colors = config.get_color_palette()
        
        for i, y_col in enumerate(y_cols):
            plt.fill_between(
                df[x_col], 
                df[y_col], 
                label=y_col, 
                color=colors[i % len(colors)],
                alpha=0.6
            )
    
    def _create_pie_chart(self, df: pd.DataFrame, config: ChartConfig, chart_data: ChartData):
        """Create pie chart"""
        
        category_col = chart_data.category_column or df.columns[0]
        value_col = chart_data.value_column or df.columns[1]
        
        colors = config.get_color_palette()
        
        plt.pie(
            df[value_col], 
            labels=df[category_col], 
            colors=colors,
            autopct='%1.1f%%',
            startangle=90
        )
        plt.axis('equal')
    
    def _create_scatter_chart(self, df: pd.DataFrame, config: ChartConfig, chart_data: ChartData):
        """Create scatter plot"""
        
        x_col = chart_data.x_column or df.columns[0]
        y_col = chart_data.y_columns[0] if chart_data.y_columns else df.columns[1]
        
        colors = config.get_color_palette()
        
        plt.scatter(
            df[x_col], 
            df[y_col], 
            color=colors[0],
            alpha=0.7,
            s=50
        )
    
    def _create_heatmap(self, df: pd.DataFrame, config: ChartConfig, chart_data: ChartData):
        """Create heatmap"""
        
        # Assume df is already a correlation matrix or similar
        sns.heatmap(
            df, 
            annot=True, 
            cmap='RdYlBu_r', 
            center=0,
            square=True,
            fmt='.2f'
        )
    
    def _create_histogram(self, df: pd.DataFrame, config: ChartConfig, chart_data: ChartData):
        """Create histogram"""
        
        value_col = chart_data.value_column or df.columns[0]
        colors = config.get_color_palette()
        
        plt.hist(
            df[value_col], 
            bins=30, 
            color=colors[0], 
            alpha=0.7,
            edgecolor='black'
        )
    
    def _create_box_plot(self, df: pd.DataFrame, config: ChartConfig, chart_data: ChartData):
        """Create box plot"""
        
        if chart_data.category_column and chart_data.value_column:
            # Grouped box plot
            df.boxplot(column=chart_data.value_column, by=chart_data.category_column)
        else:
            # Simple box plot
            columns = chart_data.y_columns or df.select_dtypes(include=[np.number]).columns.tolist()
            df[columns].boxplot()
    
    def _generate_output(self, fig: Figure, output_format: OutputFormat) -> str:
        """Generate output in specified format"""
        
        if output_format == OutputFormat.BASE64:
            buffer = BytesIO()
            fig.savefig(buffer, format='png', bbox_inches='tight', dpi=300)
            buffer.seek(0)
            
            image_base64 = base64.b64encode(buffer.getvalue()).decode()
            buffer.close()
            
            return f"data:image/png;base64,{image_base64}"
        
        elif output_format == OutputFormat.PNG:
            buffer = BytesIO()
            fig.savefig(buffer, format='png', bbox_inches='tight', dpi=300)
            return buffer.getvalue()
        
        elif output_format == OutputFormat.SVG:
            buffer = BytesIO()
            fig.savefig(buffer, format='svg', bbox_inches='tight')
            return buffer.getvalue().decode()
        
        elif output_format == OutputFormat.PDF:
            buffer = BytesIO()
            fig.savefig(buffer, format='pdf', bbox_inches='tight')
            return buffer.getvalue()
        
        else:
            raise ValueError(f"Unsupported output format: {output_format}")


class PlotlyChartEngine:
    """Plotly-based interactive chart generation engine"""
    
    def __init__(self):
        if not PLOTLY_AVAILABLE:
            raise ImportError("Plotly not available")
    
    def create_chart(
        self, 
        chart_data: ChartData, 
        config: ChartConfig, 
        output_format: OutputFormat = OutputFormat.HTML
    ) -> GeneratedChart:
        """Create interactive chart using Plotly"""
        
        df = chart_data.to_dataframe()
        
        # Create figure based on chart type
        if config.chart_type == ChartType.LINE:
            fig = self._create_line_chart(df, config, chart_data)
        elif config.chart_type == ChartType.BAR:
            fig = self._create_bar_chart(df, config, chart_data)
        elif config.chart_type == ChartType.AREA:
            fig = self._create_area_chart(df, config, chart_data)
        elif config.chart_type == ChartType.PIE:
            fig = self._create_pie_chart(df, config, chart_data)
        elif config.chart_type == ChartType.SCATTER:
            fig = self._create_scatter_chart(df, config, chart_data)
        elif config.chart_type == ChartType.HEATMAP:
            fig = self._create_heatmap(df, config, chart_data)
        elif config.chart_type == ChartType.HISTOGRAM:
            fig = self._create_histogram(df, config, chart_data)
        elif config.chart_type == ChartType.BOX:
            fig = self._create_box_plot(df, config, chart_data)
        elif config.chart_type == ChartType.CANDLESTICK:
            fig = self._create_candlestick_chart(df, config, chart_data)
        elif config.chart_type == ChartType.GAUGE:
            fig = self._create_gauge_chart(df, config, chart_data)
        elif config.chart_type == ChartType.TREEMAP:
            fig = self._create_treemap(df, config, chart_data)
        elif config.chart_type == ChartType.WATERFALL:
            fig = self._create_waterfall_chart(df, config, chart_data)
        else:
            raise ValueError(f"Unsupported chart type: {config.chart_type}")
        
        # Apply styling and layout
        self._apply_layout(fig, config)
        
        # Generate output
        content = self._generate_output(fig, output_format)
        
        chart_id = f"chart_{datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')}"
        
        return GeneratedChart(
            chart_id=chart_id,
            chart_type=config.chart_type,
            output_format=output_format,
            content=content,
            metadata={
                "title": config.title,
                "width": config.width,
                "height": config.height,
                "style": config.style.value,
                "interactive": True
            }
        )
    
    def _apply_layout(self, fig, config: ChartConfig):
        """Apply layout and styling to Plotly figure"""
        
        colors = config.get_color_palette()
        
        # Base layout
        layout_config = {
            'title': {
                'text': config.title,
                'font': {'size': 16, 'family': 'Arial, sans-serif'},
                'x': 0.5
            },
            'width': config.width,
            'height': config.height,
            'showlegend': config.show_legend,
            'font': {'family': 'Arial, sans-serif'},
            'margin': {'t': 60, 'b': 60, 'l': 60, 'r': 60}
        }
        
        # Axis labels
        if config.x_axis_label:
            layout_config['xaxis'] = {'title': config.x_axis_label}
        
        if config.y_axis_label:
            layout_config['yaxis'] = {'title': config.y_axis_label}
        
        # Grid configuration
        if config.show_grid:
            if 'xaxis' not in layout_config:
                layout_config['xaxis'] = {}
            if 'yaxis' not in layout_config:
                layout_config['yaxis'] = {}
            
            layout_config['xaxis']['showgrid'] = True
            layout_config['yaxis']['showgrid'] = True
        
        # Style-specific configurations
        if config.style == ChartStyle.DARK:
            layout_config.update({
                'paper_bgcolor': '#2E2E2E',
                'plot_bgcolor': '#3E3E3E',
                'font': {'color': 'white'}
            })
        elif config.style == ChartStyle.MINIMAL:
            layout_config.update({
                'paper_bgcolor': 'white',
                'plot_bgcolor': 'white'
            })
        
        # Apply custom styling
        layout_config.update(config.custom_styling)
        
        fig.update_layout(**layout_config)
    
    def _create_line_chart(self, df: pd.DataFrame, config: ChartConfig, chart_data: ChartData):
        """Create Plotly line chart"""
        
        x_col = chart_data.x_column or df.columns[0]
        y_cols = chart_data.y_columns or [df.columns[1]]
        
        fig = go.Figure()
        colors = config.get_color_palette()
        
        for i, y_col in enumerate(y_cols):
            fig.add_trace(go.Scatter(
                x=df[x_col],
                y=df[y_col],
                mode='lines+markers',
                name=y_col,
                line=dict(color=colors[i % len(colors)], width=2),
                marker=dict(size=6)
            ))
        
        return fig
    
    def _create_bar_chart(self, df: pd.DataFrame, config: ChartConfig, chart_data: ChartData):
        """Create Plotly bar chart"""
        
        x_col = chart_data.x_column or df.columns[0]
        y_cols = chart_data.y_columns or [df.columns[1]]
        
        fig = go.Figure()
        colors = config.get_color_palette()
        
        for i, y_col in enumerate(y_cols):
            fig.add_trace(go.Bar(
                x=df[x_col],
                y=df[y_col],
                name=y_col,
                marker_color=colors[i % len(colors)]
            ))
        
        return fig
    
    def _create_area_chart(self, df: pd.DataFrame, config: ChartConfig, chart_data: ChartData):
        """Create Plotly area chart"""
        
        x_col = chart_data.x_column or df.columns[0]
        y_cols = chart_data.y_columns or [df.columns[1]]
        
        fig = go.Figure()
        colors = config.get_color_palette()
        
        for i, y_col in enumerate(y_cols):
            fig.add_trace(go.Scatter(
                x=df[x_col],
                y=df[y_col],
                mode='lines',
                fill='tonexty' if i > 0 else 'tozeroy',
                name=y_col,
                line=dict(color=colors[i % len(colors)])
            ))
        
        return fig
    
    def _create_pie_chart(self, df: pd.DataFrame, config: ChartConfig, chart_data: ChartData):
        """Create Plotly pie chart"""
        
        category_col = chart_data.category_column or df.columns[0]
        value_col = chart_data.value_column or df.columns[1]
        
        fig = go.Figure(data=[go.Pie(
            labels=df[category_col],
            values=df[value_col],
            hole=0.3,  # Donut style
            marker_colors=config.get_color_palette()
        )])
        
        return fig
    
    def _create_scatter_chart(self, df: pd.DataFrame, config: ChartConfig, chart_data: ChartData):
        """Create Plotly scatter chart"""
        
        x_col = chart_data.x_column or df.columns[0]
        y_col = chart_data.y_columns[0] if chart_data.y_columns else df.columns[1]
        
        fig = go.Figure(data=go.Scatter(
            x=df[x_col],
            y=df[y_col],
            mode='markers',
            marker=dict(
                size=10,
                color=config.get_color_palette()[0],
                opacity=0.7
            )
        ))
        
        return fig
    
    def _create_heatmap(self, df: pd.DataFrame, config: ChartConfig, chart_data: ChartData):
        """Create Plotly heatmap"""
        
        fig = go.Figure(data=go.Heatmap(
            z=df.values,
            x=df.columns,
            y=df.index,
            colorscale='RdYlBu',
            text=df.values,
            texttemplate="%{text:.2f}",
            showscale=True
        ))
        
        return fig
    
    def _create_histogram(self, df: pd.DataFrame, config: ChartConfig, chart_data: ChartData):
        """Create Plotly histogram"""
        
        value_col = chart_data.value_column or df.columns[0]
        
        fig = go.Figure(data=[go.Histogram(
            x=df[value_col],
            nbinsx=30,
            marker_color=config.get_color_palette()[0]
        )])
        
        return fig
    
    def _create_box_plot(self, df: pd.DataFrame, config: ChartConfig, chart_data: ChartData):
        """Create Plotly box plot"""
        
        fig = go.Figure()
        colors = config.get_color_palette()
        
        if chart_data.category_column and chart_data.value_column:
            # Grouped box plot
            categories = df[chart_data.category_column].unique()
            
            for i, category in enumerate(categories):
                category_data = df[df[chart_data.category_column] == category]
                fig.add_trace(go.Box(
                    y=category_data[chart_data.value_column],
                    name=str(category),
                    marker_color=colors[i % len(colors)]
                ))
        else:
            # Simple box plot
            columns = chart_data.y_columns or df.select_dtypes(include=[np.number]).columns.tolist()
            
            for i, col in enumerate(columns):
                fig.add_trace(go.Box(
                    y=df[col],
                    name=col,
                    marker_color=colors[i % len(colors)]
                ))
        
        return fig
    
    def _create_candlestick_chart(self, df: pd.DataFrame, config: ChartConfig, chart_data: ChartData):
        """Create Plotly candlestick chart"""
        
        # Assume df has OHLC data
        required_cols = ['open', 'high', 'low', 'close']
        date_col = chart_data.x_column or 'date'
        
        fig = go.Figure(data=go.Candlestick(
            x=df[date_col],
            open=df['open'],
            high=df['high'],
            low=df['low'],
            close=df['close']
        ))
        
        return fig
    
    def _create_gauge_chart(self, df: pd.DataFrame, config: ChartConfig, chart_data: ChartData):
        """Create Plotly gauge chart"""
        
        value_col = chart_data.value_column or df.columns[0]
        value = df[value_col].iloc[0] if len(df) > 0 else 0
        
        fig = go.Figure(go.Indicator(
            mode="gauge+number+delta",
            value=value,
            domain={'x': [0, 1], 'y': [0, 1]},
            gauge={
                'axis': {'range': [None, df[value_col].max() * 1.2]},
                'bar': {'color': config.get_color_palette()[0]},
                'steps': [
                    {'range': [0, df[value_col].max() * 0.5], 'color': "lightgray"},
                    {'range': [df[value_col].max() * 0.5, df[value_col].max()], 'color': "gray"}
                ],
                'threshold': {
                    'line': {'color': "red", 'width': 4},
                    'thickness': 0.75,
                    'value': df[value_col].max() * 0.9
                }
            }
        ))
        
        return fig
    
    def _create_treemap(self, df: pd.DataFrame, config: ChartConfig, chart_data: ChartData):
        """Create Plotly treemap"""
        
        category_col = chart_data.category_column or df.columns[0]
        value_col = chart_data.value_column or df.columns[1]
        
        fig = go.Figure(go.Treemap(
            labels=df[category_col],
            values=df[value_col],
            parents=[""] * len(df),
            textinfo="label+value",
            marker_colorscale='Viridis'
        ))
        
        return fig
    
    def _create_waterfall_chart(self, df: pd.DataFrame, config: ChartConfig, chart_data: ChartData):
        """Create Plotly waterfall chart"""
        
        x_col = chart_data.x_column or df.columns[0]
        y_col = chart_data.y_columns[0] if chart_data.y_columns else df.columns[1]
        
        fig = go.Figure(go.Waterfall(
            name="",
            orientation="v",
            measure=["relative"] * len(df),
            x=df[x_col],
            textposition="outside",
            text=df[y_col].apply(lambda x: f"{x:+.1f}"),
            y=df[y_col],
            connector={"line": {"color": "rgb(63, 63, 63)"}},
        ))
        
        return fig
    
    def _generate_output(self, fig, output_format: OutputFormat) -> str:
        """Generate output in specified format"""
        
        if output_format == OutputFormat.HTML:
            return pio.to_html(fig, include_plotlyjs='cdn', div_id=f"chart_{datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')}")
        
        elif output_format == OutputFormat.JSON:
            return pio.to_json(fig)
        
        elif output_format == OutputFormat.PNG:
            img_bytes = pio.to_image(fig, format='png', width=fig.layout.width, height=fig.layout.height)
            return base64.b64encode(img_bytes).decode()
        
        elif output_format == OutputFormat.SVG:
            return pio.to_image(fig, format='svg').decode()
        
        elif output_format == OutputFormat.PDF:
            return pio.to_image(fig, format='pdf')
        
        else:
            raise ValueError(f"Unsupported output format: {output_format}")


class VisualizationEngine:
    """
    Advanced visualization engine for report generation
    
    Supports multiple chart types, interactive visualizations,
    and custom styling with multiple backend engines.
    """
    
    def __init__(self, default_engine: str = "matplotlib"):
        self.default_engine = default_engine
        self.engines = {}
        
        # Initialize available engines
        if MATPLOTLIB_AVAILABLE:
            self.engines['matplotlib'] = MatplotlibChartEngine()
        
        if PLOTLY_AVAILABLE:
            self.engines['plotly'] = PlotlyChartEngine()
        
        if not self.engines:
            raise ImportError("No visualization engines available")
        
        # Chart templates for common use cases
        self.chart_templates = self._create_chart_templates()
    
    def _create_chart_templates(self) -> Dict[str, ChartConfig]:
        """Create predefined chart templates"""
        
        templates = {
            "performance_line": ChartConfig(
                chart_type=ChartType.LINE,
                title="Portfolio Performance",
                style=ChartStyle.PROFESSIONAL,
                show_grid=True,
                x_axis_label="Date",
                y_axis_label="Cumulative Return (%)"
            ),
            
            "allocation_pie": ChartConfig(
                chart_type=ChartType.PIE,
                title="Portfolio Allocation",
                style=ChartStyle.CORPORATE,
                show_legend=True
            ),
            
            "risk_metrics_bar": ChartConfig(
                chart_type=ChartType.BAR,
                title="Risk Metrics Comparison",
                style=ChartStyle.MODERN,
                show_grid=True,
                y_axis_label="Value"
            ),
            
            "correlation_heatmap": ChartConfig(
                chart_type=ChartType.HEATMAP,
                title="Strategy Correlation Matrix",
                style=ChartStyle.MINIMAL,
                show_legend=False
            ),
            
            "returns_histogram": ChartConfig(
                chart_type=ChartType.HISTOGRAM,
                title="Daily Returns Distribution",
                style=ChartStyle.DEFAULT,
                x_axis_label="Daily Return (%)",
                y_axis_label="Frequency"
            ),
            
            "drawdown_area": ChartConfig(
                chart_type=ChartType.AREA,
                title="Portfolio Drawdown",
                style=ChartStyle.PROFESSIONAL,
                show_grid=True,
                x_axis_label="Date",
                y_axis_label="Drawdown (%)"
            )
        }
        
        return templates
    
    def create_chart(
        self,
        chart_data: ChartData,
        config: ChartConfig,
        engine: Optional[str] = None,
        output_format: OutputFormat = OutputFormat.BASE64
    ) -> GeneratedChart:
        """Create chart with specified engine"""
        
        engine_name = engine or self.default_engine
        
        if engine_name not in self.engines:
            raise ValueError(f"Engine '{engine_name}' not available")
        
        chart_engine = self.engines[engine_name]
        
        return chart_engine.create_chart(chart_data, config, output_format)
    
    def create_chart_from_template(
        self,
        template_name: str,
        chart_data: ChartData,
        title_override: Optional[str] = None,
        engine: Optional[str] = None,
        output_format: OutputFormat = OutputFormat.BASE64
    ) -> GeneratedChart:
        """Create chart using predefined template"""
        
        if template_name not in self.chart_templates:
            raise ValueError(f"Template '{template_name}' not found")
        
        config = self.chart_templates[template_name]
        
        if title_override:
            config.title = title_override
        
        return self.create_chart(chart_data, config, engine, output_format)
    
    def create_performance_chart(
        self,
        performance_data: Dict[str, Any],
        title: str = "Portfolio Performance",
        engine: Optional[str] = None
    ) -> GeneratedChart:
        """Create standardized performance chart"""
        
        # Convert performance data to DataFrame
        df_data = {
            'date': performance_data.get('dates', []),
            'cumulative_return': performance_data.get('cumulative_returns', []),
            'benchmark_return': performance_data.get('benchmark_returns', [])
        }
        
        chart_data = ChartData(
            data=df_data,
            x_column='date',
            y_columns=['cumulative_return', 'benchmark_return']
        )
        
        config = ChartConfig(
            chart_type=ChartType.LINE,
            title=title,
            style=ChartStyle.PROFESSIONAL,
            width=800,
            height=400,
            show_grid=True,
            x_axis_label="Date",
            y_axis_label="Cumulative Return (%)",
            color_palette=['#2E86AB', '#F18F01']
        )
        
        return self.create_chart(chart_data, config, engine)
    
    def create_allocation_chart(
        self,
        allocation_data: Dict[str, float],
        title: str = "Portfolio Allocation",
        engine: Optional[str] = None
    ) -> GeneratedChart:
        """Create standardized allocation chart"""
        
        df_data = {
            'asset': list(allocation_data.keys()),
            'allocation': list(allocation_data.values())
        }
        
        chart_data = ChartData(
            data=df_data,
            category_column='asset',
            value_column='allocation'
        )
        
        config = ChartConfig(
            chart_type=ChartType.PIE,
            title=title,
            style=ChartStyle.CORPORATE,
            width=600,
            height=400,
            show_legend=True
        )
        
        return self.create_chart(chart_data, config, engine)
    
    def create_correlation_heatmap(
        self,
        correlation_matrix: pd.DataFrame,
        title: str = "Strategy Correlation Matrix",
        engine: Optional[str] = None
    ) -> GeneratedChart:
        """Create correlation heatmap"""
        
        chart_data = ChartData(data=correlation_matrix)
        
        config = ChartConfig(
            chart_type=ChartType.HEATMAP,
            title=title,
            style=ChartStyle.MINIMAL,
            width=600,
            height=500,
            show_legend=False
        )
        
        return self.create_chart(chart_data, config, engine)
    
    def create_risk_metrics_chart(
        self,
        risk_metrics: Dict[str, float],
        title: str = "Risk Metrics",
        engine: Optional[str] = None
    ) -> GeneratedChart:
        """Create risk metrics bar chart"""
        
        df_data = {
            'metric': list(risk_metrics.keys()),
            'value': list(risk_metrics.values())
        }
        
        chart_data = ChartData(
            data=df_data,
            x_column='metric',
            y_columns=['value']
        )
        
        config = ChartConfig(
            chart_type=ChartType.BAR,
            title=title,
            style=ChartStyle.MODERN,
            width=700,
            height=400,
            show_grid=True,
            x_axis_rotation=45,
            y_axis_label="Value"
        )
        
        return self.create_chart(chart_data, config, engine)
    
    def create_dashboard(
        self,
        charts: List[GeneratedChart],
        title: str = "Portfolio Dashboard",
        layout: str = "grid"
    ) -> str:
        """Create dashboard combining multiple charts"""
        
        if not PLOTLY_AVAILABLE:
            logger.warning("Dashboard creation requires Plotly")
            return ""
        
        # Create subplots based on layout
        if layout == "grid":
            rows = int(np.ceil(len(charts) / 2))
            cols = 2 if len(charts) > 1 else 1
        elif layout == "vertical":
            rows = len(charts)
            cols = 1
        else:  # horizontal
            rows = 1
            cols = len(charts)
        
        fig = make_subplots(
            rows=rows,
            cols=cols,
            subplot_titles=[chart.metadata.get('title', f'Chart {i+1}') for i, chart in enumerate(charts)]
        )
        
        # Add charts to subplots
        for i, chart in enumerate(charts):
            row = (i // cols) + 1 if layout == "grid" else i + 1 if layout == "vertical" else 1
            col = (i % cols) + 1 if layout == "grid" else 1 if layout == "vertical" else i + 1
            
            # Note: This would require parsing the chart content and adding traces
            # For now, returning a placeholder
            logger.info(f"Adding chart {i+1} to dashboard at row {row}, col {col}")
        
        fig.update_layout(
            title=title,
            height=600 * rows,
            showlegend=True
        )
        
        return pio.to_html(fig, include_plotlyjs='cdn')
    
    def get_available_engines(self) -> List[str]:
        """Get list of available visualization engines"""
        return list(self.engines.keys())
    
    def get_chart_templates(self) -> List[str]:
        """Get list of available chart templates"""
        return list(self.chart_templates.keys())
    
    def add_custom_template(self, name: str, config: ChartConfig):
        """Add custom chart template"""
        self.chart_templates[name] = config
        logger.info(f"Added custom chart template: {name}")
    
    def batch_create_charts(
        self,
        chart_specs: List[Dict[str, Any]],
        engine: Optional[str] = None
    ) -> List[GeneratedChart]:
        """Create multiple charts in batch"""
        
        charts = []
        
        for spec in chart_specs:
            try:
                chart_data = ChartData(**spec['data'])
                config = ChartConfig(**spec['config'])
                output_format = OutputFormat(spec.get('output_format', 'base64'))
                
                chart = self.create_chart(chart_data, config, engine, output_format)
                charts.append(chart)
            
            except Exception as e:
                logger.error(f"Failed to create chart from spec: {e}")
                continue
        
        return charts