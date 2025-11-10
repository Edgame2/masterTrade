"""
Dynamic Strategy Data Manager - Bidirectional communication between Strategy and Market Data services

This module enables dynamic data requests from strategy service to market data service,
allowing AI/ML strategies to request custom indicators, alternative data, and specialized
market analysis in real-time.
"""

import asyncio
import json
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, asdict
from enum import Enum
import structlog

import aio_pika
import aiohttp

logger = structlog.get_logger()

class DataRequestType(Enum):
    TECHNICAL_INDICATORS = "technical_indicators"
    VOLUME_PROFILE = "volume_profile"  
    ORDER_FLOW = "order_flow"
    LIQUIDITY_ZONES = "liquidity_zones"
    SENTIMENT_DATA = "sentiment_data"
    CORRELATION_MATRIX = "correlation_matrix"
    MACRO_INDICATORS = "macro_indicators"
    ALTERNATIVE_DATA = "alternative_data"
    CUSTOM_COMPOSITE = "custom_composite"

class DataPriority(Enum):
    LOW = "low"
    NORMAL = "normal" 
    HIGH = "high"
    CRITICAL = "critical"

@dataclass
class StrategyDataRequest:
    request_id: str
    strategy_id: str
    strategy_name: str
    request_type: DataRequestType
    symbols: List[str]
    timeframes: List[str]
    parameters: Dict[str, Any]
    priority: DataPriority
    callback_endpoint: Optional[str]
    expires_at: datetime
    created_at: datetime = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc)

@dataclass 
class DataResponse:
    request_id: str
    strategy_id: str
    data_type: str
    symbol: str
    timeframe: str
    data: Dict[str, Any]
    timestamp: datetime
    quality_score: float = 1.0
    latency_ms: int = 0

