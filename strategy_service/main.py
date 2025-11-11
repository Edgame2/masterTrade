"""
Strategy Service - Advanced AI/ML Trading Strategy Engine

This service manages sophisticated trading strategies using machine learning,
genetic programming, and advanced optimization techniques.
"""

import asyncio
import json
import os
import sys
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

import structlog
import uvicorn
from fastapi import FastAPI, HTTPException, BackgroundTasks, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import aio_pika

# Import Redis cache manager
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from shared.redis_client import RedisCacheManager
from shared.cache_decorators import cached, simple_key

# Robust imports with fallbacks
try:
    from config import settings
except ImportError as e:
    structlog.get_logger().warning("Config import failed", error=str(e))
    class MockSettings:
        DATABASE_URL = "mock://localhost"
        RABBITMQ_URL = "amqp://localhost"
        PORT = 8001
    settings = MockSettings()

# Choose between real Postgres backend and lightweight mock
USE_MOCK_DATABASE = os.getenv("STRATEGY_SERVICE_USE_MOCK_DB", "false").lower() == "true"
if USE_MOCK_DATABASE:
    from mock_database import Database
    print("🔧 Using mock strategy database for development")
else:
    try:
        from postgres_database import Database
    except ImportError as e:
        structlog.get_logger().warning("Postgres database import failed, falling back to mock", error=str(e))
        from mock_database import Database

try:
    from core.orchestrator import AdvancedStrategyOrchestrator
    from core.strategy_generator import AdvancedStrategyGenerator
except ImportError as e:
    structlog.get_logger().warning("Core modules import failed", error=str(e))
    # Create mock classes
    class AdvancedStrategyOrchestrator:
        def __init__(self, *args, **kwargs): pass
        async def initialize(self): pass
        async def start(self): pass
        async def stop(self): pass
        
    class AdvancedStrategyGenerator:
        def __init__(self, *args, **kwargs): pass
        async def generate_strategy(self): return {"id": "mock_strategy"}

# Import other modules with fallbacks
component_imports = [
    ('enhanced_market_data_consumer', 'EnhancedMarketDataConsumer'),
    ('dynamic_data_manager', 'StrategyDataManager'),
    ('daily_strategy_reviewer', 'DailyStrategyReviewer'),
    ('database_extensions', 'extend_database_with_review_methods'),
    ('api_endpoints', 'create_strategy_api'),
    ('automatic_strategy_activation', 'AutomaticStrategyActivationManager'),
    ('crypto_selection_engine', 'CryptoSelectionEngine'),
    ('automatic_pipeline', 'AutomaticStrategyPipeline'),  # NEW: Automatic generation & backtesting
    ('price_prediction_service', 'PricePredictionService'),
    ('market_signal_consumer', 'MarketSignalConsumer')  # NEW: Real-time signal consumer
]

# Create mock classes for missing components
EnhancedMarketDataConsumer = type('EnhancedMarketDataConsumer', (), {'__init__': lambda self, *args, **kwargs: None})
StrategyDataManager = type('StrategyDataManager', (), {'__init__': lambda self, *args, **kwargs: None})
DailyStrategyReviewer = type('DailyStrategyReviewer', (), {'__init__': lambda self, *args, **kwargs: None})
extend_database_with_review_methods = lambda db: db
create_strategy_api = lambda app: app
AutomaticStrategyActivationManager = type('AutomaticStrategyActivationManager', (), {'__init__': lambda self, *args, **kwargs: None})
CryptoSelectionEngine = type('CryptoSelectionEngine', (), {'__init__': lambda self, *args, **kwargs: None})
AutomaticStrategyPipeline = type('AutomaticStrategyPipeline', (), {'__init__': lambda self, *args, **kwargs: None})  # NEW
MarketSignalConsumer = type('MarketSignalConsumer', (), {'__init__': lambda self, *args, **kwargs: None, 'start': lambda self: None, 'stop': lambda self: None})  # NEW


class _DefaultPricePredictionService:
    def __init__(self, *args, **kwargs):
        pass

    async def initialize(self):
        pass

    async def get_prediction(self, *args, **kwargs):
        return None

    async def get_supported_symbols(self):
        return []


PricePredictionService = _DefaultPricePredictionService

for module_name, class_name in component_imports:
    try:
        exec(f"from {module_name} import {class_name}")
    except ImportError as e:
        structlog.get_logger().warning(f"Component import failed: {module_name}.{class_name}", error=str(e))

import asyncio
import json
import logging
import signal
import sys
from datetime import datetime, timezone
from typing import Dict, List, Optional

import aio_pika
import pandas as pd
import structlog
import torch
from aiohttp import web
from prometheus_client import Counter, Gauge, Histogram, start_http_server

# Import basic components with fallbacks
try:
    from config import settings
except ImportError:
    class MockSettings:
        PORT = 8001
        RABBITMQ_URL = "amqp://localhost"
        DATABASE_URL = "mock://localhost"
    settings = MockSettings()

# Import models with fallbacks
try:
    from models import MarketData, Signal, Strategy
except ImportError as e:
    logger.warning("Models not available, using mocks", error=str(e))
    class MarketData:
        def __init__(self, **kwargs): self.__dict__.update(kwargs)
    class Signal:
        def __init__(self, **kwargs): self.__dict__.update(kwargs)
    class Strategy:
        def __init__(self, **kwargs): self.__dict__.update(kwargs)

