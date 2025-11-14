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
import sys
import os

# Import Redis caching decorators
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from shared.cache_decorators import cached
from shared.prometheus_metrics import create_instrumentator

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


# Cache key functions for Redis caching
def _prediction_cache_key(symbol: str, force_refresh: bool) -> str:
    """Generate cache key for price predictions"""
    return f"prediction:{symbol}:{force_refresh}"


def _review_history_cache_key(strategy_id: str, limit: int) -> str:
    """Generate cache key for review history"""
    return f"review_history:{strategy_id}:{limit}"


def _dashboard_cache_key() -> str:
    """Generate cache key for performance dashboard"""
    return "dashboard:performance"


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
    
    # Add Prometheus instrumentation
    instrumentator = create_instrumentator("strategy_service", "2.0.0")
    instrumentator.instrument(app).expose(app)
    
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
    
    @app.get("/strategies")
    async def list_strategies():
        """List all strategies"""
        try:
            db = strategy_service.db
            if not db:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Database not available"
                )
            
            strategies = await db.get_all_strategies()
            return {
                "strategies": strategies,
                "total": len(strategies),
                "timestamp": datetime.now(timezone.utc)
            }
        except Exception as e:
            logger.error(f"Error listing strategies: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to retrieve strategies: {str(e)}"
            )

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
        """Get review history for a specific strategy (Cached: 120s TTL)"""
        try:
            # Use cached method for better performance
            history = await strategy_service.get_cached_review_history(
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
    
    @app.get("/api/v1/cache/stats")
    async def get_cache_stats():
        """Get Redis cache statistics"""
        try:
            stats = {
                'service_stats': {
                    'cache_hits': strategy_service.cache_hits,
                    'cache_misses': strategy_service.cache_misses,
                    'hit_rate': strategy_service.cache_hits / (strategy_service.cache_hits + strategy_service.cache_misses) 
                                if (strategy_service.cache_hits + strategy_service.cache_misses) > 0 else 0.0
                },
                'redis_connected': strategy_service.redis_cache is not None and 
                                   strategy_service.redis_cache._connected if strategy_service.redis_cache else False,
                'cached_methods': {
                    'dashboard_data': '60s TTL',
                    'review_history': '120s TTL'
                }
            }
            
            return {
                'success': True,
                'stats': stats,
                'timestamp': datetime.now(timezone.utc)
            }
            
        except Exception as e:
            logger.error(f"Error getting cache stats: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to get cache stats: {str(e)}"
            )
    
    # ====================================================================
    # Strategy Generation API Endpoints
    # ====================================================================
    
    class GenerateStrategiesRequest(BaseModel):
        num_strategies: int = 100
        config: Optional[Dict] = None
    
    class GenerationJobResponse(BaseModel):
        job_id: str
        status: str
        message: str
    
    class GenerationProgressResponse(BaseModel):
        job_id: str
        status: str
        total_strategies: int
        strategies_generated: int
        strategies_backtested: int
        strategies_passed: int
        strategies_failed: int
        current_strategy: Optional[str] = None
        error_message: Optional[str] = None
        started_at: Optional[datetime] = None
        completed_at: Optional[datetime] = None
        estimated_completion: Optional[datetime] = None
    
    class BacktestSummary(BaseModel):
        strategy_id: str
        win_rate: float
        sharpe_ratio: float
        cagr: float
        max_drawdown: float
        total_trades: int
        monthly_returns: List[float]
        passed_criteria: bool
    
    class GenerationResultsResponse(BaseModel):
        job_id: str
        status: str
        total_strategies: int
        strategies_passed: int
        strategies_failed: int
        backtest_results: List[BacktestSummary]
        started_at: Optional[str] = None
        completed_at: Optional[str] = None
    
    class JobListItem(BaseModel):
        job_id: str
        status: str
        total_strategies: int
        strategies_generated: int
        strategies_backtested: int
        started_at: datetime
        completed_at: Optional[datetime]
    
    @app.post("/api/v1/strategies/generate", response_model=GenerationJobResponse, tags=["strategy-generation"])
    async def generate_strategies(request: GenerateStrategiesRequest):
        """
        Start a new strategy generation job
        
        - **num_strategies**: Number of strategies to generate (default: 100)
        - **config**: Optional configuration parameters for generation
        """
        try:
            if not hasattr(strategy_service, 'generation_manager') or not strategy_service.generation_manager:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Strategy generation manager not initialized"
                )
            
            if request.num_strategies < 1 or request.num_strategies > 1000:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Number of strategies must be between 1 and 1000"
                )
            
            job_id = await strategy_service.generation_manager.start_generation_job(
                num_strategies=request.num_strategies,
                strategy_config=request.config or {}
            )
            
            return GenerationJobResponse(
                job_id=job_id,
                status="PENDING",
                message=f"Generation job started for {request.num_strategies} strategies"
            )
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error starting generation job: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to start generation job: {str(e)}"
            )
    
    @app.get("/api/v1/strategies/jobs/{job_id}/progress", response_model=GenerationProgressResponse, tags=["strategy-generation"])
    async def get_generation_progress(job_id: str):
        """
        Get current progress of a strategy generation job
        
        - **job_id**: Unique identifier of the generation job
        """
        try:
            if not hasattr(strategy_service, 'generation_manager') or not strategy_service.generation_manager:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Strategy generation manager not initialized"
                )
            
            progress = await strategy_service.generation_manager.get_job_progress(job_id)
            
            if not progress:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Generation job {job_id} not found"
                )
            
            return GenerationProgressResponse(**progress)
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error getting generation progress: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to get generation progress: {str(e)}"
            )
    
    @app.get("/api/v1/strategies/jobs/{job_id}/results", response_model=GenerationResultsResponse, tags=["strategy-generation"])
    async def get_generation_results(job_id: str):
        """
        Get final results of a completed strategy generation job
        
        - **job_id**: Unique identifier of the generation job
        """
        try:
            if not hasattr(strategy_service, 'generation_manager') or not strategy_service.generation_manager:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Strategy generation manager not initialized"
                )
            
            results = await strategy_service.generation_manager.get_job_results(job_id)
            
            if not results:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Generation job {job_id} not found or not completed"
                )
            
            return GenerationResultsResponse(**results)
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error getting generation results: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to get generation results: {str(e)}"
            )
    
    @app.get("/api/v1/strategies/jobs", response_model=List[JobListItem], tags=["strategy-generation"])
    async def list_generation_jobs(
        status_filter: Optional[str] = Query(None, description="Filter by status (PENDING, GENERATING, BACKTESTING, COMPLETED, FAILED, CANCELLED)"),
        limit: int = Query(50, ge=1, le=100, description="Maximum number of jobs to return")
    ):
        """
        List all strategy generation jobs
        
        - **status_filter**: Optional filter by job status
        - **limit**: Maximum number of jobs to return (1-100)
        """
        try:
            if not hasattr(strategy_service, 'generation_manager') or not strategy_service.generation_manager:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Strategy generation manager not initialized"
                )
            
            jobs = await strategy_service.generation_manager.list_jobs(
                status_filter=status_filter,
                limit=limit
            )
            
            return [JobListItem(**job) for job in jobs]
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error listing generation jobs: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to list generation jobs: {str(e)}"
            )
    
    @app.delete("/api/v1/strategies/jobs/{job_id}", tags=["strategy-generation"])
    async def cancel_generation_job(job_id: str):
        """
        Cancel a running strategy generation job
        
        - **job_id**: Unique identifier of the generation job
        """
        try:
            if not hasattr(strategy_service, 'generation_manager') or not strategy_service.generation_manager:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Strategy generation manager not initialized"
                )
            
            success = await strategy_service.generation_manager.cancel_job(job_id)
            
            if not success:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Generation job {job_id} not found or cannot be cancelled"
                )
            
            return {
                "job_id": job_id,
                "status": "CANCELLED",
                "message": "Generation job cancelled successfully"
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error cancelling generation job: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to cancel generation job: {str(e)}"
            )
    
    @app.get("/api/v1/strategy/goal-based/adjustment")
    async def get_goal_based_adjustment():
        """Get current goal-based strategy adjustment factors"""
        try:
            # Check activation_manager first (where goal_selector is integrated)
            activation_manager = None
            if hasattr(strategy_service, 'activation_manager') and hasattr(strategy_service.activation_manager, 'goal_selector'):
                activation_manager = strategy_service.activation_manager
            elif hasattr(strategy_service, 'enhanced_activation_system') and hasattr(strategy_service.enhanced_activation_system, 'goal_selector'):
                activation_manager = strategy_service.enhanced_activation_system
            
            if not activation_manager or not hasattr(activation_manager, 'goal_selector'):
                raise HTTPException(
                    status_code=503,
                    detail="Goal-based selector not initialized"
                )
            
            summary = activation_manager.goal_selector.get_current_adjustment_summary()
            
            return {
                "success": True,
                "adjustment": summary,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error getting goal-based adjustment: {e}")
            raise HTTPException(
                status_code=500,
                detail=str(e)
            )
    
    @app.post("/api/v1/strategy/goal-based/refresh")
    async def refresh_goal_progress():
        """Manually refresh goal progress from risk manager"""
        try:
            # Check activation_manager first (where goal_selector is integrated)
            activation_manager = None
            if hasattr(strategy_service, 'activation_manager') and hasattr(strategy_service.activation_manager, 'goal_selector'):
                activation_manager = strategy_service.activation_manager
            elif hasattr(strategy_service, 'enhanced_activation_system') and hasattr(strategy_service.enhanced_activation_system, 'goal_selector'):
                activation_manager = strategy_service.enhanced_activation_system
            
            if not activation_manager or not hasattr(activation_manager, 'goal_selector'):
                raise HTTPException(
                    status_code=503,
                    detail="Goal-based selector not initialized"
                )
            
            # Force refresh from risk manager
            goal_progress = await activation_manager.goal_selector.get_goal_progress()
            
            return {
                "success": True,
                "goals": {
                    goal_type: {
                        "progress": f"{goal.progress_percent:.1f}%",
                        "status": goal.status,
                        "current_value": float(goal.current_value),
                        "target_value": float(goal.target_value)
                    }
                    for goal_type, goal in goal_progress.items()
                },
                "message": "Goal progress refreshed successfully",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error refreshing goal progress: {e}")
            raise HTTPException(
                status_code=500,
                detail=str(e)
            )
    
    # =========================================================================
    # Feature Store & ML Features Endpoints
    # =========================================================================
    
    @app.get("/api/v1/features/compute/{symbol}")
    async def compute_features(symbol: str):
        """
        Compute all ML features for a symbol
        
        Returns computed features without storing them in the feature store.
        Useful for real-time feature inspection.
        """
        try:
            if not hasattr(strategy_service, 'feature_pipeline') or not strategy_service.feature_pipeline:
                raise HTTPException(
                    status_code=503,
                    detail="Feature pipeline not initialized"
                )
            
            features = await strategy_service.feature_pipeline.compute_all_features(symbol)
            
            return {
                "success": True,
                "symbol": symbol,
                "features": features,
                "feature_count": len(features),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error computing features for {symbol}: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to compute features: {str(e)}"
            )
    
    @app.post("/api/v1/features/compute-and-store/{symbol}")
    async def compute_and_store_features(symbol: str):
        """
        Compute and store ML features for a symbol
        
        Computes all feature types and stores them in the PostgreSQL feature store.
        Auto-registers new features if enabled.
        """
        try:
            if not hasattr(strategy_service, 'feature_pipeline') or not strategy_service.feature_pipeline:
                raise HTTPException(
                    status_code=503,
                    detail="Feature pipeline not initialized"
                )
            
            feature_count = await strategy_service.feature_pipeline.compute_and_store_features(symbol)
            
            return {
                "success": True,
                "symbol": symbol,
                "features_stored": feature_count,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error storing features for {symbol}: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to store features: {str(e)}"
            )
    
    @app.get("/api/v1/features/retrieve/{symbol}")
    async def retrieve_features(
        symbol: str,
        feature_names: Optional[str] = Query(None, description="Comma-separated feature names"),
        as_of_time: Optional[str] = Query(None, description="Point-in-time timestamp (ISO format)")
    ):
        """
        Retrieve stored features for a symbol
        
        Args:
            symbol: Cryptocurrency symbol
            feature_names: Optional comma-separated list of feature names to retrieve
            as_of_time: Optional timestamp for point-in-time retrieval (for backtesting)
        """
        try:
            if not hasattr(strategy_service, 'feature_store') or not strategy_service.feature_store:
                raise HTTPException(
                    status_code=503,
                    detail="Feature store not initialized"
                )
            
            # Parse timestamp if provided
            timestamp = None
            if as_of_time:
                try:
                    timestamp = datetime.fromisoformat(as_of_time.replace('Z', '+00:00'))
                except ValueError:
                    raise HTTPException(
                        status_code=400,
                        detail="Invalid as_of_time format. Use ISO format (e.g., 2025-11-11T14:00:00Z)"
                    )
            
            # Get feature IDs for the specified names
            if feature_names:
                names = [name.strip() for name in feature_names.split(',')]
                feature_ids = []
                for name in names:
                    fid = await strategy_service.feature_store.get_feature_id(name)
                    if fid:
                        feature_ids.append(fid)
                
                if not feature_ids:
                    raise HTTPException(
                        status_code=404,
                        detail="No matching features found"
                    )
                
                # Bulk retrieval
                features = await strategy_service.feature_store.get_features_bulk(
                    feature_ids=feature_ids,
                    symbol=symbol,
                    as_of_time=timestamp
                )
                
                # Convert feature_id back to feature_name
                result = {}
                for fid, value in features.items():
                    # Get feature name from ID
                    feature_def = await strategy_service.feature_store.get_feature_definition(fid)
                    if feature_def:
                        result[feature_def.feature_name] = value
            else:
                # Get all features for symbol
                # We need to list all registered features and retrieve them
                all_features = await strategy_service.feature_store.list_features(active_only=True)
                feature_ids = [f.id for f in all_features]
                
                if not feature_ids:
                    return {
                        "success": True,
                        "symbol": symbol,
                        "features": {},
                        "feature_count": 0,
                        "as_of_time": as_of_time,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                
                features = await strategy_service.feature_store.get_features_bulk(
                    feature_ids=feature_ids,
                    symbol=symbol,
                    as_of_time=timestamp
                )
                
                # Convert to feature names
                result = {}
                for fid, value in features.items():
                    feature_def = await strategy_service.feature_store.get_feature_definition(fid)
                    if feature_def:
                        result[feature_def.feature_name] = value
            
            return {
                "success": True,
                "symbol": symbol,
                "features": result,
                "feature_count": len(result),
                "as_of_time": as_of_time,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error retrieving features for {symbol}: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to retrieve features: {str(e)}"
            )
    
    @app.get("/api/v1/features/list")
    async def list_features(
        feature_type: Optional[str] = Query(None, description="Filter by type: technical, onchain, social, macro, composite"),
        active_only: bool = Query(True, description="Include only active features")
    ):
        """
        List all registered features in the feature store
        
        Args:
            feature_type: Optional filter by feature type
            active_only: Whether to include only active features
        """
        try:
            if not hasattr(strategy_service, 'feature_store') or not strategy_service.feature_store:
                raise HTTPException(
                    status_code=503,
                    detail="Feature store not initialized"
                )
            
            features = await strategy_service.feature_store.list_features(
                feature_type=feature_type,
                active_only=active_only
            )
            
            feature_list = [
                {
                    "id": f.id,
                    "name": f.feature_name,
                    "type": f.feature_type,
                    "description": f.description,
                    "data_sources": f.data_sources,
                    "version": f.version,
                    "is_active": f.is_active,
                    "created_at": f.created_at.isoformat() if f.created_at else None
                }
                for f in features
            ]
            
            return {
                "success": True,
                "features": feature_list,
                "count": len(feature_list),
                "filter": {
                    "feature_type": feature_type,
                    "active_only": active_only
                },
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error listing features: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to list features: {str(e)}"
            )
    
    @app.get("/api/v1/features/summary")
    async def get_feature_summary():
        """
        Get summary statistics of the feature store
        
        Returns counts, types, and metadata about stored features.
        """
        try:
            if not hasattr(strategy_service, 'feature_pipeline') or not strategy_service.feature_pipeline:
                raise HTTPException(
                    status_code=503,
                    detail="Feature pipeline not initialized"
                )
            
            summary = await strategy_service.feature_pipeline.get_feature_summary()
            
            return {
                "success": True,
                "summary": summary,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error getting feature summary: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to get feature summary: {str(e)}"
            )
    
    # ==========================================
    # Feature-Aware Strategy Evaluation Endpoints
    # ==========================================
    
    @app.post("/api/v1/strategy/evaluate-with-features")
    async def evaluate_strategy_with_features(
        strategy_id: str,
        symbol: str,
        include_features: bool = True
    ):
        """
        Evaluate a strategy with optional ML features
        
        Args:
            strategy_id: Strategy ID to evaluate
            symbol: Cryptocurrency symbol
            include_features: Whether to include ML features (default: True)
            
        Returns:
            Evaluation results including signal, confidence, and features used
        """
        try:
            result = await strategy_service.evaluate_strategy_with_features(
                strategy_id=strategy_id,
                symbol=symbol,
                include_features=include_features
            )
            
            if not result.get("success", False):
                raise HTTPException(
                    status_code=404,
                    detail=result.get("error", "Evaluation failed")
                )
            
            return result
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error evaluating strategy with features: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to evaluate strategy: {str(e)}"
            )
    
    @app.get("/api/v1/strategy/signal/{strategy_id}/{symbol}")
    async def get_strategy_signal(
        strategy_id: str,
        symbol: str,
        use_features: bool = Query(True, description="Use ML features for signal generation")
    ):
        """
        Get trading signal from a strategy for a symbol
        
        This endpoint evaluates the strategy and returns a trading signal
        (BUY/SELL/HOLD) with confidence and reasoning.
        
        Args:
            strategy_id: Strategy ID
            symbol: Cryptocurrency symbol
            use_features: Whether to use ML features (default: True)
            
        Returns:
            Trading signal with action, confidence, and reasoning
        """
        try:
            result = await strategy_service.evaluate_strategy_with_features(
                strategy_id=strategy_id,
                symbol=symbol,
                include_features=use_features
            )
            
            if not result.get("success", False):
                raise HTTPException(
                    status_code=404,
                    detail=result.get("error", "Signal generation failed")
                )
            
            return {
                "success": True,
                "strategy_id": strategy_id,
                "symbol": symbol,
                "signal": result.get("signal", {}),
                "features_used": use_features,
                "feature_count": result.get("feature_count", 0),
                "timestamp": result.get("timestamp")
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error generating strategy signal: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to generate signal: {str(e)}"
            )
    
    @app.get("/api/v1/features/compute-for-signal/{symbol}")
    async def compute_features_for_signal(symbol: str):
        """
        Compute ML features for a symbol for signal generation
        
        This is a convenience endpoint to see what features would be
        used for signal generation without actually generating a signal.
        
        Args:
            symbol: Cryptocurrency symbol
            
        Returns:
            Computed features and their values
        """
        try:
            features = await strategy_service.compute_features_for_symbol(symbol)
            
            return {
                "success": True,
                "symbol": symbol,
                "features": features,
                "feature_count": len(features),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error computing features for signal: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to compute features: {str(e)}"
            )
    
    # Include enhanced strategy activation router
    if hasattr(strategy_service, 'enhanced_activation_system') and strategy_service.enhanced_activation_system:
        set_activation_system(strategy_service.enhanced_activation_system)
        app.include_router(activation_router)
        logger.info("Enhanced strategy activation API registered")
    
    # ============================================================
    # GOAL-ORIENTED TRADING API ENDPOINTS
    # ============================================================
    
    @app.get("/api/v1/goals/summary")
    async def get_goals_summary(goal_id: Optional[str] = None):
        """
        Get summary of financial goals and their progress.
        
        Returns overview of all active goals including:
        - Monthly return target (10%)
        - Monthly profit target ($10K)
        - Portfolio value target ($1M)
        
        Args:
            goal_id: Optional specific goal ID (None = all goals)
            
        Returns:
            Goal summary with progress metrics
        """
        try:
            from goal_tracker import GoalTracker
            
            tracker = GoalTracker(strategy_service.db)
            summary = await tracker.get_goal_summary(goal_id)
            
            return {
                "success": True,
                "data": summary,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error fetching goal summary: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to fetch goal summary: {str(e)}"
            )
    
    @app.get("/api/v1/goals/{goal_id}/progress")
    async def get_goal_progress_history(
        goal_id: str,
        limit: int = Query(100, ge=1, le=1000, description="Number of progress records")
    ):
        """
        Get historical progress tracking for a specific goal.
        
        Args:
            goal_id: Goal UUID
            limit: Number of records to return
            
        Returns:
            Time-series data of goal progress
        """
        try:
            import uuid
            query = """
                SELECT * FROM goal_progress
                WHERE goal_id = $1
                ORDER BY timestamp DESC
                LIMIT $2
            """
            records = await strategy_service.db._postgres.fetch(query, uuid.UUID(goal_id), limit)
            
            progress_data = []
            for record in records:
                progress_data.append({
                    "timestamp": record["timestamp"].isoformat(),
                    "current_value": float(record["current_value"]),
                    "progress_pct": float(record["progress_pct"]),
                    "portfolio_value": float(record["portfolio_value"]),
                    "realized_pnl": float(record["realized_pnl"]),
                    "unrealized_pnl": float(record["unrealized_pnl"]),
                    "win_rate": float(record["win_rate"]) if record["win_rate"] else None,
                    "sharpe_ratio": float(record["sharpe_ratio"]) if record["sharpe_ratio"] else None,
                    "on_track": record["on_track"],
                    "required_daily_return": float(record["required_daily_return"]) if record["required_daily_return"] else None
                })
            
            return {
                "success": True,
                "goal_id": goal_id,
                "progress_history": progress_data,
                "count": len(progress_data)
            }
            
        except Exception as e:
            logger.error(f"Error fetching goal progress: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to fetch goal progress: {str(e)}"
            )
    
    @app.get("/api/v1/goals/{goal_id}/adjustments")
    async def get_goal_adjustments(goal_id: str, limit: int = Query(50, ge=1, le=500)):
        """
        Get automatic adjustments made to achieve a goal.
        
        Shows how risk tolerance and position sizes have been adjusted
        based on goal progress.
        
        Args:
            goal_id: Goal UUID
            limit: Number of adjustments to return
            
        Returns:
            List of adjustments with before/after values
        """
        try:
            import uuid
            query = """
                SELECT * FROM goal_adjustments
                WHERE goal_id = $1
                ORDER BY applied_at DESC
                LIMIT $2
            """
            records = await strategy_service.db._postgres.fetch(query, uuid.UUID(goal_id), limit)
            
            adjustments = []
            for record in records:
                adjustments.append({
                    "id": str(record["id"]),
                    "adjustment_type": record["adjustment_type"],
                    "reason": record["reason"],
                    "previous_value": float(record["previous_value"]) if record["previous_value"] else None,
                    "new_value": float(record["new_value"]) if record["new_value"] else None,
                    "applied_at": record["applied_at"].isoformat(),
                    "status": record["status"]
                })
            
            return {
                "success": True,
                "goal_id": goal_id,
                "adjustments": adjustments,
                "count": len(adjustments)
            }
            
        except Exception as e:
            logger.error(f"Error fetching goal adjustments: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to fetch goal adjustments: {str(e)}"
            )
    
    @app.post("/api/v1/goals/{goal_id}/update-progress")
    async def trigger_goal_progress_update(goal_id: str):
        """
        Manually trigger a progress update for a specific goal.
        
        Normally runs hourly automatically, but can be triggered manually
        for immediate feedback.
        
        Args:
            goal_id: Goal UUID
            
        Returns:
            Updated progress metrics
        """
        try:
            from goal_tracker import GoalTracker
            
            tracker = GoalTracker(strategy_service.db)
            await tracker.update_goal_progress(goal_id)
            
            # Get updated summary
            summary = await tracker.get_goal_summary(goal_id)
            
            return {
                "success": True,
                "message": "Goal progress updated",
                "data": summary
            }
            
        except Exception as e:
            logger.error(f"Error updating goal progress: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to update goal progress: {str(e)}"
            )
    
    @app.post("/api/v1/position-sizing/calculate")
    async def calculate_position_size(
        strategy_id: str,
        symbol: str,
        current_price: float,
        stop_loss_pct: float,
        confidence: float = 0.5,
        goal_id: Optional[str] = None
    ):
        """
        Calculate optimal position size based on goal-oriented sizing.
        
        Takes into account:
        - Goal progress (ahead/behind schedule)
        - Current portfolio value
        - Win rate and Sharpe ratio
        - Kelly Criterion
        - Risk tolerance
        
        Args:
            strategy_id: Strategy generating signal
            symbol: Trading pair (e.g., 'BTCUSDT')
            current_price: Current market price
            stop_loss_pct: Stop loss distance as % (e.g., 0.02 for 2%)
            confidence: Model confidence in signal (0-1)
            goal_id: Specific goal to optimize for (None = highest priority)
            
        Returns:
            Recommended position size, allocation %, risk amount, reasoning
        """
        try:
            from decimal import Decimal
            from position_sizing_engine import GoalOrientedPositionSizer
            
            sizer = GoalOrientedPositionSizer(strategy_service.db)
            
            recommendation = await sizer.calculate_position_size(
                strategy_id=strategy_id,
                symbol=symbol,
                current_price=Decimal(str(current_price)),
                stop_loss_pct=Decimal(str(stop_loss_pct)),
                confidence=Decimal(str(confidence)),
                goal_id=goal_id
            )
            
            return {
                "success": True,
                "recommendation": recommendation,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error calculating position size: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to calculate position size: {str(e)}"
            )
    
    @app.get("/api/v1/goals/milestones/{goal_id}")
    async def get_goal_milestones(goal_id: str):
        """
        Get milestones for a specific goal.
        
        Milestones are intermediate targets towards the main goal
        (e.g., "First $1K profit", "10 consecutive wins").
        
        Args:
            goal_id: Goal UUID
            
        Returns:
            List of milestones with achievement status
        """
        try:
            import uuid
            query = """
                SELECT * FROM goal_milestones
                WHERE goal_id = $1
                ORDER BY milestone_value
            """
            records = await strategy_service.db._postgres.fetch(query, uuid.UUID(goal_id))
            
            milestones = []
            for record in records:
                milestones.append({
                    "id": str(record["id"]),
                    "milestone_name": record["milestone_name"],
                    "milestone_value": float(record["milestone_value"]),
                    "achieved": record["achieved"],
                    "achieved_at": record["achieved_at"].isoformat() if record["achieved_at"] else None,
                    "reward_action": record["reward_action"]
                })
            
            return {
                "success": True,
                "goal_id": goal_id,
                "milestones": milestones,
                "total": len(milestones),
                "achieved_count": sum(1 for m in milestones if m["achieved"])
            }
            
        except Exception as e:
            logger.error(f"Error fetching goal milestones: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to fetch goal milestones: {str(e)}"
            )
    
    return app