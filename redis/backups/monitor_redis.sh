#!/bin/bash

################################################################################
# MasterTrade Redis Monitoring Script
#
# Description:
#   Monitors Redis health, persistence, memory, and backup status
#
# Usage:
#   ./monitor_redis.sh
#
# Author: MasterTrade DevOps Team
# Date: 2025-11-12
################################################################################

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REDIS_CONTAINER="${REDIS_CONTAINER:-mastertrade_redis}"
BACKUP_DIR="${BACKUP_DIR:-${SCRIPT_DIR}/data}"
MAX_BACKUP_AGE_HOURS="${MAX_BACKUP_AGE_HOURS:-25}"
MAX_MEMORY_PERCENT="${MAX_MEMORY_PERCENT:-90}"
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

# Send alert
send_alert() {
    local message="$1"
    local priority="${2:-high}"
    local metric="${3:-redis_health}"
    
    if command -v curl &> /dev/null; then
        curl -X POST "${ALERT_ENDPOINT}" \
            -H "Content-Type: application/json" \
            -d "{
                \"service_name\": \"redis\",
                \"health_metric\": \"${metric}\",
                \"operator\": \"<\",
                \"threshold\": 1.0,
                \"priority\": \"${priority}\",
                \"channels\": [\"email\"],
                \"consecutive_failures\": 1
            }" &>/dev/null || true
    fi
}

# Check Redis container
check_redis_container() {
    log_info "Checking Redis container..."
    
    if ! docker ps --filter "name=${REDIS_CONTAINER}" --filter "status=running" | grep -q "${REDIS_CONTAINER}"; then
        log_error "Redis container is not running"
        send_alert "Redis container not running" "critical" "redis_container"
        return 1
    fi
    
    log_success "Redis container is running"
    return 0
}

# Check Redis connectivity
check_redis_connectivity() {
    log_info "Checking Redis connectivity..."
    
    if ! docker exec "${REDIS_CONTAINER}" redis-cli PING &>/dev/null; then
        log_error "Cannot connect to Redis"
        send_alert "Redis not responding to PING" "critical" "redis_connectivity"
        return 1
    fi
    
    log_success "Redis is responding"
    return 0
}

# Check memory usage
check_memory_usage() {
    log_info "Checking memory usage..."
    
    local maxmemory=$(docker exec "${REDIS_CONTAINER}" redis-cli CONFIG GET maxmemory | tail -1)
    local used_memory=$(docker exec "${REDIS_CONTAINER}" redis-cli INFO memory | grep "used_memory:" | cut -d: -f2 | tr -d '\r')
    local used_memory_human=$(docker exec "${REDIS_CONTAINER}" redis-cli INFO memory | grep "used_memory_human:" | cut -d: -f2 | tr -d '\r')
    
    log_info "Memory used: ${used_memory_human}"
    
    if [ "${maxmemory}" != "0" ]; then
        local usage_percent=$((used_memory * 100 / maxmemory))
        log_info "Memory usage: ${usage_percent}%"
        
        if [ ${usage_percent} -ge ${MAX_MEMORY_PERCENT} ]; then
            log_error "Memory usage too high: ${usage_percent}%"
            send_alert "Redis memory usage at ${usage_percent}%" "critical" "redis_memory"
            return 1
        elif [ ${usage_percent} -ge 80 ]; then
            log_warning "Memory usage high: ${usage_percent}%"
        fi
    fi
    
    log_success "Memory usage is acceptable"
    return 0
}

