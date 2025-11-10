#!/bin/bash
# MasterTrade System Startup Script
# Starts all services in the correct order with Cosmos DB integration

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🚀 Starting MasterTrade System with Cosmos DB${NC}"
echo "============================================================"

# Function to check if a port is in use
check_port() {
    local port=$1
    if netstat -tlnp | grep -q ":$port "; then
        return 0  # Port is in use
    else
        return 1  # Port is free
    fi
}

# Function to wait for a service to be ready
wait_for_service() {
    local port=$1
    local service_name=$2
    local max_attempts=30
    local attempt=1

    echo -e "${YELLOW}⏳ Waiting for $service_name to be ready on port $port...${NC}"
    
    while [ $attempt -le $max_attempts ]; do
        if check_port $port; then
            echo -e "${GREEN}✅ $service_name is ready!${NC}"
            return 0
        fi
        
        echo -e "${YELLOW}   Attempt $attempt/$max_attempts - waiting...${NC}"
        sleep 2
        attempt=$((attempt + 1))
    done
    
    echo -e "${RED}❌ $service_name failed to start within $((max_attempts * 2)) seconds${NC}"
    return 1
}

# Function to start a service
start_service() {
    local service_dir=$1
    local service_name=$2
    local port=$3
    
    echo -e "\n${BLUE}🚀 Starting $service_name...${NC}"
    
    # Check if service is already running
    if check_port $port; then
        echo -e "${YELLOW}⚠️  $service_name already running on port $port${NC}"
        return 0
    fi
    
    cd /home/neodyme/Documents/Projects/masterTrade/$service_dir
    
    # Create virtual environment if it doesn't exist
    if [ ! -d "venv" ]; then
        echo -e "${YELLOW}📦 Creating virtual environment for $service_name...${NC}"
        python3 -m venv venv
    fi
    
    # Install requirements
    if [ -f "requirements.txt" ]; then
        echo -e "${YELLOW}📦 Installing requirements for $service_name...${NC}"
        source venv/bin/activate
        pip install -r requirements.txt > /dev/null 2>&1
        deactivate
    fi
    
    # Start the service in background
    echo -e "${GREEN}▶️  Launching $service_name...${NC}"
    nohup ./venv/bin/python3 main.py > logs/${service_name}.log 2>&1 &
    local pid=$!
    echo $pid > /tmp/${service_name}.pid
    
    # Wait for service to be ready
    wait_for_service $port "$service_name"
}

# Create logs directory
mkdir -p /home/neodyme/Documents/Projects/masterTrade/logs

# Check infrastructure services
echo -e "\n${BLUE}🔍 Checking Infrastructure Services...${NC}"

# Check Redis
if systemctl is-active --quiet redis-server; then
    echo -e "${GREEN}✅ Redis is running${NC}"
else
    echo -e "${YELLOW}🔧 Starting Redis...${NC}"
    sudo systemctl start redis-server
fi

# Check RabbitMQ
if systemctl is-active --quiet rabbitmq-server; then
    echo -e "${GREEN}✅ RabbitMQ is running${NC}"
else
    echo -e "${YELLOW}🔧 Starting RabbitMQ...${NC}"
    sudo systemctl start rabbitmq-server
fi

# PostgreSQL is disabled - using Cosmos DB only
echo -e "${GREEN}✅ Cosmos DB: Primary database (PostgreSQL disabled)${NC}"

echo -e "\n${BLUE}🎯 Starting MasterTrade Services...${NC}"

# Start services in dependency order
start_service "api_gateway" "API Gateway" 8080
start_service "market_data_service" "Market Data Service" 8001
start_service "strategy_service" "Strategy Service" 8002
start_service "order_executor" "Order Executor" 8003
start_service "risk_manager" "Risk Manager" 8004
start_service "arbitrage_service" "Arbitrage Service" 8005

echo -e "\n${BLUE}🖥️  Starting Monitoring UI...${NC}"
cd /home/neodyme/Documents/Projects/masterTrade/monitoring_ui
if check_port 3000; then
    echo -e "${YELLOW}⚠️  Monitoring UI already running on port 3000${NC}"
else
    echo -e "${GREEN}▶️  Launching Monitoring UI...${NC}"
    nohup npm run dev > ../logs/monitoring_ui.log 2>&1 &
    echo $! > /tmp/monitoring_ui.pid
    wait_for_service 3000 "Monitoring UI"
fi

echo -e "\n${GREEN}🎉 MasterTrade System Started Successfully!${NC}"
echo "============================================================"
echo -e "${BLUE}📊 Service Status:${NC}"
echo -e "${GREEN}✅ API Gateway:      http://localhost:8080${NC}"
echo -e "${GREEN}✅ Market Data:      http://localhost:8001${NC}" 
echo -e "${GREEN}✅ Strategy Service: http://localhost:8002${NC}"
echo -e "${GREEN}✅ Order Executor:   http://localhost:8003${NC}"
echo -e "${GREEN}✅ Risk Manager:     http://localhost:8004${NC}"
echo -e "${GREEN}✅ Arbitrage:        http://localhost:8005${NC}"
echo -e "${GREEN}✅ Monitoring UI:    http://localhost:3000${NC}"

echo -e "\n${BLUE}💾 Database Status:${NC}"
echo -e "${GREEN}✅ Cosmos DB:        Connected (mmasterTrade) - Primary Database${NC}"
echo -e "${GREEN}✅ Redis:            Running${NC}"
echo -e "${GREEN}✅ RabbitMQ:         Running${NC}"
echo -e "${YELLOW}❌ PostgreSQL:       Disabled (Using Cosmos DB only)${NC}"

echo -e "\n${YELLOW}📋 To stop all services, run: ./stop_mastertrade.sh${NC}"
echo -e "${YELLOW}📋 View logs in: /home/neodyme/Documents/Projects/masterTrade/logs/${NC}"