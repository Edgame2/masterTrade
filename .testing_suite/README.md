# MasterTrade Testing Suite

Comprehensive testing framework for the MasterTrade automated trading system.

## Overview

This testing suite validates all components of the trading bot including:
- Database connectivity and schema
- Microservices health and APIs
- Data collection pipelines
- Strategy generation and backtesting
- Order execution and position management
- Risk management systems
- Monitoring and alerting
- Message queue (RabbitMQ) operations

## Test Modules

### 1. Environment Variables Tests (`test_environment.py`)
- Host environment variables check
- Docker Compose environment configuration
- Container environment variables validation
- Database credentials validity
- RabbitMQ credentials validity
- API keys and secrets configuration
- Service configuration files existence
- **Tests: 7**

### 2. Database Tests (`test_database.py`)
- PostgreSQL and TimescaleDB connectivity
- Critical table existence and schema validation
- Hypertables and continuous aggregates
- Index verification
- Insert/query performance benchmarks
- **Tests: 14**

### 3. Service Tests (`test_services.py`)
- Health endpoints for all 7 microservices
- API endpoint functionality
- Response time benchmarks (<2s requirement)
- **Tests: 11**

### 4. Data Collection Tests (`test_data_collection.py`)
- Market data collection from exchanges
- Sentiment data collection
- On-chain data collection
- Data freshness and quality
- Symbol coverage
- **Tests: 8**

### 5. Strategy Generation Tests (`test_strategy_generation.py`)
- Strategy generation system
- Backtesting framework
- Learning insights storage
- USDC symbol usage (bug fix verification)
- Strategy states and performance tracking
- **Tests: 10**

### 6. Order Execution Tests (`test_order_execution.py`)
- Order executor service health
- Paper trading mode
- Order states and tracking
- Position management
- Stop loss orders
- **Tests: 8**

### 7. Risk Management Tests (`test_risk_management.py`)
- Risk manager service health
- Position size limits
- Exposure limits
- Risk parameters
- Portfolio-level risk tracking
- **Tests: 6**

### 8. Monitoring Tests (`test_monitoring.py`)
- Grafana accessibility and dashboards
- Prometheus accessibility and targets
- Alert system health
- **Tests: 5**

### 9. Message Queue Tests (`test_message_queue.py`)
- RabbitMQ management interface
- Connections and consumers
- Exchanges and queues
- Message routing and bindings
- **Tests: 5**

## Running Tests

### Run All Tests
```bash
cd /home/neodyme/Documents/Projects/masterTrade/.testing_suite
python3 run_all_tests.py
```

### Run Individual Test Module
```bash
python3 test_database.py
python3 test_services.py
python3 test_data_collection.py
python3 test_strategy_generation.py
python3 test_order_execution.py
python3 test_risk_management.py
python3 test_monitoring.py
python3 test_message_queue.py
```

## Exit Codes

The main test runner (`run_all_tests.py`) returns:
- **0** (Success): ≥80% pass rate - System is healthy
- **1** (Warning): 60-79% pass rate - Some issues need attention
- **2** (Critical): <60% pass rate - Critical issues present

## Requirements

### Python Packages
```bash
pip install asyncpg aiohttp
```

### Services Running
All services should be running via Docker Compose:
```bash
docker compose up -d
```

### Database Connectivity
- PostgreSQL on port 5432
- TimescaleDB on port 5433
- Credentials: `mastertrade / mastertrade`

### Service Ports
- API Gateway: 8080
- Market Data: 8000
- Order Executor: 8002
- Risk Manager: 8003
- Data Access API: 8005
- Strategy Service: 8006
- Alert System: 8007
- RabbitMQ Management: 15672
- Grafana: 3000
- Prometheus: 9090

## Test Results Interpretation

### Excellent (≥95% pass)
System is fully operational and ready for automated trading.

### Good (80-94% pass)
System is mostly working. Review failed tests for non-critical issues.

### Fair (60-79% pass)
Some components have issues. Fix before enabling live trading.

### Critical (<60% pass)
Major issues present. System not ready for trading.

## Recent Bug Fixes Tested

### 1. Learning Insights Table (✅ Fixed)
- **Issue**: Missing `learning_insights` table
- **Test**: `test_database.py::test_learning_insights_table`
- **Verification**: Table exists with correct schema

### 2. JSON Parsing in Backtesting (✅ Fixed)
- **Issue**: Strategy dict being passed as string
- **Test**: `test_strategy_generation.py::test_strategy_parameters`
- **Verification**: All strategy parameters are valid JSON

### 3. USDC Symbol Usage (✅ Fixed)
- **Issue**: Code using USDT, database has USDC pairs
- **Test**: `test_strategy_generation.py::test_usdc_symbols`
- **Verification**: New strategies use USDC pairs only

## Next Steps

After running tests:

1. **Review Results**: Check pass/fail rates and error messages
2. **Fix Issues**: Address any failed tests
3. **Wait for 3:00 AM UTC**: Monitor automated strategy generation
4. **Verify Fixes**: Check logs for successful generation and backtesting
5. **Monitor Performance**: Track strategy activation and trading

## Test Coverage

Total tests: **74 tests** across 9 modules

- Environment Variables: 7 tests (9%)
- Database: 14 tests (19%)
- Services: 11 tests (15%)
- Data Collection: 8 tests (11%)
- Strategy Generation: 10 tests (14%)
- Order Execution: 8 tests (11%)
- Risk Management: 6 tests (8%)
- Monitoring: 5 tests (7%)
- Message Queue: 5 tests (7%)

## Continuous Monitoring

For ongoing system health monitoring:
- Grafana dashboards: http://localhost:3000
- Prometheus metrics: http://localhost:9090
- RabbitMQ management: http://localhost:15672

## Support

For issues or questions about the testing suite:
1. Check individual test file for detailed implementation
2. Review error messages in test output
3. Check service logs: `docker compose logs <service_name>`
4. Verify database connectivity and schema
