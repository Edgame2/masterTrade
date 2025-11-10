"""
FastAPI endpoints for Strategy Service with Daily Review functionality

This module provides REST API endpoints for strategy management including
manual strategy reviews and daily review scheduling.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks, Response, status, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import structlog

# Import the enhanced strategy activation API
from strategy_activation_api import router as activation_router, set_activation_system

logger = structlog.get_logger()


def _safe_optional_float(value) -> Optional[float]:
    """Convert value to float when possible, otherwise return None."""
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _safe_float(value, default: float = 0.0) -> float:
    """Convert value to float, returning a default on failure."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)

# Request/Response Models
class StrategyReviewRequest(BaseModel):
    strategy_id: Optional[str] = None
    force_review: bool = False

class StrategyReviewResponse(BaseModel):
    strategy_id: str
    performance_grade: str
    decision: str
    confidence_score: float
    strengths: List[str]
    weaknesses: List[str]
    improvement_suggestions: List[str]
    review_timestamp: datetime

class DailyReviewSummaryResponse(BaseModel):
    review_date: str
    total_strategies_reviewed: int
    grade_distribution: Dict[str, int]
    decision_distribution: Dict[str, int]
    avg_confidence: float
    top_performers: List[str]
    strategies_needing_attention: List[str]


class PricePredictionResponse(BaseModel):
    symbol: str
    predicted_price: float
    predicted_change_pct: float
    current_price: float
    prediction_timestamp: datetime
    confidence_score: float
    confidence_lower: Optional[float] = None
    confidence_upper: Optional[float] = None
    model_version: Optional[str] = None
    horizon: str
    generated_at: Optional[datetime] = None


class SupportedPredictionSymbolsResponse(BaseModel):
    supported_symbols: List[str]

