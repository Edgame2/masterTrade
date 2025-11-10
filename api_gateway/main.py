"""
API Gateway - REST API and WebSocket gateway for MasterTrade

Provides unified API access to all trading bot services.
"""

import asyncio
import json
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional

import structlog
from fastapi import FastAPI, HTTPException, Depends, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import Counter, Histogram, CollectorRegistry, generate_latest
import uvicorn

from config import settings

# Select between real Cosmos database and optional mock development store
USE_MOCK_DATABASE = os.getenv("USE_MOCK_DATABASE", "false").lower() == "true"

if USE_MOCK_DATABASE:
    from mock_database import Database
else:
    from database import Database

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

if USE_MOCK_DATABASE:
    logger.warning("Using mock API gateway database; Cosmos DB connectivity disabled")
else:
    logger.info("Using Azure Cosmos DB for API gateway data access")

# Metrics - Clear registry to avoid conflicts
from prometheus_client import CollectorRegistry, REGISTRY
registry = CollectorRegistry()

# Create metrics with unique names
api_requests = Counter('gateway_api_requests_total', 'Total API requests', ['method', 'endpoint', 'status'], registry=registry)
request_duration = Histogram('gateway_request_duration_seconds', 'Request duration', registry=registry)

# FastAPI app
app = FastAPI(
    title="MasterTrade API Gateway",
    description="Unified API for the MasterTrade crypto trading bot",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # React frontend
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database instance
database = Database()

# WebSocket connections manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except:
                # Remove broken connections
                self.active_connections.remove(connection)

manager = ConnectionManager()

@app.on_event("startup")
async def startup_event():
    """Initialize database connection"""
    await database.connect()
    logger.info("API Gateway started")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    await database.disconnect()
    logger.info("API Gateway stopped")

# Health check
@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "api_gateway"}

# Metrics endpoint
@app.get("/metrics")
async def metrics():
    from prometheus_client import CONTENT_TYPE_LATEST
    return Response(generate_latest(registry), media_type=CONTENT_TYPE_LATEST)

