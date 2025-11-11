"""
Data Access Service - Provides unified access to market data stored in Azure Cosmos DB

This service provides REST API endpoints for other services to access market data,
ensuring consistent data access patterns and implementing caching for performance.
"""

import asyncio
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
from decimal import Decimal

import structlog
from fastapi import FastAPI, HTTPException, Query, Path, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

from database import Database
from config import settings
from indicator_models import IndicatorConfiguration, IndicatorRequest, BulkIndicatorRequest, IndicatorResult
from technical_indicator_calculator import IndicatorCalculator

# Configure logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

# Metrics - Check if already registered to avoid duplicate registration
from prometheus_client import REGISTRY

def get_or_create_counter(name, description, labels):
    if name in REGISTRY._names_to_collectors:
        return REGISTRY._names_to_collectors[name]
    return Counter(name, description, labels)

def get_or_create_histogram(name, description, labels):
    if name in REGISTRY._names_to_collectors:
        return REGISTRY._names_to_collectors[name]
    return Histogram(name, description, labels)

api_requests = get_or_create_counter('data_access_requests_total', 'Total API requests', ['endpoint', 'method'])
response_time = get_or_create_histogram('data_access_response_time_seconds', 'Response time', ['endpoint'])
cache_hits = get_or_create_counter('data_access_cache_hits_total', 'Cache hits', ['type'])

# Application Setup# FastAPI app
app = FastAPI(
    title="MasterTrade Data Access API",
    description="Unified data access for market data stored in Azure Cosmos DB",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database instance
database = Database()

# Simple in-memory cache
cache: Dict[str, Dict] = {}
CACHE_TTL = 60  # 60 seconds

class MarketDataResponse(BaseModel):
    symbol: str
    data: List[Dict[str, Any]]
    count: int
    from_cache: bool = False

class LatestPriceResponse(BaseModel):
    symbol: str
    price: float
    timestamp: str
    volume_24h: float
    price_change_24h: float

class SymbolsResponse(BaseModel):
    symbols: List[Dict[str, Any]]
    count: int

# Initialize indicator calculator
indicator_calculator = None

@app.on_event("startup")
async def startup_event():
    """Initialize database connection and indicator calculator"""
    global indicator_calculator
    await database.connect()
    indicator_calculator = IndicatorCalculator(database)
    logger.info("Data Access API started with indicator calculator")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    await database.disconnect()
    logger.info("Data Access API stopped")

def get_cache_key(endpoint: str, **params) -> str:
    """Generate cache key from endpoint and parameters"""
    param_str = "_".join([f"{k}={v}" for k, v in sorted(params.items())])
    return f"{endpoint}_{param_str}"

def is_cache_valid(cache_entry: Dict) -> bool:
    """Check if cache entry is still valid"""
    if not cache_entry:
        return False
    
    cache_time = cache_entry.get('timestamp', 0)
    return (datetime.now().timestamp() - cache_time) < CACHE_TTL

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "data_access_api"}

@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

@app.get("/api/symbols", response_model=SymbolsResponse)
async def get_symbols():
    """Get all available trading symbols"""
    api_requests.labels(endpoint='symbols', method='GET').inc()
    
    with response_time.labels(endpoint='symbols').time():
        try:
            # This would be implemented in the database class
            symbols = []  # Placeholder for now
            
            return SymbolsResponse(symbols=symbols, count=len(symbols))
            
        except Exception as e:
            logger.error("Error fetching symbols", error=str(e))
            raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/api/market-data/{symbol}", response_model=MarketDataResponse)
async def get_market_data(
    symbol: str = Path(..., description="Trading symbol (e.g., BTCUSDC)"),
    interval: str = Query("1m", description="Data interval (1m, 5m, 15m, 1h, 4h, 1d)"),
    limit: int = Query(100, ge=1, le=1000, description="Number of records to return"),
    hours_back: int = Query(24, ge=1, le=168, description="Hours of historical data")
):
    """Get market data for a specific symbol"""
    api_requests.labels(endpoint='market_data', method='GET').inc()
    
    # Check cache first
    cache_key = get_cache_key("market_data", symbol=symbol, interval=interval, 
                             limit=limit, hours_back=hours_back)
    
    if cache_key in cache and is_cache_valid(cache[cache_key]):
        cache_hits.labels(type='market_data').inc()
        cached_data = cache[cache_key]['data']
        return MarketDataResponse(
            symbol=symbol,
            data=cached_data,
            count=len(cached_data),
            from_cache=True
        )
    
    with response_time.labels(endpoint='market_data').time():
        try:
            data = await database.get_market_data_for_analysis(
                symbol=symbol.upper(),
                interval=interval,
                hours_back=hours_back
            )
            
            # Apply limit
            if limit < len(data):
                data = data[-limit:]
            
            # Cache the result
            cache[cache_key] = {
                'data': data,
                'timestamp': datetime.now().timestamp()
            }
            
            return MarketDataResponse(
                symbol=symbol,
                data=data,
                count=len(data),
                from_cache=False
            )
            
        except Exception as e:
            logger.error("Error fetching market data", symbol=symbol, error=str(e))
            raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/api/latest-price/{symbol}", response_model=LatestPriceResponse)
