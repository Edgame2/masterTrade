"""
Simple Order Executor Service - Without Pydantic
Handles order execution, trade management, and position tracking
"""

import asyncio
import json
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any

import uvicorn
from fastapi import FastAPI, HTTPException, status, Query
from fastapi.middleware.cors import CORSMiddleware

# Configure basic logging
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Use mock database for development
USE_MOCK_DATABASE = True
if USE_MOCK_DATABASE:
    from mock_database import Database
    from mock_components import ExchangeManager, EnvironmentConfigManager, OrderManager
    print("🔧 Using mock order executor components for development")
else:
    from database import Database
    from exchange_manager import ExchangeManager
    from strategy_environment_manager import EnvironmentConfigManager

# FastAPI app
app = FastAPI(
    title="MasterTrade Order Executor Service",
    description="Complete Order Execution and Trade Management System",
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

class SimpleOrderExecutorService:
    """Simple Order Executor Service with full functionality"""
    
    def __init__(self):
        self.database = Database()
        self.exchange_manager = ExchangeManager()
        self.environment_manager = EnvironmentConfigManager()
        self.order_manager = OrderManager()
        
        self.running = False
        
        # Execution tracking
        self.active_orders: Dict[str, Dict] = {}
        self.execution_history: List[Dict] = []
        self.position_tracking: Dict[str, Dict] = {}
        
        # Performance metrics
        self.execution_stats: Dict[str, Any] = {
            'orders_processed': 0,
            'orders_filled': 0,
            'orders_failed': 0,
            'average_execution_time': 0.0,
            'total_volume': 0.0
        }
        
    async def initialize(self):
        """Initialize the order executor service"""
        try:
            # Connect to database
            await self.database.connect()
            logger.info("Order executor database connected")
            
            # Initialize exchange manager
            await self.exchange_manager.initialize()
            logger.info("Exchange manager initialized")
            
            # Initialize order manager
            await self.order_manager.initialize(self.database, self.exchange_manager)
            logger.info("Order manager initialized")
            
            # Load active orders
            await self._load_active_orders()
            
            # Start background tasks
            asyncio.create_task(self._order_monitoring_loop())
            asyncio.create_task(self._execution_stats_loop())
            
            self.running = True
            logger.info("Simple Order Executor Service initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize order executor service: {str(e)}")
            raise
    
    async def _load_active_orders(self):
        """Load active orders from database"""
        try:
            orders = await self.database.get_active_orders()
            for order in orders:
                self.active_orders[order['id']] = order
            logger.info(f"Loaded {len(orders)} active orders")
        except Exception as e:
            logger.error(f"Failed to load active orders: {str(e)}")
    
    async def _order_monitoring_loop(self):
        """Monitor active orders for status updates"""
        while self.running:
            try:
                # Update status of all active orders
                for order_id, order in list(self.active_orders.items()):
                    await self._update_order_status(order_id, order)
                
                # Wait before next check
                await asyncio.sleep(5)  # Check every 5 seconds
                
            except Exception as e:
                logger.error(f"Error in order monitoring loop: {str(e)}")
                await asyncio.sleep(2)
    
    async def _update_order_status(self, order_id: str, order: Dict):
        """Update order status from exchange"""
        try:
            # Fetch order status from exchange (mock)
            exchange_data = await self.exchange_manager.fetch_order(
                order.get('exchange_order_id', order_id),
                order['symbol']
            )
            
            # Update order in database if status changed
            if exchange_data['status'] != order.get('status'):
                await self.database.update_order_from_exchange(order_id, exchange_data)
                
                # Update local cache
                order.update({
                    'status': exchange_data['status'],
                    'filled_quantity': exchange_data.get('filled', 0),
                    'average_price': exchange_data.get('average', 0)
                })
                
                # Remove from active orders if completed
                if exchange_data['status'] in ['filled', 'canceled', 'rejected']:
                    self.active_orders.pop(order_id, None)
                    self.execution_stats['orders_filled'] += 1 if exchange_data['status'] == 'filled' else 0
                
                logger.info(f"Order status updated {order_id}: {exchange_data['status']}")
                
        except Exception as e:
            logger.error(f"Failed to update order status {order_id}: {str(e)}")
    
    async def _execution_stats_loop(self):
        """Update execution statistics"""
        while self.running:
            try:
                # Calculate statistics
                stats = await self.database.get_execution_stats()
                self.execution_stats.update(stats)
                
                # Log statistics periodically
                logger.info(f"Execution stats updated: {self.execution_stats}")
                
                await asyncio.sleep(60)  # Update every minute
                
            except Exception as e:
                logger.error(f"Error in stats loop: {str(e)}")
                await asyncio.sleep(30)
    
    async def create_order(self, order_data: Dict) -> Dict:
        """Create and execute a new order"""
        try:
            # Create order in database
            db_order = await self.database.create_order(order_data)
            order_id = db_order['id']
            
            # Submit to exchange
            exchange_result = await self.exchange_manager.create_order(
                environment=order_data.get('environment', 'testnet'),
                symbol=order_data['symbol'],
                order_type=order_data['order_type'],
                side=order_data['side'],
                quantity=order_data['quantity'],
                price=order_data.get('price')
            )
            
            # Update order with exchange data
            updates = {
                'exchange_order_id': exchange_result['id'],
                'status': exchange_result['status'],
                'submitted_at': datetime.now(timezone.utc).isoformat()
            }
            
            await self.database.update_order(order_id, updates)
            
            # Add to active orders
            db_order.update(updates)
            self.active_orders[order_id] = db_order
            
            # Update stats
            self.execution_stats['orders_processed'] += 1
            
            logger.info(f"Order created and submitted {order_id}: {exchange_result['id']}")
            return db_order
            
        except Exception as e:
            logger.error(f"Failed to create order: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))
    
    async def process_signal(self, signal_data: Dict) -> Dict:
        """Process trading signal and create appropriate order"""
        try:
            # Convert signal to order
            side = 'buy' if signal_data['signal_type'].upper() == 'BUY' else 'sell'
            order_type = 'market'  # Default to market order for signals
            
            # Calculate quantity if not provided
            quantity = signal_data.get('quantity')
            if not quantity:
                # Default position size calculation (mock)
                quantity = min(0.001, 1000.0 / signal_data['price'])  # $1000 worth or 0.001 BTC max
            
            # Create order data
            order_data = {
                'strategy_id': signal_data['strategy_id'],
                'symbol': signal_data['symbol'],
                'side': side,
                'order_type': order_type,
                'quantity': quantity,
                'price': signal_data['price'] if order_type == 'limit' else None,
                'metadata': {
                    'signal_strength': signal_data['strength'],
                    'signal_price': signal_data['price'],
                    'auto_generated': True,
                    **signal_data.get('metadata', {})
                }
            }
            
            # Create the order
            result = await self.create_order(order_data)
            
            logger.info(f"Signal processed into order: {signal_data['signal_type']} -> {result['id']}")
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to process signal: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))
    
    async def shutdown(self):
        """Shutdown the order executor service"""
        self.running = False
        
        # Close exchange connections
        if self.exchange_manager:
            await self.exchange_manager.close()
        
        # Close database
        await self.database.disconnect()
        
        logger.info("Order executor service shutdown complete")

