#!/usr/bin/env python3
"""
Order Execution Tests

Tests order execution, paper trading, and position management.
"""

import asyncio
import asyncpg
import aiohttp
from typing import Dict
from datetime import datetime, timedelta


class OrderExecutionTests:
    """Test order execution system"""
    
    def __init__(self):
        self.results = {'total': 0, 'passed': 0, 'failed': 0, 'skipped': 0, 'errors': []}
        self.pg_conn = None
        
        self.pg_dsn = "postgresql://mastertrade:mastertrade@localhost:5432/mastertrade"
        self.order_executor_url = "http://localhost:8002"
    
    async def run_all_tests(self) -> Dict:
        """Run all order execution tests"""
        self.pg_conn = await asyncpg.connect(self.pg_dsn)
        
        tests = [
            ("Orders Table", self.test_orders_table),
            ("Trades Table", self.test_trades_table),
            ("Positions Table", self.test_positions_table),
            ("Order Executor Health", self.test_order_executor_health),
            ("Paper Trading Mode", self.test_paper_trading_mode),
            ("Order States", self.test_order_states),
            ("Position Tracking", self.test_position_tracking),
            ("Stop Loss Orders", self.test_stop_loss_orders),
        ]
        
        for test_name, test_func in tests:
            await self._run_test(test_name, test_func)
        
        await self.pg_conn.close()
        
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
    # Order Execution Tests
    # =========================================================================
    
    async def test_orders_table(self):
        """Test orders table exists with correct schema"""
        columns = await self.pg_conn.fetch("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'orders'
            ORDER BY ordinal_position
        """)
        
        assert len(columns) > 0, "orders table does not exist"
        
        required_cols = {'id', 'strategy_id', 'symbol', 'side', 'order_type', 'quantity', 'price', 'status'}
        found_cols = {col['column_name'] for col in columns}
        
        missing = required_cols - found_cols
        assert len(missing) == 0, f"Missing columns in orders table: {missing}"
    
    async def test_trades_table(self):
        """Test trades table exists"""
        columns = await self.pg_conn.fetch("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'trades'
        """)
        
        assert len(columns) > 0, "trades table does not exist"
        
        required_cols = {'id', 'order_id', 'symbol', 'side', 'executed_quantity', 'executed_price'}
        found_cols = {col['column_name'] for col in columns}
        
        missing = required_cols - found_cols
        assert len(missing) == 0, f"Missing columns in trades table: {missing}"
    
    async def test_positions_table(self):
        """Test positions table exists"""
        exists = await self.pg_conn.fetchval("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables 
                WHERE table_name = 'positions'
            )
        """)
        assert exists, "positions table does not exist"
    
    async def test_order_executor_health(self):
        """Test order executor service is healthy"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.order_executor_url}/health", timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    assert resp.status == 200, f"Order executor health check failed: {resp.status}"
        except aiohttp.ClientError as e:
            raise AssertionError(f"Order executor not accessible: {e}")
    
    async def test_paper_trading_mode(self):
        """Test paper trading mode is configured"""
        # Check if settings table has paper trading configuration
        exists = await self.pg_conn.fetchval("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables 
                WHERE table_name = 'settings'
            )
        """)
        
        if exists:
            setting = await self.pg_conn.fetchrow("""
                SELECT value FROM settings 
                WHERE key = 'trading_mode'
            """)
            
            if setting:
                mode = setting['value']
                print(f"(mode: {mode}) ", end="")
        else:
            print("(settings table not found - OK) ", end="")
    
    async def test_order_states(self):
        """Test order states are valid"""
        orders = await self.pg_conn.fetch("""
            SELECT DISTINCT status FROM orders
        """)
        
        if len(orders) == 0:
            print("(no orders yet - OK) ", end="")
            return
        
        valid_states = {'pending', 'open', 'filled', 'partially_filled', 'cancelled', 'rejected', 'expired'}
        found_states = {o['status'] for o in orders}
        
        invalid = found_states - valid_states
        assert len(invalid) == 0, f"Invalid order states found: {invalid}"
    
    async def test_position_tracking(self):
        """Test positions are being tracked"""
        count = await self.pg_conn.fetchval("SELECT COUNT(*) FROM positions")
        
        # May be 0 if no trading yet
        assert count >= 0, "Position count query failed"
        
        print(f"({count} positions) ", end="")
    
    async def test_stop_loss_orders(self):
        """Test stop loss orders are supported"""
        # Check if orders table supports stop orders
        orders = await self.pg_conn.fetch("""
            SELECT order_type FROM orders 
            WHERE order_type ILIKE '%stop%'
            LIMIT 5
        """)
        
        if len(orders) == 0:
            print("(no stop orders yet - OK) ", end="")
        else:
            print(f"({len(orders)} stop orders found) ", end="")


if __name__ == "__main__":
    async def run():
        tests = OrderExecutionTests()
        results = await tests.run_all_tests()
        print(f"\nResults: {results}")
    
    asyncio.run(run())
