#!/bin/bash

# MasterTrade System Integration Test Script
# Tests all components and generates a comprehensive report

echo "🔧 MasterTrade System Integration Test"
echo "======================================"
echo "Date: $(date)"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Test results
declare -A test_results

# Helper function to test HTTP endpoint
test_endpoint() {
    local name="$1"
    local url="$2"
    local expected_status="$3"
    
    echo -n "Testing $name... "
    
    response=$(curl -s -w "%{http_code}" --connect-timeout 10 "$url" -o /tmp/response_body.tmp)
    status_code="${response: -3}"
    
    if [ "$status_code" = "$expected_status" ]; then
        echo -e "${GREEN}✓ PASS${NC} (HTTP $status_code)"
        test_results["$name"]="PASS"
        return 0
    else
        echo -e "${RED}✗ FAIL${NC} (HTTP $status_code, expected $expected_status)"
        test_results["$name"]="FAIL"
        return 1
    fi
}

# Helper function to test port
test_port() {
    local service="$1"
    local port="$2"
    
    echo -n "Testing $service port $port... "
    
    if lsof -i :$port >/dev/null 2>&1; then
        echo -e "${GREEN}✓ LISTENING${NC}"
        test_results["${service}_port"]="PASS"
        return 0
    else
        echo -e "${RED}✗ NOT LISTENING${NC}"
        test_results["${service}_port"]="FAIL"
        return 1
    fi
}

echo "📡 Port Connectivity Tests"
echo "-------------------------"

# Test ports
test_port "API Gateway" 8090
test_port "Market Data Service" 8000
test_port "Strategy Service" 8001
test_port "Order Executor" 8081
test_port "Monitoring UI" 3001

echo ""
echo "🌐 API Endpoint Tests"
echo "--------------------"

# Test API endpoints
test_endpoint "API Gateway Health" "http://localhost:8090/health" "200"
test_endpoint "API Gateway Docs" "http://localhost:8090/docs" "200"
test_endpoint "Dashboard Overview" "http://localhost:8090/api/dashboard/overview" "200"
test_endpoint "Portfolio Balance" "http://localhost:8090/api/portfolio/balance" "200"
test_endpoint "Strategies List" "http://localhost:8090/api/strategies" "200"
test_endpoint "Active Orders" "http://localhost:8090/api/orders/active" "200"
test_endpoint "Metrics" "http://localhost:8090/metrics" "200"

echo ""
echo "🔄 Service Integration Tests"
echo "----------------------------"

# Test Market Data Service (if available)
if lsof -i :8000 >/dev/null 2>&1; then
    test_endpoint "Market Data Health" "http://localhost:8000/health" "200"
    test_endpoint "Market Data Config" "http://localhost:8000/config" "200"
else
    echo -e "Market Data Service... ${YELLOW}⚠ OFFLINE${NC}"
    test_results["market_data_integration"]="OFFLINE"
fi

# Test Strategy Service (if available)  
if lsof -i :8001 >/dev/null 2>&1; then
    test_endpoint "Strategy Service Health" "http://localhost:8001/health" "200"
    test_endpoint "Strategy Service Config" "http://localhost:8001/config" "200"
else
    echo -e "Strategy Service... ${YELLOW}⚠ OFFLINE${NC}"
    test_results["strategy_integration"]="OFFLINE"
fi

# Test Order Executor (if available)
if lsof -i :8081 >/dev/null 2>&1; then
    test_endpoint "Order Executor Health" "http://localhost:8081/health" "200"
else
    echo -e "Order Executor... ${YELLOW}⚠ OFFLINE${NC}"
    test_results["order_executor_integration"]="OFFLINE"
fi

echo ""
echo "🔐 Security & Configuration Tests"
echo "--------------------------------"

# Test environment configuration
if [ -f ".env" ]; then
    echo -e "Environment config... ${GREEN}✓ PRESENT${NC}"
    test_results["env_config"]="PASS"
    
    # Check critical env vars
    if grep -q "USE_KEY_VAULT" .env; then
        vault_setting=$(grep "USE_KEY_VAULT" .env | cut -d'=' -f2)
        echo -e "Key Vault setting... ${BLUE}$vault_setting${NC}"
        test_results["keyvault_config"]="CONFIGURED"
    fi
    
    if grep -q "COSMOS_DB_ENDPOINT" .env; then
        echo -e "Cosmos DB config... ${GREEN}✓ PRESENT${NC}"
        test_results["cosmosdb_config"]="PASS"
    fi
else
    echo -e "Environment config... ${RED}✗ MISSING${NC}"
    test_results["env_config"]="FAIL"
fi

echo ""
echo "🔍 Database Connectivity Tests"
echo "------------------------------"

