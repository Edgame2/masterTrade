"""
Portfolio Performance Attribution

Analyzes and decomposes portfolio performance into various sources:
- Asset allocation effects
- Security selection effects  
- Interaction effects
- Factor-based attribution
- Sector-based attribution
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple
import logging
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class AttributionMethod(Enum):
    """Performance attribution methods"""
    BRINSON = "brinson"                    # Brinson-Fachler attribution
    BRINSON_HOOD_BEEBOWER = "bhb"         # Original Brinson-Hood-Beebower
    FACTOR_BASED = "factor_based"         # Factor-based attribution
    SECTOR_BASED = "sector_based"         # Sector-based attribution
    MULTI_PERIOD = "multi_period"         # Multi-period attribution


@dataclass
class AttributionComponent:
    """Individual attribution component"""
    name: str                    # Component name
    value: float                # Attribution value (in basis points or percentage)
    percentage: float           # As percentage of total return
    description: str            # Description of component


@dataclass 
class AttributionResult:
    """Complete performance attribution result"""
    # Time period
    start_date: str
    end_date: str
    
    # Returns
    portfolio_return: float      # Portfolio return
    benchmark_return: float      # Benchmark return
    active_return: float         # Portfolio - benchmark
    
    # Attribution components
    asset_allocation: float      # Asset allocation effect
    security_selection: float   # Security selection effect
    interaction: float          # Interaction effect
    
    # Detailed attribution by asset/sector
    asset_contributions: Dict[str, AttributionComponent]
    
    # Factor attributions (if applicable)
    factor_attributions: Optional[Dict[str, AttributionComponent]] = None
    
    # Sector attributions (if applicable)  
    sector_attributions: Optional[Dict[str, AttributionComponent]] = None
    
    # Statistical measures
    tracking_error: Optional[float] = None
    information_ratio: Optional[float] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary"""
        result = {
            "start_date": self.start_date,
            "end_date": self.end_date,
            "portfolio_return": self.portfolio_return,
            "benchmark_return": self.benchmark_return,
            "active_return": self.active_return,
            "asset_allocation": self.asset_allocation,
            "security_selection": self.security_selection,
            "interaction": self.interaction,
            "asset_contributions": {
                asset: component.__dict__ 
                for asset, component in self.asset_contributions.items()
            },
            "tracking_error": self.tracking_error,
            "information_ratio": self.information_ratio,
        }
        
        if self.factor_attributions:
            result["factor_attributions"] = {
                factor: component.__dict__
                for factor, component in self.factor_attributions.items()
            }
        
        if self.sector_attributions:
            result["sector_attributions"] = {
                sector: component.__dict__
                for sector, component in self.sector_attributions.items()
            }
        
        return result