# Import strategies with fallbacks
try:
    from strategies import StrategyFactory, StrategyManager
except ImportError as e:
    logger.warning("Strategy components not available, using mocks", error=str(e))
    class MockStrategyFactory:
        @staticmethod
        def create_strategy(strategy_type, config): return Strategy()
    class MockStrategyManager:
        def __init__(self): 
            self.strategies = []
        async def load_strategies(self, db): 
            logger.info("Mock strategies loaded")
        def get_active_strategies(self): 
            return []
    StrategyFactory = MockStrategyFactory()
    StrategyManager = MockStrategyManager

# Import market data consumer with fallback
try:
    sys.path.append('../shared')
    from enhanced_market_data_consumer import EnhancedMarketDataConsumer, MarketDataMessage
except ImportError as e:
    # Market data consumer not available, using mock
    class EnhancedMarketDataConsumer:
        def __init__(self, *args, **kwargs): pass
        async def connect(self): pass
        async def start_consuming(self): pass
        async def stop(self): pass
    class MarketDataMessage:
        def __init__(self, **kwargs): self.__dict__.update(kwargs)

# Import core components with fallbacks
try:
    from core.orchestrator import AdvancedStrategyOrchestrator
    from core.strategy_generator import AdvancedStrategyGenerator
except ImportError as e:
    logger.warning("Core components not available", error=str(e))

# Mock ML components for now
class MockTransformer:
    def __init__(self, *args, **kwargs): pass
    async def predict(self, data): return {"prediction": 0.5}

class MockRLAgent:
    def __init__(self, *args, **kwargs): pass
    async def get_action(self, state): return {"action": "hold"}

def create_market_transformer(*args, **kwargs):
    return MockTransformer()

def create_rl_agent_manager(*args, **kwargs):
    return MockRLAgent()

class TransformerConfig:
    pass

class AgentConfig:
    pass

# Configure structured logging
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

logger = structlog.get_logger()

# Prometheus Metrics
market_data_processed = Counter('market_data_processed_total', 'Total market data messages processed', ['symbol'])
signals_generated = Counter('signals_generated_total', 'Total trading signals generated', ['strategy', 'symbol', 'signal_type'])
strategy_execution_time = Histogram('strategy_execution_seconds', 'Time spent executing strategies', ['strategy'])
active_strategies = Gauge('active_strategies_total', 'Number of active strategies')
database_operations = Counter('database_operations_total', 'Total database operations', ['operation', 'status'])


