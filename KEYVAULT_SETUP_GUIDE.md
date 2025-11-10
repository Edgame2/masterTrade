# Guide de Configuration Azure Key Vault - MasterTrade
## 🔐 Configuration Rapide des Secrets

### 📋 Liste des Secrets Requis

| Catégorie | Nom du Secret | Description | Priorité |
|-----------|---------------|-------------|----------|
| **🗄️ Base de Données** | `cosmos-key` | Clé primaire Cosmos DB | 🔴 Critique |
| | `cosmos-endpoint` | URL endpoint Cosmos DB | 🔴 Critique |
| | `cosmos-database` | Nom de la base de données | 🔴 Critique |
| **💱 Exchange** | `binance-testnet-api-key` | Clé API Binance testnet | 🟡 Important |
| | `binance-testnet-api-secret` | Secret API Binance testnet | 🟡 Important |
| | `binance-api-key` | Clé API Binance production | 🟠 Production |
| | `binance-api-secret` | Secret API Binance production | 🟠 Production |
| **📨 Messaging** | `rabbitmq-url` | URL complète RabbitMQ | 🟡 Important |
| | `rabbitmq-password` | Mot de passe RabbitMQ | 🟡 Important |
| **🔒 Sécurité** | `jwt-secret` | Clé JWT (256 bits min) | 🔴 Critique |
| | `api-encryption-key` | Clé de chiffrement API | 🟡 Important |
| **📊 APIs Externes** | `alpha-vantage-api-key` | Alpha Vantage API | 🔵 Optionnel |
| | `finnhub-api-key` | Finnhub API | 🔵 Optionnel |
| | `newsapi-key` | NewsAPI | 🔵 Optionnel |
| | `polygon-api-key` | Polygon.io API | 🔵 Optionnel |

### 🚀 Méthodes de Configuration

#### Option 1: Script Automatisé (Recommandé)
```bash
# 1. Cloner et modifier le script
cp setup-keyvault-secrets.sh my-secrets.sh

# 2. Remplacer les valeurs YOUR_ACTUAL_* par vos vraies valeurs
nano my-secrets.sh

# 3. Exécuter
chmod +x my-secrets.sh
./my-secrets.sh
```

#### Option 2: Azure CLI Manuel
```bash
# Exemple pour les secrets critiques
az keyvault secret set --vault-name "mastertrade" --name "cosmos-key" --value "VOTRE_CLE_COSMOS"
az keyvault secret set --vault-name "mastertrade" --name "jwt-secret" --value "VOTRE_CLE_JWT_256_BITS"
az keyvault secret set --vault-name "mastertrade" --name "binance-testnet-api-key" --value "VOTRE_CLE_BINANCE_TEST"
```

#### Option 3: Portail Azure
1. Aller sur https://portal.azure.com
2. Rechercher "Key Vaults" → Sélectionner "mastertrade"
3. Cliquer sur "Secrets" dans le menu de gauche
4. Cliquer "+ Generate/Import" pour chaque secret

### 🎯 Configuration Minimale pour Commencer

Pour faire fonctionner le système avec les fonctionnalités de base :

```bash
# Secrets essentiels (minimum viable)
az keyvault secret set --vault-name "mastertrade" --name "cosmos-key" --value "YOUR_COSMOS_KEY"
az keyvault secret set --vault-name "mastertrade" --name "jwt-secret" --value "$(openssl rand -base64 32)"
az keyvault secret set --vault-name "mastertrade" --name "rabbitmq-password" --value "secure_password_123"
az keyvault secret set --vault-name "mastertrade" --name "binance-testnet-api-key" --value "YOUR_TESTNET_KEY"
az keyvault secret set --vault-name "mastertrade" --name "binance-testnet-api-secret" --value "YOUR_TESTNET_SECRET"
```

### 📝 Génération de Clés Sécurisées

```bash
# JWT Secret (256 bits)
openssl rand -base64 32

# API Encryption Key (256 bits)  
openssl rand -hex 32

# Mot de passe fort
openssl rand -base64 16
```

### 🔍 Vérification de la Configuration

```bash
# Lister tous les secrets
az keyvault secret list --vault-name "mastertrade" --query "[].name" -o table

# Tester l'accès à un secret (sans révéler la valeur)
az keyvault secret show --vault-name "mastertrade" --name "cosmos-key" --query "attributes"

# Vérifier les permissions
az keyvault show --name "mastertrade" --query "properties.accessPolicies[].permissions"
```

### 🛡️ Configuration des Permissions

Votre Service Principal a déjà les bonnes permissions, mais pour référence :

```bash
# Ajouter des permissions à un utilisateur/application
az keyvault set-policy \
  --name "mastertrade" \
  --object-id "OBJECT_ID" \
  --secret-permissions get list set delete
```

### 🔧 Activation dans les Services

Après création des secrets, activez Key Vault dans vos services :

```bash
# Dans chaque service, mettre à jour la configuration
export USE_KEY_VAULT=true
export AZURE_KEY_VAULT_URL="https://mastertrade.vault.azure.net/"

# Ou modifier les fichiers .env des services
echo "USE_KEY_VAULT=true" >> api_gateway/.env
echo "USE_KEY_VAULT=true" >> market_data_service/.env
# etc.
```

### ❗ Erreurs Communes et Solutions

#### Erreur: "Access denied"
```bash
# Solution: Vérifier les permissions
az keyvault show --name "mastertrade" --query "properties.accessPolicies"
```

#### Erreur: "Key Vault not found"
```bash
# Solution: Vérifier l'existence et l'accès
az keyvault list --query "[?name=='mastertrade']"
```

#### Erreur: "Authentication failed"
```bash
# Solution: Re-authentifier
az login
az account set --subscription "YOUR_SUBSCRIPTION_ID"
```

### 🔄 Maintenance

#### Rotation des Secrets
```bash
# Exemple de rotation d'une clé JWT
NEW_JWT=$(openssl rand -base64 32)
az keyvault secret set --vault-name "mastertrade" --name "jwt-secret" --value "$NEW_JWT"

# Redémarrer les services pour prendre en compte la nouvelle clé
```

#### Backup des Secrets
```bash
# Exporter la liste des secrets (sans les valeurs)
az keyvault secret list --vault-name "mastertrade" > secrets-backup.json
```

### 📞 Support

En cas de problème :
1. Vérifiez les logs des services : `docker logs [service-name]`
2. Testez la connectivité Key Vault : `az keyvault secret show --vault-name mastertrade --name cosmos-key`
3. Vérifiez les permissions : Service Principal doit avoir les droits "Get", "List" sur les secrets

### 🎉 Test Final

Une fois tous les secrets configurés :

```bash
# Test de connectivité complète
cd /home/neodyme/Documents/Projects/masterTrade
./test_multi_environment_execution.py
```

Le système devrait maintenant fonctionner avec une sécurité renforcée via Azure Key Vault !