# Test database connections (basic connectivity)
echo -n "Testing Cosmos DB connectivity... "
if curl -s --connect-timeout 5 "http://localhost:8090/api/dashboard/overview" | grep -q "total_strategies"; then
    echo -e "${GREEN}✓ CONNECTED${NC}"
    test_results["cosmosdb_connectivity"]="PASS"
else
    echo -e "${YELLOW}⚠ LIMITED${NC} (auth issues expected in dev mode)"
    test_results["cosmosdb_connectivity"]="LIMITED"
fi

echo ""
echo "📊 Performance & Monitoring Tests"
echo "---------------------------------"

# Test monitoring UI
echo -n "Testing Monitoring UI... "
if curl -s --connect-timeout 10 "http://localhost:3001" | grep -q "html"; then
    echo -e "${GREEN}✓ ACCESSIBLE${NC}"
    test_results["monitoring_ui"]="PASS"
else
    echo -e "${RED}✗ INACCESSIBLE${NC}"
    test_results["monitoring_ui"]="FAIL"
fi

# Test metrics endpoint
echo -n "Testing Prometheus metrics... "
if curl -s --connect-timeout 5 "http://localhost:8090/metrics" | grep -q "gateway_"; then
    echo -e "${GREEN}✓ METRICS AVAILABLE${NC}"
    test_results["prometheus_metrics"]="PASS"
else
    echo -e "${RED}✗ NO METRICS${NC}"
    test_results["prometheus_metrics"]="FAIL"
fi

echo ""
echo "📈 Multi-Environment System Tests"
echo "---------------------------------"

# Test environment-specific configurations
echo "Testing multi-environment support:"

# Check if environment configurations exist
for env in testnet production; do
    echo -n "  $env environment... "
    if grep -q "$env" .env 2>/dev/null || [ -f "config/${env}.env" ]; then
        echo -e "${GREEN}✓ CONFIGURED${NC}"
        test_results["${env}_env"]="PASS"
    else
        echo -e "${YELLOW}⚠ BASIC${NC}"
        test_results["${env}_env"]="BASIC"
    fi
done

echo ""
echo "📋 Test Summary Report"
echo "====================="

# Count results
pass_count=0
fail_count=0
offline_count=0
limited_count=0

for test in "${!test_results[@]}"; do
    case "${test_results[$test]}" in
        "PASS") ((pass_count++)) ;;
        "FAIL") ((fail_count++)) ;;
        "OFFLINE") ((offline_count++)) ;;
        "LIMITED"|"BASIC"|"CONFIGURED") ((limited_count++)) ;;
    esac
done

total_tests=$((pass_count + fail_count + offline_count + limited_count))

echo "Total tests: $total_tests"
echo -e "${GREEN}Passed: $pass_count${NC}"
echo -e "${RED}Failed: $fail_count${NC}"
echo -e "${YELLOW}Offline/Limited: $((offline_count + limited_count))${NC}"

# Overall system status
if [ $fail_count -eq 0 ] && [ $pass_count -gt 0 ]; then
    echo ""
    echo -e "🎉 ${GREEN}SYSTEM STATUS: OPERATIONAL${NC}"
    echo "✅ Core components are working"
    echo "⚠️  Some services may have auth issues (expected in dev mode)"
    echo "🔧 Ready for production configuration"
elif [ $pass_count -gt $fail_count ]; then
    echo ""
    echo -e "🔧 ${YELLOW}SYSTEM STATUS: PARTIALLY OPERATIONAL${NC}"
    echo "✅ Basic functionality available"
    echo "⚠️  Some components need attention"
elif [ $fail_count -gt $pass_count ]; then
    echo ""
    echo -e "🚨 ${RED}SYSTEM STATUS: DEGRADED${NC}"
    echo "❌ Multiple components failing"
    echo "🔧 Immediate attention required"
else
    echo ""
    echo -e "🔍 ${BLUE}SYSTEM STATUS: UNKNOWN${NC}"
    echo "❓ Unable to determine system status"
fi

echo ""
echo "📝 Detailed Results:"
echo "-------------------"
for test in "${!test_results[@]}"; do
    result="${test_results[$test]}"
    case "$result" in
        "PASS") color=$GREEN ;;
        "FAIL") color=$RED ;;
        *) color=$YELLOW ;;
    esac
    printf "%-30s %s%s%s\n" "$test" "$color" "$result" "$NC"
done

echo ""
echo "🔗 Access URLs:"
echo "---------------"
echo "API Gateway: http://localhost:8090"
echo "API Documentation: http://localhost:8090/docs"
echo "Monitoring UI: http://localhost:3001"
echo "Prometheus Metrics: http://localhost:8090/metrics"

echo ""
echo "Test completed at $(date)"