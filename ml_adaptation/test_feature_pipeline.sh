#!/bin/bash
# Test suite for Feature Computation Pipeline

echo "====================================="
echo "Feature Pipeline Test Suite"
echo "====================================="
echo ""

DB_NAME="mastertrade"
DB_USER="mastertrade"
CONTAINER="mastertrade_postgres"

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

PASSED=0
FAILED=0

test_result() {
    if [ $1 -eq 0 ]; then
        echo -e "${GREEN}✓ PASSED${NC}"
        ((PASSED++))
    else
        echo -e "${RED}✗ FAILED${NC}"
        ((FAILED++))
    fi
}

echo "Test 1: Verify feature_pipeline.py file exists"
if [ -f "ml_adaptation/feature_pipeline.py" ]; then
    echo "  File exists: ml_adaptation/feature_pipeline.py"
    test_result 0
else
    echo "  File not found!"
    test_result 1
fi
echo ""

echo "Test 2: Check FeatureComputationPipeline class exists"
if grep -q "class FeatureComputationPipeline" ml_adaptation/feature_pipeline.py; then
    echo "  FeatureComputationPipeline class found"
    test_result 0
else
    echo "  FeatureComputationPipeline class not found"
    test_result 1
fi
echo ""

echo "Test 3: Verify all compute methods exist"
METHODS=(
    "compute_all_features"
    "compute_technical_features"
    "compute_onchain_features"
    "compute_social_features"
    "compute_macro_features"
    "compute_composite_features"
    "compute_and_store_features"
)

ALL_METHODS_FOUND=0
for method in "${METHODS[@]}"; do
    if grep -q "async def $method" ml_adaptation/feature_pipeline.py; then
        echo "  ✓ Found: $method"
    else
        echo "  ✗ Missing: $method"
        ALL_METHODS_FOUND=1
    fi
done
test_result $ALL_METHODS_FOUND
echo ""

echo "Test 4: Verify feature types are implemented"
FEATURE_TYPES=(
    "technical"
    "onchain"
    "social"
    "macro"
    "composite"
)

ALL_TYPES_FOUND=0
for ftype in "${FEATURE_TYPES[@]}"; do
    if grep -q "$ftype" ml_adaptation/feature_pipeline.py; then
        echo "  ✓ Feature type: $ftype"
    else
        echo "  ✗ Missing: $ftype"
        ALL_TYPES_FOUND=1
    fi
done
test_result $ALL_TYPES_FOUND
echo ""

echo "Test 5: Check auto-registration functionality"
if grep -q "_auto_register_features" ml_adaptation/feature_pipeline.py; then
    echo "  Auto-registration method found"
    if grep -q "enable_auto_registration" ml_adaptation/feature_pipeline.py; then
        echo "  Auto-registration flag found"
        test_result 0
    else
        echo "  Auto-registration flag missing"
        test_result 1
    fi
else
    echo "  Auto-registration method not found"
    test_result 1
fi
echo ""

echo "Test 6: Verify database integration"
DB_METHODS=(
    "get_indicator_results"
    "get_onchain_metrics"
    "get_social_sentiment"
    "get_stock_index_data"
)

ALL_DB_METHODS=0
for method in "${DB_METHODS[@]}"; do
    if grep -q "$method" ml_adaptation/feature_pipeline.py; then
        echo "  ✓ Uses: $method"
    else
        echo "  ✗ Missing: $method"
        ALL_DB_METHODS=1
    fi
done
test_result $ALL_DB_METHODS
echo ""

echo "Test 7: Check feature store integration"
if grep -q "PostgreSQLFeatureStore" ml_adaptation/feature_pipeline.py; then
    echo "  ✓ PostgreSQLFeatureStore imported"
    if grep -q "feature_store.register_feature" ml_adaptation/feature_pipeline.py; then
        echo "  ✓ Uses feature registration"
        test_result 0
    else
        echo "  ✗ Feature registration not used"
        test_result 1
    fi
else
    echo "  PostgreSQLFeatureStore not imported"
    test_result 1
fi
echo ""

echo "Test 8: Verify composite features logic"
COMPOSITE_FEATURES=(
    "risk_score"
    "sentiment_alignment"
    "market_strength"
    "sentiment_divergence"
)

COMPOSITE_COUNT=0
for feature in "${COMPOSITE_FEATURES[@]}"; do
    if grep -q "$feature" ml_adaptation/feature_pipeline.py; then
        echo "  ✓ Composite feature: $feature"
        ((COMPOSITE_COUNT++))
    fi
