#!/bin/bash

################################################################################
# MasterTrade Redis Backup Script
#
# Description:
#   Creates backups of Redis RDB and AOF files
#   Supports both manual and automated execution via cron
#
# Usage:
#   ./backup_redis.sh
#
# Environment Variables:
#   REDIS_CONTAINER - Redis container name (default: mastertrade_redis)
#   REDIS_DATA_DIR - Redis data directory (default: /var/lib/docker/volumes/mastertrade_redis_data/_data)
#   BACKUP_DIR - Backup storage directory
#   RETENTION_DAYS - Backup retention in days (default: 30)
#
# Author: MasterTrade DevOps Team
# Date: 2025-11-12
################################################################################

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REDIS_CONTAINER="${REDIS_CONTAINER:-mastertrade_redis}"
BACKUP_DIR="${BACKUP_DIR:-${SCRIPT_DIR}/backups/data}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
ALERT_ENDPOINT="${ALERT_ENDPOINT:-http://localhost:8007/api/alerts/health}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $(date '+%Y-%m-%d %H:%M:%S') - $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $(date '+%Y-%m-%d %H:%M:%S') - $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $(date '+%Y-%m-%d %H:%M:%S') - $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $(date '+%Y-%m-%d %H:%M:%S') - $1"
}

# Error handler
error_exit() {
    log_error "$1"
    send_alert "Redis backup failed: $1" "critical"
    exit 1
}

# Send alert to alert system
send_alert() {
    local message="$1"
    local priority="${2:-high}"
    
    if command -v curl &> /dev/null; then
        curl -X POST "${ALERT_ENDPOINT}" \
            -H "Content-Type: application/json" \
            -d "{
                \"service_name\": \"redis_backup\",
                \"health_metric\": \"backup_status\",
                \"operator\": \"<\",
                \"threshold\": 1.0,
                \"priority\": \"${priority}\",
                \"channels\": [\"email\"],
                \"consecutive_failures\": 1
            }" &>/dev/null || log_warning "Failed to send alert"
    fi
}

# Check dependencies
check_dependencies() {
    log_info "Checking dependencies..."
    
    if ! command -v docker &> /dev/null; then
        error_exit "Docker is not installed"
    fi
    
    if ! command -v gzip &> /dev/null; then
        error_exit "gzip is not installed"
    fi
    
    if ! command -v sha256sum &> /dev/null; then
        error_exit "sha256sum is not installed"
    fi
    
    log_success "All dependencies are available"
}

# Check Redis container
check_redis_container() {
    log_info "Checking Redis container..."
    
    if ! docker ps --filter "name=${REDIS_CONTAINER}" --filter "status=running" | grep -q "${REDIS_CONTAINER}"; then
        error_exit "Redis container '${REDIS_CONTAINER}' is not running"
    fi
    
    log_success "Redis container is running"
}

# Create backup directories
create_backup_dirs() {
    log_info "Creating backup directories..."
    
    mkdir -p "${BACKUP_DIR}/rdb"
    mkdir -p "${BACKUP_DIR}/aof"
    mkdir -p "${BACKUP_DIR}/logs"
    mkdir -p "${BACKUP_DIR}/metadata"
    
    log_success "Backup directories created"
}

# Get Redis info
get_redis_info() {
    log_info "Getting Redis information..."
    
    REDIS_VERSION=$(docker exec "${REDIS_CONTAINER}" redis-cli INFO server | grep redis_version | cut -d: -f2 | tr -d '\r')
    USED_MEMORY=$(docker exec "${REDIS_CONTAINER}" redis-cli INFO memory | grep used_memory_human | cut -d: -f2 | tr -d '\r')
    KEYSPACE_KEYS=$(docker exec "${REDIS_CONTAINER}" redis-cli DBSIZE | cut -d: -f2 | tr -d '\r')
    
    log_info "Redis version: ${REDIS_VERSION}"
    log_info "Memory used: ${USED_MEMORY}"
    log_info "Total keys: ${KEYSPACE_KEYS}"
}

# Trigger Redis BGSAVE
trigger_bgsave() {
    log_info "Triggering Redis BGSAVE..."
    
    # Trigger BGSAVE
    docker exec "${REDIS_CONTAINER}" redis-cli BGSAVE >/dev/null || error_exit "Failed to trigger BGSAVE"
    
    # Wait for BGSAVE to complete
    local max_wait=300  # 5 minutes
    local waited=0
    
    while [ $waited -lt $max_wait ]; do
        local last_save=$(docker exec "${REDIS_CONTAINER}" redis-cli LASTSAVE)
        local current_time=$(date +%s)
        local save_age=$((current_time - last_save))
        
        if [ $save_age -lt 10 ]; then
            log_success "BGSAVE completed"
            return 0
        fi
        
        sleep 2
        waited=$((waited + 2))
    done
    
    error_exit "BGSAVE timeout after ${max_wait} seconds"
}

