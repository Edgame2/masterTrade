#!/bin/bash

# masterTrade Health Monitor
# Continuous monitoring and alerting system for production deployment

set -euo pipefail

# Configuration
HEALTH_CHECK_INTERVAL=30  # seconds
ALERT_THRESHOLD_CONSECUTIVE_FAILURES=3
ALERT_COOLDOWN_MINUTES=15
METRICS_RETENTION_HOURS=24

# Alert destinations
SLACK_WEBHOOK_URL="${SLACK_WEBHOOK_URL:-}"
EMAIL_RECIPIENTS="${EMAIL_RECIPIENTS:-ops@mastertrade.com}"
PAGERDUTY_API_KEY="${PAGERDUTY_API_KEY:-}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# State tracking
declare -A service_failure_count
declare -A last_alert_time
declare -A service_status

# Logging functions
log_info() {
    echo -e "${BLUE}[MONITOR]${NC} $(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a /var/log/mastertrade/monitor.log
}

log_success() {
    echo -e "${GREEN}[HEALTHY]${NC} $(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a /var/log/mastertrade/monitor.log
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a /var/log/mastertrade/monitor.log
}

log_error() {
    echo -e "${RED}[CRITICAL]${NC} $(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a /var/log/mastertrade/monitor.log
}

# Send Slack alert
send_slack_alert() {
    local message="$1"
    local severity="$2"
    
    if [[ -z "$SLACK_WEBHOOK_URL" ]]; then
        return 0
    fi
    
    local color="#36a64f"  # Green
    case $severity in
        "warning") color="#ffaa00" ;;  # Orange
        "critical") color="#ff0000" ;; # Red
    esac
    
    local payload=$(cat <<EOF
{
    "attachments": [
        {
            "color": "$color",
            "title": "masterTrade Alert - $severity",
            "text": "$message",
            "ts": $(date +%s)
        }
    ]
}
EOF
    )
    
    curl -X POST -H 'Content-type: application/json' \
        --data "$payload" \
        "$SLACK_WEBHOOK_URL" &> /dev/null || true
}

# Send email alert
send_email_alert() {
    local subject="$1"
    local message="$2"
    
    if command -v mail &> /dev/null; then
        echo "$message" | mail -s "$subject" "$EMAIL_RECIPIENTS" || true
    fi
}

# Send PagerDuty alert
send_pagerduty_alert() {
    local message="$1"
    local severity="$2"
    
    if [[ -z "$PAGERDUTY_API_KEY" ]]; then
        return 0
    fi
    
    local event_action="trigger"
    if [[ "$severity" == "info" ]]; then
        event_action="resolve"
    fi
    
    local payload=$(cat <<EOF
{
    "routing_key": "$PAGERDUTY_API_KEY",
    "event_action": "$event_action",
    "dedup_key": "mastertrade_health_check",
    "payload": {
        "summary": "$message",
        "severity": "$severity",
        "source": "mastertrade-monitor"
    }
}
EOF
    )
    
    curl -X POST \
        -H "Content-Type: application/json" \
        -d "$payload" \
        "https://events.pagerduty.com/v2/enqueue" &> /dev/null || true
}

# Send comprehensive alert
send_alert() {
    local service="$1"
    local message="$2"
    local severity="$3"
    
    # Check cooldown period
    local current_time=$(date +%s)
    local last_alert=${last_alert_time[$service]:-0}
    local cooldown_seconds=$((ALERT_COOLDOWN_MINUTES * 60))
    
    if [[ $((current_time - last_alert)) -lt $cooldown_seconds ]] && [[ "$severity" != "critical" ]]; then
        return 0
    fi
    
    # Update last alert time
    last_alert_time[$service]=$current_time
    
    # Send alerts
    local full_message="Service: $service | $message | Time: $(date)"
    
    send_slack_alert "$full_message" "$severity"
    send_email_alert "masterTrade Alert: $service $severity" "$full_message"
    
    if [[ "$severity" == "critical" ]]; then
        send_pagerduty_alert "$full_message" "$severity"
    fi
    
    log_info "Alert sent for $service: $severity - $message"
}

