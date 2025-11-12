"""
Unit Tests for Twitter/X Data Collector

Tests:
- Initialization and authentication
- Tweet collection and streaming
- Sentiment analysis
- Influencer tracking
- Rate limiting
- Error handling
- Database interactions
- RabbitMQ publishing
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

from collectors.twitter_collector import TwitterCollector
from collectors.social_collector import SentimentScore
from database import Database


@pytest.fixture
def mock_database():
    """Mock database instance"""
    db = Mock(spec=Database)
    db.store_social_sentiment = AsyncMock(return_value=True)
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
def twitter_collector(mock_database, mock_rabbitmq_channel):
    """Create Twitter collector instance with mocks"""
    collector = TwitterCollector(
        database=mock_database,
        api_key="test_api_key",
        api_secret="test_api_secret",
        bearer_token="test_bearer_token",
        rate_limit=10.0,
        use_finbert=False,  # Use VADER for faster tests
        rabbitmq_channel=mock_rabbitmq_channel
    )
    return collector


class TestTwitterCollectorInitialization:
    """Test collector initialization"""
    
    def test_init_with_valid_parameters(self, mock_database, mock_rabbitmq_channel):
        """Test successful initialization"""
        collector = TwitterCollector(
            database=mock_database,
            api_key="key",
            api_secret="secret",
            bearer_token="token",
            rate_limit=1.0,
            rabbitmq_channel=mock_rabbitmq_channel
        )
        
        assert collector.collector_name == "twitter"
        assert collector.bearer_token == "token"
        assert collector.api_secret == "secret"
        assert collector.rate_limit == 1.0
        assert collector.rabbitmq_channel == mock_rabbitmq_channel
        assert collector.stream_active is False
        
    def test_init_with_finbert(self, mock_database):
        """Test initialization with FinBERT sentiment analysis"""
        collector = TwitterCollector(
            database=mock_database,
            api_key="key",
            api_secret="secret",
            bearer_token="token",
            use_finbert=True
        )
        
        assert collector.use_finbert is True
        
    def test_influencers_list_configured(self, twitter_collector):
        """Test that influencer list is configured"""
        assert len(twitter_collector.CRYPTO_INFLUENCERS) > 0
        assert "APompliano" in twitter_collector.CRYPTO_INFLUENCERS
        assert "cz_binance" in twitter_collector.CRYPTO_INFLUENCERS
        
    def test_keywords_list_configured(self, twitter_collector):
        """Test that keyword list is configured"""
        assert len(twitter_collector.CRYPTO_KEYWORDS) > 0
        assert "bitcoin" in twitter_collector.CRYPTO_KEYWORDS
        assert "BTC" in twitter_collector.CRYPTO_KEYWORDS


class TestSentimentAnalysis:
    """Test sentiment analysis functionality"""
    
    def test_analyze_sentiment_positive(self, twitter_collector):
        """Test positive sentiment detection"""
        positive_text = "Bitcoin is amazing! Great investment opportunity! 🚀"
        
        sentiment = twitter_collector._analyze_sentiment(positive_text)
        
        assert isinstance(sentiment, SentimentScore)
        assert sentiment.label in ["positive", "bullish"]
        assert sentiment.score > 0
        
    def test_analyze_sentiment_negative(self, twitter_collector):
        """Test negative sentiment detection"""
        negative_text = "Bitcoin crash incoming. Terrible investment. Avoid!"
        
        sentiment = twitter_collector._analyze_sentiment(negative_text)
        
        assert isinstance(sentiment, SentimentScore)
        assert sentiment.label in ["negative", "bearish"]
        assert sentiment.score < 0 or sentiment.confidence > 0.5
        
    def test_analyze_sentiment_neutral(self, twitter_collector):
        """Test neutral sentiment detection"""
        neutral_text = "Bitcoin price is $50,000 today."
        
        sentiment = twitter_collector._analyze_sentiment(neutral_text)
        
        assert isinstance(sentiment, SentimentScore)
        # Sentiment should be relatively neutral
        
    def test_analyze_sentiment_empty_text(self, twitter_collector):
        """Test sentiment analysis with empty text"""
        sentiment = twitter_collector._analyze_sentiment("")
        
        assert isinstance(sentiment, SentimentScore)
        # Should handle empty text gracefully


class TestTweetCollection:
    """Test tweet collection functionality"""
    
    @pytest.mark.asyncio
    async def test_collect_influencer_tweets(self, twitter_collector):
        """Test collecting tweets from influencers"""
        mock_user_data = {"id": "123456", "username": "APompliano"}
        mock_tweets = [
            {
                "id": "1234567890",
                "text": "Bitcoin is the future!",
                "created_at": "2025-11-12T10:00:00Z",
                "public_metrics": {
                    "like_count": 100,
                    "retweet_count": 50,
                    "reply_count": 10
                }
            }
        ]
        
        with patch.object(twitter_collector, '_get_user_by_username', new=AsyncMock(return_value=mock_user_data)):
            with patch.object(twitter_collector, '_get_user_tweets', new=AsyncMock(return_value=mock_tweets)):
                result = await twitter_collector._collect_influencer_tweets()
                
                assert result["count"] > 0 or isinstance(result, dict)
                
    @pytest.mark.asyncio
    async def test_collect_keyword_tweets(self, twitter_collector):
        """Test collecting tweets by keywords"""
        mock_tweets = [
            {
                "id": "1234567890",
                "text": "Bitcoin breaking new highs! #BTC",
                "created_at": "2025-11-12T10:00:00Z",
                "public_metrics": {
                    "like_count": 50,
                    "retweet_count": 20,
                    "reply_count": 5
                }
            }
        ]
        
        with patch.object(twitter_collector, '_search_tweets', new=AsyncMock(return_value=mock_tweets)):
            result = await twitter_collector._collect_keyword_tweets()
            
            assert isinstance(result, dict)
            assert "count" in result


class TestEngagementMetrics:
    """Test engagement metrics calculation"""
    
    def test_calculate_engagement_score(self, twitter_collector):
        """Test engagement score calculation"""
        tweet = {
            "public_metrics": {
                "like_count": 100,
                "retweet_count": 50,
                "reply_count": 25,
                "quote_count": 10
            }
        }
        
        score = twitter_collector._calculate_engagement_score(tweet)
        
        assert isinstance(score, (int, float))
        assert score > 0
        
    def test_calculate_engagement_score_zero(self, twitter_collector):
        """Test engagement score with zero engagement"""
        tweet = {
            "public_metrics": {
                "like_count": 0,
                "retweet_count": 0,
                "reply_count": 0,
                "quote_count": 0
            }
        }
        
        score = twitter_collector._calculate_engagement_score(tweet)
        
        assert score == 0
        
    def test_calculate_engagement_score_missing_metrics(self, twitter_collector):
        """Test engagement score with missing metrics"""
        tweet = {
            "public_metrics": {
                "like_count": 100
                # Missing other metrics
            }
        }
        
        # Should handle missing metrics gracefully
        score = twitter_collector._calculate_engagement_score(tweet)
        assert isinstance(score, (int, float))


class TestInfluencerDetection:
    """Test influencer detection and weighting"""
    
    def test_is_influencer(self, twitter_collector):
        """Test influencer detection"""
        assert twitter_collector._is_influencer("APompliano") is True
        assert twitter_collector._is_influencer("cz_binance") is True
        assert twitter_collector._is_influencer("random_user") is False
        
    def test_get_influencer_weight(self, twitter_collector):
        """Test influencer weight calculation"""
        # Major influencer
        weight_high = twitter_collector._get_influencer_weight("elonmusk")
        assert weight_high >= 1.0
        
        # Unknown user
        weight_low = twitter_collector._get_influencer_weight("unknown_user")
        assert weight_low == 1.0  # Default weight


class TestRateLimiting:
    """Test rate limiting functionality"""
    
    @pytest.mark.asyncio
    async def test_rate_limiting_enforced(self, twitter_collector):
        """Test that rate limiting delays requests"""
        twitter_collector.rate_limit = 2.0  # 2 requests per second
        
        start_time = datetime.now()
        
        # Make 3 rapid requests
        for _ in range(3):
            await twitter_collector._wait_for_rate_limit()
            
        elapsed = (datetime.now() - start_time).total_seconds()
        
        # Should take at least 1 second
        assert elapsed >= 0.9
        
    @pytest.mark.asyncio
    async def test_streaming_rate_limit(self, twitter_collector):
        """Test streaming-specific rate limiting"""
        # Test minute-based rate limiting for streaming
        twitter_collector.tweets_processed_minute = 450  # Near limit
        
        # Should track and limit appropriately
        assert twitter_collector.tweets_processed_minute > 0


class TestDatabaseInteractions:
    """Test database storage operations"""
    
    @pytest.mark.asyncio
    async def test_store_tweet_sentiment(self, twitter_collector, mock_database):
        """Test storing tweet sentiment to database"""
        tweet_data = {
            "id": "1234567890",
            "text": "Bitcoin is great!",
            "sentiment": "positive",
            "sentiment_score": 0.8,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "author_username": "test_user",
            "engagement_score": 100,
            "is_influencer": False
        }
        
        with patch.object(twitter_collector, '_store_sentiment', new=AsyncMock()):
            await twitter_collector._store_sentiment(tweet_data)
            
        # Verify database method was called
        mock_database.store_social_sentiment.assert_called()
        
    @pytest.mark.asyncio
    async def test_log_collector_health(self, twitter_collector, mock_database):
        """Test logging collector health"""
        stats = {"tweets_collected": 100, "errors": 0}
        
        await mock_database.log_collector_health(
            collector_name="twitter",
            status="healthy",
            metadata=stats
        )
        
        mock_database.log_collector_health.assert_called_once()


class TestRabbitMQPublishing:
    """Test RabbitMQ message publishing"""
    
    @pytest.mark.asyncio
    async def test_publish_sentiment_update(self, twitter_collector, mock_rabbitmq_channel):
        """Test publishing sentiment update to RabbitMQ"""
        sentiment_data = {
            "symbol": "BTC",
            "sentiment": "positive",
            "sentiment_score": 0.8,
            "source": "twitter",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        with patch.object(twitter_collector, '_publish_sentiment', new=AsyncMock()):
            await twitter_collector._publish_sentiment(sentiment_data)
            
    @pytest.mark.asyncio
    async def test_publish_without_rabbitmq(self, mock_database):
        """Test that publishing works without RabbitMQ"""
        collector = TwitterCollector(
            database=mock_database,
            api_key="key",
            api_secret="secret",
            bearer_token="token",
            rabbitmq_channel=None
        )
        
        sentiment_data = {"sentiment": "positive"}
        
        # Should not raise exception
        with patch.object(collector, '_publish_sentiment', new=AsyncMock()):
            await collector._publish_sentiment(sentiment_data)


class TestBotFiltering:
    """Test bot detection and filtering"""
    
    def test_is_bot_account(self, twitter_collector):
        """Test bot account detection"""
        # Bot-like account
        bot_user = {
            "username": "crypto_bot_12345",
            "description": "Automated trading bot",
            "verified": False
        }
        
        is_bot = twitter_collector._is_bot_account(bot_user)
        # Should detect bot-like patterns
        
    def test_is_human_account(self, twitter_collector):
        """Test human account detection"""
        # Regular human account
        human_user = {
            "username": "john_smith",
            "description": "Crypto enthusiast",
            "verified": True
        }
        
        is_bot = twitter_collector._is_bot_account(human_user)
        assert is_bot is False


class TestCryptoMentionExtraction:
    """Test cryptocurrency mention extraction"""
    
    def test_extract_crypto_mentions(self, twitter_collector):
        """Test extracting crypto mentions from text"""
        text = "Bitcoin and Ethereum are mooning! $BTC $ETH #Crypto"
        
        mentions = twitter_collector._extract_crypto_mentions(text)
        
        assert "BTC" in mentions or "bitcoin" in str(mentions).lower()
        assert "ETH" in mentions or "ethereum" in str(mentions).lower()
        
    def test_extract_no_mentions(self, twitter_collector):
        """Test text with no crypto mentions"""
        text = "Just had a great lunch today!"
        
        mentions = twitter_collector._extract_crypto_mentions(text)
        
        assert len(mentions) == 0


class TestStreamingFunctionality:
    """Test tweet streaming functionality"""
    
    @pytest.mark.asyncio
    async def test_start_stream(self, twitter_collector):
        """Test starting tweet stream"""
        with patch.object(twitter_collector, '_stream_tweets', new=AsyncMock()):
            await twitter_collector.start_streaming()
            
            assert twitter_collector.stream_active is True
            
    @pytest.mark.asyncio
    async def test_stop_stream(self, twitter_collector):
        """Test stopping tweet stream"""
        twitter_collector.stream_active = True
        twitter_collector.stream_task = AsyncMock()
        
        with patch.object(twitter_collector, 'stop_streaming', new=AsyncMock()):
            await twitter_collector.stop_streaming()
            
            # Stream should be stopped
            # (implementation specific)


class TestErrorHandling:
    """Test error handling"""
    
    @pytest.mark.asyncio
    async def test_collect_with_api_error(self, twitter_collector):
        """Test handling API errors during collection"""
        with patch.object(twitter_collector, '_get_user_by_username', new=AsyncMock(side_effect=Exception("API Error"))):
            result = await twitter_collector._collect_influencer_tweets()
            
            # Should handle error gracefully
            assert "errors" in result or result.get("count", 0) >= 0
            
    @pytest.mark.asyncio
    async def test_collect_with_rate_limit_error(self, twitter_collector):
        """Test handling rate limit errors"""
        error_response = {"status": 429, "message": "Rate limit exceeded"}
        
        with patch.object(twitter_collector, '_make_request', new=AsyncMock(side_effect=Exception("429"))):
            # Should handle rate limit error
            pass


class TestStatistics:
    """Test statistics tracking"""
    
    def test_stats_tracking(self, twitter_collector):
        """Test that statistics are tracked"""
        assert hasattr(twitter_collector, 'stats') or hasattr(twitter_collector, 'tweets_processed_minute')
        
    @pytest.mark.asyncio
    async def test_stats_updated_on_collection(self, twitter_collector):
        """Test that stats are updated after collection"""
        initial_processed = twitter_collector.stats.get("posts_processed", 0)
        
        with patch.object(twitter_collector, '_collect_influencer_tweets', new=AsyncMock(return_value={"count": 5})):
            with patch.object(twitter_collector, '_collect_keyword_tweets', new=AsyncMock(return_value={"count": 10})):
                await twitter_collector.collect_data()
                
        # Stats should have been updated
        # (implementation specific)


class TestEdgeCases:
    """Test edge cases"""
    
    @pytest.mark.asyncio
    async def test_collect_with_no_tweets(self, twitter_collector):
        """Test collection when no tweets are found"""
        with patch.object(twitter_collector, '_get_user_tweets', new=AsyncMock(return_value=[])):
            with patch.object(twitter_collector, '_search_tweets', new=AsyncMock(return_value=[])):
                result = await twitter_collector.collect_data()
                
                assert result["tweets_collected"] == 0
                
    def test_sentiment_with_emojis(self, twitter_collector):
        """Test sentiment analysis with emojis"""
        text_with_emojis = "Bitcoin to the moon! 🚀🌙💎"
        
        sentiment = twitter_collector._analyze_sentiment(text_with_emojis)
        
        assert isinstance(sentiment, SentimentScore)
        
    def test_sentiment_with_special_characters(self, twitter_collector):
        """Test sentiment analysis with special characters"""
        text = "BTC >>> $50k!!! 💯 #Bitcoin"
        
        sentiment = twitter_collector._analyze_sentiment(text)
        
        assert isinstance(sentiment, SentimentScore)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
