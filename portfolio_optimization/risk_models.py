"""
Risk Models

Implements various risk models for portfolio optimization:
- Sample covariance matrix
- Shrinkage estimators (Ledoit-Wolf)
- Factor risk models (Fama-French, custom factors)
- Exponentially weighted covariance
- Robust covariance estimators
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Tuple
import logging
import numpy as np
import pandas as pd
from scipy import linalg
from scipy.stats import norm

logger = logging.getLogger(__name__)


class RiskModelType(Enum):
    """Risk model types"""
    SAMPLE_COVARIANCE = "sample_covariance"
    SHRINKAGE_COVARIANCE = "shrinkage_covariance"
    EXPONENTIAL_COVARIANCE = "exponential_covariance"
    FACTOR_MODEL = "factor_model"
    ROBUST_COVARIANCE = "robust_covariance"


class CovarianceEstimator(Enum):
    """Covariance estimation methods"""
    SAMPLE = "sample"                    # Sample covariance
    LEDOIT_WOLF = "ledoit_wolf"         # Ledoit-Wolf shrinkage
    OAS = "oas"                         # Oracle Approximating Shrinkage
    EWMA = "ewma"                       # Exponentially Weighted Moving Average
    MCD = "mcd"                         # Minimum Covariance Determinant


@dataclass
class RiskModelResult:
    """Risk model estimation result"""
    covariance_matrix: pd.DataFrame
    correlation_matrix: pd.DataFrame
    volatilities: pd.Series
    
    # Model-specific results
    shrinkage_intensity: Optional[float] = None
    factor_loadings: Optional[pd.DataFrame] = None
    specific_variances: Optional[pd.Series] = None
    factor_covariance: Optional[pd.DataFrame] = None
    
    # Diagnostics
    condition_number: float = 0.0
    is_positive_definite: bool = True
    eigenvalues: Optional[np.ndarray] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary"""
        result = {
            "volatilities": self.volatilities.to_dict(),
            "condition_number": self.condition_number,
            "is_positive_definite": self.is_positive_definite,
        }
        
        if self.shrinkage_intensity is not None:
            result["shrinkage_intensity"] = self.shrinkage_intensity
            
        if self.factor_loadings is not None:
            result["factor_loadings"] = self.factor_loadings.to_dict()
            
        if self.specific_variances is not None:
            result["specific_variances"] = self.specific_variances.to_dict()
            
        return result


