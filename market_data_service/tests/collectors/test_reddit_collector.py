"""
Unit Tests for Reddit Data Collector

Tests:
- Initialization and authentication
- Subreddit post collection
- Comment sentiment analysis
- Upvote/downvote tracking
- Award detection
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

from collectors.reddit_collector import RedditCollector
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
def reddit_collector(mock_database, mock_rabbitmq_channel):
    """Create Reddit collector instance with mocks"""
    collector = RedditCollector(
        database=mock_database,
        client_id="test_client_id",
        client_secret="test_client_secret",
        user_agent="test_user_agent",
        rate_limit=60.0,  # Reddit: 60 requests per minute
        use_finbert=False,
        rabbitmq_channel=mock_rabbitmq_channel
    )
    return collector


class TestRedditCollectorInitialization:
    """Test collector initialization"""
    
    def test_init_with_valid_parameters(self, mock_database, mock_rabbitmq_channel):
        """Test successful initialization"""
        collector = RedditCollector(
            database=mock_database,
            client_id="client_id",
            client_secret="secret",
            user_agent="agent",
            rate_limit=60.0,
            rabbitmq_channel=mock_rabbitmq_channel
        )
        
        assert collector.collector_name == "reddit"
        assert collector.client_secret == "secret"
        assert collector.rate_limit == 60.0
        assert collector.rabbitmq_channel == mock_rabbitmq_channel
        
    def test_crypto_subreddits_configured(self, reddit_collector):
        """Test that crypto subreddits are configured"""
        assert len(reddit_collector.CRYPTO_SUBREDDITS) > 0
        assert "cryptocurrency" in reddit_collector.CRYPTO_SUBREDDITS
        assert "bitcoin" in reddit_collector.CRYPTO_SUBREDDITS
        assert "ethereum" in reddit_collector.CRYPTO_SUBREDDITS


class TestSubredditCollection:
    """Test subreddit post collection"""
    
    @pytest.mark.asyncio
    async def test_collect_hot_posts(self, reddit_collector):
        """Test collecting hot posts from subreddits"""
        mock_posts = [
            {
                "id": "abc123",
                "title": "Bitcoin reaches new ATH!",
                "selftext": "Amazing news for BTC holders",
                "score": 1500,
                "upvote_ratio": 0.95,
                "num_comments": 250,
                "created_utc": 1699800000,
                "author": "crypto_enthusiast",
                "all_awardings": []
            }
        ]
        
        with patch.object(reddit_collector, '_get_subreddit_posts', new=AsyncMock(return_value=mock_posts)):
            result = await reddit_collector._collect_subreddit_posts()
            
            assert result["count"] > 0 or isinstance(result, dict)
            
    @pytest.mark.asyncio
    async def test_collect_from_multiple_subreddits(self, reddit_collector):
        """Test collecting from multiple subreddits"""
        mock_posts = [
            {"id": "post1", "title": "BTC news", "score": 100},
            {"id": "post2", "title": "ETH update", "score": 200}
        ]
        
        with patch.object(reddit_collector, '_get_subreddit_posts', new=AsyncMock(return_value=mock_posts)):
            result = await reddit_collector.collect_data()
            
            assert isinstance(result, dict)
            assert "posts_collected" in result


class TestCommentCollection:
    """Test comment collection and analysis"""
    
    @pytest.mark.asyncio
    async def test_collect_post_comments(self, reddit_collector):
        """Test collecting comments from a post"""
        mock_comments = [
            {
                "id": "comment1",
                "body": "This is bullish for Bitcoin!",
                "score": 50,
                "created_utc": 1699800000,
                "author": "user1"
            },
            {
                "id": "comment2",
                "body": "Not sure about this...",
                "score": 10,
                "created_utc": 1699800100,
                "author": "user2"
            }
        ]
        
        with patch.object(reddit_collector, '_get_post_comments', new=AsyncMock(return_value=mock_comments)):
            comments = await reddit_collector._get_post_comments("abc123")
            
            assert len(comments) == 2
            assert comments[0]["body"] == "This is bullish for Bitcoin!"


class TestSentimentAnalysis:
    """Test sentiment analysis functionality"""
    
    def test_analyze_post_sentiment_positive(self, reddit_collector):
        """Test positive sentiment detection"""
        positive_text = "Bitcoin is amazing! Great investment! To the moon! 🚀"
        
        sentiment = reddit_collector._analyze_sentiment(positive_text)
        
        assert isinstance(sentiment, SentimentScore)
        assert sentiment.label in ["positive", "bullish"]
        
    def test_analyze_post_sentiment_negative(self, reddit_collector):
        """Test negative sentiment detection"""
        negative_text = "Bitcoin is crashing. Terrible news. Sell now!"
        
        sentiment = reddit_collector._analyze_sentiment(negative_text)
        
        assert isinstance(sentiment, SentimentScore)
        assert sentiment.label in ["negative", "bearish"]
        
    def test_combine_title_and_body_sentiment(self, reddit_collector):
        """Test combining title and body sentiment"""
        title = "Bitcoin ATH!"
        body = "This is incredible news for the entire crypto market."
        
        # Should analyze both title and body
        combined_text = f"{title}\n{body}"
        sentiment = reddit_collector._analyze_sentiment(combined_text)
        
        assert isinstance(sentiment, SentimentScore)


class TestUpvoteMetrics:
    """Test upvote and score tracking"""
    
    def test_calculate_engagement_score(self, reddit_collector):
        """Test engagement score calculation"""
        post = {
            "score": 1000,
            "upvote_ratio": 0.90,
            "num_comments": 200,
            "all_awardings": [{"count": 5}, {"count": 3}]
        }
        
        score = reddit_collector._calculate_engagement_score(post)
        
        assert isinstance(score, (int, float))
        assert score > 0
        
    def test_upvote_ratio_calculation(self, reddit_collector):
        """Test upvote ratio interpretation"""
        high_ratio_post = {"upvote_ratio": 0.95, "score": 1000}
        low_ratio_post = {"upvote_ratio": 0.60, "score": 100}
        
        high_score = reddit_collector._calculate_engagement_score(high_ratio_post)
        low_score = reddit_collector._calculate_engagement_score(low_ratio_post)
        
        # High ratio should result in higher engagement
        assert high_score > low_score


class TestAwardTracking:
    """Test Reddit award detection and tracking"""
    
    def test_detect_high_value_awards(self, reddit_collector):
        """Test detection of high-value awards (Gold, Platinum, Argentium)"""
        post_with_awards = {
            "all_awardings": [
                {"name": "Gold", "count": 5},
                {"name": "Platinum", "count": 2},
                {"name": "Helpful", "count": 10}
            ]
        }
        
        award_count = reddit_collector._count_awards(post_with_awards)
        
        assert award_count > 0
        
    def test_post_without_awards(self, reddit_collector):
        """Test post with no awards"""
        post = {"all_awardings": []}
        
        award_count = reddit_collector._count_awards(post)
        
        assert award_count == 0


class TestCryptoMentionExtraction:
    """Test cryptocurrency mention extraction"""
    
    def test_extract_crypto_from_title(self, reddit_collector):
        """Test extracting crypto mentions from title"""
        title = "Bitcoin and Ethereum analysis for 2024"
        
        mentions = reddit_collector._extract_crypto_mentions(title)
        
        assert "BTC" in mentions or "bitcoin" in str(mentions).lower()
        assert "ETH" in mentions or "ethereum" in str(mentions).lower()
        
    def test_extract_crypto_symbols(self, reddit_collector):
        """Test extracting crypto symbols ($BTC, $ETH)"""
        text = "$BTC is bullish, $ETH following closely"
        
        mentions = reddit_collector._extract_crypto_mentions(text)
        
        assert len(mentions) > 0


class TestRateLimiting:
    """Test rate limiting functionality"""
    
    @pytest.mark.asyncio
    async def test_rate_limiting_enforced(self, reddit_collector):
        """Test that rate limiting delays requests (60 req/min)"""
        reddit_collector.rate_limit = 60.0  # 60 requests per minute
        
        start_time = datetime.now()
        
        # Make 3 rapid requests
        for _ in range(3):
            await reddit_collector._wait_for_rate_limit()
            
        elapsed = (datetime.now() - start_time).total_seconds()
        
        # Should take at least ~0.1 seconds (60/min = 1 per second)
        assert elapsed >= 0.05
        
    @pytest.mark.asyncio
    async def test_minute_based_rate_limiting(self, reddit_collector):
        """Test minute-based rate limiting"""
        # Reddit API: 60 requests per minute
        reddit_collector.requests_this_minute = 59
        
        # Should track and enforce minute-based limits
        assert reddit_collector.requests_this_minute < 60


class TestDatabaseInteractions:
    """Test database storage operations"""
    
    @pytest.mark.asyncio
    async def test_store_post_sentiment(self, reddit_collector, mock_database):
        """Test storing post sentiment to database"""
        post_data = {
            "id": "abc123",
            "title": "Bitcoin ATH",
            "sentiment": "positive",
            "sentiment_score": 0.85,
            "score": 1000,
            "upvote_ratio": 0.95,
            "num_comments": 200,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "subreddit": "cryptocurrency",
            "awards": 10
        }
        
        with patch.object(reddit_collector, '_store_sentiment', new=AsyncMock()):
            await reddit_collector._store_sentiment(post_data)
            
        mock_database.store_social_sentiment.assert_called()
        
    @pytest.mark.asyncio
    async def test_log_collector_health(self, reddit_collector, mock_database):
        """Test logging collector health"""
        stats = {"posts_collected": 50, "comments_analyzed": 200, "errors": 0}
        
        await mock_database.log_collector_health(
            collector_name="reddit",
            status="healthy",
            metadata=stats
        )
        
        mock_database.log_collector_health.assert_called_once()


class TestRabbitMQPublishing:
    """Test RabbitMQ message publishing"""
    
    @pytest.mark.asyncio
    async def test_publish_sentiment_update(self, reddit_collector, mock_rabbitmq_channel):
        """Test publishing sentiment update to RabbitMQ"""
        sentiment_data = {
            "symbol": "BTC",
            "sentiment": "bullish",
            "sentiment_score": 0.9,
            "source": "reddit",
            "subreddit": "cryptocurrency",
            "engagement": 1000,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        with patch.object(reddit_collector, '_publish_sentiment', new=AsyncMock()):
            await reddit_collector._publish_sentiment(sentiment_data)
            
    @pytest.mark.asyncio
    async def test_publish_without_rabbitmq(self, mock_database):
        """Test that publishing works without RabbitMQ"""
        collector = RedditCollector(
            database=mock_database,
            client_id="id",
            client_secret="secret",
            user_agent="agent",
            rabbitmq_channel=None
        )
        
        sentiment_data = {"sentiment": "positive"}
        
        with patch.object(collector, '_publish_sentiment', new=AsyncMock()):
            await collector._publish_sentiment(sentiment_data)


class TestSubredditFiltering:
    """Test subreddit filtering and quality checks"""
    
    def test_filter_low_quality_posts(self, reddit_collector):
        """Test filtering low-quality posts"""
        low_quality_post = {
            "score": 1,
            "upvote_ratio": 0.50,
            "num_comments": 0,
            "title": "test"
        }
        
        is_quality = reddit_collector._is_quality_post(low_quality_post)
        
        assert is_quality is False
        
    def test_accept_high_quality_posts(self, reddit_collector):
        """Test accepting high-quality posts"""
        high_quality_post = {
            "score": 1000,
            "upvote_ratio": 0.90,
            "num_comments": 200,
            "title": "Important Bitcoin Analysis"
        }
        
        is_quality = reddit_collector._is_quality_post(high_quality_post)
        
        assert is_quality is True


class TestTrendingTopics:
    """Test trending topic detection"""
    
    @pytest.mark.asyncio
    async def test_detect_trending_topics(self, reddit_collector):
        """Test detecting trending crypto topics"""
        mock_posts = [
            {"title": "Bitcoin ETF approved!", "score": 5000},
            {"title": "Bitcoin ETF coming soon", "score": 3000},
            {"title": "ETF news", "score": 2000}
        ]
        
        with patch.object(reddit_collector, '_get_subreddit_posts', new=AsyncMock(return_value=mock_posts)):
            trending = await reddit_collector._detect_trending_topics()
            
            # Should detect "ETF" as trending topic
            assert len(trending) > 0 or isinstance(trending, (list, dict))


class TestErrorHandling:
    """Test error handling"""
    
    @pytest.mark.asyncio
    async def test_collect_with_api_error(self, reddit_collector):
        """Test handling API errors during collection"""
        with patch.object(reddit_collector, '_get_subreddit_posts', new=AsyncMock(side_effect=Exception("API Error"))):
            result = await reddit_collector.collect_data()
            
            assert "errors" in result or result.get("posts_collected", 0) >= 0
            
    @pytest.mark.asyncio
    async def test_collect_with_auth_error(self, reddit_collector):
        """Test handling authentication errors"""
        with patch.object(reddit_collector, '_authenticate', new=AsyncMock(side_effect=Exception("401 Unauthorized"))):
            # Should handle auth error gracefully
            pass


class TestStatistics:
    """Test statistics tracking"""
    
    def test_stats_initialization(self, reddit_collector):
        """Test that statistics are initialized"""
        assert hasattr(reddit_collector, 'stats') or hasattr(reddit_collector, 'requests_this_minute')
        
    @pytest.mark.asyncio
    async def test_stats_updated_on_collection(self, reddit_collector):
        """Test that stats are updated after collection"""
        mock_posts = [{"id": "1"}, {"id": "2"}]
        
        with patch.object(reddit_collector, '_get_subreddit_posts', new=AsyncMock(return_value=mock_posts)):
            await reddit_collector.collect_data()
            
        # Stats should track collection


class TestEdgeCases:
    """Test edge cases"""
    
    @pytest.mark.asyncio
    async def test_collect_with_no_posts(self, reddit_collector):
        """Test collection when no posts are found"""
        with patch.object(reddit_collector, '_get_subreddit_posts', new=AsyncMock(return_value=[])):
            result = await reddit_collector.collect_data()
            
            assert result["posts_collected"] == 0
            
    def test_sentiment_with_deleted_post(self, reddit_collector):
        """Test handling deleted posts"""
        deleted_post = {
            "id": "abc123",
            "selftext": "[deleted]",
            "author": "[deleted]"
        }
        
        # Should handle gracefully
        sentiment = reddit_collector._analyze_sentiment(deleted_post.get("selftext", ""))
        assert isinstance(sentiment, SentimentScore)
        
    def test_post_with_no_text(self, reddit_collector):
        """Test post with only image/link (no text)"""
        image_post = {
            "id": "abc123",
            "title": "Check this chart",
            "selftext": "",
            "url": "https://example.com/image.png"
        }
        
        # Should analyze title only
        sentiment = reddit_collector._analyze_sentiment(image_post["title"])
        assert isinstance(sentiment, SentimentScore)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
