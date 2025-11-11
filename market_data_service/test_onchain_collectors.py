"""
Test suite for on-chain data collectors

Tests:
- OnChainCollector base class functionality
- MoralisCollector whale transaction detection
- GlassnodeCollector metrics collection
- Database methods for on-chain data
- Circuit breaker and rate limiting
"""

import asyncio
from datetime import datetime, timezone
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import Database
from collectors.moralis_collector import MoralisCollector
from collectors.glassnode_collector import GlassnodeCollector
from collectors.onchain_collector import CircuitBreaker, RateLimiter
from config import settings

print("=" * 60)
print("ON-CHAIN COLLECTORS TEST SUITE")
print("=" * 60)


async def test_database_schema():
    """Test that on-chain tables are created"""
    print("\n1. Testing database schema creation...")
    
    db = Database()
    await db.connect()
    
    # Check if tables exist
    query = """
        SELECT tablename FROM pg_tables 
        WHERE schemaname = 'public' 
        AND tablename IN ('whale_transactions', 'onchain_metrics', 'wallet_labels', 'collector_health')
    """
    
    tables = await db._postgres.fetch(query)
    table_names = [row['tablename'] for row in tables]
    
    expected_tables = ['whale_transactions', 'onchain_metrics', 'wallet_labels', 'collector_health']
    
    for table in expected_tables:
        if table in table_names:
            print(f"   ✅ Table '{table}' exists")
        else:
            print(f"   ❌ Table '{table}' missing")
    
    await db.disconnect()
    
    return all(t in table_names for t in expected_tables)


async def test_circuit_breaker():
    """Test circuit breaker functionality"""
    print("\n2. Testing circuit breaker...")
    
    cb = CircuitBreaker(failure_threshold=3, timeout_seconds=5)
    
    # Test initial state
    assert cb.state == "closed", "Initial state should be closed"
    assert cb.can_attempt() == True, "Should allow attempts when closed"
    print("   ✅ Initial state: closed, allows attempts")
    
    # Record failures
    for i in range(3):
        cb.record_failure()
    
    assert cb.state == "open", "Should open after threshold failures"
    assert cb.can_attempt() == False, "Should not allow attempts when open"
    print("   ✅ Opens after 3 failures, blocks attempts")
    
    # Test recovery
    await asyncio.sleep(6)  # Wait for timeout
    assert cb.can_attempt() == True, "Should allow attempt after timeout"
    assert cb.state == "half-open", "Should be half-open after timeout"
    print("   ✅ Transitions to half-open after timeout")
    
    # Test success recovery
    cb.record_success()
    assert cb.state == "closed", "Should close after success"
    assert cb.failure_count == 0, "Should reset failure count"
    print("   ✅ Closes and resets after success")
    
    return True


async def test_rate_limiter():
    """Test rate limiter functionality"""
    print("\n3. Testing rate limiter...")
    
    rl = RateLimiter(max_requests_per_second=5.0)
    
    # Test rate limiting
    start_time = datetime.now(timezone.utc)
    
    for i in range(5):
        await rl.wait()
    
    elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
    
    # Should take at least 0.8 seconds for 5 requests at 5 req/s
    assert elapsed >= 0.8, f"Rate limiting too fast: {elapsed}s"
    assert rl.request_count == 5, f"Wrong request count: {rl.request_count}"
    print(f"   ✅ Rate limited 5 requests in {elapsed:.2f}s")
    
    # Test adaptive rate adjustment
    rl.adjust_rate(3.0)  # Slow response
    assert rl.max_requests_per_second < 5.0, "Should decrease rate on slow response"
    print(f"   ✅ Adjusted rate down to {rl.max_requests_per_second:.2f} req/s")
    
    rl.adjust_rate(0.3)  # Fast response
    old_rate = rl.max_requests_per_second
    rl.adjust_rate(0.3)
    assert rl.max_requests_per_second > old_rate, "Should increase rate on fast response"
    print(f"   ✅ Adjusted rate up to {rl.max_requests_per_second:.2f} req/s")
    
    return True