# Check persistence (AOF)
check_aof_persistence() {
    log_info "Checking AOF persistence..."
    
    local aof_enabled=$(docker exec "${REDIS_CONTAINER}" redis-cli CONFIG GET appendonly | tail -1)
    
    if [ "${aof_enabled}" != "yes" ]; then
        log_warning "AOF persistence is not enabled"
        return 0
    fi
    
    local aof_current_size=$(docker exec "${REDIS_CONTAINER}" redis-cli INFO persistence | grep "aof_current_size:" | cut -d: -f2 | tr -d '\r')
    local aof_base_size=$(docker exec "${REDIS_CONTAINER}" redis-cli INFO persistence | grep "aof_base_size:" | cut -d: -f2 | tr -d '\r')
    
    log_info "AOF current size: ${aof_current_size} bytes"
    log_info "AOF base size: ${aof_base_size} bytes"
    
    # Check last AOF rewrite status
    local aof_last_rewrite_status=$(docker exec "${REDIS_CONTAINER}" redis-cli INFO persistence | grep "aof_last_bgrewrite_status:" | cut -d: -f2 | tr -d '\r')
    
    if [ "${aof_last_rewrite_status}" = "ok" ]; then
        log_success "AOF persistence is healthy"
    else
        log_error "Last AOF rewrite failed"
        send_alert "Redis AOF rewrite failed" "high" "redis_aof"
        return 1
    fi
    
    return 0
}

# Check RDB persistence
check_rdb_persistence() {
    log_info "Checking RDB persistence..."
    
    local rdb_last_save_time=$(docker exec "${REDIS_CONTAINER}" redis-cli LASTSAVE)
    local current_time=$(date +%s)
    local save_age=$((current_time - rdb_last_save_time))
    local save_age_hours=$((save_age / 3600))
    
    log_info "Last RDB save: ${save_age_hours} hours ago"
    
    # Check last save status
    local rdb_last_save_status=$(docker exec "${REDIS_CONTAINER}" redis-cli INFO persistence | grep "rdb_last_bgsave_status:" | cut -d: -f2 | tr -d '\r')
    
    if [ "${rdb_last_save_status}" != "ok" ]; then
        log_error "Last RDB save failed"
        send_alert "Redis RDB save failed" "critical" "redis_rdb"
        return 1
    fi
    
    if [ ${save_age_hours} -gt 25 ]; then
        log_warning "RDB save is overdue (${save_age_hours} hours)"
    fi
    
    log_success "RDB persistence is healthy"
    return 0
}

# Check backup age
check_backup_age() {
    log_info "Checking backup age..."
    
    if [ ! -d "${BACKUP_DIR}/rdb" ]; then
        log_warning "Backup directory not found"
        return 0
    fi
    
    local latest_backup=$(find "${BACKUP_DIR}/rdb" -name "dump_*.rdb.gz" -type f -printf '%T@ %p\n' 2>/dev/null | sort -rn | head -1 | cut -d' ' -f2-)
    
    if [ -z "${latest_backup}" ]; then
        log_error "No backups found"
        send_alert "No Redis backups found" "critical" "redis_backup_age"
        return 1
    fi
    
    local backup_time=$(stat -c %Y "${latest_backup}" 2>/dev/null || stat -f %m "${latest_backup}" 2>/dev/null)
    local current_time=$(date +%s)
    local age_hours=$(( (current_time - backup_time) / 3600 ))
    
    log_info "Latest backup: $(basename ${latest_backup})"
    log_info "Backup age: ${age_hours} hours"
    
    if [ ${age_hours} -gt ${MAX_BACKUP_AGE_HOURS} ]; then
        log_error "Backup is too old (${age_hours} hours)"
        send_alert "Redis backup is ${age_hours} hours old" "critical" "redis_backup_age"
        return 1
    elif [ ${age_hours} -gt $((MAX_BACKUP_AGE_HOURS - 2)) ]; then
        log_warning "Backup is getting old (${age_hours} hours)"
    fi
    
    log_success "Backup age is acceptable"
    return 0
}

