"""
Stock Index Data Collection Scheduler

Runs periodic tasks for:
1. Stock index data collection (every 15 minutes during market hours)
2. Correlation analysis (every hour)
3. Historical data backfill (daily at 2 AM)
4. Market regime detection (every 30 minutes)
"""

import asyncio
import schedule
from datetime import datetime, time as dt_time
from typing import Dict, Any
import structlog

from config import settings
from database import Database
from stock_index_collector import StockIndexDataCollector
from stock_index_correlation_analyzer import StockIndexCorrelationAnalyzer

logger = structlog.get_logger()


class StockIndexScheduler:
    """Scheduler for stock index data collection and analysis"""
    
    def __init__(self):
        self.database: Database = None
        self.collector: StockIndexDataCollector = None
        self.analyzer: StockIndexCorrelationAnalyzer = None
        self.running = False
        self.tasks_stats = {
            "collection_runs": 0,
            "correlation_runs": 0,
            "errors": 0,
            "last_collection": None,
            "last_correlation": None,
            "last_error": None
        }
        
    async def initialize(self):
        """Initialize database connections and services"""
        try:
            self.database = Database()
            await self.database.__aenter__()
            
            self.collector = StockIndexDataCollector(self.database)
            await self.collector.connect()
            
            self.analyzer = StockIndexCorrelationAnalyzer(self.database)
            
            logger.info("Stock index scheduler initialized")
            
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
            
            logger.info("Stock index scheduler cleaned up")
            
        except Exception as e:
            logger.error("Error during cleanup", error=str(e))
    
    async def collect_current_data(self):
        """Collect current stock index values"""
        try:
            logger.info("Starting scheduled stock index data collection")
            
            # Collect current values
            current_data = await self.collector.fetch_current_index_values()
            
            # Store in database
            for item in current_data:
                await self.database.upsert_market_data(item)
            
            self.tasks_stats["collection_runs"] += 1
            self.tasks_stats["last_collection"] = datetime.utcnow().isoformat()
            
            logger.info(
                "Stock index data collection completed",
                records=len(current_data),
                total_runs=self.tasks_stats["collection_runs"]
            )
            
        except Exception as e:
            self.tasks_stats["errors"] += 1
            self.tasks_stats["last_error"] = str(e)
            logger.error("Error in scheduled data collection", error=str(e))
    
    async def collect_intraday_data(self):
        """Collect recent intraday data (last few hours)"""
        try:
            logger.info("Starting intraday data collection")
            
            for symbol in self.collector.tracked_indices:
                try:
                    # Fetch last 4 hours of 5-minute data
                    recent_data = await self.collector.fetch_yahoo_finance_data(
                        symbol,
                        period="1d",
                        interval="5m"
                    )
                    
                    if recent_data:
                        # Store in batches
                        batch_size = 100
                        for i in range(0, len(recent_data), batch_size):
                            batch = recent_data[i:i + batch_size]
                            await self.database.upsert_market_data_batch(batch)
                    
                    # Small delay between symbols
                    await asyncio.sleep(0.5)
                    
                except Exception as e:
                    logger.error(f"Error collecting intraday data for {symbol}", error=str(e))
            
            logger.info("Intraday data collection completed")
            
        except Exception as e:
            logger.error("Error in intraday data collection", error=str(e))
    
    async def run_correlation_analysis(self):
        """Run correlation analysis between stock indices and crypto"""
        try:
            logger.info("Starting scheduled correlation analysis")
            
            # Run comprehensive cross-market analysis
            results = await self.analyzer.analyze_cross_market_correlations(
                hours_back=168,  # 1 week
                interval="1h"
            )
            
            self.tasks_stats["correlation_runs"] += 1
            self.tasks_stats["last_correlation"] = datetime.utcnow().isoformat()
            
            # Log summary
            summary = results.get("summary", {})
            logger.info(
                "Correlation analysis completed",
                stock_crypto_pairs=len(results.get("stock_crypto_correlations", [])),
                significant_correlations=summary.get("significant_correlations_count", 0),
                avg_correlation=round(summary.get("average_correlation", 0), 3),
                dominant_regime=summary.get("dominant_market_regime", "unknown"),
                total_runs=self.tasks_stats["correlation_runs"]
            )
            
        except Exception as e:
            self.tasks_stats["errors"] += 1
            self.tasks_stats["last_error"] = str(e)
            logger.error("Error in scheduled correlation analysis", error=str(e))
    
    async def run_market_regime_detection(self):
        """Analyze market regimes for all tracked assets"""
        try:
            logger.info("Starting market regime detection")
            
            regimes_detected = 0
            
            # Analyze stock indices
            for symbol in self.collector.tracked_indices:
                regime = await self.analyzer.analyze_market_regime(
                    symbol,
                    hours_back=168,
                    interval="1h"
                )
                
                if regime.get("primary_regime") != "unknown":
                    # Store regime data
                    regime_doc = {
                        "id": f"regime_{symbol}_{int(datetime.utcnow().timestamp())}",
                        "doc_type": "market_regime",
                        **regime
                    }
                    await self.database.upsert_market_data(regime_doc)
                    regimes_detected += 1
            
            # Analyze top crypto assets
            crypto_symbols = [s.replace('USDT', '') for s in settings.DEFAULT_SYMBOLS[:10]]
            for crypto in crypto_symbols:
                crypto_full = f"{crypto}USDT"
                regime = await self.analyzer.analyze_market_regime(
                    crypto_full,
                    hours_back=168,
                    interval="1h"
                )
                
                if regime.get("primary_regime") != "unknown":
                    regime_doc = {
                        "id": f"regime_{crypto_full}_{int(datetime.utcnow().timestamp())}",
                        "doc_type": "market_regime",
                        **regime
                    }
                    await self.database.upsert_market_data(regime_doc)
                    regimes_detected += 1
            
            logger.info(
                "Market regime detection completed",
                regimes_detected=regimes_detected
            )
            
        except Exception as e:
            logger.error("Error in market regime detection", error=str(e))
    
    async def backfill_historical_data(self):
        """Backfill missing historical data"""
        try:
            logger.info("Starting historical data backfill")
            
            total_records = 0
            
            for symbol in self.collector.tracked_indices:
                try:
                    # Check for gaps in the last 30 days
                    record_count = await self.collector.collect_historical_index_data(
                        symbol,
                        days_back=30
                    )
                    total_records += record_count
                    
                    # Delay between symbols
                    await asyncio.sleep(2)
                    
                except Exception as e:
                    logger.error(f"Error backfilling data for {symbol}", error=str(e))
            
            logger.info(
                "Historical data backfill completed",
                total_records=total_records
            )
            
        except Exception as e:
            logger.error("Error in historical data backfill", error=str(e))
    
    async def generate_correlation_signals(self):
        """Generate trading signals based on correlations"""
        try:
            logger.info("Generating correlation-based trading signals")
            
            # Get top crypto symbols
            crypto_symbols = settings.DEFAULT_SYMBOLS[:10]
            signals_generated = 0
            
            for crypto_symbol in crypto_symbols:
                try:
                    signals = await self.analyzer.get_correlation_based_signals(
                        crypto_symbol,
                        hours_back=168
                    )
                    
                    if signals.get("overall_signal") != "neutral":
                        # Store signals in database
                        signal_doc = {
                            "id": f"corr_signal_{crypto_symbol}_{int(datetime.utcnow().timestamp())}",
                            "doc_type": "correlation_signal",
                            **signals
                        }
                        await self.database.upsert_market_data(signal_doc)
                        signals_generated += 1
                        
                        logger.info(
                            "Correlation signal generated",
                            symbol=crypto_symbol,
                            signal=signals["overall_signal"],
                            confidence=round(signals["confidence"], 2)
                        )
                    
                    await asyncio.sleep(0.2)
                    
                except Exception as e:
                    logger.error(f"Error generating signals for {crypto_symbol}", error=str(e))
            
            logger.info(
                "Correlation signals generation completed",
                signals_generated=signals_generated
            )
            
        except Exception as e:
            logger.error("Error generating correlation signals", error=str(e))
    
    def is_market_hours(self) -> bool:
        """Check if it's during major market hours (US or Asian markets open)"""
        now = datetime.utcnow()
        current_time = now.time()
        
        # US market hours (9:30 AM - 4:00 PM EST = 14:30 - 21:00 UTC)
        us_open = dt_time(14, 30)
        us_close = dt_time(21, 0)
        
        # Asian market hours (9:00 AM JST = 0:00 UTC, close 15:00 JST = 6:00 UTC)
        asian_open = dt_time(0, 0)
        asian_close = dt_time(6, 0)
        
        # European market hours (8:00 AM - 4:30 PM CET = 7:00 - 15:30 UTC)
        eu_open = dt_time(7, 0)
        eu_close = dt_time(15, 30)
        
        is_us_hours = us_open <= current_time <= us_close
        is_asian_hours = asian_open <= current_time <= asian_close
        is_eu_hours = eu_open <= current_time <= eu_close
        
        return is_us_hours or is_asian_hours or is_eu_hours
    
    async def run_scheduled_tasks(self):
        """Main loop for running scheduled tasks"""
        self.running = True
        
        logger.info("Stock index scheduler started")
        
        # Initial data collection
        await self.collect_current_data()
        await self.collect_intraday_data()
        
        last_collection = datetime.utcnow()
        last_correlation = datetime.utcnow()
        last_regime_check = datetime.utcnow()
        
        while self.running:
            try:
                now = datetime.utcnow()
                
                # Current data collection - every 15 minutes during market hours
                if (now - last_collection).seconds >= 900:  # 15 minutes
                    if self.is_market_hours():
                        await self.collect_current_data()
                        await self.collect_intraday_data()
                    else:
                        # Outside market hours, collect less frequently (hourly)
                        if (now - last_collection).seconds >= 3600:
                            await self.collect_current_data()
                    
                    last_collection = now
                
                # Correlation analysis - every hour
                if (now - last_correlation).seconds >= 3600:  # 1 hour
                    await self.run_correlation_analysis()
                    await self.generate_correlation_signals()
                    last_correlation = now
                
                # Market regime detection - every 30 minutes
                if (now - last_regime_check).seconds >= 1800:  # 30 minutes
                    await self.run_market_regime_detection()
                    last_regime_check = now
                
                # Historical data backfill - daily at 2 AM UTC
                if now.hour == 2 and now.minute == 0:
                    await self.backfill_historical_data()
                    await asyncio.sleep(3600)  # Sleep for an hour to avoid re-triggering
                
                # Check for new indices to track
                if now.minute == 0:  # Every hour on the hour
                    reload_result = await self.collector.reload_indices()
                    if reload_result["added"] or reload_result["removed"]:
                        logger.info(
                            "Stock indices updated",
                            added=reload_result["added"],
                            removed=reload_result["removed"]
                        )
                
                # Wait before next iteration
                await asyncio.sleep(60)  # Check every minute
                
            except Exception as e:
                self.tasks_stats["errors"] += 1
                self.tasks_stats["last_error"] = str(e)
                logger.error("Error in scheduler main loop", error=str(e))
                await asyncio.sleep(60)
    
    async def stop(self):
        """Stop the scheduler"""
        self.running = False
        logger.info("Stock index scheduler stopping...")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get scheduler statistics"""
        return {
            "running": self.running,
            "stats": self.tasks_stats,
            "tracked_indices": len(self.collector.tracked_indices) if self.collector else 0,
            "market_hours_active": self.is_market_hours()
        }


async def main():
    """Main entry point for the scheduler"""
    scheduler = StockIndexScheduler()
    
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
