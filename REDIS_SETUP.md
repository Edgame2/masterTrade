# Redis Cache Setup for MasterTrade

This document describes the Redis caching layer implementation for the MasterTrade system.

## Overview

Redis is used for:
- **API response caching** - Cache expensive queries (on-chain metrics, social sentiment, market data)
- **Signal buffering** - Buffer last 1000 trading signals for fast lookups
- **Session management** - Store user sessions for Monitor UI
- **Query result caching** - Cache backtest results and position sizing calculations

## Architecture

### Redis Configuration
- **Image**: `redis:7-alpine`
- **Port**: 6379
- **Memory Limit**: 2GB
- **Eviction Policy**: `allkeys-lru` (Least Recently Used)
- **Persistence**: AOF (Append-Only File) enabled
- **Health Check**: `redis-cli ping` every 10 seconds

### Cache TTL Strategy
| Data Type | TTL | Rationale |
|-----------|-----|-----------|
| Market Data | 30 seconds | High-frequency updates |
| Social Sentiment | 1 minute | Real-time sentiment changes |
| On-Chain Metrics | 5 minutes | Slower blockchain confirmations |
| Backtest Results | 24 hours | Expensive computations, relatively static |
| Position Sizing | 1 minute | Dynamic risk calculations |
| Trading Signals | 24 hours | Historical signal buffer |

## Deployment

### 1. Start Redis Service

```bash
# Start Redis only
docker-compose up redis -d

# Start entire stack (includes Redis)
docker-compose up -d

# Check Redis logs
docker-compose logs redis -f

# Check Redis status
docker-compose ps redis
```

### 2. Verify Redis Connection

```bash
# Run Redis CLI
docker exec -it mastertrade_redis redis-cli

# Test commands
> PING
PONG

> INFO server
# Shows server information

> INFO memory
# Shows memory usage

> EXIT
```

### 3. Test Redis Client

```bash
# From project root
cd shared
python test_redis_client.py
```

Expected output:
```
╔==========================================================╗
║               REDIS CLIENT TEST SUITE                    ║
╚==========================================================╝

=============================================================
Testing Redis Connection
=============================================================
✅ Connected to Redis successfully
✅ Ping successful: True

=============================================================
Testing Basic Operations
=============================================================
✅ Set operation: True
✅ Get operation: {'message': 'Hello Redis!', 'timestamp': '...'}
✅ Exists check: 1 key(s) found
✅ TTL: 60 seconds remaining
✅ Delete operation: 1 key(s) deleted

... (more tests)

✅ ALL TESTS PASSED!
```

## Usage

### Python Integration

```python
from shared.redis_client import RedisCacheManager

# Initialize cache manager
cache = RedisCacheManager(redis_url="redis://localhost:6379")

# Connect
await cache.connect()

# Basic operations
await cache.set("key", {"data": "value"}, ttl=300)  # 5 minute TTL
value = await cache.get("key")
await cache.delete("key")

# Disconnect when done
await cache.disconnect()
```

### Market Data Caching

```python
from shared.redis_client import cache_market_data, get_cached_market_data

# Cache market data
market_data = {
    "symbol": "BTCUSDT",
    "price": 45000.50,
    "volume": 1234567.89
}
await cache_market_data(cache, "BTCUSDT", market_data, ttl=30)

# Retrieve cached data
cached = await get_cached_market_data(cache, "BTCUSDT")
```

### Signal Buffering

```python
from shared.redis_client import buffer_signal, get_recent_signals

# Buffer a trading signal
signal = {
    "symbol": "BTCUSDT",
    "signal_type": "BUY",
    "strength": 0.85,
    "timestamp": datetime.now().timestamp()
}
await buffer_signal(cache, signal)

# Get recent signals
recent = await get_recent_signals(cache, count=100)
```

## Integration with Services

### Market Data Service

```python
# In market_data_service/main.py
from shared.redis_client import RedisCacheManager

class MarketDataService:
    def __init__(self):
        self.cache = RedisCacheManager(redis_url=settings.REDIS_URL)
        
    async def startup(self):
        await self.cache.connect()
        
    async def get_onchain_metrics(self, symbol: str):
        # Try cache first
        cache_key = f"onchain_metrics:{symbol}"
        cached = await self.cache.get(cache_key)
        if cached:
            return cached
        
        # Fetch from database
        metrics = await self.database.get_onchain_metrics(symbol)
        
        # Cache for 5 minutes
        await self.cache.set(cache_key, metrics, ttl=300)
        
        return metrics
```

### Risk Manager Service

