#!/bin/bash

# =================================================================
# Script de création des secrets Azure Key Vault pour MasterTrade
# =================================================================
#
# Usage: ./setup-keyvault-secrets.sh
# 
# Prérequis:
# - Azure CLI installé et connecté (az login)
# - Permissions sur le Key Vault "mastertrade"
# - Remplacer les valeurs YOUR_ACTUAL_* par les vraies valeurs
#
# =================================================================

set -e  # Arrêter le script en cas d'erreur

# Configuration
KEYVAULT_NAME="mastertrade"
RESOURCE_GROUP="masterTrade"  # Remplacer par votre groupe de ressources

echo "🔐 Configuration des secrets Azure Key Vault pour MasterTrade"
echo "=============================================================="

# Vérifier la connexion Azure
echo "📋 Vérification de la connexion Azure..."
az account show --query "name" -o tsv > /dev/null || {
    echo "❌ Veuillez vous connecter à Azure avec 'az login'"
    exit 1
}

echo "✅ Connecté à Azure"

# Vérifier l'existence du Key Vault
echo "📋 Vérification du Key Vault..."
az keyvault show --name "$KEYVAULT_NAME" --query "name" -o tsv > /dev/null || {
    echo "❌ Key Vault '$KEYVAULT_NAME' non trouvé"
    echo "💡 Créez-le avec: az keyvault create --name $KEYVAULT_NAME --resource-group $RESOURCE_GROUP --location westeurope"
    exit 1
}

echo "✅ Key Vault '$KEYVAULT_NAME' trouvé"

# Fonction pour créer un secret de manière sécurisée
create_secret() {
    local secret_name="$1"
    local secret_value="$2"
    local description="$3"
    
    if [[ "$secret_value" == "YOUR_ACTUAL_"* ]] || [[ "$secret_value" == "" ]]; then
        echo "⚠️  Ignorer $secret_name (valeur par défaut non remplacée)"
        return
    fi
    
    echo "🔑 Création du secret: $secret_name"
    az keyvault secret set \
        --vault-name "$KEYVAULT_NAME" \
        --name "$secret_name" \
        --value "$secret_value" \
        --description "$description" \
        --output none
    
    echo "   ✅ $secret_name créé avec succès"
}

echo ""
echo "🚀 Création des secrets..."
echo "=========================="

# =================================================================
# SECTION 1: AZURE COSMOS DB
# =================================================================

echo ""
echo "📊 Secrets Cosmos DB..."

create_secret "cosmos-key" \
    "YOUR_ACTUAL_COSMOS_PRIMARY_KEY" \
    "Cosmos DB Primary Key pour MasterTrade"

create_secret "cosmos-endpoint" \
    "https://tradebot.documents.azure.com:443/" \
    "Cosmos DB Endpoint URL"

create_secret "cosmos-database" \
    "mmasterTrade" \
    "Nom de la base de données Cosmos DB"

# =================================================================
# SECTION 2: BINANCE EXCHANGE
# =================================================================

echo ""
echo "💱 Secrets Binance..."

create_secret "binance-api-key" \
    "YOUR_BINANCE_PRODUCTION_API_KEY" \
    "Binance Production API Key"

create_secret "binance-api-secret" \
    "YOUR_BINANCE_PRODUCTION_SECRET_KEY" \
    "Binance Production API Secret"

create_secret "binance-testnet-api-key" \
    "YOUR_BINANCE_TESTNET_API_KEY" \
    "Binance Testnet API Key pour les tests"

create_secret "binance-testnet-api-secret" \
    "YOUR_BINANCE_TESTNET_SECRET_KEY" \
    "Binance Testnet API Secret pour les tests"

# =================================================================
# SECTION 3: RABBITMQ
# =================================================================

echo ""
echo "📨 Secrets RabbitMQ..."

create_secret "rabbitmq-url" \
    "amqp://mastertrade:YOUR_RABBITMQ_PASSWORD@localhost:5672/" \
    "URL complète RabbitMQ avec authentification"

create_secret "rabbitmq-user" \
    "mastertrade" \
    "Utilisateur RabbitMQ"

create_secret "rabbitmq-password" \
    "YOUR_SECURE_RABBITMQ_PASSWORD" \
    "Mot de passe RabbitMQ"

# =================================================================
# SECTION 4: EXTERNAL APIs
# =================================================================

echo ""
echo "🌐 Secrets APIs externes..."

create_secret "alpha-vantage-api-key" \
    "YOUR_ALPHA_VANTAGE_API_KEY" \
    "Alpha Vantage API Key pour données financières"

create_secret "finnhub-api-key" \
    "YOUR_FINNHUB_API_KEY" \
    "Finnhub API Key pour données de marché"

create_secret "newsapi-key" \
    "YOUR_NEWSAPI_KEY" \
    "NewsAPI Key pour analyse des sentiments"

create_secret "polygon-api-key" \
    "YOUR_POLYGON_API_KEY" \
    "Polygon.io API Key pour données US"

# =================================================================
# SECTION 5: SECURITY
# =================================================================

echo ""
echo "🔒 Secrets de sécurité..."

create_secret "jwt-secret" \
    "YOUR_STRONG_JWT_SECRET_KEY_256_BITS" \
    "Clé secrète JWT pour authentification"

create_secret "api-encryption-key" \
    "YOUR_API_ENCRYPTION_KEY_256_BITS" \
    "Clé de chiffrement API"

# =================================================================
# SECTION 6: REDIS
# =================================================================

echo ""
echo "📦 Secrets Redis..."

create_secret "redis-url" \
    "redis://localhost:6379" \
    "URL Redis"

create_secret "redis-password" \
    "YOUR_REDIS_PASSWORD" \
    "Mot de passe Redis (optionnel)"

# =================================================================
# SECTION 7: MONITORING
# =================================================================

echo ""
echo "📈 Secrets Monitoring..."

create_secret "grafana-password" \
    "YOUR_SECURE_GRAFANA_PASSWORD" \
    "Mot de passe Admin Grafana"

# =================================================================
# VÉRIFICATION FINALE
# =================================================================

echo ""
echo "🔍 Vérification des secrets créés..."
echo "====================================="

SECRET_COUNT=$(az keyvault secret list --vault-name "$KEYVAULT_NAME" --query "length(@)" -o tsv)

echo "📊 Nombre total de secrets dans Key Vault: $SECRET_COUNT"

echo ""
echo "📋 Liste des secrets:"
az keyvault secret list --vault-name "$KEYVAULT_NAME" --query "[].name" -o table

echo ""
echo "✅ Configuration terminée !"
echo ""
echo "🎯 Prochaines étapes:"
echo "   1. Vérifiez que tous vos secrets ont des vraies valeurs"
echo "   2. Testez la connexion avec: az keyvault secret show --vault-name $KEYVAULT_NAME --name cosmos-key"
echo "   3. Mettez à jour USE_KEY_VAULT=true dans vos services"
echo "   4. Redémarrez les services MasterTrade"
echo ""
echo "⚠️  Rappel sécurité:"
echo "   - Ne partagez jamais ces scripts avec de vraies valeurs"
echo "   - Activez l'audit sur Key Vault"
echo "   - Rotez régulièrement les clés API"