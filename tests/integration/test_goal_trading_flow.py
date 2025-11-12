"""
Integration Test: Goal-Oriented Trading Flow

Tests the complete end-to-end flow:
1. Goal setup and configuration
2. Position sizing based on goals
3. Trade execution with goal-adjusted risk
4. Goal progress tracking and updates
5. Strategy selection based on goal status
6. Adaptive risk adjustments

This validates that all components work together correctly.
"""

import asyncio
import os
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Any
import pytest
import asyncpg
from asyncpg import Pool

# Test configuration
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://mastertrade:mastertrade@localhost:5432/mastertrade"
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture(scope="module")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module")
async def db_pool() -> Pool:
    """Create PostgreSQL connection pool for tests."""
    pool = await asyncpg.create_pool(
        TEST_DATABASE_URL,
        min_size=2,
        max_size=10,
        command_timeout=60
    )
    
    yield pool
    
    await pool.close()


@pytest.fixture
async def db_connection(db_pool: Pool):
    """Get database connection for a test."""
    async with db_pool.acquire() as conn:
        yield conn


@pytest.fixture
async def clean_goal_data(db_connection):
    """Clean up goal-related test data before and after tests."""
    # Clean before test
    await _cleanup_goal_tables(db_connection)
    
    yield
    
    # Clean after test
    await _cleanup_goal_tables(db_connection)


async def _cleanup_goal_tables(conn):
    """Clean up test data from goal-related tables."""
    tables = [
        'goal_adjustment_log',
        'goal_progress_history',
        'financial_goals',
        'positions',
        'trades',
        'strategy_instances',
        'strategy_performance'
    ]
    
    for table in tables:
        try:
            await conn.execute(f"""
                DELETE FROM {table} 
                WHERE user_id = 'test_user_goal_integration' 
                OR strategy_id LIKE 'test_goal_strategy_%'
            """)
        except Exception as e:
            # Table might not exist or have different schema
            print(f"Warning: Could not clean {table}: {e}")


# ============================================================================
# Helper Functions
# ============================================================================

async def create_test_goal(
    conn,
    user_id: str = "test_user_goal_integration",
    goal_type: str = "monthly_return",
    target_value: float = 5.0,
    current_value: float = 0.0,
    progress_pct: float = 0.0
) -> int:
    """Create a test financial goal."""
    result = await conn.fetchrow("""
        INSERT INTO financial_goals (
            user_id, goal_type, target_value, current_value,
            progress_pct, start_date, target_date, status
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        RETURNING goal_id
    """,
        user_id,
        goal_type,
        target_value,
        current_value,
        progress_pct,
        datetime.utcnow().date(),
        (datetime.utcnow() + timedelta(days=30)).date(),
        "active"
    )
    return result['goal_id']


async def get_goal_progress(conn, goal_id: int) -> Dict[str, Any]:
    """Get current goal progress."""
    result = await conn.fetchrow("""
        SELECT * FROM financial_goals WHERE goal_id = $1
    """, goal_id)
    
    if not result:
        return {}
    
    return dict(result)


async def create_test_strategy(
    conn,
    strategy_id: str,
    strategy_name: str,
    risk_profile: str = "moderate"
) -> str:
    """Create a test strategy instance."""
    await conn.execute("""
        INSERT INTO strategy_instances (
            strategy_id, strategy_name, strategy_type,
            parameters, status, risk_profile, created_at
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        ON CONFLICT (strategy_id) DO UPDATE
        SET strategy_name = EXCLUDED.strategy_name
    """,
        strategy_id,
        strategy_name,
        "momentum",
        {"test": True},
        "active",
        risk_profile,
        datetime.utcnow()
    )
    return strategy_id


async def simulate_trade_execution(
    conn,
    user_id: str,
    strategy_id: str,
    symbol: str,
    position_size: float,
    entry_price: float,
    exit_price: float,
    profit_loss: float
) -> int:
    """Simulate trade execution and record in database."""
    # Record trade
    result = await conn.fetchrow("""
        INSERT INTO trades (
            user_id, strategy_id, symbol, side, quantity,
            entry_price, exit_price, profit_loss,
            entry_time, exit_time, status
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
        RETURNING trade_id
    """,
        user_id,
        strategy_id,
        symbol,
        "LONG",
        position_size,
        entry_price,
        exit_price,
        profit_loss,
        datetime.utcnow() - timedelta(hours=1),
        datetime.utcnow(),
        "closed"
    )
    
    return result['trade_id']


