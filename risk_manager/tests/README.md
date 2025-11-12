# Goal-Oriented System Unit Tests

Comprehensive unit tests for the goal-oriented trading system in MasterTrade.

## Quick Start

### Install Dependencies
```bash
cd /home/neodyme/Documents/Projects/masterTrade/risk_manager
pip install -r requirements-test.txt
```

### Run All Tests
```bash
pytest tests/ -v
```

### Run with Coverage
```bash
pytest tests/ -v --cov
```

## Test Files

| Test File | Module Tested | Tests | Status |
|-----------|--------------|-------|--------|
| `test_goal_tracking_unit.py` | Goal Tracking Service | 40+ | ✅ |
| `test_goal_oriented_sizing_unit.py` | Position Sizing Adjustments | 45+ | ✅ |
| `test_goal_based_drawdown_unit.py` | Drawdown Protection | 40+ | ✅ |

**Total:** 125+ test methods across 3 modules

## Test Coverage

### Goal Tracking Service Tests
**File:** `test_goal_tracking_unit.py`

**Coverage:**
- ✅ Initialization (defaults, custom targets)
- ✅ Goal progress calculation (monthly return, income, portfolio value)
- ✅ Daily snapshots (creation, once per day, data recording)
- ✅ Alert triggering (achieved, at risk, on track)
- ✅ Goal status determination (on track, ahead, at risk, achieved)
- ✅ Monthly reset (new month detection, income clearing, portfolio value update)
- ✅ Service lifecycle (start, stop, cannot start twice)
- ✅ Edge cases (goal achieved early, severe underperformance, negative returns, zero start value, milestone reached)
- ✅ Daily scheduler (runs daily, handles errors)

**Test Classes:** 9
**Test Methods:** 40+

---

### Goal-Oriented Sizing Tests
**File:** `test_goal_oriented_sizing_unit.py`

**Coverage:**
- ✅ Initialization (database, targets, factors, thresholds)
- ✅ Adjustment factor calculation (on track = 1.0x, behind = aggressive, ahead = conservative)
- ✅ Portfolio milestone protection (preservation mode near €1M, full preservation at €950k, no preservation below €800k)
- ✅ Progress-based adjustments (critical <50%, at risk 50-70%, ahead >115%)
- ✅ Time-based adjustments (early month tolerance, late month urgency)
- ✅ Combined factors (behind but near milestone, ahead but low portfolio)
- ✅ Edge cases (zero progress, negative progress, extreme overperformance, first/last day of month)
- ✅ Database integration (fetch goal progress)
- ✅ Factor boundaries (never below 0.5, never above 1.3)

**Test Classes:** 9
**Test Methods:** 45+

**Key Scenarios Tested:**
- **Normal sizing (1.0x):** 85-115% of target progress
- **Aggressive sizing (1.1-1.3x):** <85% of target progress
- **Conservative sizing (0.7-0.9x):** >115% of target progress
- **Preservation mode (0.5-0.7x):** Portfolio value >€800k approaching €1M

---

### Goal-Based Drawdown Protection Tests
**File:** `test_goal_based_drawdown_unit.py`

**Coverage:**
- ✅ Initialization (defaults, custom limits)
- ✅ Drawdown stance determination (normal, protective, breached)
- ✅ Dynamic limit adjustments (5% normal, 2% protective)
- ✅ Breach detection (normal mode, protective mode, within limit)
- ✅ Action triggering (pause new, reduce positions, close all)
- ✅ Monthly peak tracking (update on new high, no update below peak, reset on new month)
- ✅ Drawdown calculation (percentage, zero at peak, large drawdown)
- ✅ Event logging (breach events to database)
- ✅ Goal progress caching (reduce DB queries, cache expiration)
- ✅ Edge cases (zero peak, negative drawdown, exactly at threshold, above milestone)
- ✅ Protective vs normal thresholds (stricter in protective mode)
- ✅ Multiple breach actions (can trigger multiple actions)

**Test Classes:** 12
**Test Methods:** 40+

**Key Protection Modes:**
- **Normal (5% limit):** <90% of €1M milestone
- **Protective (2% limit):** >90% of €1M milestone
- **Actions on breach:** Pause new → Reduce 50% → Close all

---

## Test Infrastructure

### Fixtures (conftest.py)
Shared test fixtures:
- `mock_database` - Mock RiskPostgresDatabase with all methods
- `fixed_datetime` - Fixed timestamp for testing
- `goal_progress_data` - Sample goal progress data

