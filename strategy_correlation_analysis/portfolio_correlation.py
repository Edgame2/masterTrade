"""
Portfolio Correlation Analysis

Portfolio-level correlation analysis including:
- Diversification scoring and optimization
- Concentration risk analysis
- Correlation-based allocation recommendations
- Portfolio correlation breakdown and attribution
"""

import logging
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Union
from dataclasses import dataclass, field
from enum import Enum
import scipy.stats as stats
from scipy.optimize import minimize
import warnings

logger = logging.getLogger(__name__)


class DiversificationMetric(Enum):
    """Diversification measurement methods"""
    CORRELATION_BASED = "correlation_based"
    HERFINDAHL_INDEX = "herfindahl_index"
    EFFECTIVE_STRATEGIES = "effective_strategies"
    DIVERSIFICATION_RATIO = "diversification_ratio"
    MAXIMUM_DRAWDOWN_RATIO = "maximum_drawdown_ratio"


class AllocationObjective(Enum):
    """Portfolio allocation objectives"""
    MINIMIZE_CORRELATION = "minimize_correlation"
    MAXIMIZE_DIVERSIFICATION = "maximize_diversification"
    EQUAL_RISK_CONTRIBUTION = "equal_risk_contribution"
    MINIMUM_VARIANCE = "minimum_variance"
    RISK_PARITY = "risk_parity"


@dataclass
class DiversificationScore:
    """Portfolio diversification scoring"""
    overall_score: float
    correlation_score: float
    concentration_score: float
    risk_distribution_score: float
    effective_strategies: float
    diversification_ratio: float
    metric_breakdown: Dict[str, float] = field(default_factory=dict)
    
    @property
    def diversification_grade(self) -> str:
        """Grade diversification quality"""
        if self.overall_score >= 0.8:
            return "Excellent"
        elif self.overall_score >= 0.65:
            return "Good"
        elif self.overall_score >= 0.5:
            return "Fair"
        elif self.overall_score >= 0.35:
            return "Poor"
        else:
            return "Very Poor"
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "overall_score": self.overall_score,
            "correlation_score": self.correlation_score,
            "concentration_score": self.concentration_score,
            "risk_distribution_score": self.risk_distribution_score,
            "effective_strategies": self.effective_strategies,
            "diversification_ratio": self.diversification_ratio,
            "diversification_grade": self.diversification_grade,
            "metric_breakdown": self.metric_breakdown
        }


@dataclass
class ConcentrationRisk:
    """Portfolio concentration risk analysis"""
    strategy_concentrations: Dict[str, float]
    herfindahl_index: float
    top_strategy_weight: float
    top_3_strategies_weight: float
    effective_number_strategies: float
    concentration_risk_level: str
    risk_metrics: Dict[str, float] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "strategy_concentrations": self.strategy_concentrations,
            "herfindahl_index": self.herfindahl_index,
            "top_strategy_weight": self.top_strategy_weight,
            "top_3_strategies_weight": self.top_3_strategies_weight,
            "effective_number_strategies": self.effective_number_strategies,
            "concentration_risk_level": self.concentration_risk_level,
            "risk_metrics": self.risk_metrics
        }


@dataclass
class CorrelationBreakdown:
    """Portfolio correlation breakdown analysis"""
    weighted_average_correlation: float
    pairwise_correlations: Dict[str, Dict[str, float]]
    correlation_contributions: Dict[str, float]
    high_correlation_pairs: List[Tuple[str, str, float]]
    correlation_clusters: Dict[str, List[str]]
    risk_contribution_from_correlation: float
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "weighted_average_correlation": self.weighted_average_correlation,
            "pairwise_correlations": self.pairwise_correlations,
            "correlation_contributions": self.correlation_contributions,
            "high_correlation_pairs": [
                {"strategy1": pair[0], "strategy2": pair[1], "correlation": pair[2]}
                for pair in self.high_correlation_pairs
            ],
            "correlation_clusters": self.correlation_clusters,
            "risk_contribution_from_correlation": self.risk_contribution_from_correlation
        }


@dataclass
class AllocationRecommendation:
    """Portfolio allocation recommendation"""
    recommended_weights: Dict[str, float]
    current_weights: Dict[str, float]
    weight_changes: Dict[str, float]
    objective: AllocationObjective
    expected_diversification_improvement: float
    expected_risk_reduction: float
    rebalancing_cost_estimate: float
    recommendation_confidence: float
    rationale: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "recommended_weights": self.recommended_weights,
            "current_weights": self.current_weights,
            "weight_changes": self.weight_changes,
            "objective": self.objective.value,
            "expected_diversification_improvement": self.expected_diversification_improvement,
            "expected_risk_reduction": self.expected_risk_reduction,
            "rebalancing_cost_estimate": self.rebalancing_cost_estimate,
            "recommendation_confidence": self.recommendation_confidence,
            "rationale": self.rationale
        }