async def get_latest_price(
    symbol: str = Path(..., description="Trading symbol (e.g., BTCUSDC)")
):
    """Get latest price and 24h statistics for a symbol"""
    api_requests.labels(endpoint='latest_price', method='GET').inc()
    
    # Check cache first
    cache_key = get_cache_key("latest_price", symbol=symbol)
    
    if cache_key in cache and is_cache_valid(cache[cache_key]):
        cache_hits.labels(type='latest_price').inc()
        return cache[cache_key]['data']
    
    with response_time.labels(endpoint='latest_price').time():
        try:
            # Get latest data point
            latest_data = await database.get_latest_market_data(symbol.upper(), limit=1)
            
            if not latest_data:
                raise HTTPException(status_code=404, detail="Symbol not found or no data available")
            
            current = latest_data[0]
            
            # Get 24h ago data for comparison
            data_24h = await database.get_market_data_for_analysis(
                symbol=symbol.upper(),
                interval='1h',
                hours_back=25
            )
            
            # Calculate 24h change
            price_change_24h = 0.0
            if len(data_24h) >= 24:
                old_price = float(data_24h[0]['close_price'])
                current_price = float(current['close_price'])
                price_change_24h = ((current_price - old_price) / old_price) * 100
            
            # Calculate 24h volume (sum of last 24 hours)
            volume_24h = sum(float(d['volume']) for d in data_24h[-24:]) if data_24h else 0.0
            
            response = LatestPriceResponse(
                symbol=symbol.upper(),
                price=float(current['close_price']),
                timestamp=current['timestamp'],
                volume_24h=volume_24h,
                price_change_24h=price_change_24h
            )
            
            # Cache the result with shorter TTL for latest price
            cache[cache_key] = {
                'data': response,
                'timestamp': datetime.now().timestamp()
            }
            
            return response
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Error fetching latest price", symbol=symbol, error=str(e))
            raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/api/ohlcv/{symbol}")
async def get_ohlcv_data(
    symbol: str = Path(..., description="Trading symbol (e.g., BTCUSDC)"),
    interval: str = Query("1m", description="Data interval"),
    limit: int = Query(500, ge=1, le=2000, description="Number of records")
):
    """Get OHLCV data in format suitable for charting libraries"""
    api_requests.labels(endpoint='ohlcv', method='GET').inc()
    
    with response_time.labels(endpoint='ohlcv').time():
        try:
            data = await database.get_market_data_for_analysis(
                symbol=symbol.upper(),
                interval=interval,
                hours_back=168  # 1 week max
            )
            
            if limit < len(data):
                data = data[-limit:]
            
            # Format for charting libraries (TradingView format)
            ohlcv_data = []
            for item in data:
                ohlcv_data.append({
                    'time': int(datetime.fromisoformat(item['timestamp']).timestamp()),
                    'open': float(item['open_price']),
                    'high': float(item['high_price']),
                    'low': float(item['low_price']),
                    'close': float(item['close_price']),
                    'volume': float(item['volume'])
                })
            
            return {
                'symbol': symbol.upper(),
                'interval': interval,
                'data': ohlcv_data,
                'count': len(ohlcv_data)
            }
            
        except Exception as e:
            logger.error("Error fetching OHLCV data", symbol=symbol, error=str(e))
            raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/api/trades/{symbol}")
async def get_recent_trades(
    symbol: str = Path(..., description="Trading symbol (e.g., BTCUSDC)"),
    limit: int = Query(100, ge=1, le=1000, description="Number of trades")
):
    """Get recent trades for a symbol"""
    api_requests.labels(endpoint='trades', method='GET').inc()
    
    with response_time.labels(endpoint='trades').time():
        try:
            # This would be implemented in the database class
            trades = []  # Placeholder for now
            
            return {
                'symbol': symbol.upper(),
                'trades': trades,
                'count': len(trades)
            }
            
        except Exception as e:
            logger.error("Error fetching trades", symbol=symbol, error=str(e))
            raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/api/orderbook/{symbol}")
async def get_orderbook(
    symbol: str = Path(..., description="Trading symbol (e.g., BTCUSDC)"),
    depth: int = Query(20, ge=5, le=100, description="Order book depth")
):
    """Get current order book for a symbol"""
    api_requests.labels(endpoint='orderbook', method='GET').inc()
    
    with response_time.labels(endpoint='orderbook').time():
        try:
            # This would be implemented in the database class
            orderbook = {
                'symbol': symbol.upper(),
                'bids': [],
                'asks': [],
                'timestamp': datetime.now().isoformat()
            }
            
            return orderbook
            
        except Exception as e:
            logger.error("Error fetching orderbook", symbol=symbol, error=str(e))
            raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/api/stats/{symbol}")
async def get_symbol_stats(
    symbol: str = Path(..., description="Trading symbol (e.g., BTCUSDC)")
):
    """Get comprehensive statistics for a symbol"""
    api_requests.labels(endpoint='stats', method='GET').inc()
    
    with response_time.labels(endpoint='stats').time():
        try:
            # Get various timeframe data
            data_1h = await database.get_market_data_for_analysis(symbol.upper(), '1h', 24)
            data_1d = await database.get_market_data_for_analysis(symbol.upper(), '1d', 30)
            
            if not data_1h:
                raise HTTPException(status_code=404, detail="Symbol not found")
            
            current_price = float(data_1h[-1]['close_price']) if data_1h else 0
            
            # Calculate statistics
            stats = {
                'symbol': symbol.upper(),
                'current_price': current_price,
                'volume_24h': sum(float(d['volume']) for d in data_1h[-24:]) if data_1h else 0,
                'high_24h': max(float(d['high_price']) for d in data_1h[-24:]) if data_1h else 0,
                'low_24h': min(float(d['low_price']) for d in data_1h[-24:]) if data_1h else 0,
                'change_24h': 0,  # Calculate percentage change
                'change_7d': 0,   # Calculate 7-day change
                'change_30d': 0,  # Calculate 30-day change
                'avg_volume_30d': sum(float(d['volume']) for d in data_1d) / len(data_1d) if data_1d else 0,
                'timestamp': datetime.now().isoformat()
            }
            
            # Calculate percentage changes
            if len(data_1h) >= 24:
                old_price_24h = float(data_1h[-24]['close_price'])
                stats['change_24h'] = ((current_price - old_price_24h) / old_price_24h) * 100
            
            if len(data_1d) >= 7:
                old_price_7d = float(data_1d[-7]['close_price'])
                stats['change_7d'] = ((current_price - old_price_7d) / old_price_7d) * 100
            
            if len(data_1d) >= 30:
                old_price_30d = float(data_1d[0]['close_price'])
                stats['change_30d'] = ((current_price - old_price_30d) / old_price_30d) * 100
            
            return stats
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Error calculating symbol stats", symbol=symbol, error=str(e))
            raise HTTPException(status_code=500, detail="Internal server error")

