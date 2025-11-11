# Social Sentiment REST API v1 Documentation

## Overview

The Social Sentiment API provides access to aggregated social media sentiment data for cryptocurrencies. This API allows you to query sentiment scores, trending topics, and influencer activity from Twitter, Reddit, and other social platforms.

**Base URL**: `http://localhost:8000/api/v1/social`

**Authentication**: None required (currently internal service)

**Rate Limiting**: 
- 60 requests per minute per client
- Burst limit: 10 requests per second

## Endpoints

### 1. Get Sentiment by Symbol

Retrieve aggregated sentiment data for a specific cryptocurrency symbol.

**Endpoint**: `GET /api/v1/social/sentiment/{symbol}`

#### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| symbol | string | Yes | Cryptocurrency symbol (e.g., BTC, ETH, DOGE) |

#### Query Parameters

| Parameter | Type | Default | Range | Description |
|-----------|------|---------|-------|-------------|
| hours | integer | 24 | 1-720 | Hours of historical data to retrieve |
| source | string | all | twitter, reddit, all | Filter by data source |
| limit | integer | 100 | 1-1000 | Maximum number of results to return |

#### Response Schema

```json
{
  "success": true,
  "symbol": "BTC",
  "data": [
    {
      "post_id": "1234567890",
      "text": "Bitcoin looking bullish! 🚀",
      "source": "twitter",
      "symbol": "BTC",
      "author_id": "user123",
      "author_username": "crypto_trader",
      "timestamp": "2025-11-11T12:00:00Z",
      "sentiment_score": 0.85,
      "sentiment_category": "positive",
      "sentiment_positive": 0.9,
      "sentiment_neutral": 0.08,
      "sentiment_negative": 0.02,
      "engagement_score": 1250,
      "like_count": 850,
      "retweet_count": 300,
      "reply_count": 100,
      "is_influencer": true
    }
  ],
  "count": 1,
  "summary": {
    "average_sentiment": 0.68,
    "total_mentions": 1234,
    "total_engagement": 567890,
    "sentiment_breakdown": {
      "positive": 720,
      "neutral": 350,
      "negative": 164
    },
    "by_source": {
      "twitter": {
        "count": 800,
        "avg_sentiment": 0.72
      },
      "reddit": {
        "count": 434,
        "avg_sentiment": 0.61
      }
    }
  },
  "filters": {
    "hours": 24,
    "source": "all",
    "limit": 100
  },
  "timestamp": "2025-11-11T14:00:00Z"
}
```

#### Sentiment Score Scale

- **Score Range**: -1.0 to +1.0
- **Positive**: > 0.2 (bullish sentiment)
- **Neutral**: -0.2 to 0.2 (mixed/neutral sentiment)
- **Negative**: < -0.2 (bearish sentiment)

#### Example Requests

```bash
# Get BTC sentiment for last 24 hours (all sources)
curl "http://localhost:8000/api/v1/social/sentiment/BTC"

# Get ETH sentiment from Twitter only, last 7 days
curl "http://localhost:8000/api/v1/social/sentiment/ETH?source=twitter&hours=168"

# Get DOGE sentiment, last 48 hours, limited to 50 results
curl "http://localhost:8000/api/v1/social/sentiment/DOGE?hours=48&limit=50"
```

---

### 2. Get Trending Cryptocurrencies

Retrieve the most mentioned and discussed cryptocurrencies on social media.

**Endpoint**: `GET /api/v1/social/trending`

#### Query Parameters

| Parameter | Type | Default | Range | Description |
|-----------|------|---------|-------|-------------|
| limit | integer | 20 | 1-100 | Number of trending topics to return |
| hours | integer | 24 | N/A | Hours to analyze (currently fixed at 24) |

#### Response Schema

```json
{
  "success": true,
  "data": [
    {
      "symbol": "BTC",
      "rank": 1,
      "mention_count": 5432,
      "avg_sentiment": 0.65,
      "total_engagement": 876543,
      "unique_authors": 3210,
      "timestamp": "2025-11-11T14:00:00Z"
    },
    {
      "symbol": "ETH",
      "rank": 2,
      "mention_count": 3210,
      "avg_sentiment": 0.58,
      "total_engagement": 543210,
      "unique_authors": 2150,
      "timestamp": "2025-11-11T14:00:00Z"
    }
  ],
  "count": 20,
  "filters": {
    "limit": 20,
    "hours": 24
  },
  "timestamp": "2025-11-11T14:00:00Z"
}
```

#### Ranking Criteria

Trending topics are ranked by:
1. **Primary**: Mention count (number of posts)
2. **Secondary**: Total engagement (likes + retweets + replies)

#### Example Requests

```bash
# Get top 20 trending cryptocurrencies
curl "http://localhost:8000/api/v1/social/trending"

# Get top 5 trending cryptocurrencies
curl "http://localhost:8000/api/v1/social/trending?limit=5"
```

---

### 3. Get Influencer Sentiment

Retrieve social media influencers and their sentiment towards cryptocurrencies.

**Endpoint**: `GET /api/v1/social/influencers`

#### Query Parameters

