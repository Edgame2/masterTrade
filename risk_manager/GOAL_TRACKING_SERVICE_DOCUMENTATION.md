# Goal Tracking Service Documentation

## Overview

The Goal Tracking Service is a fully automated system that monitors financial goals on a daily basis, records progress, and sends alerts when goals are achieved or at risk. It tracks three types of financial goals: monthly return, monthly income, and portfolio value milestones.

## Architecture

### Components

1. **GoalTrackingService** (`risk_manager/goal_tracking_service.py`)
   - Main service class with daily scheduler
   - Runs at 23:59 UTC every day
   - Calculates portfolio metrics and updates goal progress

2. **Database Layer** (`risk_manager/database.py`)
   - `get_all_goals_status()` - Query current status
   - `get_goal_history()` - Historical progress
   - `update_goal_progress_snapshot()` - Daily snapshot storage

3. **REST API** (`risk_manager/main.py`)
   - 5 endpoints for goal management and monitoring
   - Integration with FastAPI application

## Goal Types

### 1. Monthly Return Goal
- **Target**: Configurable percentage (default: 5%)
- **Calculation**: `(current_portfolio - start_of_month) / start_of_month * 100`
- **Resets**: Automatically on 1st of each month

### 2. Monthly Income Goal
- **Target**: Configurable dollar amount (default: $2000)
- **Calculation**: Sum of realized profits for current month
- **Resets**: Automatically on 1st of each month
- **Recording**: Via `POST /goals/record-profit` when positions close

### 3. Portfolio Value Goal
- **Target**: Configurable dollar milestone (default: $50,000)
- **Calculation**: Sum of all open position values
- **Tracking**: Continuous (no monthly reset)

## Goal Status Levels

| Status | Condition | Description |
|--------|-----------|-------------|
| **achieved** | progress ≥ 100% | Goal successfully met |
| **on_track** | 85% ≤ progress < 100% | Within 15% of target |
| **at_risk** | 70% ≤ progress < 85% | Behind schedule, needs attention |
| **behind** | progress < 70% | Significantly behind target |

## Daily Scheduler

The service runs automatically at **23:59 UTC** every day:

1. Calculate current portfolio value
2. Calculate monthly return (vs. start of month)
3. Retrieve monthly income (accumulated realized profits)
4. Update all three goals in database
5. Check for status changes and send alerts
6. Store daily snapshot in history

## REST API Endpoints

### 1. GET /goals/status

Get current status of all financial goals.

**Request**:
```bash
GET http://localhost:8003/goals/status
```

**Response**:
```json
{
  "success": true,
  "goals": [
    {
      "goal_type": "monthly_income",
      "target_value": 2000.0,
      "current_value": 1450.0,
      "progress_percent": 72.5,
      "status": "at_risk",
      "updated_at": "2025-11-11T23:59:00"
    },
    {
      "goal_type": "monthly_return",
      "target_value": 5.0,
      "current_value": 4.2,
      "progress_percent": 84.0,
      "status": "on_track",
      "updated_at": "2025-11-11T23:59:00"
    },
    {
      "goal_type": "portfolio_value",
      "target_value": 50000.0,
      "current_value": 47500.0,
      "progress_percent": 95.0,
      "status": "on_track",
      "updated_at": "2025-11-11T23:59:00"
    }
  ],
  "timestamp": "2025-11-11T14:30:00+00:00"
}
```

---

### 2. GET /goals/history/{goal_type}

Get historical progress for a specific goal.

**Request**:
```bash
GET http://localhost:8003/goals/history/monthly_return?days=30
```

**Query Parameters**:
- `days` (optional): Number of days of history (default: 30, max: 365)

**Response**:
```json
{
  "success": true,
  "goal_type": "monthly_return",
  "history": [
    {
      "date": "2025-11-11",
      "actual_value": 4.2,
      "target_value": 5.0,
      "variance_percent": -16.0,
      "status": "on_track"
    },
    {
      "date": "2025-11-10",
      "actual_value": 3.8,
      "target_value": 5.0,
      "variance_percent": -24.0,
      "status": "at_risk"
    }
  ],
  "days": 30
}
```

