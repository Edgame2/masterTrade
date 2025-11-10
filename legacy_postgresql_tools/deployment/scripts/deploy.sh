#!/bin/bash

# masterTrade Production Deployment Script
# Automated deployment with comprehensive health checks and rollback capabilities

set -euo pipefail

# Configuration
DEPLOYMENT_CONFIG="production-docker-compose.yml"
ENVIRONMENT="production"
BACKUP_RETENTION_DAYS=30
HEALTH_CHECK_TIMEOUT=300
MAX_ROLLBACK_ATTEMPTS=3

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
    echo -e "${RED}[ERROR]${NC} $(date '+%Y-%m-%d %H:%M:%S') - $1"
}

# Cleanup function
cleanup() {
    log_info "Cleaning up temporary files..."
    rm -f /tmp/mastertrade_deployment_*.log
}

# Error handler
error_handler() {
    local exit_code=$?
    log_error "Deployment failed with exit code: $exit_code"
    log_error "Check logs for details: /var/log/mastertrade/deployment.log"
    
    # Attempt rollback on failure
    if [[ $exit_code -ne 0 ]]; then
        log_warning "Initiating emergency rollback..."
        rollback_deployment
    fi
    
    cleanup
    exit $exit_code
}

# Set error trap
trap error_handler ERR

# Check prerequisites
check_prerequisites() {
    log_info "Checking deployment prerequisites..."
    
    # Check if Docker is running
    if ! docker info &> /dev/null; then
        log_error "Docker is not running or not accessible"
        exit 1
    fi
    
    # Check if Docker Compose is available
    if ! command -v docker-compose &> /dev/null; then
        log_error "Docker Compose is not installed"
        exit 1
    fi
    
    # Check if .env file exists
    if [[ ! -f ".env" ]]; then
        log_error ".env file not found. Copy from .env.production.template"
        exit 1
    fi
    
    # Check disk space (minimum 10GB)
    available_space=$(df . | awk 'NR==2 {print $4}')
    if [[ $available_space -lt 10485760 ]]; then  # 10GB in KB
        log_error "Insufficient disk space. At least 10GB required"
        exit 1
    fi
    
    # Check memory (minimum 8GB)
    total_memory=$(free -m | awk 'NR==2{printf "%.1f", $2/1024}')
    if (( $(echo "$total_memory < 8.0" | bc -l) )); then
        log_error "Insufficient memory. At least 8GB RAM required"
        exit 1
    fi
    
    log_success "All prerequisites met"
}

# Create backup
create_backup() {
    log_info "Creating backup of current deployment..."
    
    local backup_dir="backups/$(date '+%Y%m%d_%H%M%S')"
    mkdir -p "$backup_dir"
    
    # Backup database
    if docker-compose ps postgres_primary | grep -q "Up"; then
        log_info "Backing up PostgreSQL database..."
        docker-compose exec -T postgres_primary pg_dumpall -U mastertrade_prod > "$backup_dir/database_backup.sql"
    fi
    
    # Backup Redis data
    if docker-compose ps redis_cluster | grep -q "Up"; then
        log_info "Backing up Redis data..."
        docker-compose exec -T redis_cluster redis-cli BGSAVE
        docker cp $(docker-compose ps -q redis_cluster):/data/dump.rdb "$backup_dir/redis_backup.rdb"
    fi
    
    # Backup configuration files
    cp -r deployment "$backup_dir/"
    cp .env "$backup_dir/"
    
    # Save current image tags
    docker-compose config > "$backup_dir/docker-compose-resolved.yml"
    
    log_success "Backup created at: $backup_dir"
    echo "$backup_dir" > .last_backup
    
    # Clean old backups
    find backups/ -type d -mtime +$BACKUP_RETENTION_DAYS -exec rm -rf {} + 2>/dev/null || true
}

# Pull latest images
pull_images() {
    log_info "Pulling latest Docker images..."
    
    # Pull base images
    docker-compose -f "$DEPLOYMENT_CONFIG" pull --quiet
    
    # Build custom images
    log_info "Building custom services..."
    docker-compose -f "$DEPLOYMENT_CONFIG" build --no-cache --pull
    
    log_success "Images updated successfully"
}

