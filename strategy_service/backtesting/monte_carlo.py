"""
Monte Carlo Simulation for Strategy Robustness Testing

Tests strategy robustness by:
- Randomizing trade order
- Bootstrapping returns
- Testing parameter sensitivity
- Simulating different market scenarios
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import structlog
from concurrent.futures import ProcessPoolExecutor
from scipy import stats

from .backtest_engine import BacktestEngine, BacktestConfig, BacktestResult, Trade

logger = structlog.get_logger()


class SimulationType(Enum):
    """Monte Carlo simulation types"""
    TRADE_RANDOMIZATION = "trade_randomization"  # Shuffle trade order
    RETURN_BOOTSTRAPPING = "return_bootstrapping"  # Resample returns
    PARAMETER_SENSITIVITY = "parameter_sensitivity"  # Random parameter variation
    ENTRY_TIMING = "entry_timing"  # Vary entry timing
    EXIT_TIMING = "exit_timing"  # Vary exit timing
    COMBINED = "combined"  # All above


@dataclass
class MonteCarloConfig:
    """Configuration for Monte Carlo simulation"""
    
    # Simulation parameters
    n_simulations: int = 1000
    simulation_type: SimulationType = SimulationType.TRADE_RANDOMIZATION
    
    # Parameter sensitivity
    param_variation_pct: float = 10.0  # ±10% parameter variation
    
    # Entry/exit timing
    timing_variation_bars: int = 5  # ±5 bars variation
    
    # Confidence levels
    confidence_levels: List[float] = field(default_factory=lambda: [0.05, 0.25, 0.50, 0.75, 0.95])
    
    # Parallel processing
    n_workers: int = 4
    
    # Random seed for reproducibility
    random_seed: Optional[int] = 42


@dataclass
class MonteCarloResult:
    """Results from Monte Carlo simulation"""
    
    config: MonteCarloConfig
    strategy_name: str
    original_result: BacktestResult
    
    # Simulation results
    simulations: List[Dict] = field(default_factory=list)
    n_simulations: int = 0
    
    # Distribution statistics
    mean_return: float = 0.0
    std_return: float = 0.0
    median_return: float = 0.0
    
    mean_sharpe: float = 0.0
    std_sharpe: float = 0.0
    median_sharpe: float = 0.0
    
    mean_max_dd: float = 0.0
    std_max_dd: float = 0.0
    median_max_dd: float = 0.0
    
    mean_win_rate: float = 0.0
    std_win_rate: float = 0.0
    
    # Confidence intervals
    return_confidence_intervals: Dict[float, Tuple[float, float]] = field(default_factory=dict)
    sharpe_confidence_intervals: Dict[float, Tuple[float, float]] = field(default_factory=dict)
    drawdown_confidence_intervals: Dict[float, Tuple[float, float]] = field(default_factory=dict)
    
    # Risk metrics
    probability_of_profit: float = 0.0
    probability_of_ruin: float = 0.0  # Probability of >50% drawdown
    value_at_risk_95: float = 0.0
    conditional_var_95: float = 0.0
    
    # Robustness scores
    return_stability_score: float = 0.0  # Lower std = more stable
    sharpe_stability_score: float = 0.0
    parameter_sensitivity_score: float = 0.0
    overall_robustness_score: float = 0.0


class MonteCarloSimulator:
    """
    Monte Carlo Simulator for Strategy Robustness Testing
    """
    
    def __init__(self, config: MonteCarloConfig):
        self.config = config
        
        if self.config.random_seed is not None:
            np.random.seed(self.config.random_seed)
    
    def simulate(
        self,
        original_result: BacktestResult,
        data: Optional[pd.DataFrame] = None,
        strategy_class: Optional[Any] = None,
        strategy_name: str = "Unknown"
    ) -> MonteCarloResult:
        """
        Run Monte Carlo simulation
        
        Args:
            original_result: Original backtest result to test
            data: Historical data (needed for some simulation types)
            strategy_class: Strategy class (needed for parameter sensitivity)
            strategy_name: Name of strategy
            
        Returns:
            MonteCarloResult with robustness analysis
        """
        try:
            logger.info(
                f"Starting Monte Carlo simulation: {strategy_name}",
                n_simulations=self.config.n_simulations,
                simulation_type=self.config.simulation_type.value
            )
            
            simulations = []
            
            # Run simulations based on type
            if self.config.simulation_type == SimulationType.TRADE_RANDOMIZATION:
                simulations = self._trade_randomization(original_result)
                
            elif self.config.simulation_type == SimulationType.RETURN_BOOTSTRAPPING:
                simulations = self._return_bootstrapping(original_result)
                
            elif self.config.simulation_type == SimulationType.PARAMETER_SENSITIVITY:
                if strategy_class is None or data is None:
                    raise ValueError("strategy_class and data required for parameter sensitivity")
                simulations = self._parameter_sensitivity(
                    original_result,
                    data,
                    strategy_class
                )
                
            elif self.config.simulation_type == SimulationType.COMBINED:
                # Combine multiple simulation types
                sims1 = self._trade_randomization(original_result)
                sims2 = self._return_bootstrapping(original_result)
                simulations = sims1 + sims2
            
            # Analyze results
            mc_result = self._analyze_simulations(
                simulations,
                original_result,
                strategy_name
            )
            
            logger.info(
                f"Monte Carlo completed: {strategy_name}",
                mean_return=f"{mc_result.mean_return:.2f}%",
                std_return=f"{mc_result.std_return:.2f}%",
                prob_profit=f"{mc_result.probability_of_profit:.2f}",
                robustness=f"{mc_result.overall_robustness_score:.2f}"
            )
            
            return mc_result
            
        except Exception as e:
            logger.error(f"Error in Monte Carlo simulation: {e}", exc_info=True)
            raise
    
    def _trade_randomization(self, original_result: BacktestResult) -> List[Dict]:
        """
        Simulate by randomizing trade order
        
        This tests if results are dependent on specific trade sequence
        """
        logger.info("Running trade randomization simulation")
        
        simulations = []
        trades = original_result.trades.copy()
        
        for i in range(self.config.n_simulations):
            # Shuffle trades
            np.random.shuffle(trades)
            
            # Recalculate equity curve and metrics
            equity_curve, metrics = self._calculate_metrics_from_trades(
                trades,
                original_result.initial_capital
            )
            
            simulations.append({
                'simulation_id': i,
                'type': 'trade_randomization',
                'total_return_pct': metrics['total_return_pct'],
                'sharpe_ratio': metrics['sharpe_ratio'],
                'max_drawdown': metrics['max_drawdown'],
                'win_rate': metrics['win_rate'],
                'profit_factor': metrics['profit_factor']
            })
        
        return simulations
    
    def _return_bootstrapping(self, original_result: BacktestResult) -> List[Dict]:
        """
        Bootstrap returns to create synthetic equity curves
        
        Resamples returns with replacement to test distribution robustness
        """
        logger.info("Running return bootstrapping simulation")
        
        simulations = []
        
        # Get returns from original equity curve
        returns = original_result.equity_curve.pct_change().dropna()
        
        if len(returns) == 0:
            logger.warning("No returns to bootstrap")
            return simulations
        
        for i in range(self.config.n_simulations):
            # Bootstrap returns
            bootstrapped_returns = np.random.choice(
                returns,
                size=len(returns),
                replace=True
            )
            
            # Create synthetic equity curve
            equity_curve = pd.Series(index=returns.index)
            equity_curve.iloc[0] = original_result.initial_capital
            
            for idx in range(1, len(equity_curve)):
                equity_curve.iloc[idx] = equity_curve.iloc[idx-1] * (1 + bootstrapped_returns[idx-1])
            
            # Calculate metrics
            total_return = equity_curve.iloc[-1] - original_result.initial_capital
            total_return_pct = (total_return / original_result.initial_capital) * 100
            
            sharpe = self._calculate_sharpe(bootstrapped_returns)
            
            running_max = equity_curve.expanding().max()
            drawdown = (equity_curve - running_max) / running_max
            max_drawdown = abs(drawdown.min()) * 100
            
            simulations.append({
                'simulation_id': i,
                'type': 'return_bootstrapping',
                'total_return_pct': total_return_pct,
                'sharpe_ratio': sharpe,
                'max_drawdown': max_drawdown,
                'win_rate': 0.0,  # Not applicable for bootstrapping
                'profit_factor': 0.0
            })
        
        return simulations
    
    def _parameter_sensitivity(
        self,
        original_result: BacktestResult,
        data: pd.DataFrame,
        strategy_class: Any
    ) -> List[Dict]:
        """
        Test sensitivity to parameter variations
        
        Randomly varies parameters within specified range
        """
        logger.info("Running parameter sensitivity simulation")
        
        simulations = []
        original_params = original_result.strategy_params
        
        if not original_params:
            logger.warning("No parameters to vary")
            return simulations
        
        for i in range(self.config.n_simulations):
            # Vary parameters
            varied_params = {}
            for param_name, param_value in original_params.items():
                if isinstance(param_value, (int, float)):
                    # Add random variation
                    variation = np.random.uniform(
                        -self.config.param_variation_pct / 100,
                        self.config.param_variation_pct / 100
                    )
                    varied_value = param_value * (1 + variation)
                    
                    # Ensure positive for certain parameters
                    if param_name in ['period', 'window', 'length']:
                        varied_value = max(1, int(varied_value))
                    
                    varied_params[param_name] = varied_value
                else:
                    varied_params[param_name] = param_value
            
            try:
                # Run backtest with varied parameters
                strategy = strategy_class(**varied_params)
                signals = strategy.generate_signals(data)
                
                engine = BacktestEngine(original_result.config)
                result = engine.run(
                    data,
                    signals,
                    original_result.strategy_name,
                    varied_params
                )
                
                simulations.append({
                    'simulation_id': i,
                    'type': 'parameter_sensitivity',
                    'total_return_pct': result.total_return_percent,
                    'sharpe_ratio': result.sharpe_ratio,
                    'max_drawdown': result.max_drawdown,
                    'win_rate': result.win_rate,
                    'profit_factor': result.profit_factor,
                    'params': varied_params
                })
                
            except Exception as e:
                logger.warning(f"Error in parameter variation {i}: {e}")
                continue
        
        return simulations
    
    def _calculate_metrics_from_trades(
        self,
        trades: List[Trade],
        initial_capital: float
    ) -> Tuple[pd.Series, Dict]:
        """Calculate metrics from list of trades"""
        
        # Build equity curve
        equity = initial_capital
        equity_points = [(trades[0].entry_time, equity)]
        
        for trade in trades:
            if trade.exit_time:
                equity += trade.pnl
                equity_points.append((trade.exit_time, equity))
        
        equity_curve = pd.DataFrame(equity_points, columns=['timestamp', 'equity'])
        equity_curve = equity_curve.set_index('timestamp')['equity']
        
        # Calculate metrics
        total_return = equity - initial_capital
        total_return_pct = (total_return / initial_capital) * 100
        
        returns = equity_curve.pct_change().dropna()
        sharpe = self._calculate_sharpe(returns)
        
        running_max = equity_curve.expanding().max()
        drawdown = (equity_curve - running_max) / running_max
        max_drawdown = abs(drawdown.min()) * 100
        
        winning_trades = len([t for t in trades if t.pnl > 0])
        win_rate = (winning_trades / len(trades) * 100) if trades else 0
        
        gross_profit = sum(t.pnl for t in trades if t.pnl > 0)
        gross_loss = abs(sum(t.pnl for t in trades if t.pnl < 0))
        profit_factor = gross_profit / gross_loss if gross_loss != 0 else 0
        
        metrics = {
            'total_return_pct': total_return_pct,
            'sharpe_ratio': sharpe,
            'max_drawdown': max_drawdown,
            'win_rate': win_rate,
            'profit_factor': profit_factor
        }
        
        return equity_curve, metrics
    
    def _calculate_sharpe(self, returns: pd.Series) -> float:
        """Calculate Sharpe ratio"""
        if len(returns) == 0 or returns.std() == 0:
            return 0.0
        return np.sqrt(252) * returns.mean() / returns.std()
    
    def _analyze_simulations(
        self,
        simulations: List[Dict],
        original_result: BacktestResult,
        strategy_name: str
    ) -> MonteCarloResult:
        """Analyze Monte Carlo simulation results"""
        
        if not simulations:
            logger.warning("No simulations to analyze")
            return MonteCarloResult(
                config=self.config,
                strategy_name=strategy_name,
                original_result=original_result
            )
        
        # Extract metrics
        returns = [s['total_return_pct'] for s in simulations]
        sharpes = [s['sharpe_ratio'] for s in simulations]
        drawdowns = [s['max_drawdown'] for s in simulations]
        win_rates = [s['win_rate'] for s in simulations if s['win_rate'] > 0]
        
        # Calculate statistics
        mean_return = np.mean(returns)
        std_return = np.std(returns)
        median_return = np.median(returns)
        
        mean_sharpe = np.mean(sharpes)
        std_sharpe = np.std(sharpes)
        median_sharpe = np.median(sharpes)
        
        mean_max_dd = np.mean(drawdowns)
        std_max_dd = np.std(drawdowns)
        median_max_dd = np.median(drawdowns)
        
        mean_win_rate = np.mean(win_rates) if win_rates else 0.0
        std_win_rate = np.std(win_rates) if win_rates else 0.0
        
        # Confidence intervals
        return_ci = self._calculate_confidence_intervals(returns)
        sharpe_ci = self._calculate_confidence_intervals(sharpes)
        drawdown_ci = self._calculate_confidence_intervals(drawdowns)
        
        # Risk metrics
        prob_profit = len([r for r in returns if r > 0]) / len(returns)
        prob_ruin = len([d for d in drawdowns if d > 50]) / len(drawdowns)
        
        var_95 = np.percentile(returns, 5)
        # CVaR (Conditional VaR) - average of worst 5%
        worst_5pct = [r for r in returns if r <= var_95]
        cvar_95 = np.mean(worst_5pct) if worst_5pct else var_95
        
        # Robustness scores
        # Return stability: how consistent are returns (lower CV = better)
        cv_returns = std_return / abs(mean_return) if mean_return != 0 else 999
        return_stability = max(0, 1 - cv_returns / 2)  # Normalize to 0-1
        
        # Sharpe stability
        cv_sharpe = std_sharpe / mean_sharpe if mean_sharpe > 0 else 999
        sharpe_stability = max(0, 1 - cv_sharpe)
        
        # Parameter sensitivity (only for param sensitivity simulations)
        param_sensitivity = 0.5  # Default
        if self.config.simulation_type == SimulationType.PARAMETER_SENSITIVITY:
            # Lower std = less sensitive = more robust
            param_sensitivity = max(0, 1 - std_return / 100)
        
        # Overall robustness (weighted average)
        overall_robustness = (
            return_stability * 0.3 +
            sharpe_stability * 0.3 +
            param_sensitivity * 0.2 +
            prob_profit * 0.2
        )
        
        return MonteCarloResult(
            config=self.config,
            strategy_name=strategy_name,
            original_result=original_result,
            simulations=simulations,
            n_simulations=len(simulations),
            mean_return=mean_return,
            std_return=std_return,
            median_return=median_return,
            mean_sharpe=mean_sharpe,
            std_sharpe=std_sharpe,
            median_sharpe=median_sharpe,
            mean_max_dd=mean_max_dd,
            std_max_dd=std_max_dd,
            median_max_dd=median_max_dd,
            mean_win_rate=mean_win_rate,
            std_win_rate=std_win_rate,
            return_confidence_intervals=return_ci,
            sharpe_confidence_intervals=sharpe_ci,
            drawdown_confidence_intervals=drawdown_ci,
            probability_of_profit=prob_profit,
            probability_of_ruin=prob_ruin,
            value_at_risk_95=var_95,
            conditional_var_95=cvar_95,
            return_stability_score=return_stability,
            sharpe_stability_score=sharpe_stability,
            parameter_sensitivity_score=param_sensitivity,
            overall_robustness_score=overall_robustness
        )
    
    def _calculate_confidence_intervals(
        self,
        values: List[float]
    ) -> Dict[float, Tuple[float, float]]:
        """Calculate confidence intervals"""
        intervals = {}
        
        for conf_level in self.config.confidence_levels:
            lower_pct = ((1 - conf_level) / 2) * 100
            upper_pct = (conf_level + (1 - conf_level) / 2) * 100
            
            lower = np.percentile(values, lower_pct)
            upper = np.percentile(values, upper_pct)
            
            intervals[conf_level] = (lower, upper)
        
        return intervals