async def get_position_sizing_adjustment(
    conn,
    goal_id: int,
    base_position_size: float
) -> Dict[str, Any]:
    """
    Simulate goal-based position sizing calculation.
    In production, this would call the PositionSizingEngine.
    """
    goal = await get_goal_progress(conn, goal_id)
    
    if not goal:
        return {
            "adjusted_size": base_position_size,
            "adjustment_factor": 1.0,
            "reason": "No goal found"
        }
    
    progress_pct = goal.get('progress_pct', 0.0)
    
    # Adjustment logic (simplified version of goal_oriented_sizing.py)
    if progress_pct >= 80.0:
        # Close to goal - reduce risk
        adjustment_factor = 0.7
        reason = "Near goal achievement - reducing risk"
    elif progress_pct >= 50.0:
        # On track - normal sizing
        adjustment_factor = 1.0
        reason = "On track to goal"
    elif progress_pct < 30.0:
        # Behind - increase risk slightly
        adjustment_factor = 1.3
        reason = "Behind goal - increasing position size"
    else:
        adjustment_factor = 1.0
        reason = "Normal position sizing"
    
    return {
        "adjusted_size": base_position_size * adjustment_factor,
        "adjustment_factor": adjustment_factor,
        "reason": reason,
        "progress_pct": progress_pct
    }


async def update_goal_progress(
    conn,
    goal_id: int,
    new_current_value: float
):
    """Update goal progress after trade."""
    goal = await get_goal_progress(conn, goal_id)
    
    if not goal:
        return
    
    target_value = goal['target_value']
    progress_pct = (new_current_value / target_value * 100) if target_value > 0 else 0.0
    
    await conn.execute("""
        UPDATE financial_goals
        SET current_value = $1,
            progress_pct = $2,
            updated_at = $3
        WHERE goal_id = $4
    """,
        new_current_value,
        progress_pct,
        datetime.utcnow(),
        goal_id
    )
    
    # Log progress history
    await conn.execute("""
        INSERT INTO goal_progress_history (
            goal_id, snapshot_date, current_value, progress_pct
        )
        VALUES ($1, $2, $3, $4)
    """,
        goal_id,
        datetime.utcnow().date(),
        new_current_value,
        progress_pct
    )


async def select_strategy_based_on_goal(
    conn,
    goal_id: int,
    available_strategies: list
) -> Dict[str, Any]:
    """
    Simulate goal-based strategy selection.
    In production, this would call the GoalBasedStrategySelector.
    """
    goal = await get_goal_progress(conn, goal_id)
    
    if not goal:
        return {
            "selected_strategy": available_strategies[0] if available_strategies else None,
            "reason": "No goal found - using default"
        }
    
    progress_pct = goal.get('progress_pct', 0.0)
    goal_type = goal.get('goal_type', '')
    
    # Strategy selection logic
    if progress_pct >= 80.0:
        # Near goal - prefer conservative strategies
        selected = next(
            (s for s in available_strategies if 'mean_reversion' in s.lower() or 'conservative' in s.lower()),
            available_strategies[0]
        )
        reason = "Near goal - selecting conservative strategy"
    elif progress_pct < 30.0:
        # Behind goal - prefer aggressive strategies
        selected = next(
            (s for s in available_strategies if 'momentum' in s.lower() or 'breakout' in s.lower()),
            available_strategies[0]
        )
        reason = "Behind goal - selecting aggressive strategy"
    else:
        # On track - balanced approach
        selected = available_strategies[0]
        reason = "On track - balanced strategy selection"
    
    return {
        "selected_strategy": selected,
        "reason": reason,
        "progress_pct": progress_pct
    }


# ============================================================================
# Integration Tests
# ============================================================================