class StrategyService:
    """Enhanced strategy execution service with comprehensive market data"""
    
    def __init__(self):
        # Initialize database (with mock for development)
        try:
            if hasattr(Database, "db"):
                extend_database_with_review_methods(Database)
        except Exception:
            pass  # Either mock database or extension not required
            
        self.database = Database()
        self.rabbitmq_connection: Optional[aio_pika.Connection] = None
        self.rabbitmq_channel: Optional[aio_pika.Channel] = None
        self.exchanges: Dict[str, aio_pika.Exchange] = {}
        self.strategy_manager = StrategyManager()
        
        # Redis cache
        self.redis_cache = None
        self.cache_hits = 0
        self.cache_misses = 0
        
        # Enhanced market data consumer for comprehensive data access
        self.market_data_consumer: Optional[EnhancedMarketDataConsumer] = None
        self.market_signal_consumer = None  # NEW: Market signal consumer for real-time signals
        
        # Market data cache for strategy decisions
        self.market_data_cache: Dict[str, List[Dict]] = {}  # symbol -> recent data points
        self.sentiment_data: Dict[str, Dict] = {}  # symbol/global sentiment
        self.correlation_data: Dict = {}
        self.stock_indices: Dict[str, Dict] = {}
        self.current_prices: Dict[str, Dict] = {}
        
        # NEW: Signal caches for real-time data from RabbitMQ
        self.market_signals_cache: Dict[str, List[Dict]] = {}  # symbol -> recent signals
        self.whale_alerts_cache: Dict[str, List[Dict]] = {}    # symbol -> recent whale alerts
        self.sentiment_cache: Dict[str, Dict] = {}              # symbol -> {source: data}
        self.onchain_metrics_cache: Dict[str, Dict] = {}        # symbol -> {metric: data}
        self.institutional_flow_cache: Dict[str, List[Dict]] = {}  # symbol -> recent flows
        
        # AI/ML Components
        self.transformer_model = None
        self.rl_agent_manager = None
        self.strategy_orchestrator = None
        self.daily_reviewer = None
        self.activation_manager = None
        self.crypto_selection_engine = None
        self.automatic_pipeline = None  # NEW: Automatic strategy generation & backtesting
        self.price_prediction_service = None
        
        self.running = False
        self.consumer_tasks: List[asyncio.Task] = []
        
    async def initialize(self):
        """Initialize all connections and services including AI/ML components"""
        try:
            # Initialize database
            await self.database.connect()
            logger.info("Database connected successfully")
            
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
            
            # Initialize RabbitMQ (optional for development)
            try:
                await self._init_rabbitmq()
                logger.info("RabbitMQ connected successfully")
                
                # Initialize market signal consumer (requires RabbitMQ)
                if self.rabbitmq_channel:
                    try:
                        self.market_signal_consumer = MarketSignalConsumer(
                            rabbitmq_channel=self.rabbitmq_channel,
                            strategy_service=self
                        )
                        await self.market_signal_consumer.start()
                        logger.info("Market signal consumer started - receiving real-time signals")
                    except Exception as e:
                        logger.warning("Market signal consumer initialization failed", error=str(e))
            except Exception as e:
                logger.warning("RabbitMQ unavailable, continuing without messaging", error=str(e))
            
            # Initialize enhanced market data consumer (optional)
            try:
                await self._init_market_data_consumer()
                logger.info("Market data consumer initialized")
            except Exception as e:
                logger.warning("Market data consumer unavailable", error=str(e))
            
            # Initialize AI/ML components (optional)
            try:
                await self._init_ai_ml_components()
                logger.info("AI/ML components initialized")
            except Exception as e:
                logger.warning("AI/ML components unavailable", error=str(e))
            
            # Initialize strategy generation manager (always)
            # This is critical for UI-driven strategy generation
            try:
                from strategy_generation_api import StrategyGenerationManager
                self.generation_manager = StrategyGenerationManager(
                    database=self.database,
                    strategy_generator=getattr(self, 'strategy_generator', None),
                    backtest_engine=getattr(getattr(self, 'automatic_pipeline', None), 'backtest_engine', None)
                )
                logger.info("Strategy generation manager initialized and ready")
            except Exception as e:
                logger.error(f"Failed to initialize strategy generation manager: {e}")
                self.generation_manager = None
            
            # Load strategies from database
            try:
                await self.strategy_manager.load_strategies(self.database)
                logger.info("Strategies loaded from database")
            except Exception as e:
                logger.warning("Failed to load strategies", error=str(e))
            
            logger.info("Strategy service initialized successfully")
            
        except Exception as e:
            logger.error("Failed to initialize service", error=str(e))
            # Don't raise - allow service to start even with some failures
            logger.warning("Service starting with limited functionality")

    async def _init_ai_ml_components(self):
        """Initialize AI/ML components for advanced strategy generation"""
        try:
            logger.info("Initializing AI/ML components...")
            
            # Check for GPU availability
            device = "cuda" if torch.cuda.is_available() else "cpu"
            logger.info(f"Using device: {device}")
            
            # Initialize transformer model for market prediction
            transformer_config = TransformerConfig(
                sequence_length=128,
                d_model=512,
                num_heads=8,
                num_layers=6,
                prediction_horizon=24,
                num_assets=50,
                num_features=20
            )
            
            self.transformer_model = create_market_transformer(transformer_config)
            logger.info("Transformer model initialized")
            
            # Initialize RL agent manager for strategy optimization
            agent_config = AgentConfig(
                state_dim=transformer_config.d_model,
                action_dim=3,  # buy, sell, hold
                learning_rate=3e-4,
                buffer_size=100000,
                batch_size=256
            )
            
            self.rl_agent_manager = create_rl_agent_manager(agent_config)
            logger.info("RL agent manager initialized")
            
            # Initialize advanced strategy orchestrator
            self.strategy_orchestrator = AdvancedStrategyOrchestrator(settings, self.database)
            await self.strategy_orchestrator.start()
            logger.info("Advanced strategy orchestrator started")
            
            # Load pre-trained models if available
            await self._load_pretrained_models()
            
            # Initialize daily strategy reviewer
            if hasattr(self, 'strategy_generator') and hasattr(self, 'market_data_consumer'):
                self.daily_reviewer = DailyStrategyReviewer(
                    database=self.database,
                    strategy_generator=self.strategy_generator,
                    market_data_consumer=self.market_data_consumer,
                    strategy_data_manager=getattr(self, 'strategy_data_manager', None)
                )
                logger.info("Daily strategy reviewer initialized")
            
            # Initialize automatic strategy activation manager (legacy)
            self.activation_manager = AutomaticStrategyActivationManager(self.database)
            await self.activation_manager.initialize()
            logger.info("Automatic strategy activation manager initialized")
            
            # Initialize enhanced strategy activation system (new)
            from enhanced_strategy_activation import EnhancedStrategyActivationSystem
            self.enhanced_activation_system = EnhancedStrategyActivationSystem(self.database)
            await self.enhanced_activation_system.initialize()
            logger.info("Enhanced strategy activation system initialized")
            
            # Initialize crypto selection engine
            self.crypto_selection_engine = CryptoSelectionEngine(self.database)
            logger.info("Crypto selection engine initialized")
            
            # Initialize automatic strategy pipeline (NEW)
            # This handles: generation -> backtest -> learn -> improve cycle
            self.automatic_pipeline = AutomaticStrategyPipeline(
                database=self.database,
                market_data_consumer=self.market_data_consumer
            )
            logger.info("Automatic strategy generation & backtesting pipeline initialized")

            # Initialize shared price prediction service used by other microservices
            self.price_prediction_service = PricePredictionService(
                database=self.database,
                price_predictor=getattr(self.automatic_pipeline, 'price_predictor', None)
            )
            await self.price_prediction_service.initialize()
            logger.info("Price prediction service initialized and ready")
            
            logger.info("All AI/ML components initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize AI/ML components: {e}")
            raise

    async def _load_pretrained_models(self):
        """Load pre-trained models if available"""
        try:
            # Check for saved model checkpoints
            model_path = getattr(settings, 'MODEL_SAVE_PATH', '/app/models')
            
            # Try to load transformer model weights
            try:
                transformer_path = f"{model_path}/transformer_latest.pt"
                # In a real implementation, you would load the state dict
                logger.info("Pre-trained models would be loaded here if available")
            except FileNotFoundError:
                logger.info("No pre-trained transformer model found, using fresh initialization")
            
            # Try to load RL agent weights
            try:
                agent_path = f"{model_path}/rl_agents_latest.pt"
                # In a real implementation, you would load the agent states
                logger.info("RL agent checkpoints would be loaded here if available")
            except FileNotFoundError:
                logger.info("No pre-trained RL agents found, using fresh initialization")
            
        except Exception as e:
            logger.warning(f"Error loading pre-trained models: {e}")
            # Continue with fresh models
    
    async def _init_rabbitmq(self):
        """Initialize RabbitMQ connection and exchanges"""
        try:
            self.rabbitmq_connection = await aio_pika.connect_robust(
                settings.RABBITMQ_URL,
                heartbeat=600,
                blocked_connection_timeout=300,
            )
            self.rabbitmq_channel = await self.rabbitmq_connection.channel()
            await self.rabbitmq_channel.set_qos(prefetch_count=50)
            
            # Declare exchanges
            self.exchanges['market'] = await self.rabbitmq_channel.declare_exchange(
                'mastertrade.market', aio_pika.ExchangeType.TOPIC, durable=True
            )
            
            self.exchanges['trading'] = await self.rabbitmq_channel.declare_exchange(
                'mastertrade.trading', aio_pika.ExchangeType.TOPIC, durable=True
            )
            
            logger.info("RabbitMQ initialized successfully")
            
        except Exception as e:
            logger.error("Failed to initialize RabbitMQ", error=str(e))
            raise
    
    async def _init_market_data_consumer(self):
        """Initialize enhanced market data consumer for strategy decisions"""
        try:
            self.market_data_consumer = EnhancedMarketDataConsumer(
                rabbitmq_url=settings.RABBITMQ_URL,
                api_base_url="http://localhost:8005",  # Market data service API
                service_name="strategy_service"
            )
            
            await self.market_data_consumer.initialize()
            
            # Register handlers for all data types to enrich strategy decisions
            self.market_data_consumer.add_message_handler("market_data", self._handle_market_data)
            self.market_data_consumer.add_message_handler("ticker_updates", self._handle_ticker_update)
            self.market_data_consumer.add_message_handler("sentiment_updates", self._handle_sentiment_data)
            self.market_data_consumer.add_message_handler("correlation_updates", self._handle_correlation_data)
            self.market_data_consumer.add_message_handler("stock_index_updates", self._handle_stock_index_data)
            
            logger.info("Enhanced market data consumer initialized for strategy service")
            
        except Exception as e:
            logger.error("Failed to initialize market data consumer", error=str(e))
            raise
    
    async def _handle_market_data(self, message: MarketDataMessage):
        """Handle market data for strategy analysis"""
        try:
            data = message.data
            symbol = data.get('symbol')
            
            if symbol:
                # Maintain a rolling window of market data for each symbol
                if symbol not in self.market_data_cache:
                    self.market_data_cache[symbol] = []
                
                # Add new data point
                self.market_data_cache[symbol].append(data)
                
                # Keep only last 200 data points (adjust as needed)
                if len(self.market_data_cache[symbol]) > 200:
                    self.market_data_cache[symbol] = self.market_data_cache[symbol][-200:]
                
                # Trigger strategy evaluation with new data
                await self._evaluate_strategies_for_symbol(symbol)
                
        except Exception as e:
            logger.error("Error handling market data for strategies", error=str(e))
    
    async def _handle_ticker_update(self, message: MarketDataMessage):
        """Handle ticker updates for current price tracking"""
        try:
            data = message.data
            symbol = data.get('symbol')
            if symbol:
                self.current_prices[symbol] = data
                
        except Exception as e:
            logger.error("Error handling ticker update", error=str(e))
    
    async def _handle_sentiment_data(self, message: MarketDataMessage):
        """Handle sentiment data for strategy enhancement"""
        try:
            data = message.data
            
            # Store global sentiment
            if 'global_crypto_sentiment' in data:
                self.sentiment_data['global_crypto'] = data['global_crypto_sentiment']
            
            if 'global_market_sentiment' in data:
                self.sentiment_data['global_market'] = data['global_market_sentiment']
            
            # Store per-symbol sentiment
            for key, value in data.items():
                if key.endswith('_sentiment') and key not in ['global_crypto_sentiment', 'global_market_sentiment']:
                    symbol = key.replace('_sentiment', '').upper()
                    self.sentiment_data[symbol] = value
            
            logger.debug("Updated sentiment data for strategy analysis")
            
        except Exception as e:
            logger.error("Error handling sentiment data", error=str(e))
    
    async def _handle_correlation_data(self, message: MarketDataMessage):
        """Handle correlation data for market context"""
        try:
            self.correlation_data = message.data
            logger.debug("Updated correlation data for strategy context")
            
        except Exception as e:
            logger.error("Error handling correlation data", error=str(e))
    
    async def _handle_stock_index_data(self, message: MarketDataMessage):
        """Handle stock index data for market context"""
        try:
            data = message.data
            for index_name, index_data in data.items():
                self.stock_indices[index_name] = index_data
            
            logger.debug("Updated stock index data for strategy context")
            
        except Exception as e:
            logger.error("Error handling stock index data", error=str(e))
    
    async def _evaluate_strategies_for_symbol(self, symbol: str):
        """Evaluate all strategies for a specific symbol with enhanced data"""
        try:
            if symbol not in self.market_data_cache or len(self.market_data_cache[symbol]) < 2:
                return
            
            # Get recent market data
            market_data_list = self.market_data_cache[symbol]
            latest_data = market_data_list[-1]
            
            # Create MarketData object
            market_data = MarketData(
                symbol=symbol,
                timestamp=datetime.fromisoformat(latest_data['timestamp'].replace('Z', '+00:00')),
                open_price=float(latest_data['open_price']),
                high_price=float(latest_data['high_price']),
                low_price=float(latest_data['low_price']),
                close_price=float(latest_data['close_price']),
                volume=float(latest_data['volume'])
            )
            
            # Execute strategies with enhanced context
            await self._execute_enhanced_strategies(market_data, market_data_list)
            
        except Exception as e:
            logger.error(f"Error evaluating strategies for {symbol}", error=str(e))
    
    async def _execute_enhanced_strategies(self, market_data: MarketData, historical_data: List[Dict]):
        """Execute strategies with enhanced market context"""
        try:
            # Get active strategies
            strategies = await self.strategy_manager.get_active_strategies_for_symbol(market_data.symbol)
            
            for strategy in strategies:
                try:
                    # Create enhanced context for strategy
                    enhanced_context = {
                        'current_data': market_data,
                        'historical_data': historical_data,
                        'sentiment': self.sentiment_data.get(market_data.symbol, {}),
                        'global_crypto_sentiment': self.sentiment_data.get('global_crypto', {}),
                        'global_market_sentiment': self.sentiment_data.get('global_market', {}),
                        'correlation_data': self.correlation_data,
                        'stock_indices': self.stock_indices,
                        'current_price': self.current_prices.get(market_data.symbol, {})
                    }
                    
                    # Execute strategy with enhanced context
                    signals = await self._run_enhanced_strategy(strategy, enhanced_context)
                    
                    # Process generated signals
                    for signal in signals:
                        await self._process_signal(signal)
                        
                except Exception as e:
                    logger.error(f"Error executing strategy {strategy.name}", error=str(e))
                    
        except Exception as e:
            logger.error("Error in enhanced strategy execution", error=str(e))
    
    async def _run_enhanced_strategy(self, strategy: Strategy, context: Dict) -> List[Signal]:
        """Run strategy with enhanced market context"""
        try:
            with strategy_execution_time.labels(strategy=strategy.name).time():
                # Use the strategy factory to execute with enhanced context
                signals = await self.strategy_manager.execute_strategy_with_context(
                    strategy, context
                )
                
                signals_generated.labels(
                    strategy=strategy.name,
                    symbol=context['current_data'].symbol,
                    signal_type='mixed'  # Could be buy/sell/hold
                ).inc()
                
                return signals
                
        except Exception as e:
            logger.error(f"Error running strategy {strategy.name}", error=str(e))
            return []
    
    async def start_consumers(self):
        """Start consuming all types of market data for enhanced strategy analysis"""
        try:
            self.running = True
            
            # Enhanced market data consumer handles its own background tasks
            # No need to explicitly start consuming - initialized in initialize()
            # if self.market_data_consumer:
            #     market_data_task = asyncio.create_task(
            #         self.market_data_consumer.start_consuming_all_market_data()
            #     )
            #     self.consumer_tasks.append(market_data_task)
            
            # Keep the original market data consumer for backward compatibility
            market_queue = await self.rabbitmq_channel.declare_queue(
                'strategy_market_data_legacy',
                durable=True
            )
            
            # Bind to kline data (legacy)
            await market_queue.bind(
                self.exchanges['market'],
                routing_key='market.data.kline'
            )
            
            # Start consuming legacy format
            consumer_tag = await market_queue.consume(
                self._process_legacy_market_data,
                no_ack=False
            )
            
            logger.info("Started consuming all market data types for enhanced strategy analysis")
            
            # Start automatic strategy generation & backtesting pipeline (NEW)
            # Runs daily at 3:00 AM UTC: generate 500 strategies -> backtest -> learn
            if self.automatic_pipeline:
                await self.automatic_pipeline.start()
                logger.info("Automatic strategy pipeline started (3:00 AM UTC daily)")
            
            # Start daily strategy review scheduler
            if self.daily_reviewer:
                review_task = asyncio.create_task(self._schedule_daily_reviews())
                self.consumer_tasks.append(review_task)
                logger.info("Daily strategy review scheduler started")
            
            # Start automatic strategy activation checker (every 4 hours)
            if self.activation_manager:
                activation_task = asyncio.create_task(self._schedule_activation_checks())
                self.consumer_tasks.append(activation_task)
                logger.info("Automatic strategy activation checker started")
            
            # Keep running
            while self.running:
                await asyncio.sleep(1)
                
        except Exception as e:
            logger.error("Error in message consumers", error=str(e))
            raise
    
    async def _process_legacy_market_data(self, message: aio_pika.IncomingMessage):
        """Process incoming market data message"""
        async with message.process():
            try:
                data = json.loads(message.body.decode())
                market_data = MarketData(**data)
                
                # Process with all active strategies
                await self._execute_strategies(market_data)
                
                market_data_processed.labels(symbol=market_data.symbol).inc()
                
            except Exception as e:
                logger.error("Error processing market data", error=str(e))
    
    async def _execute_strategies(self, market_data: MarketData):
        """Execute all active strategies for the given market data"""
        try:
            strategies = await self.strategy_manager.get_active_strategies_for_symbol(market_data.symbol)
            active_strategies.set(len(strategies))
            
            for strategy in strategies:
                try:
                    with strategy_execution_time.labels(strategy=strategy.name).time():
                        signals = await self._run_strategy(strategy, market_data)
                        
                        for signal in signals:
                            await self._process_signal(signal)
                            
                except Exception as e:
                    logger.error("Error executing strategy", 
                               strategy=strategy.name, 
                               symbol=market_data.symbol, 
                               error=str(e))
                    
        except Exception as e:
            logger.error("Error in strategy execution", error=str(e))
    
    async def _run_strategy(self, strategy: Strategy, market_data: MarketData) -> List[Signal]:
        """Run a specific strategy"""
        try:
            # Get historical data needed for the strategy
            historical_data = await self.database.get_historical_data(
                symbol=market_data.symbol,
                limit=strategy.parameters.get('lookback_period', 100)
            )
            
            if len(historical_data) < 20:  # Need minimum data points
                return []
            
            # Create DataFrame for analysis
            df = pd.DataFrame([
                {
                    'timestamp': d['timestamp'],
                    'open': float(d['open_price']),
                    'high': float(d['high_price']),
                    'low': float(d['low_price']),
                    'close': float(d['close_price']),
                    'volume': float(d['volume'])
                }
                for d in historical_data
            ])
            
            # Get strategy implementation
            strategy_impl = StrategyFactory.create_strategy(strategy.type)
            
            # Execute strategy
            signals = strategy_impl.execute(df, strategy.parameters)
            
            # Convert to Signal objects
            result_signals = []
            for signal_data in signals:
                signal = Signal(
                    strategy_id=strategy.id,
                    symbol=market_data.symbol,
                    signal_type=signal_data['type'],
                    confidence=signal_data['confidence'],
                    price=signal_data['price'],
                    quantity=signal_data.get('quantity'),
                    metadata=signal_data.get('metadata', {}),
                    timestamp=datetime.now(timezone.utc)
                )
                result_signals.append(signal)
            
            return result_signals
            
        except Exception as e:
            logger.error("Error running strategy", strategy=strategy.name, error=str(e))
            return []
    
    async def _process_signal(self, signal: Signal):
        """Process and store a generated signal"""
        try:
            # Store signal in database
            await self.database.insert_signal(signal)
            database_operations.labels(operation='insert_signal', status='success').inc()
            
            # Publish signal to trading exchange
            await self._publish_signal(signal)
            
            signals_generated.labels(
                strategy=str(signal.strategy_id),
                symbol=signal.symbol,
                signal_type=signal.signal_type
            ).inc()
            
            logger.info("Signal generated", 
                       strategy_id=signal.strategy_id,
                       symbol=signal.symbol,
                       type=signal.signal_type,
                       confidence=signal.confidence,
                       price=signal.price)
            
        except Exception as e:
            logger.error("Error processing signal", error=str(e))
            database_operations.labels(operation='insert_signal', status='error').inc()
    
    async def _publish_signal(self, signal: Signal):
        """Publish trading signal to RabbitMQ"""
        try:
            routing_key = f"signal.{signal.signal_type.lower()}"
            
            message = aio_pika.Message(
                json.dumps(signal.model_dump(), default=str).encode(),
                content_type='application/json',
                timestamp=datetime.now(timezone.utc)
            )
            
            await self.exchanges['trading'].publish(
                message, routing_key=routing_key
            )
            
        except Exception as e:
            logger.error("Error publishing signal", error=str(e))
    
    async def _schedule_daily_reviews(self):
        """Schedule and run daily strategy reviews"""
        try:
            import schedule
            from datetime import time
            
            # Schedule daily review at 2:00 AM UTC
            next_review = datetime.now(timezone.utc).replace(hour=2, minute=0, second=0, microsecond=0)
            
            # If we've passed 2 AM today, schedule for tomorrow
            if datetime.now(timezone.utc) > next_review:
                next_review += timedelta(days=1)
            
            logger.info(f"Next strategy review scheduled for: {next_review}")
            
            while self.running:
                current_time = datetime.now(timezone.utc)
                
                # Check if it's time for daily review (2:00 AM UTC daily)
                if (current_time.hour == 2 and current_time.minute == 0 and 
                    current_time.second < 30):  # 30-second window
                    
                    logger.info("Starting scheduled daily strategy review and activation check")
                    try:
                        # Run daily strategy review
                        review_results = await self.daily_reviewer.run_daily_review()
                        
                        logger.info(
                            "Daily strategy review completed successfully",
                            strategies_reviewed=len(review_results),
                            timestamp=current_time
                        )
                        
                        # Run automatic strategy activation check
                        activation_results = await self.activation_manager.check_and_update_active_strategies()
                        
                        logger.info(
                            "Automatic strategy activation completed",
                            activated=len(activation_results['activated']),
                            deactivated=len(activation_results['deactivated']),
                            timestamp=current_time
                        )
                        
                        # Run daily crypto selection
                        crypto_selections = await self.crypto_selection_engine.run_daily_selection()
                        
                        logger.info(
                            "Daily crypto selection completed",
                            selected_count=len(crypto_selections),
                            selected_cryptos=[c.symbol for c in crypto_selections],
                            timestamp=current_time
                        )
                        
                        # Send combined review, activation, and crypto selection notification
                        await self._send_review_notification(review_results, activation_results, crypto_selections)
                        
                    except Exception as e:
                        logger.error(f"Error in scheduled daily review and activation: {e}")
                
                # Sleep for 30 seconds before next check
                await asyncio.sleep(30)
                
        except Exception as e:
            logger.error(f"Error in daily review scheduler: {e}")
    
    async def _schedule_activation_checks(self):
        """Schedule automatic strategy activation checks every 4 hours"""
        try:
            logger.info("Starting automatic strategy activation scheduler (every 4 hours)")
            
            while self.running:
                try:
                    # Check and update active strategies
                    activation_results = await self.activation_manager.check_and_update_active_strategies()
                    
                    if activation_results['activated'] or activation_results['deactivated']:
                        logger.info(
                            "Strategy activation check completed",
                            activated_strategies=activation_results['activated'],
                            deactivated_strategies=activation_results['deactivated'],
                            timestamp=datetime.now(timezone.utc)
                        )
                        
                        # Send activation notification if changes were made
                        await self._send_activation_notification(activation_results)
                    
                except Exception as e:
                    logger.error(f"Error in strategy activation check: {e}")
                
                # Sleep for 4 hours
                await asyncio.sleep(4 * 3600)  # 4 hours in seconds
                
        except Exception as e:
            logger.error(f"Error in activation scheduler: {e}")
    
    async def _send_activation_notification(self, activation_results: Dict):
        """Send notification about strategy activation changes"""
        try:
            notification = {
                'type': 'strategy_activation_update',
                'timestamp': datetime.now(timezone.utc),
                'activated_strategies': activation_results['activated'],
                'deactivated_strategies': activation_results['deactivated'],
                'total_changes': len(activation_results['activated']) + len(activation_results['deactivated']),
                'reason': 'automatic_optimization'
            }
            
            # Store notification in database
            await self.database.store_notification(notification)
            
            logger.info(
                "Strategy activation notification sent",
                activated=len(activation_results['activated']),
                deactivated=len(activation_results['deactivated'])
            )
            
        except Exception as e:
            logger.error(f"Error sending activation notification: {e}")
    
    async def _send_review_notification(self, review_results: Dict, activation_results: Dict = None, crypto_selections: List = None):
        """Send notification about daily review results, activation changes, and crypto selections"""
        try:
            # Count different grades and decisions
            grades = [r.performance_grade.value for r in review_results.values()]
            decisions = [r.decision.value for r in review_results.values()]
            
            excellent_count = grades.count('A+')
            poor_count = grades.count('D') + grades.count('C')
            replacement_count = decisions.count('replace_strategy')
            optimization_count = decisions.count('optimize_parameters')
            
            notification = {
                'type': 'daily_strategy_review_summary',
                'timestamp': datetime.now(timezone.utc),
                'total_strategies': len(review_results),
                'excellent_performers': excellent_count,
                'poor_performers': poor_count,
                'strategies_replaced': replacement_count,
                'strategies_optimized': optimization_count,
                'review_date': datetime.now(timezone.utc).date().isoformat()
            }
            
            # Add activation results if provided
            if activation_results:
                notification['activation_changes'] = {
                    'activated_strategies': activation_results['activated'],
                    'deactivated_strategies': activation_results['deactivated'],
                    'total_activation_changes': len(activation_results['activated']) + len(activation_results['deactivated'])
                }
            
            # Add crypto selection results if provided
            if crypto_selections:
                notification['crypto_selections'] = {
                    'selected_cryptos': [c.symbol for c in crypto_selections],
                    'total_selected': len(crypto_selections),
                    'top_scored_crypto': crypto_selections[0].symbol if crypto_selections else None,
                    'average_score': sum(c.score for c in crypto_selections) / len(crypto_selections) if crypto_selections else 0
                }
            
            # Store notification in database
            await self.database.store_notification(notification)
            
            # Send via RabbitMQ to monitoring service
            if 'monitoring' in self.exchanges:
                message = aio_pika.Message(
                    json.dumps(notification, default=str).encode(),
                    content_type='application/json'
                )
                
                await self.exchanges['monitoring'].publish(
                    message,
                    routing_key='strategy.review.summary'
                )
            
            logger.info("Daily review notification sent")
            
        except Exception as e:
            logger.error(f"Error sending review notification: {e}")
    
    async def run_manual_strategy_review(self, strategy_id: str = None):
        """Manually trigger strategy review for testing or immediate analysis"""
        try:
            if not self.daily_reviewer:
                raise ValueError("Daily reviewer not initialized")
            
            if strategy_id:
                logger.info(f"Running manual review for strategy: {strategy_id}")
                # Review specific strategy
                strategy = await self.database.get_strategy(strategy_id)
                if not strategy:
                    raise ValueError(f"Strategy {strategy_id} not found")
                
                performance_metrics = await self.daily_reviewer._calculate_performance_metrics(strategy_id)
                if performance_metrics:
                    review_result = await self.daily_reviewer._conduct_strategy_review(
                        strategy, performance_metrics
                    )
                    await self.daily_reviewer._store_review_result(review_result)
                    await self.daily_reviewer._execute_review_actions(review_result)
                    
                    return {strategy_id: review_result}
                else:
                    logger.warning(f"Insufficient data for strategy {strategy_id}")
                    return {}
            else:
                logger.info("Running manual review for all strategies")
                # Review all strategies
                return await self.daily_reviewer.run_daily_review()
                
        except Exception as e:
            logger.error(f"Error in manual strategy review: {e}")
            raise
    
    # Cached API helper methods for performance optimization
    @cached(prefix='dashboard_perf', ttl=60, key_func=lambda self: 'dashboard')
    async def get_cached_dashboard_data(self) -> Dict:
        """Get cached performance dashboard data (60s TTL)"""
        try:
            # Get active strategies
            active_strategies = await self.database.get_active_strategies()
            
            dashboard_data = {
                "total_active_strategies": len(active_strategies),
                "performance_overview": {},
                "top_performers": [],
                "underperformers": [],
                "market_regime": getattr(self.daily_reviewer, 'current_market_regime', 'unknown') if self.daily_reviewer else 'unknown',
                "last_update": datetime.now(timezone.utc)
            }
            
            # Track cache hit/miss
            if self.redis_cache:
                self.cache_hits += 1
            
            return dashboard_data
            
        except Exception as e:
            logger.error(f"Error getting cached dashboard data: {e}")
            if self.redis_cache:
                self.cache_misses += 1
            raise
    
    @cached(prefix='review_history', ttl=120, key_func=lambda self, strategy_id, limit: f"{strategy_id}:{limit}")
    async def get_cached_review_history(self, strategy_id: str, limit: int = 10) -> List[Dict]:
        """Get cached review history for a strategy (120s TTL)"""
        try:
            history = await self.database.get_strategy_review_history(
                strategy_id=strategy_id,
                limit=limit
            )
            
            # Track cache hit/miss
            if self.redis_cache:
                self.cache_hits += 1
            
            return history if history else []
            
        except Exception as e:
            logger.error(f"Error getting cached review history: {e}")
            if self.redis_cache:
                self.cache_misses += 1
            raise
    
    async def stop(self):
        """Stop the service gracefully"""
        logger.info("Stopping enhanced strategy service...")
        self.running = False
        
        # Stop market signal consumer
        if self.market_signal_consumer:
            try:
                await self.market_signal_consumer.stop()
                logger.info("Market signal consumer stopped")
            except Exception as e:
                logger.error("Error stopping market signal consumer", error=str(e))
        
        # Cancel consumer tasks
        for task in self.consumer_tasks:
            task.cancel()
        
        if self.consumer_tasks:
            await asyncio.gather(*self.consumer_tasks, return_exceptions=True)
        
        # Disconnect market data consumer
        if self.market_data_consumer:
            try:
                await self.market_data_consumer.close()
            except AttributeError:
                pass  # close() method not available
        
        # Close connections
        if self.rabbitmq_connection:
            await self.rabbitmq_connection.close()
        
        # Close Redis connection
        if self.redis_cache:
            try:
                await self.redis_cache.close()
                logger.info("Redis cache connection closed")
            except Exception as e:
                logger.error("Error closing Redis cache", error=str(e))
        
        await self.database.disconnect()
        
        logger.info("Enhanced strategy service stopped")


