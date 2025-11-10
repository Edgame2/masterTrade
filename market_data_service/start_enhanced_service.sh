#!/bin/bash

# Enhanced Market Data Service Startup Script
# This script starts the market data service with all enhanced features

echo "🚀 Starting Enhanced Market Data Service..."
echo "Features: Historical Data + Real-time Streaming + Sentiment Analysis"

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install/upgrade dependencies
echo "📦 Installing dependencies..."
pip install -r requirements.txt

# Download NLTK data for sentiment analysis
echo "📚 Downloading NLTK data for sentiment analysis..."
python -c "import nltk; nltk.download('punkt'); nltk.download('vader_lexicon'); nltk.download('brown')"

# Check environment variables
echo "🔧 Checking configuration..."
if [ ! -f "../.env" ]; then
    echo "⚠️  Warning: .env file not found. Copy .env.example to .env and configure it."
    echo "Required: COSMOS_ENDPOINT, COSMOS_DATABASE, MANAGED_IDENTITY_CLIENT_ID"
fi

# Start the service
echo "🎯 Starting Enhanced Market Data Service..."
echo "Components starting:"
echo "  • Historical Data Collector"
echo "  • Real-time WebSocket Streams (Binance)"
echo "  • Sentiment Analysis Engine"
echo "  • Azure Cosmos DB Storage"
echo "  • Data Access API (port 8005)"
echo "  • Prometheus Metrics (port 8001)"

# Run with Python
python main.py