# Health check function
health_check() {
    local service=$1
    local endpoint=$2
    local timeout=${3:-60}
    local interval=5
    local elapsed=0
    
    log_info "Performing health check for $service..."
    
    while [[ $elapsed -lt $timeout ]]; do
        if curl -f -s "$endpoint" &> /dev/null; then
            log_success "$service is healthy"
            return 0
        fi
        
        sleep $interval
        elapsed=$((elapsed + interval))
        echo -n "."
    done
    
    log_error "$service failed health check after ${timeout}s"
    return 1
}

# Deploy services in stages
deploy_services() {
    log_info "Starting staged deployment..."
    
    # Stage 1: Infrastructure services
    log_info "Stage 1: Deploying infrastructure services..."
    docker-compose -f "$DEPLOYMENT_CONFIG" up -d \
        postgres_primary \
        postgres_replica \
        redis_cluster \
        rabbitmq_cluster \
        vault
    
    # Wait for infrastructure
    sleep 30
    
    # Stage 2: Core services
    log_info "Stage 2: Deploying core services..."
    docker-compose -f "$DEPLOYMENT_CONFIG" up -d \
        market_data_service \
        strategy_service \
        risk_manager \
        order_executor
    
    # Wait for core services
    sleep 60
    
    # Stage 3: API Gateway and load balancer
    log_info "Stage 3: Deploying API gateway and load balancer..."
    docker-compose -f "$DEPLOYMENT_CONFIG" up -d \
        api_gateway_1 \
        api_gateway_2 \
        nginx
    
    # Stage 4: Monitoring and logging
    log_info "Stage 4: Deploying monitoring stack..."
    docker-compose -f "$DEPLOYMENT_CONFIG" up -d \
        prometheus \
        grafana \
        alertmanager \
        elasticsearch \
        logstash \
        kibana
    
    # Stage 5: Backup service
    log_info "Stage 5: Deploying backup service..."
    docker-compose -f "$DEPLOYMENT_CONFIG" up -d backup_service
    
    log_success "All services deployed successfully"
}

# Comprehensive health checks
perform_health_checks() {
    log_info "Performing comprehensive health checks..."
    
    local failed_checks=0
    
    # API Gateway health check
    if ! health_check "API Gateway" "http://localhost/health" 120; then
        ((failed_checks++))
    fi
    
    # Database health check
    if ! docker-compose exec -T postgres_primary pg_isready -U mastertrade_prod; then
        log_error "PostgreSQL primary is not ready"
        ((failed_checks++))
    fi
    
    # Redis health check
    if ! docker-compose exec -T redis_cluster redis-cli ping | grep -q "PONG"; then
        log_error "Redis is not responding"
        ((failed_checks++))
    fi
    
    # RabbitMQ health check
    if ! docker-compose exec -T rabbitmq_cluster rabbitmq-diagnostics ping; then
        log_error "RabbitMQ is not ready"
        ((failed_checks++))
    fi
    
    # Service health checks
    local services=("market_data_service" "strategy_service" "risk_manager" "order_executor")
    for service in "${services[@]}"; do
        if ! docker-compose ps "$service" | grep -q "Up"; then
            log_error "$service is not running"
            ((failed_checks++))
        fi
    done
    
    # Monitoring stack health checks
    if ! health_check "Grafana" "http://localhost:3000/api/health" 60; then
        log_warning "Grafana health check failed (non-critical)"
    fi
    
    if ! health_check "Prometheus" "http://localhost:9090/-/healthy" 60; then
        log_warning "Prometheus health check failed (non-critical)"
    fi
    
    if [[ $failed_checks -eq 0 ]]; then
        log_success "All critical health checks passed"
        return 0
    else
        log_error "$failed_checks critical health checks failed"
        return 1
    fi
}

