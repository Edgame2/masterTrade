"""
Scheduled Historical Data Updates

Continuous background service for:
- Keeping historical data up-to-date
- Filling data gaps automatically
- Running daily quality checks
- Updating new trading pairs
"""

import asyncio
import schedule
import time
from datetime import datetime, timedelta
from typing import List
import structlog

from config import settings
from database import Database
from enhanced_historical_collector import EnhancedHistoricalDataCollector

logger = structlog.get_logger()

class HistoricalDataScheduler:
    """Manage scheduled historical data updates"""
    
    def __init__(self):
        self.database = Database()
        self.collector = None
        self.running = False
        
    async def initialize(self):
        """Initialize the scheduler"""
        self.collector = EnhancedHistoricalDataCollector(self.database)
        await self.database.__aenter__()
        await self.collector.__aenter__()
        
    async def shutdown(self):
        """Shutdown the scheduler"""
        self.running = False
        if self.collector:
            await self.collector.__aexit__(None, None, None)
        if self.database:
            await self.database.__aexit__(None, None, None)
    
    async def update_recent_data(self):
        """Update recent data for all symbols (last 7 days)"""
        logger.info("Running scheduled data update (last 7 days)")
        
        try:
            results = await self.collector.collect_comprehensive_historical_data(
                symbols=settings.DEFAULT_SYMBOLS,
                timeframes=settings.HISTORICAL_INTERVALS,
                days_back={tf: 7 for tf in settings.HISTORICAL_INTERVALS},
                parallel_symbols=5,
                parallel_timeframes=3
            )
            
            logger.info("Scheduled data update completed", results=results)
            
        except Exception as e:
            logger.error(f"Error in scheduled data update: {e}")
    
    async def backfill_gaps(self):
        """Check and fill data gaps"""
        logger.info("Running gap detection and backfill")
        
        try:
            for symbol in settings.DEFAULT_SYMBOLS:
                for timeframe in settings.HISTORICAL_INTERVALS:
                    filled = await self.collector.base_collector.backfill_missing_data(
                        symbol=symbol,
                        interval=timeframe,
                        check_days=30  # Check last 30 days
                    )
                    
                    if filled > 0:
                        logger.info(f"Filled {filled} gaps for {symbol} {timeframe}")
                        
        except Exception as e:
            logger.error(f"Error in gap backfill: {e}")
    
    async def run_quality_checks(self):
        """Run data quality checks"""
        logger.info("Running scheduled quality checks")
        
        try:
            for symbol in settings.DEFAULT_SYMBOLS:
                for timeframe in settings.HISTORICAL_INTERVALS:
                    metrics = await self.collector._check_data_quality(symbol, timeframe)
                    
                    # Alert if quality is low
                    if metrics.quality_score < 70:
                        logger.warning(
                            f"Low data quality detected: {symbol} {timeframe}",
                            quality_score=metrics.quality_score,
                            completeness=metrics.completeness_pct
                        )
                        
        except Exception as e:
            logger.error(f"Error in quality checks: {e}")
    
    async def add_new_symbol(self, symbol: str):
        """Add a new symbol and collect its historical data"""
        logger.info(f"Adding new symbol: {symbol}")
        
        try:
            results = await self.collector.collect_comprehensive_historical_data(
                symbols=[symbol],
                timeframes=settings.HISTORICAL_INTERVALS,
                parallel_symbols=1,
                parallel_timeframes=3
            )
            
            logger.info(f"New symbol {symbol} data collected", results=results)
            
            # Add to default symbols if successful
            if symbol not in settings.DEFAULT_SYMBOLS:
                settings.DEFAULT_SYMBOLS.append(symbol)
                
        except Exception as e:
            logger.error(f"Error adding new symbol {symbol}: {e}")
    
    def schedule_jobs(self):
        """Set up all scheduled jobs"""
        
        # Update recent data every 6 hours
        schedule.every(6).hours.do(
            lambda: asyncio.create_task(self.update_recent_data())
        )
        
        # Backfill gaps daily at 3 AM
        schedule.every().day.at("03:00").do(
            lambda: asyncio.create_task(self.backfill_gaps())
        )
        
        # Quality checks daily at 4 AM
        schedule.every().day.at("04:00").do(
            lambda: asyncio.create_task(self.run_quality_checks())
        )
        
        logger.info("Scheduled jobs configured:")
        logger.info("  - Data updates: Every 6 hours")
        logger.info("  - Gap backfill: Daily at 3 AM")
        logger.info("  - Quality checks: Daily at 4 AM")
    
    async def run(self):
        """Run the scheduler"""
        await self.initialize()
        self.schedule_jobs()
        self.running = True
        
        logger.info("Historical data scheduler started")
        
        # Run initial update
        await self.update_recent_data()
        
        while self.running:
            schedule.run_pending()
            await asyncio.sleep(60)  # Check every minute
            
        logger.info("Historical data scheduler stopped")


async def main():
    """Main entry point"""
    scheduler = HistoricalDataScheduler()
    
    try:
        await scheduler.run()
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
    finally:
        await scheduler.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
