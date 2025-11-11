"""
Test script for goal-oriented position sizing module

This script tests the goal-oriented sizing functionality:
1. Database connection and goal progress retrieval
2. Goal adjustment factor calculation
3. Integration with position sizing engine
"""

import asyncio
import sys
from decimal import Decimal
from typing import Dict

sys.path.insert(0, '/app')

from database import RiskPostgresDatabase
from goal_oriented_sizing import GoalOrientedSizingModule
from position_sizing import PositionSizingEngine, PositionSizeRequest
import structlog

logger = structlog.get_logger()


async def test_database_methods():
    """Test database methods for goal tracking"""
    print("\n" + "="*60)
    print("TEST 1: Database Goal Progress Methods")
    print("="*60)
    
    db = RiskPostgresDatabase()
    
    try:
        # Test get_current_goal_progress
        print("\nFetching current goal progress...")
        progress = await db.get_current_goal_progress()
        
        print("\nGoal Progress Results:")
        print(f"  Monthly Return Progress: {progress.get('monthly_return_progress', 0):.2%}")
        print(f"  Monthly Income Progress: {progress.get('monthly_income_progress', 0):.2%}")
        print(f"  Portfolio Value: €{progress.get('portfolio_value', 0):,.2f}")
        print(f"  Monthly Return (actual): {progress.get('monthly_return_actual', 0):.2%}")
        print(f"  Monthly Income (actual): €{progress.get('monthly_income_actual', 0):,.2f}")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Error testing database methods: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_goal_adjustment_calculation():
    """Test goal adjustment factor calculation"""
    print("\n" + "="*60)
    print("TEST 2: Goal Adjustment Factor Calculation")
    print("="*60)
    
    db = RiskPostgresDatabase()
    module = GoalOrientedSizingModule(db)
    
    test_scenarios = [
        {
            "name": "Behind on Both Goals (Aggressive)",
            "portfolio_value": 50000.0,
            "monthly_return_progress": 0.5,  # 50% of target
            "monthly_income_progress": 0.6,  # 60% of target
            "expected_range": (1.15, 1.3)
        },
        {
            "name": "On Track (Normal)",
            "portfolio_value": 100000.0,
            "monthly_return_progress": 0.95,  # 95% of target
            "monthly_income_progress": 0.90,  # 90% of target
            "expected_range": (0.95, 1.05)
        },
        {
            "name": "Ahead of Goals (Conservative)",
            "portfolio_value": 200000.0,
            "monthly_return_progress": 1.2,  # 120% of target
            "monthly_income_progress": 1.15,  # 115% of target
            "expected_range": (0.7, 0.9)
        },
        {
            "name": "Near €1M (Capital Preservation)",
            "portfolio_value": 900000.0,
            "monthly_return_progress": 1.0,
            "monthly_income_progress": 1.0,
            "expected_range": (0.5, 0.7)
        }
    ]
    
    print("\nTesting various scenarios...")
    all_passed = True
    
    for scenario in test_scenarios:
        print(f"\n📊 Scenario: {scenario['name']}")
        print(f"   Portfolio: €{scenario['portfolio_value']:,.2f}")
        print(f"   Return Progress: {scenario['monthly_return_progress']:.1%}")
        print(f"   Income Progress: {scenario['monthly_income_progress']:.1%}")
        
        try:
            factor = await module.calculate_goal_adjustment_factor(
                current_portfolio_value=scenario['portfolio_value'],
                monthly_return_progress=scenario['monthly_return_progress'],
                monthly_income_progress=scenario['monthly_income_progress'],
                days_into_month=15  # Mid-month
            )
            
            min_expected, max_expected = scenario['expected_range']
            passed = min_expected <= factor <= max_expected
            
            status = "✅ PASS" if passed else "❌ FAIL"
            print(f"   Adjustment Factor: {factor:.3f}")
            print(f"   Expected Range: {min_expected:.2f} - {max_expected:.2f}")
            print(f"   {status}")
            
            if not passed:
                all_passed = False
                
        except Exception as e:
            print(f"   ❌ ERROR: {e}")
            all_passed = False
    
    return all_passed