# Rollback deployment
rollback_deployment() {
    log_warning "Initiating deployment rollback..."
    
    if [[ ! -f ".last_backup" ]]; then
        log_error "No backup reference found for rollback"
        return 1
    fi
    
    local backup_dir=$(cat .last_backup)
    if [[ ! -d "$backup_dir" ]]; then
        log_error "Backup directory not found: $backup_dir"
        return 1
    fi
    
    # Stop current services
    log_info "Stopping current services..."
    docker-compose -f "$DEPLOYMENT_CONFIG" down --timeout 30
    
    # Restore configuration
    log_info "Restoring configuration..."
    cp "$backup_dir/.env" .env
    
    # Restore database
    if [[ -f "$backup_dir/database_backup.sql" ]]; then
        log_info "Restoring database..."
        # Start only database for restore
        docker-compose -f "$DEPLOYMENT_CONFIG" up -d postgres_primary
        sleep 30
        docker-compose exec -T postgres_primary psql -U mastertrade_prod -f /tmp/database_backup.sql < "$backup_dir/database_backup.sql"
    fi
    
    # Start services with old configuration
    log_info "Starting services from backup..."
    docker-compose -f "$backup_dir/deployment/docker-compose-resolved.yml" up -d
    
    # Basic health check after rollback
    sleep 60
    if health_check "API Gateway (Rollback)" "http://localhost/health" 60; then
        log_success "Rollback completed successfully"
        return 0
    else
        log_error "Rollback failed - manual intervention required"
        return 1
    fi
}

# Generate deployment report
generate_deployment_report() {
    log_info "Generating deployment report..."
    
    local report_file="deployment_reports/deployment_$(date '+%Y%m%d_%H%M%S').json"
    mkdir -p deployment_reports
    
    # Collect deployment information
    local deployment_info=$(cat <<EOF
{
    "deployment": {
        "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
        "environment": "$ENVIRONMENT",
        "version": "$(git rev-parse HEAD 2>/dev/null || echo 'unknown')",
        "services": $(docker-compose -f "$DEPLOYMENT_CONFIG" ps --format json | jq -s '.'),
        "images": $(docker-compose -f "$DEPLOYMENT_CONFIG" images --format json | jq -s '.'),
        "system_info": {
            "hostname": "$(hostname)",
            "os": "$(uname -a)",
            "docker_version": "$(docker --version)",
            "compose_version": "$(docker-compose --version)"
        }
    }
}
EOF
    )
    
    echo "$deployment_info" | jq '.' > "$report_file"
    log_success "Deployment report saved: $report_file"
}

# Post-deployment tasks
post_deployment_tasks() {
    log_info "Executing post-deployment tasks..."
    
    # Update system configurations
    log_info "Updating system configurations..."
    
    # Set up log rotation
    cat > /etc/logrotate.d/mastertrade << 'EOF'
/var/log/mastertrade/*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    create 644 mastertrade mastertrade
    postrotate
        docker-compose -f /opt/mastertrade/production-docker-compose.yml kill -s USR1 nginx
    endscript
}
EOF
    
    # Set up monitoring alerts
    log_info "Configuring monitoring alerts..."
    
    # Warm up caches
    log_info "Warming up application caches..."
    curl -s "http://localhost/api/v1/health/detailed" > /dev/null || true
    
    # Schedule automatic backups
    log_info "Setting up automatic backup schedule..."
    echo "0 2 * * * /opt/mastertrade/scripts/backup.sh" | crontab -
    
    log_success "Post-deployment tasks completed"
}

# Main deployment function
main() {
    log_info "Starting masterTrade production deployment..."
    log_info "Deployment configuration: $DEPLOYMENT_CONFIG"
    
    # Create log directory
    mkdir -p /var/log/mastertrade
    
    # Check prerequisites
    check_prerequisites
    
    # Create backup
    create_backup
    
    # Pull and build images
    pull_images
    
    # Deploy services
    deploy_services
    
    # Comprehensive health checks
    if ! perform_health_checks; then
        log_error "Health checks failed - initiating rollback"
        rollback_deployment
        exit 1
    fi
    
    # Post-deployment tasks
    post_deployment_tasks
    
    # Generate deployment report
    generate_deployment_report
    
    # Final status
    log_success "==================================="
    log_success "masterTrade Production Deployment Complete!"
    log_success "==================================="
    log_info "API Endpoint: https://api.mastertrade.local"
    log_info "Monitoring: https://monitoring.mastertrade.local"
    log_info "Logs: https://logs.mastertrade.local"
    log_info "Services Status:"
    
    docker-compose -f "$DEPLOYMENT_CONFIG" ps
    
    log_info "Deployment completed at: $(date)"
}

# Script execution
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi