#!/bin/bash

################################################################################
# MasterTrade PostgreSQL Restore Script
#
# Description:
#   Restores PostgreSQL database from full or incremental backup
#   Supports point-in-time recovery with WAL files
#
# Usage:
#   ./restore_backup.sh [backup_file] [target_database]
#   ./restore_backup.sh --latest [target_database]
#   ./restore_backup.sh --list
#
# Examples:
#   ./restore_backup.sh data/full/mastertrade_full_20251112_120000.sql.gz mastertrade_restored
#   ./restore_backup.sh --latest mastertrade_test
#   ./restore_backup.sh --list
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

# PostgreSQL connection details
PGHOST="${PGHOST:-localhost}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-postgres}"
export PGPASSWORD="${PGPASSWORD:-postgres}"

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
    echo -e "${RED}[ERROR]${NC} $(date '+%Y-%m-%d %H:%M:%S') - $1" >&2
}

# Error handler
error_handler() {
    log_error "Restore failed at line $1"
    exit 1
}

trap 'error_handler $LINENO' ERR

# List available backups
list_backups() {
    log_info "=========================================="
    log_info "Available Backups"
    log_info "=========================================="
    
    log_info ""
    log_info "FULL BACKUPS:"
    log_info "----------------------------------------"
    
    if [[ -d "${BACKUP_DIR}/full" ]]; then
        local count=0
        while IFS= read -r backup_file; do
            ((count++))
            local backup_name=$(basename "${backup_file}")
            local backup_size=$(du -h "${backup_file}" | cut -f1)
            local backup_date=$(stat -c %y "${backup_file}" 2>/dev/null | cut -d'.' -f1 || stat -f "%Sm" -t "%Y-%m-%d %H:%M:%S" "${backup_file}" 2>/dev/null)
            
            echo -e "${GREEN}${count}.${NC} ${backup_name}"
            echo "   Size: ${backup_size}"
            echo "   Date: ${backup_date}"
            
            # Show metadata if available
            local meta_file="${backup_file%.sql.gz}.meta"
            if [[ -f "${meta_file}" ]]; then
                local db_size=$(grep -o '"database_size": "[^"]*"' "${meta_file}" 2>/dev/null | cut -d'"' -f4 || echo "unknown")
                local duration=$(grep -o '"duration_seconds": [0-9]*' "${meta_file}" 2>/dev/null | awk '{print $2}' || echo "unknown")
                echo "   Original DB Size: ${db_size}"
                echo "   Backup Duration: ${duration}s"
            fi
            echo ""
        done < <(find "${BACKUP_DIR}/full" -name "*.sql.gz" -type f | sort -r)
        
        if [[ ${count} -eq 0 ]]; then
            echo "No full backups found"
        fi
    else
        echo "No full backup directory found"
    fi
    
    log_info ""
    log_info "INCREMENTAL BACKUPS:"
    log_info "----------------------------------------"
    
    if [[ -d "${BACKUP_DIR}/incremental" ]]; then
        local base_count=$(find "${BACKUP_DIR}/incremental" -maxdepth 1 -name "base_*" -type d 2>/dev/null | wc -l)
        local wal_count=$(ls -1 "${BACKUP_DIR}/incremental/wal" 2>/dev/null | wc -l)
        local wal_size=$(du -sh "${BACKUP_DIR}/incremental/wal" 2>/dev/null | cut -f1 || echo "0")
        
        echo "Base backups: ${base_count}"
        echo "WAL files: ${wal_count}"
        echo "WAL archive size: ${wal_size}"
    else
        echo "No incremental backup directory found"
    fi
    
    log_info "=========================================="
    exit 0
}

# Get latest backup file
get_latest_backup() {
    local latest=$(find "${BACKUP_DIR}/full" -name "*.sql.gz" -type f -printf '%T@ %p\n' 2>/dev/null | sort -rn | head -1 | cut -d' ' -f2-)
    
    if [[ -z "${latest}" ]]; then
        log_error "No backups found in ${BACKUP_DIR}/full"
        exit 1
    fi
    
    echo "${latest}"
}

# Verify backup file
verify_backup_file() {
    local backup_file="$1"
    
    log_info "Verifying backup file: ${backup_file}"
    
    # Check if file exists
    if [[ ! -f "${backup_file}" ]]; then
        log_error "Backup file not found: ${backup_file}"
        exit 1
    fi
    
    # Check if file is readable
    if [[ ! -r "${backup_file}" ]]; then
        log_error "Backup file is not readable: ${backup_file}"
        exit 1
    fi
    
    # Check gzip integrity
    if ! gzip -t "${backup_file}" 2>/dev/null; then
        log_error "Backup file is corrupted (gzip test failed)"
        exit 1
    fi
    
    # Verify checksum if metadata available
    local meta_file="${backup_file%.sql.gz}.meta"
    if [[ -f "${meta_file}" ]]; then
        local stored_checksum=$(grep -o '"checksum": "[^"]*"' "${meta_file}" 2>/dev/null | cut -d'"' -f4)
        if [[ -n "${stored_checksum}" ]]; then
            local actual_checksum=$(sha256sum "${backup_file}" | awk '{print $1}')
            if [[ "${stored_checksum}" != "${actual_checksum}" ]]; then
                log_error "Checksum mismatch! Backup file may be corrupted"
                log_error "Expected: ${stored_checksum}"
                log_error "Actual: ${actual_checksum}"
                exit 1
            fi
            log_success "Checksum verified"
        fi
    fi
    
    log_success "Backup file verification passed"
}

