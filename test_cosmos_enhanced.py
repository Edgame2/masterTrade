#!/usr/bin/env python3
"""
masterTrade Cosmos DB Connection Test
Tests Azure Cosmos DB connection and creates database/containers if needed
"""
import asyncio
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def check_requirements():
    """Check if required packages are installed"""
    try:
        from azure.cosmos.aio import CosmosClient
        from azure.cosmos import PartitionKey
        from azure.cosmos.exceptions import CosmosResourceNotFoundError
        from azure.identity.aio import DefaultAzureCredential
        import aiohttp
        return True, None
    except ImportError as e:
        return False, str(e)

async def test_cosmos_connection():
    """Test Cosmos DB connection and setup"""
    print("🚀 masterTrade Cosmos DB Connection Test")
    print("=" * 60)
    
    # Check requirements
    req_ok, req_error = check_requirements()
    if not req_ok:
        print(f"❌ Missing required packages: {req_error}")
        print("💡 Install with: pip install azure-cosmos azure-identity python-dotenv aiohttp")
        return False
    
    # Import after requirements check
    from azure.cosmos.aio import CosmosClient
    from azure.cosmos import PartitionKey
    from azure.cosmos.exceptions import CosmosResourceNotFoundError, CosmosHttpResponseError
    from azure.identity.aio import DefaultAzureCredential
    
    # Get configuration
    endpoint = os.getenv('COSMOS_ENDPOINT')
    key = os.getenv('COSMOS_KEY') 
    database_name = os.getenv('COSMOS_DATABASE', 'mmasterTrade')
    
    print("🔍 Testing Azure Cosmos DB Connection...")
    print("=" * 60)
    print(f"📍 Endpoint: {endpoint}")
    print(f"🗄️  Database: {database_name}")
    print(f"🔑 Key configured: {'Yes' if key else 'No'}")
    
    if not endpoint:
        print("❌ COSMOS_ENDPOINT not configured in .env")
        return False
    
    try:
        # Create client
        if key:
            print("🔐 Using direct authentication with key")
            client = CosmosClient(endpoint, key)
        else:
            print("🔐 Using Azure Managed Identity")
            credential = DefaultAzureCredential()
            client = CosmosClient(endpoint, credential)
        
        print("\n⏳ Testing connection...")
        
        # Test connection by listing databases
        databases = []
        try:
            async for db in client.list_databases():
                databases.append(db['id'])
            print(f"✅ Connection successful! Found {len(databases)} databases")
            if databases:
                print(f"📋 Existing databases: {', '.join(databases)}")
        except Exception as e:
            print(f"❌ Failed to list databases: {e}")
            return False
        
        # Check if our database exists, create if not
        database = None
        try:
            database = client.get_database_client(database_name)
            await database.read()
            print(f"✅ Database '{database_name}' exists")
        except CosmosResourceNotFoundError:
            print(f"🔧 Database '{database_name}' not found, creating...")
            try:
                database = await client.create_database(database_name)
                print(f"✅ Database '{database_name}' created successfully!")
            except Exception as e:
                print(f"❌ Failed to create database: {e}")
                return False
        except Exception as e:
            print(f"❌ Error checking database: {e}")
            return False
        
        # List containers in the database
        print(f"\n📦 Checking containers in '{database_name}'...")
        containers = []
        try:
            async for container in database.list_containers():
                containers.append(container['id'])
            
            if containers:
                print(f"✅ Found {len(containers)} containers: {', '.join(containers)}")
            else:
                print("ℹ️  No containers found")
        except Exception as e:
            print(f"❌ Error listing containers: {e}")
            return False
        
        # Create essential containers for masterTrade if they don't exist
        essential_containers = [
            'trades',
            'orders', 
            'market_data',
            'strategies',
            'portfolios'
        ]
        
        print("\n🔧 Ensuring essential containers exist...")
        for container_name in essential_containers:
            try:
                if container_name not in containers:
                    print(f"🆕 Creating container '{container_name}'...")
                    await database.create_container(
                        id=container_name,
                        partition_key=PartitionKey(path="/id")
                    )
                    print(f"✅ Container '{container_name}' created")
                else:
                    print(f"✅ Container '{container_name}' already exists")
            except Exception as e:
                print(f"❌ Failed to create container '{container_name}': {e}")
        
        # Test CRUD operations
        print("\n🧪 Testing CRUD operations...")
        try:
            # Get trades container
            trades_container = database.get_container_client('trades')
            
            # Insert test document
            test_doc = {
                "id": "connection_test",
                "type": "test",
                "timestamp": "2024-11-07T16:00:00Z",
                "status": "success",
                "message": "masterTrade connection test"
            }
            
            print("📝 Inserting test document...")
            await trades_container.create_item(test_doc)
            print("✅ Test document inserted")
            
            # Read test document  
            print("📖 Reading test document...")
            read_doc = await trades_container.read_item(
                item="connection_test", 
                partition_key="connection_test"
            )
            print("✅ Test document read successfully")
            
            # Delete test document
            print("🗑️  Cleaning up test document...")
            await trades_container.delete_item(
                item="connection_test",
                partition_key="connection_test"
            )
            print("✅ Test document cleaned up")
            
        except Exception as e:
            print(f"❌ CRUD test failed: {e}")
            return False
        
        print("\n🎉 All tests passed! Cosmos DB is ready for masterTrade")
        return True
        
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return False
    finally:
        # Ensure client is closed
        try:
            await client.close()
        except:
            pass

async def main():
    """Main test function"""
    success = await test_cosmos_connection()
    
    print("\n" + "=" * 60)
    print("📊 Test Summary:")
    if success:
        print("✅ Cosmos DB connection: SUCCESS")
        print("🚀 masterTrade database is ready to use!")
    else:
        print("❌ Cosmos DB connection: FAILED") 
        print("💡 Check your .env configuration and Azure credentials")
    
    return 0 if success else 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)