#!/bin/bash

# Initialize Cosmos DB container for Crypto Selection System
# This script ensures the crypto_selections container exists

# Database configuration
DB_NAME="mastertrade"
COSMOS_ENDPOINT=${COSMOS_ENDPOINT:-""}
COSMOS_KEY=${COSMOS_KEY:-""}

if [ -z "$COSMOS_ENDPOINT" ] || [ -z "$COSMOS_KEY" ]; then
    echo "Error: COSMOS_ENDPOINT and COSMOS_KEY environment variables must be set"
    exit 1
fi

echo "Initializing Crypto Selection System containers..."

# Container configurations
declare -A CONTAINERS
CONTAINERS[crypto_selections]="/selection_date"
CONTAINERS[crypto_analysis_cache]="/symbol"
CONTAINERS[crypto_market_metrics]="/date"

# Function to create container if it doesn't exist
create_container() {
    local container_name=$1
    local partition_key=$2
    
    echo "Creating container: $container_name with partition key: $partition_key"
    
    az cosmosdb sql container create \
        --account-name $(echo $COSMOS_ENDPOINT | sed 's/https:\/\///g' | sed 's/\..*//g') \
        --database-name $DB_NAME \
        --name $container_name \
        --partition-key-path $partition_key \
        --throughput 400 \
        --output table 2>/dev/null || echo "Container $container_name already exists or created successfully"
}

# Create all containers
for container in "${!CONTAINERS[@]}"; do
    create_container "$container" "${CONTAINERS[$container]}"
done

# Initialize default crypto selection settings
echo ""
echo "Initializing crypto selection settings..."

# Create initial configuration if needed
python3 << EOF
import asyncio
import os
from datetime import datetime, timezone
from azure.cosmos import CosmosClient

async def initialize_crypto_settings():
    try:
        # Connect to Cosmos DB
        endpoint = os.getenv('COSMOS_ENDPOINT')
        key = os.getenv('COSMOS_KEY')
        
        client = CosmosClient(endpoint, key)
        database = client.get_database_client('$DB_NAME')
        
        # Initialize settings container if needed
        try:
            settings_container = database.get_container_client('settings')
        except Exception:
            print("Settings container not found, skipping crypto settings initialization")
            return
        
        # Default crypto selection settings
        crypto_settings = [
            {
                'id': 'DAILY_CRYPTO_COUNT',
                'key': 'DAILY_CRYPTO_COUNT',
                'value': '10',
                'description': 'Number of cryptocurrencies to select daily for trading',
                'type': 'integer'
            },
            {
                'id': 'MIN_MARKET_CAP',
                'key': 'MIN_MARKET_CAP',
                'value': '100000000',
                'description': 'Minimum market cap (USD) for crypto selection',
                'type': 'float'
            },
            {
                'id': 'MIN_DAILY_VOLUME',
                'key': 'MIN_DAILY_VOLUME', 
                'value': '10000000',
                'description': 'Minimum daily volume (USD) for crypto selection',
                'type': 'float'
            },
            {
                'id': 'EXCLUDE_STABLECOINS',
                'key': 'EXCLUDE_STABLECOINS',
                'value': 'true',
                'description': 'Whether to exclude stablecoins from selection',
                'type': 'boolean'
            }
        ]
        
        for setting in crypto_settings:
            try:
                # Check if setting already exists
                existing = settings_container.read_item(
                    item=setting['id'],
                    partition_key=setting['key']
                )
                print(f"Setting {setting['key']} already exists with value: {existing.get('value')}")
                
            except Exception:
                # Setting doesn't exist, create it
                setting['created_at'] = datetime.now(timezone.utc).isoformat()
                setting['updated_at'] = datetime.now(timezone.utc).isoformat()
                
                settings_container.create_item(setting)
                print(f"Created {setting['key']} setting with value: {setting['value']}")
            
    except Exception as e:
        print(f"Error initializing crypto settings: {e}")

# Run the initialization
asyncio.run(initialize_crypto_settings())
EOF

echo ""
echo "Crypto Selection System initialization completed!"
echo ""
echo "Summary of containers created/verified:"
echo "  - crypto_selections (partition key: /selection_date) - for daily crypto selections"
echo "  - crypto_analysis_cache (partition key: /symbol) - for caching analysis data"
echo "  - crypto_market_metrics (partition key: /date) - for historical market metrics"
echo ""
echo "Default settings initialized:"
echo "  - DAILY_CRYPTO_COUNT = 10 (number of cryptos to select daily)"
echo "  - MIN_MARKET_CAP = 100M USD (minimum market cap requirement)"
echo "  - MIN_DAILY_VOLUME = 10M USD (minimum daily volume requirement)"  
echo "  - EXCLUDE_STABLECOINS = true (exclude stablecoins from selection)"
echo ""
echo "The strategy service will now:"
echo "  1. Analyze all available cryptocurrencies daily at 1:00 AM UTC"
echo "  2. Select the top performing cryptos based on multiple factors"
echo "  3. Store selections in database for market_data_service access"
echo "  4. Update selections automatically to adapt to market conditions"
echo "  - REST API endpoints on strategy service"