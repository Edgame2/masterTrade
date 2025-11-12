#!/bin/bash

################################################################################
# MasterTrade PostgreSQL Full Backup Script
# 
# Description:
#   Performs a complete PostgreSQL database backup with compression
#   Designed for daily execution via cron
#
# Usage:
#   ./backup_full.sh [database_name]
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
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"
COMPRESSION_LEVEL="${COMPRESSION_LEVEL:-6}"

# PostgreSQL connection details
PGHOST="${PGHOST:-localhost}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-postgres}"
export PGPASSWORD="${PGPASSWORD:-postgres}"

# Timestamp for backup file
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/full/${DATABASE}_full_${TIMESTAMP}.sql.gz"
BACKUP_METADATA="${BACKUP_DIR}/full/${DATABASE}_full_${TIMESTAMP}.meta"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

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
    log_error "Backup failed at line $1"
    
    # Cleanup partial backup
    if [[ -f "${BACKUP_FILE}" ]]; then
        log_warning "Removing partial backup file: ${BACKUP_FILE}"
        rm -f "${BACKUP_FILE}"
    fi
    
    if [[ -f "${BACKUP_METADATA}" ]]; then
        rm -f "${BACKUP_METADATA}"
    fi
    
    # Send alert (if notification system available)
    send_alert "PostgreSQL full backup failed for database: ${DATABASE}" "critical"
    
    exit 1
}

trap 'error_handler $LINENO' ERR

# Send alert function (placeholder for integration with alert system)
send_alert() {
    local message="$1"
    local priority="${2:-medium}"
    
    # Try to send alert via alert system
    if command -v curl &> /dev/null; then
        curl -X POST "http://localhost:8007/api/alerts/health" \
            -H "Content-Type: application/json" \
            -d "{
                \"service_name\": \"postgresql_backup\",
                \"health_metric\": \"backup_status\",
                \"operator\": \"<\",
                \"threshold\": 1.0,
                \"priority\": \"${priority}\",
                \"channels\": [\"email\"]
            }" &>/dev/null || true
    fi
    
    # Also log to syslog if available
    if command -v logger &> /dev/null; then
        logger -t "mastertrade-backup" -p user.error "${message}"
    fi
}

