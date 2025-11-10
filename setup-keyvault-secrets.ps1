# =================================================================
# Script PowerShell pour créer les secrets Azure Key Vault
# =================================================================
#
# Usage: .\setup-keyvault-secrets.ps1
# 
# Prérequis:
# - Azure CLI installé et connecté (az login)
# - PowerShell 5.1 ou PowerShell Core
# - Permissions sur le Key Vault "mastertrade"
#

param(
    [string]$KeyVaultName = "mastertrade",
    [string]$ResourceGroup = "masterTrade"
)

$ErrorActionPreference = "Stop"

Write-Host "🔐 Configuration des secrets Azure Key Vault pour MasterTrade" -ForegroundColor Cyan
Write-Host "==============================================================" -ForegroundColor Cyan

# Vérifier la connexion Azure
Write-Host "📋 Vérification de la connexion Azure..." -ForegroundColor Yellow
try {
    $account = az account show --query "name" -o tsv
    Write-Host "✅ Connecté à Azure: $account" -ForegroundColor Green
}
catch {
    Write-Host "❌ Veuillez vous connecter à Azure avec 'az login'" -ForegroundColor Red
    exit 1
}

# Vérifier l'existence du Key Vault
Write-Host "📋 Vérification du Key Vault..." -ForegroundColor Yellow
try {
    $vault = az keyvault show --name $KeyVaultName --query "name" -o tsv
    Write-Host "✅ Key Vault '$KeyVaultName' trouvé" -ForegroundColor Green
}
catch {
    Write-Host "❌ Key Vault '$KeyVaultName' non trouvé" -ForegroundColor Red
    Write-Host "💡 Créez-le avec: az keyvault create --name $KeyVaultName --resource-group $ResourceGroup --location westeurope" -ForegroundColor Yellow
    exit 1
}

