"""
Portfolio Optimization API

FastAPI endpoints for all portfolio optimization functionality including:
- Portfolio optimization with multiple methods
- Efficient frontier generation
- Risk model estimation  
- Black-Litterman optimization
- Portfolio rebalancing
- Performance attribution
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from .portfolio_optimizer import (
    PortfolioOptimizer, OptimizationMethod, OptimizationObjective,
    PortfolioConstraints, OptimizationResult
)
from .efficient_frontier import EfficientFrontier, FrontierPoint, OptimalPortfolios
from .risk_models import RiskModel, RiskModelType, CovarianceEstimator
from .black_litterman import (
    BlackLittermanModel, ViewSpecification, MarketCapWeights,
    create_absolute_view, create_relative_view
)
from .rebalancer import (
    PortfolioRebalancer, RebalancingFrequency, RebalancingTrigger,
    RebalancingConstraints, RebalancingDecision
)
from .performance_attribution import (
    PerformanceAttribution, AttributionMethod, AttributionResult
)

logger = logging.getLogger(__name__)

# Create API router
router = APIRouter(prefix="/portfolio", tags=["portfolio_optimization"])


# Pydantic models for API requests/responses
class OptimizationRequest(BaseModel):
    """Portfolio optimization request"""
    expected_returns: Dict[str, float] = Field(..., description="Expected returns by asset")
    covariance_data: Optional[Dict[str, Dict[str, float]]] = Field(None, description="Covariance matrix data")
    method: OptimizationMethod = Field(OptimizationMethod.MEAN_VARIANCE, description="Optimization method")
    objective: OptimizationObjective = Field(OptimizationObjective.MAXIMIZE_SHARPE, description="Optimization objective")
    constraints: Optional[Dict] = Field(None, description="Portfolio constraints")
    risk_free_rate: float = Field(0.02, description="Risk-free rate")


class EfficientFrontierRequest(BaseModel):
    """Efficient frontier generation request"""
    expected_returns: Dict[str, float]
    covariance_data: Dict[str, Dict[str, float]]
    num_points: int = Field(50, ge=10, le=200, description="Number of frontier points")
    constraints: Optional[Dict] = None
    risk_free_rate: float = Field(0.02)


class RiskModelRequest(BaseModel):
    """Risk model estimation request"""
    returns_data: Dict[str, List[float]] = Field(..., description="Historical returns by asset")
    estimator: CovarianceEstimator = Field(CovarianceEstimator.LEDOIT_WOLF, description="Covariance estimator")
    shrinkage_target: Optional[str] = Field("constant_correlation", description="Shrinkage target")
    factor_data: Optional[Dict[str, List[float]]] = Field(None, description="Factor returns data")


class BlackLittermanRequest(BaseModel):
    """Black-Litterman optimization request"""
    expected_returns: Dict[str, float]
    covariance_data: Dict[str, Dict[str, float]]
    market_cap_weights: Dict[str, float]
    views: List[Dict] = Field(..., description="Investor views")
    risk_aversion: float = Field(3.0, description="Risk aversion parameter")
    tau: float = Field(0.025, description="Uncertainty parameter")
    risk_free_rate: float = Field(0.02)


class RebalancingRequest(BaseModel):
    """Portfolio rebalancing request"""
    current_weights: Dict[str, float]
    target_weights: Dict[str, float]
    current_date: datetime
    last_rebalance_date: Optional[datetime] = None
    portfolio_value: float = Field(100000.0, description="Total portfolio value")
    frequency: RebalancingFrequency = Field(RebalancingFrequency.MONTHLY)
    trigger: RebalancingTrigger = Field(RebalancingTrigger.COMBINED)
    constraints: Optional[Dict] = None


class AttributionRequest(BaseModel):
    """Performance attribution request"""
    portfolio_returns: List[float]
    portfolio_weights: Dict[str, List[float]]  # Time series of weights
    benchmark_returns: List[float]
    benchmark_weights: Dict[str, List[float]]
    asset_returns: Dict[str, List[float]]
    dates: List[str]  # ISO format dates
    method: AttributionMethod = Field(AttributionMethod.BRINSON)
    sector_mapping: Optional[Dict[str, str]] = None


# Portfolio Optimization Endpoints
@router.post("/optimize", response_model=Dict)
async def optimize_portfolio(request: OptimizationRequest):
    """
    Optimize portfolio using specified method and constraints.
    """
    try:
        # Convert covariance data to DataFrame if provided
        covariance_matrix = None
        if request.covariance_data:
            covariance_matrix = pd.DataFrame(request.covariance_data)
        
        # Convert constraints
        constraints = None
        if request.constraints:
            constraints = PortfolioConstraints(**request.constraints)
        
        # Create optimizer
        optimizer = PortfolioOptimizer(risk_free_rate=request.risk_free_rate)
        
        # Optimize
        result = optimizer.optimize(
            expected_returns=request.expected_returns,
            covariance_matrix=covariance_matrix,
            method=request.method,
            objective=request.objective,
            constraints=constraints
        )
        
        return result.to_dict()
    
    except Exception as e:
        logger.error(f"Portfolio optimization error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/efficient-frontier", response_model=Dict)
async def generate_efficient_frontier(request: EfficientFrontierRequest):
    """
    Generate efficient frontier for given assets.
    """
    try:
        # Convert to DataFrames
        expected_returns = pd.Series(request.expected_returns)
        covariance_matrix = pd.DataFrame(request.covariance_data)
        
        # Convert constraints
        constraints = None
        if request.constraints:
            constraints = PortfolioConstraints(**request.constraints)
        
        # Generate frontier
        frontier = EfficientFrontier(
            expected_returns=expected_returns,
            covariance_matrix=covariance_matrix,
            risk_free_rate=request.risk_free_rate
        )
        
        # Generate points
        frontier_points = frontier.generate_frontier(
            num_points=request.num_points,
            constraints=constraints
        )
        
        # Find optimal portfolios
        optimal_portfolios = frontier.find_optimal_portfolios(constraints=constraints)
        
        return {
            "frontier_points": [point.to_dict() for point in frontier_points],
            "optimal_portfolios": optimal_portfolios.to_dict(),
            "statistics": frontier.get_risk_return_statistics().to_dict()
        }
    
    except Exception as e:
        logger.error(f"Efficient frontier error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


# Risk Model Endpoints
@router.post("/risk-model", response_model=Dict)
async def estimate_risk_model(request: RiskModelRequest):
    """
    Estimate covariance matrix using specified method.
    """
    try:
        # Convert returns data to DataFrame
        returns_df = pd.DataFrame(request.returns_data)
        
        # Convert factor data if provided
        factor_df = None
        if request.factor_data:
            factor_df = pd.DataFrame(request.factor_data)
        
        # Create risk model
        risk_model = RiskModel()
        
        # Estimate covariance
        result = risk_model.estimate_covariance(
            returns=returns_df,
            estimator=request.estimator,
            shrinkage_target=request.shrinkage_target,
            factor_returns=factor_df
        )
        
        return result.to_dict()
    
    except Exception as e:
        logger.error(f"Risk model estimation error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


# Black-Litterman Endpoints
@router.post("/black-litterman", response_model=Dict)
async def black_litterman_optimization(request: BlackLittermanRequest):
    """
    Perform Black-Litterman portfolio optimization with investor views.
    """
    try:
        # Convert data to required formats
        covariance_matrix = pd.DataFrame(request.covariance_data)
        market_weights = MarketCapWeights(weights=request.market_cap_weights)
        
        # Convert views
        views = []
        for view_data in request.views:
            view = ViewSpecification(**view_data)
            views.append(view)
        
        # Create Black-Litterman model
        bl_model = BlackLittermanModel(
            risk_aversion=request.risk_aversion,
            tau=request.tau,
            risk_free_rate=request.risk_free_rate
        )
        
        # Optimize
        new_returns, new_covariance = bl_model.optimize(
            covariance_matrix=covariance_matrix,
            market_cap_weights=market_weights,
            views=views
        )
        
        # Analyze view impact
        impact_analysis = bl_model.analyze_view_impact(
            covariance_matrix=covariance_matrix,
            market_cap_weights=market_weights,
            views=views
        )
        
        return {
            "new_expected_returns": new_returns.to_dict(),
            "new_covariance_matrix": new_covariance.to_dict(),
            "view_impact_analysis": impact_analysis
        }
    
    except Exception as e:
        logger.error(f"Black-Litterman optimization error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/create-view", response_model=Dict)
async def create_investment_view(
    view_type: str = Query(..., description="View type: absolute, relative, or sector"),
    asset1: str = Query(..., description="Primary asset"),
    expected_return: float = Query(..., description="Expected return"),
    confidence: float = Query(..., ge=0.0, le=1.0, description="Confidence level"),
    asset2: Optional[str] = Query(None, description="Second asset for relative views"),
    sector_assets: Optional[List[str]] = Query(None, description="Assets for sector view"),
    sector_weights: Optional[List[float]] = Query(None, description="Weights for sector view"),
    sector_name: Optional[str] = Query(None, description="Sector name")
):
    """
    Create investment view for Black-Litterman optimization.
    """
    try:
        if view_type == "absolute":
            view = create_absolute_view(asset1, expected_return, confidence)
        elif view_type == "relative":
            if not asset2:
                raise ValueError("asset2 required for relative views")
            view = create_relative_view(asset1, asset2, expected_return, confidence)
        elif view_type == "sector":
            if not sector_assets or not sector_weights or not sector_name:
                raise ValueError("sector_assets, sector_weights, and sector_name required for sector views")
            from .black_litterman import create_sector_view
            view = create_sector_view(sector_assets, sector_weights, expected_return, confidence, sector_name)
        else:
            raise ValueError("Invalid view_type. Must be 'absolute', 'relative', or 'sector'")
        
        return view.to_dict()
    
    except Exception as e:
        logger.error(f"View creation error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


# Rebalancing Endpoints
@router.post("/rebalancing-check", response_model=Dict)
async def check_rebalancing_needed(request: RebalancingRequest):
    """
    Check if portfolio rebalancing is needed and get trade recommendations.
    """
    try:
        # Convert constraints
        constraints = None
        if request.constraints:
            constraints = RebalancingConstraints(**request.constraints)
        
        # Create rebalancer
        rebalancer = PortfolioRebalancer(
            frequency=request.frequency,
            trigger=request.trigger,
            constraints=constraints
        )
        
        # Check rebalancing
        decision = rebalancer.check_rebalancing_needed(
            current_weights=request.current_weights,
            target_weights=request.target_weights,
            current_date=request.current_date,
            last_rebalance_date=request.last_rebalance_date,
            portfolio_value=request.portfolio_value
        )
        
        return decision.to_dict()
    
    except Exception as e:
        logger.error(f"Rebalancing check error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/optimize-rebalancing-frequency", response_model=Dict)
async def optimize_rebalancing_frequency(
    returns_data: Dict[str, List[float]],
    target_weights: Dict[str, float],
    frequencies: Optional[List[RebalancingFrequency]] = Query(None)
):
    """
    Optimize rebalancing frequency based on historical performance.
    """
    try:
        # Convert data
        returns_df = pd.DataFrame(returns_data)
        
        # Default frequencies to test
        if frequencies is None:
            frequencies = [
                RebalancingFrequency.WEEKLY,
                RebalancingFrequency.MONTHLY,
                RebalancingFrequency.QUARTERLY
            ]
        
        # Create rebalancer
        rebalancer = PortfolioRebalancer()
        
        # Optimize frequency
        results = rebalancer.optimize_rebalancing_frequency(
            returns_data=returns_df,
            target_weights=target_weights,
            frequencies_to_test=frequencies
        )
        
        # Convert enum keys to strings for JSON serialization
        return {freq.value: metrics for freq, metrics in results.items()}
    
    except Exception as e:
        logger.error(f"Rebalancing frequency optimization error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


# Performance Attribution Endpoints
@router.post("/performance-attribution", response_model=Dict)
async def attribute_performance(request: AttributionRequest):
    """
    Perform performance attribution analysis.
    """
    try:
        # Convert data to pandas
        dates = pd.to_datetime(request.dates)
        
        portfolio_returns = pd.Series(request.portfolio_returns, index=dates)
        benchmark_returns = pd.Series(request.benchmark_returns, index=dates)
        
        # Convert weights (assuming they're time series)
        portfolio_weights = pd.DataFrame(request.portfolio_weights, index=dates)
        benchmark_weights = pd.DataFrame(request.benchmark_weights, index=dates)
        asset_returns = pd.DataFrame(request.asset_returns, index=dates)
        
        # Create attribution analyzer
        attribution = PerformanceAttribution(method=request.method)
        
        # Perform attribution
        result = attribution.attribute_performance(
            portfolio_returns=portfolio_returns,
            portfolio_weights=portfolio_weights,
            benchmark_returns=benchmark_returns,
            benchmark_weights=benchmark_weights,
            asset_returns=asset_returns,
            sector_mapping=request.sector_mapping
        )
        
        return result.to_dict()
    
    except Exception as e:
        logger.error(f"Performance attribution error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/multi-period-attribution", response_model=Dict)
async def multi_period_attribution(
    request: AttributionRequest,
    period_frequency: str = Query("M", description="Period frequency: M (monthly), Q (quarterly)")
):
    """
    Perform multi-period performance attribution analysis.
    """
    try:
        # Convert data to pandas (same as above)
        dates = pd.to_datetime(request.dates)
        portfolio_returns = pd.Series(request.portfolio_returns, index=dates)
        benchmark_returns = pd.Series(request.benchmark_returns, index=dates)
        portfolio_weights = pd.DataFrame(request.portfolio_weights, index=dates)
        benchmark_weights = pd.DataFrame(request.benchmark_weights, index=dates)
        asset_returns = pd.DataFrame(request.asset_returns, index=dates)
        
        # Create attribution analyzer
        attribution = PerformanceAttribution(method=request.method)
        
        # Perform multi-period attribution
        results = attribution.multi_period_attribution(
            portfolio_returns=portfolio_returns,
            portfolio_weights=portfolio_weights,
            benchmark_returns=benchmark_returns,
            benchmark_weights=benchmark_weights,
            asset_returns=asset_returns,
            period_frequency=period_frequency
        )
        
        # Get summary statistics
        summary = attribution.attribution_summary(results)
        
        return {
            "period_results": [result.to_dict() for result in results],
            "summary_statistics": summary
        }
    
    except Exception as e:
        logger.error(f"Multi-period attribution error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


# Utility Endpoints
@router.get("/methods", response_model=Dict)
async def get_available_methods():
    """
    Get all available optimization methods and configuration options.
    """
    return {
        "optimization_methods": [method.value for method in OptimizationMethod],
        "optimization_objectives": [objective.value for objective in OptimizationObjective],
        "covariance_estimators": [estimator.value for estimator in CovarianceEstimator],
        "risk_model_types": [model_type.value for model_type in RiskModelType],
        "rebalancing_frequencies": [freq.value for freq in RebalancingFrequency],
        "rebalancing_triggers": [trigger.value for trigger in RebalancingTrigger],
        "attribution_methods": [method.value for method in AttributionMethod],
    }


@router.get("/health", response_model=Dict)
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "portfolio_optimization",
        "timestamp": datetime.utcnow().isoformat()
    }