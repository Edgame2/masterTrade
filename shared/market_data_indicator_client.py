"""
Market Data Indicator Client

Client library for strategy service to request and manage technical indicators
from the market data service efficiently.
"""

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Callable

import aio_pika
import aiohttp
import structlog

logger = structlog.get_logger()


class IndicatorRequestBuilder:
    """Builder class for creating indicator configurations"""
    
    def __init__(self, symbol: str, interval: str = "5m"):
        self.symbol = symbol
        self.interval = interval
        self.indicators = []
        self.strategy_id = None
    
    def set_strategy_id(self, strategy_id: str):
        """Set the strategy ID for this request"""
        self.strategy_id = strategy_id
        return self
    
    def add_sma(self, period: int, priority: int = 1) -> 'IndicatorRequestBuilder':
        """Add Simple Moving Average indicator"""
        config = {
            "id": f"sma_{period}_{self.symbol}_{uuid.uuid4().hex[:8]}",
            "indicator_type": "sma",
            "parameters": [{"name": "period", "value": period, "data_type": "int"}],
            "symbol": self.symbol,
            "interval": self.interval,
            "periods_required": period + 10,
            "output_fields": [f"sma_{period}"],
            "strategy_id": self.strategy_id or "default",
            "priority": priority
        }
        self.indicators.append(config)
        return self
    
    def add_ema(self, period: int, priority: int = 1) -> 'IndicatorRequestBuilder':
        """Add Exponential Moving Average indicator"""
        config = {
            "id": f"ema_{period}_{self.symbol}_{uuid.uuid4().hex[:8]}",
            "indicator_type": "ema",
            "parameters": [{"name": "period", "value": period, "data_type": "int"}],
            "symbol": self.symbol,
            "interval": self.interval,
            "periods_required": period + 10,
            "output_fields": [f"ema_{period}"],
            "strategy_id": self.strategy_id or "default",
            "priority": priority
        }
        self.indicators.append(config)
        return self
    
    def add_rsi(self, period: int = 14, priority: int = 1) -> 'IndicatorRequestBuilder':
        """Add RSI indicator"""
        config = {
            "id": f"rsi_{period}_{self.symbol}_{uuid.uuid4().hex[:8]}",
            "indicator_type": "rsi",
            "parameters": [{"name": "period", "value": period, "data_type": "int"}],
            "symbol": self.symbol,
            "interval": self.interval,
            "periods_required": period + 15,
            "output_fields": [f"rsi_{period}"],
            "strategy_id": self.strategy_id or "default",
            "priority": priority
        }
        self.indicators.append(config)
        return self
    
    def add_macd(self, fast_period: int = 12, slow_period: int = 26, 
                 signal_period: int = 9, priority: int = 1) -> 'IndicatorRequestBuilder':
        """Add MACD indicator"""
        config = {
            "id": f"macd_{fast_period}_{slow_period}_{signal_period}_{self.symbol}_{uuid.uuid4().hex[:8]}",
            "indicator_type": "macd",
            "parameters": [
                {"name": "fast_period", "value": fast_period, "data_type": "int"},
                {"name": "slow_period", "value": slow_period, "data_type": "int"},
                {"name": "signal_period", "value": signal_period, "data_type": "int"}
            ],
            "symbol": self.symbol,
            "interval": self.interval,
            "periods_required": slow_period + signal_period + 15,
            "output_fields": ["macd_line", "macd_signal", "macd_histogram"],
            "strategy_id": self.strategy_id or "default",
            "priority": priority
        }
        self.indicators.append(config)
        return self
    
    def add_bollinger_bands(self, period: int = 20, std_dev: float = 2.0, 
                           priority: int = 1) -> 'IndicatorRequestBuilder':
        """Add Bollinger Bands indicator"""
        config = {
            "id": f"bb_{period}_{std_dev}_{self.symbol}_{uuid.uuid4().hex[:8]}",
            "indicator_type": "bollinger_bands",
            "parameters": [
                {"name": "period", "value": period, "data_type": "int"},
                {"name": "std_dev", "value": std_dev, "data_type": "float"}
            ],
            "symbol": self.symbol,
            "interval": self.interval,
            "periods_required": period + 15,
            "output_fields": ["bb_upper", "bb_middle", "bb_lower"],
            "strategy_id": self.strategy_id or "default",
            "priority": priority
        }
        self.indicators.append(config)
        return self
    
    def build(self) -> List[Dict]:
        """Build the indicator configurations"""
        return self.indicators