# Check service health
check_service_health() {
    local service="$1"
    local endpoint="$2"
    local timeout="${3:-10}"
    
    # Perform health check
    local http_code=$(curl -s -o /dev/null -w "%{http_code}" --max-time "$timeout" "$endpoint" 2>/dev/null || echo "000")
    
    if [[ "$http_code" =~ ^2[0-9][0-9]$ ]]; then
        # Service is healthy
        service_failure_count[$service]=0
        
        # If service was previously down, send recovery alert
        if [[ "${service_status[$service]:-healthy}" == "unhealthy" ]]; then
            send_alert "$service" "Service recovered and is now healthy" "info"
            log_success "$service recovered"
        fi
        
        service_status[$service]="healthy"
        return 0
    else
        # Service is unhealthy
        local failures=${service_failure_count[$service]:-0}
        failures=$((failures + 1))
        service_failure_count[$service]=$failures
        service_status[$service]="unhealthy"
        
        log_warning "$service health check failed (attempt $failures/$ALERT_THRESHOLD_CONSECUTIVE_FAILURES) - HTTP $http_code"
        
        # Send alert if threshold reached
        if [[ $failures -ge $ALERT_THRESHOLD_CONSECUTIVE_FAILURES ]]; then
            local severity="warning"
            if [[ $failures -ge $((ALERT_THRESHOLD_CONSECUTIVE_FAILURES * 2)) ]]; then
                severity="critical"
            fi
            
            send_alert "$service" "Health check failed $failures consecutive times (HTTP $http_code)" "$severity"
        fi
        
        return 1
    fi
}

# Check Docker container health
check_container_health() {
    local container="$1"
    
    # Check if container is running
    if ! docker ps --format "{{.Names}}" | grep -q "^${container}$"; then
        log_error "Container $container is not running"
        send_alert "$container" "Container is not running" "critical"
        return 1
    fi
    
    # Check container health status
    local health_status=$(docker inspect --format='{{.State.Health.Status}}' "$container" 2>/dev/null || echo "unknown")
    
    case $health_status in
        "healthy")
            log_success "Container $container is healthy"
            return 0
            ;;
        "unhealthy")
            log_error "Container $container is unhealthy"
            send_alert "$container" "Container health check failed" "warning"
            return 1
            ;;
        "starting")
            log_info "Container $container is starting"
            return 0
            ;;
        *)
            log_warning "Container $container health status unknown: $health_status"
            return 1
            ;;
    esac
}

# Check system resources
check_system_resources() {
    # Check disk space (alert if > 85% full)
    local disk_usage=$(df / | awk 'NR==2 {print $5}' | sed 's/%//')
    if [[ $disk_usage -gt 85 ]]; then
        local severity="warning"
        if [[ $disk_usage -gt 95 ]]; then
            severity="critical"
        fi
        send_alert "system" "Disk usage is ${disk_usage}%" "$severity"
    fi
    
    # Check memory usage (alert if > 90% used)
    local memory_usage=$(free | awk 'NR==2{printf "%.0f", $3*100/$2}')
    if [[ $memory_usage -gt 90 ]]; then
        send_alert "system" "Memory usage is ${memory_usage}%" "warning"
    fi
    
    # Check load average (alert if > number of CPUs)
    local cpu_count=$(nproc)
    local load_avg=$(uptime | awk -F'load average:' '{print $2}' | awk '{print $1}' | sed 's/,//')
    if (( $(echo "$load_avg > $cpu_count" | bc -l) )); then
        send_alert "system" "Load average is $load_avg (CPUs: $cpu_count)" "warning"
    fi
}

# Check database performance
check_database_performance() {
    local max_connections=$(docker-compose exec -T postgres_primary psql -U mastertrade_prod -t -c "SHOW max_connections;" 2>/dev/null | tr -d ' ' || echo "0")
    local current_connections=$(docker-compose exec -T postgres_primary psql -U mastertrade_prod -t -c "SELECT count(*) FROM pg_stat_activity;" 2>/dev/null | tr -d ' ' || echo "0")
    
    if [[ $max_connections -gt 0 && $current_connections -gt 0 ]]; then
        local connection_percentage=$(( current_connections * 100 / max_connections ))
        
        if [[ $connection_percentage -gt 80 ]]; then
            send_alert "database" "Connection usage is ${connection_percentage}% (${current_connections}/${max_connections})" "warning"
        fi
    fi
    
    # Check for long-running queries (> 5 minutes)
    local long_queries=$(docker-compose exec -T postgres_primary psql -U mastertrade_prod -t -c "SELECT count(*) FROM pg_stat_activity WHERE state = 'active' AND query_start < now() - interval '5 minutes';" 2>/dev/null | tr -d ' ' || echo "0")
    
    if [[ $long_queries -gt 0 ]]; then
        send_alert "database" "$long_queries long-running queries detected (>5 minutes)" "warning"
    fi
}

