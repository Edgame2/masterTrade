#!/usr/bin/env python3
"""
TimescaleDB Integration Test

This script tests the TimescaleDB integration with all three data stores:
- PriceDataStore (OHLCV data)
- SentimentDataStore (sentiment analysis)
- FlowDataStore (on-chain flows)

Run this after starting the TimescaleDB service to verify the integration.

Usage:
    python test_timescaledb_integration.py
"""

import asyncio
import asyncpg
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import structlog

# Configure logging
structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer()
    ]
)
logger = structlog.get_logger()

# Import data stores
import sys
sys.path.append('/home/neodyme/Documents/Projects/masterTrade/market_data_service')

from price_data_store import PriceDataStore
from sentiment_store import SentimentDataStore
from flow_data_store import FlowDataStore


class MockDatabase:
    """Mock database connection for testing"""
    
    def __init__(self, pool):
        self.pool = pool
    
    async def execute(self, query, *args):
        async with self.pool.acquire() as conn:
            return await conn.execute(query, *args)
    
    async def executemany(self, query, data):
        async with self.pool.acquire() as conn:
            return await conn.executemany(query, data)
    
    async def fetch(self, query, *args):
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, *args)
    
    async def fetchrow(self, query, *args):
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, *args)


async def test_price_store(db: MockDatabase):
    """Test PriceDataStore"""
    logger.info("Testing PriceDataStore...")
    
    store = PriceDataStore(db)
    now = datetime.now(timezone.utc)
    
    # Test single insert
    success = await store.store_price(
        symbol="BTCUSDT",
        interval="1m",
        timestamp=now,
        open=50000.0,
        high=50100.0,
        low=49900.0,
        close=50050.0,
        volume=10.5
    )
    assert success, "Failed to store price"
    logger.info("✅ Single price insert successful")
    
    # Test batch insert
    prices = [
        {
            'symbol': 'BTCUSDT',
            'interval': '1m',
            'timestamp': now - timedelta(minutes=i),
            'open': 50000.0 - i * 10,
            'high': 50100.0 - i * 10,
            'low': 49900.0 - i * 10,
            'close': 50050.0 - i * 10,
            'volume': 10.0 + i
        }
        for i in range(1, 61)  # 60 minutes
    ]
    count = await store.store_prices_batch(prices)
    assert count == 60, f"Expected 60 inserts, got {count}"
    logger.info("✅ Batch price insert successful (60 rows)")
    
    # Test OHLCV query
    ohlcv = await store.get_ohlcv(
        symbol="BTCUSDT",
        interval="1h",
        start_time=now - timedelta(hours=2),
        end_time=now
    )
    logger.info(f"✅ OHLCV query returned {len(ohlcv)} data points")
    
    # Test latest price
    latest = await store.get_latest_price("BTCUSDT", "1m")
    assert latest is not None, "Failed to get latest price"
    logger.info(f"✅ Latest price: ${latest['close']:.2f}")
    
    # Test price change
    change = await store.get_price_change("BTCUSDT", hours=1)
    logger.info(f"✅ Price change: {change.get('percent_change', 0):.2f}%")
    
    logger.info("✅ PriceDataStore tests passed!\n")


