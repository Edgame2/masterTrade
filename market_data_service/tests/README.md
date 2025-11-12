# Collector Unit Tests

Comprehensive unit tests for all data collectors in the market_data_service.

## Quick Start

### 1. Install Test Dependencies
```bash
cd /home/neodyme/Documents/Projects/masterTrade/market_data_service
pip install -r requirements-test.txt
```

### 2. Run All Tests
```bash
# Using the test runner script (recommended)
./run_collector_tests.sh

# Or directly with pytest
pytest tests/collectors/ -v --cov
```

## Test Files

| Test File | Collector | Tests | Lines | Status |
|-----------|-----------|-------|-------|--------|
| `test_moralis_collector.py` | Moralis (On-chain) | 30+ | 490 | ✅ |
| `test_twitter_collector.py` | Twitter (Social) | 35+ | 450+ | ✅ |
| `test_reddit_collector.py` | Reddit (Social) | 33+ | 450+ | ✅ |
| `test_glassnode_collector.py` | Glassnode (On-chain) | 38+ | 520+ | ✅ |
| `test_lunarcrush_collector.py` | LunarCrush (Social) | 35+ | 480+ | ✅ |

**Total:** 171+ test methods, ~2,400 lines of test code

## Test Runner Options

```bash
# Verbose output
./run_collector_tests.sh -v

# Run in parallel (faster)
./run_collector_tests.sh -p

# Run specific collector tests
./run_collector_tests.sh -t moralis
./run_collector_tests.sh -t twitter
./run_collector_tests.sh -t reddit

# Skip coverage (faster execution)
./run_collector_tests.sh --no-coverage

# Help
./run_collector_tests.sh -h
```

## Running Individual Test Classes

```bash
# Run specific test class
pytest tests/collectors/test_moralis_collector.py::TestWhaleDetection -v

# Run specific test method
pytest tests/collectors/test_moralis_collector.py::TestWhaleDetection::test_is_whale_transaction_btc -v
```

## Coverage

**Target:** >80% code coverage

### View Coverage Report
```bash
# Run tests with coverage
pytest tests/collectors/ -v --cov=collectors --cov-report=html

# Open HTML report
xdg-open htmlcov/index.html
```

### Coverage Configuration
See `pytest.ini` for coverage settings:
- Fail threshold: 80%
- Reports: HTML, XML, terminal
- Excluded: tests, venv, __pycache__

## Test Structure

### Fixtures (conftest.py)
Shared fixtures available to all tests:
- `mock_db` - Mock database
- `mock_rabbitmq` - Mock RabbitMQ channel
- `mock_http_session` - Mock HTTP session
- `sample_*` - Sample data for each collector type

### Test Classes
Each test file contains multiple test classes:
1. **Initialization** - Constructor and config tests
2. **Core Functionality** - Business logic tests
3. **API Interactions** - External API tests
4. **Database Operations** - Storage tests
5. **RabbitMQ Publishing** - Message publishing tests
6. **Rate Limiting** - Rate limit enforcement
7. **Error Handling** - Exception and retry tests
8. **Statistics** - Tracking and monitoring
9. **Edge Cases** - Boundary conditions

## Mocking Strategy

All external dependencies are mocked:
- ✅ **Database**: AsyncMock for all DB operations
- ✅ **RabbitMQ**: AsyncMock for channel and publishing
- ✅ **HTTP APIs**: patch decorators for API calls
- ✅ **Time**: Fixed timestamps where needed

Benefits:
- Fast execution (~30 seconds for all tests)
- No external service dependencies
- Deterministic results
- Isolated test environment

## Test Categories

### Unit Tests (default)
```bash
pytest tests/collectors/ -m unit
```

### Async Tests
```bash
pytest tests/collectors/ -m asyncio
```

### Slow Tests (skipped by default)
```bash
pytest tests/collectors/ -m slow
```

## Continuous Integration

### GitHub Actions Example
```yaml
name: Collector Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
        with:
          python-version: 3.11
      - name: Install dependencies
        run: pip install -r requirements-test.txt
      - name: Run tests
        run: pytest tests/collectors/ -v --cov --cov-fail-under=80
```

## Troubleshooting

### Import Errors
```bash
# Ensure you're in the market_data_service directory
cd /home/neodyme/Documents/Projects/masterTrade/market_data_service

# Install dependencies
pip install -r requirements-test.txt
```

### Coverage Below 80%
```bash
# Run with coverage report to see missing lines
pytest tests/collectors/ --cov=collectors --cov-report=term-missing

# View HTML report for detailed analysis
xdg-open htmlcov/index.html
```

### Slow Test Execution
```bash
# Run in parallel
pytest tests/collectors/ -n auto

# Or skip coverage
pytest tests/collectors/ --no-cov
```

## Test Data

Sample test data available in `conftest.py`:
- Whale transactions ($1M+ USD)
- Social media posts (Twitter, Reddit)
- On-chain metrics (NVT, MVRV, NUPL)
- Social metrics (AltRank, Galaxy Score)

## Adding New Tests

### 1. Create Test File
```python
# tests/collectors/test_new_collector.py
import pytest
from unittest.mock import AsyncMock

from collectors.new_collector import NewCollector

@pytest.fixture
def new_collector(mock_db, mock_rabbitmq):
    return NewCollector(
        database=mock_db,
        api_key="test_key",
        rabbitmq_channel=mock_rabbitmq
    )

class TestNewCollector:
    @pytest.mark.asyncio
    async def test_collect_data(self, new_collector):
        result = await new_collector.collect_data()
        assert result is not None
```

### 2. Run New Tests
```bash
pytest tests/collectors/test_new_collector.py -v
```

## Best Practices

1. **Use Fixtures**: Leverage shared fixtures from `conftest.py`
2. **Mock Everything**: Mock all external dependencies
3. **Test Edge Cases**: Include boundary conditions
4. **Descriptive Names**: Use clear test method names
5. **Async Tests**: Mark async tests with `@pytest.mark.asyncio`
6. **Assertions**: Use specific assertions with clear messages
7. **Coverage**: Aim for >80% coverage

## Documentation

- **Summary**: See `COLLECTOR_TESTS_SUMMARY.md` for detailed implementation summary
- **Configuration**: See `pytest.ini` for pytest settings
- **Dependencies**: See `requirements-test.txt` for test dependencies

## Support

For issues or questions:
1. Check test output for specific error messages
2. Review `COLLECTOR_TESTS_SUMMARY.md` for implementation details
3. Verify all dependencies are installed: `pip install -r requirements-test.txt`
4. Ensure you're in the correct directory: `market_data_service/`

---

**Last Updated:** 2025-11-12  
**Coverage Target:** >80%  
**Test Count:** 171+ methods  
**Status:** ✅ Production Ready
