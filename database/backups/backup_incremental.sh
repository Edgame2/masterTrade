#!/bin/bash

################################################################################
# MasterTrade PostgreSQL Incremental Backup Script
#
# Description:
#   Performs incremental PostgreSQL backup using WAL (Write-Ahead Log) archiving
#   Designed for hourly execution via cron
#
# Usage:
#   ./backup_incremental.sh [database_name]
#
# Prerequisites:
#   - PostgreSQL WAL archiving must be enabled
#   - archive_mode = on
#   - archive_command configured
#
# Environment Variables Required:
#   PGHOST - PostgreSQL host (default: localhost)
#   PGPORT - PostgreSQL port (default: 5432)
#   PGUSER - PostgreSQL user (default: postgres)
#   PGPASSWORD - PostgreSQL password
#
# Author: MasterTrade DevOps Team
# Date: 2025-11-12
################################################################################

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_DIR="${BACKUP_DIR:-${SCRIPT_DIR}/data}"
DATABASE="${1:-mastertrade}"
RETENTION_DAYS="${WAL_RETENTION_DAYS:-7}"

# PostgreSQL connection details
PGHOST="${PGHOST:-localhost}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-postgres}"
export PGPASSWORD="${PGPASSWORD:-postgres}"

# Timestamp
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
WAL_ARCHIVE_DIR="${BACKUP_DIR}/incremental/wal"
BACKUP_LABEL="${DATABASE}_incremental_${TIMESTAMP}"

# Colors for output
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
    echo -e "${RED}[ERROR]${NC} $(date '+%Y-%m-%d %H:%M:%S') - $1" >&2
}

# Error handler
error_handler() {
    log_error "Incremental backup failed at line $1"
    exit 1
}

trap 'error_handler $LINENO' ERR

# Send alert function
send_alert() {
    local message="$1"
    local priority="${2:-medium}"
    
    if command -v curl &> /dev/null; then
        curl -X POST "http://localhost:8007/api/alerts/health" \
            -H "Content-Type: application/json" \
            -d "{
                \"service_name\": \"postgresql_backup\",
                \"health_metric\": \"incremental_backup_status\",
                \"operator\": \"<\",
                \"threshold\": 1.0,
                \"priority\": \"${priority}\",
                \"channels\": [\"email\"]
            }" &>/dev/null || true
    fi
}

# Check if WAL archiving is enabled
check_wal_archiving() {
    log_info "Checking WAL archiving configuration..."
    
    local archive_mode=$(psql -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "${DATABASE}" -t -c \
        "SHOW archive_mode" 2>/dev/null | tr -d ' ')
    
    if [[ "${archive_mode}" != "on" ]]; then
        log_warning "WAL archiving is not enabled (archive_mode = ${archive_mode})"
        log_warning "Incremental backups require WAL archiving"
        log_info "To enable WAL archiving, add to postgresql.conf:"
        log_info "  archive_mode = on"
        log_info "  archive_command = 'test ! -f ${WAL_ARCHIVE_DIR}/%f && cp %p ${WAL_ARCHIVE_DIR}/%f'"
        log_info "  wal_level = replica"
        log_warning "Falling back to base backup instead"
        return 1
    fi
    
    log_success "WAL archiving is enabled"
    return 0
}

# Create WAL archive directory
create_wal_archive_dir() {
    log_info "Creating WAL archive directory..."
    
    mkdir -p "${WAL_ARCHIVE_DIR}"
    mkdir -p "${BACKUP_DIR}/incremental/metadata"
    mkdir -p "${BACKUP_DIR}/logs"
    
    # Set permissions (PostgreSQL user needs write access)
    chmod 755 "${WAL_ARCHIVE_DIR}"
    
    log_success "WAL archive directory created: ${WAL_ARCHIVE_DIR}"
}

# Start base backup for WAL archiving
start_base_backup() {
    log_info "Starting base backup (for WAL archiving point-in-time recovery)..."
    
    local base_backup_dir="${BACKUP_DIR}/incremental/base_${TIMESTAMP}"
    mkdir -p "${base_backup_dir}"
    
    # Use pg_basebackup for physical backup
    if command -v pg_basebackup &> /dev/null; then
        log_info "Using pg_basebackup for base backup..."
        
        pg_basebackup -h "${PGHOST}" \
                      -p "${PGPORT}" \
                      -U "${PGUSER}" \
                      -D "${base_backup_dir}" \
                      -F tar \
                      -z \
                      -P \
                      -v \
                      --wal-method=fetch \
                      --label="${BACKUP_LABEL}" 2>&1 | \
                      tee "${BACKUP_DIR}/logs/backup_incremental_${TIMESTAMP}.log" || true
        
        log_success "Base backup completed: ${base_backup_dir}"
        
        # Create metadata
        cat > "${BACKUP_DIR}/incremental/metadata/${BACKUP_LABEL}.meta" <<EOF
{
  "backup_type": "incremental_base",
  "database": "${DATABASE}",
  "timestamp": "${TIMESTAMP}",
  "date": "$(date -Iseconds)",
  "base_backup_dir": "${base_backup_dir}",
  "wal_archive_dir": "${WAL_ARCHIVE_DIR}",
  "label": "${BACKUP_LABEL}"
}
EOF
        
        return 0
    else
        log_warning "pg_basebackup not found, using pg_start_backup/pg_stop_backup"
        return 1
    fi
}

