# Local PostgreSQL Configuration - MasterTrade System

## Overview
The MasterTrade system has been configured to use a local PostgreSQL database running on the host machine instead of a containerized PostgreSQL instance.

## Changes Made

### 1. Docker Compose Configuration (`docker-compose.yml`)

#### Removed Services:
- **Containerized PostgreSQL** (`postgres` service) - Removed completely
- **PgBouncer** - Removed as it depended on the containerized PostgreSQL

#### Updated Environment Variables:
All microservices now connect to the host PostgreSQL using the host's actual IP address: `192.168.1.15`

Services updated:
- `market_data_service` - POSTGRES_HOST=192.168.1.15
- `data_access_api` - POSTGRES_HOST=192.168.1.15
- `alert_system` - DATABASE_URL uses 192.168.1.15
- `strategy_service` - POSTGRES_HOST=192.168.1.15
- `order_executor` - POSTGRES_HOST=192.168.1.15
- `risk_manager` - POSTGRES_HOST=192.168.1.15
- `api_gateway` - POSTGRES_HOST=192.168.1.15

#### Kept Services:
- **TimescaleDB** - Still runs as a container (separate time-series database on port 5433)
- All other microservices continue to run in containers

### 2. Host PostgreSQL Configuration

#### Verified Settings:
- **PostgreSQL Version**: 17
- **Listen Addresses**: `*` (all interfaces)
- **Port**: 5432
- **Authentication**: MD5/SCRAM-SHA-256

#### pg_hba.conf Rules:
The following authentication rules allow Docker containers to connect:
```
host    all             all             172.17.0.0/16           md5
host    all             all             172.18.0.0/16           md5
```

### 3. Database Credentials

Credentials remain the same (from `.env` file):
- **Database Name**: mastertrade
- **Username**: mastertrade
- **Password**: mastertrade

### 4. Network Configuration

#### Docker Network:
- **Network Name**: mastertrade_mastertrade_network
- **Subnet**: 172.18.0.0/16
- **Gateway**: 172.18.0.1

#### Host Access:
- Containers connect to host PostgreSQL via: `192.168.1.15:5432`
- Alternative hostnames tried:
  - `host.docker.internal` - DNS resolution issues
  - `172.17.0.1` - Wrong network (docker0 bridge not active)
  - `172.18.0.1` - Gateway not accessible from containers
  - **192.168.1.15** - ✅ **WORKING** (host's actual IP address)

## Validation Steps

### 1. Verify Host PostgreSQL is Running:
```bash
sudo systemctl status postgresql
```

### 2. Check PostgreSQL is Listening:
```bash
ss -tlnp | grep 5432
```
Expected output: `0.0.0.0:5432` and `[::]:5432`

### 3. Test Connection from Host:
```bash
PGPASSWORD=mastertrade psql -h localhost -U mastertrade -d mastertrade -c "SELECT COUNT(*) FROM market_data;"
```

### 4. Test Connection from Container:
```bash
docker exec mastertrade_strategy python -c "import socket; s = socket.socket(); s.settimeout(2); result = s.connect_ex(('192.168.1.15', 5432)); print('Connection result:', result); s.close()"
```
Expected output: `Connection result: 0` (success)

### 5. Check Container Environment:
```bash
docker exec mastertrade_strategy printenv | grep POSTGRES_HOST
```
Expected output: `POSTGRES_HOST=192.168.1.15`

### 6. Verify Strategy Service Logs:
```bash
docker logs mastertrade_strategy 2>&1 | grep -E "(PostgreSQL|Connected)" | tail -10
```
Should see successful connection messages, no "[Errno 111] Connect call failed" errors.

## Data Verification

The host PostgreSQL contains the required market data:
```sql
-- Total records: 727,867 (as of configuration)
SELECT COUNT(*) FROM market_data;

-- BTCUSDC 1h records: 735 (Oct 11 - Nov 11, 2025)
SELECT COUNT(*) FROM market_data WHERE data->>'symbol' = 'BTCUSDC' AND data->>'interval' = '1h';

-- JSONB structure example:
SELECT data FROM market_data LIMIT 1;
-- Returns: {"id": "BTCUSDC_1h_...", "symbol": "BTCUSDC", "volume": 310.48, "interval": "1h",
--           "low_price": 110974.63, "timestamp": "2025-10-11T19:00:00Z", 
--           "open_price": 112080.99, "high_price": 112149.0, "close_price": 111312.36}
```

## Deployment

To start the system with the new configuration:

```bash
cd /home/neodyme/Documents/Projects/masterTrade
docker compose down
docker compose up -d
```

## Benefits

1. **Data Persistence**: Market data persists independently of Docker containers
2. **Performance**: Direct connection to local PostgreSQL (no network overhead)
3. **Management**: Easier database administration and backups
4. **Resource Efficiency**: No containerized PostgreSQL consuming Docker resources
5. **Flexibility**: Can access database directly from host for queries and maintenance

## Important Notes

### Network Dependency:
The configuration uses the host's actual IP address (`192.168.1.15`). If the host's IP changes:
1. Update `docker-compose.yml` with the new IP
2. Restart all containers: `docker compose down && docker compose up -d`

### Alternative Approach:
If host IP is dynamic (DHCP), consider:
1. Setting a static IP for the host machine
2. Or using Docker's host network mode for specific services

### Security Considerations:
- PostgreSQL is accessible from the Docker network (172.18.0.0/16)
- Authentication is enforced (MD5/SCRAM-SHA-256)
- Default credentials should be changed for production
- Consider using SSL/TLS for PostgreSQL connections in production

## Troubleshooting

### Issue: Containers can't connect to PostgreSQL
**Check 1**: Verify PostgreSQL is listening on all interfaces
```bash
sudo -u postgres psql -c "SHOW listen_addresses;"
```
Should return: `*`

**Check 2**: Verify pg_hba.conf allows Docker networks
```bash
sudo cat /etc/postgresql/17/main/pg_hba.conf | grep -E "172\.(17|18)"
```

**Check 3**: Test connection from container
```bash
docker exec mastertrade_strategy python -c "import socket; s = socket.socket(); s.settimeout(2); print(s.connect_ex(('192.168.1.15', 5432))); s.close()"
```

### Issue: Host IP changed
1. Find new IP: `ip -4 addr show | grep inet`
2. Update `docker-compose.yml`: Replace all instances of `192.168.1.15` with new IP
3. Restart: `docker compose down && docker compose up -d`

## Files Modified

- `docker-compose.yml` - Removed postgres service, updated POSTGRES_HOST to 192.168.1.15

## Files NOT Modified

- `/etc/postgresql/17/main/postgresql.conf` - Already configured correctly
- `/etc/postgresql/17/main/pg_hba.conf` - Already had Docker network rules
- `.env` - Database credentials remain unchanged

---

**Configuration Date**: 2025-11-14  
**Configured By**: GitHub Copilot  
**PostgreSQL Version**: 17  
**Docker Network**: mastertrade_mastertrade_network (172.18.0.0/16)
