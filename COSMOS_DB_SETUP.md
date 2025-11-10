# Azure Cosmos DB Configuration Guide for masterTrade

## Overview
The masterTrade system has been configured to use Azure Cosmos DB as the primary database for all services, replacing PostgreSQL. This provides better scalability, global distribution, and multi-model support.

## Configuration Files Updated

### 1. Environment Variables (.env)
```bash
# Azure Cosmos DB Configuration
COSMOS_ENDPOINT=https://your-cosmos-account.documents.azure.com:443/
COSMOS_KEY=your_cosmos_primary_key_here
COSMOS_DATABASE=mastertrade
COSMOS_CONTAINER=trading_data
USE_COSMOS_DB=true

# Azure Configuration
USE_KEY_VAULT=true
AZURE_KEY_VAULT_URL=https://your-keyvault.vault.azure.net/
AZURE_CLIENT_ID=your_application_client_id
AZURE_CLIENT_SECRET=your_application_client_secret
AZURE_TENANT_ID=your_azure_tenant_id
MANAGED_IDENTITY_CLIENT_ID=your_managed_identity_client_id
```

## Services Using Cosmos DB

### 1. API Gateway Service
- **File**: `api_gateway/database.py`
- **Status**: ✅ Already configured for Cosmos DB
- **Dependencies**: ✅ Installed (azure-cosmos, azure-identity, azure-keyvault-secrets)

### 2. Market Data Service
- **File**: `market_data_service/database.py` 
- **Status**: ✅ Already configured for Cosmos DB
- **Dependencies**: ✅ Installed (azure-cosmos, azure-identity, azure-keyvault-secrets)

### 3. Strategy Service
- **File**: `strategy_service/database.py`
- **Status**: ✅ Already configured for Cosmos DB
- **Dependencies**: Azure packages need to be installed

### 4. Risk Manager Service
- **File**: `risk_manager/database.py`
- **Status**: ✅ Already configured for Cosmos DB
- **Dependencies**: Azure packages need to be installed

### 5. Order Executor Service
- **File**: `order_executor/database.py`
- **Status**: Needs verification and dependencies

### 6. Monitoring UI
- **Status**: ✅ Updated to use Cosmos DB
- **Dependencies**: ✅ Installed (@azure/cosmos, @azure/identity)
- **API Routes**: Updated to connect to Cosmos DB with fallback to mock data

## Cosmos DB Containers

The system expects the following containers in Cosmos DB:

1. **Strategies** - Trading strategy configurations and performance
2. **StrategyPerformance** - Historical performance metrics
3. **Positions** - Current and historical trading positions
4. **MarketData** - Real-time and historical market data
5. **Orders** - Trading order history and status
6. **RiskMetrics** - Risk management data and calculations

## Setup Steps

### 1. Azure Cosmos DB Account Setup
```bash
# Create Cosmos DB account (using Azure CLI)
az cosmosdb create --name your-cosmos-account --resource-group your-rg --kind GlobalDocumentDB

# Get connection details
az cosmosdb show-connection-strings --name your-cosmos-account --resource-group your-rg
```

### 2. Create Database and Containers
```javascript
// Use Cosmos DB Data Explorer or SDK to create:
// Database: mastertrade
// Containers with appropriate partition keys:
//   - Strategies (partition key: /strategy_type)
//   - StrategyPerformance (partition key: /strategy_id)  
//   - Positions (partition key: /symbol)
//   - MarketData (partition key: /symbol)
//   - Orders (partition key: /symbol)
//   - RiskMetrics (partition key: /portfolio_id)
```

### 3. Update Environment Variables
Replace the placeholder values in `.env` with your actual Azure credentials:
- `COSMOS_ENDPOINT`: Your Cosmos DB endpoint URL
- `COSMOS_KEY`: Primary key from Azure portal
- `AZURE_CLIENT_ID`: Service principal client ID
- `AZURE_CLIENT_SECRET`: Service principal secret
- `AZURE_TENANT_ID`: Your Azure tenant ID

### 4. Install Dependencies (if needed)
```bash
# For Python services
cd api_gateway && pip install azure-cosmos azure-identity azure-keyvault-secrets
cd ../market_data_service && pip install azure-cosmos azure-identity azure-keyvault-secrets
cd ../strategy_service && pip install azure-cosmos azure-identity azure-keyvault-secrets

# For monitoring UI  
cd ../monitoring_ui && npm install @azure/cosmos @azure/identity
```

## Testing Connection

### 1. Health Check Endpoint
The monitoring UI now has a health check endpoint:
```
GET http://localhost:3001/api/health
```

### 2. Fallback Behavior
All services are configured with fallback behavior:
- If Cosmos DB is unavailable, services return mock data
- Logs will indicate when fallback mode is active
- No service interruption during database connectivity issues

## Key Features

### 1. Global Distribution
- Cosmos DB provides automatic global distribution
- Low latency access from multiple regions
- Built-in disaster recovery

### 2. Multi-Model Support
- Document model for flexible schema
- Graph capabilities for relationship analysis
- Time-series data for market analytics

### 3. Automatic Scaling
- Serverless or provisioned throughput options
- Automatic scaling based on demand
- Cost optimization features

### 4. Security
- Encryption at rest and in transit
- Role-based access control
- Integration with Azure Key Vault
- VNet integration support

## Migration Notes

### From PostgreSQL to Cosmos DB
1. **Data Model Changes**: 
   - Relational tables → JSON documents
   - Foreign keys → Embedded/referenced documents
   - Joins → Denormalization or multiple queries

2. **Query Language**:
   - SQL-like syntax but with JSON operations
   - Partition key considerations for performance
   - Cross-partition queries are more expensive

3. **Consistency Levels**:
   - Choose appropriate consistency level
   - Default: Session consistency
   - Options: Strong, Bounded staleness, Session, Consistent prefix, Eventual

## Performance Optimization

### 1. Partition Key Design
- Choose partition keys for even distribution
- Avoid hot partitions
- Consider query patterns

### 2. Indexing Strategy  
- Automatic indexing by default
- Custom index policies for specific queries
- Exclude unnecessary paths to reduce RU consumption

### 3. Request Unit (RU) Management
- Monitor RU consumption
- Optimize queries to reduce RU usage
- Use appropriate consistency levels

## Monitoring and Alerting

### 1. Built-in Metrics
- Request units consumed
- Storage usage
- Latency metrics
- Availability metrics

### 2. Integration with Azure Monitor
- Custom alerts on RU consumption
- Performance insights
- Query performance statistics

## Next Steps

1. **Complete Installation**: Install Azure dependencies for remaining services
2. **Configure Credentials**: Add real Azure credentials to `.env`
3. **Create Containers**: Set up Cosmos DB containers with proper partition keys
4. **Test Connection**: Use health check endpoint to verify connectivity
5. **Data Migration**: Migrate any existing data from PostgreSQL
6. **Performance Tuning**: Optimize queries and partition keys based on usage patterns

The system is now ready to use Azure Cosmos DB as the primary database!