"""Simple test to debug state issue"""
import asyncio
from collections import namedtuple

# Mock Redis
class MockRedis:
    def __init__(self):
        self.data = {}
    async def get(self, key):
        return self.data.get(key)
    async def setex(self, key, ttl, value):
        self.data[key] = value
        return True

from collectors.onchain_collector import CircuitBreaker

async def main():
    redis = MockRedis()
    cb = CircuitBreaker(
        failure_threshold=2,
        timeout_seconds=1,
        half_open_max_calls=3,
        half_open_success_threshold=2,
        collector_name="test",
        redis_cache=redis
    )
    
    print(f"Initial state: '{cb.state}' (repr: {repr(cb.state)})")
    
    # Open circuit
    cb.record_failure()
    cb.record_failure()
    print(f"After failures: '{cb.state}' (repr: {repr(cb.state)})")
    
    # Wait and transition
    await asyncio.sleep(1.1)
    result = cb.can_attempt()
    print(f"can_attempt returned: {result}")
    print(f"State after can_attempt: '{cb.state}' (repr: {repr(cb.state)})")
    
    # Check exact equality
    print(f"cb.state == 'half-open': {cb.state == 'half-open'}")
    print(f"cb.state == 'half_open': {cb.state == 'half_open'}")
    print(f"Length of state: {len(cb.state)}")
    print(f"Bytes: {cb.state.encode()}")
    
    # Try the assertion
    try:
        assert cb.state == "half-open", "Should be half-open"
        print("✅ Assertion passed!")
    except AssertionError as e:
        print(f"❌ Assertion failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())
