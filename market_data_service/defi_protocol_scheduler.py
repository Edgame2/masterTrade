#!/usr/bin/env python3
"""
DeFi Protocol Metrics Scheduler

Runs the DeFi protocol collector on a schedule to gather TVL, volume, fees,
and other metrics from major DeFi protocols via TheGraph and Dune Analytics.
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from database import Database
from defi_protocol_collector import run_defi_collector_scheduler
import structlog

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = structlog.get_logger()


async def main():
    """Main entry point for DeFi metrics scheduler."""
    
    # Get configuration from environment
    dune_api_key = os.getenv("DUNE_API_KEY")
    interval_minutes = int(os.getenv("DEFI_COLLECTION_INTERVAL_MINUTES", "60"))
    
    # Database connection
    db_url = os.getenv(
        "DATABASE_URL",
        "postgresql://mastertrade:mastertrade123@localhost:5432/mastertrade"
    )
    
    logger.info(
        "Starting DeFi protocol metrics scheduler",
        interval_minutes=interval_minutes,
        dune_enabled=bool(dune_api_key)
    )
    
    # Initialize database
    database = Database(db_url)
    await database.connect()
    
    try:
        # Run scheduler
        await run_defi_collector_scheduler(
            database=database,
            dune_api_key=dune_api_key,
            interval_minutes=interval_minutes
        )
    except KeyboardInterrupt:
        logger.info("Shutting down DeFi protocol scheduler")
    finally:
        await database.close()


if __name__ == "__main__":
    asyncio.run(main())