class PerformanceAttribution:
    """
    Portfolio performance attribution engine.
    
    Decomposes portfolio performance into various sources to understand
    what drove returns relative to a benchmark.
    """
    
    def __init__(self, method: AttributionMethod = AttributionMethod.BRINSON):
        self.method = method
    
    def attribute_performance(
        self,
        portfolio_returns: pd.Series,
        portfolio_weights: pd.DataFrame,
        benchmark_returns: pd.Series,
        benchmark_weights: pd.DataFrame,
        asset_returns: pd.DataFrame,
        sector_mapping: Optional[Dict[str, str]] = None,
        factor_exposures: Optional[pd.DataFrame] = None,
        factor_returns: Optional[pd.DataFrame] = None
    ) -> AttributionResult:
        """
        Perform comprehensive performance attribution.
        
        Args:
            portfolio_returns: Portfolio returns over time
            portfolio_weights: Portfolio weights over time
            benchmark_returns: Benchmark returns over time  
            benchmark_weights: Benchmark weights over time
            asset_returns: Individual asset returns
            sector_mapping: Asset to sector mapping
            factor_exposures: Factor exposures for assets
            factor_returns: Factor returns over time
            
        Returns:
            Attribution result with decomposed performance
        """
        # Calculate period returns
        portfolio_return = (1 + portfolio_returns).prod() - 1
        benchmark_return = (1 + benchmark_returns).prod() - 1
        active_return = portfolio_return - benchmark_return
        
        # Get time period
        start_date = portfolio_returns.index[0].strftime("%Y-%m-%d")
        end_date = portfolio_returns.index[-1].strftime("%Y-%m-%d")
        
        # Perform attribution based on method
        if self.method == AttributionMethod.BRINSON:
            attribution_components = self._brinson_attribution(
                portfolio_weights, benchmark_weights, asset_returns
            )
        elif self.method == AttributionMethod.FACTOR_BASED:
            attribution_components = self._factor_based_attribution(
                portfolio_weights, benchmark_weights, factor_exposures, factor_returns
            )
        else:
            # Default to Brinson
            attribution_components = self._brinson_attribution(
                portfolio_weights, benchmark_weights, asset_returns
            )
        
        # Asset-level contributions
        asset_contributions = self._calculate_asset_contributions(
            portfolio_weights, benchmark_weights, asset_returns
        )
        
        # Sector attribution if mapping provided
        sector_attributions = None
        if sector_mapping:
            sector_attributions = self._calculate_sector_attribution(
                portfolio_weights, benchmark_weights, asset_returns, sector_mapping
            )
        
        # Factor attribution if factor data provided
        factor_attributions = None
        if factor_exposures is not None and factor_returns is not None:
            factor_attributions = self._calculate_factor_attribution(
                portfolio_weights, benchmark_weights, factor_exposures, factor_returns
            )
        
        # Calculate tracking statistics
        tracking_error = portfolio_returns.std() * np.sqrt(252) if len(portfolio_returns) > 1 else None
        information_ratio = (
            active_return / (tracking_error / np.sqrt(252)) if tracking_error and tracking_error > 0 else None
        )
        
        return AttributionResult(
            start_date=start_date,
            end_date=end_date,
            portfolio_return=portfolio_return,
            benchmark_return=benchmark_return,
            active_return=active_return,
            asset_allocation=attribution_components["asset_allocation"],
            security_selection=attribution_components["security_selection"],
            interaction=attribution_components["interaction"],
            asset_contributions=asset_contributions,
            factor_attributions=factor_attributions,
            sector_attributions=sector_attributions,
            tracking_error=tracking_error,
            information_ratio=information_ratio,
        )
    
    def _brinson_attribution(
        self,
        portfolio_weights: pd.DataFrame,
        benchmark_weights: pd.DataFrame,
        asset_returns: pd.DataFrame
    ) -> Dict[str, float]:
        """
        Perform Brinson-Fachler attribution.
        
        Decomposes active return into:
        1. Asset Allocation: (wp - wb) * rb
        2. Security Selection: wb * (rp - rb)  
        3. Interaction: (wp - wb) * (rp - rb)
        
        Where:
        wp, wb = portfolio and benchmark weights
        rp, rb = portfolio and benchmark returns
        """
        # Use average weights over the period
        avg_port_weights = portfolio_weights.mean()
        avg_bench_weights = benchmark_weights.mean()
        
        # Use period returns
        period_returns = (1 + asset_returns).prod() - 1
        
        # Align assets
        common_assets = list(set(avg_port_weights.index) & set(avg_bench_weights.index) & set(period_returns.index))
        
        asset_allocation = 0.0
        security_selection = 0.0
        interaction = 0.0
        
        for asset in common_assets:
            wp = avg_port_weights.get(asset, 0.0)
            wb = avg_bench_weights.get(asset, 0.0) 
            rp = period_returns.get(asset, 0.0)
            rb = period_returns.get(asset, 0.0)  # Assuming asset returns are the same
            
            # For proper Brinson attribution, we need sector/benchmark returns
            # This is a simplified version using asset returns
            weight_diff = wp - wb
            
            asset_allocation += weight_diff * rb
            security_selection += wb * (rp - rb)  # This will be 0 without proper benchmark
            interaction += weight_diff * (rp - rb)  # This will be 0 without proper benchmark
        
        return {
            "asset_allocation": asset_allocation,
            "security_selection": security_selection,
            "interaction": interaction,
        }
    
    def _factor_based_attribution(
        self,
        portfolio_weights: pd.DataFrame,
        benchmark_weights: pd.DataFrame,
        factor_exposures: pd.DataFrame,
        factor_returns: pd.DataFrame
    ) -> Dict[str, float]:
        """
        Perform factor-based attribution.
        
        Attributes performance to systematic factors:
        Active Return = Σ (Active Factor Exposure_i * Factor Return_i) + Selection
        """
        # Calculate active weights
        active_weights = portfolio_weights.mean() - benchmark_weights.mean()
        
        # Calculate active factor exposures
        active_factor_exposures = {}
        for factor in factor_exposures.columns:
            factor_exposure = 0.0
            for asset in active_weights.index:
                if asset in factor_exposures.index:
                    asset_exposure = factor_exposures.loc[asset, factor]
                    factor_exposure += active_weights[asset] * asset_exposure
            active_factor_exposures[factor] = factor_exposure
        
        # Calculate factor contributions
        factor_contributions = {}
        total_factor_return = 0.0
        
        period_factor_returns = (1 + factor_returns).prod() - 1
        
        for factor, exposure in active_factor_exposures.items():
            if factor in period_factor_returns.index:
                factor_return = period_factor_returns[factor]
                contribution = exposure * factor_return
                factor_contributions[factor] = contribution
                total_factor_return += contribution
        
        # Selection effect is residual (simplified)
        selection_effect = 0.0  # Would need residual returns from factor model
        
        return {
            "asset_allocation": total_factor_return,
            "security_selection": selection_effect,
            "interaction": 0.0,
            "factor_contributions": factor_contributions,
        }
    
    def _calculate_asset_contributions(
        self,
        portfolio_weights: pd.DataFrame,
        benchmark_weights: pd.DataFrame,
        asset_returns: pd.DataFrame
    ) -> Dict[str, AttributionComponent]:
        """Calculate individual asset contributions to performance"""
        contributions = {}
        
        # Use average weights
        avg_port_weights = portfolio_weights.mean()
        avg_bench_weights = benchmark_weights.mean()
        
        # Period returns
        period_returns = (1 + asset_returns).prod() - 1
        
        total_portfolio_return = sum(
            avg_port_weights.get(asset, 0.0) * period_returns.get(asset, 0.0)
            for asset in period_returns.index
        )
        
        for asset in period_returns.index:
            port_weight = avg_port_weights.get(asset, 0.0)
            bench_weight = avg_bench_weights.get(asset, 0.0)
            asset_return = period_returns[asset]
            
            # Asset contribution to portfolio return
            contribution_value = port_weight * asset_return
            
            # Active contribution (vs benchmark)
            active_contribution = (port_weight - bench_weight) * asset_return
            
            # Percentage of total return
            percentage = (contribution_value / total_portfolio_return * 100) if total_portfolio_return != 0 else 0.0
            
            contributions[asset] = AttributionComponent(
                name=asset,
                value=contribution_value,
                percentage=percentage,
                description=f"Asset {asset} contributed {contribution_value:.2%} to portfolio return"
            )
        
        return contributions
    
    def _calculate_sector_attribution(
        self,
        portfolio_weights: pd.DataFrame,
        benchmark_weights: pd.DataFrame,
        asset_returns: pd.DataFrame,
        sector_mapping: Dict[str, str]
    ) -> Dict[str, AttributionComponent]:
        """Calculate sector-level attribution"""
        # Aggregate weights and returns by sector
        sectors = set(sector_mapping.values())
        sector_attributions = {}
        
        for sector in sectors:
            sector_assets = [asset for asset, sec in sector_mapping.items() if sec == sector]
            
            # Sector weights (sum of constituent assets)
            port_sector_weight = sum(
                portfolio_weights.mean().get(asset, 0.0) 
                for asset in sector_assets
            )
            bench_sector_weight = sum(
                benchmark_weights.mean().get(asset, 0.0)
                for asset in sector_assets
            )
            
            # Sector return (weighted average of constituent returns)
            period_returns = (1 + asset_returns).prod() - 1
            
            sector_return = 0.0
            total_weight = 0.0
            
            for asset in sector_assets:
                if asset in period_returns.index:
                    weight = portfolio_weights.mean().get(asset, 0.0)
                    if weight > 0:
                        sector_return += weight * period_returns[asset]
                        total_weight += weight
            
            if total_weight > 0:
                sector_return /= total_weight
            
            # Sector attribution (simplified allocation effect)
            allocation_effect = (port_sector_weight - bench_sector_weight) * sector_return
            
            sector_attributions[sector] = AttributionComponent(
                name=sector,
                value=allocation_effect,
                percentage=(allocation_effect * 100) if allocation_effect else 0.0,
                description=f"Sector {sector} allocation effect: {allocation_effect:.2%}"
            )
        
        return sector_attributions
    
    def _calculate_factor_attribution(
        self,
        portfolio_weights: pd.DataFrame,
        benchmark_weights: pd.DataFrame,
        factor_exposures: pd.DataFrame,
        factor_returns: pd.DataFrame
    ) -> Dict[str, AttributionComponent]:
        """Calculate factor-based attribution"""
        factor_attributions = {}
        
        # Calculate active factor exposures
        active_weights = portfolio_weights.mean() - benchmark_weights.mean()
        
        period_factor_returns = (1 + factor_returns).prod() - 1
        
        for factor in factor_exposures.columns:
            # Calculate portfolio factor exposure
            port_factor_exposure = 0.0
            bench_factor_exposure = 0.0
            
            for asset in factor_exposures.index:
                port_weight = portfolio_weights.mean().get(asset, 0.0)
                bench_weight = benchmark_weights.mean().get(asset, 0.0)
                asset_factor_exposure = factor_exposures.loc[asset, factor]
                
                port_factor_exposure += port_weight * asset_factor_exposure
                bench_factor_exposure += bench_weight * asset_factor_exposure
            
            # Active factor exposure
            active_factor_exposure = port_factor_exposure - bench_factor_exposure
            
            # Factor contribution
            factor_return = period_factor_returns.get(factor, 0.0)
            factor_contribution = active_factor_exposure * factor_return
            
            factor_attributions[factor] = AttributionComponent(
                name=factor,
                value=factor_contribution,
                percentage=(factor_contribution * 100) if factor_contribution else 0.0,
                description=f"Factor {factor} contributed {factor_contribution:.2%} from {active_factor_exposure:.2f} active exposure"
            )
        
        return factor_attributions
    
    def multi_period_attribution(
        self,
        portfolio_returns: pd.DataFrame,
        portfolio_weights: pd.DataFrame,
        benchmark_returns: pd.DataFrame,
        benchmark_weights: pd.DataFrame,
        asset_returns: pd.DataFrame,
        period_frequency: str = "M"  # Monthly periods
    ) -> List[AttributionResult]:
        """
        Perform multi-period attribution analysis.
        
        Args:
            period_frequency: 'M' for monthly, 'Q' for quarterly, etc.
            
        Returns:
            List of attribution results for each period
        """
        # Resample data by periods
        period_groups = portfolio_returns.resample(period_frequency)
        
        attribution_results = []
        
        for period_name, period_data in period_groups:
            if len(period_data) == 0:
                continue
            
            # Get period start and end dates
            period_start = period_data.index[0]
            period_end = period_data.index[-1]
            
            # Extract data for this period
            period_port_weights = portfolio_weights.loc[period_start:period_end]
            period_bench_weights = benchmark_weights.loc[period_start:period_end]
            period_asset_returns = asset_returns.loc[period_start:period_end]
            period_bench_returns = benchmark_returns.loc[period_start:period_end]
            
            # Perform attribution for this period
            period_attribution = self.attribute_performance(
                period_data,
                period_port_weights,
                period_bench_returns,
                period_bench_weights,
                period_asset_returns
            )
            
            attribution_results.append(period_attribution)
        
        return attribution_results
    
    def attribution_summary(
        self,
        attribution_results: List[AttributionResult]
    ) -> Dict[str, float]:
        """
        Summarize attribution results across multiple periods.
        
        Returns:
            Summary statistics of attribution components
        """
        if not attribution_results:
            return {}
        
        # Collect attribution components
        asset_allocations = [result.asset_allocation for result in attribution_results]
        security_selections = [result.security_selection for result in attribution_results]
        interactions = [result.interaction for result in attribution_results]
        active_returns = [result.active_return for result in attribution_results]
        
        return {
            "avg_asset_allocation": np.mean(asset_allocations),
            "avg_security_selection": np.mean(security_selections),
            "avg_interaction": np.mean(interactions),
            "avg_active_return": np.mean(active_returns),
            "total_asset_allocation": np.sum(asset_allocations),
            "total_security_selection": np.sum(security_selections),
            "total_interaction": np.sum(interactions),
            "total_active_return": np.sum(active_returns),
            "asset_allocation_volatility": np.std(asset_allocations) * np.sqrt(252),
            "security_selection_volatility": np.std(security_selections) * np.sqrt(252),
            "active_return_volatility": np.std(active_returns) * np.sqrt(252),
        }