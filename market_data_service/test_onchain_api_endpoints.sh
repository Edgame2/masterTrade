#!/bin/bash
# Test script for On-Chain Data Query API Endpoints

echo "========================================="
echo "Testing On-Chain Data Query API Endpoints"
echo "========================================="

BASE_URL="http://localhost:8000"

echo ""
echo "1. Testing GET /api/v1/onchain/whale-transactions"
echo "-------------------------------------------------"
curl -s "${BASE_URL}/api/v1/onchain/whale-transactions?hours=168&limit=5" | jq '.success, .count, .summary'

echo ""
echo ""
echo "2. Testing GET /api/v1/onchain/whale-transactions (with symbol filter)"
echo "-----------------------------------------------------------------------"
curl -s "${BASE_URL}/api/v1/onchain/whale-transactions?symbol=BTC&hours=168&limit=3" | jq '.success, .count, .filters'

echo ""
echo ""
echo "3. Testing GET /api/v1/onchain/whale-transactions (with min_amount filter)"
echo "--------------------------------------------------------------------------"
curl -s "${BASE_URL}/api/v1/onchain/whale-transactions?min_amount=1000000&hours=168&limit=5" | jq '.success, .count, .summary.total_volume_usd'

echo ""
echo ""
echo "4. Testing GET /api/v1/onchain/metrics/{symbol} - BTC"
echo "-----------------------------------------------------"
curl -s "${BASE_URL}/api/v1/onchain/metrics/BTC?hours=168&limit=10" | jq '.success, .symbol, .count, .latest_metrics, .available_metrics'

echo ""
echo ""
echo "5. Testing GET /api/v1/onchain/metrics/{symbol} - ETH"
echo "-----------------------------------------------------"
curl -s "${BASE_URL}/api/v1/onchain/metrics/ETH?hours=168" | jq '.success, .symbol, .count, .available_metrics'

echo ""
echo ""
echo "6. Testing GET /api/v1/onchain/metrics/{symbol} (specific metric: nvt)"
echo "-----------------------------------------------------------------------"
curl -s "${BASE_URL}/api/v1/onchain/metrics/BTC?metric_name=nvt&hours=168" | jq '.success, .count, .filters'

echo ""
echo ""
echo "7. Testing GET /api/v1/onchain/wallet/{address} (example whale wallet)"
echo "-----------------------------------------------------------------------"
# Using a sample Ethereum address format
curl -s "${BASE_URL}/api/v1/onchain/wallet/0x1234567890123456789012345678901234567890" | jq '.success, .address, .label, .category, .is_labeled'

echo ""
echo ""
echo "8. Testing GET /api/v1/onchain/wallet/{address} (with transactions)"
echo "--------------------------------------------------------------------"
curl -s "${BASE_URL}/api/v1/onchain/wallet/0x1234567890123456789012345678901234567890?include_transactions=true&tx_limit=5" | jq '.success, .address, .transactions.count, .transactions.summary'

echo ""
echo ""
echo "9. Testing invalid wallet address format"
echo "-----------------------------------------"
curl -s "${BASE_URL}/api/v1/onchain/wallet/invalid_address" | jq '.success, .error'

echo ""
echo ""
echo "10. Testing missing symbol parameter"
echo "-------------------------------------"
curl -s "${BASE_URL}/api/v1/onchain/metrics/" | jq '.'

echo ""
echo ""
echo "========================================="
echo "All tests completed!"
echo "========================================="
