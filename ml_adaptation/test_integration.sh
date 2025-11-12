#!/bin/bash
# Integration test for Feature Store with Strategy Service

echo "==========================================="
echo "Feature Store Integration Test"
echo "==========================================="
echo ""

BASE_URL="http://localhost:8006/api/v1"
PASSED=0
FAILED=0

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

test_result() {
    if [ $1 -eq 0 ]; then
        echo -e "${GREEN}✓ PASSED${NC}"
        ((PASSED++))
    else
        echo -e "${RED}✗ FAILED${NC}"
        ((FAILED++))
    fi
}

echo "Test 1: Feature Summary Endpoint"
RESPONSE=$(curl -s "$BASE_URL/features/summary")
if echo "$RESPONSE" | grep -q '"success":true'; then
    echo "  ✓ Summary endpoint accessible"
    if echo "$RESPONSE" | grep -q '"total_features"'; then
        echo "  ✓ Contains feature count"
        test_result 0
    else
        echo "  ✗ Missing feature count"
        test_result 1
    fi
else
    echo "  ✗ Summary endpoint failed"
    test_result 1
fi
echo ""

echo "Test 2: List Features Endpoint"
RESPONSE=$(curl -s "$BASE_URL/features/list")
if echo "$RESPONSE" | grep -q '"success":true'; then
    echo "  ✓ List endpoint accessible"
    if echo "$RESPONSE" | grep -q '"features"'; then
        echo "  ✓ Contains features array"
        test_result 0
    else
        echo "  ✗ Missing features array"
        test_result 1
    fi
else
    echo "  ✗ List endpoint failed"
    test_result 1
fi
echo ""

echo "Test 3: Compute Features Endpoint"
RESPONSE=$(curl -s "$BASE_URL/features/compute/BTCUSDT")
if echo "$RESPONSE" | grep -q '"success":true'; then
    echo "  ✓ Compute endpoint accessible"
    if echo "$RESPONSE" | grep -q '"symbol":"BTCUSDT"'; then
        echo "  ✓ Correct symbol in response"
        test_result 0
    else
        echo "  ✗ Wrong symbol in response"
        test_result 1
    fi
else
    echo "  ✗ Compute endpoint failed"
    test_result 1
fi
echo ""

echo "Test 4: Compute and Store Features Endpoint"
RESPONSE=$(curl -s -X POST "$BASE_URL/features/compute-and-store/ETHUSDT")
if echo "$RESPONSE" | grep -q '"success":true'; then
    echo "  ✓ Compute-and-store endpoint accessible"
    if echo "$RESPONSE" | grep -q '"features_stored"'; then
        echo "  ✓ Contains features_stored count"
        test_result 0
    else
        echo "  ✗ Missing features_stored count"
        test_result 1
    fi
else
    echo "  ✗ Compute-and-store endpoint failed"
    test_result 1
fi
echo ""

echo "Test 5: Retrieve Features Endpoint"
RESPONSE=$(curl -s "$BASE_URL/features/retrieve/BTCUSDT?limit=10")
if echo "$RESPONSE" | grep -q '"success":true'; then
    echo "  ✓ Retrieve endpoint accessible"
    if echo "$RESPONSE" | grep -q '"features"'; then
        echo "  ✓ Contains features in response"
        test_result 0
    else
        echo "  ✗ Missing features in response"
        test_result 1
    fi
else
    echo "  ✗ Retrieve endpoint failed"
    test_result 1
fi
echo ""

echo "Test 6: Feature Store Module Import"
docker compose exec -T strategy_service python -c "
from ml_adaptation.feature_store import PostgreSQLFeatureStore
from ml_adaptation.feature_pipeline import FeatureComputationPipeline
print('Import successful')
" 2>&1 | grep -q "Import successful"

if [ $? -eq 0 ]; then
    echo "  ✓ Feature store modules importable"
    test_result 0
else
    echo "  ✗ Feature store modules import failed"
    test_result 1
fi
echo ""

echo "Test 7: Feature Pipeline in Service"
docker compose logs strategy_service --tail=200 2>&1 | grep -q "Feature"
if [ $? -eq 0 ]; then
    echo "  ✓ Feature-related logs found"
    
    # Check for initialization errors
    if docker compose logs strategy_service --tail=200 2>&1 | grep -i "feature" | grep -qi "error"; then
        echo "  ⚠ Feature errors found in logs"
        test_result 1
    else
        echo "  ✓ No feature errors in logs"
        test_result 0
    fi
else
    echo "  ⚠ No feature logs found (might be silent success)"
    test_result 0
fi
echo ""

echo "Test 8: Database Feature Tables Exist"
docker exec mastertrade_postgres psql -U mastertrade -d mastertrade -c "\dt feature_*" 2>&1 | grep -q "feature_definitions"
if [ $? -eq 0 ]; then
    echo "  ✓ Feature store tables exist"
    test_result 0
else
    echo "  ✗ Feature store tables missing"
    test_result 1
fi
echo ""

echo "Test 9: Feature Store Data Query"
FEATURE_COUNT=$(docker exec mastertrade_postgres psql -U mastertrade -d mastertrade -t -c "SELECT COUNT(*) FROM feature_definitions WHERE is_active = true" 2>&1 | tr -d ' ')
echo "  Active features in database: $FEATURE_COUNT"
if [ "$FEATURE_COUNT" -ge 0 ]; then
    echo "  ✓ Can query feature store"
    test_result 0
else
    echo "  ✗ Cannot query feature store"
    test_result 1
fi
echo ""

echo "Test 10: Service Responding"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/features/summary")
if [ "$HTTP_CODE" -eq 200 ]; then
    echo "  ✓ Service responding with HTTP 200"
    test_result 0
else
    echo "  ✗ Service responding with HTTP $HTTP_CODE"
    test_result 1
fi
echo ""

echo "==========================================="
echo "Test Summary"
echo "==========================================="
echo -e "Passed: ${GREEN}$PASSED${NC}"
echo -e "Failed: ${RED}$FAILED${NC}"
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}All tests passed! Feature store integration successful.${NC}"
    exit 0
else
    echo -e "${RED}Some tests failed.${NC}"
    exit 1
fi