# Check connected clients
check_connected_clients() {
    log_info "Checking connected clients..."
    
    local connected_clients=$(docker exec "${REDIS_CONTAINER}" redis-cli INFO clients | grep "connected_clients:" | cut -d: -f2 | tr -d '\r')
    local blocked_clients=$(docker exec "${REDIS_CONTAINER}" redis-cli INFO clients | grep "blocked_clients:" | cut -d: -f2 | tr -d '\r')
    
    log_info "Connected clients: ${connected_clients}"
    log_info "Blocked clients: ${blocked_clients}"
    
    if [ ${connected_clients} -gt 9000 ]; then
        log_warning "High number of connected clients: ${connected_clients}"
    fi
    
    if [ ${blocked_clients} -gt 100 ]; then
        log_warning "Many blocked clients: ${blocked_clients}"
    fi
    
    log_success "Client connections are normal"
    return 0
}

# Check keyspace
check_keyspace() {
    log_info "Checking keyspace..."
    
    local total_keys=$(docker exec "${REDIS_CONTAINER}" redis-cli DBSIZE | tr -d '\r')
    
    log_info "Total keys: ${total_keys}"
    
    # Check expired keys
    local expired_keys=$(docker exec "${REDIS_CONTAINER}" redis-cli INFO stats | grep "expired_keys:" | cut -d: -f2 | tr -d '\r')
    local evicted_keys=$(docker exec "${REDIS_CONTAINER}" redis-cli INFO stats | grep "evicted_keys:" | cut -d: -f2 | tr -d '\r')
    
    log_info "Expired keys (lifetime): ${expired_keys}"
    log_info "Evicted keys (lifetime): ${evicted_keys}"
    
    if [ ${evicted_keys} -gt 10000 ]; then
        log_warning "Many keys have been evicted (${evicted_keys}) - consider increasing maxmemory"
    fi
    
    log_success "Keyspace is healthy"
    return 0
}

# Check replication (if configured)
check_replication() {
    log_info "Checking replication..."
    
    local role=$(docker exec "${REDIS_CONTAINER}" redis-cli INFO replication | grep "role:" | cut -d: -f2 | tr -d '\r')
    
    log_info "Redis role: ${role}"
    
    if [ "${role}" = "master" ]; then
        local connected_slaves=$(docker exec "${REDIS_CONTAINER}" redis-cli INFO replication | grep "connected_slaves:" | cut -d: -f2 | tr -d '\r')
        log_info "Connected slaves: ${connected_slaves}"
    fi
    
    log_success "Replication check complete"
    return 0
}

# Generate summary
generate_summary() {
    log_info ""
    log_info "=========================================="
    log_info "Redis Monitoring Summary"
    log_info "=========================================="
    
    if [ ${ERRORS} -eq 0 ] && [ ${WARNINGS} -eq 0 ]; then
        log_success "All checks passed - Redis is healthy"
        send_alert "Redis monitoring: All checks passed" "info" "redis_health"
    elif [ ${ERRORS} -eq 0 ] && [ ${WARNINGS} -gt 0 ]; then
        log_warning "Checks completed with ${WARNINGS} warning(s)"
        send_alert "Redis monitoring: ${WARNINGS} warnings detected" "medium" "redis_health"
    else
        log_error "Checks completed with ${ERRORS} error(s) and ${WARNINGS} warning(s)"
        send_alert "Redis monitoring: ${ERRORS} errors and ${WARNINGS} warnings" "critical" "redis_health"
    fi
    
    log_info "=========================================="
}

# Main execution
main() {
    log_info "=========================================="
    log_info "MasterTrade Redis Monitoring"
    log_info "=========================================="
    log_info "Timestamp: $(date -Iseconds)"
    log_info "Container: ${REDIS_CONTAINER}"
    log_info "=========================================="
    log_info ""
    
    # Run all checks
    check_redis_container || true
    check_redis_connectivity || true
    check_memory_usage || true
    check_aof_persistence || true
    check_rdb_persistence || true
    check_backup_age || true
    check_connected_clients || true
    check_keyspace || true
    check_replication || true
    
    # Generate summary
    generate_summary
    
    # Exit with appropriate code
    if [ ${ERRORS} -gt 0 ]; then
        exit 1
    fi
    
    exit 0
}

main "$@"
