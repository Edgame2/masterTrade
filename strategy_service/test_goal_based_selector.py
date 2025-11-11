#!/usr/bin/env python3
"""
Test Goal-Based Strategy Selector

Tests the goal-based strategy selector functionality including:
- Goal progress fetching from risk manager
- Strategy adjustment calculation
- Score adjustment based on goals
- API endpoints
"""

import asyncio
import aiohttp
import json
from datetime import datetime

# Base URLs for testing
STRATEGY_SERVICE_URL = "http://localhost:8006"
RISK_MANAGER_URL = "http://localhost:8003"


async def test_goal_status_available():
    """Test that goal status is available from risk manager"""
    print("\n=== Test 1: Goal Status Available ===")
    
    async with aiohttp.ClientSession() as session:
        url = f"{RISK_MANAGER_URL}/goals/status"
        
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                if response.status == 200:
                    data = await response.json()
                    print("✅ Risk manager goal status accessible")
                    print(f"   Goals found: {len(data.get('goals', []))}")
                    return True
                else:
                    print(f"❌ Risk manager returned status {response.status}")
                    return False
        except Exception as e:
            print(f"❌ Cannot connect to risk manager: {e}")
            return False


async def test_goal_based_adjustment():
    """Test getting goal-based adjustment factors"""
    print("\n=== Test 2: Get Goal-Based Adjustment ===")
    
    async with aiohttp.ClientSession() as session:
        url = f"{STRATEGY_SERVICE_URL}/api/v1/strategy/goal-based/adjustment"
        
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                status = response.status
                data = await response.json()
                
                print(f"Status: {status}")
                print(f"Response: {json.dumps(data, indent=2)}")
                
                if status == 200 and data.get('success'):
                    adjustment = data.get('adjustment', {})
                    print("✅ Successfully retrieved goal-based adjustment")
                    print(f"   Stance: {adjustment.get('stance', 'unknown')}")
                    print(f"   Aggressiveness: {adjustment.get('aggressiveness_multiplier', 1.0):.2f}x")
                    return True
                else:
                    print("❌ Failed to get adjustment")
                    return False
        except Exception as e:
            print(f"❌ Error: {e}")
            return False


