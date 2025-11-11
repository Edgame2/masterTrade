"""
Market Data Service - Enhanced with Historical Data, Real-time Streaming, and Sentiment Analysis

This service provides:
1. Historical data collection from Binance REST API
2. Real-time market data streaming via Binance WebSocket
3. Sentiment analysis from multiple sources (news, social media, market indicators)
4. Data storage in Azure Cosmos DB with optimized indexing
5. Message publishing to RabbitMQ for other services
"""

import asyncio
import json
import logging
import signal
import sys
import websockets
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

import aio_pika
from binance import AsyncClient, BinanceSocketManager
import structlog
import uvloop
from aiohttp import web
from prometheus_client import Counter, Gauge, Histogram, start_http_server

from config import settings, initialize_settings

# Use real Cosmos DB database
USE_MOCK = False
if USE_MOCK:
    from mock_database import MockDatabase as Database
else:
    from database import Database

from models import MarketData, OrderBookData, TradeData
from signal_aggregator import SignalAggregator

# Import Redis cache manager
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from shared.redis_client import RedisCacheManager

# Import components with fallback to mock versions
try:
    from historical_data_collector import HistoricalDataCollector
    from sentiment_data_collector import SentimentDataCollector
    from stock_index_collector import StockIndexDataCollector
    from technical_indicator_calculator import IndicatorCalculator
    from indicator_configuration_manager import IndicatorConfigurationManager
    from strategy_request_handler import StrategyDataRequestHandler
    from collectors.moralis_collector import MoralisCollector
    from collectors.glassnode_collector import GlassnodeCollector
    from collectors.twitter_collector import TwitterCollector
    from collectors.reddit_collector import RedditCollector
    from collectors.lunarcrush_collector import LunarCrushCollector
except ImportError as e:
    structlog.get_logger().warning("Some components unavailable, using mocks", error=str(e))
    from mock_components import (
        SentimentDataCollector, StockIndexDataCollector, 
        IndicatorCalculator, IndicatorConfigurationManager, StrategyDataRequestHandler
    )
    from mock_historical_collector import HistoricalDataCollector

# Configure structured logging
try:
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
except Exception as e:
    pass  # Structlog already configured

logger = structlog.get_logger()

# Prometheus Metrics
market_data_messages = Counter('market_data_messages_total', 'Total market data messages processed', ['symbol', 'type'])
websocket_connections = Gauge('websocket_connections', 'Number of active WebSocket connections')
message_processing_time = Histogram('message_processing_seconds', 'Time spent processing messages')
database_operations = Counter('database_operations_total', 'Total database operations', ['operation', 'status'])
rabbitmq_messages = Counter('rabbitmq_messages_total', 'Total RabbitMQ messages published', ['exchange', 'status'])

