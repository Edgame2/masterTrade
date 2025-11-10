# Azure Key Vault Integration Guide

This guide explains how to set up and use Azure Key Vault for secure environment variable management in the Market Data Service.

## Overview

Azure Key Vault integration provides:
- ✅ **Secure Secret Storage**: Centralized secret management
- ✅ **Managed Identity Authentication**: Passwordless authentication
- ✅ **Audit Logging**: Track secret access and changes
- ✅ **Secret Rotation**: Automated secret rotation capabilities
- ✅ **Access Control**: Fine-grained RBAC permissions
- ✅ **Fallback Support**: Graceful degradation to environment variables

## Architecture

```
[Market Data Service] 
    ↓ (Managed Identity)
[Azure Key Vault] 
    ↓ (Secrets)
[API Keys, Connection Strings, etc.]
```

## Setup Steps

### 1. Create Azure Key Vault

Run the provided setup script:

```bash
./setup_keyvault.sh
```

Or manually create:

```bash
# Create Resource Group
az group create --name mastertrade-rg --location "East US"

# Create Key Vault
az keyvault create \
    --name mastertrade-keyvault \
    --resource-group mastertrade-rg \
    --location "East US" \
    --enable-soft-delete true \
    --sku standard
```

### 2. Upload Secrets to Key Vault

```bash
# Azure Configuration
az keyvault secret set --vault-name mastertrade-keyvault --name "COSMOS-ENDPOINT" --value "https://your-cosmos.documents.azure.com:443/"
az keyvault secret set --vault-name mastertrade-keyvault --name "RABBITMQ-URL" --value "amqp://user:pass@rabbitmq:5672/"

# API Keys
az keyvault secret set --vault-name mastertrade-keyvault --name "BINANCE-API-KEY" --value "your-binance-key"
az keyvault secret set --vault-name mastertrade-keyvault --name "BINANCE-API-SECRET" --value "your-binance-secret"
az keyvault secret set --vault-name mastertrade-keyvault --name "ALPHA-VANTAGE-API-KEY" --value "your-alphav-key"
az keyvault secret set --vault-name mastertrade-keyvault --name "NEWS-API-KEY" --value "your-news-key"
```

### 3. Configure Managed Identity

#### For Azure Container Apps:
```bash
# Enable system-assigned managed identity
az containerapp identity assign \
    --name mastertrade-app \
    --resource-group mastertrade-rg \
    --system-assigned

# Get the principal ID
PRINCIPAL_ID=$(az containerapp show \
    --name mastertrade-app \
    --resource-group mastertrade-rg \
    --query identity.principalId -o tsv)

# Grant Key Vault access
az keyvault set-policy \
    --name mastertrade-keyvault \
    --object-id $PRINCIPAL_ID \
    --secret-permissions get list
```

#### For Azure App Service:
```bash
# Enable system-assigned managed identity
az webapp identity assign \
    --name mastertrade-app \
    --resource-group mastertrade-rg

# Get the principal ID  
PRINCIPAL_ID=$(az webapp show \
    --name mastertrade-app \
    --resource-group mastertrade-rg \
    --query identity.principalId -o tsv)

# Grant Key Vault access
az keyvault set-policy \
    --name mastertrade-keyvault \
    --object-id $PRINCIPAL_ID \
    --secret-permissions get list
```

### 4. Set Environment Variables

For your deployed service, set these environment variables:

```bash
AZURE_KEY_VAULT_URL=https://mastertrade-keyvault.vault.azure.net/
USE_KEY_VAULT=true
```

## Local Development Setup

### 1. Install Dependencies
```bash
pip install azure-keyvault-secrets azure-identity
```

### 2. Azure CLI Login
```bash
az login
```

### 3. Set Environment Variables
```bash
export AZURE_KEY_VAULT_URL=https://mastertrade-keyvault.vault.azure.net/
export USE_KEY_VAULT=true
```

### 4. Test Configuration
```bash
python test_keyvault_integration.py
```