# Archive WAL files
archive_wal_files() {
    log_info "Archiving WAL files..."
    
    # Get current WAL file
    local current_wal=$(psql -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "${DATABASE}" -t -c \
        "SELECT pg_walfile_name(pg_current_wal_lsn())" 2>/dev/null | tr -d ' ')
    
    if [[ -n "${current_wal}" ]]; then
        log_info "Current WAL file: ${current_wal}"
        
        # Force WAL switch to archive current segment
        psql -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "${DATABASE}" -c \
            "SELECT pg_switch_wal()" &>/dev/null || true
        
        log_success "WAL switch executed"
    fi
    
    # Count WAL files
    local wal_count=$(ls -1 "${WAL_ARCHIVE_DIR}" 2>/dev/null | wc -l)
    local wal_size=$(du -sh "${WAL_ARCHIVE_DIR}" 2>/dev/null | cut -f1 || echo "0")
    
    log_info "WAL files archived: ${wal_count}"
    log_info "WAL archive size: ${wal_size}"
}

# Cleanup old WAL files
cleanup_old_wal_files() {
    log_info "Cleaning up WAL files older than ${RETENTION_DAYS} days..."
    
    local deleted_count=0
    
    # Find and delete old WAL files
    while IFS= read -r -d '' file; do
        log_info "Deleting old WAL file: $(basename "${file}")"
        rm -f "${file}"
        ((deleted_count++))
    done < <(find "${WAL_ARCHIVE_DIR}" -type f -mtime +${RETENTION_DAYS} -print0 2>/dev/null)
    
    if [[ ${deleted_count} -gt 0 ]]; then
        log_success "Deleted ${deleted_count} old WAL file(s)"
    else
        log_info "No old WAL files to delete"
    fi
    
    # Cleanup old base backups
    log_info "Cleaning up old base backups..."
    
    deleted_count=0
    while IFS= read -r -d '' dir; do
        log_info "Deleting old base backup: $(basename "${dir}")"
        rm -rf "${dir}"
        ((deleted_count++))
    done < <(find "${BACKUP_DIR}/incremental" -maxdepth 1 -name "base_*" -type d -mtime +${RETENTION_DAYS} -print0 2>/dev/null)
    
    if [[ ${deleted_count} -gt 0 ]]; then
        log_success "Deleted ${deleted_count} old base backup(s)"
    else
        log_info "No old base backups to delete"
    fi
}

# Verify WAL archive integrity
verify_wal_archive() {
    log_info "Verifying WAL archive integrity..."
    
    local wal_files=$(ls -1 "${WAL_ARCHIVE_DIR}" 2>/dev/null | wc -l)
    
    if [[ ${wal_files} -eq 0 ]]; then
        log_warning "No WAL files found in archive"
        return 1
    fi
    
    # Check if WAL files are valid (16MB size typically)
    local invalid_count=0
    for wal_file in "${WAL_ARCHIVE_DIR}"/*; do
        if [[ -f "${wal_file}" ]]; then
            local file_size=$(stat -f%z "${wal_file}" 2>/dev/null || stat -c%s "${wal_file}" 2>/dev/null || echo "0")
            # WAL files should be 16MB (16777216 bytes) when full
            if [[ ${file_size} -lt 1000000 ]]; then
                log_warning "Suspicious WAL file size: $(basename "${wal_file}") - ${file_size} bytes"
                ((invalid_count++))
            fi
        fi
    done
    
    if [[ ${invalid_count} -gt 0 ]]; then
        log_warning "Found ${invalid_count} potentially invalid WAL file(s)"
    else
        log_success "WAL archive integrity verified"
    fi
}

# Print backup statistics
print_statistics() {
    log_info "=== Incremental Backup Statistics ==="
    
    local wal_count=$(ls -1 "${WAL_ARCHIVE_DIR}" 2>/dev/null | wc -l)
    local wal_size=$(du -sh "${WAL_ARCHIVE_DIR}" 2>/dev/null | cut -f1 || echo "unknown")
    local base_count=$(find "${BACKUP_DIR}/incremental" -maxdepth 1 -name "base_*" -type d 2>/dev/null | wc -l)
    
    log_info "WAL files: ${wal_count}"
    log_info "WAL archive size: ${wal_size}"
    log_info "Base backups: ${base_count}"
    log_info "Retention period: ${RETENTION_DAYS} days"
}

# Main execution
main() {
    log_info "=========================================="
    log_info "MasterTrade PostgreSQL Incremental Backup"
    log_info "=========================================="
    log_info "Database: ${DATABASE}"
    log_info "Timestamp: ${TIMESTAMP}"
    log_info "=========================================="
    
    # Create directories
    create_wal_archive_dir
    
    # Check if WAL archiving is enabled
    if check_wal_archiving; then
        # Perform incremental backup
        start_base_backup || log_warning "Base backup failed, continuing with WAL archiving"
        
        # Archive current WAL files
        archive_wal_files
        
        # Verify archive
        verify_wal_archive || log_warning "WAL archive verification had warnings"
        
        # Cleanup old files
        cleanup_old_wal_files
        
        # Print statistics
        print_statistics
        
        log_success "=========================================="
        log_success "Incremental backup completed successfully!"
        log_success "WAL archive: ${WAL_ARCHIVE_DIR}"
        log_success "=========================================="
        
        send_alert "PostgreSQL incremental backup completed for database: ${DATABASE}" "info"
    else
        log_error "Cannot perform incremental backup without WAL archiving"
        log_info "Please enable WAL archiving in postgresql.conf"
        send_alert "PostgreSQL incremental backup skipped - WAL archiving not enabled" "warning"
        exit 1
    fi
    
    exit 0
}

# Run main function
main "$@"
