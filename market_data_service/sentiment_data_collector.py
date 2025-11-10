"""
Sentiment Data Collector for Market Data Service

This module collects sentiment data from various sources:
- Crypto Fear & Greed Index
- Financial news sentiment analysis
- Social media sentiment (Twitter/Reddit)
- Market indicators and sentiment metrics
"""

import asyncio
import aiohttp
import json
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
import re
from textblob import TextBlob
import structlog

from config import settings
from database import Database

logger = structlog.get_logger()

class SentimentDataCollector:
    """Collects sentiment data from various sources"""
    
    def __init__(self, database: Database):
        self.database = database
        self.session: Optional[aiohttp.ClientSession] = None
        
    async def __aenter__(self):
        """Async context manager entry"""
        await self.connect()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.disconnect()
        
    async def connect(self):
        """Initialize HTTP session"""
        if not self.session:
            timeout = aiohttp.ClientTimeout(total=30)
            self.session = aiohttp.ClientSession(timeout=timeout)
            
    async def disconnect(self):
        """Close HTTP session"""
        if self.session:
            await self.session.close()
            self.session = None
            
    async def _make_request(self, url: str, headers: Dict = None, params: Dict = None) -> Dict:
        """Make HTTP request with error handling"""
        if not self.session:
            await self.connect()
            
        try:
            async with self.session.get(url, headers=headers, params=params) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error_text = await response.text()
                    logger.error(
                        "API request failed",
                        url=url,
                        status=response.status,
                        error=error_text
                    )
                    return {}
                    
        except Exception as e:
            logger.error("Error making request", url=url, error=str(e))
            return {}
            
    def _analyze_text_sentiment(self, text: str) -> Dict[str, float]:
        """Analyze sentiment of text using TextBlob"""
        try:
            blob = TextBlob(text)
            return {
                "polarity": blob.sentiment.polarity,  # -1 to 1 (negative to positive)
                "subjectivity": blob.sentiment.subjectivity  # 0 to 1 (objective to subjective)
            }
        except Exception as e:
            logger.error("Error analyzing text sentiment", error=str(e))
            return {"polarity": 0.0, "subjectivity": 0.0}
            
    async def collect_fear_greed_index(self) -> Optional[Dict[str, Any]]:
        """Collect Crypto Fear & Greed Index"""
        if not settings.SENTIMENT_SOURCES.get("fear_greed_index", False):
            return None
            
        try:
            # Fear & Greed Index API (free)
            url = f"{settings.FEAR_GREED_API_URL}?limit=1"
            response = await self._make_request(url)
            
            if response and "data" in response and len(response["data"]) > 0:
                data = response["data"][0]
                
                sentiment_data = {
                    "id": f"fear_greed_{int(datetime.utcnow().timestamp())}",
                    "source": "fear_greed_index",
                    "type": "global_crypto_sentiment",
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "value": int(data["value"]),
                    "classification": data["value_classification"],
                    "metadata": {
                        "time_until_update": data.get("time_until_update"),
                        "raw_data": data
                    },
                    "created_at": datetime.utcnow().isoformat() + "Z"
                }
                
                logger.info(
                    "Fear & Greed Index collected",
                    value=sentiment_data["value"],
                    classification=sentiment_data["classification"]
                )
                
                return sentiment_data
                
        except Exception as e:
            logger.error("Error collecting Fear & Greed Index", error=str(e))
            
        return None
        
    async def collect_news_sentiment(self, crypto_symbols: List[str] = None) -> List[Dict[str, Any]]:
        """Collect news sentiment for cryptocurrencies"""
        if not settings.SENTIMENT_SOURCES.get("news_sentiment", False) or not settings.NEWS_API_KEY:
            return []
            
        if crypto_symbols is None:
            crypto_symbols = ["BTC", "ETH", "ADA", "SOL", "DOT"]
            
        sentiment_data = []
        
        for symbol in crypto_symbols:
            try:
                # Get keywords for this crypto
                keywords = settings.CRYPTO_SENTIMENT_KEYWORDS.get(symbol, [symbol.lower()])
                query = " OR ".join(keywords)
                
                # NewsAPI.org endpoint
                url = "https://newsapi.org/v2/everything"
                headers = {"X-API-Key": settings.NEWS_API_KEY}
                params = {
                    "q": query,
                    "language": "en",
                    "sortBy": "publishedAt",
                    "from": (datetime.utcnow() - timedelta(hours=24)).isoformat(),
                    "pageSize": 20
                }
                
                response = await self._make_request(url, headers=headers, params=params)
                
                if response and "articles" in response:
                    articles = response["articles"]
                    
                    # Analyze sentiment for each article
                    total_polarity = 0.0
                    total_subjectivity = 0.0
                    article_count = 0
                    article_sentiments = []
                    
                    for article in articles[:10]:  # Analyze top 10 articles
                        if article.get("title") and article.get("description"):
                            text = f"{article['title']} {article['description']}"
                            sentiment = self._analyze_text_sentiment(text)
                            
                            article_sentiments.append({
                                "title": article["title"],
                                "url": article["url"],
                                "publishedAt": article["publishedAt"],
                                "source": article["source"]["name"],
                                "sentiment": sentiment
                            })
                            
                            total_polarity += sentiment["polarity"]
                            total_subjectivity += sentiment["subjectivity"]
                            article_count += 1
                            
                    if article_count > 0:
                        avg_polarity = total_polarity / article_count
                        avg_subjectivity = total_subjectivity / article_count
                        
                        # Classify sentiment
                        if avg_polarity > 0.1:
                            classification = "positive"
                        elif avg_polarity < -0.1:
                            classification = "negative"
                        else:
                            classification = "neutral"
                            
                        sentiment_data.append({
                            "id": f"news_sentiment_{symbol}_{int(datetime.utcnow().timestamp())}",
                            "source": "news_sentiment",
                            "type": "crypto_news_sentiment",
                            "symbol": symbol,
                            "timestamp": datetime.utcnow().isoformat() + "Z",
                            "polarity": avg_polarity,
                            "subjectivity": avg_subjectivity,
                            "classification": classification,
                            "article_count": article_count,
                            "metadata": {
                                "articles": article_sentiments,
                                "keywords_used": keywords
                            },
                            "created_at": datetime.utcnow().isoformat() + "Z"
                        })
                        
                        logger.info(
                            "News sentiment collected",
                            symbol=symbol,
                            polarity=avg_polarity,
                            classification=classification,
                            article_count=article_count
                        )
                        
                # Rate limiting
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error("Error collecting news sentiment", symbol=symbol, error=str(e))
                
        return sentiment_data
        
    async def collect_social_sentiment(self, crypto_symbols: List[str] = None) -> List[Dict[str, Any]]:
        """Collect social media sentiment (Twitter/Reddit)"""
        if not settings.SENTIMENT_SOURCES.get("social_sentiment", False):
            return []
            
        sentiment_data = []
        
        # Twitter sentiment collection (if Twitter API is configured)
        if settings.TWITTER_BEARER_TOKEN:
            twitter_sentiment = await self._collect_twitter_sentiment(crypto_symbols)
            sentiment_data.extend(twitter_sentiment)
            
        # Reddit sentiment collection (if Reddit API is configured)
        if settings.REDDIT_CLIENT_ID and settings.REDDIT_CLIENT_SECRET:
            reddit_sentiment = await self._collect_reddit_sentiment(crypto_symbols)
            sentiment_data.extend(reddit_sentiment)
            
        return sentiment_data
        
    async def _collect_twitter_sentiment(self, crypto_symbols: List[str]) -> List[Dict[str, Any]]:
        """Collect sentiment from Twitter API v2"""
        if crypto_symbols is None:
            crypto_symbols = ["BTC", "ETH", "ADA", "SOL", "DOT"]
            
        sentiment_data = []
        
        for symbol in crypto_symbols:
            try:
                keywords = settings.CRYPTO_SENTIMENT_KEYWORDS.get(symbol, [symbol.lower()])
                query = " OR ".join([f'"{keyword}"' for keyword in keywords])
                
                # Twitter API v2 search endpoint
                url = "https://api.twitter.com/2/tweets/search/recent"
                headers = {"Authorization": f"Bearer {settings.TWITTER_BEARER_TOKEN}"}
                params = {
                    "query": query,
                    "max_results": 50,
                    "tweet.fields": "created_at,public_metrics,lang",
                    "start_time": (datetime.utcnow() - timedelta(hours=24)).isoformat()
                }
                
                response = await self._make_request(url, headers=headers, params=params)
                
                if response and "data" in response:
                    tweets = response["data"]
                    
                    # Analyze sentiment for each tweet
                    total_polarity = 0.0
                    total_subjectivity = 0.0
                    tweet_count = 0
                    tweet_sentiments = []
                    
                    for tweet in tweets:
                        if tweet.get("lang") == "en":  # Only analyze English tweets
                            sentiment = self._analyze_text_sentiment(tweet["text"])
                            
                            tweet_sentiments.append({
                                "id": tweet["id"],
                                "text": tweet["text"][:100] + "...",  # Truncate for storage
                                "created_at": tweet["created_at"],
                                "sentiment": sentiment,
                                "metrics": tweet.get("public_metrics", {})
                            })
                            
                            total_polarity += sentiment["polarity"]
                            total_subjectivity += sentiment["subjectivity"]
                            tweet_count += 1
                            
                    if tweet_count > 0:
                        avg_polarity = total_polarity / tweet_count
                        avg_subjectivity = total_subjectivity / tweet_count
                        
                        # Classify sentiment
                        if avg_polarity > 0.1:
                            classification = "positive"
                        elif avg_polarity < -0.1:
                            classification = "negative"
                        else:
                            classification = "neutral"
                            
                        sentiment_data.append({
                            "id": f"twitter_sentiment_{symbol}_{int(datetime.utcnow().timestamp())}",
                            "source": "twitter_sentiment",
                            "type": "crypto_social_sentiment",
                            "symbol": symbol,
                            "timestamp": datetime.utcnow().isoformat() + "Z",
                            "polarity": avg_polarity,
                            "subjectivity": avg_subjectivity,
                            "classification": classification,
                            "tweet_count": tweet_count,
                            "metadata": {
                                "tweets": tweet_sentiments[:10],  # Store top 10 tweets
                                "keywords_used": keywords
                            },
                            "created_at": datetime.utcnow().isoformat() + "Z"
                        })
                        
                        logger.info(
                            "Twitter sentiment collected",
                            symbol=symbol,
                            polarity=avg_polarity,
                            classification=classification,
                            tweet_count=tweet_count
                        )
                        
                # Rate limiting
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error("Error collecting Twitter sentiment", symbol=symbol, error=str(e))
                
        return sentiment_data
        
    async def _collect_reddit_sentiment(self, crypto_symbols: List[str]) -> List[Dict[str, Any]]:
        """Collect sentiment from Reddit API"""
        # Reddit API implementation would go here
        # For now, returning empty list as Reddit API requires OAuth flow
        logger.info("Reddit sentiment collection not implemented yet")
        return []
        
    async def collect_market_sentiment(self) -> Optional[Dict[str, Any]]:
        """Collect overall market sentiment indicators"""
        if not settings.SENTIMENT_SOURCES.get("market_sentiment", False):
            return None
            
        try:
            # This would collect various market indicators
            # For now, we'll create a simple market sentiment based on available data
            
            sentiment_data = {
                "id": f"market_sentiment_{int(datetime.utcnow().timestamp())}",
                "source": "market_sentiment",
                "type": "global_market_sentiment",
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "indicators": {
                    "vix_level": "unknown",  # Would fetch VIX data
                    "crypto_dominance": "unknown",  # Would fetch BTC dominance
                    "market_cap_change": "unknown"  # Would fetch total crypto market cap change
                },
                "classification": "neutral",  # Would calculate based on indicators
                "confidence": 0.5,
                "metadata": {
                    "data_sources": ["placeholder"],
                    "calculation_method": "composite_indicators"
                },
                "created_at": datetime.utcnow().isoformat() + "Z"
            }
            
            logger.info("Market sentiment collected (placeholder)")
            return sentiment_data
            
        except Exception as e:
            logger.error("Error collecting market sentiment", error=str(e))
            
        return None
        
    async def collect_all_sentiment_data(self, crypto_symbols: List[str] = None) -> Dict[str, List[Dict[str, Any]]]:
        """Collect all types of sentiment data"""
        
        if crypto_symbols is None:
            crypto_symbols = [symbol[:-4] for symbol in settings.DEFAULT_SYMBOLS]  # Remove USDC suffix
            
        results = {
            "fear_greed": [],
            "news_sentiment": [],
            "social_sentiment": [],
            "market_sentiment": []
        }
        
        logger.info("Starting sentiment data collection", crypto_symbols=crypto_symbols)
        
        # Collect Fear & Greed Index
        if settings.SENTIMENT_SOURCES.get("fear_greed_index", False):
            fear_greed = await self.collect_fear_greed_index()
            if fear_greed:
                results["fear_greed"].append(fear_greed)
                await self.database.upsert_sentiment_data(fear_greed)
                
        # Collect News Sentiment
        if settings.SENTIMENT_SOURCES.get("news_sentiment", False):
            news_sentiment = await self.collect_news_sentiment(crypto_symbols)
            results["news_sentiment"] = news_sentiment
            for sentiment in news_sentiment:
                await self.database.upsert_sentiment_data(sentiment)
                
        # Collect Social Media Sentiment
        if settings.SENTIMENT_SOURCES.get("social_sentiment", False):
            social_sentiment = await self.collect_social_sentiment(crypto_symbols)
            results["social_sentiment"] = social_sentiment
            for sentiment in social_sentiment:
                await self.database.upsert_sentiment_data(sentiment)
                
        # Collect Market Sentiment
        if settings.SENTIMENT_SOURCES.get("market_sentiment", False):
            market_sentiment = await self.collect_market_sentiment()
            if market_sentiment:
                results["market_sentiment"].append(market_sentiment)
                await self.database.upsert_sentiment_data(market_sentiment)
                
        logger.info(
            "Sentiment data collection completed",
            fear_greed_count=len(results["fear_greed"]),
            news_sentiment_count=len(results["news_sentiment"]),
            social_sentiment_count=len(results["social_sentiment"]),
            market_sentiment_count=len(results["market_sentiment"])
        )
        
        return results

# Example usage
async def main():
    """Example usage of the sentiment data collector"""
    database = Database()
    
    async with database, SentimentDataCollector(database) as collector:
        # Collect all sentiment data
        results = await collector.collect_all_sentiment_data()
        
        print("Sentiment data collection results:")
        for category, data in results.items():
            print(f"{category}: {len(data)} records")

if __name__ == "__main__":
    asyncio.run(main())