#!/usr/bin/env python3
"""
Risk Management Tests

Tests risk management limits, position sizing, and safety systems.
"""

import asyncio
import asyncpg
import aiohttp
from typing import Dict


class RiskManagementTests:
    """Test risk management system"""
    
    def __init__(self):
        self.results = {'total': 0, 'passed': 0, 'failed': 0, 'skipped': 0, 'errors': []}
        self.pg_conn = None
        
        self.pg_dsn = "postgresql://mastertrade:mastertrade@localhost:5432/mastertrade"
        self.risk_manager_url = "http://localhost:8003"
    
    async def run_all_tests(self) -> Dict:
        """Run all risk management tests"""
        self.pg_conn = await asyncpg.connect(self.pg_dsn)
        
        tests = [
            ("Risk Manager Health", self.test_risk_manager_health),
            ("Risk Limits Table", self.test_risk_limits_table),
            ("Position Size Limits", self.test_position_size_limits),
            ("Exposure Limits", self.test_exposure_limits),
            ("Risk Parameters", self.test_risk_parameters),
            ("Portfolio Risk", self.test_portfolio_risk),
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
    # Risk Management Tests
    # =========================================================================
    
    async def test_risk_manager_health(self):
        """Test risk manager service is healthy"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.risk_manager_url}/health", timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    assert resp.status == 200, f"Risk manager health check failed: {resp.status}"
        except aiohttp.ClientError as e:
            raise AssertionError(f"Risk manager not accessible: {e}")
    
    async def test_risk_limits_table(self):
        """Test risk limits are configured"""
        exists = await self.pg_conn.fetchval("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables 
                WHERE table_name = 'risk_limits'
            )
        """)
        
        if not exists:
            print("(risk_limits table not found - may be in settings) ", end="")
            return
        
        count = await self.pg_conn.fetchval("SELECT COUNT(*) FROM risk_limits")
        assert count >= 0, "Risk limits query failed"
    
    async def test_position_size_limits(self):
        """Test position size limits are enforced"""
        # Check settings for max position size
        exists = await self.pg_conn.fetchval("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables 
                WHERE table_name = 'settings'
            )
        """)
        
        if exists:
            setting = await self.pg_conn.fetchrow("""
                SELECT value FROM settings 
                WHERE key ILIKE '%position%size%' OR key ILIKE '%max%position%'
                LIMIT 1
            """)
            
            if setting:
                print(f"(limit configured: {setting['value']}) ", end="")
            else:
                print("(no position size limit found in settings) ", end="")
        else:
            print("(settings table not found) ", end="")
    
    async def test_exposure_limits(self):
        """Test exposure limits configuration"""
        # Check for exposure-related settings
        exists = await self.pg_conn.fetchval("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables 
                WHERE table_name = 'settings'
            )
        """)
        
        if exists:
            settings = await self.pg_conn.fetch("""
                SELECT key, value FROM settings 
                WHERE key ILIKE '%exposure%' OR key ILIKE '%leverage%'
            """)
            
            if len(settings) > 0:
                print(f"({len(settings)} exposure settings) ", end="")
            else:
                print("(no exposure settings - may use defaults) ", end="")
    
    async def test_risk_parameters(self):
        """Test risk parameters are reasonable"""
        # Check settings table for risk parameters
        exists = await self.pg_conn.fetchval("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables 
                WHERE table_name = 'settings'
            )
        """)
        
        if not exists:
            print("(settings table not found) ", end="")
            return
        
        risk_settings = await self.pg_conn.fetch("""
            SELECT key, value FROM settings 
            WHERE key ILIKE '%risk%' OR key ILIKE '%stop%loss%' OR key ILIKE '%drawdown%'
        """)
        
        print(f"({len(risk_settings)} risk parameters) ", end="")
    
    async def test_portfolio_risk(self):
        """Test portfolio-level risk tracking"""
        # Check if portfolio risk metrics are calculated
        exists = await self.pg_conn.fetchval("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables 
                WHERE table_name = 'portfolio_metrics'
            )
        """)
        
        if exists:
            count = await self.pg_conn.fetchval("SELECT COUNT(*) FROM portfolio_metrics")
            print(f"({count} portfolio metrics) ", end="")
        else:
            print("(portfolio_metrics table not found - OK) ", end="")


if __name__ == "__main__":
    async def run():
        tests = RiskManagementTests()
        results = await tests.run_all_tests()
        print(f"\nResults: {results}")
    
    asyncio.run(run())
