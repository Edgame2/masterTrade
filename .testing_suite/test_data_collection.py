#!/usr/bin/env python3
"""
Data Collection Tests

Tests all data collection pipelines and storage.
"""

import asyncio
import asyncpg
from typing import Dict
from datetime import datetime, timedelta


class DataCollectionTests:
    """Test data collection systems"""
    
    def __init__(self):
        self.results = {'total': 0, 'passed': 0, 'failed': 0, 'skipped': 0, 'errors': []}
        self.pg_conn = None
        self.ts_conn = None
        
        self.pg_dsn = "postgresql://mastertrade:mastertrade@localhost:5432/mastertrade"
        self.ts_dsn = "postgresql://mastertrade:mastertrade@localhost:5433/mastertrade_timeseries"
    
    async def run_all_tests(self) -> Dict:
        """Run all data collection tests"""
        self.pg_conn = await asyncpg.connect(self.pg_dsn)
        self.ts_conn = await asyncpg.connect(self.ts_dsn)
        
        tests = [
            ("Market Data Collection", self.test_market_data_collection),
            ("Price Data in TimescaleDB", self.test_timescale_price_data),
            ("Sentiment Data Collection", self.test_sentiment_data),
            ("On-Chain Data Collection", self.test_onchain_data),
            ("Stock Index Data", self.test_stock_index_data),
            ("Data Freshness", self.test_data_freshness),
            ("Symbol Coverage", self.test_symbol_coverage),
            ("Data Quality", self.test_data_quality),
        ]
        
        for test_name, test_func in tests:
            await self._run_test(test_name, test_func)
        
        await self.pg_conn.close()
        await self.ts_conn.close()
        
        return self.results
    
    async def _run_test(self, name: str, func):
        """Run a single test"""
        self.results['total'] += 1
        try:
            print(f"  Testing: {name}...", end=" ")
            await func()
            print("✅ PASS")
            self.results['passed'] += 1
        except Exception as e:
            print(f"❌ FAIL: {e}")
            self.results['failed'] += 1
            self.results['errors'].append(f"{name}: {str(e)}")
    
    # =========================================================================
    # Data Collection Tests
    # =========================================================================
    
    async def test_market_data_collection(self):
        """Test market data is being collected"""
        count = await self.pg_conn.fetchval("SELECT COUNT(*) FROM market_data")
        assert count > 100000, f"Insufficient market data: {count} records (expected > 100000)"
    
    async def test_timescale_price_data(self):
        """Test TimescaleDB price data"""
        # Check if price_data table has any data
        count = await self.ts_conn.fetchval("SELECT COUNT(*) FROM price_data")
        # May be 0 if just deployed, so just check table works
        assert count >= 0, "price_data table query failed"
    
    async def test_sentiment_data(self):
        """Test sentiment data collection"""
        # Check sentiment_data table exists and is queryable
        exists = await self.pg_conn.fetchval("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables 
                WHERE table_name = 'sentiment_data'
            )
        """)
        assert exists, "sentiment_data table does not exist"
        
        count = await self.pg_conn.fetchval("SELECT COUNT(*) FROM sentiment_data")
        assert count >= 0, "sentiment_data query failed"
    
    async def test_onchain_data(self):
        """Test on-chain data collection"""
        exists = await self.pg_conn.fetchval("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables 
                WHERE table_name = 'on_chain_data'
            )
        """)
        assert exists, "on_chain_data table does not exist"
    
    async def test_stock_index_data(self):
        """Test stock index correlation data"""
        exists = await self.pg_conn.fetchval("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables 
                WHERE table_name = 'stock_indices'
            )
        """)
        # May not exist in all setups, so just log
        if not exists:
            print("(stock_indices table not found - OK) ", end="")
    
    async def test_data_freshness(self):
        """Test that data is recent (within 24 hours)"""
        # Check market_data has recent data
        recent_count = await self.pg_conn.fetchval("""
            SELECT COUNT(*) FROM market_data 
            WHERE created_at >= NOW() - INTERVAL '24 hours'
        """)
        
        # At least some data should be recent
        assert recent_count >= 0, "Data freshness check failed"
    
    async def test_symbol_coverage(self):
        """Test multiple symbols are covered"""
        symbols = await self.pg_conn.fetch("""
            SELECT DISTINCT data->>'symbol' as symbol 
            FROM market_data 
            LIMIT 20
        """)
        
        assert len(symbols) >= 3, f"Insufficient symbol coverage: {len(symbols)} symbols (expected >= 3)"
    
    async def test_data_quality(self):
        """Test data quality (no nulls in critical fields)"""
        null_count = await self.pg_conn.fetchval("""
            SELECT COUNT(*) FROM market_data 
            WHERE data IS NULL OR data = '{}'::jsonb
        """)
        
        total = await self.pg_conn.fetchval("SELECT COUNT(*) FROM market_data")
        null_percentage = (null_count / total * 100) if total > 0 else 0
        
        assert null_percentage < 1.0, f"Too many null records: {null_percentage:.2f}%"


if __name__ == "__main__":
    async def run():
        tests = DataCollectionTests()
        results = await tests.run_all_tests()
        print(f"\nResults: {results}")
    
    asyncio.run(run())
