"""
LunarCrush Data Collector for Market Data Service

Collects aggregated social metrics from LunarCrush API:
- AltRank (social dominance ranking)
- Galaxy Score (overall social + market health)
- Social volume and sentiment
- Influencer activity
- Social dominance and correlation metrics

Requires LunarCrush API key (~$200/month for Pro plan)
"""

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, Any, List
import structlog
import aio_pika

from database import Database
from collectors.social_collector import SocialCollector

# Import message schemas
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
from shared.message_schemas import (
    SocialSentimentUpdate,
    TrendDirection,
    serialize_message,
    RoutingKeys
)

logger = structlog.get_logger()


class LunarCrushCollector(SocialCollector):
    """
    LunarCrush aggregated social metrics collector
    
    Features:
    - AltRank and Galaxy Score tracking
    - Social volume and sentiment aggregates
    - Influencer activity metrics
    - Social dominance indicators
    """
    
    # Top cryptocurrencies to track
    TRACKED_SYMBOLS = [
        "BTC", "ETH", "BNB", "XRP", "ADA",
        "SOL", "DOT", "DOGE", "MATIC", "AVAX",
        "LINK", "UNI", "ATOM", "LTC", "etc",
        "XLM", "ALGO", "VET", "FIL", "HBAR"
    ]
    
    def __init__(
        self,
        database: Database,
        api_key: str,
        rate_limit: float = 0.2,  # LunarCrush allows ~300/day, we use conservative limit
        use_finbert: bool = False,
        rabbitmq_channel: Optional[aio_pika.Channel] = None
    ):
        """
        Initialize LunarCrush collector
        
        Args:
            database: Database instance
            api_key: LunarCrush API key
            rate_limit: Requests per second
            use_finbert: Not used for aggregated metrics
            rabbitmq_channel: Optional RabbitMQ channel for publishing metrics
        """
        super().__init__(
            collector_name="lunarcrush",
            database=database,
            api_key=api_key,
            api_url="https://api.lunarcrush.com/v2",
            rate_limit=rate_limit,
            use_finbert=False  # Not needed for aggregated data
        )
        
        self.rabbitmq_channel = rabbitmq_channel
        logger.info("LunarCrush collector initialized")
        
    async def collect_data(self) -> Dict[str, Any]:
        """
        Collect aggregated social metrics from LunarCrush
        
        Returns:
            Collection results
        """
        results = {
            "metrics_collected": 0,
            "symbols_processed": 0,
            "top_gainers": [],
            "top_losers": [],
            "errors": []
        }
        
        try:
            # Collect metrics for tracked symbols
            for symbol in self.TRACKED_SYMBOLS:
                try:
                    metrics = await self._collect_asset_metrics(symbol)
                    if metrics:
                        await self._store_metrics(symbol, metrics)
                        results["metrics_collected"] += 1
                        results["symbols_processed"] += 1
                        
                except Exception as e:
                    error_msg = f"Failed to collect metrics for {symbol}: {str(e)}"
                    logger.warning(error_msg)
                    results["errors"].append(error_msg)
                    
            # Get global metrics
            try:
                global_metrics = await self._collect_global_metrics()
                if global_metrics:
                    results["top_gainers"] = global_metrics.get("top_gainers", [])
                    results["top_losers"] = global_metrics.get("top_losers", [])
                    
            except Exception as e:
                error_msg = f"Failed to collect global metrics: {str(e)}"
                logger.warning(error_msg)
                results["errors"].append(error_msg)
                
            self.stats["last_collection"] = datetime.now(timezone.utc).isoformat()
            self.stats["posts_processed"] += results["metrics_collected"]
            
            # Log collector health
            await self.database.log_collector_health(
                collector_name=self.collector_name,
                status="healthy",
                metadata=results
            )
            
        except Exception as e:
            error_msg = f"LunarCrush collection failed: {str(e)}"
            logger.error(error_msg, error=str(e))
            results["errors"].append(error_msg)
            self.stats["errors"] += 1
            
            await self.database.log_collector_health(
                collector_name=self.collector_name,
                status="error",
                metadata={"error": str(e)}
            )
            
        return results
        
    async def _collect_asset_metrics(self, symbol: str) -> Optional[Dict]:
        """
        Collect metrics for a specific asset
        
        Args:
            symbol: Cryptocurrency symbol
            
        Returns:
            Asset metrics or None
        """
        endpoint = "assets"
        params = {
            "key": self.api_key,
            "symbol": symbol,
            "data": "market,social,time_series"
        }
        
        data = await self._make_request(endpoint, params)
        
        if not data or "data" not in data:
            return None
            
        asset_data = data["data"]
        if isinstance(asset_data, list) and len(asset_data) > 0:
            return asset_data[0]
        elif isinstance(asset_data, dict):
            return asset_data
            
        return None
        
    async def _collect_global_metrics(self) -> Optional[Dict]:
        """Collect global market metrics"""
        endpoint = "global"
        params = {
            "key": self.api_key
        }
        
        data = await self._make_request(endpoint, params)
        
        if not data or "data" not in data:
            return None
            
        return data["data"]
        
    async def _store_metrics(self, symbol: str, metrics: Dict):
        """
        Store LunarCrush metrics in database
        
        Args:
            symbol: Cryptocurrency symbol
            metrics: Metrics data from API
        """
        try:
            timestamp = datetime.now(timezone.utc)
            
            # Extract key metrics
            altrank = metrics.get("alt_rank")
            altrank_30d = metrics.get("alt_rank_30d")
            galaxy_score = metrics.get("galaxy_score")
            volatility = metrics.get("volatility")
            
            # Social metrics
            social_volume = metrics.get("social_volume", 0)
            social_volume_24h = metrics.get("social_volume_24h", 0)
            social_dominance = metrics.get("social_dominance", 0.0)
            social_contributors = metrics.get("social_contributors", 0)
            
            # Sentiment
            sentiment = metrics.get("sentiment", 3)  # 1-5 scale
            average_sentiment = metrics.get("average_sentiment", 0.0)
            
            # Engagement
            tweets_24h = metrics.get("tweets", 0)
            reddit_posts_24h = metrics.get("reddit_posts_24h", 0)
            reddit_comments_24h = metrics.get("reddit_comments_24h", 0)
            
            # Market data
            price = metrics.get("price")
            price_btc = metrics.get("price_btc")
            volume_24h = metrics.get("volume_24h")
            market_cap = metrics.get("market_cap")
            percent_change_24h = metrics.get("percent_change_24h")
            
            # Correlation
            correlation_rank = metrics.get("correlation_rank")
            
            # Create aggregated metrics entry
            aggregated_data = {
                "symbol": symbol,
                "timestamp": timestamp,
                "altrank": altrank,
                "altrank_30d": altrank_30d,
                "galaxy_score": galaxy_score,
                "volatility": volatility,
                "social_volume": social_volume,
                "social_volume_24h": social_volume_24h,
                "social_dominance": social_dominance,
                "social_contributors": social_contributors,
                "sentiment_score": sentiment,
                "average_sentiment": average_sentiment,
                "tweets_24h": tweets_24h,
                "reddit_posts_24h": reddit_posts_24h,
                "reddit_comments_24h": reddit_comments_24h,
                "price": price,
                "price_btc": price_btc,
                "volume_24h": volume_24h,
                "market_cap": market_cap,
                "percent_change_24h": percent_change_24h,
                "correlation_rank": correlation_rank,
                "source": "lunarcrush",
                "metadata": {
                    "url": metrics.get("url"),
                    "categories": metrics.get("categories", []),
                    "timeSeries": metrics.get("timeSeries", {})
                }
            }
            
            # Store in database
            success = await self.database.store_social_metrics_aggregated(aggregated_data)
            
            if not success:
                logger.warning("Failed to store LunarCrush metrics", symbol=symbol)
            else:
                logger.debug(
                    "Stored LunarCrush metrics",
                    symbol=symbol,
                    altrank=altrank,
                    galaxy_score=galaxy_score,
                    social_volume=social_volume
                )
                
                # Publish to RabbitMQ if channel available
                if self.rabbitmq_channel:
                    await self._publish_sentiment_update(aggregated_data, symbol)
                
        except Exception as e:
            logger.error("Failed to store LunarCrush metrics", symbol=symbol, error=str(e))
            
    async def get_trending_assets(self, limit: int = 10) -> List[Dict]:
        """
        Get trending assets by social metrics
        
        Args:
            limit: Number of assets to return
            
        Returns:
            List of trending assets
        """
        endpoint = "feeds"
        params = {
            "key": self.api_key,
            "limit": limit,
            "type": "trending"
        }
        
        data = await self._make_request(endpoint, params)
        
        if not data or "data" not in data:
            return []
            
        return data["data"]
        
    async def get_influencer_activity(self, symbol: Optional[str] = None) -> List[Dict]:
        """
        Get recent influencer activity
        
        Args:
            symbol: Optional symbol to filter by
            
        Returns:
            List of influencer posts
        """
        endpoint = "influencers"
        params = {
            "key": self.api_key
        }
        
        if symbol:
            params["symbol"] = symbol
            
        data = await self._make_request(endpoint, params)
        
        if not data or "data" not in data:
            return []
            
        return data["data"]
        
    async def _make_request(
        self,
        endpoint: str,
        params: Optional[Dict] = None,
        method: str = "GET"
    ) -> Optional[Dict]:
        """
        Make rate-limited API request to LunarCrush
        
        Overrides parent method to handle LunarCrush-specific auth
        """
        if not self.circuit_breaker.can_attempt():
            logger.warning(
                f"{self.collector_name} circuit breaker open, skipping request",
                endpoint=endpoint
            )
            return None
            
        await self.rate_limiter.acquire()
        
        if not self.session:
            await self.connect()
            
        url = f"{self.api_url}/{endpoint}"
        
        # LunarCrush uses key in query params, not headers
        if not params:
            params = {}
        if "key" not in params:
            params["key"] = self.api_key
            
        try:
            async with self.session.get(url, params=params) as response:
                response.raise_for_status()
                data = await response.json()
                
                self.circuit_breaker.record_success()
                return data
                
        except Exception as e:
            self.circuit_breaker.record_failure()
            self.stats["errors"] += 1
            logger.error(
                f"{self.collector_name} request failed",
                endpoint=endpoint,
                error=str(e)
            )
            
            # Log collector health
            await self.database.log_collector_health(
                collector_name=self.collector_name,
                status="error",
                metadata={"endpoint": endpoint, "error": str(e)}
            )
            
            return None
    
    async def _publish_sentiment_update(self, aggregated_data: Dict, symbol: str):
        """
        Publish social sentiment update to RabbitMQ
        
        Args:
            aggregated_data: Aggregated metrics data dictionary
            symbol: Cryptocurrency symbol
        """
        try:
            # Determine signal based on sentiment score
            sentiment_score = aggregated_data.get("sentiment_score", 0.0)
            if sentiment_score >= 0.3:
                signal = TrendDirection.BULLISH
            elif sentiment_score <= -0.3:
                signal = TrendDirection.BEARISH
            else:
                signal = TrendDirection.NEUTRAL
            
            # Social volume from LunarCrush
            social_volume = aggregated_data.get("social_volume", 0)
            
            # Create SocialSentimentUpdate message
            update = SocialSentimentUpdate(
                update_id=f"lunarcrush_{symbol.lower()}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
                symbol=symbol,
                source="lunarcrush",
                sentiment_score=sentiment_score,
                social_volume=social_volume,
                engagement_metrics={
                    "altrank": aggregated_data.get("altrank"),
                    "galaxy_score": aggregated_data.get("galaxy_score"),
                    "social_dominance": aggregated_data.get("social_dominance"),
                    "market_dominance": aggregated_data.get("market_dominance"),
                    "social_contributors": aggregated_data.get("social_contributors")
                },
                influencer_sentiment=sentiment_score,  # LunarCrush is pre-aggregated
                trending_topics=[symbol],
                signal=signal,
                confidence=abs(sentiment_score),
                timestamp=aggregated_data["timestamp"],
                metadata={
                    "altrank": aggregated_data.get("altrank"),
                    "galaxy_score": aggregated_data.get("galaxy_score"),
                    "correlation_rank": aggregated_data.get("correlation_rank"),
                    "source": "lunarcrush_aggregated"
                }
            )
            
            # Publish to RabbitMQ
            message = aio_pika.Message(
                body=serialize_message(update).encode(),
                content_type="application/json",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT
            )
            
            await self.rabbitmq_channel.default_exchange.publish(
                message,
                routing_key=RoutingKeys.SENTIMENT_AGGREGATED
            )
            
            logger.debug(
                "Published LunarCrush sentiment to RabbitMQ",
                symbol=symbol,
                sentiment=sentiment_score,
                altrank=aggregated_data.get("altrank"),
                galaxy_score=aggregated_data.get("galaxy_score")
            )
            
        except Exception as e:
            logger.error(
                "Failed to publish LunarCrush sentiment",
                symbol=symbol,
                error=str(e)
            )