# Trigger AOF rewrite
trigger_aof_rewrite() {
    log_info "Triggering AOF rewrite..."
    
    docker exec "${REDIS_CONTAINER}" redis-cli BGREWRITEAOF >/dev/null || log_warning "Failed to trigger AOF rewrite"
    
    # Wait a bit for rewrite to start
    sleep 5
    
    log_success "AOF rewrite triggered"
}

# Backup RDB file
backup_rdb() {
    log_info "Backing up RDB file..."
    
    local rdb_file="dump.rdb"
    local backup_file="${BACKUP_DIR}/rdb/dump_${TIMESTAMP}.rdb"
    
    # Copy RDB file from container
    docker cp "${REDIS_CONTAINER}:/data/${rdb_file}" "${backup_file}" || error_exit "Failed to copy RDB file"
    
    # Get file size
    local file_size=$(stat -c %s "${backup_file}" 2>/dev/null || stat -f %z "${backup_file}" 2>/dev/null)
    local file_size_human=$(du -h "${backup_file}" | cut -f1)
    
    log_info "RDB file size: ${file_size_human}"
    
    # Compress RDB file
    log_info "Compressing RDB file..."
    gzip -f "${backup_file}" || error_exit "Failed to compress RDB file"
    
    local compressed_file="${backup_file}.gz"
    local compressed_size=$(stat -c %s "${compressed_file}" 2>/dev/null || stat -f %z "${compressed_file}" 2>/dev/null)
    local compressed_size_human=$(du -h "${compressed_file}" | cut -f1)
    
    log_success "RDB compressed: ${compressed_size_human}"
    
    # Generate checksum
    local checksum=$(sha256sum "${compressed_file}" | awk '{print $1}')
    
    # Create metadata
    cat > "${BACKUP_DIR}/metadata/rdb_${TIMESTAMP}.meta" << EOF
{
  "backup_type": "rdb",
  "backup_file": "$(basename ${compressed_file})",
  "timestamp": "$(date -Iseconds)",
  "redis_version": "${REDIS_VERSION}",
  "used_memory": "${USED_MEMORY}",
  "total_keys": "${KEYSPACE_KEYS}",
  "original_size_bytes": ${file_size},
  "compressed_size_bytes": ${compressed_size},
  "compression_ratio": $(awk "BEGIN {printf \"%.2f\", ${file_size}/${compressed_size}}"),
  "checksum": "${checksum}"
}
EOF
    
    log_success "RDB backup complete: $(basename ${compressed_file})"
}

# Backup AOF file
backup_aof() {
    log_info "Backing up AOF file..."
    
    local aof_file="appendonly.aof"
    local backup_file="${BACKUP_DIR}/aof/appendonly_${TIMESTAMP}.aof"
    
    # Check if AOF exists
    if ! docker exec "${REDIS_CONTAINER}" test -f "/data/${aof_file}"; then
        log_warning "AOF file not found, skipping AOF backup"
        return 0
    fi
    
    # Copy AOF file from container
    docker cp "${REDIS_CONTAINER}:/data/${aof_file}" "${backup_file}" || log_warning "Failed to copy AOF file"
    
    if [ ! -f "${backup_file}" ]; then
        log_warning "AOF backup skipped"
        return 0
    fi
    
    # Get file size
    local file_size=$(stat -c %s "${backup_file}" 2>/dev/null || stat -f %z "${backup_file}" 2>/dev/null)
    local file_size_human=$(du -h "${backup_file}" | cut -f1)
    
    log_info "AOF file size: ${file_size_human}"
    
    # Compress AOF file
    log_info "Compressing AOF file..."
    gzip -f "${backup_file}" || log_warning "Failed to compress AOF file"
    
    local compressed_file="${backup_file}.gz"
    
    if [ ! -f "${compressed_file}" ]; then
        log_warning "AOF compression failed"
        return 0
    fi
    
    local compressed_size=$(stat -c %s "${compressed_file}" 2>/dev/null || stat -f %z "${compressed_file}" 2>/dev/null)
    local compressed_size_human=$(du -h "${compressed_file}" | cut -f1)
    
    log_success "AOF compressed: ${compressed_size_human}"
    
    # Generate checksum
    local checksum=$(sha256sum "${compressed_file}" | awk '{print $1}')
    
    # Create metadata
    cat > "${BACKUP_DIR}/metadata/aof_${TIMESTAMP}.meta" << EOF
{
  "backup_type": "aof",
  "backup_file": "$(basename ${compressed_file})",
  "timestamp": "$(date -Iseconds)",
  "redis_version": "${REDIS_VERSION}",
  "used_memory": "${USED_MEMORY}",
  "total_keys": "${KEYSPACE_KEYS}",
  "original_size_bytes": ${file_size},
  "compressed_size_bytes": ${compressed_size},
  "compression_ratio": $(awk "BEGIN {printf \"%.2f\", ${file_size}/${compressed_size}}"),
  "checksum": "${checksum}"
}
EOF
    
    log_success "AOF backup complete: $(basename ${compressed_file})"
}

