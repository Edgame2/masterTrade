#!/usr/bin/env python3
"""
Test Goal Tracking Service

Tests goal tracking functionality including:
- Goal status queries
- Historical progress tracking
- Manual snapshots
- Target updates
- Profit recording
"""

import asyncio
import aiohttp
import json
from datetime import datetime, timedelta

BASE_URL = "http://localhost:8003"  # Risk manager service


async def test_get_goals_status():
    """Test getting current goal status"""
    print("\n=== Test 1: Get Goals Status ===")
    
    async with aiohttp.ClientSession() as session:
        url = f"{BASE_URL}/goals/status"
        
        async with session.get(url) as response:
            status = response.status
            data = await response.json()
            
            print(f"Status: {status}")
            print(f"Response: {json.dumps(data, indent=2)}")
            
            if status == 200 and data.get('success'):
                print("✅ Successfully retrieved goals status")
                if data.get('goals'):
                    for goal in data['goals']:
                        print(f"  - {goal['goal_type']}: {goal['progress_percent']:.1f}% ({goal['status']})")
            else:
                print("❌ Failed to get goals status")


async def test_manual_snapshot():
    """Test triggering manual goal snapshot"""
    print("\n=== Test 2: Manual Snapshot ===")
    
    async with aiohttp.ClientSession() as session:
        url = f"{BASE_URL}/goals/manual-snapshot"
        
        async with session.post(url) as response:
            status = response.status
            data = await response.json()
            
            print(f"Status: {status}")
            print(f"Response: {json.dumps(data, indent=2)}")
            
            if status == 200 and data.get('success'):
                print("✅ Successfully triggered manual snapshot")
            else:
                print("❌ Failed to trigger snapshot")


async def test_goal_history():
    """Test getting goal history"""
    print("\n=== Test 3: Goal History ===")
    
    goal_types = ['monthly_return', 'monthly_income', 'portfolio_value']
    
    async with aiohttp.ClientSession() as session:
        for goal_type in goal_types:
            print(f"\nHistory for {goal_type}:")
            url = f"{BASE_URL}/goals/history/{goal_type}?days=30"
            
            async with session.get(url) as response:
                status = response.status
                data = await response.json()
                
                if status == 200 and data.get('success'):
                    history = data.get('history', [])
                    print(f"✅ Retrieved {len(history)} history records")
                    
                    if history:
                        # Show last 3 records
                        for record in history[:3]:
                            print(f"  - {record['date']}: {record['actual_value']:.2f} ({record['status']})")
                else:
                    print(f"❌ Failed to get history: {data}")


async def test_invalid_goal_type():
    """Test with invalid goal type"""
    print("\n=== Test 4: Invalid Goal Type ===")
    
    async with aiohttp.ClientSession() as session:
        url = f"{BASE_URL}/goals/history/invalid_goal"
        
        async with session.get(url) as response:
            status = response.status
            data = await response.json()
            
            print(f"Status: {status}")
            print(f"Response: {json.dumps(data, indent=2)}")
            
            if status == 400:
                print("✅ Correctly rejected invalid goal type")
            else:
                print("❌ Should have rejected invalid goal type")


async def test_update_goal_targets():
    """Test updating goal targets"""
    print("\n=== Test 5: Update Goal Targets ===")
    
    async with aiohttp.ClientSession() as session:
        # Update monthly return target to 6%
        url = f"{BASE_URL}/goals/targets?monthly_return_target=6.0"
        
        async with session.put(url) as response:
            status = response.status
            data = await response.json()
            
            print(f"Status: {status}")
            print(f"Response: {json.dumps(data, indent=2)}")
            
            if status == 200 and data.get('success'):
                print("✅ Successfully updated goal targets")
            else:
                print("❌ Failed to update targets")


async def test_update_multiple_targets():
    """Test updating multiple goal targets at once"""
    print("\n=== Test 6: Update Multiple Targets ===")
    
    async with aiohttp.ClientSession() as session:
        url = (f"{BASE_URL}/goals/targets?"
               f"monthly_return_target=5.0&"
               f"monthly_income_target=2500.0&"
               f"portfolio_value_target=60000.0")
        
        async with session.put(url) as response:
            status = response.status
            data = await response.json()
            
            print(f"Status: {status}")
            print(f"Response: {json.dumps(data, indent=2)}")
            
            if status == 200 and data.get('success'):
                print("✅ Successfully updated all targets")
                updates = data.get('updates', {})
                for key, value in updates.items():
                    print(f"  - {key}: {value}")
            else:
                print("❌ Failed to update targets")


