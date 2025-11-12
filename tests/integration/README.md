# Integration Tests

Integration tests for the MasterTrade system that validate end-to-end workflows across multiple services.

## Goal-Oriented Trading Integration Tests

**File:** `test_goal_trading_flow.py`

Tests the complete goal-oriented trading flow including:

### Test Coverage

#### 1. Complete Goal Trading Flow
- **Test:** `test_complete_goal_trading_flow`
- **Validates:**
  - Goal creation and initialization
  - Position sizing calculation based on goal progress
  - Trade execution simulation
  - Goal progress updates after trades
  - Risk adjustment at different progress levels (0%, 40%, 90%)
  - Expected behavior: Position sizing increases when behind, normal at 40%, reduces near 90%

#### 2. Strategy Selection Based on Goal Progress
- **Test:** `test_strategy_selection_based_on_goal_progress`
- **Validates:**
  - Aggressive strategy selection when behind goal (10% progress)
  - Balanced strategy selection when on track (50% progress)
  - Conservative strategy selection near goal achievement (85% progress)
  - Strategy types: momentum, mean_reversion, breakout

#### 3. Risk Adjustment Triggers
- **Test:** `test_risk_adjustment_triggers`
- **Validates:**
  - Position sizing adjustments at various progress levels
  - Test cases: 0%, 25%, 50%, 80%, 95% progress
  - Expected adjustments:
    - 0-25%: Increase risk (factor >= 1.0)
    - 50%: Normal risk (factor ~1.0)
    - 80-95%: Reduce risk (factor <= 1.0)

#### 4. Goal Progress History Logging
- **Test:** `test_goal_progress_history_logging`
- **Validates:**
  - Progress snapshots are recorded to `goal_progress_history` table
  - Historical tracking from 0% to 100% progress
  - Data integrity and timeline accuracy

## Running Tests

### Prerequisites

1. PostgreSQL database running with schema initialized:
```bash
psql -U mastertrade -d mastertrade -f risk_manager/migrations/add_goal_oriented_tables.sql
```

2. Required tables:
   - `financial_goals`
   - `goal_progress_history`
   - `goal_adjustment_log`
   - `strategy_instances`
   - `trades`
   - `positions`

3. Environment variables:
```bash
export TEST_DATABASE_URL="postgresql://mastertrade:mastertrade@localhost:5432/mastertrade"
```

### Run All Integration Tests

```bash
cd /home/neodyme/Documents/Projects/masterTrade
pytest tests/integration/test_goal_trading_flow.py -v -s
```

### Run Specific Test

```bash
pytest tests/integration/test_goal_trading_flow.py::test_complete_goal_trading_flow -v -s
```

### Run with Coverage

```bash
pytest tests/integration/ --cov=risk_manager --cov=strategy_service --cov-report=html
```

## Test Database Setup

The tests use a clean slate approach with fixtures that:

1. **`db_pool`**: Creates PostgreSQL connection pool (session scope)
2. **`db_connection`**: Provides connection per test (function scope)
3. **`clean_goal_data`**: Cleans test data before and after each test

### Cleanup Strategy

Tests clean up data using `user_id = 'test_user_goal_integration'` prefix:
- Removes all test goals
- Removes all test trades
- Removes all test strategies
- Removes progress history

## Expected Test Results

All tests should pass with the following validations:

### Test 1: Complete Flow
- ✅ Goal created successfully
- ✅ Position sizing increases when at 0% progress
- ✅ Trade executed and recorded
- ✅ Goal progress updated to 40%
- ✅ Position sizing normalizes at 40% progress
- ✅ Position sizing reduces at 90% progress

### Test 2: Strategy Selection
- ✅ Aggressive strategy (momentum/breakout) selected when behind (10%)
- ✅ Balanced strategy selected when on track (50%)
- ✅ Conservative strategy (mean_reversion) selected near goal (85%)

### Test 3: Risk Adjustments
- ✅ 5 different progress levels tested
- ✅ Adjustment factors calculated correctly
- ✅ Risk increases when behind, normal on track, reduces near goal