# Cleanup old backups
cleanup_old_backups() {
    log_info "Cleaning up old backups (retention: ${RETENTION_DAYS} days)..."
    
    local deleted_count=0
    
    # Cleanup RDB backups
    while IFS= read -r file; do
        rm -f "${file}"
        rm -f "${file%.gz}"  # Remove uncompressed if exists
        ((deleted_count++))
    done < <(find "${BACKUP_DIR}/rdb" -name "dump_*.rdb.gz" -type f -mtime +${RETENTION_DAYS})
    
    # Cleanup AOF backups
    while IFS= read -r file; do
        rm -f "${file}"
        rm -f "${file%.gz}"
        ((deleted_count++))
    done < <(find "${BACKUP_DIR}/aof" -name "appendonly_*.aof.gz" -type f -mtime +${RETENTION_DAYS})
    
    # Cleanup old metadata
    find "${BACKUP_DIR}/metadata" -name "*.meta" -type f -mtime +${RETENTION_DAYS} -delete
    
    # Cleanup old logs
    find "${BACKUP_DIR}/logs" -name "*.log" -type f -mtime +90 -delete
    
    if [ $deleted_count -gt 0 ]; then
        log_success "Deleted ${deleted_count} old backup(s)"
    else
        log_info "No old backups to delete"
    fi
}

# Display backup summary
display_summary() {
    log_info ""
    log_info "=========================================="
    log_info "Redis Backup Summary"
    log_info "=========================================="
    log_info "Timestamp: $(date -Iseconds)"
    log_info "Redis version: ${REDIS_VERSION}"
    log_info "Memory used: ${USED_MEMORY}"
    log_info "Total keys: ${KEYSPACE_KEYS}"
    
    # Count backups
    local rdb_count=$(find "${BACKUP_DIR}/rdb" -name "dump_*.rdb.gz" -type f | wc -l)
    local aof_count=$(find "${BACKUP_DIR}/aof" -name "appendonly_*.aof.gz" -type f | wc -l)
    
    log_info "Total RDB backups: ${rdb_count}"
    log_info "Total AOF backups: ${aof_count}"
    
    # Disk usage
    local backup_size=$(du -sh "${BACKUP_DIR}" | cut -f1)
    log_info "Backup directory size: ${backup_size}"
    
    log_info "=========================================="
    log_success "Redis backup completed successfully"
    
    send_alert "Redis backup completed successfully" "info"
}

# Main execution
main() {
    log_info "=========================================="
    log_info "MasterTrade Redis Backup"
    log_info "=========================================="
    log_info "Timestamp: $(date -Iseconds)"
    log_info "Container: ${REDIS_CONTAINER}"
    log_info "Backup directory: ${BACKUP_DIR}"
    log_info "Retention: ${RETENTION_DAYS} days"
    log_info "=========================================="
    log_info ""
    
    # Setup logging
    local log_file="${BACKUP_DIR}/logs/backup_redis_${TIMESTAMP}.log"
    
    check_dependencies
    check_redis_container
    create_backup_dirs
    get_redis_info
    
    # Perform backups
    trigger_bgsave
    backup_rdb
    
    trigger_aof_rewrite
    sleep 10  # Wait for rewrite to complete
    backup_aof
    
    # Cleanup and summary
    cleanup_old_backups
    display_summary
    
    log_info "Backup log: ${log_file}"
}

# Run main function and log output
main "$@" 2>&1 | tee "${BACKUP_DIR}/logs/backup_redis_${TIMESTAMP}.log"
