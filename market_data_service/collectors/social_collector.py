"""
Base Social Media Data Collector for Market Data Service

This module provides a base class for collecting social sentiment data from various sources:
- Twitter/X (real-time tweets, influencer tracking)
- Reddit (posts, comments, sentiment from crypto subreddits)
- LunarCrush (aggregated social metrics)
- Discord/Telegram (optional community sentiment)

Features:
- NLP sentiment analysis (VADER for quick sentiment, FinBERT for financial context)
- Rate limiting with adaptive backoff
- Circuit breaker pattern for failure handling
- Bot detection and filtering
- Influencer tracking and weighting
"""

import asyncio
import aiohttp
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Any, List, Tuple
from enum import Enum
import structlog
from collections import defaultdict

# NLP imports
try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    VADER_AVAILABLE = True
except ImportError:
    VADER_AVAILABLE = False
    
try:
    from transformers import AutoTokenizer, AutoModelForSequenceClassification
    import torch
    FINBERT_AVAILABLE = True
except ImportError:
    FINBERT_AVAILABLE = False

from database import Database
from collectors.onchain_collector import CircuitBreaker, RateLimiter, CollectorStatus

logger = structlog.get_logger()


class SentimentScore(Enum):
    """Sentiment classification"""
    VERY_NEGATIVE = "very_negative"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    POSITIVE = "positive"
    VERY_POSITIVE = "very_positive"


