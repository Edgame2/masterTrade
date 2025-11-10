"""
Strategy Correlation Analysis Module

Comprehensive system for analyzing correlations between trading strategies,
portfolio-level correlation insights, and correlation-based allocation.

Components:
- CorrelationAnalyzer: Cross-strategy correlation tracking and analysis
- RegimeAnalyzer: Market regime detection and regime-based correlation modeling
- PortfolioCorrelation: Portfolio-level correlation insights and diversification analysis
- CorrelationModels: Advanced correlation models and prediction frameworks
- API: REST endpoints for all correlation analysis functionality

Key Features:
- Real-time strategy correlation tracking
- Rolling correlation analysis with multiple time windows
- Correlation breakdown analysis (by market conditions, time periods, volatility regimes)
- Cross-asset and cross-strategy correlation matrices
- Correlation decay analysis and half-life estimation
- Dynamic correlation modeling with GARCH-DCC framework
- Portfolio diversification scoring and optimization
- Correlation-based strategy allocation recommendations
- Market regime detection using Hidden Markov Models
- Correlation forecasting and prediction intervals
"""

from .correlation_analyzer import (
    CorrelationAnalyzer,
    CorrelationResult,
    CorrelationMatrix,
    RollingCorrelation,
    StrategyPair
)

from .regime_analyzer import (
    RegimeAnalyzer,
    MarketRegime,
    RegimeCorrelation,
    RegimeTransition,
    HMMRegimeDetector
)

from .portfolio_correlation import (
    PortfolioCorrelation,
    DiversificationScore,
    CorrelationBreakdown,
    AllocationRecommendation,
    ConcentrationRisk
)

from .correlation_models import (
    CorrelationModel,
    DynamicCorrelationModel,
    GARCHDCCModel,
    EWMACorrelationModel,
    ShrinkageCorrelationModel,
    CorrelationForecast
)

__all__ = [
    # Core Analyzer
    'CorrelationAnalyzer',
    'CorrelationResult',
    'CorrelationMatrix',
    'RollingCorrelation',
    'StrategyPair',
    
    # Regime Analysis
    'RegimeAnalyzer',
    'MarketRegime',
    'RegimeCorrelation',
    'RegimeTransition',
    'HMMRegimeDetector',
    
    # Portfolio Analysis
    'PortfolioCorrelation',
    'DiversificationScore',
    'CorrelationBreakdown',
    'AllocationRecommendation',
    'ConcentrationRisk',
    
    # Correlation Models
    'CorrelationModel',
    'DynamicCorrelationModel',
    'GARCHDCCModel',
    'EWMACorrelationModel',
    'ShrinkageCorrelationModel',
    'CorrelationForecast'
]

# Module metadata
__version__ = "1.0.0"
__author__ = "MasterTrade Strategy Correlation Analysis Team"
__description__ = "Advanced strategy correlation analysis and portfolio diversification system"