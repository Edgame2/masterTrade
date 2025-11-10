#!/bin/bash

# Macro-Economic Data Collection Startup Script
# This script starts the macro-economic data scheduler service

echo "=========================================="
echo "Macro-Economic Data Scheduler Service"
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

# Check for optional API keys
if [ -z "$FRED_API_KEY" ]; then
    echo "INFO: FRED_API_KEY not set (optional)"
    echo "  To enable FRED economic indicators:"
    echo "  export FRED_API_KEY=<your-fred-api-key>"
fi

if [ -z "$ALPHA_VANTAGE_API_KEY" ]; then
    echo "INFO: ALPHA_VANTAGE_API_KEY not set (optional)"
    echo "  For additional economic data:"
    echo "  export ALPHA_VANTAGE_API_KEY=<your-alpha-vantage-key>"
fi

# Start the macro-economic scheduler
echo ""
echo "Starting Macro-Economic Data Scheduler..."
echo "  Data Sources:"
echo "    - Yahoo Finance: Commodities, Currencies, Treasury Yields"
echo "    - FRED API: Interest Rates, Inflation, GDP, Employment"
echo "    - Alternative.me: Crypto Fear & Greed Index"
echo ""
echo "  Schedule:"
echo "    - Commodities: Every 15 min (market hours) / hourly (off-hours)"
echo "    - Currencies: Every 15 minutes"
echo "    - Treasury Yields: Daily at 21:00 UTC"
echo "    - FRED Indicators: Daily at 08:00 UTC"
echo "    - Fear & Greed: Every 6 hours"
echo "    - Macro Summary: Every hour"
echo ""
echo "Press Ctrl+C to stop"
echo ""

python macro_economic_scheduler.py
