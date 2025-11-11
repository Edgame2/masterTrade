# Signal Buffer System

## Overview

The Signal Buffer system provides fast, in-memory access to recent market signals using Redis sorted sets. Signals are automatically buffered when published to RabbitMQ, maintaining a rolling window of the last 1000 signals with 24-hour TTL.

## Architecture

```
Signal Aggregator
    ↓
_aggregate_signal_for_symbol()
    ↓
_publish_signal()
    ├─→ RabbitMQ (for strategy service consumption)
    └─→ Redis Buffer (for fast retrieval)
         - Key: signals:recent
         - Type: Sorted Set
         - Score: Timestamp
         - Max: 1000 signals
         - TTL: 24 hours
```

## Features

- **Automatic Buffering**: Every signal published to RabbitMQ is automatically buffered in Redis
- **Size Management**: Maintains last 1000 signals (oldest auto-removed)
- **Time-to-Live**: 24-hour TTL on buffered data
- **Filtering**: Support for symbol, limit, and time-range filtering
- **Statistics**: Real-time analytics on signal distribution
- **Graceful Degradation**: System continues working if Redis is unavailable

## HTTP API Endpoints

### 1. Get Recent Signals

```bash
GET /signals/recent?symbol=BTCUSDT&limit=100&hours=24
```

**Query Parameters:**
- `symbol` (optional): Filter by trading pair (e.g., BTCUSDT, ETHUSDT)
- `limit` (optional, default: 100, max: 1000): Number of signals to return
- `hours` (optional): Only return signals from last N hours

**Response:**
```json
{
  "success": true,
  "signals": [
    {
      "signal_id": "agg_20251111_124530_btcusdt",
      "symbol": "BTCUSDT",
      "overall_signal": "bullish",
      "signal_strength": "strong",
      "confidence": 0.85,
      "recommended_action": "buy",
      "timestamp": "2025-11-11T12:45:30.123456"
    }
  ],
  "count": 1,
  "filters": {
    "symbol": "BTCUSDT",
    "limit": 100,
    "hours_back": 24
  }
}
```

### 2. Get Signal Statistics

```bash
GET /signals/stats?symbol=BTCUSDT&hours=24
```

**Query Parameters:**
- `symbol` (required): Trading pair to analyze
- `hours` (optional, default: 24): Analysis period in hours

**Response:**
```json
{
  "success": true,
  "statistics": {
    "symbol": "BTCUSDT",
    "period_hours": 24,
    "total_signals": 145,
    "bullish_count": 87,
    "bearish_count": 45,
    "neutral_count": 13,
    "bullish_percent": 60.0,
    "bearish_percent": 31.0,
    "average_confidence": 0.742,
    "strong_signals_count": 42,
    "strong_signals_percent": 29.0,
    "action_distribution": {
      "buy": 87,
      "sell": 45,
      "hold": 13
    },
    "latest_signal": {
      "direction": "bullish",
      "strength": "strong",
      "confidence": 0.85,
      "action": "buy",
      "timestamp": "2025-11-11T12:45:30.123456"
    }
  }
}
```

### 3. Get Buffer Information

```bash
GET /signals/buffer/info
```

**Response:**
```json
{
  "success": true,
  "buffer_info": {
    "current_size": 1000,
    "max_size": 1000,
    "ttl_seconds": 86400,
    "ttl_hours": 24.0,
    "oldest_signal": "2025-11-10T12:45:30.123456",
    "newest_signal": "2025-11-11T12:45:30.123456",
    "redis_key": "signals:recent"
  }
}
```

## Python API (Direct Access)

### From Strategy Service

```python
from market_data_service.signal_aggregator import SignalAggregator

# Get signal aggregator instance
aggregator = service.signal_aggregator

# Get recent signals for a symbol
signals = await aggregator.get_recent_signals(
    symbol="BTCUSDT",
    limit=50,
    hours_back=1
)

# Get statistics
stats = await aggregator.get_signal_statistics(
    symbol="BTCUSDT",
    hours=24
)

print(f"Bullish signals: {stats['bullish_percent']}%")
print(f"Average confidence: {stats['average_confidence']}")
```

### From Redis Client

```python
from shared.redis_client import RedisCacheManager

redis = RedisCacheManager(redis_url="redis://redis:6379")
await redis.connect()

# Get last 100 signals
signals = await redis.zrange("signals:recent", -100, -1)

# Get buffer size
size = await redis.zcard("signals:recent")

# Get signals from last hour
import time
cutoff = time.time() - 3600
recent = await redis.redis.zrangebyscore(
    "signals:recent",
    cutoff,
    '+inf'
)
```

## Use Cases

### 1. Real-Time Strategy Monitoring
Monitor what signals are being generated for quick strategy adjustments:

```bash
# Check recent signals
curl "http://localhost:8000/signals/recent?limit=10"

# Get hourly statistics
curl "http://localhost:8000/signals/stats?symbol=BTCUSDT&hours=1"
```

### 2. Signal Quality Analysis
Analyze signal distribution to tune aggregation weights:

