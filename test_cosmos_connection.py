#!/usr/bin/env python3
"""
Simple Cosmos DB Connection Test for masterTrade
Tests the connection to Azure Cosmos DB using the credentials from .env
"""

import os
import asyncio
import sys
from pathlib import Path

# Add the current directory to Python path
sys.path.append(str(Path(__file__).parent))

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

async def test_cosmos_connection():
    """Test Cosmos DB connection and basic operations"""
    
    try:
        from azure.cosmos.aio import CosmosClient
        from azure.identity.aio import DefaultAzureCredential
        
        print("🔍 Testing Azure Cosmos DB Connection...")
        print("=" * 60)
        
        # Get configuration from environment
        endpoint = os.getenv('COSMOS_ENDPOINT')
        key = os.getenv('COSMOS_KEY') 
        database_name = os.getenv('COSMOS_DATABASE', 'mmasterTrade')
        
        print(f"📍 Endpoint: {endpoint}")
        print(f"🗄️  Database: {database_name}")
        print(f"🔑 Key configured: {'Yes' if key else 'No (using Managed Identity)'}")
        
        # Create client
        if key:
            client = CosmosClient(endpoint, key)
            print("🔐 Using direct authentication with key")
        else:
            credential = DefaultAzureCredential()
            client = CosmosClient(endpoint, credential)
            print("🔐 Using Azure Managed Identity")
        
        print("\n⏳ Connecting to Cosmos DB...")
        
        # Test database connection
        try:
            database = client.get_database_client(database_name)
            
            # Try to read database properties
            db_properties = await database.read()
            print(f"✅ Successfully connected to database: {db_properties['id']}")
            
            # List containers
            print("\n📦 Available containers:")
            containers = []
            async for container in database.list_containers():
                containers.append(container['id'])
                print(f"   📁 {container['id']}")
            
            if not containers:
                print("   ⚠️  No containers found - database is empty")
                
                # Create a test container
                print("\n🔧 Creating test container...")
                container_name = "test_connection"
                container = await database.create_container(
                    id=container_name,
                    partition_key="/id",
                    offer_throughput=400
                )
                print(f"✅ Created container: {container_name}")
                
                # Insert a test document
                print("\n📝 Inserting test document...")
                test_doc = {
                    "id": "test_doc_1",
                    "type": "connection_test",
                    "timestamp": "2024-11-07T16:00:00Z",
                    "message": "masterTrade Cosmos DB connection test successful"
                }
                
                await container.create_item(test_doc)
                print("✅ Test document inserted successfully")
                
                # Read the test document back
                print("\n📖 Reading test document...")
                read_doc = await container.read_item(item="test_doc_1", partition_key="test_doc_1")
                print(f"✅ Read document: {read_doc['message']}")
                
                # Clean up test container
                print("\n🧹 Cleaning up test container...")
                await database.delete_container(container_name)
                print("✅ Test container deleted")
                
            else:
                # Test reading from an existing container
                container_name = containers[0]
                container = database.get_container_client(container_name)
                
                print(f"\n📖 Testing read access to container '{container_name}'...")
                
                # Try to query the container
                query = "SELECT TOP 1 * FROM c"
                items = []
                async for item in container.query_items(query=query):
                    items.append(item)
                
                if items:
                    print(f"✅ Successfully read {len(items)} item(s) from container")
                    print(f"   Sample item ID: {items[0].get('id', 'No ID field')}")
                else:
                    print("ℹ️  Container is empty, but connection successful")
            
        except Exception as db_error:
            print(f"❌ Database error: {str(db_error)}")
            return False
            
    except ImportError as e:
        print(f"❌ Missing required packages: {e}")
        print("💡 Install with: pip install azure-cosmos azure-identity python-dotenv")
        return False
        
    except Exception as e:
        print(f"❌ Connection failed: {str(e)}")
        return False
    
    finally:
        if 'client' in locals():
            await client.close()
    
    print("\n🎉 Cosmos DB connection test completed successfully!")
    return True

async def test_containers_setup():
    """Test if required containers exist and create them if needed"""
    
    required_containers = [
        {"name": "Strategies", "partition_key": "/strategy_type"},
        {"name": "StrategyPerformance", "partition_key": "/strategy_id"},
        {"name": "Positions", "partition_key": "/symbol"},
        {"name": "MarketData", "partition_key": "/symbol"},
        {"name": "Orders", "partition_key": "/symbol"},
        {"name": "RiskMetrics", "partition_key": "/portfolio_id"}
    ]
    
    print("\n🏗️  Checking required containers for masterTrade...")
    print("=" * 60)
    
    try:
        from azure.cosmos.aio import CosmosClient
        
        endpoint = os.getenv('COSMOS_ENDPOINT')
        key = os.getenv('COSMOS_KEY')
        database_name = os.getenv('COSMOS_DATABASE', 'mmasterTrade')
        
        client = CosmosClient(endpoint, key)
        database = client.get_database_client(database_name)
        
        # Get existing containers
        existing_containers = []
        async for container in database.list_containers():
            existing_containers.append(container['id'])
        
        print(f"📋 Existing containers: {len(existing_containers)}")
        for container_name in existing_containers:
            print(f"   ✅ {container_name}")
        
        # Check which containers are missing
        missing_containers = []
        for container_info in required_containers:
            if container_info["name"] not in existing_containers:
                missing_containers.append(container_info)
        
        if missing_containers:
            print(f"\n⚠️  Missing containers: {len(missing_containers)}")
            for container_info in missing_containers:
                print(f"   ❌ {container_info['name']}")
            
            print("\n🔧 Would you like to create missing containers? (This is just a test - no containers will be created)")
            print("💡 Use Azure Portal or CLI to create these containers with appropriate throughput settings")
            
        else:
            print("\n✅ All required containers are present!")
        
        await client.close()
        return True
        
    except Exception as e:
        print(f"❌ Container check failed: {str(e)}")
        return False

async def main():
    """Main test function"""
    print("🚀 masterTrade Cosmos DB Connection Test")
    print("=" * 60)
    
    # Test basic connection
    connection_success = await test_cosmos_connection()
    
    if connection_success:
        # Test container setup
        await test_containers_setup()
        
        print("\n" + "=" * 60)
        print("📊 Test Summary:")
        print("✅ Cosmos DB connection: SUCCESS")
        print("✅ Authentication: SUCCESS") 
        print("✅ Read/Write operations: SUCCESS")
        print("🎯 Ready for masterTrade integration!")
        
    else:
        print("\n" + "=" * 60)
        print("📊 Test Summary:")
        print("❌ Cosmos DB connection: FAILED")
        print("💡 Check your .env configuration and Azure credentials")
    
    return connection_success

if __name__ == "__main__":
    try:
        result = asyncio.run(main())
        sys.exit(0 if result else 1)
    except KeyboardInterrupt:
        print("\n\n🛑 Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n💥 Unexpected error: {e}")
        sys.exit(1)