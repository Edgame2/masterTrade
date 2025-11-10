"""
Market Microstructure API

FastAPI endpoints for microstructure analysis.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict
from datetime import datetime

from .order_flow_analyzer import TradeClassification
from .market_depth_analyzer import OrderBookLevel
from .microstructure_signals import MicrostructureSignalGenerator


# Global instance
signal_generator = MicrostructureSignalGenerator()

microstructure_router = APIRouter(prefix="/api/microstructure", tags=["microstructure"])


# ============= Request/Response Models =============

class RecordTradeRequest(BaseModel):
    symbol: str
    timestamp: str  # ISO format
    price: float
    volume: float
    bid: float
    ask: float


class RecordQuoteRequest(BaseModel):
    symbol: str
    timestamp: str
    bid: float
    ask: float
    bid_size: float
    ask_size: float


class UpdateOrderBookRequest(BaseModel):
    symbol: str
    timestamp: str
    bids: List[Dict]  # [{price, quantity, num_orders}]
    asks: List[Dict]


class SpreadAnalysisRequest(BaseModel):
    symbol: str
    trade_price: float
    trade_side: str  # "buy" or "sell"


# ============= Order Flow Endpoints =============

@microstructure_router.post("/order-flow/record-trade")
async def record_trade(request: RecordTradeRequest):
    """Record trade for order flow analysis"""
    
    try:
        timestamp = datetime.fromisoformat(request.timestamp.replace('Z', '+00:00'))
        
        analyzer = signal_generator.get_order_flow_analyzer()
        analyzer.record_trade(
            symbol=request.symbol,
            timestamp=timestamp,
            price=request.price,
            volume=request.volume,
            bid=request.bid,
            ask=request.ask,
        )
        
        return {"status": "success", "symbol": request.symbol}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@microstructure_router.get("/order-flow/{symbol}/metrics")
async def get_order_flow_metrics(symbol: str, lookback_minutes: Optional[int] = None):
    """Get order flow metrics"""
    
    try:
        analyzer = signal_generator.get_order_flow_analyzer()
        metrics = analyzer.calculate_metrics(symbol, lookback_minutes)
        
        if not metrics:
            raise HTTPException(status_code=404, detail="No data available")
        
        return {
            "symbol": metrics.symbol,
            "total_volume": metrics.total_volume,
            "buy_volume": metrics.buy_volume,
            "sell_volume": metrics.sell_volume,
            "ofi": metrics.ofi,
            "buy_pressure": metrics.buy_pressure,
            "sell_pressure": metrics.sell_pressure,
            "net_pressure": metrics.net_pressure,
            "vwap": metrics.vwap,
            "buy_vwap": metrics.buy_vwap,
            "sell_vwap": metrics.sell_vwap,
            "is_bullish": metrics.is_bullish(),
            "is_bearish": metrics.is_bearish(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@microstructure_router.get("/order-flow/{symbol}/toxic-flow")
async def detect_toxic_flow(symbol: str, threshold: float = 0.3):
    """Detect toxic (informed) order flow"""
    
    try:
        analyzer = signal_generator.get_order_flow_analyzer()
        result = analyzer.detect_toxic_flow(symbol, threshold)
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============= Bid-Ask Spread Endpoints =============

@microstructure_router.post("/spread/record-quote")
async def record_quote(request: RecordQuoteRequest):
    """Record quote for spread analysis"""
    
    try:
        timestamp = datetime.fromisoformat(request.timestamp.replace('Z', '+00:00'))
        
        analyzer = signal_generator.get_bid_ask_analyzer()
        analyzer.record_quote(
            symbol=request.symbol,
            timestamp=timestamp,
            bid=request.bid,
            ask=request.ask,
            bid_size=request.bid_size,
            ask_size=request.ask_size,
        )
        
        return {"status": "success", "symbol": request.symbol}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@microstructure_router.get("/spread/{symbol}/metrics")
async def get_spread_metrics(symbol: str):
    """Get bid-ask spread metrics"""
    
    try:
        analyzer = signal_generator.get_bid_ask_analyzer()
        metrics = analyzer.calculate_metrics(symbol)
        
        if not metrics:
            raise HTTPException(status_code=404, detail="No data available")
        
        return {
            "symbol": metrics.symbol,
            "current_bid": metrics.current_bid,
            "current_ask": metrics.current_ask,
            "current_spread": metrics.current_spread,
            "current_spread_bps": metrics.current_spread_bps,
            "avg_spread": metrics.avg_spread,
            "spread_std": metrics.spread_std,
            "spread_pct": metrics.spread_pct,
            "bid_size": metrics.bid_size,
            "ask_size": metrics.ask_size,
            "size_imbalance": metrics.size_imbalance,
            "tightness_score": metrics.tightness_score,
            "is_tight": metrics.is_tight(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@microstructure_router.post("/spread/analyze")
async def analyze_spread(request: SpreadAnalysisRequest):
    """Analyze spread for a trade"""
    
    try:
        analyzer = signal_generator.get_bid_ask_analyzer()
        analysis = analyzer.analyze_spread(
            symbol=request.symbol,
            trade_price=request.trade_price,
            trade_side=request.trade_side,
        )
        
        if not analysis:
            raise HTTPException(status_code=404, detail="No quote data available")
        
        return {
            "symbol": analysis.symbol,
            "quoted_spread": analysis.quoted_spread,
            "effective_spread": analysis.effective_spread,
            "quoted_spread_bps": analysis.quoted_spread_bps,
            "effective_spread_bps": analysis.effective_spread_bps,
            "price_improvement": analysis.price_improvement,
            "has_price_improvement": analysis.has_price_improvement(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@microstructure_router.get("/spread/{symbol}/widening")
async def detect_spread_widening(symbol: str, threshold_std: float = 2.0):
    """Detect unusual spread widening"""
    
    try:
        analyzer = signal_generator.get_bid_ask_analyzer()
        result = analyzer.detect_spread_widening(symbol, threshold_std)
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============= Market Depth Endpoints =============

@microstructure_router.post("/depth/update-orderbook")
async def update_order_book(request: UpdateOrderBookRequest):
    """Update order book for depth analysis"""
    
    try:
        timestamp = datetime.fromisoformat(request.timestamp.replace('Z', '+00:00'))
        
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
        
        analyzer = signal_generator.get_depth_analyzer()
        analyzer.update_order_book(request.symbol, timestamp, bids, asks)
        
        return {"status": "success", "symbol": request.symbol}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@microstructure_router.get("/depth/{symbol}/imbalance")
async def get_depth_imbalance(symbol: str, num_levels: int = 10):
    """Get order book depth imbalance"""
    
    try:
        analyzer = signal_generator.get_depth_analyzer()
        imbalance = analyzer.calculate_depth_imbalance(symbol, num_levels)
        
        if not imbalance:
            raise HTTPException(status_code=404, detail="No order book data")
        
        return {
            "symbol": imbalance.symbol,
            "imbalance_ratio": imbalance.imbalance_ratio,
            "bid_depth_l1": imbalance.bid_depth_l1,
            "ask_depth_l1": imbalance.ask_depth_l1,
            "bid_depth_l5": imbalance.bid_depth_l5,
            "ask_depth_l5": imbalance.ask_depth_l5,
            "total_bid_depth": imbalance.total_bid_depth,
            "total_ask_depth": imbalance.total_ask_depth,
            "is_bullish": imbalance.is_bullish(),
            "is_bearish": imbalance.is_bearish(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@microstructure_router.get("/depth/{symbol}/metrics")
async def get_depth_metrics(symbol: str, order_size_usd: float = 10000.0):
    """Get comprehensive depth metrics"""
    
    try:
        analyzer = signal_generator.get_depth_analyzer()
        metrics = analyzer.calculate_metrics(symbol, order_size_usd)
        
        if not metrics:
            raise HTTPException(status_code=404, detail="No order book data")
        
        return {
            "symbol": metrics.symbol,
            "imbalance_ratio": metrics.depth_imbalance.imbalance_ratio,
            "buy_market_impact_bps": metrics.buy_market_impact_bps,
            "sell_market_impact_bps": metrics.sell_market_impact_bps,
            "resilience_score": metrics.resilience_score,
            "depth_concentration": metrics.depth_concentration,
            "depth_diversity": metrics.depth_diversity,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@microstructure_router.get("/depth/{symbol}/cliff")
async def detect_depth_cliff(symbol: str, side: str = "bid", threshold_pct: float = 50.0):
    """Detect depth cliff (sudden liquidity drop)"""
    
    try:
        analyzer = signal_generator.get_depth_analyzer()
        result = analyzer.detect_depth_cliff(symbol, side, threshold_pct)
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============= VPIN Endpoints =============

@microstructure_router.post("/vpin/add-trade")
async def add_vpin_trade(symbol: str, timestamp: str, volume: float, is_buy: bool):
    """Add trade to VPIN calculation"""
    
    try:
        ts = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        
        calculator = signal_generator.get_vpin_calculator()
        calculator.add_trade(symbol, ts, volume, is_buy)
        
        return {"status": "success", "symbol": symbol}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@microstructure_router.get("/vpin/{symbol}/metrics")
async def get_vpin_metrics(symbol: str):
    """Get VPIN metrics"""
    
    try:
        calculator = signal_generator.get_vpin_calculator()
        metrics = calculator.calculate_vpin(symbol)
        
        if not metrics:
            raise HTTPException(status_code=404, detail="Insufficient data for VPIN")
        
        return {
            "symbol": metrics.symbol,
            "vpin": metrics.vpin,
            "toxicity_level": metrics.toxicity_level.value,
            "is_toxic": metrics.is_toxic,
            "adverse_selection_risk": metrics.adverse_selection_risk,
            "vpin_trend": metrics.vpin_trend,
            "description": metrics.get_toxicity_description(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@microstructure_router.get("/vpin/{symbol}/spike")
async def detect_toxicity_spike(symbol: str, threshold: float = 0.6):
    """Detect toxicity spike"""
    
    try:
        calculator = signal_generator.get_vpin_calculator()
        result = calculator.detect_toxicity_spike(symbol, threshold)
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============= Signal Generation Endpoints =============

@microstructure_router.get("/signal/{symbol}")
async def generate_signal(symbol: str):
    """Generate comprehensive microstructure signal"""
    
    try:
        signal = signal_generator.generate_signal(symbol)
        
        if not signal:
            raise HTTPException(status_code=404, detail="Insufficient data")
        
        return signal.to_dict()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@microstructure_router.get("/health")
async def health_check():
    """Health check"""
    return {
        "status": "healthy",
        "components": {
            "order_flow_analyzer": "operational",
            "bid_ask_analyzer": "operational",
            "depth_analyzer": "operational",
            "vpin_calculator": "operational",
        }
    }