## Secret Name Conventions

Key Vault secret names use hyphens (Azure requirement), which are converted to underscores for environment variables:

| Key Vault Secret | Environment Variable |
|------------------|---------------------|
| `BINANCE-API-KEY` | `BINANCE_API_KEY` |
| `COSMOS-ENDPOINT` | `COSMOS_ENDPOINT` |
| `RABBITMQ-URL` | `RABBITMQ_URL` |

## Usage in Code

The service automatically loads secrets on startup:

```python
from config import initialize_settings, settings

# Initialize with Key Vault
await initialize_settings()

# Use configuration
api_key = settings.BINANCE_API_KEY  # Loaded from Key Vault
cosmos_endpoint = settings.COSMOS_ENDPOINT  # Loaded from Key Vault
```

## Fallback Behavior

The system provides graceful fallback:

1. **Key Vault Available**: Loads secrets from Key Vault
2. **Key Vault Unavailable**: Falls back to environment variables
3. **Neither Available**: Uses default values from configuration

## Security Best Practices

### 1. Principle of Least Privilege
- Grant minimal permissions (`get` and `list` only)
- Use specific secret permissions, not broad access

### 2. Network Security
```bash
# Restrict Key Vault access to specific networks
az keyvault network-rule add \
    --vault-name mastertrade-keyvault \
    --subnet /subscriptions/.../subnets/app-subnet
```

### 3. Monitoring and Logging
```bash
# Enable Key Vault logging
az monitor diagnostic-settings create \
    --name keyvault-diagnostics \
    --resource mastertrade-keyvault \
    --logs '[{"category": "AuditEvent", "enabled": true}]' \
    --workspace your-log-analytics-workspace
```

### 4. Secret Rotation
- Implement regular API key rotation
- Use Key Vault versioning for rollback capability
- Monitor secret expiration dates

### 5. Access Reviews
- Regularly audit Key Vault access policies
- Remove unused service principals
- Monitor access logs for anomalies

## Troubleshooting

### Common Issues

1. **Authentication Failed**
   ```
   Solution: Ensure managed identity is enabled and has proper permissions
   Test: az login (for local development)
   ```

2. **Key Vault Not Found**
   ```
   Solution: Verify Key Vault URL and name
   Test: az keyvault show --name mastertrade-keyvault
   ```

3. **Secret Not Found**
   ```
   Solution: Check secret names match exactly (case-sensitive)
   Test: az keyvault secret list --vault-name mastertrade-keyvault
   ```

4. **Permission Denied**
   ```
   Solution: Check access policy includes 'get' and 'list' permissions
   Test: az keyvault show --name mastertrade-keyvault --query properties.accessPolicies
   ```

### Debug Commands

```bash
# List all secrets
az keyvault secret list --vault-name mastertrade-keyvault --output table

# Get secret value
az keyvault secret show --vault-name mastertrade-keyvault --name BINANCE-API-KEY --query value -o tsv

# Check access policies
az keyvault show --name mastertrade-keyvault --query properties.accessPolicies

# Test authentication
az account get-access-token --resource https://vault.azure.net/
```

## Migration from Environment Variables

1. **Identify Secrets**: List all sensitive environment variables
2. **Upload to Key Vault**: Use the setup script or manual upload
3. **Update Configuration**: Enable `USE_KEY_VAULT=true`
4. **Test Locally**: Verify secrets load correctly
5. **Deploy**: Update production environment variables
6. **Clean Up**: Remove sensitive values from environment configs

## Benefits Summary

- 🔒 **Enhanced Security**: Centralized secret management with encryption
- 🔄 **Easy Rotation**: Update secrets without redeploying applications
- 📊 **Audit Trail**: Complete logging of secret access and modifications
- 🎯 **Access Control**: Fine-grained permissions with Azure RBAC
- 🔧 **DevOps Integration**: Seamless CI/CD pipeline integration
- 🛡️ **Compliance**: Meets enterprise security and compliance requirements