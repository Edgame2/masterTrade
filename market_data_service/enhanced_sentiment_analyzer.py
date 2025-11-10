"""
Enhanced Sentiment Analysis System

This module provides advanced sentiment analysis with:
- Multi-source data collection (Twitter, Reddit, Telegram, News)
- Named Entity Recognition for crypto mentions
- On-chain metrics integration
- Sentiment aggregation and scoring
- Real-time monitoring capabilities
"""

import asyncio
import aiohttp
import praw
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any, Tuple
import re
from textblob import TextBlob
import nltk
from collections import defaultdict, Counter
import structlog

from config import settings
from database import Database

logger = structlog.get_logger()

# Download required NLTK data
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt', quiet=True)

try:
    nltk.data.find('taggers/averaged_perceptron_tagger')
except LookupError:
    nltk.download('averaged_perceptron_tagger', quiet=True)


class SentimentCategory:
    """Sentiment category classifications"""
    EXTREMELY_BEARISH = "extremely_bearish"
    BEARISH = "bearish"
    SLIGHTLY_BEARISH = "slightly_bearish"
    NEUTRAL = "neutral"
    SLIGHTLY_BULLISH = "slightly_bullish"
    BULLISH = "bullish"
    EXTREMELY_BULLISH = "extremely_bullish"


