"""
Simplified Market Data Service for development
Provides basic HTTP endpoints without complex dependencies
"""

import asyncio
import json
from datetime import datetime
from typing import Dict, List
import structlog
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import aiohttp

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

# FastAPI app
app = FastAPI(
    title="MasterTrade Market Data Service",
    description="Simplified Market Data API for development",
    version="1.0.0-dev"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mock data storage
mock_data = {
    'symbols': ['BTCUSDC', 'ETHUSDC', 'ADAUSDC'],
    'market_data': [],
    'last_update': datetime.utcnow()
}

@app.on_event("startup")
async def startup_event():
    logger.info("Market Data Service starting up")
    # Initialize some mock data
    for symbol in mock_data['symbols']:
        mock_data['market_data'].append({
            'symbol': symbol,
            'price': 50000.0,  # Mock price
            'volume': 1000.0,
            'timestamp': datetime.utcnow().isoformat()
        })

@app.get("/health")
async def health_check():
    return {
        "status": "healthy", 
        "service": "market_data_service",
        "timestamp": datetime.utcnow().isoformat()
    }

@app.get("/")
async def root():
    return {
        "service": "MasterTrade Market Data Service",
        "version": "1.0.0-dev",
        "status": "running",
        "endpoints": ["/health", "/symbols", "/market-data", "/config"]
    }

@app.get("/symbols")
async def get_symbols():
    """Get list of tracked symbols"""
    return {
        "symbols": mock_data['symbols'],
        "count": len(mock_data['symbols']),
        "last_update": mock_data['last_update'].isoformat()
    }

@app.get("/market-data")
async def get_market_data():
    """Get current market data"""
    return {
        "data": mock_data['market_data'],
        "count": len(mock_data['market_data']),
        "last_update": mock_data['last_update'].isoformat()
    }

@app.get("/market-data/{symbol}")
async def get_symbol_data(symbol: str):
    """Get market data for specific symbol"""
    symbol_data = [d for d in mock_data['market_data'] if d['symbol'] == symbol.upper()]
    if symbol_data:
        return symbol_data[0]
    return {"error": "Symbol not found", "symbol": symbol}

@app.get("/config")
async def get_config():
    """Get service configuration"""
    return {
        "service": "market_data_service",
        "mock_mode": True,
        "symbols_tracked": len(mock_data['symbols']),
        "database": "mock",
        "messaging": "disabled"
    }

@app.post("/symbols/{symbol}")
async def add_symbol(symbol: str):
    """Add a symbol to tracking"""
    symbol = symbol.upper()
    if symbol not in mock_data['symbols']:
        mock_data['symbols'].append(symbol)
        mock_data['market_data'].append({
            'symbol': symbol,
            'price': 1000.0,  # Mock price
            'volume': 100.0,
            'timestamp': datetime.utcnow().isoformat()
        })
        logger.info("Added symbol for tracking", symbol=symbol)
        return {"message": f"Symbol {symbol} added", "symbol": symbol}
    return {"message": f"Symbol {symbol} already tracked", "symbol": symbol}

@app.get("/stats")
async def get_stats():
    """Get service statistics"""
    return {
        "symbols_count": len(mock_data['symbols']),
        "market_data_count": len(mock_data['market_data']),
        "uptime": datetime.utcnow().isoformat(),
        "service_mode": "development"
    }

class SimpleMarketDataService:
    def __init__(self):
        self.app = app
        
    async def start(self):
        """Start the service"""
        logger.info("Starting Simple Market Data Service on port 8000")
        config = uvicorn.Config(
            app=self.app,
            host="0.0.0.0",
            port=8000,
            log_config=None,  # Use our own logging
            access_log=False
        )
        server = uvicorn.Server(config)
        await server.serve()

# Main execution
if __name__ == "__main__":
    try:
        service = SimpleMarketDataService()
        asyncio.run(service.start())
    except KeyboardInterrupt:
        logger.info("Service stopped by user")
    except Exception as e:
        logger.error("Service error", error=str(e))
        raise