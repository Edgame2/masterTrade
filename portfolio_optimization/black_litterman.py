"""
Black-Litterman Model

Implements the Black-Litterman portfolio optimization model,
which combines market equilibrium with investor views to
generate expected returns and optimal portfolios.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import logging
import numpy as np
import pandas as pd
from scipy import linalg

logger = logging.getLogger(__name__)


@dataclass
class ViewSpecification:
    """
    Investor view specification for Black-Litterman model.
    
    A view expresses an opinion about expected returns:
    - Absolute view: "Asset A will return 10%"
    - Relative view: "Asset A will outperform Asset B by 3%"
    """
    name: str                           # View identifier
    assets: List[str]                   # Assets involved in the view
    weights: List[float]                # Weights for each asset (sum can be != 1)
    expected_return: float              # Expected return of the view
    confidence: float                   # Confidence in the view (0-1)
    
    def __post_init__(self):
        """Validate view specification"""
        if len(self.assets) != len(self.weights):
            raise ValueError("Number of assets must match number of weights")
        
        if not 0 <= self.confidence <= 1:
            raise ValueError("Confidence must be between 0 and 1")
    
    @property
    def is_absolute_view(self) -> bool:
        """Check if this is an absolute view (single asset, weight = 1)"""
        return len(self.assets) == 1 and abs(self.weights[0] - 1.0) < 1e-6
    
    @property
    def is_relative_view(self) -> bool:
        """Check if this is a relative view (multiple assets or weight != 1)"""
        return not self.is_absolute_view
    
    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "name": self.name,
            "assets": self.assets,
            "weights": self.weights,
            "expected_return": self.expected_return,
            "confidence": self.confidence,
            "type": "absolute" if self.is_absolute_view else "relative",
        }


@dataclass
class MarketCapWeights:
    """Market capitalization weights for equilibrium calculation"""
    weights: Dict[str, float]
    total_market_cap: Optional[float] = None
    
    def normalize(self) -> 'MarketCapWeights':
        """Normalize weights to sum to 1"""
        total = sum(self.weights.values())
        if total == 0:
            raise ValueError("Total market cap cannot be zero")
        
        normalized_weights = {
            asset: weight / total 
            for asset, weight in self.weights.items()
        }
        
        return MarketCapWeights(
            weights=normalized_weights,
            total_market_cap=self.total_market_cap
        )


class BlackLittermanModel:
    """
    Black-Litterman portfolio optimization model.
    
    The model combines:
    1. Market equilibrium (implied returns from market cap weights)
    2. Investor views (opinions about future returns)
    3. Uncertainty about both equilibrium and views
    
    To produce:
    - New expected returns (blend of equilibrium and views)
    - New covariance matrix (adjusted for view uncertainty)
    """
    
    def __init__(
        self,
        risk_aversion: float = 3.0,    # Market risk aversion parameter
        tau: float = 0.025,            # Uncertainty scaling parameter
        risk_free_rate: float = 0.02   # Risk-free rate
    ):
        self.risk_aversion = risk_aversion
        self.tau = tau
        self.risk_free_rate = risk_free_rate
    
    def compute_implied_returns(
        self,
        market_cap_weights: MarketCapWeights,
        covariance_matrix: pd.DataFrame
    ) -> pd.Series:
        """
        Compute implied equilibrium returns from market cap weights.
        
        Uses reverse optimization: given market weights are optimal,
        what returns are implied by CAPM equilibrium?
        
        Formula: μ = λ * Σ * w_market
        Where λ is risk aversion parameter
        """
        # Ensure weights are normalized
        market_weights_norm = market_cap_weights.normalize()
        
        # Get assets in covariance matrix order
        assets = covariance_matrix.index.tolist()
        
        # Market weight vector
        w_market = np.array([
            market_weights_norm.weights.get(asset, 0.0) 
            for asset in assets
        ])
        
        # Covariance matrix
        sigma = covariance_matrix.values
        
        # Implied returns: μ = λ * Σ * w
        implied_returns = self.risk_aversion * sigma @ w_market
        
        return pd.Series(implied_returns, index=assets)
    
    def optimize(
        self,
        covariance_matrix: pd.DataFrame,
        market_cap_weights: MarketCapWeights,
        views: List[ViewSpecification],
        view_uncertainty_method: str = "proportional"
    ) -> Tuple[pd.Series, pd.DataFrame]:
        """
        Perform Black-Litterman optimization.
        
        Args:
            covariance_matrix: Asset covariance matrix
            market_cap_weights: Market capitalization weights
            views: List of investor views
            view_uncertainty_method: Method to compute view uncertainty
            
        Returns:
            Tuple of (new_expected_returns, new_covariance_matrix)
        """
        # Step 1: Compute implied equilibrium returns
        mu_prior = self.compute_implied_returns(market_cap_weights, covariance_matrix)
        
        if not views:
            # No views - return prior
            return mu_prior, covariance_matrix
        
        # Step 2: Set up view matrices
        P, Q, Omega = self._setup_view_matrices(views, mu_prior.index, covariance_matrix, view_uncertainty_method)
        
        # Step 3: Black-Litterman formula
        # New expected returns: μ_BL = [(τΣ)^-1 + P'Ω^-1P]^-1 * [(τΣ)^-1*μ + P'Ω^-1*Q]
        # New covariance: Σ_BL = [(τΣ)^-1 + P'Ω^-1P]^-1
        
        sigma = covariance_matrix.values
        tau_sigma = self.tau * sigma
        tau_sigma_inv = linalg.inv(tau_sigma)
        omega_inv = linalg.inv(Omega)
        
        # Precision matrix for new distribution
        M1 = tau_sigma_inv + P.T @ omega_inv @ P
        M1_inv = linalg.inv(M1)
        
        # New expected returns
        mu_BL = M1_inv @ (tau_sigma_inv @ mu_prior.values + P.T @ omega_inv @ Q)
        
        # New covariance matrix
        sigma_BL = M1_inv
        
        # Convert back to pandas
        new_expected_returns = pd.Series(mu_BL, index=mu_prior.index)
        new_covariance_matrix = pd.DataFrame(
            sigma_BL,
            index=covariance_matrix.index,
            columns=covariance_matrix.columns
        )
        
        return new_expected_returns, new_covariance_matrix
    
    def _setup_view_matrices(
        self,
        views: List[ViewSpecification],
        asset_names: List[str],
        covariance_matrix: pd.DataFrame,
        uncertainty_method: str
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Set up P (picking), Q (views), and Ω (uncertainty) matrices.
        
        Args:
            views: List of view specifications
            asset_names: List of asset names in order
            covariance_matrix: Asset covariance matrix
            uncertainty_method: Method to compute view uncertainty
            
        Returns:
            Tuple of (P, Q, Omega) matrices
        """
        n_assets = len(asset_names)
        n_views = len(views)
        
        # P matrix: picking matrix (which assets each view refers to)
        P = np.zeros((n_views, n_assets))
        
        # Q vector: view expectations
        Q = np.zeros(n_views)
        
        for i, view in enumerate(views):
            Q[i] = view.expected_return
            
            for asset, weight in zip(view.assets, view.weights):
                if asset in asset_names:
                    asset_idx = asset_names.index(asset)
                    P[i, asset_idx] = weight
                else:
                    logger.warning(f"Asset {asset} in view {view.name} not found in universe")
        
        # Ω matrix: view uncertainty (diagonal matrix)
        Omega = self._compute_view_uncertainty(views, P, covariance_matrix, uncertainty_method)
        
        return P, Q, Omega
    
    def _compute_view_uncertainty(
        self,
        views: List[ViewSpecification],
        P: np.ndarray,
        covariance_matrix: pd.DataFrame,
        method: str
    ) -> np.ndarray:
        """
        Compute view uncertainty matrix Ω.
        
        Different methods for estimating uncertainty:
        1. Proportional: Ω = τ * P * Σ * P' (scaled by confidence)
        2. Idzorek: Based on confidence levels
        3. Fixed: Use fixed uncertainty values
        """
        n_views = len(views)
        sigma = covariance_matrix.values
        
        if method == "proportional":
            # Proportional to view portfolio variance
            Omega = np.zeros((n_views, n_views))
            
            for i, view in enumerate(views):
                # View portfolio variance: P_i * Σ * P_i'  
                view_variance = P[i:i+1] @ sigma @ P[i:i+1].T
                
                # Scale by tau and inverse confidence
                # Higher confidence = lower uncertainty
                uncertainty_scale = self.tau / max(view.confidence, 0.01)  # Avoid division by zero
                Omega[i, i] = uncertainty_scale * view_variance[0, 0]
        
        elif method == "idzorek":
            # Idzorek method: derive uncertainty from confidence
            Omega = np.zeros((n_views, n_views))
            
            for i, view in enumerate(views):
                # View portfolio variance
                view_variance = P[i:i+1] @ sigma @ P[i:i+1].T
                
                # Idzorek formula for uncertainty
                # ω = (1/c - 1) * τ * P * Σ * P'
                # where c is confidence (0 < c <= 1)
                confidence = max(view.confidence, 0.01)
                uncertainty_multiplier = (1 / confidence - 1) * self.tau
                Omega[i, i] = uncertainty_multiplier * view_variance[0, 0]
        
        elif method == "fixed":
            # Fixed uncertainty based on asset volatilities
            asset_vols = np.sqrt(np.diag(sigma))
            avg_vol = np.mean(asset_vols)
            
            Omega = np.zeros((n_views, n_views))
            for i, view in enumerate(views):
                # Use average volatility scaled by inverse confidence
                base_uncertainty = (avg_vol ** 2) * 0.1  # 10% of average variance
                Omega[i, i] = base_uncertainty / max(view.confidence, 0.01)
        
        else:
            raise ValueError(f"Unknown uncertainty method: {method}")
        
        return Omega
    
    def analyze_view_impact(
        self,
        covariance_matrix: pd.DataFrame,
        market_cap_weights: MarketCapWeights,
        views: List[ViewSpecification]
    ) -> Dict:
        """
        Analyze the impact of views on expected returns and optimal portfolio.
        
        Returns:
            Dictionary with view impact analysis
        """
        # Prior (no views)
        mu_prior = self.compute_implied_returns(market_cap_weights, covariance_matrix)
        
        # Posterior (with views)
        mu_posterior, sigma_posterior = self.optimize(
            covariance_matrix, market_cap_weights, views
        )
        
        # Changes in expected returns
        return_changes = mu_posterior - mu_prior
        
        # View contributions to return changes
        view_contributions = {}
        
        for view in views:
            # Impact of individual view
            mu_single_view, _ = self.optimize(
                covariance_matrix, market_cap_weights, [view]
            )
            
            view_contribution = mu_single_view - mu_prior
            view_contributions[view.name] = {
                "return_impact": view_contribution.to_dict(),
                "max_impact": view_contribution.abs().max(),
                "total_impact": view_contribution.abs().sum(),
            }
        
        # Portfolio weight changes (using simple mean-variance optimization)
        try:
            from .portfolio_optimizer import PortfolioOptimizer, OptimizationMethod
            
            optimizer = PortfolioOptimizer(risk_free_rate=self.risk_free_rate)
            
            # Prior portfolio
            prior_result = optimizer.optimize(
                mu_prior.to_dict(),
                covariance_matrix,
                OptimizationMethod.MAX_SHARPE
            )
            
            # Posterior portfolio  
            posterior_result = optimizer.optimize(
                mu_posterior.to_dict(),
                sigma_posterior,
                OptimizationMethod.MAX_SHARPE
            )
            
            # Weight changes
            weight_changes = {}
            for asset in mu_prior.index:
                prior_weight = prior_result.weights.get(asset, 0.0)
                posterior_weight = posterior_result.weights.get(asset, 0.0)
                weight_changes[asset] = posterior_weight - prior_weight
            
        except ImportError:
            weight_changes = {}
            logger.warning("Portfolio optimizer not available for weight change analysis")
        
        return {
            "prior_returns": mu_prior.to_dict(),
            "posterior_returns": mu_posterior.to_dict(),
            "return_changes": return_changes.to_dict(),
            "view_contributions": view_contributions,
            "weight_changes": weight_changes,
            "total_return_change": return_changes.abs().sum(),
            "max_return_change": return_changes.abs().max(),
        }
    
    def calibrate_tau(
        self,
        covariance_matrix: pd.DataFrame,
        method: str = "empirical",
        **kwargs
    ) -> float:
        """
        Calibrate the τ parameter.
        
        τ represents the uncertainty in the prior (equilibrium returns).
        Different calibration methods:
        1. Empirical: τ = 1/T (where T is sample size)
        2. Ledoit: Based on eigenvalues of covariance matrix
        3. Fixed: Use a fixed value (default 0.025)
        """
        if method == "empirical":
            sample_size = kwargs.get("sample_size", 252)  # Default 1 year
            return 1.0 / sample_size
        
        elif method == "ledoit":
            # Based on trace of covariance matrix
            eigenvals = np.linalg.eigvals(covariance_matrix.values)
            return 1.0 / np.sum(eigenvals)
        
        elif method == "fixed":
            return kwargs.get("tau_value", 0.025)
        
        else:
            raise ValueError(f"Unknown tau calibration method: {method}")


def create_absolute_view(asset: str, expected_return: float, confidence: float) -> ViewSpecification:
    """Helper function to create absolute view"""
    return ViewSpecification(
        name=f"{asset}_absolute_{expected_return:.1%}",
        assets=[asset],
        weights=[1.0],
        expected_return=expected_return,
        confidence=confidence
    )


def create_relative_view(
    asset1: str, 
    asset2: str, 
    relative_return: float, 
    confidence: float
) -> ViewSpecification:
    """Helper function to create relative view (asset1 vs asset2)"""
    return ViewSpecification(
        name=f"{asset1}_vs_{asset2}_{relative_return:+.1%}",
        assets=[asset1, asset2],
        weights=[1.0, -1.0],
        expected_return=relative_return,
        confidence=confidence
    )


def create_sector_view(
    sector_assets: List[str],
    sector_weights: List[float],
    expected_return: float,
    confidence: float,
    sector_name: str
) -> ViewSpecification:
    """Helper function to create sector view"""
    return ViewSpecification(
        name=f"{sector_name}_sector_{expected_return:.1%}",
        assets=sector_assets,
        weights=sector_weights,
        expected_return=expected_return,
        confidence=confidence
    )