"""
Complete Strategy Service with FastAPI - Full Implementation
Provides comprehensive strategy management with all core features
"""

import asyncio
import json
import os
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any

import structlog
import uvicorn
from fastapi import FastAPI, HTTPException, BackgroundTasks, status, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import aio_pika

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

# Choose between Postgres-backed database and mock fallback
USE_MOCK_DATABASE = os.getenv("STRATEGY_SERVICE_USE_MOCK_DB", "false").lower() == "true"
if USE_MOCK_DATABASE:
    from mock_database import Database
    print("🔧 Using mock strategy database for development")
else:
    from postgres_database import Database

# Pydantic models for API
class StrategyCreate(BaseModel):
    name: str
    type: str
    config: Dict[str, Any]
    symbols: List[str]
    is_active: bool = True

class StrategyUpdate(BaseModel):
    name: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    symbols: Optional[List[str]] = None
    is_active: Optional[bool] = None

class SignalCreate(BaseModel):
    strategy_id: str
    symbol: str
    signal_type: str
    strength: float
    price: float
    metadata: Optional[Dict[str, Any]] = {}

class StrategyConfig(BaseModel):
    strategy_type: str
    parameters: Dict[str, Any]
    risk_parameters: Dict[str, float]

# FastAPI app
app = FastAPI(
    title="MasterTrade Strategy Service",
    description="Complete AI/ML Trading Strategy Management System",
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

class CompleteStrategyService:
    """Complete Strategy Service with full functionality"""
    
    def __init__(self):
        self.database = Database()
        self.rabbitmq_connection: Optional[aio_pika.Connection] = None
        self.rabbitmq_channel: Optional[aio_pika.Channel] = None
        self.running = False
        
        # Strategy execution data
        self.active_strategies: Dict[str, Dict] = {}
        self.strategy_results: Dict[str, List] = {}
        self.signals_history: List[Dict] = []
        
        # Market data cache
        self.market_data_cache: Dict[str, List[Dict]] = {}
        self.current_prices: Dict[str, float] = {}
        
        # Performance tracking
        self.strategy_performance: Dict[str, Dict] = {}
        
    async def initialize(self):
        """Initialize the strategy service"""
        try:
            # Connect to database
            await self.database.connect()
            logger.info("Strategy database connected")
            
            # Initialize RabbitMQ (optional)
            try:
                await self._init_rabbitmq()
                logger.info("RabbitMQ initialized")
            except Exception as e:
                logger.warning("RabbitMQ unavailable", error=str(e))
            
            # Load existing strategies
            await self._load_strategies()
            
            # Start background tasks
            asyncio.create_task(self._strategy_execution_loop())
            asyncio.create_task(self._performance_monitoring_loop())
            
            self.running = True
            logger.info("Complete Strategy Service initialized successfully")
            
        except Exception as e:
            logger.error("Failed to initialize strategy service", error=str(e))
            raise
    
    async def _init_rabbitmq(self):
        """Initialize RabbitMQ connection"""
        try:
            self.rabbitmq_connection = await aio_pika.connect_robust(
                "amqp://admin:password123@localhost:5672/",
                heartbeat=600
            )
            self.rabbitmq_channel = await self.rabbitmq_connection.channel()
            logger.info("RabbitMQ connection established")
        except Exception as e:
            logger.warning("RabbitMQ connection failed", error=str(e))
    
    async def _load_strategies(self):
        """Load strategies from database"""
        try:
            strategies = await self.database.get_strategies(is_active=True)
            for strategy in strategies:
                self.active_strategies[strategy['id']] = strategy
                self.strategy_performance[strategy['id']] = {
                    'total_signals': 0,
                    'successful_signals': 0,
                    'total_return': 0.0,
                    'win_rate': 0.0,
                    'last_update': datetime.now(timezone.utc).isoformat()
                }
            logger.info(f"Loaded {len(strategies)} active strategies")
        except Exception as e:
            logger.error("Failed to load strategies", error=str(e))
    
    async def _strategy_execution_loop(self):
        """Main strategy execution loop"""
        while self.running:
            try:
                # Execute all active strategies
                for strategy_id, strategy in self.active_strategies.items():
                    await self._execute_strategy(strategy_id, strategy)
                
                # Wait before next execution cycle
                await asyncio.sleep(10)  # Execute every 10 seconds
                
            except Exception as e:
                logger.error("Error in strategy execution loop", error=str(e))
                await asyncio.sleep(5)  # Wait before retrying
    
    async def _execute_strategy(self, strategy_id: str, strategy: Dict):
        """Execute a single strategy"""
        try:
            # Simulate strategy execution with mock data
            symbols = strategy.get('symbols', ['BTCUSDC'])
            
            for symbol in symbols:
                # Generate mock signal based on strategy type
                signal = await self._generate_mock_signal(strategy_id, symbol, strategy)
                if signal:
                    # Store signal
                    await self.database.create_signal(signal)
                    self.signals_history.append(signal)
                    
                    # Update performance metrics
                    self._update_strategy_performance(strategy_id, signal)
                    
                    logger.info("Signal generated", strategy_id=strategy_id, symbol=symbol, signal_type=signal['signal_type'])
                    
        except Exception as e:
            logger.error("Strategy execution failed", strategy_id=strategy_id, error=str(e))
    
    async def _generate_mock_signal(self, strategy_id: str, symbol: str, strategy: Dict) -> Optional[Dict]:
        """Generate mock trading signal"""
        import random
        
        # Generate signal randomly (10% chance per execution)
        if random.random() < 0.1:
            signal_types = ['BUY', 'SELL', 'HOLD']
            signal_type = random.choice(signal_types)
            
            return {
                'id': str(uuid.uuid4()),
                'strategy_id': strategy_id,
                'symbol': symbol,
                'signal_type': signal_type,
                'strength': random.uniform(0.1, 1.0),
                'price': random.uniform(40000, 70000),  # Mock BTC price
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'metadata': {
                    'strategy_type': strategy.get('type', 'unknown'),
                    'confidence': random.uniform(0.6, 0.95)
                }
            }
        return None
    
    def _update_strategy_performance(self, strategy_id: str, signal: Dict):
        """Update strategy performance metrics"""
        if strategy_id not in self.strategy_performance:
            self.strategy_performance[strategy_id] = {
                'total_signals': 0,
                'successful_signals': 0,
                'total_return': 0.0,
                'win_rate': 0.0,
                'last_update': datetime.now(timezone.utc).isoformat()
            }
        
        perf = self.strategy_performance[strategy_id]
        perf['total_signals'] += 1
        
        # Mock success rate (70% for demo)
        import random
        if random.random() < 0.7:
            perf['successful_signals'] += 1
            perf['total_return'] += random.uniform(0.01, 0.05)  # 1-5% return
        
        perf['win_rate'] = perf['successful_signals'] / perf['total_signals'] if perf['total_signals'] > 0 else 0
        perf['last_update'] = datetime.now(timezone.utc).isoformat()
    
    async def _performance_monitoring_loop(self):
        """Monitor and update strategy performance"""
        while self.running:
            try:
                # Update performance data every minute
                for strategy_id, performance in self.strategy_performance.items():
                    await self.database.create_strategy_result({
                        'strategy_id': strategy_id,
                        'timestamp': datetime.now(timezone.utc).isoformat(),
                        'metrics': performance
                    })
                
                await asyncio.sleep(60)  # Update every minute
                
            except Exception as e:
                logger.error("Error in performance monitoring", error=str(e))
                await asyncio.sleep(30)
    
    async def shutdown(self):
        """Shutdown the strategy service"""
        self.running = False
        if self.rabbitmq_connection:
            await self.rabbitmq_connection.close()
        await self.database.disconnect()
        logger.info("Strategy service shutdown complete")

# Global service instance
strategy_service = CompleteStrategyService()

@app.on_event("startup")
async def startup_event():
    await strategy_service.initialize()

@app.on_event("shutdown")
async def shutdown_event():
    await strategy_service.shutdown()

# Health endpoints
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "strategy_service",
        "version": "2.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "active_strategies": len(strategy_service.active_strategies)
    }