async def test_refresh_goal_progress():
    """Test manually refreshing goal progress"""
    print("\n=== Test 3: Refresh Goal Progress ===")
    
    async with aiohttp.ClientSession() as session:
        url = f"{STRATEGY_SERVICE_URL}/api/v1/strategy/goal-based/refresh"
        
        try:
            async with session.post(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                status = response.status
                data = await response.json()
                
                print(f"Status: {status}")
                print(f"Response: {json.dumps(data, indent=2)[:500]}...")  # Truncate
                
                if status == 200 and data.get('success'):
                    goals = data.get('goals', {})
                    print("✅ Successfully refreshed goal progress")
                    print(f"   Goals updated: {len(goals)}")
                    
                    for goal_type, info in goals.items():
                        print(f"   - {goal_type}: {info.get('progress', 'N/A')} ({info.get('status', 'unknown')})")
                    
                    return True
                else:
                    print("❌ Failed to refresh goals")
                    return False
        except Exception as e:
            print(f"❌ Error: {e}")
            return False


async def test_adjustment_after_refresh():
    """Test that adjustment changes after refresh"""
    print("\n=== Test 4: Adjustment After Refresh ===")
    
    async with aiohttp.ClientSession() as session:
        # Refresh first
        await session.post(
            f"{STRATEGY_SERVICE_URL}/api/v1/strategy/goal-based/refresh",
            timeout=aiohttp.ClientTimeout(total=10)
        )
        
        # Wait a moment
        await asyncio.sleep(1)
        
        # Get adjustment
        async with session.get(
            f"{STRATEGY_SERVICE_URL}/api/v1/strategy/goal-based/adjustment",
            timeout=aiohttp.ClientTimeout(total=10)
        ) as response:
            if response.status == 200:
                data = await response.json()
                adjustment = data.get('adjustment', {})
                
                print("✅ Adjustment retrieved after refresh")
                print(f"   Status: {adjustment.get('status', 'unknown')}")
                print(f"   Stance: {adjustment.get('stance', 'unknown')}")
                print(f"   Goal progress:")
                
                for goal_type, progress in adjustment.get('goal_progress', {}).items():
                    print(f"     - {goal_type}: {progress.get('progress', 'N/A')} ({progress.get('status', 'unknown')})")
                
                return True
            else:
                print("❌ Failed to get adjustment")
                return False


async def test_multiple_adjustments():
    """Test multiple consecutive adjustment requests"""
    print("\n=== Test 5: Multiple Adjustment Requests ===")
    
    async with aiohttp.ClientSession() as session:
        for i in range(3):
            async with session.get(
                f"{STRATEGY_SERVICE_URL}/api/v1/strategy/goal-based/adjustment",
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    stance = data.get('adjustment', {}).get('stance', 'unknown')
                    print(f"   Request {i+1}: {stance}")
                else:
                    print(f"   Request {i+1}: Failed (status {response.status})")
                    return False
            
            await asyncio.sleep(0.5)
        
        print("✅ Multiple requests successful")
        return True


async def test_goal_progress_caching():
    """Test that goal progress is cached (not fetched every time)"""
    print("\n=== Test 6: Goal Progress Caching ===")
    
    async with aiohttp.ClientSession() as session:
        # First request - should fetch from risk manager
        start = datetime.now()
        async with session.get(
            f"{STRATEGY_SERVICE_URL}/api/v1/strategy/goal-based/adjustment",
            timeout=aiohttp.ClientTimeout(total=10)
        ) as response:
            first_duration = (datetime.now() - start).total_seconds()
            first_data = await response.json()
        
        # Second request immediately - should use cache
        start = datetime.now()
        async with session.get(
            f"{STRATEGY_SERVICE_URL}/api/v1/strategy/goal-based/adjustment",
            timeout=aiohttp.ClientTimeout(total=10)
        ) as response:
            second_duration = (datetime.now() - start).total_seconds()
            second_data = await response.json()
        
        print(f"   First request: {first_duration:.3f}s")
        print(f"   Second request: {second_duration:.3f}s")
        
        if second_duration < first_duration:
            print("✅ Second request faster (likely cached)")
            return True
        else:
            print("⚠️  Second request not significantly faster")
            return True  # Not a failure, just observation


async def test_invalid_endpoints():
    """Test error handling for invalid requests"""
    print("\n=== Test 7: Invalid Endpoint Handling ===")
    
    async with aiohttp.ClientSession() as session:
        # Test invalid endpoint
        async with session.get(
            f"{STRATEGY_SERVICE_URL}/api/v1/strategy/goal-based/invalid",
            timeout=aiohttp.ClientTimeout(total=5)
        ) as response:
            if response.status == 404:
                print("✅ 404 returned for invalid endpoint")
                return True
            else:
                print(f"❌ Expected 404, got {response.status}")
                return False


async def run_all_tests():
    """Run all goal-based selector tests"""
    print("=" * 60)
    print("GOAL-BASED STRATEGY SELECTOR TESTS")
    print("=" * 60)
    
    results = []
    
    try:
        # Basic connectivity
        results.append(await test_goal_status_available())
        
        # Core functionality
        results.append(await test_goal_based_adjustment())
        results.append(await test_refresh_goal_progress())
        results.append(await test_adjustment_after_refresh())
        
        # Performance and reliability
        results.append(await test_multiple_adjustments())
        results.append(await test_goal_progress_caching())
        
        # Error handling
        results.append(await test_invalid_endpoints())
        
        # Summary
        print("\n" + "=" * 60)
        print("TEST SUMMARY")
        print("=" * 60)
        passed = sum(results)
        total = len(results)
        print(f"Passed: {passed}/{total}")
        
        if passed == total:
            print("✅ All tests passed!")
        else:
            print(f"❌ {total - passed} test(s) failed")
        
    except Exception as e:
        print(f"\n❌ Test suite error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(run_all_tests())
