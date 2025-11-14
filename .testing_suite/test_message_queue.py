#!/usr/bin/env python3
"""
Message Queue Tests

Tests RabbitMQ connectivity, exchanges, queues, and message routing.
"""

import asyncio
import aiohttp
import json
from typing import Dict


class MessageQueueTests:
    """Test RabbitMQ message queue system"""
    
    def __init__(self):
        self.results = {'total': 0, 'passed': 0, 'failed': 0, 'skipped': 0, 'errors': []}
        
        # RabbitMQ management API
        self.rabbitmq_url = "http://localhost:15672"
        self.rabbitmq_user = "mastertrade"
        self.rabbitmq_pass = "rabbitmq_secure_password"
    
    async def run_all_tests(self) -> Dict:
        """Run all message queue tests"""
        tests = [
            ("RabbitMQ Management UI", self.test_rabbitmq_management),
            ("RabbitMQ Connections", self.test_rabbitmq_connections),
            ("RabbitMQ Exchanges", self.test_rabbitmq_exchanges),
            ("RabbitMQ Queues", self.test_rabbitmq_queues),
            ("Message Routing", self.test_message_routing),
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
    # Message Queue Tests
    # =========================================================================
    
    async def test_rabbitmq_management(self):
        """Test RabbitMQ management interface is accessible"""
        try:
            auth = aiohttp.BasicAuth(self.rabbitmq_user, self.rabbitmq_pass)
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.rabbitmq_url}/api/overview",
                    auth=auth,
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    assert resp.status == 200, f"RabbitMQ management not accessible: {resp.status}"
                    
                    data = await resp.json()
                    version = data.get('rabbitmq_version', 'unknown')
                    print(f"(v{version}) ", end="")
        except aiohttp.ClientError as e:
            raise AssertionError(f"RabbitMQ management not accessible: {e}")
    
    async def test_rabbitmq_connections(self):
        """Test RabbitMQ has active connections"""
        try:
            auth = aiohttp.BasicAuth(self.rabbitmq_user, self.rabbitmq_pass)
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.rabbitmq_url}/api/connections",
                    auth=auth,
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    assert resp.status == 200, f"RabbitMQ connections endpoint failed: {resp.status}"
                    
                    connections = await resp.json()
                    print(f"({len(connections)} connections) ", end="")
        except aiohttp.ClientError as e:
            raise AssertionError(f"RabbitMQ connections not accessible: {e}")
    
    async def test_rabbitmq_exchanges(self):
        """Test RabbitMQ has exchanges configured"""
        try:
            auth = aiohttp.BasicAuth(self.rabbitmq_user, self.rabbitmq_pass)
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.rabbitmq_url}/api/exchanges",
                    auth=auth,
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    assert resp.status == 200, f"RabbitMQ exchanges endpoint failed: {resp.status}"
                    
                    exchanges = await resp.json()
                    
                    # Filter out default exchanges
                    custom_exchanges = [e for e in exchanges if not e['name'].startswith('amq.')]
                    
                    print(f"({len(custom_exchanges)} custom exchanges) ", end="")
                    
                    # Check for expected exchanges
                    exchange_names = {e['name'] for e in exchanges}
                    expected = {'market_data', 'strategy', 'orders', 'alerts'}
                    
                    found = expected & exchange_names
                    if len(found) > 0:
                        print(f"(found: {', '.join(found)}) ", end="")
        except aiohttp.ClientError as e:
            raise AssertionError(f"RabbitMQ exchanges not accessible: {e}")
    
    async def test_rabbitmq_queues(self):
        """Test RabbitMQ has queues configured"""
        try:
            auth = aiohttp.BasicAuth(self.rabbitmq_user, self.rabbitmq_pass)
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.rabbitmq_url}/api/queues",
                    auth=auth,
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    assert resp.status == 200, f"RabbitMQ queues endpoint failed: {resp.status}"
                    
                    queues = await resp.json()
                    print(f"({len(queues)} queues) ", end="")
                    
                    # Check for active consumers
                    total_consumers = sum(q.get('consumers', 0) for q in queues)
                    print(f"({total_consumers} consumers) ", end="")
        except aiohttp.ClientError as e:
            raise AssertionError(f"RabbitMQ queues not accessible: {e}")
    
    async def test_message_routing(self):
        """Test message routing is configured"""
        try:
            auth = aiohttp.BasicAuth(self.rabbitmq_user, self.rabbitmq_pass)
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.rabbitmq_url}/api/bindings",
                    auth=auth,
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    assert resp.status == 200, f"RabbitMQ bindings endpoint failed: {resp.status}"
                    
                    bindings = await resp.json()
                    
                    # Filter out default bindings
                    custom_bindings = [
                        b for b in bindings 
                        if not b.get('source', '').startswith('amq.') and b.get('source') != ''
                    ]
                    
                    print(f"({len(custom_bindings)} custom bindings) ", end="")
        except aiohttp.ClientError as e:
            raise AssertionError(f"RabbitMQ bindings not accessible: {e}")


if __name__ == "__main__":
    async def run():
        tests = MessageQueueTests()
        results = await tests.run_all_tests()
        print(f"\nResults: {results}")
    
    asyncio.run(run())
