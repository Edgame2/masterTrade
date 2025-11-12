#!/bin/bash

################################################################################
# MasterTrade Redis Restore Script
#
# Description:
#   Restores Redis data from RDB or AOF backup files
#   Supports multiple restore modes and validation
#
# Usage:
#   ./restore_redis.sh --list
#   ./restore_redis.sh --latest
#   ./restore_redis.sh <backup_file>
#
# Author: MasterTrade DevOps Team
# Date: 2025-11-12
################################################################################

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REDIS_CONTAINER="${REDIS_CONTAINER:-mastertrade_redis}"
BACKUP_DIR="${BACKUP_DIR:-${SCRIPT_DIR}/data}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

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

# Show usage
show_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --list          List available backups"
    echo "  --latest        Restore from latest backup"
    echo "  <backup_file>   Restore from specific backup file"
    echo ""
    echo "Examples:"
    echo "  $0 --list"
    echo "  $0 --latest"
    echo "  $0 data/rdb/dump_20251112_120000.rdb.gz"
    exit 1
}

# List available backups
list_backups() {
    log_info "Available Redis Backups:"
    echo ""
    
    log_info "=== RDB Backups ==="
    if [ -d "${BACKUP_DIR}/rdb" ]; then
        find "${BACKUP_DIR}/rdb" -name "dump_*.rdb.gz" -type f -printf '%T@ %p\n' 2>/dev/null | \
            sort -rn | \
            while read -r timestamp file; do
                local size=$(du -h "${file}" | cut -f1)
                local date=$(date -d "@${timestamp}" '+%Y-%m-%d %H:%M:%S' 2>/dev/null || date -r "${timestamp}" '+%Y-%m-%d %H:%M:%S' 2>/dev/null)
                echo "  $(basename "${file}") (${size}) - ${date}"
                
                # Show metadata if available
                local meta_file="${file%.gz}.meta"
                meta_file="${meta_file/rdb\//metadata/rdb_}"
                meta_file="${meta_file%.rdb/.meta}"
                meta_file="${BACKUP_DIR}/metadata/$(basename ${file%.rdb.gz}).meta"
                
                if [ -f "${meta_file}" ]; then
                    local keys=$(grep -o '"total_keys": "[^"]*"' "${meta_file}" | cut -d'"' -f4)
                    local memory=$(grep -o '"used_memory": "[^"]*"' "${meta_file}" | cut -d'"' -f4)
                    [ -n "${keys}" ] && echo "    Keys: ${keys}, Memory: ${memory}"
                fi
            done
    fi
    
    echo ""
    log_info "=== AOF Backups ==="
    if [ -d "${BACKUP_DIR}/aof" ]; then
        find "${BACKUP_DIR}/aof" -name "appendonly_*.aof.gz" -type f -printf '%T@ %p\n' 2>/dev/null | \
            sort -rn | \
            while read -r timestamp file; do
                local size=$(du -h "${file}" | cut -f1)
                local date=$(date -d "@${timestamp}" '+%Y-%m-%d %H:%M:%S' 2>/dev/null || date -r "${timestamp}" '+%Y-%m-%d %H:%M:%S' 2>/dev/null)
                echo "  $(basename "${file}") (${size}) - ${date}"
            done
    fi
    echo ""
}

# Get latest backup
get_latest_backup() {
    local backup_type="${1:-rdb}"  # Default to RDB
    
    if [ "${backup_type}" = "rdb" ]; then
        find "${BACKUP_DIR}/rdb" -name "dump_*.rdb.gz" -type f -printf '%T@ %p\n' 2>/dev/null | \
            sort -rn | head -1 | cut -d' ' -f2-
    else
        find "${BACKUP_DIR}/aof" -name "appendonly_*.aof.gz" -type f -printf '%T@ %p\n' 2>/dev/null | \
            sort -rn | head -1 | cut -d' ' -f2-
    fi
}