class MarketDataService:
    """Enhanced main service class for market data collection and processing"""
    
    def __init__(self):
        # Core components
        self.database = Database()
        self.historical_collector = None
        self.sentiment_collector = None
        self.stock_index_collector = None
        
        # On-chain data collectors
        self.moralis_collector = None
        self.glassnode_collector = None
        
        # Social media collectors
        self.twitter_collector = None
        self.reddit_collector = None
        self.lunarcrush_collector = None
        
        # Technical indicator system
        self.indicator_calculator = None
        self.indicator_config_manager = None
        self.strategy_request_handler = None
        
        # Signal aggregation
        self.signal_aggregator = None
        
        # Redis cache
        self.redis_cache = None
        self.cache_hits = 0
        self.cache_misses = 0
        
        # WebSocket connections
        self.websocket_connections: Dict[str, websockets.WebSocketServerProtocol] = {}
        self.websocket_streams = {}
        
        # RabbitMQ
        self.rabbitmq_connection: Optional[aio_pika.Connection] = None
        self.rabbitmq_channel: Optional[aio_pika.Channel] = None
        self.exchanges: Dict[str, aio_pika.Exchange] = {}
        
        # Configuration
        self.symbols: List[str] = []  # Will be loaded from database
        self.running = False
        
        # Background tasks
        self.websocket_tasks: List[asyncio.Task] = []
        self.scheduled_tasks: List[asyncio.Task] = []

        # Binance websocket manager
        self.binance_client: Optional[AsyncClient] = None
        self.socket_manager: Optional[BinanceSocketManager] = None
        
    async def initialize(self):
        """Initialize all connections and services"""
        try:
            logger.info("Initializing Market Data Service with enhanced features")
            
            # Skip Key Vault when USE_KEY_VAULT is False (use .env directly)
            if settings.USE_KEY_VAULT:
                try:
                    logger.info("Loading configuration from Azure Key Vault")
                    await initialize_settings()
                    logger.info("Configuration loaded successfully")
                except Exception as e:
                    logger.warning("Key Vault unavailable, using local config", error=str(e))
            else:
                logger.info("Using local .env configuration (Key Vault disabled)")
            
            # Initialize Redis cache
            try:
                redis_url = getattr(settings, 'REDIS_URL', 'redis://redis:6379')
                self.redis_cache = RedisCacheManager(redis_url=redis_url)
                connected = await self.redis_cache.connect()
                if connected:
                    logger.info("Redis cache connected successfully")
                else:
                    logger.warning("Redis cache unavailable - caching disabled")
                    self.redis_cache = None
            except Exception as e:
                logger.warning("Redis initialization failed - caching disabled", error=str(e))
                self.redis_cache = None
            
            # Initialize database connection
            await self.database.connect()
            logger.info("Database connection established")
            
            # Initialize default symbols if database is empty
            try:
                if hasattr(self.database, 'initialize_default_symbols'):
                    await self.database.initialize_default_symbols()
            except Exception as e:
                logger.warning("Could not initialize default symbols", error=str(e))
            
            # Load symbols from database (only symbols with tracking = true)
            await self._load_symbols_from_database()
            logger.info(f"Loaded {len(self.symbols)} symbols for tracking")
            
            # Initialize historical data collector
            self.historical_collector = HistoricalDataCollector(self.database, redis_cache=self.redis_cache)
            await self.historical_collector.connect()
            logger.info("Historical data collector initialized")
            
            # Initialize sentiment data collector
            if settings.SENTIMENT_ENABLED:
                self.sentiment_collector = SentimentDataCollector(self.database)  # No redis_cache yet
                await self.sentiment_collector.connect()
                logger.info("Sentiment data collector initialized")
                
            # Initialize stock index collector
            if settings.STOCK_INDEX_ENABLED:
                self.stock_index_collector = StockIndexDataCollector(self.database)  # No redis_cache yet
                await self.stock_index_collector.connect()
                logger.info("Stock index collector initialized")
            
            # Initialize on-chain collectors with Redis support for adaptive rate limiting
            if settings.ONCHAIN_COLLECTION_ENABLED:
                if settings.MORALIS_API_KEY:
                    self.moralis_collector = MoralisCollector(
                        database=self.database,
                        api_key=settings.MORALIS_API_KEY,
                        rate_limit=settings.MORALIS_RATE_LIMIT,
                        redis_cache=self.redis_cache
                    )
                    await self.moralis_collector.connect()
                    logger.info("Moralis on-chain collector initialized with adaptive rate limiting")
                else:
                    logger.warning("MORALIS_API_KEY not set - Moralis collector disabled")
                
                if settings.GLASSNODE_API_KEY:
                    self.glassnode_collector = GlassnodeCollector(
                        database=self.database,
                        api_key=settings.GLASSNODE_API_KEY,
                        rate_limit=settings.GLASSNODE_RATE_LIMIT,
                        redis_cache=self.redis_cache
                    )
                    await self.glassnode_collector.connect()
                    logger.info("Glassnode on-chain collector initialized with adaptive rate limiting")
                else:
                    logger.warning("GLASSNODE_API_KEY not set - Glassnode collector disabled")
            
            # Initialize social media collectors with Redis support for adaptive rate limiting
            if settings.SOCIAL_COLLECTION_ENABLED:
                if settings.TWITTER_BEARER_TOKEN:
                    self.twitter_collector = TwitterCollector(
                        database=self.database,
                        api_key=settings.TWITTER_API_KEY,
                        api_secret=settings.TWITTER_API_SECRET,
                        bearer_token=settings.TWITTER_BEARER_TOKEN,
                        rate_limit=settings.TWITTER_RATE_LIMIT,
                        use_finbert=settings.SOCIAL_USE_FINBERT,
                        redis_cache=self.redis_cache
                    )
                    await self.twitter_collector.connect()
                    logger.info("Twitter social collector initialized with adaptive rate limiting")
                else:
                    logger.warning("TWITTER_BEARER_TOKEN not set - Twitter collector disabled")
                
                if settings.REDDIT_CLIENT_ID and settings.REDDIT_CLIENT_SECRET:
                    self.reddit_collector = RedditCollector(
                        database=self.database,
                        client_id=settings.REDDIT_CLIENT_ID,
                        client_secret=settings.REDDIT_CLIENT_SECRET,
                        user_agent=settings.REDDIT_USER_AGENT,
                        rate_limit=settings.REDDIT_RATE_LIMIT,
                        use_finbert=settings.SOCIAL_USE_FINBERT,
                        redis_cache=self.redis_cache
                    )
                    await self.reddit_collector.connect()
                    logger.info("Reddit social collector initialized with adaptive rate limiting")
                else:
                    logger.warning("REDDIT_CLIENT_ID/SECRET not set - Reddit collector disabled")
                
                if settings.LUNARCRUSH_API_KEY:
                    self.lunarcrush_collector = LunarCrushCollector(
                        database=self.database,
                        api_key=settings.LUNARCRUSH_API_KEY,
                        rate_limit=settings.LUNARCRUSH_RATE_LIMIT,
                        use_finbert=False,  # Not needed for aggregated metrics
                        redis_cache=self.redis_cache
                    )
                    await self.lunarcrush_collector.connect()
                    logger.info("LunarCrush social collector initialized with adaptive rate limiting")
                else:
                    logger.warning("LUNARCRUSH_API_KEY not set - LunarCrush collector disabled")
            
            # Initialize RabbitMQ
            try:
                await self._init_rabbitmq()
                logger.info("RabbitMQ connection established")
                
                # Update collectors with RabbitMQ channel for message publishing
                if self.rabbitmq_channel:
                    if self.moralis_collector:
                        self.moralis_collector.rabbitmq_channel = self.rabbitmq_channel
                        logger.info("Moralis collector connected to RabbitMQ")
                    if self.glassnode_collector:
                        self.glassnode_collector.rabbitmq_channel = self.rabbitmq_channel
                        logger.info("Glassnode collector connected to RabbitMQ")
                    if self.twitter_collector:
                        self.twitter_collector.rabbitmq_channel = self.rabbitmq_channel
                        logger.info("Twitter collector connected to RabbitMQ")
                    if self.reddit_collector:
                        self.reddit_collector.rabbitmq_channel = self.rabbitmq_channel
                        logger.info("Reddit collector connected to RabbitMQ")
                    if self.lunarcrush_collector:
                        self.lunarcrush_collector.rabbitmq_channel = self.rabbitmq_channel
                        logger.info("LunarCrush collector connected to RabbitMQ")
            except Exception as e:
                logger.warning("RabbitMQ unavailable, continuing without messaging", error=str(e))
            
            # Initialize signal aggregator (requires RabbitMQ)
            if self.rabbitmq_channel:
                try:
                    self.signal_aggregator = SignalAggregator(
                        database=self.database,
                        rabbitmq_channel=self.rabbitmq_channel,
                        redis_cache=self.redis_cache
                    )
                    logger.info("Signal aggregator initialized")
                except Exception as e:
                    logger.warning("Signal aggregator initialization failed", error=str(e))
            
            # Initialize technical indicator system
            try:
                await self._init_indicator_system()
                logger.info("Technical indicator system initialized")
            except Exception as e:
                logger.warning("Technical indicators unavailable", error=str(e))
            
            # Initialize strategy request handler
            self.strategy_request_handler = StrategyDataRequestHandler(
                database=self.database,
                rabbitmq_url=settings.RABBITMQ_URL
            )
            await self.strategy_request_handler.initialize()
            logger.info("Strategy request handler initialized")
            
            logger.info("Market data service initialized successfully")
            
        except Exception as e:
            logger.error("Failed to initialize service", error=str(e))
            raise
            
    async def _load_symbols_from_database(self):
        """Load symbols with tracking=true from database"""
        try:
            if hasattr(self.database, 'get_tracked_symbols'):
                tracked_symbols_data = await self.database.get_tracked_symbols(
                    asset_type="crypto", 
                    exchange="binance"
                )
                # Extract symbol names
                self.symbols = [symbol_data['symbol'] for symbol_data in tracked_symbols_data]
            else:
                # For mock database, use all active symbols
                symbols_data = await self.database.get_all_active_symbols()
                self.symbols = [symbol_data['symbol'] for symbol_data in symbols_data]
            
            if not self.symbols:
                logger.warning("No tracked symbols found in database, using default symbols")
                # Fallback to default symbols from config
                self.symbols = settings.DEFAULT_SYMBOLS
                # Add default symbols to mock database
                for symbol in self.symbols:
                    await self.database.ensure_symbol_tracking(symbol, {
                        'asset_type': 'crypto',
                        'exchange': 'binance',
                        'is_active': True
                    })
            else:
                symbol_list = ", ".join(self.symbols)
                logger.info(f"Loaded symbols for tracking: {symbol_list}")
                
        except Exception as e:
            logger.error("Error loading symbols from database", error=str(e))
            # Fallback to default symbols from config
            self.symbols = settings.DEFAULT_SYMBOLS
            logger.warning("Falling back to default symbols from configuration")
            
    async def reload_symbols(self):
        """Reload symbols from database (for dynamic updates)"""
        old_symbols = set(self.symbols)
        await self._load_symbols_from_database()
        new_symbols = set(self.symbols)
        
        added_symbols = new_symbols - old_symbols
        removed_symbols = old_symbols - new_symbols
        
        if added_symbols:
            logger.info(f"New symbols added: {', '.join(added_symbols)}")
            # TODO: Start data collection for new symbols
            
        if removed_symbols:
            logger.info(f"Symbols removed: {', '.join(removed_symbols)}")
            # TODO: Stop data collection for removed symbols
            
        return {
            "added": list(added_symbols),
            "removed": list(removed_symbols),
            "total": len(self.symbols)
        }
    
    async def _init_rabbitmq(self):
        """Initialize RabbitMQ connection and exchanges"""
        try:
            self.rabbitmq_connection = await aio_pika.connect_robust(
                settings.RABBITMQ_URL,
                heartbeat=600,
                blocked_connection_timeout=300,
            )
            self.rabbitmq_channel = await self.rabbitmq_connection.channel()
            await self.rabbitmq_channel.set_qos(prefetch_count=100)
            
            # Declare exchanges
            self.exchanges['market'] = await self.rabbitmq_channel.declare_exchange(
                'mastertrade.market', aio_pika.ExchangeType.TOPIC, durable=True
            )
            
            logger.info("RabbitMQ initialized successfully")
            
        except Exception as e:
            logger.error("Failed to initialize RabbitMQ", error=str(e))
    
    async def _init_indicator_system(self):
        """Initialize technical indicator calculation system"""
        try:
            # Initialize indicator calculator
            self.indicator_calculator = IndicatorCalculator(self.database)
            logger.info("Technical indicator calculator initialized")
            
            # Initialize indicator configuration manager
            self.indicator_config_manager = IndicatorConfigurationManager(
                self.indicator_calculator,
                self.database,
                self.rabbitmq_channel
            )
            
            # Load configurations
            if hasattr(self.indicator_config_manager, 'load_configurations'):
                await self.indicator_config_manager.load_configurations()
            
            logger.info("Indicator configuration manager initialized")
            logger.info("Indicator background processing started")
            
        except Exception as e:
            logger.error("Failed to initialize indicator system", error=str(e))
            raise
            raise

    async def _init_socket_manager(self):
        """Initialize Binance websocket manager for real-time streams"""
        if self.socket_manager:
            return

        try:
            api_key = getattr(settings, "BINANCE_API_KEY", None)
            api_secret = getattr(settings, "BINANCE_API_SECRET", None)
            testnet = getattr(settings, "BINANCE_USE_TESTNET", False)

            self.binance_client = await AsyncClient.create(api_key, api_secret, testnet=testnet)
            self.socket_manager = BinanceSocketManager(self.binance_client)
        except Exception as exc:
            # Ensure we clean up partial initialization
            if self.binance_client:
                try:
                    await self.binance_client.close_connection()
                except Exception:
                    pass
            self.binance_client = None
            self.socket_manager = None
            raise exc
    
    async def start_streams(self):
        """Start WebSocket streams for all symbols"""
        try:
            self.running = True
            
            # Start individual streams for each symbol
            for symbol in self.symbols:
                # Kline/Candlestick stream (1-minute intervals)
                kline_task = asyncio.create_task(
                    self._handle_kline_stream(symbol)
                )
                self.websocket_tasks.append(kline_task)
                
                # Trade stream
                trade_task = asyncio.create_task(
                    self._handle_trade_stream(symbol)
                )
                self.websocket_tasks.append(trade_task)
                
                # Order book stream
                orderbook_task = asyncio.create_task(
                    self._handle_orderbook_stream(symbol)
                )
                self.websocket_tasks.append(orderbook_task)
            
            websocket_connections.set(len(self.websocket_tasks))
            logger.info(f"Started {len(self.websocket_tasks)} WebSocket streams", 
                       symbols=self.symbols)
            
            # Wait for all tasks
            await asyncio.gather(*self.websocket_tasks, return_exceptions=True)
            
        except Exception as e:
            logger.error("Error in WebSocket streams", error=str(e))
            raise
    
    async def _handle_kline_stream(self, symbol: str):
        """Handle kline/candlestick WebSocket stream"""
        socket = None
        try:
            socket = self.socket_manager.kline_socket(symbol, interval='1m')
            
            async with socket as stream:
                logger.info(f"Started kline stream for {symbol}")
                
                while self.running:
                    try:
                        msg = await stream.recv()
                        await self._process_kline_data(msg)
                        market_data_messages.labels(symbol=symbol, type='kline').inc()
                        
                    except Exception as e:
                        logger.error(f"Error processing kline data for {symbol}", error=str(e))
                        
        except Exception as e:
            logger.error(f"Kline stream error for {symbol}", error=str(e))
        finally:
            if socket:
                await socket.close()
    
    async def _handle_trade_stream(self, symbol: str):
        """Handle trade WebSocket stream"""
        socket = None
        try:
            socket = self.socket_manager.trade_socket(symbol)
            
            async with socket as stream:
                logger.info(f"Started trade stream for {symbol}")
                
                while self.running:
                    try:
                        msg = await stream.recv()
                        await self._process_trade_data(msg)
                        market_data_messages.labels(symbol=symbol, type='trade').inc()
                        
                    except Exception as e:
                        logger.error(f"Error processing trade data for {symbol}", error=str(e))
                        
        except Exception as e:
            logger.error(f"Trade stream error for {symbol}", error=str(e))
        finally:
            if socket:
                await socket.close()
    
    async def _handle_orderbook_stream(self, symbol: str):
        """Handle order book WebSocket stream"""
        socket = None
        try:
            socket = self.socket_manager.depth_socket(symbol, depth=20)
            
            async with socket as stream:
                logger.info(f"Started order book stream for {symbol}")
                
                while self.running:
                    try:
                        msg = await stream.recv()
                        await self._process_orderbook_data(msg)
                        market_data_messages.labels(symbol=symbol, type='orderbook').inc()
                        
                    except Exception as e:
                        logger.error(f"Error processing order book data for {symbol}", error=str(e))
                        
        except Exception as e:
            logger.error(f"Order book stream error for {symbol}", error=str(e))
        finally:
            if socket:
                await socket.close()
    
    @message_processing_time.time()
    async def _process_kline_data(self, msg: dict):
        """Process kline/candlestick data"""
        try:
            kline_data = msg['k']
            
            market_data = MarketData(
                symbol=kline_data['s'],
                timestamp=datetime.fromtimestamp(kline_data['t'] / 1000, tz=timezone.utc),
                open_price=float(kline_data['o']),
                high_price=float(kline_data['h']),
                low_price=float(kline_data['l']),
                close_price=float(kline_data['c']),
                volume=float(kline_data['v']),
                quote_volume=float(kline_data['q']),
                trades_count=int(kline_data['n']),
                interval='1m'
            )
            
            # Store in database (only closed candles)
            if kline_data['x']:  # Is kline closed
                await self.database.insert_market_data(market_data)
                database_operations.labels(operation='insert_market_data', status='success').inc()
            
            # Publish to RabbitMQ
            await self._publish_market_data('market.data.kline', market_data.model_dump())
            
        except Exception as e:
            logger.error("Error processing kline data", error=str(e), data=msg)
            database_operations.labels(operation='insert_market_data', status='error').inc()
    
    @message_processing_time.time()
    async def _process_trade_data(self, msg: dict):
        """Process trade data"""
        try:
            trade_data = TradeData(
                symbol=msg['s'],
                timestamp=datetime.fromtimestamp(msg['T'] / 1000, tz=timezone.utc),
                price=float(msg['p']),
                quantity=float(msg['q']),
                is_buyer_maker=msg['m']
            )
            
            # Store in database
            await self.database.insert_trade_data(trade_data)

            # Initialize Binance socket manager
            try:
                await self._init_socket_manager()
                logger.info("Binance socket manager initialized")
            except Exception as e:
                logger.warning("Failed to initialize Binance socket manager", error=str(e))
            database_operations.labels(operation='insert_trade_data', status='success').inc()
            
            # Publish to RabbitMQ
            await self._publish_market_data('market.data.trade', trade_data.model_dump())
            
        except Exception as e:
            logger.error("Error processing trade data", error=str(e), data=msg)
            database_operations.labels(operation='insert_trade_data', status='error').inc()
    
    @message_processing_time.time()
    async def _process_orderbook_data(self, msg: dict):
        """Process order book data"""
        try:
            orderbook_data = OrderBookData(
                symbol=msg['s'],
                timestamp=datetime.fromtimestamp(msg['E'] / 1000, tz=timezone.utc),
                bids=msg['b'],
                asks=msg['a']
            )
            
            # Store in database (sample every 10 updates)
            import random
            if random.randint(1, 10) == 1:
                await self.database.insert_orderbook_data(orderbook_data)
                database_operations.labels(operation='insert_orderbook_data', status='success').inc()
            
            # Always publish to RabbitMQ for real-time processing
            await self._publish_market_data('market.data.orderbook', orderbook_data.model_dump())
            
        except Exception as e:
            logger.error("Error processing order book data", error=str(e), data=msg)
            database_operations.labels(operation='insert_orderbook_data', status='error').inc()
    
    async def _publish_market_data(self, routing_key: str, data: dict):
        """Publish market data to RabbitMQ"""
        try:
            if not self.exchanges.get('market'):
                return
                
            message = aio_pika.Message(
                json.dumps(data, default=str).encode(),
                content_type='application/json',
                timestamp=datetime.now(timezone.utc)
            )
            
            await self.exchanges['market'].publish(
                message, routing_key=routing_key
            )
            
            rabbitmq_messages.labels(exchange='market', status='success').inc()
            
        except Exception as e:
            logger.error("Error publishing to RabbitMQ", error=str(e), routing_key=routing_key)
            rabbitmq_messages.labels(exchange='market', status='error').inc()
    
    async def _publish_to_rabbitmq(self, data_type: str, data: dict, routing_key: str):
        """Enhanced RabbitMQ publisher for all data types"""
        try:
            if not self.exchanges.get('market'):
                return
                
            # Add metadata to all messages
            enriched_data = {
                "data_type": data_type,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "source": "market_data_service",
                "data": data
            }
                
            message = aio_pika.Message(
                json.dumps(enriched_data, default=str).encode(),
                content_type='application/json',
                timestamp=datetime.now(timezone.utc),
                headers={
                    "data_type": data_type,
                    "source": "market_data_service"
                }
            )
            
            await self.exchanges['market'].publish(
                message, routing_key=routing_key
            )
            
            rabbitmq_messages.labels(exchange='market', status='success').inc()
            logger.debug(f"Published {data_type} data to RabbitMQ", routing_key=routing_key)
            
        except Exception as e:
            logger.error(f"Error publishing {data_type} to RabbitMQ", error=str(e), routing_key=routing_key)
            rabbitmq_messages.labels(exchange='market', status='error').inc()
    
    async def start_enhanced_features(self):
        """Start enhanced features: historical data collection, real-time streams, and sentiment analysis"""
        logger.info("Starting enhanced market data features")
        
        # Set running flag
        self.running = True
        
        # Start historical data collection (one-time on startup)
        if hasattr(self, 'historical_collector') and self.historical_collector:
            historical_task = asyncio.create_task(self._collect_initial_historical_data())
            self.scheduled_tasks.append(historical_task)
            
        # Start real-time WebSocket streams  
        realtime_task = asyncio.create_task(self._start_realtime_streams())
        self.scheduled_tasks.append(realtime_task)
        
        # Start sentiment analysis (periodic)
        if settings.SENTIMENT_ENABLED and self.sentiment_collector:
            sentiment_task = asyncio.create_task(self._start_sentiment_collection())
            self.scheduled_tasks.append(sentiment_task)
            
        # Start stock index collection (periodic)
        if settings.STOCK_INDEX_ENABLED and hasattr(self, 'stock_index_collector') and self.stock_index_collector:
            stock_index_task = asyncio.create_task(self._start_stock_index_collection())
            self.scheduled_tasks.append(stock_index_task)
        
        # Start on-chain data collection (periodic)
        if settings.ONCHAIN_COLLECTION_ENABLED and (self.moralis_collector or self.glassnode_collector):
            onchain_task = asyncio.create_task(self._start_onchain_collection())
            self.scheduled_tasks.append(onchain_task)
            logger.info("On-chain data collection scheduled")
        
        # Start social media collection (periodic)
        if settings.SOCIAL_COLLECTION_ENABLED and (self.twitter_collector or self.reddit_collector or self.lunarcrush_collector):
            social_task = asyncio.create_task(self._start_social_collection())
            self.scheduled_tasks.append(social_task)
            logger.info("Social media data collection scheduled")
        
        # Start signal aggregator (real-time signal generation)
        if self.signal_aggregator:
            try:
                await self.signal_aggregator.start()
                logger.info("Signal aggregator started - publishing signals every 60 seconds")
            except Exception as e:
                logger.error("Failed to start signal aggregator", error=str(e))
            
        # Start periodic data maintenance
        maintenance_task = asyncio.create_task(self._start_data_maintenance())
        self.scheduled_tasks.append(maintenance_task)
        
        logger.info("Enhanced features started successfully")
        
    async def _collect_initial_historical_data(self):
        """Collect initial historical data for all symbols"""
        try:
            logger.info("Starting initial historical data collection")
            
            # Check if we already have recent data
            for symbol in self.symbols:
                try:
                    # Check if we have data from the last 24 hours
                    recent_data = await self.database.get_market_data_for_analysis(
                        symbol=symbol,
                        interval="1h",
                        hours_back=24
                    )
                    
                    if len(recent_data) < 20:  # If we have less than 20 hours of recent data
                        logger.info(f"Collecting historical data for {symbol}")
                        
                        # Collect historical data for different intervals
                        for interval in settings.HISTORICAL_INTERVALS:
                            try:
                                record_count = await self.historical_collector.collect_historical_data_for_symbol(
                                    symbol=symbol,
                                    interval=interval,
                                    days_back=min(30, settings.HISTORICAL_DATA_DAYS)  # Limit initial collection
                                )
                                logger.info(f"Collected {record_count} records for {symbol} {interval}")
                                
                                # Small delay between intervals
                                await asyncio.sleep(0.5)
                                
                            except Exception as e:
                                logger.error(f"Failed to collect historical data for {symbol} {interval}", error=str(e))
                                
                        # Delay between symbols to avoid rate limits
                        await asyncio.sleep(2)
                    else:
                        logger.info(f"Recent data exists for {symbol}, skipping historical collection")
                        
                except Exception as e:
                    logger.error(f"Error checking/collecting historical data for {symbol}", error=str(e))
                    
            logger.info("Initial historical data collection completed")
            
        except Exception as e:
            logger.error("Error in initial historical data collection", error=str(e))
            
    async def _start_realtime_streams(self):
        """Start real-time WebSocket streams for all symbols"""
        try:
            logger.info("Starting real-time WebSocket streams")
            if not self.socket_manager:
                logger.warning("Binance socket manager not initialized; skipping real-time stream startup")
                return
            
            for symbol in self.symbols:
                # Create WebSocket streams for each symbol
                kline_task = asyncio.create_task(self._handle_binance_websocket(symbol, "kline"))
                ticker_task = asyncio.create_task(self._handle_binance_websocket(symbol, "ticker"))
                
                self.websocket_tasks.extend([kline_task, ticker_task])
                
                # Small delay between symbols
                await asyncio.sleep(0.1)
                
            websocket_connections.set(len(self.websocket_tasks))
            logger.info(f"Started {len(self.websocket_tasks)} real-time streams")
            
            # Wait for all WebSocket tasks
            await asyncio.gather(*self.websocket_tasks, return_exceptions=True)
            
        except Exception as e:
            logger.error("Error starting real-time streams", error=str(e))
            
    async def _handle_binance_websocket(self, symbol: str, stream_type: str):
        """Handle individual Binance WebSocket connection"""
        reconnect_attempts = 0
        max_attempts = settings.WS_MAX_RECONNECT_ATTEMPTS
        
        while self.running and reconnect_attempts < max_attempts:
            try:
                # Construct WebSocket URL
                stream_name = f"{symbol.lower()}@{stream_type}_1m" if stream_type == "kline" else f"{symbol.lower()}@ticker"
                ws_url = f"{settings.BINANCE_WSS_URL}{stream_name}"
                
                logger.info(f"Connecting to {stream_type} stream for {symbol}")
                
                async with websockets.connect(ws_url) as websocket:
                    reconnect_attempts = 0  # Reset on successful connection
                    
                    # Send ping periodically
                    ping_task = asyncio.create_task(self._send_websocket_ping(websocket))
                    
                    try:
                        while self.running:
                            try:
                                # Set a timeout for receiving messages
                                message = await asyncio.wait_for(
                                    websocket.recv(), 
                                    timeout=settings.WS_PING_INTERVAL
                                )
                                
                                data = json.loads(message)
                                await self._process_websocket_message(symbol, stream_type, data)
                                market_data_messages.labels(symbol=symbol, type=stream_type).inc()
                                
                            except asyncio.TimeoutError:
                                logger.debug(f"WebSocket timeout for {symbol} {stream_type}")
                                continue
                            except websockets.exceptions.ConnectionClosed:
                                logger.warning(f"WebSocket connection closed for {symbol} {stream_type}")
                                break
                            except Exception as e:
                                logger.error(f"Error processing WebSocket message for {symbol}", error=str(e))
                                
                    finally:
                        ping_task.cancel()
                        
            except Exception as e:
                reconnect_attempts += 1
                logger.error(
                    f"WebSocket connection failed for {symbol} {stream_type}",
                    error=str(e),
                    attempt=reconnect_attempts
                )
                
                if reconnect_attempts < max_attempts:
                    await asyncio.sleep(settings.WS_RECONNECT_INTERVAL * reconnect_attempts)
                    
        logger.warning(f"Max reconnection attempts reached for {symbol} {stream_type}")
        
    async def _send_websocket_ping(self, websocket):
        """Send periodic ping to keep WebSocket alive"""
        try:
            while self.running:
                await asyncio.sleep(settings.WS_PING_INTERVAL)
                await websocket.ping()
        except Exception as e:
            logger.debug("WebSocket ping error", error=str(e))
            
    async def _process_websocket_message(self, symbol: str, stream_type: str, data: Dict):
        """Process incoming WebSocket message"""
        try:
            with message_processing_time.time():
                if stream_type == "kline" and "k" in data:
                    await self._process_kline_websocket_data(symbol, data["k"])
                elif stream_type == "ticker":
                    await self._process_ticker_websocket_data(symbol, data)
                    
        except Exception as e:
            logger.error(f"Error processing {stream_type} data for {symbol}", error=str(e))
            
    async def _process_kline_websocket_data(self, symbol: str, kline_data: Dict):
        """Process kline data from WebSocket"""
        try:
            # Only process closed klines for accuracy
            if kline_data.get("x", False):  # x indicates if kline is closed
                market_data_item = {
                    "id": f"{symbol}_1m_{int(kline_data['t'] / 1000)}",
                    "symbol": symbol,
                    "interval": "1m",
                    "timestamp": datetime.fromtimestamp(kline_data["t"] / 1000).isoformat() + "Z",
                    "open_price": str(kline_data["o"]),
                    "high_price": str(kline_data["h"]),
                    "low_price": str(kline_data["l"]),
                    "close_price": str(kline_data["c"]),
                    "volume": str(kline_data["v"]),
                    "close_time": datetime.fromtimestamp(kline_data["T"] / 1000).isoformat() + "Z",
                    "quote_asset_volume": str(kline_data["q"]),
                    "number_of_trades": int(kline_data["n"]),
                    "taker_buy_base_asset_volume": str(kline_data["V"]),
                    "taker_buy_quote_asset_volume": str(kline_data["Q"]),
                    "base_asset": symbol[:-4],  # Remove USDC suffix
                    "quote_asset": "USDC",
                    "created_at": datetime.utcnow().isoformat() + "Z"
                }
                
                # Store in database
                await self.database.upsert_market_data(market_data_item)
                database_operations.labels(operation='upsert', status='success').inc()
                
                # Publish to RabbitMQ
                await self._publish_to_rabbitmq("market_data", market_data_item, f"market.{symbol}.kline")
                
        except Exception as e:
            database_operations.labels(operation='upsert', status='error').inc()
            logger.error(f"Error processing kline data for {symbol}", error=str(e))
            
    async def _process_ticker_websocket_data(self, symbol: str, ticker_data: Dict):
        """Process ticker data from WebSocket"""
        try:
            ticker_item = {
                "symbol": symbol,
                "price": float(ticker_data.get("c", 0)),
                "price_change": float(ticker_data.get("p", 0)),
                "price_change_percent": float(ticker_data.get("P", 0)),
                "volume": float(ticker_data.get("v", 0)),
                "high_price": float(ticker_data.get("h", 0)),
                "low_price": float(ticker_data.get("l", 0)),
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
            
            # Publish ticker updates to RabbitMQ for real-time consumption
            await self._publish_to_rabbitmq("ticker_updates", ticker_item, f"ticker.{symbol}")
            
        except Exception as e:
            logger.error(f"Error processing ticker data for {symbol}", error=str(e))
            
    async def _start_sentiment_collection(self):
        """Start periodic sentiment data collection"""
        try:
            logger.info("Starting sentiment data collection")
            
            while self.running:
                try:
                    # Collect sentiment data
                    crypto_symbols = [symbol[:-4] for symbol in self.symbols]  # Remove USDC suffix
                    sentiment_results = await self.sentiment_collector.collect_all_sentiment_data(crypto_symbols)
                    
                    total_collected = sum(len(data) for data in sentiment_results.values())
                    logger.info(f"Collected {total_collected} sentiment data points")
                    
                    # Publish sentiment summary to RabbitMQ
                    if total_collected > 0:
                        summary = {
                            "timestamp": datetime.utcnow().isoformat() + "Z",
                            "total_records": total_collected,
                            "categories": {k: len(v) for k, v in sentiment_results.items()}
                        }
                        await self._publish_to_rabbitmq("sentiment_updates", summary, "sentiment.summary")
                        
                except Exception as e:
                    logger.error("Error in sentiment collection cycle", error=str(e))
                    
                # Wait for next collection cycle
                await asyncio.sleep(settings.SENTIMENT_UPDATE_INTERVAL)
                
        except Exception as e:
            logger.error("Error starting sentiment collection", error=str(e))
            
    async def _start_stock_index_collection(self):
        """Start periodic stock index data collection"""
        try:
            logger.info("Starting stock index data collection")
            
            while self.running:
                try:
                    # Collect current stock index values
                    current_data = await self.stock_index_collector.collect_current_index_values()
                    logger.info(f"Collected {len(current_data)} current stock index values")
                    
                    # Collect historical data (less frequently)
                    # Only run historical collection every 6th cycle (6 hours with default 1 hour intervals)
                    if hasattr(self, '_stock_index_cycle_count'):
                        self._stock_index_cycle_count += 1
                    else:
                        self._stock_index_cycle_count = 1
                        
                    if self._stock_index_cycle_count % 6 == 0:
                        historical_data = await self.stock_index_collector.collect_historical_data(
                            days=7,  # Collect last week of data
                            interval="1d"
                        )
                        logger.info(f"Collected {len(historical_data)} historical stock index records")
                    
                    # Publish stock market summary to RabbitMQ
                    if current_data:
                        summary = await self._get_stock_market_summary(current_data)
                        await self._publish_to_rabbitmq("stock_index_updates", summary, "stock.summary")
                        
                        # Also publish correlation indicators
                        correlation_data = await self._get_market_correlation_data()
                        await self._publish_to_rabbitmq("correlation_updates", correlation_data, "correlation.market")
                        
                except Exception as e:
                    logger.error("Error in stock index collection cycle", error=str(e))
                    
                # Wait for next collection cycle (default: 1 hour)
                await asyncio.sleep(settings.STOCK_INDEX_UPDATE_INTERVAL)
                
        except Exception as e:
            logger.error("Error starting stock index collection", error=str(e))
    
    async def _start_onchain_collection(self):
        """Start periodic on-chain data collection"""
        try:
            logger.info("Starting on-chain data collection")
            
            # Symbols to track for on-chain data
            onchain_symbols = ["BTC", "ETH", "USDT", "USDC"]
            
            while self.running:
                try:
                    collection_start = datetime.now(timezone.utc)
                    
                    # Collect whale transactions from Moralis
                    if self.moralis_collector:
                        try:
                            success = await self.moralis_collector.collect(
                                symbols=onchain_symbols,
                                hours=1  # Collect last hour of data
                            )
                            
                            if success:
                                # Get collector stats
                                status = await self.moralis_collector.get_status()
                                logger.info(
                                    "Moralis collection completed",
                                    data_points=status['stats']['data_points_collected'],
                                    status=status['status']
                                )
                                
                                # Get recent whale transactions
                                whale_txs = await self.database.get_whale_transactions(
                                    hours=1,
                                    limit=10
                                )
                                
                                # Publish whale alerts to RabbitMQ
                                if whale_txs:
                                    for tx in whale_txs:
                                        if tx.get('amount', 0) > settings.ONCHAIN_WHALE_THRESHOLD_USD / 40000:  # Rough USD conversion
                                            await self._publish_to_rabbitmq(
                                                "whale_alert",
                                                tx,
                                                f"onchain.whale.{tx['symbol']}"
                                            )
                                    
                                    logger.info(f"Published {len(whale_txs)} whale alerts")
                            
                        except Exception as e:
                            logger.error("Error in Moralis collection", error=str(e))
                    
                    # Small delay between collectors
                    await asyncio.sleep(2)
                    
                    # Collect on-chain metrics from Glassnode
                    if self.glassnode_collector:
                        try:
                            # Metrics to collect
                            metrics = [
                                "nvt", "mvrv", "nupl",
                                "exchange_netflow", "exchange_inflow", "exchange_outflow",
                                "active_addresses"
                            ]
                            
                            success = await self.glassnode_collector.collect(
                                symbols=["BTC", "ETH"],
                                metrics=metrics,
                                interval="24h"
                            )
                            
                            if success:
                                # Get collector stats
                                status = await self.glassnode_collector.get_status()
                                logger.info(
                                    "Glassnode collection completed",
                                    data_points=status['stats']['data_points_collected'],
                                    status=status['status']
                                )
                                
                                # Get recent metrics and publish to RabbitMQ
                                for symbol in ["BTC", "ETH"]:
                                    metrics_data = await self.database.get_onchain_metrics(
                                        symbol=symbol,
                                        hours=2,
                                        limit=10
                                    )
                                    
                                    if metrics_data:
                                        # Create metrics summary
                                        summary = {
                                            "symbol": symbol,
                                            "timestamp": datetime.now(timezone.utc).isoformat(),
                                            "metrics": {}
                                        }
                                        
                                        for metric in metrics_data:
                                            metric_name = metric.get('metric_name')
                                            if metric_name:
                                                summary["metrics"][metric_name] = {
                                                    "value": metric.get('value'),
                                                    "category": metric.get('metric_category'),
                                                    "timestamp": metric.get('timestamp')
                                                }
                                        
                                        # Publish to RabbitMQ
                                        await self._publish_to_rabbitmq(
                                            "onchain_metrics",
                                            summary,
                                            f"onchain.metrics.{symbol}"
                                        )
                                
                        except Exception as e:
                            logger.error("Error in Glassnode collection", error=str(e))
                    
                    # Log collection cycle duration
                    duration = (datetime.now(timezone.utc) - collection_start).total_seconds()
                    logger.info(
                        "On-chain collection cycle completed",
                        duration_seconds=duration
                    )
                    
                except Exception as e:
                    logger.error("Error in on-chain collection cycle", error=str(e))
                    
                # Wait for next collection cycle
                await asyncio.sleep(settings.ONCHAIN_COLLECTION_INTERVAL)
                
        except Exception as e:
            logger.error("Error starting on-chain collection", error=str(e))
    
    async def _start_social_collection(self):
        """
        Start periodic social media data collection
        
        Collects sentiment data from:
        - Twitter: Influencer tweets and keyword monitoring
        - Reddit: Crypto subreddit posts and comments
        - LunarCrush: Aggregated social metrics
        """
        logger.info("Starting social media data collection")
        interval = settings.SOCIAL_COLLECTION_INTERVAL
        
        while self.running:
            try:
                cycle_start = datetime.now(timezone.utc)
                logger.info("Starting social collection cycle")
                
                # Collect Twitter data
                if self.twitter_collector:
                    try:
                        logger.info("Collecting Twitter data")
                        twitter_results = await self.twitter_collector.collect_data()
                        
                        logger.info(
                            "Twitter collection complete",
                            tweets=twitter_results.get("tweets_collected", 0),
                            influencer_tweets=twitter_results.get("influencer_tweets", 0)
                        )
                        
                        # Get collector stats
                        twitter_status = self.twitter_collector.get_status()
                        
                        # Publish Twitter sentiment summary to RabbitMQ
                        if twitter_results.get("tweets_collected", 0) > 0:
                            sentiment_summary = {
                                "source": "twitter",
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                                "tweets_collected": twitter_results.get("tweets_collected", 0),
                                "influencer_tweets": twitter_results.get("influencer_tweets", 0),
                                "sentiment_distribution": twitter_results.get("sentiment_distribution", {}),
                                "crypto_mentions": twitter_results.get("crypto_mentions", {}),
                                "collector_status": twitter_status
                            }
                            
                            await self._publish_to_rabbitmq(
                                sentiment_summary,
                                "social_sentiment",
                                "social.sentiment.twitter"
                            )
                            
                    except Exception as e:
                        logger.error("Twitter collection failed", error=str(e))
                
                # Collect Reddit data
                if self.reddit_collector:
                    try:
                        logger.info("Collecting Reddit data")
                        reddit_results = await self.reddit_collector.collect_data()
                        
                        logger.info(
                            "Reddit collection complete",
                            posts=reddit_results.get("posts_collected", 0),
                            comments=reddit_results.get("comments_collected", 0)
                        )
                        
                        # Get collector stats
                        reddit_status = self.reddit_collector.get_status()
                        
                        # Publish Reddit sentiment summary to RabbitMQ
                        if reddit_results.get("posts_collected", 0) > 0:
                            sentiment_summary = {
                                "source": "reddit",
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                                "posts_collected": reddit_results.get("posts_collected", 0),
                                "comments_collected": reddit_results.get("comments_collected", 0),
                                "sentiment_distribution": reddit_results.get("sentiment_distribution", {}),
                                "crypto_mentions": reddit_results.get("crypto_mentions", {}),
                                "collector_status": reddit_status
                            }
                            
                            await self._publish_to_rabbitmq(
                                sentiment_summary,
                                "social_sentiment",
                                "social.sentiment.reddit"
                            )
                            
                    except Exception as e:
                        logger.error("Reddit collection failed", error=str(e))
                
                # Collect LunarCrush data
                if self.lunarcrush_collector:
                    try:
                        logger.info("Collecting LunarCrush data")
                        lunarcrush_results = await self.lunarcrush_collector.collect_data()
                        
                        logger.info(
                            "LunarCrush collection complete",
                            metrics_collected=lunarcrush_results.get("metrics_collected", 0),
                            symbols_processed=lunarcrush_results.get("symbols_processed", 0)
                        )
                        
                        # Get collector stats
                        lunarcrush_status = self.lunarcrush_collector.get_status()
                        
                        # Publish LunarCrush metrics summary to RabbitMQ
                        if lunarcrush_results.get("metrics_collected", 0) > 0:
                            metrics_summary = {
                                "source": "lunarcrush",
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                                "metrics_collected": lunarcrush_results.get("metrics_collected", 0),
                                "symbols_processed": lunarcrush_results.get("symbols_processed", 0),
                                "top_gainers": lunarcrush_results.get("top_gainers", []),
                                "top_losers": lunarcrush_results.get("top_losers", []),
                                "collector_status": lunarcrush_status
                            }
                            
                            await self._publish_to_rabbitmq(
                                metrics_summary,
                                "social_metrics",
                                "social.metrics.lunarcrush"
                            )
                            
                    except Exception as e:
                        logger.error("LunarCrush collection failed", error=str(e))
                
                # Log cycle completion
                cycle_duration = (datetime.now(timezone.utc) - cycle_start).total_seconds()
                logger.info(
                    "Social collection cycle complete",
                    duration_seconds=cycle_duration,
                    next_cycle_in=interval
                )
                
                # Wait for next cycle
                await asyncio.sleep(interval)
                
            except asyncio.CancelledError:
                logger.info("Social collection cancelled")
                break
            except Exception as e:
                logger.error("Error in social collection cycle", error=str(e))
                await asyncio.sleep(60)  # Wait 1 minute before retry on error
            
    async def _get_stock_market_summary(self, current_data: List[Dict]) -> Dict:
        """Generate stock market summary from current data"""
        try:
            summary = {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "total_indices": len(current_data),
                "categories": {},
                "market_sentiment": "neutral",
                "key_indices": {}
            }
            
            # Categorize indices and calculate sentiment
            positive_count = 0
            negative_count = 0
            
            for data in current_data:
                symbol = data.get('symbol', '')
                change_percent = data.get('change_percent', 0)
                category = data.get('metadata', {}).get('category', 'unknown')
                
                # Count sentiment
                if change_percent > 0:
                    positive_count += 1
                elif change_percent < 0:
                    negative_count += 1
                    
                # Group by category
                if category not in summary["categories"]:
                    summary["categories"][category] = {
                        "count": 0,
                        "avg_change": 0,
                        "positive": 0,
                        "negative": 0
                    }
                    
                summary["categories"][category]["count"] += 1
                if change_percent > 0:
                    summary["categories"][category]["positive"] += 1
                elif change_percent < 0:
                    summary["categories"][category]["negative"] += 1
                    
                # Track key US indices
                if symbol in ["^GSPC", "^IXIC", "^DJI", "^VIX"]:
                    summary["key_indices"][symbol] = {
                        "current_price": data.get('current_price'),
                        "change": data.get('change'),
                        "change_percent": change_percent,
                        "full_name": data.get('metadata', {}).get('full_name', symbol)
                    }
                    
            # Determine overall market sentiment
            total_counted = positive_count + negative_count
            if total_counted > 0:
                positive_ratio = positive_count / total_counted
                if positive_ratio > 0.6:
                    summary["market_sentiment"] = "bullish"
                elif positive_ratio < 0.4:
                    summary["market_sentiment"] = "bearish"
                else:
                    summary["market_sentiment"] = "neutral"
                    
            summary["sentiment_breakdown"] = {
                "positive": positive_count,
                "negative": negative_count,
                "neutral": len(current_data) - total_counted,
                "positive_ratio": positive_count / len(current_data) if current_data else 0
            }
            
            return summary
            
        except Exception as e:
            logger.error("Error generating stock market summary", error=str(e))
            return {"error": "Failed to generate summary"}
            
    async def _get_market_correlation_data(self) -> Dict:
        """Get correlation indicators between crypto and stock markets"""
        try:
            # Get correlation indicators from database
            correlation_indicators = await self.database.get_market_correlation_indicators()
            return correlation_indicators
            
        except Exception as e:
            logger.error("Error getting market correlation data", error=str(e))
            return {"error": "Failed to get correlation data"}
            
    async def _start_data_maintenance(self):
        """Start periodic data maintenance tasks"""
        try:
            logger.info("Starting data maintenance tasks")
            
            while self.running:
                try:
                    # Check for missing data and backfill
                    for symbol in self.symbols:
                        try:
                            filled_count = await self.historical_collector.backfill_missing_data(
                                symbol=symbol,
                                interval="1m",
                                check_days=1  # Check last day for gaps
                            )
                            
                            if filled_count > 0:
                                logger.info(f"Backfilled {filled_count} records for {symbol}")
                                
                        except Exception as e:
                            logger.error(f"Error in backfill for {symbol}", error=str(e))
                            
                    # Sleep for 1 hour before next maintenance cycle
                    await asyncio.sleep(3600)
                    
                except Exception as e:
                    logger.error("Error in maintenance cycle", error=str(e))
                    await asyncio.sleep(600)  # Wait 10 minutes before retry
                    
        except Exception as e:
            logger.error("Error starting data maintenance", error=str(e))
    
    async def stop(self):
        """Stop the service gracefully"""
        logger.info("Stopping enhanced market data service...")
        self.running = False
        
        # Cancel all background tasks
        all_tasks = self.websocket_tasks + self.scheduled_tasks
        for task in all_tasks:
            task.cancel()
        
        if all_tasks:
            await asyncio.gather(*all_tasks, return_exceptions=True)
        
        # Stop indicator system
        if hasattr(self, 'indicator_config_manager') and self.indicator_config_manager:
            await self.indicator_config_manager.stop_processing()
        
        # Close collectors
        if hasattr(self, 'historical_collector') and self.historical_collector:
            await self.historical_collector.disconnect()
            
        if hasattr(self, 'sentiment_collector') and self.sentiment_collector:
            await self.sentiment_collector.disconnect()
            
        if hasattr(self, 'stock_index_collector') and self.stock_index_collector:
            await self.stock_index_collector.disconnect()
        
        # Close on-chain collectors
        if hasattr(self, 'moralis_collector') and self.moralis_collector:
            await self.moralis_collector.disconnect()
            logger.info("Moralis collector disconnected")
            
        if hasattr(self, 'glassnode_collector') and self.glassnode_collector:
            await self.glassnode_collector.disconnect()
            logger.info("Glassnode collector disconnected")
        
        # Close social media collectors
        if hasattr(self, 'twitter_collector') and self.twitter_collector:
            await self.twitter_collector.disconnect()
            logger.info("Twitter collector disconnected")
            
        if hasattr(self, 'reddit_collector') and self.reddit_collector:
            await self.reddit_collector.disconnect()
            logger.info("Reddit collector disconnected")
            
        if hasattr(self, 'lunarcrush_collector') and self.lunarcrush_collector:
            await self.lunarcrush_collector.disconnect()
            logger.info("LunarCrush collector disconnected")
        
        # Stop signal aggregator
        if hasattr(self, 'signal_aggregator') and self.signal_aggregator:
            await self.signal_aggregator.stop()
            logger.info("Signal aggregator stopped")

        if self.socket_manager:
            try:
                await self.socket_manager.close()
            except Exception as exc:
                logger.warning("Error closing Binance socket manager", error=str(exc))
            self.socket_manager = None

        if self.binance_client:
            try:
                await self.binance_client.close_connection()
            except Exception as exc:
                logger.warning("Error closing Binance client", error=str(exc))
            self.binance_client = None
        
        # Close connections
        if self.rabbitmq_connection and not self.rabbitmq_connection.is_closed:
            await self.rabbitmq_connection.close()
        
        # Close Redis cache
        if self.redis_cache:
            try:
                await self.redis_cache.disconnect()
                logger.info("Redis cache disconnected")
            except Exception as e:
                logger.warning("Error closing Redis cache", error=str(e))
        
        if self.database:
            await self.database.disconnect()
        
        websocket_connections.set(0)
        logger.info("Market data service stopped successfully")
        logger.info("Market data service stopped")


# Health check endpoint
async def health_check(request):
    return web.json_response({'status': 'healthy', 'service': 'market_data_service'})

async def get_cache_stats(request):
    """Get Redis cache statistics"""
    try:
        service = request.app['service']
        
        stats = {
            'service_stats': {
                'cache_hits': service.cache_hits,
                'cache_misses': service.cache_misses,
                'hit_rate': service.cache_hits / (service.cache_hits + service.cache_misses) if (service.cache_hits + service.cache_misses) > 0 else 0.0
            },
            'redis_connected': service.redis_cache is not None and service.redis_cache._connected if service.redis_cache else False
        }
        
        # Add collector stats if available
        if service.historical_collector and hasattr(service.historical_collector, 'cache_hits'):
            stats['historical_collector'] = {
                'cache_hits': service.historical_collector.cache_hits,
                'cache_misses': service.historical_collector.cache_misses,
                'hit_rate': service.historical_collector.cache_hits / (service.historical_collector.cache_hits + service.historical_collector.cache_misses) if (service.historical_collector.cache_hits + service.historical_collector.cache_misses) > 0 else 0.0
            }
        
        # Add signal aggregator stats if available
        if service.signal_aggregator and hasattr(service.signal_aggregator, 'cache_hits'):
            stats['signal_aggregator'] = {
                'cache_hits': service.signal_aggregator.cache_hits,
                'cache_misses': service.signal_aggregator.cache_misses,
                'hit_rate': service.signal_aggregator.cache_hits / (service.signal_aggregator.cache_hits + service.signal_aggregator.cache_misses) if (service.signal_aggregator.cache_hits + service.signal_aggregator.cache_misses) > 0 else 0.0
            }
        
        return web.json_response({
            'success': True,
            'stats': stats
        })
        
    except Exception as e:
        return web.json_response({
            'success': False,
            'error': str(e)
        }, status=500)

async def get_whale_transactions(request):
    """Get recent whale transactions"""
    try:
        service = request.app['service']
        
        # Get query parameters
        symbol = request.query.get('symbol', None)
        hours = int(request.query.get('hours', 24))
        min_amount = float(request.query.get('min_amount', 0)) if request.query.get('min_amount') else None
        limit = int(request.query.get('limit', 100))
        
        # Query database
        transactions = await service.database.get_whale_transactions(
            symbol=symbol,
            hours=hours,
            min_amount=min_amount,
            limit=limit
        )
        
        return web.json_response({
            'success': True,
            'count': len(transactions),
            'transactions': transactions
        })
        
    except Exception as e:
        logger.error("Error getting whale transactions", error=str(e))
        return web.json_response({
            'success': False,
            'error': str(e)
        }, status=500)

async def get_onchain_metrics(request):
    """Get on-chain metrics"""
    try:
        service = request.app['service']
        
        # Get query parameters
        symbol = request.query.get('symbol', 'BTC')
        metric_name = request.query.get('metric_name', None)
        hours = int(request.query.get('hours', 24))
        limit = int(request.query.get('limit', 100))
        
        # Query database
        metrics = await service.database.get_onchain_metrics(
            symbol=symbol,
            metric_name=metric_name,
            hours=hours,
            limit=limit
        )
        
        return web.json_response({
            'success': True,
            'symbol': symbol,
            'count': len(metrics),
            'metrics': metrics
        })
        
    except Exception as e:
        logger.error("Error getting on-chain metrics", error=str(e))
        return web.json_response({
            'success': False,
            'error': str(e)
        }, status=500)

async def get_collector_health(request):
    """Get collector health status"""
    try:
        service = request.app['service']
        
        # Get query parameters
        collector_name = request.query.get('collector', None)
        hours = int(request.query.get('hours', 24))
        
        # Query database
        health_logs = await service.database.get_collector_health(
            collector_name=collector_name,
            hours=hours
        )
        
        # Get current collector status
        collectors_status = {}
        
        if service.moralis_collector:
            collectors_status['moralis'] = await service.moralis_collector.get_status()
        
        if service.glassnode_collector:
            collectors_status['glassnode'] = await service.glassnode_collector.get_status()
        
        return web.json_response({
            'success': True,
            'current_status': collectors_status,
            'health_logs': health_logs,
            'count': len(health_logs)
        })
        
    except Exception as e:
        logger.error("Error getting collector health", error=str(e))
        return web.json_response({
            'success': False,
            'error': str(e)
        }, status=500)

async def get_social_sentiment(request):
    """Get social sentiment data (Twitter, Reddit)"""
    try:
        # Get query parameters
        symbol = request.query.get('symbol')
        source = request.query.get('source')  # twitter, reddit
        hours = int(request.query.get('hours', 24))
        limit = int(request.query.get('limit', 100))
        
        # Get sentiment data from database
        service = request.app['service']
        sentiment_data = await service.database.get_social_sentiment(
            symbol=symbol,
            source=source,
            hours=hours,
            limit=limit
        )
        
        return web.json_response({
            'success': True,
            'data': sentiment_data,
            'count': len(sentiment_data),
            'filters': {
                'symbol': symbol,
                'source': source,
                'hours': hours,
                'limit': limit
            }
        })
        
    except Exception as e:
        logger.error("Error getting social sentiment", error=str(e))
        return web.json_response({
            'success': False,
            'error': str(e)
        }, status=500)

async def get_social_metrics(request):
    """Get aggregated social metrics (LunarCrush)"""
    try:
        # Get query parameters
        symbol = request.query.get('symbol')
        hours = int(request.query.get('hours', 24))
        limit = int(request.query.get('limit', 100))
        
        # Get metrics from database
        service = request.app['service']
        metrics_data = await service.database.get_social_metrics_aggregated(
            symbol=symbol,
            hours=hours,
            limit=limit
        )
        
        return web.json_response({
            'success': True,
            'data': metrics_data,
            'count': len(metrics_data),
            'filters': {
                'symbol': symbol,
                'hours': hours,
                'limit': limit
            }
        })
        
    except Exception as e:
        logger.error("Error getting social metrics", error=str(e))
        return web.json_response({
            'success': False,
            'error': str(e)
        }, status=500)

async def get_trending_topics(request):
    """Get trending cryptocurrency topics based on social volume"""
    try:
        # Get query parameters
        limit = int(request.query.get('limit', 10))
        
        # Get trending topics from database
        service = request.app['service']
        trending = await service.database.get_trending_topics(limit=limit)
        
        return web.json_response({
            'success': True,
            'data': trending,
            'count': len(trending)
        })
        
    except Exception as e:
        logger.error("Error getting trending topics", error=str(e))
        return web.json_response({
            'success': False,
            'error': str(e)
        }, status=500)

async def get_social_collectors_health(request):
    """Get health status of social collectors"""
    try:
        service = request.app['service']
        
        # Get collector health
        collector_name = request.query.get('collector')  # twitter, reddit, lunarcrush
        hours = int(request.query.get('hours', 24))
        
        health_logs = await service.database.get_collector_health(
            collector_name=collector_name,
            hours=hours
        )
        
        # Get current collector status
        collectors_status = {}
        
        if service.twitter_collector:
            collectors_status['twitter'] = service.twitter_collector.get_status()
        
        if service.reddit_collector:
            collectors_status['reddit'] = service.reddit_collector.get_status()
        
        if service.lunarcrush_collector:
            collectors_status['lunarcrush'] = service.lunarcrush_collector.get_status()
        
        return web.json_response({
            'success': True,
            'current_status': collectors_status,
            'health_logs': health_logs,
            'count': len(health_logs)
        })
        
    except Exception as e:
        logger.error("Error getting social collector health", error=str(e))
        return web.json_response({
            'success': False,
            'error': str(e)
        }, status=500)

async def get_all_collectors_health(request):
    """Get health status for all collectors"""
    try:
        service = request.app['service']
        
        # Get health summary from database
        try:
            summary = await service.database.get_collector_health_summary()
        except Exception as db_error:
            logger.error("Database error getting health summary", error=str(db_error))
            summary = {}
        
        # Enrich with real-time status if collectors are running
        collectors = {}
        
        # On-chain collectors
        if hasattr(service, 'moralis_collector') and service.moralis_collector:
            collectors['moralis'] = {
                **summary.get('moralis', {}),
                'enabled': True
            }
        
        if hasattr(service, 'glassnode_collector') and service.glassnode_collector:
            collectors['glassnode'] = {
                **summary.get('glassnode', {}),
                'enabled': True
            }
        
        # Social collectors
        if hasattr(service, 'twitter_collector') and service.twitter_collector:
            collectors['twitter'] = {
                **summary.get('twitter', {}),
                'enabled': True
            }
        
        if hasattr(service, 'reddit_collector') and service.reddit_collector:
            collectors['reddit'] = {
                **summary.get('reddit', {}),
                'enabled': True
            }
        
        if hasattr(service, 'lunarcrush_collector') and service.lunarcrush_collector:
            collectors['lunarcrush'] = {
                **summary.get('lunarcrush', {}),
                'enabled': True
            }
        
        # Add database records for any other collectors
        for collector_name, health_info in summary.items():
            if collector_name not in collectors:
                collectors[collector_name] = {
                    **health_info,
                    'enabled': False
                }
        
        return web.json_response({
            'success': True,
            'collectors': collectors,
            'collector_count': len(collectors),
            'timestamp': datetime.now(timezone.utc).isoformat()
        })
        
    except Exception as e:
        import traceback
        logger.error("Error getting collectors health", error=str(e), traceback=traceback.format_exc())
        return web.json_response({
            'success': False,
            'error': str(e),
            'error_type': type(e).__name__
        }, status=500)

async def get_collector_health_detail(request):
    """Get detailed health history for a specific collector"""
    try:
        service = request.app['service']
        collector_name = request.match_info.get('collector_name')
        
        if not collector_name:
            return web.json_response({
                'success': False,
                'error': 'collector_name is required'
            }, status=400)
        
        # Get parameters
        limit = int(request.query.get('limit', 100))
        hours_back = int(request.query.get('hours', 24))
        
        # Get health records from database
        health_records = await service.database.get_collector_health(
            collector_name=collector_name,
            limit=limit,
            hours_back=hours_back
        )
        
        if not health_records:
            return web.json_response({
                'success': False,
                'error': f'No health records found for collector: {collector_name}'
            }, status=404)
        
        # Calculate health statistics
        total_checks = len(health_records)
        healthy_count = sum(1 for r in health_records if r['status'] == 'healthy')
        failed_count = sum(1 for r in health_records if r['status'] == 'failed')
        degraded_count = sum(1 for r in health_records if r['status'] == 'degraded')
        
        health_rate = (healthy_count / total_checks * 100) if total_checks > 0 else 0
        
        return web.json_response({
            'success': True,
            'collector_name': collector_name,
            'statistics': {
                'total_checks': total_checks,
                'healthy': healthy_count,
                'failed': failed_count,
                'degraded': degraded_count,
                'health_rate': round(health_rate, 2)
            },
            'recent_records': health_records[:20],  # Return last 20 for UI
            'all_records_count': total_checks
        })
        
    except Exception as e:
        import traceback
        logger.error("Error getting collector health detail", error=str(e), traceback=traceback.format_exc())
        return web.json_response({
            'success': False,
            'error': str(e),
            'error_type': type(e).__name__
        }, status=500)

# ============================================================================
# Signal Buffer Endpoints
# ============================================================================

async def get_recent_signals(request):
    """
    Get recent aggregated signals from Redis buffer
    
    Query parameters:
    - symbol: Filter by trading pair (optional)
    - limit: Max signals to return (default: 100, max: 1000)
    - hours: Only return signals from last N hours (optional)
    
    Example: /signals/recent?symbol=BTCUSDT&limit=50&hours=24
    """
    try:
        service = request.app['service']
        
        if not service.signal_aggregator:
            return web.json_response({
                'success': False,
                'error': 'Signal aggregator not initialized'
            }, status=503)
        
        # Parse query parameters
        symbol = request.query.get('symbol')
        limit = min(int(request.query.get('limit', 100)), 1000)  # Cap at 1000
        hours_back = int(request.query.get('hours')) if 'hours' in request.query else None
        
        # Get signals from buffer
        signals = await service.signal_aggregator.get_recent_signals(
            symbol=symbol,
            limit=limit,
            hours_back=hours_back
        )
        
        # Serialize signals
        signals_data = []
        for signal in signals:
            signal_dict = signal.model_dump() if hasattr(signal, 'model_dump') else signal.dict()
            # Convert datetime objects to ISO strings
            for key, value in signal_dict.items():
                if isinstance(value, datetime):
                    signal_dict[key] = value.isoformat()
            signals_data.append(signal_dict)
        
        return web.json_response({
            'success': True,
            'signals': signals_data,
            'count': len(signals_data),
            'filters': {
                'symbol': symbol,
                'limit': limit,
                'hours_back': hours_back
            }
        })
        
    except ValueError as e:
        return web.json_response({
            'success': False,
            'error': f'Invalid parameter: {str(e)}'
        }, status=400)
    except Exception as e:
        import traceback
        logger.error("Error getting recent signals", error=str(e), traceback=traceback.format_exc())
        return web.json_response({
            'success': False,
            'error': str(e),
            'error_type': type(e).__name__
        }, status=500)

async def get_signal_statistics(request):
    """
    Get statistics about recent signals for a symbol
    
    Query parameters:
    - symbol: Trading pair (required)
    - hours: Period to analyze (default: 24)
    
    Example: /signals/stats?symbol=BTCUSDT&hours=48
    """
    try:
        service = request.app['service']
        
        if not service.signal_aggregator:
            return web.json_response({
                'success': False,
                'error': 'Signal aggregator not initialized'
            }, status=503)
        
        # Parse query parameters
        symbol = request.query.get('symbol')
        if not symbol:
            return web.json_response({
                'success': False,
                'error': 'symbol parameter is required'
            }, status=400)
        
        hours = int(request.query.get('hours', 24))
        
        # Get statistics
        stats = await service.signal_aggregator.get_signal_statistics(symbol, hours)
        
        # Convert datetime in latest_signal if present
        if stats.get('latest_signal') and isinstance(stats['latest_signal'].get('timestamp'), datetime):
            stats['latest_signal']['timestamp'] = stats['latest_signal']['timestamp'].isoformat()
        
        return web.json_response({
            'success': True,
            'statistics': stats
        })
        
    except ValueError as e:
        return web.json_response({
            'success': False,
            'error': f'Invalid parameter: {str(e)}'
        }, status=400)
    except Exception as e:
        import traceback
        logger.error("Error getting signal statistics", error=str(e), traceback=traceback.format_exc())
        return web.json_response({
            'success': False,
            'error': str(e),
            'error_type': type(e).__name__
        }, status=500)

async def get_signal_buffer_info(request):
    """
    Get information about the signal buffer (size, TTL, etc.)
    
    Example: /signals/buffer/info
    """
    try:
        service = request.app['service']
        
        if not service.signal_aggregator or not service.signal_aggregator.redis_cache:
            return web.json_response({
                'success': False,
                'error': 'Redis signal buffer not available'
            }, status=503)
        
        redis = service.signal_aggregator.redis_cache
        redis_key = "signals:recent"
        
        # Get buffer info
        buffer_size = await redis.zcard(redis_key)
        ttl = await redis.ttl(redis_key)
        
        # Get time range of buffered signals
        oldest_signal = None
        newest_signal = None
        
        if buffer_size > 0:
            # Get oldest (first in sorted set)
            oldest = await redis.zrange(redis_key, 0, 0, withscores=True)
            if oldest:
                oldest_signal = datetime.fromtimestamp(oldest[0][1]).isoformat()
            
            # Get newest (last in sorted set)
            newest = await redis.zrange(redis_key, -1, -1, withscores=True)
            if newest:
                newest_signal = datetime.fromtimestamp(newest[0][1]).isoformat()
        
        return web.json_response({
            'success': True,
            'buffer_info': {
                'current_size': buffer_size,
                'max_size': 1000,
                'ttl_seconds': ttl if ttl > 0 else None,
                'ttl_hours': round(ttl / 3600, 2) if ttl > 0 else None,
                'oldest_signal': oldest_signal,
                'newest_signal': newest_signal,
                'redis_key': redis_key
            }
        })
        
    except Exception as e:
        import traceback
        logger.error("Error getting buffer info", error=str(e), traceback=traceback.format_exc())
        return web.json_response({
            'success': False,
            'error': str(e),
            'error_type': type(e).__name__
        }, status=500)

# ============================================================================
# Data Source Management Endpoints
# ============================================================================

async def list_collectors(request):
    """List all collectors with their status, configuration, and metrics"""
    try:
        service = request.app['service']
        
        collectors_info = {}
        
        # Helper function to get collector info
        def get_collector_info(collector, name, collector_type):
            if not collector:
                return None
            
            info = {
                'name': name,
                'type': collector_type,
                'enabled': True,
                'connected': getattr(collector, 'session', None) is not None,
            }
            
            # Get rate limiter stats
            if hasattr(collector, 'rate_limiter'):
                rl = collector.rate_limiter
                info['rate_limiter'] = {
                    'current_rate': rl.max_requests_per_second,
                    'backoff_multiplier': rl.backoff_multiplier,
                    'total_requests': rl.total_requests,
                    'total_throttles': rl.total_throttles,
                    'total_backoffs': rl.total_backoffs,
                    'last_request_time': rl.last_request_time.isoformat() if rl.last_request_time else None,
                }
                
                # Get per-endpoint stats if available
                if hasattr(rl, 'endpoint_stats') and rl.endpoint_stats:
                    info['rate_limiter']['endpoints'] = {}
                    for endpoint, stats in rl.endpoint_stats.items():
                        info['rate_limiter']['endpoints'][endpoint] = {
                            'requests': stats['requests'],
                            'rate_limit': stats.get('rate_limit'),
                            'remaining': stats.get('remaining'),
                            'reset_time': stats.get('reset_time')
                        }
            
            # Get circuit breaker status
            if hasattr(collector, 'circuit_breaker'):
                cb_status = collector.circuit_breaker.get_status()
                info['circuit_breaker'] = {
                    'state': cb_status['state'],
                    'failure_count': cb_status['failure_count'],
                    'failure_threshold': cb_status['failure_threshold'],
                    'health_score': cb_status.get('health_score', 0),
                    'statistics': cb_status.get('statistics', {})
                }
            
            # Get collector-specific config
            if hasattr(collector, 'api_key'):
                info['has_api_key'] = bool(collector.api_key)
            
            if hasattr(collector, 'rate_limit'):
                info['configured_rate_limit'] = collector.rate_limit
            
            return info
        
        # On-chain collectors
        if service.moralis_collector:
            collectors_info['moralis'] = get_collector_info(service.moralis_collector, 'moralis', 'onchain')
        if service.glassnode_collector:
            collectors_info['glassnode'] = get_collector_info(service.glassnode_collector, 'glassnode', 'onchain')
        
        # Social media collectors
        if service.twitter_collector:
            collectors_info['twitter'] = get_collector_info(service.twitter_collector, 'twitter', 'social')
        if service.reddit_collector:
            collectors_info['reddit'] = get_collector_info(service.reddit_collector, 'reddit', 'social')
        if service.lunarcrush_collector:
            collectors_info['lunarcrush'] = get_collector_info(service.lunarcrush_collector, 'lunarcrush', 'social')
        
        # Historical and sentiment collectors
        if service.historical_collector:
            info = {
                'name': 'historical',
                'type': 'market_data',
                'enabled': True,
                'connected': True
            }
            collectors_info['historical'] = info
        
        if service.sentiment_collector:
            info = {
                'name': 'sentiment',
                'type': 'sentiment',
                'enabled': True,
                'connected': True
            }
            collectors_info['sentiment'] = info
        
        if service.stock_index_collector:
            info = {
                'name': 'stock_index',
                'type': 'market_data',
                'enabled': True,
                'connected': True
            }
            collectors_info['stock_index'] = info
        
        return web.json_response({
            'success': True,
            'collectors': collectors_info,
            'total_count': len(collectors_info),
            'timestamp': datetime.now(timezone.utc).isoformat()
        })
        
    except Exception as e:
        import traceback
        logger.error("Error listing collectors", error=str(e), traceback=traceback.format_exc())
        return web.json_response({
            'success': False,
            'error': str(e)
        }, status=500)

async def get_collector_status(request):
    """Get detailed status for a specific collector"""
    try:
        service = request.app['service']
        collector_name = request.match_info.get('name')
        
        collector_map = {
            'moralis': service.moralis_collector,
            'glassnode': service.glassnode_collector,
            'twitter': service.twitter_collector,
            'reddit': service.reddit_collector,
            'lunarcrush': service.lunarcrush_collector,
            'historical': service.historical_collector,
            'sentiment': service.sentiment_collector,
            'stock_index': service.stock_index_collector
        }
        
        collector = collector_map.get(collector_name)
        if not collector:
            return web.json_response({
                'success': False,
                'error': f'Collector not found: {collector_name}'
            }, status=404)
        
        status = {
            'name': collector_name,
            'enabled': True,
            'connected': getattr(collector, 'session', None) is not None,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        # Rate limiter details
        if hasattr(collector, 'rate_limiter'):
            rl = collector.rate_limiter
            status['rate_limiter'] = {
                'current_rate': rl.max_requests_per_second,
                'initial_rate': rl.initial_rate,
                'backoff_multiplier': rl.backoff_multiplier,
                'max_backoff': rl.max_backoff,
                'statistics': {
                    'total_requests': rl.total_requests,
                    'total_throttles': rl.total_throttles,
                    'total_backoffs': rl.total_backoffs,
                    'total_429_errors': rl.total_429_errors,
                    'total_adjustments': rl.total_adjustments
                },
                'last_request_time': rl.last_request_time.isoformat() if rl.last_request_time else None,
                'last_adjustment_time': rl.last_adjustment_time.isoformat() if rl.last_adjustment_time else None
            }
            
            # Per-endpoint statistics
            if hasattr(rl, 'endpoint_stats') and rl.endpoint_stats:
                status['rate_limiter']['endpoint_details'] = rl.endpoint_stats
        
        # Circuit breaker details
        if hasattr(collector, 'circuit_breaker'):
            cb_status = collector.circuit_breaker.get_status()
            status['circuit_breaker'] = cb_status
        
        # Get recent health records from database
        try:
            health_records = await service.database.get_collector_health(
                collector_name=collector_name,
                limit=10,
                hours=24
            )
            
            if health_records:
                status['recent_health'] = health_records[:5]
                status['health_summary'] = {
                    'total_checks': len(health_records),
                    'healthy': sum(1 for r in health_records if r.get('status') == 'healthy'),
                    'failed': sum(1 for r in health_records if r.get('status') == 'failed')
                }
        except Exception as e:
            logger.warning(f"Could not fetch health records for {collector_name}", error=str(e))
        
        # Cost tracking (if available)
        if hasattr(collector, 'api_calls_count'):
            status['usage'] = {
                'api_calls': collector.api_calls_count
            }
        
        return web.json_response({
            'success': True,
            'collector': status
        })
        
    except Exception as e:
        import traceback
        logger.error("Error getting collector status", error=str(e), traceback=traceback.format_exc())
        return web.json_response({
            'success': False,
            'error': str(e)
        }, status=500)

async def enable_collector(request):
    """Enable a collector"""
    try:
        service = request.app['service']
        collector_name = request.match_info.get('name')
        
        collector_map = {
            'moralis': service.moralis_collector,
            'glassnode': service.glassnode_collector,
            'twitter': service.twitter_collector,
            'reddit': service.reddit_collector,
            'lunarcrush': service.lunarcrush_collector
        }
        
        collector = collector_map.get(collector_name)
        if not collector:
            return web.json_response({
                'success': False,
                'error': f'Collector not found: {collector_name}'
            }, status=404)
        
        # For now, collectors are always enabled when initialized
        # In the future, we could add an 'enabled' flag to collectors
        
        logger.info(f"Collector {collector_name} enabled via API")
        
        return web.json_response({
            'success': True,
            'message': f'Collector {collector_name} is enabled',
            'collector': collector_name
        })
        
    except Exception as e:
        import traceback
        logger.error("Error enabling collector", error=str(e), traceback=traceback.format_exc())
        return web.json_response({
            'success': False,
            'error': str(e)
        }, status=500)

async def disable_collector(request):
    """Disable a collector"""
    try:
        service = request.app['service']
        collector_name = request.match_info.get('name')
        
        collector_map = {
            'moralis': service.moralis_collector,
            'glassnode': service.glassnode_collector,
            'twitter': service.twitter_collector,
            'reddit': service.reddit_collector,
            'lunarcrush': service.lunarcrush_collector
        }
        
        collector = collector_map.get(collector_name)
        if not collector:
            return web.json_response({
                'success': False,
                'error': f'Collector not found: {collector_name}'
            }, status=404)
        
        # Disconnect the collector
        if hasattr(collector, 'disconnect'):
            await collector.disconnect()
        
        logger.info(f"Collector {collector_name} disabled via API")
        
        return web.json_response({
            'success': True,
            'message': f'Collector {collector_name} has been disabled',
            'collector': collector_name
        })
        
    except Exception as e:
        import traceback
        logger.error("Error disabling collector", error=str(e), traceback=traceback.format_exc())
        return web.json_response({
            'success': False,
            'error': str(e)
        }, status=500)

async def restart_collector(request):
    """Restart a collector (disconnect and reconnect)"""
    try:
        service = request.app['service']
        collector_name = request.match_info.get('name')
        
        collector_map = {
            'moralis': service.moralis_collector,
            'glassnode': service.glassnode_collector,
            'twitter': service.twitter_collector,
            'reddit': service.reddit_collector,
            'lunarcrush': service.lunarcrush_collector
        }
        
        collector = collector_map.get(collector_name)
        if not collector:
            return web.json_response({
                'success': False,
                'error': f'Collector not found: {collector_name}'
            }, status=404)
        
        # Disconnect
        if hasattr(collector, 'disconnect'):
            await collector.disconnect()
            logger.info(f"Collector {collector_name} disconnected")
        
        # Wait a moment
        await asyncio.sleep(1)
        
        # Reconnect
        if hasattr(collector, 'connect'):
            await collector.connect()
            logger.info(f"Collector {collector_name} reconnected")
        
        logger.info(f"Collector {collector_name} restarted via API")
        
        return web.json_response({
            'success': True,
            'message': f'Collector {collector_name} has been restarted',
            'collector': collector_name
        })
        
    except Exception as e:
        import traceback
        logger.error("Error restarting collector", error=str(e), traceback=traceback.format_exc())
        return web.json_response({
            'success': False,
            'error': str(e)
        }, status=500)

async def configure_collector_rate_limit(request):
    """Update rate limit configuration for a collector"""
    try:
        service = request.app['service']
        collector_name = request.match_info.get('name')
        
        collector_map = {
            'moralis': service.moralis_collector,
            'glassnode': service.glassnode_collector,
            'twitter': service.twitter_collector,
            'reddit': service.reddit_collector,
            'lunarcrush': service.lunarcrush_collector
        }
        
        collector = collector_map.get(collector_name)
        if not collector:
            return web.json_response({
                'success': False,
                'error': f'Collector not found: {collector_name}'
            }, status=404)
        
        if not hasattr(collector, 'rate_limiter'):
            return web.json_response({
                'success': False,
                'error': f'Collector {collector_name} does not have rate limiting'
            }, status=400)
        
        # Get request body
        try:
            data = await request.json()
        except:
            return web.json_response({
                'success': False,
                'error': 'Invalid JSON in request body'
            }, status=400)
        
        rl = collector.rate_limiter
        
        # Update rate limit settings
        if 'max_requests_per_second' in data:
            new_rate = float(data['max_requests_per_second'])
            if new_rate <= 0:
                return web.json_response({
                    'success': False,
                    'error': 'max_requests_per_second must be positive'
                }, status=400)
            rl.max_requests_per_second = new_rate
            rl.interval = 1.0 / new_rate
            logger.info(f"Updated {collector_name} rate limit to {new_rate} req/s")
        
        if 'backoff_multiplier' in data:
            new_multiplier = float(data['backoff_multiplier'])
            if new_multiplier < 1.0:
                return web.json_response({
                    'success': False,
                    'error': 'backoff_multiplier must be >= 1.0'
                }, status=400)
            rl.backoff_multiplier = new_multiplier
            logger.info(f"Updated {collector_name} backoff multiplier to {new_multiplier}")
        
        if 'max_backoff' in data:
            new_max = float(data['max_backoff'])
            if new_max < 1.0:
                return web.json_response({
                    'success': False,
                    'error': 'max_backoff must be >= 1.0'
                }, status=400)
            rl.max_backoff = new_max
            logger.info(f"Updated {collector_name} max backoff to {new_max}")
        
        # Save to Redis if available
        if hasattr(rl, 'save_state_to_redis'):
            await rl.save_state_to_redis()
        
        return web.json_response({
            'success': True,
            'message': f'Rate limit configuration updated for {collector_name}',
            'collector': collector_name,
            'updated_config': {
                'max_requests_per_second': rl.max_requests_per_second,
                'backoff_multiplier': rl.backoff_multiplier,
                'max_backoff': rl.max_backoff
            }
        })
        
    except Exception as e:
        import traceback
        logger.error("Error configuring rate limit", error=str(e), traceback=traceback.format_exc())
        return web.json_response({
            'success': False,
            'error': str(e)
        }, status=500)

async def reset_circuit_breaker(request):
    """Reset circuit breaker for a collector"""
    try:
        service = request.app['service']
        collector_name = request.match_info.get('name')
        
        collector_map = {
            'moralis': service.moralis_collector,
            'glassnode': service.glassnode_collector,
            'twitter': service.twitter_collector,
            'reddit': service.reddit_collector,
            'lunarcrush': service.lunarcrush_collector
        }
        
        collector = collector_map.get(collector_name)
        if not collector:
            return web.json_response({
                'success': False,
                'error': f'Collector not found: {collector_name}'
            }, status=404)
        
        if not hasattr(collector, 'circuit_breaker'):
            return web.json_response({
                'success': False,
                'error': f'Collector {collector_name} does not have circuit breaker'
            }, status=400)
        
        # Reset the circuit breaker
        collector.circuit_breaker.reset()
        
        # Save to Redis if available
        if hasattr(collector.circuit_breaker, 'save_state_to_redis'):
            await collector.circuit_breaker.save_state_to_redis()
        
        logger.info(f"Circuit breaker reset for {collector_name} via API")
        
        return web.json_response({
            'success': True,
            'message': f'Circuit breaker reset for {collector_name}',
            'collector': collector_name,
            'new_state': collector.circuit_breaker.get_status()
        })
        
    except Exception as e:
        import traceback
        logger.error("Error resetting circuit breaker", error=str(e), traceback=traceback.format_exc())
        return web.json_response({
            'success': False,
            'error': str(e)
        }, status=500)

async def force_circuit_breaker_state(request):
    """Force circuit breaker to open or closed state"""
    try:
        service = request.app['service']
        collector_name = request.match_info.get('name')
        
        collector_map = {
            'moralis': service.moralis_collector,
            'glassnode': service.glassnode_collector,
            'twitter': service.twitter_collector,
            'reddit': service.reddit_collector,
            'lunarcrush': service.lunarcrush_collector
        }
        
        collector = collector_map.get(collector_name)
        if not collector:
            return web.json_response({
                'success': False,
                'error': f'Collector not found: {collector_name}'
            }, status=404)
        
        if not hasattr(collector, 'circuit_breaker'):
            return web.json_response({
                'success': False,
                'error': f'Collector {collector_name} does not have circuit breaker'
            }, status=400)
        
        # Get request body
        try:
            data = await request.json()
        except:
            return web.json_response({
                'success': False,
                'error': 'Invalid JSON in request body'
            }, status=400)
        
        state = data.get('state', '').lower()
        if state not in ['open', 'closed']:
            return web.json_response({
                'success': False,
                'error': 'state must be "open" or "closed"'
            }, status=400)
        
        cb = collector.circuit_breaker
        
        if state == 'open':
            cb.force_open()
        else:
            cb.force_close()
        
        # Save to Redis if available
        if hasattr(cb, 'save_state_to_redis'):
            await cb.save_state_to_redis()
        
        logger.info(f"Circuit breaker forced to {state} for {collector_name} via API")
        
        return web.json_response({
            'success': True,
            'message': f'Circuit breaker forced to {state} for {collector_name}',
            'collector': collector_name,
            'new_state': cb.get_status()
        })
        
    except Exception as e:
        import traceback
        logger.error("Error forcing circuit breaker state", error=str(e), traceback=traceback.format_exc())
        return web.json_response({
            'success': False,
            'error': str(e)
        }, status=500)

async def get_collector_costs(request):
    """Get cost and quota information for collectors"""
    try:
        service = request.app['service']
        
        costs = {}
        
        # Define cost structures (these would ideally come from config or database)
        cost_info = {
            'moralis': {
                'tier': 'Pro',
                'monthly_quota': 3000000,  # 3M compute units
                'cost_per_call': 0.00001,  # Approximate
                'quota_unit': 'compute_units'
            },
            'glassnode': {
                'tier': 'Professional',
                'daily_quota': 10000,
                'cost_per_call': 0.001,
                'quota_unit': 'requests'
            },
            'twitter': {
                'tier': 'Essential',
                'monthly_quota': 500000,
                'cost_per_call': 0.0001,
                'quota_unit': 'tweets'
            },
            'reddit': {
                'tier': 'Free',
                'daily_quota': 60,  # 60 requests per minute
                'cost_per_call': 0,
                'quota_unit': 'requests'
            },
            'lunarcrush': {
                'tier': 'Pro',
                'daily_quota': 10000,
                'cost_per_call': 0.0005,
                'quota_unit': 'requests'
            }
        }
        
        collector_map = {
            'moralis': service.moralis_collector,
            'glassnode': service.glassnode_collector,
            'twitter': service.twitter_collector,
            'reddit': service.reddit_collector,
            'lunarcrush': service.lunarcrush_collector
        }
        
        for name, collector in collector_map.items():
            if not collector:
                continue
            
            usage = {
                'api_calls': 0,
                'estimated_cost': 0.0
            }
            
            # Get usage from rate limiter
            if hasattr(collector, 'rate_limiter'):
                usage['api_calls'] = collector.rate_limiter.total_requests
                
                if name in cost_info:
                    cost_per_call = cost_info[name]['cost_per_call']
                    usage['estimated_cost'] = usage['api_calls'] * cost_per_call
            
            costs[name] = {
                **cost_info.get(name, {}),
                'current_usage': usage,
                'quota_remaining': None  # Would need to track this
            }
        
        # Calculate totals
        total_calls = sum(c['current_usage']['api_calls'] for c in costs.values())
        total_cost = sum(c['current_usage']['estimated_cost'] for c in costs.values())
        
        return web.json_response({
            'success': True,
            'collectors': costs,
            'totals': {
                'total_api_calls': total_calls,
                'total_estimated_cost': round(total_cost, 2)
            },
            'timestamp': datetime.now(timezone.utc).isoformat()
        })
        
    except Exception as e:
        import traceback
        logger.error("Error getting collector costs", error=str(e), traceback=traceback.format_exc())
        return web.json_response({
            'success': False,
            'error': str(e)
        }, status=500)

# ============================================================================
# Enhanced REST API v1 Endpoints - On-Chain Data
# ============================================================================

async def api_v1_whale_transactions(request):
    """
    GET /api/v1/onchain/whale-transactions
    
    Query whale transactions with filtering options.
    
    Query Parameters:
        - symbol (str, optional): Filter by cryptocurrency symbol (e.g., 'BTC', 'ETH')
        - hours (int, default=24): Hours of history to retrieve
        - min_amount (float, optional): Minimum transaction amount in USD
        - limit (int, default=100): Maximum number of results
        - from_entity (str, optional): Filter by sender entity
        - to_entity (str, optional): Filter by receiver entity
    
    Returns:
        JSON response with whale transactions
    """
    try:
        service = request.app['service']
        
        # Parse query parameters
        symbol = request.query.get('symbol')
        hours = int(request.query.get('hours', 24))
        min_amount = float(request.query.get('min_amount')) if request.query.get('min_amount') else None
        limit = int(request.query.get('limit', 100))
        
        # Query database
        transactions = await service.database.get_whale_transactions(
            symbol=symbol,
            hours=hours,
            min_amount=min_amount,
            limit=limit
        )
        
        # Calculate summary statistics
        if transactions:
            total_volume = sum(float(tx.get('amount', 0)) for tx in transactions)
            avg_amount = total_volume / len(transactions) if transactions else 0
            max_transaction = max(transactions, key=lambda x: float(x.get('amount', 0)))
            
            # Count by type
            exchange_inflows = sum(1 for tx in transactions if tx.get('transaction_type') == 'exchange_inflow')
            exchange_outflows = sum(1 for tx in transactions if tx.get('transaction_type') == 'exchange_outflow')
            large_transfers = sum(1 for tx in transactions if tx.get('transaction_type') == 'large_transfer')
        else:
            total_volume = 0
            avg_amount = 0
            max_transaction = None
            exchange_inflows = 0
            exchange_outflows = 0
            large_transfers = 0
        
        return web.json_response({
            'success': True,
            'data': transactions,
            'count': len(transactions),
            'summary': {
                'total_volume_usd': round(total_volume, 2),
                'average_amount_usd': round(avg_amount, 2),
                'largest_transaction': {
                    'amount': float(max_transaction.get('amount', 0)) if max_transaction else 0,
                    'symbol': max_transaction.get('symbol') if max_transaction else None,
                    'tx_hash': max_transaction.get('tx_hash') if max_transaction else None
                } if max_transaction else None,
                'by_type': {
                    'exchange_inflows': exchange_inflows,
                    'exchange_outflows': exchange_outflows,
                    'large_transfers': large_transfers
                }
            },
            'filters': {
                'symbol': symbol,
                'hours': hours,
                'min_amount': min_amount,
                'limit': limit
            },
            'timestamp': datetime.now(timezone.utc).isoformat()
        })
        
    except ValueError as e:
        return web.json_response({
            'success': False,
            'error': f'Invalid parameter value: {str(e)}'
        }, status=400)
    except Exception as e:
        logger.error("Error getting whale transactions", error=str(e))
        return web.json_response({
            'success': False,
            'error': str(e)
        }, status=500)

async def api_v1_onchain_metrics_by_symbol(request):
    """
    GET /api/v1/onchain/metrics/{symbol}
    
    Get on-chain metrics for a specific cryptocurrency.
    
    Path Parameters:
        - symbol (str): Cryptocurrency symbol (e.g., 'BTC', 'ETH')
    
    Query Parameters:
        - metric_name (str, optional): Specific metric to retrieve (nvt, mvrv, exchange_flow, etc.)
        - hours (int, default=24): Hours of history to retrieve
        - limit (int, default=100): Maximum number of results
    
    Returns:
        JSON response with on-chain metrics
    """
    try:
        service = request.app['service']
        
        # Get path parameter
        symbol = request.match_info.get('symbol', '').upper()
        if not symbol:
            return web.json_response({
                'success': False,
                'error': 'Symbol is required'
            }, status=400)
        
        # Parse query parameters
        metric_name = request.query.get('metric_name')
        hours = int(request.query.get('hours', 24))
        limit = int(request.query.get('limit', 100))
        
        # Query database
        metrics = await service.database.get_onchain_metrics(
            symbol=symbol,
            metric_name=metric_name,
            hours=hours,
            limit=limit
        )
        
        # Group metrics by name for better presentation
        metrics_by_name = {}
        for metric in metrics:
            name = metric.get('metric_name')
            if name not in metrics_by_name:
                metrics_by_name[name] = []
            metrics_by_name[name].append(metric)
        
        # Get latest value for each metric
        latest_metrics = {}
        for name, metric_list in metrics_by_name.items():
            if metric_list:
                # Sort by timestamp and get latest
                sorted_metrics = sorted(metric_list, key=lambda x: x.get('timestamp', ''), reverse=True)
                latest_metrics[name] = {
                    'value': sorted_metrics[0].get('value'),
                    'timestamp': sorted_metrics[0].get('timestamp'),
                    'unit': sorted_metrics[0].get('unit', ''),
                    'data_points': len(metric_list)
                }
        
        return web.json_response({
            'success': True,
            'symbol': symbol,
            'data': metrics,
            'count': len(metrics),
            'latest_metrics': latest_metrics,
            'available_metrics': list(metrics_by_name.keys()),
            'filters': {
                'metric_name': metric_name,
                'hours': hours,
                'limit': limit
            },
            'timestamp': datetime.now(timezone.utc).isoformat()
        })
        
    except ValueError as e:
        return web.json_response({
            'success': False,
            'error': f'Invalid parameter value: {str(e)}'
        }, status=400)
    except Exception as e:
        logger.error("Error getting on-chain metrics", error=str(e), symbol=symbol)
        return web.json_response({
            'success': False,
            'error': str(e)
        }, status=500)

async def api_v1_wallet_info(request):
    """
    GET /api/v1/onchain/wallet/{address}
    
    Get information about a specific wallet address.
    
    Path Parameters:
        - address (str): Wallet address to query
    
    Query Parameters:
        - include_transactions (bool, default=false): Include recent transactions
        - tx_limit (int, default=10): Number of recent transactions to include
    
    Returns:
        JSON response with wallet information
    """
    try:
        service = request.app['service']
        
        # Get path parameter
        address = request.match_info.get('address', '').lower()
        if not address:
            return web.json_response({
                'success': False,
                'error': 'Wallet address is required'
            }, status=400)
        
        # Validate address format (basic check for Ethereum-like addresses)
        if not address.startswith('0x') or len(address) != 42:
            return web.json_response({
                'success': False,
                'error': 'Invalid wallet address format. Expected Ethereum address (0x...)'
            }, status=400)
        
        # Parse query parameters
        include_transactions = request.query.get('include_transactions', 'false').lower() == 'true'
        tx_limit = int(request.query.get('tx_limit', 10))
        
        # Get wallet label/category if known
        wallet_label = await service.database.get_wallet_label(address)
        
        response_data = {
            'success': True,
            'address': address,
            'label': wallet_label.get('label') if wallet_label else 'Unknown',
            'category': wallet_label.get('category') if wallet_label else 'unknown',
            'is_labeled': wallet_label is not None,
            'metadata': wallet_label.get('metadata', {}) if wallet_label else {}
        }
        
        # Optionally include recent transactions involving this address
        if include_transactions:
            # Query whale transactions that involve this address
            all_transactions = await service.database.get_whale_transactions(
                hours=168,  # Last week
                limit=1000  # Get more to filter
            )
            
            # Filter transactions involving this address
            wallet_transactions = [
                tx for tx in all_transactions
                if tx.get('from_address', '').lower() == address or
                   tx.get('to_address', '').lower() == address
            ][:tx_limit]
            
            # Calculate transaction summary
            total_sent = sum(
                float(tx.get('amount', 0))
                for tx in wallet_transactions
                if tx.get('from_address', '').lower() == address
            )
            total_received = sum(
                float(tx.get('amount', 0))
                for tx in wallet_transactions
                if tx.get('to_address', '').lower() == address
            )
            
            response_data['transactions'] = {
                'recent': wallet_transactions,
                'count': len(wallet_transactions),
                'summary': {
                    'total_sent_usd': round(total_sent, 2),
                    'total_received_usd': round(total_received, 2),
                    'net_flow_usd': round(total_received - total_sent, 2)
                }
            }
        
        response_data['timestamp'] = datetime.now(timezone.utc).isoformat()
        
        return web.json_response(response_data)
        
    except ValueError as e:
        return web.json_response({
            'success': False,
            'error': f'Invalid parameter value: {str(e)}'
        }, status=400)
    except Exception as e:
        logger.error("Error getting wallet info", error=str(e), address=address)
        return web.json_response({
            'success': False,
            'error': str(e)
        }, status=500)

# ============================================================================
# End of Enhanced REST API v1 Endpoints
# ============================================================================

# ==========================================
# Enhanced REST API v1 - Social Sentiment Endpoints
# ==========================================

async def api_v1_social_sentiment_by_symbol(request):
    """
    REST API endpoint to get aggregated sentiment data for a symbol
    
    GET /api/v1/social/sentiment/{symbol}
    
    Path Parameters:
        symbol: Cryptocurrency symbol (e.g., BTC, ETH)
    
    Query Parameters:
        hours: Hours of history (default: 24, max: 720)
        source: Filter by source (twitter, reddit, all) (optional)
        limit: Maximum results (default: 100, max: 1000)
    
    Returns:
        {
            "success": true,
            "symbol": "BTC",
            "data": [...sentiment records...],
            "count": 50,
            "summary": {
                "average_sentiment": 0.65,
                "total_mentions": 1234,
                "total_engagement": 56789,
                "sentiment_breakdown": {
                    "positive": 60,
                    "neutral": 30,
                    "negative": 10
                },
                "by_source": {
                    "twitter": {"count": 800, "avg_sentiment": 0.68},
                    "reddit": {"count": 434, "avg_sentiment": 0.61}
                }
            },
            "filters": {...},
            "timestamp": "2025-11-11T12:00:00Z"
        }
    """
    try:
        service = request.app['service']
        
        # Extract path parameter
        symbol = request.match_info.get('symbol', '').upper()
        if not symbol:
            return web.Response(
                text=json.dumps({
                    "success": False,
                    "error": "Symbol parameter is required"
                }),
                status=400,
                content_type='application/json'
            )
        
        # Parse query parameters
        hours = int(request.query.get('hours', 24))
        hours = min(max(hours, 1), 720)  # Clamp between 1 and 720 hours
        
        source = request.query.get('source', '').lower()
        if source and source not in ['twitter', 'reddit', 'all', '']:
            return web.Response(
                text=json.dumps({
                    "success": False,
                    "error": "Invalid source. Must be 'twitter', 'reddit', or 'all'"
                }),
                status=400,
                content_type='application/json'
            )
        
        # Use None for 'all' or empty string
        if source in ['all', '']:
            source = None
        
        limit = int(request.query.get('limit', 100))
        limit = min(max(limit, 1), 1000)  # Clamp between 1 and 1000
        
        # Get sentiment data from database
        sentiment_data = await service.database.get_social_sentiment(
            symbol=symbol,
            source=source,
            hours=hours,
            limit=limit
        )
        
        # Calculate summary statistics
        summary = {
            "average_sentiment": 0.0,
            "total_mentions": len(sentiment_data),
            "total_engagement": 0,
            "sentiment_breakdown": {
                "positive": 0,
                "neutral": 0,
                "negative": 0
            },
            "by_source": {}
        }
        
        if sentiment_data:
            sentiment_scores = []
            source_stats = {}
            
            for record in sentiment_data:
                # Extract sentiment score
                score = record.get('sentiment_score', 0.0)
                if isinstance(score, (int, float)):
                    sentiment_scores.append(score)
                    
                    # Classify sentiment
                    if score > 0.2:
                        summary["sentiment_breakdown"]["positive"] += 1
                    elif score < -0.2:
                        summary["sentiment_breakdown"]["negative"] += 1
                    else:
                        summary["sentiment_breakdown"]["neutral"] += 1
                
                # Aggregate engagement
                engagement = record.get('engagement_score', 0)
                if isinstance(engagement, (int, float)):
                    summary["total_engagement"] += int(engagement)
                
                # Track by source
                rec_source = record.get('source', 'unknown')
                if rec_source not in source_stats:
                    source_stats[rec_source] = {
                        "count": 0,
                        "total_sentiment": 0.0
                    }
                source_stats[rec_source]["count"] += 1
                source_stats[rec_source]["total_sentiment"] += score
            
            # Calculate averages
            if sentiment_scores:
                summary["average_sentiment"] = sum(sentiment_scores) / len(sentiment_scores)
            
            # Calculate per-source averages
            for src, stats in source_stats.items():
                summary["by_source"][src] = {
                    "count": stats["count"],
                    "avg_sentiment": stats["total_sentiment"] / stats["count"] if stats["count"] > 0 else 0.0
                }
        
        response = {
            "success": True,
            "symbol": symbol,
            "data": sentiment_data,
            "count": len(sentiment_data),
            "summary": summary,
            "filters": {
                "hours": hours,
                "source": source if source else "all",
                "limit": limit
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        return web.Response(
            text=json.dumps(response, indent=2),
            content_type='application/json'
        )
        
    except ValueError as e:
        logger.error("Invalid query parameter", error=str(e))
        return web.Response(
            text=json.dumps({
                "success": False,
                "error": f"Invalid parameter value: {str(e)}"
            }),
            status=400,
            content_type='application/json'
        )
    except Exception as e:
        logger.error("Error in api_v1_social_sentiment_by_symbol", error=str(e))
        return web.Response(
            text=json.dumps({
                "success": False,
                "error": "Internal server error"
            }),
            status=500,
            content_type='application/json'
        )


async def api_v1_social_trending(request):
    """
    REST API endpoint to get trending cryptocurrencies
    
    GET /api/v1/social/trending
    
    Query Parameters:
        limit: Number of trending topics (default: 20, max: 100)
        hours: Hours to analyze (default: 24, max: 168)
    
    Returns:
        {
            "success": true,
            "data": [
                {
                    "symbol": "BTC",
                    "mention_count": 1234,
                    "avg_sentiment": 0.65,
                    "total_engagement": 56789,
                    "unique_authors": 890,
                    "rank": 1
                },
                ...
            ],
            "count": 20,
            "filters": {...},
            "timestamp": "2025-11-11T12:00:00Z"
        }
    """
    try:
        service = request.app['service']
        
        # Parse query parameters
        limit = int(request.query.get('limit', 20))
        limit = min(max(limit, 1), 100)  # Clamp between 1 and 100
        
        hours = int(request.query.get('hours', 24))
        hours = min(max(hours, 1), 168)  # Clamp between 1 and 168 hours (1 week)
        
        # Get trending topics from database
        # Note: The database method doesn't currently support hours parameter
        # We'll use the default 24-hour window
        trending_data = await service.database.get_trending_topics(limit=limit)
        
        # Add rank to each item
        for idx, item in enumerate(trending_data, start=1):
            item["rank"] = idx
        
        response = {
            "success": True,
            "data": trending_data,
            "count": len(trending_data),
            "filters": {
                "limit": limit,
                "hours": 24  # Fixed at 24 hours for now
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        return web.Response(
            text=json.dumps(response, indent=2),
            content_type='application/json'
        )
        
    except ValueError as e:
        logger.error("Invalid query parameter", error=str(e))
        return web.Response(
            text=json.dumps({
                "success": False,
                "error": f"Invalid parameter value: {str(e)}"
            }),
            status=400,
            content_type='application/json'
        )
    except Exception as e:
        logger.error("Error in api_v1_social_trending", error=str(e))
        return web.Response(
            text=json.dumps({
                "success": False,
                "error": "Internal server error"
            }),
            status=500,
            content_type='application/json'
        )


async def api_v1_social_influencers(request):
    """
    REST API endpoint to get top influencers and their sentiment
    
    GET /api/v1/social/influencers
    
    Query Parameters:
        symbol: Filter by cryptocurrency symbol (optional)
        limit: Number of influencers to return (default: 50, max: 200)
        hours: Hours of history (default: 24, max: 168)
        min_followers: Minimum follower count (optional)
    
    Returns:
        {
            "success": true,
            "data": [
                {
                    "author_id": "user123",
                    "username": "crypto_guru",
                    "follower_count": 50000,
                    "post_count": 15,
                    "avg_sentiment": 0.75,
                    "total_engagement": 12345,
                    "symbols_mentioned": ["BTC", "ETH"],
                    "is_verified": true
                },
                ...
            ],
            "count": 50,
            "filters": {...},
            "timestamp": "2025-11-11T12:00:00Z"
        }
    """
    try:
        service = request.app['service']
        
        # Parse query parameters
        symbol = request.query.get('symbol', '').upper() if request.query.get('symbol') else None
        
        limit = int(request.query.get('limit', 50))
        limit = min(max(limit, 1), 200)  # Clamp between 1 and 200
        
        hours = int(request.query.get('hours', 24))
        hours = min(max(hours, 1), 168)  # Clamp between 1 and 168 hours
        
        min_followers = request.query.get('min_followers')
        if min_followers:
            min_followers = int(min_followers)
        else:
            min_followers = 0
        
        # Get influencer data from database
        # We need to query social_sentiment table with is_influencer = true
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        
        if symbol:
            query = """
                SELECT 
                    data->>'author_id' as author_id,
                    data->>'author_username' as username,
                    MAX((data->>'author_followers')::int) as follower_count,
                    COUNT(*) as post_count,
                    AVG((data->>'sentiment_score')::float) as avg_sentiment,
                    SUM((data->>'engagement_score')::int) as total_engagement,
                    ARRAY_AGG(DISTINCT data->>'symbol') as symbols_mentioned,
                    BOOL_OR((data->>'is_verified')::boolean) as is_verified
                FROM social_sentiment
                WHERE (data->>'is_influencer')::boolean = true
                  AND data->>'symbol' = $1
                  AND (data->>'timestamp')::timestamptz >= $2
                GROUP BY data->>'author_id', data->>'author_username'
                HAVING MAX((data->>'author_followers')::int) >= $3
                ORDER BY follower_count DESC, total_engagement DESC
                LIMIT $4
            """
            params = [symbol, cutoff, min_followers, limit]
        else:
            query = """
                SELECT 
                    data->>'author_id' as author_id,
                    data->>'author_username' as username,
                    MAX((data->>'author_followers')::int) as follower_count,
                    COUNT(*) as post_count,
                    AVG((data->>'sentiment_score')::float) as avg_sentiment,
                    SUM((data->>'engagement_score')::int) as total_engagement,
                    ARRAY_AGG(DISTINCT data->>'symbol') as symbols_mentioned,
                    BOOL_OR((data->>'is_verified')::boolean) as is_verified
                FROM social_sentiment
                WHERE (data->>'is_influencer')::boolean = true
                  AND (data->>'timestamp')::timestamptz >= $1
                GROUP BY data->>'author_id', data->>'author_username'
                HAVING MAX((data->>'author_followers')::int) >= $2
                ORDER BY follower_count DESC, total_engagement DESC
                LIMIT $3
            """
            params = [cutoff, min_followers, limit]
        
        rows = await service.database._postgres.fetch(query, *params)
        
        influencers = []
        for row in rows:
            influencers.append({
                "author_id": row["author_id"],
                "username": row["username"],
                "follower_count": row["follower_count"],
                "post_count": row["post_count"],
                "avg_sentiment": float(row["avg_sentiment"]) if row["avg_sentiment"] else 0.0,
                "total_engagement": row["total_engagement"] if row["total_engagement"] else 0,
                "symbols_mentioned": row["symbols_mentioned"],
                "is_verified": row["is_verified"] if row["is_verified"] else False
            })
        
        response = {
            "success": True,
            "data": influencers,
            "count": len(influencers),
            "filters": {
                "symbol": symbol if symbol else "all",
                "limit": limit,
                "hours": hours,
                "min_followers": min_followers
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        return web.Response(
            text=json.dumps(response, indent=2),
            content_type='application/json'
        )
        
    except ValueError as e:
        logger.error("Invalid query parameter", error=str(e))
        return web.Response(
            text=json.dumps({
                "success": False,
                "error": f"Invalid parameter value: {str(e)}"
            }),
            status=400,
            content_type='application/json'
        )
    except Exception as e:
        logger.error("Error in api_v1_social_influencers", error=str(e))
        return web.Response(
            text=json.dumps({
                "success": False,
                "error": "Internal server error"
            }),
            status=500,
            content_type='application/json'
        )

async def create_health_server():
    """Create health check server"""
    app = web.Application()
    app.router.add_get('/health', health_check)
    app.router.add_get('/cache/stats', get_cache_stats)
    
    # General collector health endpoints
    app.router.add_get('/health/collectors', get_all_collectors_health)
    app.router.add_get('/health/collectors/{collector_name}', get_collector_health_detail)
    
    # Signal buffer endpoints
    app.router.add_get('/signals/recent', get_recent_signals)
    app.router.add_get('/signals/stats', get_signal_statistics)
    app.router.add_get('/signals/buffer/info', get_signal_buffer_info)
    
    # On-chain data endpoints (legacy, kept for backward compatibility)
    app.router.add_get('/onchain/whales', get_whale_transactions)
    app.router.add_get('/onchain/metrics', get_onchain_metrics)
    app.router.add_get('/onchain/collectors/health', get_collector_health)
    
    # Enhanced REST API v1 - On-Chain Data Endpoints
    app.router.add_get('/api/v1/onchain/whale-transactions', api_v1_whale_transactions)
    app.router.add_get('/api/v1/onchain/metrics/{symbol}', api_v1_onchain_metrics_by_symbol)
    app.router.add_get('/api/v1/onchain/wallet/{address}', api_v1_wallet_info)
    
    # Enhanced REST API v1 - Social Sentiment Endpoints
    app.router.add_get('/api/v1/social/sentiment/{symbol}', api_v1_social_sentiment_by_symbol)
    app.router.add_get('/api/v1/social/trending', api_v1_social_trending)
    app.router.add_get('/api/v1/social/influencers', api_v1_social_influencers)
    
    # Social sentiment endpoints
    app.router.add_get('/social/sentiment', get_social_sentiment)
    app.router.add_get('/social/metrics', get_social_metrics)
    app.router.add_get('/social/trending', get_trending_topics)
    app.router.add_get('/social/collectors/health', get_social_collectors_health)
    
    # Data Source Management Endpoints
    app.router.add_get('/collectors', list_collectors)
    app.router.add_get('/collectors/{name}', get_collector_status)
    app.router.add_post('/collectors/{name}/enable', enable_collector)
    app.router.add_post('/collectors/{name}/disable', disable_collector)
    app.router.add_post('/collectors/{name}/restart', restart_collector)
    app.router.add_put('/collectors/{name}/rate-limit', configure_collector_rate_limit)
    app.router.add_post('/collectors/{name}/circuit-breaker/reset', reset_circuit_breaker)
    app.router.add_put('/collectors/{name}/circuit-breaker/state', force_circuit_breaker_state)
    app.router.add_get('/collectors/costs', get_collector_costs)
    
    return app

async def main():
    """Main application entry point"""
    # Setup signal handlers
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Start Prometheus metrics server on separate port (9001)
    start_http_server(settings.PROMETHEUS_PORT)
    logger.info(f"Started Prometheus metrics server on port {settings.PROMETHEUS_PORT}")
    
    # Initialize service first
    service = MarketDataService()
    
    # Start health check server on port 8000
    health_app = await create_health_server()
    health_app['service'] = service  # Store service reference for endpoints
    health_runner = web.AppRunner(health_app)
    await health_runner.setup()
    health_site = web.TCPSite(health_runner, '0.0.0.0', 8000)
    await health_site.start()
    logger.info("Started health check server on port 8000")
    
    try:
        await service.initialize()
        await service.start_enhanced_features()
        
        # Keep service running
        logger.info("Market data service is running with enhanced features...")
        while service.running:
            await asyncio.sleep(1)
        
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    except Exception as e:
        logger.error("Service error", error=str(e))
        sys.exit(1)
    finally:
        await service.stop()


if __name__ == "__main__":
    # Use uvloop for better performance
    uvloop.install()
    asyncio.run(main())