# Fonction pour créer un secret
function Create-Secret {
    param(
        [string]$SecretName,
        [string]$SecretValue,
        [string]$Description
    )
    
    if ($SecretValue -like "YOUR_ACTUAL_*" -or [string]::IsNullOrEmpty($SecretValue)) {
        Write-Host "⚠️  Ignorer $SecretName (valeur par défaut non remplacée)" -ForegroundColor Yellow
        return
    }
    
    Write-Host "🔑 Création du secret: $SecretName" -ForegroundColor Blue
    
    try {
        az keyvault secret set `
            --vault-name $KeyVaultName `
            --name $SecretName `
            --value $SecretValue `
            --description $Description `
            --output none
        
        Write-Host "   ✅ $SecretName créé avec succès" -ForegroundColor Green
    }
    catch {
        Write-Host "   ❌ Erreur lors de la création de $SecretName" -ForegroundColor Red
        Write-Host "   Erreur: $($_.Exception.Message)" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "🚀 Création des secrets..." -ForegroundColor Cyan
Write-Host "==========================" -ForegroundColor Cyan

# =================================================================
# SECRETS CONFIGURATION
# =================================================================

# 📊 Cosmos DB
Write-Host ""
Write-Host "📊 Secrets Cosmos DB..." -ForegroundColor Magenta

Create-Secret -SecretName "cosmos-key" `
    -SecretValue "YOUR_ACTUAL_COSMOS_PRIMARY_KEY" `
    -Description "Cosmos DB Primary Key pour MasterTrade"

Create-Secret -SecretName "cosmos-endpoint" `
    -SecretValue "https://tradebot.documents.azure.com:443/" `
    -Description "Cosmos DB Endpoint URL"

Create-Secret -SecretName "cosmos-database" `
    -SecretValue "mmasterTrade" `
    -Description "Nom de la base de données Cosmos DB"

# 💱 Binance Exchange
Write-Host ""
Write-Host "💱 Secrets Binance..." -ForegroundColor Magenta

Create-Secret -SecretName "binance-api-key" `
    -SecretValue "YOUR_BINANCE_PRODUCTION_API_KEY" `
    -Description "Binance Production API Key"

Create-Secret -SecretName "binance-api-secret" `
    -SecretValue "YOUR_BINANCE_PRODUCTION_SECRET_KEY" `
    -Description "Binance Production API Secret"

Create-Secret -SecretName "binance-testnet-api-key" `
    -SecretValue "YOUR_BINANCE_TESTNET_API_KEY" `
    -Description "Binance Testnet API Key pour les tests"

Create-Secret -SecretName "binance-testnet-api-secret" `
    -SecretValue "YOUR_BINANCE_TESTNET_SECRET_KEY" `
    -Description "Binance Testnet API Secret pour les tests"

# 📨 RabbitMQ
Write-Host ""
Write-Host "📨 Secrets RabbitMQ..." -ForegroundColor Magenta

Create-Secret -SecretName "rabbitmq-url" `
    -SecretValue "amqp://mastertrade:YOUR_RABBITMQ_PASSWORD@localhost:5672/" `
    -Description "URL complète RabbitMQ avec authentification"

Create-Secret -SecretName "rabbitmq-user" `
    -SecretValue "mastertrade" `
    -Description "Utilisateur RabbitMQ"

Create-Secret -SecretName "rabbitmq-password" `
    -SecretValue "YOUR_SECURE_RABBITMQ_PASSWORD" `
    -Description "Mot de passe RabbitMQ"

# 🌐 APIs externes
Write-Host ""
Write-Host "🌐 Secrets APIs externes..." -ForegroundColor Magenta

Create-Secret -SecretName "alpha-vantage-api-key" `
    -SecretValue "YOUR_ALPHA_VANTAGE_API_KEY" `
    -Description "Alpha Vantage API Key pour données financières"

Create-Secret -SecretName "finnhub-api-key" `
    -SecretValue "YOUR_FINNHUB_API_KEY" `
    -Description "Finnhub API Key pour données de marché"

Create-Secret -SecretName "newsapi-key" `
    -SecretValue "YOUR_NEWSAPI_KEY" `
    -Description "NewsAPI Key pour analyse des sentiments"

Create-Secret -SecretName "polygon-api-key" `
    -SecretValue "YOUR_POLYGON_API_KEY" `
    -Description "Polygon.io API Key pour données US"

# 🔒 Sécurité
Write-Host ""
Write-Host "🔒 Secrets de sécurité..." -ForegroundColor Magenta

Create-Secret -SecretName "jwt-secret" `
    -SecretValue "YOUR_STRONG_JWT_SECRET_KEY_256_BITS" `
    -Description "Clé secrète JWT pour authentification"

Create-Secret -SecretName "api-encryption-key" `
    -SecretValue "YOUR_API_ENCRYPTION_KEY_256_BITS" `
    -Description "Clé de chiffrement API"

# 📦 Redis
Write-Host ""
Write-Host "📦 Secrets Redis..." -ForegroundColor Magenta

Create-Secret -SecretName "redis-url" `
    -SecretValue "redis://localhost:6379" `
    -Description "URL Redis"

Create-Secret -SecretName "redis-password" `
    -SecretValue "YOUR_REDIS_PASSWORD" `
    -Description "Mot de passe Redis (optionnel)"

# 📈 Monitoring
Write-Host ""
Write-Host "📈 Secrets Monitoring..." -ForegroundColor Magenta

Create-Secret -SecretName "grafana-password" `
    -SecretValue "YOUR_SECURE_GRAFANA_PASSWORD" `
    -Description "Mot de passe Admin Grafana"

# =================================================================
# VÉRIFICATION FINALE
# =================================================================

Write-Host ""
Write-Host "🔍 Vérification des secrets créés..." -ForegroundColor Cyan
Write-Host "=====================================" -ForegroundColor Cyan

try {
    $secretCount = az keyvault secret list --vault-name $KeyVaultName --query "length(@)" -o tsv
    Write-Host "📊 Nombre total de secrets dans Key Vault: $secretCount" -ForegroundColor Green
    
    Write-Host ""
    Write-Host "📋 Liste des secrets:" -ForegroundColor Yellow
    az keyvault secret list --vault-name $KeyVaultName --query "[].name" -o table
}
catch {
    Write-Host "❌ Erreur lors de la vérification des secrets" -ForegroundColor Red
}

Write-Host ""
Write-Host "✅ Configuration terminée !" -ForegroundColor Green
Write-Host ""
Write-Host "🎯 Prochaines étapes:" -ForegroundColor Cyan
Write-Host "   1. Vérifiez que tous vos secrets ont des vraies valeurs" -ForegroundColor White
Write-Host "   2. Testez la connexion avec: az keyvault secret show --vault-name $KeyVaultName --name cosmos-key" -ForegroundColor White
Write-Host "   3. Mettez à jour USE_KEY_VAULT=true dans vos services" -ForegroundColor White
Write-Host "   4. Redémarrez les services MasterTrade" -ForegroundColor White
Write-Host ""
Write-Host "⚠️  Rappel sécurité:" -ForegroundColor Red
Write-Host "   - Ne partagez jamais ces scripts avec de vraies valeurs" -ForegroundColor Yellow
Write-Host "   - Activez l'audit sur Key Vault" -ForegroundColor Yellow
Write-Host "   - Rotez régulièrement les clés API" -ForegroundColor Yellow