# Global service instance
order_executor_service = SimpleOrderExecutorService()

@app.on_event("startup")
async def startup_event():
    await order_executor_service.initialize()

@app.on_event("shutdown")
async def shutdown_event():
    await order_executor_service.shutdown()

# Health endpoints
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "order_executor",
        "version": "2.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "active_orders": len(order_executor_service.active_orders),
        "execution_stats": order_executor_service.execution_stats
    }

@app.get("/")
async def root():
    return {
        "service": "MasterTrade Order Executor Service",
        "version": "2.0.0",
        "status": "running",
        "features": [
            "Order Management", "Exchange Integration", "Position Tracking",
            "Risk Management", "Signal Processing", "Multi-Environment Support"
        ],
        "endpoints": [
            "/health", "/orders", "/trades", "/positions", 
            "/signals", "/config", "/dashboard", "/stats"
        ]
    }

# Order Management Endpoints
@app.post("/orders", status_code=status.HTTP_201_CREATED)
async def create_order(order_data: dict):
    """Create a new order"""
    return await order_executor_service.create_order(order_data)

@app.get("/orders")
async def get_orders(
    status: Optional[str] = Query(None),
    symbol: Optional[str] = Query(None),
    strategy_id: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000)
):
    """Get orders with optional filters"""
    try:
        filters = {}
        if status:
            filters['status'] = status
        if symbol:
            filters['symbol'] = symbol.upper()
        if strategy_id:
            filters['strategy_id'] = strategy_id
            
        orders = await order_executor_service.database.get_orders(**filters)
        return {
            "orders": orders[:limit],
            "total": len(orders),
            "active_count": len(order_executor_service.active_orders),
            "filters": filters
        }
    except Exception as e:
        logger.error(f"Failed to get orders: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/orders/{order_id}")