# Stock Index Endpoints
@app.get("/api/stock-indices")
async def get_all_stock_indices(
    interval: str = Query("1d", description="Time interval"),
    hours_back: int = Query(24, description="Hours of data to retrieve"),
    limit: int = Query(50, description="Maximum number of records")
):
    """Get all current stock index values"""
    api_requests.labels(endpoint='/api/stock-indices', method='GET').inc()
    
    with response_time.labels(endpoint='/api/stock-indices').time():
        try:
            data = await database.get_stock_index_data(
                asset_type="stock_index_current",
                interval=interval,
                hours_back=hours_back,
                limit=limit
            )
            
            return {
                "indices": data,
                "count": len(data),
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
            
        except Exception as e:
            logger.error("Error getting stock indices", error=str(e))
            raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/api/stock-indices/{symbol}")
async def get_stock_index_data(
    symbol: str = Path(..., description="Stock index symbol (e.g. ^GSPC, ^IXIC)"),
    interval: str = Query("1d", description="Time interval"),
    hours_back: int = Query(24, description="Hours of data to retrieve"),
    limit: int = Query(100, description="Maximum number of records")
):
    """Get historical data for a specific stock index"""
    api_requests.labels(endpoint='/api/stock-indices/{symbol}', method='GET').inc()
    
    with response_time.labels(endpoint='/api/stock-indices/{symbol}').time():
        try:
            # Get both current and historical data
            current_data = await database.get_stock_index_data(
                symbol=symbol,
                asset_type="stock_index_current",
                hours_back=1,
                limit=1
            )
            
            historical_data = await database.get_stock_index_data(
                symbol=symbol,
                asset_type="stock_index",
                interval=interval,
                hours_back=hours_back,
                limit=limit
            )
            
            return {
                "symbol": symbol,
                "current": current_data[0] if current_data else None,
                "historical": historical_data,
                "count": len(historical_data),
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
            
        except Exception as e:
            logger.error("Error getting stock index data", symbol=symbol, error=str(e))
            raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/api/market-summary/stocks")
async def get_stock_market_summary():
    """Get summary of stock market performance"""
    api_requests.labels(endpoint='/api/market-summary/stocks', method='GET').inc()
    
    with response_time.labels(endpoint='/api/market-summary/stocks').time():
        try:
            summary = await database.get_stock_market_summary()
            return summary
            
        except Exception as e:
            logger.error("Error getting stock market summary", error=str(e))
            raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/api/correlation/markets")
async def get_market_correlation():
    """Get correlation indicators between crypto and stock markets"""
    api_requests.labels(endpoint='/api/correlation/markets', method='GET').inc()
    
    with response_time.labels(endpoint='/api/correlation/markets').time():
        try:
            correlation = await database.get_market_correlation_indicators()
            return correlation
            
        except Exception as e:
            logger.error("Error getting market correlation", error=str(e))
            raise HTTPException(status_code=500, detail="Internal server error")

# Sentiment Analysis Endpoints
@app.get("/api/sentiment/{asset_type}")
async def get_sentiment_data(
    asset_type: str = Path(..., description="Asset type (crypto, global_market, global_crypto)"),
    hours_back: int = Query(24, description="Hours of data to retrieve"),
    limit: int = Query(100, description="Maximum number of records")
):
    """Get sentiment analysis data"""
    api_requests.labels(endpoint='/api/sentiment/{asset_type}', method='GET').inc()
    
    with response_time.labels(endpoint='/api/sentiment/{asset_type}').time():
        try:
            data = await database.get_sentiment_data(
                asset_type=asset_type,
                hours_back=hours_back,
                limit=limit
            )
            
            return {
                "sentiment_data": data,
                "count": len(data),
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
            
        except Exception as e:
            logger.error("Error getting sentiment data", asset_type=asset_type, error=str(e))
            raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/api/sentiment/summary")
async def get_sentiment_summary():
    """Get overall sentiment summary across all categories"""
    api_requests.labels(endpoint='/api/sentiment/summary', method='GET').inc()
    
    with response_time.labels(endpoint='/api/sentiment/summary').time():
        try:
            summary = await database.get_sentiment_summary()
            return summary
            
        except Exception as e:
            logger.error("Error getting sentiment summary", error=str(e))
            raise HTTPException(status_code=500, detail="Internal server error")

# Symbol Management Endpoints  
@app.get("/api/symbols/tracked")
async def get_tracked_symbols(
    asset_type: str = Query("crypto", description="Asset type filter"),
    exchange: str = Query("binance", description="Exchange filter")
):
    """Get all symbols with tracking enabled"""
    api_requests.labels(endpoint='/api/symbols/tracked', method='GET').inc()
    
    with response_time.labels(endpoint='/api/symbols/tracked').time():
        try:
            symbols = await database.get_tracked_symbols(
                asset_type=asset_type,
                exchange=exchange
            )
            
            return {
                "symbols": symbols,
                "count": len(symbols),
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
            
        except Exception as e:
            logger.error("Error getting tracked symbols", error=str(e))
            raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/api/symbols/all")
async def get_all_symbols(include_inactive: bool = Query(False, description="Include inactive symbols")):
    """Get all symbols in the system"""
    api_requests.labels(endpoint='/api/symbols/all', method='GET').inc()
    
    with response_time.labels(endpoint='/api/symbols/all').time():
        try:
            symbols = await database.get_all_symbols(include_inactive=include_inactive)
            
            return {
                "symbols": symbols,
                "count": len(symbols),
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
            
        except Exception as e:
            logger.error("Error getting all symbols", error=str(e))
            raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/api/symbols/{symbol}")
async def get_symbol_info(symbol: str = Path(..., description="Symbol to get info for")):
    """Get detailed information about a specific symbol"""
    api_requests.labels(endpoint='/api/symbols/{symbol}', method='GET').inc()
    
    with response_time.labels(endpoint='/api/symbols/{symbol}').time():
        try:
            symbol_info = await database.get_symbol_tracking_info(symbol)
            
            if not symbol_info:
                raise HTTPException(status_code=404, detail="Symbol not found")
                
            return symbol_info
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Error getting symbol info", symbol=symbol, error=str(e))
            raise HTTPException(status_code=500, detail="Internal server error")

class SymbolTrackingRequest(BaseModel):
    symbol: str
    base_asset: str
    quote_asset: str
    tracking: bool = True
    asset_type: str = "crypto"
    exchange: str = "binance"
    priority: int = 1
    intervals: List[str] = ["1m", "5m", "15m", "1h", "4h", "1d"]
    notes: str = ""

@app.post("/api/symbols")
async def add_symbol_tracking(symbol_request: SymbolTrackingRequest):
    """Add a new symbol to tracking"""
    api_requests.labels(endpoint='/api/symbols', method='POST').inc()
    
    with response_time.labels(endpoint='/api/symbols').time():
        try:
            from models import SymbolTracking
            
            symbol_tracking = SymbolTracking(
                id=symbol_request.symbol,
                symbol=symbol_request.symbol,
                base_asset=symbol_request.base_asset,
                quote_asset=symbol_request.quote_asset,
                tracking=symbol_request.tracking,
                asset_type=symbol_request.asset_type,
                exchange=symbol_request.exchange,
                priority=symbol_request.priority,
                intervals=symbol_request.intervals,
                notes=symbol_request.notes
            )
            
            success = await database.add_symbol_tracking(symbol_tracking)
            
            if success:
                return {
                    "success": True,
                    "message": f"Symbol {symbol_request.symbol} added to tracking",
                    "symbol": symbol_request.symbol
                }
            else:
                raise HTTPException(status_code=409, detail="Symbol already exists or could not be added")
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Error adding symbol", symbol=symbol_request.symbol, error=str(e))
            raise HTTPException(status_code=500, detail="Internal server error")

class SymbolUpdateRequest(BaseModel):
    tracking: Optional[bool] = None
    priority: Optional[int] = None
    intervals: Optional[List[str]] = None
    notes: Optional[str] = None

@app.put("/api/symbols/{symbol}")
async def update_symbol_tracking(
    symbol: str = Path(..., description="Symbol to update"),
    update_request: SymbolUpdateRequest = None
):
    """Update symbol tracking configuration"""
    api_requests.labels(endpoint='/api/symbols/{symbol}', method='PUT').inc()
    
    with response_time.labels(endpoint='/api/symbols/{symbol}').time():
        try:
            # Build update dict from non-None values
            updates = {}
            if update_request.tracking is not None:
                updates['tracking'] = update_request.tracking
            if update_request.priority is not None:
                updates['priority'] = update_request.priority
            if update_request.intervals is not None:
                updates['intervals'] = update_request.intervals
            if update_request.notes is not None:
                updates['notes'] = update_request.notes
                
            if not updates:
                raise HTTPException(status_code=400, detail="No valid updates provided")
                
            success = await database.update_symbol_tracking(symbol, updates)
            
            if success:
                return {
                    "success": True,
                    "message": f"Symbol {symbol} updated",
                    "updates": list(updates.keys())
                }
            else:
                raise HTTPException(status_code=404, detail="Symbol not found")
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Error updating symbol", symbol=symbol, error=str(e))
            raise HTTPException(status_code=500, detail="Internal server error")

@app.delete("/api/symbols/{symbol}")
async def remove_symbol_tracking(symbol: str = Path(..., description="Symbol to remove")):
    """Remove symbol from tracking"""
    api_requests.labels(endpoint='/api/symbols/{symbol}', method='DELETE').inc()
    
    with response_time.labels(endpoint='/api/symbols/{symbol}').time():
        try:
            success = await database.remove_symbol_tracking(symbol)
            
            if success:
                return {
                    "success": True,
                    "message": f"Symbol {symbol} removed from tracking"
                }
            else:
                raise HTTPException(status_code=404, detail="Symbol not found")
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Error removing symbol", symbol=symbol, error=str(e))
            raise HTTPException(status_code=500, detail="Internal server error")

@app.put("/api/symbols/{symbol}/tracking")
async def toggle_symbol_tracking(
    symbol: str = Path(..., description="Symbol to toggle"),
    tracking: bool = Query(..., description="Enable or disable tracking")
):
    """Enable or disable tracking for a symbol"""
    api_requests.labels(endpoint='/api/symbols/{symbol}/tracking', method='PUT').inc()
    
    with response_time.labels(endpoint='/api/symbols/{symbol}/tracking').time():
        try:
            success = await database.set_symbol_tracking(symbol, tracking)
            
            if success:
                status = "enabled" if tracking else "disabled"
                return {
                    "success": True,
                    "message": f"Tracking {status} for symbol {symbol}",
                    "symbol": symbol,
                    "tracking": tracking
                }
            else:
                raise HTTPException(status_code=404, detail="Symbol not found")
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Error toggling symbol tracking", symbol=symbol, error=str(e))
            raise HTTPException(status_code=500, detail="Internal server error")

# Stock Index Management Endpoints
@app.get("/api/stock-indices/tracked")
async def get_tracked_stock_indices(
    region: str = Query(None, description="Filter by region (us, uk, japan, etc.)"),
    category: str = Query(None, description="Filter by category (major, volatility, bonds)")
):
    """Get all stock indices with tracking enabled"""
    api_requests.labels(endpoint='/api/stock-indices/tracked', method='GET').inc()
    
    with response_time.labels(endpoint='/api/stock-indices/tracked').time():
        try:
            indices = await database.get_tracked_stock_indices(region=region, category=category)
            
            return {
                "indices": indices,
                "count": len(indices),
                "filters": {"region": region, "category": category},
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
            
        except Exception as e:
            logger.error("Error getting tracked stock indices", error=str(e))
            raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/api/stock-indices/categories")
async def get_stock_indices_by_category():
    """Get stock indices organized by category"""
    api_requests.labels(endpoint='/api/stock-indices/categories', method='GET').inc()
    
    with response_time.labels(endpoint='/api/stock-indices/categories').time():
        try:
            categories = await database.get_stock_indices_by_category()
            
            return {
                "categories": categories,
                "total_indices": sum(len(indices) for indices in categories.values()),
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
            
        except Exception as e:
            logger.error("Error getting stock indices by category", error=str(e))
            raise HTTPException(status_code=500, detail="Internal server error")

class StockIndexRequest(BaseModel):
    symbol: str
    full_name: str
    region: str
    category: str = "major"
    tracking: bool = True
    priority: int = 1
    intervals: List[str] = ["1d", "1h"]
    notes: str = ""

@app.post("/api/stock-indices")
async def add_stock_index_tracking(index_request: StockIndexRequest):
    """Add a new stock index to tracking"""
    api_requests.labels(endpoint='/api/stock-indices', method='POST').inc()
    
    with response_time.labels(endpoint='/api/stock-indices').time():
        try:
            from models import SymbolTracking
            
            index_tracking = SymbolTracking(
                id=index_request.symbol,
                symbol=index_request.symbol,
                base_asset=index_request.full_name,
                quote_asset=index_request.region.upper(),
                tracking=index_request.tracking,
                asset_type="stock_index",
                exchange="global_markets",
                priority=index_request.priority,
                intervals=index_request.intervals,
                notes=f"{index_request.category} {index_request.region} index - {index_request.notes}"
            )
            
            success = await database.add_symbol_tracking(index_tracking)
            
            if success:
                return {
                    "success": True,
                    "message": f"Stock index {index_request.symbol} added to tracking",
                    "index": index_request.symbol
                }
            else:
                raise HTTPException(status_code=409, detail="Stock index already exists or could not be added")
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Error adding stock index", index=index_request.symbol, error=str(e))
            raise HTTPException(status_code=500, detail="Internal server error")

class StockIndexUpdateRequest(BaseModel):
    tracking: Optional[bool] = None
    priority: Optional[int] = None
    intervals: Optional[List[str]] = None
    category: Optional[str] = None
    region: Optional[str] = None
    full_name: Optional[str] = None
    notes: Optional[str] = None

@app.put("/api/stock-indices/{symbol}")
async def update_stock_index_tracking(
    symbol: str = Path(..., description="Stock index symbol to update"),
    update_request: StockIndexUpdateRequest = None
):
    """Update stock index tracking configuration"""
    api_requests.labels(endpoint='/api/stock-indices/{symbol}', method='PUT').inc()
    
    with response_time.labels(endpoint='/api/stock-indices/{symbol}').time():
        try:
            # Build metadata updates
            metadata = {}
            regular_updates = {}
            
            if update_request.tracking is not None:
                regular_updates['tracking'] = update_request.tracking
            if update_request.priority is not None:
                regular_updates['priority'] = update_request.priority
            if update_request.intervals is not None:
                regular_updates['intervals'] = update_request.intervals
            if update_request.notes is not None:
                regular_updates['notes'] = update_request.notes
                
            # Handle metadata updates separately
            if update_request.category is not None:
                metadata['category'] = update_request.category
            if update_request.region is not None:
                metadata['region'] = update_request.region
            if update_request.full_name is not None:
                metadata['full_name'] = update_request.full_name
                
            success = True
            
            # Apply regular updates
            if regular_updates:
                success = await database.update_symbol_tracking(symbol, regular_updates)
                
            # Apply metadata updates
            if metadata and success:
                success = await database.update_stock_index_metadata(symbol, metadata)
            
            if not regular_updates and not metadata:
                raise HTTPException(status_code=400, detail="No valid updates provided")
            
            if success:
                return {
                    "success": True,
                    "message": f"Stock index {symbol} updated",
                    "updates": list(regular_updates.keys()) + list(metadata.keys())
                }
            else:
                raise HTTPException(status_code=404, detail="Stock index not found")
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Error updating stock index", symbol=symbol, error=str(e))
            raise HTTPException(status_code=500, detail="Internal server error")

@app.delete("/api/stock-indices/{symbol}")
async def remove_stock_index_tracking(symbol: str = Path(..., description="Stock index symbol to remove")):
    """Remove stock index from tracking"""
    api_requests.labels(endpoint='/api/stock-indices/{symbol}', method='DELETE').inc()
    
    with response_time.labels(endpoint='/api/stock-indices/{symbol}').time():
        try:
            success = await database.remove_symbol_tracking(symbol)
            
            if success:
                return {
                    "success": True,
                    "message": f"Stock index {symbol} removed from tracking"
                }
            else:
                raise HTTPException(status_code=404, detail="Stock index not found")
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Error removing stock index", symbol=symbol, error=str(e))
            raise HTTPException(status_code=500, detail="Internal server error")

@app.put("/api/stock-indices/{symbol}/tracking")
async def toggle_stock_index_tracking(
    symbol: str = Path(..., description="Stock index symbol to toggle"),
    tracking: bool = Query(..., description="Enable or disable tracking")
):
    """Enable or disable tracking for a stock index"""
    api_requests.labels(endpoint='/api/stock-indices/{symbol}/tracking', method='PUT').inc()
    
    with response_time.labels(endpoint='/api/stock-indices/{symbol}/tracking').time():
        try:
            success = await database.set_symbol_tracking(symbol, tracking)
            
            if success:
                status = "enabled" if tracking else "disabled"
                return {
                    "success": True,
                    "message": f"Tracking {status} for stock index {symbol}",
                    "index": symbol,
                    "tracking": tracking
                }
            else:
                raise HTTPException(status_code=404, detail="Stock index not found")
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Error toggling stock index tracking", symbol=symbol, error=str(e))
            raise HTTPException(status_code=500, detail="Internal server error")

# Sentiment Analysis Endpoints
@app.get("/api/sentiment")
async def get_sentiment_data(
    symbol: Optional[str] = Query(None, description="Specific symbol (optional)"),
    hours_back: int = Query(24, ge=1, le=168, description="Hours of sentiment data")
):
    """Get sentiment analysis data"""
    api_requests.labels(endpoint='sentiment', method='GET').inc()
    
    with response_time.labels(endpoint='sentiment').time():
        try:
            sentiment_data = await database.get_sentiment_data(
                symbol=symbol,
                hours_back=hours_back
            )
            
            return {
                "symbol": symbol,
                "hours_back": hours_back,
                "data": sentiment_data,
                "count": len(sentiment_data),
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error("Error fetching sentiment data", error=str(e))
            raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/api/sentiment/global")
async def get_global_sentiment():
    """Get global market and crypto sentiment"""
    api_requests.labels(endpoint='global_sentiment', method='GET').inc()
    
    with response_time.labels(endpoint='global_sentiment').time():
        try:
            global_sentiment = await database.get_global_sentiment()
            
            return {
                "global_crypto_sentiment": global_sentiment.get("crypto", {}),
                "global_market_sentiment": global_sentiment.get("market", {}),
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error("Error fetching global sentiment", error=str(e))
            raise HTTPException(status_code=500, detail="Internal server error")

# Market Correlation Endpoints
@app.get("/api/correlation")
async def get_correlation_data(
    hours_back: int = Query(24, ge=1, le=168, description="Hours of correlation data")
):
    """Get market correlation analysis data"""
    api_requests.labels(endpoint='correlation', method='GET').inc()
    
    with response_time.labels(endpoint='correlation').time():
        try:
            correlation_data = await database.get_correlation_data(hours_back=hours_back)
            
            return {
                "hours_back": hours_back,
                "data": correlation_data,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error("Error fetching correlation data", error=str(e))
            raise HTTPException(status_code=500, detail="Internal server error")

# Real-time Data Summary Endpoint  
@app.get("/api/market-summary")
async def get_market_summary():
    """Get comprehensive market data summary"""
    api_requests.labels(endpoint='market_summary', method='GET').inc()
    
    with response_time.labels(endpoint='market_summary').time():
        try:
            # Get latest data from various sources
            latest_prices = await database.get_latest_prices_all_symbols()
            sentiment_summary = await database.get_global_sentiment()
            stock_indices = await database.get_latest_stock_indices()
            correlation_summary = await database.get_correlation_data(hours_back=1)
            
            return {
                "market_data": {
                    "total_symbols": len(latest_prices),
                    "latest_prices": latest_prices,
                    "last_update": datetime.now().isoformat()
                },
                "sentiment": sentiment_summary,
                "stock_indices": stock_indices,
                "correlation": correlation_summary,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error("Error generating market summary", error=str(e))
            raise HTTPException(status_code=500, detail="Internal server error")

# Technical Indicator Endpoints
@app.post("/api/indicators/calculate")
async def calculate_single_indicator(config: IndicatorConfiguration):
    """Calculate a single technical indicator"""
    api_requests.labels(endpoint='calculate_indicator', method='POST').inc()
    
    with response_time.labels(endpoint='calculate_indicator').time():
        try:
            result = await indicator_calculator.calculate_indicator(config)
            return result.dict()
            
        except Exception as e:
            logger.error("Error calculating indicator", error=str(e))
            raise HTTPException(status_code=500, detail=f"Calculation error: {str(e)}")

@app.post("/api/indicators/bulk-calculate")
async def calculate_bulk_indicators(request: BulkIndicatorRequest):
    """Calculate multiple technical indicators efficiently"""
    api_requests.labels(endpoint='bulk_calculate_indicators', method='POST').inc()
    
    with response_time.labels(endpoint='bulk_calculate_indicators').time():
        try:
            results = await indicator_calculator.calculate_bulk_indicators(request)
            return {
                "strategy_id": request.strategy_id,
                "results": [result.dict() for result in results],
                "total_results": len(results)
            }
            
        except Exception as e:
            logger.error("Error calculating bulk indicators", error=str(e))
            raise HTTPException(status_code=500, detail=f"Bulk calculation error: {str(e)}")

# Database-driven Indicator Configuration Endpoints
@app.post("/api/indicators/configurations")
async def create_indicator_configuration(config: Dict[str, Any]):
    """Create a new indicator configuration in database"""
    api_requests.labels(endpoint='create_indicator_config', method='POST').inc()
    
    with response_time.labels(endpoint='create_indicator_config').time():
        try:
            from models import IndicatorConfigurationDB
            
            # Convert to database model
            db_config = IndicatorConfigurationDB(**config)
            
            # Store in database
            success = await database.create_indicator_configuration(db_config)
            
            if success:
                return {
                    "status": "success",
                    "configuration_id": db_config.id,
                    "message": "Configuration created successfully"
                }
            else:
                raise HTTPException(status_code=409, detail="Configuration already exists")
            
        except Exception as e:
            logger.error("Error creating indicator configuration", error=str(e))
            raise HTTPException(status_code=500, detail=f"Configuration creation error: {str(e)}")

@app.get("/api/indicators/configurations")
async def get_indicator_configurations(
    strategy_id: str = Query(None, description="Filter by strategy ID"),
    active_only: bool = Query(True, description="Only return active configurations")
):
    """Get indicator configurations from database"""
    api_requests.labels(endpoint='get_indicator_configs', method='GET').inc()
    
    with response_time.labels(endpoint='get_indicator_configs').time():
        try:
            if strategy_id:
                configs = await database.get_active_indicator_configurations(strategy_id)
            else:
                configs = await database.get_active_indicator_configurations()
            
            return {
                "strategy_id": strategy_id,
                "active_only": active_only,
                "configurations": configs,
                "count": len(configs)
            }
            
        except Exception as e:
            logger.error("Error getting indicator configurations", error=str(e))
            raise HTTPException(status_code=500, detail=f"Configuration retrieval error: {str(e)}")

@app.get("/api/indicators/configurations/{config_id}")
async def get_indicator_configuration(
    config_id: str = Path(description="Configuration ID"),
    strategy_id: str = Query(description="Strategy ID (required for partition key)")
):
    """Get a specific indicator configuration"""
    api_requests.labels(endpoint='get_indicator_config', method='GET').inc()
    
    with response_time.labels(endpoint='get_indicator_config').time():
        try:
            config = await database.get_indicator_configuration(config_id, strategy_id)
            
            if not config:
                raise HTTPException(status_code=404, detail="Configuration not found")
            
            return config
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Error getting indicator configuration", config_id=config_id, error=str(e))
            raise HTTPException(status_code=500, detail=f"Configuration retrieval error: {str(e)}")

@app.put("/api/indicators/configurations/{config_id}")
async def update_indicator_configuration(
    config_id: str = Path(description="Configuration ID"),
    strategy_id: str = Query(description="Strategy ID (required for partition key)"),
    updates: Dict[str, Any] = None
):
    """Update an indicator configuration"""
    api_requests.labels(endpoint='update_indicator_config', method='PUT').inc()
    
    with response_time.labels(endpoint='update_indicator_config').time():
        try:
            success = await database.update_indicator_configuration(config_id, strategy_id, updates)
            
            if success:
                return {
                    "status": "success",
                    "configuration_id": config_id,
                    "message": "Configuration updated successfully"
                }
            else:
                raise HTTPException(status_code=404, detail="Configuration not found")
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Error updating indicator configuration", config_id=config_id, error=str(e))
            raise HTTPException(status_code=500, detail=f"Configuration update error: {str(e)}")

@app.delete("/api/indicators/configurations/{config_id}")
async def delete_indicator_configuration(
    config_id: str = Path(description="Configuration ID"),
    strategy_id: str = Query(description="Strategy ID (required for partition key)")
):
    """Delete an indicator configuration"""
    api_requests.labels(endpoint='delete_indicator_config', method='DELETE').inc()
    
    with response_time.labels(endpoint='delete_indicator_config').time():
        try:
            success = await database.delete_indicator_configuration(config_id, strategy_id)
            
            if success:
                return {
                    "status": "success",
                    "configuration_id": config_id,
                    "message": "Configuration deleted successfully"
                }
            else:
                raise HTTPException(status_code=404, detail="Configuration not found")
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Error deleting indicator configuration", config_id=config_id, error=str(e))
            raise HTTPException(status_code=500, detail=f"Configuration deletion error: {str(e)}")

@app.get("/api/indicators/results/{symbol}")
async def get_indicator_results(
    symbol: str = Path(description="Trading symbol"),
    configuration_id: str = Query(None, description="Filter by configuration ID"),
    hours_back: int = Query(24, ge=1, le=168, description="Hours of history"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum results")
):
    """Get indicator calculation results from database"""
    api_requests.labels(endpoint='get_indicator_results', method='GET').inc()
    
    with response_time.labels(endpoint='get_indicator_results').time():
        try:
            if configuration_id:
                results = await database.get_indicator_results_history(
                    configuration_id, symbol, hours_back, limit
                )
            else:
                # Get latest results for all configurations of this symbol
                latest_result = await database.get_latest_indicator_result("", symbol)
                results = [latest_result] if latest_result else []
            
            return {
                "symbol": symbol,
                "configuration_id": configuration_id,
                "hours_back": hours_back,
                "results": results,
                "count": len(results)
            }
            
        except Exception as e:
            logger.error("Error getting indicator results", symbol=symbol, error=str(e))
            raise HTTPException(status_code=500, detail=f"Results retrieval error: {str(e)}")

@app.get("/api/indicators/performance")
async def get_indicator_performance():
    """Get indicator calculation performance metrics"""
    api_requests.labels(endpoint='indicator_performance', method='GET').inc()
    
    try:
        cache_stats = indicator_calculator.get_cache_statistics()
        
        return {
            "cache_statistics": cache_stats,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error("Error fetching indicator performance", error=str(e))
        raise HTTPException(status_code=500, detail="Performance metrics error")

@app.get("/api/indicators/strategies")
async def get_strategies_with_indicators():
    """Get list of strategies that have indicator configurations"""
    api_requests.labels(endpoint='get_strategies', method='GET').inc()
    
    try:
        configs = await database.get_active_indicator_configurations()
        
        # Group by strategy
        strategies = {}
        for config in configs:
            strategy_id = config['strategy_id']
            if strategy_id not in strategies:
                strategies[strategy_id] = {
                    'strategy_id': strategy_id,
                    'strategy_name': config.get('strategy_name', ''),
                    'strategy_version': config.get('strategy_version', '1.0'),
                    'configuration_count': 0,
                    'symbols': set(),
                    'indicator_types': set()
                }
            
            strategies[strategy_id]['configuration_count'] += 1
            strategies[strategy_id]['symbols'].add(config['symbol'])
            strategies[strategy_id]['indicator_types'].add(config['indicator_type'])
        
        # Convert sets to lists for JSON serialization
        for strategy in strategies.values():
            strategy['symbols'] = list(strategy['symbols'])
            strategy['indicator_types'] = list(strategy['indicator_types'])
        
        return {
            "strategies": list(strategies.values()),
            "total_strategies": len(strategies)
        }
        
    except Exception as e:
        logger.error("Error getting strategies with indicators", error=str(e))
        raise HTTPException(status_code=500, detail="Strategies retrieval error")


@app.post("/api/collect-historical-data")
async def trigger_historical_data_collection(
    symbols: List[str] = Query(..., description="List of symbols to collect data for"),
    timeframes: List[str] = Query(default=["1h", "4h", "1d"], description="Timeframes to collect"),
    days_back: int = Query(default=30, description="Days of historical data to collect")
):
    """
    Trigger historical data collection for specified symbols
    
    This endpoint is called by Strategy Service when it selects cryptos for trading
    to ensure sufficient historical data is available in Cosmos DB.
    """
    try:
        api_requests.labels(endpoint='collect_historical_data', method='POST').inc()
        
        logger.info("Historical data collection requested", 
                   symbols=symbols, timeframes=timeframes, days_back=days_back)
        
        from historical_data_collector import HistoricalDataCollector
        
        collector = HistoricalDataCollector(database)
        await collector.connect()
        
        results = {}
        total_records = 0
        
        for symbol in symbols:
            symbol_results = {}
            
            for timeframe in timeframes:
                try:
                    logger.info(f"Collecting {symbol} - {timeframe}", days_back=days_back)
                    
                    record_count = await collector.collect_historical_data_for_symbol(
                        symbol=symbol,
                        interval=timeframe,
                        days_back=days_back
                    )
                    
                    symbol_results[timeframe] = {
                        'status': 'success',
                        'records_collected': record_count
                    }
                    total_records += record_count
                    
                    logger.info(f"Collected {record_count} records for {symbol} - {timeframe}")
                    
                except Exception as e:
                    logger.error(f"Error collecting {symbol} - {timeframe}", error=str(e))
                    symbol_results[timeframe] = {
                        'status': 'error',
                        'error': str(e),
                        'records_collected': 0
                    }
                
                # Rate limiting between requests
                await asyncio.sleep(0.2)
            
            results[symbol] = symbol_results
        
        await collector.disconnect()
        
        return {
            "status": "completed",
            "total_records": total_records,
            "symbols_processed": len(symbols),
            "timeframes_processed": len(timeframes),
            "results": results,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error("Historical data collection failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Collection failed: {str(e)}")


@app.get("/api/historical-data-status/{symbol}")
async def get_historical_data_status(
    symbol: str = Path(..., description="Trading symbol"),
    timeframe: str = Query(default="1h", description="Timeframe to check")
):
    """
    Check if sufficient historical data exists for a symbol
    """
    try:
        api_requests.labels(endpoint='historical_data_status', method='GET').inc()
        
        # Check last 30 days of data
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(days=30)
        
        query = f"""
        SELECT COUNT(1) as record_count, MIN(c.timestamp) as earliest, MAX(c.timestamp) as latest
        FROM c 
        WHERE c.symbol = '{symbol}' 
        AND c.interval = '{timeframe}'
        AND c.timestamp >= '{start_time.isoformat()}'
        """
        
        items = await database.query_market_data(query)
        
        if items:
            item = items[0]
            has_sufficient_data = item.get('record_count', 0) > 100  # At least 100 data points
            
            return {
                "symbol": symbol,
                "timeframe": timeframe,
                "has_sufficient_data": has_sufficient_data,
                "record_count": item.get('record_count', 0),
                "earliest_data": item.get('earliest'),
                "latest_data": item.get('latest'),
                "days_covered": (datetime.fromisoformat(item['latest'].replace('Z', '+00:00')) - 
                               datetime.fromisoformat(item['earliest'].replace('Z', '+00:00'))).days if item.get('latest') and item.get('earliest') else 0
            }
        else:
            return {
                "symbol": symbol,
                "timeframe": timeframe,
                "has_sufficient_data": False,
                "record_count": 0,
                "message": "No historical data found"
            }
            
    except Exception as e:
        logger.error("Error checking historical data status", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    uvicorn.run(
        "data_access_api:app",
        host="0.0.0.0",
        port=8005,
        log_level=settings.LOG_LEVEL.lower(),
        reload=False
    )