class StrategyDataManager:
    """
    Manages dynamic data requests between Strategy Service and Market Data Service
    
    Features:
    - Real-time indicator requests based on strategy needs
    - Custom composite indicator generation
    - Alternative data integration (sentiment, news, social media)
    - Cross-asset correlation analysis
    - Volume profile and order flow analysis
    - Dynamic symbol and timeframe management
    """
    
    def __init__(self, rabbitmq_url: str, market_data_api_url: str):
        self.rabbitmq_url = rabbitmq_url
        self.market_data_api_url = market_data_api_url.rstrip('/')
        
        # Connection management
        self.rabbitmq_connection: Optional[aio_pika.Connection] = None
        self.rabbitmq_channel: Optional[aio_pika.Channel] = None
        self.http_session: Optional[aiohttp.ClientSession] = None
        
        # Request tracking
        self.active_requests: Dict[str, StrategyDataRequest] = {}
        self.request_callbacks: Dict[str, Callable] = {}
        self.strategy_subscriptions: Dict[str, List[str]] = {}  # strategy_id -> request_ids
        
        # Performance tracking
        self.request_metrics: Dict[str, Dict] = {}
        
    async def initialize(self):
        """Initialize connections and message handlers"""
        try:
            # Initialize RabbitMQ
            await self._init_rabbitmq()
            
            # Initialize HTTP session
            self.http_session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30)
            )
            
            # Start background tasks
            asyncio.create_task(self._request_cleanup_task())
            asyncio.create_task(self._performance_monitoring_task())
            
            logger.info("Strategy Data Manager initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize Strategy Data Manager: {e}")
            raise
    
    async def _init_rabbitmq(self):
        """Initialize RabbitMQ connection for bidirectional communication"""
        self.rabbitmq_connection = await aio_pika.connect_robust(
            self.rabbitmq_url,
            heartbeat=600,
            blocked_connection_timeout=300,
        )
        self.rabbitmq_channel = await self.rabbitmq_connection.channel()
        await self.rabbitmq_channel.set_qos(prefetch_count=100)
        
        # Declare exchanges for strategy-market data communication
        self.strategy_exchange = await self.rabbitmq_channel.declare_exchange(
            'mastertrade.strategy.requests', aio_pika.ExchangeType.TOPIC, durable=True
        )
        
        self.market_data_exchange = await self.rabbitmq_channel.declare_exchange(
            'mastertrade.market.responses', aio_pika.ExchangeType.TOPIC, durable=True
        )
        
        # Create response queue for this service
        self.response_queue = await self.rabbitmq_channel.declare_queue(
            f'strategy_data_responses_{uuid.uuid4().hex[:8]}',
            durable=False,
            auto_delete=True
        )
        
        # Bind to response routing keys
        await self.response_queue.bind(
            self.market_data_exchange,
            routing_key='market.response.*'
        )
        
        # Start consuming responses
        await self.response_queue.consume(self._handle_data_response)
        
        logger.info("RabbitMQ initialized for strategy data management")
    
    async def request_technical_indicators(self, 
                                         strategy_id: str,
                                         strategy_name: str,
                                         symbols: List[str],
                                         indicators: List[Dict],
                                         timeframes: List[str] = None,
                                         priority: DataPriority = DataPriority.NORMAL,
                                         callback: Callable = None) -> str:
        """
        Request technical indicators for strategy analysis
        
        Args:
            strategy_id: Unique strategy identifier
            strategy_name: Human readable strategy name
            symbols: List of trading symbols
            indicators: List of indicator configurations
            timeframes: List of timeframes (default: ['5m', '1h'])
            priority: Request priority level
            callback: Optional callback function for results
            
        Returns:
            Request ID for tracking
        """
        request_id = str(uuid.uuid4())
        
        if timeframes is None:
            timeframes = ['5m', '1h']
        
        parameters = {
            'indicators': indicators,
            'calculation_params': {
                'lookback_periods': 200,
                'include_volume': True,
                'real_time_updates': True
            }
        }
        
        request = StrategyDataRequest(
            request_id=request_id,
            strategy_id=strategy_id,
            strategy_name=strategy_name,
            request_type=DataRequestType.TECHNICAL_INDICATORS,
            symbols=symbols,
            timeframes=timeframes,
            parameters=parameters,
            priority=priority,
            callback_endpoint=None,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1)
        )
        
        await self._send_data_request(request)
        
        if callback:
            self.request_callbacks[request_id] = callback
        
        return request_id
    
    async def request_volume_profile(self,
                                   strategy_id: str,
                                   symbols: List[str],
                                   timeframes: List[str] = None,
                                   profile_type: str = "volume_at_price",
                                   callback: Callable = None) -> str:
        """Request volume profile analysis for symbols"""
        
        request_id = str(uuid.uuid4())
        
        if timeframes is None:
            timeframes = ['1h', '4h', '1d']
        
        parameters = {
            'profile_type': profile_type,  # volume_at_price, time_at_price, volume_weighted_price
            'resolution': 50,  # Number of price levels
            'session_splits': True,  # Split by trading sessions
            'value_area_percentage': 70  # Value area calculation
        }
        
        request = StrategyDataRequest(
            request_id=request_id,
            strategy_id=strategy_id,
            strategy_name=f"Volume Profile Request",
            request_type=DataRequestType.VOLUME_PROFILE,
            symbols=symbols,
            timeframes=timeframes,
            parameters=parameters,
            priority=DataPriority.NORMAL,
            callback_endpoint=None,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=30)
        )
        
        await self._send_data_request(request)
        
        if callback:
            self.request_callbacks[request_id] = callback
        
        return request_id
    
    async def request_sentiment_correlation(self,
                                          strategy_id: str,
                                          symbols: List[str],
                                          sentiment_sources: List[str] = None,
                                          callback: Callable = None) -> str:
        """Request sentiment data correlation with price movements"""
        
        request_id = str(uuid.uuid4())
        
        if sentiment_sources is None:
            sentiment_sources = ['twitter', 'reddit', 'news', 'fear_greed_index']
        
        parameters = {
            'sentiment_sources': sentiment_sources,
            'correlation_window': '24h',
            'aggregation_method': 'weighted_average',
            'include_entity_sentiment': True,  # Sentiment for specific entities (e.g., Bitcoin, Ethereum)
            'real_time_updates': True
        }
        
        request = StrategyDataRequest(
            request_id=request_id,
            strategy_id=strategy_id,
            strategy_name=f"Sentiment Correlation Request",
            request_type=DataRequestType.SENTIMENT_DATA,
            symbols=symbols,
            timeframes=['1h'],
            parameters=parameters,
            priority=DataPriority.HIGH,
            callback_endpoint=None,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=2)
        )
        
        await self._send_data_request(request)
        
        if callback:
            self.request_callbacks[request_id] = callback
        
        return request_id
    
    async def request_cross_asset_correlation(self,
                                            strategy_id: str,
                                            primary_symbols: List[str],
                                            correlation_assets: List[str] = None,
                                            callback: Callable = None) -> str:
        """Request cross-asset correlation analysis"""
        
        request_id = str(uuid.uuid4())
        
        if correlation_assets is None:
            correlation_assets = ['SPY', 'QQQ', 'GLD', 'DXY', 'VIX', 'TNX']
        
        parameters = {
            'correlation_assets': correlation_assets,
            'correlation_window': '30d',
            'rolling_correlation': True,
            'correlation_methods': ['pearson', 'spearman', 'kendall'],
            'include_lag_analysis': True,
            'update_frequency': '1h'
        }
        
        request = StrategyDataRequest(
            request_id=request_id,
            strategy_id=strategy_id,
            strategy_name=f"Cross-Asset Correlation Request",
            request_type=DataRequestType.CORRELATION_MATRIX,
            symbols=primary_symbols,
            timeframes=['1h', '1d'],
            parameters=parameters,
            priority=DataPriority.NORMAL,
            callback_endpoint=None,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=4)
        )
        
        await self._send_data_request(request)
        
        if callback:
            self.request_callbacks[request_id] = callback
        
        return request_id
    
    async def request_custom_composite_indicator(self,
                                               strategy_id: str,
                                               symbols: List[str],
                                               formula: str,
                                               input_indicators: List[Dict],
                                               timeframes: List[str] = None,
                                               callback: Callable = None) -> str:
        """Request custom composite indicator calculation"""
        
        request_id = str(uuid.uuid4())
        
        if timeframes is None:
            timeframes = ['5m', '15m', '1h']
        
        parameters = {
            'formula': formula,  # Mathematical formula using indicator names as variables
            'input_indicators': input_indicators,
            'normalization': True,
            'smoothing': {
                'enabled': True,
                'method': 'ema',
                'period': 3
            },
            'validation': {
                'min_value': None,
                'max_value': None,
                'bounds_handling': 'clip'  # clip, normalize, ignore
            }
        }
        
        request = StrategyDataRequest(
            request_id=request_id,
            strategy_id=strategy_id,
            strategy_name=f"Custom Composite Indicator",
            request_type=DataRequestType.CUSTOM_COMPOSITE,
            symbols=symbols,
            timeframes=timeframes,
            parameters=parameters,
            priority=DataPriority.HIGH,
            callback_endpoint=None,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=20)
        )
        
        await self._send_data_request(request)
        
        if callback:
            self.request_callbacks[request_id] = callback
        
        return request_id
    
    async def request_macro_economic_correlation(self,
                                              strategy_id: str,
                                              symbols: List[str],
                                              macro_indicators: List[str] = None,
                                              callback: Callable = None) -> str:
        """Request macro-economic indicator correlation analysis"""
        
        request_id = str(uuid.uuid4())
        
        if macro_indicators is None:
            macro_indicators = [
                'interest_rates', 'inflation_data', 'gdp_growth',
                'unemployment_rate', 'currency_strength', 'commodity_prices'
            ]
        
        parameters = {
            'macro_indicators': macro_indicators,
            'correlation_timeframes': ['1d', '1w', '1M'],
            'lag_analysis': {
                'enabled': True,
                'max_lag_days': 30,
                'lag_step': 1
            },
            'statistical_tests': ['granger_causality', 'cointegration'],
            'update_frequency': 'daily'
        }
        
        request = StrategyDataRequest(
            request_id=request_id,
            strategy_id=strategy_id,
            strategy_name=f"Macro Economic Correlation",
            request_type=DataRequestType.MACRO_INDICATORS,
            symbols=symbols,
            timeframes=['1d'],
            parameters=parameters,
            priority=DataPriority.LOW,
            callback_endpoint=None,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=8)
        )
        
        await self._send_data_request(request)
        
        if callback:
            self.request_callbacks[request_id] = callback
        
        return request_id
    
    async def _send_data_request(self, request: StrategyDataRequest):
        """Send data request to market data service via RabbitMQ"""
        try:
            # Store request for tracking
            self.active_requests[request.request_id] = request
            
            # Add to strategy subscriptions
            if request.strategy_id not in self.strategy_subscriptions:
                self.strategy_subscriptions[request.strategy_id] = []
            self.strategy_subscriptions[request.strategy_id].append(request.request_id)
            
            # Create message
            message_body = {
                'request': asdict(request),
                'response_queue': self.response_queue.name,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
            
            # Routing key based on request type and priority
            routing_key = f"strategy.request.{request.request_type.value}.{request.priority.value}"
            
            # Publish request
            message = aio_pika.Message(
                json.dumps(message_body, default=str).encode(),
                content_type='application/json',
                headers={
                    'request_id': request.request_id,
                    'strategy_id': request.strategy_id,
                    'request_type': request.request_type.value,
                    'priority': request.priority.value
                }
            )
            
            await self.strategy_exchange.publish(
                message,
                routing_key=routing_key
            )
            
            logger.info(
                "Data request sent to market data service",
                request_id=request.request_id,
                strategy_id=request.strategy_id,
                request_type=request.request_type.value
            )
            
        except Exception as e:
            logger.error(
                "Failed to send data request",
                request_id=request.request_id,
                error=str(e)
            )
            # Remove from tracking on error
            self.active_requests.pop(request.request_id, None)
            raise
    
    async def _handle_data_response(self, message: aio_pika.IncomingMessage):
        """Handle data response from market data service"""
        try:
            # Parse response
            response_data = json.loads(message.body.decode())
            request_id = response_data.get('request_id')
            
            if request_id not in self.active_requests:
                logger.warning(f"Received response for unknown request: {request_id}")
                await message.ack()
                return
            
            # Create data response object
            data_response = DataResponse(
                request_id=request_id,
                strategy_id=response_data.get('strategy_id'),
                data_type=response_data.get('data_type'),
                symbol=response_data.get('symbol'),
                timeframe=response_data.get('timeframe'),
                data=response_data.get('data', {}),
                timestamp=datetime.fromisoformat(response_data.get('timestamp')),
                quality_score=response_data.get('quality_score', 1.0),
                latency_ms=response_data.get('latency_ms', 0)
            )
            
            # Call registered callback if exists
            if request_id in self.request_callbacks:
                try:
                    callback = self.request_callbacks[request_id]
                    await callback(data_response)
                except Exception as e:
                    logger.error(f"Error in callback for request {request_id}: {e}")
            
            # Update metrics
            self._update_request_metrics(request_id, data_response)
            
            # Check if request is complete
            if response_data.get('is_complete', False):
                # Clean up completed request
                self.active_requests.pop(request_id, None)
                self.request_callbacks.pop(request_id, None)
            
            await message.ack()
            
        except Exception as e:
            logger.error(f"Error handling data response: {e}")
            await message.nack(requeue=False)
    
    def _update_request_metrics(self, request_id: str, response: DataResponse):
        """Update performance metrics for requests"""
        if request_id not in self.request_metrics:
            self.request_metrics[request_id] = {
                'start_time': datetime.now(timezone.utc),
                'responses_received': 0,
                'total_latency_ms': 0,
                'quality_scores': []
            }
        
        metrics = self.request_metrics[request_id]
        metrics['responses_received'] += 1
        metrics['total_latency_ms'] += response.latency_ms
        metrics['quality_scores'].append(response.quality_score)
    
    async def cancel_request(self, request_id: str) -> bool:
        """Cancel an active data request"""
        try:
            if request_id not in self.active_requests:
                return False
            
            # Send cancellation message
            cancel_message = {
                'action': 'cancel_request',
                'request_id': request_id,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
            
            message = aio_pika.Message(
                json.dumps(cancel_message).encode(),
                content_type='application/json'
            )
            
            await self.strategy_exchange.publish(
                message,
                routing_key='strategy.request.cancel'
            )
            
            # Clean up local tracking
            self.active_requests.pop(request_id, None)
            self.request_callbacks.pop(request_id, None)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to cancel request {request_id}: {e}")
            return False
    
    async def get_request_status(self, request_id: str) -> Optional[Dict]:
        """Get status of an active request"""
        if request_id not in self.active_requests:
            return None
        
        request = self.active_requests[request_id]
        metrics = self.request_metrics.get(request_id, {})
        
        return {
            'request_id': request_id,
            'strategy_id': request.strategy_id,
            'request_type': request.request_type.value,
            'status': 'active',
            'created_at': request.created_at,
            'expires_at': request.expires_at,
            'responses_received': metrics.get('responses_received', 0),
            'average_latency_ms': (
                metrics.get('total_latency_ms', 0) / 
                max(1, metrics.get('responses_received', 1))
            ),
            'average_quality_score': (
                sum(metrics.get('quality_scores', [1.0])) / 
                max(1, len(metrics.get('quality_scores', [1.0])))
            )
        }
    
    async def get_strategy_requests(self, strategy_id: str) -> List[Dict]:
        """Get all active requests for a strategy"""
        request_ids = self.strategy_subscriptions.get(strategy_id, [])
        return [
            await self.get_request_status(req_id)
            for req_id in request_ids
            if req_id in self.active_requests
        ]
    
    async def _request_cleanup_task(self):
        """Background task to clean up expired requests"""
        while True:
            try:
                current_time = datetime.now(timezone.utc)
                expired_requests = [
                    req_id for req_id, request in self.active_requests.items()
                    if request.expires_at < current_time
                ]
                
                for req_id in expired_requests:
                    await self.cancel_request(req_id)
                    logger.info(f"Cleaned up expired request: {req_id}")
                
                await asyncio.sleep(60)  # Check every minute
                
            except Exception as e:
                logger.error(f"Error in request cleanup task: {e}")
                await asyncio.sleep(60)
    
    async def _performance_monitoring_task(self):
        """Background task to monitor performance and log metrics"""
        while True:
            try:
                # Log performance metrics every 5 minutes
                total_active = len(self.active_requests)
                total_strategies = len(self.strategy_subscriptions)
                
                if total_active > 0:
                    avg_quality = sum(
                        sum(metrics.get('quality_scores', [1.0])) / 
                        max(1, len(metrics.get('quality_scores', [1.0])))
                        for metrics in self.request_metrics.values()
                    ) / len(self.request_metrics)
                    
                    logger.info(
                        "Strategy Data Manager Performance",
                        active_requests=total_active,
                        active_strategies=total_strategies,
                        average_quality_score=avg_quality
                    )
                
                await asyncio.sleep(300)  # Every 5 minutes
                
            except Exception as e:
                logger.error(f"Error in performance monitoring: {e}")
                await asyncio.sleep(300)
    
    async def close(self):
        """Clean up connections and resources"""
        try:
            # Cancel all active requests
            for request_id in list(self.active_requests.keys()):
                await self.cancel_request(request_id)
            
            # Close connections
            if self.http_session:
                await self.http_session.close()
            
            if self.rabbitmq_connection:
                await self.rabbitmq_connection.close()
            
            logger.info("Strategy Data Manager closed successfully")
            
        except Exception as e:
            logger.error(f"Error closing Strategy Data Manager: {e}")


# Convenience functions for easy integration
async def create_strategy_data_manager(rabbitmq_url: str, market_data_api_url: str) -> StrategyDataManager:
    """Create and initialize a Strategy Data Manager"""
    manager = StrategyDataManager(rabbitmq_url, market_data_api_url)
    await manager.initialize()
    return manager