# Real-time Sentiment Analysis System

## Overview
The Sentiment Analysis System provides comprehensive market sentiment tracking for cryptocurrency assets through multi-source data collection, Named Entity Recognition (NER), and intelligent sentiment aggregation. The system integrates social media (Reddit, Twitter, Telegram), news articles, and market sentiment indices to generate actionable sentiment scores.

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Sentiment Analysis System                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌──────────────────┐  ┌──────────────────┐  ┌───────────────┐ │
│  │  Reddit          │  │  Twitter         │  │  Telegram     │ │
│  │  Collector       │  │  Collector       │  │  Monitor      │ │
│  │  (8 subreddits)  │  │  (Twitter API)   │  │  (Optional)   │ │
│  └────────┬─────────┘  └────────┬─────────┘  └───────┬───────┘ │
│           │                     │                     │          │
│           └─────────────────────┴─────────────────────┘          │
│                                 │                                │
│                    ┌────────────▼────────────┐                   │
│                    │  Enhanced Sentiment     │                   │
│                    │  Analyzer               │                   │
│                    │  - NER (15 patterns)    │                   │
│                    │  - Crypto keywords      │                   │
│                    │  - 7-tier scoring       │                   │
│                    └────────────┬────────────┘                   │
│                                 │                                │
│           ┌─────────────────────┴─────────────────────┐          │
│           │                                           │          │
│  ┌────────▼─────────┐  ┌──────────────────┐  ┌──────▼────────┐ │
│  │  News API        │  │  Fear & Greed    │  │  On-Chain     │ │
│  │  Collector       │  │  Index           │  │  Metrics      │ │
│  │  (Crypto news)   │  │  (CNN Index)     │  │  (Optional)   │ │
│  └────────┬─────────┘  └────────┬─────────┘  └───────┬───────┘ │
│           │                     │                     │          │
│           └─────────────────────┴─────────────────────┘          │
│                                 │                                │
│                    ┌────────────▼────────────┐                   │
│                    │  Comprehensive          │                   │
│                    │  Sentiment Aggregator   │                   │
│                    │  - Multi-source merge   │                   │
│                    │  - Confidence scoring   │                   │
│                    │  - Weighted average     │                   │
│                    └────────────┬────────────┘                   │
│                                 │                                │
│                    ┌────────────▼────────────┐                   │
│                    │  Cosmos DB Storage      │                   │
│                    │  - sentiment_data       │                   │
│                    │  - aggregated_sentiment │                   │
│                    └─────────────────────────┘                   │
└─────────────────────────────────────────────────────────────────┘
```

## Key Components

### 1. Enhanced Sentiment Analyzer (`enhanced_sentiment_analyzer.py`)

#### EnhancedSentimentAnalyzer Class
Core sentiment analysis engine with crypto-specific intelligence.

**Key Features:**
- **Named Entity Recognition (NER)**: Extracts cryptocurrency mentions using 15 regex patterns
  - Symbol patterns: BTC, ETH, $BTC, #Bitcoin
  - Full names: Bitcoin, Ethereum, Binance Coin
  - Ticker variations: BTCUSD, BTC/USD, BTC-USDT
  
- **Crypto-Specific Sentiment Analysis**: 
  - TextBlob baseline sentiment (70% weight)
  - Crypto keyword analysis (30% weight)
  - POSITIVE_KEYWORDS: moon, bullish, pump, breakout, rally, etc.
  - NEGATIVE_KEYWORDS: dump, crash, scam, bear, panic, etc.

- **7-Tier Sentiment Classification**:
  ```
  extremely_bearish: < -0.6
  very_bearish:      -0.6 to -0.3
  bearish:           -0.3 to -0.1
  neutral:           -0.1 to 0.1
  bullish:            0.1 to 0.3
  very_bullish:       0.3 to 0.6
  extremely_bullish:  > 0.6
  ```

**Key Methods:**
```python
extract_crypto_entities(text: str) -> List[str]
    # Extracts all crypto mentions from text
    # Returns: List of normalized symbols (e.g., ['BTC', 'ETH'])

analyze_sentiment(text: str) -> Dict[str, Any]
    # Analyzes sentiment with crypto context
    # Returns: {
    #   'score': -1.0 to 1.0,
    #   'classification': str,
    #   'entities': List[str],
    #   'confidence': 0.0 to 1.0
    # }

aggregate_sentiments(sentiments: List[Dict]) -> Dict[str, Any]
    # Aggregates multiple sentiment sources
    # Returns: Weighted average with confidence score
