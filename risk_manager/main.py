"""
Risk Management API Endpoints

This module provides FastAPI endpoints for all risk management functionality
including position sizing, stop-loss management, portfolio risk monitoring, and alerts.
"""

from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Union
from datetime import datetime, timezone, timedelta
from enum import Enum
import asyncio
import structlog
import sys

sys.path.append('../shared')
from price_prediction_client import PricePredictionClient

from config import settings
from database import RiskManagementDatabase
from position_sizing import PositionSizingEngine, PositionSizeRequest, PositionSizeResult
from stop_loss_manager import StopLossManager, StopLossConfig, StopLossType, StopLossOrder
from portfolio_risk_controller import PortfolioRiskController, RiskMetrics, RiskAlert, RiskLevel
from advanced_risk_service import get_advanced_risk_service

logger = structlog.get_logger()

# Pydantic models for API requests/responses

class PositionSizeRequestModel(BaseModel):
    """Position sizing request model"""
    symbol: str = Field(..., description="Trading symbol")
    strategy_id: str = Field(..., description="Strategy identifier")
    signal_strength: float = Field(..., ge=0.0, le=1.0, description="Signal strength (0-1)")
    current_price: float = Field(..., gt=0, description="Current market price")
    volatility: Optional[float] = Field(None, ge=0, description="Asset volatility")
    stop_loss_percent: Optional[float] = Field(None, ge=0, le=50, description="Stop-loss percentage")
    risk_per_trade_percent: Optional[float] = Field(None, ge=0.1, le=10, description="Risk per trade percentage")
    order_side: Optional[str] = Field(None, description="Intended order side (BUY or SELL)")

class PositionSizeResponse(BaseModel):
    """Position sizing response model"""
    success: bool
    recommended_size_usd: float
    recommended_quantity: float
    position_risk_percent: float
    stop_loss_price: Optional[float]
    max_loss_usd: float
    confidence_score: float
    risk_factors: Dict[str, float]
    warnings: List[str]
    approved: bool
    price_prediction: Optional[Dict[str, Union[float, str]]] = None

class StopLossConfigModel(BaseModel):
    """Stop-loss configuration model"""
    stop_type: StopLossType
    initial_stop_percent: float = Field(..., ge=0.1, le=20, description="Initial stop-loss percentage")
    trailing_distance_percent: Optional[float] = Field(None, ge=0.1, le=10, description="Trailing distance percentage")
    max_loss_percent: Optional[float] = Field(None, ge=1, le=50, description="Maximum loss percentage")
    min_profit_before_trail: Optional[float] = Field(None, ge=0, le=10, description="Minimum profit before trailing")
    volatility_multiplier: Optional[float] = Field(None, ge=0.5, le=5, description="Volatility multiplier")
    support_resistance_buffer: Optional[float] = Field(None, ge=0.1, le=2, description="S/R buffer percentage")
    time_decay_enabled: bool = Field(False, description="Enable time-based decay")
    breakeven_protection: bool = Field(True, description="Enable breakeven protection")

class StopLossCreateRequest(BaseModel):
    """Stop-loss creation request"""
    position_id: str = Field(..., description="Position identifier")
    symbol: str = Field(..., description="Trading symbol")
    entry_price: float = Field(..., gt=0, description="Position entry price")
    quantity: float = Field(..., gt=0, description="Position quantity")
    config: StopLossConfigModel
    metadata: Optional[Dict] = Field(None, description="Additional metadata")

class PriceUpdateModel(BaseModel):
    """Price update model for real-time risk monitoring"""
    price_updates: Dict[str, float] = Field(..., description="Symbol to price mapping")

class RiskLimitsModel(BaseModel):
    """Risk limits configuration model"""
    max_single_position: Optional[float] = Field(None, ge=1, le=50, description="Maximum single position %")
    max_var_percent: Optional[float] = Field(None, ge=1, le=20, description="Maximum VaR %")
    max_drawdown_percent: Optional[float] = Field(None, ge=5, le=50, description="Maximum drawdown %")
    max_leverage: Optional[float] = Field(None, ge=1, le=10, description="Maximum leverage ratio")

# Initialize components
database = RiskManagementDatabase()
price_prediction_client = PricePredictionClient(
    base_url=settings.STRATEGY_SERVICE_URL,
    service_name=settings.SERVICE_NAME,
    cache_ttl_seconds=180
)

position_sizing_engine = PositionSizingEngine(
    database,
    price_prediction_client=price_prediction_client
)
stop_loss_manager = StopLossManager(database)
portfolio_controller = PortfolioRiskController(database)

