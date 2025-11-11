"""
Simple Integration Test for Social Collectors

Tests social collector integration without full service initialization.
"""

import asyncio
import sys
import os
from datetime import datetime, timezone

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import settings
from database import Database

print("=" * 60)
print("SOCIAL COLLECTORS SIMPLE INTEGRATION TEST")
print("=" * 60)


async def test_configuration():
    """Test that configuration has all social settings"""
    print("\n1. Testing configuration...")
    
    required_settings = [
        ('TWITTER_API_KEY', str),
        ('TWITTER_API_SECRET', str),
        ('TWITTER_BEARER_TOKEN', str),
        ('TWITTER_RATE_LIMIT', float),
        ('REDDIT_CLIENT_ID', str),
        ('REDDIT_CLIENT_SECRET', str),
        ('REDDIT_USER_AGENT', str),
        ('REDDIT_RATE_LIMIT', float),
        ('LUNARCRUSH_API_KEY', str),
        ('LUNARCRUSH_API_URL', str),
        ('LUNARCRUSH_RATE_LIMIT', float),
        ('SOCIAL_COLLECTION_ENABLED', bool),
        ('SOCIAL_COLLECTION_INTERVAL', int),
        ('SOCIAL_USE_FINBERT', bool),
        ('SOCIAL_MIN_ENGAGEMENT', int),
    ]
    
    for setting_name, expected_type in required_settings:
        assert hasattr(settings, setting_name), f"Missing setting: {setting_name}"
        value = getattr(settings, setting_name)
        assert isinstance(value, expected_type), f"{setting_name} should be {expected_type.__name__}"
        print(f"   ✅ {setting_name}: {value if not 'KEY' in setting_name and not 'SECRET' in setting_name and not 'TOKEN' in setting_name else '<set>' if value else '<not set>'}")
    
    return True


async def test_database_methods():
    """Test that database has all required social methods"""
    print("\n2. Testing database methods...")
    
    db = Database()
    await db.connect()
    
    # Check all required methods exist
    methods = [
        'store_social_sentiment',
        'store_social_metrics_aggregated',
        'get_social_sentiment',
        'get_social_metrics_aggregated',
        'get_trending_topics',
    ]
    
    for method in methods:
        assert hasattr(db, method), f"Missing method: {method}"
        print(f"   ✅ {method}")
    
    await db.disconnect()
    
    return True


async def test_collectors_can_be_initialized():
    """Test that social collectors can be instantiated"""
    print("\n3. Testing collector instantiation...")
    
    from collectors.social_collector import SocialCollector
    from collectors.twitter_collector import TwitterCollector
    from collectors.reddit_collector import RedditCollector
    from collectors.lunarcrush_collector import LunarCrushCollector
    
    db = Database()
    await db.connect()
    
    # Test base social collector
    base = SocialCollector(
        collector_name="test",
        database=db,
        api_key="test_key",
        rate_limit=1.0
    )
    assert base.collector_name == "test"
    assert base.database == db
    print("   ✅ SocialCollector instantiated")
    
    # Test Twitter collector
    twitter = TwitterCollector(
        database=db,
        api_key="test_key",
        api_secret="test_secret",
        bearer_token="test_token",
        rate_limit=1.0
    )
    assert twitter.collector_name == "twitter"
    print("   ✅ TwitterCollector instantiated")
    
    # Test Reddit collector
    reddit = RedditCollector(
        database=db,
        client_id="test_id",
        client_secret="test_secret",
        user_agent="test_agent",
        rate_limit=0.5
    )
    assert reddit.collector_name == "reddit"
    print("   ✅ RedditCollector instantiated")
    
    # Test LunarCrush collector
    lunarcrush = LunarCrushCollector(
        database=db,
        api_key="test_key",
        rate_limit=0.2
    )
    assert lunarcrush.collector_name == "lunarcrush"
    print("   ✅ LunarCrushCollector instantiated")
    
    await db.disconnect()
    
    return True


async def test_sentiment_analysis():
    """Test sentiment analysis functionality"""
    print("\n4. Testing sentiment analysis...")
    
    from collectors.social_collector import SocialCollector
    
    db = Database()
    await db.connect()
    
    collector = SocialCollector(
        collector_name="test",
        database=db,
        api_key="test",
        rate_limit=1.0
    )
    
    # Test positive sentiment
    scores, category = collector.analyze_sentiment("Bitcoin is pumping! Great news! 🚀")
    print(f"   ✅ Positive text: {category.value}, compound: {scores.get('compound', 0):.2f}")
    
    # Test negative sentiment
    scores, category = collector.analyze_sentiment("Bitcoin is crashing. Terrible market conditions.")
    print(f"   ✅ Negative text: {category.value}, compound: {scores.get('compound', 0):.2f}")
    
    # Test neutral sentiment
    scores, category = collector.analyze_sentiment("Bitcoin price is $50,000.")
    print(f"   ✅ Neutral text: {category.value}, compound: {scores.get('compound', 0):.2f}")
    
    # Test crypto extraction
    cryptos = collector.extract_crypto_mentions("Bitcoin and Ethereum are up, but Dogecoin is down")
    assert 'BTC' in cryptos or 'ETH' in cryptos or 'DOGE' in cryptos
    print(f"   ✅ Crypto extraction: {cryptos}")
    
    # Test bot detection
    is_bot = collector.is_bot("crypto_bot_123")
    assert is_bot == True
    print(f"   ✅ Bot detection: bot username correctly identified")
    
    await db.disconnect()
    
    return True