```

### 2. Reddit Sentiment Collector (`RedditSentimentCollector`)

Monitors 8 major cryptocurrency subreddits using PRAW (Reddit API).

**Monitored Subreddits:**
- r/CryptoCurrency (3.5M+ members)
- r/Bitcoin (4M+ members)
- r/Ethereum (1.5M+ members)
- r/BitcoinMarkets (active traders)
- r/CryptoMarkets (general trading)
- r/altcoin (altcoin discussions)
- r/CryptoMoonShots (high-risk plays)
- r/defi (DeFi projects)

**Collection Strategy:**
- Fetches top 100 hot posts per subreddit
- Analyzes post titles and selftext
- Extracts crypto entities and sentiment
- Filters by minimum score threshold (configurable)
- Runs every 2 hours via scheduler

**Reddit API Setup:**
```bash
# Required credentials in config.py
REDDIT_CLIENT_ID = "your_client_id"
REDDIT_CLIENT_SECRET = "your_client_secret"
REDDIT_USER_AGENT = "TradingBotSentiment/1.0"

# Get credentials at: https://www.reddit.com/prefs/apps
# Create a "script" type application
```

### 3. Twitter Sentiment Collector (from `sentiment_data_collector.py`)

Monitors Twitter for cryptocurrency mentions and sentiment.

**Features:**
- Twitter API v2 integration
- Keyword-based search for crypto terms
- Real-time tweet streaming (optional)
- Sentiment analysis with crypto context
- Runs every 30 minutes

**Twitter API Setup:**
```bash
# Required credentials in config.py
TWITTER_BEARER_TOKEN = "your_bearer_token"

# Get credentials at: https://developer.twitter.com/
# Apply for Elevated access for streaming
```

### 4. News Sentiment Collector

Collects and analyzes cryptocurrency news articles.

**Sources:**
- NewsAPI.org (crypto-specific queries)
- CoinDesk, CryptoNews, etc.
- Press releases and announcements

**Features:**
- Article title and content analysis
- Source credibility weighting
- Publication recency scoring
- Runs every 1 hour

**NewsAPI Setup:**
```bash
# Required credentials in config.py
NEWS_API_KEY = "your_api_key"

# Get API key at: https://newsapi.org/
# Free tier: 100 requests/day
```

### 5. Fear & Greed Index Collector

Monitors the Crypto Fear & Greed Index from Alternative.me.

**Features:**
- Market-wide sentiment indicator (0-100)
- Historical trend tracking
- No API key required
- Runs every 6 hours

**Index Interpretation:**
```
0-24:   Extreme Fear (opportunity to buy)
25-44:  Fear
45-55:  Neutral
56-75:  Greed
76-100: Extreme Greed (potential correction)
```

### 6. Comprehensive Sentiment Aggregator

Combines all sentiment sources into unified scores per crypto asset.

**Aggregation Logic:**
```python
# Weighted average based on source reliability
weights = {
    'reddit': 0.25,      # Social sentiment
    'twitter': 0.25,     # Real-time buzz
    'news': 0.30,        # Professional analysis
    'fear_greed': 0.20   # Market-wide sentiment
}