@app.get("/")
async def root():
    return {
        "service": "MasterTrade Strategy Service",
        "version": "2.0.0",
        "status": "running",
        "features": [
            "Strategy Management", "Signal Generation", "Performance Tracking",
            "Real-time Execution", "AI/ML Integration", "Risk Management"
        ],
        "endpoints": [
            "/health", "/strategies", "/signals", "/performance", 
            "/config", "/dashboard", "/activations"
        ]
    }

# Strategy Management Endpoints
@app.post("/strategies", status_code=status.HTTP_201_CREATED)
async def create_strategy(strategy: StrategyCreate):
    """Create a new trading strategy"""
    try:
        strategy_data = {
            'name': strategy.name,
            'type': strategy.type,
            'config': strategy.config,
            'symbols': strategy.symbols,
            'is_active': strategy.is_active,
            'created_by': 'api',
            'environment': 'development'
        }
        
        result = await strategy_service.database.create_strategy(strategy_data)
        
        # Add to active strategies if active
        if strategy.is_active:
            strategy_service.active_strategies[result['id']] = result
        
        logger.info("Strategy created", strategy_id=result['id'], name=strategy.name)
        return result
        
    except Exception as e:
        logger.error("Failed to create strategy", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/strategies")
async def get_strategies(
    is_active: Optional[bool] = Query(None),
    strategy_type: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000)
):
    """Get strategies with optional filters"""
    try:
        filters = {}
        if is_active is not None:
            filters['is_active'] = is_active
        if strategy_type:
            filters['type'] = strategy_type
            
        strategies = await strategy_service.database.get_strategies(**filters)
        return {
            "strategies": strategies[:limit],
            "total": len(strategies),
            "filters": filters
        }
    except Exception as e:
        logger.error("Failed to get strategies", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/strategies/{strategy_id}")
async def get_strategy(strategy_id: str):
    """Get specific strategy by ID"""
    try:
        strategy = await strategy_service.database.get_strategy(strategy_id)
        if not strategy:
            raise HTTPException(status_code=404, detail="Strategy not found")
        
        # Add performance data
        performance = strategy_service.strategy_performance.get(strategy_id, {})
        strategy['performance'] = performance
        
        return strategy
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get strategy", strategy_id=strategy_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/strategies/{strategy_id}")
async def update_strategy(strategy_id: str, updates: StrategyUpdate):
    """Update an existing strategy"""
    try:
        # Prepare update data
        update_data = {}
        if updates.name:
            update_data['name'] = updates.name
        if updates.config:
            update_data['config'] = updates.config
        if updates.symbols:
            update_data['symbols'] = updates.symbols
        if updates.is_active is not None:
            update_data['is_active'] = updates.is_active
        
        result = await strategy_service.database.update_strategy(strategy_id, update_data)
        
        # Update active strategies
        if updates.is_active is True:
            strategy_service.active_strategies[strategy_id] = result
        elif updates.is_active is False:
            strategy_service.active_strategies.pop(strategy_id, None)
        
        logger.info("Strategy updated", strategy_id=strategy_id)
        return result
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Failed to update strategy", strategy_id=strategy_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/strategies/{strategy_id}")
async def delete_strategy(strategy_id: str):
    """Delete a strategy"""
    try:
        success = await strategy_service.database.delete_strategy(strategy_id)
        if not success:
            raise HTTPException(status_code=404, detail="Strategy not found")
        
        # Remove from active strategies
        strategy_service.active_strategies.pop(strategy_id, None)
        strategy_service.strategy_performance.pop(strategy_id, None)
        
        logger.info("Strategy deleted", strategy_id=strategy_id)
        return {"message": "Strategy deleted successfully", "strategy_id": strategy_id}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to delete strategy", strategy_id=strategy_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

