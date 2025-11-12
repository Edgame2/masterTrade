#!/bin/bash

################################################################################
# MasterTrade PostgreSQL Backup Monitoring Script
#
# Description:
#   Monitors backup health and sends alerts if issues are detected
#   Checks: backup age, file integrity, disk space, backup size trends
#
# Usage:
#   ./monitor_backups.sh
#
# Author: MasterTrade DevOps Team
# Date: 2025-11-12
################################################################################

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_DIR="${BACKUP_DIR:-${SCRIPT_DIR}/data}"
MAX_BACKUP_AGE_HOURS="${MAX_BACKUP_AGE_HOURS:-25}"  # Alert if last backup > 25 hours old
MIN_DISK_SPACE_GB="${MIN_DISK_SPACE_GB:-10}"  # Alert if free space < 10GB
ALERT_ENDPOINT="${ALERT_ENDPOINT:-http://localhost:8007/api/alerts/health}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Counters
WARNINGS=0
ERRORS=0

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $(date '+%Y-%m-%d %H:%M:%S') - $1"
}

log_success() {
    echo -e "${GREEN}[OK]${NC} $(date '+%Y-%m-%d %H:%M:%S') - $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $(date '+%Y-%m-%d %H:%M:%S') - $1"
    ((WARNINGS++))
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $(date '+%Y-%m-%d %H:%M:%S') - $1"
    ((ERRORS++))
}

# Send alert to alert system
send_alert() {
    local message="$1"
    local priority="${2:-high}"
    local health_metric="${3:-backup_health}"
    
    if command -v curl &> /dev/null; then
        curl -X POST "${ALERT_ENDPOINT}" \
            -H "Content-Type: application/json" \
            -d "{
                \"service_name\": \"postgresql_backup\",
                \"health_metric\": \"${health_metric}\",
                \"operator\": \"<\",
                \"threshold\": 1.0,
                \"priority\": \"${priority}\",
                \"channels\": [\"email\"],
                \"consecutive_failures\": 1
            }" &>/dev/null || log_warning "Failed to send alert"
    fi
}

# Check if backup directory exists
check_backup_directory() {
    log_info "Checking backup directory..."
    
    if [[ ! -d "${BACKUP_DIR}" ]]; then
        log_error "Backup directory does not exist: ${BACKUP_DIR}"
        send_alert "Backup directory missing: ${BACKUP_DIR}" "critical" "backup_directory"
        return 1
    fi
    
    if [[ ! -d "${BACKUP_DIR}/full" ]]; then
        log_error "Full backup directory does not exist: ${BACKUP_DIR}/full"
        send_alert "Full backup directory missing" "critical" "backup_directory"
        return 1
    fi
    
    log_success "Backup directories exist"
    return 0
}

# Check last backup age
check_backup_age() {
    log_info "Checking backup age..."
    
    local latest_backup=$(find "${BACKUP_DIR}/full" -name "*.sql.gz" -type f -printf '%T@ %p\n' 2>/dev/null | sort -rn | head -1 | cut -d' ' -f2-)
    
    if [[ -z "${latest_backup}" ]]; then
        log_error "No backups found"
        send_alert "No PostgreSQL backups found" "critical" "backup_age"
        return 1
    fi
    
    local backup_time=$(stat -c %Y "${latest_backup}" 2>/dev/null || stat -f %m "${latest_backup}" 2>/dev/null)
    local current_time=$(date +%s)
    local age_hours=$(( (current_time - backup_time) / 3600 ))
    
    log_info "Latest backup: $(basename "${latest_backup}")"
    log_info "Backup age: ${age_hours} hours"
    
    if [[ ${age_hours} -gt ${MAX_BACKUP_AGE_HOURS} ]]; then
        log_error "Backup is too old (${age_hours} hours > ${MAX_BACKUP_AGE_HOURS} hours)"
        send_alert "PostgreSQL backup is ${age_hours} hours old (threshold: ${MAX_BACKUP_AGE_HOURS}h)" "critical" "backup_age"
        return 1
    elif [[ ${age_hours} -gt $((MAX_BACKUP_AGE_HOURS - 2)) ]]; then
        log_warning "Backup is getting old (${age_hours} hours)"
        return 0
    fi
    
    log_success "Backup age is acceptable (${age_hours} hours)"
    return 0
}