class MarketDataIndicatorClient:
    """Client for requesting technical indicators from market data service"""
    
    def __init__(self, rabbitmq_url: str, api_base_url: str):
        self.rabbitmq_url = rabbitmq_url
        self.api_base_url = api_base_url.rstrip('/')
        
        # RabbitMQ components
        self.connection: Optional[aio_pika.Connection] = None
        self.channel: Optional[aio_pika.Channel] = None
        self.indicator_exchange: Optional[aio_pika.Exchange] = None
        self.results_queue: Optional[aio_pika.Queue] = None
        
        # HTTP session
        self.session: Optional[aiohttp.ClientSession] = None
        
        # Result handlers
        self.result_handlers: Dict[str, Callable] = {}
        self.pending_requests: Dict[str, asyncio.Event] = {}
        self.request_results: Dict[str, Any] = {}
        
    async def connect(self):
        """Initialize connections to RabbitMQ and HTTP"""
        try:
            # RabbitMQ connection
            self.connection = await aio_pika.connect_robust(self.rabbitmq_url)
            self.channel = await self.connection.channel()
            
            # Declare exchanges
            self.indicator_exchange = await self.channel.declare_exchange(
                'indicator_config',
                aio_pika.ExchangeType.TOPIC,
                durable=True
            )
            
            # Results exchange
            results_exchange = await self.channel.declare_exchange(
                'indicator_results',
                aio_pika.ExchangeType.TOPIC,
                durable=True
            )
            
            # Create unique queue for receiving results
            queue_name = f"strategy_indicators_{uuid.uuid4().hex[:8]}"
            self.results_queue = await self.channel.declare_queue(
                queue_name,
                auto_delete=True,
                arguments={"x-message-ttl": 300000}  # 5 minutes TTL
            )
            
            # Bind to receive all indicator results
            await self.results_queue.bind(results_exchange, routing_key="result.#")
            
            # Start consuming results
            await self.results_queue.consume(self._handle_indicator_result)
            
            # HTTP session
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30)
            )
            
            logger.info("Market data indicator client connected")
            
        except Exception as e:
            logger.error("Error connecting indicator client", error=str(e))
            raise
    
    async def disconnect(self):
        """Close all connections"""
        if self.session:
            await self.session.close()
        
        if self.connection:
            await self.connection.close()
        
        logger.info("Market data indicator client disconnected")
    
    async def _handle_indicator_result(self, message: aio_pika.IncomingMessage):
        """Handle incoming indicator results"""
        async with message.process():
            try:
                result = json.loads(message.body.decode())
                config_id = result.get('configuration_id')
                
                # Store result
                if config_id:
                    self.request_results[config_id] = result
                
                # Notify waiting requests
                if config_id in self.pending_requests:
                    self.pending_requests[config_id].set()
                
                # Call registered handlers
                if config_id in self.result_handlers:
                    try:
                        await self.result_handlers[config_id](result)
                    except Exception as e:
                        logger.error("Error in result handler", config_id=config_id, error=str(e))
                
                logger.debug("Processed indicator result", config_id=config_id)
                
            except Exception as e:
                logger.error("Error handling indicator result", error=str(e))
    
    async def request_indicator(self, config: Dict, wait_for_result: bool = True, 
                              timeout: float = 30.0) -> Optional[Dict]:
        """Request a single indicator calculation"""
        try:
            config_id = config['id']
            
            # Setup waiting mechanism if needed
            if wait_for_result:
                self.pending_requests[config_id] = asyncio.Event()
            
            # Send configuration request
            request_data = {
                'configuration': config,
                'calculate_immediately': True,
                'reply_to': self.results_queue.name if self.results_queue else None
            }
            
            message = aio_pika.Message(
                json.dumps(request_data, default=str).encode(),
                content_type='application/json',
                correlation_id=config_id
            )
            
            await self.indicator_exchange.publish(
                message,
                routing_key='config.request.add'
            )
            
            # Wait for result if requested
            if wait_for_result:
                try:
                    await asyncio.wait_for(
                        self.pending_requests[config_id].wait(),
                        timeout=timeout
                    )
                    result = self.request_results.get(config_id)
                    
                    # Cleanup
                    self.pending_requests.pop(config_id, None)
                    self.request_results.pop(config_id, None)
                    
                    return result
                    
                except asyncio.TimeoutError:
                    logger.warning("Indicator request timeout", config_id=config_id)
                    self.pending_requests.pop(config_id, None)
                    return None
            
            return {'status': 'requested', 'config_id': config_id}
            
        except Exception as e:
            logger.error("Error requesting indicator", error=str(e))
            raise
    
    async def request_bulk_indicators(self, strategy_id: str, 
                                    indicators: List[Dict],
                                    wait_for_results: bool = True,
                                    timeout: float = 60.0) -> List[Dict]:
        """Request multiple indicators efficiently"""
        try:
            # Create bulk request
            bulk_request = {
                'strategy_id': strategy_id,
                'requests': [{
                    'strategy_id': strategy_id,
                    'indicators': indicators,
                    'symbols': list(set(ind['symbol'] for ind in indicators)),
                    'intervals': list(set(ind['interval'] for ind in indicators))
                }],
                'parallel_execution': True,
                'batch_size': 20
            }
            
            request_data = {
                'request': bulk_request,
                'reply_to': self.results_queue.name if self.results_queue else None
            }
            
            # Setup waiting for all results
            config_ids = [ind['id'] for ind in indicators]
            if wait_for_results:
                for config_id in config_ids:
                    self.pending_requests[config_id] = asyncio.Event()
            
            # Send bulk request
            message = aio_pika.Message(
                json.dumps(request_data, default=str).encode(),
                content_type='application/json'
            )
            
            await self.indicator_exchange.publish(
                message,
                routing_key='config.request.bulk'
            )
            
            # Wait for all results
            if wait_for_results:
                try:
                    # Wait for all results
                    await asyncio.wait_for(
                        asyncio.gather(*[
                            self.pending_requests[cid].wait() 
                            for cid in config_ids
                        ]),
                        timeout=timeout
                    )
                    
                    # Collect results
                    results = []
                    for config_id in config_ids:
                        result = self.request_results.get(config_id)
                        if result:
                            results.append(result)
                    
                    # Cleanup
                    for config_id in config_ids:
                        self.pending_requests.pop(config_id, None)
                        self.request_results.pop(config_id, None)
                    
                    return results
                    
                except asyncio.TimeoutError:
                    logger.warning("Bulk indicator request timeout", strategy_id=strategy_id)
                    return []
            
            return [{'status': 'requested', 'strategy_id': strategy_id}]
            
        except Exception as e:
            logger.error("Error requesting bulk indicators", error=str(e))
            raise
    
    async def get_cached_indicators_rest(self, symbol: str, interval: str = "5m", 
                                       indicator_types: List[str] = None) -> Dict:
        """Get cached indicators via REST API"""
        try:
            params = {
                'interval': interval
            }
            
            if indicator_types:
                params['indicator_types'] = ','.join(indicator_types)
            
            url = f"{self.api_base_url}/api/indicators/cached/{symbol}"
            
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.error("REST API error", status=response.status)
                    return {}
                    
        except Exception as e:
            logger.error("Error getting cached indicators via REST", error=str(e))
            return {}
    
    async def calculate_indicator_rest(self, config: Dict) -> Dict:
        """Calculate indicator via REST API (synchronous)"""
        try:
            url = f"{self.api_base_url}/api/indicators/calculate"
            
            async with self.session.post(url, json=config) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error_text = await response.text()
                    logger.error("REST calculation error", 
                               status=response.status, error=error_text)
                    return {}
                    
        except Exception as e:
            logger.error("Error calculating indicator via REST", error=str(e))
            return {}
    
    def register_result_handler(self, config_id: str, handler: Callable):
        """Register a handler for indicator results"""
        self.result_handlers[config_id] = handler
    
    def unregister_result_handler(self, config_id: str):
        """Unregister result handler"""
        self.result_handlers.pop(config_id, None)


