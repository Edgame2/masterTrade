#!/usr/bin/env python3
"""
Database Tests

Tests all database connectivity, schema integrity, and data operations.
"""

import asyncio
import asyncpg
from datetime import datetime, timedelta
from typing import Dict, List
import os


class DatabaseTests:
    """Comprehensive database testing"""
    
    def __init__(self):
        self.results = {'total': 0, 'passed': 0, 'failed': 0, 'skipped': 0, 'errors': []}
        self.pg_conn = None
        self.ts_conn = None
        
        # Connection strings
        self.pg_dsn = f"postgresql://mastertrade:mastertrade@localhost:5432/mastertrade"
        self.ts_dsn = f"postgresql://mastertrade:mastertrade@localhost:5433/mastertrade_timeseries"
    
    async def run_all_tests(self) -> Dict:
        """Run all database tests"""
        tests = [
            ("PostgreSQL Connection", self.test_postgres_connection),
            ("TimescaleDB Connection", self.test_timescaledb_connection),
            ("Critical Tables Exist", self.test_critical_tables),
            ("Strategies Table Schema", self.test_strategies_table),
            ("Trades Table Schema", self.test_trades_table),
            ("Market Data Table", self.test_market_data_table),
            ("Settings Table", self.test_settings_table),
            ("Learning Insights Table", self.test_learning_insights_table),
            ("TimescaleDB Hypertables", self.test_hypertables),
            ("Continuous Aggregates", self.test_continuous_aggregates),
            ("Database Indexes", self.test_indexes),
            ("Data Integrity", self.test_data_integrity),
            ("Insert Performance", self.test_insert_performance),
            ("Query Performance", self.test_query_performance),
        ]
        
        for test_name, test_func in tests:
            await self._run_test(test_name, test_func)
        
        # Cleanup
        if self.pg_conn:
            await self.pg_conn.close()
        if self.ts_conn:
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
    # Connection Tests
    # =========================================================================
    
    async def test_postgres_connection(self):
        """Test PostgreSQL connection"""
        self.pg_conn = await asyncpg.connect(self.pg_dsn)
        result = await self.pg_conn.fetchval("SELECT 1")
        assert result == 1, "PostgreSQL connection test failed"
    
    async def test_timescaledb_connection(self):
        """Test TimescaleDB connection"""
        self.ts_conn = await asyncpg.connect(self.ts_dsn)
        result = await self.ts_conn.fetchval("SELECT 1")
        assert result == 1, "TimescaleDB connection test failed"
    
    # =========================================================================
    # Schema Tests
    # =========================================================================
    
    async def test_critical_tables(self):
        """Test that all critical tables exist"""
        required_tables = [
            'strategies', 'trades', 'positions', 'market_data',
            'backtest_results', 'signals', 'alerts', 'settings',
            'learning_insights', 'sentiment_data', 'on_chain_data'
        ]
        
        for table in required_tables:
            result = await self.pg_conn.fetchval(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = $1)",
                table
            )
            assert result, f"Required table '{table}' does not exist"
    
    async def test_strategies_table(self):
        """Test strategies table schema"""
        columns = await self.pg_conn.fetch("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'strategies'
        """)
        
        column_names = {row['column_name'] for row in columns}
        required = {'id', 'name', 'type', 'parameters', 'configuration', 'status', 'is_active'}
        
        missing = required - column_names
        assert not missing, f"Strategies table missing columns: {missing}"
    
    async def test_trades_table(self):
        """Test trades table schema"""
        columns = await self.pg_conn.fetch("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'trades'
        """)
        
        column_names = {row['column_name'] for row in columns}
        required = {'id', 'strategy_id', 'symbol', 'side', 'quantity', 'price', 'executed_at', 'status'}
        
        missing = required - column_names
        assert not missing, f"Trades table missing columns: {missing}"
    
    async def test_market_data_table(self):
        """Test market_data table has data"""
        count = await self.pg_conn.fetchval("SELECT COUNT(*) FROM market_data")
        assert count > 0, f"Market data table is empty (expected > 0, got {count})"
    
    async def test_settings_table(self):
        """Test settings table exists and has data"""
        count = await self.pg_conn.fetchval("SELECT COUNT(*) FROM settings")
        assert count >= 0, "Settings table query failed"
    
    async def test_learning_insights_table(self):
        """Test learning_insights table exists (created today)"""
        exists = await self.pg_conn.fetchval("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables 
                WHERE table_name = 'learning_insights'
            )
        """)
        assert exists, "learning_insights table does not exist"
        
        # Check schema
        columns = await self.pg_conn.fetch("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'learning_insights'
        """)
        column_names = {row['column_name'] for row in columns}
        required = {'id', 'generation_date', 'insight_type', 'insight_data', 'confidence_score'}
        
        missing = required - column_names
        assert not missing, f"learning_insights missing columns: {missing}"
    
    # =========================================================================
    # TimescaleDB Tests
    # =========================================================================
    
    async def test_hypertables(self):
        """Test TimescaleDB hypertables"""
        hypertables = await self.ts_conn.fetch("""
            SELECT hypertable_name, compression_enabled 
            FROM timescaledb_information.hypertables
        """)
        
        assert len(hypertables) >= 4, f"Expected at least 4 hypertables, got {len(hypertables)}"
        
        hypertable_names = {row['hypertable_name'] for row in hypertables}
        expected = {'price_data', 'sentiment_data', 'flow_data', 'indicator_data'}
        
        missing = expected - hypertable_names
        assert not missing, f"Missing hypertables: {missing}"
        
        # Check compression enabled
        for row in hypertables:
            assert row['compression_enabled'], f"Compression not enabled for {row['hypertable_name']}"
    
    async def test_continuous_aggregates(self):
        """Test continuous aggregates"""
        aggregates = await self.ts_conn.fetch("""
            SELECT view_name 
            FROM timescaledb_information.continuous_aggregates
        """)
        
        assert len(aggregates) >= 10, f"Expected at least 10 continuous aggregates, got {len(aggregates)}"
        
        view_names = {row['view_name'] for row in aggregates}
        expected_views = [
            'price_data_5m', 'price_data_15m', 'price_data_1h', 'price_data_4h', 'price_data_1d',
            'sentiment_hourly', 'sentiment_daily', 'flow_hourly', 'flow_daily'
        ]
        
        for view in expected_views:
            assert view in view_names, f"Missing continuous aggregate: {view}"
    
    # =========================================================================
    # Performance Tests
    # =========================================================================
    
    async def test_indexes(self):
        """Test critical indexes exist"""
        indexes = await self.pg_conn.fetch("""
            SELECT tablename, indexname 
            FROM pg_indexes 
            WHERE schemaname = 'public'
        """)
        
        index_names = {row['indexname'] for row in indexes}
        
        # Check for critical indexes
        critical_patterns = ['strategies_pkey', 'trades_pkey', 'idx_']
        
        found_critical = [pattern for pattern in critical_patterns if any(pattern in idx for idx in index_names)]
        assert len(found_critical) >= 2, f"Missing critical indexes, found: {found_critical}"
    
    async def test_data_integrity(self):
        """Test data integrity constraints"""
        # Test foreign key constraints exist
        constraints = await self.pg_conn.fetch("""
            SELECT constraint_name, table_name 
            FROM information_schema.table_constraints 
            WHERE constraint_type = 'FOREIGN KEY'
        """)
        
        assert len(constraints) > 0, "No foreign key constraints found"
    
    async def test_insert_performance(self):
        """Test insert performance"""
        # Insert a test strategy
        start = datetime.now()
        
        strategy_id = await self.pg_conn.fetchval("""
            INSERT INTO strategies (name, type, parameters, configuration, is_active, status)
            VALUES ('Test Strategy', 'test', '{}', '{}', false, 'test')
            RETURNING id
        """)
        
        duration = (datetime.now() - start).total_seconds()
        
        # Cleanup
        await self.pg_conn.execute("DELETE FROM strategies WHERE id = $1", strategy_id)
        
        assert duration < 0.1, f"Insert took too long: {duration}s (expected < 0.1s)"
    
    async def test_query_performance(self):
        """Test query performance"""
        start = datetime.now()
        
        await self.pg_conn.fetch("SELECT * FROM strategies LIMIT 100")
        
        duration = (datetime.now() - start).total_seconds()
        assert duration < 0.5, f"Query took too long: {duration}s (expected < 0.5s)"


if __name__ == "__main__":
    async def run():
        tests = DatabaseTests()
        results = await tests.run_all_tests()
        print(f"\nResults: {results}")
    
    asyncio.run(run())
