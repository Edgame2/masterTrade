#!/bin/bash

# MasterTrade - System Status Check
# Shows the status of all services

echo "📊 MasterTrade System Status"
echo "=================================="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Function to check service
check_service() {
    local name=$1
    local port=$2
    local health_url=$3
    
    if lsof -ti:$port >/dev/null 2>&1; then
        if [ ! -z "$health_url" ] && curl -s "$health_url" > /dev/null 2>&1; then
            echo -e "${GREEN}✓ RUNNING${NC}  $name (port $port)"
        else
            echo -e "${YELLOW}⚠ STARTING${NC} $name (port $port)"
        fi
    else
        echo -e "${RED}✗ STOPPED${NC}  $name (port $port)"
    fi
}

echo "Services:"
echo "----------"
check_service "Market Data Service" 8000 "http://localhost:8000/health"
check_service "Strategy Service   " 8001 "http://localhost:8001/health"
check_service "Order Executor     " 8081 "http://localhost:8081/health"
check_service "API Gateway        " 8090 "http://localhost:8090/health"
check_service "Frontend UI        " 3000 "http://localhost:3000"

echo ""
echo "Process Details:"
echo "----------------"
ps aux | grep -E "(main\.py|next-server)" | grep -v grep | awk '{printf "PID: %-7s CPU: %-5s MEM: %-5s CMD: %s\n", $2, $3"%", $4"%", $11}'

echo ""
echo "API Endpoints:"
echo "--------------"
echo "• Management UI:    http://localhost:3000"
echo "• API Gateway:      http://localhost:8090"
echo "• Market Data API:  http://localhost:8000"
echo "• Strategy API:     http://localhost:8001"
echo "• Order Executor:   http://localhost:8081"

echo ""
echo "Log Files:"
echo "----------"
echo "• Market Data:      /tmp/market_data.log"
echo "• Strategy Service: /tmp/strategy_service.log"
echo "• Order Executor:   /tmp/order_executor.log"
echo "• API Gateway:      /tmp/api_gateway.log"
echo "• Frontend:         /tmp/frontend.log"

echo ""
echo "Quick Commands:"
echo "---------------"
echo "• Start all:   ./restart.sh"
echo "• Stop all:    ./stop.sh"
echo "• View logs:   tail -f /tmp/[service].log"
echo ""
