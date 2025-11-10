"""
Enhanced Market Data Consumer - Comprehensive client for consuming all market data types

This module provides a unified consumer for all types of market data published by the 
market_data_service, including real-time crypto data, sentiment analysis, stock indices,
and correlation data. It can be used by order_executor, strategy_service, and other services.
"""

import asyncio
import json
import aiohttp
import aio_pika
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime, timezone
from dataclasses import dataclass
import structlog

logger = structlog.get_logger()

@dataclass
class MarketDataMessage:
    """Unified market data message structure"""
    data_type: str
    timestamp: str
    source: str
    data: Dict[str, Any]
    routing_key: Optional[str] = None
    headers: Optional[Dict[str, Any]] = None

class EnhancedMarketDataConsumer:
    """Comprehensive market data consumer with RabbitMQ and REST API access"""
    
    def __init__(self, 
                 rabbitmq_url: str = "amqp://mastertrade:mastertrade@localhost:5672/",
                 api_base_url: str = "http://localhost:8005",
                 service_name: str = "unknown_service"):
        
        self.rabbitmq_url = rabbitmq_url
        self.api_base_url = api_base_url.rstrip('/')
        self.service_name = service_name
        
        # RabbitMQ connections
        self.rabbitmq_connection: Optional[aio_pika.Connection] = None
        self.rabbitmq_channel: Optional[aio_pika.Channel] = None
        self.exchanges: Dict[str, aio_pika.Exchange] = {}
        
        # HTTP session for REST API access
        self.http_session: Optional[aiohttp.ClientSession] = None
        
        # Message handlers
        self.message_handlers: Dict[str, List[Callable]] = {}
        
        # Consumer tasks
        self.consumer_tasks: List[asyncio.Task] = []
        self.running = False
        
    async def initialize(self):
        """Initialize RabbitMQ and HTTP connections"""
        try:
            # Initialize RabbitMQ
            await self._init_rabbitmq()
            
            # Initialize HTTP session
            await self._init_http_session()
            
            logger.info("Enhanced market data consumer initialized", service=self.service_name)
            
        except Exception as e:
            logger.error("Failed to initialize market data consumer", error=str(e))
            raise
    
    async def _init_rabbitmq(self):
        """Initialize RabbitMQ connection and exchanges"""
        try:
            self.rabbitmq_connection = await aio_pika.connect_robust(
                self.rabbitmq_url,
                heartbeat=600,
                blocked_connection_timeout=300,
            )
            self.rabbitmq_channel = await self.rabbitmq_connection.channel()
            await self.rabbitmq_channel.set_qos(prefetch_count=50)
            
            # Declare exchanges
            self.exchanges['market'] = await self.rabbitmq_channel.declare_exchange(
                'mastertrade.market', aio_pika.ExchangeType.TOPIC, durable=True
            )
            
            logger.info("RabbitMQ initialized for market data consumer")
            
        except Exception as e:
            logger.error("Failed to initialize RabbitMQ", error=str(e))
            raise
    
    async def _init_http_session(self):
        """Initialize HTTP session for REST API access"""
        timeout = aiohttp.ClientTimeout(total=30)
        self.http_session = aiohttp.ClientSession(timeout=timeout)
        
    async def disconnect(self):
        """Clean up connections"""
        self.running = False
        
        # Cancel consumer tasks
        for task in self.consumer_tasks:
            task.cancel()
        
        if self.consumer_tasks:
            await asyncio.gather(*self.consumer_tasks, return_exceptions=True)
        
        # Close RabbitMQ connection
        if self.rabbitmq_connection and not self.rabbitmq_connection.is_closed:
            await self.rabbitmq_connection.close()
        
        # Close HTTP session
        if self.http_session:
            await self.http_session.close()
        
        logger.info("Market data consumer disconnected")
    
    def add_message_handler(self, data_type: str, handler: Callable[[MarketDataMessage], None]):
        """Add a message handler for specific data type"""
        if data_type not in self.message_handlers:
            self.message_handlers[data_type] = []
        self.message_handlers[data_type].append(handler)
        logger.info(f"Added handler for {data_type} data type")
    
    async def start_consuming_all_market_data(self):
        """Start consuming all types of market data"""
        try:
            self.running = True
            
            # Create dedicated queue for this service
            queue_name = f"{self.service_name}_market_data"
            queue = await self.rabbitmq_channel.declare_queue(
                queue_name,
                durable=True,
                auto_delete=False
            )
            
            # Bind to all market data routing keys
            bindings = [
                "market.data.*",      # Real-time market data (kline, trade, orderbook)
                "sentiment.*",        # Sentiment analysis data
                "stock.*",           # Stock index data
                "correlation.*",     # Market correlation data
                "ticker.*"           # Price ticker updates
            ]
            
            for routing_key in bindings:
                await queue.bind(self.exchanges['market'], routing_key=routing_key)
                logger.info(f"Bound to routing key: {routing_key}")
            
            # Start consuming
            consumer_task = asyncio.create_task(
                self._consume_messages(queue)
            )
            self.consumer_tasks.append(consumer_task)
            
            logger.info("Started consuming all market data types", service=self.service_name)
            
        except Exception as e:
            logger.error("Error starting market data consumer", error=str(e))
            raise
    
    async def start_consuming_specific_data_types(self, data_types: List[str]):
        """Start consuming specific data types only"""
        try:
            self.running = True
            
            # Create dedicated queue for this service
            queue_name = f"{self.service_name}_specific_data"
            queue = await self.rabbitmq_channel.declare_queue(
                queue_name,
                durable=True,
                auto_delete=False
            )
            
            # Map data types to routing keys
            routing_key_map = {
                "market_data": "market.data.*",
                "kline": "market.data.kline",
                "trade": "market.data.trade",
                "orderbook": "market.data.orderbook",
                "sentiment": "sentiment.*",
                "stock_index": "stock.*",
                "correlation": "correlation.*",
                "ticker": "ticker.*"
            }
            
            # Bind to specified data types
            for data_type in data_types:
                if data_type in routing_key_map:
                    routing_key = routing_key_map[data_type]
                    await queue.bind(self.exchanges['market'], routing_key=routing_key)
                    logger.info(f"Bound to {data_type} data via routing key: {routing_key}")
            
            # Start consuming
            consumer_task = asyncio.create_task(
                self._consume_messages(queue)
            )
            self.consumer_tasks.append(consumer_task)
            
            logger.info("Started consuming specific data types", 
                       data_types=data_types, service=self.service_name)
            
        except Exception as e:
            logger.error("Error starting specific data type consumer", error=str(e))
            raise
    
    async def _consume_messages(self, queue: aio_pika.Queue):
        """Consume and process messages from queue"""
        try:
            async with queue.iterator() as queue_iter:
                async for message in queue_iter:
                    if not self.running:
                        break
                        
                    async with message.process():
                        try:
                            # Parse message
                            message_data = json.loads(message.body.decode())
                            
                            # Create structured message
                            market_message = MarketDataMessage(
                                data_type=message_data.get("data_type", "unknown"),
                                timestamp=message_data.get("timestamp", ""),
                                source=message_data.get("source", "unknown"),
                                data=message_data.get("data", {}),
                                routing_key=message.routing_key,
                                headers=dict(message.headers) if message.headers else {}
                            )
                            
                            # Process with registered handlers
                            await self._process_message(market_message)
                            
                        except Exception as e:
                            logger.error("Error processing message", error=str(e))
                            
        except Exception as e:
            logger.error("Error in message consumer", error=str(e))
    
    async def _process_message(self, message: MarketDataMessage):
        """Process message with registered handlers"""
        try:
            # Call handlers for specific data type
            if message.data_type in self.message_handlers:
                for handler in self.message_handlers[message.data_type]:
                    try:
                        if asyncio.iscoroutinefunction(handler):
                            await handler(message)
                        else:
                            handler(message)
                    except Exception as e:
                        logger.error(f"Error in handler for {message.data_type}", error=str(e))
            
            # Call handlers for "all" data types
            if "all" in self.message_handlers:
                for handler in self.message_handlers["all"]:
                    try:
                        if asyncio.iscoroutinefunction(handler):
                            await handler(message)
                        else:
                            handler(message)
                    except Exception as e:
                        logger.error("Error in universal handler", error=str(e))
            
        except Exception as e:
            logger.error("Error processing message", error=str(e))
    
    # REST API methods for historical data access
    
    async def get_market_data(self, symbol: str, interval: str = "1m", 
                            limit: int = 100, hours_back: int = 24) -> Dict[str, Any]:
        """Get market data via REST API"""
        try:
            url = f"{self.api_base_url}/api/market-data/{symbol}"
            params = {
                "interval": interval,
                "limit": limit,
                "hours_back": hours_back
            }
            
            async with self.http_session.get(url, params=params) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.error(f"API error: {response.status}")
                    return {}
                    
        except Exception as e:
            logger.error("Error fetching market data via API", error=str(e))
            return {}
    
    async def get_latest_price(self, symbol: str) -> Dict[str, Any]:
        """Get latest price via REST API"""
        try:
            url = f"{self.api_base_url}/api/latest-price/{symbol}"
            
            async with self.http_session.get(url) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.error(f"API error: {response.status}")
                    return {}
                    
        except Exception as e:
            logger.error("Error fetching latest price via API", error=str(e))
            return {}
    
    async def get_sentiment_data(self, symbol: Optional[str] = None, 
                               hours_back: int = 24) -> Dict[str, Any]:
        """Get sentiment data via REST API"""
        try:
            url = f"{self.api_base_url}/api/sentiment"
            params = {"hours_back": hours_back}
            if symbol:
                params["symbol"] = symbol
            
            async with self.http_session.get(url, params=params) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.error(f"API error: {response.status}")
                    return {}
                    
        except Exception as e:
            logger.error("Error fetching sentiment data via API", error=str(e))
            return {}
    
    async def get_stock_indices(self, hours_back: int = 24) -> Dict[str, Any]:
        """Get stock index data via REST API"""
        try:
            url = f"{self.api_base_url}/api/stock-indices"
            params = {"hours_back": hours_back}
            
            async with self.http_session.get(url, params=params) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.error(f"API error: {response.status}")
                    return {}
                    
        except Exception as e:
            logger.error("Error fetching stock index data via API", error=str(e))
            return {}
    
    async def get_correlation_data(self, hours_back: int = 24) -> Dict[str, Any]:
        """Get correlation analysis data via REST API"""
        try:
            url = f"{self.api_base_url}/api/correlation"
            params = {"hours_back": hours_back}
            
            async with self.http_session.get(url, params=params) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.error(f"API error: {response.status}")
                    return {}
                    
        except Exception as e:
            logger.error("Error fetching correlation data via API", error=str(e))
            return {}