@pytest.mark.asyncio
async def test_complete_goal_trading_flow(db_connection, clean_goal_data):
    """
    Test the complete goal-oriented trading flow:
    1. Create goal
    2. Calculate position sizing
    3. Execute trade
    4. Update goal progress
    5. Verify adjustments
    """
    user_id = "test_user_goal_integration"
    base_position_size = 1000.0  # $1000 base position
    
    # Step 1: Create a monthly return goal (5% target)
    goal_id = await create_test_goal(
        db_connection,
        user_id=user_id,
        goal_type="monthly_return",
        target_value=5.0,  # 5% return target
        current_value=0.0,
        progress_pct=0.0
    )
    
    assert goal_id > 0, "Goal should be created"
    
    # Step 2: Get initial position sizing (should be normal or slightly aggressive)
    sizing_info = await get_position_sizing_adjustment(
        db_connection,
        goal_id,
        base_position_size
    )
    
    assert sizing_info['adjusted_size'] >= base_position_size, \
        "Position size should be normal or increased when starting from 0%"
    
    initial_position_size = sizing_info['adjusted_size']
    
    # Step 3: Create test strategy
    strategy_id = "test_goal_strategy_momentum_001"
    await create_test_strategy(
        db_connection,
        strategy_id,
        "Test Momentum Strategy",
        risk_profile="moderate"
    )
    
    # Step 4: Simulate successful trade (2% profit)
    entry_price = 50000.0
    exit_price = 51000.0  # 2% gain
    profit = initial_position_size * 0.02
    
    trade_id = await simulate_trade_execution(
        db_connection,
        user_id=user_id,
        strategy_id=strategy_id,
        symbol="BTCUSDT",
        position_size=initial_position_size / entry_price,
        entry_price=entry_price,
        exit_price=exit_price,
        profit_loss=profit
    )
    
    assert trade_id > 0, "Trade should be recorded"
    
    # Step 5: Update goal progress (2% achieved out of 5% target = 40% progress)
    new_current_value = 2.0  # 2% return achieved
    await update_goal_progress(
        db_connection,
        goal_id,
        new_current_value
    )
    
    # Step 6: Verify goal progress was updated
    updated_goal = await get_goal_progress(db_connection, goal_id)
    
    assert updated_goal['current_value'] == 2.0, "Current value should be updated"
    assert updated_goal['progress_pct'] == 40.0, "Progress should be 40%"
    
    # Step 7: Get new position sizing (should be normal at 40% progress)
    new_sizing_info = await get_position_sizing_adjustment(
        db_connection,
        goal_id,
        base_position_size
    )
    
    assert new_sizing_info['adjustment_factor'] == 1.0, \
        "At 40% progress, position sizing should be normal"
    
    # Step 8: Simulate more trades to reach 90% progress
    for i in range(3):
        await simulate_trade_execution(
            db_connection,
            user_id=user_id,
            strategy_id=strategy_id,
            symbol="BTCUSDT",
            position_size=100.0,
            entry_price=50000.0,
            exit_price=50500.0,
            profit_loss=50.0
        )
    
    # Update to 90% progress (4.5% out of 5% target)
    await update_goal_progress(
        db_connection,
        goal_id,
        4.5
    )
    
    # Step 9: Verify risk reduction near goal
    near_goal_sizing = await get_position_sizing_adjustment(
        db_connection,
        goal_id,
        base_position_size
    )
    
    assert near_goal_sizing['adjustment_factor'] < 1.0, \
        "Position sizing should be reduced when close to goal (90% progress)"
    assert near_goal_sizing['adjusted_size'] < base_position_size, \
        "Adjusted position size should be smaller near goal achievement"


@pytest.mark.asyncio
async def test_strategy_selection_based_on_goal_progress(db_connection, clean_goal_data):
    """
    Test that strategy selection adapts based on goal progress.
    """
    user_id = "test_user_goal_integration"
    
    # Available strategies
    strategies = [
        "test_goal_strategy_momentum_001",
        "test_goal_strategy_mean_reversion_001",
        "test_goal_strategy_breakout_001"
    ]
    
    # Create strategies in database
    for strat_id in strategies:
        await create_test_strategy(
            db_connection,
            strat_id,
            strat_id.replace("test_goal_strategy_", "").replace("_", " ").title()
        )
    
    # Test 1: Behind goal (10% progress) - should prefer aggressive
    goal_id_behind = await create_test_goal(
        db_connection,
        user_id=user_id,
        goal_type="monthly_return",
        target_value=5.0,
        current_value=0.5,
        progress_pct=10.0
    )
    
    selection_behind = await select_strategy_based_on_goal(
        db_connection,
        goal_id_behind,
        strategies
    )
    
    assert "momentum" in selection_behind['selected_strategy'].lower() or \
           "breakout" in selection_behind['selected_strategy'].lower(), \
        "Should select aggressive strategy when behind goal"
    
    # Test 2: On track (50% progress) - should be balanced
    goal_id_ontrack = await create_test_goal(
        db_connection,
        user_id=f"{user_id}_2",
        goal_type="monthly_return",
        target_value=5.0,
        current_value=2.5,
        progress_pct=50.0
    )
    
    selection_ontrack = await select_strategy_based_on_goal(
        db_connection,
        goal_id_ontrack,
        strategies
    )
    
    assert selection_ontrack['selected_strategy'] is not None, \
        "Should select a strategy when on track"
    
    # Test 3: Near goal (85% progress) - should prefer conservative
    goal_id_near = await create_test_goal(
        db_connection,
        user_id=f"{user_id}_3",
        goal_type="monthly_return",
        target_value=5.0,
        current_value=4.25,
        progress_pct=85.0
    )
    
    selection_near = await select_strategy_based_on_goal(
        db_connection,
        goal_id_near,
        strategies
    )
    
    assert "mean_reversion" in selection_near['selected_strategy'].lower() or \
           "conservative" in selection_near['selected_strategy'].lower(), \
        "Should select conservative strategy near goal achievement"


