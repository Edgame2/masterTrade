"""
Advanced Backtesting Framework for MasterTrade

Comprehensive backtesting with:
- Walk-forward analysis
- Monte Carlo simulation
- Realistic slippage and fees
- Parameter optimization
- Performance attribution
- Regime-specific analysis
"""

from .backtest_engine import BacktestEngine, BacktestConfig, BacktestResult
from .walk_forward import WalkForwardAnalyzer, WalkForwardConfig
from .monte_carlo import MonteCarloSimulator, MonteCarloConfig
from .optimization import ParameterOptimizer, OptimizationConfig
from .performance_metrics import PerformanceAnalyzer, MetricsCalculator

__all__ = [
    'BacktestEngine',
    'BacktestConfig',
    'BacktestResult',
    'WalkForwardAnalyzer',
    'WalkForwardConfig',
    'MonteCarloSimulator',
    'MonteCarloConfig',
    'ParameterOptimizer',
    'OptimizationConfig',
    'PerformanceAnalyzer',
    'MetricsCalculator',
]
