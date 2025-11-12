# End-to-End Test Suite

Comprehensive end-to-end tests for the MasterTrade system, verifying complete data flow from collection to API retrieval.

## Overview

The E2E test suite validates:
- **Data Pipeline**: Collector → RabbitMQ → Consumer → PostgreSQL → API
- **Collector Integration**: Real collector behavior with mocked external APIs
- **Signal Aggregation**: Multi-source signal generation and strategy consumption
- **API Queries**: REST API endpoints with filtering, pagination, and error handling

## Test Structure

```
tests/e2e/
├── __init__.py                      # Package initialization
├── conftest.py                       # Shared fixtures and utilities
├── test_data_pipeline.py            # Complete pipeline E2E tests
├── test_collector_integration.py    # Collector behavior tests
├── test_signal_aggregation.py       # Signal aggregation tests
└── test_api_queries.py              # API endpoint tests
```

## Prerequisites

### Services Required

The following services must be running:
- **PostgreSQL**: Port 5432 (database)
- **RabbitMQ**: Port 5672 (message broker)
- **market_data_service**: Port 8000 (API)
- **strategy_service**: Port 8006 (API)
- **risk_manager**: Port 8003 (API)

### Dependencies

Install test dependencies:

```bash
pip install -r requirements-test.txt
```

Required packages:
- `pytest>=7.4.0`
- `pytest-asyncio>=0.21.0`
- `pytest-timeout>=2.1.0`
- `aiohttp>=3.8.0`
- `aio_pika>=9.0.0`
- `asyncpg>=0.28.0`
- `aioresponses>=0.7.4`

### Environment Variables

Set test environment variables (optional):

```bash
export TEST_DATABASE_URL="postgresql://mastertrade:mastertrade@localhost:5432/mastertrade"
export TEST_RABBITMQ_URL="amqp://guest:guest@localhost:5672/"
export MARKET_DATA_API_URL="http://localhost:8000"
export STRATEGY_API_URL="http://localhost:8006"
export RISK_MANAGER_API_URL="http://localhost:8003"
```

## Running Tests

### Run All E2E Tests

```bash
cd /home/neodyme/Documents/Projects/masterTrade
pytest tests/e2e/ -v
```

### Run Specific Test Files

```bash
# Data pipeline tests
pytest tests/e2e/test_data_pipeline.py -v

# Collector integration tests
pytest tests/e2e/test_collector_integration.py -v

# Signal aggregation tests
pytest tests/e2e/test_signal_aggregation.py -v

# API query tests
pytest tests/e2e/test_api_queries.py -v
```

### Run Specific Test Classes

```bash
# Whale transaction pipeline
pytest tests/e2e/test_data_pipeline.py::TestDataPipelineE2E::test_whale_transaction_pipeline -v

# Moralis collector
pytest tests/e2e/test_collector_integration.py::TestMoralisCollectorIntegration -v

# Signal aggregation
pytest tests/e2e/test_signal_aggregation.py::TestSignalAggregationE2E -v

# API endpoints
pytest tests/e2e/test_api_queries.py::TestWhaleTransactionAPI -v
```

### Run with Coverage

```bash
pytest tests/e2e/ -v --cov=market_data_service --cov=strategy_service --cov-report=html
```

### Quick Test Script

Use the provided runner script:

```bash
./tests/e2e/run_e2e_tests.sh
```

## Test Categories

### 1. Data Pipeline Tests (`test_data_pipeline.py`)

Tests complete data flow through the system:

| Test | Description | Verifies |
|------|-------------|----------|
| `test_whale_transaction_pipeline` | Whale transaction E2E flow | Message publishing, storage, API retrieval, latency <60s |
| `test_onchain_metric_pipeline` | On-chain metric E2E flow | GlassnodeCollector → RabbitMQ → DB → API |
| `test_social_sentiment_pipeline` | Social sentiment E2E flow | TwitterCollector → RabbitMQ → DB → API |
| `test_error_handling_in_pipeline` | Error handling | Invalid JSON, missing fields, constraint violations |
| `test_high_throughput_pipeline` | Performance | Burst handling (10 messages), no data loss |

