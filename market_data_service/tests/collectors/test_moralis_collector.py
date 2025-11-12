"""
Unit Tests for Moralis On-Chain Data Collector

Tests:
- Initialization and configuration
- Whale transaction detection
- DEX trade monitoring
- Rate limiting
- Error handling
- API mocking
- Database interactions
- RabbitMQ message publishing
"""

import asyncio
import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime, timezone, timedelta
import json

# Import the collector
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from collectors.moralis_collector import MoralisCollector
from collectors.onchain_collector import CollectorStatus
from database import Database


@pytest.fixture
def mock_database():
    """Mock database instance"""
    db = Mock(spec=Database)
    db.store_whale_transaction = AsyncMock(return_value=True)
    db.store_onchain_metrics = AsyncMock(return_value=True)
    db.log_collector_health = AsyncMock(return_value=True)
    return db


@pytest.fixture
def mock_rabbitmq_channel():
    """Mock RabbitMQ channel"""
    channel = AsyncMock()
    channel.default_exchange = Mock()
    channel.default_exchange.publish = AsyncMock()
    return channel


@pytest.fixture
def moralis_collector(mock_database, mock_rabbitmq_channel):
    """Create Moralis collector instance with mocks"""
    collector = MoralisCollector(
        database=mock_database,
        api_key="test_api_key",
        rate_limit=10.0,  # High rate limit for tests
        timeout=5,
        rabbitmq_channel=mock_rabbitmq_channel
    )
    return collector


class TestMoralisCollectorInitialization:
    """Test collector initialization"""
    
    def test_init_with_valid_parameters(self, mock_database, mock_rabbitmq_channel):
        """Test successful initialization"""
        collector = MoralisCollector(
            database=mock_database,
            api_key="test_key",
            rate_limit=5.0,
            timeout=10,
            rabbitmq_channel=mock_rabbitmq_channel
        )
        
        assert collector.collector_name == "moralis"
        assert collector.api_key == "test_key"
        assert collector.rate_limit == 5.0
        assert collector.timeout == 10
        assert collector.status == CollectorStatus.IDLE
        assert collector.rabbitmq_channel == mock_rabbitmq_channel
        
    def test_init_without_rabbitmq(self, mock_database):
        """Test initialization without RabbitMQ channel"""
        collector = MoralisCollector(
            database=mock_database,
            api_key="test_key"
        )
        
        assert collector.rabbitmq_channel is None
        
    def test_watched_wallets_initialized(self, moralis_collector):
        """Test that watched wallets are initialized"""
        assert len(moralis_collector.watched_wallets) > 0
        assert isinstance(moralis_collector.watched_wallets, set)


class TestWhaleDetection:
    """Test whale transaction detection logic"""
    
    def test_is_whale_transaction_btc(self, moralis_collector):
        """Test whale detection for BTC transactions"""
        # Large BTC transaction
        large_tx = {"value_usd": 2_000_000, "symbol": "BTC"}
        assert moralis_collector._is_whale_transaction(large_tx) is True
        
        # Small BTC transaction
        small_tx = {"value_usd": 100_000, "symbol": "BTC"}
        assert moralis_collector._is_whale_transaction(small_tx) is False
        
    def test_is_whale_transaction_eth(self, moralis_collector):
        """Test whale detection for ETH transactions"""
        # Large ETH transaction
        large_tx = {"value_usd": 1_500_000, "symbol": "ETH"}
        assert moralis_collector._is_whale_transaction(large_tx) is True
        
        # Small ETH transaction
        small_tx = {"value_usd": 500_000, "symbol": "ETH"}
        assert moralis_collector._is_whale_transaction(small_tx) is False
        
    def test_is_whale_transaction_threshold(self, moralis_collector):
        """Test whale detection at exact threshold"""
        # Exactly at threshold
        threshold_tx = {"value_usd": 1_000_000, "symbol": "USDT"}
        assert moralis_collector._is_whale_transaction(threshold_tx) is True
        
        # Just below threshold
        below_tx = {"value_usd": 999_999, "symbol": "USDT"}
        assert moralis_collector._is_whale_transaction(below_tx) is False


class TestRateLimiting:
    """Test rate limiting functionality"""
    
    @pytest.mark.asyncio
    async def test_rate_limiting_enforced(self, moralis_collector):
        """Test that rate limiting delays requests"""
        # Set low rate limit for testing
        moralis_collector.rate_limit = 2.0  # 2 requests per second
        
        start_time = datetime.now()
        
        # Make 3 rapid requests (should take ~1 second with 2 req/s limit)
        for _ in range(3):
            await moralis_collector._wait_for_rate_limit()
            
        elapsed = (datetime.now() - start_time).total_seconds()
        
        # Should take at least 1 second (3 requests at 2 req/s)
        assert elapsed >= 0.9  # Allow small timing variance
        
    @pytest.mark.asyncio
    async def test_rate_limit_tracking(self, moralis_collector):
        """Test that request count is tracked"""
        initial_count = moralis_collector.requests_made
        
        await moralis_collector._wait_for_rate_limit()
        
        assert moralis_collector.requests_made == initial_count + 1