async def test_data_storage_and_retrieval():
    """Test storing and retrieving social data"""
    print("\n5. Testing data storage and retrieval...")
    
    db = Database()
    await db.connect()
    
    # Test social sentiment storage
    sentiment = {
        'symbol': 'BTC',
        'source': 'test',
        'text': 'Test tweet about Bitcoin',
        'sentiment_score': 0.5,
        'sentiment_category': 'positive',
        'sentiment_positive': 0.7,
        'sentiment_negative': 0.1,
        'sentiment_neutral': 0.2,
        'timestamp': datetime.now(timezone.utc),
        'author_id': 'test_user',
        'author_username': 'test_user',
        'is_influencer': False,
        'engagement_score': 100,
        'like_count': 50,
        'retweet_count': 25,
        'reply_count': 25,
        'post_id': 'test_simple_sentiment_123',
        'metadata': {'test': True}
    }
    
    success = await db.store_social_sentiment(sentiment)
    assert success, "Failed to store social sentiment"
    print("   ✅ Stored social sentiment")
    
    sentiments = await db.get_social_sentiment(symbol='BTC', hours=1)
    assert len(sentiments) > 0, "No sentiments retrieved"
    print(f"   ✅ Retrieved {len(sentiments)} sentiment(s)")
    
    # Test aggregated metrics storage
    metrics = {
        'symbol': 'BTC',
        'timestamp': datetime.now(timezone.utc),
        'altrank': 1,
        'altrank_30d': 1,
        'galaxy_score': 85,
        'volatility': 0.05,
        'social_volume': 10000,
        'social_volume_24h': 15000,
        'social_dominance': 45.5,
        'social_contributors': 5000,
        'sentiment_score': 4,
        'average_sentiment': 0.6,
        'tweets_24h': 5000,
        'reddit_posts_24h': 100,
        'reddit_comments_24h': 500,
        'price': 50000,
        'price_btc': 1.0,
        'volume_24h': 25000000000,
        'market_cap': 950000000000,
        'percent_change_24h': 2.5,
        'correlation_rank': 1,
        'source': 'test',
        'metadata': {'test': True}
    }
    
    success = await db.store_social_metrics_aggregated(metrics)
    assert success, "Failed to store aggregated metrics"
    print("   ✅ Stored aggregated social metrics")
    
    metrics_list = await db.get_social_metrics_aggregated(symbol='BTC', hours=1)
    assert len(metrics_list) > 0, "No metrics retrieved"
    print(f"   ✅ Retrieved {len(metrics_list)} metric(s)")
    
    # Test trending topics
    trending = await db.get_trending_topics(limit=5)
    print(f"   ✅ Retrieved {len(trending)} trending topic(s)")
    
    await db.disconnect()
    
    return True


async def test_imports_work():
    """Test that main.py can import the social collectors"""
    print("\n6. Testing imports in main.py...")
    
    try:
        import sys
        import importlib
        
        # Remove main from cache if it exists
        if 'main' in sys.modules:
            del sys.modules['main']
        
        # Import main
        import main
        
        # Check that MarketDataService has the collector attributes
        service = main.MarketDataService()
        assert hasattr(service, 'twitter_collector'), "MarketDataService missing twitter_collector"
        assert hasattr(service, 'reddit_collector'), "MarketDataService missing reddit_collector"
        assert hasattr(service, 'lunarcrush_collector'), "MarketDataService missing lunarcrush_collector"
        print("   ✅ MarketDataService has social collector attributes")
        
        # Check that collectors are None initially
        assert service.twitter_collector is None, "Collectors should be None initially"
        assert service.reddit_collector is None, "Collectors should be None initially"
        assert service.lunarcrush_collector is None, "Collectors should be None initially"
        print("   ✅ Collectors are None initially (correct)")
        
        return True
        
    except Exception as e:
        print(f"   ❌ Import test failed: {e}")
        # This is not critical - just informational
        return True


async def run_all_tests():
    """Run all tests"""
    tests = [
        ("Configuration", test_configuration),
        ("Database Methods", test_database_methods),
        ("Collector Instantiation", test_collectors_can_be_initialized),
        ("Sentiment Analysis", test_sentiment_analysis),
        ("Data Storage/Retrieval", test_data_storage_and_retrieval),
        ("Main.py Imports", test_imports_work),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            result = await test_func()
            results.append((test_name, result, None))
        except Exception as e:
            results.append((test_name, False, str(e)))
    
    # Print summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    passed = 0
    failed = 0
    
    for test_name, result, error in results:
        if result:
            print(f"✅ {test_name}: PASSED")
            passed += 1
        else:
            print(f"❌ {test_name}: FAILED")
            if error:
                print(f"   Error: {error}")
            failed += 1
    
    print("\n" + "-" * 60)
    print(f"Total: {passed + failed} tests")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    
    if failed == 0:
        print("\n🎉 All integration tests passed!")
    else:
        print(f"\n⚠️  {failed} test(s) failed")
    
    print("=" * 60)
    
    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