class RiskModel:
    """
    Risk model for portfolio optimization.
    
    Provides various covariance matrix estimation methods
    with appropriate shrinkage and regularization.
    """
    
    def __init__(
        self,
        lookback_window: int = 252,  # 1 year of daily data
        min_periods: int = 60,       # Minimum periods for estimation
    ):
        self.lookback_window = lookback_window
        self.min_periods = min_periods
    
    def estimate_covariance(
        self,
        returns: pd.DataFrame,
        method: CovarianceEstimator = CovarianceEstimator.LEDOIT_WOLF,
        **kwargs
    ) -> RiskModelResult:
        """
        Estimate covariance matrix using specified method.
        
        Args:
            returns: Asset returns DataFrame (dates x assets)
            method: Covariance estimation method
            **kwargs: Method-specific parameters
            
        Returns:
            Risk model result with covariance matrix and diagnostics
        """
        # Validate inputs
        if len(returns) < self.min_periods:
            raise ValueError(f"Insufficient data: {len(returns)} < {self.min_periods}")
        
        # Use most recent data within lookback window
        if len(returns) > self.lookback_window:
            returns = returns.tail(self.lookback_window)
        
        # Remove any NaN values
        returns = returns.dropna()
        
        if len(returns) < self.min_periods:
            raise ValueError(f"Insufficient clean data: {len(returns)} < {self.min_periods}")
        
        # Estimate based on method
        if method == CovarianceEstimator.SAMPLE:
            return self._estimate_sample_covariance(returns)
        elif method == CovarianceEstimator.LEDOIT_WOLF:
            return self._estimate_ledoit_wolf_covariance(returns, **kwargs)
        elif method == CovarianceEstimator.EWMA:
            return self._estimate_ewma_covariance(returns, **kwargs)
        elif method == CovarianceEstimator.MCD:
            return self._estimate_robust_covariance(returns, **kwargs)
        else:
            raise ValueError(f"Unsupported covariance estimator: {method}")
    
    def _estimate_sample_covariance(self, returns: pd.DataFrame) -> RiskModelResult:
        """Estimate sample covariance matrix"""
        # Sample covariance
        cov_matrix = returns.cov()
        
        # Annualize (assuming daily returns)
        cov_matrix = cov_matrix * 252
        
        return self._create_result(cov_matrix)
    
    def _estimate_ledoit_wolf_covariance(
        self,
        returns: pd.DataFrame,
        shrinkage_target: str = "single_factor",
        **kwargs
    ) -> RiskModelResult:
        """
        Estimate covariance using Ledoit-Wolf shrinkage.
        
        Shrinks sample covariance towards a structured target.
        """
        # Sample covariance
        sample_cov = returns.cov() * 252
        
        # Define shrinkage target
        if shrinkage_target == "single_factor":
            # Single-factor model target
            target = self._single_factor_target(returns)
        elif shrinkage_target == "constant_correlation":
            # Constant correlation target  
            target = self._constant_correlation_target(returns)
        elif shrinkage_target == "identity":
            # Identity matrix target
            target = pd.DataFrame(
                np.eye(len(returns.columns)),
                index=returns.columns,
                columns=returns.columns
            ) * sample_cov.values.trace() / len(returns.columns)
        else:
            raise ValueError(f"Unknown shrinkage target: {shrinkage_target}")
        
        # Compute optimal shrinkage intensity
        shrinkage_intensity = self._compute_shrinkage_intensity(returns, sample_cov, target)
        
        # Shrunk covariance matrix
        shrunk_cov = (1 - shrinkage_intensity) * sample_cov + shrinkage_intensity * target
        
        result = self._create_result(shrunk_cov)
        result.shrinkage_intensity = shrinkage_intensity
        
        return result
    
    def _estimate_ewma_covariance(
        self,
        returns: pd.DataFrame,
        decay_factor: float = 0.94,
        **kwargs
    ) -> RiskModelResult:
        """
        Estimate covariance using Exponentially Weighted Moving Average.
        
        More recent observations get higher weights.
        """
        n_periods, n_assets = returns.shape
        
        # Initialize with equal weights
        weights = np.array([decay_factor ** i for i in range(n_periods)])
        weights = weights[::-1]  # Reverse so recent gets higher weight
        weights = weights / weights.sum()  # Normalize
        
        # Weighted mean
        weighted_mean = np.average(returns.values, axis=0, weights=weights)
        
        # Weighted covariance
        centered_returns = returns.values - weighted_mean
        
        # Manual computation of weighted covariance
        cov_matrix = np.zeros((n_assets, n_assets))
        
        for i in range(n_periods):
            outer_product = np.outer(centered_returns[i], centered_returns[i])
            cov_matrix += weights[i] * outer_product
        
        # Create DataFrame
        cov_df = pd.DataFrame(
            cov_matrix * 252,  # Annualize
            index=returns.columns,
            columns=returns.columns
        )
        
        return self._create_result(cov_df)
    
    def _estimate_robust_covariance(
        self,
        returns: pd.DataFrame,
        contamination: float = 0.1,
        **kwargs
    ) -> RiskModelResult:
        """
        Estimate robust covariance using Minimum Covariance Determinant.
        
        Robust to outliers in the data.
        """
        try:
            from sklearn.covariance import MinCovDet
        except ImportError:
            logger.warning("sklearn not available, falling back to sample covariance")
            return self._estimate_sample_covariance(returns)
        
        # Fit robust covariance estimator
        robust_cov = MinCovDet(
            store_precision=False,
            assume_centered=False,
            support_fraction=None,
            random_state=42
        )
        
        robust_cov.fit(returns.values)
        
        # Create covariance DataFrame
        cov_df = pd.DataFrame(
            robust_cov.covariance_ * 252,  # Annualize
            index=returns.columns,
            columns=returns.columns
        )
        
        return self._create_result(cov_df)
    
    def _single_factor_target(self, returns: pd.DataFrame) -> pd.DataFrame:
        """
        Create single-factor model shrinkage target.
        
        Assumes all assets have the same beta to a market factor.
        """
        # Use equal-weighted portfolio as market proxy
        market_returns = returns.mean(axis=1)
        
        # Estimate betas
        betas = {}
        for asset in returns.columns:
            asset_returns = returns[asset]
            covariance = np.cov(asset_returns, market_returns)[0, 1]
            market_variance = np.var(market_returns)
            betas[asset] = covariance / market_variance if market_variance > 0 else 0
        
        # Single-factor covariance matrix
        beta_vector = np.array([betas[asset] for asset in returns.columns])
        market_var = np.var(market_returns) * 252  # Annualized
        
        # Factor covariance matrix
        factor_cov = np.outer(beta_vector, beta_vector) * market_var
        
        # Add specific variances (residual variances)
        specific_vars = []
        for asset in returns.columns:
            asset_var = np.var(returns[asset]) * 252
            factor_var = (betas[asset] ** 2) * market_var
            specific_var = max(asset_var - factor_var, 0.01 * asset_var)  # At least 1% specific risk
            specific_vars.append(specific_var)
        
        # Total covariance
        target_cov = factor_cov + np.diag(specific_vars)
        
        return pd.DataFrame(
            target_cov,
            index=returns.columns,
            columns=returns.columns
        )
    
    def _constant_correlation_target(self, returns: pd.DataFrame) -> pd.DataFrame:
        """
        Create constant correlation shrinkage target.
        
        All correlations equal to average correlation.
        """
        # Sample covariance and correlation
        sample_cov = returns.cov() * 252
        sample_corr = returns.corr()
        
        # Average correlation (excluding diagonal)
        n = len(returns.columns)
        avg_corr = (sample_corr.values.sum() - n) / (n * (n - 1))
        
        # Constant correlation matrix
        target_corr = np.full((n, n), avg_corr)
        np.fill_diagonal(target_corr, 1.0)
        
        # Convert to covariance using sample volatilities
        volatilities = np.sqrt(np.diag(sample_cov))
        target_cov = np.outer(volatilities, volatilities) * target_corr
        
        return pd.DataFrame(
            target_cov,
            index=returns.columns,
            columns=returns.columns
        )
    
    def _compute_shrinkage_intensity(
        self,
        returns: pd.DataFrame,
        sample_cov: pd.DataFrame,
        target_cov: pd.DataFrame
    ) -> float:
        """
        Compute optimal shrinkage intensity using Ledoit-Wolf method.
        
        Returns shrinkage parameter between 0 (no shrinkage) and 1 (full shrinkage).
        """
        n_periods, n_assets = returns.shape
        
        # Convert to numpy
        sample_cov_np = sample_cov.values
        target_cov_np = target_cov.values
        
        # Asymptotic variance of sample covariance estimator
        # This is a simplified version - full LW formula is more complex
        
        # Frobenius norm of difference
        diff = sample_cov_np - target_cov_np
        norm_diff_sq = np.sum(diff ** 2)
        
        if norm_diff_sq == 0:
            return 0.0  # No shrinkage needed
        
        # Estimate asymptotic variance (simplified)
        # In practice, this would use the full Ledoit-Wolf formula
        asymptotic_var = np.sum(sample_cov_np ** 2) / n_periods
        
        # Optimal shrinkage intensity
        shrinkage = min(asymptotic_var / norm_diff_sq, 1.0)
        shrinkage = max(shrinkage, 0.0)
        
        return shrinkage
    
    def _create_result(self, cov_matrix: pd.DataFrame) -> RiskModelResult:
        """Create risk model result with diagnostics"""
        # Ensure positive definiteness
        cov_matrix = self._ensure_positive_definite(cov_matrix)
        
        # Correlation matrix
        volatilities = np.sqrt(np.diag(cov_matrix))
        corr_matrix = cov_matrix.div(volatilities, axis=0).div(volatilities, axis=1)
        
        # Diagnostics
        eigenvals = np.linalg.eigvals(cov_matrix.values)
        condition_number = np.max(eigenvals) / np.min(eigenvals) if np.min(eigenvals) > 0 else np.inf
        is_positive_definite = np.all(eigenvals > 0)
        
        return RiskModelResult(
            covariance_matrix=cov_matrix,
            correlation_matrix=corr_matrix,
            volatilities=pd.Series(volatilities, index=cov_matrix.index),
            condition_number=condition_number,
            is_positive_definite=is_positive_definite,
            eigenvalues=eigenvals,
        )
    
    def _ensure_positive_definite(
        self,
        cov_matrix: pd.DataFrame,
        regularization: float = 1e-8
    ) -> pd.DataFrame:
        """
        Ensure covariance matrix is positive definite.
        
        Adds regularization to diagonal if needed.
        """
        eigenvals = np.linalg.eigvals(cov_matrix.values)
        min_eigenval = np.min(eigenvals)
        
        if min_eigenval <= 0:
            # Add regularization to diagonal
            regularization_amount = abs(min_eigenval) + regularization
            cov_matrix = cov_matrix + np.eye(len(cov_matrix)) * regularization_amount
            logger.warning(f"Added regularization: {regularization_amount:.2e}")
        
        return cov_matrix


