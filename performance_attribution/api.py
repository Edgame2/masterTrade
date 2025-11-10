"""
Performance Attribution API

REST API endpoints for attribution analysis
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Dict, List, Optional
from datetime import datetime
import pandas as pd
import logging

from .attribution_engine import AttributionEngine, AttributionConfig, AttributionMethod
from .benchmark_manager import BenchmarkManager, BenchmarkType
from .factor_models import MultiFactorModel
from .trade_attribution import TradeAttributor, AttributionCategory

router = APIRouter(prefix="/api/attribution", tags=["attribution"])
logger = logging.getLogger(__name__)

# Global instances (would be dependency-injected in production)
attribution_engine: Optional[AttributionEngine] = None
benchmark_manager: Optional[BenchmarkManager] = None
trade_attributor: Optional[TradeAttributor] = None


# Request/Response Models

class AttributionRequest(BaseModel):
    """Request for attribution analysis"""
    strategy_name: str
    start_date: datetime
    end_date: datetime
    
    # Method
    method: str = "factor_regression"  # factor_regression, brinson, returns_based
    
    # Factors to use
    use_market_factor: bool = True
    use_momentum_factor: bool = True
    use_volatility_factor: bool = True
    use_carry_factor: bool = True
    
    # Benchmark
    benchmark_name: str = "BTC"
    
    # Options
    rolling_window_days: int = 90
    risk_free_rate: float = 0.04


class BenchmarkRequest(BaseModel):
    """Request to create a benchmark"""
    name: str
    benchmark_type: str  # single_asset, market_index, risk_free
    
    # For single asset
    symbol: Optional[str] = None
    
    # For market index
    components: Optional[Dict[str, float]] = None
    
    # For risk-free
    annual_rate: Optional[float] = None
    
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None


class TradeAttributionRequest(BaseModel):
    """Request for trade-level attribution"""
    strategy_name: str
    start_date: datetime
    end_date: datetime
    
    # Grouping
    group_by: str = "regime"  # regime, signal, timeframe, entry_quality, exit_quality


class AttributionResponse(BaseModel):
    """Response with attribution results"""
    strategy_name: str
    period_start: datetime
    period_end: datetime
    
    # Performance
    total_return_pct: float
    benchmark_return_pct: float
    excess_return_pct: float
    
    # Alpha-beta
    alpha_annual_pct: float
    alpha_daily_pct: float
    is_alpha_significant: bool
    market_beta: float
    information_ratio: float
    r_squared: float
    
    # Factor exposures
    factor_exposures: Dict[str, Dict]  # factor_name -> {beta, contribution, etc}
    
    # Risk
    tracking_error: float
    
    # Explained
    explained_return_pct: float
    unexplained_return_pct: float


class BenchmarkComparisonResponse(BaseModel):
    """Response with benchmark comparison"""
    strategy_name: str
    benchmark_name: str
    
    # Returns
    strategy_return_pct: float
    benchmark_return_pct: float
    excess_return_pct: float
    
    # Risk
    strategy_volatility: float
    benchmark_volatility: float
    tracking_error: float
    
    # Risk-adjusted
    strategy_sharpe: float
    benchmark_sharpe: float
    information_ratio: float
    
    # Correlation
    correlation: float
    beta: float


class TradeAttributionResponse(BaseModel):
    """Response with trade-level attribution"""
    strategy_name: str
    total_trades: int
    
    # Component contributions
    components: Dict[str, Dict]  # component_name -> {pnl, contribution_pct, etc}
    
    # Summary
    avg_entry_quality: float
    avg_exit_quality: float
    avg_holding_efficiency: float
    
    # Top contributors
    best_component: str
    worst_component: str


# API Endpoints

@router.post("/analyze", response_model=AttributionResponse)
async def analyze_performance(request: AttributionRequest):
    """
    Perform comprehensive attribution analysis
    
    Decomposes strategy returns into:
    - Alpha (skill)
    - Beta (market exposure)
    - Factor exposures
    - Explained vs unexplained returns
    """
    try:
        # Create config
        config = AttributionConfig(
            start_date=request.start_date,
            end_date=request.end_date,
            method=AttributionMethod(request.method),
            use_market_factor=request.use_market_factor,
            use_momentum_factor=request.use_momentum_factor,
            use_volatility_factor=request.use_volatility_factor,
            use_carry_factor=request.use_carry_factor,
            rolling_window_days=request.rolling_window_days,
            risk_free_rate=request.risk_free_rate
        )
        
        # Create engine
        engine = AttributionEngine(config)
        
        # TODO: Load actual data from database
        # For now, placeholder
        returns = pd.Series()  # Load strategy returns
        benchmark_returns = pd.Series()  # Load benchmark returns
        
        # Calculate factors
        factor_model = MultiFactorModel(
            use_market=request.use_market_factor,
            use_momentum=request.use_momentum_factor,
            use_volatility=request.use_volatility_factor,
            use_carry=request.use_carry_factor
        )
        
        # TODO: Load market data
        market_data = pd.DataFrame()
        factor_returns = await factor_model.calculate_all_factor_returns(
            market_data, request.start_date, request.end_date
        )
        
        # Run attribution
        result = await engine.analyze(
            returns, factor_returns, benchmark_returns,
            strategy_name=request.strategy_name
        )
        
        # Format response
        factor_exposures_dict = {}
        for name, exposure in result.factor_exposures.items():
            factor_exposures_dict[name] = {
                "beta": exposure.beta,
                "t_statistic": exposure.t_statistic,
                "p_value": exposure.p_value,
                "is_significant": exposure.is_significant,
                "contribution": exposure.contribution,
                "contribution_pct": exposure.contribution_pct
            }
        
        response = AttributionResponse(
            strategy_name=result.strategy_name,
            period_start=result.start_date,
            period_end=result.end_date,
            total_return_pct=result.total_return * 100,
            benchmark_return_pct=result.benchmark_return * 100,
            excess_return_pct=result.excess_return * 100,
            alpha_annual_pct=result.alpha_beta.alpha_annual * 100,
            alpha_daily_pct=result.alpha_beta.alpha_daily * 100,
            is_alpha_significant=result.alpha_beta.is_alpha_significant,
            market_beta=result.alpha_beta.market_beta,
            information_ratio=result.alpha_beta.information_ratio,
            r_squared=result.alpha_beta.r_squared,
            factor_exposures=factor_exposures_dict,
            tracking_error=result.tracking_error,
            explained_return_pct=result.explained_return * 100,
            unexplained_return_pct=result.unexplained_return * 100
        )
        
        return response
    
    except Exception as e:
        logger.error(f"Error in attribution analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/benchmark/create")
async def create_benchmark(request: BenchmarkRequest):
    """Create a new benchmark"""
    try:
        global benchmark_manager
        if benchmark_manager is None:
            benchmark_manager = BenchmarkManager()
        
        if request.benchmark_type == "single_asset":
            if not request.symbol:
                raise HTTPException(status_code=400, detail="Symbol required for single asset benchmark")
            
            # TODO: Load returns from database
            returns = pd.Series()
            
            benchmark = benchmark_manager.create_single_asset_benchmark(
                request.name, request.symbol, returns
            )
        
        elif request.benchmark_type == "risk_free":
            if request.annual_rate is None:
                raise HTTPException(status_code=400, detail="Annual rate required for risk-free benchmark")
            
            if not request.start_date or not request.end_date:
                raise HTTPException(status_code=400, detail="Dates required for risk-free benchmark")
            
            benchmark = benchmark_manager.create_risk_free_benchmark(
                request.name, request.annual_rate, request.start_date, request.end_date
            )
        
        else:
            raise HTTPException(status_code=400, detail=f"Unknown benchmark type: {request.benchmark_type}")
        
        return {
            "status": "success",
            "benchmark_name": benchmark.name,
            "benchmark_type": benchmark.benchmark_type.value
        }
    
    except Exception as e:
        logger.error(f"Error creating benchmark: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/benchmark/compare", response_model=BenchmarkComparisonResponse)
async def compare_to_benchmark(
    strategy_name: str = Query(...),
    benchmark_name: str = Query(...),
    start_date: datetime = Query(...),
    end_date: datetime = Query(...),
    risk_free_rate: float = Query(0.04)
):
    """Compare strategy performance to a benchmark"""
    try:
        global benchmark_manager
        if benchmark_manager is None:
            benchmark_manager = BenchmarkManager()
        
        # TODO: Load strategy returns
        strategy_returns = pd.Series()
        
        # Compare
        comparison = benchmark_manager.compare_to_benchmark(
            strategy_returns, benchmark_name, risk_free_rate
        )
        
        response = BenchmarkComparisonResponse(
            strategy_name=strategy_name,
            benchmark_name=comparison.benchmark_name,
            strategy_return_pct=comparison.strategy_return * 100,
            benchmark_return_pct=comparison.benchmark_return * 100,
            excess_return_pct=comparison.excess_return * 100,
            strategy_volatility=comparison.strategy_volatility,
            benchmark_volatility=comparison.benchmark_volatility,
            tracking_error=comparison.tracking_error,
            strategy_sharpe=comparison.strategy_sharpe,
            benchmark_sharpe=comparison.benchmark_sharpe,
            information_ratio=comparison.information_ratio,
            correlation=comparison.correlation,
            beta=comparison.beta
        )
        
        return response
    
    except Exception as e:
        logger.error(f"Error comparing to benchmark: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/trades/attribute", response_model=TradeAttributionResponse)
async def attribute_trades(request: TradeAttributionRequest):
    """Perform trade-level attribution analysis"""
    try:
        global trade_attributor
        if trade_attributor is None:
            trade_attributor = TradeAttributor()
        
        # TODO: Load trades from database
        trades = []  # Load trades for strategy in date range
        
        # TODO: Load market data
        market_data = pd.DataFrame()
        
        # Attribute trades
        attributions = trade_attributor.attribute_trades(trades, market_data)
        
        # Aggregate by requested grouping
        category_map = {
            "regime": AttributionCategory.MARKET_CONDITION,
            "signal": AttributionCategory.SIGNAL_TYPE,
            "timeframe": AttributionCategory.TIMEFRAME,
            "entry_quality": AttributionCategory.ENTRY_QUALITY,
            "exit_quality": AttributionCategory.EXIT_QUALITY,
            "holding": AttributionCategory.HOLDING_PERIOD
        }
        
        category = category_map.get(request.group_by, AttributionCategory.MARKET_CONDITION)
        components = trade_attributor.aggregate_by_component(attributions, category)
        
        # Format components
        components_dict = {}
        best_component = None
        worst_component = None
        best_pnl = float('-inf')
        worst_pnl = float('inf')
        
        for name, contrib in components.items():
            components_dict[name] = {
                "total_pnl": contrib.total_pnl,
                "contribution_pct": contrib.contribution_pct,
                "num_trades": contrib.num_trades,
                "avg_pnl_per_trade": contrib.avg_pnl_per_trade,
                "avg_score": contrib.avg_score,
                "consistency": contrib.consistency
            }
            
            if contrib.total_pnl > best_pnl:
                best_pnl = contrib.total_pnl
                best_component = name
            if contrib.total_pnl < worst_pnl:
                worst_pnl = contrib.total_pnl
                worst_component = name
        
        # Calculate averages
        if attributions:
            avg_entry_quality = sum(a.entry_quality_score for a in attributions) / len(attributions)
            avg_exit_quality = sum(a.exit_quality_score for a in attributions) / len(attributions)
            avg_holding_efficiency = sum(a.holding_efficiency for a in attributions) / len(attributions)
        else:
            avg_entry_quality = 0
            avg_exit_quality = 0
            avg_holding_efficiency = 0
        
        response = TradeAttributionResponse(
            strategy_name=request.strategy_name,
            total_trades=len(attributions),
            components=components_dict,
            avg_entry_quality=avg_entry_quality,
            avg_exit_quality=avg_exit_quality,
            avg_holding_efficiency=avg_holding_efficiency,
            best_component=best_component or "none",
            worst_component=worst_component or "none"
        )
        
        return response
    
    except Exception as e:
        logger.error(f"Error attributing trades: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "performance_attribution",
        "features": [
            "factor_attribution",
            "alpha_beta_decomposition",
            "benchmark_comparison",
            "trade_attribution"
        ]
    }
