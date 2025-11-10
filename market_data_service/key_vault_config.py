"""
Azure Key Vault Integration for Market Data Service

This module provides secure configuration management using Azure Key Vault.
It replaces direct environment variables with Key Vault secrets for production security.
"""

import os
import asyncio
from typing import Dict, Optional, Any
import structlog
from azure.keyvault.secrets.aio import SecretClient
from azure.identity.aio import DefaultAzureCredential, ChainedTokenCredential, ManagedIdentityCredential
from azure.core.exceptions import ResourceNotFoundError, AzureError

logger = structlog.get_logger()


class KeyVaultConfig:
    """Azure Key Vault configuration manager"""
    
    def __init__(self, vault_url: str = None):
        self.vault_url = vault_url or os.getenv("AZURE_KEY_VAULT_URL", "")
        self.client: Optional[SecretClient] = None
        self.credential = None
        self._secret_cache: Dict[str, str] = {}
        self._initialized = False
        
    async def __aenter__(self):
        """Async context manager entry"""
        await self.initialize()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close()
        
    async def initialize(self):
        """Initialize Key Vault client with proper authentication"""
        try:
            if self._initialized:
                return
                
            if not self.vault_url:
                logger.warning("No Azure Key Vault URL provided, falling back to environment variables")
                return
                
            logger.info("Initializing Azure Key Vault client", vault_url=self.vault_url)
            
            # Create credential chain for authentication
            # Try managed identity first (production), then default credential (development)
            managed_identity_credential = ManagedIdentityCredential(
                client_id=os.getenv("AZURE_CLIENT_ID")  # Optional for user-assigned MI
            )
            
            self.credential = ChainedTokenCredential(
                managed_identity_credential,
                DefaultAzureCredential()
            )
            
            # Create Key Vault client
            self.client = SecretClient(
                vault_url=self.vault_url, 
                credential=self.credential
            )
            
            # Test connection by listing secrets (requires Key Vault Reader permission)
            try:
                secret_properties = []
                async for secret_property in self.client.list_properties_of_secrets():
                    secret_properties.append(secret_property.name)
                    if len(secret_properties) >= 1:  # Just test with first secret
                        break
                        
                logger.info("Azure Key Vault connection successful", 
                           vault_url=self.vault_url,
                           secrets_available=len(secret_properties))
                self._initialized = True
                
            except Exception as e:
                logger.error("Failed to connect to Azure Key Vault", 
                           vault_url=self.vault_url, error=str(e))
                # Don't raise error - allow fallback to env vars
                
        except Exception as e:
            logger.error("Error initializing Key Vault client", error=str(e))
            # Continue without Key Vault - will fall back to environment variables
            
    async def close(self):
        """Close Key Vault connections"""
        try:
            if self.client:
                await self.client.close()
            if self.credential:
                await self.credential.close()
        except Exception as e:
            logger.error("Error closing Key Vault connections", error=str(e))
            
    async def get_secret(self, secret_name: str, default_value: str = "") -> str:
        """
        Get secret from Key Vault with fallback to environment variables
        
        Args:
            secret_name: Name of the secret in Key Vault
            default_value: Default value if secret not found
            
        Returns:
            Secret value or default value
        """
        try:
            # Check cache first
            if secret_name in self._secret_cache:
                return self._secret_cache[secret_name]
                
            # Try Key Vault if initialized
            if self._initialized and self.client:
                try:
                    secret = await self.client.get_secret(secret_name)
                    value = secret.value
                    
                    # Cache the secret (consider security implications in production)
                    self._secret_cache[secret_name] = value
                    
                    logger.debug("Retrieved secret from Key Vault", secret_name=secret_name)
                    return value
                    
                except ResourceNotFoundError:
                    logger.warning("Secret not found in Key Vault", secret_name=secret_name)
                except Exception as e:
                    logger.error("Error retrieving secret from Key Vault", 
                               secret_name=secret_name, error=str(e))
            
            # Fallback to environment variable
            env_value = os.getenv(secret_name, default_value)
            if env_value:
                logger.debug("Using environment variable fallback", secret_name=secret_name)
                self._secret_cache[secret_name] = env_value
                return env_value
            else:
                logger.warning("Secret not found in Key Vault or environment", 
                             secret_name=secret_name)
                return default_value
                
        except Exception as e:
            logger.error("Error getting secret", secret_name=secret_name, error=str(e))
            return default_value
            
    async def get_secrets_batch(self, secret_names: Dict[str, str]) -> Dict[str, str]:
        """
        Get multiple secrets in batch for efficiency
        
        Args:
            secret_names: Dict mapping secret names to default values
            
        Returns:
            Dict of secret names to values
        """
        results = {}
        
        # Process secrets concurrently for better performance
        tasks = []
        for name, default in secret_names.items():
            task = asyncio.create_task(self.get_secret(name, default))
            tasks.append((name, task))
            
        # Wait for all tasks to complete
        for name, task in tasks:
            try:
                results[name] = await task
            except Exception as e:
                logger.error("Error in batch secret retrieval", secret_name=name, error=str(e))
                results[name] = secret_names[name]  # Use default value
                
        return results
        
    def clear_cache(self):
        """Clear the secret cache (useful for credential rotation)"""
        self._secret_cache.clear()
        logger.info("Key Vault secret cache cleared")


