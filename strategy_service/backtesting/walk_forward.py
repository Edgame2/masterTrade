"""
Walk-Forward Analysis

Implements walk-forward optimization to prevent overfitting and
validate strategy robustness across different market periods.
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
import structlog
from concurrent.futures import ProcessPoolExecutor, as_completed

from .backtest_engine import BacktestEngine, BacktestConfig, BacktestResult

logger = structlog.get_logger()


@dataclass
class WalkForwardConfig:
    """Configuration for walk-forward analysis"""
    
    # Window sizes
    in_sample_days: int = 90  # Training window
    out_sample_days: int = 30  # Testing window
    step_days: int = 30  # How much to move forward each iteration
    
    # Optimization
    optimize_in_sample: bool = True
    optimization_metric: str = "sharpe_ratio"  # "sharpe_ratio", "total_return", "calmar_ratio"
    
    # Anchored vs rolling
    anchored: bool = False  # If True, always start from beginning
    
    # Min data requirements
    min_trades_required: int = 10
    min_data_points: int = 1000


@dataclass
class WalkForwardWindow:
    """Single walk-forward window"""
    window_id: int
    in_sample_start: datetime
    in_sample_end: datetime
    out_sample_start: datetime
    out_sample_end: datetime
    
    # Results
    in_sample_result: Optional[BacktestResult] = None
    out_sample_result: Optional[BacktestResult] = None
    
    # Best parameters found
    best_params: Dict = field(default_factory=dict)
    optimization_score: float = 0.0
    
    # Degradation metrics
    is_degradation: float = 0.0  # In-sample to out-sample performance degradation


@dataclass
class WalkForwardResult:
    """Complete walk-forward analysis results"""
    
    config: WalkForwardConfig
    strategy_name: str
    
    # Windows
    windows: List[WalkForwardWindow] = field(default_factory=list)
    total_windows: int = 0
    
    # Combined out-of-sample performance
    combined_equity_curve: pd.Series = field(default_factory=lambda: pd.Series())
    combined_trades: List = field(default_factory=list)
    
    # Aggregate metrics
    total_return_pct: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    
    # Stability metrics
    avg_is_degradation: float = 0.0
    std_is_degradation: float = 0.0
    consistency_score: float = 0.0  # How consistent are results across windows
    
    # Parameter stability
    param_stability: Dict[str, float] = field(default_factory=dict)


class WalkForwardAnalyzer:
    """
    Walk-Forward Analysis Implementation
    
    Divides historical data into in-sample (training) and out-sample (testing) periods.
    Optimizes parameters on in-sample, tests on out-sample.
    Rolls forward through entire dataset to validate robustness.
    """
    
    def __init__(self, config: WalkForwardConfig, backtest_config: BacktestConfig):
        self.config = config
        self.backtest_config = backtest_config
    
    def analyze(
        self,
        data: pd.DataFrame,
        strategy_class: Any,
        param_ranges: Dict[str, List],
        strategy_name: str = "Unknown"
    ) -> WalkForwardResult:
        """
        Run walk-forward analysis
        
        Args:
            data: Historical OHLCV data
            strategy_class: Strategy class that generates signals
            param_ranges: Dict of parameter names to lists of values to test
            strategy_name: Name of strategy
            
        Returns:
            WalkForwardResult with comprehensive analysis
        """
        try:
            logger.info(
                f"Starting walk-forward analysis: {strategy_name}",
                in_sample_days=self.config.in_sample_days,
                out_sample_days=self.config.out_sample_days,
                step_days=self.config.step_days
            )
            
            # Create windows
            windows = self._create_windows(data)
            
            logger.info(f"Created {len(windows)} walk-forward windows")
            
            # Process each window
            results = []
            for window in windows:
                logger.info(
                    f"Processing window {window.window_id + 1}/{len(windows)}",
                    in_sample_start=window.in_sample_start,
                    out_sample_start=window.out_sample_start
                )
                
                window_result = self._process_window(
                    window,
                    data,
                    strategy_class,
                    param_ranges,
                    strategy_name
                )
                
                results.append(window_result)
            
            # Aggregate results
            wf_result = self._aggregate_results(
                results,
                strategy_name
            )
            
            logger.info(
                f"Walk-forward analysis completed: {strategy_name}",
                total_return_pct=f"{wf_result.total_return_pct:.2f}%",
                sharpe=f"{wf_result.sharpe_ratio:.2f}",
                avg_degradation=f"{wf_result.avg_is_degradation:.2f}%",
                consistency=f"{wf_result.consistency_score:.2f}"
            )
            
            return wf_result
            
        except Exception as e:
            logger.error(f"Error in walk-forward analysis: {e}", exc_info=True)
            raise
    
    def _create_windows(self, data: pd.DataFrame) -> List[WalkForwardWindow]:
        """Create walk-forward windows"""
        windows = []
        
        data_start = data['timestamp'].min()
        data_end = data['timestamp'].max()
        
        window_id = 0
        current_start = data_start
        
        while True:
            # Calculate window boundaries
            if self.config.anchored:
                in_sample_start = data_start
            else:
                in_sample_start = current_start
            
            in_sample_end = in_sample_start + timedelta(days=self.config.in_sample_days)
            out_sample_start = in_sample_end
            out_sample_end = out_sample_start + timedelta(days=self.config.out_sample_days)
            
            # Check if we have enough data
            if out_sample_end > data_end:
                break
            
            # Check minimum data points
            in_sample_data = data[
                (data['timestamp'] >= in_sample_start) &
                (data['timestamp'] < in_sample_end)
            ]
            
            out_sample_data = data[
                (data['timestamp'] >= out_sample_start) &
                (data['timestamp'] < out_sample_end)
            ]
            
            if len(in_sample_data) < self.config.min_data_points or \
               len(out_sample_data) < self.config.min_data_points:
                logger.warning(
                    f"Skipping window {window_id}: insufficient data",
                    in_sample_points=len(in_sample_data),
                    out_sample_points=len(out_sample_data)
                )
                current_start += timedelta(days=self.config.step_days)
                continue
            
            window = WalkForwardWindow(
                window_id=window_id,
                in_sample_start=in_sample_start,
                in_sample_end=in_sample_end,
                out_sample_start=out_sample_start,
                out_sample_end=out_sample_end
            )
            
            windows.append(window)
            window_id += 1
            
            # Move forward
            current_start += timedelta(days=self.config.step_days)
        
        return windows
    
    def _process_window(
        self,
        window: WalkForwardWindow,
        data: pd.DataFrame,
        strategy_class: Any,
        param_ranges: Dict[str, List],
        strategy_name: str
    ) -> WalkForwardWindow:
        """Process a single walk-forward window"""
        
        # Get in-sample and out-sample data
        in_sample_data = data[
            (data['timestamp'] >= window.in_sample_start) &
            (data['timestamp'] < window.in_sample_end)
        ].copy()
        
        out_sample_data = data[
            (data['timestamp'] >= window.out_sample_start) &
            (data['timestamp'] < window.out_sample_end)
        ].copy()
        
        if self.config.optimize_in_sample:
            # Optimize on in-sample period
            best_params, best_score = self._optimize_parameters(
                in_sample_data,
                strategy_class,
                param_ranges,
                strategy_name
            )
            
            window.best_params = best_params
            window.optimization_score = best_score
            
            # Run in-sample backtest with best params
            strategy = strategy_class(**best_params)
            signals = strategy.generate_signals(in_sample_data)
            
            in_sample_config = self._create_window_config(
                window.in_sample_start,
                window.in_sample_end
            )
            
            engine = BacktestEngine(in_sample_config)
            window.in_sample_result = engine.run(
                in_sample_data,
                signals,
                strategy_name,
                best_params
            )
        else:
            # Use default parameters
            strategy = strategy_class()
            signals = strategy.generate_signals(in_sample_data)
            best_params = strategy.get_parameters()
            window.best_params = best_params
        
        # Test on out-sample period with same parameters
        strategy = strategy_class(**window.best_params)
        signals = strategy.generate_signals(out_sample_data)
        
        out_sample_config = self._create_window_config(
            window.out_sample_start,
            window.out_sample_end
        )
        
        engine = BacktestEngine(out_sample_config)
        window.out_sample_result = engine.run(
            out_sample_data,
            signals,
            strategy_name,
            window.best_params
        )
        
        # Calculate degradation
        if window.in_sample_result and window.out_sample_result:
            window.is_degradation = self._calculate_degradation(
                window.in_sample_result,
                window.out_sample_result
            )
        
        return window
    
    def _optimize_parameters(
        self,
        data: pd.DataFrame,
        strategy_class: Any,
        param_ranges: Dict[str, List],
        strategy_name: str
    ) -> Tuple[Dict, float]:
        """
        Optimize strategy parameters on in-sample data
        
        Uses grid search over parameter ranges
        """
        from itertools import product
        
        # Generate all parameter combinations
        param_names = list(param_ranges.keys())
        param_values = list(param_ranges.values())
        param_combinations = list(product(*param_values))
        
        logger.info(
            f"Testing {len(param_combinations)} parameter combinations",
            param_names=param_names
        )
        
        best_score = -np.inf
        best_params = {}
        
        # Test each combination
        for combo in param_combinations:
            params = dict(zip(param_names, combo))
            
            try:
                # Generate signals with these parameters
                strategy = strategy_class(**params)
                signals = strategy.generate_signals(data)
                
                # Run backtest
                config = self._create_window_config(
                    data['timestamp'].min(),
                    data['timestamp'].max()
                )
                
                engine = BacktestEngine(config)
                result = engine.run(data, signals, strategy_name, params)
                
                # Check minimum trades requirement
                if result.total_trades < self.config.min_trades_required:
                    continue
                
                # Get optimization metric score
                score = self._get_optimization_score(result)
                
                if score > best_score:
                    best_score = score
                    best_params = params
                    
            except Exception as e:
                logger.warning(f"Error testing parameters {params}: {e}")
                continue
        
        if not best_params:
            # No valid parameters found, use defaults
            logger.warning("No valid parameters found, using defaults")
            strategy = strategy_class()
            best_params = strategy.get_parameters()
            best_score = 0.0
        
        logger.info(
            f"Best parameters found",
            params=best_params,
            score=f"{best_score:.4f}"
        )
        
        return best_params, best_score
    
    def _get_optimization_score(self, result: BacktestResult) -> float:
        """Get score for optimization metric"""
        metric = self.config.optimization_metric
        
        if metric == "sharpe_ratio":
            return result.sharpe_ratio
        elif metric == "total_return":
            return result.total_return_percent
        elif metric == "calmar_ratio":
            return result.calmar_ratio
        elif metric == "sortino_ratio":
            return result.sortino_ratio
        elif metric == "profit_factor":
            return result.profit_factor
        else:
            return result.sharpe_ratio
    
    def _calculate_degradation(
        self,
        in_sample: BacktestResult,
        out_sample: BacktestResult
    ) -> float:
        """
        Calculate performance degradation from in-sample to out-sample
        
        Positive value means out-sample performed worse
        Negative value means out-sample performed better (suspicious!)
        """
        metric = self.config.optimization_metric
        
        if metric == "sharpe_ratio":
            is_score = in_sample.sharpe_ratio
            oos_score = out_sample.sharpe_ratio
        elif metric == "total_return":
            is_score = in_sample.total_return_percent
            oos_score = out_sample.total_return_percent
        elif metric == "calmar_ratio":
            is_score = in_sample.calmar_ratio
            oos_score = out_sample.calmar_ratio
        else:
            is_score = in_sample.sharpe_ratio
            oos_score = out_sample.sharpe_ratio
        
        if is_score == 0:
            return 0.0
        
        degradation = ((is_score - oos_score) / abs(is_score)) * 100
        
        return degradation
    
    def _create_window_config(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> BacktestConfig:
        """Create backtest config for window"""
        config = BacktestConfig(
            start_date=start_date,
            end_date=end_date,
            initial_capital=self.backtest_config.initial_capital,
            maker_fee=self.backtest_config.maker_fee,
            taker_fee=self.backtest_config.taker_fee,
            funding_rate=self.backtest_config.funding_rate,
            fixed_slippage_bps=self.backtest_config.fixed_slippage_bps,
            volume_slippage_factor=self.backtest_config.volume_slippage_factor,
            volatility_slippage_factor=self.backtest_config.volatility_slippage_factor,
            max_position_size=self.backtest_config.max_position_size,
            max_leverage=self.backtest_config.max_leverage,
            allow_short=self.backtest_config.allow_short
        )
        
        return config
    
    def _aggregate_results(
        self,
        windows: List[WalkForwardWindow],
        strategy_name: str
    ) -> WalkForwardResult:
        """Aggregate walk-forward results"""
        
        # Combine out-of-sample equity curves
        equity_curves = []
        all_trades = []
        
        for window in windows:
            if window.out_sample_result:
                equity_curves.append(window.out_sample_result.equity_curve)
                all_trades.extend(window.out_sample_result.trades)
        
        # Concatenate equity curves
        if equity_curves:
            combined_equity = pd.concat(equity_curves)
        else:
            combined_equity = pd.Series()
        
        # Calculate aggregate metrics
        if len(combined_equity) > 0:
            initial_capital = self.backtest_config.initial_capital
            final_capital = combined_equity.iloc[-1]
            total_return_pct = ((final_capital - initial_capital) / initial_capital) * 100
            
            returns = combined_equity.pct_change().dropna()
            sharpe = self._calculate_sharpe(returns)
            
            running_max = combined_equity.expanding().max()
            drawdown = (combined_equity - running_max) / running_max
            max_drawdown = abs(drawdown.min()) * 100
            
            # Trade stats
            winning_trades = len([t for t in all_trades if t.pnl > 0])
            win_rate = (winning_trades / len(all_trades) * 100) if all_trades else 0
            
            gross_profit = sum(t.pnl for t in all_trades if t.pnl > 0)
            gross_loss = abs(sum(t.pnl for t in all_trades if t.pnl < 0))
            profit_factor = gross_profit / gross_loss if gross_loss != 0 else 0
        else:
            total_return_pct = 0.0
            sharpe = 0.0
            max_drawdown = 0.0
            win_rate = 0.0
            profit_factor = 0.0
        
        # Degradation statistics
        degradations = [w.is_degradation for w in windows if w.is_degradation != 0]
        avg_degradation = np.mean(degradations) if degradations else 0.0
        std_degradation = np.std(degradations) if degradations else 0.0
        
        # Consistency score (how similar are out-sample returns across windows)
        oos_returns = [
            w.out_sample_result.total_return_percent
            for w in windows
            if w.out_sample_result
        ]
        consistency = 1.0 - (np.std(oos_returns) / np.mean(np.abs(oos_returns))) if oos_returns else 0.0
        consistency = max(0.0, min(1.0, consistency))
        
        # Parameter stability
        param_stability = self._calculate_param_stability(windows)
        
        return WalkForwardResult(
            config=self.config,
            strategy_name=strategy_name,
            windows=windows,
            total_windows=len(windows),
            combined_equity_curve=combined_equity,
            combined_trades=all_trades,
            total_return_pct=total_return_pct,
            sharpe_ratio=sharpe,
            max_drawdown=max_drawdown,
            win_rate=win_rate,
            profit_factor=profit_factor,
            avg_is_degradation=avg_degradation,
            std_is_degradation=std_degradation,
            consistency_score=consistency,
            param_stability=param_stability
        )
    
    def _calculate_sharpe(self, returns: pd.Series) -> float:
        """Calculate Sharpe ratio"""
        if len(returns) == 0 or returns.std() == 0:
            return 0.0
        return np.sqrt(252) * returns.mean() / returns.std()
    
    def _calculate_param_stability(
        self,
        windows: List[WalkForwardWindow]
    ) -> Dict[str, float]:
        """
        Calculate parameter stability across windows
        
        Returns coefficient of variation for each parameter
        """
        if not windows or not windows[0].best_params:
            return {}
        
        # Collect parameter values across windows
        param_values = {}
        for param_name in windows[0].best_params.keys():
            values = []
            for window in windows:
                if param_name in window.best_params:
                    val = window.best_params[param_name]
                    # Only include numeric values
                    if isinstance(val, (int, float)):
                        values.append(val)
            
            if values:
                # Coefficient of variation
                mean_val = np.mean(values)
                std_val = np.std(values)
                cv = std_val / mean_val if mean_val != 0 else 0.0
                param_values[param_name] = cv
        
        return param_values
