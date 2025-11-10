#!/bin/bash

# MasterTrade - System Restart Script
# Stops and restarts all MasterTrade services

set -e  # Exit on error

echo "🔄 Restarting MasterTrade System..."
echo "=================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Base directory
BASE_DIR="/home/neodyme/Documents/Projects/masterTrade"
cd "$BASE_DIR"

# Function to check if a port is in use
port_in_use() {
    lsof -ti:$1 >/dev/null 2>&1
}

# Function to kill process on port
kill_port() {
    local port=$1
    local name=$2
    if port_in_use $port; then
        echo -e "${YELLOW}⏹  Stopping $name (port $port)...${NC}"
        lsof -ti:$port | xargs kill -9 2>/dev/null || true
        sleep 1
    fi
}

# Step 1: Stop all services
echo "⏹  Stopping all services..."
echo "----------------------------"

# Stop Python services
kill_port 8000 "Market Data Service"
kill_port 8001 "Strategy Service"
kill_port 8081 "Order Executor"
kill_port 8090 "API Gateway"

# Stop Frontend
kill_port 3000 "Frontend UI"

# Kill any remaining Python services
pkill -f "market_data_service.*main.py" 2>/dev/null || true
pkill -f "strategy_service.*main.py" 2>/dev/null || true
pkill -f "order_executor.*main.py" 2>/dev/null || true
pkill -f "api_gateway.*main.py" 2>/dev/null || true

echo -e "${GREEN}✓ All services stopped${NC}"
echo ""
sleep 2

# Step 2: Start services in correct order
echo "🚀 Starting services..."
echo "----------------------------"

# Start Market Data Service
echo -e "${YELLOW}▶ Starting Market Data Service...${NC}"
cd "$BASE_DIR/market_data_service"
if [ ! -d "venv" ]; then
    echo -e "${RED}⚠ Virtual environment not found for Market Data Service${NC}"
else
    # Use main.py for Cosmos DB support
    RABBITMQ_URL="amqp://guest:guest@localhost:5672/" nohup ./venv/bin/python main.py > /tmp/market_data.log 2>&1 &
    sleep 5
    if port_in_use 8000; then
        echo -e "${GREEN}✓ Market Data Service started on port 8000${NC}"
    else
        echo -e "${YELLOW}⚠ Market Data Service is starting (check logs)${NC}"
    fi
fi

# Start Strategy Service
echo -e "${YELLOW}▶ Starting Strategy Service...${NC}"
cd "$BASE_DIR/strategy_service"
if [ ! -d "venv" ]; then
    echo -e "${RED}⚠ Virtual environment not found for Strategy Service${NC}"
else
    # Use complete_main.py if available, otherwise main.py
    if [ -f "complete_main.py" ]; then
        RABBITMQ_URL="amqp://guest:guest@localhost:5672/" nohup ./venv/bin/python complete_main.py > /tmp/strategy_service.log 2>&1 &
    else
        RABBITMQ_URL="amqp://guest:guest@localhost:5672/" nohup ./venv/bin/python main.py > /tmp/strategy_service.log 2>&1 &
    fi
    sleep 5
    if port_in_use 8001; then
        echo -e "${GREEN}✓ Strategy Service started on port 8001${NC}"
    else
        echo -e "${YELLOW}⚠ Strategy Service is starting (check logs)${NC}"
    fi
fi

# Start Order Executor
echo -e "${YELLOW}▶ Starting Order Executor...${NC}"
cd "$BASE_DIR/order_executor"
if [ ! -d "venv" ]; then
    echo -e "${RED}⚠ Virtual environment not found for Order Executor${NC}"
else
    # Use simple_main.py if available, otherwise main.py
    if [ -f "simple_main.py" ]; then
        RABBITMQ_URL="amqp://guest:guest@localhost:5672/" nohup ./venv/bin/python simple_main.py > /tmp/order_executor.log 2>&1 &
    else
        RABBITMQ_URL="amqp://guest:guest@localhost:5672/" nohup ./venv/bin/python main.py > /tmp/order_executor.log 2>&1 &
    fi
    sleep 5
    if port_in_use 8081; then
        echo -e "${GREEN}✓ Order Executor started on port 8081${NC}"
    else
        echo -e "${YELLOW}⚠ Order Executor is starting (check logs)${NC}"
    fi
fi

# Start API Gateway (with mock database for now)
echo -e "${YELLOW}▶ Starting API Gateway...${NC}"
cd "$BASE_DIR/api_gateway"
if [ ! -d "venv" ]; then
    echo -e "${RED}⚠ Virtual environment not found for API Gateway${NC}"
else
    USE_MOCK_DATABASE=true nohup ./venv/bin/python main.py > /tmp/api_gateway.log 2>&1 &
    sleep 3
    if port_in_use 8090; then
        echo -e "${GREEN}✓ API Gateway started on port 8090${NC}"
    else
        echo -e "${RED}✗ Failed to start API Gateway${NC}"
    fi
fi

# Start Frontend UI (if not already running)
echo -e "${YELLOW}▶ Starting Frontend UI...${NC}"
cd "$BASE_DIR/monitoring_ui"
if ! port_in_use 3000; then
    if [ -d "node_modules" ]; then
        nohup npm run dev > /tmp/frontend.log 2>&1 &
        sleep 5
        if port_in_use 3000; then
            echo -e "${GREEN}✓ Frontend UI started on port 3000${NC}"
        else
            echo -e "${RED}✗ Failed to start Frontend UI${NC}"
        fi
    else
        echo -e "${RED}⚠ node_modules not found. Run 'npm install' first${NC}"
    fi
else
    echo -e "${GREEN}✓ Frontend UI already running on port 3000${NC}"
fi

echo ""
echo "=================================="
echo "🎉 System Restart Complete!"
echo "=================================="
echo ""

# Step 3: Health check
echo "🏥 Health Check:"
echo "----------------------------"

sleep 2

check_service() {
    local name=$1
    local url=$2
    if curl -s "$url" > /dev/null 2>&1; then
        echo -e "${GREEN}✓${NC} $name"
    else
        echo -e "${RED}✗${NC} $name"
    fi
}

check_service "Market Data Service (8000)" "http://localhost:8000/health"
check_service "Strategy Service (8001)" "http://localhost:8001/health"
check_service "Order Executor (8081)" "http://localhost:8081/health"
check_service "API Gateway (8090)" "http://localhost:8090/health"
check_service "Frontend UI (3000)" "http://localhost:3000"

echo ""
echo "📊 Access Points:"
echo "   • Management UI:    http://localhost:3000"
echo "   • API Gateway:      http://localhost:8090"
echo "   • Market Data:      http://localhost:8000"
echo "   • Strategy Service: http://localhost:8001"
echo "   • Order Executor:   http://localhost:8081"
echo ""
echo "📋 View Logs:"
echo "   tail -f /tmp/market_data.log"
echo "   tail -f /tmp/strategy_service.log"
echo "   tail -f /tmp/order_executor.log"
echo "   tail -f /tmp/api_gateway.log"
echo "   tail -f /tmp/frontend.log"
echo ""
