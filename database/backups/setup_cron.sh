#!/bin/bash

################################################################################
# MasterTrade PostgreSQL Backup Cron Setup Script
#
# Description:
#   Sets up automated cron jobs for PostgreSQL backups
#   - Daily full backups at 2:00 AM
#   - Hourly incremental backups (if WAL archiving configured)
#   - Backup monitoring every 15 minutes
#
# Usage:
#   ./setup_cron.sh
#
# Author: MasterTrade DevOps Team
# Date: 2025-11-12
################################################################################

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATABASE="${DATABASE:-mastertrade}"
CRON_USER="${CRON_USER:-$(whoami)}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running as correct user
check_user() {
    log_info "Checking user permissions..."
    
    if [[ "${CRON_USER}" != "$(whoami)" ]]; then
        log_error "This script should be run as user: ${CRON_USER}"
        exit 1
    fi
    
    log_success "Running as correct user: $(whoami)"
}

# Check if backup scripts exist
check_scripts() {
    log_info "Checking backup scripts..."
    
    if [[ ! -f "${SCRIPT_DIR}/backup_full.sh" ]]; then
        log_error "Full backup script not found: ${SCRIPT_DIR}/backup_full.sh"
        exit 1
    fi
    
    if [[ ! -f "${SCRIPT_DIR}/monitor_backups.sh" ]]; then
        log_error "Monitoring script not found: ${SCRIPT_DIR}/monitor_backups.sh"
        exit 1
    fi
    
    if [[ ! -x "${SCRIPT_DIR}/backup_full.sh" ]]; then
        log_warning "Full backup script is not executable, fixing..."
        chmod +x "${SCRIPT_DIR}/backup_full.sh"
    fi
    
    if [[ ! -x "${SCRIPT_DIR}/monitor_backups.sh" ]]; then
        log_warning "Monitoring script is not executable, fixing..."
        chmod +x "${SCRIPT_DIR}/monitor_backups.sh"
    fi
    
    log_success "All backup scripts found and executable"
}

# Create cron jobs
setup_cron_jobs() {
    log_info "Setting up cron jobs..."
    
    # Backup existing crontab
    crontab -l > /tmp/crontab_backup_$(date +%Y%m%d_%H%M%S).txt 2>/dev/null || true
    
    # Get existing crontab
    local current_cron=$(crontab -l 2>/dev/null || true)
    
    # Remove existing MasterTrade backup cron jobs
    local new_cron=$(echo "${current_cron}" | grep -v "MasterTrade PostgreSQL Backup" || true)
    
    # Add new cron jobs
    local cron_entries=""
    
    # Header comment
    cron_entries+="# MasterTrade PostgreSQL Backup Automation\n"
    
    # Daily full backup at 2:00 AM
    cron_entries+="0 2 * * * cd ${SCRIPT_DIR} && BACKUP_DIR=${SCRIPT_DIR}/data ./backup_full.sh ${DATABASE} >> ${SCRIPT_DIR}/data/logs/backup_full_cron.log 2>&1  # MasterTrade PostgreSQL Backup - Daily Full\n"
    
    # Backup monitoring every 15 minutes
    cron_entries+="*/15 * * * * cd ${SCRIPT_DIR} && BACKUP_DIR=${SCRIPT_DIR}/data ./monitor_backups.sh >> ${SCRIPT_DIR}/data/logs/monitor_cron.log 2>&1  # MasterTrade PostgreSQL Backup - Monitor\n"
    
    # Check if incremental backup script exists
    if [[ -f "${SCRIPT_DIR}/backup_incremental.sh" && -x "${SCRIPT_DIR}/backup_incremental.sh" ]]; then
        # Hourly incremental backup at 5 minutes past the hour
        cron_entries+="5 * * * * cd ${SCRIPT_DIR} && BACKUP_DIR=${SCRIPT_DIR}/data ./backup_incremental.sh ${DATABASE} >> ${SCRIPT_DIR}/data/logs/backup_incremental_cron.log 2>&1  # MasterTrade PostgreSQL Backup - Hourly Incremental\n"
        log_info "Added hourly incremental backup job"
    else
        log_warning "Incremental backup script not found or not executable, skipping..."
    fi
    
    # Combine old and new cron entries
    local final_cron="${new_cron}"
    if [[ -n "${final_cron}" ]]; then
        final_cron+="\n\n"
    fi
    final_cron+="${cron_entries}"
    
    # Install new crontab
    echo -e "${final_cron}" | crontab -
    
    log_success "Cron jobs installed successfully"
}

# Display cron schedule
display_schedule() {
    log_info ""
    log_info "=========================================="
    log_info "Backup Schedule"
    log_info "=========================================="
    log_info "Full Backup:        Daily at 2:00 AM"
    log_info "Incremental Backup: Every hour at :05"
    log_info "Monitoring:         Every 15 minutes"
    log_info "=========================================="
    log_info ""
    log_info "Current crontab entries for backups:"
    echo ""
    crontab -l | grep "MasterTrade PostgreSQL Backup" || log_warning "No backup cron jobs found"
    echo ""
}

# Create log directory
create_log_directory() {
    log_info "Creating log directory..."
    
    local log_dir="${SCRIPT_DIR}/data/logs"
    mkdir -p "${log_dir}"
    
    log_success "Log directory created: ${log_dir}"
}

# Test run monitoring script
test_monitoring() {
    log_info "Testing monitoring script..."
    
    if "${SCRIPT_DIR}/monitor_backups.sh"; then
        log_success "Monitoring script test passed"
    else
        log_warning "Monitoring script test failed (this is expected if no backups exist yet)"
    fi
}

# Main execution
main() {
    log_info "=========================================="
    log_info "MasterTrade PostgreSQL Backup Cron Setup"
    log_info "=========================================="
    log_info "Timestamp: $(date -Iseconds)"
    log_info "Database: ${DATABASE}"
    log_info "User: ${CRON_USER}"
    log_info "=========================================="
    log_info ""
    
    check_user
    check_scripts
    create_log_directory
    setup_cron_jobs
    display_schedule
    test_monitoring
    
    log_info ""
    log_success "Backup automation setup complete!"
    log_info ""
    log_info "Next steps:"
    log_info "1. Verify PostgreSQL credentials are set in environment"
    log_info "2. Run a manual backup test: ./backup_full.sh ${DATABASE}"
    log_info "3. Check logs in: ${SCRIPT_DIR}/data/logs/"
    log_info "4. For incremental backups, configure PostgreSQL archive_mode"
    log_info ""
}

main "$@"
