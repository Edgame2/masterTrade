"""
Twitter/X Data Collector for Market Data Service

Collects real-time cryptocurrency sentiment from Twitter/X using API v2:
- Streaming tweets with crypto keywords and hashtags
- Tracking influential crypto accounts
- Sentiment analysis and engagement metrics
- Bot filtering and quality scoring

Requires Twitter API v2 Basic tier (~$100/month) or higher
"""

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, Any, List
import structlog
import aio_pika

from database import Database
from collectors.social_collector import SocialCollector, SentimentScore

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


class TwitterCollector(SocialCollector):
    """
    Twitter/X data collector for crypto sentiment
    
    Features:
    - Real-time tweet streaming
    - Influencer tracking
    - Sentiment analysis
    - Engagement metrics
    """
    
    # Influential crypto accounts to track
    CRYPTO_INFLUENCERS = [
        "APompliano",  # Anthony Pompliano
        "100trillionUSD",  # PlanB
        "cz_binance",  # CZ Binance
        "VitalikButerin",  # Vitalik
        "elonmusk",  # Elon Musk
        "michael_saylor",  # Michael Saylor
        "CathieDWood",  # Cathie Wood
        "aantonop",  # Andreas Antonopoulos
        "naval",  # Naval Ravikant
        "balajis",  # Balaji Srinivasan
    ]
    
    # Crypto-related keywords and hashtags
    CRYPTO_KEYWORDS = [
        "bitcoin", "BTC", "#Bitcoin",
        "ethereum", "ETH", "#Ethereum",
        "crypto", "#Crypto",
        "blockchain", "#Blockchain",
        "DeFi", "#DeFi",
        "NFT", "#NFT",
        "Web3", "#Web3",
        "$BTC", "$ETH",
    ]
    
    def __init__(
        self,
        database: Database,
        api_key: str,
        api_secret: str,
        bearer_token: str,
        rate_limit: float = 1.0,
        use_finbert: bool = False,
        rabbitmq_channel: Optional[aio_pika.Channel] = None
    ):
        """
        Initialize Twitter collector
        
        Args:
            database: Database instance
            api_key: Twitter API key
            api_secret: Twitter API secret
            bearer_token: Twitter bearer token for API v2
            rate_limit: Requests per second
            use_finbert: Use FinBERT for sentiment analysis
            rabbitmq_channel: Optional RabbitMQ channel for publishing sentiment
        """
        super().__init__(
            collector_name="twitter",
            database=database,
            api_key=bearer_token,  # Use bearer token as api_key
            api_url="https://api.twitter.com/2",
            rate_limit=rate_limit,
            use_finbert=use_finbert
        )
        
        self.api_secret = api_secret
        self.bearer_token = bearer_token
        self.rabbitmq_channel = rabbitmq_channel
        
        # Streaming state
        self.stream_active = False
        self.stream_task: Optional[asyncio.Task] = None
        
        # Rate limiting for streaming API
        self.tweets_processed_minute = 0
        self.minute_reset = datetime.now(timezone.utc)
        
        logger.info("Twitter collector initialized")
        
    async def collect_data(self) -> Dict[str, Any]:
        """
        Collect Twitter data (both search and streaming)
        
        Returns:
            Collection results
        """
        results = {
            "tweets_collected": 0,
            "influencer_tweets": 0,
            "sentiment_distribution": {"positive": 0, "negative": 0, "neutral": 0},
            "crypto_mentions": {},
            "errors": []
        }
        
        try:
            # Collect recent tweets from influencers
            influencer_results = await self._collect_influencer_tweets()
            results["influencer_tweets"] = influencer_results["count"]
            results["tweets_collected"] += influencer_results["count"]
            
            # Collect recent tweets by keywords
            keyword_results = await self._collect_keyword_tweets()
            results["tweets_collected"] += keyword_results["count"]
            
            # Update sentiment distribution
            for category, count in keyword_results.get("sentiment", {}).items():
                results["sentiment_distribution"][category] = \
                    results["sentiment_distribution"].get(category, 0) + count
                    
            # Update crypto mentions
            for symbol, count in keyword_results.get("crypto_mentions", {}).items():
                results["crypto_mentions"][symbol] = \
                    results["crypto_mentions"].get(symbol, 0) + count
                    
            self.stats["last_collection"] = datetime.now(timezone.utc).isoformat()
            self.stats["posts_processed"] += results["tweets_collected"]
            
            # Log collector health
            await self.database.log_collector_health(
                collector_name=self.collector_name,
                status="healthy",
                metadata=results
            )
            
        except Exception as e:
            error_msg = f"Twitter collection failed: {str(e)}"
            logger.error(error_msg, error=str(e))
            results["errors"].append(error_msg)
            self.stats["errors"] += 1
            
            await self.database.log_collector_health(
                collector_name=self.collector_name,
                status="error",
                metadata={"error": str(e)}
            )
            
        return results
        
    async def _collect_influencer_tweets(self) -> Dict[str, Any]:
        """
        Collect recent tweets from influential crypto accounts
        
        Returns:
            Collection results
        """
        results = {"count": 0, "errors": []}
        
        for username in self.CRYPTO_INFLUENCERS:
            try:
                # Get user ID first
                user_data = await self._get_user_by_username(username)
                if not user_data:
                    continue
                    
                user_id = user_data["id"]
                
                # Get recent tweets
                tweets = await self._get_user_tweets(
                    user_id=user_id,
                    max_results=10
                )
                
                if not tweets:
                    continue
                    
                # Process and store tweets
                for tweet in tweets:
                    await self._process_and_store_tweet(
                        tweet,
                        is_influencer=True,
                        influencer_username=username
                    )
                    results["count"] += 1
                    
            except Exception as e:
                error_msg = f"Failed to collect tweets from {username}: {str(e)}"
                logger.warning(error_msg)
                results["errors"].append(error_msg)
                
        return results
        
    async def _collect_keyword_tweets(self) -> Dict[str, Any]:
        """
        Collect recent tweets containing crypto keywords
        
        Returns:
            Collection results
        """
        results = {
            "count": 0,
            "sentiment": {"positive": 0, "negative": 0, "neutral": 0},
            "crypto_mentions": {},
            "errors": []
        }
        
        try:
            # Build search query (OR of keywords, limited to 512 chars)
            query_parts = self.CRYPTO_KEYWORDS[:10]  # Limit to avoid query length issues
            query = " OR ".join(query_parts)
            query += " -is:retweet lang:en"  # Exclude retweets, English only
            
            # Search recent tweets
            tweets = await self._search_recent_tweets(
                query=query,
                max_results=100
            )
            
            if not tweets:
                return results
                
            # Process tweets
            for tweet in tweets:
                processed = await self._process_and_store_tweet(tweet)
                if processed:
                    results["count"] += 1
                    
                    # Update sentiment distribution
                    sentiment_cat = processed.get("sentiment_category", "neutral")
                    if "positive" in sentiment_cat:
                        results["sentiment"]["positive"] += 1
                    elif "negative" in sentiment_cat:
                        results["sentiment"]["negative"] += 1
                    else:
                        results["sentiment"]["neutral"] += 1
                        
                    # Update crypto mentions
                    for symbol in processed.get("mentioned_cryptos", []):
                        results["crypto_mentions"][symbol] = \
                            results["crypto_mentions"].get(symbol, 0) + 1
                            
        except Exception as e:
            error_msg = f"Keyword tweet collection failed: {str(e)}"
            logger.warning(error_msg)
            results["errors"].append(error_msg)
            
        return results
        
    async def _get_user_by_username(self, username: str) -> Optional[Dict]:
        """Get user data by username"""
        endpoint = f"users/by/username/{username}"
        params = {"user.fields": "public_metrics,verified,created_at"}
        
        data = await self._make_request(endpoint, params)
        return data.get("data") if data else None
        
    async def _get_user_tweets(
        self,
        user_id: str,
        max_results: int = 10
    ) -> List[Dict]:
        """Get recent tweets from a user"""
        endpoint = f"users/{user_id}/tweets"
        params = {
            "max_results": min(max_results, 100),
            "tweet.fields": "created_at,public_metrics,referenced_tweets",
            "exclude": "retweets,replies"
        }
        
        data = await self._make_request(endpoint, params)
        return data.get("data", []) if data else []
        
    async def _search_recent_tweets(
        self,
        query: str,
        max_results: int = 100
    ) -> List[Dict]:
        """Search recent tweets by query"""
        endpoint = "tweets/search/recent"
        params = {
            "query": query,
            "max_results": min(max_results, 100),
            "tweet.fields": "created_at,public_metrics,author_id",
        }
        
        data = await self._make_request(endpoint, params)
        return data.get("data", []) if data else []
        
    async def _process_and_store_tweet(
        self,
        tweet: Dict,
        is_influencer: bool = False,
        influencer_username: Optional[str] = None
    ) -> Optional[Dict]:
        """
        Process tweet and store in database
        
        Args:
            tweet: Tweet data from API
            is_influencer: Whether tweet is from an influencer
            influencer_username: Username if influencer
            
        Returns:
            Processed tweet data or None
        """
        try:
            # Extract tweet text
            text = tweet.get("text", "")
            if not text:
                return None
                
            # Check for bot (basic heuristics)
            author_id = tweet.get("author_id")
            if self.is_bot(author_id or "unknown"):
                return None
                
            # Clean text
            cleaned_text = self.clean_text(text)
            
            # Analyze sentiment
            sentiment_scores, sentiment_category = self.analyze_sentiment(cleaned_text)
            
            # Extract crypto mentions
            mentioned_cryptos = self.extract_crypto_mentions(text)
            
            # Get engagement metrics
            public_metrics = tweet.get("public_metrics", {})
            engagement_score = (
                public_metrics.get("like_count", 0) +
                public_metrics.get("retweet_count", 0) * 2 +
                public_metrics.get("reply_count", 0)
            )
            
            # Create timestamp
            created_at = tweet.get("created_at")
            if created_at:
                timestamp = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            else:
                timestamp = datetime.now(timezone.utc)
                
            # Store each mentioned crypto separately
            for symbol in mentioned_cryptos:
                sentiment_data = {
                    "symbol": symbol,
                    "source": "twitter",
                    "text": text,
                    "sentiment_score": sentiment_scores.get("compound", 0.0),
                    "sentiment_category": sentiment_category.value,
                    "sentiment_positive": sentiment_scores.get("positive", 0.0),
                    "sentiment_negative": sentiment_scores.get("negative", 0.0),
                    "sentiment_neutral": sentiment_scores.get("neutral", 0.0),
                    "timestamp": timestamp,
                    "author_id": author_id,
                    "author_username": influencer_username,
                    "is_influencer": is_influencer,
                    "engagement_score": engagement_score,
                    "like_count": public_metrics.get("like_count", 0),
                    "retweet_count": public_metrics.get("retweet_count", 0),
                    "reply_count": public_metrics.get("reply_count", 0),
                    "post_id": tweet.get("id"),
                    "metadata": {
                        "tweet_id": tweet.get("id"),
                        "influencer": is_influencer,
                        "influencer_username": influencer_username
                    }
                }
                
                # Store in database
                success = await self.database.store_social_sentiment(sentiment_data)
                
                if not success:
                    logger.warning("Failed to store tweet sentiment", symbol=symbol)
                else:
                    # Publish to RabbitMQ if channel available
                    if self.rabbitmq_channel:
                        await self._publish_sentiment_update(sentiment_data, symbol)
                    
            return {
                "text": text,
                "sentiment_category": sentiment_category.value,
                "mentioned_cryptos": mentioned_cryptos,
                "engagement_score": engagement_score
            }
            
        except Exception as e:
            logger.error("Failed to process tweet", error=str(e))
            return None
            
    async def start_streaming(self):
        """Start streaming tweets (optional real-time feature)"""
        if self.stream_active:
            logger.warning("Twitter streaming already active")
            return
            
        self.stream_active = True
        self.stream_task = asyncio.create_task(self._stream_tweets())
        logger.info("Twitter streaming started")
        
    async def stop_streaming(self):
        """Stop streaming tweets"""
        self.stream_active = False
        if self.stream_task:
            self.stream_task.cancel()
            try:
                await self.stream_task
            except asyncio.CancelledError:
                pass
            self.stream_task = None
        logger.info("Twitter streaming stopped")
        
    async def _stream_tweets(self):
        """
        Stream tweets in real-time (requires streaming API access)
        
        Note: This is a placeholder for streaming functionality.
        Actual implementation would use Twitter's streaming API endpoints.
        """
        logger.info("Twitter streaming not yet fully implemented")
        # TODO: Implement streaming API connection
        # This would connect to the streaming endpoint and process tweets in real-time
    
    async def _publish_sentiment_update(self, sentiment_data: Dict, symbol: str):
        """
        Publish social sentiment update to RabbitMQ
        
        Args:
            sentiment_data: Sentiment data dictionary
            symbol: Cryptocurrency symbol
        """
        try:
            # Determine signal based on sentiment score
            sentiment_score = sentiment_data["sentiment_score"]
            if sentiment_score >= 0.3:
                signal = TrendDirection.BULLISH
            elif sentiment_score <= -0.3:
                signal = TrendDirection.BEARISH
            else:
                signal = TrendDirection.NEUTRAL
            
            # Calculate social volume (single tweet = 1, but weighted by engagement)
            engagement_score = sentiment_data.get("engagement_score", 0.0)
            social_volume = max(1, int(engagement_score * 10))  # Scale engagement
            
            # Create SocialSentimentUpdate message
            update = SocialSentimentUpdate(
                update_id=f"twitter_{symbol.lower()}_{sentiment_data.get('post_id', '')}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
                symbol=symbol,
                source="twitter",
                sentiment_score=sentiment_score,
                social_volume=social_volume,
                engagement_metrics={
                    "likes": sentiment_data.get("like_count", 0),
                    "retweets": sentiment_data.get("retweet_count", 0),
                    "replies": sentiment_data.get("reply_count", 0),
                    "engagement_score": engagement_score
                },
                influencer_sentiment=sentiment_score if sentiment_data.get("is_influencer") else None,
                trending_topics=[symbol],
                signal=signal,
                confidence=abs(sentiment_score),
                timestamp=sentiment_data["timestamp"],
                metadata={
                    "author": sentiment_data.get("author_username"),
                    "is_influencer": sentiment_data.get("is_influencer", False),
                    "tweet_id": sentiment_data.get("post_id"),
                    "text_preview": sentiment_data["text"][:100] if len(sentiment_data["text"]) > 100 else sentiment_data["text"]
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
                routing_key=RoutingKeys.SENTIMENT_TWITTER
            )
            
            logger.debug(
                "Published Twitter sentiment to RabbitMQ",
                symbol=symbol,
                sentiment=sentiment_score,
                author=sentiment_data.get("author_username"),
                is_influencer=sentiment_data.get("is_influencer")
            )
            
        except Exception as e:
            logger.error(
                "Failed to publish Twitter sentiment",
                symbol=symbol,
                error=str(e)
            )
