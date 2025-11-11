# Azure Key Vault Secrets Configuration for MasterTrade
# ==================================================
# 
# Cette liste contient tous les secrets nécessaires pour configurer
# Azure Key Vault pour le système de trading MasterTrade.
#
# Instructions d'utilisation :
# 1. Remplacez les valeurs "YOUR_ACTUAL_VALUE" par vos vraies valeurs
# 2. Utilisez Azure CLI ou le portail Azure pour créer ces secrets
# 3. Respectez exactement les noms des secrets (sensible à la casse)

# =================================================================
# SECTION 1: AZURE COSMOS DB CONFIGURATION
# =================================================================

# Cosmos DB Primary Key (obtenu depuis le portail Azure)
cosmos-key: "YOUR_ACTUAL_COSMOS_PRIMARY_KEY"

# Cosmos DB Endpoint URL 
cosmos-endpoint: "https://tradebot.documents.azure.com:443/"

# Nom de la base de données Cosmos DB
cosmos-database: "mmasterTrade"

# =================================================================
# SECTION 2: BINANCE EXCHANGE CONFIGURATION
# =================================================================

# Binance Production API Credentials
binance-api-key: "YOUR_BINANCE_PRODUCTION_API_KEY"
binance-api-secret: "YOUR_BINANCE_PRODUCTION_SECRET_KEY"

# Binance Testnet API Credentials (pour les tests)
binance-testnet-api-key: "YOUR_BINANCE_TESTNET_API_KEY" 
binance-testnet-api-secret: "YOUR_BINANCE_TESTNET_SECRET_KEY"

# =================================================================
# SECTION 3: RABBITMQ MESSAGE BROKER
# =================================================================

# URL complète RabbitMQ avec authentification
rabbitmq-url: "amqp://mastertrade:YOUR_RABBITMQ_PASSWORD@localhost:5672/"

# Utilisateur RabbitMQ
rabbitmq-user: "mastertrade"

# Mot de passe RabbitMQ
rabbitmq-password: "YOUR_SECURE_RABBITMQ_PASSWORD"

# =================================================================
# SECTION 4: EXTERNAL API SERVICES
# =================================================================

# Alpha Vantage pour données financières
alpha-vantage-api-key: "YOUR_ALPHA_VANTAGE_API_KEY"

# Finnhub pour données de marché supplémentaires
finnhub-api-key: "YOUR_FINNHUB_API_KEY"

# NewsAPI pour analyse des sentiments
newsapi-key: "YOUR_NEWSAPI_KEY"

# Polygon.io pour données de marché US
polygon-api-key: "YOUR_POLYGON_API_KEY"

# =================================================================
# SECTION 5: SECURITY & AUTHENTICATION
# =================================================================

# Clé secrète JWT pour l'authentification
jwt-secret: "YOUR_STRONG_JWT_SECRET_KEY_256_BITS"

# Clé de chiffrement API
api-encryption-key: "YOUR_API_ENCRYPTION_KEY_256_BITS"

# =================================================================
# SECTION 6: REDIS CONFIGURATION
# =================================================================

# URL Redis avec authentification si nécessaire
redis-url: "redis://localhost:6379"

# Mot de passe Redis (si activé)
redis-password: "YOUR_REDIS_PASSWORD"

# =================================================================
# SECTION 7: MONITORING & OBSERVABILITY
# =================================================================

# Mot de passe Grafana Admin
grafana-password: "YOUR_SECURE_GRAFANA_PASSWORD"

# =================================================================
# SECTION 8: AZURE SERVICE PRINCIPAL (déjà configuré)
# =================================================================

# Client ID de l'application Azure AD
azure-client-id: "your-azure-client-id"

# Client Secret de l'application Azure AD
azure-client-secret: "your-azure-client-secret"

# Tenant ID Azure AD
azure-tenant-id: "your-azure-tenant-id"

# =================================================================
# COMMANDES AZURE CLI POUR CRÉER LES SECRETS
# =================================================================

# Exemple de commandes pour créer les secrets via Azure CLI :
# 
# az keyvault secret set --vault-name "mastertrade" --name "cosmos-key" --value "YOUR_ACTUAL_VALUE"
# az keyvault secret set --vault-name "mastertrade" --name "binance-api-key" --value "YOUR_ACTUAL_VALUE"
# az keyvault secret set --vault-name "mastertrade" --name "binance-api-secret" --value "YOUR_ACTUAL_VALUE"
# 
# ... répétez pour tous les secrets ci-dessus

# =================================================================
# VALIDATION ET TEST
# =================================================================

# Après avoir créé les secrets, testez avec :
# az keyvault secret list --vault-name "mastertrade" --query "[].name" -o table

# =================================================================
# SECRETS PRIORITAIRES POUR COMMENCER
# =================================================================

# Secrets essentiels pour démarrer le système :
# 1. cosmos-key (obligatoire pour la base de données)
# 2. binance-testnet-api-key (pour commencer les tests)
# 3. binance-testnet-api-secret (pour commencer les tests)  
# 4. jwt-secret (pour l'authentification)
# 5. rabbitmq-password (pour la messagerie)

# =================================================================
# SÉCURITÉ
# =================================================================

# ⚠️  IMPORTANT: 
# - Ne jamais commiter les vraies valeurs dans Git
# - Utilisez des permissions restrictives sur Key Vault
# - Activez l'audit des accès aux secrets
# - Rotez régulièrement les clés API
# - Utilisez des environnements séparés (dev/staging/prod)