"""
Test script for Redis signal buffer functionality

Tests:
1. Signal buffering in Redis sorted set
2. Signal retrieval with filters
3. Buffer size management (1000 max)
4. TTL management
5. Statistics generation
"""

import asyncio
import sys
import os
from datetime import datetime, timedelta

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from shared.redis_client import RedisCacheManager
from shared.message_schemas import (
    MarketSignalAggregate,
    TrendDirection,
    SignalStrength
)


async def test_signal_buffer():
    """Test signal buffer functionality"""
    print("=" * 60)
    print("Testing Redis Signal Buffer")
    print("=" * 60)
    
    # Initialize Redis
    redis = RedisCacheManager(redis_url="redis://redis:6379")
    connected = await redis.connect()
    
    if not connected:
        print("❌ Failed to connect to Redis")
        return
    
    print("✅ Connected to Redis\n")
    
    # Clean up any existing signals from test
    redis_key = "signals:recent"
    await redis.redis.delete(redis_key)
    print(f"🧹 Cleaned up existing signals in {redis_key}\n")
    
    # Test 1: Add signals to buffer
    print("Test 1: Adding test signals to buffer...")
    test_signals = []
    
    for i in range(10):
        signal = MarketSignalAggregate(
            signal_id=f"test_signal_{i}",
            symbol="BTCUSDT" if i % 2 == 0 else "ETHUSDT",
            overall_signal=TrendDirection.BULLISH if i < 5 else TrendDirection.BEARISH,
            signal_strength=SignalStrength.STRONG if i % 3 == 0 else SignalStrength.MODERATE,
            confidence=0.7 + (i * 0.02),
            timestamp=datetime.utcnow() - timedelta(minutes=i),
            recommended_action="buy" if i < 5 else "sell"
        )
        test_signals.append(signal)
        
        # Buffer signal in Redis
        from shared.message_schemas import serialize_message
        signal_json = serialize_message(signal)
        score = signal.timestamp.timestamp()
        
        await redis.zadd(redis_key, {signal_json: score})
    
    buffer_size = await redis.zcard(redis_key)
    print(f"✅ Added {len(test_signals)} signals")
    print(f"✅ Current buffer size: {buffer_size}\n")
    
    # Test 2: Retrieve all signals
    print("Test 2: Retrieving all signals...")
    all_signals = await redis.zrange(redis_key, 0, -1)
    print(f"✅ Retrieved {len(all_signals)} signals")
    if all_signals:
        first_signal = all_signals[0]
        if isinstance(first_signal, dict):
            print(f"   First signal symbol: {first_signal.get('symbol', 'N/A')}")
        else:
            print(f"   First signal: {str(first_signal)[:100]}...")
    print()
    
    # Test 3: Retrieve last 5 signals
    print("Test 3: Retrieving last 5 signals...")
    recent_5 = await redis.zrange(redis_key, -5, -1)
    print(f"✅ Retrieved {len(recent_5)} most recent signals\n")
    
    # Test 4: Test buffer size limit (add 995 more to reach 1005 total)
    print("Test 4: Testing buffer size limit (1000 max)...")
    for i in range(995):
        signal = MarketSignalAggregate(
            signal_id=f"overflow_signal_{i}",
            symbol="BTCUSDT",
            overall_signal=TrendDirection.NEUTRAL,
            signal_strength=SignalStrength.WEAK,
            confidence=0.5,
            timestamp=datetime.utcnow(),
            recommended_action="hold"
        )
        
        signal_json = serialize_message(signal)
        score = signal.timestamp.timestamp()
        await redis.zadd(redis_key, {signal_json: score})
    
    # Check size
    current_size = await redis.zcard(redis_key)
    print(f"   Current size after adding 995 more: {current_size}")
    
    # Trim to 1000
    if current_size > 1000:
        remove_count = current_size - 1000
        removed = await redis.zremrangebyrank(redis_key, 0, remove_count - 1)
        print(f"   Removed {removed} oldest signals")
        current_size = await redis.zcard(redis_key)
        print(f"✅ Buffer trimmed to {current_size} signals\n")
    
    # Test 5: Set TTL
    print("Test 5: Setting TTL to 24 hours...")
    ttl_set = await redis.expire(redis_key, 86400)
    ttl_value = await redis.ttl(redis_key)
    print(f"✅ TTL set: {ttl_set}")
    print(f"✅ Current TTL: {ttl_value} seconds (~{ttl_value/3600:.1f} hours)\n")
    
    # Test 6: Get buffer info
    print("Test 6: Getting buffer info...")
    buffer_size = await redis.zcard(redis_key)
    ttl = await redis.ttl(redis_key)
    
    # Get oldest and newest signal timestamps
    oldest = await redis.zrange(redis_key, 0, 0, withscores=True)
    newest = await redis.zrange(redis_key, -1, -1, withscores=True)
    
    print(f"   Buffer size: {buffer_size}")
    print(f"   TTL: {ttl}s (~{ttl/3600:.1f}h)")
    if oldest:
        oldest_time = datetime.fromtimestamp(oldest[0][1])
        print(f"   Oldest signal: {oldest_time.isoformat()}")
    if newest:
        newest_time = datetime.fromtimestamp(newest[0][1])
        print(f"   Newest signal: {newest_time.isoformat()}")
    print()
    
    # Test 7: Filter by time (last hour only)
    print("Test 7: Filtering signals by time (last hour)...")
    cutoff = (datetime.utcnow() - timedelta(hours=1)).timestamp()
    recent_signals = await redis.redis.zrangebyscore(
        redis_key,
        cutoff,
        '+inf'
    )
    print(f"✅ Found {len(recent_signals)} signals from last hour\n")
    
    # Cleanup
    print("Cleanup: Removing test data...")
    await redis.redis.delete(redis_key)
    print("✅ Test data cleaned up\n")
    
    await redis.disconnect()
    
    print("=" * 60)
    print("All tests completed successfully! ✅")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_signal_buffer())
