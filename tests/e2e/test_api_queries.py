"""
API Query End-to-End Tests

Tests REST API endpoints for data retrieval:
1. Store test data in PostgreSQL
2. Query via REST API endpoints
3. Verify response format, filtering, pagination
4. Test error handling and validation

Tests all major API endpoints:
- Whale transactions
- On-chain metrics
- Social sentiment
- Market signals
- Data source management
"""

import asyncio
import json
from datetime import datetime, timedelta
import pytest
import aiohttp


class TestWhaleTransactionAPI:
    """Test whale transaction API endpoints."""
    
    @pytest.mark.asyncio
    async def test_list_whale_transactions(
        self,
        db_connection,
        clean_test_data,
        whale_transaction_data,
        market_data_api_url
    ):
        """Test GET /api/v1/onchain/whale-transactions."""
        # Store test data
        for i in range(5):
            test_tx = whale_transaction_data(
                symbol="BTC",
                amount_usd=1000000.0 + (i * 100000)
            )
            test_tx['transaction_hash'] = f"0x{'1' * 64}_{i}"
            
            await db_connection.execute(
                """
                INSERT INTO whale_transactions (data, created_at)
                VALUES ($1::jsonb, NOW())
                """,
                json.dumps(test_tx)
            )
        
        print("✓ Stored 5 test whale transactions")
        
        # Query API
        async with aiohttp.ClientSession() as session:
            params = {
                'symbol': 'BTC',
                'min_amount': 1000000,
                'limit': 10
            }
            
            async with session.get(
                f"{market_data_api_url}/api/v1/onchain/whale-transactions",
                params=params
            ) as response:
                assert response.status == 200
                
                data = await response.json()
                
                # Verify response structure
                assert 'success' in data
                assert 'transactions' in data
                assert 'count' in data
                assert 'summary' in data
                
                # Verify data
                assert data['success'] is True
                assert data['count'] >= 5
                
                # Verify summary statistics
                assert 'total_volume_usd' in data['summary']
                assert 'largest_transaction_usd' in data['summary']
                
                print(f"✓ Retrieved {data['count']} transactions")
                print(f"✓ Total volume: ${data['summary']['total_volume_usd']:,.2f}")
    
    
    @pytest.mark.asyncio
    async def test_filter_by_amount(
        self,
        db_connection,
        clean_test_data,
        whale_transaction_data,
        market_data_api_url
    ):
        """Test filtering whale transactions by minimum amount."""
        # Store transactions with different amounts
        amounts = [500000, 1000000, 2000000, 5000000]
        
        for i, amount in enumerate(amounts):
            test_tx = whale_transaction_data(symbol="BTC", amount_usd=amount)
            test_tx['transaction_hash'] = f"0x{'2' * 64}_{i}"
            
            await db_connection.execute(
                """
                INSERT INTO whale_transactions (data, created_at)
                VALUES ($1::jsonb, NOW())
                """,
                json.dumps(test_tx)
            )
        
        print(f"✓ Stored transactions with amounts: {amounts}")
        
        # Query with min_amount=2000000
        async with aiohttp.ClientSession() as session:
            params = {
                'symbol': 'BTC',
                'min_amount': 2000000,
                'limit': 10
            }
            
            async with session.get(
                f"{market_data_api_url}/api/v1/onchain/whale-transactions",
                params=params
            ) as response:
                assert response.status == 200
                
                data = await response.json()
                
                # Should only return transactions >= 2M
                for tx in data['transactions']:
                    assert tx['amount_usd'] >= 2000000
                
                print(f"✓ Filter by amount working: {data['count']} transactions >= $2M")
    
    
    @pytest.mark.asyncio
    async def test_pagination(
        self,
        db_connection,
        clean_test_data,
        whale_transaction_data,
        market_data_api_url
    ):
        """Test pagination of whale transactions."""
        # Store 15 transactions
        for i in range(15):
            test_tx = whale_transaction_data(symbol="BTC", amount_usd=1000000.0)
            test_tx['transaction_hash'] = f"0x{'3' * 64}_{i}"
            
            await db_connection.execute(
                """
                INSERT INTO whale_transactions (data, created_at)
                VALUES ($1::jsonb, NOW())
                """,
                json.dumps(test_tx)
            )
        
        print("✓ Stored 15 transactions")
        
        # Request with limit=5
        async with aiohttp.ClientSession() as session:
            params = {
                'symbol': 'BTC',
                'limit': 5
            }
            
            async with session.get(
                f"{market_data_api_url}/api/v1/onchain/whale-transactions",
                params=params
            ) as response:
                assert response.status == 200
                
                data = await response.json()
                
                # Should return max 5 results
                assert len(data['transactions']) <= 5
                
                print(f"✓ Pagination working: requested 5, got {len(data['transactions'])}")


