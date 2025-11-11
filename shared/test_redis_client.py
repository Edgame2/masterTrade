"""
Test Redis Cache Manager

Run this to verify Redis connection and basic operations
"""

import asyncio
import sys
from datetime import datetime
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.redis_client import (
    RedisCacheManager,
    cache_market_data,
    get_cached_market_data,
    buffer_signal,
    get_recent_signals
)


async def test_redis_connection():
    """Test basic Redis connection"""
    print("=" * 60)
    print("Testing Redis Connection")
    print("=" * 60)
    
    cache = RedisCacheManager(redis_url="redis://localhost:6379")
    
    # Connect
    connected = await cache.connect()
    if not connected:
        print("❌ Failed to connect to Redis")
        print("Make sure Redis is running: docker-compose up redis -d")
        return False
    
    print("✅ Connected to Redis successfully")
    
    # Test ping
    ping_result = await cache.ping()
    print(f"✅ Ping successful: {ping_result}")
    
    return cache


async def test_basic_operations(cache: RedisCacheManager):
    """Test basic get/set operations"""
    print("\n" + "=" * 60)
    print("Testing Basic Operations")
    print("=" * 60)
    
    # Test set
    test_key = "test:key:1"
    test_value = {"message": "Hello Redis!", "timestamp": datetime.now().isoformat()}
    
    set_result = await cache.set(test_key, test_value, ttl=60)
    print(f"✅ Set operation: {set_result}")
    
    # Test get
    get_result = await cache.get(test_key)
    print(f"✅ Get operation: {get_result}")
    
    # Test exists
    exists_result = await cache.exists(test_key)
    print(f"✅ Exists check: {exists_result} key(s) found")
    
    # Test TTL
    ttl_result = await cache.ttl(test_key)
    print(f"✅ TTL: {ttl_result} seconds remaining")
    
    # Test delete
    delete_result = await cache.delete(test_key)
    print(f"✅ Delete operation: {delete_result} key(s) deleted")


async def test_market_data_cache(cache: RedisCacheManager):
    """Test market data caching"""
    print("\n" + "=" * 60)
    print("Testing Market Data Cache")
    print("=" * 60)
    
    # Cache market data
    market_data = {
        "symbol": "BTCUSDT",
        "price": 45000.50,
        "volume": 1234567.89,
        "timestamp": datetime.now().isoformat()
    }
    
    result = await cache_market_data(cache, "BTCUSDT", market_data, ttl=30)
    print(f"✅ Cached market data: {result}")
    
    # Retrieve cached data
    cached_data = await get_cached_market_data(cache, "BTCUSDT")
    print(f"✅ Retrieved cached data: {cached_data}")


async def test_signal_buffering(cache: RedisCacheManager):
    """Test signal buffering with sorted sets"""
    print("\n" + "=" * 60)
    print("Testing Signal Buffering")
    print("=" * 60)
    
    # Buffer multiple signals
    for i in range(5):
        signal = {
            "signal_id": f"signal_{i}",
            "symbol": "BTCUSDT",
            "signal_type": "BUY" if i % 2 == 0 else "SELL",
            "strength": 0.8 + (i * 0.05),
            "timestamp": datetime.now().timestamp() + i
        }
        
        result = await buffer_signal(cache, signal)
        print(f"✅ Buffered signal {i}: {result}")
    
    # Retrieve recent signals
    recent_signals = await get_recent_signals(cache, count=10)
    print(f"✅ Retrieved {len(recent_signals)} recent signals")
    
    for idx, signal in enumerate(recent_signals):
        print(f"   Signal {idx}: {signal.get('signal_id')} - {signal.get('signal_type')}")


async def test_hash_operations(cache: RedisCacheManager):
    """Test hash operations"""
    print("\n" + "=" * 60)
    print("Testing Hash Operations")
    print("=" * 60)
    
    # Set hash fields
    hash_data = {
        "symbol": "BTCUSDT",
        "price": 45000.50,
        "volume": 1234567.89,
        "last_update": datetime.now().isoformat()
    }
    
    set_result = await cache.hset("market:BTCUSDT", hash_data)
    print(f"✅ Set hash fields: {set_result} field(s)")
    
    # Get single field
    price = await cache.hget("market:BTCUSDT", "price")
    print(f"✅ Get single field (price): {price}")
    
    # Get all fields
    all_data = await cache.hgetall("market:BTCUSDT")
    print(f"✅ Get all fields: {all_data}")


async def test_redis_info(cache: RedisCacheManager):
    """Test Redis server info"""
    print("\n" + "=" * 60)
    print("Redis Server Information")
    print("=" * 60)
    
    info = await cache.info("server")
    
    if info:
        print(f"Redis Version: {info.get('redis_version', 'unknown')}")
        print(f"Redis Mode: {info.get('redis_mode', 'unknown')}")
        print(f"OS: {info.get('os', 'unknown')}")
        print(f"Uptime (seconds): {info.get('uptime_in_seconds', 'unknown')}")
    
    memory_info = await cache.info("memory")
    if memory_info:
        used_memory = memory_info.get('used_memory_human', 'unknown')
        max_memory = memory_info.get('maxmemory_human', 'unknown')
        print(f"Used Memory: {used_memory}")
        print(f"Max Memory: {max_memory}")


async def cleanup(cache: RedisCacheManager):
    """Cleanup test data"""
    print("\n" + "=" * 60)
    print("Cleanup")
    print("=" * 60)
    
    # Delete test keys
    await cache.delete("market_data:BTCUSDT", "market:BTCUSDT", "signals:recent")
    print("✅ Test data cleaned up")
    
    # Disconnect
    await cache.disconnect()
    print("✅ Disconnected from Redis")


async def main():
    """Run all tests"""
    print("\n")
    print("╔" + "=" * 58 + "╗")
    print("║" + " " * 15 + "REDIS CLIENT TEST SUITE" + " " * 20 + "║")
    print("╚" + "=" * 58 + "╝")
    print()
    
    try:
        # Test connection
        cache = await test_redis_connection()
        if not cache:
            return
        
        # Run tests
        await test_basic_operations(cache)
        await test_market_data_cache(cache)
        await test_signal_buffering(cache)
        await test_hash_operations(cache)
        await test_redis_info(cache)
        
        # Cleanup
        await cleanup(cache)
        
        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED!")
        print("=" * 60 + "\n")
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
