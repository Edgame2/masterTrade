"""
Test script for enhanced circuit breaker functionality.

Tests:
1. Basic failure tracking and circuit opening
2. Half-open state entry after timeout
3. Gradual recovery (2 of 3 successes closes circuit)
4. Failed recovery and reopening
5. Exponential backoff on failed recovery
6. Manual controls (force_open, force_close, reset)
7. Redis state persistence
8. Statistics tracking and health score
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

# Mock Redis before importing collectors
class MockRedis:
    def __init__(self):
        self.data = {}
        
    async def get(self, key):
        return self.data.get(key)
    
    async def set(self, key, value, ex=None, ttl=None):
        """Set key with optional expiration (ex or ttl in seconds)"""
        self.data[key] = value
        return True
        
    async def setex(self, key, ttl, value):
        self.data[key] = value
        return True
        
    async def delete(self, key):
        if key in self.data:
            del self.data[key]
        return True

# Import after mocking
from collectors.onchain_collector import CircuitBreaker


async def test_basic_failure_tracking():
    """Test 1: Basic failure tracking and circuit opening"""
    print("\n" + "="*80)
    print("TEST 1: Basic Failure Tracking and Circuit Opening")
    print("="*80)
    
    redis_cache = MockRedis()
    cb = CircuitBreaker(
        failure_threshold=3,
        timeout_seconds=5,
        half_open_max_calls=3,
        half_open_success_threshold=2,
        collector_name="test",
        redis_cache=redis_cache
    )
    
    print(f"Initial state: {cb.state}")
    assert cb.state == "closed", "Circuit should start in closed state"
    print("✅ Circuit starts in closed state")
    
    # Record failures to open circuit
    for i in range(3):
        cb.record_failure()
        print(f"  Failure {i+1} recorded. State: {cb.state}, Failures: {cb.failure_count}/{cb.failure_threshold}")
    
    assert cb.state == "open", "Circuit should open after threshold failures"
    print(f"✅ Circuit opened after {cb.failure_threshold} failures")
    
    # Verify requests are blocked
    can_attempt = cb.can_attempt()
    print(f"  Can attempt while open: {can_attempt}")
    assert not can_attempt, "Requests should be blocked when circuit is open"
    print("✅ Requests blocked in open state")
    
    status = cb.get_status()
    print(f"\nCircuit Status:")
    print(f"  State: {status['state']}")
    print(f"  Failures: {status['failure_count']}/{status['failure_threshold']}")
    print(f"  Circuit Opens: {status['statistics']['circuit_opens']}")
    
    return True


async def test_half_open_entry():
    """Test 2: Half-open state entry after timeout"""
    print("\n" + "="*80)
    print("TEST 2: Half-Open State Entry After Timeout")
    print("="*80)
    
    redis_cache = MockRedis()
    cb = CircuitBreaker(
        failure_threshold=2,
        timeout_seconds=2,  # Short timeout for testing
        half_open_max_calls=3,
        half_open_success_threshold=2,
        collector_name="test",
        redis_cache=redis_cache
    )
    
    # Open the circuit
    cb.record_failure()
    cb.record_failure()
    print(f"Circuit opened. State: {cb.state}")
    assert cb.state == "open", "Circuit should be open"
    
    # Wait for timeout
    print(f"Waiting {cb.timeout_seconds} seconds for timeout...")
    await asyncio.sleep(cb.timeout_seconds + 0.1)
    
    # Check if we can attempt (this internally transitions to half-open)
    can_attempt = cb.can_attempt()
    print(f"After timeout - Can attempt: {can_attempt}, State: {cb.state}")
    assert can_attempt, "Should allow attempt after timeout"
    # Note: can_attempt() transitions state internally during the call
    assert cb.state == "half-open", "Should transition to half-open state"
    print("✅ Circuit transitioned to half-open after timeout")
    
    status = cb.get_status()
    print(f"\nHalf-Open Status:")
    print(f"  State: {status['state']}")
    if 'half_open' in status:
        print(f"  Half-Open Attempts: {status['half_open']['attempts']}/{status['half_open']['max_calls']}")
        print(f"  Half-Open Successes: {status['half_open']['successes']}/{status['half_open']['success_threshold']}")
    
    return True


async def test_gradual_recovery_success():
    """Test 3: Gradual recovery (2 of 3 successes closes circuit)"""
    print("\n" + "="*80)
    print("TEST 3: Gradual Recovery - Successful Closure")
    print("="*80)
    
    redis_cache = MockRedis()
    cb = CircuitBreaker(
        failure_threshold=2,
        timeout_seconds=1,
        half_open_max_calls=3,
        half_open_success_threshold=2,
        collector_name="test",
        redis_cache=redis_cache
    )
    
    # Open circuit and wait for half-open
    cb.record_failure()
    cb.record_failure()
    print("Circuit opened")
    await asyncio.sleep(1.1)
    cb.can_attempt()  # Transition to half-open
    print(f"State after can_attempt: {cb.state}")
    assert cb.state == "half-open", "Should be in half-open state"
    
    # Record successful attempts
    print("\nRecording half-open test attempts:")
    cb.can_attempt()  # Increment half_open_attempts
    cb.record_success()
    print(f"  Success 1: Attempts={cb.half_open_attempts}, Successes={cb.half_open_successes}, State={cb.state}")
    assert cb.state == "half-open", "Should remain half-open after 1 success"
    
    cb.can_attempt()  # Increment half_open_attempts
    cb.record_success()
    print(f"  Success 2: Attempts={cb.half_open_attempts}, Successes={cb.half_open_successes}, State={cb.state}")
    assert cb.state == "closed", "Circuit should close after 2 successes"
    print("✅ Circuit closed after reaching success threshold (2/3)")
    
    status = cb.get_status()
    print(f"\nRecovery Statistics:")
    print(f"  Successful Recoveries: {status['statistics']['successful_recoveries']}")
    total_ops = status['statistics']['total_successes'] + status['statistics']['total_failures']
    health = status['statistics']['total_successes'] / total_ops if total_ops > 0 else 0
    print(f"  Health Score: {health:.2f}")
    
    return True


async def test_failed_recovery():
    """Test 4: Failed recovery and reopening"""
    print("\n" + "="*80)
    print("TEST 4: Failed Recovery and Reopening")
    print("="*80)
    
    redis_cache = MockRedis()
    cb = CircuitBreaker(
        failure_threshold=2,
        timeout_seconds=1,
        half_open_max_calls=3,
        half_open_success_threshold=2,
        collector_name="test",
        redis_cache=redis_cache
    )
    
    # Open circuit and transition to half-open
    cb.record_failure()
    cb.record_failure()
    await asyncio.sleep(1.1)
    cb.can_attempt()
    print(f"State: {cb.state}")
    assert cb.state == "half-open", "Should be in half-open state"
    
    # Record a failure in half-open state
    print("\nRecording failure in half-open state:")
    cb.can_attempt()  # Increment half_open_attempts
    cb.record_failure()
    print(f"  After failure: State={cb.state}")
    assert cb.state == "open", "Circuit should reopen immediately on half-open failure"
    print("✅ Circuit reopened immediately on half-open failure")
    
    status = cb.get_status()
    print(f"\nFailed Recovery Statistics:")
    print(f"  Failed Recoveries: {status['statistics']['failed_recoveries']}")
    print(f"  Circuit Opens: {status['statistics']['circuit_opens']}")
    
    return True


async def test_exponential_backoff():
    """Test 5: Exponential backoff on failed recovery"""
    print("\n" + "="*80)
    print("TEST 5: Exponential Backoff on Failed Recovery")
    print("="*80)
    
    redis_cache = MockRedis()
    cb = CircuitBreaker(
        failure_threshold=2,
        timeout_seconds=2,
        half_open_max_calls=3,
        half_open_success_threshold=2,
        collector_name="test",
        redis_cache=redis_cache
    )
    
    initial_timeout = cb.timeout_seconds
    print(f"Initial timeout: {initial_timeout}s")
    
    # First failure cycle
    cb.record_failure()
    cb.record_failure()
    print(f"Circuit opened. Timeout: {cb.timeout_seconds}s")
    
    # Transition to half-open and fail recovery
    await asyncio.sleep(cb.timeout_seconds + 0.1)
    cb.can_attempt()
    cb.can_attempt()
    cb.record_failure()
    
    new_timeout = cb.timeout_seconds
    print(f"After failed recovery - New timeout: {new_timeout}s")
    expected_timeout = initial_timeout * 1.5
    assert new_timeout == expected_timeout, f"Timeout should be {expected_timeout}s (1.5x)"
    print(f"✅ Timeout increased by 1.5x: {initial_timeout}s → {new_timeout}s")
    
    # Another failed recovery
    await asyncio.sleep(new_timeout + 0.1)
    cb.can_attempt()
    cb.can_attempt()
    cb.record_failure()
    
    newer_timeout = cb.timeout_seconds
    print(f"After 2nd failed recovery - New timeout: {newer_timeout}s")
    expected_timeout = new_timeout * 1.5
    assert newer_timeout == expected_timeout, f"Timeout should be {expected_timeout}s (1.5x again)"
    print(f"✅ Timeout increased again: {new_timeout}s → {newer_timeout}s")
    
    # Test max timeout cap - set timeout very high and trigger reopen
    cb.timeout_seconds = 2500  # Close to max
    await asyncio.sleep(2.6)  # Wait long enough
    cb.can_attempt()  # Enter half-open
    cb.can_attempt()  # Attempt
    cb.record_failure()  # Reopen with 1.5x increase (2500 * 1.5 = 3750, capped at 3600)
    print(f"After setting timeout near max - Result: {cb.timeout_seconds}s")
    assert cb.timeout_seconds <= 3600, "Timeout should be capped at 3600s or less"
    print(f"✅ Timeout properly managed (max cap enforced)")
    
    return True


async def test_manual_controls():
    """Test 6: Manual controls (force_open, force_close, reset)"""
    print("\n" + "="*80)
    print("TEST 6: Manual Controls")
    print("="*80)
    
    redis_cache = MockRedis()
    cb = CircuitBreaker(
        failure_threshold=3,
        timeout_seconds=5,
        half_open_max_calls=3,
        half_open_success_threshold=2,
        collector_name="test",
        redis_cache=redis_cache
    )
    
    # Test force_open
    print("\nTesting force_open():")
    print(f"  Before: State={cb.state}")
    cb.force_open()
    print(f"  After: State={cb.state}")
    assert cb.state == "open", "force_open should set state to open"
    print("✅ force_open() works correctly")
    
    # Test force_close
    print("\nTesting force_close():")
    print(f"  Before: State={cb.state}")
    cb.force_close()
    print(f"  After: State={cb.state}")
    assert cb.state == "closed", "force_close should set state to closed"
    print("✅ force_close() works correctly")
    
    # Test reset
    print("\nTesting reset():")
    cb.record_failure()
    cb.record_failure()
    cb.record_success()
    total_ops = cb.stats['total_successes'] + cb.stats['total_failures']
    print(f"  Before reset: Failures={cb.failure_count}, Total ops={total_ops}")
    cb.reset()
    total_ops_after = cb.stats['total_successes'] + cb.stats['total_failures']
    print(f"  After reset: State={cb.state}, Failures={cb.failure_count}, Total ops={total_ops_after}")
    assert cb.state == "closed", "Reset should return to closed state"
    assert cb.failure_count == 0, "Reset should clear failure count"
    # Note: reset() keeps statistics for historical tracking
    print("✅ reset() clears state correctly (keeps stats for history)")
    
    return True


async def test_redis_persistence():
    """Test 7: Redis state persistence"""
    print("\n" + "="*80)
    print("TEST 7: Redis State Persistence")
    print("="*80)
    
    redis_cache = MockRedis()
    
    # Create circuit breaker and record some activity
    cb1 = CircuitBreaker(
        failure_threshold=3,
        timeout_seconds=5,
        half_open_max_calls=3,
        half_open_success_threshold=2,
        collector_name="test_persist",
        redis_cache=redis_cache
    )
    
    cb1.record_failure()
    cb1.record_failure()
    cb1.record_success()
    total_ops1 = cb1.stats['total_successes'] + cb1.stats['total_failures']
    print(f"Original CB: State={cb1.state}, Failures={cb1.failure_count}, Total ops={total_ops1}")
    
    # Save state to Redis
    await cb1.save_state_to_redis()
    print("✅ State saved to Redis")
    
    # Create new circuit breaker and load state
    cb2 = CircuitBreaker(
        failure_threshold=3,
        timeout_seconds=5,
        half_open_max_calls=3,
        half_open_success_threshold=2,
        collector_name="test_persist",
        redis_cache=redis_cache
    )
    
    total_ops2_before = cb2.stats['total_successes'] + cb2.stats['total_failures']
    print(f"New CB before load: State={cb2.state}, Failures={cb2.failure_count}, Total ops={total_ops2_before}")
    await cb2.load_state_from_redis()
    total_ops2_after = cb2.stats['total_successes'] + cb2.stats['total_failures']
    print(f"New CB after load: State={cb2.state}, Failures={cb2.failure_count}, Total ops={total_ops2_after}")
    
    assert cb2.state == cb1.state, "State should match"
    assert cb2.failure_count == cb1.failure_count, "Failure count should match"
    assert total_ops2_after == total_ops1, "Total operations should match"
    print("✅ State loaded from Redis correctly")
    
    # Verify statistics were preserved
    status1 = cb1.get_status()
    status2 = cb2.get_status()
    assert status2['statistics'] == status1['statistics'], "Statistics should match"
    print("✅ Statistics preserved in Redis")
    
    return True


async def test_statistics_and_health():
    """Test 8: Statistics tracking and health score"""
    print("\n" + "="*80)
    print("TEST 8: Statistics Tracking and Health Score")
    print("="*80)
    
    redis_cache = MockRedis()
    cb = CircuitBreaker(
        failure_threshold=3,
        timeout_seconds=1,
        half_open_max_calls=3,
        half_open_success_threshold=2,
        collector_name="test",
        redis_cache=redis_cache
    )
    
    # Record mixed success/failure
    print("\nRecording mixed activity:")
    cb.record_success()
    cb.record_success()
    cb.record_success()
    cb.record_failure()
    cb.record_failure()
    
    status = cb.get_status()
    total_ops = status['statistics']['total_successes'] + status['statistics']['total_failures']
    print(f"  Total operations: {total_ops}")
    print(f"  Success count: {status['statistics']['total_successes']}")
    print(f"  Failure count: {status['statistics']['total_failures']}")
    
    # Calculate health score manually
    health_score = status['statistics']['total_successes'] / total_ops if total_ops > 0 else 0
    print(f"  Health score: {health_score:.2f}")
    
    expected_health = 3 / 5  # 3 successes out of 5 total
    assert abs(health_score - expected_health) < 0.01, f"Health score should be {expected_health:.2f}"
    print(f"✅ Health score calculated correctly: {health_score:.2f}")
    
    # Open circuit and verify statistics
    cb.record_failure()  # Third failure opens circuit
    status = cb.get_status()
    print(f"\nAfter opening circuit:")
    print(f"  Circuit Opens: {status['statistics']['circuit_opens']}")
    assert status['statistics']['circuit_opens'] == 1, "Should have 1 circuit open"
    print("✅ Circuit open tracked in statistics")
    
    # Test successful recovery
    await asyncio.sleep(1.1)
    cb.can_attempt()  # Transition to half-open
    cb.can_attempt()
    cb.record_success()
    cb.can_attempt()
    cb.record_success()  # Should close circuit
    
    status = cb.get_status()
    print(f"\nAfter successful recovery:")
    print(f"  Successful Recoveries: {status['statistics']['successful_recoveries']}")
    total_ops = status['statistics']['total_successes'] + status['statistics']['total_failures']
    health_score = status['statistics']['total_successes'] / total_ops if total_ops > 0 else 0
    print(f"  Health Score: {health_score:.2f}")
    assert status['statistics']['successful_recoveries'] == 1, "Should have 1 successful recovery"
    print("✅ Successful recovery tracked in statistics")
    
    return True


async def main():
    """Run all tests"""
    print("\n" + "="*80)
    print("CIRCUIT BREAKER ENHANCEMENT TEST SUITE")
    print("="*80)
    
    tests = [
        ("Basic Failure Tracking", test_basic_failure_tracking),
        ("Half-Open Entry", test_half_open_entry),
        ("Gradual Recovery Success", test_gradual_recovery_success),
        ("Failed Recovery", test_failed_recovery),
        ("Exponential Backoff", test_exponential_backoff),
        ("Manual Controls", test_manual_controls),
        ("Redis Persistence", test_redis_persistence),
        ("Statistics and Health", test_statistics_and_health),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_func in tests:
        try:
            result = await test_func()
            if result:
                passed += 1
                print(f"\n✅ TEST PASSED: {name}")
        except AssertionError as e:
            failed += 1
            print(f"\n❌ TEST FAILED: {name}")
            print(f"   Error: {e}")
        except Exception as e:
            failed += 1
            print(f"\n❌ TEST FAILED: {name}")
            print(f"   Unexpected error: {e}")
            import traceback
            traceback.print_exc()
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    print(f"Total Tests: {len(tests)}")
    print(f"Passed: {passed} ✅")
    print(f"Failed: {failed} ❌")
    
    if failed == 0:
        print("\n🎉 ALL TESTS PASSED!")
    else:
        print(f"\n⚠️  {failed} test(s) failed")
    
    print("="*80)


if __name__ == "__main__":
    asyncio.run(main())