# Check dependencies
check_dependencies() {
    log_info "Checking dependencies..."
    
    local missing_deps=()
    
    if ! command -v pg_dump &> /dev/null; then
        missing_deps+=("pg_dump (postgresql-client)")
    fi
    
    if ! command -v gzip &> /dev/null; then
        missing_deps+=("gzip")
    fi
    
    if [[ ${#missing_deps[@]} -gt 0 ]]; then
        log_error "Missing dependencies: ${missing_deps[*]}"
        log_error "Install with: apt-get install postgresql-client gzip"
        exit 1
    fi
    
    log_success "All dependencies satisfied"
}

# Create backup directories
create_backup_dirs() {
    log_info "Creating backup directories..."
    
    mkdir -p "${BACKUP_DIR}/full"
    mkdir -p "${BACKUP_DIR}/incremental"
    mkdir -p "${BACKUP_DIR}/logs"
    
    log_success "Backup directories created"
}

# Test database connection
test_connection() {
    log_info "Testing database connection..."
    
    if ! psql -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d postgres -c "SELECT 1" &>/dev/null; then
        log_error "Cannot connect to PostgreSQL at ${PGHOST}:${PGPORT}"
        log_error "Check PGHOST, PGPORT, PGUSER, and PGPASSWORD environment variables"
        exit 1
    fi
    
    log_success "Database connection successful"
}

# Get database size
get_database_size() {
    local size_bytes=$(psql -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "${DATABASE}" -t -c \
        "SELECT pg_database_size('${DATABASE}')" 2>/dev/null || echo "0")
    
    # Convert to human-readable format
    if command -v numfmt &> /dev/null; then
        echo $(numfmt --to=iec --format="%.2f" ${size_bytes} 2>/dev/null || echo "unknown")
    else
        echo "${size_bytes} bytes"
    fi
}

# Perform full backup
perform_backup() {
    local db_size=$(get_database_size)
    log_info "Starting full backup of database '${DATABASE}' (size: ${db_size})"
    log_info "Backup file: ${BACKUP_FILE}"
    
    # Record start time
    local start_time=$(date +%s)
    
    # Perform backup with compression
    log_info "Running pg_dump with compression level ${COMPRESSION_LEVEL}..."
    
    pg_dump -h "${PGHOST}" \
            -p "${PGPORT}" \
            -U "${PGUSER}" \
            -d "${DATABASE}" \
            --format=plain \
            --verbose \
            --no-owner \
            --no-acl \
            --compress=${COMPRESSION_LEVEL} \
            --file="${BACKUP_FILE}" 2>&1 | \
            tee "${BACKUP_DIR}/logs/backup_full_${TIMESTAMP}.log" | \
            grep -v "^pg_dump: " || true
    
    # Record end time
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    
    # Get backup file size
    local backup_size=$(du -h "${BACKUP_FILE}" | cut -f1)
    
    log_success "Backup completed in ${duration} seconds"
    log_info "Backup file size: ${backup_size}"
    
    # Create metadata file
    create_metadata "${db_size}" "${backup_size}" "${duration}"
}

# Create backup metadata
create_metadata() {
    local db_size="$1"
    local backup_size="$2"
    local duration="$3"
    
    log_info "Creating metadata file..."
    
    cat > "${BACKUP_METADATA}" <<EOF
{
  "backup_type": "full",
  "database": "${DATABASE}",
  "timestamp": "${TIMESTAMP}",
  "date": "$(date -Iseconds)",
  "hostname": "$(hostname)",
  "pg_version": "$(psql -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -t -c "SHOW server_version" 2>/dev/null | tr -d ' ')",
  "database_size": "${db_size}",
  "backup_size": "${backup_size}",
  "compression_level": ${COMPRESSION_LEVEL},
  "duration_seconds": ${duration},
  "backup_file": "${BACKUP_FILE}",
  "checksum": "$(sha256sum "${BACKUP_FILE}" | awk '{print $1}')"
}
EOF
    
    log_success "Metadata file created: ${BACKUP_METADATA}"
}

# Verify backup integrity
verify_backup() {
    log_info "Verifying backup integrity..."
    
    # Check if file exists and is not empty
    if [[ ! -f "${BACKUP_FILE}" ]]; then
        log_error "Backup file not found: ${BACKUP_FILE}"
        return 1
    fi
    
    if [[ ! -s "${BACKUP_FILE}" ]]; then
        log_error "Backup file is empty: ${BACKUP_FILE}"
        return 1
    fi
    
    # Test gzip integrity
    if ! gzip -t "${BACKUP_FILE}" 2>/dev/null; then
        log_error "Backup file is corrupted (gzip test failed)"
        return 1
    fi
    
    log_success "Backup integrity verified"
}

# Cleanup old backups
cleanup_old_backups() {
    log_info "Cleaning up backups older than ${RETENTION_DAYS} days..."
    
    local deleted_count=0
    
    # Find and delete old backup files
    while IFS= read -r -d '' file; do
        log_info "Deleting old backup: $(basename "${file}")"
        rm -f "${file}"
        # Also delete metadata if exists
        rm -f "${file%.sql.gz}.meta"
        ((deleted_count++))
    done < <(find "${BACKUP_DIR}/full" -name "${DATABASE}_full_*.sql.gz" -type f -mtime +${RETENTION_DAYS} -print0 2>/dev/null)
    
    if [[ ${deleted_count} -gt 0 ]]; then
        log_success "Deleted ${deleted_count} old backup(s)"
    else
        log_info "No old backups to delete"
    fi
}

# Print backup statistics
print_statistics() {
    log_info "=== Backup Statistics ==="
    
    local backup_count=$(find "${BACKUP_DIR}/full" -name "${DATABASE}_full_*.sql.gz" -type f | wc -l)
    local total_size=$(du -sh "${BACKUP_DIR}/full" 2>/dev/null | cut -f1 || echo "unknown")
    local oldest_backup=$(find "${BACKUP_DIR}/full" -name "${DATABASE}_full_*.sql.gz" -type f -printf '%T+ %p\n' 2>/dev/null | sort | head -1 | cut -d' ' -f1 || echo "none")
    
    log_info "Total backups: ${backup_count}"
    log_info "Total size: ${total_size}"
    log_info "Oldest backup: ${oldest_backup}"
    log_info "Retention period: ${RETENTION_DAYS} days"
}

# Main execution
main() {
    log_info "=========================================="
    log_info "MasterTrade PostgreSQL Full Backup"
    log_info "=========================================="
    log_info "Database: ${DATABASE}"
    log_info "Timestamp: ${TIMESTAMP}"
    log_info "=========================================="
    
    # Pre-flight checks
    check_dependencies
    create_backup_dirs
    test_connection
    
    # Perform backup
    perform_backup
    
    # Verify backup
    verify_backup
    
    # Cleanup old backups
    cleanup_old_backups
    
    # Print statistics
    print_statistics
    
    log_success "=========================================="
    log_success "Full backup completed successfully!"
    log_success "Backup file: ${BACKUP_FILE}"
    log_success "=========================================="
    
    # Send success notification
    send_alert "PostgreSQL full backup completed successfully for database: ${DATABASE}" "info"
    
    exit 0
}

# Run main function
main "$@"