```python
# In risk_manager/database.py
from shared.redis_client import RedisCacheManager

class RiskPostgresDatabase:
    def __init__(self):
        self.cache = RedisCacheManager(redis_url=settings.REDIS_URL)
        
    async def get_backtest_results(self, strategy_id: str):
        # Cache backtest results for 24 hours
        cache_key = f"backtest:{strategy_id}"
        cached = await self.cache.get(cache_key)
        if cached:
            return cached
        
        results = await self._fetch_backtest_from_db(strategy_id)
        await self.cache.set(cache_key, results, ttl=86400)
        
        return results
```

## Monitoring

### Redis Metrics

Monitor Redis health via:

1. **Docker Health Checks**
   ```bash
   docker inspect mastertrade_redis | grep -A 10 Health
   ```

2. **Redis CLI INFO**
   ```bash
   docker exec -it mastertrade_redis redis-cli INFO
   ```

3. **Redis Commander** (Optional GUI)
   ```yaml
   redis-commander:
     image: rediscommander/redis-commander:latest
     environment:
       - REDIS_HOSTS=local:redis:6379
     ports:
       - "8081:8081"
     depends_on:
       - redis
   ```

### Key Metrics to Monitor

- **Memory Usage**: Should stay under 2GB limit
- **Hit Rate**: Cache hits vs misses ratio
- **Evicted Keys**: Number of keys removed due to memory limit
- **Connected Clients**: Number of active connections
- **Commands/sec**: Request throughput

### Redis CLI Monitoring Commands

```bash
# Real-time statistics
redis-cli --stat

# Monitor all commands
redis-cli MONITOR

# Check memory usage
redis-cli INFO memory | grep used_memory_human

# Check client connections
redis-cli CLIENT LIST

# Check key count
redis-cli DBSIZE
```

## Troubleshooting

### Common Issues

1. **Connection Refused**
   ```bash
   # Check if Redis is running
   docker-compose ps redis
   
   # Check Redis logs
   docker-compose logs redis
   
   # Restart Redis
   docker-compose restart redis
   ```

2. **Out of Memory**
   ```bash
   # Check memory usage
   docker exec -it mastertrade_redis redis-cli INFO memory
   
   # Clear database (CAUTION!)
   docker exec -it mastertrade_redis redis-cli FLUSHDB
   ```

3. **High Latency**
   ```bash
   # Check slow log
   docker exec -it mastertrade_redis redis-cli SLOWLOG GET 10
   
   # Check for blocking operations
   docker exec -it mastertrade_redis redis-cli CLIENT LIST
   ```

### Performance Tuning

1. **Increase Memory Limit** (if needed)
   ```yaml
   # In docker-compose.yml
   command: redis-server --appendonly yes --maxmemory 4gb
   ```

2. **Adjust Eviction Policy**
   ```yaml
   # Options: allkeys-lru, volatile-lru, allkeys-random, volatile-random, volatile-ttl, noeviction
   command: redis-server --maxmemory-policy allkeys-lfu
   ```

3. **Connection Pooling**
   ```python
   cache = RedisCacheManager(
       redis_url="redis://localhost:6379",
       max_connections=100  # Increase for high-load scenarios
   )
   ```

## Security

### Production Recommendations

1. **Enable Authentication**
   ```yaml
   command: redis-server --requirepass your_secure_password
   ```

2. **Use TLS/SSL**
   ```yaml
   command: redis-server --tls-port 6380 --port 0 --tls-cert-file /path/to/cert --tls-key-file /path/to/key
   ```

3. **Network Isolation**
   - Keep Redis on internal network only
   - Don't expose port 6379 to public internet
   - Use VPN or SSH tunneling for remote access

4. **Backup Configuration**
   ```bash
   # Manual backup
   docker exec mastertrade_redis redis-cli BGSAVE
   
   # Copy RDB file
   docker cp mastertrade_redis:/data/dump.rdb ./backup/
   ```

## Maintenance

### Regular Tasks

1. **Monitor Memory Usage**
   ```bash
   # Add to cron
   docker exec mastertrade_redis redis-cli INFO memory | grep used_memory_human
   ```

2. **Check for Slow Queries**
   ```bash
   docker exec mastertrade_redis redis-cli SLOWLOG GET 100
   ```

3. **Backup AOF File**
   ```bash
   docker cp mastertrade_redis:/data/appendonly.aof ./backup/
   ```

4. **Optimize AOF File**
   ```bash
   docker exec mastertrade_redis redis-cli BGREWRITEAOF
   ```

## References

- [Redis Official Documentation](https://redis.io/documentation)
- [Redis Python Client](https://redis-py.readthedocs.io/)
- [Redis Best Practices](https://redis.io/topics/memory-optimization)
- [Redis Caching Patterns](https://redis.io/topics/lru-cache)

## Support

For issues or questions:
1. Check logs: `docker-compose logs redis`
2. Review this documentation
3. Consult Redis official documentation
4. Contact system administrator