| Parameter | Type | Default | Range | Description |
|-----------|------|---------|-------|-------------|
| symbol | string | all | - | Filter by cryptocurrency symbol (optional) |
| limit | integer | 50 | 1-200 | Number of influencers to return |
| hours | integer | 24 | 1-168 | Hours of history to analyze |
| min_followers | integer | 0 | 0+ | Minimum follower count threshold |

#### Response Schema

```json
{
  "success": true,
  "data": [
    {
      "author_id": "influencer123",
      "username": "crypto_expert",
      "follower_count": 125000,
      "post_count": 15,
      "avg_sentiment": 0.72,
      "total_engagement": 87654,
      "symbols_mentioned": ["BTC", "ETH", "SOL"],
      "is_verified": true
    }
  ],
  "count": 50,
  "filters": {
    "symbol": "all",
    "limit": 50,
    "hours": 24,
    "min_followers": 0
  },
  "timestamp": "2025-11-11T14:00:00Z"
}
```

#### Influencer Criteria

An account is classified as an influencer if:
- Follower count > 10,000
- Verified account (blue checkmark)
- High engagement rate
- Regular crypto-related content

#### Ranking

Influencers are ranked by:
1. **Primary**: Follower count
2. **Secondary**: Total engagement

#### Example Requests

```bash
# Get top 50 influencers (all symbols)
curl "http://localhost:8000/api/v1/social/influencers"

# Get top 10 Bitcoin influencers
curl "http://localhost:8000/api/v1/social/influencers?symbol=BTC&limit=10"

# Get influencers with 50k+ followers, last 7 days
curl "http://localhost:8000/api/v1/social/influencers?min_followers=50000&hours=168"

# Get verified Ethereum influencers (100k+ followers)
curl "http://localhost:8000/api/v1/social/influencers?symbol=ETH&min_followers=100000"
```

---

## Error Responses

All endpoints return consistent error responses:

```json
{
  "success": false,
  "error": "Error message describing what went wrong"
}
```

### HTTP Status Codes

| Code | Description | Common Causes |
|------|-------------|---------------|
| 200 | OK | Request successful |
| 400 | Bad Request | Invalid parameters (wrong type, out of range, invalid source) |
| 404 | Not Found | Endpoint doesn't exist |
| 500 | Internal Server Error | Database error, service unavailable |

### Common Errors

**Invalid Source**:
```json
{
  "success": false,
  "error": "Invalid source. Must be 'twitter', 'reddit', or 'all'"
}
```

**Invalid Parameter Type**:
```json
{
  "success": false,
  "error": "Invalid parameter value: invalid literal for int() with base 10: 'abc'"
}
```

**Missing Symbol**:
```json
{
  "success": false,
  "error": "Symbol parameter is required"
}
```

---

## Data Freshness

- **Sentiment Data**: Updated every 5-15 minutes
- **Trending Topics**: Calculated every 15 minutes
- **Influencer Stats**: Updated hourly

Actual update frequency depends on social media API rate limits and data availability.

---

## Integration Examples

### Python (using requests)

```python
import requests
from datetime import datetime, timedelta

BASE_URL = "http://localhost:8000/api/v1/social"

# Get BTC sentiment
def get_btc_sentiment(hours=24):
    response = requests.get(
        f"{BASE_URL}/sentiment/BTC",
        params={"hours": hours, "limit": 100}
    )
    data = response.json()
    
    if data["success"]:
        print(f"BTC Sentiment: {data['summary']['average_sentiment']:.2f}")
        print(f"Total mentions: {data['summary']['total_mentions']}")
        print(f"Positive: {data['summary']['sentiment_breakdown']['positive']}")
        print(f"Negative: {data['summary']['sentiment_breakdown']['negative']}")
        return data
    else:
        print(f"Error: {data['error']}")
        return None

# Get trending cryptocurrencies
def get_trending(limit=10):
    response = requests.get(
        f"{BASE_URL}/trending",
        params={"limit": limit}
    )
    data = response.json()
    
    if data["success"]:
        print(f"\nTop {limit} Trending Cryptocurrencies:")
        for item in data["data"]:
            print(f"{item['rank']}. {item['symbol']}: "
                  f"{item['mention_count']} mentions, "
                  f"sentiment {item['avg_sentiment']:.2f}")
        return data
    else:
        print(f"Error: {data['error']}")
        return None

# Get top influencers for a symbol
def get_top_influencers(symbol="BTC", min_followers=10000):
    response = requests.get(
        f"{BASE_URL}/influencers",
        params={
            "symbol": symbol,
            "min_followers": min_followers,
            "limit": 20
        }
    )
    data = response.json()
    
    if data["success"]:
        print(f"\nTop Influencers for {symbol}:")
        for influencer in data["data"]:
            print(f"@{influencer['username']}: "
                  f"{influencer['follower_count']:,} followers, "
                  f"sentiment {influencer['avg_sentiment']:.2f}, "
                  f"{influencer['post_count']} posts")
        return data
    else:
        print(f"Error: {data['error']}")
        return None

# Run examples
if __name__ == "__main__":
    btc_data = get_btc_sentiment(hours=24)
    trending_data = get_trending(limit=10)
    influencers = get_top_influencers(symbol="BTC", min_followers=50000)
```