```python
stats = await aggregator.get_signal_statistics("BTCUSDT", hours=24)

if stats['strong_signals_percent'] < 20:
    print("Warning: Low percentage of strong signals")
    print(f"Average confidence: {stats['average_confidence']}")
```

### 3. Fast Signal Lookup
Retrieve recent signals without database queries:

```python
# Get last 5 minutes of signals for multiple symbols
for symbol in ["BTCUSDT", "ETHUSDT", "BNBUSDT"]:
    signals = await aggregator.get_recent_signals(
        symbol=symbol,
        hours_back=0.083,  # 5 minutes = 0.083 hours
        limit=10
    )
    print(f"{symbol}: {len(signals)} signals")
```

## Configuration

### Buffer Settings

Settings are configured in `signal_aggregator.py`:

```python
# In _buffer_signal_in_redis()
redis_key = "signals:recent"      # Redis key name
max_signals = 1000                 # Maximum buffer size
ttl_seconds = 86400                # 24 hours

# Buffer management
if count > 1000:
    remove_count = count - 1000
    await redis.zremrangebyrank(redis_key, 0, remove_count - 1)
```

### Modifying Buffer Size

To change buffer size, edit `signal_aggregator.py`:

```python
# Around line 750
count = await self.redis_cache.zcard(redis_key)
if count > 2000:  # Changed from 1000
    remove_count = count - 2000
    await self.redis_cache.zremrangebyrank(redis_key, 0, remove_count - 1)
```

### Modifying TTL

```python
# Around line 757
await self.redis_cache.expire(redis_key, 172800)  # Changed to 48 hours
```

## Performance Characteristics

- **Write Performance**: O(log N) for adding to sorted set (~0.1ms per signal)
- **Read Performance**: O(log N + M) where M is number of results (~1-5ms for 100 signals)
- **Memory Usage**: ~2KB per signal × 1000 = ~2MB total
- **Buffer Latency**: <1ms for buffering (non-blocking)
- **Retrieval Latency**: <10ms for 100 signals with filtering

## Monitoring

### Check Buffer Health

```bash
# Get buffer info
curl http://localhost:8000/signals/buffer/info

# Check Redis directly
docker compose exec redis redis-cli
> ZCARD signals:recent
> TTL signals:recent
> ZRANGE signals:recent 0 0 WITHSCORES
```

### Monitor Signal Generation

```bash
# Watch for signal buffering in logs
docker compose logs market_data_service --follow | grep "Signal buffered"

# Check signal publication
docker compose logs market_data_service --follow | grep "Published market signal"
```

## Error Handling

The system handles errors gracefully:

1. **Redis Unavailable**: Logging warning, signal still published to RabbitMQ
2. **Buffer Full**: Oldest signals automatically removed
3. **Invalid Query**: HTTP 400 with error message
4. **Deserialization Error**: Signal skipped with warning log

## Testing

### Unit Tests

```bash
# Run buffer tests
docker compose exec market_data_service python test_signal_buffer.py
```

### Integration Tests

```bash
# Run endpoint tests
python market_data_service/test_signal_buffer_integration.py
```

### Manual Testing

```bash
# 1. Check buffer is empty
curl http://localhost:8000/signals/buffer/info

# 2. Wait 60 seconds for signal aggregator to run

# 3. Check buffer has signals
curl http://localhost:8000/signals/recent?limit=5

# 4. Get statistics
curl "http://localhost:8000/signals/stats?symbol=BTCUSDT&hours=1"
```

## Troubleshooting

### No Signals in Buffer

1. Check signal aggregator is running:
   ```bash
   docker compose logs market_data_service | grep "Signal aggregator"
   ```

2. Check Redis connection:
   ```bash
   docker compose logs market_data_service | grep "Redis"
   ```

3. Check symbols are configured:
   ```bash
   docker compose logs market_data_service | grep "active symbols"
   ```

### Buffer Not Growing

1. Check for errors in signal generation:
   ```bash
   docker compose logs market_data_service | grep -i "error.*signal"
   ```

2. Verify Redis is healthy:
   ```bash
   docker compose exec redis redis-cli PING
   ```

3. Check TTL hasn't expired:
   ```bash
   curl http://localhost:8000/signals/buffer/info
   ```

## Future Enhancements

Potential improvements for the signal buffer:

1. **Per-Symbol Buffers**: Separate sorted sets for each trading pair
2. **Signal Compression**: Store compressed signals to save memory
3. **Longer History**: Archive old signals to PostgreSQL with hourly aggregation
4. **Real-Time Subscriptions**: WebSocket endpoint for live signal streaming
5. **Signal Replay**: Time-travel capability for backtesting strategies
6. **Aggregated Metrics**: Pre-computed hourly/daily signal statistics

## Related Documentation

- [Market Data Service API](./API_DOCUMENTATION.md)
- [Signal Aggregator](./signal_aggregator.py)
- [Redis Client](../shared/redis_client.py)
- [Message Schemas](../shared/message_schemas.py)
