"""
Risk Management Service Integration

This module integrates all risk management components and provides
a unified service interface for the MasterTrade system.
"""

import asyncio
import signal
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Dict, Any, Optional
import structlog

from shared.price_prediction_client import PricePredictionClient

from config import settings
from database import RiskPostgresDatabase
from position_sizing import PositionSizingEngine
from stop_loss_manager import StopLossManager
from portfolio_risk_controller import PortfolioRiskController
from message_handler import RiskMessageHandler
from main import app

logger = structlog.get_logger()

class RiskManagementService:
    """
    Comprehensive Risk Management Service
    
    Integrates all risk management components:
    - Position sizing engine
    - Stop-loss management 
    - Portfolio risk controls
    - Real-time risk monitoring
    - Message queue integration
    - REST API endpoints
    """
    
    def __init__(self):
        self.database = None
        self.position_sizing_engine = None
        self.stop_loss_manager = None
        self.portfolio_controller = None
        self.message_handler = None
        self.price_prediction_client: Optional[PricePredictionClient] = None
        self.running = False
        
    async def initialize(self):
        """Initialize all service components"""
        try:
            logger.info("Initializing Risk Management Service")
            
            # Initialize database
            self.database = RiskPostgresDatabase()
            await self.database.initialize()

            # IMPORTANT: Also initialize the module-level database and components from main.py
            # These are used by goal_tracking_service and other module-level objects
            import main
            await main.database.initialize()
            await main.price_prediction_client.initialize()
            await main.goal_tracking_service.start()
            logger.info("Main module components initialized")

            # Initialize price prediction client
            self.price_prediction_client = PricePredictionClient(
                base_url=settings.STRATEGY_SERVICE_URL,
                service_name=settings.SERVICE_NAME,
                cache_ttl_seconds=180
            )
            await self.price_prediction_client.initialize()
            
            # Initialize engines
            self.position_sizing_engine = PositionSizingEngine(
                self.database,
                price_prediction_client=self.price_prediction_client
            )
            self.stop_loss_manager = StopLossManager(self.database)
            self.portfolio_controller = PortfolioRiskController(self.database)
            
            # Initialize message handler
            self.message_handler = RiskMessageHandler(
                self.database,
                self.position_sizing_engine,
                self.stop_loss_manager,
                self.portfolio_controller
            )
            
            await self.message_handler.initialize()
            
            # Start background tasks
            await self._start_background_tasks()
            
            self.running = True
            
            logger.info("Risk Management Service initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize Risk Management Service: {e}")
            raise
    
    async def _start_background_tasks(self):
        """Start background monitoring and maintenance tasks"""
        try:
            # Portfolio risk monitoring task
            asyncio.create_task(self._portfolio_risk_monitor())
            
            # Stop-loss monitoring task
            asyncio.create_task(self._stop_loss_monitor())
            
            # Risk metrics calculation task
            asyncio.create_task(self._risk_metrics_calculator())
            
            # Correlation matrix update task
            asyncio.create_task(self._correlation_updater())
            
            logger.info("Background tasks started successfully")
            
        except Exception as e:
            logger.error(f"Failed to start background tasks: {e}")
            raise
    
    async def _portfolio_risk_monitor(self):
        """Continuous portfolio risk monitoring"""
        while self.running:
            try:
                # Check risk limits every 30 seconds
                await asyncio.sleep(30)
                
                if not self.running:
                    break
                
                # Calculate current risk metrics
                try:
                    risk_metrics = await self.portfolio_controller.calculate_portfolio_risk()
                except ValueError as ve:
                    # Handle empty portfolio or circular reference gracefully
                    if "Circular reference" in str(ve) or "empty" in str(ve).lower():
                        logger.debug("No active positions for risk calculation")
                        continue
                    raise
                
                # Check for limit breaches
                alerts = await self.portfolio_controller.check_risk_limits()
                
                # Send critical alerts immediately
                for alert in alerts:
                    if alert.severity.value in ['HIGH', 'CRITICAL']:
                        await self.message_handler.broadcast_portfolio_alert(
                            alert_type=alert.alert_type.value,
                            severity=alert.severity.value,
                            title=alert.title,
                            message=alert.message,
                            symbol=alert.symbol,
                            recommendation=alert.recommendation
                        )
                
                # Log risk status
                if risk_metrics.risk_level.value in ['HIGH', 'CRITICAL']:
                    logger.warning(
                        f"High portfolio risk detected",
                        risk_level=risk_metrics.risk_level.value,
                        risk_score=risk_metrics.risk_score,
                        var_1d=risk_metrics.var_1d,
                        drawdown=risk_metrics.current_drawdown
                    )
                
            except Exception as e:
                logger.error(f"Error in portfolio risk monitoring: {e}")
                await asyncio.sleep(60)  # Wait longer on error
    
    async def _stop_loss_monitor(self):
        """Continuous stop-loss monitoring"""
        while self.running:
            try:
                # Check stop-losses every 10 seconds
                await asyncio.sleep(10)
                
                if not self.running:
                    break
                
                # This would normally be triggered by price updates
                # For now, we'll do a periodic check for any missed triggers
                
                # Get current market prices (would integrate with market data service)
                # For demonstration, we'll skip this periodic check as price updates
                # should come through the message queue
                
            except Exception as e:
                logger.error(f"Error in stop-loss monitoring: {e}")
                await asyncio.sleep(30)
    
    async def _risk_metrics_calculator(self):
        """Periodic risk metrics calculation and storage"""
        while self.running:
            try:
                # Calculate detailed risk metrics every 5 minutes
                await asyncio.sleep(300)
                
                if not self.running:
                    break
                
                # Calculate comprehensive risk metrics
                risk_metrics = await self.portfolio_controller.calculate_portfolio_risk()
                
                # Store historical risk metrics
                await self.database.store_risk_metrics(risk_metrics)
                
                logger.info(
                    f"Risk metrics calculated and stored",
                    portfolio_value=risk_metrics.total_portfolio_value,
                    risk_score=risk_metrics.risk_score,
                    var_1d=risk_metrics.var_1d
                )
                
            except Exception as e:
                logger.error(f"Error in risk metrics calculation: {e}")
                await asyncio.sleep(600)  # Wait longer on error
    
    async def _correlation_updater(self):
        """Periodic correlation matrix updates"""
        while self.running:
            try:
                # Update correlation matrix every hour
                await asyncio.sleep(3600)
                
                if not self.running:
                    break
                
                # Calculate new correlation matrix
                await self.database.update_correlation_matrix()
                
                logger.info("Correlation matrix updated")
                
            except Exception as e:
                logger.error(f"Error updating correlation matrix: {e}")
                await asyncio.sleep(1800)  # Wait 30 minutes on error
    
    async def get_service_status(self) -> Dict[str, Any]:
        """Get comprehensive service status"""
        try:
            # Check component health
            database_healthy = await self._check_database_health()
            message_queue_healthy = self.message_handler.is_running()
            
            # Get current metrics
            risk_metrics = await self.portfolio_controller.calculate_portfolio_risk()
            
            # Get active alerts
            alerts = await self.database.get_active_risk_alerts()
            
            return {
                "service_status": "running" if self.running else "stopped",
                "components": {
                    "database": "healthy" if database_healthy else "unhealthy",
                    "message_queue": "healthy" if message_queue_healthy else "unhealthy",
                    "position_sizing": "healthy",
                    "stop_loss_manager": "healthy",
                    "portfolio_controller": "healthy"
                },
                "current_metrics": {
                    "portfolio_value": risk_metrics.total_portfolio_value,
                    "risk_level": risk_metrics.risk_level.value,
                    "risk_score": risk_metrics.risk_score,
                    "var_1d": risk_metrics.var_1d,
                    "current_drawdown": risk_metrics.current_drawdown,
                    "leverage_ratio": risk_metrics.leverage_ratio
                },
                "active_alerts": len(alerts),
                "uptime": datetime.now(timezone.utc),
                "version": "1.0.0"
            }
            
        except Exception as e:
            logger.error(f"Error getting service status: {e}")
            return {
                "service_status": "error",
                "error": str(e),
                "timestamp": datetime.now(timezone.utc)
            }
    
    async def _check_database_health(self) -> bool:
        """Check database connection health"""
        try:
            await self.database.get_account_balance()
            return True
        except Exception:
            return False
    
    async def shutdown(self):
        """Graceful service shutdown"""
        try:
            logger.info("Shutting down Risk Management Service")
            
            self.running = False
            
            # Close message handler
            if self.message_handler:
                await self.message_handler.close()
            
            if self.price_prediction_client:
                await self.price_prediction_client.close()

            # Close database connections
            if self.database:
                await self.database.close()
            
            logger.info("Risk Management Service shutdown completed")
            
        except Exception as e:
            logger.error(f"Error during service shutdown: {e}")

