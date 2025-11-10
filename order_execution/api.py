"""
Order Execution API

FastAPI endpoints for order execution optimization.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict
from datetime import datetime

from .execution_algorithms import (
    ExecutionAlgorithm, TWAPAlgorithm, VWAPAlgorithm,
    POVAlgorithm, AdaptiveAlgorithm, select_execution_algorithm,
    ExecutionSlice, OrderSide
)
from .order_splitter import OrderSplitter, IcebergOrder, SplitStrategy
from .liquidity_analyzer import (
    OrderBookAnalyzer, VolumeProfileAnalyzer,
    LiquidityScore, OrderBookLevel
)
from .exchange_router import (
    SmartOrderRouter, ExchangeQuote, RoutingStrategy
)
from .slippage_tracker import SlippageTracker


# Global instances
order_book_analyzer = OrderBookAnalyzer()
volume_analyzer = VolumeProfileAnalyzer()
smart_router = SmartOrderRouter()
slippage_tracker = SlippageTracker()

# Active execution plans
active_executions: Dict[str, ExecutionAlgorithm] = {}

execution_router = APIRouter(prefix="/api/execution", tags=["execution"])


# ============= Request/Response Models =============

class AlgorithmRecommendationRequest(BaseModel):
    symbol: str
    order_size_usd: float
    daily_volume_usd: float
    urgency: float = 0.5
    duration_minutes: int = 60


class CreateExecutionRequest(BaseModel):
    order_id: str
    symbol: str
    side: str
    quantity: float
    algorithm: str  # "TWAP", "VWAP", "POV", "ADAPTIVE"
    duration_minutes: int
    urgency: Optional[float] = 0.5


class UpdateOrderBookRequest(BaseModel):
    symbol: str
    bids: List[Dict]  # [{price, quantity, num_orders}]
    asks: List[Dict]


class RecordExecutionRequest(BaseModel):
    order_id: str
    symbol: str
    side: str
    arrival_price: float
    fills: List[Dict]  # [{price, quantity, timestamp}]


class UpdateExchangeQuoteRequest(BaseModel):
    exchange: str
    symbol: str
    bid: float
    ask: float
    bid_size: float
    ask_size: float
    fee_bps: float
    latency_ms: float


class RouteOrderRequest(BaseModel):
    symbol: str
    side: str
    quantity: float
    allow_splits: bool = True


# ============= Endpoints =============

@execution_router.post("/recommend-algorithm")
async def recommend_algorithm(request: AlgorithmRecommendationRequest):
    """Recommend execution algorithm based on order characteristics"""
    
    try:
        recommendation = select_execution_algorithm(
            order_size_usd=request.order_size_usd,
            daily_volume_usd=request.daily_volume_usd,
            urgency=request.urgency,
            duration_minutes=request.duration_minutes,
        )
        
        return {
            "symbol": request.symbol,
            "recommended_algorithm": recommendation,
            "order_size_pct": (request.order_size_usd / request.daily_volume_usd) * 100,
            "urgency": request.urgency,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@execution_router.post("/create-execution")
async def create_execution(request: CreateExecutionRequest):
    """Create execution plan with slices"""
    
    try:
        # Create algorithm instance
        if request.algorithm == "TWAP":
            algo = TWAPAlgorithm(
                symbol=request.symbol,
                side=request.side,
                total_quantity=request.quantity,
                duration_minutes=request.duration_minutes,
            )
        elif request.algorithm == "VWAP":
            algo = VWAPAlgorithm(
                symbol=request.symbol,
                side=request.side,
                total_quantity=request.quantity,
                duration_minutes=request.duration_minutes,
            )
        elif request.algorithm == "POV":
            algo = POVAlgorithm(
                symbol=request.symbol,
                side=request.side,
                total_quantity=request.quantity,
                duration_minutes=request.duration_minutes,
            )
        elif request.algorithm == "ADAPTIVE":
            algo = AdaptiveAlgorithm(
                symbol=request.symbol,
                side=request.side,
                total_quantity=request.quantity,
                urgency=request.urgency,
            )
        else:
            raise HTTPException(status_code=400, detail=f"Unknown algorithm: {request.algorithm}")
        
        # Generate slices
        slices = algo.generate_slices()
        
        # Store active execution
        active_executions[request.order_id] = algo
        
        return {
            "order_id": request.order_id,
            "algorithm": request.algorithm,
            "num_slices": len(slices),
            "slices": [
                {
                    "slice_id": s.slice_id,
                    "quantity": s.quantity,
                    "scheduled_time": s.scheduled_time.isoformat() if s.scheduled_time else None,
                }
                for s in slices
            ],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@execution_router.get("/execution/{order_id}/status")
async def get_execution_status(order_id: str):
    """Get execution status"""
    
    if order_id not in active_executions:
        raise HTTPException(status_code=404, detail="Order not found")
    
    algo = active_executions[order_id]
    
    return {
        "order_id": order_id,
        "symbol": algo.symbol,
        "total_quantity": algo.total_quantity,
        "completion_rate": algo.get_completion_rate(),
        "average_price": algo.get_average_price(),
        "num_slices": len(algo.slices),
        "completed_slices": sum(1 for s in algo.slices if s.is_complete()),
    }


@execution_router.post("/liquidity/update-orderbook")
async def update_order_book(request: UpdateOrderBookRequest):
    """Update order book for liquidity analysis"""
    
    try:
        # Convert to OrderBookLevel objects
        bids = [
            OrderBookLevel(
                price=b["price"],
                quantity=b["quantity"],
                num_orders=b.get("num_orders", 1)
            )
            for b in request.bids
        ]
        
        asks = [
            OrderBookLevel(
                price=a["price"],
                quantity=a["quantity"],
                num_orders=a.get("num_orders", 1)
            )
            for a in request.asks
        ]
        
        order_book_analyzer.update_order_book(request.symbol, bids, asks)
        
        return {"status": "success", "symbol": request.symbol}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@execution_router.get("/liquidity/{symbol}/analyze")
async def analyze_liquidity(symbol: str, order_size_usd: float = 10000.0):
    """Analyze market liquidity"""
    
    try:
        score = order_book_analyzer.analyze_liquidity(symbol, order_size_usd)
        
        if not score:
            raise HTTPException(status_code=404, detail="No order book data available")
        
        return {
            "symbol": score.symbol,
            "overall_score": score.overall_score,
            "depth_score": score.depth_score,
            "spread_score": score.spread_score,
            "volume_score": score.volume_score,
            "bid_ask_spread_bps": score.bid_ask_spread_bps,
            "market_impact_bps": score.market_impact_bps,
            "is_liquid": score.is_liquid(),
            "timestamp": score.timestamp.isoformat(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@execution_router.post("/routing/update-quote")
async def update_exchange_quote(request: UpdateExchangeQuoteRequest):
    """Update quote from exchange"""
    
    try:
        quote = ExchangeQuote(
            exchange=request.exchange,
            symbol=request.symbol,
            bid=request.bid,
            ask=request.ask,
            bid_size=request.bid_size,
            ask_size=request.ask_size,
            fee_bps=request.fee_bps,
            latency_ms=request.latency_ms,
            timestamp=datetime.utcnow(),
        )
        
        smart_router.update_quote(quote)
        
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@execution_router.post("/routing/route-order")
async def route_order(request: RouteOrderRequest):
    """Get routing recommendation"""
    
    try:
        decisions = smart_router.route_order(
            symbol=request.symbol,
            side=request.side,
            quantity=request.quantity,
            allow_splits=request.allow_splits,
        )
        
        if not decisions:
            raise HTTPException(status_code=404, detail="No routing available")
        
        return {
            "symbol": request.symbol,
            "num_routes": len(decisions),
            "routes": [
                {
                    "exchange": d.exchange,
                    "expected_price": d.expected_price,
                    "expected_fee_bps": d.expected_fee_bps,
                    "liquidity_score": d.liquidity_score,
                    "routing_reason": d.routing_reason,
                }
                for d in decisions
            ],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@execution_router.post("/slippage/record")
async def record_slippage(request: RecordExecutionRequest):
    """Record execution and calculate slippage"""
    
    try:
        metrics = slippage_tracker.record_execution(
            order_id=request.order_id,
            symbol=request.symbol,
            side=request.side,
            arrival_price=request.arrival_price,
            fills=request.fills,
        )
        
        if not metrics:
            raise HTTPException(status_code=400, detail="Failed to record execution")
        
        return {
            "order_id": metrics.order_id,
            "slippage_bps": metrics.slippage_bps,
            "percentage_slippage": metrics.percentage_slippage,
            "average_execution_price": metrics.average_execution_price,
            "filled_quantity": metrics.filled_quantity,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@execution_router.get("/slippage/statistics")
async def get_slippage_statistics(symbol: Optional[str] = None, lookback_hours: int = 24):
    """Get slippage statistics"""
    
    try:
        stats = slippage_tracker.get_statistics(symbol, lookback_hours)
        quality_stats = slippage_tracker.get_quality_statistics(lookback_hours)
        
        return {
            "slippage_stats": stats,
            "quality_stats": quality_stats,
            "lookback_hours": lookback_hours,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@execution_router.get("/health")
async def health_check():
    """Health check"""
    return {
        "status": "healthy",
        "active_executions": len(active_executions),
        "tracked_symbols": len(order_book_analyzer.order_books),
    }
