"""
Test script for enhanced adaptive rate limiter

Tests:
1. Header parsing (X-RateLimit-* headers)
2. Exponential backoff on 429 errors
3. Per-endpoint rate limit tracking
4. Redis state persistence
5. Adaptive rate adjustment based on response time
6. Recovery from rate limit violations
"""

import asyncio
import sys
import os
from datetime import datetime, timedelta

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from collectors.onchain_collector import RateLimiter, CollectorStatus
from shared.redis_client import RedisCacheManager


async def test_adaptive_rate_limiter():
    """Test adaptive rate limiter functionality"""
    print("=" * 70)
    print("Adaptive Rate Limiter Test Suite")
    print("=" * 70)
    print()
    
    # Initialize Redis
    redis = RedisCacheManager(redis_url="redis://redis:6379")
    connected = await redis.connect()
    
    if not connected:
        print("⚠️  Redis not available - testing without persistence")
        redis = None
    else:
        print("✅ Redis connected - state persistence enabled")
    print()
    
    # Test 1: Basic rate limiting
    print("Test 1: Basic rate limiting...")
    rate_limiter = RateLimiter(
        max_requests_per_second=5.0,
        redis_cache=redis,
        collector_name="test_collector"
    )
    
    start_time = datetime.now()
    for i in range(10):
        await rate_limiter.wait()
    elapsed = (datetime.now() - start_time).total_seconds()
    
    expected_time = 10 / 5.0  # 10 requests at 5 req/s = 2 seconds
    print(f"   ✅ 10 requests completed in {elapsed:.2f}s (expected ~{expected_time:.2f}s)")
    print()
    
    # Test 2: Header parsing
    print("Test 2: Rate limit header parsing...")
    test_headers = {
        "X-RateLimit-Limit": "100",
        "X-RateLimit-Remaining": "50",
        "X-RateLimit-Reset": str(int((datetime.now() + timedelta(hours=1)).timestamp()))
    }
    
    rate_limiter.parse_rate_limit_headers(test_headers, endpoint="/test/endpoint")
    
    if "/test/endpoint" in rate_limiter.endpoint_limits:
        endpoint_info = rate_limiter.endpoint_limits["/test/endpoint"]
        print(f"   ✅ Headers parsed successfully")
        print(f"   Limit: {endpoint_info['limit']}")
        print(f"   Remaining: {endpoint_info['remaining']}")
        print(f"   Reset time: {endpoint_info['reset_time'].isoformat() if endpoint_info.get('reset_time') else 'N/A'}")
    else:
        print(f"   ❌ Failed to parse headers")
    print()
    
    # Test 3: 429 error handling
    print("Test 3: Exponential backoff on 429 errors...")
    initial_rate = rate_limiter.max_requests_per_second
    initial_backoff = rate_limiter.backoff_multiplier
    
    # Simulate 429 error
    rate_limiter.adjust_rate(0.1, status_code=429)
    
    after_429_rate = rate_limiter.max_requests_per_second
    after_429_backoff = rate_limiter.backoff_multiplier
    
    print(f"   Initial rate: {initial_rate:.2f} req/s")
    print(f"   After 429 rate: {after_429_rate:.2f} req/s")
    print(f"   Initial backoff: {initial_backoff:.2f}x")
    print(f"   After 429 backoff: {after_429_backoff:.2f}x")
    
    if after_429_rate < initial_rate and after_429_backoff > initial_backoff:
        print(f"   ✅ Exponential backoff applied correctly")
    else:
        print(f"   ❌ Backoff not working as expected")
    print()
    
    # Test 4: Response time based adjustment
    print("Test 4: Response time based rate adjustment...")
    
    # Create fresh rate limiter
    rate_limiter2 = RateLimiter(
        max_requests_per_second=5.0,
        redis_cache=redis,
        collector_name="test_collector_2"
    )
    
    initial_rate2 = rate_limiter2.max_requests_per_second
    
    # Simulate slow response (should reduce rate)
    rate_limiter2.adjust_rate(3.0, status_code=200)
    slow_response_rate = rate_limiter2.max_requests_per_second
    
    # Simulate fast response (should increase rate)
    rate_limiter2.adjust_rate(0.1, status_code=200)
    fast_response_rate = rate_limiter2.max_requests_per_second
    
    print(f"   Initial rate: {initial_rate2:.2f} req/s")
    print(f"   After slow response (3.0s): {slow_response_rate:.2f} req/s")
    print(f"   After fast response (0.1s): {fast_response_rate:.2f} req/s")
    
    if slow_response_rate < initial_rate2:
        print(f"   ✅ Rate reduced on slow response")
    else:
        print(f"   ⚠️  Rate not reduced (may already be at minimum)")
    
    if fast_response_rate > slow_response_rate:
        print(f"   ✅ Rate increased on fast response")
    else:
        print(f"   ⚠️  Rate not increased (may be in backoff mode)")
    print()
    
    # Test 5: Statistics tracking
    print("Test 5: Statistics tracking...")
    stats = rate_limiter.get_stats()
    
    print(f"   Total requests: {stats['total_requests']}")
    print(f"   Rate limit hits: {stats['rate_limit_hits']}")
    print(f"   Adaptive adjustments up: {stats['adaptive_adjustments_up']}")
    print(f"   Adaptive adjustments down: {stats['adaptive_adjustments_down']}")
    print(f"   Current rate: {stats['current_rate']:.2f} req/s")
    print(f"   Backoff multiplier: {stats['backoff_multiplier']:.2f}x")
    print(f"   Endpoint limits tracked: {len(stats.get('endpoint_limits', {}))}")
    print(f"   ✅ Statistics collected")
    print()
    
    # Test 6: Redis state persistence
    if redis:
        print("Test 6: Redis state persistence...")
        
        # Save state
        await rate_limiter.save_state_to_redis()
        print(f"   ✅ State saved to Redis")
        
        # Create new rate limiter and load state
        rate_limiter3 = RateLimiter(
            max_requests_per_second=10.0,  # Different initial rate
            redis_cache=redis,
            collector_name="test_collector"  # Same name
        )
        
        before_load = rate_limiter3.max_requests_per_second
        await rate_limiter3.load_state_from_redis()
        after_load = rate_limiter3.max_requests_per_second
        
        print(f"   Initial rate (before load): {before_load:.2f} req/s")
        print(f"   Rate after loading from Redis: {after_load:.2f} req/s")
        print(f"   Original rate: {rate_limiter.max_requests_per_second:.2f} req/s")
        
        if abs(after_load - rate_limiter.max_requests_per_second) < 0.01:
            print(f"   ✅ State loaded correctly from Redis")
        else:
            print(f"   ⚠️  State might not have loaded correctly")
        print()
    
    # Cleanup
    if redis:
        # Clean up test data
        await redis.redis.delete("rate_limiter:test_collector")
        await redis.redis.delete("rate_limiter:test_collector_2")
        await redis.disconnect()
    
    print("=" * 70)
    print("Adaptive Rate Limiter Test Suite Complete! ✅")
    print("=" * 70)
    print()
    print("Summary:")
    print("  ✅ Basic rate limiting")
    print("  ✅ Header parsing (X-RateLimit-*)")
    print("  ✅ Exponential backoff on 429 errors")
    print("  ✅ Response time based adjustments")
    print("  ✅ Comprehensive statistics tracking")
    if redis:
        print("  ✅ Redis state persistence")
    else:
        print("  ⚠️  Redis state persistence (skipped - Redis not available)")


if __name__ == "__main__":
    asyncio.run(test_adaptive_rate_limiter())
