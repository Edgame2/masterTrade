# MasterTrade Operations Runbook

**Version**: 1.0  
**Last Updated**: November 12, 2025  
**Maintained By**: Operations Team

---

## Table of Contents

1. [System Overview](#system-overview)
2. [Service Architecture](#service-architecture)
3. [Daily Operations](#daily-operations)
4. [Common Issues & Troubleshooting](#common-issues--troubleshooting)
5. [Service Management](#service-management)
6. [Database Operations](#database-operations)
7. [Backup & Recovery](#backup--recovery)
8. [Monitoring & Alerts](#monitoring--alerts)
9. [Incident Response](#incident-response)
10. [Escalation Procedures](#escalation-procedures)
11. [Maintenance Windows](#maintenance-windows)
12. [Performance Tuning](#performance-tuning)

---

## System Overview

### System Status
- **Environment**: Production
- **Deployment Platform**: Docker Compose
- **Database**: PostgreSQL 15
- **Message Broker**: RabbitMQ 3.12
- **Cache Layer**: Redis 7
- **Monitoring**: Prometheus + Grafana

### Service Inventory

| Service | Port | Health Check | Critical? |
|---------|------|--------------|-----------|
| PostgreSQL | 5432 | `pg_isready -U mastertrade` | ✅ Yes |
| RabbitMQ | 5672/15672 | `rabbitmq-diagnostics ping` | ✅ Yes |
| Redis | 6379 | `redis-cli ping` | ✅ Yes |
| Market Data Service | 8000 | `http://localhost:8000/health` | ✅ Yes |
| Data Access API | 8005 | `http://localhost:8005/health` | ⚠️ High |
| Strategy Service | 8006 | `http://localhost:8006/health` | ✅ Yes |
| Alert System | 8007 | `http://localhost:8007/health` | ⚠️ High |
| Risk Manager | 8080 | `http://localhost:8080/health` | ✅ Yes |
| Order Executor | 8081 | `http://localhost:8081/health` | ✅ Yes |
| Monitoring UI | 3000 | `http://localhost:3000` | ⚠️ Medium |
| Prometheus | 9090 | `http://localhost:9090/-/healthy` | ⚠️ Medium |
| Grafana | 3000 | `http://localhost:3000/api/health` | ⚠️ Medium |

---

## Service Architecture

### Data Flow
```
Market Data Sources
    ↓
Market Data Service (collectors)
    ↓
RabbitMQ (message routing)
    ↓
Strategy Service (signal generation)
    ↓
Risk Manager (validation)
    ↓
Order Executor (execution)
    ↓
PostgreSQL (persistence)
```

### Dependencies
- **Strategy Service** depends on: PostgreSQL, RabbitMQ, Redis, Market Data Service
- **Order Executor** depends on: PostgreSQL, RabbitMQ, Risk Manager
- **Risk Manager** depends on: PostgreSQL, RabbitMQ
- **Market Data Service** depends on: PostgreSQL, RabbitMQ, Redis
- **Alert System** depends on: PostgreSQL

---

## Daily Operations

### Morning Checklist (9:00 AM)

1. **Check Service Health**
   ```bash
   ./status.sh
   ```
   - All services should show "RUNNING"
   - Check for any restart events in last 24h

2. **Verify Strategy Generation**
   ```bash
   # Check if daily generation completed (runs at 3 AM UTC)
   docker logs mastertrade_strategy | grep "Strategy generation completed"
   ```
   - Should see 500 strategies generated
   - Backtest completion within 3 hours

3. **Check Data Collection**
   ```bash
   curl http://localhost:8000/health/collectors
   ```
   - All collectors should be "healthy" or "degraded" (not "failed")
   - Review any circuit breaker activations

4. **Review Alert History**
   ```bash
   curl http://localhost:8007/api/alerts/recent?hours=24 | jq .
   ```
   - Check for critical alerts
   - Verify alert delivery success rate >95%

5. **Check Database Size**
   ```bash
   docker exec mastertrade_postgres psql -U mastertrade -c "
   SELECT pg_size_pretty(pg_database_size('mastertrade'));"
   ```
   - Monitor growth rate
   - Alert if >80% of disk capacity

6. **Verify Backup Completion**
   ```bash
   ls -lh database/backups/daily/
   ls -lh redis/backups/
   ```
   - Daily backups should exist from last night
   - Check backup age and file size

### Evening Checklist (6:00 PM)

1. **Review Trading Performance**
   - Open Grafana: http://localhost:3000
   - Check "Trading Performance" dashboard
   - Verify P&L, win rate, drawdown metrics

2. **Check Active Strategies**
   ```bash
   curl http://localhost:8006/api/strategies/active | jq '.count'
   ```
   - Should match MAX_ACTIVE_STRATEGIES setting (default: 2-10)

3. **Review System Metrics**
   - Open Prometheus: http://localhost:9090
   - Check API latency (target: p95 <200ms)
   - Check message queue depth (should be <1000)

4. **Verify Redis Memory**
   ```bash
   docker exec mastertrade_redis redis-cli INFO memory | grep used_memory_human
   ```
   - Should be <2GB (maxmemory limit)

---

## Common Issues & Troubleshooting

### Issue 1: Service Won't Start

**Symptoms**: Service container exits immediately or restarts continuously

**Diagnosis**:
```bash
# Check logs
docker logs mastertrade_<service_name>

# Check container status
docker ps -a | grep mastertrade

# Check resource usage
docker stats --no-stream
```

**Common Causes & Solutions**:

1. **Database Connection Failure**
   - **Cause**: PostgreSQL not ready
   - **Solution**: Wait for PostgreSQL health check, then restart service
   ```bash
   docker-compose restart <service_name>
   ```

2. **Port Already in Use**
   - **Cause**: Another process using the port
   - **Solution**: Find and stop conflicting process
   ```bash
   sudo lsof -i :<port_number>
   sudo kill -9 <PID>
   docker-compose up -d <service_name>
   ```

3. **Missing Environment Variables**
   - **Cause**: .env file not loaded
   - **Solution**: Verify .env exists and reload
   ```bash
   cat .env | grep <VARIABLE_NAME>
   docker-compose down
   docker-compose up -d
   ```

4. **Out of Memory**
   - **Cause**: Container memory limit exceeded
   - **Solution**: Increase memory limit in docker-compose.yml
   ```yaml
   services:
     <service_name>:
       deploy:
         resources:
           limits:
             memory: 2G
   ```

### Issue 2: High Database CPU Usage

**Symptoms**: PostgreSQL using >80% CPU, slow queries

**Diagnosis**:
```bash
# Check active queries
docker exec mastertrade_postgres psql -U mastertrade -c "
SELECT pid, now() - pg_stat_activity.query_start AS duration, query 
FROM pg_stat_activity 
WHERE state = 'active' AND now() - pg_stat_activity.query_start > interval '5 seconds'
ORDER BY duration DESC;"

# Check table sizes
docker exec mastertrade_postgres psql -U mastertrade -c "
SELECT schemaname, tablename, pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables 
WHERE schemaname = 'public' 
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC 
LIMIT 10;"
```

**Solutions**:

1. **Kill Long-Running Query**
   ```bash
   docker exec mastertrade_postgres psql -U mastertrade -c "
   SELECT pg_terminate_backend(<pid>);"
   ```

2. **Run VACUUM ANALYZE**
   ```bash
   docker exec mastertrade_postgres psql -U mastertrade -c "VACUUM ANALYZE;"
   ```

3. **Check Missing Indexes**
   ```bash
   docker exec mastertrade_postgres psql -U mastertrade -c "
   SELECT schemaname, tablename, attname, n_distinct, correlation 
   FROM pg_stats 
   WHERE schemaname = 'public' AND n_distinct > 100 
   ORDER BY n_distinct DESC;"
   ```

4. **Deploy PgBouncer** (if not already deployed)
   ```bash
   # Uncomment PgBouncer in docker-compose.yml
   docker-compose up -d pgbouncer
   ```

### Issue 3: RabbitMQ Queue Buildup

**Symptoms**: Message queue depth >10,000, consumers lagging

**Diagnosis**:
```bash
# Check queue depths
curl -u guest:guest http://localhost:15672/api/queues | jq '.[] | {name: .name, messages: .messages}'

# Check consumer status
curl -u guest:guest http://localhost:15672/api/consumers | jq '.[] | {queue: .queue.name, state: .state}'
```

**Solutions**:

1. **Restart Slow Consumer**
   ```bash
   docker-compose restart strategy_service
   ```

2. **Purge Old Messages** (if messages are stale)
   ```bash
   curl -u guest:guest -X DELETE http://localhost:15672/api/queues/%2F/<queue_name>/contents
   ```

3. **Scale Consumers** (increase processing capacity)
   ```yaml
   # In docker-compose.yml
   services:
     strategy_service:
       deploy:
         replicas: 2
   ```

4. **Check for Poison Messages**
   ```bash
   # Inspect failed messages in dead letter queue
   docker exec mastertrade_rabbitmq rabbitmqadmin get queue=strategy_service_dlq count=10
   ```

### Issue 4: Redis Out of Memory

**Symptoms**: Redis evicting keys, cache misses increasing

**Diagnosis**:
```bash
# Check memory usage
docker exec mastertrade_redis redis-cli INFO memory

# Check eviction stats
docker exec mastertrade_redis redis-cli INFO stats | grep evicted

# Check key count
docker exec mastertrade_redis redis-cli DBSIZE
```

**Solutions**:

1. **Flush Old Cache** (if safe)
   ```bash
   docker exec mastertrade_redis redis-cli FLUSHDB
   ```

2. **Increase Memory Limit**
   ```bash
   # Edit redis.conf
   maxmemory 4gb
   
   # Restart Redis
   docker-compose restart redis
   ```

3. **Adjust Eviction Policy**
   ```bash
   # Edit redis.conf
   maxmemory-policy allkeys-lru
   ```

4. **Check for Memory Leaks**
   ```bash
   # Find largest keys
   docker exec mastertrade_redis redis-cli --bigkeys
   ```

### Issue 5: Strategy Service Not Generating Strategies

**Symptoms**: No strategies generated at 3 AM UTC, backtest queue empty

**Diagnosis**:
```bash
# Check scheduler status
docker logs mastertrade_strategy | grep "schedule_daily_generation"

# Check last generation timestamp
curl http://localhost:8006/api/strategies/generation/status | jq '.last_generation'

# Check database for recent strategies
docker exec mastertrade_postgres psql -U mastertrade -c "
SELECT COUNT(*), MAX(created_at) FROM strategies WHERE created_at > NOW() - INTERVAL '24 hours';"
```

**Solutions**:

1. **Manually Trigger Generation**
   ```bash
   curl -X POST http://localhost:8006/api/strategies/generate \
     -H "Content-Type: application/json" \
     -d '{"count": 500}'
   ```

2. **Check Price Prediction Service**
   ```bash
   docker logs mastertrade_strategy | grep "PricePredictionService"
   ```

3. **Verify Market Data Availability**
   ```bash
   curl http://localhost:8000/api/v1/historical/BTCUSDT/1h?days=90 | jq '.data | length'
   ```
   - Should return >2000 data points

4. **Restart Strategy Service**
   ```bash
   docker-compose restart strategy_service
   ```

### Issue 6: Alert Notifications Not Sending

**Symptoms**: Alerts created but not delivered, delivery failures in logs

**Diagnosis**:
```bash
# Check alert delivery status
curl http://localhost:8007/api/alerts/history?limit=50 | jq '.alerts[] | {id, status, channels}'

# Check notification channel health
curl http://localhost:8007/api/notifications/health | jq .

# Check logs
docker logs mastertrade_alert_system | grep -i error
```

**Solutions**:

1. **Verify Channel Configuration**
   ```bash
   # Check environment variables
   docker exec mastertrade_alert_system env | grep -E "SMTP|TWILIO|TELEGRAM"
   ```

2. **Test Email Channel**
   ```bash
   curl -X POST http://localhost:8007/api/notifications/test \
     -H "Content-Type: application/json" \
     -d '{"channel": "email", "recipient": "test@example.com"}'
   ```

3. **Check Rate Limits**
   - Email: 100/hour (SMTP provider limits)
   - SMS: 50/hour (Twilio limits)
   - Telegram: 30/second (API limits)

4. **Review Failed Alerts**
   ```bash
   curl http://localhost:8007/api/alerts/history?status=failed | jq .
   ```

---

## Service Management

### Starting Services

**Full System Start**:
```bash
cd /home/neodyme/Documents/Projects/masterTrade
docker-compose up -d
```

**Start Specific Service**:
```bash
docker-compose up -d <service_name>
```

**Start with Logs**:
```bash
docker-compose up <service_name>
```

### Stopping Services

**Stop All Services**:
```bash
./stop.sh
# OR
docker-compose down
```

**Stop Specific Service**:
```bash
docker-compose stop <service_name>
```

**Stop with Volume Cleanup** (⚠️ DELETES DATA):
```bash
docker-compose down -v
```

### Restarting Services

**Restart All Services**:
```bash
./restart.sh
# OR
docker-compose restart
```

**Restart Specific Service**:
```bash
docker-compose restart <service_name>
```

**Restart with Rebuild**:
```bash
docker-compose up -d --build <service_name>
```

### Viewing Logs

**Real-time Logs (All Services)**:
```bash
docker-compose logs -f
```

**Real-time Logs (Specific Service)**:
```bash
docker-compose logs -f <service_name>
```

**Last 100 Lines**:
```bash
docker logs --tail 100 mastertrade_<service_name>
```

**Search Logs**:
```bash
docker logs mastertrade_<service_name> 2>&1 | grep -i "error"
```

**Export Logs**:
```bash
docker logs mastertrade_<service_name> > logs/<service_name>_$(date +%Y%m%d).log
```

### Service Status Check

**Quick Status**:
```bash
./status.sh
```

**Detailed Status**:
```bash
docker-compose ps
docker stats --no-stream
```

**Health Checks**:
```bash
# All services
for port in 8000 8005 8006 8007 8080 8081; do
  echo "Port $port:"
  curl -s http://localhost:$port/health | jq -r '.status // "UNREACHABLE"'
done
```

---

## Database Operations

### PostgreSQL Management

**Connect to Database**:
```bash
docker exec -it mastertrade_postgres psql -U mastertrade -d mastertrade
```

**Run SQL File**:
```bash
docker exec -i mastertrade_postgres psql -U mastertrade -d mastertrade < script.sql
```

**Database Size**:
```bash
docker exec mastertrade_postgres psql -U mastertrade -c "
SELECT 
  pg_size_pretty(pg_database_size('mastertrade')) as database_size,
  pg_size_pretty(pg_total_relation_size('strategies')) as strategies_table,
  pg_size_pretty(pg_total_relation_size('market_data')) as market_data_table;"
```

**Active Connections**:
```bash
docker exec mastertrade_postgres psql -U mastertrade -c "
SELECT count(*), application_name FROM pg_stat_activity 
WHERE state = 'active' GROUP BY application_name;"
```

**Slow Queries**:
```bash
docker exec mastertrade_postgres psql -U mastertrade -c "
SELECT pid, now() - pg_stat_activity.query_start AS duration, query, state
FROM pg_stat_activity
WHERE (now() - pg_stat_activity.query_start) > interval '5 seconds'
ORDER BY duration DESC;"
```

**Vacuum Statistics**:
```bash
docker exec mastertrade_postgres psql -U mastertrade -c "
SELECT schemaname, tablename, last_vacuum, last_autovacuum, last_analyze
FROM pg_stat_user_tables
WHERE schemaname = 'public'
ORDER BY last_autovacuum DESC NULLS LAST
LIMIT 10;"
```

### Redis Management

**Connect to Redis**:
```bash
docker exec -it mastertrade_redis redis-cli
```

**Check Memory**:
```bash
docker exec mastertrade_redis redis-cli INFO memory | grep used_memory_human
```

**Key Statistics**:
```bash
docker exec mastertrade_redis redis-cli INFO keyspace
docker exec mastertrade_redis redis-cli DBSIZE
```

**Find Largest Keys**:
```bash
docker exec mastertrade_redis redis-cli --bigkeys
```

**Flush Cache** (⚠️ Use with caution):
```bash
docker exec mastertrade_redis redis-cli FLUSHDB
```

**Monitor Commands**:
```bash
docker exec mastertrade_redis redis-cli MONITOR
```

---

## Backup & Recovery

### PostgreSQL Backup

**Manual Full Backup**:
```bash
cd database/backups
./backup_full.sh mastertrade
```

**Manual Incremental Backup**:
```bash
cd database/backups
./backup_incremental.sh
```

**Automated Backups** (setup cron):
```bash
cd database/backups
./setup_cron.sh
```

**List Backups**:
```bash
cd database/backups
./restore_backup.sh --list
```

**Restore Latest Backup**:
```bash
cd database/backups
./restore_backup.sh --latest
```

**Restore Specific Backup**:
```bash
cd database/backups
./restore_backup.sh daily/mastertrade_backup_20251112_020000.sql.gz
```

**Monitor Backup Health**:
```bash
cd database/backups
./monitor_backups.sh
```

### Redis Backup

**Manual Backup**:
```bash
cd redis/backups
./backup_redis.sh
```

**List Backups**:
```bash
cd redis/backups
./restore_redis.sh --list
```

**Restore Latest**:
```bash
cd redis/backups
./restore_redis.sh --latest
```

**Monitor Redis Health**:
```bash
cd redis/backups
./monitor_redis.sh
```

### Disaster Recovery Procedure

**Scenario**: Complete system failure, need to restore from backups

1. **Stop All Services**:
   ```bash
   docker-compose down
   ```

2. **Restore PostgreSQL**:
   ```bash
   # Start only PostgreSQL
   docker-compose up -d postgres
   
   # Wait for PostgreSQL to be ready
   until docker exec mastertrade_postgres pg_isready -U mastertrade; do sleep 2; done
   
   # Restore from backup
   cd database/backups
   ./restore_backup.sh --latest
   ```

3. **Restore Redis** (optional, cache can rebuild):
   ```bash
   docker-compose up -d redis
   cd redis/backups
   ./restore_redis.sh --latest
   ```

4. **Start Remaining Services**:
   ```bash
   cd /home/neodyme/Documents/Projects/masterTrade
   docker-compose up -d
   ```

5. **Verify System Health**:
   ```bash
   ./status.sh
   
   # Check each service
   for port in 8000 8005 8006 8007 8080 8081; do
     curl http://localhost:$port/health
   done
   ```

6. **Verify Data Integrity**:
   ```bash
   # Check strategy count
   curl http://localhost:8006/api/strategies | jq '.count'
   
   # Check recent market data
   curl http://localhost:8000/api/v1/historical/BTCUSDT/1h?limit=10 | jq .
   ```

---

## Monitoring & Alerts

### Prometheus Queries

**Access Prometheus**: http://localhost:9090

**Useful Queries**:

1. **Service Uptime**:
   ```promql
   up{job=~".*mastertrade.*"}
   ```

2. **API Latency (p95)**:
   ```promql
   histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))
   ```

3. **Database Connection Count**:
   ```promql
   pg_stat_database_numbackends{datname="mastertrade"}
   ```

4. **RabbitMQ Queue Depth**:
   ```promql
   rabbitmq_queue_messages{queue=~"strategy_service.*"}
   ```

5. **Redis Memory Usage**:
   ```promql
   redis_memory_used_bytes / redis_memory_max_bytes * 100
   ```

6. **Strategy Generation Rate**:
   ```promql
   rate(strategy_generation_total[1h])
   ```

### Grafana Dashboards

**Access Grafana**: http://localhost:3000 (admin/admin)

**Available Dashboards**:
1. **System Health** - Services, HTTP metrics, database, RabbitMQ, Redis
2. **Data Sources** - Collector health, data rates, errors, latency
3. **Trading Performance** - P&L, positions, orders, signals, goals
4. **ML Models** - Accuracy, drift, predictions, training

**Key Metrics to Monitor**:
- Service uptime: Target >99.9%
- API p95 latency: Target <200ms
- Database connections: Alert if >80% of max
- Queue depth: Alert if >1000 messages
- Redis memory: Alert if >90% of maxmemory
- Strategy win rate: Target >55%

### Alert Configuration

**Alert Channels Configured**:
- Email (SMTP)
- SMS (Twilio)
- Telegram
- Discord
- Slack
- Webhooks

**Critical Alerts**:
1. Service Down (any critical service)
2. Database Connection Pool Exhausted
3. RabbitMQ Queue Depth >10,000
4. Redis Memory >90%
5. Backup Failed
6. Strategy Generation Failed
7. Order Execution Failure

**Alert Response Times**:
- **Critical** (P0): Immediate response (<15 minutes)
- **High** (P1): 1 hour
- **Medium** (P2): 4 hours
- **Low** (P3): Next business day

---

## Incident Response

### Incident Severity Levels

**P0 - Critical**:
- Complete system outage
- Data loss or corruption
- Security breach
- Trading halted

**P1 - High**:
- Service degradation affecting trading
- Database performance issues
- Multiple service failures
- Backup failures

**P2 - Medium**:
- Single service failure (non-critical)
- Data collection issues
- Monitoring system failure
- Alert delivery issues

**P3 - Low**:
- Minor UI issues
- Non-critical feature failures
- Documentation errors
- Cosmetic issues

### Incident Response Workflow

1. **Detection**:
   - Automated alert received
   - Monitoring system trigger
   - User report

2. **Assessment** (5 minutes):
   - Determine severity level
   - Identify affected services
   - Estimate impact scope

3. **Notification** (10 minutes):
   - Alert on-call engineer
   - Notify stakeholders if P0/P1
   - Update status page

4. **Investigation** (varies):
   - Check service logs
   - Review monitoring dashboards
   - Run diagnostic commands

5. **Mitigation** (varies):
   - Apply temporary fix
   - Failover to backup
   - Scale resources

6. **Resolution** (varies):
   - Apply permanent fix
   - Verify system stability
   - Update documentation

7. **Post-Mortem** (within 24h for P0/P1):
   - Root cause analysis
   - Action items
   - Prevention measures

### Incident Response Playbooks

#### Playbook 1: Database Connection Pool Exhausted

**Symptoms**: Services unable to connect to database, "max connections" errors

**Immediate Actions**:
1. Check current connections:
   ```bash
   docker exec mastertrade_postgres psql -U mastertrade -c "
   SELECT count(*) FROM pg_stat_activity WHERE state = 'active';"
   ```

2. Kill idle connections:
   ```bash
   docker exec mastertrade_postgres psql -U mastertrade -c "
   SELECT pg_terminate_backend(pid) FROM pg_stat_activity 
   WHERE state = 'idle' AND state_change < NOW() - INTERVAL '10 minutes';"
   ```

3. Restart service with most connections:
   ```bash
   docker-compose restart <service_name>
   ```

4. Deploy PgBouncer (permanent solution):
   ```bash
   # Enable in docker-compose.yml
   docker-compose up -d pgbouncer
   ```

#### Playbook 2: RabbitMQ Queue Buildup

**Symptoms**: Queue depth >10,000, consumer lag increasing

**Immediate Actions**:
1. Identify problematic queue:
   ```bash
   curl -u guest:guest http://localhost:15672/api/queues | jq '.[] | select(.messages > 10000)'
   ```

2. Restart consumer service:
   ```bash
   docker-compose restart strategy_service
   ```

3. If queue continues growing, purge old messages:
   ```bash
   curl -u guest:guest -X DELETE \
     http://localhost:15672/api/queues/%2F/<queue_name>/contents
   ```

4. Scale consumers:
   ```yaml
   # docker-compose.yml
   strategy_service:
     deploy:
       replicas: 2
   ```

#### Playbook 3: Complete System Outage

**Symptoms**: All services down, no response from any endpoint

**Immediate Actions**:
1. Check Docker daemon:
   ```bash
   sudo systemctl status docker
   sudo systemctl restart docker
   ```

2. Check disk space:
   ```bash
   df -h
   ```
   - If >95% full, clean up old logs and backups

3. Restart all services:
   ```bash
   ./restart.sh
   ```

4. If restart fails, restore from backup:
   - Follow Disaster Recovery Procedure above

5. Verify each service:
   ```bash
   ./status.sh
   ```

---

## Escalation Procedures

### On-Call Rotation

**Primary On-Call**: Operations Team Member 1  
**Secondary On-Call**: Operations Team Member 2  
**Escalation Contact**: Engineering Lead  
**Executive Contact**: CTO (P0 incidents only)

### Escalation Matrix

| Severity | Initial Response | Escalate After | Escalate To |
|----------|-----------------|----------------|-------------|
| P0 | Immediate | 15 minutes | Engineering Lead |
| P1 | 1 hour | 2 hours | Team Lead |
| P2 | 4 hours | 8 hours | Team Lead |
| P3 | Next day | 3 days | Team Lead |

### Contact Information

**Emergency Contacts**:
- Operations Team: ops@mastertrade.com
- Engineering Lead: lead@mastertrade.com
- Database Admin: dba@mastertrade.com
- Security Team: security@mastertrade.com

**External Vendors**:
- AWS Support: support.aws.amazon.com
- Docker Support: support.docker.com
- PostgreSQL Support: postgresql.org/support

---

## Maintenance Windows

### Scheduled Maintenance

**Frequency**: Monthly (first Sunday, 2:00 AM - 6:00 AM UTC)

**Pre-Maintenance Checklist**:
1. Notify users 7 days in advance
2. Create full system backup
3. Test rollback procedures
4. Prepare deployment scripts
5. Schedule team availability

**Maintenance Procedure**:
1. Enable maintenance mode
2. Stop trading strategies
3. Complete database migrations
4. Deploy service updates
5. Run smoke tests
6. Resume trading strategies
7. Monitor for 1 hour

**Post-Maintenance**:
1. Verify all services healthy
2. Check data integrity
3. Review performance metrics
4. Document changes
5. Send completion notification

### Emergency Maintenance

**Triggers**:
- Critical security vulnerability
- Data corruption detected
- Service unavailability >1 hour

**Procedure**:
1. Assess impact and urgency
2. Notify stakeholders immediately
3. Apply fix with expedited process
4. Extended monitoring period
5. Post-mortem within 24 hours

---

## Performance Tuning

### Database Optimization

**Check Query Performance**:
```sql
-- Slowest queries
SELECT query, mean_exec_time, calls
FROM pg_stat_statements
ORDER BY mean_exec_time DESC
LIMIT 10;

-- Most called queries
SELECT query, calls, mean_exec_time
FROM pg_stat_statements
ORDER BY calls DESC
LIMIT 10;
```

**Add Missing Indexes**:
```sql
-- Find unused indexes
SELECT schemaname, tablename, indexname, idx_scan
FROM pg_stat_user_indexes
WHERE idx_scan = 0 AND indexname NOT LIKE 'pg_%';

-- Add indexes for common queries
CREATE INDEX CONCURRENTLY idx_strategies_status ON strategies(status);
CREATE INDEX CONCURRENTLY idx_market_data_symbol_timestamp ON market_data(symbol, timestamp);
```

**Tune PostgreSQL Settings**:
```ini
# postgresql.conf
shared_buffers = 4GB          # 25% of RAM
effective_cache_size = 12GB   # 75% of RAM
work_mem = 50MB               # RAM / max_connections
maintenance_work_mem = 1GB
```

### Redis Optimization

**Memory Optimization**:
```bash
# Use appropriate eviction policy
CONFIG SET maxmemory-policy allkeys-lru

# Enable compression for large values
CONFIG SET lazyfree-lazy-eviction yes
```

**Performance Tuning**:
```bash
# Disable RDB snapshots if using AOF
CONFIG SET save ""

# Tune AOF rewrite
CONFIG SET auto-aof-rewrite-percentage 100
CONFIG SET auto-aof-rewrite-min-size 64mb
```

### Application Optimization

**Connection Pooling**:
- Deploy PgBouncer for PostgreSQL
- Use Redis connection pooling
- Configure appropriate pool sizes

**Caching Strategy**:
- Cache frequently accessed data (market data, indicators)
- Set appropriate TTLs (1-5 minutes for real-time data)
- Use cache-aside pattern

**Async Processing**:
- Use RabbitMQ for long-running tasks
- Implement task queues for batch operations
- Scale consumers based on queue depth

---

## Appendix

### Quick Command Reference

```bash
# Status checks
./status.sh
docker-compose ps
docker stats

# Service management
docker-compose up -d
docker-compose restart <service>
docker-compose logs -f <service>

# Database
docker exec -it mastertrade_postgres psql -U mastertrade
docker exec mastertrade_postgres pg_dump -U mastertrade > backup.sql

# Backups
cd database/backups && ./backup_full.sh mastertrade
cd redis/backups && ./backup_redis.sh

# Health checks
curl http://localhost:8000/health
curl http://localhost:8000/health/collectors
```

### Configuration Files

- **Docker Compose**: `docker-compose.yml`
- **Environment Variables**: `.env`
- **PostgreSQL Config**: `postgres/postgresql.conf`
- **Redis Config**: `redis/redis.conf`
- **RabbitMQ Config**: `rabbitmq/rabbitmq.config`
- **Prometheus Config**: `monitoring/prometheus/prometheus.yml`
- **Grafana Provisioning**: `monitoring/grafana/provisioning/`

### Log Locations

- **Application Logs**: `docker logs mastertrade_<service>`
- **PostgreSQL Logs**: `postgres_data/pg_log/`
- **RabbitMQ Logs**: `rabbitmq_data/log/`
- **Backup Logs**: `database/backups/*.log`, `redis/backups/*.log`

### Useful SQL Queries

```sql
-- Active strategies
SELECT id, name, status, performance_score FROM strategies WHERE status = 'active';

-- Recent trades
SELECT * FROM trades WHERE created_at > NOW() - INTERVAL '1 hour' ORDER BY created_at DESC;

-- System settings
SELECT * FROM settings;

-- Alert history
SELECT * FROM alert_history WHERE created_at > NOW() - INTERVAL '24 hours';

-- Collector health
SELECT name, status, last_success_at FROM data_source_health ORDER BY last_check_at DESC;
```

---

**End of Operations Runbook**  
**For updates or corrections, contact the Operations Team**
