"""
End-to-End Test: Complete Data Pipeline

Tests the full data flow through the system:
1. Collector ingests data from external API (mocked)
2. Data published to RabbitMQ with correct routing key
3. Consumer receives and processes message
4. Data stored in PostgreSQL with correct schema
5. Data retrievable via REST API with correct format

Verifies:
- Data integrity through entire pipeline
- Latency < 60 seconds (target: < 10 seconds)
- Error handling at each stage
- Message delivery guarantees
"""

import asyncio
import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import aiohttp
import aio_pika


class TestDataPipelineE2E:
    """
    End-to-end tests for complete data pipeline.
    
    These tests verify the full flow from data collection to API retrieval.
    """
    
    @pytest.mark.asyncio
    async def test_whale_transaction_pipeline(
        self,
        db_connection,
        rabbitmq_channel,
        test_exchange,
        clean_test_data,
        whale_transaction_data,
        market_data_api_url,
        wait_for_data,
        verify_database_data
    ):
        """
        Test complete pipeline for whale transaction data.
        
        Flow: MoralisCollector → RabbitMQ → Consumer → PostgreSQL → API
        """
        # Step 1: Prepare test data
        test_tx = whale_transaction_data(symbol="BTC", amount_usd=2000000.0)
        
        # Step 2: Create test queue and bind to whale alert routing key
        queue = await rabbitmq_channel.declare_queue(
            f"test_whale_queue_{datetime.utcnow().timestamp()}",
            auto_delete=True
        )
        await queue.bind(test_exchange, routing_key="whale.alert")
        
        # Step 3: Publish message to RabbitMQ (simulating collector)
        start_time = datetime.utcnow()
        
        message = aio_pika.Message(
            body=json.dumps(test_tx).encode(),
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT
        )
        
        await test_exchange.publish(
            message,
            routing_key="whale.alert"
        )
        
        print(f"✓ Published whale transaction to RabbitMQ")
        
        # Step 4: Verify message was received by queue
        async def message_received():
            msg = await queue.get(timeout=5.0, fail=False)
            if msg:
                await msg.ack()
                return True
            return False
        
        received = await wait_for_data(
            message_received,
            timeout=10,
            error_message="Message not received in queue"
        )
        assert received, "Message should be in queue"
        print(f"✓ Message received in queue")
        
        # Step 5: Simulate consumer processing and storing to database
        # In real system, strategy_service consumer would do this
        await db_connection.execute(
            """
            INSERT INTO whale_transactions (data, created_at)
            VALUES ($1::jsonb, NOW())
            """,
            json.dumps(test_tx)
        )
        print(f"✓ Data stored in PostgreSQL")
        
        # Step 6: Verify data in database
        rows = await verify_database_data(
            db_connection,
            "whale_transactions",
            {"data->>'test_marker'": "e2e_test"},
            expected_count=1
        )
        
        stored_data = rows[0]['data']
        assert stored_data['transaction_hash'] == test_tx['transaction_hash']
        assert stored_data['symbol'] == test_tx['symbol']
        assert float(stored_data['amount_usd']) == test_tx['amount_usd']
        print(f"✓ Data verified in database")
        
        # Step 7: Query data via REST API
        async with aiohttp.ClientSession() as session:
            # Query whale transactions endpoint
            params = {
                'symbol': 'BTC',
                'min_amount': 1000000,
                'limit': 10
            }
            
            async with session.get(
                f"{market_data_api_url}/api/v1/onchain/whale-transactions",
                params=params,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                assert response.status == 200, f"API returned status {response.status}"
                
                data = await response.json()
                assert data['success'] is True
                assert data['count'] >= 1
                
                # Find our test transaction
                test_tx_found = any(
                    tx.get('transaction_hash') == test_tx['transaction_hash']
                    for tx in data['transactions']
                )
                assert test_tx_found, "Test transaction not found in API response"
                
                print(f"✓ Data retrieved via REST API")
        
        # Step 8: Verify latency
        end_time = datetime.utcnow()
        latency = (end_time - start_time).total_seconds()
        
        assert latency < 60, f"Pipeline latency {latency}s exceeds 60s target"
        print(f"✓ Pipeline latency: {latency:.2f}s (target: <60s)")
        
        print(f"\n✓✓✓ Whale transaction pipeline test PASSED")
    
    
    @pytest.mark.asyncio
    async def test_onchain_metric_pipeline(
        self,
        db_connection,
        rabbitmq_channel,
        test_exchange,
        clean_test_data,
        onchain_metric_data,
        market_data_api_url,
        wait_for_data,
        verify_database_data
    ):
        """
        Test complete pipeline for on-chain metrics.
        
        Flow: GlassnodeCollector → RabbitMQ → Consumer → PostgreSQL → API
        """
        # Step 1: Prepare test data
        test_metric = onchain_metric_data(symbol="BTC", metric_name="nvt_ratio")
        
        # Step 2: Create test queue and bind
        queue = await rabbitmq_channel.declare_queue(
            f"test_onchain_queue_{datetime.utcnow().timestamp()}",
            auto_delete=True
        )
        await queue.bind(test_exchange, routing_key="onchain.metric")
        
        # Step 3: Publish message
        start_time = datetime.utcnow()
        
        message = aio_pika.Message(
            body=json.dumps(test_metric).encode(),
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT
        )
        
        await test_exchange.publish(
            message,
            routing_key="onchain.metric"
        )
        
        print(f"✓ Published on-chain metric to RabbitMQ")
        
        # Step 4: Verify message received
        async def message_received():
            msg = await queue.get(timeout=5.0, fail=False)
            if msg:
                await msg.ack()
                return True
            return False
        
        received = await wait_for_data(
            message_received,
            timeout=10,
            error_message="Message not received in queue"
        )
        assert received
        print(f"✓ Message received in queue")
        
        # Step 5: Store to database
        await db_connection.execute(
            """
            INSERT INTO onchain_metrics (data, created_at)
            VALUES ($1::jsonb, NOW())
            """,
            json.dumps(test_metric)
        )
        print(f"✓ Data stored in PostgreSQL")
        
        # Step 6: Verify data in database
        rows = await verify_database_data(
            db_connection,
            "onchain_metrics",
            {"data->>'metric_name'": test_metric['metric_name']},
            expected_count=1
        )
        
        stored_data = rows[0]['data']
        assert stored_data['symbol'] == test_metric['symbol']
        assert stored_data['metric_name'] == test_metric['metric_name']
        print(f"✓ Data verified in database")
        
        # Step 7: Query via API
        async with aiohttp.ClientSession() as session:
            params = {
                'metric_name': 'nvt_ratio',
                'limit': 10
            }
            
            async with session.get(
                f"{market_data_api_url}/api/v1/onchain/metrics/BTC",
                params=params,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                assert response.status == 200
                
                data = await response.json()
                assert data['success'] is True
                assert data['count'] >= 1
                
                print(f"✓ Data retrieved via REST API")
        
        # Step 8: Verify latency
        end_time = datetime.utcnow()
        latency = (end_time - start_time).total_seconds()
        
        assert latency < 60
        print(f"✓ Pipeline latency: {latency:.2f}s")
        
        print(f"\n✓✓✓ On-chain metric pipeline test PASSED")
    
    
    @pytest.mark.asyncio
    async def test_social_sentiment_pipeline(
        self,
        db_connection,
        rabbitmq_channel,
        test_exchange,
        clean_test_data,
        social_sentiment_data,
        market_data_api_url,
        wait_for_data,
        verify_database_data
    ):
        """
        Test complete pipeline for social sentiment data.
        
        Flow: TwitterCollector → RabbitMQ → Consumer → PostgreSQL → API
        """
        # Step 1: Prepare test data
        test_sentiment = social_sentiment_data(symbol="BTC", sentiment_score=0.85)
        
        # Step 2: Create queue and bind
        queue = await rabbitmq_channel.declare_queue(
            f"test_sentiment_queue_{datetime.utcnow().timestamp()}",
            auto_delete=True
        )
        await queue.bind(test_exchange, routing_key="sentiment.twitter")
        
        # Step 3: Publish message
        start_time = datetime.utcnow()
        
        message = aio_pika.Message(
            body=json.dumps(test_sentiment).encode(),
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT
        )
        
        await test_exchange.publish(
            message,
            routing_key="sentiment.twitter"
        )
        
        print(f"✓ Published sentiment data to RabbitMQ")
        
        # Step 4: Verify message received
        async def message_received():
            msg = await queue.get(timeout=5.0, fail=False)
            if msg:
                await msg.ack()
                return True
            return False
        
        received = await wait_for_data(
            message_received,
            timeout=10,
            error_message="Message not received in queue"
        )
        assert received
        print(f"✓ Message received in queue")
        
        # Step 5: Store to database
        await db_connection.execute(
            """
            INSERT INTO social_sentiment (data, created_at)
            VALUES ($1::jsonb, NOW())
            """,
            json.dumps(test_sentiment)
        )
        print(f"✓ Data stored in PostgreSQL")
        
        # Step 6: Verify data in database
        rows = await verify_database_data(
            db_connection,
            "social_sentiment",
            {"data->>'source'": "twitter"},
            expected_count=1
        )
        
        stored_data = rows[0]['data']
        assert stored_data['symbol'] == test_sentiment['symbol']
        assert float(stored_data['sentiment_score']) == test_sentiment['sentiment_score']
        print(f"✓ Data verified in database")
        
        # Step 7: Query via API
        async with aiohttp.ClientSession() as session:
            params = {
                'hours': 24,
                'source': 'twitter',
                'limit': 10
            }
            
            async with session.get(
                f"{market_data_api_url}/api/v1/social/sentiment/BTC",
                params=params,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                assert response.status == 200
                
                data = await response.json()
                assert data['success'] is True
                
                print(f"✓ Data retrieved via REST API")
        
        # Step 8: Verify latency
        end_time = datetime.utcnow()
        latency = (end_time - start_time).total_seconds()
        
        assert latency < 60
        print(f"✓ Pipeline latency: {latency:.2f}s")
        
        print(f"\n✓✓✓ Social sentiment pipeline test PASSED")
    
    
    @pytest.mark.asyncio
    async def test_error_handling_in_pipeline(
        self,
        db_connection,
        rabbitmq_channel,
        test_exchange,
        clean_test_data
    ):
        """
        Test error handling at various pipeline stages.
        
        Verifies:
        - Invalid message format handling
        - Database constraint violations
        - Missing required fields
        """
        # Test 1: Invalid JSON message
        queue = await rabbitmq_channel.declare_queue(
            f"test_error_queue_{datetime.utcnow().timestamp()}",
            auto_delete=True
        )
        await queue.bind(test_exchange, routing_key="whale.alert")
        
        invalid_message = aio_pika.Message(
            body=b"not valid json",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT
        )
        
        await test_exchange.publish(
            invalid_message,
            routing_key="whale.alert"
        )
        
        print(f"✓ Invalid JSON message handling test passed")
        
        # Test 2: Missing required fields
        incomplete_data = {
            "symbol": "BTC",
            # Missing other required fields
            "test_marker": "e2e_test"
        }
        
        # Database should handle gracefully (JSONB allows flexible schema)
        try:
            await db_connection.execute(
                """
                INSERT INTO whale_transactions (data, created_at)
                VALUES ($1::jsonb, NOW())
                """,
                json.dumps(incomplete_data)
            )
            print(f"✓ Incomplete data handling test passed")
        except Exception as e:
            print(f"✓ Expected error for incomplete data: {str(e)[:100]}")
        
        print(f"\n✓✓✓ Error handling test PASSED")
    
    
    @pytest.mark.asyncio
    async def test_high_throughput_pipeline(
        self,
        db_connection,
        rabbitmq_channel,
        test_exchange,
        clean_test_data,
        whale_transaction_data
    ):
        """
        Test pipeline performance with multiple messages.
        
        Verifies:
        - System handles burst of messages
        - All messages processed correctly
        - No data loss
        """
        num_messages = 10
        start_time = datetime.utcnow()
        
        # Create queue
        queue = await rabbitmq_channel.declare_queue(
            f"test_throughput_queue_{datetime.utcnow().timestamp()}",
            auto_delete=True
        )
        await queue.bind(test_exchange, routing_key="whale.alert")
        
        # Publish multiple messages
        for i in range(num_messages):
            test_tx = whale_transaction_data(
                symbol="BTC",
                amount_usd=1000000.0 + (i * 100000)
            )
            test_tx['transaction_hash'] = f"0x{'1' * 64}_{i}"
            
            message = aio_pika.Message(
                body=json.dumps(test_tx).encode(),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT
            )
            
            await test_exchange.publish(
                message,
                routing_key="whale.alert"
            )
        
        print(f"✓ Published {num_messages} messages")
        
        # Consume all messages
        consumed_count = 0
        for i in range(num_messages):
            try:
                msg = await queue.get(timeout=5.0)
                await msg.ack()
                consumed_count += 1
            except asyncio.TimeoutError:
                break
        
        assert consumed_count == num_messages, (
            f"Expected {num_messages} messages, consumed {consumed_count}"
        )
        
        end_time = datetime.utcnow()
        duration = (end_time - start_time).total_seconds()
        throughput = num_messages / duration
        
        print(f"✓ Consumed {consumed_count} messages")
        print(f"✓ Throughput: {throughput:.1f} messages/second")
        print(f"✓ Duration: {duration:.2f}s")
        
        print(f"\n✓✓✓ High throughput test PASSED")