async def test_database_methods():
    """Test database methods for on-chain data"""
    print("\n4. Testing database methods...")
    
    db = Database()
    await db.connect()
    
    # Test whale transaction storage
    tx_data = {
        "tx_hash": "0xtest123456789",
        "symbol": "BTC",
        "from_address": "0xfrom123",
        "to_address": "0xto456",
        "amount": 1500.5,
        "timestamp": datetime.now(timezone.utc),
        "block_number": 12345678,
        "source": "test"
    }
    
    success = await db.store_whale_transaction(tx_data)
    assert success, "Failed to store whale transaction"
    print("   ✅ Stored whale transaction")
    
    # Retrieve whale transactions
    transactions = await db.get_whale_transactions(symbol="BTC", hours=24, limit=10)
    assert len(transactions) > 0, "No transactions retrieved"
    assert transactions[0]["tx_hash"] == "0xtest123456789", "Wrong transaction retrieved"
    print(f"   ✅ Retrieved {len(transactions)} whale transaction(s)")
    
    # Test on-chain metrics storage
    metric_data = [{
        "symbol": "BTC",
        "metric_name": "nvt",
        "metric_category": "valuation",
        "value": 95.5,
        "timestamp": datetime.now(timezone.utc),
        "interval": "24h",
        "source": "test",
        "description": "Network Value to Transactions"
    }]
    
    success = await db.store_onchain_metrics(metric_data)
    assert success, "Failed to store on-chain metrics"
    print("   ✅ Stored on-chain metric")
    
    # Retrieve metrics
    metrics = await db.get_onchain_metrics(symbol="BTC", metric_name="nvt", hours=24)
    assert len(metrics) > 0, "No metrics retrieved"
    assert metrics[0]["metric_name"] == "nvt", "Wrong metric retrieved"
    print(f"   ✅ Retrieved {len(metrics)} metric(s)")
    
    # Test wallet label storage
    success = await db.store_wallet_label(
        address="0xwhale123",
        label="Known Whale #1",
        category="whale",
        metadata={"source": "manual"}
    )
    assert success, "Failed to store wallet label"
    print("   ✅ Stored wallet label")
    
    # Retrieve wallet label
    label = await db.get_wallet_label("0xwhale123")
    assert label is not None, "Wallet label not retrieved"
    assert label["label"] == "Known Whale #1", "Wrong label retrieved"
    print("   ✅ Retrieved wallet label")
    
    # Test collector health logging
    success = await db.log_collector_health(
        collector_name="test_collector",
        status="healthy",
        metadata={"test": True}
    )
    assert success, "Failed to log collector health"
    print("   ✅ Logged collector health")
    
    # Retrieve collector health
    health = await db.get_collector_health(collector_name="test_collector", hours=1)
    assert len(health) > 0, "No health logs retrieved"
    print(f"   ✅ Retrieved {len(health)} health log(s)")
    
    await db.disconnect()
    
    return True


async def test_moralis_collector():
    """Test Moralis collector initialization"""
    print("\n5. Testing Moralis collector...")
    
    if not settings.MORALIS_API_KEY:
        print("   ⚠️  MORALIS_API_KEY not set - skipping API tests")
        print("   ℹ️  Collector can be initialized when API key is provided")
        return True
    
    db = Database()
    await db.connect()
    
    collector = MoralisCollector(
        database=db,
        api_key=settings.MORALIS_API_KEY,
        rate_limit=3.0
    )
    await collector.connect()
    
    print("   ✅ Moralis collector initialized")
    
    # Test collector status
    status = await collector.get_status()
    assert status["collector_name"] == "moralis", "Wrong collector name"
    print(f"   ✅ Collector status: {status['status']}")
    
    # Test watched wallet management
    await collector.add_watched_wallet("0xtest123")
    wallets = await collector.get_watched_wallets()
    assert "0xtest123" in wallets, "Wallet not added"
    print(f"   ✅ Watching {len(wallets)} wallet(s)")
    
    await collector.disconnect()
    await db.disconnect()
    
    return True


async def test_glassnode_collector():
    """Test Glassnode collector initialization"""
    print("\n6. Testing Glassnode collector...")
    
    if not settings.GLASSNODE_API_KEY:
        print("   ⚠️  GLASSNODE_API_KEY not set - skipping API tests")
        print("   ℹ️  Collector can be initialized when API key is provided")
        return True
    
    db = Database()
    await db.connect()
    
    collector = GlassnodeCollector(
        database=db,
        api_key=settings.GLASSNODE_API_KEY,
        rate_limit=1.0
    )
    await collector.connect()
    
    print("   ✅ Glassnode collector initialized")
    
    # Test collector status
    status = await collector.get_status()
    assert status["collector_name"] == "glassnode", "Wrong collector name"
    print(f"   ✅ Collector status: {status['status']}")
    
    # Test metrics configuration
    assert len(collector.METRICS) > 0, "No metrics configured"
    print(f"   ✅ {len(collector.METRICS)} metrics available")
    
    await collector.disconnect()
    await db.disconnect()
    
    return True


async def run_all_tests():
    """Run all tests"""
    tests = [
        ("Database Schema", test_database_schema),
        ("Circuit Breaker", test_circuit_breaker),
        ("Rate Limiter", test_rate_limiter),
        ("Database Methods", test_database_methods),
        ("Moralis Collector", test_moralis_collector),
        ("Glassnode Collector", test_glassnode_collector),
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
    print("=" * 60)
    
    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
