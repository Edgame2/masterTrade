#!/bin/bash

# Stock Index Data Collection and Correlation Analysis Startup Script
# This script starts the stock index scheduler service

echo "=========================================="
echo "Stock Index Scheduler Service"
echo "=========================================="
echo ""

# Set the directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install/Update dependencies
echo "Installing dependencies..."
pip install -r requirements.txt

# Check for required environment variables
if [ -z "$COSMOS_ENDPOINT" ]; then
    echo "WARNING: COSMOS_ENDPOINT not set!"
    echo "Please set Azure Cosmos DB environment variables:"
    echo "  export COSMOS_ENDPOINT=<your-cosmos-endpoint>"
    echo "  export COSMOS_KEY=<your-cosmos-key>"
    echo "  export COSMOS_DATABASE_NAME=<your-database-name>"
fi

# Start the stock index scheduler
echo ""
echo "Starting Stock Index Scheduler..."
echo "  - Data collection: Every 15 minutes (market hours)"
echo "  - Correlation analysis: Every hour"
echo "  - Market regime detection: Every 30 minutes"
echo "  - Historical backfill: Daily at 2 AM UTC"
echo ""
echo "Press Ctrl+C to stop"
echo ""

python stock_index_scheduler.py
