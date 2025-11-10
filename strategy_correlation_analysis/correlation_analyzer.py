"""
Strategy Correlation Analyzer

Comprehensive analysis of correlations between trading strategies including:
- Cross-strategy correlation tracking
- Rolling correlation analysis with multiple time windows
- Correlation breakdown by market conditions
- Correlation decay analysis and half-life estimation
- Strategy pair analysis and clustering
"""

import logging
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Union
from dataclasses import dataclass, field
from enum import Enum
import scipy.stats as stats
from scipy.cluster.hierarchy import linkage, dendrogram, fcluster
from scipy.spatial.distance import squareform
import warnings

logger = logging.getLogger(__name__)


class CorrelationType(Enum):
    """Types of correlation analysis"""
    PEARSON = "pearson"
    SPEARMAN = "spearman"
    KENDALL = "kendall"
    ROLLING_PEARSON = "rolling_pearson"
    EXPONENTIAL_WEIGHTED = "exponential_weighted"


class TimeWindow(Enum):
    """Time windows for correlation analysis"""
    INTRADAY = "1H"
    DAILY = "1D"
    WEEKLY = "1W"
    MONTHLY = "1M"
    QUARTERLY = "3M"
    YEARLY = "1Y"


class MarketCondition(Enum):
    """Market condition classifications"""
    BULL = "bull"
    BEAR = "bear"
    SIDEWAYS = "sideways"
    HIGH_VOLATILITY = "high_volatility"
    LOW_VOLATILITY = "low_volatility"
    CRISIS = "crisis"


@dataclass
class StrategyPair:
    """Strategy pair for correlation analysis"""
    strategy1: str
    strategy2: str
    
    def __post_init__(self):
        # Ensure consistent ordering for symmetry
        if self.strategy1 > self.strategy2:
            self.strategy1, self.strategy2 = self.strategy2, self.strategy1
    
    def __hash__(self):
        return hash((self.strategy1, self.strategy2))
    
    def __str__(self):
        return f"{self.strategy1}-{self.strategy2}"


@dataclass
class CorrelationResult:
    """Result of correlation analysis between strategies"""
    pair: StrategyPair
    correlation: float
    p_value: float
    confidence_interval: Tuple[float, float]
    sample_size: int
    correlation_type: CorrelationType
    time_window: TimeWindow
    market_condition: Optional[MarketCondition] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    significance_level: float = 0.05
    
    @property
    def is_significant(self) -> bool:
        """Check if correlation is statistically significant"""
        return self.p_value < self.significance_level
    
    @property
    def correlation_strength(self) -> str:
        """Classify correlation strength"""
        abs_corr = abs(self.correlation)
        if abs_corr < 0.1:
            return "negligible"
        elif abs_corr < 0.3:
            return "weak"
        elif abs_corr < 0.5:
            return "moderate"
        elif abs_corr < 0.7:
            return "strong"
        else:
            return "very_strong"
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "pair": str(self.pair),
            "strategy1": self.pair.strategy1,
            "strategy2": self.pair.strategy2,
            "correlation": self.correlation,
            "p_value": self.p_value,
            "confidence_interval": self.confidence_interval,
            "sample_size": self.sample_size,
            "correlation_type": self.correlation_type.value,
            "time_window": self.time_window.value,
            "market_condition": self.market_condition.value if self.market_condition else None,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "is_significant": self.is_significant,
            "correlation_strength": self.correlation_strength,
            "significance_level": self.significance_level
        }


@dataclass
class RollingCorrelation:
    """Rolling correlation analysis results"""
    pair: StrategyPair
    correlations: pd.Series
    window_size: int
    min_periods: int
    correlation_type: CorrelationType
    
    @property
    def mean_correlation(self) -> float:
        """Mean rolling correlation"""
        return float(self.correlations.mean())
    
    @property
    def correlation_volatility(self) -> float:
        """Volatility of correlations"""
        return float(self.correlations.std())
    
    @property
    def correlation_trend(self) -> float:
        """Linear trend in correlations"""
        if len(self.correlations) < 2:
            return 0.0
        
        x = np.arange(len(self.correlations))
        slope, _, _, _, _ = stats.linregress(x, self.correlations.values)
        return float(slope)
    
    def get_correlation_percentiles(self) -> Dict[str, float]:
        """Get correlation percentiles"""
        return {
            "p5": float(self.correlations.quantile(0.05)),
            "p25": float(self.correlations.quantile(0.25)),
            "p50": float(self.correlations.quantile(0.50)),
            "p75": float(self.correlations.quantile(0.75)),
            "p95": float(self.correlations.quantile(0.95))
        }
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "pair": str(self.pair),
            "strategy1": self.pair.strategy1,
            "strategy2": self.pair.strategy2,
            "window_size": self.window_size,
            "min_periods": self.min_periods,
            "correlation_type": self.correlation_type.value,
            "mean_correlation": self.mean_correlation,
            "correlation_volatility": self.correlation_volatility,
            "correlation_trend": self.correlation_trend,
            "percentiles": self.get_correlation_percentiles(),
            "sample_size": len(self.correlations),
            "correlations_data": self.correlations.to_dict()
        }


