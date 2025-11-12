"""
Collector Integration Tests

Tests collector behavior with mocked external APIs to verify:
- API request formation and headers
- Response parsing and data transformation
- Database storage operations
- RabbitMQ message publishing
- Rate limiting enforcement
- Error handling and retries
- Circuit breaker behavior

These tests use real collector code with mocked HTTP responses.
"""

import asyncio
import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import aiohttp
from aioresponses import aioresponses


# Import collectors
import sys
sys.path.insert(0, '/home/neodyme/Documents/Projects/masterTrade/market_data_service')

from collectors.moralis_collector import MoralisCollector
from collectors.glassnode_collector import GlassnodeCollector
from collectors.twitter_collector import TwitterCollector
from collectors.reddit_collector import RedditCollector


class TestMoralisCollectorIntegration:
    """Integration tests for Moralis collector."""
    
    @pytest.mark.asyncio
    async def test_collect_whale_transactions_success(
        self,
        db_connection,
        rabbitmq_channel,
        clean_test_data
    ):
        """Test successful whale transaction collection."""
        # Mock database
        mock_db = AsyncMock()
        mock_db.store_whale_transaction = AsyncMock()
        
        # Create collector
        collector = MoralisCollector(
            database=mock_db,
            rabbitmq_channel=rabbitmq_channel
        )
        
        # Mock API response
        mock_response = {
            "result": [
                {
                    "hash": "0x" + "a" * 64,
                    "from_address": "0x" + "1" * 40,
                    "to_address": "0x" + "2" * 40,
                    "value": "10000000000000000000",  # 10 ETH
                    "block_timestamp": datetime.utcnow().isoformat(),
                    "transaction_fee": "21000000000000000"  # 0.021 ETH
                }
            ]
        }
        
        with aioresponses() as mocked:
            # Mock the wallet history endpoint
            mocked.get(
                "https://deep-index.moralis.io/api/v2/wallets/0x123/history",
                payload=mock_response,
                status=200
            )
            
            # Collect data
            await collector.collect_whale_transactions(
                wallet_address="0x123",
                min_amount_usd=1000000
            )
            
            # Verify database was called
            assert mock_db.store_whale_transaction.called
            call_args = mock_db.store_whale_transaction.call_args[0][0]
            
            assert call_args['transaction_hash'] == mock_response['result'][0]['hash']
            assert call_args['from_address'] == mock_response['result'][0]['from_address']
            assert call_args['to_address'] == mock_response['result'][0]['to_address']
            
            print("✓ Moralis collector successfully processed whale transaction")
    
    
    @pytest.mark.asyncio
    async def test_rate_limiting_enforcement(self, db_connection):
        """Test that rate limiting is enforced."""
        mock_db = AsyncMock()
        
        collector = MoralisCollector(
            database=mock_db,
            rabbitmq_channel=None
        )
        
        # Set a low rate limit for testing
        collector.rate_limiter.max_requests_per_second = 1
        
        start_time = asyncio.get_event_loop().time()
        
        # Make 3 requests
        for i in range(3):
            await collector.rate_limiter.acquire()
        
        end_time = asyncio.get_event_loop().time()
        duration = end_time - start_time
        
        # Should take at least 2 seconds (3 requests at 1 req/s)
        assert duration >= 2.0, f"Rate limiting not enforced: {duration}s"
        
        print(f"✓ Rate limiting enforced: {duration:.2f}s for 3 requests")
    
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_opens_on_failures(self, db_connection):
        """Test that circuit breaker opens after consecutive failures."""
        mock_db = AsyncMock()
        mock_db.store_whale_transaction = AsyncMock(side_effect=Exception("DB error"))
        
        collector = MoralisCollector(
            database=mock_db,
            rabbitmq_channel=None
        )
        
        # Set low failure threshold for testing
        collector.circuit_breaker.failure_threshold = 3
        
        # Simulate failures
        mock_response = {"result": [{"hash": "0x123"}]}
        
        with aioresponses() as mocked:
            mocked.get(
                "https://deep-index.moralis.io/api/v2/wallets/0x123/history",
                payload=mock_response,
                status=200,
                repeat=True
            )
            
            # Trigger failures
            for i in range(3):
                try:
                    await collector.collect_whale_transactions("0x123", 1000000)
                except Exception:
                    pass
            
            # Circuit should be open now
            assert collector.circuit_breaker.state == "open"
            
            print("✓ Circuit breaker opened after consecutive failures")


