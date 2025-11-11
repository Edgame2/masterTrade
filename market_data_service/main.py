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
        
        # Technical indicator system
        self.indicator_calculator = None
        self.indicator_config_manager = None
        self.strategy_request_handler = None
        
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
            self.historical_collector = HistoricalDataCollector(self.database)
            await self.historical_collector.connect()
            logger.info("Historical data collector initialized")
            
            # Initialize sentiment data collector
            if settings.SENTIMENT_ENABLED:
                self.sentiment_collector = SentimentDataCollector(self.database)
                await self.sentiment_collector.connect()
                logger.info("Sentiment data collector initialized")
                
            # Initialize stock index collector
            if settings.STOCK_INDEX_ENABLED:
                self.stock_index_collector = StockIndexDataCollector(self.database)
                await self.stock_index_collector.connect()
                logger.info("Stock index collector initialized")
            
            # Initialize on-chain collectors
            if settings.ONCHAIN_COLLECTION_ENABLED:
                if settings.MORALIS_API_KEY:
                    self.moralis_collector = MoralisCollector(
                        database=self.database,
                        api_key=settings.MORALIS_API_KEY,
                        rate_limit=settings.MORALIS_RATE_LIMIT
                    )
                    await self.moralis_collector.connect()
                    logger.info("Moralis on-chain collector initialized")
                else:
                    logger.warning("MORALIS_API_KEY not set - Moralis collector disabled")
                
                if settings.GLASSNODE_API_KEY:
                    self.glassnode_collector = GlassnodeCollector(
                        database=self.database,
                        api_key=settings.GLASSNODE_API_KEY,
                        rate_limit=settings.GLASSNODE_RATE_LIMIT
                    )
                    await self.glassnode_collector.connect()
                    logger.info("Glassnode on-chain collector initialized")
                else:
                    logger.warning("GLASSNODE_API_KEY not set - Glassnode collector disabled")
            
            # Initialize RabbitMQ
            try:
                await self._init_rabbitmq()
                logger.info("RabbitMQ connection established")
            except Exception as e:
                logger.warning("RabbitMQ unavailable, continuing without messaging", error=str(e))
            
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
        
        if self.database:
            await self.database.disconnect()
        
        websocket_connections.set(0)
        logger.info("Market data service stopped successfully")
        logger.info("Market data service stopped")


# Health check endpoint
async def health_check(request):
    return web.json_response({'status': 'healthy', 'service': 'market_data_service'})

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

async def create_health_server():
    """Create health check server"""
    app = web.Application()
    app.router.add_get('/health', health_check)
    app.router.add_get('/onchain/whales', get_whale_transactions)
    app.router.add_get('/onchain/metrics', get_onchain_metrics)
    app.router.add_get('/onchain/collectors/health', get_collector_health)
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