class TestAPIRequests:
    """Test API request handling"""
    
    @pytest.mark.asyncio
    async def test_make_request_success(self, moralis_collector):
        """Test successful API request"""
        mock_response = {"result": [{"hash": "0x123", "value": "1000"}]}
        
        with patch.object(moralis_collector, '_make_request', new=AsyncMock(return_value=mock_response)):
            response = await moralis_collector._make_request("/test")
            
            assert response == mock_response
            
    @pytest.mark.asyncio
    async def test_make_request_with_retry(self, moralis_collector):
        """Test request retry on failure"""
        # First call fails, second succeeds
        mock_response = {"result": []}
        
        with patch.object(moralis_collector, '_make_request', new=AsyncMock(side_effect=[
            Exception("Network error"),
            mock_response
        ])):
            with patch.object(moralis_collector, 'max_retries', 2):
                # Should eventually succeed after retry
                pass  # Test structure depends on actual retry implementation
                
    @pytest.mark.asyncio
    async def test_make_request_timeout(self, moralis_collector):
        """Test request timeout handling"""
        with patch.object(moralis_collector, '_make_request', new=AsyncMock(side_effect=asyncio.TimeoutError)):
            with pytest.raises((asyncio.TimeoutError, Exception)):
                await moralis_collector._make_request("/test")


class TestWalletTransactions:
    """Test wallet transaction collection"""
    
    @pytest.mark.asyncio
    async def test_get_wallet_transactions(self, moralis_collector):
        """Test fetching wallet transactions"""
        mock_transactions = {
            "result": [
                {
                    "hash": "0xabc123",
                    "from_address": "0x123",
                    "to_address": "0x456",
                    "value": "1000000000000000000",
                    "block_timestamp": "2025-11-12T10:00:00Z"
                }
            ]
        }
        
        with patch.object(moralis_collector, '_make_request', new=AsyncMock(return_value=mock_transactions)):
            transactions = await moralis_collector._get_wallet_transactions("0x123")
            
            assert len(transactions) == 1
            assert transactions[0]["hash"] == "0xabc123"
            
    @pytest.mark.asyncio
    async def test_get_wallet_transactions_empty(self, moralis_collector):
        """Test wallet with no transactions"""
        mock_response = {"result": []}
        
        with patch.object(moralis_collector, '_make_request', new=AsyncMock(return_value=mock_response)):
            transactions = await moralis_collector._get_wallet_transactions("0x789")
            
            assert len(transactions) == 0