# Confidence calculation
confidence = (
    0.3 * source_count / max_sources +
    0.4 * (1 - sentiment_variance) +
    0.3 * data_recency_score
)
```

**Output Format:**
```python
{
    'symbol': 'BTCUSDT',
    'timestamp': '2024-01-15T10:30:00Z',
    'sentiment_score': 0.45,        # -1.0 to 1.0
    'classification': 'bullish',
    'confidence': 0.82,              # 0.0 to 1.0
    'sources': {
        'reddit': {'score': 0.38, 'count': 150},
        'twitter': {'score': 0.52, 'count': 89},
        'news': {'score': 0.41, 'count': 12},
        'fear_greed': {'score': 0.65, 'value': 65}
    },
    'entity_mentions': {
        'BTC': 150,
        'Bitcoin': 89,
        'BTCUSDT': 45
    },
    'trend': 'increasing'  # increasing/stable/decreasing
}
```

### 7. Sentiment Scheduler (`sentiment_scheduler.py`)

Automated periodic collection of all sentiment sources.

**Collection Schedule:**
```python
COLLECTION_INTERVALS = {
    'reddit': 7200,          # Every 2 hours
    'news': 3600,            # Every 1 hour
    'twitter': 1800,         # Every 30 minutes
    'fear_greed': 21600,     # Every 6 hours
    'aggregation': 1800      # Every 30 minutes
}
```

**Adaptive Scheduling:**
- Increases frequency during high volatility periods
- Reduces frequency during low activity (weekends)
- Error handling with exponential backoff
- Statistics tracking for monitoring

**Starting the Scheduler:**
```bash
cd /home/neodyme/Documents/Projects/masterTrade/market_data_service
./start_sentiment_scheduler.sh
```

## Database Schema

### Sentiment Data Collection
```python
{
    'id': 'sentiment_reddit_BTCUSDT_20240115103000',
    'document_type': 'sentiment_data',
    'source': 'reddit',           # reddit/twitter/news/fear_greed
    'symbol': 'BTCUSDT',
    'timestamp': '2024-01-15T10:30:00Z',
    'sentiment_score': 0.45,
    'classification': 'bullish',
    'confidence': 0.75,
    'text_sample': 'Bitcoin looking strong...',
    'entities_mentioned': ['BTC', 'Bitcoin'],
    'metadata': {
        'subreddit': 'CryptoCurrency',
        'post_score': 1250,
        'comment_count': 89,
        'author': 'crypto_trader_123'
    }
}
```

### Aggregated Sentiment
```python
{
    'id': 'aggregated_sentiment_BTCUSDT_20240115103000',
    'document_type': 'aggregated_sentiment',
    'symbol': 'BTCUSDT',
    'timestamp': '2024-01-15T10:30:00Z',
    'sentiment_score': 0.48,
    'classification': 'bullish',
    'confidence': 0.82,
    'sources': {
        'reddit': {'score': 0.45, 'count': 150, 'weight': 0.25},
        'twitter': {'score': 0.52, 'count': 89, 'weight': 0.25},
        'news': {'score': 0.44, 'count': 12, 'weight': 0.30},
        'fear_greed': {'score': 0.65, 'value': 65, 'weight': 0.20}
    },
    'entity_mentions': {'BTC': 150, 'Bitcoin': 89, 'BTCUSDT': 45},
    'trend': 'increasing',
    'previous_sentiment': 0.42,
    'change_rate': 0.06
}
```

## API Endpoints

### Get Current Sentiment
```http
GET /api/sentiment/{symbol}

Response:
{
    "symbol": "BTCUSDT",
    "current_sentiment": {
        "score": 0.48,
        "classification": "bullish",
        "confidence": 0.82
    },
    "sources": {...},
    "trend": "increasing"
}
```

### Get Historical Sentiment
```http
GET /api/sentiment/{symbol}/history?hours=24

Response:
{
    "symbol": "BTCUSDT",
    "timeframe": "24h",
    "sentiment_history": [
        {
            "timestamp": "2024-01-15T10:30:00Z",
            "score": 0.48,
            "classification": "bullish"
        },
        ...
    ],
    "average_sentiment": 0.45,
    "sentiment_volatility": 0.12
}
```

### Get Multi-Source Sentiment
```http
GET /api/sentiment/{symbol}/sources

Response:
{
    "symbol": "BTCUSDT",
    "timestamp": "2024-01-15T10:30:00Z",
    "sources": {
        "reddit": {
            "score": 0.45,
            "top_posts": [...]
        },
        "twitter": {
            "score": 0.52,
            "top_tweets": [...]
        },
        "news": {
            "score": 0.44,
            "top_articles": [...]
        },
        "fear_greed": {
            "value": 65,
            "classification": "Greed"
        }
    }
}
```

## Integration with Strategy Service

### Using Sentiment in Trading Strategies

```python
from shared.market_data_indicator_client import MarketDataIndicatorClient

class SentimentAwareStrategy:
    def __init__(self):
        self.market_data_client = MarketDataIndicatorClient()
        
    async def analyze_with_sentiment(self, symbol: str):
        # Get current sentiment
        sentiment = await self.market_data_client.get_sentiment(symbol)
        
        # Get technical indicators
        indicators = await self.market_data_client.get_indicators(symbol)
        
        # Combine signals
        if sentiment['score'] > 0.3 and sentiment['confidence'] > 0.7:
            # Strong bullish sentiment with high confidence
            if indicators['rsi'] < 40:
                # Oversold + bullish sentiment = strong buy
                return {'action': 'BUY', 'strength': 'HIGH'}
                
        elif sentiment['score'] < -0.3 and sentiment['confidence'] > 0.7:
            # Strong bearish sentiment with high confidence
            if indicators['rsi'] > 60:
                # Overbought + bearish sentiment = strong sell
                return {'action': 'SELL', 'strength': 'HIGH'}
        
        return {'action': 'HOLD', 'strength': 'MEDIUM'}