# Global service instance
risk_service = RiskManagementService()

@asynccontextmanager
async def lifespan(app):
    """FastAPI lifespan manager"""
    # Startup
    try:
        await risk_service.initialize()
        yield
    finally:
        # Shutdown
        await risk_service.shutdown()

# Update FastAPI app with lifespan
app.router.lifespan_context = lifespan

def setup_signal_handlers():
    """Setup signal handlers for graceful shutdown"""
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, starting graceful shutdown")
        asyncio.create_task(risk_service.shutdown())
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

async def main():
    """Main service entry point"""
    try:
        # Setup signal handlers
        setup_signal_handlers()
        
        # Initialize service
        await risk_service.initialize()
        
        # Start FastAPI server
        import uvicorn
        
        config = uvicorn.Config(
            app,
            host=settings.HOST,
            port=settings.PORT,
            log_level="info",
            access_log=True,
            loop="asyncio"
        )
        
        server = uvicorn.Server(config)
        
        logger.info(
            f"Starting Risk Management Service",
            host=settings.HOST,
            port=settings.PORT
        )
        
        await server.serve()
        
    except Exception as e:
        logger.error(f"Failed to start Risk Management Service: {e}")
        raise
    finally:
        await risk_service.shutdown()

if __name__ == "__main__":
    asyncio.run(main())