# Check backup file integrity
check_backup_integrity() {
    log_info "Checking backup integrity..."
    
    local backup_count=0
    local corrupted_count=0
    
    while IFS= read -r backup_file; do
        ((backup_count++))
        
        # Test gzip integrity
        if ! gzip -t "${backup_file}" 2>/dev/null; then
            log_error "Corrupted backup: $(basename "${backup_file}")"
            ((corrupted_count++))
        fi
        
        # Verify checksum if metadata available
        local meta_file="${backup_file%.sql.gz}.meta"
        if [[ -f "${meta_file}" ]]; then
            local stored_checksum=$(grep -o '"checksum": "[^"]*"' "${meta_file}" 2>/dev/null | cut -d'"' -f4)
            if [[ -n "${stored_checksum}" ]]; then
                local actual_checksum=$(sha256sum "${backup_file}" | awk '{print $1}')
                if [[ "${stored_checksum}" != "${actual_checksum}" ]]; then
                    log_error "Checksum mismatch: $(basename "${backup_file}")"
                    ((corrupted_count++))
                fi
            fi
        fi
    done < <(find "${BACKUP_DIR}/full" -name "*.sql.gz" -type f -mtime -7)
    
    if [[ ${corrupted_count} -gt 0 ]]; then
        log_error "Found ${corrupted_count} corrupted backup(s) out of ${backup_count}"
        send_alert "Found ${corrupted_count} corrupted PostgreSQL backups" "critical" "backup_integrity"
        return 1
    fi
    
    log_success "All ${backup_count} recent backups are intact"
    return 0
}

# Check disk space
check_disk_space() {
    log_info "Checking disk space..."
    
    local backup_partition=$(df -h "${BACKUP_DIR}" | tail -1)
    local free_space_gb=$(echo "${backup_partition}" | awk '{print $4}' | sed 's/G//')
    local usage_percent=$(echo "${backup_partition}" | awk '{print $5}' | sed 's/%//')
    
    log_info "Disk usage: ${usage_percent}%"
    log_info "Free space: ${free_space_gb}GB"
    
    # Check if free space is a number
    if [[ "${free_space_gb}" =~ ^[0-9]+$ ]]; then
        if [[ ${free_space_gb} -lt ${MIN_DISK_SPACE_GB} ]]; then
            log_error "Low disk space: ${free_space_gb}GB (threshold: ${MIN_DISK_SPACE_GB}GB)"
            send_alert "Low disk space for backups: ${free_space_gb}GB remaining" "critical" "disk_space"
            return 1
        elif [[ ${free_space_gb} -lt $((MIN_DISK_SPACE_GB * 2)) ]]; then
            log_warning "Disk space getting low: ${free_space_gb}GB"
        fi
    fi
    
    if [[ ${usage_percent} -gt 90 ]]; then
        log_error "Disk usage too high: ${usage_percent}%"
        send_alert "Backup disk usage at ${usage_percent}%" "critical" "disk_space"
        return 1
    elif [[ ${usage_percent} -gt 80 ]]; then
        log_warning "Disk usage high: ${usage_percent}%"
    fi
    
    log_success "Disk space is adequate (${free_space_gb}GB free, ${usage_percent}% used)"
    return 0
}

