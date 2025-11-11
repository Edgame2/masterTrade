#!/bin/bash

# Test script for Social Sentiment REST API v1 Endpoints
# Tests all 3 social sentiment endpoints with various parameters

BASE_URL="http://localhost:8000"
SOCIAL_API="${BASE_URL}/api/v1/social"

echo "========================================"
echo "Testing Social Sentiment API Endpoints"
echo "========================================"
echo ""

# Test 1: Get sentiment for BTC
echo "Test 1 - GET /api/v1/social/sentiment/BTC"
echo "Expected: Returns sentiment data for BTC with summary statistics"
curl -s "${SOCIAL_API}/sentiment/BTC" | jq '{
  success: .success,
  symbol: .symbol,
  count: .count,
  summary: {
    average_sentiment: .summary.average_sentiment,
    total_mentions: .summary.total_mentions,
    total_engagement: .summary.total_engagement,
    sentiment_breakdown: .summary.sentiment_breakdown
  },
  filters: .filters
}'
echo ""
echo "----------------------------------------"
echo ""

# Test 2: Get sentiment for BTC with source filter (twitter)
echo "Test 2 - GET /api/v1/social/sentiment/BTC?source=twitter"
echo "Expected: Returns only Twitter sentiment for BTC"
curl -s "${SOCIAL_API}/sentiment/BTC?source=twitter" | jq '{
  success: .success,
  symbol: .symbol,
  count: .count,
  summary: {
    by_source: .summary.by_source
  },
  filters: .filters
}'
echo ""
echo "----------------------------------------"
echo ""

# Test 3: Get sentiment for ETH with hours parameter
echo "Test 3 - GET /api/v1/social/sentiment/ETH?hours=168&limit=10"
echo "Expected: Returns ETH sentiment for last 7 days, limited to 10 results"
curl -s "${SOCIAL_API}/sentiment/ETH?hours=168&limit=10" | jq '{
  success: .success,
  symbol: .symbol,
  count: .count,
  filters: .filters
}'
echo ""
echo "----------------------------------------"
echo ""

# Test 4: Get sentiment with invalid source
echo "Test 4 - GET /api/v1/social/sentiment/BTC?source=invalid"
echo "Expected: Returns error (400 Bad Request)"
curl -s "${SOCIAL_API}/sentiment/BTC?source=invalid" | jq '{
  success: .success,
  error: .error
}'
echo ""
echo "----------------------------------------"
echo ""

# Test 5: Get trending cryptocurrencies
echo "Test 5 - GET /api/v1/social/trending"
echo "Expected: Returns top 20 trending cryptocurrencies"
curl -s "${SOCIAL_API}/trending" | jq '{
  success: .success,
  count: .count,
  top_3: .data[:3] | map({
    rank: .rank,
    symbol: .symbol,
    mention_count: .mention_count,
    avg_sentiment: .avg_sentiment
  }),
  filters: .filters
}'
echo ""
echo "----------------------------------------"
echo ""

# Test 6: Get trending with limit parameter
echo "Test 6 - GET /api/v1/social/trending?limit=5"
echo "Expected: Returns top 5 trending cryptocurrencies"
curl -s "${SOCIAL_API}/trending?limit=5" | jq '{
  success: .success,
  count: .count,
  data: .data | map({rank: .rank, symbol: .symbol}),
  filters: .filters
}'
echo ""
echo "----------------------------------------"
echo ""

# Test 7: Get influencers (all symbols)
echo "Test 7 - GET /api/v1/social/influencers"
echo "Expected: Returns top 50 influencers across all symbols"
curl -s "${SOCIAL_API}/influencers" | jq '{
  success: .success,
  count: .count,
  top_3: .data[:3] | map({
    username: .username,
    follower_count: .follower_count,
    post_count: .post_count,
    avg_sentiment: .avg_sentiment,
    symbols_mentioned: .symbols_mentioned
  }),
  filters: .filters
}'
echo ""
echo "----------------------------------------"
echo ""

# Test 8: Get influencers filtered by symbol
echo "Test 8 - GET /api/v1/social/influencers?symbol=BTC&limit=10"
echo "Expected: Returns top 10 influencers who mentioned BTC"
curl -s "${SOCIAL_API}/influencers?symbol=BTC&limit=10" | jq '{
  success: .success,
  count: .count,
  data: .data | map({username: .username, follower_count: .follower_count}),
  filters: .filters
}'
echo ""
echo "----------------------------------------"
echo ""

# Test 9: Get influencers with min_followers parameter
echo "Test 9 - GET /api/v1/social/influencers?min_followers=10000&limit=20"
echo "Expected: Returns influencers with at least 10,000 followers"
curl -s "${SOCIAL_API}/influencers?min_followers=10000&limit=20" | jq '{
  success: .success,
  count: .count,
  min_followers: .data | map(.follower_count) | min,
  filters: .filters
}'
echo ""
echo "----------------------------------------"
echo ""

# Test 10: Get sentiment for missing symbol
echo "Test 10 - GET /api/v1/social/sentiment/UNKNOWN"
echo "Expected: Returns success with 0 results (no data for this symbol)"
curl -s "${SOCIAL_API}/sentiment/UNKNOWN" | jq '{
  success: .success,
  symbol: .symbol,
  count: .count
}'
echo ""
echo "----------------------------------------"
echo ""

# Test 11: Test invalid limit parameter
echo "Test 11 - GET /api/v1/social/sentiment/BTC?limit=abc"
echo "Expected: Returns error (400 Bad Request)"
curl -s "${SOCIAL_API}/sentiment/BTC?limit=abc" | jq '{
  success: .success,
  error: .error
}'
echo ""
echo "----------------------------------------"
echo ""

echo "========================================"
echo "All tests completed!"
echo "========================================"