```

### Sentiment-Based Position Sizing

```python
def adjust_position_size_by_sentiment(
    base_size: float,
    sentiment_score: float,
    confidence: float
) -> float:
    """
    Adjust position size based on sentiment analysis.
    
    - Strong positive sentiment (>0.5) + high confidence: Increase by 20%
    - Weak sentiment or low confidence: Decrease by 20%
    - Negative sentiment: Reduce position size
    """
    if confidence < 0.6:
        # Low confidence - reduce position
        return base_size * 0.8
    
    if sentiment_score > 0.5:
        # Strong bullish sentiment
        return base_size * 1.2
    elif sentiment_score < -0.3:
        # Bearish sentiment - reduce position
        return base_size * 0.7
    
    return base_size
```

### Sentiment Divergence Detection

```python
async def detect_sentiment_divergence(symbol: str):
    """
    Detect divergence between price action and sentiment.
    Strong divergences can signal trend reversals.
    """
    # Get price trend
    price_data = await get_price_history(symbol, hours=24)
    price_trend = calculate_trend(price_data)
    
    # Get sentiment trend
    sentiment_history = await get_sentiment_history(symbol, hours=24)
    sentiment_trend = calculate_trend(sentiment_history)
    
    # Check for divergence
    if price_trend > 0.3 and sentiment_trend < -0.3:
        # Price rising but sentiment falling - potential reversal
        return {
            'type': 'bearish_divergence',
            'strength': abs(price_trend - sentiment_trend),
            'signal': 'CAUTION - Consider taking profits'
        }
    elif price_trend < -0.3 and sentiment_trend > 0.3:
        # Price falling but sentiment rising - potential bottom
        return {
            'type': 'bullish_divergence',
            'strength': abs(price_trend - sentiment_trend),
            'signal': 'OPPORTUNITY - Consider entering position'
        }
    
    return {'type': 'no_divergence', 'signal': 'NORMAL'}
```

## Configuration

### Environment Variables

```bash
# Sentiment Analysis Configuration
SENTIMENT_ENABLED=true

# Reddit API (https://www.reddit.com/prefs/apps)
REDDIT_CLIENT_ID=your_reddit_client_id
REDDIT_CLIENT_SECRET=your_reddit_client_secret
REDDIT_USER_AGENT=TradingBotSentiment/1.0

# Twitter API (https://developer.twitter.com/)
TWITTER_BEARER_TOKEN=your_twitter_bearer_token

# News API (https://newsapi.org/)
NEWS_API_KEY=your_newsapi_key

# Telegram (Optional - https://my.telegram.org/)
TELEGRAM_API_ID=your_telegram_api_id
TELEGRAM_API_HASH=your_telegram_api_hash

# Collection Settings
SENTIMENT_COLLECTION_INTERVAL=1800  # 30 minutes
REDDIT_POSTS_LIMIT=100
TWITTER_TWEETS_LIMIT=100
NEWS_ARTICLES_LIMIT=50
```

### config.py Settings

```python
# Sentiment Analysis Configuration
SENTIMENT_ENABLED: bool = True
SENTIMENT_COLLECTION_INTERVAL: int = 1800  # seconds

# API Credentials
REDDIT_CLIENT_ID: str = "your_client_id"
REDDIT_CLIENT_SECRET: str = "your_client_secret"
REDDIT_USER_AGENT: str = "TradingBotSentiment/1.0"
TWITTER_BEARER_TOKEN: str = "your_bearer_token"
NEWS_API_KEY: str = "your_api_key"

# Collection Limits
REDDIT_POSTS_LIMIT: int = 100
TWITTER_TWEETS_LIMIT: int = 100
NEWS_ARTICLES_LIMIT: int = 50
SENTIMENT_MIN_CONFIDENCE: float = 0.6
```

## Setup & Installation

### 1. Install Dependencies

```bash
cd /home/neodyme/Documents/Projects/masterTrade/market_data_service

# Install Python packages
pip install -r requirements.txt

# Download NLTK data (required for sentiment analysis)
python -c "import nltk; nltk.download('punkt'); nltk.download('averaged_perceptron_tagger')"
```

### 2. Configure API Credentials

```bash
# Edit config.py with your API credentials
nano config.py

# Or set environment variables
export REDDIT_CLIENT_ID="your_reddit_client_id"
export REDDIT_CLIENT_SECRET="your_reddit_client_secret"
export TWITTER_BEARER_TOKEN="your_twitter_bearer_token"
export NEWS_API_KEY="your_newsapi_key"
```

### 3. Start Sentiment Scheduler

```bash
# Make startup script executable
chmod +x start_sentiment_scheduler.sh

# Start the scheduler
./start_sentiment_scheduler.sh
```

### 4. Verify Operation

```bash
# Check logs
tail -f logs/sentiment_scheduler.log

