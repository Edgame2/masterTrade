#!/usr/bin/env python3
"""
Test script for Azure Key Vault integration
"""

import asyncio
import sys
import os
from datetime import datetime

# Add the current directory to Python path
sys.path.append('.')

async def test_keyvault_integration():
    """Test Azure Key Vault integration"""
    
    print("🔐 Testing Azure Key Vault Integration")
    print("=" * 45)
    
    # Test 1: Check environment variables
    print("\n📋 Test 1: Check Key Vault environment variables")
    vault_url = os.getenv("AZURE_KEY_VAULT_URL", "")
    vault_name = os.getenv("AZURE_KEY_VAULT_NAME", "")
    use_kv = os.getenv("USE_KEY_VAULT", "false").lower() == "true"
    
    print(f"Key Vault URL: {vault_url or 'Not set'}")
    print(f"Key Vault Name: {vault_name or 'Not set'}")
    print(f"Use Key Vault: {use_kv}")
    
    if not vault_url and not vault_name:
        print("⚠️  No Key Vault configuration found")
        print("💡 Set AZURE_KEY_VAULT_URL or AZURE_KEY_VAULT_NAME environment variable")
        print("💡 For testing, you can use: export AZURE_KEY_VAULT_URL='https://your-keyvault.vault.azure.net/'")
    
    # Test 2: Test Key Vault client initialization
    print("\n📋 Test 2: Initialize Key Vault client")
    try:
        from key_vault_config import KeyVaultConfig
        
        kv_config = KeyVaultConfig(vault_url or f"https://{vault_name}.vault.azure.net/" if vault_name else "")
        
        async with kv_config as kv:
            print("✅ Key Vault client initialized successfully")
            
            # Test 3: Test secret retrieval
            print("\n📋 Test 3: Test secret retrieval")
            
            # Test with a non-existent secret (should fall back to env var)
            test_secret = await kv.get_secret("TEST_SECRET", "default_value")
            print(f"Test secret retrieval: {test_secret}")
            
            # Test batch secret loading
            test_secrets = {
                "LOG_LEVEL": "INFO",
                "SERVICE_NAME": "market_data_service", 
                "NONEXISTENT_SECRET": "default"
            }
            
            batch_results = await kv.get_secrets_batch(test_secrets)
            print(f"Batch secret results: {len(batch_results)} secrets loaded")
            
            for name, value in batch_results.items():
                print(f"  {name}: {'*' * len(value) if value and name.endswith('KEY') else value}")
    
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("💡 Make sure azure-keyvault-secrets is installed: pip install azure-keyvault-secrets")
        return
    except Exception as e:
        print(f"⚠️  Key Vault client error: {e}")
        print("💡 This is expected if Key Vault is not configured or accessible")
    
    # Test 4: Test configuration loading
    print("\n📋 Test 4: Test configuration loading with Key Vault")
    try:
        from config import initialize_settings, settings
        
        print("Loading configuration...")
        await initialize_settings()
        
        print("✅ Configuration loaded successfully")
        print(f"Service name: {settings.SERVICE_NAME}")
        print(f"Log level: {settings.LOG_LEVEL}")
        print(f"Use Key Vault: {settings.USE_KEY_VAULT}")
        print(f"Cosmos endpoint: {settings.COSMOS_ENDPOINT[:30]}..." if settings.COSMOS_ENDPOINT else "Not set")
        
    except Exception as e:
        print(f"❌ Configuration loading error: {e}")
    
    # Test 5: Test Azure authentication
    print("\n📋 Test 5: Test Azure authentication")
    try:
        from azure.identity.aio import DefaultAzureCredential
        
        credential = DefaultAzureCredential()
        
        # Try to get a token (this will test if authentication works)
        try:
            # Test with Key Vault scope
            token = await credential.get_token("https://vault.azure.net/.default")
            if token:
                print("✅ Azure authentication successful")
                print(f"Token expires: {datetime.fromtimestamp(token.expires_on)}")
            else:
                print("❌ Failed to get authentication token")
        except Exception as auth_error:
            print(f"⚠️  Authentication test failed: {auth_error}")
            print("💡 For local testing, run: az login")
            print("💡 For production, ensure managed identity is configured")
        finally:
            await credential.close()
            
    except ImportError:
        print("❌ Azure Identity library not available")
    except Exception as e:
        print(f"❌ Azure authentication error: {e}")
    
    print(f"\n🔐 Key Vault integration test completed!")
    
    # Summary and next steps
    print(f"\n📋 Summary and Next Steps:")
    print("1. ✅ Ensure Azure CLI is installed and you're logged in: az login")
    print("2. 🔧 Run setup script to create Key Vault: ./setup_keyvault.sh")
    print("3. 🔑 Update secrets with real API keys in Azure Portal or CLI")
    print("4. 🚀 Deploy with managed identity for production security")
    print("")
    print("Environment variables for testing:")
    print(f"export AZURE_KEY_VAULT_URL='https://your-keyvault.vault.azure.net/'")
    print(f"export USE_KEY_VAULT='true'")

if __name__ == "__main__":
    # Run the test
    asyncio.run(test_keyvault_integration())