def create_strategy_api(strategy_service) -> FastAPI:
    """Create FastAPI app with strategy management endpoints"""
    
    app = FastAPI(
        title="MasterTrade Strategy Service API",
        description="Advanced AI/ML Strategy Management with Daily Review System",
        version="2.0.0"
    )
    
    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    @app.get("/health")
    async def health_check():
        """Health check endpoint"""
        return {
            "status": "healthy",
            "service": "strategy_service",
            "timestamp": datetime.now(timezone.utc),
            "daily_reviewer_active": strategy_service.daily_reviewer is not None
        }

    @app.get(
        "/api/v1/predictions/{symbol}",
        response_model=PricePredictionResponse,
        tags=["price-predictions"],
    )
    async def get_price_prediction(
        symbol: str,
        force_refresh: bool = Query(False, description="Force regeneration of prediction"),
    ) -> PricePredictionResponse:
        """Get the latest 1-hour ahead price prediction for a symbol."""
        service = getattr(strategy_service, "price_prediction_service", None)
        if service is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Price prediction service unavailable",
            )

        prediction = await service.get_prediction(symbol, force_refresh=force_refresh)
        if not prediction:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Prediction not available",
            )

        return PricePredictionResponse(
            symbol=prediction.get("symbol", symbol.upper()),
            predicted_price=_safe_float(
                prediction.get("predicted_price"),
                default=prediction.get("current_price", 0.0)
            ),
            predicted_change_pct=_safe_float(
                prediction.get("predicted_change_pct", 0.0),
                default=0.0
            ),
            current_price=_safe_float(prediction.get("current_price", 0.0), default=0.0),
            prediction_timestamp=prediction.get(
                "prediction_timestamp",
                prediction.get("generated_at", datetime.now(timezone.utc)),
            ),
            confidence_score=_safe_float(
                prediction.get("confidence_score", 0.0),
                default=0.0
            ),
            confidence_lower=_safe_optional_float(prediction.get("confidence_lower")),
            confidence_upper=_safe_optional_float(prediction.get("confidence_upper")),
            model_version=prediction.get("model_version"),
            horizon=str(prediction.get("horizon", "1h")),
            generated_at=prediction.get("generated_at"),
        )

    @app.get(
        "/api/v1/predictions",
        response_model=SupportedPredictionSymbolsResponse,
        tags=["price-predictions"],
    )
    async def list_supported_prediction_symbols() -> SupportedPredictionSymbolsResponse:
        """Return the set of symbols that currently support predictions."""
        service = getattr(strategy_service, "price_prediction_service", None)
        if service is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Price prediction service unavailable",
            )

        symbols = await service.get_supported_symbols()
        return SupportedPredictionSymbolsResponse(supported_symbols=symbols)
    
    @app.post("/api/v1/strategy/review/manual", response_model=Dict[str, StrategyReviewResponse])
    async def trigger_manual_review(
        request: StrategyReviewRequest,
        background_tasks: BackgroundTasks
    ):
        """
        Manually trigger strategy review
        
        - **strategy_id**: Optional specific strategy ID to review (if None, reviews all)
        - **force_review**: Force review even if recently reviewed
        """
        try:
            if not strategy_service.daily_reviewer:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Daily reviewer not initialized"
                )
            
            # Run review in background
            review_results = await strategy_service.run_manual_strategy_review(
                strategy_id=request.strategy_id
            )
            
            # Convert to response format
            response = {}
            for strategy_id, review in review_results.items():
                response[strategy_id] = StrategyReviewResponse(
                    strategy_id=review.strategy_id,
                    performance_grade=review.performance_grade.value,
                    decision=review.decision.value,
                    confidence_score=review.confidence_score,
                    strengths=review.strengths,
                    weaknesses=review.weaknesses,
                    improvement_suggestions=review.improvement_suggestions,
                    review_timestamp=review.review_timestamp
                )
            
            return response
            
        except Exception as e:
            logger.error(f"Error in manual strategy review: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to run strategy review: {str(e)}"
            )
    
    @app.get("/api/v1/strategy/review/history/{strategy_id}")
    async def get_strategy_review_history(
        strategy_id: str,
        limit: int = Query(default=10, ge=1, le=100)
    ):
        """Get review history for a specific strategy"""
        try:
            history = await strategy_service.database.get_strategy_review_history(
                strategy_id=strategy_id,
                limit=limit
            )
            
            if not history:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"No review history found for strategy {strategy_id}"
                )
            
            return {
                "strategy_id": strategy_id,
                "review_count": len(history),
                "reviews": history
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error getting review history: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to get review history: {str(e)}"
            )
    
    @app.get("/api/v1/strategy/review/summary/daily", response_model=DailyReviewSummaryResponse)
    async def get_daily_review_summary(
        date: Optional[str] = Query(default=None, description="Date in YYYY-MM-DD format, defaults to today")
    ):
        """Get daily review summary for a specific date"""
        try:
            if date is None:
                date = datetime.now(timezone.utc).date().isoformat()
            
            summary = await strategy_service.database.get_daily_review_summary(date)
            
            if not summary:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"No review summary found for date {date}"
                )
            
            return DailyReviewSummaryResponse(**summary)
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error getting daily summary: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to get daily summary: {str(e)}"
            )
    
    @app.get("/api/v1/strategy/performance/dashboard")
    async def get_strategy_performance_dashboard():
        """Get comprehensive strategy performance dashboard data"""
        try:
            # Get active strategies
            active_strategies = await strategy_service.database.get_active_strategies()
            
            dashboard_data = {
                "total_active_strategies": len(active_strategies),
                "performance_overview": {},
                "top_performers": [],
                "underperformers": [],
                "recent_reviews": [],
                "market_regime": getattr(strategy_service.daily_reviewer, 'current_market_regime', 'unknown'),
                "last_update": datetime.now(timezone.utc)
            }
            
            # Get performance metrics for each strategy
            performance_data = []
            for strategy in active_strategies[:50]:  # Limit to 50 for performance
                try:
                    metrics = await strategy_service.daily_reviewer._calculate_performance_metrics(
                        strategy['id']
                    )
                    if metrics:
                        performance_data.append({
                            "strategy_id": strategy['id'],
                            "strategy_name": strategy.get('name', ''),
                            "sharpe_ratio": metrics.sharpe_ratio,
                            "total_return": metrics.total_return,
                            "max_drawdown": metrics.max_drawdown,
                            "win_rate": metrics.win_rate,
                            "total_trades": metrics.total_trades
                        })
                except Exception as e:
                    logger.warning(f"Could not get metrics for strategy {strategy['id']}: {e}")
                    continue
            
            # Sort and categorize
            performance_data.sort(key=lambda x: x['sharpe_ratio'], reverse=True)
            
            dashboard_data["top_performers"] = performance_data[:10]
            dashboard_data["underperformers"] = [p for p in performance_data if p['sharpe_ratio'] < 0][-10:]
            
            # Performance overview
            if performance_data:
                dashboard_data["performance_overview"] = {
                    "avg_sharpe_ratio": sum(p['sharpe_ratio'] for p in performance_data) / len(performance_data),
                    "avg_return": sum(p['total_return'] for p in performance_data) / len(performance_data),
                    "strategies_profitable": len([p for p in performance_data if p['total_return'] > 0]),
                    "strategies_with_positive_sharpe": len([p for p in performance_data if p['sharpe_ratio'] > 0])
                }
            
            # Get recent reviews
            recent_reviews = await strategy_service.database.get_recent_strategy_reviews(limit=20)
            dashboard_data["recent_reviews"] = recent_reviews
            
            return dashboard_data
            
        except Exception as e:
            logger.error(f"Error generating dashboard: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to generate dashboard: {str(e)}"
            )
    
    @app.post("/api/v1/strategy/{strategy_id}/pause")
    async def pause_strategy(strategy_id: str):
        """Pause a specific strategy"""
        try:
            success = await strategy_service.database.update_strategy_status(
                strategy_id, 'paused'
            )
            
            if not success:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Strategy {strategy_id} not found"
                )
            
            return {
                "strategy_id": strategy_id,
                "status": "paused",
                "timestamp": datetime.now(timezone.utc)
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error pausing strategy: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to pause strategy: {str(e)}"
            )
    
    @app.post("/api/v1/strategy/{strategy_id}/resume")
    async def resume_strategy(strategy_id: str):
        """Resume a paused strategy"""
        try:
            success = await strategy_service.database.update_strategy_status(
                strategy_id, 'active'
            )
            
            if not success:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Strategy {strategy_id} not found"
                )
            
            return {
                "strategy_id": strategy_id,
                "status": "active",
                "timestamp": datetime.now(timezone.utc)
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error resuming strategy: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to resume strategy: {str(e)}"
            )
    
    @app.get("/api/v1/strategy/review/schedule")
    async def get_review_schedule():
        """Get the current review schedule configuration"""
        return {
            "daily_review_time": "02:00 UTC",
            "review_enabled": strategy_service.daily_reviewer is not None,
            "lookback_days": getattr(strategy_service.daily_reviewer, 'review_lookback_days', 30),
            "min_trades_for_review": getattr(strategy_service.daily_reviewer, 'min_trades_for_review', 10),
            "next_scheduled_review": "Daily at 02:00 UTC"
        }
    
    # Strategy Activation Management Endpoints
    
    @app.get("/api/v1/strategy/activation/status")
    async def get_activation_status():
        """Get current strategy activation status and statistics"""
        try:
            if not strategy_service.activation_manager:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Strategy activation manager not initialized"
                )
            
            status_info = await strategy_service.activation_manager.get_activation_status()
            return status_info
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error getting activation status: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to get activation status: {str(e)}"
            )
    
    @app.post("/api/v1/strategy/activation/check")
    async def trigger_activation_check(background_tasks: BackgroundTasks):
        """Manually trigger strategy activation check"""
        try:
            if not strategy_service.activation_manager:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Strategy activation manager not initialized"
                )
            
            # Run activation check in background
            background_tasks.add_task(
                strategy_service.activation_manager.check_and_update_active_strategies
            )
            
            return {
                "message": "Strategy activation check triggered",
                "timestamp": datetime.now(timezone.utc)
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error triggering activation check: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to trigger activation check: {str(e)}"
            )
    
    @app.get("/api/v1/strategy/activation/max-active")
    async def get_max_active_strategies():
        """Get current MAX_ACTIVE_STRATEGIES setting"""
        try:
            if not strategy_service.activation_manager:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Strategy activation manager not initialized"
                )
            
            return {
                "max_active_strategies": strategy_service.activation_manager.max_active_strategies,
                "source": "database_setting"
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error getting max active strategies: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to get max active strategies: {str(e)}"
            )
    
    @app.put("/api/v1/strategy/activation/max-active")
    async def update_max_active_strategies(max_active: int):
        """Update MAX_ACTIVE_STRATEGIES setting"""
        try:
            if not strategy_service.activation_manager:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Strategy activation manager not initialized"
                )
            
            if max_active < 1:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="MAX_ACTIVE_STRATEGIES must be at least 1"
                )
            
            success = await strategy_service.activation_manager.update_max_active_strategies(max_active)
            
            if not success:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to update MAX_ACTIVE_STRATEGIES"
                )
            
            return {
                "message": "MAX_ACTIVE_STRATEGIES updated successfully",
                "new_value": max_active,
                "timestamp": datetime.now(timezone.utc)
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error updating max active strategies: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to update max active strategies: {str(e)}"
            )
    
    @app.get("/api/v1/strategy/activation/log")
    async def get_activation_log(limit: int = Query(default=20, ge=1, le=100)):
        """Get strategy activation change log"""
        try:
            container = strategy_service.database.db.get_container_client('strategy_activation_log')
            
            query = """
            SELECT * FROM c 
            ORDER BY c.timestamp DESC 
            OFFSET 0 LIMIT @limit
            """
            
            activation_logs = []
            async for item in container.query_items(
                query=query,
                parameters=[{"name": "@limit", "value": limit}],
                enable_cross_partition_query=True
            ):
                activation_logs.append(item)
            
            return {
                "activation_logs": activation_logs,
                "total_returned": len(activation_logs)
            }
            
        except Exception as e:
            logger.error(f"Error getting activation log: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to get activation log: {str(e)}"
            )

    # Crypto Selection Management Endpoints
    
    @app.get("/api/v1/crypto/selections/current")
    async def get_current_crypto_selections():
        """Get current day's cryptocurrency selections"""
        try:
            if not strategy_service.crypto_selection_engine:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Crypto selection engine not initialized"
                )
            
            selections = await strategy_service.crypto_selection_engine.get_current_selections()
            
            if not selections:
                return {
                    "message": "No selections found for today",
                    "selection_date": datetime.now(timezone.utc).date().isoformat(),
                    "selected_cryptos": []
                }
            
            return selections
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error getting current crypto selections: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to get current crypto selections: {str(e)}"
            )
    
    @app.get("/api/v1/crypto/selections/history")
    async def get_crypto_selection_history(days_back: int = Query(default=7, ge=1, le=30)):
        """Get historical cryptocurrency selections"""
        try:
            if not strategy_service.crypto_selection_engine:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Crypto selection engine not initialized"
                )
            
            selections = await strategy_service.crypto_selection_engine.get_selection_history(days_back)
            
            return {
                "selection_history": selections,
                "days_back": days_back,
                "total_selection_days": len(selections)
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error getting crypto selection history: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to get crypto selection history: {str(e)}"
            )
    
    @app.post("/api/v1/crypto/selections/run")
    async def trigger_crypto_selection(background_tasks: BackgroundTasks):
        """Manually trigger cryptocurrency selection process"""
        try:
            if not strategy_service.crypto_selection_engine:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Crypto selection engine not initialized"
                )
            
            # Run selection in background
            background_tasks.add_task(
                strategy_service.crypto_selection_engine.run_daily_selection
            )
            
            return {
                "message": "Cryptocurrency selection process triggered",
                "timestamp": datetime.now(timezone.utc),
                "status": "running"
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error triggering crypto selection: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to trigger crypto selection: {str(e)}"
            )
    
    @app.get("/api/v1/crypto/selections/top-performers")
    async def get_top_performing_cryptos(limit: int = Query(default=10, ge=1, le=20)):
        """Get top performing cryptocurrencies from latest selection"""
        try:
            if not strategy_service.crypto_selection_engine:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Crypto selection engine not initialized"
                )
            
            current_selections = await strategy_service.crypto_selection_engine.get_current_selections()
            
            if not current_selections or 'selected_cryptos' not in current_selections:
                return {
                    "top_performers": [],
                    "message": "No current selections available"
                }
            
            # Sort by overall score and return top N
            sorted_cryptos = sorted(
                current_selections['selected_cryptos'], 
                key=lambda x: x['overall_score'], 
                reverse=True
            )
            
            top_performers = sorted_cryptos[:limit]
            
            return {
                "top_performers": top_performers,
                "selection_date": current_selections.get('selection_date'),
                "total_available": len(current_selections['selected_cryptos'])
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error getting top performing cryptos: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to get top performing cryptos: {str(e)}"
            )
    
    @app.get("/api/v1/crypto/selections/analysis/{symbol}")
    async def get_crypto_selection_analysis(symbol: str):
        """Get detailed analysis for a specific cryptocurrency selection"""
        try:
            if not strategy_service.crypto_selection_engine:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Crypto selection engine not initialized"
                )
            
            current_selections = await strategy_service.crypto_selection_engine.get_current_selections()
            
            if not current_selections or 'selected_cryptos' not in current_selections:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="No current selections available"
                )
            
            # Find the specific crypto
            crypto_analysis = None
            for crypto in current_selections['selected_cryptos']:
                if crypto['symbol'] == symbol.upper():
                    crypto_analysis = crypto
                    break
            
            if not crypto_analysis:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Cryptocurrency {symbol} not found in current selections"
                )
            
            return {
                "symbol": symbol.upper(),
                "analysis": crypto_analysis,
                "selection_date": current_selections.get('selection_date'),
                "selection_criteria": current_selections.get('selection_criteria', {})
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error getting crypto analysis for {symbol}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to get crypto analysis: {str(e)}"
            )

    @app.get("/api/v1/metrics")
    async def get_metrics():
        """Get Prometheus metrics"""
        from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
        
        return Response(
            content=generate_latest(),
            media_type=CONTENT_TYPE_LATEST
        )
    
    # Include enhanced strategy activation router
    if hasattr(strategy_service, 'enhanced_activation_system') and strategy_service.enhanced_activation_system:
        set_activation_system(strategy_service.enhanced_activation_system)
        app.include_router(activation_router)
        logger.info("Enhanced strategy activation API registered")
    
    return app