app = FastAPI(
    title="MasterTrade Risk Management API",
    description="Comprehensive risk management system for trading operations",
    version="1.0.0"
)

# Include advanced risk management router
from advanced_risk_api import router as advanced_risk_router
app.include_router(advanced_risk_router)

# Dependency to get database connection
async def get_database():
    """Get database connection"""
    return database

@app.on_event("startup")
async def startup_event():
    """Initialize application on startup"""
    try:
        logger.info("Starting Risk Management API")
        await database.initialize()
    await price_prediction_client.initialize()
        logger.info("Risk Management API started successfully")
    except Exception as e:
        logger.error(f"Failed to start Risk Management API: {e}")
        raise

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    try:
        logger.info("Shutting down Risk Management API")
        await database.close()
    await price_prediction_client.close()
        logger.info("Risk Management API shutdown completed")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")

# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        # Check database connection
        await database.get_account_balance()
        return {
            "status": "healthy",
            "timestamp": datetime.now(timezone.utc),
            "version": "1.0.0",
            "components": {
                "database": "healthy",
                "position_sizing": "healthy",
                "stop_loss_manager": "healthy",
                "portfolio_controller": "healthy"
            }
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.now(timezone.utc)
            }
        )

# Position Sizing Endpoints

@app.post("/position-sizing/calculate", response_model=PositionSizeResponse)
async def calculate_position_size(
    request: PositionSizeRequestModel,
    db: RiskManagementDatabase = Depends(get_database)
):
    """
    Calculate optimal position size for a trading signal
    
    This endpoint uses multiple algorithms including volatility-based sizing,
    Kelly criterion, and risk parity to determine the optimal position size.
    """
    try:
        logger.info(f"Position sizing request for {request.symbol}", strategy_id=request.strategy_id)
        
        # Convert to internal request format
        size_request = PositionSizeRequest(
            symbol=request.symbol,
            strategy_id=request.strategy_id,
            signal_strength=request.signal_strength,
            current_price=request.current_price,
            volatility=request.volatility,
            stop_loss_percent=request.stop_loss_percent,
            risk_per_trade_percent=request.risk_per_trade_percent,
            order_side=request.order_side
        )
        
        # Calculate position size
        result = await position_sizing_engine.calculate_position_size(size_request)
        
        return PositionSizeResponse(
            success=True,
            recommended_size_usd=result.recommended_size_usd,
            recommended_quantity=result.recommended_quantity,
            position_risk_percent=result.position_risk_percent,
            stop_loss_price=result.stop_loss_price,
            max_loss_usd=result.max_loss_usd,
            confidence_score=result.confidence_score,
            risk_factors=result.risk_factors,
            warnings=result.warnings,
            approved=result.approved,
            price_prediction=result.price_prediction
        )
        
    except Exception as e:
        logger.error(f"Error calculating position size: {e}")
        raise HTTPException(status_code=500, detail=f"Position sizing calculation failed: {str(e)}")