# Example usage
async def example_usage():
    """Example of how to use the enhanced market data consumer"""
    
    # Initialize consumer
    consumer = EnhancedMarketDataConsumer(service_name="example_service")
    await consumer.initialize()
    
    # Define message handlers
    async def handle_market_data(message: MarketDataMessage):
        print(f"Received market data: {message.data_type} for symbol: {message.data.get('symbol', 'N/A')}")
    
    async def handle_sentiment_data(message: MarketDataMessage):
        print(f"Received sentiment data: {message.data}")
    
    async def handle_all_data(message: MarketDataMessage):
        print(f"Universal handler - Data type: {message.data_type}, Timestamp: {message.timestamp}")
    
    # Register handlers
    consumer.add_message_handler("market_data", handle_market_data)
    consumer.add_message_handler("sentiment_updates", handle_sentiment_data)
    consumer.add_message_handler("all", handle_all_data)
    
    try:
        # Start consuming specific data types
        await consumer.start_consuming_specific_data_types(["market_data", "sentiment", "ticker"])
        
        # Keep running for demo
        await asyncio.sleep(60)
        
        # Example API calls
        market_data = await consumer.get_market_data("BTCUSDC", interval="5m", limit=50)
        print(f"Market data via API: {len(market_data.get('data', []))} records")
        
        latest_price = await consumer.get_latest_price("BTCUSDC")
        print(f"Latest price via API: {latest_price}")
        
    finally:
        await consumer.disconnect()

if __name__ == "__main__":
    asyncio.run(example_usage())