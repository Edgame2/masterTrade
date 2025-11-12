"""
Shared pytest fixtures and configuration for collector tests

This conftest.py provides common fixtures, utilities, and test helpers
that are shared across all collector test modules.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, MagicMock
from datetime import datetime, timezone
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


# ============================================================================
# Pytest Configuration
# ============================================================================

def pytest_configure(config):
    """Configure pytest markers"""
    config.addinivalue_line(
        "markers", "asyncio: mark test as async"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow running"
    )
    config.addinivalue_line(
        "markers", "integration: mark test as integration test"
    )


# ============================================================================
# Event Loop Fixtures
# ============================================================================

@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# ============================================================================
# Database Fixtures
# ============================================================================

@pytest.fixture
def mock_db():
    """Create a generic mock database instance"""
    db = Mock()
    db.store_whale_transaction = AsyncMock(return_value=True)
    db.store_onchain_metrics = AsyncMock(return_value=True)
    db.store_social_sentiment = AsyncMock(return_value=True)
    db.store_lunarcrush_metrics = AsyncMock(return_value=True)
    db.log_collector_health = AsyncMock(return_value=True)
    db.execute = AsyncMock(return_value=True)
    db.fetch = AsyncMock(return_value=[])
    db.fetchrow = AsyncMock(return_value=None)
    return db


@pytest.fixture
def mock_db_with_data():
    """Create mock database with sample data"""
    db = Mock()
    
    # Sample whale transactions
    db.store_whale_transaction = AsyncMock(return_value=True)
    db.get_whale_transactions = AsyncMock(return_value=[
        {
            "hash": "0x123...",
            "symbol": "BTC",
            "amount": 1500,
            "value_usd": 75000000,
            "timestamp": datetime.now(timezone.utc)
        }
    ])
    
    # Sample on-chain metrics
    db.store_onchain_metrics = AsyncMock(return_value=True)
    db.get_onchain_metrics = AsyncMock(return_value={
        "nvt_ratio": 75.5,
        "mvrv_ratio": 2.3,
        "active_addresses": 1000000
    })
    
    # Sample social sentiment
    db.store_social_sentiment = AsyncMock(return_value=True)
    db.get_social_sentiment = AsyncMock(return_value={
        "sentiment": "bullish",
        "sentiment_score": 0.75,
        "source": "twitter"
    })
    
    db.log_collector_health = AsyncMock(return_value=True)
    
    return db


# ============================================================================
# RabbitMQ Fixtures
# ============================================================================

@pytest.fixture
def mock_rabbitmq():
    """Create a mock RabbitMQ channel"""
    channel = AsyncMock()
    channel.default_exchange = Mock()
    channel.default_exchange.publish = AsyncMock()
    channel.close = AsyncMock()
    channel.is_closed = False
    return channel


@pytest.fixture
def mock_rabbitmq_with_queue():
    """Create mock RabbitMQ with queue"""
    channel = AsyncMock()
    queue = AsyncMock()
    queue.name = "test_queue"
    
    channel.default_exchange = Mock()
    channel.default_exchange.publish = AsyncMock()
    channel.declare_queue = AsyncMock(return_value=queue)
    channel.close = AsyncMock()
    
    return channel


# ============================================================================
# Time Utilities
# ============================================================================

@pytest.fixture
def fixed_datetime():
    """Return a fixed datetime for testing"""
    return datetime(2025, 11, 12, 10, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def time_now():
    """Return current datetime"""
    return datetime.now(timezone.utc)


# ============================================================================
# HTTP Request Mocking
# ============================================================================

@pytest.fixture
def mock_http_response():
    """Create mock HTTP response"""
    response = Mock()
    response.status_code = 200
    response.json = Mock(return_value={"data": []})
    response.text = "{}"
    return response


@pytest.fixture
def mock_http_session():
    """Create mock aiohttp session"""
    session = AsyncMock()
    
    # Mock get request
    get_response = AsyncMock()
    get_response.status = 200
    get_response.json = AsyncMock(return_value={"data": []})
    get_response.__aenter__ = AsyncMock(return_value=get_response)
    get_response.__aexit__ = AsyncMock(return_value=None)
    
    session.get = Mock(return_value=get_response)
    session.post = Mock(return_value=get_response)
    session.close = AsyncMock()
    
    return session


# ============================================================================
# Collector Test Data
# ============================================================================

@pytest.fixture
def sample_whale_transaction():
    """Sample whale transaction data"""
    return {
        "hash": "0xabc123def456...",
        "from_address": "0x1111111...",
        "to_address": "0x2222222...",
        "symbol": "BTC",
        "amount": 1500.0,
        "value_usd": 75000000.0,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "block_number": 800000
    }


@pytest.fixture
def sample_twitter_data():
    """Sample Twitter data"""
    return {
        "id": "1234567890",
        "text": "Bitcoin is amazing! 🚀",
        "created_at": "2025-11-12T10:00:00Z",
        "author": {
            "username": "crypto_user",
            "verified": False
        },
        "public_metrics": {
            "like_count": 100,
            "retweet_count": 50,
            "reply_count": 10
        }
    }


@pytest.fixture
def sample_reddit_data():
    """Sample Reddit data"""
    return {
        "id": "abc123",
        "title": "Bitcoin reaches new ATH!",
        "selftext": "Amazing news for crypto",
        "score": 1500,
        "upvote_ratio": 0.95,
        "num_comments": 250,
        "created_utc": 1699800000,
        "author": "crypto_enthusiast",
        "subreddit": "cryptocurrency",
        "all_awardings": []
    }


@pytest.fixture
def sample_onchain_metrics():
    """Sample on-chain metrics data"""
    return {
        "symbol": "BTC",
        "nvt_ratio": 75.5,
        "mvrv_ratio": 2.3,
        "exchange_net_flow": -5000,
        "nupl": 0.65,
        "active_addresses": 1000000,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@pytest.fixture
def sample_lunarcrush_metrics():
    """Sample LunarCrush metrics data"""
    return {
        "symbol": "BTC",
        "alt_rank": 1,
        "galaxy_score": 85,
        "social_volume": 50000,
        "social_dominance": 45.5,
        "sentiment": "bullish",
        "sentiment_score": 0.75,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


# ============================================================================
# Test Utilities
# ============================================================================

class AsyncIterator:
    """Helper class for async iteration in tests"""
    def __init__(self, items):
        self.items = items
        self.index = 0
    
    def __aiter__(self):
        return self
    
    async def __anext__(self):
        if self.index >= len(self.items):
            raise StopAsyncIteration
        item = self.items[self.index]
        self.index += 1
        return item


@pytest.fixture
def async_iterator():
    """Factory for creating async iterators"""
    return AsyncIterator


# ============================================================================
# Environment Configuration
# ============================================================================

@pytest.fixture
def test_env_vars(monkeypatch):
    """Set test environment variables"""
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost/test")
    monkeypatch.setenv("RABBITMQ_URL", "amqp://test:test@localhost/")
    monkeypatch.setenv("MORALIS_API_KEY", "test_moralis_key")
    monkeypatch.setenv("TWITTER_API_KEY", "test_twitter_key")
    monkeypatch.setenv("REDDIT_CLIENT_ID", "test_reddit_id")
    monkeypatch.setenv("GLASSNODE_API_KEY", "test_glassnode_key")
    monkeypatch.setenv("LUNARCRUSH_API_KEY", "test_lunarcrush_key")


# ============================================================================
# Assertion Helpers
# ============================================================================

def assert_valid_timestamp(timestamp_str):
    """Assert that timestamp string is valid ISO format"""
    try:
        datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        return True
    except (ValueError, AttributeError):
        return False


def assert_valid_sentiment(sentiment_data):
    """Assert that sentiment data has required fields"""
    assert "sentiment" in sentiment_data
    assert sentiment_data["sentiment"] in ["bullish", "bearish", "neutral", "positive", "negative"]
    assert "sentiment_score" in sentiment_data
    assert -1 <= sentiment_data["sentiment_score"] <= 1


def assert_valid_whale_transaction(tx_data):
    """Assert that whale transaction data is valid"""
    required_fields = ["hash", "symbol", "amount", "value_usd", "timestamp"]
    for field in required_fields:
        assert field in tx_data
    assert tx_data["value_usd"] > 0
    assert tx_data["amount"] > 0


# ============================================================================
# Pytest Hooks
# ============================================================================

@pytest.fixture(autouse=True)
def reset_singleton_collectors():
    """Reset any singleton collector instances between tests"""
    # This prevents state leakage between tests
    yield
    # Cleanup code here if needed


# ============================================================================
# Logging Configuration
# ============================================================================

@pytest.fixture(autouse=True)
def configure_test_logging(caplog):
    """Configure logging for tests"""
    import logging
    caplog.set_level(logging.INFO)
    return caplog
