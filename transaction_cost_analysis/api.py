"""
Transaction Cost Analysis API

FastAPI endpoints for comprehensive transaction cost analysis including:
- Market impact modeling and calibration
- Implementation shortfall analysis
- TWAP/VWAP benchmark analysis
- Execution optimization and scheduling
- Real-time TCA monitoring
- Cost attribution analysis
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field

from .cost_models import (
    create_impact_model, MarketImpactModel, TransactionCost
)
from .implementation_shortfall import (
    ImplementationShortfall, ExecutionBenchmark, ShortfallAnalysis
)
from .benchmark_analysis import (
    TWAPAnalyzer, VWAPAnalyzer, BenchmarkType, analyze_multiple_benchmarks
)
from .execution_optimizer import (
    ExecutionOptimizer, ExecutionStrategy, TradingConstraints, OptimalSchedule
)
from .real_time_monitor import (
    RealTimeTCAMonitor, AlertType, TCAAlert, MonitoringMetrics
)
from .cost_attribution import (
    CostAttribution, AttributionResult
)

logger = logging.getLogger(__name__)

# Create API router
router = APIRouter(prefix="/tca", tags=["transaction_cost_analysis"])

# Global TCA monitor instance
tca_monitor = RealTimeTCAMonitor()


# Pydantic models for API requests/responses
class MarketImpactRequest(BaseModel):
    """Market impact estimation request"""
    model_type: str = Field("square_root", description="Impact model type")
    trade_size: float = Field(..., description="Trade size (shares)")
    average_daily_volume: float = Field(..., description="Average daily volume")
    volatility: float = Field(..., description="Asset volatility")
    spread: float = Field(..., description="Bid-ask spread")
    market_data: Optional[Dict] = Field(None, description="Additional market data")


class ImplementationShortfallRequest(BaseModel):
    """Implementation shortfall analysis request"""
    order_id: str = Field(..., description="Order identifier")
    symbol: str = Field(..., description="Asset symbol")
    side: str = Field(..., description="Buy or sell")
    target_quantity: float = Field(..., description="Target quantity")
    benchmark_price: float = Field(..., description="Benchmark price")
    executions: List[Dict] = Field(..., description="List of execution fills")
    market_data: List[Dict] = Field(..., description="Market data during execution")
    benchmark_type: str = Field("arrival_price", description="Benchmark type")


class BenchmarkAnalysisRequest(BaseModel):
    """Benchmark analysis request"""
    executions: List[Dict] = Field(..., description="Execution fills")
    market_data: List[Dict] = Field(..., description="Market data")
    benchmark_types: List[str] = Field(["twap", "vwap"], description="Benchmark types to analyze")


class ExecutionOptimizationRequest(BaseModel):
    """Execution optimization request"""
    symbol: str = Field(..., description="Asset symbol")
    total_quantity: float = Field(..., description="Total quantity to execute")
    side: str = Field(..., description="Buy or sell")
    strategy: str = Field("implementation_shortfall", description="Execution strategy")
    market_data: Dict = Field(..., description="Market data")
    constraints: Dict = Field(..., description="Trading constraints")
    objective: str = Field("minimize_cost", description="Optimization objective")


class RealTimeMonitorRequest(BaseModel):
    """Real-time monitoring setup request"""
    order_id: str = Field(..., description="Order ID to monitor")
    symbol: str = Field(..., description="Asset symbol")
    side: str = Field(..., description="Buy or sell")
    target_quantity: float = Field(..., description="Target quantity")
    arrival_price: float = Field(..., description="Arrival price")
    start_time: datetime = Field(..., description="Execution start time")
    expected_end_time: datetime = Field(..., description="Expected end time")
    strategy: str = Field("unknown", description="Execution strategy")


class FillUpdateRequest(BaseModel):
    """Fill update for monitoring"""
    order_id: str = Field(..., description="Order ID")
    fill_price: float = Field(..., description="Fill price")
    fill_quantity: float = Field(..., description="Fill quantity")
    fill_time: datetime = Field(..., description="Fill timestamp")
    market_price: Optional[float] = Field(None, description="Market price at fill time")


class CostAttributionRequest(BaseModel):
    """Cost attribution analysis request"""
    order_data: Dict = Field(..., description="Order execution data")
    market_data: List[Dict] = Field(..., description="Market data during execution")
    venue_data: Optional[Dict] = Field(None, description="Venue-specific data")
    strategy_context: Optional[Dict] = Field(None, description="Strategy context")


# Market Impact Endpoints
@router.post("/market-impact/estimate", response_model=Dict)
async def estimate_market_impact(request: MarketImpactRequest):
    """
    Estimate market impact using specified model.
    """
    try:
        # Create impact model
        model = create_impact_model(
            model_type=request.model_type,
            **request.market_data or {}
        )
        
        # Estimate impact
        temp_impact, perm_impact = model.estimate_impact(
            trade_size=request.trade_size,
            average_daily_volume=request.average_daily_volume,
            volatility=request.volatility,
            spread=request.spread
        )
        
        total_impact = temp_impact + perm_impact
        
        return {
            "model_type": request.model_type,
            "temporary_impact_bps": temp_impact,
            "permanent_impact_bps": perm_impact,
            "total_impact_bps": total_impact,
            "impact_breakdown": {
                "temporary_percentage": (temp_impact / total_impact * 100) if total_impact > 0 else 0,
                "permanent_percentage": (perm_impact / total_impact * 100) if total_impact > 0 else 0
            }
        }
    
    except Exception as e:
        logger.error(f"Market impact estimation error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/market-impact/calculate-cost", response_model=Dict)
async def calculate_transaction_cost(
    symbol: str,
    trade_size: float,
    price: float,
    side: str,
    market_data: Dict,
    model_type: str = "square_root",
    commission_rate: float = 0.001
):
    """
    Calculate complete transaction cost breakdown.
    """
    try:
        # Create impact model
        model = create_impact_model(model_type)
        
        # Calculate total cost
        transaction_cost = model.calculate_total_cost(
            symbol=symbol,
            trade_size=trade_size,
            price=price,
            side=side,
            market_data=market_data,
            commission_rate=commission_rate
        )
        
        return transaction_cost.to_dict()
    
    except Exception as e:
        logger.error(f"Transaction cost calculation error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


# Implementation Shortfall Endpoints
@router.post("/implementation-shortfall/analyze", response_model=Dict)
async def analyze_implementation_shortfall(request: ImplementationShortfallRequest):
    """
    Perform implementation shortfall analysis.
    """
    try:
        # Convert market data to DataFrame
        market_df = pd.DataFrame(request.market_data)
        if not market_df.empty and "timestamp" in market_df.columns:
            market_df["timestamp"] = pd.to_datetime(market_df["timestamp"])
            market_df.set_index("timestamp", inplace=True)
        
        # Convert benchmark type
        benchmark_enum = ExecutionBenchmark(request.benchmark_type)
        
        # Create analyzer
        analyzer = ImplementationShortfall()
        
        # Perform analysis
        result = analyzer.analyze_execution(
            order_id=request.order_id,
            symbol=request.symbol,
            side=request.side,
            target_quantity=request.target_quantity,
            benchmark_price=request.benchmark_price,
            executions=request.executions,
            market_data=market_df,
            benchmark_type=benchmark_enum
        )
        
        return result.to_dict()
    
    except Exception as e:
        logger.error(f"Implementation shortfall analysis error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/implementation-shortfall/batch-analyze", response_model=Dict)
async def batch_analyze_implementation_shortfall(
    orders_data: List[Dict],
    market_data_dict: Dict[str, List[Dict]]
):
    """
    Perform batch implementation shortfall analysis.
    """
    try:
        # Convert market data
        market_data_frames = {}
        for symbol, data in market_data_dict.items():
            df = pd.DataFrame(data)
            if not df.empty and "timestamp" in df.columns:
                df["timestamp"] = pd.to_datetime(df["timestamp"])
                df.set_index("timestamp", inplace=True)
            market_data_frames[symbol] = df
        
        # Create analyzer
        analyzer = ImplementationShortfall()
        
        # Batch analysis
        results = analyzer.batch_analyze(orders_data, market_data_frames)
        
        # Generate summary
        summary = analyzer.generate_summary_report(results)
        
        return {
            "individual_analyses": [result.to_dict() for result in results],
            "summary_report": summary
        }
    
    except Exception as e:
        logger.error(f"Batch implementation shortfall analysis error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


# Benchmark Analysis Endpoints
@router.post("/benchmark-analysis/analyze", response_model=Dict)
async def analyze_execution_benchmarks(request: BenchmarkAnalysisRequest):
    """
    Analyze execution performance against multiple benchmarks.
    """
    try:
        # Convert market data to DataFrame
        market_df = pd.DataFrame(request.market_data)
        if not market_df.empty and "timestamp" in market_df.columns:
            market_df["timestamp"] = pd.to_datetime(market_df["timestamp"])
            market_df.set_index("timestamp", inplace=True)
        
        # Analyze against multiple benchmarks
        results = analyze_multiple_benchmarks(request.executions, market_df)
        
        return {
            "benchmark_results": results,
            "summary": {
                "best_benchmark": min(results.keys(), key=lambda k: abs(results[k].get("performance_bps", 0))) if results else None,
                "worst_benchmark": max(results.keys(), key=lambda k: abs(results[k].get("performance_bps", 0))) if results else None,
            }
        }
    
    except Exception as e:
        logger.error(f"Benchmark analysis error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/benchmark-analysis/twap", response_model=Dict)
async def analyze_twap_performance(
    executions: List[Dict],
    market_data: List[Dict],
    target_duration_minutes: int = 60
):
    """
    Analyze execution performance vs TWAP benchmark.
    """
    try:
        # Convert market data
        market_df = pd.DataFrame(market_data)
        if not market_df.empty and "timestamp" in market_df.columns:
            market_df["timestamp"] = pd.to_datetime(market_df["timestamp"])
            market_df.set_index("timestamp", inplace=True)
        
        # TWAP analysis
        twap_analyzer = TWAPAnalyzer()
        result = twap_analyzer.analyze_vs_twap(
            executions, market_df, target_duration_minutes
        )
        
        return result.to_dict()
    
    except Exception as e:
        logger.error(f"TWAP analysis error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/benchmark-analysis/vwap", response_model=Dict)
async def analyze_vwap_performance(
    executions: List[Dict],
    market_data: List[Dict]
):
    """
    Analyze execution performance vs VWAP benchmark.
    """
    try:
        # Convert market data
        market_df = pd.DataFrame(market_data)
        if not market_df.empty and "timestamp" in market_df.columns:
            market_df["timestamp"] = pd.to_datetime(market_df["timestamp"])
            market_df.set_index("timestamp", inplace=True)
        
        # VWAP analysis
        vwap_analyzer = VWAPAnalyzer()
        result = vwap_analyzer.analyze_vs_vwap(executions, market_df)
        
        return result.to_dict()
    
    except Exception as e:
        logger.error(f"VWAP analysis error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


# Execution Optimization Endpoints
@router.post("/execution-optimization/optimize", response_model=Dict)
async def optimize_execution(request: ExecutionOptimizationRequest):
    """
    Optimize execution strategy and schedule.
    """
    try:
        # Convert strategy and constraints
        strategy_enum = ExecutionStrategy(request.strategy)
        
        # Convert constraints dict to TradingConstraints
        constraints_dict = request.constraints
        constraints = TradingConstraints(
            start_time=pd.to_datetime(constraints_dict["start_time"]),
            end_time=pd.to_datetime(constraints_dict["end_time"]),
            **{k: v for k, v in constraints_dict.items() if k not in ["start_time", "end_time"]}
        )
        
        # Create optimizer
        optimizer = ExecutionOptimizer()
        
        # Optimize execution
        optimal_schedule = optimizer.optimize_execution(
            symbol=request.symbol,
            total_quantity=request.total_quantity,
            side=request.side,
            strategy=strategy_enum,
            market_data=request.market_data,
            constraints=constraints
        )
        
        return optimal_schedule.to_dict()
    
    except Exception as e:
        logger.error(f"Execution optimization error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/execution-optimization/compare-strategies", response_model=Dict)
async def compare_execution_strategies(request: ExecutionOptimizationRequest):
    """
    Compare multiple execution strategies.
    """
    try:
        # Convert constraints
        constraints_dict = request.constraints
        constraints = TradingConstraints(
            start_time=pd.to_datetime(constraints_dict["start_time"]),
            end_time=pd.to_datetime(constraints_dict["end_time"]),
            **{k: v for k, v in constraints_dict.items() if k not in ["start_time", "end_time"]}
        )
        
        # Create optimizer
        optimizer = ExecutionOptimizer()
        
        # Compare strategies
        strategy_results = optimizer.compare_strategies(
            symbol=request.symbol,
            total_quantity=request.total_quantity,
            side=request.side,
            market_data=request.market_data,
            constraints=constraints
        )
        
        # Recommend best strategy
        recommended_strategy, recommended_schedule = optimizer.recommend_strategy(
            symbol=request.symbol,
            total_quantity=request.total_quantity,
            side=request.side,
            market_data=request.market_data,
            constraints=constraints,
            objective=request.objective
        )
        
        return {
            "strategy_comparison": {
                strategy: schedule.to_dict() 
                for strategy, schedule in strategy_results.items()
            },
            "recommended_strategy": recommended_strategy.value,
            "recommended_schedule": recommended_schedule.to_dict()
        }
    
    except Exception as e:
        logger.error(f"Strategy comparison error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


# Real-time Monitoring Endpoints
@router.post("/monitoring/start", response_model=Dict)
async def start_real_time_monitoring(background_tasks: BackgroundTasks):
    """
    Start real-time TCA monitoring.
    """
    try:
        background_tasks.add_task(tca_monitor.start_monitoring)
        
        return {
            "status": "monitoring_started",
            "message": "Real-time TCA monitoring has been started"
        }
    
    except Exception as e:
        logger.error(f"Monitoring start error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/monitoring/stop", response_model=Dict)
async def stop_real_time_monitoring(background_tasks: BackgroundTasks):
    """
    Stop real-time TCA monitoring.
    """
    try:
        background_tasks.add_task(tca_monitor.stop_monitoring)
        
        return {
            "status": "monitoring_stopped",
            "message": "Real-time TCA monitoring has been stopped"
        }
    
    except Exception as e:
        logger.error(f"Monitoring stop error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/monitoring/add-order", response_model=Dict)
async def add_order_for_monitoring(request: RealTimeMonitorRequest):
    """
    Add order to real-time monitoring.
    """
    try:
        tca_monitor.add_order_for_monitoring(
            order_id=request.order_id,
            symbol=request.symbol,
            side=request.side,
            target_quantity=request.target_quantity,
            arrival_price=request.arrival_price,
            start_time=request.start_time,
            expected_end_time=request.expected_end_time,
            strategy=request.strategy
        )
        
        return {
            "status": "order_added",
            "order_id": request.order_id,
            "message": f"Order {request.order_id} added to monitoring"
        }
    
    except Exception as e:
        logger.error(f"Add order monitoring error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/monitoring/update-fill", response_model=Dict)
async def update_order_fill(request: FillUpdateRequest):
    """
    Update order with new fill for monitoring.
    """
    try:
        tca_monitor.update_order_fill(
            order_id=request.order_id,
            fill_price=request.fill_price,
            fill_quantity=request.fill_quantity,
            fill_time=request.fill_time,
            market_price=request.market_price
        )
        
        return {
            "status": "fill_updated",
            "order_id": request.order_id,
            "message": f"Fill updated for order {request.order_id}"
        }
    
    except Exception as e:
        logger.error(f"Fill update error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/monitoring/order-metrics/{order_id}", response_model=Dict)
async def get_order_metrics(order_id: str):
    """
    Get current monitoring metrics for order.
    """
    try:
        metrics = tca_monitor.get_order_metrics(order_id)
        
        if metrics is None:
            raise HTTPException(status_code=404, detail=f"Order {order_id} not found in monitoring")
        
        return metrics.to_dict()
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get order metrics error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/monitoring/alerts", response_model=Dict)
async def get_recent_alerts(limit: int = 10):
    """
    Get recent TCA alerts.
    """
    try:
        alerts = tca_monitor.get_recent_alerts(limit)
        
        return {
            "alerts": [alert.to_dict() for alert in alerts],
            "count": len(alerts)
        }
    
    except Exception as e:
        logger.error(f"Get alerts error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/monitoring/execution-report/{order_id}", response_model=Dict)
async def generate_execution_report(order_id: str):
    """
    Generate comprehensive execution report.
    """
    try:
        report = tca_monitor.generate_execution_report(order_id)
        return report
    
    except Exception as e:
        logger.error(f"Execution report error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


# Cost Attribution Endpoints
@router.post("/cost-attribution/analyze", response_model=Dict)
async def analyze_cost_attribution(request: CostAttributionRequest):
    """
    Perform comprehensive cost attribution analysis.
    """
    try:
        # Convert market data to DataFrame
        market_df = pd.DataFrame(request.market_data)
        if not market_df.empty and "timestamp" in market_df.columns:
            market_df["timestamp"] = pd.to_datetime(market_df["timestamp"])
            market_df.set_index("timestamp", inplace=True)
        
        # Create attribution analyzer
        attribution = CostAttribution()
        
        # Perform analysis
        result = attribution.attribute_execution_costs(
            order_data=request.order_data,
            market_data=market_df,
            venue_data=request.venue_data,
            strategy_context=request.strategy_context
        )
        
        return result.to_dict()
    
    except Exception as e:
        logger.error(f"Cost attribution analysis error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/cost-attribution/batch-analyze", response_model=Dict)
async def batch_analyze_cost_attribution(
    orders_data: List[Dict],
    market_data_dict: Dict[str, List[Dict]]
):
    """
    Perform batch cost attribution analysis.
    """
    try:
        # Convert market data
        market_data_frames = {}
        for symbol, data in market_data_dict.items():
            df = pd.DataFrame(data)
            if not df.empty and "timestamp" in df.columns:
                df["timestamp"] = pd.to_datetime(df["timestamp"])
                df.set_index("timestamp", inplace=True)
            market_data_frames[symbol] = df
        
        # Create attribution analyzer
        attribution = CostAttribution()
        
        # Batch analysis
        results = attribution.batch_attribution_analysis(orders_data, market_data_frames)
        
        # Generate summary
        summary = attribution.generate_attribution_summary(results)
        
        return {
            "individual_attributions": [result.to_dict() for result in results],
            "summary_report": summary
        }
    
    except Exception as e:
        logger.error(f"Batch cost attribution error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


# Utility Endpoints
@router.get("/models", response_model=Dict)
async def get_available_models():
    """
    Get all available TCA models and configurations.
    """
    return {
        "market_impact_models": ["linear", "square_root", "power_law", "liquidity_adjusted"],
        "execution_strategies": [strategy.value for strategy in ExecutionStrategy],
        "benchmark_types": [benchmark.value for benchmark in BenchmarkType],
        "alert_types": [alert_type.value for alert_type in AlertType],
    }


@router.get("/health", response_model=Dict)
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "transaction_cost_analysis",
        "monitoring_active": tca_monitor._is_monitoring,
        "timestamp": datetime.utcnow().isoformat()
    }