class PortfolioCorrelation:
    """
    Comprehensive portfolio-level correlation analysis
    
    Analyzes correlations at the portfolio level including diversification scoring,
    concentration risk analysis, and correlation-based allocation recommendations.
    """
    
    def __init__(self):
        self.correlation_matrix = None
        self.strategy_returns = None
        self.strategy_weights = None
    
    def analyze_portfolio_correlation(
        self,
        strategy_returns: Dict[str, pd.Series],
        strategy_weights: Dict[str, float],
        benchmark_returns: Optional[pd.Series] = None
    ) -> Dict[str, Union[DiversificationScore, ConcentrationRisk, CorrelationBreakdown]]:
        """
        Comprehensive portfolio correlation analysis
        """
        # Store data
        self.strategy_returns = strategy_returns
        self.strategy_weights = strategy_weights
        
        # Align returns and calculate correlation matrix
        returns_df = pd.DataFrame(strategy_returns).dropna()
        self.correlation_matrix = returns_df.corr()
        
        # Normalize weights
        total_weight = sum(strategy_weights.values())
        normalized_weights = {k: v/total_weight for k, v in strategy_weights.items()}
        
        # Calculate diversification score
        diversification_score = self._calculate_diversification_score(
            returns_df, normalized_weights
        )
        
        # Calculate concentration risk
        concentration_risk = self._calculate_concentration_risk(normalized_weights)
        
        # Calculate correlation breakdown
        correlation_breakdown = self._calculate_correlation_breakdown(
            self.correlation_matrix, normalized_weights
        )
        
        return {
            "diversification_score": diversification_score,
            "concentration_risk": concentration_risk,
            "correlation_breakdown": correlation_breakdown
        }
    
    def _calculate_diversification_score(
        self,
        returns_df: pd.DataFrame,
        weights: Dict[str, float]
    ) -> DiversificationScore:
        """Calculate comprehensive diversification score"""
        
        # 1. Correlation-based score
        correlation_score = self._correlation_based_score(self.correlation_matrix, weights)
        
        # 2. Concentration score (1 - Herfindahl Index)
        hhi = sum(w**2 for w in weights.values())
        concentration_score = 1 - hhi
        
        # 3. Risk distribution score
        risk_distribution_score = self._risk_distribution_score(returns_df, weights)
        
        # 4. Effective number of strategies
        effective_strategies = 1 / hhi
        
        # 5. Diversification ratio
        diversification_ratio = self._diversification_ratio(returns_df, weights)
        
        # Combine scores (weighted average)
        overall_score = (
            0.4 * correlation_score +
            0.3 * concentration_score +
            0.2 * risk_distribution_score +
            0.1 * min(1.0, effective_strategies / len(weights))  # Normalize effective strategies
        )
        
        metric_breakdown = {
            "herfindahl_index": hhi,
            "weighted_avg_correlation": self._weighted_average_correlation(self.correlation_matrix, weights),
            "portfolio_volatility": self._portfolio_volatility(returns_df, weights),
            "avg_strategy_volatility": np.mean([returns_df[strategy].std() for strategy in weights.keys()])
        }
        
        return DiversificationScore(
            overall_score=overall_score,
            correlation_score=correlation_score,
            concentration_score=concentration_score,
            risk_distribution_score=risk_distribution_score,
            effective_strategies=effective_strategies,
            diversification_ratio=diversification_ratio,
            metric_breakdown=metric_breakdown
        )
    
    def _correlation_based_score(
        self,
        correlation_matrix: pd.DataFrame,
        weights: Dict[str, float]
    ) -> float:
        """Calculate correlation-based diversification score"""
        
        # Weighted average correlation
        weighted_corr = self._weighted_average_correlation(correlation_matrix, weights)
        
        # Convert correlation to score (lower correlation = higher score)
        # Score ranges from 0 (perfect correlation) to 1 (perfect diversification)
        correlation_score = max(0, 1 - abs(weighted_corr))
        
        return correlation_score
    
    def _weighted_average_correlation(
        self,
        correlation_matrix: pd.DataFrame,
        weights: Dict[str, float]
    ) -> float:
        """Calculate weighted average correlation"""
        
        strategies = list(weights.keys())
        total_weighted_corr = 0.0
        total_weight = 0.0
        
        for i, strategy1 in enumerate(strategies):
            for j, strategy2 in enumerate(strategies):
                if i != j and strategy1 in correlation_matrix.index and strategy2 in correlation_matrix.columns:
                    weight_product = weights[strategy1] * weights[strategy2]
                    correlation = correlation_matrix.loc[strategy1, strategy2]
                    total_weighted_corr += weight_product * correlation
                    total_weight += weight_product
        
        return total_weighted_corr / total_weight if total_weight > 0 else 0
    
    def _risk_distribution_score(
        self,
        returns_df: pd.DataFrame,
        weights: Dict[str, float]
    ) -> float:
        """Calculate risk distribution score"""
        
        # Calculate risk contributions
        strategy_vols = {}
        for strategy in weights.keys():
            if strategy in returns_df.columns:
                strategy_vols[strategy] = returns_df[strategy].std()
        
        # Calculate portfolio volatility
        portfolio_vol = self._portfolio_volatility(returns_df, weights)
        
        if portfolio_vol == 0:
            return 0.0
        
        # Calculate marginal risk contributions
        risk_contributions = {}
        total_risk_contribution = 0.0
        
        for strategy in weights.keys():
            if strategy in strategy_vols:
                # Simplified risk contribution calculation
                marginal_risk = strategy_vols[strategy] * weights[strategy]
                
                # Account for correlations
                corr_adjustment = 0.0
                for other_strategy in weights.keys():
                    if other_strategy != strategy and other_strategy in strategy_vols:
                        if strategy in self.correlation_matrix.index and other_strategy in self.correlation_matrix.columns:
                            correlation = self.correlation_matrix.loc[strategy, other_strategy]
                            corr_adjustment += weights[other_strategy] * strategy_vols[other_strategy] * correlation
                
                risk_contribution = (marginal_risk + corr_adjustment) / portfolio_vol
                risk_contributions[strategy] = risk_contribution
                total_risk_contribution += abs(risk_contribution)
        
        # Normalize risk contributions
        if total_risk_contribution > 0:
            risk_contributions = {k: v/total_risk_contribution for k, v in risk_contributions.items()}
        
        # Score based on how evenly risk is distributed (entropy-like measure)
        n_strategies = len(risk_contributions)
        if n_strategies <= 1:
            return 0.0
        
        # Calculate entropy of risk distribution
        entropy = 0.0
        for risk_contrib in risk_contributions.values():
            if risk_contrib > 0:
                entropy -= risk_contrib * np.log(risk_contrib)
        
        # Normalize by maximum possible entropy
        max_entropy = np.log(n_strategies)
        risk_distribution_score = entropy / max_entropy if max_entropy > 0 else 0.0
        
        return risk_distribution_score
    
    def _portfolio_volatility(
        self,
        returns_df: pd.DataFrame,
        weights: Dict[str, float]
    ) -> float:
        """Calculate portfolio volatility"""
        
        # Create weight vector
        strategies = [s for s in weights.keys() if s in returns_df.columns]
        weight_vector = np.array([weights[s] for s in strategies])
        
        # Get correlation matrix subset
        corr_subset = self.correlation_matrix.loc[strategies, strategies]
        
        # Get volatilities
        vols = np.array([returns_df[s].std() for s in strategies])
        
        # Calculate covariance matrix
        cov_matrix = np.outer(vols, vols) * corr_subset.values
        
        # Portfolio variance
        portfolio_variance = np.dot(weight_vector, np.dot(cov_matrix, weight_vector))
        
        return np.sqrt(portfolio_variance)
    
    def _diversification_ratio(
        self,
        returns_df: pd.DataFrame,
        weights: Dict[str, float]
    ) -> float:
        """Calculate diversification ratio"""
        
        # Weighted average volatility
        weighted_avg_vol = sum(
            weights[strategy] * returns_df[strategy].std()
            for strategy in weights.keys()
            if strategy in returns_df.columns
        )
        
        # Portfolio volatility
        portfolio_vol = self._portfolio_volatility(returns_df, weights)
        
        if portfolio_vol == 0:
            return 0.0
        
        return weighted_avg_vol / portfolio_vol
    
    def _calculate_concentration_risk(
        self,
        weights: Dict[str, float]
    ) -> ConcentrationRisk:
        """Calculate portfolio concentration risk metrics"""
        
        weight_values = list(weights.values())
        weight_values.sort(reverse=True)
        
        # Herfindahl-Hirschman Index
        hhi = sum(w**2 for w in weight_values)
        
        # Top strategy weight
        top_weight = weight_values[0] if weight_values else 0
        
        # Top 3 strategies weight
        top_3_weight = sum(weight_values[:3]) if len(weight_values) >= 3 else sum(weight_values)
        
        # Effective number of strategies
        effective_strategies = 1 / hhi if hhi > 0 else 0
        
        # Concentration risk level
        if hhi > 0.5:
            risk_level = "Very High"
        elif hhi > 0.25:
            risk_level = "High"
        elif hhi > 0.15:
            risk_level = "Moderate"
        elif hhi > 0.1:
            risk_level = "Low"
        else:
            risk_level = "Very Low"
        
        # Additional risk metrics
        risk_metrics = {
            "gini_coefficient": self._gini_coefficient(weight_values),
            "entropy": self._entropy(weight_values),
            "max_weight_ratio": top_weight / (sum(weight_values[1:]) if len(weight_values) > 1 else 1)
        }
        
        return ConcentrationRisk(
            strategy_concentrations=weights,
            herfindahl_index=hhi,
            top_strategy_weight=top_weight,
            top_3_strategies_weight=top_3_weight,
            effective_number_strategies=effective_strategies,
            concentration_risk_level=risk_level,
            risk_metrics=risk_metrics
        )
    
    def _gini_coefficient(self, weights: List[float]) -> float:
        """Calculate Gini coefficient for weight distribution"""
        if not weights or len(weights) == 1:
            return 0.0
        
        weights = sorted(weights)
        n = len(weights)
        index = np.arange(1, n + 1)
        
        return (2 * np.sum(index * weights)) / (n * np.sum(weights)) - (n + 1) / n
    
    def _entropy(self, weights: List[float]) -> float:
        """Calculate entropy of weight distribution"""
        if not weights:
            return 0.0
        
        total_weight = sum(weights)
        if total_weight == 0:
            return 0.0
        
        normalized_weights = [w / total_weight for w in weights]
        entropy = 0.0
        
        for w in normalized_weights:
            if w > 0:
                entropy -= w * np.log(w)
        
        return entropy
    
    def _calculate_correlation_breakdown(
        self,
        correlation_matrix: pd.DataFrame,
        weights: Dict[str, float]
    ) -> CorrelationBreakdown:
        """Calculate detailed correlation breakdown"""
        
        # Weighted average correlation
        weighted_avg_corr = self._weighted_average_correlation(correlation_matrix, weights)
        
        # Pairwise correlations
        pairwise_correlations = {}
        for strategy1 in weights.keys():
            if strategy1 in correlation_matrix.index:
                pairwise_correlations[strategy1] = {}
                for strategy2 in weights.keys():
                    if strategy2 in correlation_matrix.columns and strategy1 != strategy2:
                        pairwise_correlations[strategy1][strategy2] = float(
                            correlation_matrix.loc[strategy1, strategy2]
                        )
        
        # Correlation contributions (how much each strategy contributes to portfolio correlation)
        correlation_contributions = {}
        for strategy in weights.keys():
            if strategy in correlation_matrix.index:
                contribution = 0.0
                for other_strategy in weights.keys():
                    if other_strategy != strategy and other_strategy in correlation_matrix.columns:
                        corr = correlation_matrix.loc[strategy, other_strategy]
                        contribution += weights[strategy] * weights[other_strategy] * corr
                
                correlation_contributions[strategy] = contribution
        
        # High correlation pairs (absolute correlation > 0.5)
        high_correlation_pairs = []
        strategies = list(weights.keys())
        
        for i, strategy1 in enumerate(strategies):
            for strategy2 in strategies[i+1:]:
                if strategy1 in correlation_matrix.index and strategy2 in correlation_matrix.columns:
                    corr = correlation_matrix.loc[strategy1, strategy2]
                    if abs(corr) > 0.5:
                        high_correlation_pairs.append((strategy1, strategy2, float(corr)))
        
        # Sort by absolute correlation
        high_correlation_pairs.sort(key=lambda x: abs(x[2]), reverse=True)
        
        # Correlation clusters (simple clustering based on correlation threshold)
        correlation_clusters = self._identify_correlation_clusters(correlation_matrix, weights, threshold=0.3)
        
        # Risk contribution from correlation
        risk_from_correlation = self._calculate_correlation_risk_contribution(
            correlation_matrix, weights
        )
        
        return CorrelationBreakdown(
            weighted_average_correlation=weighted_avg_corr,
            pairwise_correlations=pairwise_correlations,
            correlation_contributions=correlation_contributions,
            high_correlation_pairs=high_correlation_pairs,
            correlation_clusters=correlation_clusters,
            risk_contribution_from_correlation=risk_from_correlation
        )
    
    def _identify_correlation_clusters(
        self,
        correlation_matrix: pd.DataFrame,
        weights: Dict[str, float],
        threshold: float = 0.3
    ) -> Dict[str, List[str]]:
        """Identify correlation clusters among strategies"""
        
        strategies = [s for s in weights.keys() if s in correlation_matrix.index]
        clusters = {}
        assigned_strategies = set()
        cluster_id = 1
        
        for strategy1 in strategies:
            if strategy1 in assigned_strategies:
                continue
            
            # Start new cluster
            cluster_name = f"cluster_{cluster_id}"
            cluster_strategies = [strategy1]
            assigned_strategies.add(strategy1)
            
            # Find correlated strategies
            for strategy2 in strategies:
                if strategy2 != strategy1 and strategy2 not in assigned_strategies:
                    if strategy2 in correlation_matrix.columns:
                        corr = abs(correlation_matrix.loc[strategy1, strategy2])
                        if corr > threshold:
                            cluster_strategies.append(strategy2)
                            assigned_strategies.add(strategy2)
            
            if len(cluster_strategies) > 1:
                clusters[cluster_name] = cluster_strategies
                cluster_id += 1
        
        return clusters
    
    def _calculate_correlation_risk_contribution(
        self,
        correlation_matrix: pd.DataFrame,
        weights: Dict[str, float]
    ) -> float:
        """Calculate risk contribution from correlations"""
        
        strategies = [s for s in weights.keys() if s in correlation_matrix.index]
        
        if len(strategies) < 2:
            return 0.0
        
        # Calculate portfolio variance with and without correlations
        weight_vector = np.array([weights[s] for s in strategies])
        
        # Variance with correlations
        corr_subset = correlation_matrix.loc[strategies, strategies]
        portfolio_var_with_corr = np.dot(weight_vector, np.dot(corr_subset.values, weight_vector))
        
        # Variance without correlations (diagonal correlation matrix)
        identity_matrix = np.eye(len(strategies))
        portfolio_var_without_corr = np.dot(weight_vector, np.dot(identity_matrix, weight_vector))
        
        # Risk contribution from correlation
        if portfolio_var_without_corr > 0:
            risk_from_correlation = (portfolio_var_with_corr - portfolio_var_without_corr) / portfolio_var_without_corr
        else:
            risk_from_correlation = 0.0
        
        return float(risk_from_correlation)
    
    def generate_allocation_recommendations(
        self,
        strategy_returns: Dict[str, pd.Series],
        current_weights: Dict[str, float],
        objective: AllocationObjective = AllocationObjective.MAXIMIZE_DIVERSIFICATION,
        constraints: Optional[Dict] = None
    ) -> AllocationRecommendation:
        """
        Generate allocation recommendations based on correlation analysis
        """
        
        # Align returns and calculate correlation matrix
        returns_df = pd.DataFrame(strategy_returns).dropna()
        correlation_matrix = returns_df.corr()
        
        # Normalize current weights
        total_weight = sum(current_weights.values())
        normalized_current_weights = {k: v/total_weight for k, v in current_weights.items()}
        
        # Default constraints
        if constraints is None:
            constraints = {
                'min_weight': 0.01,  # Minimum 1% allocation
                'max_weight': 0.5,   # Maximum 50% allocation
                'max_weight_change': 0.2  # Maximum 20% weight change
            }
        
        # Optimize allocation based on objective
        if objective == AllocationObjective.MINIMIZE_CORRELATION:
            recommended_weights = self._minimize_correlation_optimization(
                correlation_matrix, normalized_current_weights, constraints
            )
        elif objective == AllocationObjective.MAXIMIZE_DIVERSIFICATION:
            recommended_weights = self._maximize_diversification_optimization(
                returns_df, correlation_matrix, normalized_current_weights, constraints
            )
        elif objective == AllocationObjective.EQUAL_RISK_CONTRIBUTION:
            recommended_weights = self._equal_risk_contribution_optimization(
                returns_df, correlation_matrix, normalized_current_weights, constraints
            )
        elif objective == AllocationObjective.MINIMUM_VARIANCE:
            recommended_weights = self._minimum_variance_optimization(
                returns_df, correlation_matrix, normalized_current_weights, constraints
            )
        else:
            # Default to equal weights with constraints
            n_strategies = len(current_weights)
            equal_weight = 1.0 / n_strategies
            recommended_weights = {
                strategy: max(constraints['min_weight'], min(constraints['max_weight'], equal_weight))
                for strategy in current_weights.keys()
            }
        
        # Normalize recommended weights
        total_recommended = sum(recommended_weights.values())
        if total_recommended > 0:
            recommended_weights = {k: v/total_recommended for k, v in recommended_weights.items()}
        
        # Calculate weight changes
        weight_changes = {
            strategy: recommended_weights.get(strategy, 0) - normalized_current_weights.get(strategy, 0)
            for strategy in set(list(recommended_weights.keys()) + list(normalized_current_weights.keys()))
        }
        
        # Calculate expected improvements
        current_diversification = self._calculate_diversification_score(returns_df, normalized_current_weights)
        recommended_diversification = self._calculate_diversification_score(returns_df, recommended_weights)
        
        expected_diversification_improvement = (
            recommended_diversification.overall_score - current_diversification.overall_score
        )
        
        current_portfolio_vol = self._portfolio_volatility(returns_df, normalized_current_weights)
        recommended_portfolio_vol = self._portfolio_volatility(returns_df, recommended_weights)
        expected_risk_reduction = (current_portfolio_vol - recommended_portfolio_vol) / current_portfolio_vol if current_portfolio_vol > 0 else 0
        
        # Estimate rebalancing costs (simplified)
        rebalancing_cost_estimate = sum(abs(change) for change in weight_changes.values()) * 0.001  # 0.1% cost per weight change
        
        # Calculate confidence based on improvement and stability
        improvement_magnitude = abs(expected_diversification_improvement) + abs(expected_risk_reduction)
        confidence = min(1.0, improvement_magnitude * 2)  # Simple confidence metric
        
        # Generate rationale
        rationale = self._generate_allocation_rationale(
            weight_changes, expected_diversification_improvement, expected_risk_reduction, objective
        )
        
        return AllocationRecommendation(
            recommended_weights=recommended_weights,
            current_weights=normalized_current_weights,
            weight_changes=weight_changes,
            objective=objective,
            expected_diversification_improvement=expected_diversification_improvement,
            expected_risk_reduction=expected_risk_reduction,
            rebalancing_cost_estimate=rebalancing_cost_estimate,
            recommendation_confidence=confidence,
            rationale=rationale
        )
    
    def _minimize_correlation_optimization(
        self,
        correlation_matrix: pd.DataFrame,
        current_weights: Dict[str, float],
        constraints: Dict
    ) -> Dict[str, float]:
        """Optimize weights to minimize portfolio correlation"""
        
        strategies = list(current_weights.keys())
        n_strategies = len(strategies)
        
        # Objective function: minimize weighted average correlation
        def objective(weights):
            weight_dict = dict(zip(strategies, weights))
            return abs(self._weighted_average_correlation(correlation_matrix, weight_dict))
        
        # Constraints
        cons = [
            {'type': 'eq', 'fun': lambda w: np.sum(w) - 1.0}  # Weights sum to 1
        ]
        
        # Bounds
        bounds = [
            (constraints['min_weight'], constraints['max_weight'])
            for _ in range(n_strategies)
        ]
        
        # Initial guess (current weights)
        x0 = np.array([current_weights[strategy] for strategy in strategies])
        
        try:
            result = minimize(objective, x0, method='SLSQP', bounds=bounds, constraints=cons)
            
            if result.success:
                return dict(zip(strategies, result.x))
            else:
                logger.warning("Correlation minimization optimization failed, using equal weights")
                equal_weight = 1.0 / n_strategies
                return {strategy: equal_weight for strategy in strategies}
        
        except Exception as e:
            logger.error(f"Optimization failed: {e}")
            equal_weight = 1.0 / n_strategies
            return {strategy: equal_weight for strategy in strategies}
    
    def _maximize_diversification_optimization(
        self,
        returns_df: pd.DataFrame,
        correlation_matrix: pd.DataFrame,
        current_weights: Dict[str, float],
        constraints: Dict
    ) -> Dict[str, float]:
        """Optimize weights to maximize diversification ratio"""
        
        strategies = list(current_weights.keys())
        n_strategies = len(strategies)
        
        # Objective function: maximize diversification ratio
        def objective(weights):
            weight_dict = dict(zip(strategies, weights))
            div_ratio = self._diversification_ratio(returns_df, weight_dict)
            return -div_ratio  # Negative for minimization
        
        # Constraints
        cons = [
            {'type': 'eq', 'fun': lambda w: np.sum(w) - 1.0}  # Weights sum to 1
        ]
        
        # Bounds
        bounds = [
            (constraints['min_weight'], constraints['max_weight'])
            for _ in range(n_strategies)
        ]
        
        # Initial guess
        x0 = np.array([current_weights[strategy] for strategy in strategies])
        
        try:
            result = minimize(objective, x0, method='SLSQP', bounds=bounds, constraints=cons)
            
            if result.success:
                return dict(zip(strategies, result.x))
            else:
                return current_weights
        
        except Exception as e:
            logger.error(f"Diversification optimization failed: {e}")
            return current_weights
    
    def _equal_risk_contribution_optimization(
        self,
        returns_df: pd.DataFrame,
        correlation_matrix: pd.DataFrame,
        current_weights: Dict[str, float],
        constraints: Dict
    ) -> Dict[str, float]:
        """Optimize for equal risk contribution (risk parity)"""
        
        strategies = list(current_weights.keys())
        n_strategies = len(strategies)
        target_risk_contrib = 1.0 / n_strategies
        
        # Simplified risk parity: weight inversely proportional to volatility
        try:
            strategy_vols = {}
            for strategy in strategies:
                if strategy in returns_df.columns:
                    strategy_vols[strategy] = returns_df[strategy].std()
            
            # Inverse volatility weights
            inv_vol_weights = {}
            total_inv_vol = sum(1/vol for vol in strategy_vols.values() if vol > 0)
            
            for strategy, vol in strategy_vols.items():
                if vol > 0:
                    weight = (1/vol) / total_inv_vol
                    # Apply constraints
                    weight = max(constraints['min_weight'], min(constraints['max_weight'], weight))
                    inv_vol_weights[strategy] = weight
            
            # Normalize
            total_weight = sum(inv_vol_weights.values())
            if total_weight > 0:
                inv_vol_weights = {k: v/total_weight for k, v in inv_vol_weights.items()}
            
            return inv_vol_weights
        
        except Exception as e:
            logger.error(f"Risk parity optimization failed: {e}")
            equal_weight = 1.0 / n_strategies
            return {strategy: equal_weight for strategy in strategies}
    
    def _minimum_variance_optimization(
        self,
        returns_df: pd.DataFrame,
        correlation_matrix: pd.DataFrame,
        current_weights: Dict[str, float],
        constraints: Dict
    ) -> Dict[str, float]:
        """Optimize for minimum portfolio variance"""
        
        strategies = list(current_weights.keys())
        n_strategies = len(strategies)
        
        # Get volatilities and covariance matrix
        try:
            vols = np.array([returns_df[s].std() for s in strategies])
            corr_subset = correlation_matrix.loc[strategies, strategies]
            cov_matrix = np.outer(vols, vols) * corr_subset.values
            
            # Objective function: portfolio variance
            def objective(weights):
                return np.dot(weights, np.dot(cov_matrix, weights))
            
            # Constraints
            cons = [
                {'type': 'eq', 'fun': lambda w: np.sum(w) - 1.0}
            ]
            
            # Bounds
            bounds = [
                (constraints['min_weight'], constraints['max_weight'])
                for _ in range(n_strategies)
            ]
            
            # Initial guess
            x0 = np.array([current_weights[strategy] for strategy in strategies])
            
            result = minimize(objective, x0, method='SLSQP', bounds=bounds, constraints=cons)
            
            if result.success:
                return dict(zip(strategies, result.x))
            else:
                return current_weights
        
        except Exception as e:
            logger.error(f"Minimum variance optimization failed: {e}")
            return current_weights
    
    def _generate_allocation_rationale(
        self,
        weight_changes: Dict[str, float],
        diversification_improvement: float,
        risk_reduction: float,
        objective: AllocationObjective
    ) -> List[str]:
        """Generate rationale for allocation recommendations"""
        
        rationale = []
        
        # Objective-specific rationale
        if objective == AllocationObjective.MINIMIZE_CORRELATION:
            rationale.append("Allocation optimized to minimize portfolio correlation and improve diversification")
        elif objective == AllocationObjective.MAXIMIZE_DIVERSIFICATION:
            rationale.append("Allocation optimized to maximize diversification ratio")
        elif objective == AllocationObjective.EQUAL_RISK_CONTRIBUTION:
            rationale.append("Allocation optimized for equal risk contribution (risk parity)")
        elif objective == AllocationObjective.MINIMUM_VARIANCE:
            rationale.append("Allocation optimized to minimize portfolio variance")
        
        # Major weight changes
        significant_increases = [
            strategy for strategy, change in weight_changes.items() if change > 0.05
        ]
        significant_decreases = [
            strategy for strategy, change in weight_changes.items() if change < -0.05
        ]
        
        if significant_increases:
            rationale.append(f"Increase allocation to: {', '.join(significant_increases)}")
        
        if significant_decreases:
            rationale.append(f"Reduce allocation to: {', '.join(significant_decreases)}")
        
        # Expected improvements
        if diversification_improvement > 0.05:
            rationale.append(f"Expected diversification improvement: {diversification_improvement:.2%}")
        
        if risk_reduction > 0.02:
            rationale.append(f"Expected risk reduction: {risk_reduction:.2%}")
        
        if not rationale:
            rationale.append("Current allocation appears well-diversified")
        
        return rationale
    
    def generate_portfolio_correlation_report(
        self,
        strategy_returns: Dict[str, pd.Series],
        strategy_weights: Dict[str, float],
        include_recommendations: bool = True
    ) -> Dict[str, Union[str, Dict, List]]:
        """
        Generate comprehensive portfolio correlation report
        """
        
        # Perform portfolio analysis
        portfolio_analysis = self.analyze_portfolio_correlation(strategy_returns, strategy_weights)
        
        # Generate allocation recommendations if requested
        allocation_recommendations = {}
        if include_recommendations:
            for objective in AllocationObjective:
                try:
                    recommendation = self.generate_allocation_recommendations(
                        strategy_returns, strategy_weights, objective
                    )
                    allocation_recommendations[objective.value] = recommendation.to_dict()
                except Exception as e:
                    logger.warning(f"Failed to generate recommendation for {objective.value}: {e}")
        
        report = {
            'timestamp': datetime.utcnow().isoformat(),
            'portfolio_analysis': {
                'diversification_score': portfolio_analysis['diversification_score'].to_dict(),
                'concentration_risk': portfolio_analysis['concentration_risk'].to_dict(),
                'correlation_breakdown': portfolio_analysis['correlation_breakdown'].to_dict()
            },
            'allocation_recommendations': allocation_recommendations,
            'summary_insights': self._generate_summary_insights(portfolio_analysis),
            'action_items': self._generate_action_items(portfolio_analysis, allocation_recommendations)
        }
        
        return report
    
    def _generate_summary_insights(
        self,
        portfolio_analysis: Dict
    ) -> List[str]:
        """Generate summary insights from portfolio analysis"""
        
        insights = []
        
        diversification_score = portfolio_analysis['diversification_score']
        concentration_risk = portfolio_analysis['concentration_risk']
        correlation_breakdown = portfolio_analysis['correlation_breakdown']
        
        # Diversification insights
        if diversification_score.overall_score < 0.5:
            insights.append(f"Portfolio has poor diversification (score: {diversification_score.overall_score:.2f})")
        elif diversification_score.overall_score > 0.8:
            insights.append(f"Portfolio is well-diversified (score: {diversification_score.overall_score:.2f})")
        
        # Concentration insights
        if concentration_risk.herfindahl_index > 0.25:
            insights.append(f"High concentration risk detected (HHI: {concentration_risk.herfindahl_index:.3f})")
        
        # Correlation insights
        if correlation_breakdown.weighted_average_correlation > 0.5:
            insights.append("High average correlation between strategies may reduce diversification benefits")
        
        if len(correlation_breakdown.high_correlation_pairs) > 0:
            insights.append(f"{len(correlation_breakdown.high_correlation_pairs)} highly correlated strategy pairs identified")
        
        return insights
    
    def _generate_action_items(
        self,
        portfolio_analysis: Dict,
        allocation_recommendations: Dict
    ) -> List[str]:
        """Generate actionable recommendations"""
        
        action_items = []
        
        diversification_score = portfolio_analysis['diversification_score']
        concentration_risk = portfolio_analysis['concentration_risk']
        
        # Diversification actions
        if diversification_score.overall_score < 0.6:
            action_items.append("Consider rebalancing to improve portfolio diversification")
        
        # Concentration actions
        if concentration_risk.top_strategy_weight > 0.4:
            action_items.append(f"Consider reducing allocation to top strategy (currently {concentration_risk.top_strategy_weight:.1%})")
        
        # Correlation actions
        if len(portfolio_analysis['correlation_breakdown'].high_correlation_pairs) > 2:
            action_items.append("Review highly correlated strategies for potential consolidation")
        
        # Recommendation actions
        if allocation_recommendations:
            best_recommendation = None
            best_improvement = 0
            
            for obj, rec in allocation_recommendations.items():
                improvement = rec.get('expected_diversification_improvement', 0)
                if improvement > best_improvement:
                    best_improvement = improvement
                    best_recommendation = obj
            
            if best_recommendation and best_improvement > 0.05:
                action_items.append(f"Consider {best_recommendation} rebalancing for {best_improvement:.1%} diversification improvement")
        
        return action_items