# Verify backup file
verify_backup_file() {
    local backup_file="$1"
    
    log_info "Verifying backup file..."
    
    # Check file exists
    if [ ! -f "${backup_file}" ]; then
        log_error "Backup file not found: ${backup_file}"
        return 1
    fi
    
    # Check file readable
    if [ ! -r "${backup_file}" ]; then
        log_error "Backup file not readable: ${backup_file}"
        return 1
    fi
    
    # Test gzip integrity
    log_info "Testing gzip integrity..."
    if ! gzip -t "${backup_file}" 2>/dev/null; then
        log_error "Backup file is corrupted (gzip test failed)"
        return 1
    fi
    
    # Verify checksum if metadata available
    local filename=$(basename "${backup_file}")
    local meta_pattern="${filename%.rdb.gz}"
    meta_pattern="${meta_pattern%.aof.gz}"
    
    local meta_file=$(find "${BACKUP_DIR}/metadata" -name "${meta_pattern}*.meta" | head -1)
    
    if [ -f "${meta_file}" ]; then
        log_info "Verifying checksum..."
        local stored_checksum=$(grep -o '"checksum": "[^"]*"' "${meta_file}" | cut -d'"' -f4)
        local actual_checksum=$(sha256sum "${backup_file}" | awk '{print $1}')
        
        if [ "${stored_checksum}" != "${actual_checksum}" ]; then
            log_error "Checksum mismatch!"
            log_error "Expected: ${stored_checksum}"
            log_error "Actual: ${actual_checksum}"
            return 1
        fi
        
        log_success "Checksum verified"
    fi
    
    log_success "Backup file verification passed"
    return 0
}

# Check Redis container
check_redis_container() {
    log_info "Checking Redis container..."
    
    if ! docker ps --filter "name=${REDIS_CONTAINER}" --filter "status=running" | grep -q "${REDIS_CONTAINER}"; then
        log_error "Redis container '${REDIS_CONTAINER}' is not running"
        return 1
    fi
    
    log_success "Redis container is running"
    return 0
}

# Get current Redis stats (before restore)
get_current_stats() {
    log_info "Getting current Redis stats..."
    
    CURRENT_KEYS=$(docker exec "${REDIS_CONTAINER}" redis-cli DBSIZE | tr -d '\r')
    CURRENT_MEMORY=$(docker exec "${REDIS_CONTAINER}" redis-cli INFO memory | grep used_memory_human | cut -d: -f2 | tr -d '\r')
    
    log_info "Current keys: ${CURRENT_KEYS}"
    log_info "Current memory: ${CURRENT_MEMORY}"
}

# Stop Redis temporarily
stop_redis() {
    log_info "Stopping Redis temporarily..."
    
    docker stop "${REDIS_CONTAINER}" || {
        log_error "Failed to stop Redis container"
        return 1
    }
    
    log_success "Redis stopped"
}

# Start Redis
start_redis() {
    log_info "Starting Redis..."
    
    docker start "${REDIS_CONTAINER}" || {
        log_error "Failed to start Redis container"
        return 1
    }
    
    # Wait for Redis to be ready
    local max_wait=30
    local waited=0
    
    while [ $waited -lt $max_wait ]; do
        if docker exec "${REDIS_CONTAINER}" redis-cli PING &>/dev/null; then
            log_success "Redis started successfully"
            return 0
        fi
        sleep 1
        waited=$((waited + 1))
    done
    
    log_error "Redis failed to start within ${max_wait} seconds"
    return 1
}

# Restore RDB file
restore_rdb() {
    local backup_file="$1"
    
    log_info "Restoring from RDB backup: $(basename ${backup_file})"
    
    # Extract backup file
    local temp_file="/tmp/dump_restore_${TIMESTAMP}.rdb"
    gunzip -c "${backup_file}" > "${temp_file}" || {
        log_error "Failed to decompress backup file"
        return 1
    }
    
    # Copy to container
    log_info "Copying RDB file to container..."
    docker cp "${temp_file}" "${REDIS_CONTAINER}:/data/dump.rdb" || {
        log_error "Failed to copy RDB file to container"
        rm -f "${temp_file}"
        return 1
    }
    
    # Cleanup temp file
    rm -f "${temp_file}"
    
    log_success "RDB file restored"
}

