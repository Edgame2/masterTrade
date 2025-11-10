#!/bin/bash
"""
Azure Key Vault Setup Script for Market Data Service

This script sets up Azure Key Vault with all required secrets for the Market Data Service.
It creates the Key Vault, sets access policies, and uploads secrets.

Prerequisites:
- Azure CLI installed and logged in
- Appropriate Azure permissions for Key Vault operations
"""

# Configuration
RESOURCE_GROUP="mastertrade-rg"
KEY_VAULT_NAME="mastertrade-keyvault"
LOCATION="East US"
SERVICE_PRINCIPAL_NAME="mastertrade-sp"

echo "🔐 Setting up Azure Key Vault for Market Data Service"
echo "=================================================="

# Check if logged in to Azure
if ! az account show > /dev/null 2>&1; then
    echo "❌ Please login to Azure CLI first: az login"
    exit 1
fi

echo "✅ Azure CLI authenticated"

# Create Resource Group if it doesn't exist
echo "📦 Creating resource group: $RESOURCE_GROUP"
az group create --name $RESOURCE_GROUP --location "$LOCATION" --output table

# Create Key Vault
echo "🔐 Creating Key Vault: $KEY_VAULT_NAME"
az keyvault create \
    --name $KEY_VAULT_NAME \
    --resource-group $RESOURCE_GROUP \
    --location "$LOCATION" \
    --enable-soft-delete true \
    --enable-purge-protection false \
    --sku standard \
    --output table

# Get the current user's object ID for access policy
USER_OBJECT_ID=$(az ad signed-in-user show --query objectId --output tsv)
echo "👤 Current user object ID: $USER_OBJECT_ID"

# Set access policy for current user (for initial setup)
echo "🔑 Setting Key Vault access policy for current user"
az keyvault set-policy \
    --name $KEY_VAULT_NAME \
    --object-id $USER_OBJECT_ID \
    --secret-permissions get list set delete backup restore recover purge \
    --output table

echo "📝 Creating secrets in Key Vault..."

# Azure Configuration Secrets
echo "  🔹 Azure configuration secrets"
az keyvault secret set --vault-name $KEY_VAULT_NAME --name "COSMOS-ENDPOINT" --value "https://your-mastertrade-cosmos.documents.azure.com:443/"
az keyvault secret set --vault-name $KEY_VAULT_NAME --name "COSMOS-DATABASE" --value "mastertrade"
az keyvault secret set --vault-name $KEY_VAULT_NAME --name "MANAGED-IDENTITY-CLIENT-ID" --value ""

# RabbitMQ Configuration
echo "  🔹 RabbitMQ configuration"
az keyvault secret set --vault-name $KEY_VAULT_NAME --name "RABBITMQ-URL" --value "amqp://admin:SecurePassword123@rabbitmq:5672/"

# API Keys (you'll need to update these with real values)
echo "  🔹 API keys (update with real values later)"
az keyvault secret set --vault-name $KEY_VAULT_NAME --name "BINANCE-API-KEY" --value "your-binance-api-key-here"
az keyvault secret set --vault-name $KEY_VAULT_NAME --name "BINANCE-API-SECRET" --value "your-binance-api-secret-here"
az keyvault secret set --vault-name $KEY_VAULT_NAME --name "ALPHA-VANTAGE-API-KEY" --value "your-alpha-vantage-key-here"
az keyvault secret set --vault-name $KEY_VAULT_NAME --name "FINNHUB-API-KEY" --value "your-finnhub-key-here"

# Sentiment Analysis APIs
echo "  🔹 Sentiment analysis API keys"
az keyvault secret set --vault-name $KEY_VAULT_NAME --name "NEWS-API-KEY" --value "your-news-api-key-here"
az keyvault secret set --vault-name $KEY_VAULT_NAME --name "TWITTER-BEARER-TOKEN" --value "your-twitter-bearer-token-here"
az keyvault secret set --vault-name $KEY_VAULT_NAME --name "REDDIT-CLIENT-ID" --value "your-reddit-client-id-here"
az keyvault secret set --vault-name $KEY_VAULT_NAME --name "REDDIT-CLIENT-SECRET" --value "your-reddit-client-secret-here"

# Service Configuration
echo "  🔹 Service configuration"
az keyvault secret set --vault-name $KEY_VAULT_NAME --name "LOG-LEVEL" --value "INFO"

echo ""
echo "✅ Key Vault setup completed!"
echo ""
echo "📋 Next Steps:"
echo "1. Update the API key secrets with real values:"
echo "   az keyvault secret set --vault-name $KEY_VAULT_NAME --name 'BINANCE-API-KEY' --value 'your-real-key'"
echo ""
echo "2. Set up Managed Identity for your Azure service:"
echo "   - Enable system-assigned or user-assigned managed identity"
echo "   - Grant Key Vault access policy to the managed identity"
echo ""
echo "3. Set environment variables for your service:"
echo "   export AZURE_KEY_VAULT_URL='https://$KEY_VAULT_NAME.vault.azure.net/'"
echo "   export USE_KEY_VAULT='true'"
echo ""
echo "4. For local development, ensure you're logged in with Azure CLI:"
echo "   az login"
echo ""
echo "🔍 Key Vault URL: https://$KEY_VAULT_NAME.vault.azure.net/"
echo ""

# Create managed identity setup instructions
cat > setup_managed_identity.md << EOF
# Managed Identity Setup for Market Data Service

## For Azure Container Apps/App Service

1. **Enable Managed Identity**:
   \`\`\`bash
   # For Container Apps
   az containerapp identity assign --name your-app-name --resource-group $RESOURCE_GROUP --system-assigned
   
   # For App Service
   az webapp identity assign --name your-app-name --resource-group $RESOURCE_GROUP
   \`\`\`

2. **Get the Managed Identity Object ID**:
   \`\`\`bash
   # For Container Apps
   IDENTITY_ID=\$(az containerapp show --name your-app-name --resource-group $RESOURCE_GROUP --query identity.principalId --output tsv)
   
   # For App Service  
   IDENTITY_ID=\$(az webapp show --name your-app-name --resource-group $RESOURCE_GROUP --query identity.principalId --output tsv)
   \`\`\`

3. **Grant Key Vault Access**:
   \`\`\`bash
   az keyvault set-policy \\
       --name $KEY_VAULT_NAME \\
       --object-id \$IDENTITY_ID \\
       --secret-permissions get list \\
       --output table
   \`\`\`

4. **Set Environment Variables**:
   \`\`\`bash
   AZURE_KEY_VAULT_URL=https://$KEY_VAULT_NAME.vault.azure.net/
   USE_KEY_VAULT=true
   \`\`\`

## For Local Development

1. **Login with Azure CLI**:
   \`\`\`bash
   az login
   \`\`\`

2. **Set Environment Variables**:
   \`\`\`bash
   export AZURE_KEY_VAULT_URL=https://$KEY_VAULT_NAME.vault.azure.net/
   export USE_KEY_VAULT=true
   \`\`\`

## Security Best Practices

1. **Principle of Least Privilege**: Grant only 'get' and 'list' permissions to the managed identity
2. **Network Security**: Configure Key Vault firewall to restrict access
3. **Monitoring**: Enable Key Vault logging and monitoring
4. **Secret Rotation**: Implement regular secret rotation policies
5. **Access Reviews**: Regularly review and audit Key Vault access policies

EOF

echo "📄 Created setup_managed_identity.md with detailed instructions"
echo "🔐 Key Vault setup completed successfully!"