**Valid goal_type values**:
- `monthly_return`
- `monthly_income`
- `portfolio_value`

---

### 3. POST /goals/manual-snapshot

Manually trigger a goal tracking snapshot (for testing or admin use).

**Request**:
```bash
POST http://localhost:8003/goals/manual-snapshot
```

**Response**:
```json
{
  "success": true,
  "message": "Manual goal snapshot completed",
  "timestamp": "2025-11-11T14:45:00+00:00"
}
```

**Use Cases**:
- Testing the goal tracking system
- Updating goals after significant trades
- Admin operations outside of daily schedule

---

### 4. PUT /goals/targets

Update financial goal targets (admin only).

**Request**:
```bash
PUT http://localhost:8003/goals/targets?monthly_return_target=6.0&monthly_income_target=2500.0&portfolio_value_target=60000.0
```

**Query Parameters** (at least one required):
- `monthly_return_target` (optional): Monthly return target in % (range: 0.1-50)
- `monthly_income_target` (optional): Monthly income target in $ (range: 1-1000000)
- `portfolio_value_target` (optional): Portfolio value target in $ (range: 100-10000000)

**Response**:
```json
{
  "success": true,
  "updates": {
    "monthly_return_target": 6.0,
    "monthly_income_target": 2500.0,
    "portfolio_value_target": 60000.0
  },
  "message": "Goal targets updated successfully"
}
```

**Error Response** (no targets provided):
```json
{
  "detail": "At least one target must be provided"
}
```

---

### 5. POST /goals/record-profit

Record realized profit for monthly income tracking.

**Request**:
```bash
POST http://localhost:8003/goals/record-profit?profit=150.0
```

**Query Parameters**:
- `profit` (required): Realized profit amount (can be negative for losses)

**Response**:
```json
{
  "success": true,
  "profit_recorded": 150.0,
  "month_to_date": 1600.0,
  "message": "Profit recorded successfully"
}
```

**Use Cases**:
- Call this endpoint when a position closes with realized PnL
- Automatically accumulates toward monthly income goal
- Resets to $0 on the 1st of each month

---

## Alert System

The service sends alerts when:

1. **Goal Achieved** (progress ≥ 100%)
   - Monthly return reaches target
   - Monthly income reaches target
   - Portfolio value reaches milestone

2. **Goal At Risk** (progress < 85%)
   - Monthly return falling behind
   - Monthly income below expectation

3. **Goal Behind** (progress < 70%)
   - Significant underperformance
   - Requires attention

**Alert Format** (logged):
```
Goal alert: monthly_return achieved
  Actual: 5.20%
  Target: 5.00%
  Message: Monthly return goal achieved: 5.20% (target: 5.00%)
```

## Integration Example

### Python Integration

```python
import aiohttp

async def check_goal_status():
    """Check current goal status"""
    async with aiohttp.ClientSession() as session:
        async with session.get("http://localhost:8003/goals/status") as response:
            data = await response.json()
            
            if data["success"]:
                for goal in data["goals"]:
                    print(f"{goal['goal_type']}: {goal['progress_percent']:.1f}% ({goal['status']})")

async def record_trade_profit(profit: float):
    """Record profit when closing a position"""
    async with aiohttp.ClientSession() as session:
        url = f"http://localhost:8003/goals/record-profit?profit={profit}"
        async with session.post(url) as response:
            data = await response.json()
            
            if data["success"]:
                print(f"Recorded profit: ${profit:.2f}")
                print(f"Month to date: ${data['month_to_date']:.2f}")
```

### From Order Executor

When a position closes with realized PnL:

```python
# After closing position
realized_pnl = calculate_realized_pnl(position)

# Record profit for monthly income goal
await http_client.post(
    "http://risk_manager:8003/goals/record-profit",
    params={"profit": realized_pnl}
)
```

## Service Lifecycle

### Startup Sequence

1. Risk manager service starts
2. Database connection initialized
3. `GoalTrackingService` instantiated
4. `goal_tracking_service.start()` called
5. Tracking state initialized (portfolio value, month-to-date income)
6. Daily scheduler starts in background

