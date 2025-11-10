#!/bin/bash

# Historical Data Collection Script
# Collects comprehensive historical data for backtesting

set -e

echo "🚀 MasterTrade - Historical Data Collection"
echo "============================================"
echo ""

# Configuration
SYMBOLS="${SYMBOLS:-BTCUSDC ETHUSDC ADAUSDC SOLUSDC DOTUSDC LINKUSDC AVAXUSDC MATICUSDC}"
TIMEFRAMES="${TIMEFRAMES:-1m 5m 15m 30m 1h 4h 1d}"
DAYS="${DAYS:-365}"
PARALLEL_SYMBOLS="${PARALLEL_SYMBOLS:-3}"
PARALLEL_TIMEFRAMES="${PARALLEL_TIMEFRAMES:-2}"
EXPORT_DIR="${EXPORT_DIR:-./historical_data_export}"

echo "Configuration:"
echo "  Symbols: $SYMBOLS"
echo "  Timeframes: $TIMEFRAMES"
echo "  Days back: $DAYS"
echo "  Parallel symbols: $PARALLEL_SYMBOLS"
echo "  Parallel timeframes: $PARALLEL_TIMEFRAMES"
echo ""

# Navigate to market_data_service directory
cd "$(dirname "$0")/market_data_service"

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install/update dependencies
echo "📦 Installing dependencies..."
pip install -q --upgrade pip
pip install -q -r requirements.txt

echo ""
echo "🔄 Starting historical data collection..."
echo "This may take several hours depending on the number of symbols and timeframes."
echo ""

# Run the enhanced historical collector
python enhanced_historical_collector.py \
    --symbols $SYMBOLS \
    --timeframes $TIMEFRAMES \
    --days $DAYS \
    --parallel-symbols $PARALLEL_SYMBOLS \
    --parallel-timeframes $PARALLEL_TIMEFRAMES \
    --export $EXPORT_DIR

echo ""
echo "✅ Historical data collection completed!"
echo ""
echo "Data exported to: $EXPORT_DIR"
echo ""
echo "You can now use this data for:"
echo "  - Backtesting strategies"
echo "  - Training ML models"
echo "  - Statistical analysis"
echo ""
