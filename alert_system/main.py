"""
Alert System Service - Monitoring and Notifications

Provides comprehensive alerting capabilities:
- Price alerts (breakouts, support/resistance)
- Strategy performance alerts
- Risk breach alerts
- System health alerts
- Performance milestones
- Multi-channel delivery (email, SMS, Telegram, Discord)
"""

import asyncio
import json
import logging
import signal
import sys
from datetime import datetime, timezone
from typing import Dict, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn
import structlog

from config import settings
from database import Database
from api import alert_router

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

# Initialize FastAPI app
app = FastAPI(
    title="MasterTrade Alert System",
    description="Alert and notification management system for automated trading",
    version="1.0.0",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure based on environment
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include alert router
app.include_router(alert_router)

# Global database instance
db: Optional[Database] = None


@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    global db
    
    logger.info("starting_alert_system", port=settings.PORT)
    
    try:
        # Initialize database connection
        db = Database(settings.DATABASE_URL)
        await db.connect()
        logger.info("database_connected")
        
        # Initialize alert tables
        await db.initialize_alerts_schema()
        logger.info("alert_schema_initialized")
        
        logger.info("alert_system_ready", port=settings.PORT)
        
    except Exception as e:
        logger.error("startup_failed", error=str(e), exc_info=True)
        raise


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    global db
    
    logger.info("shutting_down_alert_system")
    
    try:
        if db:
            await db.close()
            logger.info("database_closed")
            
    except Exception as e:
        logger.error("shutdown_error", error=str(e))


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        # Check database connectivity
        if db and await db.check_connection():
            return {
                "status": "healthy",
                "service": "alert_system",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "database": "connected"
            }
        else:
            return JSONResponse(
                status_code=503,
                content={
                    "status": "unhealthy",
                    "service": "alert_system",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "database": "disconnected"
                }
            )
    except Exception as e:
        logger.error("health_check_failed", error=str(e))
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "service": "alert_system",
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        )


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "MasterTrade Alert System",
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "health": "/health",
            "docs": "/docs",
            "alerts": "/api/alerts",
        }
    }


def signal_handler(sig, frame):
    """Handle shutdown signals"""
    logger.info("signal_received", signal=sig)
    sys.exit(0)


if __name__ == "__main__":
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Run the service
    logger.info("starting_uvicorn", host=settings.HOST, port=settings.PORT)
    
    uvicorn.run(
        app,
        host=settings.HOST,
        port=settings.PORT,
        log_level="info",
        access_log=True,
    )
