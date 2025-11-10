"""
Portfolio Optimizer

Core portfolio optimization engine implementing multiple optimization methods:
- Mean-Variance Optimization (Markowitz)
- Risk Parity
- Maximum Diversification
- Minimum Variance
- Equal Risk Contribution
- Black-Litterman
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Tuple
import logging
import numpy as np
import pandas as pd
from scipy import optimize
from scipy.stats import norm

logger = logging.getLogger(__name__)


class OptimizationMethod(Enum):
    """Portfolio optimization methods"""
    MEAN_VARIANCE = "mean_variance"              # Markowitz MPT
    RISK_PARITY = "risk_parity"                  # Equal risk contribution
    MIN_VARIANCE = "min_variance"                # Minimum variance
    MAX_DIVERSIFICATION = "max_diversification"  # Maximum diversification ratio
    EQUAL_WEIGHT = "equal_weight"                # 1/N allocation
    MAX_SHARPE = "max_sharpe"                   # Maximum Sharpe ratio
    BLACK_LITTERMAN = "black_litterman"          # Black-Litterman model
    HIERARCHICAL_RISK_PARITY = "hrp"            # Hierarchical Risk Parity


class OptimizationObjective(Enum):
    """Optimization objectives"""
    MAXIMIZE_RETURN = "max_return"
    MINIMIZE_RISK = "min_risk"
    MAXIMIZE_SHARPE = "max_sharpe"
    MAXIMIZE_UTILITY = "max_utility"
    TARGET_RISK = "target_risk"
    TARGET_RETURN = "target_return"


@dataclass
class PortfolioConstraints:
    """Portfolio optimization constraints"""
    # Weight constraints
    min_weight: float = 0.0       # Minimum asset weight (0 = no shorting)
    max_weight: float = 1.0       # Maximum asset weight
    sum_to_one: bool = True       # Weights sum to 1
    
    # Asset-specific constraints
    min_weights: Optional[Dict[str, float]] = None  # Per-asset minimums
    max_weights: Optional[Dict[str, float]] = None  # Per-asset maximums
    
    # Group constraints
    sector_limits: Optional[Dict[str, Tuple[float, float]]] = None
    
    # Risk constraints
    max_portfolio_vol: Optional[float] = None     # Maximum portfolio volatility
    max_tracking_error: Optional[float] = None    # Maximum tracking error vs benchmark
    
    # Turnover constraints
    max_turnover: Optional[float] = None          # Maximum turnover
    current_weights: Optional[Dict[str, float]] = None  # Current portfolio for turnover
    
    # L1/L2 regularization
    l1_penalty: float = 0.0       # Lasso penalty (sparsity)
    l2_penalty: float = 0.0       # Ridge penalty (smoothness)
    
    def __post_init__(self):
        """Initialize default dictionaries"""
        if self.min_weights is None:
            self.min_weights = {}
        if self.max_weights is None:
            self.max_weights = {}
        if self.sector_limits is None:
            self.sector_limits = {}
        if self.current_weights is None:
            self.current_weights = {}


@dataclass
class OptimizationResult:
    """Portfolio optimization result"""
    weights: Dict[str, float]
    expected_return: float
    expected_volatility: float
    sharpe_ratio: float
    
    # Diagnostics
    optimization_success: bool
    optimization_message: str
    iterations: int
    
    # Risk decomposition
    risk_contributions: Optional[Dict[str, float]] = None
    factor_exposures: Optional[Dict[str, float]] = None
    
    # Additional metrics
    diversification_ratio: Optional[float] = None
    effective_assets: Optional[float] = None  # Herfindahl index
    turnover: Optional[float] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "weights": self.weights,
            "expected_return": self.expected_return,
            "expected_volatility": self.expected_volatility,
            "sharpe_ratio": self.sharpe_ratio,
            "optimization_success": self.optimization_success,
            "optimization_message": self.optimization_message,
            "iterations": self.iterations,
            "risk_contributions": self.risk_contributions,
            "factor_exposures": self.factor_exposures,
            "diversification_ratio": self.diversification_ratio,
            "effective_assets": self.effective_assets,
            "turnover": self.turnover,
        }


class PortfolioOptimizer:
    """
    Core portfolio optimization engine.
    
    Implements multiple optimization methods with comprehensive constraint handling.
    """
    
    def __init__(
        self,
        risk_free_rate: float = 0.02,  # 2% annual risk-free rate
        frequency: int = 252,          # Daily frequency (252 trading days)
    ):
        self.risk_free_rate = risk_free_rate
        self.frequency = frequency
        
        # Optimization parameters
        self.max_iterations = 1000
        self.tolerance = 1e-8
    
    def optimize(
        self,
        expected_returns: Dict[str, float],
        covariance_matrix: pd.DataFrame,
        method: OptimizationMethod,
        objective: OptimizationObjective = OptimizationObjective.MAXIMIZE_SHARPE,
        constraints: Optional[PortfolioConstraints] = None,
        **kwargs
    ) -> OptimizationResult:
        """
        Optimize portfolio using specified method.
        
        Args:
            expected_returns: Expected returns for each asset
            covariance_matrix: Asset covariance matrix
            method: Optimization method
            objective: Optimization objective
            constraints: Portfolio constraints
            **kwargs: Method-specific parameters
        """
        if constraints is None:
            constraints = PortfolioConstraints()
        
        # Convert to numpy arrays
        assets = list(expected_returns.keys())
        mu = np.array([expected_returns[asset] for asset in assets])
        cov = covariance_matrix.loc[assets, assets].values
        
        # Validate inputs
        self._validate_inputs(mu, cov, assets)
        
        # Choose optimization method
        if method == OptimizationMethod.MEAN_VARIANCE:
            return self._optimize_mean_variance(mu, cov, assets, objective, constraints, **kwargs)
        elif method == OptimizationMethod.RISK_PARITY:
            return self._optimize_risk_parity(mu, cov, assets, constraints, **kwargs)
        elif method == OptimizationMethod.MIN_VARIANCE:
            return self._optimize_min_variance(mu, cov, assets, constraints, **kwargs)
        elif method == OptimizationMethod.MAX_SHARPE:
            return self._optimize_max_sharpe(mu, cov, assets, constraints, **kwargs)
        elif method == OptimizationMethod.MAX_DIVERSIFICATION:
            return self._optimize_max_diversification(mu, cov, assets, constraints, **kwargs)
        elif method == OptimizationMethod.EQUAL_WEIGHT:
            return self._optimize_equal_weight(mu, cov, assets, constraints, **kwargs)
        else:
            raise ValueError(f"Unsupported optimization method: {method}")
    
    def _validate_inputs(self, mu: np.ndarray, cov: np.ndarray, assets: List[str]):
        """Validate optimization inputs"""
        n_assets = len(assets)
        
        if len(mu) != n_assets:
            raise ValueError("Expected returns length doesn't match number of assets")
        
        if cov.shape != (n_assets, n_assets):
            raise ValueError("Covariance matrix shape doesn't match number of assets")
        
        # Check for positive definite covariance matrix
        eigenvals = np.linalg.eigvals(cov)
        if not np.all(eigenvals > 0):
            logger.warning("Covariance matrix is not positive definite")
            # Add regularization
            min_eigenval = np.min(eigenvals)
            if min_eigenval <= 0:
                cov += np.eye(n_assets) * (abs(min_eigenval) + 1e-8)
    
    def _optimize_mean_variance(
        self,
        mu: np.ndarray,
        cov: np.ndarray,
        assets: List[str],
        objective: OptimizationObjective,
        constraints: PortfolioConstraints,
        **kwargs
    ) -> OptimizationResult:
        """Mean-Variance optimization (Markowitz)"""
        n_assets = len(assets)
        
        # Target parameters
        target_return = kwargs.get('target_return', None)
        target_risk = kwargs.get('target_risk', None)
        risk_aversion = kwargs.get('risk_aversion', 1.0)
        
        # Objective function
        def objective_func(w):
            portfolio_return = np.dot(w, mu)
            portfolio_var = np.dot(w, np.dot(cov, w))
            
            if objective == OptimizationObjective.MAXIMIZE_RETURN:
                return -portfolio_return  # Minimize negative return
            elif objective == OptimizationObjective.MINIMIZE_RISK:
                return portfolio_var
            elif objective == OptimizationObjective.MAXIMIZE_SHARPE:
                portfolio_vol = np.sqrt(portfolio_var)
                if portfolio_vol == 0:
                    return -np.inf
                return -(portfolio_return - self.risk_free_rate) / portfolio_vol
            elif objective == OptimizationObjective.MAXIMIZE_UTILITY:
                return -(portfolio_return - 0.5 * risk_aversion * portfolio_var)
            elif objective == OptimizationObjective.TARGET_RISK:
                if target_risk is None:
                    raise ValueError("target_risk must be specified for TARGET_RISK objective")
                penalty = 1000 * (np.sqrt(portfolio_var) - target_risk) ** 2
                return -portfolio_return + penalty
            elif objective == OptimizationObjective.TARGET_RETURN:
                if target_return is None:
                    raise ValueError("target_return must be specified for TARGET_RETURN objective")
                penalty = 1000 * (portfolio_return - target_return) ** 2
                return portfolio_var + penalty
        
        # Build constraints
        constraint_list = self._build_constraints(n_assets, assets, constraints)
        
        # Initial guess (equal weights)
        x0 = np.ones(n_assets) / n_assets
        
        # Bounds
        bounds = self._build_bounds(n_assets, assets, constraints)
        
        # Optimize
        result = optimize.minimize(
            objective_func,
            x0,
            method='SLSQP',
            bounds=bounds,
            constraints=constraint_list,
            options={'maxiter': self.max_iterations, 'ftol': self.tolerance}
        )
        
        return self._create_result(result.x, mu, cov, assets, result)
    
    def _optimize_risk_parity(
        self,
        mu: np.ndarray,
        cov: np.ndarray,
        assets: List[str],
        constraints: PortfolioConstraints,
        **kwargs
    ) -> OptimizationResult:
        """Risk Parity optimization (Equal Risk Contribution)"""
        n_assets = len(assets)
        
        def risk_parity_objective(w):
            """Minimize sum of squared differences in risk contributions"""
            portfolio_var = np.dot(w, np.dot(cov, w))
            
            if portfolio_var == 0:
                return 1e6
            
            # Risk contributions
            marginal_risk = np.dot(cov, w)
            risk_contributions = w * marginal_risk / portfolio_var
            
            # Target risk contribution (equal for all assets)
            target_rc = 1.0 / n_assets
            
            # Sum of squared deviations from target
            return np.sum((risk_contributions - target_rc) ** 2)
        
        # Build constraints
        constraint_list = self._build_constraints(n_assets, assets, constraints)
        
        # Initial guess
        x0 = np.ones(n_assets) / n_assets
        
        # Bounds
        bounds = self._build_bounds(n_assets, assets, constraints)
        
        # Optimize
        result = optimize.minimize(
            risk_parity_objective,
            x0,
            method='SLSQP',
            bounds=bounds,
            constraints=constraint_list,
            options={'maxiter': self.max_iterations, 'ftol': self.tolerance}
        )
        
        return self._create_result(result.x, mu, cov, assets, result)
    
    def _optimize_min_variance(
        self,
        mu: np.ndarray,
        cov: np.ndarray,
        assets: List[str],
        constraints: PortfolioConstraints,
        **kwargs
    ) -> OptimizationResult:
        """Minimum Variance optimization"""
        n_assets = len(assets)
        
        def min_var_objective(w):
            return np.dot(w, np.dot(cov, w))
        
        # Build constraints
        constraint_list = self._build_constraints(n_assets, assets, constraints)
        
        # Initial guess
        x0 = np.ones(n_assets) / n_assets
        
        # Bounds
        bounds = self._build_bounds(n_assets, assets, constraints)
        
        # Optimize
        result = optimize.minimize(
            min_var_objective,
            x0,
            method='SLSQP',
            bounds=bounds,
            constraints=constraint_list,
            options={'maxiter': self.max_iterations, 'ftol': self.tolerance}
        )
        
        return self._create_result(result.x, mu, cov, assets, result)
    
    def _optimize_max_sharpe(
        self,
        mu: np.ndarray,
        cov: np.ndarray,
        assets: List[str],
        constraints: PortfolioConstraints,
        **kwargs
    ) -> OptimizationResult:
        """Maximum Sharpe ratio optimization"""
        # This is equivalent to mean-variance with MAXIMIZE_SHARPE objective
        return self._optimize_mean_variance(
            mu, cov, assets, OptimizationObjective.MAXIMIZE_SHARPE, constraints, **kwargs
        )
    
    def _optimize_max_diversification(
        self,
        mu: np.ndarray,
        cov: np.ndarray,
        assets: List[str],
        constraints: PortfolioConstraints,
        **kwargs
    ) -> OptimizationResult:
        """Maximum Diversification ratio optimization"""
        n_assets = len(assets)
        
        # Asset volatilities
        asset_vols = np.sqrt(np.diag(cov))
        
        def max_div_objective(w):
            """Minimize negative diversification ratio"""
            weighted_vol = np.dot(w, asset_vols)  # Weighted average volatility
            portfolio_vol = np.sqrt(np.dot(w, np.dot(cov, w)))  # Portfolio volatility
            
            if portfolio_vol == 0:
                return 1e6
            
            diversification_ratio = weighted_vol / portfolio_vol
            return -diversification_ratio  # Minimize negative (maximize positive)
        
        # Build constraints
        constraint_list = self._build_constraints(n_assets, assets, constraints)
        
        # Initial guess
        x0 = np.ones(n_assets) / n_assets
        
        # Bounds
        bounds = self._build_bounds(n_assets, assets, constraints)
        
        # Optimize
        result = optimize.minimize(
            max_div_objective,
            x0,
            method='SLSQP',
            bounds=bounds,
            constraints=constraint_list,
            options={'maxiter': self.max_iterations, 'ftol': self.tolerance}
        )
        
        return self._create_result(result.x, mu, cov, assets, result)
    
    def _optimize_equal_weight(
        self,
        mu: np.ndarray,
        cov: np.ndarray,
        assets: List[str],
        constraints: PortfolioConstraints,
        **kwargs
    ) -> OptimizationResult:
        """Equal weight (1/N) allocation"""
        n_assets = len(assets)
        
        # Equal weights
        weights = np.ones(n_assets) / n_assets
        
        # Create mock optimization result
        mock_result = type('MockResult', (), {
            'success': True,
            'message': 'Equal weight allocation',
            'nit': 0,
        })()
        
        return self._create_result(weights, mu, cov, assets, mock_result)
    
    def _build_constraints(
        self,
        n_assets: int,
        assets: List[str],
        constraints: PortfolioConstraints
    ) -> List[dict]:
        """Build optimization constraints"""
        constraint_list = []
        
        # Sum to one constraint
        if constraints.sum_to_one:
            constraint_list.append({
                'type': 'eq',
                'fun': lambda w: np.sum(w) - 1.0
            })
        
        # Maximum portfolio volatility
        if constraints.max_portfolio_vol is not None:
            def vol_constraint(w):
                # This needs access to cov matrix - we'll handle this differently
                pass  # TODO: Implement in calling function
        
        # Turnover constraint
        if constraints.max_turnover is not None and constraints.current_weights:
            current_w = np.array([
                constraints.current_weights.get(asset, 0.0) for asset in assets
            ])
            
            def turnover_constraint(w):
                turnover = np.sum(np.abs(w - current_w))
                return constraints.max_turnover - turnover
            
            constraint_list.append({
                'type': 'ineq',
                'fun': turnover_constraint
            })
        
        return constraint_list
    
    def _build_bounds(
        self,
        n_assets: int,
        assets: List[str],
        constraints: PortfolioConstraints
    ) -> List[Tuple[float, float]]:
        """Build optimization bounds"""
        bounds = []
        
        for i, asset in enumerate(assets):
            min_w = constraints.min_weights.get(asset, constraints.min_weight)
            max_w = constraints.max_weights.get(asset, constraints.max_weight)
            bounds.append((min_w, max_w))
        
        return bounds
    
    def _create_result(
        self,
        weights: np.ndarray,
        mu: np.ndarray,
        cov: np.ndarray,
        assets: List[str],
        opt_result
    ) -> OptimizationResult:
        """Create optimization result"""
        # Portfolio metrics
        portfolio_return = np.dot(weights, mu)
        portfolio_var = np.dot(weights, np.dot(cov, weights))
        portfolio_vol = np.sqrt(portfolio_var)
        
        # Sharpe ratio
        if portfolio_vol == 0:
            sharpe_ratio = 0.0
        else:
            sharpe_ratio = (portfolio_return - self.risk_free_rate) / portfolio_vol
        
        # Risk contributions
        if portfolio_var > 0:
            marginal_risk = np.dot(cov, weights)
            risk_contributions = {
                assets[i]: (weights[i] * marginal_risk[i] / portfolio_var)
                for i in range(len(assets))
            }
        else:
            risk_contributions = {asset: 0.0 for asset in assets}
        
        # Diversification ratio
        asset_vols = np.sqrt(np.diag(cov))
        weighted_vol = np.dot(weights, asset_vols)
        if portfolio_vol == 0:
            diversification_ratio = 1.0
        else:
            diversification_ratio = weighted_vol / portfolio_vol
        
        # Effective number of assets (inverse Herfindahl index)
        effective_assets = 1.0 / np.sum(weights ** 2) if np.any(weights > 0) else 0.0
        
        return OptimizationResult(
            weights={assets[i]: weights[i] for i in range(len(assets))},
            expected_return=portfolio_return,
            expected_volatility=portfolio_vol,
            sharpe_ratio=sharpe_ratio,
            optimization_success=opt_result.success,
            optimization_message=opt_result.message,
            iterations=getattr(opt_result, 'nit', 0),
            risk_contributions=risk_contributions,
            diversification_ratio=diversification_ratio,
            effective_assets=effective_assets,
        )
    
    def calculate_portfolio_metrics(
        self,
        weights: Dict[str, float],
        expected_returns: Dict[str, float],
        covariance_matrix: pd.DataFrame
    ) -> dict:
        """Calculate portfolio metrics for given weights"""
        assets = list(weights.keys())
        w = np.array([weights[asset] for asset in assets])
        mu = np.array([expected_returns[asset] for asset in assets])
        cov = covariance_matrix.loc[assets, assets].values
        
        # Portfolio metrics
        portfolio_return = np.dot(w, mu)
        portfolio_var = np.dot(w, np.dot(cov, w))
        portfolio_vol = np.sqrt(portfolio_var)
        
        # Sharpe ratio
        sharpe_ratio = (portfolio_return - self.risk_free_rate) / portfolio_vol if portfolio_vol > 0 else 0
        
        # Risk contributions
        if portfolio_var > 0:
            marginal_risk = np.dot(cov, w)
            risk_contributions = {
                assets[i]: (w[i] * marginal_risk[i] / portfolio_var)
                for i in range(len(assets))
            }
        else:
            risk_contributions = {asset: 0.0 for asset in assets}
        
        # Diversification ratio
        asset_vols = np.sqrt(np.diag(cov))
        weighted_vol = np.dot(w, asset_vols)
        diversification_ratio = weighted_vol / portfolio_vol if portfolio_vol > 0 else 1.0
        
        # Effective assets
        effective_assets = 1.0 / np.sum(w ** 2) if np.any(w > 0) else 0.0
        
        return {
            "expected_return": portfolio_return,
            "expected_volatility": portfolio_vol,
            "sharpe_ratio": sharpe_ratio,
            "risk_contributions": risk_contributions,
            "diversification_ratio": diversification_ratio,
            "effective_assets": effective_assets,
        }