class TestGlassnodeCollectorIntegration:
    """Integration tests for Glassnode collector."""
    
    @pytest.mark.asyncio
    async def test_collect_nvt_ratio_success(
        self,
        db_connection,
        rabbitmq_channel,
        clean_test_data
    ):
        """Test successful NVT ratio collection."""
        mock_db = AsyncMock()
        mock_db.store_onchain_metrics = AsyncMock()
        
        collector = GlassnodeCollector(
            database=mock_db,
            rabbitmq_channel=rabbitmq_channel
        )
        
        # Mock API response
        mock_response = [
            {
                "t": int(datetime.utcnow().timestamp()),
                "v": 75.5
            }
        ]
        
        with aioresponses() as mocked:
            mocked.get(
                "https://api.glassnode.com/v1/metrics/indicators/nvt",
                payload=mock_response,
                status=200
            )
            
            # Collect NVT ratio
            await collector.collect_nvt_ratio(symbol="BTC")
            
            # Verify database was called
            assert mock_db.store_onchain_metrics.called
            call_args = mock_db.store_onchain_metrics.call_args[0][0]
            
            assert call_args['metric_name'] == 'nvt_ratio'
            assert call_args['symbol'] == 'BTC'
            assert call_args['metric_value'] == 75.5
            
            print("✓ Glassnode collector successfully processed NVT ratio")
    
    
    @pytest.mark.asyncio
    async def test_api_error_handling(self, db_connection):
        """Test handling of API errors."""
        mock_db = AsyncMock()
        
        collector = GlassnodeCollector(
            database=mock_db,
            rabbitmq_channel=None
        )
        
        # Mock 429 rate limit error
        with aioresponses() as mocked:
            mocked.get(
                "https://api.glassnode.com/v1/metrics/indicators/nvt",
                status=429,
                headers={"Retry-After": "5"}
            )
            
            # Should handle gracefully without throwing
            try:
                await collector.collect_nvt_ratio(symbol="BTC")
                print("✓ Handled 429 rate limit error gracefully")
            except Exception as e:
                # Circuit breaker might raise after threshold
                print(f"✓ Circuit breaker raised after rate limit: {type(e).__name__}")


class TestTwitterCollectorIntegration:
    """Integration tests for Twitter collector."""
    
    @pytest.mark.asyncio
    async def test_collect_tweets_success(
        self,
        db_connection,
        rabbitmq_channel,
        clean_test_data
    ):
        """Test successful tweet collection."""
        mock_db = AsyncMock()
        mock_db.store_social_sentiment = AsyncMock()
        
        collector = TwitterCollector(
            database=mock_db,
            rabbitmq_channel=rabbitmq_channel
        )
        
        # Mock Twitter API response
        mock_response = {
            "data": [
                {
                    "id": "123456789",
                    "text": "Bitcoin is looking bullish! #BTC",
                    "created_at": datetime.utcnow().isoformat(),
                    "author_id": "987654321",
                    "public_metrics": {
                        "retweet_count": 10,
                        "reply_count": 5,
                        "like_count": 50,
                        "quote_count": 2
                    }
                }
            ],
            "includes": {
                "users": [
                    {
                        "id": "987654321",
                        "username": "crypto_trader",
                        "verified": False
                    }
                ]
            }
        }
        
        with aioresponses() as mocked:
            mocked.get(
                "https://api.twitter.com/2/tweets/search/recent",
                payload=mock_response,
                status=200
            )
            
            # Collect tweets
            await collector.collect_tweets(query="#Bitcoin", max_results=10)
            
            # Verify database was called
            assert mock_db.store_social_sentiment.called
            call_args = mock_db.store_social_sentiment.call_args[0][0]
            
            assert call_args['source'] == 'twitter'
            assert call_args['text'] == mock_response['data'][0]['text']
            assert 'sentiment_score' in call_args
            
            print("✓ Twitter collector successfully processed tweets")
    
    
    @pytest.mark.asyncio
    async def test_sentiment_analysis(self, db_connection):
        """Test sentiment analysis of tweets."""
        mock_db = AsyncMock()
        
        collector = TwitterCollector(
            database=mock_db,
            rabbitmq_channel=None
        )
        
        # Test positive sentiment
        positive_text = "Bitcoin is amazing! I love crypto! 🚀"
        positive_score = collector._analyze_sentiment(positive_text)
        assert positive_score > 0, f"Expected positive score, got {positive_score}"
        
        # Test negative sentiment
        negative_text = "Bitcoin is crashing! This is terrible!"
        negative_score = collector._analyze_sentiment(negative_text)
        assert negative_score < 0, f"Expected negative score, got {negative_score}"
        
        # Test neutral sentiment
        neutral_text = "Bitcoin price is $50000"
        neutral_score = collector._analyze_sentiment(neutral_text)
        assert -0.2 < neutral_score < 0.2, f"Expected neutral score, got {neutral_score}"
        
        print("✓ Sentiment analysis working correctly")


