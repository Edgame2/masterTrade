"""
Order Executor Service - Enhanced with Market Data Integration

This service processes trading signals and executes orders on the exchange,
managing order lifecycle and tracking execution status. Now enhanced with
comprehensive market data access for better execution decisions.
"""

import asyncio
import json
import logging
import signal
import sys
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

import aio_pika
import ccxt.async_support as ccxt
import structlog
from aiohttp import web
from prometheus_client import Counter, Gauge, Histogram, start_http_server

from config import settings
from database import Database
from models import Order, Signal, Trade, OrderRequest
from exchange_manager import ExchangeManager
from strategy_environment_manager import EnvironmentConfigManager
from order_manager import OrderManager
from shared.enhanced_market_data_consumer import (
    EnhancedMarketDataConsumer,
    MarketDataMessage,
)
from shared.price_prediction_client import PricePredictionClient

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
signals_received = Counter('signals_received_total', 'Total trading signals received', ['signal_type'])
orders_created = Counter('orders_created_total', 'Total orders created', ['symbol', 'side', 'type'])
orders_filled = Counter('orders_filled_total', 'Total orders filled', ['symbol', 'side'])
orders_failed = Counter('orders_failed_total', 'Total orders failed', ['symbol', 'reason'])
order_execution_time = Histogram('order_execution_seconds', 'Time to execute orders')
active_orders = Gauge('active_orders_total', 'Number of active orders')
exchange_errors = Counter('exchange_errors_total', 'Total exchange API errors', ['error_type'])


