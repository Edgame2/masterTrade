# PostgreSQL Automated Backup System - Documentation

## Table of Contents
1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Components](#components)
4. [Configuration](#configuration)
5. [Installation](#installation)
6. [Usage](#usage)
7. [Monitoring](#monitoring)
8. [Restore Procedures](#restore-procedures)
9. [Troubleshooting](#troubleshooting)
10. [Maintenance](#maintenance)

---

## Overview

The MasterTrade PostgreSQL Automated Backup System provides comprehensive data protection through:

- **Daily Full Backups**: Complete database dumps at 2:00 AM
- **Hourly Incremental Backups**: WAL archiving for point-in-time recovery (optional)
- **Automated Monitoring**: Health checks every 15 minutes
- **Intelligent Retention**: 30 days for full backups, 7 days for incremental
- **Alert Integration**: Automatic notifications via alert system
- **Verified Integrity**: SHA-256 checksums and gzip validation

### Key Features

✅ Fully automated backup and monitoring  
✅ Point-in-time recovery capability  
✅ Compression to save disk space (gzip level 6)  
✅ Checksum verification for data integrity  
✅ Automatic cleanup of old backups  
✅ Alert system integration for failures  
✅ Detailed logging for audit trails  
✅ Multiple restore modes (latest, specific, list)  

---

## Architecture

### Backup Flow

```
┌─────────────────┐
│  PostgreSQL DB  │
└────────┬────────┘
         │
    ┌────▼────┐
    │ pg_dump │ (Full Backup)
    └────┬────┘
         │
    ┌────▼──────────┐
    │ gzip compress │
    └────┬──────────┘
         │
    ┌────▼─────────────┐
    │ SHA-256 checksum │
    └────┬─────────────┘
         │
    ┌────▼────────────┐
    │ Store + Metadata│
    └─────────────────┘
```

### Incremental Backup Flow (WAL Archiving)

```
┌─────────────────┐
│  PostgreSQL DB  │
└────────┬────────┘
         │
    ┌────▼────────┐
    │ WAL Segment │
    └────┬────────┘
         │
    ┌────▼──────────┐
    │ archive_command│
    └────┬──────────┘
         │
    ┌────▼──────────┐
    │  WAL Archive  │
    └────┬──────────┘
         │
    ┌────▼───────────┐
    │ pg_basebackup  │ (Base Backup)
    └────────────────┘
```

### Directory Structure

```
database/backups/
├── backup_full.sh            # Daily full backup script
├── backup_incremental.sh     # Hourly incremental backup script
├── restore_backup.sh         # Restore utility
├── monitor_backups.sh        # Health monitoring script
├── setup_cron.sh            # Cron automation setup
└── data/
    ├── full/                # Full backup storage
    │   ├── mastertrade_full_20250112_020000.sql.gz
    │   ├── mastertrade_full_20250112_020000.meta
    │   └── ...
    ├── incremental/         # Incremental backups
    │   ├── wal/            # WAL archive files
    │   ├── base_*/         # Base backups
    │   └── metadata/       # Incremental metadata
    └── logs/               # Operation logs
        ├── backup_full_20250112_020000.log
        ├── backup_incremental_20250112_050000.log
        ├── monitor_backups.log
        └── restore_20250112_150000.log
```

---

## Components

### 1. Full Backup Script (`backup_full.sh`)

**Purpose**: Creates complete database dumps daily

**Features**:
- Uses `pg_dump` for logical backups
- Gzip compression (configurable level, default 6)
- SHA-256 checksum generation
- Metadata tracking (size, duration, version, checksum)
- Automatic cleanup based on retention policy (30 days)
- Alert system integration
- Detailed logging

**Usage**:
```bash
./backup_full.sh <database_name>

# Example
./backup_full.sh mastertrade
```

**Environment Variables**:
```bash
# PostgreSQL connection
export PGHOST=localhost
export PGPORT=5432
export PGUSER=postgres
export PGPASSWORD=your_password

# Backup configuration
export BACKUP_DIR=/path/to/backups/data
export RETENTION_DAYS=30
export COMPRESSION_LEVEL=6
```

### 2. Incremental Backup Script (`backup_incremental.sh`)

**Purpose**: Creates hourly incremental backups using WAL archiving

**Features**:
- Uses `pg_basebackup` for physical backups
- WAL file archiving for point-in-time recovery
- Automatic WAL switching
- 7-day retention for WAL files
- Base backup creation
- WAL integrity verification

**Usage**:
```bash
./backup_incremental.sh <database_name>

# Example
./backup_incremental.sh mastertrade
```

**Prerequisites**:
PostgreSQL must be configured for WAL archiving:

```sql
-- In postgresql.conf
archive_mode = on
wal_level = replica
archive_command = 'test ! -f /path/to/wal/%f && cp %p /path/to/wal/%f'

-- Reload configuration
SELECT pg_reload_conf();
```

### 3. Restore Script (`restore_backup.sh`)

**Purpose**: Restores PostgreSQL database from backups

**Features**:
- Three restore modes: list, latest, specific file
- Checksum verification before restore
- Database drop with user confirmation
- Post-restore validation
- Detailed logging

**Usage**:

```bash
# List available backups
./restore_backup.sh --list

# Restore latest backup
./restore_backup.sh --latest <target_database>

# Restore specific backup file
./restore_backup.sh <backup_file> <target_database>

# Examples
./restore_backup.sh --list
./restore_backup.sh --latest mastertrade_test
./restore_backup.sh data/full/mastertrade_full_20250112_020000.sql.gz mastertrade_restored
```

**Safety Features**:
- User confirmation before overwriting existing database
- Connection termination before drop
- Checksum verification
- Post-restore validation

### 4. Monitoring Script (`monitor_backups.sh`)

**Purpose**: Continuous health checks for backup system

**Features**:
- Backup age verification
- File integrity checks (gzip + checksum)
- Disk space monitoring
- Backup size trend analysis
- Backup count verification
- WAL archive health
- Alert integration

**Usage**:
```bash
./monitor_backups.sh
```

**Checks Performed**:
1. ✅ Backup directory existence
2. ✅ Last backup age (alert if > 25 hours)
3. ✅ Backup file integrity (gzip test + checksum)
4. ✅ Disk space availability (alert if < 10GB)
5. ✅ Backup size trends (detect anomalies)
6. ✅ Backup count (recent and total)
7. ✅ WAL archive health (if enabled)

**Environment Variables**:
```bash
export BACKUP_DIR=/path/to/backups/data
export MAX_BACKUP_AGE_HOURS=25
export MIN_DISK_SPACE_GB=10
export ALERT_ENDPOINT=http://localhost:8007/api/alerts/health
```

### 5. Cron Setup Script (`setup_cron.sh`)

**Purpose**: Automates backup and monitoring with cron jobs

**Features**:
- Automatic cron job creation
- Existing crontab backup
- Log directory creation
- Schedule verification
- Test run of monitoring

**Usage**:
```bash
./setup_cron.sh
```

**Cron Schedule**:
```cron
# Daily full backup at 2:00 AM
0 2 * * * cd /path/to/backups && ./backup_full.sh mastertrade

# Hourly incremental backup at :05
5 * * * * cd /path/to/backups && ./backup_incremental.sh mastertrade

# Monitoring every 15 minutes
*/15 * * * * cd /path/to/backups && ./monitor_backups.sh
```

---

## Configuration

### PostgreSQL Connection

Set environment variables for PostgreSQL connection:

```bash
export PGHOST=localhost
export PGPORT=5432
export PGUSER=postgres
export PGPASSWORD=your_secure_password
```

**Recommended**: Use `.pgpass` file for secure password storage:

```bash
# Create ~/.pgpass
echo "localhost:5432:mastertrade:postgres:your_password" > ~/.pgpass
chmod 600 ~/.pgpass
```

### Backup Configuration

```bash
# Backup directory (absolute path)
export BACKUP_DIR=/home/neodyme/Documents/Projects/masterTrade/database/backups/data

# Full backup retention (days)
export RETENTION_DAYS=30

# Incremental backup retention (days)
export WAL_RETENTION_DAYS=7

# Compression level (1-9, default 6)
export COMPRESSION_LEVEL=6

# Monitoring thresholds
export MAX_BACKUP_AGE_HOURS=25
export MIN_DISK_SPACE_GB=10

# Alert system endpoint
export ALERT_ENDPOINT=http://localhost:8007/api/alerts/health
```

### PostgreSQL Configuration for Incremental Backups

Edit `postgresql.conf`:

```ini
# Enable WAL archiving
archive_mode = on
wal_level = replica

# Archive command (adjust path)
archive_command = 'test ! -f /path/to/backups/data/incremental/wal/%f && cp %p /path/to/backups/data/incremental/wal/%f'

# Optional: increase WAL size for better performance
min_wal_size = 1GB
max_wal_size = 4GB
```

Restart PostgreSQL:
```bash
sudo systemctl restart postgresql
```

---

## Installation

### Step 1: Clone or Copy Scripts

```bash
cd /home/neodyme/Documents/Projects/masterTrade/database/backups
```

Ensure all scripts are present:
- `backup_full.sh`
- `backup_incremental.sh`
- `restore_backup.sh`
- `monitor_backups.sh`
- `setup_cron.sh`

### Step 2: Make Scripts Executable

```bash
chmod +x backup_full.sh
chmod +x backup_incremental.sh
chmod +x restore_backup.sh
chmod +x monitor_backups.sh
chmod +x setup_cron.sh
```

### Step 3: Configure PostgreSQL Connection

```bash
# Create .env file
cat > .env << EOF
export PGHOST=localhost
export PGPORT=5432
export PGUSER=postgres
export PGPASSWORD=your_password
export BACKUP_DIR=$(pwd)/data
EOF

# Load environment
source .env
```

### Step 4: Configure PostgreSQL for WAL Archiving (Optional)

```bash
# Edit postgresql.conf
sudo nano /etc/postgresql/*/main/postgresql.conf

# Add/modify:
archive_mode = on
wal_level = replica
archive_command = 'test ! -f /path/to/backups/data/incremental/wal/%f && cp %p /path/to/backups/data/incremental/wal/%f'

# Restart PostgreSQL
sudo systemctl restart postgresql
```

### Step 5: Test Manual Backup

```bash
# Test full backup
./backup_full.sh mastertrade

# Verify backup created
ls -lh data/full/

# Test monitoring
./monitor_backups.sh
```

### Step 6: Setup Automated Backups

```bash
# Run cron setup script
./setup_cron.sh

# Verify cron jobs installed
crontab -l | grep "MasterTrade PostgreSQL Backup"
```

### Step 7: Verify Installation

```bash
# Check cron logs after first scheduled run
tail -f data/logs/backup_full_cron.log
tail -f data/logs/monitor_cron.log
```

---

## Usage

### Manual Full Backup

```bash
cd /home/neodyme/Documents/Projects/masterTrade/database/backups

# Load environment
source .env

# Run backup
./backup_full.sh mastertrade

# Check results
ls -lh data/full/
cat data/logs/backup_full_$(date +%Y%m%d)*.log
```

### Manual Incremental Backup

```bash
# Ensure PostgreSQL is configured for WAL archiving
./backup_incremental.sh mastertrade

# Check WAL files
ls -lh data/incremental/wal/
```

### List Available Backups

```bash
./restore_backup.sh --list
```

Output example:
```
Available Full Backups:
-----------------------
mastertrade_full_20250112_020000.sql.gz (142 MB) - 2025-01-12 02:00:00
mastertrade_full_20250111_020000.sql.gz (140 MB) - 2025-01-11 02:00:00
mastertrade_full_20250110_020000.sql.gz (138 MB) - 2025-01-10 02:00:00
```

### Restore Latest Backup

```bash
# Restore to test database
./restore_backup.sh --latest mastertrade_test

# Restore to original database (will prompt for confirmation)
./restore_backup.sh --latest mastertrade
```

### Restore Specific Backup

```bash
# Find backup file
./restore_backup.sh --list

# Restore specific file
./restore_backup.sh data/full/mastertrade_full_20250110_020000.sql.gz mastertrade_restored
```

### Check Backup Health

```bash
# Manual health check
./monitor_backups.sh

# View monitoring logs
tail -f data/logs/monitor_backups.log
```

---

## Monitoring

### Health Check Indicators

The monitoring script checks:

| Check | Threshold | Severity |
|-------|-----------|----------|
| Backup Age | > 25 hours | Critical |
| Disk Space | < 10 GB | Critical |
| Disk Usage | > 90% | Critical |
| File Integrity | Corrupted | Critical |
| Backup Count | 0 recent | Critical |
| Size Decrease | > 30% | Warning |
| Size Increase | > 50% | Warning |

### Alert Integration

Alerts are sent to the alert system at `http://localhost:8007/api/alerts/health`

**Alert Types**:
- `backup_age` - Backup too old
- `disk_space` - Low disk space
- `backup_integrity` - Corrupted backup files
- `backup_count` - Missing backups
- `backup_health` - Overall health status

### Monitoring Logs

```bash
# Real-time monitoring
tail -f data/logs/monitor_cron.log

# Full backup logs
tail -f data/logs/backup_full_cron.log

# Incremental backup logs
tail -f data/logs/backup_incremental_cron.log
```

### Grafana Dashboard (Optional)

Create metrics from monitoring logs for visualization:

```json
{
  "backup_age_hours": 12,
  "disk_free_gb": 45,
  "disk_usage_percent": 72,
  "backup_count_total": 28,
  "backup_count_recent": 7,
  "corrupted_backups": 0,
  "last_backup_size_mb": 142
}
```

---

## Restore Procedures

### Emergency Restore (Production Down)

**Scenario**: Database corruption or complete data loss

**Steps**:

1. **Stop Application Services**
   ```bash
   docker-compose stop
   ```

2. **Identify Latest Backup**
   ```bash
   cd /home/neodyme/Documents/Projects/masterTrade/database/backups
   ./restore_backup.sh --list | head -5
   ```

3. **Restore Database**
   ```bash
   # This will drop and recreate the database
   ./restore_backup.sh --latest mastertrade
   
   # Confirm when prompted
   ```

4. **Verify Restoration**
   ```bash
   psql -h localhost -U postgres -d mastertrade -c "\dt"
   psql -h localhost -U postgres -d mastertrade -c "SELECT COUNT(*) FROM strategies;"
   ```

5. **Restart Services**
   ```bash
   cd ../..
   docker-compose up -d
   ```

### Point-in-Time Recovery (PITR)

**Scenario**: Need to restore to specific time (requires WAL archiving)

**Prerequisites**:
- Base backup exists
- WAL files available for target time

**Steps**:

1. **Stop PostgreSQL**
   ```bash
   sudo systemctl stop postgresql
   ```

2. **Backup Current Data** (if possible)
   ```bash
   sudo mv /var/lib/postgresql/*/main /var/lib/postgresql/*/main.backup
   ```

3. **Extract Base Backup**
   ```bash
   cd /var/lib/postgresql/*/
   sudo tar -xzf /path/to/backups/data/incremental/base_*/base.tar.gz
   ```

4. **Create recovery.conf**
   ```bash
   sudo nano /var/lib/postgresql/*/main/recovery.conf
   
   # Add:
   restore_command = 'cp /path/to/backups/data/incremental/wal/%f %p'
   recovery_target_time = '2025-01-12 14:30:00'
   recovery_target_action = 'promote'
   ```

5. **Start PostgreSQL**
   ```bash
   sudo systemctl start postgresql
   ```

6. **Verify Recovery**
   ```bash
   psql -h localhost -U postgres -d mastertrade -c "SELECT NOW();"
   ```

### Test Restore (Monthly Procedure)

**Purpose**: Verify backup integrity and restore procedures

**Frequency**: Monthly

**Steps**:

1. **Create Test Environment**
   ```bash
   psql -h localhost -U postgres -c "CREATE DATABASE mastertrade_restore_test;"
   ```

2. **Restore Latest Backup**
   ```bash
   ./restore_backup.sh --latest mastertrade_restore_test
   ```

3. **Verify Data Integrity**
   ```bash
   # Check table count
   psql -h localhost -U postgres -d mastertrade_restore_test -c "\dt" | wc -l
   
   # Check record counts
   psql -h localhost -U postgres -d mastertrade_restore_test -c "
     SELECT 'strategies' as table, COUNT(*) FROM strategies
     UNION ALL
     SELECT 'backtest_results', COUNT(*) FROM backtest_results
     UNION ALL
     SELECT 'market_data', COUNT(*) FROM market_data;
   "
   ```

4. **Compare with Production**
   ```bash
   # Production counts
   psql -h localhost -U postgres -d mastertrade -c "SELECT COUNT(*) FROM strategies;"
   
   # Test restore counts
   psql -h localhost -U postgres -d mastertrade_restore_test -c "SELECT COUNT(*) FROM strategies;"
   ```

5. **Document Results**
   ```bash
   cat > restore_test_$(date +%Y%m%d).txt << EOF
   Restore Test - $(date -Iseconds)
   Backup File: $(ls -t data/full/*.sql.gz | head -1)
   Restoration: SUCCESS
   Tables: XX
   Total Records: XXXXX
   Duration: X minutes
   Issues: None
   EOF
   ```

6. **Cleanup Test Database**
   ```bash
   psql -h localhost -U postgres -c "DROP DATABASE mastertrade_restore_test;"
   ```

---

## Troubleshooting

### Issue: Backup Script Fails with "Connection Refused"

**Symptoms**:
```
[ERROR] Failed to connect to PostgreSQL
psql: could not connect to server: Connection refused
```

**Solution**:
```bash
# Check PostgreSQL is running
sudo systemctl status postgresql

# Check PostgreSQL port
sudo netstat -tlnp | grep 5432

# Verify connection settings
echo "Host: $PGHOST, Port: $PGPORT, User: $PGUSER"

# Test connection manually
psql -h localhost -U postgres -d mastertrade -c "SELECT 1;"
```

### Issue: "Permission Denied" Creating Backup

**Symptoms**:
```
[ERROR] Failed to create backup directory
mkdir: cannot create directory: Permission denied
```

**Solution**:
```bash
# Check directory permissions
ls -ld database/backups/

# Fix ownership
sudo chown -R $(whoami):$(whoami) database/backups/

# Ensure write permissions
chmod 755 database/backups/
```

### Issue: Backup File Checksum Mismatch

**Symptoms**:
```
[ERROR] Checksum mismatch: mastertrade_full_20250112_020000.sql.gz
```

**Solution**:
```bash
# Backup file may be corrupted
# Remove corrupted backup
rm data/full/mastertrade_full_20250112_020000.sql.gz
rm data/full/mastertrade_full_20250112_020000.meta

# Run new backup
./backup_full.sh mastertrade
```

### Issue: WAL Archiving Not Working

**Symptoms**:
```
[WARNING] No WAL files found
[ERROR] archive_mode is not enabled
```

**Solution**:
```bash
# Check PostgreSQL configuration
psql -h localhost -U postgres -c "SHOW archive_mode;"
psql -h localhost -U postgres -c "SHOW wal_level;"

# If not enabled, edit postgresql.conf
sudo nano /etc/postgresql/*/main/postgresql.conf

# Add/modify:
archive_mode = on
wal_level = replica
archive_command = 'test ! -f /path/to/wal/%f && cp %p /path/to/wal/%f'

# Restart PostgreSQL
sudo systemctl restart postgresql

# Verify
psql -h localhost -U postgres -c "SHOW archive_mode;"
```

### Issue: Disk Space Full During Backup

**Symptoms**:
```
[ERROR] No space left on device
gzip: stdout: No space left on device
```

**Solution**:
```bash
# Check disk space
df -h

# Clean up old backups manually
find data/full/ -name "*.sql.gz" -mtime +30 -delete

# Clean up old WAL files
find data/incremental/wal/ -type f -mtime +7 -delete

# Consider reducing retention period
export RETENTION_DAYS=14

# Or move backups to external storage
```

### Issue: Cron Jobs Not Running

**Symptoms**:
- No backup files being created
- No monitoring logs updating

**Solution**:
```bash
# Check cron is running
sudo systemctl status cron

# Verify cron jobs installed
crontab -l | grep "MasterTrade"

# Check cron logs
tail -f /var/log/syslog | grep CRON

# Test manual execution
cd /home/neodyme/Documents/Projects/masterTrade/database/backups
./backup_full.sh mastertrade

# Ensure scripts have correct paths in cron
# Edit crontab if needed
crontab -e
```

### Issue: Restore Fails with "Database Does Not Exist"

**Symptoms**:
```
[ERROR] Failed to restore backup
psql: FATAL: database "mastertrade_test" does not exist
```

**Solution**:
```bash
# Create target database first
psql -h localhost -U postgres -c "CREATE DATABASE mastertrade_test;"

# Then restore
./restore_backup.sh --latest mastertrade_test
```

---

## Maintenance

### Weekly Maintenance

**Tasks**:
1. Check backup logs for errors
2. Verify disk space usage
3. Review monitoring alerts

**Commands**:
```bash
# Check recent backup logs
tail -100 data/logs/backup_full_cron.log

# Review errors
grep -i error data/logs/*.log

# Check disk usage
df -h | grep backups
du -sh data/full/ data/incremental/
```

### Monthly Maintenance

**Tasks**:
1. Perform test restore
2. Review backup size trends
3. Update documentation if needed
4. Verify alerting is working

**Commands**:
```bash
# Test restore
./restore_backup.sh --latest mastertrade_test

# Check backup sizes
ls -lh data/full/ | tail -30

# Verify alert system
curl -X GET http://localhost:8007/api/alerts
```

### Quarterly Maintenance

**Tasks**:
1. Review retention policies
2. Test disaster recovery procedures
3. Update backup scripts if needed
4. Verify off-site backup strategy

### Backup Retention Policy

**Current Settings**:
- Full backups: 30 days
- Incremental backups: 7 days
- Logs: 90 days (recommended)

**Adjust if Needed**:
```bash
# Increase retention
export RETENTION_DAYS=60
export WAL_RETENTION_DAYS=14

# Or decrease for disk space
export RETENTION_DAYS=14
export WAL_RETENTION_DAYS=3
```

### Disk Space Management

**Monitor Usage**:
```bash
# Check backup directory size
du -sh data/

# Check growth rate
du -sh data/full/ --time | sort -h

# Estimate required space
# Formula: daily_backup_size * retention_days * 1.2 (safety margin)
```

**Cleanup Strategy**:
```bash
# Manual cleanup of old backups
find data/full/ -name "*.sql.gz" -mtime +60 -delete
find data/full/ -name "*.meta" -mtime +60 -delete

# Clean old logs
find data/logs/ -name "*.log" -mtime +90 -delete
```

### Backup Verification Schedule

| Frequency | Task | Duration |
|-----------|------|----------|
| Continuous | Automated monitoring | 15 min intervals |
| Daily | Backup creation | 2:00 AM |
| Weekly | Log review | 30 minutes |
| Monthly | Test restore | 1-2 hours |
| Quarterly | Full DR test | 4-8 hours |

---

## Best Practices

### Security

1. **Protect Credentials**
   - Use `.pgpass` file instead of environment variables
   - Secure backup files with appropriate permissions (600)
   - Encrypt backups for off-site storage

2. **Access Control**
   - Limit backup script execution to specific users
   - Use read-only credentials for restore testing

3. **Network Security**
   - If backing up to remote storage, use encrypted connections
   - Consider VPN for off-site backup transfers

### Performance

1. **Timing**
   - Schedule full backups during low-traffic periods (2 AM)
   - Stagger incremental backups throughout the hour

2. **Compression**
   - Balance compression level vs. time (level 6 recommended)
   - Higher levels (8-9) save space but take longer

3. **Parallel Backups**
   - Use `pg_dump` with `--jobs` flag for large databases
   - Example: `pg_dump --jobs=4` for 4 parallel workers

### Reliability

1. **Monitoring**
   - Review monitoring alerts promptly
   - Set up escalation for critical failures

2. **Testing**
   - Test restores monthly (minimum)
   - Document restore procedures

3. **Documentation**
   - Keep runbooks up to date
   - Document any custom configurations

### Disaster Recovery

1. **Off-Site Backups**
   - Copy backups to remote location (cloud, remote server)
   - Automate off-site transfers
   - Test off-site restore procedures

2. **Recovery Time Objective (RTO)**
   - Target: < 1 hour for full restoration
   - Document and practice recovery procedures

3. **Recovery Point Objective (RPO)**
   - Full backup: Up to 24 hours data loss
   - Incremental: Up to 1 hour data loss (with PITR)

---

## Appendix

### File Format Specifications

**Full Backup File**:
- Format: gzipped SQL dump
- Naming: `{database}_full_{timestamp}.sql.gz`
- Example: `mastertrade_full_20250112_020000.sql.gz`

**Metadata File**:
```json
{
  "backup_file": "mastertrade_full_20250112_020000.sql.gz",
  "database": "mastertrade",
  "timestamp": "2025-01-12T02:00:00Z",
  "size_bytes": 148954832,
  "size_human": "142M",
  "duration_seconds": 45,
  "pg_version": "14.10",
  "checksum": "a1b2c3d4e5f6...",
  "compression_level": 6
}
```

### Environment Variables Reference

```bash
# PostgreSQL Connection
PGHOST=localhost                    # PostgreSQL host
PGPORT=5432                         # PostgreSQL port
PGUSER=postgres                     # PostgreSQL user
PGPASSWORD=password                 # PostgreSQL password

# Backup Configuration
BACKUP_DIR=/path/to/data            # Backup storage directory
RETENTION_DAYS=30                   # Full backup retention
WAL_RETENTION_DAYS=7                # Incremental retention
COMPRESSION_LEVEL=6                 # Gzip compression (1-9)

# Monitoring Configuration
MAX_BACKUP_AGE_HOURS=25             # Alert threshold for backup age
MIN_DISK_SPACE_GB=10                # Alert threshold for disk space
ALERT_ENDPOINT=http://localhost:8007/api/alerts/health  # Alert system URL
```

### Script Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error |
| 2 | Configuration error |
| 3 | PostgreSQL connection error |
| 4 | Backup creation failed |
| 5 | Verification failed |

### Useful Commands

```bash
# Check PostgreSQL version
psql --version

# Check database size
psql -h localhost -U postgres -d mastertrade -c "SELECT pg_size_pretty(pg_database_size('mastertrade'));"

# List all databases
psql -h localhost -U postgres -l

# Force WAL switch (triggers archiving)
psql -h localhost -U postgres -c "SELECT pg_switch_wal();"

# Check current WAL position
psql -h localhost -U postgres -c "SELECT pg_current_wal_lsn();"

# Vacuum database (recommended before backup)
psql -h localhost -U postgres -d mastertrade -c "VACUUM FULL ANALYZE;"
```

---

## Support

For issues or questions:

1. Check troubleshooting section
2. Review logs in `data/logs/`
3. Check PostgreSQL logs: `/var/log/postgresql/`
4. Contact DevOps team

---

**Document Version**: 1.0  
**Last Updated**: 2025-01-12  
**Author**: MasterTrade DevOps Team