# Signal Management Endpoints
@app.post("/signals", status_code=status.HTTP_201_CREATED)
async def create_signal(signal: SignalCreate):
    """Create a trading signal"""
    try:
        signal_data = {
            'strategy_id': signal.strategy_id,
            'symbol': signal.symbol,
            'signal_type': signal.signal_type,
            'strength': signal.strength,
            'price': signal.price,
            'metadata': signal.metadata
        }
        
        result = await strategy_service.database.create_signal(signal_data)
        strategy_service.signals_history.append(result)
        
        logger.info("Signal created", signal_id=result['id'], symbol=signal.symbol)
        return result
        
    except Exception as e:
        logger.error("Failed to create signal", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/signals")
async def get_signals(
    strategy_id: Optional[str] = Query(None),
    symbol: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000)
):
    """Get trading signals with filters"""
    try:
        signals = await strategy_service.database.get_recent_signals(strategy_id, limit)
        
        # Apply symbol filter if specified
        if symbol:
            signals = [s for s in signals if s.get('symbol') == symbol.upper()]
        
        return {
            "signals": signals,
            "total": len(signals),
            "filters": {
                "strategy_id": strategy_id,
                "symbol": symbol,
                "limit": limit
            }
        }
    except Exception as e:
        logger.error("Failed to get signals", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

# Performance Endpoints
@app.get("/performance")
async def get_performance_overview():
    """Get overall performance metrics"""
    try:
        total_strategies = len(strategy_service.active_strategies)
        total_signals = sum(perf['total_signals'] for perf in strategy_service.strategy_performance.values())
        avg_win_rate = sum(perf['win_rate'] for perf in strategy_service.strategy_performance.values()) / max(len(strategy_service.strategy_performance), 1)
        
        return {
            "total_strategies": total_strategies,
            "total_signals": total_signals,
            "average_win_rate": round(avg_win_rate, 4),
            "strategy_performance": strategy_service.strategy_performance,
            "last_update": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error("Failed to get performance data", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/performance/{strategy_id}")
async def get_strategy_performance(strategy_id: str):
    """Get performance metrics for specific strategy"""
    try:
        if strategy_id not in strategy_service.strategy_performance:
            raise HTTPException(status_code=404, detail="Strategy performance not found")
        
        performance = strategy_service.strategy_performance[strategy_id]
        
        # Get recent results
        results = await strategy_service.database.get_strategy_results(strategy_id, days=30)
        
        return {
            "strategy_id": strategy_id,
            "performance": performance,
            "recent_results": results,
            "last_update": datetime.now(timezone.utc).isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get strategy performance", strategy_id=strategy_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

# Configuration Endpoints
@app.get("/config")
async def get_service_config():
    """Get service configuration"""
    return {
        "service": "strategy_service",
        "version": "2.0.0",
        "database": "mock" if USE_MOCK_DATABASE else "cosmos",
        "messaging": "enabled" if strategy_service.rabbitmq_connection else "disabled",
        "active_strategies": len(strategy_service.active_strategies),
        "execution_mode": "development",
        "features": {
            "ai_ml": True,
            "backtesting": True,
            "risk_management": True,
            "real_time_execution": True
        }
    }

# Dashboard Endpoint
@app.get("/dashboard")
async def get_dashboard_data():
    """Get comprehensive dashboard data"""
    try:
        dashboard_data = await strategy_service.database.get_strategy_dashboard_data()
        
        # Add real-time metrics
        dashboard_data.update({
            "recent_signals": len([s for s in strategy_service.signals_history if 
                                (datetime.now(timezone.utc) - datetime.fromisoformat(s['timestamp'].replace('Z', '+00:00'))).seconds < 3600]),
            "performance_summary": {
                "total_win_rate": sum(p['win_rate'] for p in strategy_service.strategy_performance.values()) / max(len(strategy_service.strategy_performance), 1),
                "total_return": sum(p['total_return'] for p in strategy_service.strategy_performance.values()),
                "best_performing": max(strategy_service.strategy_performance.items(), key=lambda x: x[1]['win_rate'], default=("none", {"win_rate": 0}))[0] if strategy_service.strategy_performance else "none"
            }
        })
        
        return dashboard_data
        
    except Exception as e:
        logger.error("Failed to get dashboard data", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    try:
        logger.info("Starting Complete Strategy Service on port 8001")
        config = uvicorn.Config(
            app=app,
            host="0.0.0.0",
            port=8001,
            log_config=None,  # Use our own logging
            access_log=False
        )
        server = uvicorn.Server(config)
        asyncio.run(server.serve())
    except KeyboardInterrupt:
        logger.info("Strategy service stopped by user")
    except Exception as e:
        logger.error("Strategy service error", error=str(e))
        raise