async def get_order(order_id: str):
    """Get specific order by ID"""
    try:
        order = await order_executor_service.database.get_order(order_id)
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        
        # Add execution logs
        logs = await order_executor_service.database.get_execution_logs(order_id)
        order['execution_logs'] = logs
        
        return order
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get order {order_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/orders/{order_id}")
async def update_order(order_id: str, updates: dict):
    """Update an existing order"""
    try:
        result = await order_executor_service.database.update_order(order_id, updates)
        
        # Update active orders cache
        if order_id in order_executor_service.active_orders:
            order_executor_service.active_orders[order_id].update(updates)
        
        logger.info(f"Order updated: {order_id}")
        return result
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to update order {order_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/orders/{order_id}")
async def cancel_order(order_id: str):
    """Cancel an order"""
    try:
        # Cancel with order manager
        result = await order_executor_service.order_manager.cancel_order(order_id)
        
        # Update database
        await order_executor_service.database.update_order(order_id, {'status': 'canceled'})
        
        # Remove from active orders
        order_executor_service.active_orders.pop(order_id, None)
        
        logger.info(f"Order canceled: {order_id}")
        return result
        
    except Exception as e:
        logger.error(f"Failed to cancel order {order_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Signal Processing Endpoints
@app.post("/signals/process", status_code=status.HTTP_201_CREATED)
async def process_signal(signal_data: dict):
    """Process a trading signal"""
    return await order_executor_service.process_signal(signal_data)

@app.get("/signals/active")
async def get_active_signals():
    """Get currently processing signals"""
    return {
        "active_signals": 0,  # Mock for now
        "signals_processed_today": order_executor_service.execution_stats['orders_processed'],
        "last_update": datetime.now(timezone.utc).isoformat()
    }

# Trade Management Endpoints
@app.get("/trades")
async def get_trades(
    order_id: Optional[str] = Query(None),
    symbol: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000)
):
    """Get trades"""
    try:
        trades = await order_executor_service.database.get_trades(order_id, limit)
        
        # Apply symbol filter if specified
        if symbol:
            trades = [t for t in trades if t.get('symbol') == symbol.upper()]
        
        return {
            "trades": trades,
            "total": len(trades),
            "filters": {
                "order_id": order_id,
                "symbol": symbol,
                "limit": limit
            }
        }
    except Exception as e:
        logger.error(f"Failed to get trades: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Position Management Endpoints
@app.get("/positions")
async def get_positions(
    strategy_id: Optional[str] = Query(None),
    is_open: Optional[bool] = Query(None)
):
    """Get positions"""
    try:
        positions = await order_executor_service.database.get_positions(strategy_id, is_open)
        
        return {
            "positions": positions,
            "total": len(positions),
            "open_positions": len([p for p in positions if p.get('is_open', True)]),
            "filters": {
                "strategy_id": strategy_id,
                "is_open": is_open
            }
        }
    except Exception as e:
        logger.error(f"Failed to get positions: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Configuration and Stats Endpoints
@app.get("/config")
async def get_service_config():
    """Get service configuration"""
    return {
        "service": "order_executor",
        "version": "2.0.0",
        "database": "mock" if USE_MOCK_DATABASE else "cosmos",
        "exchange_manager": "mock" if USE_MOCK_DATABASE else "live",
        "environments": order_executor_service.environment_manager.get_available_environments(),
        "active_orders": len(order_executor_service.active_orders),
        "features": {
            "multi_exchange": True,
            "risk_management": True,
            "position_tracking": True,
            "signal_processing": True
        }
    }

@app.get("/stats")
async def get_execution_stats():
    """Get execution statistics"""
    try:
        db_stats = await order_executor_service.database.get_execution_stats()
        
        return {
            "execution_stats": order_executor_service.execution_stats,
            "database_stats": db_stats,
            "active_orders": len(order_executor_service.active_orders),
            "last_update": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error(f"Failed to get execution stats: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/dashboard")
async def get_dashboard_data():
    """Get comprehensive dashboard data"""
    try:
        dashboard_data = await order_executor_service.database.get_order_executor_dashboard()
        
        # Add real-time metrics
        dashboard_data.update({
            "execution_stats": order_executor_service.execution_stats,
            "active_orders_detail": list(order_executor_service.active_orders.values()),
            "service_status": {
                "running": order_executor_service.running,
                "exchange_connected": True,  # Mock
                "database_connected": order_executor_service.database.connected
            }
        })
        
        return dashboard_data
        
    except Exception as e:
        logger.error(f"Failed to get dashboard data: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    try:
        logger.info("Starting Simple Order Executor Service on port 8081")
        config = uvicorn.Config(
            app=app,
            host="0.0.0.0",
            port=8081,
            log_level="info"
        )
        server = uvicorn.Server(config)
        asyncio.run(server.serve())
    except KeyboardInterrupt:
        logger.info("Order executor service stopped by user")
    except Exception as e:
        logger.error(f"Order executor service error: {str(e)}")
        raise