# Dashboard data endpoints
@app.get("/api/dashboard/overview")
async def get_dashboard_overview():
    """Get dashboard overview data"""
    try:
        overview = await database.get_dashboard_overview()
        return overview
    except Exception as e:
        logger.error("Error getting dashboard overview", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/api/portfolio/balance")
async def get_portfolio_balance():
    """Get current portfolio balance"""
    try:
        balance = await database.get_portfolio_balance()
        return balance
    except Exception as e:
        logger.error("Error getting portfolio balance", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/api/strategies")
async def get_strategies():
    """Get all trading strategies"""
    try:
        strategies = await database.get_all_strategies()
        return strategies
    except Exception as e:
        logger.error("Error getting strategies", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/api/orders/active")
async def get_active_orders():
    """Get active orders"""
    try:
        orders = await database.get_active_orders()
        return [order.model_dump() for order in orders]
    except Exception as e:
        logger.error("Error getting active orders", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/api/orders/recent")
async def get_recent_orders(limit: int = 50):
    """Get recent orders"""
    try:
        orders = await database.get_recent_orders(limit)
        return orders
    except Exception as e:
        logger.error("Error getting recent orders", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/api/trades/recent")
async def get_recent_trades(limit: int = 50):
    """Get recent trades"""
    try:
        trades = await database.get_recent_trades(limit)
        return trades
    except Exception as e:
        logger.error("Error getting recent trades", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/api/signals/recent")
async def get_recent_signals(limit: int = 100):
    """Get recent trading signals"""
    try:
        signals = await database.get_recent_signals(limit)
        return signals
    except Exception as e:
        logger.error("Error getting recent signals", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/api/market-data/{symbol}")
async def get_market_data(symbol: str, limit: int = 100):
    """Get market data for a symbol"""
    try:
        data = await database.get_market_data(symbol, limit)
        return data
    except Exception as e:
        logger.error("Error getting market data", symbol=symbol, error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")

# Strategy Environment Management Endpoints
@app.get("/api/strategy-environments")
async def get_strategy_environments():
    """Get all strategy environment configurations"""
    try:
        configs = await database.get_all_strategy_environment_configs()
        return configs
    except Exception as e:
        logger.error("Error getting strategy environments", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/api/strategy-environments/{strategy_id}")
@app.put("/api/strategy-environments/{strategy_id}")
async def set_strategy_environment(strategy_id: int, environment_config: dict):
    """Set environment configuration for a strategy"""
    try:
        # Validate environment
        if environment_config.get("environment") not in ["testnet", "production"]:
            raise HTTPException(status_code=400, detail="Environment must be 'testnet' or 'production'")
            
        # Store configuration
        success = await database.set_strategy_environment(strategy_id, environment_config)
        
        if success:
            return {"success": True, "message": "Strategy environment updated"}
        else:
            raise HTTPException(status_code=404, detail="Strategy not found")
    except Exception as e:
        logger.error("Error setting strategy environment", strategy_id=strategy_id, error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/api/strategy-environments/{strategy_id}")
async def get_strategy_environment_config(strategy_id: int):
    """Get environment configuration for a specific strategy"""
    try:
        config = await database.get_strategy_environment_config(strategy_id)
        if config:
            return config
        else:
            # Return default configuration
            return {
                "strategy_id": strategy_id,
                "environment": "testnet",
                "max_position_size": None,
                "max_daily_trades": None,
                "risk_multiplier": 1.0,
                "enabled": True
            }
    except Exception as e:
        logger.error("Error getting strategy environment config", strategy_id=strategy_id, error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/api/exchange-environments/status")
async def get_exchange_environments_status():
    """Get status of exchange environments (testnet and production)"""
    try:
        # This will query the order executor service for exchange status
        return {
            "testnet": {
                "connected": True,
                "last_ping": "2025-11-07T17:00:00Z",
                "active_orders": 3,
                "balance_available": True
            },
            "production": {
                "connected": True,
                "last_ping": "2025-11-07T17:00:00Z",
                "active_orders": 1,
                "balance_available": True
            }
        }
    except Exception as e:
        logger.error("Error getting exchange environments status", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")

# Crypto/Symbol Management Endpoints
@app.get("/api/symbols")
async def get_all_symbols(include_inactive: bool = False):
    """Get all crypto trading pairs/symbols"""
    try:
        symbols = await database.get_all_symbols(include_inactive=include_inactive)
        return {
            "symbols": symbols,
            "count": len(symbols),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error("Error getting symbols", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/api/symbols/{symbol}")
async def get_symbol_details(symbol: str):
    """Get detailed information about a specific symbol"""
    try:
        symbol_info = await database.get_symbol_tracking_info(symbol.upper())
        if not symbol_info:
            raise HTTPException(status_code=404, detail=f"Symbol {symbol} not found")
        return symbol_info
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting symbol details", symbol=symbol, error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/api/symbols/{symbol}/historical-data")
async def get_symbol_historical_data_stats(symbol: str):
    """Get historical data availability statistics for a symbol"""
    try:
        stats = await database.get_symbol_historical_stats(symbol.upper())
        return stats
    except Exception as e:
        logger.error("Error getting historical data stats", symbol=symbol, error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/api/symbols/{symbol}/toggle-tracking")
async def toggle_symbol_tracking(symbol: str):
    """Toggle tracking status for a symbol (activate/deactivate for trading)"""
    try:
        success = await database.toggle_symbol_tracking(symbol.upper())
        if success:
            symbol_info = await database.get_symbol_tracking_info(symbol.upper())
            return {
                "success": True,
                "message": f"Symbol {symbol} tracking updated",
                "tracking": symbol_info.get("tracking", False) if symbol_info else False
            }
        else:
            raise HTTPException(status_code=404, detail=f"Symbol {symbol} not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error toggling symbol tracking", symbol=symbol, error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")

@app.put("/api/symbols/{symbol}")
async def update_symbol(symbol: str, updates: dict):
    """Update symbol tracking configuration"""
    try:
        success = await database.update_symbol_tracking(symbol.upper(), updates)
        if success:
            return {
                "success": True,
                "message": f"Symbol {symbol} updated successfully"
            }
        else:
            raise HTTPException(status_code=404, detail=f"Symbol {symbol} not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error updating symbol", symbol=symbol, error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")

# Configuration endpoints
@app.post("/api/strategies/{strategy_id}/toggle")
async def toggle_strategy(strategy_id: int):
    """Toggle strategy active status"""
    try:
        success = await database.toggle_strategy_status(strategy_id)
        if success:
            return {"success": True, "message": "Strategy status updated"}
        else:
            raise HTTPException(status_code=404, detail="Strategy not found")
    except Exception as e:
        logger.error("Error toggling strategy", strategy_id=strategy_id, error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/api/system/trading/toggle")
async def toggle_trading():
    """Toggle system trading enabled/disabled"""
    try:
        new_status = await database.toggle_trading_enabled()
        return {"trading_enabled": new_status}
    except Exception as e:
        logger.error("Error toggling trading", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")

# WebSocket endpoint for real-time updates
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive and handle incoming messages
            data = await websocket.receive_text()
            # Echo back for now (can be extended for specific commands)
            await websocket.send_text(f"Received: {data}")
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# Real-time data broadcasting (called by message consumers)
async def broadcast_update(update_type: str, data: dict):
    """Broadcast real-time updates to WebSocket clients"""
    message = {
        "type": update_type,
        "data": data,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    await manager.broadcast(json.dumps(message))

if __name__ == "__main__":
    import os
    port = int(os.getenv("PORT", "8090"))  # Use 8090 as default since 8080 is in use
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        log_level=settings.LOG_LEVEL.lower(),
        reload=False
    )