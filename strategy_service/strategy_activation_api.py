"""
API Endpoints for Enhanced Strategy Activation System

Provides REST API access to:
- Current activation status
- Strategy evaluation results  
- Regime detection
- Performance in similar conditions
- Manual activation controls
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from typing import List, Dict, Optional
from datetime import datetime
from enum import Enum
import structlog

from enhanced_strategy_activation import (
    EnhancedStrategyActivationSystem,
    MarketRegime,
    StrategyType,
    ActivationDecision
)

logger = structlog.get_logger()

router = APIRouter(prefix="/api/strategy-activation", tags=["Strategy Activation"])


# Request/Response Models

class StrategyEvaluationRequest(BaseModel):
    """Request to evaluate specific strategies"""
    strategy_ids: Optional[List[str]] = Field(None, description="Specific strategies to evaluate. If None, evaluates all.")
    force_check: bool = Field(False, description="Force check even if within cooldown period")


class StrategyPerformanceResponse(BaseModel):
    """Strategy performance metrics"""
    strategy_id: str
    condition_similarity: float
    historical_sharpe: float
    historical_return: float
    historical_win_rate: float
    historical_max_drawdown: float
    trade_count: int
    avg_trade_duration: float
    profit_factor: float
    consistency_score: float


class ActivationDecisionResponse(BaseModel):
    """Strategy activation decision"""
    strategy_id: str
    strategy_name: str
    action: str
    current_status: str
    new_status: str
    confidence: float
    reasoning: List[str]
    expected_sharpe: float
    expected_return: float
    risk_score: float
    performance: StrategyPerformanceResponse


class MarketConditionsResponse(BaseModel):
    """Current market conditions"""
    timestamp: str
    regime: str
    volatility: float
    trend_strength: float
    volume_trend: float
    sentiment_score: float
    fear_greed_index: int
    correlation_to_btc: float
    liquidity_score: float
    macro_score: float


class RegimeChangeResponse(BaseModel):
    """Regime change event"""
    timestamp: str
    old_regime: str
    new_regime: str
    confidence: float
    trigger_factors: List[str]
    affected_strategies: List[str]


class ActivationStatusResponse(BaseModel):
    """Current activation system status"""
    current_regime: str
    regime_confidence: float
    active_strategies: List[str]
    active_count: int
    max_active: int
    last_regime_check: Optional[str]
    last_activation_check: Optional[str]
    market_conditions: MarketConditionsResponse


class ActivationResultResponse(BaseModel):
    """Result of activation check"""
    timestamp: str
    regime: str
    activated: List[ActivationDecisionResponse]
    deactivated: List[ActivationDecisionResponse]
    kept: List[ActivationDecisionResponse]
    total_active: int


class RegimeSuitabilityResponse(BaseModel):
    """Strategy type suitability for regimes"""
    strategy_type: str
    suitability_scores: Dict[str, float]


# Global activation system instance (initialized on startup)
activation_system: Optional[EnhancedStrategyActivationSystem] = None


def set_activation_system(system: EnhancedStrategyActivationSystem):
    """Set the global activation system instance"""
    global activation_system
    activation_system = system


# API Endpoints

@router.get("/status", response_model=ActivationStatusResponse)
async def get_activation_status():
    """
    Get current activation system status
    
    Returns:
        - Current market regime
        - Active strategies
        - Market conditions
        - Last check times
    """
    try:
        if not activation_system:
            raise HTTPException(status_code=503, detail="Activation system not initialized")
        
        conditions = activation_system.current_conditions
        
        return ActivationStatusResponse(
            current_regime=activation_system.current_regime.value if activation_system.current_regime else "unknown",
            regime_confidence=0.8,  # TODO: Store confidence
            active_strategies=list(activation_system.active_strategies),
            active_count=len(activation_system.active_strategies),
            max_active=activation_system.max_active_strategies,
            last_regime_check=activation_system._last_regime_check.isoformat() if activation_system._last_regime_check else None,
            last_activation_check=activation_system._last_activation_check.isoformat() if activation_system._last_activation_check else None,
            market_conditions=MarketConditionsResponse(
                timestamp=conditions.timestamp.isoformat() if conditions else datetime.utcnow().isoformat(),
                regime=activation_system.current_regime.value if activation_system.current_regime else "unknown",
                volatility=conditions.volatility if conditions else 0.0,
                trend_strength=conditions.trend_strength if conditions else 0.0,
                volume_trend=conditions.volume_trend if conditions else 0.0,
                sentiment_score=conditions.sentiment_score if conditions else 0.0,
                fear_greed_index=conditions.fear_greed_index if conditions else 50,
                correlation_to_btc=conditions.correlation_to_btc if conditions else 0.8,
                liquidity_score=conditions.liquidity_score if conditions else 0.7,
                macro_score=conditions.macro_score if conditions else 0.0
            ) if conditions else None
        )
        
    except Exception as e:
        logger.error(f"Error getting activation status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/regime", response_model=Dict[str, str])
async def get_current_regime():
    """
    Get current market regime
    
    Returns:
        - Regime classification
        - Confidence score
    """
    try:
        if not activation_system:
            raise HTTPException(status_code=503, detail="Activation system not initialized")
        
        regime, confidence = await activation_system.detect_market_regime()
        
        return {
            "regime": regime.value,
            "confidence": f"{confidence:.2f}",
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error detecting regime: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/check", response_model=ActivationResultResponse)
async def check_activations(
    request: StrategyEvaluationRequest = StrategyEvaluationRequest(),
    background_tasks: BackgroundTasks = None
):
    """
    Check and update strategy activations
    
    Evaluates all strategies for current market conditions and
    activates/deactivates based on expected performance.
    
    Args:
        force_check: Force check even if within cooldown period
    
    Returns:
        - Strategies activated
        - Strategies deactivated
        - Strategies kept
    """
    try:
        if not activation_system:
            raise HTTPException(status_code=503, detail="Activation system not initialized")
        
        # Force check if requested
        if request.force_check:
            activation_system._last_activation_check = None
        
        # Perform activation check
        results = await activation_system.check_and_update_activations()
        
        # Convert to response format
        def to_response(decision: ActivationDecision) -> ActivationDecisionResponse:
            return ActivationDecisionResponse(
                strategy_id=decision.strategy_id,
                strategy_name=decision.strategy_name,
                action=decision.action,
                current_status=decision.current_status,
                new_status=decision.new_status,
                confidence=decision.confidence,
                reasoning=decision.reasoning,
                expected_sharpe=decision.expected_sharpe,
                expected_return=decision.expected_return,
                risk_score=decision.risk_score,
                performance=StrategyPerformanceResponse(
                    strategy_id=decision.performance_in_current_regime.strategy_id,
                    condition_similarity=decision.performance_in_current_regime.condition_similarity,
                    historical_sharpe=decision.performance_in_current_regime.historical_sharpe,
                    historical_return=decision.performance_in_current_regime.historical_return,
                    historical_win_rate=decision.performance_in_current_regime.historical_win_rate,
                    historical_max_drawdown=decision.performance_in_current_regime.historical_max_drawdown,
                    trade_count=decision.performance_in_current_regime.trade_count,
                    avg_trade_duration=decision.performance_in_current_regime.avg_trade_duration,
                    profit_factor=decision.performance_in_current_regime.profit_factor,
                    consistency_score=decision.performance_in_current_regime.consistency_score
                )
            )
        
        return ActivationResultResponse(
            timestamp=datetime.utcnow().isoformat(),
            regime=activation_system.current_regime.value if activation_system.current_regime else "unknown",
            activated=[to_response(d) for d in results['activated']],
            deactivated=[to_response(d) for d in results['deactivated']],
            kept=[to_response(d) for d in results['kept']],
            total_active=len(activation_system.active_strategies)
        )
        
    except Exception as e:
        logger.error(f"Error checking activations: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/candidates", response_model=List[ActivationDecisionResponse])
async def get_activation_candidates():
    """
    Get all strategy candidates with their evaluation scores
    
    Returns evaluation of all strategies for current conditions
    without actually changing activations.
    """
    try:
        if not activation_system:
            raise HTTPException(status_code=503, detail="Activation system not initialized")
        
        # Get all strategies
        all_strategies = await activation_system._get_all_strategies()
        
        # Evaluate each
        candidates = []
        for strategy in all_strategies:
            decision = await activation_system._evaluate_strategy_activation(strategy)
            candidates.append(ActivationDecisionResponse(
                strategy_id=decision.strategy_id,
                strategy_name=decision.strategy_name,
                action=decision.action,
                current_status=decision.current_status,
                new_status=decision.new_status,
                confidence=decision.confidence,
                reasoning=decision.reasoning,
                expected_sharpe=decision.expected_sharpe,
                expected_return=decision.expected_return,
                risk_score=decision.risk_score,
                performance=StrategyPerformanceResponse(
                    strategy_id=decision.performance_in_current_regime.strategy_id,
                    condition_similarity=decision.performance_in_current_regime.condition_similarity,
                    historical_sharpe=decision.performance_in_current_regime.historical_sharpe,
                    historical_return=decision.performance_in_current_regime.historical_return,
                    historical_win_rate=decision.performance_in_current_regime.historical_win_rate,
                    historical_max_drawdown=decision.performance_in_current_regime.historical_max_drawdown,
                    trade_count=decision.performance_in_current_regime.trade_count,
                    avg_trade_duration=decision.performance_in_current_regime.avg_trade_duration,
                    profit_factor=decision.performance_in_current_regime.profit_factor,
                    consistency_score=decision.performance_in_current_regime.consistency_score
                )
            ))
        
        # Sort by expected Sharpe
        candidates.sort(key=lambda x: x.expected_sharpe, reverse=True)
        
        return candidates
        
    except Exception as e:
        logger.error(f"Error getting candidates: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/performance/{strategy_id}", response_model=StrategyPerformanceResponse)
async def get_strategy_performance(strategy_id: str):
    """
    Get strategy performance in current market conditions
    
    Evaluates how the strategy would perform based on similar
    historical conditions.
    """
    try:
        if not activation_system:
            raise HTTPException(status_code=503, detail="Activation system not initialized")
        
        # Ensure conditions are current
        if not activation_system.current_conditions:
            await activation_system.detect_market_regime()
        
        # Find similar conditions
        similar = activation_system._find_similar_conditions(
            activation_system.current_conditions,
            top_k=10
        )
        
        # Evaluate performance
        performance = await activation_system._evaluate_strategy_in_conditions(
            strategy_id,
            similar
        )
        
        return StrategyPerformanceResponse(
            strategy_id=performance.strategy_id,
            condition_similarity=performance.condition_similarity,
            historical_sharpe=performance.historical_sharpe,
            historical_return=performance.historical_return,
            historical_win_rate=performance.historical_win_rate,
            historical_max_drawdown=performance.historical_max_drawdown,
            trade_count=performance.trade_count,
            avg_trade_duration=performance.avg_trade_duration,
            profit_factor=performance.profit_factor,
            consistency_score=performance.consistency_score
        )
        
    except Exception as e:
        logger.error(f"Error getting strategy performance: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/regime-suitability", response_model=List[RegimeSuitabilityResponse])
async def get_regime_suitability():
    """
    Get strategy type suitability matrix for all regimes
    
    Returns how suitable each strategy type is for each market regime.
    """
    try:
        if not activation_system:
            raise HTTPException(status_code=503, detail="Activation system not initialized")
        
        results = []
        for strategy_type in StrategyType:
            suitability = {}
            for regime in MarketRegime:
                score = activation_system._check_regime_suitability(strategy_type, regime)
                suitability[regime.value] = score
            
            results.append(RegimeSuitabilityResponse(
                strategy_type=strategy_type.value,
                suitability_scores=suitability
            ))
        
        return results
        
    except Exception as e:
        logger.error(f"Error getting regime suitability: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/market-conditions", response_model=MarketConditionsResponse)
async def get_market_conditions():
    """
    Get current market conditions
    
    Returns detailed snapshot of current market state including
    volatility, trend, sentiment, and other factors.
    """
    try:
        if not activation_system:
            raise HTTPException(status_code=503, detail="Activation system not initialized")
        
        # Get fresh conditions
        conditions = await activation_system._collect_current_conditions()
        
        return MarketConditionsResponse(
            timestamp=conditions.timestamp.isoformat(),
            regime=conditions.regime.value,
            volatility=conditions.volatility,
            trend_strength=conditions.trend_strength,
            volume_trend=conditions.volume_trend,
            sentiment_score=conditions.sentiment_score,
            fear_greed_index=conditions.fear_greed_index,
            correlation_to_btc=conditions.correlation_to_btc,
            liquidity_score=conditions.liquidity_score,
            macro_score=conditions.macro_score
        )
        
    except Exception as e:
        logger.error(f"Error getting market conditions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/activate/{strategy_id}")
async def manually_activate_strategy(strategy_id: str):
    """
    Manually activate a specific strategy
    
    Bypasses automatic evaluation and forces activation.
    Use with caution.
    """
    try:
        if not activation_system:
            raise HTTPException(status_code=503, detail="Activation system not initialized")
        
        # Check if we're at max capacity
        if len(activation_system.active_strategies) >= activation_system.max_active_strategies:
            raise HTTPException(
                status_code=400,
                detail=f"Maximum active strategies ({activation_system.max_active_strategies}) reached"
            )
        
        # Update strategy status in database
        container = activation_system.database.db.get_container_client('strategies')
        strategy = await container.read_item(item=strategy_id, partition_key=strategy_id)
        
        strategy['status'] = 'active'
        strategy['last_activated'] = datetime.utcnow().isoformat()
        strategy['activation_reason'] = 'Manual activation via API'
        
        await container.upsert_item(strategy)
        
        activation_system.active_strategies.add(strategy_id)
        
        logger.info(f"Strategy manually activated: {strategy_id}")
        
        return {
            "success": True,
            "strategy_id": strategy_id,
            "status": "active",
            "message": "Strategy manually activated"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error manually activating strategy: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/deactivate/{strategy_id}")
async def manually_deactivate_strategy(strategy_id: str):
    """
    Manually deactivate a specific strategy
    
    Bypasses automatic evaluation and forces deactivation.
    """
    try:
        if not activation_system:
            raise HTTPException(status_code=503, detail="Activation system not initialized")
        
        # Update strategy status in database
        container = activation_system.database.db.get_container_client('strategies')
        strategy = await container.read_item(item=strategy_id, partition_key=strategy_id)
        
        strategy['status'] = 'inactive'
        strategy['last_deactivated'] = datetime.utcnow().isoformat()
        strategy['deactivation_reason'] = 'Manual deactivation via API'
        
        await container.upsert_item(strategy)
        
        activation_system.active_strategies.discard(strategy_id)
        
        logger.info(f"Strategy manually deactivated: {strategy_id}")
        
        return {
            "success": True,
            "strategy_id": strategy_id,
            "status": "inactive",
            "message": "Strategy manually deactivated"
        }
        
    except Exception as e:
        logger.error(f"Error manually deactivating strategy: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        if not activation_system:
            return {
                "status": "unhealthy",
                "message": "Activation system not initialized"
            }
        
        return {
            "status": "healthy",
            "regime": activation_system.current_regime.value if activation_system.current_regime else None,
            "active_strategies": len(activation_system.active_strategies),
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Health check failed: {e}", exc_info=True)
        return {
            "status": "unhealthy",
            "error": str(e)
        }