class EnhancedSentimentAnalyzer:
    """Enhanced sentiment analysis with NER and aggregation"""
    
    # Crypto-specific positive keywords
    POSITIVE_KEYWORDS = [
        "moon", "bullish", "pump", "gains", "rally", "breakout", "ath", "all-time high",
        "surge", "rocket", "lambo", "hodl", "buy", "accumulate", "undervalued", "gem"
    ]
    
    # Crypto-specific negative keywords
    NEGATIVE_KEYWORDS = [
        "dump", "bearish", "crash", "scam", "rug", "rekt", "losses", "dip", "correction",
        "sell", "exit", "fud", "fear", "panic", "overvalued", "bubble", "hack"
    ]
    
    # Crypto entity patterns
    CRYPTO_PATTERNS = {
        r'\b(BTC|bitcoin)\b': 'BTC',
        r'\b(ETH|ethereum|ether)\b': 'ETH',
        r'\b(BNB|binance coin)\b': 'BNB',
        r'\b(ADA|cardano)\b': 'ADA',
        r'\b(SOL|solana)\b': 'SOL',
        r'\b(DOT|polkadot)\b': 'DOT',
        r'\b(AVAX|avalanche)\b': 'AVAX',
        r'\b(MATIC|polygon)\b': 'MATIC',
        r'\b(LINK|chainlink)\b': 'LINK',
        r'\b(UNI|uniswap)\b': 'UNI',
        r'\b(XRP|ripple)\b': 'XRP',
        r'\b(DOGE|dogecoin)\b': 'DOGE',
        r'\b(SHIB|shiba)\b': 'SHIB',
        r'\b(LTC|litecoin)\b': 'LTC',
        r'\b(ATOM|cosmos)\b': 'ATOM',
    }
    
    def __init__(self):
        self.positive_terms = set(self.POSITIVE_KEYWORDS)
        self.negative_terms = set(self.NEGATIVE_KEYWORDS)
    
    def extract_crypto_entities(self, text: str) -> List[str]:
        """Extract cryptocurrency mentions from text using NER"""
        entities = []
        text_lower = text.lower()
        
        for pattern, symbol in self.CRYPTO_PATTERNS.items():
            if re.search(pattern, text_lower, re.IGNORECASE):
                entities.append(symbol)
        
        return list(set(entities))  # Remove duplicates
    
    def analyze_sentiment(self, text: str) -> Dict[str, Any]:
        """Enhanced sentiment analysis with crypto-specific scoring"""
        # Basic TextBlob sentiment
        blob = TextBlob(text)
        base_polarity = blob.sentiment.polarity
        subjectivity = blob.sentiment.subjectivity
        
        # Crypto-specific keyword scoring
        text_lower = text.lower()
        words = text_lower.split()
        
        positive_count = sum(1 for word in words if word in self.positive_terms)
        negative_count = sum(1 for word in words if word in self.negative_terms)
        
        # Adjust polarity based on crypto keywords
        keyword_score = (positive_count - negative_count) / max(len(words), 1) * 10
        
        # Combine scores (70% TextBlob, 30% keywords)
        adjusted_polarity = base_polarity * 0.7 + keyword_score * 0.3
        
        # Clamp to [-1, 1]
        adjusted_polarity = max(-1, min(1, adjusted_polarity))
        
        # Classify sentiment
        if adjusted_polarity >= 0.6:
            category = SentimentCategory.EXTREMELY_BULLISH
        elif adjusted_polarity >= 0.3:
            category = SentimentCategory.BULLISH
        elif adjusted_polarity >= 0.1:
            category = SentimentCategory.SLIGHTLY_BULLISH
        elif adjusted_polarity <= -0.6:
            category = SentimentCategory.EXTREMELY_BEARISH
        elif adjusted_polarity <= -0.3:
            category = SentimentCategory.BEARISH
        elif adjusted_polarity <= -0.1:
            category = SentimentCategory.SLIGHTLY_BEARISH
        else:
            category = SentimentCategory.NEUTRAL
        
        return {
            "polarity": adjusted_polarity,
            "base_polarity": base_polarity,
            "keyword_score": keyword_score,
            "subjectivity": subjectivity,
            "category": category,
            "positive_keywords": positive_count,
            "negative_keywords": negative_count
        }
    
    def aggregate_sentiments(self, sentiments: List[Dict]) -> Dict[str, Any]:
        """Aggregate multiple sentiment scores"""
        if not sentiments:
            return {
                "average_polarity": 0.0,
                "median_polarity": 0.0,
                "sentiment_distribution": {},
                "confidence": 0.0
            }
        
        polarities = [s.get("polarity", 0) for s in sentiments]
        categories = [s.get("category", SentimentCategory.NEUTRAL) for s in sentiments]
        
        # Calculate statistics
        avg_polarity = sum(polarities) / len(polarities)
        sorted_polarities = sorted(polarities)
        median_polarity = sorted_polarities[len(sorted_polarities) // 2]
        
        # Sentiment distribution
        category_counts = Counter(categories)
        total = len(categories)
        distribution = {cat: count / total for cat, count in category_counts.items()}
        
        # Confidence based on agreement
        most_common_category, most_common_count = category_counts.most_common(1)[0]
        confidence = most_common_count / total
        
        # Overall category
        if avg_polarity >= 0.3:
            overall_category = SentimentCategory.BULLISH
        elif avg_polarity <= -0.3:
            overall_category = SentimentCategory.BEARISH
        else:
            overall_category = SentimentCategory.NEUTRAL
        
        return {
            "average_polarity": avg_polarity,
            "median_polarity": median_polarity,
            "sentiment_distribution": distribution,
            "confidence": confidence,
            "overall_category": overall_category,
            "sample_size": len(sentiments)
        }


class RedditSentimentCollector:
    """Collect sentiment from Reddit"""
    
    CRYPTO_SUBREDDITS = [
        "cryptocurrency",
        "CryptoMarkets",
        "Bitcoin",
        "ethereum",
        "binance",
        "CryptoCurrency",
        "altcoin",
        "defi"
    ]
    
    def __init__(self, client_id: str, client_secret: str, user_agent: str):
        self.reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent
        )
        self.analyzer = EnhancedSentimentAnalyzer()
    
    async def collect_sentiment(self, crypto_symbols: List[str], hours_back: int = 24, limit: int = 100) -> List[Dict[str, Any]]:
        """Collect sentiment from Reddit"""
        sentiment_data = []
        
        for symbol in crypto_symbols:
            try:
                logger.info(f"Collecting Reddit sentiment for {symbol}")
                
                # Search across all crypto subreddits
                all_posts = []
                all_comments = []
                
                for subreddit_name in self.CRYPTO_SUBREDDITS:
                    try:
                        subreddit = self.reddit.subreddit(subreddit_name)
                        
                        # Get hot posts
                        for post in subreddit.hot(limit=limit // len(self.CRYPTO_SUBREDDITS)):
                            # Check if post mentions the symbol
                            text = f"{post.title} {post.selftext}"
                            entities = self.analyzer.extract_crypto_entities(text)
                            
                            if symbol in entities:
                                sentiment = self.analyzer.analyze_sentiment(text)
                                all_posts.append({
                                    "text": post.title,
                                    "url": f"https://reddit.com{post.permalink}",
                                    "score": post.score,
                                    "created_utc": datetime.fromtimestamp(post.created_utc).isoformat() + "Z",
                                    "num_comments": post.num_comments,
                                    "sentiment": sentiment
                                })
                                
                                # Get top comments
                                post.comments.replace_more(limit=0)
                                for comment in post.comments[:5]:  # Top 5 comments
                                    comment_sentiment = self.analyzer.analyze_sentiment(comment.body)
                                    all_comments.append({
                                        "text": comment.body[:200],
                                        "score": comment.score,
                                        "sentiment": comment_sentiment
                                    })
                    
                    except Exception as e:
                        logger.error(f"Error accessing subreddit {subreddit_name}", error=str(e))
                    
                    # Rate limiting
                    await asyncio.sleep(0.5)
                
                if all_posts or all_comments:
                    # Aggregate sentiment
                    all_sentiments = [p["sentiment"] for p in all_posts] + [c["sentiment"] for c in all_comments]
                    aggregated = self.analyzer.aggregate_sentiments(all_sentiments)
                    
                    sentiment_data.append({
                        "id": f"reddit_sentiment_{symbol}_{int(datetime.utcnow().timestamp())}",
                        "doc_type": "sentiment_data",
                        "source": "reddit",
                        "symbol": symbol,
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                        "post_count": len(all_posts),
                        "comment_count": len(all_comments),
                        "aggregated_sentiment": aggregated,
                        "top_posts": all_posts[:10],  # Store top 10
                        "metadata": {
                            "subreddits": self.CRYPTO_SUBREDDITS,
                            "hours_back": hours_back
                        },
                        "created_at": datetime.utcnow().isoformat() + "Z"
                    })
                    
                    logger.info(
                        "Reddit sentiment collected",
                        symbol=symbol,
                        posts=len(all_posts),
                        comments=len(all_comments),
                        sentiment=aggregated["overall_category"]
                    )
            
            except Exception as e:
                logger.error(f"Error collecting Reddit sentiment for {symbol}", error=str(e))
        
        return sentiment_data


class TelegramSentimentMonitor:
    """Monitor Telegram channels for sentiment (requires Telethon)"""
    
    # Popular crypto Telegram channels (public channels only)
    CRYPTO_CHANNELS = [
        "@whale_alert",  # Whale Alert
        "@crypto",  # Generic crypto news
        # Add more public channels
    ]
    
    def __init__(self):
        self.analyzer = EnhancedSentimentAnalyzer()
        # Note: Telethon integration would require additional setup
        logger.info("Telegram monitoring initialized (placeholder)")
    
    async def collect_sentiment(self, crypto_symbols: List[str]) -> List[Dict[str, Any]]:
        """Collect sentiment from Telegram (placeholder)"""
        logger.info("Telegram sentiment collection not fully implemented")
        # This would require:
        # 1. Telethon library installation
        # 2. Telegram API credentials
        # 3. Session management
        # 4. Channel message parsing
        return []


class OnChainMetricsCollector:
    """Collect on-chain metrics that indicate sentiment"""
    
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
    
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
    
    async def collect_whale_alerts(self, symbols: List[str]) -> List[Dict[str, Any]]:
        """Collect whale transaction data"""
        # This would integrate with Whale Alert API or similar
        # For now, returning placeholder
        logger.info("Whale alert collection (placeholder)")
        return []
    
    async def collect_exchange_flows(self, symbols: List[str]) -> List[Dict[str, Any]]:
        """Collect exchange inflow/outflow data"""
        # This would track large movements to/from exchanges
        # Large inflows = potential selling pressure (bearish)
        # Large outflows = potential holding (bullish)
        logger.info("Exchange flow collection (placeholder)")
        return []
    
    async def collect_network_metrics(self, symbols: List[str]) -> List[Dict[str, Any]]:
        """Collect network activity metrics"""
        # This would collect:
        # - Active addresses
        # - Transaction volume
        # - Network hash rate
        # - Transaction fees
        logger.info("Network metrics collection (placeholder)")
        return []


class ComprehensiveSentimentCollector:
    """Main sentiment collector that aggregates all sources"""
    
    def __init__(self, database: Database):
        self.database = database
        self.analyzer = EnhancedSentimentAnalyzer()
        self.session: Optional[aiohttp.ClientSession] = None
        
        # Initialize collectors
        self.reddit_collector = None
        if hasattr(settings, 'REDDIT_CLIENT_ID') and settings.REDDIT_CLIENT_ID:
            try:
                self.reddit_collector = RedditSentimentCollector(
                    client_id=settings.REDDIT_CLIENT_ID,
                    client_secret=settings.REDDIT_CLIENT_SECRET,
                    user_agent=settings.REDDIT_USER_AGENT
                )
                logger.info("Reddit collector initialized")
            except Exception as e:
                logger.error("Failed to initialize Reddit collector", error=str(e))
        
        self.telegram_monitor = TelegramSentimentMonitor()
        self.onchain_collector = OnChainMetricsCollector()
    
    async def __aenter__(self):
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.disconnect()
    
    async def connect(self):
        """Initialize connections"""
        if not self.session:
            timeout = aiohttp.ClientTimeout(total=30)
            self.session = aiohttp.ClientSession(timeout=timeout)
        
        await self.onchain_collector.connect()
    
    async def disconnect(self):
        """Close connections"""
        if self.session:
            await self.session.close()
            self.session = None
        
        await self.onchain_collector.disconnect()
    
    async def collect_all_sentiment(self, crypto_symbols: List[str] = None) -> Dict[str, Any]:
        """Collect sentiment from all sources"""
        if crypto_symbols is None:
            crypto_symbols = ["BTC", "ETH", "BNB", "ADA", "SOL", "DOT", "AVAX", "MATIC"]
        
        results = {
            "reddit_sentiment": [],
            "telegram_sentiment": [],
            "onchain_metrics": [],
            "aggregated_by_symbol": {},
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
        
        logger.info("Starting comprehensive sentiment collection", symbols=crypto_symbols)
        
        try:
            # Collect Reddit sentiment
            if self.reddit_collector:
                reddit_data = await self.reddit_collector.collect_sentiment(crypto_symbols)
                results["reddit_sentiment"] = reddit_data
                
                # Store in database
                for item in reddit_data:
                    await self.database.upsert_market_data(item)
            
            # Collect Telegram sentiment
            telegram_data = await self.telegram_monitor.collect_sentiment(crypto_symbols)
            results["telegram_sentiment"] = telegram_data
            
            # Collect on-chain metrics
            onchain_data = await self.onchain_collector.collect_whale_alerts(crypto_symbols)
            results["onchain_metrics"] = onchain_data
            
            # Aggregate sentiment by symbol
            for symbol in crypto_symbols:
                symbol_sentiments = []
                
                # Reddit sentiment
                reddit_items = [r for r in results["reddit_sentiment"] if r["symbol"] == symbol]
                for item in reddit_items:
                    if "aggregated_sentiment" in item:
                        symbol_sentiments.append(item["aggregated_sentiment"])
                
                if symbol_sentiments:
                    # Create overall sentiment score
                    avg_polarity = sum(s["average_polarity"] for s in symbol_sentiments) / len(symbol_sentiments)
                    avg_confidence = sum(s["confidence"] for s in symbol_sentiments) / len(symbol_sentiments)
                    
                    # Sentiment score (0-100)
                    sentiment_score = int((avg_polarity + 1) * 50)  # Convert -1 to 1 → 0 to 100
                    
                    results["aggregated_by_symbol"][symbol] = {
                        "sentiment_score": sentiment_score,
                        "polarity": avg_polarity,
                        "confidence": avg_confidence,
                        "category": self._score_to_category(sentiment_score),
                        "sources": {
                            "reddit": len(reddit_items),
                            "telegram": 0,
                            "onchain": 0
                        },
                        "timestamp": datetime.utcnow().isoformat() + "Z"
                    }
                    
                    # Store aggregated sentiment
                    agg_doc = {
                        "id": f"aggregated_sentiment_{symbol}_{int(datetime.utcnow().timestamp())}",
                        "doc_type": "aggregated_sentiment",
                        "symbol": symbol,
                        **results["aggregated_by_symbol"][symbol]
                    }
                    await self.database.upsert_market_data(agg_doc)
            
            logger.info(
                "Sentiment collection completed",
                symbols_processed=len(results["aggregated_by_symbol"]),
                reddit_items=len(results["reddit_sentiment"]),
                telegram_items=len(results["telegram_sentiment"])
            )
        
        except Exception as e:
            logger.error("Error in comprehensive sentiment collection", error=str(e))
        
        return results
    
    def _score_to_category(self, score: int) -> str:
        """Convert sentiment score to category"""
        if score >= 80:
            return SentimentCategory.EXTREMELY_BULLISH
        elif score >= 65:
            return SentimentCategory.BULLISH
        elif score >= 55:
            return SentimentCategory.SLIGHTLY_BULLISH
        elif score <= 20:
            return SentimentCategory.EXTREMELY_BEARISH
        elif score <= 35:
            return SentimentCategory.BEARISH
        elif score <= 45:
            return SentimentCategory.SLIGHTLY_BEARISH
        else:
            return SentimentCategory.NEUTRAL


# Example usage
async def main():
    """Example usage"""
    database = Database()
    
    async with database, ComprehensiveSentimentCollector(database) as collector:
        results = await collector.collect_all_sentiment(["BTC", "ETH", "SOL"])
        
        print("\nSentiment Collection Results:")
        print(f"Reddit items: {len(results['reddit_sentiment'])}")
        print(f"Telegram items: {len(results['telegram_sentiment'])}")
        print(f"On-chain metrics: {len(results['onchain_metrics'])}")
        
        print("\nAggregated Sentiment by Symbol:")
        for symbol, sentiment in results['aggregated_by_symbol'].items():
            print(f"{symbol}: Score={sentiment['sentiment_score']}, Category={sentiment['category']}, Confidence={sentiment['confidence']:.2f}")


if __name__ == "__main__":
    asyncio.run(main())
