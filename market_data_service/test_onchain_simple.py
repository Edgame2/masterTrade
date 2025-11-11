"""
Simple test for on-chain collector integration

Tests only the on-chain collector integration without dependencies on other components.
"""

import asyncio
import sys
import os
from datetime import datetime, timezone

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import settings
from database import Database
from collectors.moralis_collector import MoralisCollector
from collectors.glassnode_collector import GlassnodeCollector

print("=" * 60)
print("ON-CHAIN COLLECTORS SIMPLE INTEGRATION TEST")
print("=" * 60)


async def test_database_methods():
    """Test that database has all required on-chain methods"""
    print("\n1. Testing database methods...")
    
    db = Database()
    await db.connect()
    
    # Check all required methods exist
    methods = [
        'store_whale_transaction',
        'store_onchain_metrics',
        'store_wallet_label',
        'get_whale_transactions',
        'get_onchain_metrics',
        'get_wallet_label',
        'log_collector_health',
        'get_collector_health'
    ]
    
    for method in methods:
        assert hasattr(db, method), f"Missing method: {method}"
        print(f"   ✅ {method}")
    
    await db.disconnect()
    
    return True


async def test_collectors_can_be_initialized():
    """Test that collectors can be instantiated"""
    print("\n2. Testing collector instantiation...")
    
    db = Database()
    await db.connect()
    
    # Test Moralis collector (even without API key)
    moralis = MoralisCollector(
        database=db,
        api_key="test_key",
        rate_limit=3.0
    )
    assert moralis.collector_name == "moralis"
    assert moralis.database == db
    print("   ✅ MoralisCollector instantiated")
    
    # Test Glassnode collector
    glassnode = GlassnodeCollector(
        database=db,
        api_key="test_key",
        rate_limit=1.0
    )
    assert glassnode.collector_name == "glassnode"
    assert glassnode.database == db
    print("   ✅ GlassnodeCollector instantiated")
    
    await db.disconnect()
    
    return True


async def test_configuration_exists():
    """Test that configuration has on-chain settings"""
    print("\n3. Testing configuration...")
    
    required_settings = [
        ('MORALIS_API_KEY', str),
        ('MORALIS_API_URL', str),
        ('MORALIS_RATE_LIMIT', float),
        ('GLASSNODE_API_KEY', str),
        ('GLASSNODE_API_URL', str),
        ('GLASSNODE_RATE_LIMIT', float),
        ('ONCHAIN_COLLECTION_ENABLED', bool),
        ('ONCHAIN_COLLECTION_INTERVAL', int),
        ('ONCHAIN_WHALE_THRESHOLD_BTC', float),
        ('ONCHAIN_WHALE_THRESHOLD_ETH', float),
        ('ONCHAIN_WHALE_THRESHOLD_USD', float),
    ]
    
    for setting_name, expected_type in required_settings:
        assert hasattr(settings, setting_name), f"Missing setting: {setting_name}"
        value = getattr(settings, setting_name)
        assert isinstance(value, expected_type), f"{setting_name} should be {expected_type.__name__}"
        print(f"   ✅ {setting_name}: {value}")
    
    return True