async def test_sentiment_store(db: MockDatabase):
    """Test SentimentDataStore"""
    logger.info("Testing SentimentDataStore...")
    
    store = SentimentDataStore(db)
    now = datetime.now(timezone.utc)
    
    # Test single insert
    success = await store.store_sentiment(
        asset="BTC",
        source="twitter",
        timestamp=now,
        sentiment_score=0.65,
        sentiment_label="bullish",
        volume=150,
        engagement_score=2500.0
    )
    assert success, "Failed to store sentiment"
    logger.info("✅ Single sentiment insert successful")
    
    # Test batch insert
    sentiments = [
        {
            'asset': 'BTC',
            'source': 'twitter',
            'timestamp': now - timedelta(hours=i),
            'sentiment_score': 0.5 + (i * 0.01),
            'volume': 100 + i * 10,
            'engagement_score': 2000.0 + i * 100
        }
        for i in range(1, 25)  # 24 hours
    ]
    count = await store.store_sentiments_batch(sentiments)
    assert count == 24, f"Expected 24 inserts, got {count}"
    logger.info("✅ Batch sentiment insert successful (24 rows)")
    
    # Test sentiment trend
    trend = await store.get_sentiment_trend(
        asset="BTC",
        hours=24
    )
    if trend:
        logger.info(f"✅ Sentiment trend: {trend.get('trend', 'N/A')} ({trend.get('recent_sentiment', 0):.2f})")
    
    # Test sentiment by source
    by_source = await store.get_sentiment_by_source(
        asset="BTC",
        hours=24
    )
    logger.info(f"✅ Sentiment by source: {len(by_source)} sources")
    
    # Test latest sentiment
    latest = await store.get_latest_sentiment("BTC", "twitter")
    if latest:
        logger.info(f"✅ Latest sentiment: {latest['sentiment_label']} ({latest['sentiment_score']:.2f})")
    
    logger.info("✅ SentimentDataStore tests passed!\n")


async def test_flow_store(db: MockDatabase):
    """Test FlowDataStore"""
    logger.info("Testing FlowDataStore...")
    
    store = FlowDataStore(db)
    now = datetime.now(timezone.utc)
    
    # Test single insert
    success = await store.store_flow(
        asset="BTC",
        flow_type="exchange_inflow",
        timestamp=now,
        amount=100.5,
        source="binance",
        usd_value=5025000.0
    )
    assert success, "Failed to store flow"
    logger.info("✅ Single flow insert successful")
    
    # Test batch insert
    flows = [
        {
            'asset': 'BTC',
            'flow_type': 'exchange_inflow' if i % 2 == 0 else 'exchange_outflow',
            'timestamp': now - timedelta(hours=i),
            'amount': 50.0 + i * 5,
            'source': 'binance',
            'usd_value': 2500000.0 + i * 250000
        }
        for i in range(1, 25)  # 24 hours
    ]
    count = await store.store_flows_batch(flows)
    assert count == 24, f"Expected 24 inserts, got {count}"
    logger.info("✅ Batch flow insert successful (24 rows)")
    
    # Test net flow
    net_flow = await store.get_net_flow(
        asset="BTC",
        hours=24
    )
    if net_flow:
        logger.info(f"✅ Net flow: {net_flow.get('net_flow', 0):.2f} BTC")
    
    # Test whale activity
    whales = await store.get_whale_activity(
        asset="BTC",
        hours=24,
        min_amount=10.0
    )
    logger.info(f"✅ Whale transactions: {len(whales)}")
    
    # Test exchange flows
    exchanges = await store.get_exchange_flows(
        asset="BTC",
        hours=24
    )
    logger.info(f"✅ Exchange flows: {len(exchanges)} exchanges")
    
    logger.info("✅ FlowDataStore tests passed!\n")


async def main():
    """Main test function"""
    
    logger.info("=" * 60)
    logger.info("TimescaleDB Integration Test")
    logger.info("=" * 60 + "\n")
    
    # Connect to TimescaleDB
    try:
        pool = await asyncpg.create_pool(
            host='localhost',
            port=5433,
            database='mastertrade_timeseries',
            user='mastertrade',
            password='mastertrade',
            min_size=2,
            max_size=5
        )
        logger.info("✅ Connected to TimescaleDB\n")
    except Exception as e:
        logger.error(f"❌ Failed to connect to TimescaleDB: {e}")
        logger.info("\nMake sure TimescaleDB service is running:")
        logger.info("  docker-compose up -d timescaledb")
        return
    
    db = MockDatabase(pool)
    
    try:
        # Run tests
        await test_price_store(db)
        await test_sentiment_store(db)
        await test_flow_store(db)
        
        logger.info("=" * 60)
        logger.info("✅ All tests passed successfully!")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"❌ Test failed: {e}", exc_info=True)
    
    finally:
        await pool.close()
        logger.info("\n✅ Database connection closed")


if __name__ == "__main__":
    asyncio.run(main())
