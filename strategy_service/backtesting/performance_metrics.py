"""
Performance Metrics and Analysis

Comprehensive performance metrics calculation and analysis tools.
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import structlog

from .backtest_engine import BacktestResult, Trade

logger = structlog.get_logger()


@dataclass
class PerformanceMetrics:
    """Comprehensive performance metrics"""
    
    # Returns
    total_return: float = 0.0
    total_return_pct: float = 0.0
    annualized_return: float = 0.0
    cagr: float = 0.0
    
    # Risk metrics
    volatility: float = 0.0
    annualized_volatility: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    information_ratio: float = 0.0
    
    # Drawdown
    max_drawdown: float = 0.0
    max_drawdown_duration_days: float = 0.0
    avg_drawdown: float = 0.0
    recovery_factor: float = 0.0
    
    # Trade statistics
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    
    # P&L
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    net_profit: float = 0.0
    profit_factor: float = 0.0
    
    # Trade metrics
    avg_win: float = 0.0
    avg_loss: float = 0.0
    largest_win: float = 0.0
    largest_loss: float = 0.0
    avg_win_loss_ratio: float = 0.0
    
    # Risk of ruin
    kelly_criterion: float = 0.0
    optimal_f: float = 0.0
    probability_of_profit: float = 0.0
    
    # Time analysis
    avg_trade_duration_hours: float = 0.0
    avg_winning_duration: float = 0.0
    avg_losing_duration: float = 0.0
    
    # Efficiency
    expectancy: float = 0.0
    expectancy_ratio: float = 0.0
    payoff_ratio: float = 0.0
    
    # Consistency
    consecutive_wins_max: int = 0
    consecutive_losses_max: int = 0
    monthly_win_rate: float = 0.0
    
    # MAE/MFE Analysis
    avg_mae: float = 0.0  # Maximum Adverse Excursion
    avg_mfe: float = 0.0  # Maximum Favorable Excursion
    mae_mfe_ratio: float = 0.0


class PerformanceAnalyzer:
    """
    Performance Analysis Engine
    
    Calculates comprehensive performance metrics from backtest results
    """
    
    @staticmethod
    def analyze(result: BacktestResult) -> PerformanceMetrics:
        """
        Calculate comprehensive performance metrics
        
        Args:
            result: BacktestResult to analyze
            
        Returns:
            PerformanceMetrics with all calculations
        """
        try:
            metrics = PerformanceMetrics()
            
            # Basic returns
            metrics.total_return = result.total_return
            metrics.total_return_pct = result.total_return_percent
            metrics.annualized_return = result.annualized_return
            
            # CAGR
            if result.duration_days > 0:
                years = result.duration_days / 365.25
                metrics.cagr = (((result.final_capital / result.initial_capital) ** (1 / years)) - 1) * 100
            
            # Volatility
            if len(result.equity_curve) > 0:
                returns = result.equity_curve.pct_change().dropna()
                metrics.volatility = returns.std()
                metrics.annualized_volatility = metrics.volatility * np.sqrt(252)
            
            # Risk-adjusted metrics
            metrics.sharpe_ratio = result.sharpe_ratio
            metrics.sortino_ratio = result.sortino_ratio
            metrics.calmar_ratio = result.calmar_ratio
            
            # Drawdown
            metrics.max_drawdown = result.max_drawdown
            metrics.max_drawdown_duration_days = result.max_drawdown_duration_days
            
            if len(result.drawdown_curve) > 0:
                metrics.avg_drawdown = abs(result.drawdown_curve[result.drawdown_curve < 0].mean()) * 100
            
            metrics.recovery_factor = (
                result.total_return / (result.max_drawdown / 100)
                if result.max_drawdown > 0 else 0
            )
            
            # Trade statistics
            metrics.total_trades = result.total_trades
            metrics.winning_trades = result.winning_trades
            metrics.losing_trades = result.losing_trades
            metrics.win_rate = result.win_rate
            
            # P&L
            metrics.gross_profit = result.gross_profit
            metrics.gross_loss = result.gross_loss
            metrics.net_profit = metrics.gross_profit - metrics.gross_loss
            metrics.profit_factor = result.profit_factor
            
            # Trade metrics
            metrics.avg_win = result.avg_win
            metrics.avg_loss = result.avg_loss
            metrics.avg_win_loss_ratio = result.avg_win_loss_ratio
            
            if result.trades:
                winning_pnls = [t.pnl for t in result.trades if t.pnl > 0]
                losing_pnls = [t.pnl for t in result.trades if t.pnl < 0]
                
                metrics.largest_win = max(winning_pnls) if winning_pnls else 0
                metrics.largest_loss = min(losing_pnls) if losing_pnls else 0
            
            # Kelly Criterion
            metrics.kelly_criterion = result.kelly_criterion
            
            # Optimal F (Larry Williams)
            if result.trades:
                metrics.optimal_f = MetricsCalculator.calculate_optimal_f(result.trades)
            
            # Probability of profit
            metrics.probability_of_profit = result.win_rate / 100
            
            # Time analysis
            metrics.avg_trade_duration_hours = result.avg_trade_duration_hours
            
            if result.trades:
                winning_durations = [t.duration_hours for t in result.trades if t.pnl > 0]
                losing_durations = [t.duration_hours for t in result.trades if t.pnl < 0]
                
                metrics.avg_winning_duration = np.mean(winning_durations) if winning_durations else 0
                metrics.avg_losing_duration = np.mean(losing_durations) if losing_durations else 0
            
            # Efficiency
            metrics.expectancy = result.expectancy
            metrics.expectancy_ratio = (
                metrics.expectancy / abs(metrics.avg_loss)
                if metrics.avg_loss != 0 else 0
            )
            metrics.payoff_ratio = (
                abs(metrics.avg_win / metrics.avg_loss)
                if metrics.avg_loss != 0 else 0
            )
            
            # Consistency
            metrics.consecutive_wins_max = result.max_consecutive_wins
            metrics.consecutive_losses_max = result.max_consecutive_losses
            
            # Monthly win rate
            if result.trades:
                metrics.monthly_win_rate = MetricsCalculator.calculate_monthly_win_rate(result.trades)
            
            # MAE/MFE
            if result.trades:
                maes = [t.mae for t in result.trades if t.mae != 0]
                mfes = [t.mfe for t in result.trades if t.mfe != 0]
                
                metrics.avg_mae = np.mean(maes) if maes else 0
                metrics.avg_mfe = np.mean(mfes) if mfes else 0
                metrics.mae_mfe_ratio = (
                    abs(metrics.avg_mae / metrics.avg_mfe)
                    if metrics.avg_mfe != 0 else 0
                )
            
            return metrics
            
        except Exception as e:
            logger.error(f"Error calculating performance metrics: {e}", exc_info=True)
            return PerformanceMetrics()


class MetricsCalculator:
    """Static utility methods for metric calculations"""
    
    @staticmethod
    def calculate_optimal_f(trades: List[Trade]) -> float:
        """
        Calculate Optimal F (Larry Williams)
        
        Optimal fixed fraction for position sizing
        """
        if not trades:
            return 0.0
        
        pnls = [t.pnl for t in trades]
        largest_loss = abs(min(pnls))
        
        if largest_loss == 0:
            return 0.0
        
        # Test different f values
        best_f = 0.0
        best_twrr = -np.inf
        
        for f in np.linspace(0.01, 1.0, 100):
            twrr = 1.0
            for pnl in pnls:
                hpr = 1 + (pnl / largest_loss) * f
                if hpr <= 0:
                    twrr = 0
                    break
                twrr *= hpr
            
            if twrr > best_twrr:
                best_twrr = twrr
                best_f = f
        
        return best_f
    
    @staticmethod
    def calculate_monthly_win_rate(trades: List[Trade]) -> float:
        """Calculate win rate on monthly basis"""
        if not trades:
            return 0.0
        
        # Group trades by month
        monthly_pnl = {}
        
        for trade in trades:
            if trade.exit_time:
                month_key = trade.exit_time.strftime('%Y-%m')
                if month_key not in monthly_pnl:
                    monthly_pnl[month_key] = 0.0
                monthly_pnl[month_key] += trade.pnl
        
        # Calculate win rate
        winning_months = len([pnl for pnl in monthly_pnl.values() if pnl > 0])
        total_months = len(monthly_pnl)
        
        return (winning_months / total_months * 100) if total_months > 0 else 0.0
    
    @staticmethod
    def calculate_information_ratio(
        strategy_returns: pd.Series,
        benchmark_returns: pd.Series
    ) -> float:
        """Calculate Information Ratio vs benchmark"""
        if len(strategy_returns) == 0 or len(benchmark_returns) == 0:
            return 0.0
        
        excess_returns = strategy_returns - benchmark_returns
        
        if excess_returns.std() == 0:
            return 0.0
        
        return np.sqrt(252) * excess_returns.mean() / excess_returns.std()
    
    @staticmethod
    def calculate_ulcer_index(equity_curve: pd.Series) -> float:
        """
        Calculate Ulcer Index (downside volatility measure)
        
        Measures depth and duration of drawdowns
        """
        if len(equity_curve) == 0:
            return 0.0
        
        running_max = equity_curve.expanding().max()
        drawdown_pct = ((equity_curve - running_max) / running_max) * 100
        
        squared_drawdowns = drawdown_pct ** 2
        ulcer = np.sqrt(squared_drawdowns.sum() / len(drawdown_pct))
        
        return abs(ulcer)
    
    @staticmethod
    def calculate_gain_to_pain_ratio(equity_curve: pd.Series) -> float:
        """
        Calculate Gain-to-Pain Ratio
        
        Total return divided by sum of all drawdowns
        """
        if len(equity_curve) < 2:
            return 0.0
        
        total_return = (equity_curve.iloc[-1] / equity_curve.iloc[0]) - 1
        
        running_max = equity_curve.expanding().max()
        drawdowns = running_max - equity_curve
        sum_pain = drawdowns.sum()
        
        if sum_pain == 0:
            return 0.0
        
        return total_return / (sum_pain / equity_curve.iloc[0])
    
    @staticmethod
    def calculate_k_ratio(equity_curve: pd.Series) -> float:
        """
        Calculate K-Ratio (measure of consistency)
        
        Slope of equity curve regression divided by standard error
        """
        if len(equity_curve) < 2:
            return 0.0
        
        x = np.arange(len(equity_curve))
        y = equity_curve.values
        
        # Linear regression
        coeffs = np.polyfit(x, y, 1)
        slope = coeffs[0]
        
        # Standard error
        y_pred = np.polyval(coeffs, x)
        residuals = y - y_pred
        std_error = np.std(residuals)
        
        if std_error == 0:
            return 0.0
        
        k_ratio = slope / std_error
        
        # Normalize by length
        return k_ratio * np.sqrt(len(equity_curve))
