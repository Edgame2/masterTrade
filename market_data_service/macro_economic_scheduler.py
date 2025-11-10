"""
Macro-Economic Data Collection Scheduler

Runs periodic tasks for:
1. Commodity prices collection (every 15 minutes during market hours, hourly otherwise)
2. Currency data collection (every 15 minutes)
3. Treasury yields collection (daily at market close)
4. FRED indicators collection (daily at 8 AM UTC)
5. Fear & Greed Index (every 6 hours)
6. Macro summary generation (hourly)
"""

import asyncio
from datetime import datetime, time as dt_time
from typing import Dict, Any
import structlog

from config import settings
from database import Database
from macro_economic_collector import MacroEconomicCollector

logger = structlog.get_logger()


class MacroEconomicScheduler:
    """Scheduler for macro-economic data collection"""
    
    def __init__(self):
        self.database: Database = None
        self.collector: MacroEconomicCollector = None
        self.running = False
        self.stats = {
            "commodity_runs": 0,
            "currency_runs": 0,
            "treasury_runs": 0,
            "fred_runs": 0,
            "fear_greed_runs": 0,
            "errors": 0,
            "last_collection": None,
            "last_error": None
        }
        
    async def initialize(self):
        """Initialize database connections and services"""
        try:
            self.database = Database()
            await self.database.__aenter__()
            
            self.collector = MacroEconomicCollector(self.database)
            await self.collector.connect()
            
            logger.info("Macro-economic scheduler initialized")
            
        except Exception as e:
            logger.error("Failed to initialize scheduler", error=str(e))
            raise
    
    async def cleanup(self):
        """Cleanup resources"""
        try:
            if self.collector:
                await self.collector.disconnect()
            
            if self.database:
                await self.database.__aexit__(None, None, None)
            
            logger.info("Macro-economic scheduler cleaned up")
            
        except Exception as e:
            logger.error("Error during cleanup", error=str(e))
    
    async def collect_commodities(self):
        """Collect commodity prices"""
        try:
            logger.info("Starting scheduled commodity data collection")
            
            data = await self.collector.fetch_commodities_data()
            
            # Store in database
            if data:
                await self.database.upsert_market_data_batch(data)
            
            self.stats["commodity_runs"] += 1
            self.stats["last_collection"] = datetime.utcnow().isoformat()
            
            logger.info(
                "Commodity data collection completed",
                records=len(data),
                total_runs=self.stats["commodity_runs"]
            )
            
        except Exception as e:
            self.stats["errors"] += 1
            self.stats["last_error"] = str(e)
            logger.error("Error in commodity data collection", error=str(e))
    
    async def collect_currencies(self):
        """Collect currency data"""
        try:
            logger.info("Starting scheduled currency data collection")
            
            data = await self.collector.fetch_currencies_data()
            
            # Store in database
            if data:
                await self.database.upsert_market_data_batch(data)
            
            self.stats["currency_runs"] += 1
            
            logger.info(
                "Currency data collection completed",
                records=len(data),
                total_runs=self.stats["currency_runs"]
            )
            
        except Exception as e:
            self.stats["errors"] += 1
            self.stats["last_error"] = str(e)
            logger.error("Error in currency data collection", error=str(e))
    
    async def collect_treasury_yields(self):
        """Collect treasury yields"""
        try:
            logger.info("Starting scheduled treasury yields collection")
            
            data = await self.collector.fetch_treasury_yields()
            
            # Store in database
            if data:
                await self.database.upsert_market_data_batch(data)
            
            self.stats["treasury_runs"] += 1
            
            logger.info(
                "Treasury yields collection completed",
                records=len(data),
                total_runs=self.stats["treasury_runs"]
            )
            
        except Exception as e:
            self.stats["errors"] += 1
            self.stats["last_error"] = str(e)
            logger.error("Error in treasury yields collection", error=str(e))
    
    async def collect_fred_indicators(self):
        """Collect FRED economic indicators"""
        try:
            logger.info("Starting scheduled FRED indicators collection")
            
            data = await self.collector.fetch_fred_indicators()
            
            # Store in database
            if data:
                await self.database.upsert_market_data_batch(data)
            
            self.stats["fred_runs"] += 1
            
            logger.info(
                "FRED indicators collection completed",
                records=len(data),
                total_runs=self.stats["fred_runs"]
            )
            
        except Exception as e:
            self.stats["errors"] += 1
            self.stats["last_error"] = str(e)
            logger.error("Error in FRED indicators collection", error=str(e))
    
    async def collect_fear_greed(self):
        """Collect Fear & Greed Index"""
        try:
            logger.info("Starting scheduled Fear & Greed Index collection")
            
            data = await self.collector.fetch_crypto_fear_greed_index()
            
            # Store in database
            if data:
                await self.database.upsert_market_data(data)
            
            self.stats["fear_greed_runs"] += 1
            
            logger.info(
                "Fear & Greed Index collection completed",
                total_runs=self.stats["fear_greed_runs"]
            )
            
        except Exception as e:
            self.stats["errors"] += 1
            self.stats["last_error"] = str(e)
            logger.error("Error in Fear & Greed Index collection", error=str(e))
    
    async def generate_macro_summary(self):
        """Generate and store macro-economic summary"""
        try:
            logger.info("Generating macro-economic summary")
            
            summary = await self.collector.get_macro_summary()
            
            # Store summary in database
            if summary and "error" not in summary:
                summary["id"] = f"macro_summary_{int(datetime.utcnow().timestamp())}"
                summary["doc_type"] = "macro_summary"
                await self.database.upsert_market_data(summary)
                
                logger.info(
                    "Macro summary generated",
                    risk_environment=summary.get("risk_environment"),
                    market_sentiment=summary.get("market_sentiment")
                )
            
        except Exception as e:
            logger.error("Error generating macro summary", error=str(e))
    
    def is_commodity_market_hours(self) -> bool:
        """Check if it's during commodity market hours"""
        now = datetime.utcnow()
        current_time = now.time()
        
        # Commodity markets (roughly 00:00 - 21:00 UTC, most active during US hours)
        # Sunday 18:00 - Friday 17:00 EST = Sunday 23:00 - Friday 22:00 UTC
        commodity_start = dt_time(23, 0)
        commodity_end = dt_time(22, 0)
        
        # Simplified: consider 00:00 - 21:00 UTC as active hours
        return dt_time(0, 0) <= current_time <= dt_time(21, 0)
    
    async def run_scheduled_tasks(self):
        """Main loop for running scheduled tasks"""
        self.running = True
        
        logger.info("Macro-economic scheduler started")
        
        # Initial collection
        await self.collector.collect_all_macro_data()
        
        last_commodity = datetime.utcnow()
        last_currency = datetime.utcnow()
        last_treasury = datetime.utcnow()
        last_fred = datetime.utcnow()
        last_fear_greed = datetime.utcnow()
        last_summary = datetime.utcnow()
        
        while self.running:
            try:
                now = datetime.utcnow()
                
                # Commodity prices - every 15 minutes during market hours, hourly otherwise
                if self.is_commodity_market_hours():
                    if (now - last_commodity).seconds >= 900:  # 15 minutes
                        await self.collect_commodities()
                        last_commodity = now
                else:
                    if (now - last_commodity).seconds >= 3600:  # 1 hour
                        await self.collect_commodities()
                        last_commodity = now
                
                # Currency data - every 15 minutes (24/7 market)
                if (now - last_currency).seconds >= 900:  # 15 minutes
                    await self.collect_currencies()
                    last_currency = now
                
                # Treasury yields - daily at 21:00 UTC (after US market close at 16:00 EST)
                if now.hour == 21 and now.minute == 0 and (now - last_treasury).seconds >= 3600:
                    await self.collect_treasury_yields()
                    last_treasury = now
                    await asyncio.sleep(3600)  # Sleep to avoid re-triggering
                
                # FRED indicators - daily at 8:00 UTC (data usually updated overnight)
                if now.hour == 8 and now.minute == 0 and (now - last_fred).seconds >= 3600:
                    await self.collect_fred_indicators()
                    last_fred = now
                    await asyncio.sleep(3600)
                
                # Fear & Greed Index - every 6 hours (updated daily, but check more often)
                if (now - last_fear_greed).seconds >= 21600:  # 6 hours
                    await self.collect_fear_greed()
                    last_fear_greed = now
                
                # Macro summary - every hour
                if (now - last_summary).seconds >= 3600:  # 1 hour
                    await self.generate_macro_summary()
                    last_summary = now
                
                # Wait before next iteration
                await asyncio.sleep(60)  # Check every minute
                
            except Exception as e:
                self.stats["errors"] += 1
                self.stats["last_error"] = str(e)
                logger.error("Error in scheduler main loop", error=str(e))
                await asyncio.sleep(60)
    
    async def stop(self):
        """Stop the scheduler"""
        self.running = False
        logger.info("Macro-economic scheduler stopping...")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get scheduler statistics"""
        return {
            "running": self.running,
            "stats": self.stats,
            "commodity_market_hours": self.is_commodity_market_hours()
        }


async def main():
    """Main entry point for the scheduler"""
    scheduler = MacroEconomicScheduler()
    
    try:
        await scheduler.initialize()
        
        # Run the scheduler
        await scheduler.run_scheduled_tasks()
        
    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
    except Exception as e:
        logger.error("Scheduler error", error=str(e))
    finally:
        await scheduler.stop()
        await scheduler.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