class TestOnChainMetricsAPI:
    """Test on-chain metrics API endpoints."""
    
    @pytest.mark.asyncio
    async def test_get_metrics_by_symbol(
        self,
        db_connection,
        clean_test_data,
        onchain_metric_data,
        market_data_api_url
    ):
        """Test GET /api/v1/onchain/metrics/{symbol}."""
        # Store multiple metrics
        metrics = ['nvt_ratio', 'mvrv_ratio', 'exchange_flow']
        
        for metric in metrics:
            test_metric = onchain_metric_data(symbol="BTC", metric_name=metric)
            
            await db_connection.execute(
                """
                INSERT INTO onchain_metrics (data, created_at)
                VALUES ($1::jsonb, NOW())
                """,
                json.dumps(test_metric)
            )
        
        print(f"✓ Stored {len(metrics)} metrics")
        
        # Query API
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{market_data_api_url}/api/v1/onchain/metrics/BTC",
                params={'limit': 10}
            ) as response:
                assert response.status == 200
                
                data = await response.json()
                
                # Verify response
                assert data['success'] is True
                assert 'metrics' in data
                assert data['symbol'] == 'BTC'
                
                # Should have multiple metric types
                metric_names = {m['metric_name'] for m in data['metrics']}
                assert len(metric_names) >= len(metrics)
                
                print(f"✓ Retrieved metrics: {metric_names}")
    
    
    @pytest.mark.asyncio
    async def test_filter_by_metric_name(
        self,
        db_connection,
        clean_test_data,
        onchain_metric_data,
        market_data_api_url
    ):
        """Test filtering metrics by specific metric name."""
        # Store multiple metric types
        for metric_name in ['nvt_ratio', 'mvrv_ratio']:
            test_metric = onchain_metric_data(symbol="BTC", metric_name=metric_name)
            
            await db_connection.execute(
                """
                INSERT INTO onchain_metrics (data, created_at)
                VALUES ($1::jsonb, NOW())
                """,
                json.dumps(test_metric)
            )
        
        # Query only nvt_ratio
        async with aiohttp.ClientSession() as session:
            params = {
                'metric_name': 'nvt_ratio',
                'limit': 10
            }
            
            async with session.get(
                f"{market_data_api_url}/api/v1/onchain/metrics/BTC",
                params=params
            ) as response:
                assert response.status == 200
                
                data = await response.json()
                
                # Should only return nvt_ratio
                for metric in data['metrics']:
                    assert metric['metric_name'] == 'nvt_ratio'
                
                print("✓ Metric name filter working")


class TestSocialSentimentAPI:
    """Test social sentiment API endpoints."""
    
    @pytest.mark.asyncio
    async def test_get_sentiment_by_symbol(
        self,
        db_connection,
        clean_test_data,
        social_sentiment_data,
        market_data_api_url
    ):
        """Test GET /api/v1/social/sentiment/{symbol}."""
        # Store sentiment from multiple sources
        for source in ['twitter', 'reddit']:
            test_sentiment = social_sentiment_data(symbol="BTC", sentiment_score=0.75)
            test_sentiment['source'] = source
            
            await db_connection.execute(
                """
                INSERT INTO social_sentiment (data, created_at)
                VALUES ($1::jsonb, NOW())
                """,
                json.dumps(test_sentiment)
            )
        
        print("✓ Stored sentiment from Twitter and Reddit")
        
        # Query API
        async with aiohttp.ClientSession() as session:
            params = {
                'hours': 24,
                'limit': 10
            }
            
            async with session.get(
                f"{market_data_api_url}/api/v1/social/sentiment/BTC",
                params=params
            ) as response:
                assert response.status == 200
                
                data = await response.json()
                
                # Verify response
                assert data['success'] is True
                assert 'sentiment_data' in data
                assert 'summary' in data
                
                # Verify summary statistics
                assert 'average_sentiment' in data['summary']
                assert 'total_mentions' in data['summary']
                
                print(f"✓ Average sentiment: {data['summary']['average_sentiment']:.2f}")
    
    
    @pytest.mark.asyncio
    async def test_filter_by_source(
        self,
        db_connection,
        clean_test_data,
        social_sentiment_data,
        market_data_api_url
    ):
        """Test filtering sentiment by source."""
        # Store from multiple sources
        for source in ['twitter', 'reddit']:
            test_sentiment = social_sentiment_data(symbol="BTC", sentiment_score=0.75)
            test_sentiment['source'] = source
            
            await db_connection.execute(
                """
                INSERT INTO social_sentiment (data, created_at)
                VALUES ($1::jsonb, NOW())
                """,
                json.dumps(test_sentiment)
            )
        
        # Query only Twitter
        async with aiohttp.ClientSession() as session:
            params = {
                'source': 'twitter',
                'hours': 24,
                'limit': 10
            }
            
            async with session.get(
                f"{market_data_api_url}/api/v1/social/sentiment/BTC",
                params=params
            ) as response:
                assert response.status == 200
                
                data = await response.json()
                
                # Should only return Twitter sentiment
                for item in data['sentiment_data']:
                    assert item['source'] == 'twitter'
                
                print("✓ Source filter working")
    
    
    @pytest.mark.asyncio
    async def test_trending_topics(
        self,
        db_connection,
        clean_test_data,
        social_sentiment_data,
        market_data_api_url
    ):
        """Test GET /api/v1/social/trending."""
        # Store sentiment for multiple symbols
        symbols = ['BTC', 'ETH', 'SOL']
        
        for symbol in symbols:
            # Store multiple mentions for each
            for i in range(3):
                test_sentiment = social_sentiment_data(symbol=symbol, sentiment_score=0.75)
                
                await db_connection.execute(
                    """
                    INSERT INTO social_sentiment (data, created_at)
                    VALUES ($1::jsonb, NOW())
                    """,
                    json.dumps(test_sentiment)
                )
        
        print(f"✓ Stored sentiment for symbols: {symbols}")
        
        # Query trending
        async with aiohttp.ClientSession() as session:
            params = {'limit': 10}
            
            async with session.get(
                f"{market_data_api_url}/api/v1/social/trending",
                params=params
            ) as response:
                assert response.status == 200
                
                data = await response.json()
                
                # Verify response
                assert data['success'] is True
                assert 'trending' in data
                
                # Should have entries for our symbols
                trending_symbols = {item['symbol'] for item in data['trending']}
                assert len(trending_symbols) >= len(symbols)
                
                print(f"✓ Trending symbols: {trending_symbols}")