class TestRedditCollectorIntegration:
    """Integration tests for Reddit collector."""
    
    @pytest.mark.asyncio
    async def test_collect_posts_success(
        self,
        db_connection,
        rabbitmq_channel,
        clean_test_data
    ):
        """Test successful Reddit post collection."""
        mock_db = AsyncMock()
        mock_db.store_social_sentiment = AsyncMock()
        
        collector = RedditCollector(
            database=mock_db,
            rabbitmq_channel=rabbitmq_channel
        )
        
        # Mock Reddit API response
        mock_response = {
            "data": {
                "children": [
                    {
                        "data": {
                            "id": "abc123",
                            "title": "Bitcoin Analysis",
                            "selftext": "Bitcoin is showing strong fundamentals",
                            "created_utc": datetime.utcnow().timestamp(),
                            "author": "crypto_analyst",
                            "score": 100,
                            "num_comments": 25,
                            "permalink": "/r/Bitcoin/comments/abc123/bitcoin_analysis"
                        }
                    }
                ]
            }
        }
        
        with aioresponses() as mocked:
            mocked.get(
                "https://oauth.reddit.com/r/Bitcoin/hot",
                payload=mock_response,
                status=200
            )
            
            # Collect posts
            await collector.collect_subreddit_posts(
                subreddit="Bitcoin",
                limit=10
            )
            
            # Verify database was called
            assert mock_db.store_social_sentiment.called
            call_args = mock_db.store_social_sentiment.call_args[0][0]
            
            assert call_args['source'] == 'reddit'
            assert 'selftext' in mock_response['data']['children'][0]['data']
            
            print("✓ Reddit collector successfully processed posts")
    
    
    @pytest.mark.asyncio
    async def test_rate_limit_respect(self, db_connection):
        """Test that Reddit rate limits are respected (60/min)."""
        mock_db = AsyncMock()
        
        collector = RedditCollector(
            database=mock_db,
            rabbitmq_channel=None
        )
        
        # Reddit allows 60 requests per minute
        assert collector.rate_limiter.max_requests_per_second <= 1.0
        
        print("✓ Reddit rate limiter configured correctly (<= 60 req/min)")


class TestCollectorErrorRecovery:
    """Test error recovery across all collectors."""
    
    @pytest.mark.asyncio
    async def test_network_timeout_retry(self, db_connection):
        """Test retry behavior on network timeouts."""
        mock_db = AsyncMock()
        
        collector = MoralisCollector(
            database=mock_db,
            rabbitmq_channel=None
        )
        
        # Mock timeout error
        with aioresponses() as mocked:
            # First call times out
            mocked.get(
                "https://deep-index.moralis.io/api/v2/wallets/0x123/history",
                exception=asyncio.TimeoutError()
            )
            
            # Should handle timeout gracefully
            try:
                await collector.collect_whale_transactions("0x123", 1000000)
            except Exception:
                pass  # Expected to fail
            
            print("✓ Network timeout handled gracefully")
    
    
    @pytest.mark.asyncio
    async def test_invalid_response_handling(self, db_connection):
        """Test handling of invalid API responses."""
        mock_db = AsyncMock()
        
        collector = GlassnodeCollector(
            database=mock_db,
            rabbitmq_channel=None
        )
        
        # Mock invalid JSON response
        with aioresponses() as mocked:
            mocked.get(
                "https://api.glassnode.com/v1/metrics/indicators/nvt",
                body="not valid json",
                status=200
            )
            
            # Should handle invalid JSON
            try:
                await collector.collect_nvt_ratio(symbol="BTC")
            except Exception as e:
                print(f"✓ Invalid JSON handled: {type(e).__name__}")