# Check Redis performance
check_redis_performance() {
    local redis_info=$(docker-compose exec -T redis_cluster redis-cli info memory 2>/dev/null || echo "")
    
    if [[ -n "$redis_info" ]]; then
        local used_memory=$(echo "$redis_info" | grep "used_memory:" | cut -d: -f2 | tr -d '\r')
        local max_memory=$(echo "$redis_info" | grep "maxmemory:" | cut -d: -f2 | tr -d '\r')
        
        if [[ $max_memory -gt 0 && $used_memory -gt 0 ]]; then
            local memory_percentage=$(( used_memory * 100 / max_memory ))
            
            if [[ $memory_percentage -gt 80 ]]; then
                send_alert "redis" "Memory usage is ${memory_percentage}%" "warning"
            fi
        fi
    fi
}

# Generate health metrics
generate_metrics() {
    local timestamp=$(date +%s)
    local metrics_file="/var/log/mastertrade/metrics_$(date +%Y%m%d).json"
    
    # Collect metrics
    local metrics=$(cat <<EOF
{
    "timestamp": $timestamp,
    "services": {
EOF
    )
    
    # Add service statuses
    local first=true
    for service in "${!service_status[@]}"; do
        if [[ "$first" == "true" ]]; then
            first=false
        else
            metrics+=","
        fi
        metrics+="\"$service\": {\"status\": \"${service_status[$service]}\", \"failures\": ${service_failure_count[$service]:-0}}"
    done
    
    metrics+="},\"system\": {"
    
    # Add system metrics
    local disk_usage=$(df / | awk 'NR==2 {print $5}' | sed 's/%//')
    local memory_usage=$(free | awk 'NR==2{printf "%.0f", $3*100/$2}')
    local load_avg=$(uptime | awk -F'load average:' '{print $2}' | awk '{print $1}' | sed 's/,//')
    
    metrics+="\"disk_usage_percent\": $disk_usage,"
    metrics+="\"memory_usage_percent\": $memory_usage,"
    metrics+="\"load_average\": $load_avg"
    metrics+="}}"
    
    # Append to metrics file
    echo "$metrics" >> "$metrics_file"
    
    # Clean old metrics files
    find /var/log/mastertrade/ -name "metrics_*.json" -mtime +1 -delete 2>/dev/null || true
}

# Main monitoring loop
main_monitor_loop() {
    log_info "Starting masterTrade health monitoring..."
    
    # Create log directory
    mkdir -p /var/log/mastertrade
    
    while true; do
        log_info "Running health checks..."
        
        # Check core services
        check_service_health "api_gateway" "http://localhost/health"
        check_service_health "market_data" "http://localhost/api/v1/market-data/health"
        check_service_health "strategy_service" "http://localhost/api/v1/strategy/health"
        check_service_health "risk_manager" "http://localhost/api/v1/risk/health"
        check_service_health "order_executor" "http://localhost/api/v1/orders/health"
        
        # Check monitoring services
        check_service_health "grafana" "http://localhost:3000/api/health" 5
        check_service_health "prometheus" "http://localhost:9090/-/healthy" 5
        
        # Check containers
        local containers=("postgres_primary" "redis_cluster" "rabbitmq_cluster")
        for container in "${containers[@]}"; do
            check_container_health "$container"
        done
        
        # Check system resources
        check_system_resources
        
        # Check database performance
        check_database_performance
        
        # Check Redis performance  
        check_redis_performance
        
        # Generate metrics
        generate_metrics
        
        log_info "Health check cycle completed. Next check in ${HEALTH_CHECK_INTERVAL} seconds."
        
        # Sleep until next check
        sleep $HEALTH_CHECK_INTERVAL
    done
}

# Signal handlers
cleanup() {
    log_info "Health monitor shutting down..."
    exit 0
}

trap cleanup SIGTERM SIGINT

# Main execution
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main_monitor_loop "$@"
fi