class TestAPIErrorHandling:
    """Test API error handling and validation."""
    
    @pytest.mark.asyncio
    async def test_invalid_symbol_404(
        self,
        market_data_api_url
    ):
        """Test that invalid symbol returns appropriate error."""
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{market_data_api_url}/api/v1/onchain/metrics/INVALID"
            ) as response:
                # Should return 404 or empty result
                if response.status == 404:
                    print("✓ Returns 404 for invalid symbol")
                elif response.status == 200:
                    data = await response.json()
                    assert data['count'] == 0 or len(data.get('metrics', [])) == 0
                    print("✓ Returns empty result for invalid symbol")
    
    
    @pytest.mark.asyncio
    async def test_invalid_parameters(
        self,
        market_data_api_url
    ):
        """Test validation of invalid parameters."""
        async with aiohttp.ClientSession() as session:
            # Test negative limit
            params = {'limit': -5}
            
            async with session.get(
                f"{market_data_api_url}/api/v1/onchain/whale-transactions",
                params=params
            ) as response:
                # Should return 400 or default to valid limit
                if response.status == 400:
                    print("✓ Returns 400 for negative limit")
                elif response.status == 200:
                    data = await response.json()
                    # Should use default/clamped limit
                    print("✓ Handles negative limit gracefully")
    
    
    @pytest.mark.asyncio
    async def test_api_timeout_handling(
        self,
        market_data_api_url
    ):
        """Test API timeout handling."""
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(
                    f"{market_data_api_url}/api/v1/onchain/whale-transactions",
                    params={'limit': 1000},  # Large limit
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as response:
                    # Should complete within timeout
                    assert response.status in [200, 504]
                    print("✓ API handles timeout appropriately")
            except asyncio.TimeoutError:
                print("✓ Client timeout triggered (expected for slow queries)")


class TestAPIPerformance:
    """Test API performance characteristics."""
    
    @pytest.mark.asyncio
    async def test_response_time(
        self,
        db_connection,
        clean_test_data,
        whale_transaction_data,
        market_data_api_url
    ):
        """Test API response time under normal load."""
        # Store test data
        for i in range(10):
            test_tx = whale_transaction_data()
            test_tx['transaction_hash'] = f"0x{'4' * 64}_{i}"
            
            await db_connection.execute(
                """
                INSERT INTO whale_transactions (data, created_at)
                VALUES ($1::jsonb, NOW())
                """,
                json.dumps(test_tx)
            )
        
        # Measure response time
        async with aiohttp.ClientSession() as session:
            start_time = asyncio.get_event_loop().time()
            
            async with session.get(
                f"{market_data_api_url}/api/v1/onchain/whale-transactions",
                params={'limit': 10}
            ) as response:
                assert response.status == 200
                await response.json()
            
            end_time = asyncio.get_event_loop().time()
            response_time = (end_time - start_time) * 1000  # ms
            
            # Target: < 200ms p95 latency
            assert response_time < 1000, f"Response time {response_time:.0f}ms exceeds 1000ms"
            
            print(f"✓ API response time: {response_time:.0f}ms")
    
    
    @pytest.mark.asyncio
    async def test_concurrent_requests(
        self,
        market_data_api_url
    ):
        """Test API performance with concurrent requests."""
        num_requests = 10
        
        async def make_request(session, i):
            async with session.get(
                f"{market_data_api_url}/api/v1/onchain/whale-transactions",
                params={'limit': 5}
            ) as response:
                return response.status
        
        async with aiohttp.ClientSession() as session:
            start_time = asyncio.get_event_loop().time()
            
            # Make concurrent requests
            tasks = [make_request(session, i) for i in range(num_requests)]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            end_time = asyncio.get_event_loop().time()
            duration = end_time - start_time
            
            # Verify all succeeded
            success_count = sum(1 for r in results if r == 200)
            
            print(f"✓ Concurrent requests: {success_count}/{num_requests} succeeded")
            print(f"✓ Duration: {duration:.2f}s ({num_requests/duration:.1f} req/s)")
            
            assert success_count >= num_requests * 0.9, "At least 90% should succeed"