async def test_position_sizing_integration():
    """Test integration with position sizing engine"""
    print("\n" + "="*60)
    print("TEST 3: Position Sizing Engine Integration")
    print("="*60)
    
    db = RiskPostgresDatabase()
    
    # Create position sizing engine with goal-oriented module enabled
    print("\nInitializing Position Sizing Engine with goal module...")
    engine = PositionSizingEngine(db, enable_goal_sizing=True)
    
    if not engine.goal_sizing_module:
        print("❌ Goal sizing module not initialized!")
        return False
    
    print("✅ Goal sizing module initialized successfully")
    
    # Create a test position sizing request
    request = PositionSizeRequest(
        symbol="BTCUSDT",
        strategy_id="test_strategy_001",
        signal_strength=0.8,
        current_price=50000.0,
        volatility=0.03,
        stop_loss_percent=2.0,
        risk_per_trade_percent=1.0
    )
    
    print(f"\nCalculating position size for {request.symbol}...")
    print(f"  Signal Strength: {request.signal_strength}")
    print(f"  Current Price: ${request.current_price:,.2f}")
    print(f"  Volatility: {request.volatility:.2%}")
    
    try:
        result = await engine.calculate_position_size(request)
        
        print("\n📈 Position Size Result:")
        print(f"  Recommended Size: ${result.recommended_size_usd:,.2f}")
        print(f"  Quantity: {result.recommended_quantity:.6f}")
        print(f"  Position Risk: {result.position_risk_percent:.2f}%")
        print(f"  Max Loss: ${result.max_loss_usd:,.2f}")
        print(f"  Confidence: {result.confidence_score:.2%}")
        print(f"  Approved: {'✅' if result.approved else '❌'}")
        
        if result.warnings:
            print("\n⚠️  Warnings:")
            for warning in result.warnings:
                print(f"    - {warning}")
        
        return result.approved
        
    except Exception as e:
        print(f"\n❌ Error calculating position size: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_goal_status():
    """Test goal status retrieval"""
    print("\n" + "="*60)
    print("TEST 4: Goal Status Information")
    print("="*60)
    
    db = RiskPostgresDatabase()
    module = GoalOrientedSizingModule(db)
    
    print("\nFetching current goal status...")
    
    try:
        status = await module.get_goal_status()
        
        print("\n🎯 Financial Goals Status:")
        print(f"\nTimestamp: {status.get('timestamp')}")
        print(f"Days into month: {status.get('days_into_month')}")
        
        # Monthly Return
        monthly_return = status.get('monthly_return', {})
        print(f"\n📊 Monthly Return Goal:")
        print(f"  Target: {monthly_return.get('target', 0):.1%}")
        print(f"  Current: {monthly_return.get('current', 0):.1%}")
        print(f"  Status: {monthly_return.get('status', 'unknown').upper()}")
        
        # Monthly Income
        monthly_income = status.get('monthly_income', {})
        print(f"\n💰 Monthly Income Goal:")
        print(f"  Target: €{monthly_income.get('target', 0):,.2f}")
        print(f"  Current: {monthly_income.get('current', 0):.1%} of target")
        print(f"  Status: {monthly_income.get('status', 'unknown').upper()}")
        
        # Portfolio Value
        portfolio = status.get('portfolio_value', {})
        print(f"\n💼 Portfolio Value Goal:")
        print(f"  Target: €{portfolio.get('target', 0):,.2f}")
        print(f"  Current: €{portfolio.get('current', 0):,.2f}")
        print(f"  Progress: {portfolio.get('progress', 0):.1%}")
        print(f"  Preservation Mode: {'YES ⚠️' if portfolio.get('preservation_mode') else 'NO'}")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Error getting goal status: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("GOAL-ORIENTED POSITION SIZING TEST SUITE")
    print("="*60)
    
    results = []
    
    # Run tests
    results.append(("Database Methods", await test_database_methods()))
    results.append(("Adjustment Calculation", await test_goal_adjustment_calculation()))
    results.append(("Position Sizing Integration", await test_position_sizing_integration()))
    results.append(("Goal Status", await test_goal_status()))
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {test_name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed!")
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
    
    return passed == total


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