@dataclass
class CorrelationMatrix:
    """Correlation matrix for multiple strategies"""
    strategies: List[str]
    correlation_matrix: pd.DataFrame
    p_value_matrix: pd.DataFrame
    correlation_type: CorrelationType
    time_window: TimeWindow
    market_condition: Optional[MarketCondition] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    @property
    def average_correlation(self) -> float:
        """Average pairwise correlation"""
        # Get upper triangle excluding diagonal
        mask = np.triu(np.ones_like(self.correlation_matrix, dtype=bool), k=1)
        correlations = self.correlation_matrix.values[mask]
        return float(np.mean(correlations))
    
    @property
    def correlation_dispersion(self) -> float:
        """Dispersion of pairwise correlations"""
        mask = np.triu(np.ones_like(self.correlation_matrix, dtype=bool), k=1)
        correlations = self.correlation_matrix.values[mask]
        return float(np.std(correlations))
    
    def get_strategy_clustering(self, method: str = "ward", n_clusters: int = 3) -> Dict[str, int]:
        """Cluster strategies based on correlation matrix"""
        try:
            # Convert correlation matrix to distance matrix
            distance_matrix = 1 - self.correlation_matrix.abs()
            
            # Perform hierarchical clustering
            condensed_distances = squareform(distance_matrix.values, checks=False)
            linkage_matrix = linkage(condensed_distances, method=method)
            
            # Get cluster assignments
            cluster_labels = fcluster(linkage_matrix, n_clusters, criterion='maxclust')
            
            return dict(zip(self.strategies, cluster_labels))
        
        except Exception as e:
            logger.warning(f"Clustering failed: {e}")
            return {strategy: 1 for strategy in self.strategies}
    
    def get_most_correlated_pairs(self, n: int = 5) -> List[Tuple[str, str, float]]:
        """Get most highly correlated strategy pairs"""
        pairs = []
        
        for i in range(len(self.strategies)):
            for j in range(i + 1, len(self.strategies)):
                strategy1 = self.strategies[i]
                strategy2 = self.strategies[j]
                correlation = self.correlation_matrix.iloc[i, j]
                pairs.append((strategy1, strategy2, correlation))
        
        # Sort by absolute correlation
        pairs.sort(key=lambda x: abs(x[2]), reverse=True)
        return pairs[:n]
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "strategies": self.strategies,
            "correlation_matrix": self.correlation_matrix.to_dict(),
            "p_value_matrix": self.p_value_matrix.to_dict(),
            "correlation_type": self.correlation_type.value,
            "time_window": self.time_window.value,
            "market_condition": self.market_condition.value if self.market_condition else None,
            "timestamp": self.timestamp.isoformat(),
            "average_correlation": self.average_correlation,
            "correlation_dispersion": self.correlation_dispersion,
            "most_correlated_pairs": self.get_most_correlated_pairs(),
            "strategy_clustering": self.get_strategy_clustering()
        }