@dataclass 
class FactorRiskModel:
    """
    Factor-based risk model.
    
    Decomposes risk into factor and specific components:
    Covariance = B * F * B' + D
    
    Where:
    - B: Factor loadings matrix
    - F: Factor covariance matrix  
    - D: Specific variances (diagonal)
    """
    factor_loadings: pd.DataFrame    # Assets x Factors
    factor_covariance: pd.DataFrame  # Factors x Factors
    specific_variances: pd.Series    # Asset-specific variances
    
    def get_covariance_matrix(self) -> pd.DataFrame:
        """Compute full covariance matrix from factor model"""
        # B * F * B'
        factor_part = self.factor_loadings @ self.factor_covariance @ self.factor_loadings.T
        
        # Add specific variances
        specific_part = np.diag(self.specific_variances)
        
        total_cov = factor_part + specific_part
        
        return pd.DataFrame(
            total_cov,
            index=self.factor_loadings.index,
            columns=self.factor_loadings.index
        )
    
    def get_factor_contributions(self) -> Dict[str, pd.DataFrame]:
        """Get risk contributions by factor"""
        contributions = {}
        
        for factor in self.factor_covariance.index:
            # Single factor contribution: b_f * var_f * b_f'
            factor_loadings_f = self.factor_loadings[factor].values
            factor_var = self.factor_covariance.loc[factor, factor]
            
            factor_contrib = np.outer(factor_loadings_f, factor_loadings_f) * factor_var
            
            contributions[factor] = pd.DataFrame(
                factor_contrib,
                index=self.factor_loadings.index,
                columns=self.factor_loadings.index
            )
        
        # Specific risk contribution
        contributions['specific'] = pd.DataFrame(
            np.diag(self.specific_variances),
            index=self.factor_loadings.index,
            columns=self.factor_loadings.index
        )
        
        return contributions
    
    def estimate_from_returns(
        self,
        asset_returns: pd.DataFrame,
        factor_returns: pd.DataFrame,
        method: str = 'ols'
    ) -> 'FactorRiskModel':
        """
        Estimate factor model from returns.
        
        Args:
            asset_returns: Asset returns (time x assets)
            factor_returns: Factor returns (time x factors)
            method: Estimation method ('ols', 'wls')
        """
        # Align dates
        common_dates = asset_returns.index.intersection(factor_returns.index)
        asset_returns = asset_returns.loc[common_dates]
        factor_returns = factor_returns.loc[common_dates]
        
        # Estimate factor loadings using regression
        loadings = {}
        specific_vars = {}
        
        for asset in asset_returns.columns:
            y = asset_returns[asset].values
            X = factor_returns.values
            
            # Add intercept
            X_with_intercept = np.column_stack([np.ones(len(X)), X])
            
            # OLS regression: y = a + B*f + e
            coeffs, residuals, _, _ = np.linalg.lstsq(X_with_intercept, y, rcond=None)
            
            # Factor loadings (exclude intercept)
            loadings[asset] = coeffs[1:]
            
            # Specific variance (residual variance)
            if len(residuals) > 0:
                specific_vars[asset] = residuals[0] / len(y) * 252  # Annualized
            else:
                # Fallback if no residuals returned
                fitted = X_with_intercept @ coeffs
                residuals = y - fitted
                specific_vars[asset] = np.var(residuals) * 252
        
        # Create factor loadings DataFrame
        factor_loadings_df = pd.DataFrame(loadings, index=factor_returns.columns).T
        
        # Factor covariance matrix (annualized)
        factor_cov = factor_returns.cov() * 252
        
        # Specific variances Series
        specific_vars_series = pd.Series(specific_vars)
        
        return FactorRiskModel(
            factor_loadings=factor_loadings_df,
            factor_covariance=factor_cov,
            specific_variances=specific_vars_series
        )