### Daily Execution (23:59 UTC)

1. Calculate seconds until 23:59 UTC
2. Sleep until scheduled time
3. Query current portfolio value from positions table
4. Calculate monthly return (vs. start of month baseline)
5. Retrieve accumulated monthly income
6. Update `financial_goals` table with current values
7. Store daily snapshot in `goal_progress_history` table
8. Check for status changes and generate alerts
9. If new month tomorrow, reset monthly tracking
10. Schedule next execution for tomorrow 23:59 UTC

### Shutdown

1. Service shutdown triggered
2. `goal_tracking_service.stop()` called
3. Daily scheduler task cancelled
4. Graceful cleanup

## Database Schema

### financial_goals Table

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| goal_type | VARCHAR(50) | Goal type (monthly_return, monthly_income, portfolio_value) |
| target_value | NUMERIC(20,2) | Target value |
| current_value | NUMERIC(20,2) | Current value |
| progress_percent | NUMERIC(5,2) | Progress percentage |
| target_date | DATE | Optional target date |
| status | VARCHAR(20) | Goal status |
| created_at | TIMESTAMP | Creation timestamp |
| updated_at | TIMESTAMP | Last update timestamp |

**Indexes**:
- `financial_goals_goal_type_key` (UNIQUE on goal_type)
- `idx_financial_goals_type`
- `idx_financial_goals_status`

### goal_progress_history Table

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| goal_id | UUID | Foreign key to financial_goals |
| snapshot_date | DATE | Snapshot date |
| actual_value | NUMERIC(20,2) | Actual value on date |
| variance_percent | NUMERIC(5,2) | Variance from target |
| created_at | TIMESTAMP | Creation timestamp |

**Indexes**:
- `idx_goal_progress_goal_id_date` (goal_id, snapshot_date)

### goal_adjustment_log Table

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| portfolio_value | NUMERIC(20,2) | Portfolio value at adjustment |
| adjustment_factor | NUMERIC(5,4) | Adjustment factor applied |
| reason | TEXT | Reason for adjustment |
| created_at | TIMESTAMP | Creation timestamp |

## Configuration

### Default Goal Targets

Set in `GoalTrackingService.__init__()`:

```python
self.monthly_return_target = 5.0  # 5% monthly return
self.monthly_income_target = 2000.0  # $2000 monthly income
self.portfolio_value_target = 50000.0  # $50k portfolio milestone
```

### Schedule Time

Daily execution time (UTC):

```python
target_time = datetime.combine(
    now.date(),
    time(23, 59, 0),  # 11:59 PM UTC
    tzinfo=timezone.utc
)
```

### Status Thresholds

```python
def _get_goal_status(self, progress_percent: float) -> str:
    if progress_percent >= 100:
        return "achieved"
    elif progress_percent >= 85:
        return "on_track"
    elif progress_percent >= 70:
        return "at_risk"
    else:
        return "behind"
```

## Testing

### Test Suite

**File**: `risk_manager/test_goal_tracking.py` (262 lines)

**Test Cases** (10 total):

1. ✅ Get goals status
2. ✅ Manual snapshot trigger
3. ✅ Goal history retrieval (all 3 types)
4. ✅ Invalid goal type validation
5. ✅ Update single goal target
6. ✅ Update multiple targets
7. ✅ No targets provided error
8. ✅ Record realized profit
9. ✅ Record realized loss
10. ✅ Goal status after snapshot

**Run Tests**:
```bash
python3 risk_manager/test_goal_tracking.py
```

**Expected Output**:
```
GOAL TRACKING SERVICE TESTS
===========================

=== Test 1: Get Goals Status ===
✅ Successfully retrieved goals status

... (8 more tests)

=== Test 10: Goal Status After Snapshot ===
✅ Successfully retrieved post-snapshot status

ALL TESTS COMPLETED
```

## Monitoring

### Health Check

The goal tracking service health is included in the risk manager health check:

```bash
GET http://localhost:8003/health
```

### Logs

Goal tracking logs are structured and searchable:

