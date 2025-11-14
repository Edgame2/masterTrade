"""
API Gateway - REST API and WebSocket gateway for MasterTrade

Provides unified API access to all trading bot services.
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from typing import Dict, List, Optional

import aiohttp
import structlog
import socketio
from fastapi import FastAPI, HTTPException, Depends, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import Counter, Histogram, CollectorRegistry, generate_latest
import uvicorn

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from shared.prometheus_metrics import create_instrumentator

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
    description="""
    ## Unified API Gateway for MasterTrade Crypto Trading Bot
    
    This API gateway provides centralized access to all MasterTrade trading services including:
    
    * **Portfolio Management**: Real-time portfolio tracking and balance monitoring
    * **Strategy Management**: Deploy, monitor, and control trading strategies
    * **Market Data**: Access real-time and historical market data
    * **Order Management**: Submit and track trading orders
    * **Risk Management**: Portfolio risk metrics and exposure tracking
    * **Alerts & Notifications**: Configure and manage trading alerts
    * **WebSocket Streams**: Real-time data feeds for prices, trades, and signals
    
    ### Authentication
    
    Most endpoints require authentication via API key or JWT token:
    - API Key: Include `X-API-Key` header
    - JWT Token: Include `Authorization: Bearer <token>` header
    
    ### Rate Limiting
    
    - Unauthenticated: 100 requests/minute
    - Authenticated: 1000 requests/minute
    
    ### Support
    
    - Interactive Docs: [/docs](/docs)
    - Alternative Docs: [/redoc](/redoc)
    - OpenAPI Schema: [/openapi.json](/openapi.json)
    """,
    version="1.0.0",
    terms_of_service="https://mastertrade.com/terms",
    contact={
        "name": "MasterTrade Support",
        "email": "support@mastertrade.com",
        "url": "https://mastertrade.com/support"
    },
    license_info={
        "name": "Proprietary",
        "url": "https://mastertrade.com/license"
    },
    openapi_tags=[
        {
            "name": "Health",
            "description": "Health check and monitoring endpoints"
        },
        {
            "name": "Dashboard",
            "description": "Dashboard overview and summary data"
        },
        {
            "name": "Portfolio",
            "description": "Portfolio balance and position management"
        },
        {
            "name": "Strategies",
            "description": "Trading strategy management and deployment"
        },
        {
            "name": "Orders",
            "description": "Order submission and tracking"
        },
        {
            "name": "Trades",
            "description": "Trade history and execution details"
        },
        {
            "name": "Signals",
            "description": "Trading signals and indicators"
        },
        {
            "name": "Market Data",
            "description": "Real-time and historical market data"
        },
        {
            "name": "Symbols",
            "description": "Trading pair management and configuration"
        },
        {
            "name": "Strategy Environments",
            "description": "Strategy deployment environments (paper/live)"
        },
        {
            "name": "Exchange Environments",
            "description": "Exchange connection and health status"
        }
    ]
)

# Add Prometheus instrumentation
instrumentator = create_instrumentator("api_gateway", "1.0.0")
instrumentator.instrument(app).expose(app)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # React frontend
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Socket.IO server for real-time updates
sio = socketio.AsyncServer(
    async_mode='asgi',
    cors_allowed_origins=["http://localhost:3000"],
    logger=False,
    engineio_logger=False
)

# Wrap with Socket.IO's ASGI middleware
socket_app = socketio.ASGIApp(sio, app)

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
    # Initialize user management
    await user_service.initialize()
    # Add RBAC middleware to app state
    app.state.rbac = rbac
    # Add audit logger to app state
    app.state.audit_logger = audit_logger
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

@app.get("/api/market-data/summary")
async def get_market_data_summary():
    """Get market data coverage summary across all symbols and intervals"""
    try:
        logger.info("Fetching market data summary")
        async with database.pool.acquire() as conn:
            query = """
                SELECT 
                    data->>'symbol' as symbol,
                    data->>'interval' as interval,
                    MIN(data->>'timestamp') as first_timestamp,
                    MAX(data->>'timestamp') as last_timestamp,
                    COUNT(*) as record_count
                FROM market_data
                WHERE data->>'symbol' IS NOT NULL 
                  AND data->>'interval' IS NOT NULL
                GROUP BY data->>'symbol', data->>'interval'
                ORDER BY data->>'symbol', data->>'interval'
            """
            rows = await conn.fetch(query)
            logger.info("Query executed", row_count=len(rows))
            
            summary = []
            for row in rows:
                summary.append({
                    "symbol": row["symbol"],
                    "interval": row["interval"],
                    "first_timestamp": row["first_timestamp"],
                    "last_timestamp": row["last_timestamp"],
                    "record_count": row["record_count"]
                })
            
            logger.info("Returning summary", summary_count=len(summary))
            return {"summary": summary}
    except Exception as e:
        logger.error("Error getting market data summary", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/api/collectors")
async def get_collectors_status():
    """Get market data collectors status"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("http://mastertrade_market_data:8000/collectors") as response:
                if response.status == 200:
                    return await response.json()
                else:
                    raise HTTPException(status_code=response.status, detail="Failed to fetch collectors status")
    except aiohttp.ClientError as e:
        logger.error("Error connecting to market data service", error=str(e))
        raise HTTPException(status_code=503, detail="Market data service unavailable")
    except Exception as e:
        logger.error("Error getting collectors status", error=str(e))
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

