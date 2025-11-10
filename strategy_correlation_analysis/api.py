"""
Strategy Correlation Analysis API

FastAPI endpoints for comprehensive strategy correlation analysis including:
- Cross-strategy correlation tracking and analysis
- Market regime detection and regime-based correlation analysis
- Portfolio-level correlation insights and diversification analysis
- Advanced correlation modeling and forecasting
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Union

import pandas as pd
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field

from .correlation_analyzer import (
    CorrelationAnalyzer, CorrelationType, TimeWindow, MarketCondition
)
from .regime_analyzer import (
    RegimeAnalyzer, MarketRegime, RegimeFeature, HMMRegimeDetector
)
from .portfolio_correlation import (
    PortfolioCorrelation, DiversificationMetric, AllocationObjective
)
from .correlation_models import (
    create_correlation_model, CorrelationModelType, ForecastHorizon,
    DynamicCorrelationModel, compare_correlation_models
)

logger = logging.getLogger(__name__)

# Create API router
router = APIRouter(prefix="/strategy-correlation", tags=["strategy_correlation_analysis"])

# Global analyzer instances
correlation_analyzer = CorrelationAnalyzer()
regime_analyzer = RegimeAnalyzer()
portfolio_analyzer = PortfolioCorrelation()


# Pydantic models for API requests/responses
class CorrelationAnalysisRequest(BaseModel):
    """Strategy correlation analysis request"""
    strategy_returns: Dict[str, List[float]] = Field(..., description="Strategy returns data")
    timestamps: List[str] = Field(..., description="Timestamps for returns data")
    correlation_type: str = Field("pearson", description="Correlation calculation method")
    time_window: str = Field("daily", description="Time window for analysis")
    market_condition: Optional[str] = Field(None, description="Market condition filter")
    include_rolling: bool = Field(True, description="Include rolling correlation analysis")
    rolling_window: int = Field(30, description="Rolling window size")


class RegimeAnalysisRequest(BaseModel):
    """Market regime analysis request"""
    market_data: Dict[str, List[float]] = Field(..., description="Market data (price, volume, etc.)")
    strategy_returns: Dict[str, List[float]] = Field(..., description="Strategy returns data")
    timestamps: List[str] = Field(..., description="Timestamps for data")
    features: List[str] = Field(["returns", "volatility", "momentum"], description="Features for regime detection")
    n_regimes: int = Field(4, description="Number of regimes to detect")


class PortfolioAnalysisRequest(BaseModel):
    """Portfolio correlation analysis request"""
    strategy_returns: Dict[str, List[float]] = Field(..., description="Strategy returns data")
    strategy_weights: Dict[str, float] = Field(..., description="Strategy allocation weights")
    timestamps: List[str] = Field(..., description="Timestamps for returns data")
    benchmark_returns: Optional[List[float]] = Field(None, description="Benchmark returns (optional)")


class AllocationOptimizationRequest(BaseModel):
    """Portfolio allocation optimization request"""
    strategy_returns: Dict[str, List[float]] = Field(..., description="Strategy returns data")
    current_weights: Dict[str, float] = Field(..., description="Current portfolio weights")
    timestamps: List[str] = Field(..., description="Timestamps for returns data")
    objective: str = Field("maximize_diversification", description="Optimization objective")
    constraints: Optional[Dict] = Field(None, description="Optimization constraints")


class CorrelationModelingRequest(BaseModel):
    """Correlation modeling and forecasting request"""
    strategy_returns: Dict[str, List[float]] = Field(..., description="Strategy returns data")
    timestamps: List[str] = Field(..., description="Timestamps for returns data")
    model_type: str = Field("dynamic_conditional", description="Correlation model type")
    forecast_horizons: List[int] = Field([1, 7, 30], description="Forecast horizons in days")
    strategy_pairs: Optional[List[List[str]]] = Field(None, description="Strategy pairs to forecast")


# Core Correlation Analysis Endpoints
@router.post("/analyze-correlations", response_model=Dict)
async def analyze_strategy_correlations(request: CorrelationAnalysisRequest):
    """
    Comprehensive strategy correlation analysis
    """
    try:
        # Convert request data to pandas format
        timestamps = pd.to_datetime(request.timestamps)
        strategy_returns = {}
        
        for strategy, returns in request.strategy_returns.items():
            if len(returns) != len(timestamps):
                raise ValueError(f"Returns length mismatch for strategy {strategy}")
            strategy_returns[strategy] = pd.Series(returns, index=timestamps)
        
        # Convert enums
        correlation_type = CorrelationType(request.correlation_type)
        time_window = TimeWindow(request.time_window)
        market_condition = MarketCondition(request.market_condition) if request.market_condition else None
        
        # Perform batch correlation analysis
        analysis_results = correlation_analyzer.batch_correlation_analysis(
            strategy_returns=strategy_returns,
            correlation_type=correlation_type,
            time_window=time_window,
            market_condition=market_condition,
            include_rolling=request.include_rolling,
            rolling_window=request.rolling_window
        )
        
        # Generate comprehensive report
        report = correlation_analyzer.generate_correlation_report(
            analysis_results, include_statistics=True
        )
        
        return {
            "analysis_results": {
                "pairwise_correlations": [corr.to_dict() for corr in analysis_results["pairwise_correlations"]],
                "rolling_correlations": [corr.to_dict() for corr in analysis_results["rolling_correlations"]],
                "correlation_matrix": analysis_results["correlation_matrix"].to_dict() if analysis_results["correlation_matrix"] else None
            },
            "report": report
        }
    
    except Exception as e:
        logger.error(f"Correlation analysis error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/correlation-decay-analysis", response_model=Dict)
async def analyze_correlation_decay(
    strategy1: str,
    strategy2: str,
    strategy_returns: Dict[str, List[float]],
    timestamps: List[str],
    max_lag_days: int = 60
):
    """
    Analyze correlation decay over time lags
    """
    try:
        # Convert to pandas format
        timestamps_idx = pd.to_datetime(timestamps)
        
        if strategy1 not in strategy_returns or strategy2 not in strategy_returns:
            raise ValueError(f"Strategies {strategy1} or {strategy2} not found in returns data")
        
        series1 = pd.Series(strategy_returns[strategy1], index=timestamps_idx)
        series2 = pd.Series(strategy_returns[strategy2], index=timestamps_idx)
        
        # Perform decay analysis
        decay_analysis = correlation_analyzer.analyze_correlation_decay(
            series1, series2, strategy1, strategy2, max_lag_days
        )
        
        return decay_analysis
    
    except Exception as e:
        logger.error(f"Correlation decay analysis error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


# Market Regime Analysis Endpoints
@router.post("/regime-analysis", response_model=Dict)
async def analyze_market_regimes(request: RegimeAnalysisRequest):
    """
    Comprehensive market regime analysis with correlation breakdown
    """
    try:
        # Convert data to pandas format
        timestamps = pd.to_datetime(request.timestamps)
        
        # Market data
        market_df = pd.DataFrame(request.market_data, index=timestamps)
        
        # Strategy returns
        strategy_returns = {}
        for strategy, returns in request.strategy_returns.items():
            if len(returns) != len(timestamps):
                raise ValueError(f"Returns length mismatch for strategy {strategy}")
            strategy_returns[strategy] = pd.Series(returns, index=timestamps)
        
        # Convert features
        features = [RegimeFeature(feature) for feature in request.features]
        
        # Set up regime analyzer
        regime_analyzer = RegimeAnalyzer(n_regimes=request.n_regimes)
        
        # Generate comprehensive regime report
        regime_report = regime_analyzer.generate_regime_report(
            market_data=market_df,
            strategy_returns=strategy_returns,
            features=features
        )
        
        return regime_report
    
    except Exception as e:
        logger.error(f"Regime analysis error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/regime-correlation-comparison", response_model=Dict)
async def compare_regime_correlations(request: RegimeAnalysisRequest):
    """
    Compare strategy correlations across different market regimes
    """
    try:
        # Convert data
        timestamps = pd.to_datetime(request.timestamps)
        market_df = pd.DataFrame(request.market_data, index=timestamps)
        
        strategy_returns = {}
        for strategy, returns in request.strategy_returns.items():
            strategy_returns[strategy] = pd.Series(returns, index=timestamps)
        
        features = [RegimeFeature(feature) for feature in request.features]
        
        # Analyze regime correlations
        regime_analyzer_instance = RegimeAnalyzer(n_regimes=request.n_regimes)
        regime_correlations = regime_analyzer_instance.analyze_regime_correlations(
            market_df, strategy_returns, features
        )
        
        # Compare correlations across regimes
        regime_comparison = regime_analyzer_instance.compare_regime_correlations(regime_correlations)
        
        return {
            "regime_correlations": {
                regime.value: correlation.to_dict() 
                for regime, correlation in regime_correlations.items()
            },
            "regime_comparison": regime_comparison
        }
    
    except Exception as e:
        logger.error(f"Regime correlation comparison error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/regime-transition-prediction", response_model=Dict)
async def predict_regime_transitions(
    market_data: Dict[str, List[float]],
    timestamps: List[str],
    features: List[str] = ["returns", "volatility", "momentum"],
    horizon_days: int = 30
):
    """
    Predict potential regime transitions
    """
    try:
        # Convert data
        timestamps_idx = pd.to_datetime(timestamps)
        market_df = pd.DataFrame(market_data, index=timestamps_idx)
        
        features_enum = [RegimeFeature(feature) for feature in features]
        
        # Fit regime detector
        detector = HMMRegimeDetector()
        detector.fit(market_df, features_enum)
        
        # Create regime analyzer
        analyzer = RegimeAnalyzer()
        analyzer.regime_detector = detector
        
        # Predict transitions
        predictions = analyzer.predict_regime_transitions(
            market_df, horizon_days, features_enum
        )
        
        return predictions
    
    except Exception as e:
        logger.error(f"Regime transition prediction error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


# Portfolio Correlation Analysis Endpoints
@router.post("/portfolio-analysis", response_model=Dict)
async def analyze_portfolio_correlation(request: PortfolioAnalysisRequest):
    """
    Comprehensive portfolio-level correlation analysis
    """
    try:
        # Convert data
        timestamps = pd.to_datetime(request.timestamps)
        
        strategy_returns = {}
        for strategy, returns in request.strategy_returns.items():
            if len(returns) != len(timestamps):
                raise ValueError(f"Returns length mismatch for strategy {strategy}")
            strategy_returns[strategy] = pd.Series(returns, index=timestamps)
        
        # Benchmark returns (optional)
        benchmark_returns = None
        if request.benchmark_returns:
            if len(request.benchmark_returns) != len(timestamps):
                raise ValueError("Benchmark returns length mismatch")
            benchmark_returns = pd.Series(request.benchmark_returns, index=timestamps)
        
        # Perform portfolio analysis
        portfolio_analysis = portfolio_analyzer.analyze_portfolio_correlation(
            strategy_returns=strategy_returns,
            strategy_weights=request.strategy_weights,
            benchmark_returns=benchmark_returns
        )
        
        return {
            "diversification_score": portfolio_analysis["diversification_score"].to_dict(),
            "concentration_risk": portfolio_analysis["concentration_risk"].to_dict(),
            "correlation_breakdown": portfolio_analysis["correlation_breakdown"].to_dict()
        }
    
    except Exception as e:
        logger.error(f"Portfolio analysis error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/portfolio-optimization", response_model=Dict)
async def optimize_portfolio_allocation(request: AllocationOptimizationRequest):
    """
    Generate portfolio allocation recommendations based on correlation analysis
    """
    try:
        # Convert data
        timestamps = pd.to_datetime(request.timestamps)
        
        strategy_returns = {}
        for strategy, returns in request.strategy_returns.items():
            strategy_returns[strategy] = pd.Series(returns, index=timestamps)
        
        # Convert objective
        objective = AllocationObjective(request.objective)
        
        # Generate allocation recommendations
        recommendation = portfolio_analyzer.generate_allocation_recommendations(
            strategy_returns=strategy_returns,
            current_weights=request.current_weights,
            objective=objective,
            constraints=request.constraints
        )
        
        return recommendation.to_dict()
    
    except Exception as e:
        logger.error(f"Portfolio optimization error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/portfolio-diversification-score", response_model=Dict)
async def calculate_diversification_score(
    strategy_returns: Dict[str, List[float]],
    strategy_weights: Dict[str, float],
    timestamps: List[str],
    metric: str = "correlation_based"
):
    """
    Calculate portfolio diversification score
    """
    try:
        # Convert data
        timestamps_idx = pd.to_datetime(timestamps)
        
        returns_dict = {}
        for strategy, returns in strategy_returns.items():
            returns_dict[strategy] = pd.Series(returns, index=timestamps_idx)
        
        # Calculate diversification score
        returns_df = pd.DataFrame(returns_dict).dropna()
        
        # Normalize weights
        total_weight = sum(strategy_weights.values())
        normalized_weights = {k: v/total_weight for k, v in strategy_weights.items()}
        
        diversification_score = portfolio_analyzer._calculate_diversification_score(
            returns_df, normalized_weights
        )
        
        return diversification_score.to_dict()
    
    except Exception as e:
        logger.error(f"Diversification score calculation error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


# Advanced Correlation Modeling Endpoints
@router.post("/correlation-modeling", response_model=Dict)
async def model_correlations(request: CorrelationModelingRequest):
    """
    Advanced correlation modeling and forecasting
    """
    try:
        # Convert data
        timestamps = pd.to_datetime(request.timestamps)
        
        strategy_returns = {}
        for strategy, returns in request.strategy_returns.items():
            strategy_returns[strategy] = pd.Series(returns, index=timestamps)
        
        returns_df = pd.DataFrame(strategy_returns).dropna()
        
        # Create correlation model
        model_type = CorrelationModelType(request.model_type)
        correlation_model = create_correlation_model(model_type)
        
        # Fit model
        correlation_model.fit(returns_df)
        
        # Generate forecasts
        forecasts = []
        strategies = list(returns_df.columns)
        
        # Determine strategy pairs to forecast
        if request.strategy_pairs:
            strategy_pairs = [(pair[0], pair[1]) for pair in request.strategy_pairs]
        else:
            # Use all pairs (up to 10 for performance)
            strategy_pairs = [(strategies[i], strategies[j]) 
                            for i in range(len(strategies)) 
                            for j in range(i+1, len(strategies))][:10]
        
        for strategy1, strategy2 in strategy_pairs:
            for horizon in request.forecast_horizons:
                try:
                    forecast = correlation_model.predict_correlation(
                        strategy1, strategy2, horizon
                    )
                    forecasts.append(forecast.to_dict())
                except Exception as e:
                    logger.warning(f"Forecast failed for {strategy1}-{strategy2} at horizon {horizon}: {e}")
        
        return {
            "model_info": correlation_model.get_model_info(),
            "current_correlation_matrix": correlation_model.get_correlation_matrix().to_dict(),
            "forecasts": forecasts
        }
    
    except Exception as e:
        logger.error(f"Correlation modeling error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/compare-correlation-models", response_model=Dict)
async def compare_models(
    strategy_returns: Dict[str, List[float]],
    timestamps: List[str],
    model_types: List[str] = ["ewma", "shrinkage", "garch_dcc"]
):
    """
    Compare multiple correlation models
    """
    try:
        # Convert data
        timestamps_idx = pd.to_datetime(timestamps)
        
        returns_dict = {}
        for strategy, returns in strategy_returns.items():
            returns_dict[strategy] = pd.Series(returns, index=timestamps_idx)
        
        returns_df = pd.DataFrame(returns_dict).dropna()
        
        # Create models
        models = []
        for model_type_str in model_types:
            try:
                model_type = CorrelationModelType(model_type_str)
                model = create_correlation_model(model_type)
                models.append(model)
            except Exception as e:
                logger.warning(f"Failed to create model {model_type_str}: {e}")
        
        # Compare models
        comparison_results = compare_correlation_models(
            returns_df, models
        )
        
        return comparison_results
    
    except Exception as e:
        logger.error(f"Model comparison error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/dynamic-correlation-ensemble", response_model=Dict)
async def create_dynamic_ensemble(
    strategy_returns: Dict[str, List[float]],
    timestamps: List[str]
):
    """
    Create dynamic correlation ensemble model
    """
    try:
        # Convert data
        timestamps_idx = pd.to_datetime(timestamps)
        
        returns_dict = {}
        for strategy, returns in strategy_returns.items():
            returns_dict[strategy] = pd.Series(returns, index=timestamps_idx)
        
        returns_df = pd.DataFrame(returns_dict).dropna()
        
        # Create ensemble model
        ensemble_model = DynamicCorrelationModel()
        ensemble_model.fit(returns_df)
        
        # Get model comparison
        model_comparison = ensemble_model.get_model_comparison()
        
        # Generate sample forecasts
        strategies = list(returns_df.columns)
        sample_forecasts = []
        
        if len(strategies) >= 2:
            for horizon in [1, 7, 30]:
                try:
                    forecast = ensemble_model.predict_correlation(
                        strategies[0], strategies[1], horizon
                    )
                    sample_forecasts.append(forecast.to_dict())
                except Exception as e:
                    logger.warning(f"Ensemble forecast failed: {e}")
        
        return {
            "ensemble_info": ensemble_model.get_model_info(),
            "model_comparison": model_comparison,
            "correlation_matrix": ensemble_model.get_correlation_matrix().to_dict(),
            "sample_forecasts": sample_forecasts
        }
    
    except Exception as e:
        logger.error(f"Dynamic ensemble error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


# Comprehensive Reporting Endpoints
@router.post("/comprehensive-report", response_model=Dict)
async def generate_comprehensive_report(
    strategy_returns: Dict[str, List[float]],
    strategy_weights: Dict[str, float],
    timestamps: List[str],
    market_data: Optional[Dict[str, List[float]]] = None,
    include_regime_analysis: bool = True,
    include_portfolio_optimization: bool = True,
    include_correlation_modeling: bool = True
):
    """
    Generate comprehensive strategy correlation analysis report
    """
    try:
        # Convert data
        timestamps_idx = pd.to_datetime(timestamps)
        
        returns_dict = {}
        for strategy, returns in strategy_returns.items():
            returns_dict[strategy] = pd.Series(returns, index=timestamps_idx)
        
        report = {
            "timestamp": datetime.utcnow().isoformat(),
            "analysis_summary": {
                "strategies_analyzed": list(returns_dict.keys()),
                "analysis_period": {
                    "start": timestamps[0],
                    "end": timestamps[-1],
                    "observations": len(timestamps)
                }
            }
        }
        
        # 1. Basic correlation analysis
        correlation_results = correlation_analyzer.batch_correlation_analysis(
            returns_dict, include_rolling=True
        )
        correlation_report = correlation_analyzer.generate_correlation_report(
            correlation_results, include_statistics=True
        )
        report["correlation_analysis"] = correlation_report
        
        # 2. Portfolio analysis
        portfolio_analysis = portfolio_analyzer.analyze_portfolio_correlation(
            returns_dict, strategy_weights
        )
        portfolio_report = portfolio_analyzer.generate_portfolio_correlation_report(
            returns_dict, strategy_weights, include_recommendations=include_portfolio_optimization
        )
        report["portfolio_analysis"] = portfolio_report
        
        # 3. Regime analysis (if market data provided)
        if include_regime_analysis and market_data:
            try:
                market_df = pd.DataFrame(market_data, index=timestamps_idx)
                regime_analyzer_instance = RegimeAnalyzer()
                regime_report = regime_analyzer_instance.generate_regime_report(
                    market_df, returns_dict
                )
                report["regime_analysis"] = regime_report
            except Exception as e:
                logger.warning(f"Regime analysis failed: {e}")
                report["regime_analysis"] = {"error": str(e)}
        
        # 4. Advanced correlation modeling
        if include_correlation_modeling:
            try:
                returns_df = pd.DataFrame(returns_dict).dropna()
                ensemble_model = DynamicCorrelationModel()
                ensemble_model.fit(returns_df)
                
                report["correlation_modeling"] = {
                    "model_info": ensemble_model.get_model_info(),
                    "model_comparison": ensemble_model.get_model_comparison(),
                    "current_correlations": ensemble_model.get_correlation_matrix().to_dict()
                }
            except Exception as e:
                logger.warning(f"Correlation modeling failed: {e}")
                report["correlation_modeling"] = {"error": str(e)}
        
        return report
    
    except Exception as e:
        logger.error(f"Comprehensive report generation error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


# Utility Endpoints
@router.get("/supported-features", response_model=Dict)
async def get_supported_features():
    """Get all supported analysis features and parameters"""
    return {
        "correlation_types": [ct.value for ct in CorrelationType],
        "time_windows": [tw.value for tw in TimeWindow],
        "market_conditions": [mc.value for mc in MarketCondition],
        "regime_features": [rf.value for rf in RegimeFeature],
        "market_regimes": [mr.value for mr in MarketRegime],
        "diversification_metrics": [dm.value for dm in DiversificationMetric],
        "allocation_objectives": [ao.value for ao in AllocationObjective],
        "correlation_model_types": [cmt.value for cmt in CorrelationModelType],
        "forecast_horizons": [fh.value for fh in ForecastHorizon]
    }


@router.get("/health", response_model=Dict)
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "strategy_correlation_analysis",
        "components": {
            "correlation_analyzer": "ready",
            "regime_analyzer": "ready", 
            "portfolio_analyzer": "ready"
        },
        "timestamp": datetime.utcnow().isoformat()
    }