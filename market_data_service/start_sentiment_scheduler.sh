#!/bin/bash

# Sentiment Analysis Scheduler Startup Script

echo "=========================================="
echo "Sentiment Analysis Scheduler Service"
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

# Download NLTK data if needed
echo "Downloading NLTK data..."
python -c "import nltk; nltk.download('punkt', quiet=True); nltk.download('averaged_perceptron_tagger', quiet=True)"

# Check for required environment variables
if [ -z "$COSMOS_ENDPOINT" ]; then
    echo "WARNING: COSMOS_ENDPOINT not set!"
    echo "Please set Azure Cosmos DB environment variables:"
    echo "  export COSMOS_ENDPOINT=<your-cosmos-endpoint>"
    echo "  export COSMOS_KEY=<your-cosmos-key>"
    echo "  export COSMOS_DATABASE_NAME=<your-database-name>"
fi

# Check for optional API keys
echo ""
echo "Checking API configurations..."

if [ -z "$REDDIT_CLIENT_ID" ]; then
    echo "INFO: REDDIT_CLIENT_ID not set (optional)"
    echo "  To enable Reddit sentiment:"
    echo "  export REDDIT_CLIENT_ID=<your-client-id>"
    echo "  export REDDIT_CLIENT_SECRET=<your-client-secret>"
    echo "  export REDDIT_USER_AGENT='YourApp/1.0'"
else
    echo "✓ Reddit API configured"
fi

if [ -z "$TWITTER_BEARER_TOKEN" ]; then
    echo "INFO: TWITTER_BEARER_TOKEN not set (optional)"
    echo "  To enable Twitter sentiment:"
    echo "  export TWITTER_BEARER_TOKEN=<your-token>"
else
    echo "✓ Twitter API configured"
fi

if [ -z "$NEWS_API_KEY" ]; then
    echo "INFO: NEWS_API_KEY not set (optional)"
    echo "  To enable news sentiment:"
    echo "  export NEWS_API_KEY=<your-key>"
else
    echo "✓ News API configured"
fi

# Start the sentiment scheduler
echo ""
echo "Starting Sentiment Analysis Scheduler..."
echo "  Data Sources:"
echo "    - Reddit: Multiple crypto subreddits"
echo "    - Twitter: Real-time mentions (if configured)"
echo "    - News: NewsAPI.org (if configured)"
echo "    - Fear & Greed Index: alternative.me"
echo ""
echo "  Schedule:"
echo "    - Reddit: Every 2 hours"
echo "    - News: Every hour"
echo "    - Twitter: Every 30 minutes (if configured)"
echo "    - Fear & Greed: Every 6 hours"
echo "    - Aggregation: Every 30 minutes"
echo ""
echo "Press Ctrl+C to stop"
echo ""

python sentiment_scheduler.py
