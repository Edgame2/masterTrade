"""
Indicator Configuration Manager

Handles dynamic indicator configuration requests from strategy service
via RabbitMQ and manages the lifecycle of indicator calculations.
Now uses database storage for persistent configuration management.
"""

import asyncio
import json
import uuid
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

import aio_pika
import structlog
from prometheus_client import Counter, Gauge, Histogram

from indicator_models import (
    IndicatorConfiguration, IndicatorRequest, BulkIndicatorRequest,
    IndicatorSubscription, IndicatorResult
)
from models import IndicatorConfigurationDB, IndicatorCalculationResult
from technical_indicator_calculator import IndicatorCalculator
from database import Database

logger = structlog.get_logger()

# Metrics
configuration_requests = Counter('indicator_config_requests_total', 'Configuration requests', ['action'])
subscription_events = Counter('indicator_subscription_events_total', 'Subscription events', ['event'])
message_processing = Histogram('indicator_message_processing_seconds', 'Message processing time')


class IndicatorConfigurationManager:
    """Manages dynamic indicator configuration and calculation lifecycle with database persistence"""
    
    def __init__(self, calculator: IndicatorCalculator, database: Database, rabbitmq_channel: aio_pika.Channel):
        self.calculator = calculator
        self.database = database
        self.channel = rabbitmq_channel
        self.exchanges: Dict[str, aio_pika.Exchange] = {}
        self.queues: Dict[str, aio_pika.Queue] = {}
        
        # In-memory cache for active configurations (loaded from database)
        self.cached_configurations: Dict[str, Dict[str, Any]] = {}
        self.last_db_refresh = datetime.utcnow()
        self.db_refresh_interval = 300  # Refresh from DB every 5 minutes
        
        # Background processing
        self.processing_task: Optional[asyncio.Task] = None
        self.refresh_task: Optional[asyncio.Task] = None
        self.update_interval = 60  # seconds
        
    async def initialize(self):
        """Initialize RabbitMQ exchanges and queues for indicator management"""
        try:
            # Declare indicator configuration exchange
            self.exchanges['indicator_config'] = await self.channel.declare_exchange(
                'indicator_config',
                aio_pika.ExchangeType.TOPIC,
                durable=True
            )
            
            # Declare indicator results exchange
            self.exchanges['indicator_results'] = await self.channel.declare_exchange(
                'indicator_results',
                aio_pika.ExchangeType.TOPIC,
                durable=True
            )
            
            # Queue for receiving configuration requests
            self.queues['config_requests'] = await self.channel.declare_queue(
                'market_data.indicator_config_requests',
                durable=True,
                arguments={
                    "x-message-ttl": 3600000,  # 1 hour TTL
                    "x-max-length": 1000
                }
            )
            
            # Bind configuration queue
            await self.queues['config_requests'].bind(
                self.exchanges['indicator_config'],
                routing_key='config.request.#'
            )
            
            # Start consuming configuration requests
            await self.queues['config_requests'].consume(self._handle_config_request)
            
            logger.info("Indicator configuration manager initialized")
            
        except Exception as e:
            logger.error("Error initializing indicator configuration manager", error=str(e))
            raise
    
    async def start_processing(self):
        """Start background processing tasks"""
        if not self.processing_task:
            # Load initial configurations from database
            await self._refresh_configurations_from_db()
            
            # Start processing tasks
            self.processing_task = asyncio.create_task(self._background_processor())
            self.refresh_task = asyncio.create_task(self._db_refresh_task())
            logger.info("Started indicator background processing")
    
    async def stop_processing(self):
        """Stop background processing tasks"""
        if self.processing_task:
            self.processing_task.cancel()
            try:
                await self.processing_task
            except asyncio.CancelledError:
                pass
            self.processing_task = None
            
        if self.refresh_task:
            self.refresh_task.cancel()
            try:
                await self.refresh_task
            except asyncio.CancelledError:
                pass
            self.refresh_task = None
            
        logger.info("Stopped indicator background processing")
    
    async def _refresh_configurations_from_db(self):
        """Refresh cached configurations from database"""
        try:
            # Get all active configurations from database
            db_configs = await self.database.get_active_indicator_configurations()
            
            # Update cache
            self.cached_configurations.clear()
            for config in db_configs:
                self.cached_configurations[config['id']] = config
            
            self.last_db_refresh = datetime.utcnow()
            
            logger.info("Refreshed configurations from database", 
                       count=len(self.cached_configurations))
            
        except Exception as e:
            logger.error("Error refreshing configurations from database", error=str(e))
    
    async def _db_refresh_task(self):
        """Background task to periodically refresh configurations from database"""
        while True:
            try:
                await asyncio.sleep(self.db_refresh_interval)
                await self._refresh_configurations_from_db()
                
            except asyncio.CancelledError:
                logger.info("DB refresh task cancelled")
                break
            except Exception as e:
                logger.error("Error in DB refresh task", error=str(e))
                await asyncio.sleep(60)  # Wait before retry
    
    async def _handle_config_request(self, message: aio_pika.IncomingMessage):
        """Handle incoming configuration requests from strategy service"""
        start_time = time.time()
        
        async with message.process():
            try:
                # Parse message
                routing_key = message.routing_key
                body = json.loads(message.body.decode())
                
                logger.info("Received indicator configuration request", 
                          routing_key=routing_key, strategy_id=body.get('strategy_id'))
                
                # Route based on action
                if routing_key == 'config.request.add':
                    await self._handle_add_configuration(body)
                elif routing_key == 'config.request.update':
                    await self._handle_update_configuration(body)
                elif routing_key == 'config.request.remove':
                    await self._handle_remove_configuration(body)
                elif routing_key == 'config.request.bulk':
                    await self._handle_bulk_request(body)
                elif routing_key == 'config.request.subscribe':
                    await self._handle_subscription_request(body)
                else:
                    logger.warning("Unknown configuration request type", routing_key=routing_key)
                
                configuration_requests.labels(action=routing_key.split('.')[-1]).inc()
                
            except Exception as e:
                logger.error("Error handling configuration request", error=str(e))
            finally:
                processing_time = time.time() - start_time
                message_processing.observe(processing_time)
    
    async def _handle_add_configuration(self, data: Dict[str, Any]):
        """Handle add configuration request - now stores in database"""
        try:
            # Parse configuration
            config_data = data.get('configuration')
            if not config_data:
                raise ValueError("Missing configuration data")
            
            # Convert to database model
            db_config = IndicatorConfigurationDB(
                id=config_data.get('id', f"{config_data['indicator_type']}_{uuid.uuid4().hex[:8]}"),
                strategy_id=config_data['strategy_id'],
                indicator_type=config_data['indicator_type'],
                symbol=config_data['symbol'],
                interval=config_data['interval'],
                parameters={p['name']: p['value'] for p in config_data.get('parameters', [])},
                output_fields=config_data.get('output_fields', []),
                periods_required=config_data.get('periods_required', 20),
                active=True,
                priority=config_data.get('priority', 1),
                cache_duration_minutes=config_data.get('cache_duration_minutes', 5),
                continuous_calculation=data.get('continuous_calculation', True),
                publish_to_rabbitmq=data.get('publish_to_rabbitmq', True)
            )
            
            # Store in database
            success = await self.database.create_indicator_configuration(db_config)
            if not success:
                raise Exception("Failed to store configuration in database")
            
            # Update local cache
            self.cached_configurations[db_config.id] = db_config.dict()
            
            # Immediate calculation if requested
            if data.get('calculate_immediately', True):
                # Convert back to IndicatorConfiguration for calculation
                calc_config = self._db_config_to_indicator_config(db_config.dict())
                result = await self.calculator.calculate_indicator(calc_config)
                
                # Store result in database
                await self._store_calculation_result(result, db_config)
                
                # Publish result
                await self._publish_result(result)
            
            # Send confirmation
            await self._send_response(data.get('reply_to'), {
                'status': 'success',
                'action': 'configuration_added',
                'configuration_id': db_config.id,
                'strategy_id': db_config.strategy_id
            })
            
            logger.info("Added indicator configuration to database", 
                       config_id=db_config.id, strategy_id=db_config.strategy_id)
            
        except Exception as e:
            logger.error("Error adding configuration", error=str(e))
            await self._send_error_response(data.get('reply_to'), str(e))
    
    async def _handle_update_configuration(self, data: Dict[str, Any]):
        """Handle update configuration request - now updates database"""
        try:
            config_id = data.get('configuration_id')
            strategy_id = data.get('strategy_id')
            updates = data.get('updates', {})
            
            if not config_id or not strategy_id:
                raise ValueError("Missing configuration_id or strategy_id")
            
            # Update in database
            success = await self.database.update_indicator_configuration(
                config_id, strategy_id, updates
            )
            
            if not success:
                raise ValueError(f"Configuration {config_id} not found")
            
            # Update local cache
            if config_id in self.cached_configurations:
                self.cached_configurations[config_id].update(updates)
                self.cached_configurations[config_id]['updated_at'] = datetime.utcnow().isoformat() + "Z"
            
            # Immediate recalculation if requested
            if data.get('recalculate_immediately', True):
                updated_config_dict = await self.database.get_indicator_configuration(config_id, strategy_id)
                if updated_config_dict:
                    calc_config = self._db_config_to_indicator_config(updated_config_dict)
                    result = await self.calculator.calculate_indicator(calc_config)
                    
                    # Store result and publish
                    await self._store_calculation_result(result, updated_config_dict)
                    await self._publish_result(result)
            
            await self._send_response(data.get('reply_to'), {
                'status': 'success',
                'action': 'configuration_updated',
                'configuration_id': config_id
            })
            
            logger.info("Updated indicator configuration in database", config_id=config_id)
                
        except Exception as e:
            logger.error("Error updating configuration", error=str(e))
            await self._send_error_response(data.get('reply_to'), str(e))
    
    async def _handle_remove_configuration(self, data: Dict[str, Any]):
        """Handle remove configuration request - now removes from database"""
        try:
            config_id = data.get('configuration_id')
            strategy_id = data.get('strategy_id')
            
            if not config_id or not strategy_id:
                raise ValueError("Missing configuration_id or strategy_id")
            
            # Remove from database
            success = await self.database.delete_indicator_configuration(config_id, strategy_id)
            
            if not success:
                logger.warning("Configuration not found in database for removal", config_id=config_id)
            
            # Remove from local cache
            if config_id in self.cached_configurations:
                del self.cached_configurations[config_id]
            
            await self._send_response(data.get('reply_to'), {
                'status': 'success',
                'action': 'configuration_removed',
                'configuration_id': config_id
            })
            
            logger.info("Removed indicator configuration from database", config_id=config_id)
            
        except Exception as e:
            logger.error("Error removing configuration", error=str(e))
            await self._send_error_response(data.get('reply_to'), str(e))
    
    async def _handle_bulk_request(self, data: Dict[str, Any]):
        """Handle bulk indicator calculation request"""
        try:
            request_data = data.get('request')
            if not request_data:
                raise ValueError("Missing bulk request data")
            
            bulk_request = BulkIndicatorRequest(**request_data)
            
            # Calculate all indicators
            results = await self.calculator.calculate_bulk_indicators(bulk_request)
            
            # Publish all results
            for result in results:
                await self._publish_result(result)
            
            await self._send_response(data.get('reply_to'), {
                'status': 'success',
                'action': 'bulk_calculation_completed',
                'results_count': len(results),
                'strategy_id': bulk_request.strategy_id
            })
            
            logger.info("Completed bulk indicator calculation", 
                       strategy_id=bulk_request.strategy_id, 
                       results_count=len(results))
            
        except Exception as e:
            logger.error("Error processing bulk request", error=str(e))
            await self._send_error_response(data.get('reply_to'), str(e))
    
    async def _handle_subscription_request(self, data: Dict[str, Any]):
        """Handle subscription request"""
        try:
            subscription_data = data.get('subscription')
            if not subscription_data:
                raise ValueError("Missing subscription data")
            
            subscription = IndicatorSubscription(**subscription_data)
            
            # Create subscription in calculator
            success = await self.calculator.create_subscription(
                subscription.subscription_id,
                subscription.indicators
            )
            
            if success:
                subscription_events.labels(event='created').inc()
                await self._send_response(data.get('reply_to'), {
                    'status': 'success',
                    'action': 'subscription_created',
                    'subscription_id': subscription.subscription_id
                })
            else:
                raise Exception("Failed to create subscription")
            
            logger.info("Created indicator subscription", 
                       subscription_id=subscription.subscription_id)
            
        except Exception as e:
            logger.error("Error creating subscription", error=str(e))
            await self._send_error_response(data.get('reply_to'), str(e))
    
    async def _publish_result(self, result: IndicatorResult):
        """Publish indicator result to RabbitMQ"""
        try:
            # Create routing key based on result
            routing_key = f"result.{result.symbol}.{result.interval}"
            
            # Publish result
            message = aio_pika.Message(
                json.dumps(result.dict(), default=str).encode(),
                content_type='application/json',
                timestamp=datetime.utcnow()
            )
            
            await self.exchanges['indicator_results'].publish(
                message,
                routing_key=routing_key
            )
            
            logger.debug("Published indicator result", 
                        symbol=result.symbol, 
                        configuration_id=result.configuration_id)
            
        except Exception as e:
            logger.error("Error publishing indicator result", error=str(e))
    
    async def _send_response(self, reply_to: Optional[str], response: Dict[str, Any]):
        """Send response message"""
        if reply_to:
            try:
                message = aio_pika.Message(
                    json.dumps(response, default=str).encode(),
                    content_type='application/json'
                )
                
                await self.channel.default_exchange.publish(
                    message,
                    routing_key=reply_to
                )
            except Exception as e:
                logger.error("Error sending response", error=str(e))
    
    async def _send_error_response(self, reply_to: Optional[str], error_message: str):
        """Send error response"""
        await self._send_response(reply_to, {
            'status': 'error',
            'error': error_message,
            'timestamp': datetime.utcnow().isoformat()
        })
    
    async def _background_processor(self):
        """Background task for processing subscriptions and updates from database configurations"""
        while True:
            try:
                # Get configurations due for calculation from database
                due_configs = await self.database.get_configurations_due_for_calculation(
                    max_age_seconds=self.update_interval
                )
                
                # Process each configuration
                for config_dict in due_configs:
                    try:
                        # Convert to calculation format
                        calc_config = self._db_config_to_indicator_config(config_dict)
                        
                        # Calculate indicator
                        start_time = time.time()
                        result = await self.calculator.calculate_indicator(calc_config)
                        calculation_time = (time.time() - start_time) * 1000
                        
                        # Store result in database
                        await self._store_calculation_result(result, config_dict)
                        
                        # Update calculation statistics
                        await self.database.update_calculation_statistics(
                            config_dict['id'],
                            config_dict['strategy_id'],
                            calculation_time,
                            success=True
                        )
                        
                        # Publish result if enabled
                        if config_dict.get('publish_to_rabbitmq', True):
                            await self._publish_result(result)
                        
                    except Exception as e:
                        logger.error("Error processing configuration in background", 
                                   config_id=config_dict.get('id'), error=str(e))
                        
                        # Update error statistics
                        await self.database.update_calculation_statistics(
                            config_dict['id'],
                            config_dict['strategy_id'],
                            0,
                            success=False,
                            error_message=str(e)
                        )
                
                # Wait for next cycle
                await asyncio.sleep(self.update_interval)
                
            except asyncio.CancelledError:
                logger.info("Background processor cancelled")
                break
            except Exception as e:
                logger.error("Error in background processor", error=str(e))
                await asyncio.sleep(10)  # Wait before retry
    
    def _db_config_to_indicator_config(self, db_config: Dict[str, Any]) -> IndicatorConfiguration:
        """Convert database configuration to IndicatorConfiguration for calculation"""
        # Convert parameters dict back to list format
        parameters = [
            {
                "name": name,
                "value": value,
                "data_type": "int" if isinstance(value, int) else "float" if isinstance(value, float) else "string"
            }
            for name, value in db_config.get('parameters', {}).items()
        ]
        
        return IndicatorConfiguration(
            id=db_config['id'],
            indicator_type=db_config['indicator_type'],
            parameters=parameters,
            symbol=db_config['symbol'],
            interval=db_config['interval'],
            periods_required=db_config['periods_required'],
            output_fields=db_config['output_fields'],
            cache_duration_minutes=db_config.get('cache_duration_minutes', 5),
            strategy_id=db_config['strategy_id'],
            priority=db_config.get('priority', 1)
        )
    
    async def _store_calculation_result(self, result: IndicatorResult, config_dict: Dict[str, Any]):
        """Store calculation result in database"""
        try:
            db_result = IndicatorCalculationResult(
                id=f"{result.configuration_id}_{int(result.timestamp.timestamp())}_{uuid.uuid4().hex[:8]}",
                configuration_id=result.configuration_id,
                symbol=result.symbol,
                interval=result.interval,
                timestamp=result.timestamp,
                values=result.values,
                calculation_time_ms=result.calculation_time_ms,
                data_points_used=result.data_points_used,
                cache_hit=result.cache_hit,
                metadata=result.metadata
            )
            
            await self.database.store_indicator_result(db_result)
            
        except Exception as e:
            logger.error("Error storing calculation result", 
                        config_id=result.configuration_id, error=str(e))
    
    def get_status(self) -> Dict[str, Any]:
        """Get configuration manager status"""
        return {
            'cached_configurations': len(self.cached_configurations),
            'processing_task_running': self.processing_task is not None and not self.processing_task.done(),
            'refresh_task_running': self.refresh_task is not None and not self.refresh_task.done(),
            'update_interval_seconds': self.update_interval,
            'db_refresh_interval_seconds': self.db_refresh_interval,
            'last_db_refresh': self.last_db_refresh.isoformat() if self.last_db_refresh else None,
            'strategies': list(set(config.get('strategy_id') for config in self.cached_configurations.values()))
        }
    
    async def get_configuration_status(self, strategy_id: str) -> Dict[str, Any]:
        """Get status for a specific strategy's configurations from database"""
        try:
            # Get configurations from database
            configurations = await self.database.get_active_indicator_configurations(strategy_id)
            
            config_summary = []
            for config in configurations:
                config_summary.append({
                    'id': config['id'],
                    'indicator_type': config['indicator_type'],
                    'symbol': config['symbol'],
                    'interval': config['interval'],
                    'priority': config['priority'],
                    'active': config['active'],
                    'created_at': config['created_at'],
                    'updated_at': config['updated_at'],
                    'last_calculated': config.get('last_calculated'),
                    'calculation_count': config.get('calculation_count', 0),
                    'avg_calculation_time_ms': config.get('avg_calculation_time_ms', 0),
                    'error_count': config.get('error_count', 0)
                })
            
            return {
                'strategy_id': strategy_id,
                'configuration_count': len(configurations),
                'configurations': config_summary
            }
            
        except Exception as e:
            logger.error("Error getting configuration status", strategy_id=strategy_id, error=str(e))
            return {'error': str(e)}
    
    async def get_all_strategies(self) -> List[str]:
        """Get list of all strategies with active configurations"""
        try:
            configs = await self.database.get_active_indicator_configurations()
            strategies = list(set(config['strategy_id'] for config in configs))
            return strategies
        except Exception as e:
            logger.error("Error getting strategies list", error=str(e))
            return []