# Check backup size trends
check_backup_size_trends() {
    log_info "Checking backup size trends..."
    
    local backup_files=$(find "${BACKUP_DIR}/full" -name "*.sql.gz" -type f -mtime -7 | wc -l)
    
    if [[ ${backup_files} -lt 2 ]]; then
        log_warning "Not enough backups to analyze trends (found ${backup_files})"
        return 0
    fi
    
    # Get last 3 backup sizes
    local sizes=()
    while IFS= read -r backup_file; do
        local size=$(stat -c %s "${backup_file}" 2>/dev/null || stat -f %z "${backup_file}" 2>/dev/null)
        sizes+=("${size}")
    done < <(find "${BACKUP_DIR}/full" -name "*.sql.gz" -type f -mtime -7 -printf '%T@ %p\n' 2>/dev/null | sort -rn | head -3 | cut -d' ' -f2-)
    
    if [[ ${#sizes[@]} -ge 2 ]]; then
        local latest=${sizes[0]}
        local previous=${sizes[1]}
        
        # Check if backup size decreased significantly (>30%)
        local decrease_percent=$(( (previous - latest) * 100 / previous ))
        
        if [[ ${decrease_percent} -gt 30 ]]; then
            log_warning "Backup size decreased significantly: ${decrease_percent}%"
            log_warning "This might indicate data loss or incomplete backup"
        fi
        
        # Check if backup size increased significantly (>50%)
        local increase_percent=$(( (latest - previous) * 100 / previous ))
        
        if [[ ${increase_percent} -gt 50 ]]; then
            log_warning "Backup size increased significantly: ${increase_percent}%"
            log_warning "This is normal for growing databases, but monitor disk space"
        fi
    fi
    
    log_success "Backup size trends are normal"
    return 0
}

# Check backup count
check_backup_count() {
    log_info "Checking backup count..."
    
    local full_backup_count=$(find "${BACKUP_DIR}/full" -name "*.sql.gz" -type f | wc -l)
    local recent_backup_count=$(find "${BACKUP_DIR}/full" -name "*.sql.gz" -type f -mtime -7 | wc -l)
    
    log_info "Total backups: ${full_backup_count}"
    log_info "Recent backups (7 days): ${recent_backup_count}"
    
    if [[ ${full_backup_count} -eq 0 ]]; then
        log_error "No backups found"
        send_alert "No PostgreSQL backups exist" "critical" "backup_count"
        return 1
    fi
    
    if [[ ${recent_backup_count} -eq 0 ]]; then
        log_error "No recent backups found (last 7 days)"
        send_alert "No recent PostgreSQL backups (last 7 days)" "critical" "backup_count"
        return 1
    elif [[ ${recent_backup_count} -lt 5 ]]; then
        log_warning "Few recent backups found: ${recent_backup_count} in last 7 days"
    fi
    
    log_success "Backup count is acceptable"
    return 0
}

# Check WAL archive (if exists)
check_wal_archive() {
    log_info "Checking WAL archive..."
    
    if [[ ! -d "${BACKUP_DIR}/incremental/wal" ]]; then
        log_info "No WAL archive found (incremental backups not configured)"
        return 0
    fi
    
    local wal_count=$(ls -1 "${BACKUP_DIR}/incremental/wal" 2>/dev/null | wc -l)
    local wal_size=$(du -sh "${BACKUP_DIR}/incremental/wal" 2>/dev/null | cut -f1 || echo "0")
    
    log_info "WAL files: ${wal_count}"
    log_info "WAL archive size: ${wal_size}"
    
    if [[ ${wal_count} -eq 0 ]]; then
        log_warning "No WAL files found (incremental backups may not be working)"
    else
        log_success "WAL archive exists with ${wal_count} files"
    fi
    
    return 0
}

# Generate summary report
generate_summary() {
    log_info ""
    log_info "=========================================="
    log_info "Backup Monitoring Summary"
    log_info "=========================================="
    
    if [[ ${ERRORS} -eq 0 && ${WARNINGS} -eq 0 ]]; then
        log_success "All checks passed - Backup system is healthy"
        send_alert "PostgreSQL backup monitoring: All checks passed" "info" "backup_health"
    elif [[ ${ERRORS} -eq 0 && ${WARNINGS} -gt 0 ]]; then
        log_warning "Checks completed with ${WARNINGS} warning(s)"
        send_alert "PostgreSQL backup monitoring: ${WARNINGS} warnings detected" "medium" "backup_health"
    else
        log_error "Checks completed with ${ERRORS} error(s) and ${WARNINGS} warning(s)"
        send_alert "PostgreSQL backup monitoring: ${ERRORS} errors and ${WARNINGS} warnings" "critical" "backup_health"
    fi
    
    log_info "=========================================="
}

# Main execution
main() {
    log_info "=========================================="
    log_info "MasterTrade PostgreSQL Backup Monitoring"
    log_info "=========================================="
    log_info "Timestamp: $(date -Iseconds)"
    log_info "Backup directory: ${BACKUP_DIR}"
    log_info "=========================================="
    log_info ""
    
    # Run all checks
    check_backup_directory || true
    check_backup_age || true
    check_backup_integrity || true
    check_disk_space || true
    check_backup_size_trends || true
    check_backup_count || true
    check_wal_archive || true
    
    # Generate summary
    generate_summary
    
    # Exit with appropriate code
    if [[ ${ERRORS} -gt 0 ]]; then
        exit 1
    fi
    
    exit 0
}

# Run main function
main "$@"