# Global Key Vault instance
key_vault_config = KeyVaultConfig()


async def load_secrets_from_keyvault() -> Dict[str, str]:
    """
    Load all required secrets from Key Vault
    
    Returns:
        Dictionary of configuration values
    """
    
    # Define all secrets we need to load
    required_secrets = {
        # Azure Configuration
        "COSMOS-ENDPOINT": "https://your-account.documents.azure.com:443/",
        "COSMOS-DATABASE": "mastertrade",
        "MANAGED-IDENTITY-CLIENT-ID": "",
        
        # RabbitMQ Configuration
        "RABBITMQ-URL": "amqp://admin:password123@localhost:5672/",
        
        # Binance API Configuration
        "BINANCE-API-KEY": "",
        "BINANCE-API-SECRET": "",
        
        # Stock Index APIs
        "ALPHA-VANTAGE-API-KEY": "",
        "FINNHUB-API-KEY": "",
        
        # Sentiment Analysis APIs
        "NEWS-API-KEY": "",
        "TWITTER-BEARER-TOKEN": "",
        "REDDIT-CLIENT-ID": "",
        "REDDIT-CLIENT-SECRET": "",
        
        # Service Configuration
        "LOG-LEVEL": "INFO"
    }
    
    try:
        async with key_vault_config as kv:
            secrets = await kv.get_secrets_batch(required_secrets)
            
            # Convert back to standard environment variable format
            env_secrets = {}
            for kv_name, value in secrets.items():
                env_name = kv_name.replace("-", "_")
                env_secrets[env_name] = value
                
            logger.info("Loaded configuration from Key Vault", 
                       secrets_loaded=len([v for v in secrets.values() if v]),
                       total_secrets=len(required_secrets))
                       
            return env_secrets
            
    except Exception as e:
        logger.error("Error loading secrets from Key Vault", error=str(e))
        # Return empty dict to fall back to environment variables
        return {}


def get_keyvault_url_from_env() -> str:
    """Get Key Vault URL from environment or construct from name"""
    # Try direct URL first
    vault_url = os.getenv("AZURE_KEY_VAULT_URL", "")
    if vault_url:
        return vault_url
        
    # Try to construct from vault name
    vault_name = os.getenv("AZURE_KEY_VAULT_NAME", "")
    if vault_name:
        return f"https://{vault_name}.vault.azure.net/"
        
    return ""


# Initialize Key Vault URL from environment
key_vault_config.vault_url = get_keyvault_url_from_env()