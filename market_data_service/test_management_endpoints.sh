#!/bin/bash
# Test script for Data Source Management Endpoints

BASE_URL="http://localhost:8000"

echo "========================================="
echo "Data Source Management Endpoints Tests"
echo "========================================="
echo ""

# Test 1: List all collectors
echo "1. List all collectors:"
echo "GET /collectors"
curl -s "$BASE_URL/collectors" | jq '{success, total_count, collectors: (.collectors | keys)}'
echo ""
echo ""

# Test 2: Get specific collector status
echo "2. Get historical collector status:"
echo "GET /collectors/historical"
curl -s "$BASE_URL/collectors/historical" | jq '.collector | {name, enabled, connected}'
echo ""
echo ""

# Test 3: Get collector costs
echo "3. Get collector costs:"
echo "GET /collectors/costs"
curl -s "$BASE_URL/collectors/costs" | jq '{success, totals}'
echo ""
echo ""

# Test 4: Restart collector (if onchain collectors exist)
echo "4. Test restart collector (simulated):"
echo "POST /collectors/historical/restart"
curl -s -X POST "$BASE_URL/collectors/historical/restart" | jq '{success, message}'
echo ""
echo ""

# Test 5: Configure rate limit (for collectors with rate limiting)
echo "5. Test configure rate limit (will fail for historical, but shows endpoint works):"
echo "PUT /collectors/historical/rate-limit"
curl -s -X PUT "$BASE_URL/collectors/historical/rate-limit" \
  -H "Content-Type: application/json" \
  -d '{"max_requests_per_second": 10}' | jq '.'
echo ""
echo ""

# Test 6: Circuit breaker operations
echo "6. Test circuit breaker operations (will fail for historical, but shows endpoint works):"
echo "POST /collectors/historical/circuit-breaker/reset"
curl -s -X POST "$BASE_URL/collectors/historical/circuit-breaker/reset" | jq '.'
echo ""
echo ""

# Test 7: Health check endpoints
echo "7. Get all collectors health:"
echo "GET /health/collectors"
curl -s "$BASE_URL/health/collectors" | jq '{success, collector_count, collectors: (.collectors | keys)}'
echo ""
echo ""

echo "========================================="
echo "Tests Complete!"
echo "========================================="
