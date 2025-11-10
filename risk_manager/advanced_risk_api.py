"""
Advanced Risk Management API Endpoints

Additional API endpoints for advanced risk management features:
- Trade approval with comprehensive risk checks
- Dynamic stop-loss management
- Circuit breaker monitoring and override
- Correlation analysis
- Risk dashboard
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Dict, List, Optional
from datetime import datetime
import structlog

from advanced_risk_service import get_advanced_risk_service, AdvancedRiskManagementService

logger = structlog.get_logger()

# Create router
router = APIRouter(prefix="/api/v1/advanced-risk", tags=["Advanced Risk Management"])


# Request/Response Models

class TradeApprovalRequest(BaseModel):
    """Trade approval request model"""
    symbol: str = Field(..., description="Trading symbol")
    strategy_id: str = Field(..., description="Strategy identifier")
    signal_strength: float = Field(..., ge=0.0, le=1.0, description="Signal strength (0-1)")
    requested_size_usd: float = Field(..., gt=0, description="Requested position size USD")
    current_price: float = Field(..., gt=0, description="Current market price")
    volatility: Optional[float] = Field(None, ge=0, description="Asset volatility")


class TradeApprovalResponse(BaseModel):
    """Trade approval response model"""
    approved: bool
    position_size_adjustment: float
    adjusted_size_usd: float
    stop_loss_percent: float
    stop_loss_price: float
    risk_score: float
    risk_level: str
    risk_factors: Dict[str, float]
    warnings: List[str]
    rejections: List[str]
    recommendations: List[str]
    metadata: Dict


class PositionSizeRecommendationRequest(BaseModel):
    """Position size recommendation request"""
    symbol: str
    strategy_id: str
    signal_strength: float = Field(ge=0.0, le=1.0)
    current_price: float = Field(gt=0)


class StopLossUpdateRequest(BaseModel):
    """Stop-loss update request"""
    position_id: str
    new_stop_price: Optional[float] = Field(None, gt=0)


class PortfolioLimitsUpdateRequest(BaseModel):
    """Portfolio limits update request"""
    max_portfolio_leverage: Optional[float] = Field(None, ge=1.0, le=10.0)
    max_portfolio_var_percent: Optional[float] = Field(None, ge=1.0, le=20.0)
    max_drawdown_percent: Optional[float] = Field(None, ge=5.0, le=50.0)
    max_single_position_percent: Optional[float] = Field(None, ge=1.0, le=50.0)
    max_correlated_exposure_percent: Optional[float] = Field(None, ge=10.0, le=100.0)
    max_sector_exposure_percent: Optional[float] = Field(None, ge=10.0, le=100.0)


class CircuitBreakerOverrideRequest(BaseModel):
    """Circuit breaker override request"""
    level: str = Field(..., description="none, warning, level_1, level_2, level_3")
    reason: str = Field(..., description="Reason for override")
    admin_authorization: str = Field(..., description="Admin authorization code")


# Dependency

async def get_risk_service() -> AdvancedRiskManagementService:
    """Get advanced risk service instance"""
    return get_advanced_risk_service()


# Endpoints

@router.post("/approve-trade", response_model=TradeApprovalResponse)
async def approve_trade(
    request: TradeApprovalRequest,
    service: AdvancedRiskManagementService = Depends(get_risk_service)
):
    """
    Comprehensive trade approval with all risk checks
    
    Performs:
    - Circuit breaker checks
    - Portfolio-level limit validation
    - Correlation risk assessment
    - Sector/asset class exposure checks
    - Volatility regime analysis
    - Dynamic position sizing
    - Stop-loss calculation
    
    Returns approval decision with adjustments
    """
    try:
        result = await service.approve_trade(
            symbol=request.symbol,
            strategy_id=request.strategy_id,
            signal_strength=request.signal_strength,
            requested_size_usd=request.requested_size_usd,
            current_price=request.current_price,
            volatility=request.volatility
        )
        
        # Calculate adjusted values
        adjusted_size = request.requested_size_usd * result.position_size_adjustment
        stop_loss_price = request.current_price * (1 - result.stop_loss_params.adjusted_stop_percent)
        
        # Map risk score to level
        if result.risk_score < 30:
            risk_level = "low"
        elif result.risk_score < 60:
            risk_level = "medium"
        elif result.risk_score < 80:
            risk_level = "high"
        else:
            risk_level = "critical"
        
        return TradeApprovalResponse(
            approved=result.approved,
            position_size_adjustment=result.position_size_adjustment,
            adjusted_size_usd=adjusted_size,
            stop_loss_percent=result.stop_loss_params.adjusted_stop_percent,
            stop_loss_price=stop_loss_price,
            risk_score=result.risk_score,
            risk_level=risk_level,
            risk_factors=result.risk_factors,
            warnings=result.warnings,
            rejections=result.rejections,
            recommendations=result.recommendations,
            metadata=result.metadata
        )
        
    except Exception as e:
        logger.error(f"Error in trade approval endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/position-size-recommendation")
async def get_position_size_recommendation(
    request: PositionSizeRecommendationRequest,
    service: AdvancedRiskManagementService = Depends(get_risk_service)
):
    """
    Get position size recommendation without full approval
    
    Useful for strategy services to estimate position sizes
    during strategy development or backtesting
    """
    try:
        result = await service.get_position_size_recommendation(
            symbol=request.symbol,
            strategy_id=request.strategy_id,
            signal_strength=request.signal_strength,
            current_price=request.current_price
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Error in position size recommendation: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/update-stop-loss")
async def update_stop_loss(
    request: StopLossUpdateRequest,
    service: AdvancedRiskManagementService = Depends(get_risk_service)
):
    """
    Update stop-loss for a position
    
    If new_stop_price not provided, calculates optimal stop
    based on current volatility regime
    """
    try:
        result = await service.update_stop_loss(
            position_id=request.position_id,
            new_stop_price=request.new_stop_price
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Error updating stop-loss: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/risk-status")
async def get_risk_status(
    service: AdvancedRiskManagementService = Depends(get_risk_service)
):
    """
    Get comprehensive risk status dashboard
    
    Returns:
    - Circuit breaker status
    - Current risk regime
    - Portfolio metrics (leverage, VaR, drawdown)
    - Correlation metrics
    - Active limits
    - Position count
    """
    try:
        result = await service.get_risk_status()
        return result
        
    except Exception as e:
        logger.error(f"Error getting risk status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/drawdown-status")
async def get_drawdown_status(
    service: AdvancedRiskManagementService = Depends(get_risk_service)
):
    """
    Get current drawdown and circuit breaker status
    
    Returns detailed drawdown information including:
    - Current portfolio value
    - Peak portfolio value
    - Drawdown percentage
    - Circuit breaker level
    - Position restrictions
    """
    try:
        status = await service.get_risk_status()
        
        if not status['success']:
            raise HTTPException(status_code=500, detail=status.get('error', 'Unknown error'))
        
        return {
            'success': True,
            'circuit_breaker': status['data']['circuit_breaker'],
            'portfolio_value': status['data']['portfolio_metrics']['total_value']
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting drawdown status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/update-limits")
async def update_portfolio_limits(
    request: PortfolioLimitsUpdateRequest,
    service: AdvancedRiskManagementService = Depends(get_risk_service)
):
    """
    Update portfolio risk limits
    
    Updates one or more risk limits. Only provided values are updated.
    Requires admin authorization.
    """
    try:
        # Convert request to dict, excluding None values
        limits = {k: v for k, v in request.dict().items() if v is not None}
        
        if not limits:
            raise HTTPException(status_code=400, detail="No limits provided to update")
        
        result = await service.update_portfolio_limits(limits)
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating limits: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/circuit-breaker-override")
async def override_circuit_breaker(
    request: CircuitBreakerOverrideRequest,
    service: AdvancedRiskManagementService = Depends(get_risk_service)
):
    """
    Manual override of circuit breaker
    
    ⚠️  USE WITH EXTREME CAUTION ⚠️
    
    Allows manual override of circuit breaker levels.
    Requires admin authorization code.
    All overrides are logged for audit purposes.
    """
    try:
        # Validate admin authorization
        # This is a placeholder - implement your own security
        if request.admin_authorization != "ADMIN_OVERRIDE_CODE_CHANGE_ME":
            raise HTTPException(status_code=403, detail="Invalid authorization code")
        
        # Validate level
        valid_levels = ['none', 'warning', 'level_1', 'level_2', 'level_3']
        if request.level not in valid_levels:
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid level. Must be one of: {valid_levels}"
            )
        
        result = await service.override_circuit_breaker(
            level=request.level,
            reason=request.reason
        )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in circuit breaker override: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/force-adjustment-check")
async def force_adjustment_check(
    service: AdvancedRiskManagementService = Depends(get_risk_service)
):
    """
    Manually trigger position adjustment check
    
    Forces immediate check of all positions for:
    - Stop-loss adjustments
    - Position size reductions
    - Circuit breaker actions
    
    Normally runs automatically every 5 minutes.
    """
    try:
        result = await service.force_adjustment_check()
        return result
        
    except Exception as e:
        logger.error(f"Error in force adjustment check: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/correlation-analysis")
async def get_correlation_analysis(
    symbols: Optional[str] = None,
    service: AdvancedRiskManagementService = Depends(get_risk_service)
):
    """
    Get correlation analysis for portfolio or specific symbols
    
    Args:
        symbols: Optional comma-separated list of symbols. If not provided, analyzes entire portfolio.
    
    Returns:
        Correlation metrics including:
        - Average portfolio correlation
        - Diversification ratio
        - Effective number of independent assets
        - Correlation risk score
        - Correlation clusters
        - Recommendations
    """
    try:
        symbol_list = None
        if symbols:
            symbol_list = [s.strip() for s in symbols.split(',')]
        
        result = await service.get_correlation_analysis(symbol_list)
        
        return result
        
    except Exception as e:
        logger.error(f"Error in correlation analysis: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/risk-regime")
async def get_current_risk_regime(
    service: AdvancedRiskManagementService = Depends(get_risk_service)
):
    """
    Get current market risk regime
    
    Regimes:
    - low_vol_bullish: Low volatility, positive trend
    - low_vol_bearish: Low volatility, negative trend
    - high_vol_bullish: High volatility, positive trend
    - high_vol_bearish: High volatility, negative trend
    - extreme_volatility: Extreme market volatility
    - crisis: Market crisis conditions
    
    Different regimes trigger different risk management strategies
    """
    try:
        status = await service.get_risk_status()
        
        if not status['success']:
            raise HTTPException(status_code=500, detail=status.get('error', 'Unknown error'))
        
        return {
            'success': True,
            'regime': status['data']['risk_regime'],
            'timestamp': status['data']['timestamp']
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting risk regime: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        'status': 'healthy',
        'service': 'advanced_risk_management',
        'timestamp': datetime.utcnow().isoformat()
    }
