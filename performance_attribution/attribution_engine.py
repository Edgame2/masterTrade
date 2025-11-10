"""
Attribution Engine - Core performance attribution system

Decomposes strategy returns into:
- Factor exposures (market beta, momentum, volatility, etc.)
- Alpha (skill-based excess returns)
- Strategy component contributions
- Risk-adjusted metrics
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
from scipy import stats
from scipy.optimize import minimize
import logging

logger = logging.getLogger(__name__)


class AttributionMethod(Enum):
    """Attribution calculation methods"""
    BRINSON = "brinson"  # Brinson-Fachler attribution
    FACTOR_REGRESSION = "factor_regression"  # Regression-based
    RETURNS_BASED = "returns_based"  # Returns-based style analysis
    HOLDINGS_BASED = "holdings_based"  # Holdings-based attribution


@dataclass
class AttributionConfig:
    """Configuration for attribution analysis"""
    
    # Time period
    start_date: datetime
    end_date: datetime
    
    # Attribution method
    method: AttributionMethod = AttributionMethod.FACTOR_REGRESSION
    
    # Factor model
    use_market_factor: bool = True
    use_momentum_factor: bool = True
    use_volatility_factor: bool = True
    use_size_factor: bool = True
    use_value_factor: bool = False  # Less relevant for crypto
    
    # Rolling window settings
    rolling_window_days: int = 90
    min_observations: int = 30
    
    # Risk-free rate (annual)
    risk_free_rate: float = 0.04  # 4% annual
    
    # Confidence level for intervals
    confidence_level: float = 0.95
    
    # Component attribution
    attribute_by_regime: bool = True
    attribute_by_timeframe: bool = True
    attribute_by_signal_type: bool = True


@dataclass
class FactorExposure:
    """Exposure to a single factor"""
    
    factor_name: str
    beta: float  # Factor loading
    beta_std_error: float
    t_statistic: float
    p_value: float
    is_significant: bool
    
    # Contribution to returns
    factor_return: float  # Factor's return
    contribution: float  # beta * factor_return
    contribution_pct: float  # % of total return
    
    # Time-varying
    rolling_beta: Optional[pd.Series] = None
    beta_stability: Optional[float] = None  # CV of rolling betas


@dataclass
class AlphaBetaDecomposition:
    """Alpha and beta decomposition"""
    
    # Alpha (skill-based returns)
    alpha_annual: float
    alpha_daily: float
    alpha_std_error: float
    alpha_t_stat: float
    alpha_p_value: float
    is_alpha_significant: bool
    
    # Information ratio
    information_ratio: float
    
    # Beta (market exposure)
    market_beta: float
    market_beta_std_error: float
    
    # Decomposition
    alpha_contribution: float  # Alpha * days
    beta_contribution: float  # Beta * market_return
    residual: float  # Unexplained
    
    # Fit quality
    r_squared: float
    adjusted_r_squared: float
    
    # Rolling analysis
    rolling_alpha: Optional[pd.Series] = None
    rolling_beta: Optional[pd.Series] = None
    alpha_stability: Optional[float] = None


@dataclass
class ComponentContribution:
    """Contribution from a strategy component"""
    
    component_name: str
    component_type: str  # regime, signal, timeframe, etc.
    
    # Performance
    total_return: float
    contribution_pct: float  # % of strategy return
    
    # Risk-adjusted
    sharpe_ratio: float
    win_rate: float
    
    # Volume
    num_trades: int
    avg_trade_return: float
    
    # Time
    active_days: int
    active_pct: float  # % of total days


@dataclass
class AttributionResult:
    """Complete attribution analysis result"""
    
    strategy_name: str
    start_date: datetime
    end_date: datetime
    
    # Overall performance
    total_return: float
    total_return_annual: float
    benchmark_return: float
    excess_return: float
    
    # Alpha-beta decomposition
    alpha_beta: AlphaBetaDecomposition
    
    # Factor exposures
    factor_exposures: Dict[str, FactorExposure]
    
    # Component contributions
    regime_contributions: Dict[str, ComponentContribution]
    signal_contributions: Dict[str, ComponentContribution]
    timeframe_contributions: Dict[str, ComponentContribution]
    
    # Time series
    cumulative_returns: pd.Series
    cumulative_alpha: pd.Series
    cumulative_benchmark: pd.Series
    
    # Quality metrics
    tracking_error: float
    active_share: Optional[float] = None
    
    # Attribution summary
    explained_return: float  # Return explained by factors
    unexplained_return: float  # Alpha + residual


class AttributionEngine:
    """
    Core attribution engine
    
    Performs factor-based attribution analysis to understand
    where strategy returns come from.
    """
    
    def __init__(self, config: AttributionConfig):
        self.config = config
        self.logger = logging.getLogger(__name__)
    
    async def analyze(
        self,
        returns: pd.Series,
        factor_returns: Dict[str, pd.Series],
        benchmark_returns: pd.Series,
        trades: Optional[List[Dict]] = None,
        strategy_name: str = "Strategy"
    ) -> AttributionResult:
        """
        Perform complete attribution analysis
        
        Args:
            returns: Strategy returns (daily)
            factor_returns: Dictionary of factor returns
            benchmark_returns: Benchmark returns (daily)
            trades: Optional list of trades for component attribution
            strategy_name: Name of strategy
        
        Returns:
            Complete attribution result
        """
        self.logger.info(f"Starting attribution analysis for {strategy_name}")
        
        # Align dates
        dates = returns.index.intersection(benchmark_returns.index)
        for factor_name in list(factor_returns.keys()):
            dates = dates.intersection(factor_returns[factor_name].index)
        
        returns = returns.loc[dates]
        benchmark_returns = benchmark_returns.loc[dates]
        factor_returns = {k: v.loc[dates] for k, v in factor_returns.items()}
        
        # Calculate overall metrics
        total_return = (1 + returns).prod() - 1
        total_return_annual = (1 + total_return) ** (252 / len(returns)) - 1
        benchmark_return = (1 + benchmark_returns).prod() - 1
        excess_return = total_return - benchmark_return
        
        # Alpha-beta decomposition
        alpha_beta = self._calculate_alpha_beta(
            returns, benchmark_returns, factor_returns
        )
        
        # Factor exposures
        factor_exposures = self._calculate_factor_exposures(
            returns, factor_returns
        )
        
        # Component contributions
        regime_contributions = {}
        signal_contributions = {}
        timeframe_contributions = {}
        
        if trades:
            regime_contributions = self._attribute_by_regime(trades, total_return)
            signal_contributions = self._attribute_by_signal(trades, total_return)
            timeframe_contributions = self._attribute_by_timeframe(trades, total_return)
        
        # Time series
        cumulative_returns = (1 + returns).cumprod()
        cumulative_benchmark = (1 + benchmark_returns).cumprod()
        cumulative_alpha = cumulative_returns / cumulative_benchmark
        
        # Tracking error
        tracking_error = (returns - benchmark_returns).std() * np.sqrt(252)
        
        # Explained vs unexplained return
        explained_return = sum(fe.contribution for fe in factor_exposures.values())
        unexplained_return = total_return - explained_return
        
        result = AttributionResult(
            strategy_name=strategy_name,
            start_date=self.config.start_date,
            end_date=self.config.end_date,
            total_return=total_return,
            total_return_annual=total_return_annual,
            benchmark_return=benchmark_return,
            excess_return=excess_return,
            alpha_beta=alpha_beta,
            factor_exposures=factor_exposures,
            regime_contributions=regime_contributions,
            signal_contributions=signal_contributions,
            timeframe_contributions=timeframe_contributions,
            cumulative_returns=cumulative_returns,
            cumulative_alpha=cumulative_alpha,
            cumulative_benchmark=cumulative_benchmark,
            tracking_error=tracking_error,
            explained_return=explained_return,
            unexplained_return=unexplained_return
        )
        
        self.logger.info(
            f"Attribution complete: Alpha={alpha_beta.alpha_annual:.2%}, "
            f"Beta={alpha_beta.market_beta:.2f}, "
            f"IR={alpha_beta.information_ratio:.2f}"
        )
        
        return result
    
    def _calculate_alpha_beta(
        self,
        returns: pd.Series,
        benchmark_returns: pd.Series,
        factor_returns: Dict[str, pd.Series]
    ) -> AlphaBetaDecomposition:
        """Calculate alpha-beta decomposition using factor regression"""
        
        # Prepare data
        y = returns.values
        X = []
        
        # Market factor (benchmark)
        X.append(benchmark_returns.values)
        
        # Additional factors
        for factor_return in factor_returns.values():
            X.append(factor_return.values)
        
        X = np.column_stack(X)
        
        # Add constant for alpha
        X_with_const = np.column_stack([np.ones(len(X)), X])
        
        # OLS regression
        beta_hat = np.linalg.lstsq(X_with_const, y, rcond=None)[0]
        alpha_daily = beta_hat[0]
        market_beta = beta_hat[1]
        
        # Residuals
        y_hat = X_with_const @ beta_hat
        residuals = y - y_hat
        
        # Standard errors
        n = len(y)
        k = len(beta_hat)
        sigma_squared = np.sum(residuals ** 2) / (n - k)
        var_beta = sigma_squared * np.linalg.inv(X_with_const.T @ X_with_const)
        se_alpha = np.sqrt(var_beta[0, 0])
        se_market_beta = np.sqrt(var_beta[1, 1])
        
        # T-statistics and p-values
        t_alpha = alpha_daily / se_alpha if se_alpha > 0 else 0
        p_alpha = 2 * (1 - stats.t.cdf(abs(t_alpha), n - k))
        is_significant = p_alpha < (1 - self.config.confidence_level)
        
        # Annualized alpha
        alpha_annual = alpha_daily * 252
        
        # Information ratio
        excess_returns = returns - benchmark_returns
        information_ratio = (excess_returns.mean() * 252) / (excess_returns.std() * np.sqrt(252))
        
        # Contributions
        alpha_contribution = alpha_daily * len(returns)
        beta_contribution = market_beta * benchmark_returns.sum()
        residual = returns.sum() - alpha_contribution - beta_contribution
        
        # R-squared
        ss_res = np.sum(residuals ** 2)
        ss_tot = np.sum((y - np.mean(y)) ** 2)
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
        adjusted_r_squared = 1 - (1 - r_squared) * (n - 1) / (n - k)
        
        # Rolling alpha and beta
        rolling_alpha = None
        rolling_beta = None
        alpha_stability = None
        
        if self.config.rolling_window_days > 0:
            rolling_alpha, rolling_beta = self._calculate_rolling_alpha_beta(
                returns, benchmark_returns
            )
            if rolling_alpha is not None and len(rolling_alpha) > 1:
                alpha_stability = rolling_alpha.std() / abs(rolling_alpha.mean()) if rolling_alpha.mean() != 0 else np.inf
        
        return AlphaBetaDecomposition(
            alpha_annual=alpha_annual,
            alpha_daily=alpha_daily,
            alpha_std_error=se_alpha,
            alpha_t_stat=t_alpha,
            alpha_p_value=p_alpha,
            is_alpha_significant=is_significant,
            information_ratio=information_ratio,
            market_beta=market_beta,
            market_beta_std_error=se_market_beta,
            alpha_contribution=alpha_contribution,
            beta_contribution=beta_contribution,
            residual=residual,
            r_squared=r_squared,
            adjusted_r_squared=adjusted_r_squared,
            rolling_alpha=rolling_alpha,
            rolling_beta=rolling_beta,
            alpha_stability=alpha_stability
        )
    
    def _calculate_rolling_alpha_beta(
        self,
        returns: pd.Series,
        benchmark_returns: pd.Series
    ) -> Tuple[Optional[pd.Series], Optional[pd.Series]]:
        """Calculate rolling alpha and beta"""
        
        window = self.config.rolling_window_days
        if window >= len(returns):
            return None, None
        
        rolling_alpha = []
        rolling_beta = []
        dates = []
        
        for i in range(window, len(returns)):
            window_returns = returns.iloc[i-window:i]
            window_benchmark = benchmark_returns.iloc[i-window:i]
            
            # Simple regression
            X = np.column_stack([
                np.ones(len(window_benchmark)),
                window_benchmark.values
            ])
            y = window_returns.values
            
            try:
                beta_hat = np.linalg.lstsq(X, y, rcond=None)[0]
                rolling_alpha.append(beta_hat[0] * 252)  # Annualized
                rolling_beta.append(beta_hat[1])
                dates.append(returns.index[i])
            except:
                continue
        
        if not rolling_alpha:
            return None, None
        
        return (
            pd.Series(rolling_alpha, index=dates),
            pd.Series(rolling_beta, index=dates)
        )
    
    def _calculate_factor_exposures(
        self,
        returns: pd.Series,
        factor_returns: Dict[str, pd.Series]
    ) -> Dict[str, FactorExposure]:
        """Calculate exposure to each factor"""
        
        exposures = {}
        
        # Prepare regression
        y = returns.values
        X_factors = []
        factor_names = []
        
        for name, factor_return in factor_returns.items():
            X_factors.append(factor_return.values)
            factor_names.append(name)
        
        if not X_factors:
            return exposures
        
        X = np.column_stack(X_factors)
        X_with_const = np.column_stack([np.ones(len(X)), X])
        
        # Regression
        beta_hat = np.linalg.lstsq(X_with_const, y, rcond=None)[0]
        alpha = beta_hat[0]
        betas = beta_hat[1:]
        
        # Residuals and standard errors
        y_hat = X_with_const @ beta_hat
        residuals = y - y_hat
        n = len(y)
        k = len(beta_hat)
        sigma_squared = np.sum(residuals ** 2) / (n - k)
        var_beta = sigma_squared * np.linalg.inv(X_with_const.T @ X_with_const)
        
        # Calculate for each factor
        for i, factor_name in enumerate(factor_names):
            beta = betas[i]
            se_beta = np.sqrt(var_beta[i+1, i+1])
            t_stat = beta / se_beta if se_beta > 0 else 0
            p_value = 2 * (1 - stats.t.cdf(abs(t_stat), n - k))
            is_significant = p_value < (1 - self.config.confidence_level)
            
            # Contribution
            factor_return = factor_returns[factor_name].sum()
            contribution = beta * factor_return
            contribution_pct = contribution / returns.sum() * 100 if returns.sum() != 0 else 0
            
            # Rolling beta
            rolling_beta = None
            beta_stability = None
            
            if self.config.rolling_window_days > 0:
                rolling_beta = self._calculate_rolling_factor_beta(
                    returns, factor_returns[factor_name]
                )
                if rolling_beta is not None and len(rolling_beta) > 1:
                    beta_stability = rolling_beta.std() / abs(rolling_beta.mean()) if rolling_beta.mean() != 0 else np.inf
            
            exposures[factor_name] = FactorExposure(
                factor_name=factor_name,
                beta=beta,
                beta_std_error=se_beta,
                t_statistic=t_stat,
                p_value=p_value,
                is_significant=is_significant,
                factor_return=factor_return,
                contribution=contribution,
                contribution_pct=contribution_pct,
                rolling_beta=rolling_beta,
                beta_stability=beta_stability
            )
        
        return exposures
    
    def _calculate_rolling_factor_beta(
        self,
        returns: pd.Series,
        factor_returns: pd.Series
    ) -> Optional[pd.Series]:
        """Calculate rolling beta for a single factor"""
        
        window = self.config.rolling_window_days
        if window >= len(returns):
            return None
        
        rolling_betas = []
        dates = []
        
        for i in range(window, len(returns)):
            window_returns = returns.iloc[i-window:i]
            window_factor = factor_returns.iloc[i-window:i]
            
            # Simple regression
            X = np.column_stack([
                np.ones(len(window_factor)),
                window_factor.values
            ])
            y = window_returns.values
            
            try:
                beta_hat = np.linalg.lstsq(X, y, rcond=None)[0]
                rolling_betas.append(beta_hat[1])
                dates.append(returns.index[i])
            except:
                continue
        
        if not rolling_betas:
            return None
        
        return pd.Series(rolling_betas, index=dates)
    
    def _attribute_by_regime(
        self,
        trades: List[Dict],
        total_return: float
    ) -> Dict[str, ComponentContribution]:
        """Attribute returns by market regime"""
        
        contributions = {}
        
        # Group by regime
        regime_groups = {}
        for trade in trades:
            regime = trade.get('regime', 'unknown')
            if regime not in regime_groups:
                regime_groups[regime] = []
            regime_groups[regime].append(trade)
        
        # Calculate contribution for each regime
        for regime, regime_trades in regime_groups.items():
            regime_return = sum(t.get('pnl_pct', 0) for t in regime_trades)
            num_trades = len(regime_trades)
            wins = sum(1 for t in regime_trades if t.get('pnl_pct', 0) > 0)
            win_rate = wins / num_trades if num_trades > 0 else 0
            avg_return = regime_return / num_trades if num_trades > 0 else 0
            
            # Estimate active days (approximate)
            active_days = sum(
                (t.get('exit_time', t.get('entry_time')) - t.get('entry_time')).days
                for t in regime_trades
                if 'entry_time' in t
            )
            
            contributions[regime] = ComponentContribution(
                component_name=regime,
                component_type="regime",
                total_return=regime_return,
                contribution_pct=regime_return / total_return * 100 if total_return != 0 else 0,
                sharpe_ratio=0.0,  # Would need time series
                win_rate=win_rate,
                num_trades=num_trades,
                avg_trade_return=avg_return,
                active_days=active_days,
                active_pct=0.0  # Would need total days
            )
        
        return contributions
    
    def _attribute_by_signal(
        self,
        trades: List[Dict],
        total_return: float
    ) -> Dict[str, ComponentContribution]:
        """Attribute returns by signal type"""
        
        contributions = {}
        
        # Group by signal type
        signal_groups = {}
        for trade in trades:
            signal = trade.get('signal_type', 'unknown')
            if signal not in signal_groups:
                signal_groups[signal] = []
            signal_groups[signal].append(trade)
        
        # Calculate contribution for each signal
        for signal, signal_trades in signal_groups.items():
            signal_return = sum(t.get('pnl_pct', 0) for t in signal_trades)
            num_trades = len(signal_trades)
            wins = sum(1 for t in signal_trades if t.get('pnl_pct', 0) > 0)
            win_rate = wins / num_trades if num_trades > 0 else 0
            avg_return = signal_return / num_trades if num_trades > 0 else 0
            
            contributions[signal] = ComponentContribution(
                component_name=signal,
                component_type="signal",
                total_return=signal_return,
                contribution_pct=signal_return / total_return * 100 if total_return != 0 else 0,
                sharpe_ratio=0.0,
                win_rate=win_rate,
                num_trades=num_trades,
                avg_trade_return=avg_return,
                active_days=0,
                active_pct=0.0
            )
        
        return contributions
    
    def _attribute_by_timeframe(
        self,
        trades: List[Dict],
        total_return: float
    ) -> Dict[str, ComponentContribution]:
        """Attribute returns by timeframe"""
        
        contributions = {}
        
        # Group by timeframe
        timeframe_groups = {}
        for trade in trades:
            timeframe = trade.get('timeframe', 'unknown')
            if timeframe not in timeframe_groups:
                timeframe_groups[timeframe] = []
            timeframe_groups[timeframe].append(trade)
        
        # Calculate contribution for each timeframe
        for timeframe, tf_trades in timeframe_groups.items():
            tf_return = sum(t.get('pnl_pct', 0) for t in tf_trades)
            num_trades = len(tf_trades)
            wins = sum(1 for t in tf_trades if t.get('pnl_pct', 0) > 0)
            win_rate = wins / num_trades if num_trades > 0 else 0
            avg_return = tf_return / num_trades if num_trades > 0 else 0
            
            contributions[timeframe] = ComponentContribution(
                component_name=timeframe,
                component_type="timeframe",
                total_return=tf_return,
                contribution_pct=tf_return / total_return * 100 if total_return != 0 else 0,
                sharpe_ratio=0.0,
                win_rate=win_rate,
                num_trades=num_trades,
                avg_trade_return=avg_return,
                active_days=0,
                active_pct=0.0
            )
        
        return contributions