async def test_no_targets_provided():
    """Test error when no targets provided"""
    print("\n=== Test 7: No Targets Provided ===")
    
    async with aiohttp.ClientSession() as session:
        url = f"{BASE_URL}/goals/targets"
        
        async with session.put(url) as response:
            status = response.status
            data = await response.json()
            
            print(f"Status: {status}")
            print(f"Response: {json.dumps(data, indent=2)}")
            
            if status == 400:
                print("✅ Correctly rejected empty update")
            else:
                print("❌ Should have rejected empty update")


async def test_record_profit():
    """Test recording realized profit"""
    print("\n=== Test 8: Record Realized Profit ===")
    
    async with aiohttp.ClientSession() as session:
        # Record $150 profit
        url = f"{BASE_URL}/goals/record-profit?profit=150.0"
        
        async with session.post(url) as response:
            status = response.status
            data = await response.json()
            
            print(f"Status: {status}")
            print(f"Response: {json.dumps(data, indent=2)}")
            
            if status == 200 and data.get('success'):
                print("✅ Successfully recorded profit")
                print(f"  - Profit: ${data.get('profit_recorded'):.2f}")
                print(f"  - Month to date: ${data.get('month_to_date'):.2f}")
            else:
                print("❌ Failed to record profit")


async def test_record_loss():
    """Test recording realized loss"""
    print("\n=== Test 9: Record Realized Loss ===")
    
    async with aiohttp.ClientSession() as session:
        # Record $50 loss
        url = f"{BASE_URL}/goals/record-profit?profit=-50.0"
        
        async with session.post(url) as response:
            status = response.status
            data = await response.json()
            
            print(f"Status: {status}")
            print(f"Response: {json.dumps(data, indent=2)}")
            
            if status == 200 and data.get('success'):
                print("✅ Successfully recorded loss")
                print(f"  - Loss: ${data.get('profit_recorded'):.2f}")
                print(f"  - Month to date: ${data.get('month_to_date'):.2f}")
            else:
                print("❌ Failed to record loss")


async def test_goal_status_after_snapshot():
    """Test goal status after manual snapshot"""
    print("\n=== Test 10: Goal Status After Snapshot ===")
    
    async with aiohttp.ClientSession() as session:
        # Trigger snapshot
        await session.post(f"{BASE_URL}/goals/manual-snapshot")
        
        # Wait a moment
        await asyncio.sleep(1)
        
        # Get status
        async with session.get(f"{BASE_URL}/goals/status") as response:
            status = response.status
            data = await response.json()
            
            print(f"Status: {status}")
            
            if status == 200 and data.get('success'):
                print("✅ Successfully retrieved post-snapshot status")
                for goal in data.get('goals', []):
                    print(f"  - {goal['goal_type']}:")
                    print(f"    Current: {goal['current_value']:.2f}")
                    print(f"    Target: {goal['target_value']:.2f}")
                    print(f"    Progress: {goal['progress_percent']:.1f}%")
                    print(f"    Status: {goal['status']}")
            else:
                print("❌ Failed to get status")


async def run_all_tests():
    """Run all goal tracking tests"""
    print("=" * 60)
    print("GOAL TRACKING SERVICE TESTS")
    print("=" * 60)
    
    try:
        # Basic functionality tests
        await test_get_goals_status()
        await test_manual_snapshot()
        await test_goal_history()
        
        # Validation tests
        await test_invalid_goal_type()
        await test_no_targets_provided()
        
        # Update tests
        await test_update_goal_targets()
        await test_update_multiple_targets()
        
        # Profit recording tests
        await test_record_profit()
        await test_record_loss()
        
        # Integration test
        await test_goal_status_after_snapshot()
        
        print("\n" + "=" * 60)
        print("ALL TESTS COMPLETED")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ Test suite error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(run_all_tests())
