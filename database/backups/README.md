# PostgreSQL Automated Backup System

Complete backup and restore solution for MasterTrade PostgreSQL database.

## Quick Start

### 1. Configure PostgreSQL Credentials

```bash
# Option A: Environment variables
export PGHOST=localhost
export PGPORT=5432
export PGUSER=postgres
export PGPASSWORD=your_password

# Option B: .pgpass file (recommended)
echo "localhost:5432:mastertrade:postgres:your_password" > ~/.pgpass
chmod 600 ~/.pgpass
```

### 2. Test Manual Backup

```bash
cd /home/neodyme/Documents/Projects/masterTrade/database/backups

# Run full backup
./backup_full.sh mastertrade

# Verify backup created
ls -lh data/full/
```

### 3. Setup Automated Backups

```bash
# Install cron jobs
./setup_cron.sh

# Verify cron schedule
crontab -l | grep "MasterTrade"
```

### 4. Test Restore

```bash
# List available backups
./restore_backup.sh --list

# Restore to test database
./restore_backup.sh --latest mastertrade_test
```

---

## Scripts Overview

| Script | Purpose | Usage |
|--------|---------|-------|
| `backup_full.sh` | Daily full backups | `./backup_full.sh <database>` |
| `backup_incremental.sh` | Hourly incremental backups | `./backup_incremental.sh <database>` |
| `restore_backup.sh` | Restore from backups | `./restore_backup.sh --latest <database>` |
| `monitor_backups.sh` | Health monitoring | `./monitor_backups.sh` |
| `setup_cron.sh` | Automate with cron | `./setup_cron.sh` |

---

## Features

✅ **Automated Backups**: Daily full + hourly incremental  
✅ **Monitoring**: Continuous health checks every 15 minutes  
✅ **Verification**: SHA-256 checksums + gzip integrity tests  
✅ **Retention**: Automatic cleanup (30 days full, 7 days incremental)  
✅ **Alerts**: Integration with alert system  
✅ **PITR**: Point-in-time recovery support  
✅ **Restore**: Multiple modes (latest, specific, list)  

---

## Schedule

After running `setup_cron.sh`:

- **Daily**: 2:00 AM - Full backup
- **Hourly**: :05 - Incremental backup (if WAL enabled)
- **Every 15 min**: Health monitoring

---

## Monitoring

```bash
# Check backup health
./monitor_backups.sh

# View logs
tail -f data/logs/backup_full_cron.log
tail -f data/logs/monitor_cron.log

# Check disk usage
du -sh data/
```

---

## Restore Procedures

### Emergency Restore

```bash
# 1. Stop services
docker-compose stop

# 2. Restore database
./restore_backup.sh --latest mastertrade

# 3. Restart services
docker-compose up -d
```

### Test Restore (Monthly)

```bash
# Create test database
psql -h localhost -U postgres -c "CREATE DATABASE mastertrade_test;"

# Restore latest backup
./restore_backup.sh --latest mastertrade_test

# Verify data
psql -h localhost -U postgres -d mastertrade_test -c "SELECT COUNT(*) FROM strategies;"

# Cleanup
psql -h localhost -U postgres -c "DROP DATABASE mastertrade_test;"
```

---

## Optional: Incremental Backups (WAL Archiving)

### Enable in PostgreSQL

Edit `/etc/postgresql/*/main/postgresql.conf`:

```ini
archive_mode = on
wal_level = replica
archive_command = 'test ! -f /path/to/backups/data/incremental/wal/%f && cp %p /path/to/backups/data/incremental/wal/%f'
```

Restart PostgreSQL:
```bash
sudo systemctl restart postgresql
```

Test incremental backup:
```bash
./backup_incremental.sh mastertrade
```

---

## Documentation

📖 **Full Documentation**: See `BACKUP_SYSTEM_DOCUMENTATION.md`

Topics covered:
- Architecture overview
- Installation guide
- Usage examples
- Restore procedures
- Troubleshooting
- Maintenance schedules
- Best practices

📋 **Completion Report**: See `POSTGRESQL_BACKUP_SYSTEM_COMPLETE.md`

---

## Troubleshooting

### Connection refused
```bash
# Check PostgreSQL is running
sudo systemctl status postgresql

# Test connection
psql -h localhost -U postgres -d mastertrade -c "SELECT 1;"
```

### Permission denied
```bash
# Fix ownership
sudo chown -R $(whoami):$(whoami) .

# Ensure scripts are executable
chmod +x *.sh
```

### Disk space full
```bash
# Check disk usage
df -h

# Clean old backups
find data/full/ -name "*.sql.gz" -mtime +30 -delete
```

---

## Files in This Directory

```
database/backups/
├── README.md                                    # This file
├── BACKUP_SYSTEM_DOCUMENTATION.md               # Full documentation (1,400 lines)
├── POSTGRESQL_BACKUP_SYSTEM_COMPLETE.md         # Implementation report
├── backup_full.sh                               # Daily full backup script (380 lines)
├── backup_incremental.sh                        # Hourly incremental backup (350 lines)
├── restore_backup.sh                            # Restore utility (380 lines)
├── monitor_backups.sh                           # Health monitoring (390 lines)
├── setup_cron.sh                                # Cron automation setup (240 lines)
└── data/                                        # Created on first run
    ├── full/                                    # Full backup storage
    ├── incremental/                             # Incremental backups
    │   ├── wal/                                # WAL archive
    │   └── base_*/                             # Base backups
    └── logs/                                    # Operation logs
```

---

## Support

For detailed information, see `BACKUP_SYSTEM_DOCUMENTATION.md`

For issues:
1. Check logs in `data/logs/`
2. Run `./monitor_backups.sh` for health status
3. Review troubleshooting section in documentation

---

**Status**: ✅ Production Ready  
**Last Updated**: 2025-01-12  
**Total Lines**: ~3,290 (scripts + documentation)
