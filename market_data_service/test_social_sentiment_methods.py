#!/usr/bin/env python3
"""
Test script for social sentiment database methods.
Tests the new methods added to Database class for social sentiment storage and retrieval.
"""

import asyncio
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from database import Database
from config import Settings
import structlog

logger = structlog.get_logger(__name__)


async def test_social_sentiment_methods():
    """Test all social sentiment database methods."""
    
    # Initialize database
    settings = Settings()
    db = Database()
    
    try:
        await db.connect()
        logger.info("Connected to database")
        
        # Test 1: Store social sentiment (Twitter)
        logger.info("=" * 60)
        logger.info("TEST 1: Store Twitter sentiment")
        twitter_sentiment = {
            "id": "twitter_test_001",
            "symbol": "BTC",
            "source": "twitter",
            "text": "Bitcoin is looking bullish! 🚀 #BTC",
            "sentiment_score": 0.85,
            "sentiment_category": "bullish",
            "author": "crypto_analyst",
            "engagement": {
                "likes": 150,
                "retweets": 45,
                "replies": 12,
                "total": 207
            },
            "is_influencer": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        
        result = await db.store_social_sentiment(twitter_sentiment)
        logger.info("Store Twitter sentiment result", success=result)
        assert result is True, "Failed to store Twitter sentiment"
        
        # Test 2: Store social sentiment (Reddit)
        logger.info("=" * 60)
        logger.info("TEST 2: Store Reddit sentiment")
        reddit_sentiment = {
            "id": "reddit_test_001",
            "symbol": "BTC",
            "source": "reddit",
            "text": "Analysis: BTC might see a correction soon",
            "sentiment_score": -0.45,
            "sentiment_category": "bearish",
            "author": "reddit_trader",
            "engagement": {
                "upvotes": 85,
                "downvotes": 12,
                "comments": 34,
                "awards": 2,
                "total": 133
            },
            "is_influencer": False,
            "subreddit": "CryptoCurrency",
            "timestamp": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(),
        }
        
        result = await db.store_social_sentiment(reddit_sentiment)
        logger.info("Store Reddit sentiment result", success=result)
        assert result is True, "Failed to store Reddit sentiment"
        
        # Test 3: Store another sentiment for diversity
        logger.info("=" * 60)
        logger.info("TEST 3: Store neutral Twitter sentiment")
        neutral_sentiment = {
            "id": "twitter_test_002",
            "symbol": "ETH",
            "source": "twitter",
            "text": "Ethereum gas fees are high today",
            "sentiment_score": 0.05,
            "sentiment_category": "neutral",
            "author": "eth_user",
            "engagement": {
                "likes": 23,
                "retweets": 5,
                "replies": 8,
                "total": 36
            },
            "is_influencer": False,
            "timestamp": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
        }
        
        result = await db.store_social_sentiment(neutral_sentiment)
        logger.info("Store neutral sentiment result", success=result)
        assert result is True, "Failed to store neutral sentiment"
        
        # Test 4: Store aggregated social metrics (LunarCrush)
        logger.info("=" * 60)
        logger.info("TEST 4: Store LunarCrush aggregated metrics")
        lunarcrush_metrics = {
            "id": "lunarcrush_btc_001",
            "symbol": "BTC",
            "source": "lunarcrush",
            "social_volume": 45823,
            "social_sentiment": 0.72,
            "altrank": 1,
            "galaxy_score": 72.5,
            "social_dominance": 35.8,
            "market_dominance": 48.2,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        
        result = await db.store_social_metrics_aggregated(lunarcrush_metrics)
        logger.info("Store LunarCrush metrics result", success=result)
        assert result is True, "Failed to store LunarCrush metrics"
        
        # Test 5: Store ETH metrics for comparison
        logger.info("=" * 60)
        logger.info("TEST 5: Store ETH aggregated metrics")
        eth_metrics = {
            "id": "lunarcrush_eth_001",
            "symbol": "ETH",
            "source": "lunarcrush",
            "social_volume": 28456,
            "social_sentiment": 0.65,
            "altrank": 2,
            "galaxy_score": 68.3,
            "social_dominance": 22.4,
            "market_dominance": 18.7,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        
        result = await db.store_social_metrics_aggregated(eth_metrics)
        logger.info("Store ETH metrics result", success=result)
        assert result is True, "Failed to store ETH metrics"
        
        # Test 6: Retrieve social sentiment for BTC
        logger.info("=" * 60)
        logger.info("TEST 6: Get social sentiment for BTC")
        btc_sentiments = await db.get_social_sentiment(symbol="BTC", hours=24)
        logger.info("Retrieved BTC sentiments", count=len(btc_sentiments))
        assert len(btc_sentiments) > 0, "No BTC sentiments found"
        for sentiment in btc_sentiments:
            logger.info(
                "BTC Sentiment",
                source=sentiment.get("source"),
                category=sentiment.get("sentiment_category"),
                score=sentiment.get("sentiment_score"),
                author=sentiment.get("author"),
            )
        
        # Test 7: Retrieve social sentiment filtered by source
        logger.info("=" * 60)
        logger.info("TEST 7: Get Twitter sentiments only")
        twitter_only = await db.get_social_sentiment(symbol="BTC", hours=24, source="twitter")
        logger.info("Retrieved Twitter sentiments", count=len(twitter_only))
        assert len(twitter_only) > 0, "No Twitter sentiments found"
        assert all(s.get("source") == "twitter" for s in twitter_only), "Non-Twitter data returned"
        
        # Test 8: Retrieve aggregated metrics for BTC
        logger.info("=" * 60)
        logger.info("TEST 8: Get aggregated metrics for BTC")
        btc_metrics = await db.get_social_metrics_aggregated(symbol="BTC", hours=24)
        logger.info("Retrieved BTC metrics", count=len(btc_metrics))
        assert len(btc_metrics) > 0, "No BTC metrics found"
        for metric in btc_metrics:
            logger.info(
                "BTC Metrics",
                source=metric.get("source"),
                altrank=metric.get("altrank"),
                galaxy_score=metric.get("galaxy_score"),
                social_volume=metric.get("social_volume"),
            )
        
        # Test 9: Get trending topics
        logger.info("=" * 60)
        logger.info("TEST 9: Get trending topics")
        trending = await db.get_trending_topics(limit=5)
        logger.info("Retrieved trending topics", count=len(trending))
        for topic in trending:
            logger.info(
                "Trending Topic",
                symbol=topic.get("symbol"),
                mentions=topic.get("mention_count"),
                avg_sentiment=topic.get("avg_sentiment"),
                unique_authors=topic.get("unique_authors"),
                engagement=topic.get("total_engagement"),
            )
        
        # Test 10: Get social sentiment summary for BTC
        logger.info("=" * 60)
        logger.info("TEST 10: Get social sentiment summary for BTC")
        summary = await db.get_social_sentiment_summary(symbol="BTC", hours=24)
        logger.info("Retrieved sentiment summary", data=summary)
        assert summary["symbol"] == "BTC", "Wrong symbol in summary"
        assert "overall" in summary, "Missing overall stats"
        assert "by_source" in summary, "Missing by_source stats"
        
        logger.info(
            "Overall Summary",
            total_posts=summary["overall"]["total_posts"],
            avg_sentiment=summary["overall"]["avg_sentiment"],
            bullish=summary["overall"]["bullish_count"],
            bearish=summary["overall"]["bearish_count"],
            neutral=summary["overall"]["neutral_count"],
        )
        
        for source, stats in summary["by_source"].items():
            logger.info(
                "By Source",
                source=source,
                posts=stats["total_posts"],
                avg_sentiment=stats["avg_sentiment"],
                engagement=stats["total_engagement"],
            )
        
        # Test 11: Test error handling (missing required fields)
        logger.info("=" * 60)
        logger.info("TEST 11: Test error handling with invalid data")
        invalid_sentiment = {
            "id": "invalid_001",
            # Missing symbol, source, timestamp
            "text": "This should fail",
        }
        
        result = await db.store_social_sentiment(invalid_sentiment)
        logger.info("Store invalid sentiment result", success=result)
        assert result is False, "Should have failed with invalid data"
        
        logger.info("=" * 60)
        logger.info("✅ ALL TESTS PASSED!")
        logger.info("=" * 60)
        
        return True
        
    except Exception as e:
        logger.error("Test failed", error=str(e), exc_info=True)
        return False
    
    finally:
        await db.disconnect()
        logger.info("Disconnected from database")


async def main():
    """Run tests."""
    success = await test_social_sentiment_methods()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
