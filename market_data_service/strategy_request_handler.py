"""
Strategy Data Request Handler for Market Data Service

This module handles dynamic data requests from the Strategy Service,
providing sophisticated data processing and real-time responses.
"""

import asyncio
import json
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Set
import aio_pika
import structlog
from dataclasses import dataclass, asdict
from enum import Enum

from database import Database
from technical_indicator_calculator import IndicatorCalculator
from sentiment_data_collector import SentimentDataCollector

logger = structlog.get_logger()

class RequestStatus(Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

@dataclass
class ProcessedDataResponse:
    request_id: str
    strategy_id: str
    data_type: str
    symbol: str
    timeframe: str
    data: Dict[str, Any]
    timestamp: datetime
    quality_score: float = 1.0
    latency_ms: int = 0
    is_complete: bool = False

class StrategyDataRequestHandler:
    """
    Handles dynamic data requests from Strategy Service
    
    Features:
    - Real-time technical indicator calculation
    - Volume profile and order flow analysis
    - Sentiment data correlation
    - Cross-asset correlation matrices
    - Custom composite indicator generation
    - Macro-economic data integration
    - Performance optimization and caching
    """
    
    def __init__(self, 
                 database: Database,
                 rabbitmq_url: str):
        self.database = database
        self.rabbitmq_url = rabbitmq_url
        
        # Connections
        self.rabbitmq_connection: Optional[aio_pika.Connection] = None
        self.rabbitmq_channel: Optional[aio_pika.Channel] = None
        
        # Processors
        self.indicator_calculator = IndicatorCalculator(database)
        self.sentiment_collector = SentimentDataCollector(database)
        
        # Request tracking
        self.active_requests: Dict[str, Dict] = {}
        self.request_processors: Dict[str, asyncio.Task] = {}
        
        # Performance tracking
        self.processing_stats = {
            'requests_processed': 0,
            'average_processing_time': 0,
            'cache_utilization': 0
        }
    
    async def initialize(self):
        """Initialize the request handler"""
        try:
            # Initialize RabbitMQ
            await self._init_rabbitmq()
            
            # Start background tasks
            asyncio.create_task(self._cleanup_task())
            asyncio.create_task(self._stats_reporting_task())
            
            logger.info("Strategy Data Request Handler initialized")
            
        except Exception as e:
            logger.error(f"Failed to initialize Strategy Data Request Handler: {e}")
            raise
    
    async def _init_rabbitmq(self):
        """Initialize RabbitMQ for handling strategy requests"""
        self.rabbitmq_connection = await aio_pika.connect_robust(
            self.rabbitmq_url,
            heartbeat=600,
            blocked_connection_timeout=300,
        )
        self.rabbitmq_channel = await self.rabbitmq_connection.channel()
        await self.rabbitmq_channel.set_qos(prefetch_count=50)
        
        # Declare exchanges
        self.strategy_exchange = await self.rabbitmq_channel.declare_exchange(
            'mastertrade.strategy.requests', aio_pika.ExchangeType.TOPIC, durable=True
        )
        
        self.response_exchange = await self.rabbitmq_channel.declare_exchange(
            'mastertrade.market.responses', aio_pika.ExchangeType.TOPIC, durable=True
        )
        
        # Create request queue
        self.request_queue = await self.rabbitmq_channel.declare_queue(
            'market_data_strategy_requests',
            durable=True
        )
        
        # Bind to all strategy request routing keys
        routing_patterns = [
            'strategy.request.technical_indicators.*',
            'strategy.request.volume_profile.*', 
            'strategy.request.sentiment_data.*',
            'strategy.request.correlation_matrix.*',
            'strategy.request.custom_composite.*',
            'strategy.request.macro_indicators.*',
            'strategy.request.cancel'
        ]
        
        for pattern in routing_patterns:
            await self.request_queue.bind(self.strategy_exchange, pattern)
        
        # Start consuming requests
        await self.request_queue.consume(self._handle_strategy_request)
        
        logger.info("RabbitMQ initialized for strategy data requests")
    
    async def _handle_strategy_request(self, message: aio_pika.IncomingMessage):
        """Handle incoming strategy data request"""
        try:
            # Parse request
            request_data = json.loads(message.body.decode())
            
            if request_data.get('action') == 'cancel_request':
                await self._handle_cancel_request(request_data)
                await message.ack()
                return
            
            request_info = request_data.get('request', {})
            response_queue_name = request_data.get('response_queue')
            
            request_id = request_info.get('request_id')
            request_type = request_info.get('request_type')
            
            # Track active request
            self.active_requests[request_id] = {
                'status': RequestStatus.PENDING,
                'start_time': datetime.now(timezone.utc),
                'request_info': request_info,
                'response_queue': response_queue_name,
                'message': message
            }
            
            # Route to appropriate processor
            processor_task = None
            
            if request_type == 'technical_indicators':
                processor_task = asyncio.create_task(
                    self._process_technical_indicators_request(request_id, request_info, response_queue_name)
                )
            elif request_type == 'volume_profile':
                processor_task = asyncio.create_task(
                    self._process_volume_profile_request(request_id, request_info, response_queue_name)
                )
            elif request_type == 'sentiment_data':
                processor_task = asyncio.create_task(
                    self._process_sentiment_data_request(request_id, request_info, response_queue_name)
                )
            elif request_type == 'correlation_matrix':
                processor_task = asyncio.create_task(
                    self._process_correlation_request(request_id, request_info, response_queue_name)
                )
            elif request_type == 'custom_composite':
                processor_task = asyncio.create_task(
                    self._process_custom_composite_request(request_id, request_info, response_queue_name)
                )
            elif request_type == 'macro_indicators':
                processor_task = asyncio.create_task(
                    self._process_macro_indicators_request(request_id, request_info, response_queue_name)
                )
            else:
                await self._send_error_response(
                    request_id, 
                    request_info.get('strategy_id'),
                    response_queue_name,
                    f"Unknown request type: {request_type}"
                )
                await message.ack()
                return
            
            # Track processor
            self.request_processors[request_id] = processor_task
            
            # Update status
            self.active_requests[request_id]['status'] = RequestStatus.PROCESSING
            
            await message.ack()
            
        except Exception as e:
            logger.error(f"Error handling strategy request: {e}")
            await message.nack(requeue=False)
    
    async def _process_technical_indicators_request(self, 
                                                  request_id: str, 
                                                  request_info: Dict, 
                                                  response_queue: str):
        """Process technical indicators request"""
        try:
            strategy_id = request_info.get('strategy_id')
            symbols = request_info.get('symbols', [])
            timeframes = request_info.get('timeframes', [])
            indicators = request_info.get('parameters', {}).get('indicators', [])
            
            start_time = datetime.now(timezone.utc)
            
            for symbol in symbols:
                for timeframe in timeframes:
                    # Get historical data
                    historical_data = await self.database.get_historical_data(
                        symbol=symbol,
                        timeframe=timeframe,
                        limit=500
                    )
                    
                    if not historical_data:
                        continue
                    
                    # Calculate indicators
                    indicator_results = {}
                    for indicator_config in indicators:
                        try:
                            indicator_name = indicator_config.get('name')
                            indicator_params = indicator_config.get('parameters', {})
                            
                            result = await self.indicator_calculator.calculate_indicator(
                                symbol=symbol,
                                timeframe=timeframe,
                                indicator_name=indicator_name,
                                parameters=indicator_params,
                                data=historical_data
                            )
                            
                            indicator_results[indicator_name] = result
                            
                        except Exception as e:
                            logger.error(f"Error calculating indicator {indicator_name}: {e}")
                            continue
                    
                    # Calculate processing time
                    processing_time = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
                    
                    # Send response
                    response = ProcessedDataResponse(
                        request_id=request_id,
                        strategy_id=strategy_id,
                        data_type='technical_indicators',
                        symbol=symbol,
                        timeframe=timeframe,
                        data={
                            'indicators': indicator_results,
                            'historical_data': historical_data[-50:],  # Last 50 points
                            'metadata': {
                                'calculation_time': processing_time,
                                'data_quality_score': self._calculate_data_quality(historical_data)
                            }
                        },
                        timestamp=datetime.now(timezone.utc),
                        quality_score=self._calculate_data_quality(historical_data),
                        latency_ms=int(processing_time),
                        is_complete=False
                    )
                    
                    await self._send_data_response(response, response_queue)
            
            # Send completion signal
            completion_response = ProcessedDataResponse(
                request_id=request_id,
                strategy_id=strategy_id,
                data_type='technical_indicators',
                symbol='',
                timeframe='',
                data={'status': 'completed'},
                timestamp=datetime.now(timezone.utc),
                is_complete=True
            )
            
            await self._send_data_response(completion_response, response_queue)
            
            # Update request status
            self.active_requests[request_id]['status'] = RequestStatus.COMPLETED
            
        except Exception as e:
            logger.error(f"Error processing technical indicators request {request_id}: {e}")
            await self._send_error_response(
                request_id, 
                request_info.get('strategy_id'), 
                response_queue, 
                str(e)
            )
    
    async def _process_volume_profile_request(self, 
                                            request_id: str, 
                                            request_info: Dict, 
                                            response_queue: str):
        """Process volume profile analysis request"""
        try:
            strategy_id = request_info.get('strategy_id')
            symbols = request_info.get('symbols', [])
            timeframes = request_info.get('timeframes', [])
            parameters = request_info.get('parameters', {})
            
            profile_type = parameters.get('profile_type', 'volume_at_price')
            resolution = parameters.get('resolution', 50)
            
            for symbol in symbols:
                for timeframe in timeframes:
                    # Get detailed market data with volume
                    market_data = await self.database.get_historical_data(
                        symbol=symbol,
                        timeframe=timeframe,
                        limit=1000,
                        include_volume=True
                    )
                    
                    if not market_data:
                        continue
                    
                    # Calculate volume profile
                    volume_profile = await self._calculate_volume_profile(
                        market_data, 
                        profile_type, 
                        resolution
                    )
                    
                    # Send response
                    response = ProcessedDataResponse(
                        request_id=request_id,
                        strategy_id=strategy_id,
                        data_type='volume_profile',
                        symbol=symbol,
                        timeframe=timeframe,
                        data={
                            'volume_profile': volume_profile,
                            'analysis': {
                                'poc_price': volume_profile.get('poc_price'),  # Point of Control
                                'value_area_high': volume_profile.get('value_area_high'),
                                'value_area_low': volume_profile.get('value_area_low'),
                                'volume_weighted_price': volume_profile.get('vwap')
                            }
                        },
                        timestamp=datetime.now(timezone.utc),
                        is_complete=False
                    )
                    
                    await self._send_data_response(response, response_queue)
            
            # Send completion
            await self._send_completion_response(request_id, strategy_id, response_queue)
            
        except Exception as e:
            logger.error(f"Error processing volume profile request {request_id}: {e}")
            await self._send_error_response(request_id, strategy_id, response_queue, str(e))
    
    async def _process_sentiment_data_request(self, 
                                            request_id: str, 
                                            request_info: Dict, 
                                            response_queue: str):
        """Process sentiment data correlation request"""
        try:
            strategy_id = request_info.get('strategy_id')
            symbols = request_info.get('symbols', [])
            parameters = request_info.get('parameters', {})
            
            sentiment_sources = parameters.get('sentiment_sources', ['twitter', 'reddit', 'news'])
            correlation_window = parameters.get('correlation_window', '24h')
            
            for symbol in symbols:
                # Get sentiment data
                sentiment_data = await self.sentiment_collector.get_sentiment_data(
                    symbol=symbol,
                    sources=sentiment_sources,
                    timeframe='1h',
                    lookback_hours=24
                )
                
                # Get price data for correlation
                price_data = await self.database.get_historical_data(
                    symbol=symbol,
                    timeframe='1h',
                    limit=24
                )
                
                # Calculate sentiment-price correlation
                correlation_analysis = await self._calculate_sentiment_correlation(
                    sentiment_data, 
                    price_data, 
                    correlation_window
                )
                
                response = ProcessedDataResponse(
                    request_id=request_id,
                    strategy_id=strategy_id,
                    data_type='sentiment_correlation',
                    symbol=symbol,
                    timeframe='1h',
                    data={
                        'sentiment_data': sentiment_data,
                        'correlation_analysis': correlation_analysis,
                        'insights': {
                            'sentiment_trend': correlation_analysis.get('sentiment_trend'),
                            'price_correlation': correlation_analysis.get('correlation_coefficient'),
                            'predictive_strength': correlation_analysis.get('predictive_strength')
                        }
                    },
                    timestamp=datetime.now(timezone.utc),
                    is_complete=False
                )
                
                await self._send_data_response(response, response_queue)
            
            await self._send_completion_response(request_id, strategy_id, response_queue)
            
        except Exception as e:
            logger.error(f"Error processing sentiment data request {request_id}: {e}")
            await self._send_error_response(request_id, strategy_id, response_queue, str(e))
    
    async def _process_correlation_request(self, 
                                         request_id: str, 
                                         request_info: Dict, 
                                         response_queue: str):
        """Process cross-asset correlation request"""
        try:
            strategy_id = request_info.get('strategy_id')
            symbols = request_info.get('symbols', [])
            parameters = request_info.get('parameters', {})
            
            correlation_assets = parameters.get('correlation_assets', ['SPY', 'QQQ', 'GLD'])
            correlation_window = parameters.get('correlation_window', '30d')
            
            all_symbols = symbols + correlation_assets
            
            # Get price data for all symbols
            price_data = {}
            for symbol in all_symbols:
                data = await self.database.get_historical_data(
                    symbol=symbol,
                    timeframe='1d',
                    limit=30
                )
                if data:
                    price_data[symbol] = [d['close'] for d in data]
            
            # Calculate correlation matrix
            correlation_matrix = await self._calculate_correlation_matrix(price_data)
            
            response = ProcessedDataResponse(
                request_id=request_id,
                strategy_id=strategy_id,
                data_type='correlation_matrix',
                symbol='',
                timeframe='1d',
                data={
                    'correlation_matrix': correlation_matrix,
                    'symbols': all_symbols,
                    'analysis': {
                        'strongest_correlations': correlation_matrix.get('strongest_pairs', []),
                        'market_regime': correlation_matrix.get('market_regime'),
                        'diversification_score': correlation_matrix.get('diversification_score')
                    }
                },
                timestamp=datetime.now(timezone.utc),
                is_complete=True
            )
            
            await self._send_data_response(response, response_queue)
            
        except Exception as e:
            logger.error(f"Error processing correlation request {request_id}: {e}")
            await self._send_error_response(request_id, strategy_id, response_queue, str(e))
    
    async def _process_custom_composite_request(self, 
                                              request_id: str, 
                                              request_info: Dict, 
                                              response_queue: str):
        """Process custom composite indicator request"""
        try:
            strategy_id = request_info.get('strategy_id')
            symbols = request_info.get('symbols', [])
            timeframes = request_info.get('timeframes', [])
            parameters = request_info.get('parameters', {})
            
            formula = parameters.get('formula')
            input_indicators = parameters.get('input_indicators', [])
            
            for symbol in symbols:
                for timeframe in timeframes:
                    # Calculate input indicators
                    indicator_values = {}
                    for indicator_config in input_indicators:
                        indicator_name = indicator_config.get('name')
                        result = await self.indicator_calculator.calculate_indicator(
                            symbol=symbol,
                            timeframe=timeframe,
                            indicator_name=indicator_name,
                            parameters=indicator_config.get('parameters', {})
                        )
                        indicator_values[indicator_name] = result
                    
                    # Calculate composite indicator
                    composite_result = await self._calculate_composite_indicator(
                        formula, 
                        indicator_values
                    )
                    
                    response = ProcessedDataResponse(
                        request_id=request_id,
                        strategy_id=strategy_id,
                        data_type='custom_composite',
                        symbol=symbol,
                        timeframe=timeframe,
                        data={
                            'composite_indicator': composite_result,
                            'input_indicators': indicator_values,
                            'formula': formula,
                            'metadata': {
                                'calculation_success': composite_result is not None,
                                'input_count': len(indicator_values)
                            }
                        },
                        timestamp=datetime.now(timezone.utc),
                        is_complete=False
                    )
                    
                    await self._send_data_response(response, response_queue)
            
            await self._send_completion_response(request_id, strategy_id, response_queue)
            
        except Exception as e:
            logger.error(f"Error processing custom composite request {request_id}: {e}")
            await self._send_error_response(request_id, strategy_id, response_queue, str(e))
    
    async def _process_macro_indicators_request(self, 
                                              request_id: str, 
                                              request_info: Dict, 
                                              response_queue: str):
        """Process macro-economic indicators request"""
        try:
            strategy_id = request_info.get('strategy_id')
            symbols = request_info.get('symbols', [])
            parameters = request_info.get('parameters', {})
            
            macro_indicators = parameters.get('macro_indicators', [])
            
            # Get macro-economic data (placeholder implementation)
            macro_data = await self._get_macro_economic_data(macro_indicators)
            
            # Calculate correlation with symbols
            correlations = {}
            for symbol in symbols:
                price_data = await self.database.get_historical_data(
                    symbol=symbol,
                    timeframe='1d',
                    limit=90
                )
                
                symbol_correlations = await self._calculate_macro_correlations(
                    price_data, 
                    macro_data
                )
                correlations[symbol] = symbol_correlations
            
            response = ProcessedDataResponse(
                request_id=request_id,
                strategy_id=strategy_id,
                data_type='macro_indicators',
                symbol='',
                timeframe='1d',
                data={
                    'macro_data': macro_data,
                    'symbol_correlations': correlations,
                    'analysis': {
                        'strongest_macro_factors': macro_data.get('strongest_factors', []),
                        'market_regime_indicators': macro_data.get('regime_indicators', {}),
                        'economic_cycle_phase': macro_data.get('cycle_phase', 'unknown')
                    }
                },
                timestamp=datetime.now(timezone.utc),
                is_complete=True
            )
            
            await self._send_data_response(response, response_queue)
            
        except Exception as e:
            logger.error(f"Error processing macro indicators request {request_id}: {e}")
            await self._send_error_response(request_id, strategy_id, response_queue, str(e))
    
    async def _handle_cancel_request(self, request_data: Dict):
        """Handle request cancellation"""
        request_id = request_data.get('request_id')
        
        if request_id in self.active_requests:
            # Cancel processing task
            if request_id in self.request_processors:
                task = self.request_processors[request_id]
                task.cancel()
                del self.request_processors[request_id]
            
            # Update status
            self.active_requests[request_id]['status'] = RequestStatus.CANCELLED
            
            logger.info(f"Cancelled data request: {request_id}")
    
    async def _send_data_response(self, response: ProcessedDataResponse, response_queue: str):
        """Send processed data response back to strategy service"""
        try:
            response_data = {
                'request_id': response.request_id,
                'strategy_id': response.strategy_id,
                'data_type': response.data_type,
                'symbol': response.symbol,
                'timeframe': response.timeframe,
                'data': response.data,
                'timestamp': response.timestamp.isoformat(),
                'quality_score': response.quality_score,
                'latency_ms': response.latency_ms,
                'is_complete': response.is_complete
            }
            
            # Create routing key
            routing_key = f"market.response.{response.data_type}"
            
            message = aio_pika.Message(
                json.dumps(response_data, default=str).encode(),
                content_type='application/json',
                headers={
                    'request_id': response.request_id,
                    'strategy_id': response.strategy_id,
                    'data_type': response.data_type
                }
            )
            
            await self.response_exchange.publish(message, routing_key=routing_key)
            
        except Exception as e:
            logger.error(f"Error sending data response: {e}")
    
    async def _send_completion_response(self, request_id: str, strategy_id: str, response_queue: str):
        """Send completion response"""
        completion_response = ProcessedDataResponse(
            request_id=request_id,
            strategy_id=strategy_id,
            data_type='completion',
            symbol='',
            timeframe='',
            data={'status': 'completed'},
            timestamp=datetime.now(timezone.utc),
            is_complete=True
        )
        await self._send_data_response(completion_response, response_queue)
    
    async def _send_error_response(self, request_id: str, strategy_id: str, response_queue: str, error_message: str):
        """Send error response"""
        error_response = ProcessedDataResponse(
            request_id=request_id,
            strategy_id=strategy_id,
            data_type='error',
            symbol='',
            timeframe='',
            data={'error': error_message, 'status': 'failed'},
            timestamp=datetime.now(timezone.utc),
            quality_score=0.0,
            is_complete=True
        )
        await self._send_data_response(error_response, response_queue)
    
    # Helper methods for calculations
    async def _calculate_volume_profile(self, market_data: List[Dict], profile_type: str, resolution: int) -> Dict:
        """Calculate volume profile analysis"""
        # Placeholder implementation - would contain sophisticated volume analysis
        return {
            'poc_price': 0.0,  # Point of Control
            'value_area_high': 0.0,
            'value_area_low': 0.0,
            'vwap': 0.0,
            'volume_nodes': []
        }
    
    async def _calculate_sentiment_correlation(self, sentiment_data: List[Dict], price_data: List[Dict], window: str) -> Dict:
        """Calculate sentiment-price correlation"""
        # Placeholder implementation
        return {
            'correlation_coefficient': 0.0,
            'sentiment_trend': 'neutral',
            'predictive_strength': 'low'
        }
    
    async def _calculate_correlation_matrix(self, price_data: Dict[str, List[float]]) -> Dict:
        """Calculate cross-asset correlation matrix"""
        # Placeholder implementation
        return {
            'matrix': {},
            'strongest_pairs': [],
            'market_regime': 'normal',
            'diversification_score': 0.0
        }
    
    async def _calculate_composite_indicator(self, formula: str, indicator_values: Dict) -> Optional[List[float]]:
        """Calculate custom composite indicator"""
        # Placeholder implementation - would parse and execute formula
        return []
    
    async def _get_macro_economic_data(self, indicators: List[str]) -> Dict:
        """Get macro-economic data"""
        # Placeholder implementation
        return {
            'indicators': {},
            'strongest_factors': [],
            'regime_indicators': {},
            'cycle_phase': 'expansion'
        }
    
    async def _calculate_macro_correlations(self, price_data: List[Dict], macro_data: Dict) -> Dict:
        """Calculate macro-economic correlations"""
        # Placeholder implementation
        return {}
    
    def _calculate_data_quality(self, data: List[Dict]) -> float:
        """Calculate data quality score"""
        if not data:
            return 0.0
        
        # Simple quality metrics
        completeness = len([d for d in data if all(k in d for k in ['open', 'high', 'low', 'close'])]) / len(data)
        return completeness
    
    async def _cleanup_task(self):
        """Background task to clean up completed requests"""
        while True:
            try:
                current_time = datetime.now(timezone.utc)
                cleanup_requests = []
                
                for request_id, request_info in self.active_requests.items():
                    start_time = request_info.get('start_time')
                    status = request_info.get('status')
                    
                    # Clean up old completed/failed requests
                    if status in [RequestStatus.COMPLETED, RequestStatus.FAILED, RequestStatus.CANCELLED]:
                        if (current_time - start_time).total_seconds() > 3600:  # 1 hour
                            cleanup_requests.append(request_id)
                    
                    # Clean up very old pending requests
                    elif status == RequestStatus.PENDING:
                        if (current_time - start_time).total_seconds() > 1800:  # 30 minutes
                            cleanup_requests.append(request_id)
                
                # Clean up
                for request_id in cleanup_requests:
                    if request_id in self.request_processors:
                        task = self.request_processors[request_id]
                        task.cancel()
                        del self.request_processors[request_id]
                    
                    del self.active_requests[request_id]
                
                if cleanup_requests:
                    logger.info(f"Cleaned up {len(cleanup_requests)} old requests")
                
                await asyncio.sleep(300)  # Check every 5 minutes
                
            except Exception as e:
                logger.error(f"Error in cleanup task: {e}")
                await asyncio.sleep(300)
    
    async def _stats_reporting_task(self):
        """Background task to report processing statistics"""
        while True:
            try:
                active_count = len(self.active_requests)
                processing_count = len([
                    r for r in self.active_requests.values() 
                    if r.get('status') == RequestStatus.PROCESSING
                ])
                
                logger.info(
                    "Strategy Data Request Handler Stats",
                    active_requests=active_count,
                    processing_requests=processing_count,
                    completed_requests=self.processing_stats['requests_processed']
                )
                
                await asyncio.sleep(300)  # Every 5 minutes
                
            except Exception as e:
                logger.error(f"Error in stats reporting: {e}")
                await asyncio.sleep(300)
    
    async def close(self):
        """Clean up connections and resources"""
        try:
            # Cancel all active processors
            for task in self.request_processors.values():
                task.cancel()
            
            # Close RabbitMQ connection
            if self.rabbitmq_connection:
                await self.rabbitmq_connection.close()
            
            logger.info("Strategy Data Request Handler closed successfully")
            
        except Exception as e:
            logger.error(f"Error closing Strategy Data Request Handler: {e}")