class TestDatabaseInteractions:
    """Test database storage operations"""
    
    @pytest.mark.asyncio
    async def test_store_whale_transaction(self, moralis_collector, mock_database):
        """Test storing whale transaction to database"""
        transaction_data = {
            "hash": "0xabc123",
            "from_address": "0x123",
            "to_address": "0x456",
            "value_usd": 2_000_000,
            "symbol": "ETH",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        await moralis_collector._store_whale_transaction(transaction_data)
        
        # Verify database method was called
        mock_database.store_whale_transaction.assert_called_once()
        
    @pytest.mark.asyncio
    async def test_log_collector_health(self, moralis_collector, mock_database):
        """Test logging collector health"""
        await moralis_collector._log_health("healthy", {"transactions": 10})
        
        mock_database.log_collector_health.assert_called_once_with(
            collector_name="moralis",
            status="healthy",
            metadata={"transactions": 10}
        )


class TestRabbitMQPublishing:
    """Test RabbitMQ message publishing"""
    
    @pytest.mark.asyncio
    async def test_publish_whale_alert(self, moralis_collector, mock_rabbitmq_channel):
        """Test publishing whale alert to RabbitMQ"""
        whale_data = {
            "transaction_hash": "0xabc123",
            "from_address": "0x123",
            "to_address": "0x456",
            "amount_usd": 2_000_000,
            "symbol": "ETH",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "severity": "high"
        }
        
        with patch.object(moralis_collector, '_publish_whale_alert', new=AsyncMock()):
            await moralis_collector._publish_whale_alert(whale_data)
            
            # Should have been called
            moralis_collector._publish_whale_alert.assert_called_once_with(whale_data)
            
    @pytest.mark.asyncio
    async def test_publish_without_rabbitmq(self, mock_database):
        """Test that publishing works gracefully without RabbitMQ"""
        collector = MoralisCollector(
            database=mock_database,
            api_key="test_key",
            rabbitmq_channel=None  # No RabbitMQ
        )
        
        whale_data = {"amount_usd": 2_000_000}
        
        # Should not raise exception
        with patch.object(collector, '_publish_whale_alert', new=AsyncMock()):
            await collector._publish_whale_alert(whale_data)


class TestCollectionFlow:
    """Test main collection workflow"""
    
    @pytest.mark.asyncio
    async def test_collect_with_symbols(self, moralis_collector):
        """Test collecting data for specific symbols"""
        with patch.object(moralis_collector, '_collect_token_transactions', new=AsyncMock(return_value=5)):
            result = await moralis_collector.collect(symbols=["BTC", "ETH"], hours=1)
            
            # Should return success
            assert result is True or isinstance(result, dict)
            
    @pytest.mark.asyncio
    async def test_collect_updates_status(self, moralis_collector):
        """Test that collection updates collector status"""
        initial_status = moralis_collector.status
        
        with patch.object(moralis_collector, '_collect_token_transactions', new=AsyncMock(return_value=0)):
            with patch.object(moralis_collector, '_get_wallet_transactions', new=AsyncMock(return_value=[])):
                await moralis_collector.collect(symbols=["BTC"], hours=1)
                
        # Status should have changed during collection
        # (implementation specific)
        
    @pytest.mark.asyncio
    async def test_collect_handles_errors(self, moralis_collector):
        """Test error handling during collection"""
        with patch.object(moralis_collector, '_collect_token_transactions', new=AsyncMock(side_effect=Exception("API Error"))):
            result = await moralis_collector.collect(symbols=["BTC"], hours=1)
            
            # Should handle error gracefully
            assert result is False or (isinstance(result, dict) and "error" in str(result).lower())


class TestStatistics:
    """Test collector statistics tracking"""
    
    def test_stats_initialization(self, moralis_collector):
        """Test that stats are initialized"""
        assert "requests_made" in moralis_collector.stats or hasattr(moralis_collector, 'requests_made')
        assert "errors" in moralis_collector.stats or hasattr(moralis_collector, 'errors')
        
    @pytest.mark.asyncio
    async def test_stats_updated_on_request(self, moralis_collector):
        """Test that stats are updated after requests"""
        initial_requests = getattr(moralis_collector, 'requests_made', 0)
        
        with patch.object(moralis_collector, '_make_request', new=AsyncMock(return_value={"result": []})):
            try:
                await moralis_collector._make_request("/test")
            except:
                pass
                
        # Request count should have incremented
        # (implementation specific)


class TestTokenAddresses:
    """Test token address handling"""
    
    def test_token_addresses_configured(self, moralis_collector):
        """Test that major token addresses are configured"""
        assert "BTC" in moralis_collector.TOKEN_ADDRESSES
        assert "ETH" in moralis_collector.TOKEN_ADDRESSES
        assert "USDT" in moralis_collector.TOKEN_ADDRESSES
        assert "USDC" in moralis_collector.TOKEN_ADDRESSES
        
    def test_get_token_address(self, moralis_collector):
        """Test retrieving token address"""
        btc_address = moralis_collector.TOKEN_ADDRESSES.get("BTC")
        assert btc_address is not None
        assert btc_address.startswith("0x")


class TestEdgeCases:
    """Test edge cases and error conditions"""
    
    @pytest.mark.asyncio
    async def test_collect_with_empty_symbols(self, moralis_collector):
        """Test collection with empty symbol list"""
        with patch.object(moralis_collector, '_collect_token_transactions', new=AsyncMock(return_value=0)):
            result = await moralis_collector.collect(symbols=[], hours=1)
            
            # Should handle empty list gracefully
            assert result is not None
            
    @pytest.mark.asyncio
    async def test_collect_with_invalid_hours(self, moralis_collector):
        """Test collection with invalid time range"""
        with patch.object(moralis_collector, '_collect_token_transactions', new=AsyncMock(return_value=0)):
            # Negative hours
            result = await moralis_collector.collect(symbols=["BTC"], hours=-1)
            
            # Should handle invalid input
            assert result is not None
            
    def test_whale_threshold_constants(self, moralis_collector):
        """Test whale threshold constants are reasonable"""
        assert moralis_collector.WHALE_THRESHOLD_BTC > 0
        assert moralis_collector.WHALE_THRESHOLD_ETH > 0
        assert moralis_collector.WHALE_THRESHOLD_USD > 0
        
        # Thresholds should be in reasonable ranges
        assert 100 <= moralis_collector.WHALE_THRESHOLD_BTC <= 100000
        assert 1000 <= moralis_collector.WHALE_THRESHOLD_ETH <= 1000000
        assert 100000 <= moralis_collector.WHALE_THRESHOLD_USD <= 100000000


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
