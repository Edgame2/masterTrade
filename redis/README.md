# Redis Persistence & Backup System

Complete persistence configuration and backup solution for MasterTrade Redis.

## Quick Start

### 1. Start Redis with Custom Config

```bash
cd /home/neodyme/Documents/Projects/masterTrade

# Restart Redis with new config
docker-compose up -d redis

# Verify Redis is running
docker logs mastertrade_redis

# Check persistence enabled
docker exec mastertrade_redis redis-cli CONFIG GET appendonly
docker exec mastertrade_redis redis-cli CONFIG GET save
```

### 2. Test Manual Backup

```bash
cd redis/backups

# Run backup
./backup_redis.sh

# Verify backups created
ls -lh data/rdb/
ls -lh data/aof/
```

### 3. Test Monitoring

```bash
# Check Redis health
./monitor_redis.sh
```

---

## Files Overview

| File | Purpose | Lines |
|------|---------|-------|
| `redis.conf` | Production Redis configuration | ~250 |
| `backups/backup_redis.sh` | Daily backup script | ~350 |
| `backups/restore_redis.sh` | Restore utility | ~250 |
| `backups/monitor_redis.sh` | Health monitoring | ~250 |

---

## Features

✅ **Dual Persistence**: AOF (everysec) + RDB snapshots  
✅ **Automated Backups**: Daily RDB and AOF backups  
✅ **Compression**: Gzip compression (~80-90% reduction)  
✅ **Verification**: SHA-256 checksums  
✅ **Retention**: 30-day automatic cleanup  
✅ **Monitoring**: Health checks every 15 minutes  
✅ **Recovery**: Multiple restore modes  
✅ **Alerts**: Integration with alert system  

---

## Persistence Configuration

### AOF (Append-Only File)
- **fsync**: Every second (good balance)
- **Rewrite**: Automatic at 100% growth
- **Hybrid**: RDB-AOF preamble for faster loading

### RDB (Snapshots)
- After 1 hour if ≥ 1 key changed
- After 5 minutes if ≥ 100 keys changed
- After 1 minute if ≥ 10,000 keys changed

---

## Usage

### Backup

```bash
cd /path/to/redis/backups

# Manual backup
./backup_redis.sh

# Check logs
tail -f data/logs/backup_redis_*.log
```

### Restore

```bash
# List backups
./restore_redis.sh --list

# Restore latest
./restore_redis.sh --latest

# Restore specific file
./restore_redis.sh data/rdb/dump_20251112_120000.rdb.gz
```

### Monitor

```bash
# Health check
./monitor_redis.sh

# Redis info
docker exec mastertrade_redis redis-cli INFO
docker exec mastertrade_redis redis-cli INFO memory
docker exec mastertrade_redis redis-cli INFO persistence
```

---

## Automation

### Cron Setup

```bash
# Edit crontab
crontab -e

# Add jobs
0 3 * * * cd /path/to/redis/backups && ./backup_redis.sh >> data/logs/backup_cron.log 2>&1
*/15 * * * * cd /path/to/redis/backups && ./monitor_redis.sh >> data/logs/monitor_cron.log 2>&1
```

---

## Emergency Recovery

```bash
# 1. Stop services
docker-compose stop

# 2. Restore Redis
cd redis/backups
./restore_redis.sh --latest

# 3. Restart
docker-compose up -d redis
```

---

## Monitoring Metrics

| Metric | Threshold | Severity |
|--------|-----------|----------|
| Memory Usage | > 90% | Warning |
| Backup Age | > 25 hours | Critical |
| RDB Save Status | Failed | Critical |
| AOF Rewrite | Failed | High |
| Evicted Keys | Increasing | Warning |

---

## Directory Structure

```
redis/
├── redis.conf                    # Redis configuration
├── REDIS_PERSISTENCE_COMPLETE.md # Implementation report
├── README.md                     # This file
└── backups/
    ├── backup_redis.sh          # Backup script
    ├── restore_redis.sh         # Restore script
    ├── monitor_redis.sh         # Monitoring script
    └── data/                    # Created on first run
        ├── rdb/                 # RDB backups
        ├── aof/                 # AOF backups
        ├── metadata/            # Backup metadata
        └── logs/                # Operation logs
```

---

## Troubleshooting

### Redis Won't Start

```bash
# Check logs
docker logs mastertrade_redis

# Test config
docker run --rm -v $(pwd)/redis.conf:/redis.conf redis:7-alpine \
  redis-server /redis.conf --test-memory 1
```

### Backup Fails

```bash
# Check disk space
df -h

# Check container
docker ps | grep redis

# View logs
cat backups/data/logs/backup_redis_*.log
```

### AOF Corruption

```bash
# Repair AOF
docker exec mastertrade_redis redis-check-aof --fix /data/appendonly.aof

# Or restore from backup
cd backups
./restore_redis.sh --latest
```

---

## Documentation

📖 **Full Documentation**: See `REDIS_PERSISTENCE_COMPLETE.md`

Topics covered:
- Configuration details
- Backup procedures
- Restore procedures
- Monitoring setup
- Troubleshooting
- Performance tuning

---

## Status

✅ **Implementation**: COMPLETE  
✅ **Configuration**: Production-ready  
✅ **Scripts**: Tested and executable  
✅ **Documentation**: Comprehensive  

**Last Updated**: 2025-11-12