class CorrelationAnalyzer:
    """
    Comprehensive strategy correlation analyzer
    
    Provides advanced correlation analysis between trading strategies including:
    - Static correlation analysis with statistical significance testing
    - Rolling correlation analysis with multiple time windows
    - Correlation breakdown by market conditions
    - Correlation decay analysis and half-life estimation
    - Strategy clustering based on correlation patterns
    """
    
    def __init__(self):
        self.correlation_cache: Dict[str, CorrelationResult] = {}
        self.rolling_correlation_cache: Dict[str, RollingCorrelation] = {}
        
    def calculate_correlation(
        self,
        strategy1_returns: pd.Series,
        strategy2_returns: pd.Series,
        strategy1_name: str,
        strategy2_name: str,
        correlation_type: CorrelationType = CorrelationType.PEARSON,
        time_window: TimeWindow = TimeWindow.DAILY,
        market_condition: Optional[MarketCondition] = None,
        significance_level: float = 0.05
    ) -> CorrelationResult:
        """
        Calculate correlation between two strategy return series
        """
        # Align series and drop NaN values
        aligned_data = pd.concat([strategy1_returns, strategy2_returns], axis=1).dropna()
        
        if len(aligned_data) < 10:
            raise ValueError("Insufficient data for correlation analysis")
        
        series1 = aligned_data.iloc[:, 0]
        series2 = aligned_data.iloc[:, 1]
        
        # Calculate correlation based on type
        if correlation_type == CorrelationType.PEARSON:
            correlation, p_value = stats.pearsonr(series1, series2)
        elif correlation_type == CorrelationType.SPEARMAN:
            correlation, p_value = stats.spearmanr(series1, series2)
        elif correlation_type == CorrelationType.KENDALL:
            correlation, p_value = stats.kendalltau(series1, series2)
        else:
            # Default to Pearson
            correlation, p_value = stats.pearsonr(series1, series2)
        
        # Calculate confidence interval
        n = len(series1)
        z_transform = np.arctanh(correlation)
        standard_error = 1 / np.sqrt(n - 3)
        z_critical = stats.norm.ppf(1 - significance_level/2)
        
        z_lower = z_transform - z_critical * standard_error
        z_upper = z_transform + z_critical * standard_error
        
        confidence_interval = (np.tanh(z_lower), np.tanh(z_upper))
        
        # Create strategy pair
        pair = StrategyPair(strategy1_name, strategy2_name)
        
        return CorrelationResult(
            pair=pair,
            correlation=correlation,
            p_value=p_value,
            confidence_interval=confidence_interval,
            sample_size=n,
            correlation_type=correlation_type,
            time_window=time_window,
            market_condition=market_condition,
            start_date=series1.index[0] if hasattr(series1.index[0], 'date') else None,
            end_date=series1.index[-1] if hasattr(series1.index[-1], 'date') else None,
            significance_level=significance_level
        )
    
    def calculate_rolling_correlation(
        self,
        strategy1_returns: pd.Series,
        strategy2_returns: pd.Series,
        strategy1_name: str,
        strategy2_name: str,
        window_size: int = 30,
        min_periods: int = 10,
        correlation_type: CorrelationType = CorrelationType.ROLLING_PEARSON
    ) -> RollingCorrelation:
        """
        Calculate rolling correlation between two strategy return series
        """
        # Align series
        aligned_data = pd.concat([strategy1_returns, strategy2_returns], axis=1, keys=[strategy1_name, strategy2_name])
        
        # Calculate rolling correlation
        if correlation_type == CorrelationType.ROLLING_PEARSON:
            rolling_corr = aligned_data.iloc[:, 0].rolling(
                window=window_size, 
                min_periods=min_periods
            ).corr(aligned_data.iloc[:, 1])
        elif correlation_type == CorrelationType.EXPONENTIAL_WEIGHTED:
            # Use exponentially weighted correlation
            rolling_corr = aligned_data.iloc[:, 0].ewm(
                span=window_size, 
                min_periods=min_periods
            ).corr(aligned_data.iloc[:, 1])
        else:
            # Default to rolling Pearson
            rolling_corr = aligned_data.iloc[:, 0].rolling(
                window=window_size, 
                min_periods=min_periods
            ).corr(aligned_data.iloc[:, 1])
        
        # Remove NaN values
        rolling_corr = rolling_corr.dropna()
        
        # Create strategy pair
        pair = StrategyPair(strategy1_name, strategy2_name)
        
        return RollingCorrelation(
            pair=pair,
            correlations=rolling_corr,
            window_size=window_size,
            min_periods=min_periods,
            correlation_type=correlation_type
        )
    
    def calculate_correlation_matrix(
        self,
        strategy_returns: Dict[str, pd.Series],
        correlation_type: CorrelationType = CorrelationType.PEARSON,
        time_window: TimeWindow = TimeWindow.DAILY,
        market_condition: Optional[MarketCondition] = None
    ) -> CorrelationMatrix:
        """
        Calculate correlation matrix for multiple strategies
        """
        # Align all strategy returns
        returns_df = pd.DataFrame(strategy_returns)
        returns_df = returns_df.dropna()
        
        if len(returns_df) < 10:
            raise ValueError("Insufficient data for correlation matrix calculation")
        
        strategies = list(returns_df.columns)
        
        # Calculate correlation matrix
        if correlation_type == CorrelationType.PEARSON:
            corr_matrix = returns_df.corr(method='pearson')
        elif correlation_type == CorrelationType.SPEARMAN:
            corr_matrix = returns_df.corr(method='spearman')
        elif correlation_type == CorrelationType.KENDALL:
            corr_matrix = returns_df.corr(method='kendall')
        else:
            corr_matrix = returns_df.corr(method='pearson')
        
        # Calculate p-value matrix
        n_strategies = len(strategies)
        p_value_matrix = pd.DataFrame(
            np.ones((n_strategies, n_strategies)),
            index=strategies,
            columns=strategies
        )
        
        for i, strategy1 in enumerate(strategies):
            for j, strategy2 in enumerate(strategies):
                if i != j:
                    if correlation_type == CorrelationType.PEARSON:
                        _, p_val = stats.pearsonr(returns_df[strategy1], returns_df[strategy2])
                    elif correlation_type == CorrelationType.SPEARMAN:
                        _, p_val = stats.spearmanr(returns_df[strategy1], returns_df[strategy2])
                    elif correlation_type == CorrelationType.KENDALL:
                        _, p_val = stats.kendalltau(returns_df[strategy1], returns_df[strategy2])
                    else:
                        _, p_val = stats.pearsonr(returns_df[strategy1], returns_df[strategy2])
                    
                    p_value_matrix.iloc[i, j] = p_val
                else:
                    p_value_matrix.iloc[i, j] = 0.0  # Perfect correlation on diagonal
        
        return CorrelationMatrix(
            strategies=strategies,
            correlation_matrix=corr_matrix,
            p_value_matrix=p_value_matrix,
            correlation_type=correlation_type,
            time_window=time_window,
            market_condition=market_condition
        )
    
    def analyze_correlation_decay(
        self,
        strategy1_returns: pd.Series,
        strategy2_returns: pd.Series,
        strategy1_name: str,
        strategy2_name: str,
        max_lag_days: int = 60
    ) -> Dict[str, Union[float, List[float]]]:
        """
        Analyze correlation decay over time lags
        """
        # Align series
        aligned_data = pd.concat([strategy1_returns, strategy2_returns], axis=1).dropna()
        
        if len(aligned_data) < max_lag_days + 10:
            raise ValueError("Insufficient data for correlation decay analysis")
        
        series1 = aligned_data.iloc[:, 0]
        series2 = aligned_data.iloc[:, 1]
        
        # Calculate correlations at different lags
        lags = list(range(0, max_lag_days + 1))
        correlations = []
        
        for lag in lags:
            if lag == 0:
                # Contemporaneous correlation
                corr, _ = stats.pearsonr(series1, series2)
            else:
                # Lagged correlation
                if len(series1) > lag:
                    corr, _ = stats.pearsonr(series1[:-lag], series2[lag:])
                else:
                    corr = np.nan
            
            correlations.append(corr)
        
        # Remove NaN values
        valid_indices = ~np.isnan(correlations)
        valid_lags = np.array(lags)[valid_indices]
        valid_correlations = np.array(correlations)[valid_indices]
        
        # Estimate half-life (time for correlation to decay to half)
        if len(valid_correlations) > 2 and valid_correlations[0] > 0:
            half_correlation = valid_correlations[0] / 2
            
            # Find when correlation first drops below half
            half_life_idx = np.where(valid_correlations <= half_correlation)[0]
            half_life = float(valid_lags[half_life_idx[0]]) if len(half_life_idx) > 0 else np.inf
        else:
            half_life = np.inf
        
        # Fit exponential decay model: corr(t) = corr(0) * exp(-λt)
        try:
            if len(valid_correlations) > 3 and valid_correlations[0] > 0:
                # Use log-linear regression
                log_correlations = np.log(np.abs(valid_correlations))
                slope, intercept, r_value, _, _ = stats.linregress(valid_lags, log_correlations)
                
                decay_rate = -slope
                initial_correlation = np.exp(intercept)
                fit_quality = r_value ** 2
            else:
                decay_rate = np.nan
                initial_correlation = np.nan
                fit_quality = np.nan
        
        except Exception as e:
            logger.warning(f"Decay model fitting failed: {e}")
            decay_rate = np.nan
            initial_correlation = np.nan
            fit_quality = np.nan
        
        return {
            "pair": str(StrategyPair(strategy1_name, strategy2_name)),
            "lags": lags,
            "correlations": correlations,
            "half_life_days": half_life,
            "decay_rate": decay_rate,
            "initial_correlation": initial_correlation,
            "fit_quality": fit_quality,
            "contemporaneous_correlation": correlations[0] if correlations else np.nan
        }
    
    def batch_correlation_analysis(
        self,
        strategy_returns: Dict[str, pd.Series],
        correlation_type: CorrelationType = CorrelationType.PEARSON,
        time_window: TimeWindow = TimeWindow.DAILY,
        market_condition: Optional[MarketCondition] = None,
        include_rolling: bool = True,
        rolling_window: int = 30
    ) -> Dict[str, Union[List[CorrelationResult], List[RollingCorrelation], CorrelationMatrix]]:
        """
        Perform comprehensive correlation analysis for all strategy pairs
        """
        strategies = list(strategy_returns.keys())
        
        # Pairwise correlation analysis
        pairwise_correlations = []
        rolling_correlations = []
        
        for i, strategy1 in enumerate(strategies):
            for j, strategy2 in enumerate(strategies[i+1:], i+1):
                try:
                    # Static correlation
                    corr_result = self.calculate_correlation(
                        strategy_returns[strategy1],
                        strategy_returns[strategy2],
                        strategy1,
                        strategy2,
                        correlation_type,
                        time_window,
                        market_condition
                    )
                    pairwise_correlations.append(corr_result)
                    
                    # Rolling correlation if requested
                    if include_rolling:
                        rolling_corr = self.calculate_rolling_correlation(
                            strategy_returns[strategy1],
                            strategy_returns[strategy2],
                            strategy1,
                            strategy2,
                            rolling_window
                        )
                        rolling_correlations.append(rolling_corr)
                
                except Exception as e:
                    logger.warning(f"Correlation analysis failed for {strategy1}-{strategy2}: {e}")
        
        # Correlation matrix
        try:
            correlation_matrix = self.calculate_correlation_matrix(
                strategy_returns, correlation_type, time_window, market_condition
            )
        except Exception as e:
            logger.error(f"Correlation matrix calculation failed: {e}")
            correlation_matrix = None
        
        return {
            "pairwise_correlations": pairwise_correlations,
            "rolling_correlations": rolling_correlations if include_rolling else [],
            "correlation_matrix": correlation_matrix
        }
    
    def generate_correlation_report(
        self,
        analysis_results: Dict,
        include_statistics: bool = True
    ) -> Dict[str, Union[str, Dict, List]]:
        """
        Generate comprehensive correlation analysis report
        """
        pairwise_correlations = analysis_results.get("pairwise_correlations", [])
        rolling_correlations = analysis_results.get("rolling_correlations", [])
        correlation_matrix = analysis_results.get("correlation_matrix")
        
        report = {
            "timestamp": datetime.utcnow().isoformat(),
            "summary": {
                "total_strategy_pairs": len(pairwise_correlations),
                "significant_correlations": sum(1 for corr in pairwise_correlations if corr.is_significant),
                "strong_correlations": sum(1 for corr in pairwise_correlations if abs(corr.correlation) > 0.5)
            }
        }
        
        if include_statistics and pairwise_correlations:
            correlations_values = [corr.correlation for corr in pairwise_correlations]
            
            report["correlation_statistics"] = {
                "mean_correlation": float(np.mean(correlations_values)),
                "median_correlation": float(np.median(correlations_values)),
                "std_correlation": float(np.std(correlations_values)),
                "min_correlation": float(np.min(correlations_values)),
                "max_correlation": float(np.max(correlations_values)),
                "percentiles": {
                    "p25": float(np.percentile(correlations_values, 25)),
                    "p75": float(np.percentile(correlations_values, 75)),
                    "p95": float(np.percentile(correlations_values, 95))
                }
            }
        
        # Top correlated pairs
        if pairwise_correlations:
            sorted_correlations = sorted(pairwise_correlations, key=lambda x: abs(x.correlation), reverse=True)
            report["top_correlated_pairs"] = [corr.to_dict() for corr in sorted_correlations[:10]]
        
        # Rolling correlation insights
        if rolling_correlations:
            report["rolling_correlation_insights"] = {
                "most_volatile_correlation": max(rolling_correlations, key=lambda x: x.correlation_volatility).to_dict(),
                "strongest_trend": max(rolling_correlations, key=lambda x: abs(x.correlation_trend)).to_dict()
            }
        
        # Matrix insights
        if correlation_matrix:
            report["matrix_insights"] = {
                "average_correlation": correlation_matrix.average_correlation,
                "correlation_dispersion": correlation_matrix.correlation_dispersion,
                "strategy_clustering": correlation_matrix.get_strategy_clustering()
            }
        
        return report