### Test 4: History Logging
- ✅ 5 progress snapshots recorded
- ✅ All snapshots have correct progress_pct values
- ✅ Historical data maintains chronological order

## Integration Points

These tests validate integration between:

1. **Risk Manager Service** (`goal_tracking_service.py`, `goal_oriented_sizing.py`)
2. **Strategy Service** (`goal_based_strategy_selector.py`)
3. **Database** (PostgreSQL with goal-related tables)
4. **Position Sizing Engine** (adaptive risk based on goals)

## Test Data Structure

### Sample Goal
```python
{
    "goal_id": 1,
    "user_id": "test_user_goal_integration",
    "goal_type": "monthly_return",
    "target_value": 5.0,  # 5% monthly return
    "current_value": 2.0,  # 2% achieved
    "progress_pct": 40.0,
    "status": "active"
}
```

### Sample Trade
```python
{
    "trade_id": 1,
    "user_id": "test_user_goal_integration",
    "strategy_id": "test_goal_strategy_momentum_001",
    "symbol": "BTCUSDT",
    "side": "LONG",
    "quantity": 0.02,
    "entry_price": 50000.0,
    "exit_price": 51000.0,
    "profit_loss": 20.0,
    "status": "closed"
}
```

## Troubleshooting

### Database Connection Issues

If you see connection errors:
```bash
# Check PostgreSQL is running
pg_isready -h localhost -p 5432

# Verify credentials
psql -U mastertrade -d mastertrade -c "SELECT 1"
```

### Missing Tables

If tests fail with "relation does not exist":
```bash
# Run migration
psql -U mastertrade -d mastertrade -f risk_manager/migrations/add_goal_oriented_tables.sql
```

### Test Cleanup Issues

If tests leave data behind:
```bash
# Manual cleanup
psql -U mastertrade -d mastertrade <<EOF
DELETE FROM goal_adjustment_log WHERE goal_id IN (SELECT goal_id FROM financial_goals WHERE user_id LIKE 'test_user_%');
DELETE FROM goal_progress_history WHERE goal_id IN (SELECT goal_id FROM financial_goals WHERE user_id LIKE 'test_user_%');
DELETE FROM financial_goals WHERE user_id LIKE 'test_user_%';
DELETE FROM trades WHERE user_id LIKE 'test_user_%';
DELETE FROM strategy_instances WHERE strategy_id LIKE 'test_goal_strategy_%';
EOF
```

## Future Enhancements

Potential additions to integration tests:

1. **Multi-Goal Scenarios**: Test with multiple concurrent goals
2. **Goal Conflict Resolution**: Test competing goals (risk vs return)
3. **Long-Term Goals**: Test quarterly/yearly goals
4. **Goal Failure**: Test behavior when goal becomes unreachable
5. **Alert Integration**: Test alert system triggers for goal milestones
6. **Real Market Data**: Test with historical market data replay
7. **Concurrent Trades**: Test multiple strategies executing simultaneously

## Performance Expectations

- **Test Execution Time**: ~5-10 seconds for all tests
- **Database Operations**: ~20-30 queries per test
- **Memory Usage**: <100MB per test
- **Cleanup Time**: <1 second per test

## CI/CD Integration

To run in CI/CD pipeline:

```yaml
# .github/workflows/integration-tests.yml
name: Integration Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_USER: mastertrade
          POSTGRES_PASSWORD: mastertrade
          POSTGRES_DB: mastertrade
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 5432:5432
    
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pytest pytest-asyncio asyncpg
      - name: Run migrations
        run: |
          psql -h localhost -U mastertrade -d mastertrade -f risk_manager/migrations/add_goal_oriented_tables.sql
        env:
          PGPASSWORD: mastertrade
      - name: Run integration tests
        run: pytest tests/integration/ -v
        env:
          TEST_DATABASE_URL: postgresql://mastertrade:mastertrade@localhost:5432/mastertrade
```

## Contact

For questions or issues with integration tests, contact the QA team or file an issue in the repository.
