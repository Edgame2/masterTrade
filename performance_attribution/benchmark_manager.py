"""
Benchmark Manager - Handles benchmark comparison and tracking

Supports multiple benchmark types:
- Single asset (BTC, ETH)
- Indices (crypto market indices)
- Custom portfolios
- Risk-free rate
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional
import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)


class BenchmarkType(Enum):
    """Types of benchmarks"""
    SINGLE_ASSET = "single_asset"  # BTC, ETH, etc.
    MARKET_INDEX = "market_index"  # Total crypto market
    EQUAL_WEIGHT = "equal_weight"  # Equal-weighted portfolio
    CAP_WEIGHT = "cap_weight"  # Market-cap weighted
    CUSTOM = "custom"  # Custom benchmark
    RISK_FREE = "risk_free"  # Risk-free rate


@dataclass
class Benchmark:
    """Benchmark definition"""
    
    name: str
    benchmark_type: BenchmarkType
    description: str
    
    # For single asset
    symbol: Optional[str] = None
    
    # For portfolio benchmarks
    components: Optional[Dict[str, float]] = None  # symbol -> weight
    
    # For risk-free
    annual_rate: Optional[float] = None
    
    # Benchmark returns
    returns: Optional[pd.Series] = None


@dataclass
class BenchmarkComparison:
    """Comparison of strategy vs benchmark"""
    
    benchmark_name: str
    
    # Returns
    strategy_return: float
    benchmark_return: float
    excess_return: float
    excess_return_annual: float
    
    # Risk
    strategy_volatility: float
    benchmark_volatility: float
    tracking_error: float
    
    # Risk-adjusted
    strategy_sharpe: float
    benchmark_sharpe: float
    information_ratio: float
    
    # Drawdown
    strategy_max_drawdown: float
    benchmark_max_drawdown: float
    
    # Correlation
    correlation: float
    beta: float
    
    # Active metrics
    active_return: float  # Strategy - Benchmark
    active_risk: float  # Tracking error
    active_share: Optional[float] = None  # For holdings-based


class BenchmarkManager:
    """
    Manages benchmarks and comparison calculations
    """
    
    def __init__(self):
        self.benchmarks: Dict[str, Benchmark] = {}
        self.logger = logging.getLogger(__name__)
    
    def add_benchmark(self, benchmark: Benchmark):
        """Add a benchmark"""
        self.benchmarks[benchmark.name] = benchmark
        self.logger.info(f"Added benchmark: {benchmark.name}")
    
    def create_single_asset_benchmark(
        self,
        name: str,
        symbol: str,
        returns: pd.Series
    ) -> Benchmark:
        """Create single asset benchmark (e.g., BTC, ETH)"""
        
        benchmark = Benchmark(
            name=name,
            benchmark_type=BenchmarkType.SINGLE_ASSET,
            description=f"{symbol} returns",
            symbol=symbol,
            returns=returns
        )
        
        self.add_benchmark(benchmark)
        return benchmark
    
    def create_market_index_benchmark(
        self,
        name: str,
        component_returns: Dict[str, pd.Series],
        weights: Optional[Dict[str, float]] = None
    ) -> Benchmark:
        """
        Create market index benchmark
        
        Args:
            name: Benchmark name
            component_returns: Dict of symbol -> returns series
            weights: Optional weights (if None, equal-weighted)
        """
        # Equal weights if not provided
        if weights is None:
            n = len(component_returns)
            weights = {symbol: 1.0 / n for symbol in component_returns.keys()}
        
        # Normalize weights
        total_weight = sum(weights.values())
        weights = {k: v / total_weight for k, v in weights.items()}
        
        # Calculate index returns
        index_returns = None
        for symbol, returns in component_returns.items():
            weight = weights.get(symbol, 0)
            if index_returns is None:
                index_returns = returns * weight
            else:
                index_returns = index_returns + (returns * weight)
        
        benchmark = Benchmark(
            name=name,
            benchmark_type=BenchmarkType.MARKET_INDEX,
            description=f"Market index with {len(component_returns)} components",
            components=weights,
            returns=index_returns
        )
        
        self.add_benchmark(benchmark)
        return benchmark
    
    def create_risk_free_benchmark(
        self,
        name: str,
        annual_rate: float,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp
    ) -> Benchmark:
        """Create risk-free rate benchmark"""
        
        # Generate daily risk-free returns
        dates = pd.date_range(start_date, end_date, freq='D')
        daily_rate = annual_rate / 252
        returns = pd.Series(daily_rate, index=dates)
        
        benchmark = Benchmark(
            name=name,
            benchmark_type=BenchmarkType.RISK_FREE,
            description=f"Risk-free rate: {annual_rate:.2%} annual",
            annual_rate=annual_rate,
            returns=returns
        )
        
        self.add_benchmark(benchmark)
        return benchmark
    
    def compare_to_benchmark(
        self,
        strategy_returns: pd.Series,
        benchmark_name: str,
        risk_free_rate: float = 0.04
    ) -> BenchmarkComparison:
        """
        Compare strategy to benchmark
        
        Args:
            strategy_returns: Strategy returns (daily)
            benchmark_name: Name of benchmark
            risk_free_rate: Annual risk-free rate
        
        Returns:
            Detailed comparison
        """
        # Get benchmark
        if benchmark_name not in self.benchmarks:
            raise ValueError(f"Benchmark {benchmark_name} not found")
        
        benchmark = self.benchmarks[benchmark_name]
        benchmark_returns = benchmark.returns
        
        if benchmark_returns is None:
            raise ValueError(f"Benchmark {benchmark_name} has no returns data")
        
        # Align dates
        common_dates = strategy_returns.index.intersection(benchmark_returns.index)
        strat_ret = strategy_returns.loc[common_dates]
        bench_ret = benchmark_returns.loc[common_dates]
        
        # Returns
        strategy_return = (1 + strat_ret).prod() - 1
        benchmark_return = (1 + bench_ret).prod() - 1
        excess_return = strategy_return - benchmark_return
        
        # Annualized
        n_days = len(strat_ret)
        excess_return_annual = (1 + excess_return) ** (252 / n_days) - 1
        
        # Volatility
        strategy_volatility = strat_ret.std() * np.sqrt(252)
        benchmark_volatility = bench_ret.std() * np.sqrt(252)
        
        # Tracking error (volatility of excess returns)
        excess_returns = strat_ret - bench_ret
        tracking_error = excess_returns.std() * np.sqrt(252)
        
        # Sharpe ratios
        daily_rf = risk_free_rate / 252
        strategy_sharpe = (strat_ret.mean() - daily_rf) / strat_ret.std() * np.sqrt(252) if strat_ret.std() > 0 else 0
        benchmark_sharpe = (bench_ret.mean() - daily_rf) / bench_ret.std() * np.sqrt(252) if bench_ret.std() > 0 else 0
        
        # Information ratio
        information_ratio = excess_returns.mean() / excess_returns.std() * np.sqrt(252) if excess_returns.std() > 0 else 0
        
        # Drawdowns
        strategy_max_drawdown = self._calculate_max_drawdown(strat_ret)
        benchmark_max_drawdown = self._calculate_max_drawdown(bench_ret)
        
        # Correlation and beta
        correlation = strat_ret.corr(bench_ret)
        
        # Beta via regression
        if bench_ret.std() > 0:
            beta = strat_ret.cov(bench_ret) / bench_ret.var()
        else:
            beta = 0.0
        
        # Active metrics
        active_return = strategy_return - benchmark_return
        active_risk = tracking_error
        
        comparison = BenchmarkComparison(
            benchmark_name=benchmark_name,
            strategy_return=strategy_return,
            benchmark_return=benchmark_return,
            excess_return=excess_return,
            excess_return_annual=excess_return_annual,
            strategy_volatility=strategy_volatility,
            benchmark_volatility=benchmark_volatility,
            tracking_error=tracking_error,
            strategy_sharpe=strategy_sharpe,
            benchmark_sharpe=benchmark_sharpe,
            information_ratio=information_ratio,
            strategy_max_drawdown=strategy_max_drawdown,
            benchmark_max_drawdown=benchmark_max_drawdown,
            correlation=correlation,
            beta=beta,
            active_return=active_return,
            active_risk=active_risk
        )
        
        self.logger.info(
            f"Comparison to {benchmark_name}: "
            f"Excess return={excess_return:.2%}, IR={information_ratio:.2f}, "
            f"Beta={beta:.2f}"
        )
        
        return comparison
    
    def compare_to_multiple_benchmarks(
        self,
        strategy_returns: pd.Series,
        benchmark_names: Optional[List[str]] = None,
        risk_free_rate: float = 0.04
    ) -> Dict[str, BenchmarkComparison]:
        """
        Compare strategy to multiple benchmarks
        
        Args:
            strategy_returns: Strategy returns
            benchmark_names: List of benchmark names (None = all)
            risk_free_rate: Annual risk-free rate
        
        Returns:
            Dict of benchmark_name -> comparison
        """
        if benchmark_names is None:
            benchmark_names = list(self.benchmarks.keys())
        
        comparisons = {}
        for name in benchmark_names:
            try:
                comparison = self.compare_to_benchmark(
                    strategy_returns, name, risk_free_rate
                )
                comparisons[name] = comparison
            except Exception as e:
                self.logger.error(f"Error comparing to {name}: {e}")
        
        return comparisons
    
    def _calculate_max_drawdown(self, returns: pd.Series) -> float:
        """Calculate maximum drawdown"""
        cumulative = (1 + returns).cumprod()
        running_max = cumulative.expanding().max()
        drawdown = (cumulative - running_max) / running_max
        return abs(drawdown.min())
    
    def get_best_benchmark(
        self,
        comparisons: Dict[str, BenchmarkComparison]
    ) -> str:
        """
        Get the best benchmark for a strategy based on correlation
        
        Returns benchmark name with highest correlation
        """
        best_name = None
        best_corr = -1
        
        for name, comparison in comparisons.items():
            if comparison.correlation > best_corr:
                best_corr = comparison.correlation
                best_name = name
        
        return best_name if best_name else "None"
    
    def calculate_active_share(
        self,
        strategy_weights: Dict[str, float],
        benchmark_weights: Dict[str, float]
    ) -> float:
        """
        Calculate active share (for holdings-based attribution)
        
        Active share = 0.5 * sum(|w_strategy - w_benchmark|)
        
        Returns:
            Active share between 0 (identical) and 1 (completely different)
        """
        # Get all symbols
        all_symbols = set(strategy_weights.keys()) | set(benchmark_weights.keys())
        
        # Calculate difference
        total_diff = 0.0
        for symbol in all_symbols:
            strat_weight = strategy_weights.get(symbol, 0.0)
            bench_weight = benchmark_weights.get(symbol, 0.0)
            total_diff += abs(strat_weight - bench_weight)
        
        active_share = 0.5 * total_diff
        
        return active_share