# ====================================================================
# Strategy Generation API Proxy Endpoints
# ====================================================================

async def _generate_strategies_impl(request: dict):
    """Implementation for strategy generation (shared by both endpoints)"""
    try:
        import httpx
        
        strategy_service_url = os.getenv("STRATEGY_SERVICE_URL", "http://strategy_service:8006")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{strategy_service_url}/api/v1/strategies/generate",
                json=request
            )
            response.raise_for_status()
            result = response.json()
            
            # Broadcast generation started event
            await broadcast_update("generation_started", result)
            
            return result
            
    except httpx.HTTPError as e:
        logger.error("Strategy service request failed", error=str(e))
        raise HTTPException(status_code=503, detail="Strategy service unavailable")
    except Exception as e:
        logger.error("Error generating strategies", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/api/strategies/generate")
async def generate_strategies(request: dict):
    """
    Generate new trading strategies (proxied to strategy service)
    
    Request body:
    {
        "num_strategies": 100,  // Number of strategies to generate
        "config": {}  // Optional configuration
    }
    """
    return await _generate_strategies_impl(request)

@app.post("/api/v1/strategies/generate")
async def generate_strategies_v1(request: dict):
    """
    Generate new trading strategies - v1 API (proxied to strategy service)
    
    Request body:
    {
        "num_strategies": 100,  // Number of strategies to generate
        "config": {}  // Optional configuration
    }
    """
    return await _generate_strategies_impl(request)

@app.get("/api/strategies/jobs/{job_id}/progress")
async def get_generation_progress(job_id: str):
    """Get progress of strategy generation job (proxied to strategy service)"""
    try:
        import httpx
        
        strategy_service_url = os.getenv("STRATEGY_SERVICE_URL", "http://strategy_service:8006")
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{strategy_service_url}/api/v1/strategies/jobs/{job_id}/progress"
            )
            response.raise_for_status()
            progress = response.json()
            
            # Broadcast progress update via Socket.IO
            await sio.emit("generation_progress", {
                "job_id": job_id,
                **progress
            })
            
            return progress
            
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise HTTPException(status_code=404, detail="Generation job not found")
        logger.error("Strategy service request failed", error=str(e))
        raise HTTPException(status_code=503, detail="Strategy service unavailable")
    except Exception as e:
        logger.error("Error getting generation progress", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/api/strategies/jobs/{job_id}/results")
async def get_generation_results(job_id: str):
    """Get results of completed strategy generation job (proxied to strategy service)"""
    try:
        import httpx
        
        strategy_service_url = os.getenv("STRATEGY_SERVICE_URL", "http://strategy_service:8006")
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{strategy_service_url}/api/v1/strategies/jobs/{job_id}/results"
            )
            response.raise_for_status()
            results = response.json()
            
            # Broadcast results available event
            await broadcast_update("generation_completed", {
                "job_id": job_id,
                "total_strategies": results.get("total_strategies"),
                "strategies_passed": results.get("strategies_passed")
            })
            
            return results
            
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise HTTPException(status_code=404, detail="Generation job not found or not completed")
        logger.error("Strategy service request failed", error=str(e))
        raise HTTPException(status_code=503, detail="Strategy service unavailable")
    except Exception as e:
        logger.error("Error getting generation results", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/api/strategies/jobs")
async def list_generation_jobs(
    status_filter: Optional[str] = None,
    limit: int = 50
):
    """List all strategy generation jobs (proxied to strategy service)"""
    try:
        import httpx
        
        strategy_service_url = os.getenv("STRATEGY_SERVICE_URL", "http://strategy_service:8006")
        
        params = {"limit": limit}
        if status_filter:
            params["status_filter"] = status_filter
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{strategy_service_url}/api/v1/strategies/jobs",
                params=params
            )
            response.raise_for_status()
            return response.json()
            
    except httpx.HTTPError as e:
        logger.error("Strategy service request failed", error=str(e))
        raise HTTPException(status_code=503, detail="Strategy service unavailable")
    except Exception as e:
        logger.error("Error listing generation jobs", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")

@app.delete("/api/strategies/jobs/{job_id}")
async def cancel_generation_job(job_id: str):
    """Cancel a running strategy generation job (proxied to strategy service)"""
    try:
        import httpx
        
        strategy_service_url = os.getenv("STRATEGY_SERVICE_URL", "http://strategy_service:8006")
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.delete(
                f"{strategy_service_url}/api/v1/strategies/jobs/{job_id}"
            )
            response.raise_for_status()
            result = response.json()
            
            # Broadcast cancellation event
            await broadcast_update("generation_cancelled", {
                "job_id": job_id
            })
            
            return result
            
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise HTTPException(status_code=404, detail="Generation job not found")
        logger.error("Strategy service request failed", error=str(e))
        raise HTTPException(status_code=503, detail="Strategy service unavailable")
    except Exception as e:
        logger.error("Error cancelling generation job", error=str(e))
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

@app.post("/api/system/toggle-trading")
async def toggle_trading():
    """Toggle system trading enabled/disabled"""
    try:
        new_status = await database.toggle_trading_enabled()
        return {"trading_enabled": new_status}
    except Exception as e:
        logger.error("Error toggling trading", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")

# ==================== User Management API ====================
from user_management import (
    UserManagementService,
    CreateUserRequest,
    UpdateUserRequest,
    UserRole,
    UserStatus
)
from rbac_middleware import (
    RBACMiddleware,
    Permission,
    require_permissions,
    require_role
)
from audit_logger import (
    AuditLogger,
    AuditAction,
    ResourceType
)

# Initialize user management service
user_service = UserManagementService(database)

# Initialize RBAC middleware
rbac = RBACMiddleware(user_service)

# Initialize audit logger
audit_logger = AuditLogger(user_service)

@app.post("/api/v1/users", status_code=201)
@require_permissions(Permission.USER_CREATE)
async def create_user(request: Request, create_request: CreateUserRequest):
    """Create a new user"""
    try:
        # Get user info from request state (set by RBAC decorator)
        creator_email = request.state.user.get("email", "system")
        user = await user_service.create_user(create_request, created_by=creator_email)
        return user.dict()
    except Exception as e:
        logger.error("Error creating user", error=str(e))
        if "unique constraint" in str(e).lower():
            raise HTTPException(status_code=400, detail="User with this email already exists")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/api/v1/users")
@require_permissions(Permission.USER_LIST)
async def list_users(
    request: Request,
    role: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0
):
    """List users with optional filters"""
    try:
        role_enum = UserRole(role) if role else None
        status_enum = UserStatus(status) if status else None
        
        users = await user_service.list_users(
            role=role_enum,
            status=status_enum,
            limit=limit,
            offset=offset
        )
        return {"users": [u.dict() for u in users], "count": len(users)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid role or status: {str(e)}")
    except Exception as e:
        logger.error("Error listing users", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/api/v1/users/{user_id}")
@require_permissions(Permission.USER_READ)
async def get_user(request: Request, user_id: str):
    """Get user by ID"""
    try:
        user = await user_service.get_user(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return user.dict()
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting user", error=str(e), user_id=user_id)
        raise HTTPException(status_code=500, detail="Internal server error")

@app.put("/api/v1/users/{user_id}")
@require_permissions(Permission.USER_UPDATE)
async def update_user(request: Request, user_id: str, update_request: UpdateUserRequest):
    """Update user"""
    try:
        updater_email = request.state.user.get("email", "system")
        user = await user_service.update_user(user_id, update_request, updated_by=updater_email)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return user.dict()
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error updating user", error=str(e), user_id=user_id)
        raise HTTPException(status_code=500, detail="Internal server error")

@app.delete("/api/v1/users/{user_id}")
@require_permissions(Permission.USER_DELETE)
async def delete_user(request: Request, user_id: str):
    """Delete (soft delete) user"""
    try:
        deleter_email = request.state.user.get("email", "system")
        success = await user_service.delete_user(user_id, deleted_by=deleter_email)
        if not success:
            raise HTTPException(status_code=404, detail="User not found")
        return {"success": True, "message": "User deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error deleting user", error=str(e), user_id=user_id)
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/api/v1/users/{user_id}/reset-password")
@require_role(UserRole.ADMIN)  # Only admins can reset passwords
async def reset_password(request: Request, user_id: str, new_password: str):
    """Reset user password"""
    try:
        user = await user_service.get_user(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Ensure connection
        if not database._connected:
            await database.connect()
        
        # Update password
        password_hash = UserManagementService.hash_password(new_password)
        await database._postgres.execute("""
            UPDATE users SET password_hash = $1, updated_at = NOW()
            WHERE id = $2
        """, password_hash, int(user_id))
        
        # Log audit
        admin_email = request.state.user.get("email", "system")
        await user_service.log_audit(
            user_id=request.state.user.get("user_id", "system"),
            user_email=admin_email,
            action="reset_password",
            resource_type="user",
            resource_id=user_id
        )
        
        return {"success": True, "message": "Password reset successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error resetting password", error=str(e), user_id=user_id)
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/api/v1/users/{user_id}/activities")
@require_permissions(Permission.USER_READ)
async def get_user_activities(request: Request, user_id: str, limit: int = 50):
    """Get user activities"""
    try:
        activities = await user_service.get_user_activities(user_id, limit)
        return {"activities": [a.dict() for a in activities], "count": len(activities)}
    except Exception as e:
        logger.error("Error getting user activities", error=str(e), user_id=user_id)
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/api/v1/audit-logs")
@require_permissions(Permission.AUDIT_READ)
async def get_audit_logs(
    request: Request,
    user_id: Optional[str] = None,
    resource_type: Optional[str] = None,
    limit: int = 100
):
    """Get audit logs with optional filters"""
    try:
        logs = await user_service.get_audit_logs(
            user_id=user_id,
            resource_type=resource_type,
            limit=limit
        )
        return {"logs": [l.dict() for l in logs], "count": len(logs)}
    except Exception as e:
        logger.error("Error getting audit logs", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/api/v1/audit/recent-actions")
@require_permissions(Permission.AUDIT_READ)
async def get_recent_audit_actions(
    request: Request,
    user_id: Optional[str] = None,
    resource_type: Optional[str] = None,
    action: Optional[str] = None,
    limit: int = 50
):
    """Get recent audit actions with filters"""
    try:
        resource_type_enum = ResourceType(resource_type) if resource_type else None
        action_enum = AuditAction(action) if action else None
        
        actions = await audit_logger.get_recent_actions(
            user_id=user_id,
            resource_type=resource_type_enum,
            action=action_enum,
            limit=limit
        )
        return {"actions": actions, "count": len(actions)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid resource_type or action: {str(e)}")
    except Exception as e:
        logger.error("Error getting recent audit actions", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/api/v1/audit/user-activity-summary/{user_id}")
@require_permissions(Permission.AUDIT_READ)
async def get_user_activity_summary_endpoint(
    request: Request,
    user_id: str,
    hours: int = 24
):
    """Get user activity summary for specified period"""
    try:
        summary = await audit_logger.get_user_activity_summary(user_id, hours)
        return summary
    except Exception as e:
        logger.error("Error getting user activity summary", error=str(e), user_id=user_id)
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/api/v1/audit/statistics")
@require_role(UserRole.ADMIN)
async def get_audit_statistics(request: Request, days: int = 7):
    """Get audit log statistics for the specified period"""
    try:
        # Get all audit logs for the period
        logs = await user_service.get_audit_logs(limit=10000)
        
        # Calculate statistics
        total_actions = len(logs)
        actions_by_type = {}
        actions_by_user = {}
        actions_by_resource = {}
        
        for log in logs:
            # Count by action type
            action = log.action
            actions_by_type[action] = actions_by_type.get(action, 0) + 1
            
            # Count by user
            user = log.user_email
            actions_by_user[user] = actions_by_user.get(user, 0) + 1
            
            # Count by resource type
            resource = log.resource_type
            actions_by_resource[resource] = actions_by_resource.get(resource, 0) + 1
        
        return {
            "period_days": days,
            "total_actions": total_actions,
            "actions_by_type": actions_by_type,
            "actions_by_user": actions_by_user,
            "actions_by_resource": actions_by_resource,
            "top_users": sorted(actions_by_user.items(), key=lambda x: x[1], reverse=True)[:10],
            "top_actions": sorted(actions_by_type.items(), key=lambda x: x[1], reverse=True)[:10]
        }
    except Exception as e:
        logger.error("Error getting audit statistics", error=str(e))
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
    # Also broadcast to Socket.IO clients
    await sio.emit(update_type, message)

# Socket.IO event handlers
@sio.event
async def connect(sid, environ):
    """Handle Socket.IO client connection"""
    logger.info("Socket.IO client connected", sid=sid)

@sio.event
async def disconnect(sid):
    """Handle Socket.IO client disconnection"""
    logger.info("Socket.IO client disconnected", sid=sid)

@sio.event
async def subscribe(sid, data):
    """Handle subscription to specific data streams"""
    logger.info("Client subscribed", sid=sid, data=data)
    # You can implement room-based subscriptions here
    # await sio.enter_room(sid, data.get('room'))

if __name__ == "__main__":
    import os
    port = int(os.getenv("PORT", "8080"))  # Use configured port
    uvicorn.run(
        "main:socket_app",
        host="0.0.0.0",
        port=port,
        log_level=settings.LOG_LEVEL.lower(),
        reload=False
    )