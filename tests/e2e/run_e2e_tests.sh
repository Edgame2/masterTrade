#!/bin/bash

# End-to-End Test Runner Script
# Runs comprehensive E2E tests for MasterTrade system

set -e  # Exit on error

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/../.." && pwd )"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}   MasterTrade E2E Test Suite${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Function to check if a service is running
check_service() {
    local service_name=$1
    local port=$2
    local host=${3:-localhost}
    
    if nc -z $host $port 2>/dev/null; then
        echo -e "${GREEN}✓${NC} $service_name is running on port $port"
        return 0
    else
        echo -e "${RED}✗${NC} $service_name is NOT running on port $port"
        return 1
    fi
}

# Function to check service health via HTTP
check_http_service() {
    local service_name=$1
    local url=$2
    
    if curl -sf $url > /dev/null 2>&1; then
        echo -e "${GREEN}✓${NC} $service_name is healthy at $url"
        return 0
    else
        echo -e "${YELLOW}⚠${NC} $service_name health check failed at $url"
        return 1
    fi
}

# Check prerequisites
echo -e "${BLUE}Checking prerequisites...${NC}"
echo ""

all_services_up=true

# Check PostgreSQL
if ! check_service "PostgreSQL" 5432; then
    all_services_up=false
fi

# Check RabbitMQ
if ! check_service "RabbitMQ" 5672; then
    all_services_up=false
fi

# Check market_data_service
if ! check_service "market_data_service" 8000; then
    all_services_up=false
fi

# Check strategy_service
if ! check_service "strategy_service" 8006; then
    all_services_up=false
fi

# Check risk_manager
if ! check_service "risk_manager" 8003; then
    all_services_up=false
fi

echo ""

if [ "$all_services_up" = false ]; then
    echo -e "${YELLOW}⚠ Not all services are running${NC}"
    echo -e "${YELLOW}Starting services with docker-compose...${NC}"
    echo ""
    
    cd "$PROJECT_ROOT"
    docker-compose up -d postgres rabbitmq market_data_service strategy_service risk_manager
    
    echo ""
    echo -e "${YELLOW}Waiting 10 seconds for services to start...${NC}"
    sleep 10
    echo ""
fi

# Check service health endpoints
echo -e "${BLUE}Checking service health...${NC}"
echo ""

check_http_service "market_data_service" "http://localhost:8000/health" || true
check_http_service "strategy_service" "http://localhost:8006/health" || true
check_http_service "risk_manager" "http://localhost:8003/health" || true

echo ""

# Set environment variables
export TEST_DATABASE_URL="${TEST_DATABASE_URL:-postgresql://mastertrade:mastertrade@localhost:5432/mastertrade}"
export TEST_RABBITMQ_URL="${TEST_RABBITMQ_URL:-amqp://guest:guest@localhost:5672/}"
export MARKET_DATA_API_URL="${MARKET_DATA_API_URL:-http://localhost:8000}"
export STRATEGY_API_URL="${STRATEGY_API_URL:-http://localhost:8006}"
export RISK_MANAGER_API_URL="${RISK_MANAGER_API_URL:-http://localhost:8003}"

echo -e "${BLUE}Environment variables:${NC}"
echo -e "  TEST_DATABASE_URL: $TEST_DATABASE_URL"
echo -e "  TEST_RABBITMQ_URL: $TEST_RABBITMQ_URL"
echo -e "  MARKET_DATA_API_URL: $MARKET_DATA_API_URL"
echo -e "  STRATEGY_API_URL: $STRATEGY_API_URL"
echo -e "  RISK_MANAGER_API_URL: $RISK_MANAGER_API_URL"
echo ""

# Check if pytest is installed
if ! command -v pytest &> /dev/null; then
    echo -e "${RED}✗ pytest not found${NC}"
    echo -e "${YELLOW}Installing test dependencies...${NC}"
    pip install -r "$PROJECT_ROOT/requirements-test.txt"
    echo ""
fi

# Parse command line arguments
TEST_PATTERN="${1:-}"
VERBOSE="${2:--v}"

if [ -z "$TEST_PATTERN" ]; then
    echo -e "${BLUE}Running all E2E tests...${NC}"
    TEST_PATH="$SCRIPT_DIR"
else
    echo -e "${BLUE}Running tests matching: $TEST_PATTERN${NC}"
    TEST_PATH="$SCRIPT_DIR/$TEST_PATTERN"
fi

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}   Test Execution${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Run pytest
cd "$PROJECT_ROOT"
pytest "$TEST_PATH" $VERBOSE \
    --tb=short \
    --color=yes \
    --durations=10 \
    --timeout=120 \
    --maxfail=5 \
    | tee /tmp/e2e_test_results.log

# Capture exit code
TEST_EXIT_CODE=${PIPESTATUS[0]}

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}   Test Summary${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

if [ $TEST_EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}✓✓✓ All tests PASSED${NC}"
    echo ""
    echo -e "${GREEN}Test suite completed successfully!${NC}"
else
    echo -e "${RED}✗✗✗ Some tests FAILED${NC}"
    echo ""
    echo -e "${RED}Check output above for details.${NC}"
    echo -e "${YELLOW}Log saved to: /tmp/e2e_test_results.log${NC}"
fi

echo ""
echo -e "${BLUE}Test Statistics:${NC}"
grep -E "passed|failed|error|skipped" /tmp/e2e_test_results.log | tail -1 || echo "No statistics available"

echo ""
echo -e "${BLUE}Slowest Tests:${NC}"
grep -A 10 "slowest durations" /tmp/e2e_test_results.log || echo "No duration data available"

echo ""
echo -e "${BLUE}========================================${NC}"

exit $TEST_EXIT_CODE