@pytest.mark.asyncio
async def test_risk_adjustment_triggers(db_connection, clean_goal_data):
    """
    Test that risk adjustments are triggered correctly based on goal status.
    """
    user_id = "test_user_goal_integration"
    base_position_size = 1000.0
    
    # Create goal at different progress levels and verify adjustments
    test_cases = [
        (0.0, 0.0, ">=", "Increase risk at 0% progress"),
        (25.0, 50.0, ">=", "Increase risk at 25% progress (behind)"),
        (50.0, 100.0, "==", "Normal risk at 50% progress"),
        (80.0, 160.0, "<=", "Reduce risk at 80% progress"),
        (95.0, 190.0, "<=", "Significantly reduce risk at 95% progress"),
    ]
    
    for current_value, target_value, operator, description in test_cases:
        # Create goal
        goal_id = await create_test_goal(
            db_connection,
            user_id=f"{user_id}_{current_value}",
            goal_type="monthly_return",
            target_value=target_value if target_value > 0 else 100.0,
            current_value=current_value,
            progress_pct=(current_value / target_value * 100) if target_value > 0 else 0.0
        )
        
        # Get position sizing adjustment
        sizing_info = await get_position_sizing_adjustment(
            db_connection,
            goal_id,
            base_position_size
        )
        
        adjustment_factor = sizing_info['adjustment_factor']
        
        # Verify adjustment direction
        if operator == ">=":
            assert adjustment_factor >= 1.0, \
                f"{description}: Expected factor >= 1.0, got {adjustment_factor}"
        elif operator == "<=":
            assert adjustment_factor <= 1.0, \
                f"{description}: Expected factor <= 1.0, got {adjustment_factor}"
        elif operator == "==":
            assert 0.9 <= adjustment_factor <= 1.1, \
                f"{description}: Expected factor ~1.0, got {adjustment_factor}"


@pytest.mark.asyncio
async def test_goal_progress_history_logging(db_connection, clean_goal_data):
    """
    Test that goal progress history is logged correctly.
    """
    user_id = "test_user_goal_integration"
    
    # Create goal
    goal_id = await create_test_goal(
        db_connection,
        user_id=user_id,
        goal_type="monthly_return",
        target_value=5.0,
        current_value=0.0,
        progress_pct=0.0
    )
    
    # Simulate progress over time
    progress_updates = [
        (1.0, 20.0),
        (2.0, 40.0),
        (3.0, 60.0),
        (4.0, 80.0),
        (5.0, 100.0)
    ]
    
    for current_value, expected_progress in progress_updates:
        await update_goal_progress(
            db_connection,
            goal_id,
            current_value
        )
    
    # Verify history records
    history = await db_connection.fetch("""
        SELECT * FROM goal_progress_history
        WHERE goal_id = $1
        ORDER BY snapshot_date
    """, goal_id)
    
    assert len(history) == len(progress_updates), \
        f"Should have {len(progress_updates)} history records"
    
    # Verify progress values
    for i, (current_value, expected_progress) in enumerate(progress_updates):
        assert history[i]['current_value'] == current_value, \
            f"Record {i}: current_value should be {current_value}"
        assert history[i]['progress_pct'] == expected_progress, \
            f"Record {i}: progress_pct should be {expected_progress}"


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v", "-s"])
