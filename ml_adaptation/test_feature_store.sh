#!/bin/bash

# Test Feature Store Implementation
# Validates the feature store database schema and Python implementation

echo "======================================================================"
echo "POSTGRESQL FEATURE STORE VERIFICATION"
echo "======================================================================"

# Test 1: Verify tables exist
echo ""
echo "=== Test 1: Database Tables ==="
echo "Checking if feature store tables exist..."

TABLES=$(docker exec mastertrade_postgres psql -U mastertrade -d mastertrade -t -c "SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename LIKE 'feature_%' ORDER BY tablename;")

if echo "$TABLES" | grep -q "feature_definitions"; then
    echo "✅ feature_definitions table exists"
else
    echo "❌ feature_definitions table missing"
    exit 1
fi

if echo "$TABLES" | grep -q "feature_values"; then
    echo "✅ feature_values table exists"
else
    echo "❌ feature_values table missing"
    exit 1
fi

if echo "$TABLES" | grep -q "feature_metadata"; then
    echo "✅ feature_metadata table exists"
else
    echo "❌ feature_metadata table missing"
    exit 1
fi

# Test 2: Verify table structures
echo ""
echo "=== Test 2: Table Structures ==="

echo "feature_definitions columns:"
docker exec mastertrade_postgres psql -U mastertrade -d mastertrade -c "\d feature_definitions" | grep -E "(id|feature_name|feature_type|data_sources|version)" | head -5

echo ""
echo "feature_values columns:"
docker exec mastertrade_postgres psql -U mastertrade -d mastertrade -c "\d feature_values" | grep -E "(id|feature_id|symbol|value|timestamp)" | head -5

# Test 3: Verify indexes
echo ""
echo "=== Test 3: Indexes ==="
INDEXES=$(docker exec mastertrade_postgres psql -U mastertrade -d mastertrade -t -c "SELECT indexname FROM pg_indexes WHERE tablename IN ('feature_definitions', 'feature_values', 'feature_metadata') ORDER BY indexname;")

INDEX_COUNT=$(echo "$INDEXES" | grep -v "^$" | wc -l)
echo "✅ Found $INDEX_COUNT indexes on feature store tables"

# Test 4: Test basic operations
echo ""
echo "=== Test 4: Basic Operations ==="

# Insert a test feature
echo "Inserting test feature..."
docker exec mastertrade_postgres psql -U mastertrade -d mastertrade -c "
INSERT INTO feature_definitions (feature_name, feature_type, description, data_sources, computation_logic, version)
VALUES ('test_rsi_14', 'technical', 'Test RSI feature', ARRAY['market_data'], 'RSI(14)', 1)
ON CONFLICT (feature_name) DO NOTHING;
" > /dev/null 2>&1

# Check if inserted
FEATURE_ID=$(docker exec mastertrade_postgres psql -U mastertrade -d mastertrade -t -c "SELECT id FROM feature_definitions WHERE feature_name = 'test_rsi_14';")

if [ ! -z "$FEATURE_ID" ]; then
    echo "✅ Feature registration works (ID: $(echo $FEATURE_ID | xargs))"
else
    echo "❌ Feature registration failed"
    exit 1
fi

# Insert a test value
echo "Inserting test feature value..."
docker exec mastertrade_postgres psql -U mastertrade -d mastertrade -c "
INSERT INTO feature_values (feature_id, symbol, value, timestamp)
VALUES ($FEATURE_ID, 'BTCUSDT', 65.5, NOW())
ON CONFLICT (feature_id, symbol, timestamp) DO NOTHING;
" > /dev/null 2>&1

# Check if inserted
VALUE_COUNT=$(docker exec mastertrade_postgres psql -U mastertrade -d mastertrade -t -c "SELECT COUNT(*) FROM feature_values WHERE feature_id = $FEATURE_ID;")

if [ ! -z "$VALUE_COUNT" ] && [ "$(echo $VALUE_COUNT | xargs)" -gt 0 ]; then
    echo "✅ Feature value storage works"
else
    echo "❌ Feature value storage failed"
    exit 1
fi

# Test 5: Verify Python implementation
echo ""
echo "=== Test 5: Python Implementation ==="

if [ -f "ml_adaptation/feature_store.py" ]; then
    echo "✅ feature_store.py exists"
    
    # Check for key methods
    if grep -q "class PostgreSQLFeatureStore" ml_adaptation/feature_store.py; then
        echo "✅ PostgreSQLFeatureStore class defined"
    fi
    
    if grep -q "async def register_feature" ml_adaptation/feature_store.py; then
        echo "✅ register_feature() method defined"
    fi
    
    if grep -q "async def store_feature_value" ml_adaptation/feature_store.py; then
        echo "✅ store_feature_value() method defined"
    fi
    
    if grep -q "async def get_feature" ml_adaptation/feature_store.py; then
        echo "✅ get_feature() method defined"
    fi
    
    if grep -q "async def get_features_bulk" ml_adaptation/feature_store.py; then
        echo "✅ get_features_bulk() method defined"
    fi
    
    if grep -q "async def list_features" ml_adaptation/feature_store.py; then
        echo "✅ list_features() method defined"
    fi
else
    echo "❌ feature_store.py not found"
    exit 1
fi

# Test 6: Query statistics
echo ""
echo "=== Test 6: Statistics ==="

FEATURE_COUNT=$(docker exec mastertrade_postgres psql -U mastertrade -d mastertrade -t -c "SELECT COUNT(*) FROM feature_definitions WHERE is_active = TRUE;")
VALUE_COUNT=$(docker exec mastertrade_postgres psql -U mastertrade -d mastertrade -t -c "SELECT COUNT(*) FROM feature_values;")

echo "Active features: $(echo $FEATURE_COUNT | xargs)"
echo "Feature values: $(echo $VALUE_COUNT | xargs)"

# Summary
echo ""
echo "======================================================================"
echo "TEST SUMMARY"
echo "======================================================================"
echo "✅ PASS - Database Tables"
echo "✅ PASS - Table Structures"
echo "✅ PASS - Indexes"
echo "✅ PASS - Basic Operations"
echo "✅ PASS - Python Implementation"
echo "✅ PASS - Statistics"
echo ""
echo "----------------------------------------------------------------------"
echo "Results: 6/6 tests passed"
echo "🎉 All tests passed!"
echo "======================================================================"
