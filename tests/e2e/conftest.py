"""
Pytest configuration and shared fixtures for E2E tests.

Provides:
- Database connection and cleanup
- RabbitMQ connection and queue management
- Test data generators
- HTTP client fixtures
- Service health checks
"""

import asyncio
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import pytest
import aio_pika
import asyncpg
from asyncpg import Pool


# ============================================================================
# Database Fixtures
# ============================================================================

@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def db_pool() -> Pool:
    """Create PostgreSQL connection pool for tests."""
    database_url = os.getenv(
        "TEST_DATABASE_URL",
        "postgresql://mastertrade:mastertrade@localhost:5432/mastertrade"
    )
    
    pool = await asyncpg.create_pool(
        database_url,
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
async def clean_test_data(db_connection):
    """Clean up test data before and after tests."""
    # Clean before test
    await _cleanup_test_tables(db_connection)
    
    yield
    
    # Clean after test
    await _cleanup_test_tables(db_connection)


async def _cleanup_test_tables(conn):
    """Clean up test data from all tables."""
    tables = [
        'whale_transactions',
        'onchain_metrics',
        'social_sentiment',
        'social_metrics_aggregated',
        'market_signals',
        'indicator_results',
        'historical_klines'
    ]
    
    for table in tables:
        try:
            await conn.execute(f"DELETE FROM {table} WHERE data->>'test_marker' = 'e2e_test'")
        except Exception:
            # Table might not exist
            pass


# ============================================================================
# RabbitMQ Fixtures
# ============================================================================

@pytest.fixture(scope="session")
async def rabbitmq_connection():
    """Create RabbitMQ connection for tests."""
    rabbitmq_url = os.getenv(
        "TEST_RABBITMQ_URL",
        "amqp://guest:guest@localhost:5672/"
    )
    
    connection = await aio_pika.connect_robust(rabbitmq_url)
    
    yield connection
    
    await connection.close()


@pytest.fixture
async def rabbitmq_channel(rabbitmq_connection):
    """Get RabbitMQ channel for a test."""
    channel = await rabbitmq_connection.channel()
    
    yield channel
    
    await channel.close()


@pytest.fixture
async def test_queue(rabbitmq_channel):
    """Create a test queue."""
    queue_name = f"test_queue_{datetime.utcnow().timestamp()}"
    
    queue = await rabbitmq_channel.declare_queue(
        queue_name,
        auto_delete=True
    )
    
    yield queue
    
    try:
        await queue.delete()
    except Exception:
        pass


@pytest.fixture
async def test_exchange(rabbitmq_channel):
    """Create test exchange."""
    exchange_name = "mastertrade.market"
    
    exchange = await rabbitmq_channel.declare_exchange(
        exchange_name,
        aio_pika.ExchangeType.TOPIC,
        durable=True
    )
    
    yield exchange


# ============================================================================
# Test Data Generators
# ============================================================================

@pytest.fixture
def whale_transaction_data():
    """Generate test whale transaction data."""
    def _generate(symbol: str = "BTC", amount_usd: float = 1000000.0):
        return {
            "transaction_hash": f"0x{'1234567890abcdef' * 4}",
            "from_address": f"0x{'a' * 40}",
            "to_address": f"0x{'b' * 40}",
            "symbol": symbol,
            "amount": 10.0,
            "amount_usd": amount_usd,
            "timestamp": datetime.utcnow().isoformat(),
            "chain": "ethereum",
            "from_entity": "Exchange A",
            "to_entity": "Unknown Wallet",
            "transaction_type": "exchange_outflow",
            "test_marker": "e2e_test"  # Marker for cleanup
        }
    return _generate


@pytest.fixture
def onchain_metric_data():
    """Generate test on-chain metric data."""
    def _generate(symbol: str = "BTC", metric_name: str = "nvt_ratio"):
        return {
            "symbol": symbol,
            "metric_name": metric_name,
            "metric_value": 75.5,
            "timestamp": datetime.utcnow().isoformat(),
            "source": "glassnode",
            "metadata": {
                "change_24h": 5.2,
                "test_marker": "e2e_test"
            }
        }
    return _generate


@pytest.fixture
def social_sentiment_data():
    """Generate test social sentiment data."""
    def _generate(symbol: str = "BTC", sentiment_score: float = 0.75):
        return {
            "source": "twitter",
            "symbol": symbol,
            "text": f"Bullish on {symbol}! Great fundamentals.",
            "sentiment_score": sentiment_score,
            "engagement_count": 100,
            "author": "crypto_influencer",
            "url": "https://twitter.com/crypto_influencer/status/123",
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": {
                "test_marker": "e2e_test"
            }
        }
    return _generate