**Success Criteria:**
- ✅ Data integrity preserved through entire pipeline
- ✅ Latency < 60 seconds (target: < 10 seconds)
- ✅ 100% message delivery (no loss)
- ✅ Graceful error handling

### 2. Collector Integration Tests (`test_collector_integration.py`)

Tests real collector behavior with mocked APIs:

| Collector | Tests | Mocked APIs |
|-----------|-------|-------------|
| **Moralis** | Transaction collection, rate limiting, circuit breaker | Moralis wallet history API |
| **Glassnode** | NVT ratio collection, API errors (429) | Glassnode metrics API |
| **Twitter** | Tweet collection, sentiment analysis | Twitter search API |
| **Reddit** | Post collection, rate limit respect | Reddit subreddit API |

**Success Criteria:**
- ✅ API requests formed correctly
- ✅ Rate limiting enforced (1 req/s for testing)
- ✅ Circuit breaker opens after 3 failures
- ✅ Sentiment analysis accurate (positive/negative/neutral)
- ✅ Database storage operations successful

### 3. Signal Aggregation Tests (`test_signal_aggregation.py`)

Tests multi-source signal generation:

| Test | Description | Validates |
|------|-------------|-----------|
| `test_complete_signal_aggregation_pipeline` | End-to-end signal flow | Price + Sentiment + OnChain → Signal |
| `test_weighted_signal_calculation` | Weight application | 35% price, 25% sentiment, 20% onchain, 20% flow |
| `test_conflicting_signals_handling` | Conflict resolution | Bearish price + Bullish sentiment = WEAK/HOLD |
| `test_signal_confidence_threshold` | Confidence filtering | Only >0.65 confidence triggers actions |
| `test_signal_time_decay` | Old data exclusion | Signals >1 hour excluded |
| `test_missing_source_graceful_degradation` | Partial data handling | Adjusted weights when sources missing |
| `test_signal_persistence_and_history` | Historical tracking | Signals stored for analysis |

**Success Criteria:**
- ✅ Weighted aggregation (35/25/20/20) applied correctly
- ✅ Signal strength: STRONG (≥0.7), MODERATE (≥0.5), WEAK (<0.5)
- ✅ Action determination: BUY/SELL (confidence ≥0.65), HOLD (confidence <0.65)
- ✅ Old signals (>1 hour) excluded
- ✅ Graceful handling of missing sources

### 4. API Query Tests (`test_api_queries.py`)

Tests REST API endpoints comprehensively:

| Endpoint | Tests | Validates |
|----------|-------|-----------|
| `/api/v1/onchain/whale-transactions` | List, filter by amount, pagination | Response format, filtering, limits |
| `/api/v1/onchain/metrics/{symbol}` | Get by symbol, filter by metric name | Metric aggregation, filtering |
| `/api/v1/social/sentiment/{symbol}` | Get by symbol, filter by source | Sentiment aggregation, summary stats |
| `/api/v1/social/trending` | Trending topics | Symbol ranking by mentions |

**Error Handling Tests:**
- Invalid symbol (404/empty result)
- Invalid parameters (400/graceful handling)
- Timeout handling (5s timeout)

**Performance Tests:**
- Response time < 1000ms (target: <200ms p95)
- Concurrent requests (10 simultaneous)

**Success Criteria:**
- ✅ All endpoints return correct data format
- ✅ Filtering works (symbol, amount, source, metric)
- ✅ Pagination enforced (limit parameter)
- ✅ Summary statistics calculated correctly
- ✅ Error handling graceful (400/404 responses)
- ✅ Performance acceptable (<1s response time)

## Test Data

### Automatic Cleanup

All test data is marked with `"test_marker": "e2e_test"` and automatically cleaned up:
- **Before each test**: Cleanup via `clean_test_data` fixture
- **After each test**: Cleanup via `clean_test_data` fixture

Tables cleaned:
- `whale_transactions`
- `onchain_metrics`
- `social_sentiment`
- `social_metrics_aggregated`
- `market_signals`
- `indicator_results`
- `historical_klines`

