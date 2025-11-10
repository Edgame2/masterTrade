"""
Efficient Frontier

Generates and analyzes the efficient frontier for portfolio optimization.
Provides multiple optimal portfolio points and frontier visualization.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import logging
import numpy as np
import pandas as pd

from .portfolio_optimizer import PortfolioOptimizer, OptimizationMethod, OptimizationObjective, PortfolioConstraints

logger = logging.getLogger(__name__)


@dataclass
class FrontierPoint:
    """A point on the efficient frontier"""
    expected_return: float
    expected_volatility: float
    sharpe_ratio: float
    weights: Dict[str, float]
    
    # Additional metrics
    diversification_ratio: Optional[float] = None
    effective_assets: Optional[float] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "expected_return": self.expected_return,
            "expected_volatility": self.expected_volatility,
            "sharpe_ratio": self.sharpe_ratio,
            "weights": self.weights,
            "diversification_ratio": self.diversification_ratio,
            "effective_assets": self.effective_assets,
        }


@dataclass
class OptimalPortfolios:
    """Collection of optimal portfolios"""
    min_variance: FrontierPoint
    max_sharpe: FrontierPoint
    max_return: FrontierPoint
    
    # Risk parity comparison
    risk_parity: Optional[FrontierPoint] = None
    equal_weight: Optional[FrontierPoint] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "min_variance": self.min_variance.to_dict(),
            "max_sharpe": self.max_sharpe.to_dict(),
            "max_return": self.max_return.to_dict(),
            "risk_parity": self.risk_parity.to_dict() if self.risk_parity else None,
            "equal_weight": self.equal_weight.to_dict() if self.equal_weight else None,
        }


class EfficientFrontier:
    """
    Efficient Frontier generator and analyzer.
    
    Generates the mean-variance efficient frontier and identifies
    key portfolio points (min variance, max Sharpe, etc.).
    """
    
    def __init__(
        self,
        expected_returns: Dict[str, float],
        covariance_matrix: pd.DataFrame,
        risk_free_rate: float = 0.02
    ):
        self.expected_returns = expected_returns
        self.covariance_matrix = covariance_matrix
        self.risk_free_rate = risk_free_rate
        
        # Initialize optimizer
        self.optimizer = PortfolioOptimizer(risk_free_rate=risk_free_rate)
        
        # Validate inputs
        self._validate_inputs()
        
        # Get return bounds
        self.min_return = min(expected_returns.values())
        self.max_return = max(expected_returns.values())
    
    def _validate_inputs(self):
        """Validate inputs"""
        assets = list(self.expected_returns.keys())
        
        if not all(asset in self.covariance_matrix.index for asset in assets):
            raise ValueError("Some assets missing from covariance matrix")
        
        if not all(asset in self.covariance_matrix.columns for asset in assets):
            raise ValueError("Some assets missing from covariance matrix columns")
    
    def generate_frontier(
        self,
        num_points: int = 100,
        constraints: Optional[PortfolioConstraints] = None
    ) -> List[FrontierPoint]:
        """
        Generate efficient frontier points.
        
        Args:
            num_points: Number of frontier points to generate
            constraints: Portfolio constraints
            
        Returns:
            List of frontier points sorted by risk
        """
        if constraints is None:
            constraints = PortfolioConstraints()
        
        # Find minimum variance portfolio
        min_var_result = self.optimizer.optimize(
            self.expected_returns,
            self.covariance_matrix,
            OptimizationMethod.MIN_VARIANCE,
            constraints=constraints
        )
        
        if not min_var_result.optimization_success:
            logger.error("Failed to find minimum variance portfolio")
            return []
        
        min_var_return = min_var_result.expected_return
        
        # Adjust return bounds based on constraints
        effective_min_return = max(self.min_return, min_var_return)
        effective_max_return = self.max_return
        
        # Generate target returns
        target_returns = np.linspace(effective_min_return, effective_max_return, num_points)
        
        frontier_points = []
        
        for target_return in target_returns:
            try:
                # Optimize for target return
                result = self.optimizer.optimize(
                    self.expected_returns,
                    self.covariance_matrix,
                    OptimizationMethod.MEAN_VARIANCE,
                    OptimizationObjective.TARGET_RETURN,
                    constraints=constraints,
                    target_return=target_return
                )
                
                if result.optimization_success:
                    point = FrontierPoint(
                        expected_return=result.expected_return,
                        expected_volatility=result.expected_volatility,
                        sharpe_ratio=result.sharpe_ratio,
                        weights=result.weights,
                        diversification_ratio=result.diversification_ratio,
                        effective_assets=result.effective_assets,
                    )
                    frontier_points.append(point)
                
            except Exception as e:
                logger.warning(f"Failed to optimize for return {target_return:.4f}: {e}")
                continue
        
        # Sort by volatility
        frontier_points.sort(key=lambda p: p.expected_volatility)
        
        return frontier_points
    
    def find_optimal_portfolios(
        self,
        constraints: Optional[PortfolioConstraints] = None,
        include_alternatives: bool = True
    ) -> OptimalPortfolios:
        """
        Find key optimal portfolios.
        
        Args:
            constraints: Portfolio constraints
            include_alternatives: Include risk parity and equal weight
            
        Returns:
            Collection of optimal portfolios
        """
        if constraints is None:
            constraints = PortfolioConstraints()
        
        # Minimum Variance Portfolio
        min_var_result = self.optimizer.optimize(
            self.expected_returns,
            self.covariance_matrix,
            OptimizationMethod.MIN_VARIANCE,
            constraints=constraints
        )
        
        min_variance = FrontierPoint(
            expected_return=min_var_result.expected_return,
            expected_volatility=min_var_result.expected_volatility,
            sharpe_ratio=min_var_result.sharpe_ratio,
            weights=min_var_result.weights,
            diversification_ratio=min_var_result.diversification_ratio,
            effective_assets=min_var_result.effective_assets,
        )
        
        # Maximum Sharpe Portfolio
        max_sharpe_result = self.optimizer.optimize(
            self.expected_returns,
            self.covariance_matrix,
            OptimizationMethod.MAX_SHARPE,
            constraints=constraints
        )
        
        max_sharpe = FrontierPoint(
            expected_return=max_sharpe_result.expected_return,
            expected_volatility=max_sharpe_result.expected_volatility,
            sharpe_ratio=max_sharpe_result.sharpe_ratio,
            weights=max_sharpe_result.weights,
            diversification_ratio=max_sharpe_result.diversification_ratio,
            effective_assets=max_sharpe_result.effective_assets,
        )
        
        # Maximum Return Portfolio (single asset with highest return)
        max_return_asset = max(self.expected_returns, key=self.expected_returns.get)
        max_return_weights = {asset: 0.0 for asset in self.expected_returns.keys()}
        max_return_weights[max_return_asset] = 1.0
        
        max_return_metrics = self.optimizer.calculate_portfolio_metrics(
            max_return_weights,
            self.expected_returns,
            self.covariance_matrix
        )
        
        max_return = FrontierPoint(
            expected_return=max_return_metrics["expected_return"],
            expected_volatility=max_return_metrics["expected_volatility"],
            sharpe_ratio=max_return_metrics["sharpe_ratio"],
            weights=max_return_weights,
            diversification_ratio=max_return_metrics["diversification_ratio"],
            effective_assets=max_return_metrics["effective_assets"],
        )
        
        # Optional alternative portfolios
        risk_parity = None
        equal_weight = None
        
        if include_alternatives:
            try:
                # Risk Parity Portfolio
                rp_result = self.optimizer.optimize(
                    self.expected_returns,
                    self.covariance_matrix,
                    OptimizationMethod.RISK_PARITY,
                    constraints=constraints
                )
                
                risk_parity = FrontierPoint(
                    expected_return=rp_result.expected_return,
                    expected_volatility=rp_result.expected_volatility,
                    sharpe_ratio=rp_result.sharpe_ratio,
                    weights=rp_result.weights,
                    diversification_ratio=rp_result.diversification_ratio,
                    effective_assets=rp_result.effective_assets,
                )
                
            except Exception as e:
                logger.warning(f"Failed to compute risk parity portfolio: {e}")
            
            try:
                # Equal Weight Portfolio
                eq_result = self.optimizer.optimize(
                    self.expected_returns,
                    self.covariance_matrix,
                    OptimizationMethod.EQUAL_WEIGHT,
                    constraints=constraints
                )
                
                equal_weight = FrontierPoint(
                    expected_return=eq_result.expected_return,
                    expected_volatility=eq_result.expected_volatility,
                    sharpe_ratio=eq_result.sharpe_ratio,
                    weights=eq_result.weights,
                    diversification_ratio=eq_result.diversification_ratio,
                    effective_assets=eq_result.effective_assets,
                )
                
            except Exception as e:
                logger.warning(f"Failed to compute equal weight portfolio: {e}")
        
        return OptimalPortfolios(
            min_variance=min_variance,
            max_sharpe=max_sharpe,
            max_return=max_return,
            risk_parity=risk_parity,
            equal_weight=equal_weight,
        )
    
    def calculate_capital_allocation_line(
        self,
        risky_portfolio_weights: Dict[str, float],
        num_points: int = 100
    ) -> List[Tuple[float, float]]:
        """
        Calculate Capital Allocation Line (CAL) for a risky portfolio.
        
        Args:
            risky_portfolio_weights: Weights of the risky portfolio
            num_points: Number of points on the CAL
            
        Returns:
            List of (risk, return) tuples
        """
        # Calculate risky portfolio metrics
        risky_metrics = self.optimizer.calculate_portfolio_metrics(
            risky_portfolio_weights,
            self.expected_returns,
            self.covariance_matrix
        )
        
        risky_return = risky_metrics["expected_return"]
        risky_vol = risky_metrics["expected_volatility"]
        
        # Sharpe ratio of risky portfolio
        sharpe_ratio = (risky_return - self.risk_free_rate) / risky_vol if risky_vol > 0 else 0
        
        # Generate CAL points
        # Portfolio return = rf + w_risky * (r_risky - rf)
        # Portfolio vol = w_risky * vol_risky
        
        max_leverage = 2.0  # Allow up to 200% in risky asset
        w_risky_values = np.linspace(-0.5, max_leverage, num_points)
        
        cal_points = []
        for w_risky in w_risky_values:
            port_return = self.risk_free_rate + w_risky * (risky_return - self.risk_free_rate)
            port_vol = abs(w_risky) * risky_vol
            cal_points.append((port_vol, port_return))
        
        return cal_points
    
    def analyze_portfolio_efficiency(
        self,
        portfolio_weights: Dict[str, float],
        frontier_points: Optional[List[FrontierPoint]] = None
    ) -> dict:
        """
        Analyze how efficient a given portfolio is relative to the frontier.
        
        Args:
            portfolio_weights: Portfolio to analyze
            frontier_points: Pre-computed frontier points (optional)
            
        Returns:
            Efficiency analysis
        """
        # Calculate portfolio metrics
        portfolio_metrics = self.optimizer.calculate_portfolio_metrics(
            portfolio_weights,
            self.expected_returns,
            self.covariance_matrix
        )
        
        port_return = portfolio_metrics["expected_return"]
        port_vol = portfolio_metrics["expected_volatility"]
        port_sharpe = portfolio_metrics["sharpe_ratio"]
        
        # Generate frontier if not provided
        if frontier_points is None:
            frontier_points = self.generate_frontier(num_points=50)
        
        if not frontier_points:
            return {
                "is_efficient": False,
                "distance_to_frontier": None,
                "equivalent_frontier_portfolio": None,
                "efficiency_ratio": 0.0,
            }
        
        # Find closest frontier point with same return
        target_return_points = [
            p for p in frontier_points
            if abs(p.expected_return - port_return) < 0.001
        ]
        
        if target_return_points:
            # Find minimum volatility for this return level
            min_vol_point = min(target_return_points, key=lambda p: p.expected_volatility)
            efficient_vol = min_vol_point.expected_volatility
            
            # Portfolio is efficient if volatility matches frontier
            is_efficient = abs(port_vol - efficient_vol) < 0.001
            distance_to_frontier = port_vol - efficient_vol
            efficiency_ratio = efficient_vol / port_vol if port_vol > 0 else 0.0
            
        else:
            # Find closest frontier points by return
            frontier_points.sort(key=lambda p: abs(p.expected_return - port_return))
            closest_point = frontier_points[0]
            
            is_efficient = False
            distance_to_frontier = port_vol - closest_point.expected_volatility
            efficiency_ratio = closest_point.expected_volatility / port_vol if port_vol > 0 else 0.0
        
        # Find best Sharpe ratio on frontier
        best_sharpe_point = max(frontier_points, key=lambda p: p.sharpe_ratio)
        
        return {
            "portfolio_return": port_return,
            "portfolio_volatility": port_vol,
            "portfolio_sharpe": port_sharpe,
            "is_efficient": is_efficient,
            "distance_to_frontier": distance_to_frontier,
            "efficiency_ratio": efficiency_ratio,
            "best_frontier_sharpe": best_sharpe_point.sharpe_ratio,
            "sharpe_efficiency": port_sharpe / best_sharpe_point.sharpe_ratio if best_sharpe_point.sharpe_ratio > 0 else 0.0,
        }
    
    def get_risk_return_statistics(self) -> dict:
        """Get risk-return statistics for the asset universe"""
        returns = list(self.expected_returns.values())
        
        # Asset volatilities
        assets = list(self.expected_returns.keys())
        cov_subset = self.covariance_matrix.loc[assets, assets]
        volatilities = [np.sqrt(cov_subset.loc[asset, asset]) for asset in assets]
        
        # Sharpe ratios
        sharpe_ratios = [
            (ret - self.risk_free_rate) / vol if vol > 0 else 0
            for ret, vol in zip(returns, volatilities)
        ]
        
        # Correlations
        corr_matrix = cov_subset.corr()
        
        # Get upper triangular correlations (excluding diagonal)
        n = len(assets)
        correlations = []
        for i in range(n):
            for j in range(i+1, n):
                correlations.append(corr_matrix.iloc[i, j])
        
        return {
            "num_assets": len(assets),
            "return_stats": {
                "min": min(returns),
                "max": max(returns),
                "mean": np.mean(returns),
                "std": np.std(returns),
            },
            "volatility_stats": {
                "min": min(volatilities),
                "max": max(volatilities),
                "mean": np.mean(volatilities),
                "std": np.std(volatilities),
            },
            "sharpe_stats": {
                "min": min(sharpe_ratios),
                "max": max(sharpe_ratios),
                "mean": np.mean(sharpe_ratios),
                "std": np.std(sharpe_ratios),
            },
            "correlation_stats": {
                "min": min(correlations) if correlations else 0,
                "max": max(correlations) if correlations else 0,
                "mean": np.mean(correlations) if correlations else 0,
                "std": np.std(correlations) if correlations else 0,
            },
        }