### Configuration (pytest.ini)
- Coverage target: 80%
- Async test support
- HTML and terminal coverage reports
- Warning filters

---

## Running Specific Tests

### By Test Class
```bash
# Goal tracking tests
pytest tests/test_goal_tracking_unit.py::TestGoalProgressCalculation -v

# Sizing adjustment tests
pytest tests/test_goal_oriented_sizing_unit.py::TestAdjustmentFactorCalculation -v

# Drawdown protection tests
pytest tests/test_goal_based_drawdown_unit.py::TestDrawdownBreachDetection -v
```

### By Test Method
```bash
pytest tests/test_goal_tracking_unit.py::TestGoalProgressCalculation::test_calculate_monthly_return_progress -v
```

### By Marker
```bash
# Run only async tests
pytest tests/ -m asyncio -v

# Run only unit tests
pytest tests/ -m unit -v
```

---

## Test Patterns

### Async Test Example
```python
@pytest.mark.asyncio
async def test_calculate_adjustment_factor(self, mock_database):
    module = GoalOrientedSizingModule(database=mock_database)
    
    factor = await module.calculate_goal_adjustment_factor(
        current_portfolio_value=500000.0,
        monthly_return_progress=0.90,
        monthly_income_progress=0.95,
        days_into_month=15
    )
    
    assert 0.9 <= factor <= 1.1
```

### Mocking Database Example
```python
mock_database.get_current_goal_progress = AsyncMock(return_value={
    'monthly_return_progress': 0.75,
    'monthly_income_progress': 0.80,
    'portfolio_value': 450000.0
})
```

---

## Edge Cases Covered

### Goal Tracking
- ✅ Goal achieved early in month
- ✅ Severe underperformance (10% progress on day 28)
- ✅ Negative monthly returns
- ✅ Zero start portfolio value
- ✅ Portfolio value milestone reached

### Position Sizing
- ✅ Zero progress (maximum aggressive)
- ✅ Negative progress (losses)
- ✅ Extreme overperformance (>200% of target)
- ✅ First day of month
- ✅ Last day of month
- ✅ Behind on goals but near €1M (preservation overrides)

### Drawdown Protection
- ✅ Zero peak value
- ✅ Negative drawdown (portfolio above peak)
- ✅ Exactly at milestone threshold (90%)
- ✅ Portfolio above milestone (>100%)
- ✅ Multiple actions on severe breach

---

## Coverage Report

### View HTML Coverage Report
```bash
pytest tests/ --cov --cov-report=html
xdg-open htmlcov/index.html
```

### Terminal Coverage Report
```bash
pytest tests/ --cov --cov-report=term-missing
```

---

## Integration with CI/CD

### GitHub Actions Example
```yaml
name: Goal System Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
        with:
          python-version: 3.11
      - run: pip install -r requirements-test.txt
      - run: pytest tests/ -v --cov --cov-fail-under=80
```

---

## Test Statistics

| Module | Lines of Code | Test Lines | Test/Code Ratio | Coverage Target |
|--------|--------------|------------|-----------------|-----------------|
| goal_tracking_service.py | 485 | 600+ | 1.24 | >80% |
| goal_oriented_sizing.py | 361 | 700+ | 1.94 | >80% |
| goal_based_drawdown.py | 425 | 650+ | 1.53 | >80% |
| **TOTAL** | **1,271** | **1,950+** | **1.53** | **>80%** |

---

## Production Readiness

✅ **Comprehensive test coverage** (125+ test methods)  
✅ **All edge cases tested** (early achievement, severe underperformance, negative returns, etc.)  
✅ **Mocking strategy** (all database and external dependencies mocked)  
✅ **Async test support** (pytest-asyncio configured)  
✅ **Coverage tracking** (>80% threshold)  
✅ **Test documentation** (this README + inline comments)  

---

## Troubleshooting

### Import Errors
```bash
# Ensure you're in the risk_manager directory
cd /home/neodyme/Documents/Projects/masterTrade/risk_manager

# Install dependencies
pip install -r requirements-test.txt
```

### AsyncIO Warnings
```bash
# Ensure pytest-asyncio is installed
pip install pytest-asyncio==0.21.1
```

### Coverage Below 80%
```bash
# Run with detailed coverage report
pytest tests/ --cov --cov-report=term-missing

# Identify missing coverage
xdg-open htmlcov/index.html
```

---

**Last Updated:** 2025-11-12  
**Status:** ✅ Production Ready  
**Coverage:** >80% target  
**Test Count:** 125+ methods