### Test Data Generators

Fixtures provide realistic test data:

| Fixture | Generates | Example |
|---------|-----------|---------|
| `whale_transaction_data` | Large transactions | $1M-$10M BTC transactions |
| `onchain_metric_data` | On-chain metrics | NVT ratio, MVRV, exchange flows |
| `social_sentiment_data` | Social sentiment | Twitter/Reddit posts with scores |
| `market_signal_data` | Market signals | BUY/SELL signals with confidence |

## Common Issues & Solutions

### Issue: Services Not Running

**Symptom**: Connection refused errors

**Solution**:
```bash
# Check service status
docker-compose ps

# Start services
docker-compose up -d postgres rabbitmq market_data_service
```

### Issue: Database Connection Errors

**Symptom**: `asyncpg.exceptions.InvalidCatalogNameError`

**Solution**:
```bash
# Verify database exists
docker exec mastertrade_postgres psql -U mastertrade -l

# Check connection string
echo $TEST_DATABASE_URL
```

### Issue: RabbitMQ Queue Not Found

**Symptom**: Queue doesn't exist errors

**Solution**:
```bash
# Check RabbitMQ queues
docker exec mastertrade_rabbitmq rabbitmqctl list_queues

# Restart RabbitMQ
docker-compose restart rabbitmq
```

### Issue: Test Timeouts

**Symptom**: Tests hang or timeout

**Solution**:
```bash
# Run with timeout
pytest tests/e2e/ -v --timeout=60

# Check service health
curl http://localhost:8000/health
```

### Issue: Data Not Cleaned Up

**Symptom**: Test failures due to existing data

**Solution**:
```bash
# Manual cleanup
docker exec mastertrade_postgres psql -U mastertrade -d mastertrade -c "
DELETE FROM whale_transactions WHERE data->>'test_marker' = 'e2e_test';
DELETE FROM onchain_metrics WHERE data->>'test_marker' = 'e2e_test';
DELETE FROM social_sentiment WHERE data->>'test_marker' = 'e2e_test';
"
```

## Test Metrics & KPIs

### Coverage Targets

- **Overall Coverage**: >80%
- **Critical Paths**: >90%
- **Error Handling**: 100%

### Performance Targets

- **Pipeline Latency**: <60s (target: <10s)
- **API Response Time**: <1s (target: <200ms p95)
- **Message Throughput**: >10 messages/second
- **Concurrent Requests**: 10+ simultaneous

### Reliability Targets

- **Test Pass Rate**: >95%
- **Data Integrity**: 100%
- **Error Recovery**: 100%

## Continuous Integration

### GitHub Actions Workflow

```yaml
name: E2E Tests

on: [push, pull_request]

jobs:
  e2e-tests:
    runs-on: ubuntu-latest
    
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_PASSWORD: mastertrade
        ports:
          - 5432:5432
      
      rabbitmq:
        image: rabbitmq:3-management
        ports:
          - 5672:5672
    
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          pip install -r requirements-test.txt
      
      - name: Run E2E tests
        run: |
          pytest tests/e2e/ -v --cov --cov-report=xml
      
      - name: Upload coverage
        uses: codecov/codecov-action@v3
```

## Next Steps

After E2E tests pass:

1. ✅ **Unit Tests**: Complete (collectors, goal system)
2. ✅ **E2E Tests**: Complete (data pipeline, collectors, signals, API)
3. ⏳ **Integration Tests**: Goal-oriented trading flow
4. ⏳ **Performance Tests**: Load testing, stress testing
5. ⏳ **Security Tests**: Authentication, authorization, injection

## References

- [pytest Documentation](https://docs.pytest.org/)
- [pytest-asyncio](https://pytest-asyncio.readthedocs.io/)
- [aiohttp Testing](https://docs.aiohttp.org/en/stable/testing.html)
- [RabbitMQ Testing](https://www.rabbitmq.com/testing.html)

---

**Last Updated**: November 12, 2025
**Test Suite Version**: 1.0.0
**Status**: ✅ Production Ready
