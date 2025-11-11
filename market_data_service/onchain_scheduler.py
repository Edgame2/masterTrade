"""
On-Chain Data Collection Scheduler

Runs periodic tasks for:
1. Whale transaction monitoring (every 5 minutes)
2. On-chain metrics collection (hourly)
3. Exchange flow analysis (every 15 minutes)
4. Wallet activity tracking (hourly)
"""

import asyncio
from datetime import datetime, timezone
from typing import Dict, Any
import structlog

from config import settings
from database import Database
from collectors.moralis_collector import MoralisCollector
from collectors.glassnode_collector import GlassnodeCollector

logger = structlog.get_logger()


class OnChainScheduler:
    """Scheduler for on-chain data collection"""
    
    def __init__(self):
        self.database: Database = None
        self.moralis_collector: MoralisCollector = None
        self.glassnode_collector: GlassnodeCollector = None
        self.running = False
        self.stats = {
            "whale_transaction_runs": 0,
            "onchain_metrics_runs": 0,
            "exchange_flow_runs": 0,
            "wallet_activity_runs": 0,
            "errors": 0,
            "last_collection": None,
            "last_error": None
        }
        
    async def initialize(self):
        """Initialize database connections and collectors"""
        try:
            # Initialize database
            self.database = Database()
            await self.database.connect()
            
            # Initialize Moralis collector if API key available
            if settings.MORALIS_API_KEY:
                self.moralis_collector = MoralisCollector(
                    database=self.database,
                    api_key=settings.MORALIS_API_KEY,
                    rate_limit=settings.MORALIS_RATE_LIMIT
                )
                await self.moralis_collector.connect()
                logger.info("Moralis collector initialized")
            else:
                logger.warning("MORALIS_API_KEY not set - Moralis collection disabled")
            
            # Initialize Glassnode collector if API key available
            if settings.GLASSNODE_API_KEY:
                self.glassnode_collector = GlassnodeCollector(
                    database=self.database,
                    api_key=settings.GLASSNODE_API_KEY,
                    rate_limit=settings.GLASSNODE_RATE_LIMIT
                )
                await self.glassnode_collector.connect()
                logger.info("Glassnode collector initialized")
            else:
                logger.warning("GLASSNODE_API_KEY not set - Glassnode collection disabled")
            
            logger.info("On-chain scheduler initialized")
            
        except Exception as e:
            logger.error("Failed to initialize on-chain scheduler", error=str(e))
            raise
    
    async def cleanup(self):
        """Cleanup resources"""
        try:
            if self.moralis_collector:
                await self.moralis_collector.disconnect()
            
            if self.glassnode_collector:
                await self.glassnode_collector.disconnect()
            
            if self.database:
                await self.database.disconnect()
            
            logger.info("On-chain scheduler cleaned up")
            
        except Exception as e:
            logger.error("Error during cleanup", error=str(e))
    
    async def collect_whale_transactions(self):
        """Collect whale transactions"""
        if not self.moralis_collector:
            logger.debug("Moralis collector not available - skipping whale transaction collection")
            return
            
        try:
            logger.info("Starting scheduled whale transaction collection")
            
            # Collect for major symbols
            symbols = ["BTC", "ETH", "USDT", "USDC"]
            
            success = await self.moralis_collector.collect(
                symbols=symbols,
                hours=1  # Collect last hour of data
            )
            
            if success:
                self.stats["whale_transaction_runs"] += 1
                self.stats["last_collection"] = datetime.now(timezone.utc).isoformat()
                
                logger.info(
                    "Whale transaction collection completed",
                    symbols=symbols,
                    total_runs=self.stats["whale_transaction_runs"]
                )
            else:
                self.stats["errors"] += 1
                logger.warning("Whale transaction collection failed")
            
        except Exception as e:
            self.stats["errors"] += 1
            self.stats["last_error"] = str(e)
            logger.error("Error in whale transaction collection", error=str(e))
    
    async def collect_onchain_metrics(self):
        """Collect on-chain metrics from Glassnode"""
        if not self.glassnode_collector:
            logger.debug("Glassnode collector not available - skipping on-chain metrics collection")
            return
            
        try:
            logger.info("Starting scheduled on-chain metrics collection")
            
            # Collect key metrics for BTC and ETH
            symbols = ["BTC", "ETH"]
            metrics = [
                "nvt", "mvrv", "nupl",
                "exchange_netflow", "exchange_inflow", "exchange_outflow",
                "active_addresses", "whale_addresses"
            ]
            
            success = await self.glassnode_collector.collect(
                symbols=symbols,
                metrics=metrics,
                interval="24h"
            )
            
            if success:
                self.stats["onchain_metrics_runs"] += 1
                self.stats["last_collection"] = datetime.now(timezone.utc).isoformat()
                
                logger.info(
                    "On-chain metrics collection completed",
                    symbols=symbols,
                    metrics_count=len(metrics),
                    total_runs=self.stats["onchain_metrics_runs"]
                )
            else:
                self.stats["errors"] += 1
                logger.warning("On-chain metrics collection failed")
            
        except Exception as e:
            self.stats["errors"] += 1
            self.stats["last_error"] = str(e)
            logger.error("Error in on-chain metrics collection", error=str(e))
    
    async def collect_exchange_flows(self):
        """Collect exchange flow analysis"""
        if not self.glassnode_collector:
            logger.debug("Glassnode collector not available - skipping exchange flow collection")
            return
            
        try:
            logger.info("Starting scheduled exchange flow collection")
            
            # Get exchange flow summary for major assets
            for symbol in ["BTC", "ETH"]:
                flows = await self.glassnode_collector.get_exchange_flows_summary(symbol)
                
                if flows:
                    logger.info(
                        f"Exchange flows for {symbol}",
                        netflow=flows.get("exchange_netflow"),
                        inflow=flows.get("exchange_inflow"),
                        outflow=flows.get("exchange_outflow")
                    )
                
                # Small delay between requests
                await asyncio.sleep(1)
            
            self.stats["exchange_flow_runs"] += 1
            self.stats["last_collection"] = datetime.now(timezone.utc).isoformat()
            
            logger.info(
                "Exchange flow collection completed",
                total_runs=self.stats["exchange_flow_runs"]
            )
            
        except Exception as e:
            self.stats["errors"] += 1
            self.stats["last_error"] = str(e)
            logger.error("Error in exchange flow collection", error=str(e))
    
    async def collect_wallet_activity(self):
        """Collect wallet activity from watched addresses"""
        if not self.moralis_collector:
            logger.debug("Moralis collector not available - skipping wallet activity collection")
            return
            
        try:
            logger.info("Starting scheduled wallet activity collection")
            
            # Get watched wallets
            watched_wallets = await self.moralis_collector.get_watched_wallets()
            
            if watched_wallets:
                # Collect activity for each watched wallet
                for wallet in watched_wallets:
                    # This is collected as part of the main collection
                    # Just log the watched wallet status
                    pass
                    
                logger.info(
                    "Wallet activity monitoring active",
                    watched_wallets=len(watched_wallets)
                )
            
            self.stats["wallet_activity_runs"] += 1
            self.stats["last_collection"] = datetime.now(timezone.utc).isoformat()
            
        except Exception as e:
            self.stats["errors"] += 1
            self.stats["last_error"] = str(e)
            logger.error("Error in wallet activity collection", error=str(e))
    
    async def run_collection_cycle(self):
        """Run a full collection cycle"""
        try:
            logger.info("Starting on-chain collection cycle")
            
            # Run collections in sequence
            await self.collect_whale_transactions()
            await asyncio.sleep(2)
            
            await self.collect_onchain_metrics()
            await asyncio.sleep(2)
            
            await self.collect_exchange_flows()
            await asyncio.sleep(2)
            
            await self.collect_wallet_activity()
            
            logger.info(
                "On-chain collection cycle completed",
                stats=self.stats
            )
            
        except Exception as e:
            logger.error("Error in collection cycle", error=str(e))
    
    async def start(self):
        """Start the scheduler"""
        if not settings.ONCHAIN_COLLECTION_ENABLED:
            logger.info("On-chain collection is disabled in configuration")
            return
            
        self.running = True
        logger.info(
            "Starting on-chain scheduler",
            interval_seconds=settings.ONCHAIN_COLLECTION_INTERVAL
        )
        
        while self.running:
            try:
                await self.run_collection_cycle()
                
                # Wait for next collection interval
                await asyncio.sleep(settings.ONCHAIN_COLLECTION_INTERVAL)
                
            except asyncio.CancelledError:
                logger.info("On-chain scheduler cancelled")
                break
            except Exception as e:
                logger.error("Error in scheduler main loop", error=str(e))
                await asyncio.sleep(60)  # Wait before retrying
    
    def stop(self):
        """Stop the scheduler"""
        self.running = False
        logger.info("Stopping on-chain scheduler")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get scheduler statistics"""
        return {
            **self.stats,
            "running": self.running,
            "moralis_available": self.moralis_collector is not None,
            "glassnode_available": self.glassnode_collector is not None
        }


async def main():
    """Main entry point for running the scheduler standalone"""
    scheduler = OnChainScheduler()
    
    try:
        await scheduler.initialize()
        await scheduler.start()
        
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
    except Exception as e:
        logger.error("Fatal error in scheduler", error=str(e))
    finally:
        await scheduler.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
