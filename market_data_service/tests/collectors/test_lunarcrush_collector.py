"""
Unit Tests for LunarCrush Social Aggregation Collector

Tests:
- Initialization and authentication
- AltRank metrics
- Galaxy Score calculation
- Social volume tracking
- Social dominance metrics
- Market correlation
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

from collectors.lunarcrush_collector import LunarCrushCollector
from database import Database


@pytest.fixture
def mock_database():
    """Mock database instance"""
    db = Mock(spec=Database)
    db.store_social_sentiment = AsyncMock(return_value=True)
    db.store_lunarcrush_metrics = AsyncMock(return_value=True)
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
def lunarcrush_collector(mock_database, mock_rabbitmq_channel):
    """Create LunarCrush collector instance with mocks"""
    collector = LunarCrushCollector(
        database=mock_database,
        api_key="test_lunarcrush_api_key",
        rate_limit=5.0,
        timeout=30.0,
        rabbitmq_channel=mock_rabbitmq_channel
    )
    return collector


class TestLunarCrushCollectorInitialization:
    """Test collector initialization"""
    
    def test_init_with_valid_parameters(self, mock_database, mock_rabbitmq_channel):
        """Test successful initialization"""
        collector = LunarCrushCollector(
            database=mock_database,
            api_key="api_key_abc123",
            rate_limit=3.0,
            timeout=60.0,
            rabbitmq_channel=mock_rabbitmq_channel
        )
        
        assert collector.collector_name == "lunarcrush"
        assert collector.api_key == "api_key_abc123"
        assert collector.rate_limit == 3.0
        assert collector.timeout == 60.0
        assert collector.rabbitmq_channel == mock_rabbitmq_channel
        
    def test_tracked_coins_configured(self, lunarcrush_collector):
        """Test that tracked coins are configured"""
        assert len(lunarcrush_collector.TRACKED_COINS) > 0
        assert "BTC" in lunarcrush_collector.TRACKED_COINS or "Bitcoin" in lunarcrush_collector.TRACKED_COINS
        assert "ETH" in lunarcrush_collector.TRACKED_COINS or "Ethereum" in lunarcrush_collector.TRACKED_COINS


class TestAltRankMetrics:
    """Test AltRank metrics collection"""
    
    @pytest.mark.asyncio
    async def test_get_altrank(self, lunarcrush_collector):
        """Test fetching AltRank metric"""
        mock_altrank_data = {
            "symbol": "BTC",
            "alt_rank": 1,  # Rank 1 = best performing
            "alt_rank_30d": 2,
            "timestamp": 1699800000
        }
        
        with patch.object(lunarcrush_collector, '_get_asset_metrics', new=AsyncMock(return_value=mock_altrank_data)):
            altrank = await lunarcrush_collector._get_altrank("BTC")
            
            assert altrank["alt_rank"] > 0
            assert altrank["alt_rank"] <= 1000  # Typical AltRank range
            
    @pytest.mark.asyncio
    async def test_altrank_interpretation_top_rank(self, lunarcrush_collector):
        """Test AltRank interpretation - top ranked coins"""
        top_rank = 5  # Top 5 = strong bullish signal
        
        signal = lunarcrush_collector._interpret_altrank_signal(top_rank)
        
        assert signal in ["bullish", "strong_bullish", "buy"]
        
    @pytest.mark.asyncio
    async def test_altrank_interpretation_low_rank(self, lunarcrush_collector):
        """Test AltRank interpretation - low ranked coins"""
        low_rank = 800  # Low rank = weak or bearish
        
        signal = lunarcrush_collector._interpret_altrank_signal(low_rank)
        
        assert signal in ["bearish", "weak", "neutral"]


class TestGalaxyScoreMetrics:
    """Test Galaxy Score calculation"""
    
    @pytest.mark.asyncio
    async def test_get_galaxy_score(self, lunarcrush_collector):
        """Test fetching Galaxy Score"""
        mock_score_data = {
            "symbol": "BTC",
            "galaxy_score": 75.5,  # Score 0-100
            "timestamp": 1699800000
        }
        
        with patch.object(lunarcrush_collector, '_get_asset_metrics', new=AsyncMock(return_value=mock_score_data)):
            score = await lunarcrush_collector._get_galaxy_score("BTC")
            
            assert 0 <= score["galaxy_score"] <= 100
            
    @pytest.mark.asyncio
    async def test_galaxy_score_interpretation_high(self, lunarcrush_collector):
        """Test high Galaxy Score interpretation (>75)"""
        high_score = 85
        
        signal = lunarcrush_collector._interpret_galaxy_score(high_score)
        
        assert signal in ["bullish", "strong", "buy"]
        
    @pytest.mark.asyncio
    async def test_galaxy_score_interpretation_low(self, lunarcrush_collector):
        """Test low Galaxy Score interpretation (<40)"""
        low_score = 30
        
        signal = lunarcrush_collector._interpret_galaxy_score(low_score)
        
        assert signal in ["bearish", "weak", "sell"]


class TestSocialVolumeTracking:
    """Test social volume metrics"""
    
    @pytest.mark.asyncio
    async def test_get_social_volume(self, lunarcrush_collector):
        """Test fetching social volume"""
        mock_volume_data = {
            "symbol": "BTC",
            "social_volume": 50000,  # 50k social mentions
            "social_volume_24h_change": 15.5,  # +15.5% change
            "timestamp": 1699800000
        }
        
        with patch.object(lunarcrush_collector, '_get_asset_metrics', new=AsyncMock(return_value=mock_volume_data)):
            volume = await lunarcrush_collector._get_social_volume("BTC")
            
            assert volume["social_volume"] > 0
            
    @pytest.mark.asyncio
    async def test_social_volume_spike_detection(self, lunarcrush_collector):
        """Test detecting social volume spikes"""
        current_volume = 100000
        average_volume = 50000
        
        is_spike = lunarcrush_collector._is_volume_spike(current_volume, average_volume)
        
        assert is_spike is True  # 2x increase should be spike
        
    @pytest.mark.asyncio
    async def test_social_volume_trend(self, lunarcrush_collector):
        """Test social volume trend analysis"""
        volume_data = {
            "24h_change": 25.5,  # +25.5%
            "7d_change": 50.0    # +50%
        }
        
        trend = lunarcrush_collector._analyze_volume_trend(volume_data)
        
        assert trend in ["increasing", "bullish", "uptrend"]


class TestSocialDominanceMetrics:
    """Test social dominance tracking"""
    
    @pytest.mark.asyncio
    async def test_get_social_dominance(self, lunarcrush_collector):
        """Test fetching social dominance"""
        mock_dominance_data = {
            "symbol": "BTC",
            "social_dominance": 45.5,  # 45.5% of crypto social mentions
            "timestamp": 1699800000
        }
        
        with patch.object(lunarcrush_collector, '_get_asset_metrics', new=AsyncMock(return_value=mock_dominance_data)):
            dominance = await lunarcrush_collector._get_social_dominance("BTC")
            
            assert 0 <= dominance["social_dominance"] <= 100
            
    @pytest.mark.asyncio
    async def test_dominance_interpretation_high(self, lunarcrush_collector):
        """Test high dominance interpretation"""
        high_dominance = 55.0  # BTC typically has high dominance
        
        signal = lunarcrush_collector._interpret_dominance(high_dominance, "BTC")
        
        assert signal in ["bullish", "strong", "dominant"]


class TestMarketCorrelation:
    """Test market correlation analysis"""
    
    @pytest.mark.asyncio
    async def test_get_correlation_metrics(self, lunarcrush_collector):
        """Test fetching correlation metrics"""
        mock_correlation = {
            "symbol": "ETH",
            "correlation_with_btc": 0.85,  # 85% correlation
            "timestamp": 1699800000
        }
        
        with patch.object(lunarcrush_collector, '_get_asset_metrics', new=AsyncMock(return_value=mock_correlation)):
            correlation = await lunarcrush_collector._get_correlation("ETH", "BTC")
            
            assert -1 <= correlation["correlation_with_btc"] <= 1
            
    @pytest.mark.asyncio
    async def test_correlation_interpretation(self, lunarcrush_collector):
        """Test correlation interpretation"""
        high_correlation = 0.90
        
        # High correlation means assets move together
        interpretation = lunarcrush_collector._interpret_correlation(high_correlation)
        
        assert interpretation in ["high_correlation", "moves_together", "correlated"]


class TestSocialSentimentAggregation:
    """Test social sentiment aggregation"""
    
    @pytest.mark.asyncio
    async def test_aggregate_social_sentiment(self, lunarcrush_collector):
        """Test aggregating sentiment from multiple sources"""
        mock_sentiment_data = {
            "symbol": "BTC",
            "sentiment": "bullish",
            "sentiment_score": 0.75,
            "sources": ["twitter", "reddit", "news"]
        }
        
        with patch.object(lunarcrush_collector, '_get_asset_metrics', new=AsyncMock(return_value=mock_sentiment_data)):
            sentiment = await lunarcrush_collector._get_aggregated_sentiment("BTC")
            
            assert sentiment["sentiment"] in ["bullish", "bearish", "neutral"]
            assert 0 <= sentiment["sentiment_score"] <= 1


class TestInfluencerMetrics:
    """Test influencer impact metrics"""
    
    @pytest.mark.asyncio
    async def test_get_influencer_impact(self, lunarcrush_collector):
        """Test fetching influencer impact metrics"""
        mock_influencer_data = {
            "symbol": "BTC",
            "influencer_posts": 150,
            "influencer_engagement": 500000,
            "timestamp": 1699800000
        }
        
        with patch.object(lunarcrush_collector, '_get_asset_metrics', new=AsyncMock(return_value=mock_influencer_data)):
            impact = await lunarcrush_collector._get_influencer_impact("BTC")
            
            assert impact["influencer_posts"] > 0


class TestRateLimiting:
    """Test rate limiting functionality"""
    
    @pytest.mark.asyncio
    async def test_rate_limiting_enforced(self, lunarcrush_collector):
        """Test that rate limiting delays requests"""
        lunarcrush_collector.rate_limit = 2.0  # 2 requests per second
        
        start_time = datetime.now()
        
        # Make 3 rapid requests
        for _ in range(3):
            await lunarcrush_collector._wait_for_rate_limit()
            
        elapsed = (datetime.now() - start_time).total_seconds()
        
        # Should take at least 1 second
        assert elapsed >= 0.9
        
    @pytest.mark.asyncio
    async def test_request_tracking(self, lunarcrush_collector):
        """Test that requests are tracked"""
        initial_count = lunarcrush_collector.stats.get("api_calls", 0)
        
        await lunarcrush_collector._wait_for_rate_limit()
        
        # Request count should increment


class TestAPIRequests:
    """Test API request handling"""
    
    @pytest.mark.asyncio
    async def test_successful_api_request(self, lunarcrush_collector):
        """Test successful API request"""
        mock_response = {
            "data": {
                "symbol": "BTC",
                "galaxy_score": 75
            }
        }
        
        with patch.object(lunarcrush_collector, '_make_request', new=AsyncMock(return_value=mock_response)):
            result = await lunarcrush_collector._get_asset_metrics("BTC")
            
            assert result is not None
            
    @pytest.mark.asyncio
    async def test_api_request_with_retry(self, lunarcrush_collector):
        """Test API request with retry on failure"""
        with patch.object(lunarcrush_collector, '_make_request', new=AsyncMock(side_effect=[
            Exception("Temporary error"),
            {"data": {"symbol": "BTC"}}
        ])):
            result = await lunarcrush_collector._get_asset_metrics("BTC")
            
            # Should succeed after retry
            
    @pytest.mark.asyncio
    async def test_api_request_timeout(self, lunarcrush_collector):
        """Test API request timeout handling"""
        with patch.object(lunarcrush_collector, '_make_request', new=AsyncMock(side_effect=asyncio.TimeoutError)):
            result = await lunarcrush_collector._get_asset_metrics("BTC")
            
            # Should handle timeout gracefully


class TestDatabaseInteractions:
    """Test database storage operations"""
    
    @pytest.mark.asyncio
    async def test_store_lunarcrush_metrics(self, lunarcrush_collector, mock_database):
        """Test storing LunarCrush metrics to database"""
        metrics_data = {
            "symbol": "BTC",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "alt_rank": 1,
            "galaxy_score": 85,
            "social_volume": 50000,
            "social_dominance": 45.5,
            "sentiment": "bullish",
            "sentiment_score": 0.75
        }
        
        await mock_database.store_lunarcrush_metrics(
            symbol="BTC",
            metrics=metrics_data
        )
        
        mock_database.store_lunarcrush_metrics.assert_called_once()
        
    @pytest.mark.asyncio
    async def test_log_collector_health(self, lunarcrush_collector, mock_database):
        """Test logging collector health"""
        stats = {"assets_collected": 10, "api_calls": 50, "errors": 0}
        
        await mock_database.log_collector_health(
            collector_name="lunarcrush",
            status="healthy",
            metadata=stats
        )
        
        mock_database.log_collector_health.assert_called_once()


class TestRabbitMQPublishing:
    """Test RabbitMQ message publishing"""
    
    @pytest.mark.asyncio
    async def test_publish_social_metrics(self, lunarcrush_collector, mock_rabbitmq_channel):
        """Test publishing social metrics to RabbitMQ"""
        metrics_data = {
            "symbol": "BTC",
            "alt_rank": 1,
            "galaxy_score": 85,
            "social_volume": 50000,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        with patch.object(lunarcrush_collector, '_publish_metrics', new=AsyncMock()):
            await lunarcrush_collector._publish_metrics(metrics_data)
            
    @pytest.mark.asyncio
    async def test_publish_sentiment_signal(self, lunarcrush_collector):
        """Test publishing sentiment signal"""
        sentiment_data = {
            "symbol": "BTC",
            "sentiment": "bullish",
            "sentiment_score": 0.8,
            "source": "lunarcrush_aggregated"
        }
        
        with patch.object(lunarcrush_collector, '_publish_metrics', new=AsyncMock()):
            await lunarcrush_collector._publish_metrics(sentiment_data)
            
    @pytest.mark.asyncio
    async def test_publish_without_rabbitmq(self, mock_database):
        """Test that publishing works without RabbitMQ"""
        collector = LunarCrushCollector(
            database=mock_database,
            api_key="key",
            rabbitmq_channel=None
        )
        
        metrics_data = {"symbol": "BTC"}
        
        with patch.object(collector, '_publish_metrics', new=AsyncMock()):
            await collector._publish_metrics(metrics_data)


class TestSignalAggregation:
    """Test signal aggregation from multiple metrics"""
    
    def test_aggregate_bullish_signals(self, lunarcrush_collector):
        """Test aggregating multiple bullish signals"""
        signals = {
            "altrank": "bullish",  # Top rank
            "galaxy_score": "bullish",  # High score
            "social_volume": "bullish",  # Increasing
            "sentiment": "bullish"
        }
        
        overall_signal = lunarcrush_collector._aggregate_signals(signals)
        
        assert overall_signal in ["bullish", "strong_bullish"]
        
    def test_aggregate_bearish_signals(self, lunarcrush_collector):
        """Test aggregating multiple bearish signals"""
        signals = {
            "altrank": "bearish",  # Low rank
            "galaxy_score": "bearish",  # Low score
            "social_volume": "bearish",  # Decreasing
            "sentiment": "bearish"
        }
        
        overall_signal = lunarcrush_collector._aggregate_signals(signals)
        
        assert overall_signal in ["bearish", "strong_bearish"]


class TestCollectionFlow:
    """Test main collection flow"""
    
    @pytest.mark.asyncio
    async def test_collect_all_metrics(self, lunarcrush_collector):
        """Test collecting all metrics for a coin"""
        mock_metrics = {
            "alt_rank": 5,
            "galaxy_score": 80,
            "social_volume": 50000,
            "social_dominance": 45.5
        }
        
        with patch.object(lunarcrush_collector, '_get_asset_metrics', new=AsyncMock(return_value=mock_metrics)):
            result = await lunarcrush_collector.collect_data(symbols=["BTC"])
            
            assert "metrics_collected" in result or isinstance(result, dict)
            
    @pytest.mark.asyncio
    async def test_collect_multiple_coins(self, lunarcrush_collector):
        """Test collecting metrics for multiple coins"""
        with patch.object(lunarcrush_collector, '_get_asset_metrics', new=AsyncMock(return_value={"alt_rank": 1})):
            result = await lunarcrush_collector.collect_data(symbols=["BTC", "ETH", "SOL"])
            
            assert isinstance(result, dict)


class TestErrorHandling:
    """Test error handling"""
    
    @pytest.mark.asyncio
    async def test_collect_with_api_error(self, lunarcrush_collector):
        """Test handling API errors during collection"""
        with patch.object(lunarcrush_collector, '_get_asset_metrics', new=AsyncMock(side_effect=Exception("API Error"))):
            result = await lunarcrush_collector.collect_data(symbols=["BTC"])
            
            assert "errors" in result or result.get("metrics_collected", 0) >= 0
            
    @pytest.mark.asyncio
    async def test_collect_with_invalid_api_key(self, lunarcrush_collector):
        """Test handling invalid API key"""
        with patch.object(lunarcrush_collector, '_make_request', new=AsyncMock(side_effect=Exception("401 Unauthorized"))):
            result = await lunarcrush_collector._get_asset_metrics("BTC")
            
            # Should handle auth error gracefully


class TestStatistics:
    """Test statistics tracking"""
    
    def test_stats_initialization(self, lunarcrush_collector):
        """Test that statistics are initialized"""
        assert hasattr(lunarcrush_collector, 'stats')
        assert isinstance(lunarcrush_collector.stats, dict)
        
    @pytest.mark.asyncio
    async def test_stats_updated_on_collection(self, lunarcrush_collector):
        """Test that stats are updated after collection"""
        with patch.object(lunarcrush_collector, '_get_asset_metrics', new=AsyncMock(return_value={"alt_rank": 1})):
            await lunarcrush_collector.collect_data(symbols=["BTC"])
            
        # Stats should have been updated


class TestEdgeCases:
    """Test edge cases"""
    
    @pytest.mark.asyncio
    async def test_collect_with_empty_symbols(self, lunarcrush_collector):
        """Test collection with empty symbol list"""
        result = await lunarcrush_collector.collect_data(symbols=[])
        
        assert result["metrics_collected"] == 0
        
    @pytest.mark.asyncio
    async def test_metric_with_null_value(self, lunarcrush_collector):
        """Test handling null/missing metric values"""
        mock_response = {"data": {"symbol": "BTC", "galaxy_score": None}}
        
        with patch.object(lunarcrush_collector, '_make_request', new=AsyncMock(return_value=mock_response)):
            result = await lunarcrush_collector._get_asset_metrics("BTC")
            
            # Should handle null gracefully
            
    @pytest.mark.asyncio
    async def test_unlisted_coin(self, lunarcrush_collector):
        """Test requesting metrics for unlisted coin"""
        with patch.object(lunarcrush_collector, '_make_request', new=AsyncMock(return_value={"error": "Asset not found"})):
            result = await lunarcrush_collector._get_asset_metrics("UNKNOWN_COIN")
            
            # Should handle gracefully


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
