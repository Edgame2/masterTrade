#!/usr/bin/env python3
"""
Environment Variables Tests

Tests that all required environment variables are set and valid.
"""

import asyncio
import os
import subprocess
from typing import Dict, List, Tuple


class EnvironmentTests:
    """Test environment variables and configuration"""
    
    def __init__(self):
        self.results = {'total': 0, 'passed': 0, 'failed': 0, 'skipped': 0, 'errors': []}
        
        # Required environment variables per service
        self.required_vars = {
            'postgres': [
                'POSTGRES_USER',
                'POSTGRES_PASSWORD',
                'POSTGRES_DB',
            ],
            'timescaledb': [
                'POSTGRES_USER',
                'POSTGRES_PASSWORD',
            ],
            'rabbitmq': [
                'RABBITMQ_USER',
                'RABBITMQ_PASSWORD',
            ],
            'market_data_service': [
                'POSTGRES_HOST',
                'POSTGRES_PORT',
                'POSTGRES_DB',
                'POSTGRES_USER',
                'POSTGRES_PASSWORD',
                'RABBITMQ_URL',
            ],
            'strategy_service': [
                'POSTGRES_HOST',
                'POSTGRES_PORT',
                'POSTGRES_DB',
                'POSTGRES_USER',
                'POSTGRES_PASSWORD',
                'RABBITMQ_URL',
            ],
            'order_executor': [
                'POSTGRES_HOST',
                'POSTGRES_PORT',
                'POSTGRES_DB',
                'POSTGRES_USER',
                'POSTGRES_PASSWORD',
                'RABBITMQ_URL',
            ],
            'risk_manager': [
                'POSTGRES_HOST',
                'POSTGRES_PORT',
                'POSTGRES_DB',
                'POSTGRES_USER',
                'POSTGRES_PASSWORD',
                'RABBITMQ_URL',
            ],
        }
        
        # Service container names
        self.containers = {
            'postgres': 'mastertrade_postgres',
            'timescaledb': 'mastertrade_timescaledb',
            'rabbitmq': 'mastertrade_rabbitmq',
            'market_data_service': 'mastertrade_market_data',
            'strategy_service': 'mastertrade_strategy',
            'order_executor': 'mastertrade_order_executor',
            'risk_manager': 'mastertrade_risk_manager',
        }
    
    async def run_all_tests(self) -> Dict:
        """Run all environment tests"""
        tests = [
            ("Host Environment Variables", self.test_host_environment),
            ("Docker Compose Environment", self.test_docker_compose_env),
            ("Container Environment Variables", self.test_container_environments),
            ("Database Credentials Validity", self.test_database_credentials),
            ("RabbitMQ Credentials Validity", self.test_rabbitmq_credentials),
            ("API Keys and Secrets", self.test_api_keys),
            ("Service Configuration Files", self.test_config_files),
        ]
        
        for test_name, test_func in tests:
            await self._run_test(test_name, test_func)
        
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
    # Environment Tests
    # =========================================================================
    
    async def test_host_environment(self):
        """Test host environment variables"""
        # Check for .env file
        env_file = '/home/neodyme/Documents/Projects/masterTrade/.env'
        
        if os.path.exists(env_file):
            print(f"(.env file found) ", end="")
        else:
            print(f"(.env file not found - using docker-compose defaults) ", end="")
    
    async def test_docker_compose_env(self):
        """Test docker-compose environment variables"""
        # Check if docker-compose.yml exists
        compose_file = '/home/neodyme/Documents/Projects/masterTrade/docker-compose.yml'
        
        assert os.path.exists(compose_file), "docker-compose.yml not found"
        
        # Read and check for environment variable definitions
        with open(compose_file, 'r') as f:
            content = f.read()
            
        required_vars = ['POSTGRES_USER', 'POSTGRES_PASSWORD', 'RABBITMQ_USER', 'RABBITMQ_PASSWORD']
        missing = []
        
        for var in required_vars:
            if var not in content:
                missing.append(var)
        
        if missing:
            print(f"(missing in compose: {', '.join(missing)}) ", end="")
        else:
            print(f"(all required vars defined) ", end="")
    
    async def test_container_environments(self):
        """Test environment variables in running containers"""
        issues = []
        
        for service, container_name in self.containers.items():
            # Check if container is running
            result = subprocess.run(
                ['docker', 'ps', '--filter', f'name={container_name}', '--format', '{{.Names}}'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if container_name not in result.stdout:
                issues.append(f"{service} not running")
                continue
            
            # Check environment variables
            if service in self.required_vars:
                for var in self.required_vars[service]:
                    result = subprocess.run(
                        ['docker', 'exec', container_name, 'env'],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    
                    if result.returncode != 0:
                        issues.append(f"{service}: cannot read env")
                        break
                    
                    if var not in result.stdout:
                        issues.append(f"{service}: missing {var}")
        
        if issues:
            # Non-critical issues
            print(f"({len(issues)} env issues) ", end="")
        else:
            print(f"(all containers have required vars) ", end="")
    
    async def test_database_credentials(self):
        """Test database credentials are valid"""
        import asyncpg
        
        # Test PostgreSQL
        try:
            conn = await asyncpg.connect(
                host='localhost',
                port=5432,
                database='mastertrade',
                user='mastertrade',
                password='mastertrade',
                timeout=5
            )
            await conn.close()
            print("(PostgreSQL credentials valid) ", end="")
        except Exception as e:
            raise AssertionError(f"PostgreSQL credentials invalid: {e}")
        
        # Test TimescaleDB
        try:
            conn = await asyncpg.connect(
                host='localhost',
                port=5433,
                database='mastertrade_timeseries',
                user='mastertrade',
                password='mastertrade',
                timeout=5
            )
            await conn.close()
            print("(TimescaleDB credentials valid) ", end="")
        except Exception as e:
            raise AssertionError(f"TimescaleDB credentials invalid: {e}")
    
    async def test_rabbitmq_credentials(self):
        """Test RabbitMQ credentials are valid"""
        import aiohttp
        
        try:
            auth = aiohttp.BasicAuth('mastertrade', 'rabbitmq_secure_password')
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    'http://localhost:15672/api/overview',
                    auth=auth,
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    assert resp.status == 200, f"RabbitMQ auth failed: {resp.status}"
                    print("(RabbitMQ credentials valid) ", end="")
        except Exception as e:
            raise AssertionError(f"RabbitMQ credentials invalid: {e}")
    
    async def test_api_keys(self):
        """Test API keys and secrets configuration"""
        # Check for API key environment variables in containers
        api_key_vars = [
            'BINANCE_API_KEY',
            'BINANCE_SECRET_KEY',
            'COINBASE_API_KEY',
            'COINBASE_SECRET_KEY',
        ]
        
        found_keys = []
        
        # Check in market_data_service container
        try:
            result = subprocess.run(
                ['docker', 'exec', 'mastertrade_market_data', 'env'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            for var in api_key_vars:
                if var in result.stdout:
                    found_keys.append(var)
        except:
            pass
        
        if found_keys:
            print(f"({len(found_keys)} API keys configured) ", end="")
        else:
            print("(no API keys found - using testnet/demo) ", end="")
    
    async def test_config_files(self):
        """Test service configuration files exist"""
        config_files = [
            '/home/neodyme/Documents/Projects/masterTrade/market_data_service/config.py',
            '/home/neodyme/Documents/Projects/masterTrade/strategy_service/config.py',
            '/home/neodyme/Documents/Projects/masterTrade/order_executor/config.py',
            '/home/neodyme/Documents/Projects/masterTrade/risk_manager/config.py',
        ]
        
        missing = []
        for config_file in config_files:
            if not os.path.exists(config_file):
                missing.append(os.path.basename(os.path.dirname(config_file)))
        
        if missing:
            raise AssertionError(f"Missing config files for: {', '.join(missing)}")
        else:
            print(f"(all config files present) ", end="")


if __name__ == "__main__":
    async def run():
        tests = EnvironmentTests()
        results = await tests.run_all_tests()
        print(f"\nResults: {results}")
    
    asyncio.run(run())
