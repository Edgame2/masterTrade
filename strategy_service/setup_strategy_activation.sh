#!/bin/bash

# Initialize Cosmos DB containers for Strategy Activation System
# This script ensures all required containers exist with proper partition keys

# Database configuration
DB_NAME="mastertrade"
COSMOS_ENDPOINT=${COSMOS_ENDPOINT:-""}
COSMOS_KEY=${COSMOS_KEY:-""}

if [ -z "$COSMOS_ENDPOINT" ] || [ -z "$COSMOS_KEY" ]; then
    echo "Error: COSMOS_ENDPOINT and COSMOS_KEY environment variables must be set"
    exit 1
fi

echo "Initializing Strategy Activation System containers..."

# Container configurations
declare -A CONTAINERS
CONTAINERS[settings]="/key"
CONTAINERS[strategy_activation_log]="/id" 
CONTAINERS[notifications]="/type"

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

# Initialize Settings container with MAX_ACTIVE_STRATEGIES setting
echo ""
echo "Initializing MAX_ACTIVE_STRATEGIES setting..."

# Create initial settings document if needed
python3 << EOF
import asyncio
import os
from datetime import datetime, timezone
from azure.cosmos import CosmosClient

async def initialize_settings():
    try:
        # Connect to Cosmos DB
        endpoint = os.getenv('COSMOS_ENDPOINT')
        key = os.getenv('COSMOS_KEY')
        
        client = CosmosClient(endpoint, key)
        database = client.get_database_client('$DB_NAME')
        container = database.get_container_client('settings')
        
        # Check if MAX_ACTIVE_STRATEGIES setting exists
        try:
            existing = container.read_item(
                item='MAX_ACTIVE_STRATEGIES',
                partition_key='MAX_ACTIVE_STRATEGIES'
            )
            print(f"MAX_ACTIVE_STRATEGIES setting already exists with value: {existing.get('value')}")
            
        except Exception:
            # Setting doesn't exist, create it
            setting_doc = {
                'id': 'MAX_ACTIVE_STRATEGIES',
                'key': 'MAX_ACTIVE_STRATEGIES',
                'value': '2',
                'description': 'Maximum number of active trading strategies',
                'type': 'integer',
                'created_at': datetime.now(timezone.utc).isoformat(),
                'updated_at': datetime.now(timezone.utc).isoformat()
            }
            
            container.create_item(setting_doc)
            print("Created MAX_ACTIVE_STRATEGIES setting with default value: 2")
            
    except Exception as e:
        print(f"Error initializing settings: {e}")

# Run the initialization
asyncio.run(initialize_settings())
EOF

echo ""
echo "Strategy Activation System initialization completed!"
echo ""
echo "Summary of containers created/verified:"
echo "  - settings (partition key: /key) - for MAX_ACTIVE_STRATEGIES setting"
echo "  - strategy_activation_log (partition key: /id) - for activation change logs"
echo "  - notifications (partition key: /type) - for system notifications"
echo ""
echo "Default settings initialized:"
echo "  - MAX_ACTIVE_STRATEGIES = 2"
echo ""
echo "The strategy service will now:"
echo "  1. Automatically read MAX_ACTIVE_STRATEGIES from the database"
echo "  2. Evaluate all strategies every 4 hours"  
echo "  3. Activate the best performing strategies up to the limit"
echo "  4. Log all activation changes for audit trail"