@pytest.fixture
def market_signal_data():
    """Generate test market signal data."""
    def _generate(symbol: str = "BTCUSDT", signal_strength: str = "STRONG"):
        return {
            "symbol": symbol,
            "signal_strength": signal_strength,
            "action": "BUY",
            "confidence": 0.85,
            "price_signal": 0.3,
            "sentiment_signal": 0.25,
            "onchain_signal": 0.2,
            "flow_signal": 0.1,
            "timestamp": datetime.utcnow().isoformat(),
            "test_marker": "e2e_test"
        }
    return _generate


# ============================================================================
# HTTP Client Fixtures
# ============================================================================

@pytest.fixture
def market_data_api_url():
    """Market data service API URL."""
    return os.getenv("MARKET_DATA_API_URL", "http://localhost:8000")


@pytest.fixture
def strategy_api_url():
    """Strategy service API URL."""
    return os.getenv("STRATEGY_API_URL", "http://localhost:8006")


@pytest.fixture
def risk_manager_api_url():
    """Risk manager API URL."""
    return os.getenv("RISK_MANAGER_API_URL", "http://localhost:8003")


# ============================================================================
# Helper Functions
# ============================================================================

async def wait_for_condition(
    condition_func,
    timeout: int = 30,
    check_interval: float = 0.5,
    error_message: str = "Condition not met within timeout"
):
    """
    Wait for a condition to become true.
    
    Args:
        condition_func: Async function that returns True when condition is met
        timeout: Maximum time to wait in seconds
        check_interval: Time between checks in seconds
        error_message: Error message if timeout is reached
    """
    start_time = asyncio.get_event_loop().time()
    
    while True:
        if await condition_func():
            return True
        
        elapsed = asyncio.get_event_loop().time() - start_time
        if elapsed > timeout:
            raise TimeoutError(f"{error_message} (waited {elapsed:.1f}s)")
        
        await asyncio.sleep(check_interval)


async def verify_data_in_database(
    conn,
    table: str,
    filters: Dict,
    expected_count: Optional[int] = None
) -> List[Dict]:
    """
    Verify data exists in database with given filters.
    
    Args:
        conn: Database connection
        table: Table name
        filters: Dictionary of column: value filters
        expected_count: Expected number of rows (None to skip check)
        
    Returns:
        List of matching rows as dictionaries
    """
    # Build WHERE clause
    where_conditions = []
    params = []
    param_num = 1
    
    for column, value in filters.items():
        if column.startswith('data->'):
            where_conditions.append(f"{column} = ${param_num}")
        else:
            where_conditions.append(f"{column} = ${param_num}")
        params.append(value)
        param_num += 1
    
    where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"
    
    query = f"SELECT * FROM {table} WHERE {where_clause}"
    
    rows = await conn.fetch(query, *params)
    
    if expected_count is not None:
        assert len(rows) == expected_count, (
            f"Expected {expected_count} rows in {table}, found {len(rows)}"
        )
    
    return [dict(row) for row in rows]


@pytest.fixture
def wait_for_data():
    """Fixture that provides wait_for_condition function."""
    return wait_for_condition


@pytest.fixture
def verify_database_data():
    """Fixture that provides verify_data_in_database function."""
    return verify_data_in_database