class SocialCollector:
    """
    Base class for social media data collectors
    
    Provides common functionality:
    - Sentiment analysis (VADER + FinBERT)
    - Adaptive rate limiting with header parsing
    - Circuit breaker for failure handling
    - Bot detection
    - Data normalization and storage
    """
    
    def __init__(
        self,
        collector_name: str,
        database: Database,
        api_key: Optional[str] = None,
        api_url: Optional[str] = None,
        rate_limit: float = 1.0,
        use_finbert: bool = False,
        redis_cache=None
    ):
        """
        Initialize social collector
        
        Args:
            collector_name: Name of the collector (twitter, reddit, etc.)
            database: Database instance for storage
            api_key: API key for the social media platform
            api_url: Base URL for API requests
            rate_limit: Initial requests per second limit
            use_finbert: Whether to use FinBERT for sentiment analysis
            redis_cache: Optional Redis cache for rate limiter state persistence
        """
        self.collector_name = collector_name
        self.database = database
        self.api_key = api_key
        self.api_url = api_url
        self.redis_cache = redis_cache
        
        # Rate limiting and circuit breaker with Redis support
        self.rate_limiter = RateLimiter(
            max_requests_per_second=rate_limit,
            redis_cache=redis_cache,
            collector_name=collector_name
        )
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=5,
            timeout_seconds=300,
            half_open_max_calls=3,
            half_open_success_threshold=2,
            collector_name=collector_name,
            redis_cache=redis_cache
        )
        
        # HTTP session
        self.session: Optional[aiohttp.ClientSession] = None
        
        # Sentiment analyzers
        self.vader_analyzer = None
        self.finbert_model = None
        self.finbert_tokenizer = None
        self.use_finbert = use_finbert
        
        # Initialize sentiment analyzers
        self._init_sentiment_analyzers()
        
        # Statistics
        self.stats = {
            "posts_processed": 0,
            "sentiment_analyzed": 0,
            "errors": 0,
            "last_collection": None
        }
        
        # Bot detection patterns
        self.bot_patterns = [
            r"bot$",
            r"^bot",
            r"crypto.*bot",
            r"trading.*bot",
            r"auto.*post",
        ]
        
        logger.info(
            f"{collector_name} collector initialized",
            rate_limit=rate_limit,
            vader_available=VADER_AVAILABLE,
            finbert_enabled=use_finbert and FINBERT_AVAILABLE
        )
        
    def _init_sentiment_analyzers(self):
        """Initialize sentiment analysis models"""
        # Initialize VADER (fast, rule-based)
        if VADER_AVAILABLE:
            try:
                self.vader_analyzer = SentimentIntensityAnalyzer()
                logger.info("VADER sentiment analyzer initialized")
            except Exception as e:
                logger.warning("Failed to initialize VADER", error=str(e))
        else:
            logger.warning("VADER not available, install vaderSentiment package")
            
        # Initialize FinBERT (more accurate for financial text)
        if self.use_finbert and FINBERT_AVAILABLE:
            try:
                model_name = "ProsusAI/finbert"
                self.finbert_tokenizer = AutoTokenizer.from_pretrained(model_name)
                self.finbert_model = AutoModelForSequenceClassification.from_pretrained(model_name)
                self.finbert_model.eval()
                logger.info("FinBERT model initialized")
            except Exception as e:
                logger.warning("Failed to initialize FinBERT", error=str(e))
        elif self.use_finbert and not FINBERT_AVAILABLE:
            logger.warning("FinBERT requested but transformers not available")
            
    async def connect(self):
        """Establish HTTP session and load rate limiter & circuit breaker state"""
        if not self.session:
            timeout = aiohttp.ClientTimeout(total=30)
            self.session = aiohttp.ClientSession(timeout=timeout)
            # Load previous state from Redis if available
            await self.rate_limiter.load_state_from_redis()
            await self.circuit_breaker.load_state_from_redis()
            logger.info(f"{self.collector_name} collector connected")
            
    async def disconnect(self):
        """Close HTTP session and save rate limiter & circuit breaker state"""
        if self.session:
            # Save state to Redis before disconnecting
            await self.rate_limiter.save_state_to_redis()
            await self.circuit_breaker.save_state_to_redis()
            await self.session.close()
            self.session = None
            logger.info(f"{self.collector_name} collector disconnected")
            
    def analyze_sentiment_vader(self, text: str) -> Dict[str, float]:
        """
        Analyze sentiment using VADER
        
        Args:
            text: Text to analyze
            
        Returns:
            Sentiment scores (negative, neutral, positive, compound)
        """
        if not self.vader_analyzer:
            return {"negative": 0.0, "neutral": 1.0, "positive": 0.0, "compound": 0.0}
            
        try:
            scores = self.vader_analyzer.polarity_scores(text)
            return scores
        except Exception as e:
            logger.warning("VADER sentiment analysis failed", error=str(e))
            return {"negative": 0.0, "neutral": 1.0, "positive": 0.0, "compound": 0.0}
            
    def analyze_sentiment_finbert(self, text: str) -> Dict[str, float]:
        """
        Analyze sentiment using FinBERT
        
        Args:
            text: Text to analyze
            
        Returns:
            Sentiment scores (negative, neutral, positive)
        """
        if not self.finbert_model or not self.finbert_tokenizer:
            return {"negative": 0.0, "neutral": 1.0, "positive": 0.0}
            
        try:
            # Tokenize and predict
            inputs = self.finbert_tokenizer(
                text,
                return_tensors="pt",
                truncation=True,
                max_length=512,
                padding=True
            )
            
            with torch.no_grad():
                outputs = self.finbert_model(**inputs)
                probabilities = torch.nn.functional.softmax(outputs.logits, dim=-1)
                
            # FinBERT outputs: [positive, negative, neutral]
            scores = probabilities[0].tolist()
            return {
                "positive": scores[0],
                "negative": scores[1],
                "neutral": scores[2]
            }
        except Exception as e:
            logger.warning("FinBERT sentiment analysis failed", error=str(e))
            return {"negative": 0.0, "neutral": 1.0, "positive": 0.0}
            
    def analyze_sentiment(self, text: str) -> Tuple[Dict[str, float], SentimentScore]:
        """
        Analyze sentiment using available analyzers
        
        Args:
            text: Text to analyze
            
        Returns:
            Tuple of (sentiment_scores, sentiment_category)
        """
        # Use FinBERT if available and enabled, otherwise VADER
        if self.finbert_model and self.use_finbert:
            scores = self.analyze_sentiment_finbert(text)
            compound = scores["positive"] - scores["negative"]
        else:
            scores = self.analyze_sentiment_vader(text)
            compound = scores.get("compound", 0.0)
            
        # Categorize sentiment
        if compound <= -0.6:
            category = SentimentScore.VERY_NEGATIVE
        elif compound <= -0.2:
            category = SentimentScore.NEGATIVE
        elif compound <= 0.2:
            category = SentimentScore.NEUTRAL
        elif compound <= 0.6:
            category = SentimentScore.POSITIVE
        else:
            category = SentimentScore.VERY_POSITIVE
            
        self.stats["sentiment_analyzed"] += 1
        
        return scores, category
        
    def is_bot(self, username: str, metadata: Optional[Dict] = None) -> bool:
        """
        Detect if an account is likely a bot
        
        Args:
            username: Username to check
            metadata: Additional account metadata
            
        Returns:
            True if likely a bot
        """
        # Check username patterns
        username_lower = username.lower()
        for pattern in self.bot_patterns:
            if re.search(pattern, username_lower):
                return True
                
        # Check metadata if provided
        if metadata:
            # Very low follower/following ratio might indicate bot
            followers = metadata.get("followers_count", 0)
            following = metadata.get("following_count", 0)
            
            if followers < 10 and following > 1000:
                return True
                
            # Very high posting frequency might indicate bot
            post_count = metadata.get("post_count", 0)
            account_age_days = metadata.get("account_age_days", 365)
            
            if account_age_days > 0:
                posts_per_day = post_count / account_age_days
                if posts_per_day > 100:  # More than 100 posts per day
                    return True
                    
        return False
        
    def extract_crypto_mentions(self, text: str) -> List[str]:
        """
        Extract cryptocurrency mentions from text
        
        Args:
            text: Text to analyze
            
        Returns:
            List of mentioned crypto symbols
        """
        # Common crypto symbols and keywords
        crypto_patterns = {
            "BTC": [r"\bbtc\b", r"\bbitcoin\b"],
            "ETH": [r"\beth\b", r"\bethereum\b"],
            "USDT": [r"\busdt\b", r"\btether\b"],
            "BNB": [r"\bbnb\b", r"\bbinance coin\b"],
            "USDC": [r"\busdc\b"],
            "XRP": [r"\bxrp\b", r"\bripple\b"],
            "ADA": [r"\bada\b", r"\bcardano\b"],
            "DOGE": [r"\bdoge\b", r"\bdogecoin\b"],
            "SOL": [r"\bsol\b", r"\bsolana\b"],
            "DOT": [r"\bdot\b", r"\bpolkadot\b"],
            "MATIC": [r"\bmatic\b", r"\bpolygon\b"],
            "AVAX": [r"\bavax\b", r"\bavalanche\b"],
        }
        
        text_lower = text.lower()
        mentioned = []
        
        for symbol, patterns in crypto_patterns.items():
            for pattern in patterns:
                if re.search(pattern, text_lower):
                    mentioned.append(symbol)
                    break
                    
        return list(set(mentioned))  # Remove duplicates
        
    def clean_text(self, text: str) -> str:
        """
        Clean and normalize text for analysis
        
        Args:
            text: Raw text
            
        Returns:
            Cleaned text
        """
        # Remove URLs
        text = re.sub(r'http\S+|www\.\S+', '', text)
        
        # Remove mentions and hashtags (keep the text)
        text = re.sub(r'@\w+', '', text)
        text = re.sub(r'#(\w+)', r'\1', text)
        
        # Remove extra whitespace
        text = ' '.join(text.split())
        
        return text
        
    async def _make_request(
        self,
        endpoint: str,
        params: Optional[Dict] = None,
        method: str = "GET"
    ) -> Optional[Dict]:
        """
        Make rate-limited API request with adaptive rate limiting and header parsing
        
        Args:
            endpoint: API endpoint
            params: Query parameters
            method: HTTP method
            
        Returns:
            Response data or None on failure
        """
        if not self.circuit_breaker.can_attempt():
            logger.warning(
                f"{self.collector_name} circuit breaker open, skipping request",
                endpoint=endpoint
            )
            return None
            
        # Apply rate limiting with endpoint tracking
        await self.rate_limiter.wait(endpoint=endpoint)
        
        if not self.session:
            await self.connect()
            
        url = f"{self.api_url}/{endpoint}"
        headers = {}
        
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
            
        try:
            start_time = datetime.now(timezone.utc)
            
            if method == "GET":
                async with self.session.get(url, params=params, headers=headers) as response:
                    response_time = (datetime.now(timezone.utc) - start_time).total_seconds()
                    
                    # Parse rate limit headers
                    self.rate_limiter.parse_rate_limit_headers(dict(response.headers), endpoint=endpoint)
                    
                    # Adjust rate based on response time and status
                    self.rate_limiter.adjust_rate(response_time, status_code=response.status)
                    
                    if response.status == 429:
                        # Handle rate limit
                        retry_after = response.headers.get("Retry-After", "60")
                        try:
                            retry_seconds = int(retry_after)
                        except ValueError:
                            retry_seconds = 60
                        
                        self.rate_limiter._handle_rate_limit_violation(retry_seconds)
                        logger.warning(
                            f"{self.collector_name} rate limit hit - backing off",
                            endpoint=endpoint,
                            retry_after=retry_seconds,
                            backoff_multiplier=self.rate_limiter.backoff_multiplier
                        )
                        return None
                    
                    response.raise_for_status()
                    data = await response.json()
                    
            elif method == "POST":
                async with self.session.post(url, json=params, headers=headers) as response:
                    response_time = (datetime.now(timezone.utc) - start_time).total_seconds()
                    
                    # Parse rate limit headers
                    self.rate_limiter.parse_rate_limit_headers(dict(response.headers), endpoint=endpoint)
                    
                    # Adjust rate based on response time and status
                    self.rate_limiter.adjust_rate(response_time, status_code=response.status)
                    
                    if response.status == 429:
                        # Handle rate limit
                        retry_after = response.headers.get("Retry-After", "60")
                        try:
                            retry_seconds = int(retry_after)
                        except ValueError:
                            retry_seconds = 60
                        
                        self.rate_limiter._handle_rate_limit_violation(retry_seconds)
                        logger.warning(
                            f"{self.collector_name} rate limit hit - backing off",
                            endpoint=endpoint,
                            retry_after=retry_seconds,
                            backoff_multiplier=self.rate_limiter.backoff_multiplier
                        )
                        return None
                    
                    response.raise_for_status()
                    data = await response.json()
            else:
                raise ValueError(f"Unsupported method: {method}")
                
            self.circuit_breaker.record_success()
            return data
            
        except aiohttp.ClientResponseError as e:
            self.circuit_breaker.record_failure()
            self.stats["errors"] += 1
            logger.error(
                f"{self.collector_name} request failed",
                endpoint=endpoint,
                status=e.status,
                error=str(e)
            )
            
            # Log collector health
            await self._log_health(CollectorStatus.DEGRADED, f"Request error: {str(e)}")
            
            return None
            
        except Exception as e:
            self.circuit_breaker.record_failure()
            self.stats["errors"] += 1
            logger.error(
                f"{self.collector_name} request failed",
                endpoint=endpoint,
                error=str(e)
            )
            
            # Log collector health
            await self._log_health(CollectorStatus.DEGRADED, f"Request error: {str(e)}")
            
            return None
            
    async def _log_health(self, status: CollectorStatus, message: str = ""):
        """
        Log collector health status to database
        
        Args:
            status: Collector status
            message: Optional status message
        """
        try:
            await self.database.log_collector_health(
                collector_name=self.collector_name,
                status=status.value,
                error_msg=message if status != CollectorStatus.HEALTHY else None
            )
        except Exception as e:
            logger.error(
                f"Failed to log collector health",
                collector=self.collector_name,
                error=str(e)
            )
            
    def get_status(self) -> Dict[str, Any]:
        """Get collector status"""
        status = CollectorStatus.HEALTHY
        
        if self.circuit_breaker.state == "open":
            status = CollectorStatus.CIRCUIT_OPEN
        elif self.stats["errors"] > 10:
            status = CollectorStatus.DEGRADED
            
        return {
            "collector": self.collector_name,
            "status": status.value,
            "circuit_breaker": self.circuit_breaker.get_status(),
            "rate_limiter": self.rate_limiter.get_status(),
            "stats": self.stats,
            "sentiment_enabled": VADER_AVAILABLE or (self.use_finbert and FINBERT_AVAILABLE)
        }
        
    async def collect_data(self) -> Dict[str, Any]:
        """
        Collect social media data (to be implemented by subclasses)
        
        Returns:
            Collection results
        """
        raise NotImplementedError("Subclasses must implement collect_data()")