@app.get("/position-sizing/limits")
async def get_position_sizing_limits():
    """Get current position sizing limits and parameters"""
    try:
        return {
            "min_position_size_usd": settings.MIN_POSITION_SIZE_USD,
            "max_position_size_usd": settings.MAX_POSITION_SIZE_USD,
            "max_single_position_percent": settings.MAX_SINGLE_POSITION_PERCENT,
            "default_risk_per_trade": settings.DEFAULT_RISK_PER_TRADE,
            "max_leverage_ratio": settings.MAX_LEVERAGE_RATIO,
            "asset_class_limits": {
                "crypto_max_percent": settings.CRYPTO_MAX_POSITION_PERCENT,
                "stablecoin_max_percent": settings.STABLECOIN_MAX_POSITION_PERCENT,
                "defi_max_percent": settings.DEFI_MAX_POSITION_PERCENT
            },
            "risk_thresholds": {
                "high_volatility": settings.HIGH_VOLATILITY_THRESHOLD,
                "low_liquidity": settings.LOW_LIQUIDITY_THRESHOLD,
                "risk_score_threshold": settings.RISK_SCORE_THRESHOLD
            }
        }
    except Exception as e:
        logger.error(f"Error getting position sizing limits: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Stop-Loss Management Endpoints

@app.post("/stop-loss/create")
async def create_stop_loss(
    request: StopLossCreateRequest,
    db: RiskManagementDatabase = Depends(get_database)
):
    """
    Create a new stop-loss order for a position
    
    Supports multiple stop-loss types including fixed, trailing, volatility-based,
    ATR-based, and support/resistance levels.
    """
    try:
        logger.info(f"Creating stop-loss for position {request.position_id}")
        
        # Convert config to internal format
        config = StopLossConfig(
            stop_type=request.config.stop_type,
            initial_stop_percent=request.config.initial_stop_percent,
            trailing_distance_percent=request.config.trailing_distance_percent,
            max_loss_percent=request.config.max_loss_percent,
            min_profit_before_trail=request.config.min_profit_before_trail,
            volatility_multiplier=request.config.volatility_multiplier,
            support_resistance_buffer=request.config.support_resistance_buffer,
            time_decay_enabled=request.config.time_decay_enabled,
            breakeven_protection=request.config.breakeven_protection
        )
        
        # Create stop-loss order
        stop_order = await stop_loss_manager.create_stop_loss(
            position_id=request.position_id,
            symbol=request.symbol,
            entry_price=request.entry_price,
            quantity=request.quantity,
            config=config,
            metadata=request.metadata
        )
        
        return {
            "success": True,
            "order_id": stop_order.id,
            "stop_price": stop_order.stop_price,
            "stop_type": stop_order.stop_type.value,
            "created_at": stop_order.created_at,
            "message": f"Stop-loss created for {request.symbol}"
        }
        
    except Exception as e:
        logger.error(f"Error creating stop-loss: {e}")
        raise HTTPException(status_code=500, detail=f"Stop-loss creation failed: {str(e)}")

@app.post("/stop-loss/update-prices")
async def update_stop_loss_prices(
    price_updates: PriceUpdateModel,
    background_tasks: BackgroundTasks,
    db: RiskManagementDatabase = Depends(get_database)
):
    """
    Update all stop-loss orders with new price data
    
    This endpoint processes real-time price updates and adjusts stop-loss orders
    accordingly. Returns any triggered stops.
    """
    try:
        logger.info(f"Updating stop-loss prices for {len(price_updates.price_updates)} symbols")
        
        # Update stop-loss prices
        updates = await stop_loss_manager.update_stop_losses(price_updates.price_updates)
        
        # Check for triggers
        triggered_orders = await stop_loss_manager.check_stop_triggers(price_updates.price_updates)
        
        # Schedule background portfolio risk update
        background_tasks.add_task(
            portfolio_controller.monitor_real_time_risk, 
            price_updates.price_updates
        )
        
        return {
            "success": True,
            "updates_count": len(updates),
            "triggered_count": len(triggered_orders),
            "updates": [
                {
                    "order_id": update.order_id,
                    "symbol": next(
                        (order.symbol for order in stop_loss_manager.active_stops.values() 
                         if order.id == update.order_id), "unknown"
                    ),
                    "old_stop_price": update.old_stop_price,
                    "new_stop_price": update.new_stop_price,
                    "trigger_reason": update.trigger_reason,
                    "confidence": update.confidence
                } for update in updates
            ],
            "triggered_orders": [
                {
                    "order_id": order.id,
                    "symbol": order.symbol,
                    "trigger_price": order.current_price,
                    "stop_price": order.stop_price,
                    "loss_amount": order.profit_loss
                } for order in triggered_orders
            ]
        }
        
    except Exception as e:
        logger.error(f"Error updating stop-loss prices: {e}")
        raise HTTPException(status_code=500, detail=f"Stop-loss update failed: {str(e)}")

@app.get("/stop-loss/status/{position_id}")
async def get_stop_loss_status(
    position_id: str,
    db: RiskManagementDatabase = Depends(get_database)
):
    """Get current stop-loss status for a position"""
    try:
        stop_order = await stop_loss_manager.get_stop_loss_status(position_id)
        
        if not stop_order:
            raise HTTPException(status_code=404, detail="No active stop-loss found for position")
        
        return {
            "order_id": stop_order.id,
            "position_id": stop_order.position_id,
            "symbol": stop_order.symbol,
            "stop_type": stop_order.stop_type.value,
            "status": stop_order.status.value,
            "entry_price": stop_order.entry_price,
            "current_price": stop_order.current_price,
            "stop_price": stop_order.stop_price,
            "quantity": stop_order.quantity,
            "profit_loss": stop_order.profit_loss,
            "created_at": stop_order.created_at,
            "last_updated": stop_order.last_updated,
            "config": {
                "stop_type": stop_order.config.stop_type.value,
                "initial_stop_percent": stop_order.config.initial_stop_percent,
                "trailing_distance_percent": stop_order.config.trailing_distance_percent,
                "breakeven_protection": stop_order.config.breakeven_protection,
                "time_decay_enabled": stop_order.config.time_decay_enabled
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting stop-loss status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/stop-loss/{order_id}")
async def modify_stop_loss(
    order_id: str,
    new_stop_price: Optional[float] = None,
    new_config: Optional[StopLossConfigModel] = None,
    db: RiskManagementDatabase = Depends(get_database)
):
    """Modify an existing stop-loss order"""
    try:
        config = None
        if new_config:
            config = StopLossConfig(
                stop_type=new_config.stop_type,
                initial_stop_percent=new_config.initial_stop_percent,
                trailing_distance_percent=new_config.trailing_distance_percent,
                max_loss_percent=new_config.max_loss_percent,
                min_profit_before_trail=new_config.min_profit_before_trail,
                volatility_multiplier=new_config.volatility_multiplier,
                support_resistance_buffer=new_config.support_resistance_buffer,
                time_decay_enabled=new_config.time_decay_enabled,
                breakeven_protection=new_config.breakeven_protection
            )
        
        success = await stop_loss_manager.modify_stop_loss(order_id, config, new_stop_price)
        
        if not success:
            raise HTTPException(status_code=404, detail="Stop-loss order not found or cannot be modified")
        
        return {
            "success": True,
            "order_id": order_id,
            "message": "Stop-loss order modified successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error modifying stop-loss: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/stop-loss/{order_id}")
async def cancel_stop_loss(
    order_id: str,
    db: RiskManagementDatabase = Depends(get_database)
):
    """Cancel a stop-loss order"""
    try:
        success = await stop_loss_manager.cancel_stop_loss(order_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="Stop-loss order not found")
        
        return {
            "success": True,
            "order_id": order_id,
            "message": "Stop-loss order cancelled successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cancelling stop-loss: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Portfolio Risk Management Endpoints

@app.get("/portfolio/risk-metrics")
async def get_portfolio_risk_metrics(
    db: RiskManagementDatabase = Depends(get_database)
):
    """
    Get comprehensive portfolio risk metrics
    
    Returns current risk measurements including VaR, drawdown, concentration,
    correlation risk, and overall risk score.
    """
    try:
        risk_metrics = await portfolio_controller.calculate_portfolio_risk()
        
        return {
            "timestamp": risk_metrics.timestamp,
            "portfolio_value": risk_metrics.total_portfolio_value,
            "total_exposure": risk_metrics.total_exposure,
            "cash_balance": risk_metrics.cash_balance,
            "leverage_ratio": risk_metrics.leverage_ratio,
            "risk_measures": {
                "var_1d": risk_metrics.var_1d,
                "var_5d": risk_metrics.var_5d,
                "expected_shortfall": risk_metrics.expected_shortfall,
                "max_drawdown": risk_metrics.max_drawdown,
                "current_drawdown": risk_metrics.current_drawdown
            },
            "diversification": {
                "concentration_hhi": risk_metrics.concentration_hhi,
                "correlation_risk": risk_metrics.correlation_risk,
                "sector_concentration": risk_metrics.sector_concentration,
                "largest_position_percent": risk_metrics.largest_position_percent,
                "positions_over_5pct": risk_metrics.positions_over_5pct,
                "positions_over_10pct": risk_metrics.positions_over_10pct
            },
            "liquidity": {
                "avg_liquidity_score": risk_metrics.avg_liquidity_score,
                "illiquid_positions_percent": risk_metrics.illiquid_positions_percent
            },
            "overall_risk": {
                "risk_level": risk_metrics.risk_level.value,
                "risk_score": risk_metrics.risk_score
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting portfolio risk metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/portfolio/risk-alerts")
async def get_risk_alerts(
    active_only: bool = Query(True, description="Return only active alerts"),
    db: RiskManagementDatabase = Depends(get_database)
):
    """Get current risk alerts and limit breaches"""
    try:
        if active_only:
            alerts = await portfolio_controller.check_risk_limits()
        else:
            # Get all alerts from database
            alerts = await database.get_risk_alerts(days=7)  # Last 7 days
        
        return {
            "alert_count": len(alerts),
            "alerts": [
                {
                    "id": alert.id,
                    "type": alert.alert_type.value,
                    "severity": alert.severity.value,
                    "title": alert.title,
                    "message": alert.message,
                    "symbol": alert.symbol,
                    "current_value": alert.current_value,
                    "threshold_value": alert.threshold_value,
                    "recommendation": alert.recommendation,
                    "created_at": alert.created_at,
                    "resolved_at": alert.resolved_at
                } for alert in alerts
            ]
        }
        
    except Exception as e:
        logger.error(f"Error getting risk alerts: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/portfolio/dashboard")
async def get_risk_dashboard(
    db: RiskManagementDatabase = Depends(get_database)
):
    """
    Get comprehensive risk dashboard data
    
    Returns all data needed for a complete risk management dashboard including
    current metrics, historical trends, alerts, and correlations.
    """
    try:
        dashboard_data = await portfolio_controller.get_risk_dashboard_data()
        
        # Convert datetime objects to ISO strings for JSON serialization
        if 'historical_data' in dashboard_data:
            dashboard_data['historical_data']['timestamps'] = [
                ts.isoformat() if hasattr(ts, 'isoformat') else str(ts)
                for ts in dashboard_data['historical_data']['timestamps']
            ]
        
        return dashboard_data
        
    except Exception as e:
        logger.error(f"Error getting dashboard data: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/portfolio/rebalance-suggestions")
async def get_rebalancing_suggestions(
    db: RiskManagementDatabase = Depends(get_database)
):
    """Get AI-generated portfolio rebalancing suggestions to reduce risk"""
    try:
        suggestions = await portfolio_controller.suggest_risk_rebalancing()
        
        return {
            "suggestion_count": len(suggestions),
            "suggestions": suggestions,
            "generated_at": datetime.now(timezone.utc)
        }
        
    except Exception as e:
        logger.error(f"Error getting rebalancing suggestions: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/portfolio/real-time-risk")
async def monitor_real_time_risk(
    price_updates: PriceUpdateModel,
    db: RiskManagementDatabase = Depends(get_database)
):
    """
    Real-time portfolio risk monitoring with price updates
    
    Calculates immediate risk impact of price changes and identifies
    any risk limit breaches that require immediate attention.
    """
    try:
        risk_summary = await portfolio_controller.monitor_real_time_risk(
            price_updates.price_updates
        )
        
        return risk_summary
        
    except Exception as e:
        logger.error(f"Error in real-time risk monitoring: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Configuration and Administration Endpoints

@app.get("/config/risk-limits")
async def get_risk_limits():
    """Get current risk management configuration limits"""
    return {
        "position_limits": {
            "max_single_position_percent": settings.MAX_SINGLE_POSITION_PERCENT,
            "min_position_size_usd": settings.MIN_POSITION_SIZE_USD,
            "max_position_size_usd": settings.MAX_POSITION_SIZE_USD
        },
        "portfolio_limits": {
            "max_portfolio_risk_percent": settings.MAX_PORTFOLIO_RISK_PERCENT,
            "max_leverage_ratio": settings.MAX_LEVERAGE_RATIO,
            "max_drawdown_percent": settings.MAX_DRAWDOWN_PERCENT,
            "max_var_percent": settings.MAX_VAR_PERCENT
        },
        "correlation_limits": {
            "max_correlation_exposure": settings.MAX_CORRELATION_EXPOSURE,
            "enable_correlation_limits": settings.ENABLE_CORRELATION_LIMITS
        },
        "stop_loss_limits": {
            "min_stop_loss_percent": settings.MIN_STOP_LOSS_PERCENT,
            "max_stop_loss_percent": settings.MAX_STOP_LOSS_PERCENT,
            "default_stop_loss_percent": settings.DEFAULT_STOP_LOSS_PERCENT
        }
    }

@app.put("/config/risk-limits")
async def update_risk_limits(
    limits: RiskLimitsModel,
    db: RiskManagementDatabase = Depends(get_database)
):
    """Update risk management configuration limits (admin only)"""
    try:
        # In a production system, this would include authentication and authorization
        
        updates = {}
        if limits.max_single_position is not None:
            settings.MAX_SINGLE_POSITION_PERCENT = limits.max_single_position
            updates['max_single_position_percent'] = limits.max_single_position
        
        if limits.max_var_percent is not None:
            settings.MAX_VAR_PERCENT = limits.max_var_percent
            updates['max_var_percent'] = limits.max_var_percent
        
        if limits.max_drawdown_percent is not None:
            settings.MAX_DRAWDOWN_PERCENT = limits.max_drawdown_percent
            updates['max_drawdown_percent'] = limits.max_drawdown_percent
        
        if limits.max_leverage is not None:
            settings.MAX_LEVERAGE_RATIO = limits.max_leverage
            updates['max_leverage_ratio'] = limits.max_leverage
        
        # Save configuration changes
        await database.store_configuration_change(updates)
        
        return {
            "success": True,
            "updates": updates,
            "message": "Risk limits updated successfully"
        }
        
    except Exception as e:
        logger.error(f"Error updating risk limits: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8005,
        log_level="info"
    )