"""
Reddit Data Collector for Market Data Service

Collects cryptocurrency sentiment from Reddit using PRAW (Python Reddit API Wrapper):
- Posts and comments from r/cryptocurrency, r/bitcoin, r/ethereum, etc.
- Sentiment analysis of discussions
- Upvote/downvote metrics as engagement signals
- Topic trending analysis

Requires Reddit API credentials (free tier available, 60 requests/minute)
"""

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, Any, List
import structlog

from database import Database
from collectors.social_collector import SocialCollector, SentimentScore

logger = structlog.get_logger()


class RedditCollector(SocialCollector):
    """
    Reddit data collector for crypto sentiment
    
    Features:
    - Subreddit post and comment collection
    - Sentiment analysis
    - Engagement metrics (upvotes, awards)
    - Trending topic detection
    """
    
    # Crypto-related subreddits to monitor
    CRYPTO_SUBREDDITS = [
        "cryptocurrency",
        "CryptoCurrency",
        "bitcoin",
        "Bitcoin",
        "ethereum",
        "Ethereum",
        "CryptoMarkets",
        "CryptoMoonShots",
        "BitcoinMarkets",
        "ethtrader",
        "defi",
        "DeFi",
    ]
    
    def __init__(
        self,
        database: Database,
        client_id: str,
        client_secret: str,
        user_agent: str,
        rate_limit: float = 0.5,  # Reddit allows ~60/min, we use 30/min to be safe
        use_finbert: bool = False
    ):
        """
        Initialize Reddit collector
        
        Args:
            database: Database instance
            client_id: Reddit API client ID
            client_secret: Reddit API client secret
            user_agent: Reddit API user agent
            rate_limit: Requests per second (default 0.5 = 30/min)
            use_finbert: Use FinBERT for sentiment analysis
        """
        super().__init__(
            collector_name="reddit",
            database=database,
            api_key=None,  # Reddit uses OAuth2, not API key
            api_url="https://oauth.reddit.com",
            rate_limit=rate_limit,
            use_finbert=use_finbert
        )
        
        self.client_id = client_id
        self.client_secret = client_secret
        self.user_agent = user_agent
        self.access_token: Optional[str] = None
        self.token_expires_at: Optional[datetime] = None
        
        logger.info("Reddit collector initialized")
        
    async def connect(self):
        """Establish connection and get OAuth token"""
        await super().connect()
        await self._get_access_token()
        
    async def _get_access_token(self):
        """Get Reddit OAuth2 access token"""
        try:
            import base64
            
            # Encode credentials
            credentials = f"{self.client_id}:{self.client_secret}"
            encoded = base64.b64encode(credentials.encode()).decode()
            
            # Request token
            url = "https://www.reddit.com/api/v1/access_token"
            headers = {
                "Authorization": f"Basic {encoded}",
                "User-Agent": self.user_agent
            }
            data = {
                "grant_type": "client_credentials"
            }
            
            async with self.session.post(url, headers=headers, data=data) as response:
                response.raise_for_status()
                token_data = await response.json()
                
                self.access_token = token_data["access_token"]
                expires_in = token_data.get("expires_in", 3600)
                self.token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
                
                logger.info("Reddit OAuth token acquired", expires_in=expires_in)
                
        except Exception as e:
            logger.error("Failed to get Reddit access token", error=str(e))
            raise
            
    async def _ensure_valid_token(self):
        """Ensure we have a valid access token"""
        if not self.access_token or not self.token_expires_at:
            await self._get_access_token()
        elif datetime.now(timezone.utc) >= self.token_expires_at:
            await self._get_access_token()
            
    async def collect_data(self) -> Dict[str, Any]:
        """
        Collect Reddit data from crypto subreddits
        
        Returns:
            Collection results
        """
        results = {
            "posts_collected": 0,
            "comments_collected": 0,
            "sentiment_distribution": {"positive": 0, "negative": 0, "neutral": 0},
            "crypto_mentions": {},
            "trending_topics": [],
            "errors": []
        }
        
        try:
            await self._ensure_valid_token()
            
            # Collect from each subreddit
            for subreddit in self.CRYPTO_SUBREDDITS[:5]:  # Limit to avoid rate limits
                try:
                    subreddit_results = await self._collect_subreddit_data(subreddit)
                    
                    results["posts_collected"] += subreddit_results["posts"]
                    results["comments_collected"] += subreddit_results["comments"]
                    
                    # Update sentiment distribution
                    for category, count in subreddit_results.get("sentiment", {}).items():
                        results["sentiment_distribution"][category] = \
                            results["sentiment_distribution"].get(category, 0) + count
                            
                    # Update crypto mentions
                    for symbol, count in subreddit_results.get("crypto_mentions", {}).items():
                        results["crypto_mentions"][symbol] = \
                            results["crypto_mentions"].get(symbol, 0) + count
                            
                except Exception as e:
                    error_msg = f"Failed to collect from r/{subreddit}: {str(e)}"
                    logger.warning(error_msg)
                    results["errors"].append(error_msg)
                    
            self.stats["last_collection"] = datetime.now(timezone.utc).isoformat()
            self.stats["posts_processed"] += results["posts_collected"] + results["comments_collected"]
            
            # Log collector health
            await self.database.log_collector_health(
                collector_name=self.collector_name,
                status="healthy",
                metadata=results
            )
            
        except Exception as e:
            error_msg = f"Reddit collection failed: {str(e)}"
            logger.error(error_msg, error=str(e))
            results["errors"].append(error_msg)
            self.stats["errors"] += 1
            
            await self.database.log_collector_health(
                collector_name=self.collector_name,
                status="error",
                metadata={"error": str(e)}
            )
            
        return results
        
    async def _collect_subreddit_data(self, subreddit: str) -> Dict[str, Any]:
        """
        Collect posts and comments from a subreddit
        
        Args:
            subreddit: Subreddit name
            
        Returns:
            Collection results
        """
        results = {
            "posts": 0,
            "comments": 0,
            "sentiment": {"positive": 0, "negative": 0, "neutral": 0},
            "crypto_mentions": {}
        }
        
        # Get hot posts
        posts = await self._get_subreddit_posts(subreddit, listing="hot", limit=25)
        
        for post in posts:
            # Process post
            processed_post = await self._process_and_store_post(post, subreddit)
            if processed_post:
                results["posts"] += 1
                
                # Update sentiment
                sentiment_cat = processed_post.get("sentiment_category", "neutral")
                if "positive" in sentiment_cat:
                    results["sentiment"]["positive"] += 1
                elif "negative" in sentiment_cat:
                    results["sentiment"]["negative"] += 1
                else:
                    results["sentiment"]["neutral"] += 1
                    
                # Update crypto mentions
                for symbol in processed_post.get("mentioned_cryptos", []):
                    results["crypto_mentions"][symbol] = \
                        results["crypto_mentions"].get(symbol, 0) + 1
                        
            # Get top comments for this post
            post_id = post.get("id")
            if post_id:
                comments = await self._get_post_comments(post_id, limit=10)
                
                for comment in comments:
                    processed_comment = await self._process_and_store_comment(
                        comment,
                        subreddit,
                        post_id
                    )
                    if processed_comment:
                        results["comments"] += 1
                        
                        # Update sentiment
                        sentiment_cat = processed_comment.get("sentiment_category", "neutral")
                        if "positive" in sentiment_cat:
                            results["sentiment"]["positive"] += 1
                        elif "negative" in sentiment_cat:
                            results["sentiment"]["negative"] += 1
                        else:
                            results["sentiment"]["neutral"] += 1
                            
                        # Update crypto mentions
                        for symbol in processed_comment.get("mentioned_cryptos", []):
                            results["crypto_mentions"][symbol] = \
                                results["crypto_mentions"].get(symbol, 0) + 1
                                
        return results
        
    async def _get_subreddit_posts(
        self,
        subreddit: str,
        listing: str = "hot",
        limit: int = 25
    ) -> List[Dict]:
        """
        Get posts from a subreddit
        
        Args:
            subreddit: Subreddit name
            listing: Listing type (hot, new, top, rising)
            limit: Number of posts to retrieve
            
        Returns:
            List of posts
        """
        await self._ensure_valid_token()
        
        endpoint = f"r/{subreddit}/{listing}"
        params = {"limit": min(limit, 100)}
        
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "User-Agent": self.user_agent
        }
        
        url = f"{self.api_url}/{endpoint}"
        
        try:
            async with self.session.get(url, params=params, headers=headers) as response:
                response.raise_for_status()
                data = await response.json()
                
                posts = []
                for child in data.get("data", {}).get("children", []):
                    posts.append(child.get("data", {}))
                    
                return posts
                
        except Exception as e:
            logger.error(f"Failed to get posts from r/{subreddit}", error=str(e))
            return []
            
    async def _get_post_comments(self, post_id: str, limit: int = 10) -> List[Dict]:
        """Get top comments for a post"""
        await self._ensure_valid_token()
        
        endpoint = f"comments/{post_id}"
        params = {"limit": min(limit, 100), "depth": 1}  # Only top-level comments
        
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "User-Agent": self.user_agent
        }
        
        url = f"{self.api_url}/{endpoint}"
        
        try:
            async with self.session.get(url, params=params, headers=headers) as response:
                response.raise_for_status()
                data = await response.json()
                
                # Reddit returns [post_listing, comment_listing]
                if len(data) < 2:
                    return []
                    
                comments = []
                for child in data[1].get("data", {}).get("children", []):
                    comment_data = child.get("data", {})
                    if comment_data.get("body"):  # Has text
                        comments.append(comment_data)
                        
                return comments
                
        except Exception as e:
            logger.error(f"Failed to get comments for post {post_id}", error=str(e))
            return []
            
    async def _process_and_store_post(
        self,
        post: Dict,
        subreddit: str
    ) -> Optional[Dict]:
        """Process and store Reddit post"""
        try:
            # Get post content
            title = post.get("title", "")
            selftext = post.get("selftext", "")
            text = f"{title}. {selftext}".strip()
            
            if not text:
                return None
                
            # Check for bot
            author = post.get("author", "")
            if self.is_bot(author):
                return None
                
            # Clean text
            cleaned_text = self.clean_text(text)
            
            # Analyze sentiment
            sentiment_scores, sentiment_category = self.analyze_sentiment(cleaned_text)
            
            # Extract crypto mentions
            mentioned_cryptos = self.extract_crypto_mentions(text)
            
            # Calculate engagement score
            upvotes = post.get("ups", 0)
            num_comments = post.get("num_comments", 0)
            awards = post.get("total_awards_received", 0)
            engagement_score = upvotes + (num_comments * 2) + (awards * 5)
            
            # Create timestamp
            created_utc = post.get("created_utc")
            timestamp = datetime.fromtimestamp(created_utc, tz=timezone.utc) if created_utc else datetime.now(timezone.utc)
            
            # Store for each mentioned crypto
            for symbol in mentioned_cryptos:
                sentiment_data = {
                    "symbol": symbol,
                    "source": "reddit",
                    "text": text[:1000],  # Limit text length
                    "sentiment_score": sentiment_scores.get("compound", 0.0),
                    "sentiment_category": sentiment_category.value,
                    "sentiment_positive": sentiment_scores.get("positive", 0.0),
                    "sentiment_negative": sentiment_scores.get("negative", 0.0),
                    "sentiment_neutral": sentiment_scores.get("neutral", 0.0),
                    "timestamp": timestamp,
                    "author_id": author,
                    "author_username": author,
                    "is_influencer": False,
                    "engagement_score": engagement_score,
                    "like_count": upvotes,
                    "retweet_count": 0,  # Not applicable
                    "reply_count": num_comments,
                    "post_id": post.get("id"),
                    "metadata": {
                        "subreddit": subreddit,
                        "post_id": post.get("id"),
                        "awards": awards,
                        "url": post.get("url")
                    }
                }
                
                await self.database.store_social_sentiment(sentiment_data)
                
            return {
                "text": text,
                "sentiment_category": sentiment_category.value,
                "mentioned_cryptos": mentioned_cryptos,
                "engagement_score": engagement_score
            }
            
        except Exception as e:
            logger.error("Failed to process Reddit post", error=str(e))
            return None
            
    async def _process_and_store_comment(
        self,
        comment: Dict,
        subreddit: str,
        post_id: str
    ) -> Optional[Dict]:
        """Process and store Reddit comment"""
        try:
            text = comment.get("body", "")
            if not text or len(text) < 10:  # Skip very short comments
                return None
                
            # Check for bot
            author = comment.get("author", "")
            if self.is_bot(author):
                return None
                
            # Clean text
            cleaned_text = self.clean_text(text)
            
            # Analyze sentiment
            sentiment_scores, sentiment_category = self.analyze_sentiment(cleaned_text)
            
            # Extract crypto mentions
            mentioned_cryptos = self.extract_crypto_mentions(text)
            
            if not mentioned_cryptos:  # Only store comments mentioning crypto
                return None
                
            # Calculate engagement score
            upvotes = comment.get("ups", 0)
            engagement_score = upvotes
            
            # Create timestamp
            created_utc = comment.get("created_utc")
            timestamp = datetime.fromtimestamp(created_utc, tz=timezone.utc) if created_utc else datetime.now(timezone.utc)
            
            # Store for each mentioned crypto
            for symbol in mentioned_cryptos:
                sentiment_data = {
                    "symbol": symbol,
                    "source": "reddit",
                    "text": text[:1000],
                    "sentiment_score": sentiment_scores.get("compound", 0.0),
                    "sentiment_category": sentiment_category.value,
                    "sentiment_positive": sentiment_scores.get("positive", 0.0),
                    "sentiment_negative": sentiment_scores.get("negative", 0.0),
                    "sentiment_neutral": sentiment_scores.get("neutral", 0.0),
                    "timestamp": timestamp,
                    "author_id": author,
                    "author_username": author,
                    "is_influencer": False,
                    "engagement_score": engagement_score,
                    "like_count": upvotes,
                    "retweet_count": 0,
                    "reply_count": 0,
                    "post_id": comment.get("id"),
                    "metadata": {
                        "subreddit": subreddit,
                        "parent_post_id": post_id,
                        "comment_id": comment.get("id"),
                        "is_comment": True
                    }
                }
                
                await self.database.store_social_sentiment(sentiment_data)
                
            return {
                "text": text,
                "sentiment_category": sentiment_category.value,
                "mentioned_cryptos": mentioned_cryptos,
                "engagement_score": engagement_score
            }
            
        except Exception as e:
            logger.error("Failed to process Reddit comment", error=str(e))
            return None