class OrderExecutorService:
    """Enhanced order execution service with market data integration"""
    
    def __init__(self):
        self.database = Database()
        self.rabbitmq_connection: Optional[aio_pika.Connection] = None
        self.rabbitmq_channel: Optional[aio_pika.Channel] = None
        self.exchanges: Dict[str, aio_pika.Exchange] = {}
        self.exchange_manager = ExchangeManager()
        self.env_config_manager = EnvironmentConfigManager(self.database)
        self.order_manager = OrderManager()
        
        # Enhanced market data consumer
        self.market_data_consumer: Optional[EnhancedMarketDataConsumer] = None
        self.price_prediction_client = PricePredictionClient(
            base_url=settings.STRATEGY_SERVICE_URL,
            service_name=settings.SERVICE_NAME,
            cache_ttl_seconds=180
        )
        
        # Market data cache for execution decisions
        self.current_prices: Dict[str, Dict] = {}
        self.sentiment_data: Dict[str, Dict] = {}
        self.correlation_data: Dict = {}
        self.stock_indices: Dict[str, Dict] = {}
        
        self.running = False
        self.consumer_tasks: List[asyncio.Task] = []
        
    async def initialize(self):
        """Initialize all connections and services"""
        try:
            # Initialize database
            await self.database.connect()
            
            # Initialize exchange manager
            await self.exchange_manager.initialize()
            
            # Initialize RabbitMQ
            await self._init_rabbitmq()
            
            # Initialize enhanced market data consumer
            await self._init_market_data_consumer()
            
            # Warm up price prediction client
            await self.price_prediction_client.initialize()

            # Initialize order manager
            await self.order_manager.initialize(self.database, self.exchange_manager)
            
            logger.info("Enhanced order executor service initialized successfully")
            
        except Exception as e:
            logger.error("Failed to initialize service", error=str(e))
            raise
    

    
    async def _init_rabbitmq(self):
        """Initialize RabbitMQ connection and exchanges"""
        try:
            self.rabbitmq_connection = await aio_pika.connect_robust(
                settings.RABBITMQ_URL,
                heartbeat=600,
                blocked_connection_timeout=300,
            )
            self.rabbitmq_channel = await self.rabbitmq_connection.channel()
            await self.rabbitmq_channel.set_qos(prefetch_count=10)
            
            # Declare exchanges
            self.exchanges['trading'] = await self.rabbitmq_channel.declare_exchange(
                'mastertrade.trading', aio_pika.ExchangeType.TOPIC, durable=True
            )
            
            self.exchanges['orders'] = await self.rabbitmq_channel.declare_exchange(
                'mastertrade.orders', aio_pika.ExchangeType.TOPIC, durable=True
            )
            
            self.exchanges['risk'] = await self.rabbitmq_channel.declare_exchange(
                'mastertrade.risk', aio_pika.ExchangeType.TOPIC, durable=True
            )
            
            logger.info("RabbitMQ initialized successfully")
            
        except Exception as e:
            logger.error("Failed to initialize RabbitMQ", error=str(e))
            raise
    
    async def _init_market_data_consumer(self):
        """Initialize enhanced market data consumer"""
        try:
            self.market_data_consumer = EnhancedMarketDataConsumer(
                rabbitmq_url=settings.RABBITMQ_URL,
                api_base_url="http://localhost:8005",  # Market data service API
                service_name="order_executor"
            )
            
            await self.market_data_consumer.initialize()
            
            # Register handlers for market data
            self.market_data_consumer.add_message_handler("ticker_updates", self._handle_price_update)
            self.market_data_consumer.add_message_handler("sentiment_updates", self._handle_sentiment_update)
            self.market_data_consumer.add_message_handler("correlation_updates", self._handle_correlation_update)
            self.market_data_consumer.add_message_handler("stock_index_updates", self._handle_stock_index_update)
            self.market_data_consumer.add_message_handler("market_data", self._handle_market_data_update)
            
            logger.info("Enhanced market data consumer initialized for order executor")
            
        except Exception as e:
            logger.error("Failed to initialize market data consumer", error=str(e))
            raise
    
    async def _handle_price_update(self, message: MarketDataMessage):
        """Handle real-time price updates for execution decisions"""
        try:
            data = message.data
            symbol = data.get('symbol')
            if symbol:
                self.current_prices[symbol] = {
                    'price': data.get('price'),
                    'volume': data.get('volume'),
                    'price_change': data.get('price_change'),
                    'price_change_percent': data.get('price_change_percent'),
                    'timestamp': message.timestamp
                }
                logger.debug(f"Updated price data for {symbol}: {data.get('price')}")
                
        except Exception as e:
            logger.error("Error handling price update", error=str(e))
    
    async def _handle_sentiment_update(self, message: MarketDataMessage):
        """Handle sentiment data for execution timing"""
        try:
            data = message.data
            
            # Store global sentiment data
            if 'global_crypto_sentiment' in data:
                self.sentiment_data['global_crypto'] = data['global_crypto_sentiment']
            
            if 'global_market_sentiment' in data:
                self.sentiment_data['global_market'] = data['global_market_sentiment']
            
            # Store per-symbol sentiment if available
            for key, value in data.items():
                if key.endswith('_sentiment') and key not in ['global_crypto_sentiment', 'global_market_sentiment']:
                    symbol = key.replace('_sentiment', '').upper()
                    self.sentiment_data[symbol] = value
            
            logger.debug("Updated sentiment data for execution context")
            
        except Exception as e:
            logger.error("Error handling sentiment update", error=str(e))
    
    async def _handle_correlation_update(self, message: MarketDataMessage):
        """Handle market correlation data"""
        try:
            self.correlation_data = message.data
            logger.debug("Updated correlation data for market context")
            
        except Exception as e:
            logger.error("Error handling correlation update", error=str(e))
    
    async def _handle_stock_index_update(self, message: MarketDataMessage):
        """Handle stock index updates for market context"""
        try:
            data = message.data
            for index_name, index_data in data.items():
                self.stock_indices[index_name] = index_data
            
            logger.debug("Updated stock index data for market context")
            
        except Exception as e:
            logger.error("Error handling stock index update", error=str(e))
    
    async def _handle_market_data_update(self, message: MarketDataMessage):
        """Handle general market data updates"""
        try:
            data = message.data
            symbol = data.get('symbol')
            
            if symbol and symbol not in self.current_prices:
                # Initialize price data if we don't have it yet
                self.current_prices[symbol] = {
                    'price': data.get('close_price'),
                    'volume': data.get('volume'),
                    'high_price': data.get('high_price'),
                    'low_price': data.get('low_price'),
                    'timestamp': message.timestamp
                }
                
        except Exception as e:
            logger.error("Error handling market data update", error=str(e))
    
    async def start_consumers(self):
        """Start consuming trading signals and market data"""
        try:
            self.running = True
            
            # Create and bind queues
            signal_queue = await self.rabbitmq_channel.declare_queue(
                'order_executor_signals',
                durable=True
            )
            
            # Bind to all signal types
            await signal_queue.bind(self.exchanges['trading'], routing_key='signal.buy')
            await signal_queue.bind(self.exchanges['trading'], routing_key='signal.sell')
            
            # Risk approval queue
            risk_queue = await self.rabbitmq_channel.declare_queue(
                'order_executor_risk_approved',
                durable=True
            )
            await risk_queue.bind(self.exchanges['risk'], routing_key='risk.approved')
            
            # Start consumers
            await signal_queue.consume(self._process_signal, no_ack=False)
            await risk_queue.consume(self._process_risk_approval, no_ack=False)
            
            # Start market data consumer for real-time data
            if self.market_data_consumer:
                market_data_task = asyncio.create_task(
                    self.market_data_consumer.start_consuming_specific_data_types([
                        "ticker", "sentiment", "correlation", "stock_index", "market_data"
                    ])
                )
                self.consumer_tasks.append(market_data_task)
            
            # Start order monitoring task
            monitor_task = asyncio.create_task(self._monitor_orders())
            self.consumer_tasks.append(monitor_task)
            
            logger.info("Started consuming trading signals, risk approvals, and market data")
            
            # Keep running
            while self.running:
                await asyncio.sleep(1)
                
        except Exception as e:
            logger.error("Error in message consumers", error=str(e))
            raise
    
    async def _process_signal(self, message: aio_pika.IncomingMessage):
        """Process incoming trading signal"""
        async with message.process():
            try:
                data = json.loads(message.body.decode())
                signal = Signal(**data)
                
                signals_received.labels(signal_type=signal.signal_type).inc()
                
                # Check if trading is enabled
                if not await self.database.is_trading_enabled():
                    logger.info("Trading disabled, ignoring signal", 
                               signal_type=signal.signal_type,
                               symbol=signal.symbol)
                    return
                
                # Create order request from signal
                order_request = await self._signal_to_order_request(signal)
                
                if order_request:
                    # Send to risk manager for approval
                    await self._send_for_risk_check(order_request)
                
            except Exception as e:
                logger.error("Error processing signal", error=str(e))
    
    async def _signal_to_order_request(self, signal: Signal) -> Optional[OrderRequest]:
        """Enhanced signal to order request conversion with market data integration"""
        try:
            # Get current market price - prefer cached data, fallback to exchange
            current_price = None
            
            # Try to get price from our cached market data first
            if signal.symbol in self.current_prices:
                cached_price_data = self.current_prices[signal.symbol]
                current_price = cached_price_data.get('price')
                logger.debug(f"Using cached price for {signal.symbol}: {current_price}")
            
            # Fallback to exchange API if cached data not available
            if not current_price:
                # Get environment configuration for this strategy
                env_config = await self.env_config_manager.get_strategy_environment_config(signal.strategy_id)
                environment = env_config.get("environment", "testnet") if env_config else "testnet"
                
                # Get exchange for the specific environment
                exchange = self.exchange_manager.get_exchange(environment)
                if exchange:
                    ticker = await exchange.fetch_ticker(signal.symbol)
                    current_price = ticker['last']
                    logger.debug(f"Fetched price from {environment} exchange for {signal.symbol}: {current_price}")
                else:
                    logger.error(f"No exchange available for environment: {environment}")
                    return None
            
            # Fetch forward-looking price prediction for additional context
            price_prediction = await self.price_prediction_client.get_prediction(signal.symbol)

            # Calculate position size based on strategy config
            position_size = await self.database.get_position_size_for_strategy(
                signal.strategy_id, signal.symbol
            )
            
            if not position_size or position_size <= 0:
                logger.warning("Invalid position size", 
                             strategy_id=signal.strategy_id,
                             symbol=signal.symbol)
                return None
            
            # Enhanced position sizing based on market conditions
            position_size = await self._adjust_position_size_for_market_conditions(
                signal, position_size, current_price
            )
            
            # Determine order type based on market conditions
            order_type = await self._determine_optimal_order_type(
                signal,
                current_price,
                price_prediction,
            )
            
            # Create enhanced order request with market context
            metadata = signal.metadata or {}
            metadata.update({
                'market_context': {
                    'sentiment': self.sentiment_data.get(signal.symbol, {}),
                    'global_crypto_sentiment': self.sentiment_data.get('global_crypto', {}),
                    'global_market_sentiment': self.sentiment_data.get('global_market', {}),
                    'correlation_data': self.correlation_data,
                    'stock_indices': self.stock_indices,
                    'current_price_data': self.current_prices.get(signal.symbol, {})
                },
                'price_prediction': price_prediction or {}
            })

            if price_prediction:
                predicted_change = float(price_prediction.get('predicted_change_pct', 0.0))
                predicted_direction = 'BUY' if predicted_change >= 0 else 'SELL'
                metadata['market_context']['prediction_alignment'] = {
                    'predicted_direction': predicted_direction,
                    'aligned': predicted_direction == signal.signal_type.upper(),
                    'predicted_change_pct': predicted_change
                }
            
            # Get environment configuration for this strategy
            env_config = await self.env_config_manager.get_strategy_environment_config(signal.strategy_id)
            environment = env_config.get("environment", "testnet") if env_config else "testnet"
            
            order_request = OrderRequest(
                client_order_id=str(uuid.uuid4()),
                strategy_id=signal.strategy_id,
                symbol=signal.symbol,
                side=signal.signal_type.upper(),  # BUY or SELL
                order_type=order_type,
                quantity=position_size,
                price=current_price,
                signal_id=getattr(signal, 'id', None),
                environment=environment,
                metadata=metadata
            )
            
            return order_request
            
        except Exception as e:
            logger.error("Error creating order request from signal", error=str(e))
            return None
    
    async def _adjust_position_size_for_market_conditions(self, signal: Signal, 
                                                        base_size: float, 
                                                        current_price: float) -> float:
        """Adjust position size based on market conditions"""
        try:
            adjusted_size = base_size
            
            # Adjust based on sentiment
            symbol_sentiment = self.sentiment_data.get(signal.symbol, {})
            if symbol_sentiment:
                sentiment_score = symbol_sentiment.get('score', 0)
                
                # Reduce size if sentiment conflicts with signal direction
                if signal.signal_type.upper() == 'BUY' and sentiment_score < -0.3:
                    adjusted_size *= 0.7  # Reduce by 30%
                    logger.info(f"Reduced position size due to negative sentiment for {signal.symbol}")
                elif signal.signal_type.upper() == 'SELL' and sentiment_score > 0.3:
                    adjusted_size *= 0.7  # Reduce by 30%
                    logger.info(f"Reduced position size due to positive sentiment for {signal.symbol}")
            
            # Adjust based on volatility from price data
            if signal.symbol in self.current_prices:
                price_data = self.current_prices[signal.symbol]
                price_change_percent = abs(price_data.get('price_change_percent', 0))
                
                # Reduce size for high volatility
                if price_change_percent > 5:  # More than 5% change
                    volatility_factor = max(0.5, 1 - (price_change_percent - 5) / 20)
                    adjusted_size *= volatility_factor
                    logger.info(f"Adjusted position size for volatility on {signal.symbol}: {volatility_factor}")
            
            # Adjust based on global market conditions
            global_sentiment = self.sentiment_data.get('global_market', {})
            if global_sentiment and global_sentiment.get('score', 0) < -0.5:
                adjusted_size *= 0.8  # Reduce by 20% in very negative market conditions
                logger.info(f"Reduced position size due to negative global sentiment")
            
            # Ensure minimum position size
            adjusted_size = max(adjusted_size, base_size * 0.1)  # Never less than 10% of base
            
            return adjusted_size
            
        except Exception as e:
            logger.error("Error adjusting position size", error=str(e))
            return base_size
    
    async def _determine_optimal_order_type(
        self,
        signal: Signal,
        current_price: float,
        price_prediction: Optional[Dict],
    ) -> str:
        """Determine optimal order type based on market conditions"""
        try:
            # Default to market orders
            order_type = 'MARKET'
            
            # Check volatility and volume to decide order type
            if signal.symbol in self.current_prices:
                price_data = self.current_prices[signal.symbol]
                price_change_percent = abs(price_data.get('price_change_percent', 0))
                volume = price_data.get('volume', 0)
                
                # Use limit orders for high volatility or low volume
                if price_change_percent > 3 or volume < 1000:
                    order_type = 'LIMIT'
                    logger.debug(f"Using LIMIT order for {signal.symbol} due to market conditions")

            # Adjust order type based on forward-looking prediction divergence
            if price_prediction:
                predicted_change = float(price_prediction.get('predicted_change_pct', 0.0))
                signal_side = signal.signal_type.upper()
                if signal_side == 'BUY' and predicted_change < -0.5:
                    order_type = 'LIMIT'
                elif signal_side == 'SELL' and predicted_change > 0.5:
                    order_type = 'LIMIT'
                if order_type == 'LIMIT':
                    logger.debug(
                        "Prediction suggests moderating order execution",
                        symbol=signal.symbol,
                        signal_side=signal_side,
                        predicted_change=predicted_change,
                    )
            
            return order_type
            
        except Exception as e:
            logger.error("Error determining order type", error=str(e))
            return 'MARKET'
    
    async def _send_for_risk_check(self, order_request: OrderRequest):
        """Send order request to risk manager for approval"""
        try:
            message = aio_pika.Message(
                json.dumps(order_request.model_dump(), default=str).encode(),
                content_type='application/json',
                timestamp=datetime.now(timezone.utc)
            )
            
            await self.exchanges['risk'].publish(
                message, 
                routing_key='risk.check'
            )
            
            logger.info("Sent order for risk check", 
                       order_id=order_request.client_order_id,
                       symbol=order_request.symbol,
                       side=order_request.side)
            
        except Exception as e:
            logger.error("Error sending for risk check", error=str(e))
    
    async def _process_risk_approval(self, message: aio_pika.IncomingMessage):
        """Process risk-approved order requests"""
        async with message.process():
            try:
                data = json.loads(message.body.decode())
                order_request = OrderRequest(**data)
                
                # Execute the order
                await self._execute_order(order_request)
                
            except Exception as e:
                logger.error("Error processing risk approval", error=str(e))
    
    @order_execution_time.time()
    async def _execute_order(self, order_request: OrderRequest):
        """Execute an order on the exchange"""
        try:
            # Create order in database first
            order = await self.database.create_order(order_request)
            
            if not order:
                logger.error("Failed to create order in database")
                return

            await self.order_manager.track(order)
            
            # Execute on exchange
            exchange_order = await self._place_exchange_order(order)
            
            if exchange_order:
                # Update order with exchange details
                await self.database.update_order_exchange_info(
                    order.id, 
                    exchange_order['id']
                )
                
                orders_created.labels(
                    symbol=order.symbol,
                    side=order.side,
                    type=order.order_type
                ).inc()
                
                # Publish order update
                await self._publish_order_update(order, 'CREATED')
                
                logger.info("Order executed successfully",
                           order_id=order.id,
                           exchange_order_id=exchange_order['id'],
                           symbol=order.symbol,
                           side=order.side,
                           quantity=order.quantity)
            else:
                # Mark order as failed
                await self.database.update_order_status(order.id, 'REJECTED')
                await self.order_manager.discard(order.id)
                orders_failed.labels(symbol=order.symbol, reason='exchange_error').inc()
                
        except Exception as e:
            logger.error("Error executing order", error=str(e))
            if 'order' in locals():
                await self.database.update_order_status(order.id, 'REJECTED')
                await self.order_manager.discard(order.id)
                orders_failed.labels(symbol=order.symbol, reason='execution_error').inc()
    
    async def _place_exchange_order(self, order: Order) -> Optional[Dict]:
        """Place order on exchange using environment-specific connection"""
        try:
            # Use the exchange manager to create the order with environment-specific exchange
            result = await self.exchange_manager.create_order(
                order.symbol,
                order.order_type.lower(),
                order.side.lower(), 
                order.quantity,
                order.price,
                environment=order.environment
            )
            
            return result
            
        except ccxt.NetworkError as e:
            logger.error("Network error placing order", error=str(e))
            exchange_errors.labels(error_type='network').inc()
            return None
        except ccxt.ExchangeError as e:
            logger.error("Exchange error placing order", error=str(e))
            exchange_errors.labels(error_type='exchange').inc()
            return None
        except Exception as e:
            logger.error("Unexpected error placing order", error=str(e))
            exchange_errors.labels(error_type='unexpected').inc()
            return None
    
    async def _monitor_orders(self):
        """Monitor active orders and update their status"""
        while self.running:
            try:
                # Get active orders from database
                active_orders_list = await self.database.get_active_orders()
                active_orders.set(len(active_orders_list))
                await self.order_manager.update_from_snapshot(active_orders_list)
                
                for order in active_orders_list:
                    try:
                        # Fetch order status from exchange
                        exchange_order = await self.exchange_manager.fetch_order(
                            order.exchange_order_id, order.symbol
                        )
                        
                        # Update order status if changed
                        status = exchange_order.get('status', '').lower()
                        if status and status != order.status.lower():
                            await self.database.update_order_from_exchange(
                                order.id, exchange_order
                            )
                            
                            # Handle filled orders
                            if status == 'closed':
                                await self._handle_filled_order(order, exchange_order)
                                await self.order_manager.discard(order.id)
                            elif status in {'canceled', 'cancelled', 'rejected'}:
                                await self.order_manager.discard(order.id)
                            
                            # Publish update
                            await self._publish_order_update(order, status.upper())
                    
                    except Exception as e:
                        logger.error("Error monitoring order", 
                                   order_id=order.id, 
                                   error=str(e))
                
                # Sleep before next check
                await asyncio.sleep(settings.ORDER_MONITOR_INTERVAL)
                
            except Exception as e:
                logger.error("Error in order monitoring", error=str(e))
                await asyncio.sleep(10)  # Wait longer on error
    
    async def _handle_filled_order(self, order: Order, exchange_order: Dict):
        """Handle a filled order"""
        try:
            # Create trade records
            if 'trades' in exchange_order and exchange_order['trades']:
                for trade_data in exchange_order['trades']:
                    trade = Trade(
                        order_id=order.id,
                        exchange_trade_id=trade_data['id'],
                        symbol=order.symbol,
                        side=order.side,
                        quantity=float(trade_data['amount']),
                        price=float(trade_data['price']),
                        commission=float(trade_data.get('fee', {}).get('cost', 0)),
                        commission_asset=trade_data.get('fee', {}).get('currency'),
                        is_maker=trade_data.get('takerOrMaker') == 'maker',
                        trade_time=datetime.fromtimestamp(
                            trade_data['timestamp'] / 1000, 
                            tz=timezone.utc
                        )
                    )
                    await self.database.insert_trade(trade)
            
            # Update portfolio
            await self.database.update_portfolio_from_trade(order, exchange_order)
            
            orders_filled.labels(symbol=order.symbol, side=order.side).inc()
            
            logger.info("Order filled successfully",
                       order_id=order.id,
                       symbol=order.symbol,
                       filled_quantity=exchange_order.get('filled', 0),
                       avg_price=exchange_order.get('average'))
            
        except Exception as e:
            logger.error("Error handling filled order", error=str(e))
    
    async def _publish_order_update(self, order: Order, status: str):
        """Publish order update to message queue"""
        try:
            update_data = {
                'order_id': str(order.id),
                'symbol': order.symbol,
                'side': order.side,
                'status': status,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
            
            message = aio_pika.Message(
                json.dumps(update_data).encode(),
                content_type='application/json'
            )
            
            await self.exchanges['orders'].publish(
                message, 
                routing_key=f'order.update.{status.lower()}'
            )
            
        except Exception as e:
            logger.error("Error publishing order update", error=str(e))
    
    async def stop(self):
        """Stop the service gracefully"""
        logger.info("Stopping enhanced order executor service...")
        self.running = False
        
        # Cancel consumer tasks
        for task in self.consumer_tasks:
            task.cancel()
        
        if self.consumer_tasks:
            await asyncio.gather(*self.consumer_tasks, return_exceptions=True)
        
        # Disconnect market data consumer
        if self.market_data_consumer:
            await self.market_data_consumer.disconnect()
        
        await self.price_prediction_client.close()

        # Close connections
        if self.exchange_manager:
            await self.exchange_manager.close()
        
        if self.rabbitmq_connection:
            await self.rabbitmq_connection.close()
        
        await self.database.disconnect()
        
        logger.info("Enhanced order executor service stopped")


# Health check endpoint
async def health_check(request):
    return web.json_response({'status': 'healthy', 'service': 'order_executor'})

async def metrics_endpoint(request):
    """Metrics endpoint for Prometheus"""
    from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
    
    return web.Response(
        body=generate_latest(),
        headers={'Content-Type': CONTENT_TYPE_LATEST}
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
    
    service = OrderExecutorService()
    
    try:
        await service.initialize()
        await service.start_consumers()
        
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    except Exception as e:
        logger.error("Service error", error=str(e))
        sys.exit(1)
    finally:
        await service.stop()

if __name__ == "__main__":
    asyncio.run(main())