# Test sentiment collection
python -c "
from enhanced_sentiment_analyzer import EnhancedSentimentAnalyzer
analyzer = EnhancedSentimentAnalyzer()
result = analyzer.analyze_sentiment('Bitcoin is pumping! BTC to the moon! 🚀')
print(result)
"
```

## Monitoring & Troubleshooting

### Health Checks

```python
# Check sentiment scheduler status
GET /api/health/sentiment

Response:
{
    "status": "healthy",
    "last_collection": "2024-01-15T10:30:00Z",
    "collections_today": 48,
    "active_sources": ["reddit", "news", "twitter", "fear_greed"],
    "errors_last_24h": 2
}
```

### Common Issues

1. **Reddit API Rate Limiting**
   - Symptom: HTTP 429 errors
   - Solution: Increase collection interval, reduce REDDIT_POSTS_LIMIT

2. **Twitter API Access Denied**
   - Symptom: HTTP 403 errors
   - Solution: Verify TWITTER_BEARER_TOKEN, check API access level

3. **NLTK Data Missing**
   - Symptom: LookupError for 'punkt' or 'averaged_perceptron_tagger'
   - Solution: Run `python -c "import nltk; nltk.download('punkt'); nltk.download('averaged_perceptron_tagger')"`

4. **Low Confidence Scores**
   - Symptom: All sentiment scores have confidence < 0.5
   - Solution: Increase data sources, verify API connectivity, check entity recognition patterns

### Performance Metrics

Monitor these metrics in Grafana:
- `sentiment_collections_total`: Total sentiment collections
- `sentiment_collection_duration_seconds`: Collection time per source
- `sentiment_api_errors_total`: API errors by source
- `sentiment_score_by_symbol`: Current sentiment scores
- `sentiment_confidence_average`: Average confidence scores
- `sentiment_entities_detected_total`: Entity recognition effectiveness

## Advanced Features

### 1. On-Chain Sentiment Metrics (Placeholder)

Future integration with blockchain data:
- Whale wallet movements
- Exchange inflow/outflow
- Network activity metrics
- Active addresses trend

### 2. Telegram Channel Monitoring (Placeholder)

Future Telegram integration:
- Monitor crypto trading channels
- Extract signals and sentiment
- Track influencer mentions
- Analyze group discussions

### 3. Custom Crypto Keyword Dictionary

Extend keyword dictionaries for better accuracy:

```python
# In enhanced_sentiment_analyzer.py
CUSTOM_POSITIVE_KEYWORDS = {
    'accumulation', 'breakout', 'golden cross',
    'support holding', 'reversal', 'momentum'
}

CUSTOM_NEGATIVE_KEYWORDS = {
    'death cross', 'breakdown', 'resistance',
    'dump incoming', 'rug pull', 'ponzi'
}
```

### 4. Sentiment Momentum Indicator

Calculate rate of sentiment change:

```python
sentiment_momentum = (current_sentiment - sentiment_1h_ago) / 1
# Rapid positive change = strong momentum
# Rapid negative change = panic/capitulation
```

## Best Practices

1. **Always Check Confidence Scores**
   - Only act on sentiment with confidence > 0.7
   - Low confidence = insufficient data or conflicting signals

2. **Combine Multiple Sources**
   - Don't rely on single source (e.g., only Reddit)
   - Aggregated sentiment is more reliable

3. **Consider Context**
   - Sentiment alone is not enough for trading decisions
   - Combine with technical analysis and market structure

4. **Monitor Source Quality**
   - Track which sources provide best signals
   - Adjust weights based on historical performance

5. **Handle API Rate Limits**
   - Implement exponential backoff
   - Cache results when appropriate
   - Use webhooks instead of polling when available

## References

- **Reddit API**: https://www.reddit.com/dev/api/
- **Twitter API**: https://developer.twitter.com/en/docs
- **NewsAPI**: https://newsapi.org/docs
- **Fear & Greed Index**: https://alternative.me/crypto/fear-and-greed-index/
- **NLTK Documentation**: https://www.nltk.org/
- **TextBlob Sentiment**: https://textblob.readthedocs.io/

## Related Documentation

- `MARKET_DATA_COSMOS_SUMMARY.md`: Database schema and storage
- `API_DOCUMENTATION.md`: Complete API reference
- `MARKET_DATA_STRATEGY_INTEGRATION.md`: Integration examples
- `sentiment_data_collector.py`: Original sentiment collector
- `enhanced_sentiment_analyzer.py`: Advanced sentiment analysis
- `sentiment_scheduler.py`: Automated collection scheduler