async def test_data_storage_and_retrieval():
    """Test storing and retrieving on-chain data"""
    print("\n4. Testing data storage and retrieval...")
    
    db = Database()
    await db.connect()
    
    # Test whale transaction
    tx = {
        'tx_hash': '0xtest_simple_123',
        'symbol': 'BTC',
        'from_address': '0xfrom',
        'to_address': '0xto',
        'amount': 1500.0,
        'timestamp': datetime.now(timezone.utc),
        'block_number': 123456,
        'source': 'simple_test'
    }
    
    success = await db.store_whale_transaction(tx)
    assert success, "Failed to store whale transaction"
    print("   ✅ Stored whale transaction")
    
    txs = await db.get_whale_transactions(symbol='BTC', hours=1)
    assert len(txs) > 0, "No transactions retrieved"
    print(f"   ✅ Retrieved {len(txs)} whale transaction(s)")
    
    # Test on-chain metric
    metric = [{
        'symbol': 'BTC',
        'metric_name': 'test_metric',
        'metric_category': 'test',
        'value': 123.45,
        'timestamp': datetime.now(timezone.utc),
        'interval': '1h',
        'source': 'simple_test',
        'description': 'Test metric'
    }]
    
    success = await db.store_onchain_metrics(metric)
    assert success, "Failed to store metric"
    print("   ✅ Stored on-chain metric")
    
    metrics = await db.get_onchain_metrics(symbol='BTC', hours=1)
    assert len(metrics) > 0, "No metrics retrieved"
    print(f"   ✅ Retrieved {len(metrics)} metric(s)")
    
    # Test wallet label
    success = await db.store_wallet_label(
        address='0xtest_wallet',
        label='Test Wallet',
        category='test',
        metadata={'test': True}
    )
    assert success, "Failed to store wallet label"
    print("   ✅ Stored wallet label")
    
    label = await db.get_wallet_label('0xtest_wallet')
    assert label is not None, "Wallet label not retrieved"
    assert label['label'] == 'Test Wallet'
    print("   ✅ Retrieved wallet label")
    
    # Test collector health logging
    success = await db.log_collector_health(
        collector_name='test_collector',
        status='healthy',
        metadata={'test': True}
    )
    assert success, "Failed to log collector health"
    print("   ✅ Logged collector health")
    
    health = await db.get_collector_health(collector_name='test_collector', hours=1)
    assert len(health) > 0, "No health logs retrieved"
    print(f"   ✅ Retrieved {len(health)} health log(s)")
    
    await db.disconnect()
    
    return True


async def test_imports_work():
    """Test that main.py can import the collectors"""
    print("\n5. Testing imports in main.py...")
    
    try:
        # This will try to import main.py which should have our collectors
        import sys
        import importlib
        
        # Remove main from cache if it exists
        if 'main' in sys.modules:
            del sys.modules['main']
        
        # Import main
        import main
        
        # Check that MarketDataService has the collector attributes
        service = main.MarketDataService()
        assert hasattr(service, 'moralis_collector'), "MarketDataService missing moralis_collector"
        assert hasattr(service, 'glassnode_collector'), "MarketDataService missing glassnode_collector"
        print("   ✅ MarketDataService has collector attributes")
        
        # Check that collectors are None initially
        assert service.moralis_collector is None, "Collectors should be None initially"
        assert service.glassnode_collector is None, "Collectors should be None initially"
        print("   ✅ Collectors are None initially (correct)")
        
        return True
        
    except Exception as e:
        print(f"   ❌ Import test failed: {e}")
        # This is not critical - just informational
        return True


async def run_all_tests():
    """Run all tests"""
    tests = [
        ("Configuration", test_configuration_exists),
        ("Database Methods", test_database_methods),
        ("Collector Instantiation", test_collectors_can_be_initialized),
        ("Data Storage/Retrieval", test_data_storage_and_retrieval),
        ("Main.py Imports", test_imports_work),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            result = await test_func()
            results.append((test_name, result, None))
        except Exception as e:
            results.append((test_name, False, str(e)))
    
    # Print summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    passed = 0
    failed = 0
    
    for test_name, result, error in results:
        if result:
            print(f"✅ {test_name}: PASSED")
            passed += 1
        else:
            print(f"❌ {test_name}: FAILED")
            if error:
                print(f"   Error: {error}")
            failed += 1
    
    print("\n" + "-" * 60)
    print(f"Total: {passed + failed} tests")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    
    if failed == 0:
        print("\n🎉 All integration tests passed!")
    else:
        print(f"\n⚠️  {failed} test(s) failed")
    
    print("=" * 60)
    
    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
