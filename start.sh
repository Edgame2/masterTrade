#!/bin/bash

# MasterTrade - Quick Start Script

echo "🚀 Starting MasterTrade Crypto Trading Bot..."

# Check if .env exists
if [ ! -f .env ]; then
    echo "⚙️  Copying environment template..."
    cp .env.example .env
    echo "📝 Please edit .env file with your API keys and configurations"
    echo "   - Add your Binance API keys"
    echo "   - Set secure passwords"
    echo "   - Configure trading parameters"
    echo ""
    read -p "Press Enter to continue after updating .env file..."
fi

# Create data directories
echo "📁 Creating data directories..."
mkdir -p data/rabbitmq
mkdir -p data/prometheus
mkdir -p data/grafana

# Build and start services
echo "🏗️  Building Docker containers..."
docker compose build

echo "🐳 Starting message queue..."
docker compose up -d rabbitmq

echo "⏳ Waiting for message queue to be ready..."
sleep 20

echo "🔄 Starting application services..."
docker compose up -d

echo ""
echo "✅ MasterTrade is starting up!"
echo ""
echo "📊 Access your dashboards:"
echo "   • Management UI:    http://localhost:3000"
echo "   • Grafana:         http://localhost:3001 (admin/grafana_secure_password)"
echo "   • RabbitMQ:        http://localhost:15672 (mastertrade/rabbitmq_secure_password)"
echo "   • Prometheus:      http://localhost:9090"
echo ""
echo "🔍 Check service status:"
echo "   docker compose ps"
echo ""
echo "📋 View logs:"
echo "   docker compose logs -f [service_name]"
echo ""
echo "⚠️  Remember to:"
echo "   • Verify PostgreSQL connection in .env"
echo "   • Set up your exchange API keys"
echo "   • Start with sandbox/testnet mode"
echo "   • Monitor risk settings carefully"
echo ""