# Restore AOF file
restore_aof() {
    local backup_file="$1"
    
    log_info "Restoring from AOF backup: $(basename ${backup_file})"
    
    # Extract backup file
    local temp_file="/tmp/appendonly_restore_${TIMESTAMP}.aof"
    gunzip -c "${backup_file}" > "${temp_file}" || {
        log_error "Failed to decompress backup file"
        return 1
    }
    
    # Copy to container
    log_info "Copying AOF file to container..."
    docker cp "${temp_file}" "${REDIS_CONTAINER}:/data/appendonly.aof" || {
        log_error "Failed to copy AOF file to container"
        rm -f "${temp_file}"
        return 1
    }
    
    # Cleanup temp file
    rm -f "${temp_file}"
    
    log_success "AOF file restored"
}

# Verify restored data
verify_restored_data() {
    log_info "Verifying restored data..."
    
    # Wait a bit for Redis to load data
    sleep 3
    
    RESTORED_KEYS=$(docker exec "${REDIS_CONTAINER}" redis-cli DBSIZE | tr -d '\r')
    RESTORED_MEMORY=$(docker exec "${REDIS_CONTAINER}" redis-cli INFO memory | grep used_memory_human | cut -d: -f2 | tr -d '\r')
    
    log_info "Restored keys: ${RESTORED_KEYS}"
    log_info "Restored memory: ${RESTORED_MEMORY}"
    
    if [ "${RESTORED_KEYS}" -eq 0 ]; then
        log_warning "No keys found after restore - backup may have been empty"
    else
        log_success "Data restored successfully"
    fi
}

# Confirmation prompt
confirm_restore() {
    echo ""
    log_warning "⚠️  WARNING: This will replace all current Redis data!"
    log_info "Current keys: ${CURRENT_KEYS}"
    log_info "Current memory: ${CURRENT_MEMORY}"
    echo ""
    
    read -p "Are you sure you want to proceed? (yes/no): " confirmation
    
    if [ "${confirmation}" != "yes" ]; then
        log_info "Restore cancelled by user"
        exit 0
    fi
}

# Print restore summary
print_restore_summary() {
    log_info ""
    log_info "=========================================="
    log_info "Redis Restore Summary"
    log_info "=========================================="
    log_info "Backup file: $(basename ${BACKUP_FILE})"
    log_info ""
    log_info "Before restore:"
    log_info "  Keys: ${CURRENT_KEYS}"
    log_info "  Memory: ${CURRENT_MEMORY}"
    log_info ""
    log_info "After restore:"
    log_info "  Keys: ${RESTORED_KEYS}"
    log_info "  Memory: ${RESTORED_MEMORY}"
    log_info "=========================================="
    log_success "Redis restore completed successfully"
}

# Main execution
main() {
    log_info "=========================================="
    log_info "MasterTrade Redis Restore"
    log_info "=========================================="
    log_info "Timestamp: $(date -Iseconds)"
    log_info "Container: ${REDIS_CONTAINER}"
    log_info "=========================================="
    log_info ""
    
    # Parse arguments
    if [ $# -eq 0 ]; then
        show_usage
    fi
    
    case "$1" in
        --list)
            list_backups
            exit 0
            ;;
        --latest)
            BACKUP_FILE=$(get_latest_backup "rdb")
            if [ -z "${BACKUP_FILE}" ]; then
                log_error "No backups found"
                exit 1
            fi
            log_info "Using latest backup: $(basename ${BACKUP_FILE})"
            ;;
        *)
            BACKUP_FILE="$1"
            ;;
    esac
    
    # Verify backup file
    verify_backup_file "${BACKUP_FILE}" || exit 1
    
    # Check Redis container
    check_redis_container || exit 1
    
    # Get current stats
    get_current_stats
    
    # Confirmation
    confirm_restore
    
    # Perform restore
    stop_redis || exit 1
    
    # Determine backup type and restore
    if [[ "${BACKUP_FILE}" =~ \.rdb\.gz$ ]]; then
        restore_rdb "${BACKUP_FILE}" || {
            start_redis
            exit 1
        }
    elif [[ "${BACKUP_FILE}" =~ \.aof\.gz$ ]]; then
        restore_aof "${BACKUP_FILE}" || {
            start_redis
            exit 1
        }
    else
        log_error "Unknown backup file format"
        start_redis
        exit 1
    fi
    
    # Start Redis
    start_redis || exit 1
    
    # Verify restored data
    verify_restored_data
    
    # Print summary
    print_restore_summary
}

main "$@"