# Convenience functions
def create_indicator_builder(symbol: str, interval: str = "5m") -> IndicatorRequestBuilder:
    """Create a new indicator request builder"""
    return IndicatorRequestBuilder(symbol, interval)

def create_standard_indicators(symbol: str, interval: str = "5m", 
                             strategy_id: str = "default") -> List[Dict]:
    """Create a standard set of indicators for a symbol"""
    builder = (IndicatorRequestBuilder(symbol, interval)
              .set_strategy_id(strategy_id)
              .add_sma(20)
              .add_sma(50)
              .add_ema(12)
              .add_ema(26)
              .add_rsi(14)
              .add_macd()
              .add_bollinger_bands())
    
    return builder.build()

def create_momentum_indicators(symbol: str, interval: str = "5m", 
                             strategy_id: str = "momentum") -> List[Dict]:
    """Create momentum-focused indicators"""
    builder = (IndicatorRequestBuilder(symbol, interval)
              .set_strategy_id(strategy_id)
              .add_rsi(14)
              .add_rsi(21)
              .add_macd()
              .add_ema(9)
              .add_ema(21))
    
    return builder.build()

def create_trend_indicators(symbol: str, interval: str = "5m", 
                          strategy_id: str = "trend") -> List[Dict]:
    """Create trend-focused indicators"""
    builder = (IndicatorRequestBuilder(symbol, interval)
              .set_strategy_id(strategy_id)
              .add_sma(20)
              .add_sma(50)
              .add_sma(200)
              .add_ema(20)
              .add_ema(50)
              .add_bollinger_bands())
    
    return builder.build()