### JavaScript/Node.js (using axios)

```javascript
const axios = require('axios');

const BASE_URL = 'http://localhost:8000/api/v1/social';

// Get BTC sentiment
async function getBtcSentiment(hours = 24) {
  try {
    const response = await axios.get(`${BASE_URL}/sentiment/BTC`, {
      params: { hours, limit: 100 }
    });
    
    const { data } = response.data;
    const { summary } = response.data;
    
    console.log(`BTC Sentiment: ${summary.average_sentiment.toFixed(2)}`);
    console.log(`Total mentions: ${summary.total_mentions}`);
    console.log(`Positive: ${summary.sentiment_breakdown.positive}`);
    console.log(`Negative: ${summary.sentiment_breakdown.negative}`);
    
    return response.data;
  } catch (error) {
    console.error('Error:', error.response?.data?.error || error.message);
    return null;
  }
}

// Get trending cryptocurrencies
async function getTrending(limit = 10) {
  try {
    const response = await axios.get(`${BASE_URL}/trending`, {
      params: { limit }
    });
    
    const { data } = response.data;
    
    console.log(`\nTop ${limit} Trending Cryptocurrencies:`);
    data.forEach(item => {
      console.log(`${item.rank}. ${item.symbol}: ${item.mention_count} mentions, sentiment ${item.avg_sentiment.toFixed(2)}`);
    });
    
    return response.data;
  } catch (error) {
    console.error('Error:', error.response?.data?.error || error.message);
    return null;
  }
}

// Get top influencers
async function getTopInfluencers(symbol = 'BTC', minFollowers = 10000) {
  try {
    const response = await axios.get(`${BASE_URL}/influencers`, {
      params: {
        symbol,
        min_followers: minFollowers,
        limit: 20
      }
    });
    
    const { data } = response.data;
    
    console.log(`\nTop Influencers for ${symbol}:`);
    data.forEach(influencer => {
      console.log(`@${influencer.username}: ${influencer.follower_count.toLocaleString()} followers, sentiment ${influencer.avg_sentiment.toFixed(2)}, ${influencer.post_count} posts`);
    });
    
    return response.data;
  } catch (error) {
    console.error('Error:', error.response?.data?.error || error.message);
    return null;
  }
}

// Run examples
(async () => {
  await getBtcSentiment(24);
  await getTrending(10);
  await getTopInfluencers('BTC', 50000);
})();
```

### cURL Commands

```bash
# Get BTC sentiment (last 24 hours)
curl -s "http://localhost:8000/api/v1/social/sentiment/BTC" | jq .

# Get ETH sentiment from Twitter (last 7 days)
curl -s "http://localhost:8000/api/v1/social/sentiment/ETH?source=twitter&hours=168" | jq .

# Get top 5 trending cryptocurrencies
curl -s "http://localhost:8000/api/v1/social/trending?limit=5" | jq .

# Get top 10 BTC influencers with 100k+ followers
curl -s "http://localhost:8000/api/v1/social/influencers?symbol=BTC&min_followers=100000&limit=10" | jq .

# Get all influencers (last 7 days)
curl -s "http://localhost:8000/api/v1/social/influencers?hours=168" | jq .
```

---

## Data Sources

The Social Sentiment API aggregates data from:

1. **Twitter**: Real-time tweets, retweets, likes, and replies
2. **Reddit**: Posts and comments from cryptocurrency subreddits
3. **LunarCrush**: Aggregated social metrics and sentiment scores

---

## Use Cases

### Trading Signal Generation
Monitor sentiment changes to identify potential trading opportunities:
```python
# Alert when sentiment shifts significantly
current_sentiment = get_btc_sentiment(hours=1)
previous_sentiment = get_btc_sentiment(hours=24)

sentiment_change = current_sentiment - previous_sentiment
if sentiment_change > 0.3:
    print("BULLISH SIGNAL: Sentiment increased significantly!")
```

### Trend Detection
Identify emerging cryptocurrencies before they go mainstream:
```python
trending = get_trending(limit=20)
for coin in trending["data"]:
    if coin["rank"] <= 5 and coin["avg_sentiment"] > 0.5:
        print(f"Rising star: {coin['symbol']}")
```

### Influencer Monitoring
Track what top influencers are saying:
```python
influencers = get_top_influencers(min_followers=100000)
for inf in influencers["data"]:
    if inf["avg_sentiment"] > 0.7:
        print(f"Bullish influencer: @{inf['username']}")
```

---

## Notes

- **Parameter Clamping**: All numeric parameters are automatically clamped to their valid ranges
- **Empty Results**: Empty result sets return `success: true` with `count: 0` and empty `data` array
- **Timestamp Format**: All timestamps use ISO 8601 format with UTC timezone
- **Symbol Case**: Symbol parameters are case-insensitive (converted to uppercase)

---

## Support

For issues or questions regarding the Social Sentiment API, please refer to the main documentation or contact the development team.