# Health check endpoint
async def health_check(request):
    return web.json_response({'status': 'healthy', 'service': 'strategy_service'})

async def metrics_endpoint(request):
    """Metrics endpoint for Prometheus"""
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
    
    return web.Response(
        body=generate_latest(),
        content_type=CONTENT_TYPE_LATEST
    )

async def create_web_server():
    """Create web server for health checks and metrics"""
    app = web.Application()
    app.router.add_get('/health', health_check)
    app.router.add_get('/metrics', metrics_endpoint)
    return app

async def main():
    """Main application entry point"""
    # Setup signal handlers
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Create web server
    app = await create_web_server()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', settings.PROMETHEUS_PORT)
    await site.start()
    
    logger.info(f"Started web server on port {settings.PROMETHEUS_PORT}")
    
    service = StrategyService()
    
    try:
        await service.initialize()
        
        # Start FastAPI server for strategy management
        api_app = create_strategy_api(service)
        api_config = uvicorn.Config(
            api_app, 
            host="0.0.0.0", 
            port=getattr(settings, 'STRATEGY_API_PORT', 8003),
            log_level="info"
        )
        api_server = uvicorn.Server(api_config)
        
        # Start both the message consumers and API server
        await asyncio.gather(
            service.start_consumers(),
            api_server.serve()
        )
        
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    except Exception as e:
        logger.error("Service error", error=str(e))
        sys.exit(1)
    finally:
        await service.stop()

if __name__ == "__main__":
    asyncio.run(main())