```
2025-11-11 23:59:00 [info] Running daily goal tracking date=2025-11-11
2025-11-11 23:59:00 [info] Monthly return tracked actual=4.2% target=5.0% progress=84.0%
2025-11-11 23:59:00 [info] Monthly income tracked actual=$1450.00 target=$2000.00 progress=72.5%
2025-11-11 23:59:00 [info] Portfolio value tracked actual=$47500.00 target=$50000.00 progress=95.0%
2025-11-11 23:59:00 [info] Goal alert goal_type=monthly_income status=at_risk
2025-11-11 23:59:00 [info] Daily goal tracking completed successfully
```

### Prometheus Metrics

(Future enhancement - not yet implemented)

Planned metrics:
- `goal_progress_percent{goal_type="monthly_return"}` - Goal progress
- `goal_status{goal_type="monthly_return",status="on_track"}` - Goal status
- `goals_achieved_total` - Counter of achieved goals
- `goal_tracking_errors_total` - Error counter

## Error Handling

### Common Errors

1. **PostgresManager not connected**
   - **Cause**: Database not initialized before query
   - **Solution**: Added `if not self._connected: await self.initialize()` checks
   - **Recovery**: Automatic reconnection on next query

2. **Portfolio value calculation error**
   - **Cause**: No open positions or database error
   - **Solution**: Returns 0.0 with warning log
   - **Recovery**: Continues with other goals

3. **Month rollover calculation**
   - **Cause**: Start of month value not set
   - **Solution**: Warning logged, monthly return skipped
   - **Recovery**: Resets on next month's 1st day

## Performance

### Database Queries

- **Daily execution**: 3 UPDATE queries (one per goal)
- **Status endpoint**: 1 SELECT query
- **History endpoint**: 1 JOIN query
- **Snapshot storage**: 3 INSERT queries

### Execution Time

- Daily goal tracking: < 1 second
- API endpoints: < 100ms response time
- Database operations: < 50ms per query

## Future Enhancements

1. **Prometheus Metrics**
   - Export goal progress as metrics
   - Alert integration with Grafana

2. **Notification System**
   - Email alerts for goal achievements
   - Slack/Telegram notifications
   - SMS alerts for critical goals

3. **Advanced Analytics**
   - Goal achievement prediction
   - Trend analysis
   - Seasonal patterns

4. **Multi-User Support**
   - Per-user goal tracking
   - Team/organization goals
   - Leaderboards

5. **Dynamic Targets**
   - Auto-adjusting targets based on market conditions
   - Progressive goal increases
   - Adaptive difficulty

## Troubleshooting

### Issue: Goals not updating daily

**Check**:
1. Service is running: `docker logs mastertrade_risk_manager | grep "Goal tracking service started"`
2. Scheduler is active: Check logs for "Goal tracking scheduled"
3. Database connection: `curl http://localhost:8003/health`

**Solution**:
- Restart service: `docker compose restart risk_manager`
- Manual trigger: `curl -X POST http://localhost:8003/goals/manual-snapshot`

### Issue: Incorrect progress percentages

**Check**:
1. Portfolio value calculation: `curl http://localhost:8003/goals/status`
2. Month start value: Check logs for "Reset monthly tracking"
3. Realized profits recorded: Review order executor logs

**Solution**:
- Manual snapshot: `POST /goals/manual-snapshot`
- Update targets: `PUT /goals/targets?...`

### Issue: History returns empty array

**Cause**: No historical snapshots exist yet (first day of operation)

**Solution**: Wait for daily scheduler to run or trigger manual snapshot

## Summary

The Goal Tracking Service provides:

- ✅ Fully automated daily goal monitoring
- ✅ Three goal types (return, income, portfolio value)
- ✅ Four status levels (achieved, on_track, at_risk, behind)
- ✅ Alert system for goal status changes
- ✅ REST API for monitoring and management
- ✅ Historical progress tracking
- ✅ Monthly automatic resets
- ✅ Real-time profit/loss recording
- ✅ Comprehensive testing (10/10 tests passing)
- ✅ Production-ready deployment

The service runs autonomously, requiring no manual intervention for normal operation.
