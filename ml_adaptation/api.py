"""
ML Adaptation REST API

Provides endpoints for:
- Regime detection
- Online parameter learning
- RL strategy selection
- Ensemble management
- Performance prediction
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
import numpy as np

from .regime_detector import (
    RegimeDetector,
    HMMRegimeDetector,
    GMMRegimeDetector,
    RegimeFeatures,
    calculate_regime_features,
    MarketRegime,
)

from .online_learning import (
    OnlineLearner,
    ParameterOptimizer,
    UpdateRule,
)

from .rl_strategy_selector import (
    QLearningSelector,
    DQNSelector,
    StrategyEnvironment,
)

from .ensemble_manager import (
    EnsembleManager,
    EnsembleWeightingMethod,
)

from .performance_predictor import (
    PerformancePredictor,
    PredictionModel,
)

# Initialize global instances (would use dependency injection in production)
hmm_detector = HMMRegimeDetector(n_states=3)
gmm_detector = GMMRegimeDetector(n_components=3)

online_learners: Dict[str, OnlineLearner] = {}
rl_selectors: Dict[str, QLearningSelector] = {}
ensemble_managers: Dict[str, EnsembleManager] = {}
performance_predictor = PerformancePredictor()

ml_router = APIRouter(prefix="/api/ml", tags=["ml"])


# ============================================================================
# Request/Response Models
# ============================================================================

class DetectRegimeRequest(BaseModel):
    """Request for regime detection"""
    prices: List[float]
    volumes: Optional[List[float]] = None
    lookback: int = Field(default=20, ge=5, le=100)


class RegimeResponse(BaseModel):
    """Regime detection response"""
    regime: str
    confidence: float
    probabilities: Dict[str, float]
    volatility: float
    trend_strength: float
    timestamp: str


class AddParameterRequest(BaseModel):
    """Request to add adaptive parameter"""
    strategy_id: str
    parameter_name: str
    initial_value: float
    min_value: float
    max_value: float
    learning_rate: float = 0.01
    update_rule: str = "adam"


class RecordTradeRequest(BaseModel):
    """Request to record trade for online learning"""
    strategy_id: str
    pnl: float
    return_value: float
    duration_minutes: Optional[int] = None


class SelectStrategyRequest(BaseModel):
    """Request for RL strategy selection"""
    selector_id: str
    market_features: Dict[str, float]
    explore: bool = True


class UpdateRLRequest(BaseModel):
    """Request to update RL agent"""
    selector_id: str
    selected_strategy: str
    reward: float
    next_market_features: Dict[str, float]


class CreateEnsembleRequest(BaseModel):
    """Request to create ensemble"""
    ensemble_id: str
    strategy_ids: List[str]
    weighting_method: str = "sharpe"
    min_weight: float = Field(default=0.05, ge=0.0, le=1.0)
    max_weight: float = Field(default=0.5, ge=0.0, le=1.0)


class RecordPerformanceRequest(BaseModel):
    """Request to record strategy performance"""
    ensemble_id: str
    strategy_id: str
    return_value: float


class TrainPredictorRequest(BaseModel):
    """Request to train performance predictor"""
    strategy_id: str
    historical_returns: List[float]


class PredictPerformanceRequest(BaseModel):
    """Request for performance prediction"""
    strategy_id: str
    recent_returns: Optional[List[float]] = None


# ============================================================================
# Regime Detection Endpoints
# ============================================================================

@ml_router.post("/regime/detect", response_model=RegimeResponse)
async def detect_regime(request: DetectRegimeRequest):
    """
    Detect current market regime.
    
    Args:
        request: Price and volume data
        
    Returns:
        Regime detection result
    """
    try:
        prices = np.array(request.prices)
        volumes = np.array(request.volumes) if request.volumes else None
        
        # Calculate features
        features = calculate_regime_features(
            prices=prices,
            volumes=volumes,
            lookback=request.lookback,
        )
        
        # Detect regime using HMM
        detection = hmm_detector.detect(features)
        
        return RegimeResponse(
            regime=detection.regime.value,
            confidence=detection.confidence,
            probabilities={k.value: v for k, v in detection.probabilities.items()},
            volatility=detection.features.volatility,
            trend_strength=detection.features.trend_strength,
            timestamp=detection.timestamp.isoformat(),
        )
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@ml_router.post("/regime/train/hmm")
async def train_hmm_detector(historical_prices: List[List[float]]):
    """Train HMM regime detector with historical data"""
    try:
        # Convert to features
        features_list = []
        for prices in historical_prices:
            prices_array = np.array(prices)
            features = calculate_regime_features(prices_array)
            features_list.append(features)
        
        # Fit HMM
        hmm_detector.fit(features_list)
        
        return {
            "message": "HMM detector trained successfully",
            "n_samples": len(features_list),
        }
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ============================================================================
# Online Learning Endpoints
# ============================================================================

@ml_router.post("/online-learning/add-parameter")
async def add_adaptive_parameter(request: AddParameterRequest):
    """Add an adaptive parameter for a strategy"""
    try:
        # Get or create learner
        if request.strategy_id not in online_learners:
            online_learners[request.strategy_id] = OnlineLearner(request.strategy_id)
        
        learner = online_learners[request.strategy_id]
        
        # Parse update rule
        update_rule = UpdateRule(request.update_rule)
        
        # Add parameter
        learner.add_parameter(
            name=request.parameter_name,
            initial_value=request.initial_value,
            min_value=request.min_value,
            max_value=request.max_value,
            learning_rate=request.learning_rate,
            update_rule=update_rule,
        )
        
        return {
            "message": f"Added parameter {request.parameter_name} to {request.strategy_id}",
            "current_value": request.initial_value,
        }
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@ml_router.post("/online-learning/record-trade")
async def record_trade(request: RecordTradeRequest):
    """Record a trade result for online learning"""
    try:
        if request.strategy_id not in online_learners:
            raise HTTPException(status_code=404, detail=f"Learner not found: {request.strategy_id}")
        
        learner = online_learners[request.strategy_id]
        
        trade_result = {
            "pnl": request.pnl,
            "return": request.return_value,
            "duration": request.duration_minutes,
        }
        
        learner.record_trade(trade_result)
        
        # Get updated parameters
        current_params = learner.get_current_parameters()
        
        return {
            "message": "Trade recorded",
            "trade_count": learner.trade_count,
            "current_parameters": current_params,
        }
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@ml_router.get("/online-learning/{strategy_id}/parameters")
async def get_parameters(strategy_id: str):
    """Get current parameter values for a strategy"""
    if strategy_id not in online_learners:
        raise HTTPException(status_code=404, detail=f"Learner not found: {strategy_id}")
    
    learner = online_learners[strategy_id]
    return {
        "strategy_id": strategy_id,
        "parameters": learner.get_current_parameters(),
        "statistics": learner.get_statistics(),
    }


# ============================================================================
# RL Strategy Selection Endpoints
# ============================================================================

@ml_router.post("/rl/create-selector")
async def create_rl_selector(
    selector_id: str,
    strategy_ids: List[str],
    algorithm: str = Query("qlearning", regex="^(qlearning|dqn)$"),
):
    """Create RL strategy selector"""
    try:
        if algorithm == "qlearning":
            selector = QLearningSelector(
                strategy_ids=strategy_ids,
                state_bins=10,
                learning_rate=0.1,
                epsilon=0.1,
            )
        elif algorithm == "dqn":
            selector = DQNSelector(
                strategy_ids=strategy_ids,
                state_dim=10,
                learning_rate=0.001,
                epsilon=0.1,
            )
        else:
            raise ValueError(f"Unknown algorithm: {algorithm}")
        
        rl_selectors[selector_id] = selector
        
        return {
            "message": f"Created {algorithm} selector: {selector_id}",
            "n_strategies": len(strategy_ids),
            "strategies": strategy_ids,
        }
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@ml_router.post("/rl/select-strategy")
async def select_strategy(request: SelectStrategyRequest):
    """Use RL to select strategy"""
    try:
        if request.selector_id not in rl_selectors:
            raise HTTPException(status_code=404, detail=f"Selector not found: {request.selector_id}")
        
        selector = rl_selectors[request.selector_id]
        
        # Convert features to state
        env = StrategyEnvironment(
            available_strategies=selector.strategy_ids,
            state_dim=10,
            action_dim=len(selector.strategy_ids),
        )
        
        state = env.get_state(request.market_features)
        
        # Select strategy
        selected = selector.select_strategy(state, explore=request.explore)
        
        return {
            "selected_strategy": selected,
            "selector_id": request.selector_id,
            "explore": request.explore,
        }
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@ml_router.post("/rl/update")
async def update_rl_selector(request: UpdateRLRequest):
    """Update RL selector with experience"""
    try:
        if request.selector_id not in rl_selectors:
            raise HTTPException(status_code=404, detail=f"Selector not found: {request.selector_id}")
        
        selector = rl_selectors[request.selector_id]
        
        # Get states
        env = StrategyEnvironment(
            available_strategies=selector.strategy_ids,
            state_dim=10,
            action_dim=len(selector.strategy_ids),
        )
        
        # Current state from previous features (simplified)
        state = np.random.randn(10)
        next_state = env.get_state(request.next_market_features)
        
        # Update
        selector.update(
            state=state,
            action=request.selected_strategy,
            reward=request.reward,
            next_state=next_state,
        )
        
        return {
            "message": "RL selector updated",
            "selector_id": request.selector_id,
            "reward": request.reward,
        }
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@ml_router.get("/rl/{selector_id}/statistics")
async def get_rl_statistics(selector_id: str):
    """Get RL selector statistics"""
    if selector_id not in rl_selectors:
        raise HTTPException(status_code=404, detail=f"Selector not found: {selector_id}")
    
    selector = rl_selectors[selector_id]
    return selector.get_statistics()


# ============================================================================
# Ensemble Management Endpoints
# ============================================================================

@ml_router.post("/ensemble/create")
async def create_ensemble(request: CreateEnsembleRequest):
    """Create strategy ensemble"""
    try:
        # Parse weighting method
        weighting_method = EnsembleWeightingMethod(request.weighting_method)
        
        # Create ensemble
        ensemble = EnsembleManager(
            weighting_method=weighting_method,
            min_weight=request.min_weight,
            max_weight=request.max_weight,
        )
        
        # Add strategies
        for strategy_id in request.strategy_ids:
            ensemble.add_strategy(strategy_id)
        
        ensemble_managers[request.ensemble_id] = ensemble
        
        return {
            "message": f"Created ensemble: {request.ensemble_id}",
            "n_strategies": len(request.strategy_ids),
            "weighting_method": request.weighting_method,
            "initial_weights": ensemble.get_weights(),
        }
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@ml_router.post("/ensemble/record-performance")
async def record_ensemble_performance(request: RecordPerformanceRequest):
    """Record strategy performance in ensemble"""
    try:
        if request.ensemble_id not in ensemble_managers:
            raise HTTPException(status_code=404, detail=f"Ensemble not found: {request.ensemble_id}")
        
        ensemble = ensemble_managers[request.ensemble_id]
        ensemble.record_performance(request.strategy_id, request.return_value)
        
        return {
            "message": "Performance recorded",
            "ensemble_id": request.ensemble_id,
            "strategy_id": request.strategy_id,
            "current_weights": ensemble.get_weights(),
        }
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@ml_router.post("/ensemble/{ensemble_id}/rebalance")
async def rebalance_ensemble(
    ensemble_id: str,
    current_regime: Optional[str] = None,
    regime_confidence: float = 1.0,
):
    """Manually trigger ensemble rebalancing"""
    if ensemble_id not in ensemble_managers:
        raise HTTPException(status_code=404, detail=f"Ensemble not found: {ensemble_id}")
    
    ensemble = ensemble_managers[ensemble_id]
    ensemble.rebalance(current_regime=current_regime, regime_confidence=regime_confidence)
    
    return {
        "message": "Ensemble rebalanced",
        "ensemble_id": ensemble_id,
        "new_weights": ensemble.get_weights(),
    }


@ml_router.get("/ensemble/{ensemble_id}/statistics")
async def get_ensemble_statistics(ensemble_id: str):
    """Get ensemble statistics"""
    if ensemble_id not in ensemble_managers:
        raise HTTPException(status_code=404, detail=f"Ensemble not found: {ensemble_id}")
    
    ensemble = ensemble_managers[ensemble_id]
    return ensemble.get_statistics()


# ============================================================================
# Performance Prediction Endpoints
# ============================================================================

@ml_router.post("/predict/train")
async def train_performance_predictor(request: TrainPredictorRequest):
    """Train performance predictor for a strategy"""
    try:
        returns = np.array(request.historical_returns)
        performance_predictor.train(request.strategy_id, returns)
        
        return {
            "message": f"Predictor trained for {request.strategy_id}",
            "n_samples": len(returns),
        }
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@ml_router.post("/predict/performance")
async def predict_performance(request: PredictPerformanceRequest):
    """Predict strategy performance"""
    try:
        recent_returns = np.array(request.recent_returns) if request.recent_returns else None
        
        prediction = performance_predictor.predict(
            strategy_id=request.strategy_id,
            recent_returns=recent_returns,
        )
        
        return prediction.to_dict()
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@ml_router.post("/predict/update-history")
async def update_prediction_history(strategy_id: str, new_return: float):
    """Update strategy history for predictor"""
    performance_predictor.update_history(strategy_id, new_return)
    
    return {
        "message": "History updated",
        "strategy_id": strategy_id,
    }


@ml_router.get("/predict/{strategy_id}/accuracy")
async def get_prediction_accuracy(strategy_id: str):
    """Get prediction accuracy metrics"""
    accuracy = performance_predictor.get_prediction_accuracy(strategy_id)
    
    return {
        "strategy_id": strategy_id,
        "accuracy_metrics": accuracy,
    }


# ============================================================================
# General Endpoints
# ============================================================================

@ml_router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "ml_adaptation",
        "timestamp": datetime.utcnow().isoformat(),
        "components": {
            "regime_detectors": 2,
            "online_learners": len(online_learners),
            "rl_selectors": len(rl_selectors),
            "ensembles": len(ensemble_managers),
            "performance_predictor": "active",
        }
    }


@ml_router.get("/summary")
async def get_ml_summary():
    """Get summary of all ML components"""
    return {
        "online_learners": list(online_learners.keys()),
        "rl_selectors": list(rl_selectors.keys()),
        "ensembles": list(ensemble_managers.keys()),
        "predictor_strategies": list(performance_predictor.strategy_histories.keys()),
    }
