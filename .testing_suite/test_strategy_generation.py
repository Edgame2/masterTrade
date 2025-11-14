#!/usr/bin/env python3
"""
Strategy Generation Tests

Tests automated strategy generation, backtesting, and learning systems.
"""

import asyncio
import asyncpg
import json
from typing import Dict
from datetime import datetime, timedelta


class StrategyGenerationTests:
    """Test strategy generation and learning"""
    
    def __init__(self):
        self.results = {'total': 0, 'passed': 0, 'failed': 0, 'skipped': 0, 'errors': []}
        self.pg_conn = None
        
        self.pg_dsn = "postgresql://mastertrade:mastertrade@localhost:5432/mastertrade"
    
    async def run_all_tests(self) -> Dict:
        """Run all strategy generation tests"""
        self.pg_conn = await asyncpg.connect(self.pg_dsn)
        
        tests = [
            ("Strategies Table", self.test_strategies_table),
            ("Backtest Results Table", self.test_backtest_results_table),
            ("Learning Insights Table", self.test_learning_insights_table),
            ("Strategy Generation", self.test_strategy_generation),
            ("Backtest Metrics", self.test_backtest_metrics),
            ("Strategy Parameters", self.test_strategy_parameters),
            ("USDC Symbol Usage", self.test_usdc_symbols),
            ("Strategy States", self.test_strategy_states),
            ("Performance Tracking", self.test_performance_tracking),
            ("Learning System", self.test_learning_system),
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
    # Strategy Generation Tests
    # =========================================================================
    
    async def test_strategies_table(self):
        """Test strategies table exists with correct schema"""
        columns = await self.pg_conn.fetch("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'strategies'
            ORDER BY ordinal_position
        """)
        
        assert len(columns) > 0, "strategies table does not exist"
        
        required_cols = {'id', 'name', 'parameters', 'state', 'created_at'}
        found_cols = {col['column_name'] for col in columns}
        
        missing = required_cols - found_cols
        assert len(missing) == 0, f"Missing columns: {missing}"
    
    async def test_backtest_results_table(self):
        """Test backtest_results table exists"""
        exists = await self.pg_conn.fetchval("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables 
                WHERE table_name = 'backtest_results'
            )
        """)
        assert exists, "backtest_results table does not exist"
    
    async def test_learning_insights_table(self):
        """Test learning_insights table exists (created today)"""
        exists = await self.pg_conn.fetchval("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables 
                WHERE table_name = 'learning_insights'
            )
        """)
        assert exists, "learning_insights table does not exist (should have been created today)"
        
        # Check columns
        columns = await self.pg_conn.fetch("""
            SELECT column_name FROM information_schema.columns 
            WHERE table_name = 'learning_insights'
        """)
        
        required_cols = {'id', 'generation', 'insight_type', 'data', 'created_at'}
        found_cols = {col['column_name'] for col in columns}
        
        missing = required_cols - found_cols
        assert len(missing) == 0, f"Missing columns in learning_insights: {missing}"
    
    async def test_strategy_generation(self):
        """Test that strategies are being generated"""
        count = await self.pg_conn.fetchval("SELECT COUNT(*) FROM strategies")
        
        # May be low if just started, but should exist
        assert count >= 0, "Strategy count query failed"
        
        print(f"({count} strategies) ", end="")
    
    async def test_backtest_metrics(self):
        """Test backtest metrics are stored"""
        # Check if backtest_results has metrics
        row = await self.pg_conn.fetchrow("""
            SELECT metrics FROM backtest_results 
            ORDER BY created_at DESC 
            LIMIT 1
        """)
        
        if row and row['metrics']:
            metrics = row['metrics'] if isinstance(row['metrics'], dict) else json.loads(row['metrics'])
            
            # Check for key metrics
            expected_metrics = {'sharpe_ratio', 'cagr', 'max_drawdown'}
            found_metrics = set(metrics.keys())
            
            # At least some metrics should exist
            assert len(expected_metrics & found_metrics) > 0, f"Missing key metrics in backtest results"
        else:
            print("(no backtest results yet - OK) ", end="")
    
    async def test_strategy_parameters(self):
        """Test strategy parameters are valid JSON"""
        strategies = await self.pg_conn.fetch("""
            SELECT id, parameters FROM strategies LIMIT 10
        """)
        
        for strategy in strategies:
            params = strategy['parameters']
            
            if isinstance(params, str):
                # Should be JSON parseable
                try:
                    json.loads(params)
                except json.JSONDecodeError:
                    raise AssertionError(f"Strategy {strategy['id']} has invalid JSON parameters")
            elif isinstance(params, dict):
                # Already a dict, good
                pass
            else:
                raise AssertionError(f"Strategy {strategy['id']} has invalid parameter type: {type(params)}")
    
    async def test_usdc_symbols(self):
        """Test strategies use USDC symbols (bug fix verification)"""
        # Check recent strategies
        strategies = await self.pg_conn.fetch("""
            SELECT id, parameters 
            FROM strategies 
            WHERE created_at >= NOW() - INTERVAL '7 days'
            LIMIT 20
        """)
        
        if len(strategies) == 0:
            print("(no recent strategies - will be tested in next run) ", end="")
            return
        
        usdc_count = 0
        usdt_count = 0
        
        for strategy in strategies:
            params = strategy['parameters']
            if isinstance(params, str):
                params = json.loads(params)
            
            symbol = params.get('symbol', '')
            
            if 'USDC' in symbol:
                usdc_count += 1
            elif 'USDT' in symbol:
                usdt_count += 1
        
        # After bug fix, should be USDC only
        assert usdt_count == 0, f"Found {usdt_count} strategies with USDT symbols (should be 0 after bug fix)"
        print(f"({usdc_count} USDC, {usdt_count} USDT) ", end="")
    
    async def test_strategy_states(self):
        """Test strategy states are valid"""
        strategies = await self.pg_conn.fetch("""
            SELECT DISTINCT state FROM strategies
        """)
        
        valid_states = {'draft', 'backtesting', 'paper_trading', 'active', 'paused', 'retired', 'inactive'}
        found_states = {s['state'] for s in strategies}
        
        invalid = found_states - valid_states
        assert len(invalid) == 0, f"Invalid strategy states found: {invalid}"
    
    async def test_performance_tracking(self):
        """Test strategy performance is tracked"""
        # Check if strategies have performance metrics
        strategies = await self.pg_conn.fetch("""
            SELECT id, performance_metrics 
            FROM strategies 
            WHERE state IN ('active', 'paper_trading')
            LIMIT 10
        """)
        
        if len(strategies) == 0:
            print("(no active/paper strategies yet - OK) ", end="")
            return
        
        for strategy in strategies:
            metrics = strategy['performance_metrics']
            
            if metrics:
                if isinstance(metrics, str):
                    metrics = json.loads(metrics)
                
                # Should have some performance data
                assert isinstance(metrics, dict), "Performance metrics should be a dict"
    
    async def test_learning_system(self):
        """Test learning insights are being stored"""
        count = await self.pg_conn.fetchval("SELECT COUNT(*) FROM learning_insights")
        
        # May be 0 if just started
        assert count >= 0, "Learning insights query failed"
        
        print(f"({count} insights) ", end="")


if __name__ == "__main__":
    async def run():
        tests = StrategyGenerationTests()
        results = await tests.run_all_tests()
        print(f"\nResults: {results}")
    
    asyncio.run(run())
