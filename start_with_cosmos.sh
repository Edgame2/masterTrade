#!/bin/bash

# masterTrade System Startup with Azure Cosmos DB
# This script tests and starts all services with Cosmos DB configuration

echo "🚀 Starting masterTrade System with Azure Cosmos DB..."

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "❌ Error: .env file not found. Please copy .env.example and configure it."
    exit 1
fi

# Source environment variables
source .env

# Function to check if required environment variables are set
check_cosmos_config() {
    echo "🔍 Checking Azure Cosmos DB configuration..."
    
    if [ -z "$COSMOS_ENDPOINT" ]; then
        echo "⚠️  Warning: COSMOS_ENDPOINT not set. Using fallback mode."
        return 1
    fi
    
    if [ -z "$COSMOS_KEY" ] && [ -z "$AZURE_CLIENT_ID" ]; then
        echo "⚠️  Warning: Neither COSMOS_KEY nor Azure credentials set. Using fallback mode."
        return 1
    fi
    
    echo "✅ Cosmos DB configuration found"
    return 0
}

# Function to check and start a service
start_service() {
    local service_name=$1
    local service_path=$2
    local port=$3
    
    echo "🔧 Starting $service_name..."
    
    cd "$service_path"
    
    # Check if virtual environment exists
    if [ ! -d "venv" ]; then
        echo "📦 Creating virtual environment for $service_name..."
        python3 -m venv venv
    fi
    
    # Activate virtual environment
    source venv/bin/activate
    
    # Install dependencies if requirements.txt exists
    if [ -f "requirements.txt" ]; then
        echo "📦 Installing dependencies for $service_name..."
        pip install -r requirements.txt > /dev/null 2>&1
    fi
    
    # Check if main.py exists
    if [ -f "main.py" ]; then
        echo "✅ Starting $service_name on port $port"
        python3 main.py &
        echo $! > "../.$service_name.pid"
    else
        echo "⚠️  main.py not found for $service_name"
    fi
    
    cd - > /dev/null
}

# Function to start monitoring UI
start_monitoring_ui() {
    echo "🖥️  Starting Monitoring UI..."
    cd monitoring_ui
    
    # Install dependencies if needed
    if [ ! -d "node_modules" ]; then
        echo "📦 Installing Node.js dependencies..."
        npm install > /dev/null 2>&1
    fi
    
    # Start in development mode
    echo "✅ Starting Monitoring UI on port 3000"
    npm run dev &
    echo $! > "../.monitoring_ui.pid"
    
    cd - > /dev/null
}

# Function to check service health
check_service_health() {
    local service_name=$1
    local port=$2
    local max_attempts=30
    local attempt=1
    
    echo "🏥 Checking $service_name health..."
    
    while [ $attempt -le $max_attempts ]; do
        if curl -s "http://localhost:$port/health" > /dev/null 2>&1; then
            echo "✅ $service_name is healthy"
            return 0
        fi
        
        if [ $((attempt % 5)) -eq 0 ]; then
            echo "⏳ Waiting for $service_name... (attempt $attempt/$max_attempts)"
        fi
        
        sleep 2
        attempt=$((attempt + 1))
    done
    
    echo "⚠️  $service_name health check timeout"
    return 1
}

# Main execution
main() {
    echo "════════════════════════════════════════════════════════════════"
    echo "🎯 masterTrade System Startup with Azure Cosmos DB"
    echo "════════════════════════════════════════════════════════════════"
    
    # Check Cosmos DB configuration
    check_cosmos_config
    cosmos_configured=$?
    
    # Start Redis if not running
    if ! pgrep redis-server > /dev/null; then
        echo "🔄 Starting Redis..."
        sudo systemctl start redis-server
    else
        echo "✅ Redis is already running"
    fi
    
    # Start RabbitMQ if not running
    if ! pgrep rabbitmq > /dev/null; then
        echo "🔄 Starting RabbitMQ..."
        sudo systemctl start rabbitmq-server
    else
        echo "✅ RabbitMQ is already running"
    fi
    
    # Start core services
    start_service "API Gateway" "api_gateway" "8080"
    start_service "Market Data Service" "market_data_service" "8005"
    start_service "Strategy Service" "strategy_service" "8001"
    
    # Start monitoring UI
    start_monitoring_ui
    
    echo ""
    echo "⏳ Waiting for services to start..."
    sleep 10
    
    echo ""
    echo "════════════════════════════════════════════════════════════════"
    echo "📊 System Status"
    echo "════════════════════════════════════════════════════════════════"
    
    # Check Redis
    if redis-cli ping > /dev/null 2>&1; then
        echo "✅ Redis: Running"
    else
        echo "❌ Redis: Not responding"
    fi
    
    # Check services
    services=("API Gateway:8080" "Market Data:8005" "Strategy Service:8001")
    for service_info in "${services[@]}"; do
        IFS=':' read -r name port <<< "$service_info"
        if netstat -tlnp 2>/dev/null | grep ":$port " > /dev/null; then
            echo "✅ $name: Running on port $port"
        else
            echo "⚠️  $name: Not detected on port $port"
        fi
    done
    
    # Check monitoring UI
    if netstat -tlnp 2>/dev/null | grep ":3000 " > /dev/null; then
        echo "✅ Monitoring UI: Running on port 3000"
    else
        echo "⚠️  Monitoring UI: Not detected on port 3000"
    fi
    
    echo ""
    echo "════════════════════════════════════════════════════════════════"
    echo "🌐 Access URLs"
    echo "════════════════════════════════════════════════════════════════"
    echo "📱 Monitoring Dashboard: http://localhost:3000"
    echo "🔌 API Gateway: http://localhost:8080"
    echo "📊 Market Data API: http://localhost:8005"
    echo "🤖 Strategy Service: http://localhost:8001"
    echo "🏥 Health Check: http://localhost:3000/api/health"
    echo ""
    
    if [ $cosmos_configured -eq 0 ]; then
        echo "✅ System started with Azure Cosmos DB integration"
    else
        echo "⚠️  System started in fallback mode (mock data)"
        echo "📝 See COSMOS_DB_SETUP.md for configuration instructions"
    fi
    
    echo ""
    echo "🎉 masterTrade system is ready!"
    echo "Press Ctrl+C to stop all services"
    
    # Wait for interrupt
    trap 'cleanup' INT
    wait
}

# Cleanup function
cleanup() {
    echo ""
    echo "🛑 Stopping masterTrade services..."
    
    # Kill services using PID files
    for pid_file in .*.pid; do
        if [ -f "$pid_file" ]; then
            pid=$(cat "$pid_file")
            if kill -0 "$pid" 2>/dev/null; then
                kill "$pid"
                echo "✅ Stopped $(basename "$pid_file" .pid)"
            fi
            rm -f "$pid_file"
        fi
    done
    
    echo "👋 masterTrade system stopped"
    exit 0
}

# Run main function
main