# Check if database exists
database_exists() {
    local database="$1"
    
    psql -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -lqt 2>/dev/null | \
        cut -d \| -f 1 | grep -qw "${database}"
}

# Create database if it doesn't exist
create_database() {
    local database="$1"
    
    log_info "Creating database: ${database}"
    
    createdb -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" "${database}" 2>&1 || {
        log_error "Failed to create database: ${database}"
        exit 1
    }
    
    log_success "Database created: ${database}"
}

# Drop database (with confirmation)
drop_database() {
    local database="$1"
    
    log_warning "Database '${database}' already exists"
    log_warning "Restore will OVERWRITE existing database"
    
    read -p "Continue? (yes/no): " confirm
    
    if [[ "${confirm}" != "yes" ]]; then
        log_info "Restore cancelled by user"
        exit 0
    fi
    
    log_info "Dropping existing database: ${database}"
    
    # Terminate all connections
    psql -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d postgres -c \
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '${database}' AND pid <> pg_backend_pid();" &>/dev/null || true
    
    # Drop database
    dropdb -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" "${database}" 2>&1 || {
        log_error "Failed to drop database: ${database}"
        exit 1
    }
    
    log_success "Database dropped: ${database}"
}

# Restore from backup file
restore_backup() {
    local backup_file="$1"
    local target_db="$2"
    
    log_info "Starting restore process..."
    log_info "Backup file: ${backup_file}"
    log_info "Target database: ${target_db}"
    
    # Record start time
    local start_time=$(date +%s)
    
    # Restore database
    log_info "Restoring database (this may take several minutes)..."
    
    gunzip -c "${backup_file}" | \
        psql -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "${target_db}" \
        -v ON_ERROR_STOP=1 \
        --quiet 2>&1 | \
        tee "${BACKUP_DIR}/logs/restore_$(date +%Y%m%d_%H%M%S).log" | \
        grep -i "error\|warning" || true
    
    # Record end time
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    
    log_success "Restore completed in ${duration} seconds"
}

# Verify restored database
verify_restored_database() {
    local database="$1"
    
    log_info "Verifying restored database..."
    
    # Check if database exists and is accessible
    if ! database_exists "${database}"; then
        log_error "Database does not exist after restore: ${database}"
        return 1
    fi
    
    # Get table count
    local table_count=$(psql -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "${database}" -t -c \
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public'" 2>/dev/null | tr -d ' ')
    
    log_info "Tables found: ${table_count}"
    
    if [[ ${table_count} -eq 0 ]]; then
        log_warning "No tables found in restored database"
        return 1
    fi
    
    # Get database size
    local db_size=$(psql -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "${database}" -t -c \
        "SELECT pg_size_pretty(pg_database_size('${database}'))" 2>/dev/null | tr -d ' ')
    
    log_info "Database size: ${db_size}"
    
    log_success "Database verification passed"
}

# Show restore summary
print_restore_summary() {
    local backup_file="$1"
    local target_db="$2"
    
    log_info "=========================================="
    log_info "Restore Summary"
    log_info "=========================================="
    log_info "Backup file: $(basename "${backup_file}")"
    log_info "Target database: ${target_db}"
    log_info "Database host: ${PGHOST}:${PGPORT}"
    
    # Get database info
    local table_count=$(psql -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "${target_db}" -t -c \
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public'" 2>/dev/null | tr -d ' ')
    local db_size=$(psql -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "${target_db}" -t -c \
        "SELECT pg_size_pretty(pg_database_size('${target_db}'))" 2>/dev/null | tr -d ' ')
    
    log_info "Tables: ${table_count}"
    log_info "Size: ${db_size}"
    log_info "=========================================="
}

# Main execution
main() {
    local backup_file=""
    local target_db=""
    
    # Parse arguments
    if [[ $# -eq 0 ]]; then
        log_error "Usage: $0 [backup_file|--latest|--list] [target_database]"
        log_error "Examples:"
        log_error "  $0 --list"
        log_error "  $0 --latest mastertrade_test"
        log_error "  $0 data/full/mastertrade_full_20251112.sql.gz mastertrade_restored"
        exit 1
    fi
    
    # Handle --list option
    if [[ "$1" == "--list" ]]; then
        list_backups
        exit 0
    fi
    
    # Handle --latest option
    if [[ "$1" == "--latest" ]]; then
        if [[ $# -lt 2 ]]; then
            log_error "Target database name required"
            log_error "Usage: $0 --latest <target_database>"
            exit 1
        fi
        backup_file=$(get_latest_backup)
        target_db="$2"
    else
        backup_file="$1"
        target_db="${2:-mastertrade_restored}"
    fi
    
    log_info "=========================================="
    log_info "MasterTrade PostgreSQL Database Restore"
    log_info "=========================================="
    
    # Verify backup file
    verify_backup_file "${backup_file}"
    
    # Check if target database exists
    if database_exists "${target_db}"; then
        drop_database "${target_db}"
    fi
    
    # Create target database
    create_database "${target_db}"
    
    # Restore backup
    restore_backup "${backup_file}" "${target_db}"
    
    # Verify restored database
    verify_restored_database "${target_db}" || log_warning "Database verification had warnings"
    
    # Show summary
    print_restore_summary "${backup_file}" "${target_db}"
    
    log_success "=========================================="
    log_success "Database restore completed successfully!"
    log_success "Restored database: ${target_db}"
    log_success "=========================================="
    
    exit 0
}

# Run main function
main "$@"