done

if [ $COMPOSITE_COUNT -ge 3 ]; then
    echo "  Found $COMPOSITE_COUNT composite features"
    test_result 0
else
    echo "  Only found $COMPOSITE_COUNT composite features"
    test_result 1
fi
echo ""

echo "Test 9: Check error handling"
ERROR_HANDLING=0
if grep -q "try:" ml_adaptation/feature_pipeline.py && \
   grep -q "except Exception as e:" ml_adaptation/feature_pipeline.py && \
   grep -q "logger.error" ml_adaptation/feature_pipeline.py; then
    echo "  ✓ Error handling implemented"
    test_result 0
else
    echo "  ✗ Error handling incomplete"
    test_result 1
fi
echo ""

echo "Test 10: Verify logging"
if grep -q "structlog" ml_adaptation/feature_pipeline.py; then
    echo "  ✓ Structured logging imported"
    LOG_LEVELS=0
    if grep -q "logger.info" ml_adaptation/feature_pipeline.py; then
        echo "  ✓ Info logging"
        ((LOG_LEVELS++))
    fi
    if grep -q "logger.debug" ml_adaptation/feature_pipeline.py; then
        echo "  ✓ Debug logging"
        ((LOG_LEVELS++))
    fi
    if grep -q "logger.error" ml_adaptation/feature_pipeline.py; then
        echo "  ✓ Error logging"
        ((LOG_LEVELS++))
    fi
    if grep -q "logger.warning" ml_adaptation/feature_pipeline.py; then
        echo "  ✓ Warning logging"
        ((LOG_LEVELS++))
    fi
    
    if [ $LOG_LEVELS -ge 3 ]; then
        test_result 0
    else
        echo "  Only $LOG_LEVELS log levels used"
        test_result 1
    fi
else
    echo "  Structured logging not imported"
    test_result 1
fi
echo ""

echo "Test 11: Check bulk operations support"
if grep -q "store_feature_values_bulk" ml_adaptation/feature_pipeline.py; then
    echo "  ✓ Bulk storage operation"
    test_result 0
else
    echo "  ✗ Bulk storage not implemented"
    test_result 1
fi
echo ""

echo "Test 12: Verify backtesting support"
if grep -q "compute_features_for_backtest" ml_adaptation/feature_pipeline.py; then
    echo "  ✓ Backtest feature computation"
    if grep -q "start_time" ml_adaptation/feature_pipeline.py && \
       grep -q "end_time" ml_adaptation/feature_pipeline.py; then
        echo "  ✓ Time range parameters"
        test_result 0
    else
        echo "  ✗ Time range parameters missing"
        test_result 1
    fi
else
    echo "  Backtest method not found"
    test_result 1
fi
echo ""

echo "Test 13: Check Python syntax"
if python3 -m py_compile ml_adaptation/feature_pipeline.py 2>/dev/null; then
    echo "  ✓ Python syntax valid"
    test_result 0
else
    echo "  ✗ Python syntax errors"
    test_result 1
fi
echo ""

echo "Test 14: Verify imports"
REQUIRED_IMPORTS=(
    "from datetime import"
    "from typing import"
    "import structlog"
    "from ml_adaptation.feature_store import"
)

ALL_IMPORTS=0
for import_line in "${REQUIRED_IMPORTS[@]}"; do
    if grep -q "$import_line" ml_adaptation/feature_pipeline.py; then
        echo "  ✓ $import_line"
    else
        echo "  ✗ Missing: $import_line"
        ALL_IMPORTS=1
    fi
done
test_result $ALL_IMPORTS
echo ""

echo "Test 15: Check code size and completeness"
LINE_COUNT=$(wc -l < ml_adaptation/feature_pipeline.py)
echo "  Total lines: $LINE_COUNT"
if [ $LINE_COUNT -ge 600 ]; then
    echo "  ✓ Comprehensive implementation"
    test_result 0
else
    echo "  ⚠ Implementation might be incomplete"
    test_result 1
fi
echo ""

echo "====================================="
echo "Test Summary"
echo "====================================="
echo -e "Passed: ${GREEN}$PASSED${NC}"
echo -e "Failed: ${RED}$FAILED${NC}"
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}All tests passed!${NC}"
    exit 0
else
    echo -e "${RED}Some tests failed.${NC}"
    exit 1
fi
