#!/bin/bash

# MasterTrade - System Stop Script
# Stops all MasterTrade services

echo "⏹  Stopping MasterTrade System..."
echo "=================================="
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Function to kill process on port
kill_port() {
    local port=$1
    local name=$2
    if lsof -ti:$port >/dev/null 2>&1; then
        echo -e "${YELLOW}⏹  Stopping $name (port $port)...${NC}"
        lsof -ti:$port | xargs kill -9 2>/dev/null || true
        sleep 1
        echo -e "${GREEN}✓ Stopped${NC}"
    else
        echo -e "  $name (port $port) - not running"
    fi
}

# Stop all services
kill_port 8000 "Market Data Service"
kill_port 8001 "Strategy Service"
kill_port 8081 "Order Executor"
kill_port 8090 "API Gateway"
kill_port 3000 "Frontend UI"

# Kill any remaining processes
echo ""
echo "🧹 Cleaning up remaining processes..."
pkill -f "market_data_service.*main.py" 2>/dev/null || true
pkill -f "strategy_service.*main.py" 2>/dev/null || true
pkill -f "order_executor.*main.py" 2>/dev/null || true
pkill -f "api_gateway.*main.py" 2>/dev/null || true
pkill -f "next dev" 2>/dev/null || true
pkill -f "monitoring-ui" 2>/dev/null || true

# Kill any frontend on alternate ports (3001-3010)
for port in {3001..3010}; do
    lsof -ti:$port 2>/dev/null | xargs kill -9 2>/dev/null || true
done

echo ""
echo -e "${GREEN}✅ All services stopped${NC}"
echo ""
