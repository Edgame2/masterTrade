"""
RabbitMQ Integration for Risk Management

This module provides message queue integration for real-time risk checks,
position approvals, and risk alerts to other services in the MasterTrade system.
"""

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, asdict
import aio_pika
from aio_pika import Message, DeliveryMode
import structlog

from config import settings
from database import RiskPostgresDatabase
from position_sizing import PositionSizingEngine, PositionSizeRequest, PositionSizeResult
from stop_loss_manager import StopLossManager, StopLossConfig, StopLossType
from portfolio_risk_controller import PortfolioRiskController

logger = structlog.get_logger()

@dataclass
class RiskCheckRequest:
    """Risk check request message"""
    request_id: str
    symbol: str
    strategy_id: str
    order_type: str  # order execution type (market, limit)
    order_side: str  # 'BUY', 'SELL'
    quantity: float
    price: float
    signal_strength: float
    timestamp: datetime
    metadata: Dict = None

@dataclass
class RiskCheckResponse:
    """Risk check response message"""
    request_id: str
    approved: bool
    recommended_quantity: float
    max_loss_usd: float
    confidence_score: float
    risk_factors: Dict[str, float]
    warnings: List[str]
    stop_loss_price: Optional[float]
    reason: str
    timestamp: datetime
    price_prediction: Optional[Dict] = None

@dataclass
class RiskAlert:
    """Risk alert message"""
    alert_id: str
    alert_type: str
    severity: str
    title: str
    message: str
    symbol: Optional[str]
    current_value: float
    threshold_value: float
    recommendation: str
    timestamp: datetime

@dataclass
class PortfolioUpdate:
    """Portfolio update message"""
    update_id: str
    portfolio_value: float
    total_exposure: float
    leverage_ratio: float
    var_1d: float
    current_drawdown: float
    risk_score: float
    risk_level: str
    timestamp: datetime

class RiskMessageHandler:
    """
    Message queue handler for risk management communications
    
    Handles:
    - Real-time risk check requests from strategy services
    - Position approval/rejection responses
    - Risk alerts to monitoring services
    - Portfolio updates to management interfaces
    - Stop-loss triggers to order execution service
    """
    
    def __init__(
        self,
        database: RiskPostgresDatabase,
        position_sizing_engine: PositionSizingEngine,
        stop_loss_manager: StopLossManager,
        portfolio_controller: PortfolioRiskController
    ):
        self.database = database
        self.position_sizing_engine = position_sizing_engine
        self.stop_loss_manager = stop_loss_manager
        self.portfolio_controller = portfolio_controller
        
        self.connection = None
        self.channel = None
        self.exchanges = {}
        self.queues = {}
        self.running = False
        
    async def initialize(self):
        """Initialize RabbitMQ connection and declare exchanges/queues"""
        try:
            logger.info("Initializing RabbitMQ connection for risk management")
            
            # Establish connection using URL
            self.connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
            
            # Create channel
            self.channel = await self.connection.channel()
            await self.channel.set_qos(prefetch_count=100)
            
            # Declare exchanges
            await self._declare_exchanges()
            
            # Declare queues
            await self._declare_queues()
            
            # Set up consumers
            await self._setup_consumers()
            
            logger.info("RabbitMQ connection initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize RabbitMQ connection: {e}")
            raise
    
    async def _declare_exchanges(self):
        """Declare RabbitMQ exchanges"""
        try:
            # Risk check exchange for position approval requests
            self.exchanges['risk_check'] = await self.channel.declare_exchange(
                'risk.check',
                aio_pika.ExchangeType.DIRECT,
                durable=True
            )
            
            # Risk alerts exchange for broadcasting alerts
            self.exchanges['risk_alerts'] = await self.channel.declare_exchange(
                'risk.alerts',
                aio_pika.ExchangeType.FANOUT,
                durable=True
            )
            
            # Portfolio updates exchange
            self.exchanges['portfolio_updates'] = await self.channel.declare_exchange(
                'portfolio.updates',
                aio_pika.ExchangeType.TOPIC,
                durable=True
            )
            
            # Order execution exchange for stop-loss triggers
            self.exchanges['order_execution'] = await self.channel.declare_exchange(
                'order.execution',
                aio_pika.ExchangeType.DIRECT,
                durable=True
            )
            
            logger.info("RabbitMQ exchanges declared successfully")
            
        except Exception as e:
            logger.error(f"Failed to declare exchanges: {e}")
            raise
    
    async def _declare_queues(self):
        """Declare RabbitMQ queues"""
        try:
            # Risk check request queue
            self.queues['risk_check_requests'] = await self.channel.declare_queue(
                'risk.check.requests',
                durable=True
            )
            
            # Risk check response queue (for strategy services)
            self.queues['risk_check_responses'] = await self.channel.declare_queue(
                'risk.check.responses',
                durable=True
            )
            
            # Price update queue for real-time risk monitoring
            self.queues['price_updates'] = await self.channel.declare_queue(
                'market.price.updates',
                durable=True
            )
            
            # Position updates queue for portfolio tracking
            self.queues['position_updates'] = await self.channel.declare_queue(
                'portfolio.position.updates',
                durable=True
            )
            
            # Bind queues to exchanges
            await self.queues['risk_check_requests'].bind(
                self.exchanges['risk_check'], 
                routing_key='risk.check.request'
            )
            
            await self.queues['price_updates'].bind(
                self.exchanges['portfolio_updates'],
                routing_key='market.price.*'
            )
            
            await self.queues['position_updates'].bind(
                self.exchanges['portfolio_updates'],
                routing_key='portfolio.position.*'
            )
            
            logger.info("RabbitMQ queues declared and bound successfully")
            
        except Exception as e:
            logger.error(f"Failed to declare queues: {e}")
            raise
    
    async def _setup_consumers(self):
        """Set up message consumers"""
        try:
            # Risk check request consumer
            await self.queues['risk_check_requests'].consume(
                self._handle_risk_check_request,
                no_ack=False
            )
            
            # Price update consumer
            await self.queues['price_updates'].consume(
                self._handle_price_update,
                no_ack=False
            )
            
            # Position update consumer
            await self.queues['position_updates'].consume(
                self._handle_position_update,
                no_ack=False
            )
            
            self.running = True
            logger.info("Message consumers set up successfully")
            
        except Exception as e:
            logger.error(f"Failed to set up consumers: {e}")
            raise
    
    async def _handle_risk_check_request(self, message: aio_pika.Message):
        """Handle incoming risk check requests"""
        try:
            async with message.process():
                # Parse request
                request_data = json.loads(message.body.decode())
                request = RiskCheckRequest(
                    request_id=request_data['request_id'],
                    symbol=request_data['symbol'],
                    strategy_id=request_data['strategy_id'],
                    order_type=request_data['order_type'],
                    order_side=(request_data.get('side') or request_data.get('order_side', 'BUY')).upper(),
                    quantity=request_data['quantity'],
                    price=request_data['price'],
                    signal_strength=request_data.get('signal_strength', 1.0),
                    timestamp=datetime.fromisoformat(request_data['timestamp']),
                    metadata=request_data.get('metadata', {})
                )
                
                logger.info(
                    f"Processing risk check request for {request.symbol}",
                    request_id=request.request_id,
                    strategy_id=request.strategy_id,
                    order_type=request.order_type
                )
                
                # Perform risk check
                response = await self._perform_risk_check(request)
                
                # Send response
                await self._send_risk_check_response(response)
                
                logger.info(
                    f"Risk check completed for {request.symbol}",
                    request_id=request.request_id,
                    approved=response.approved
                )
                
        except Exception as e:
            logger.error(f"Error handling risk check request: {e}")
            # Send error response if possible
            try:
                request_data = json.loads(message.body.decode())
                error_response = RiskCheckResponse(
                    request_id=request_data.get('request_id', 'unknown'),
                    approved=False,
                    recommended_quantity=0.0,
                    max_loss_usd=0.0,
                    confidence_score=0.0,
                    risk_factors={'error': 10.0},
                    warnings=[f"Risk check error: {str(e)}"],
                    stop_loss_price=None,
                    reason=f"Risk check failed: {str(e)}",
                    timestamp=datetime.now(timezone.utc),
                    price_prediction=None
                )
                await self._send_risk_check_response(error_response)
            except:
                pass  # If we can't send error response, log and continue
    
    async def _perform_risk_check(self, request: RiskCheckRequest) -> RiskCheckResponse:
        """Perform comprehensive risk check for position request"""
        try:
            # Create position sizing request
            size_request = PositionSizeRequest(
                symbol=request.symbol,
                strategy_id=request.strategy_id,
                signal_strength=request.signal_strength,
                current_price=request.price,
                volatility=None,  # Will be fetched from database
                stop_loss_percent=None,  # Will be calculated
                risk_per_trade_percent=None,  # Will use default
                order_side=request.order_side
            )
            
            # Calculate position size
            size_result = await self.position_sizing_engine.calculate_position_size(size_request)
            
            # Check if requested quantity exceeds recommendation
            requested_size_usd = request.quantity * request.price
            approved_quantity = request.quantity
            
            if requested_size_usd > size_result.recommended_size_usd:
                # Reduce quantity to recommended size
                approved_quantity = size_result.recommended_quantity
                
                # Add warning about quantity reduction
                size_result.warnings.append(
                    f"Quantity reduced from {request.quantity:.6f} to {approved_quantity:.6f}"
                )
            
            # Additional risk checks for sell orders
            if request.order_side.lower() == 'sell':
                # Check if we have sufficient position
                current_positions = await self.database.get_current_positions()
                position = next(
                    (p for p in current_positions if p['symbol'] == request.symbol), 
                    None
                )
                
                if not position or position['quantity'] < approved_quantity:
                    size_result.approved = False
                    size_result.warnings.append("Insufficient position for sell order")
            
            # Create response
            response = RiskCheckResponse(
                request_id=request.request_id,
                approved=size_result.approved,
                recommended_quantity=approved_quantity,
                max_loss_usd=size_result.max_loss_usd,
                confidence_score=size_result.confidence_score,
                risk_factors=size_result.risk_factors,
                warnings=size_result.warnings,
                stop_loss_price=size_result.stop_loss_price,
                reason="Risk check completed" if size_result.approved else "Risk limits exceeded",
                timestamp=datetime.now(timezone.utc),
                price_prediction=size_result.price_prediction
            )
            
            return response
            
        except Exception as e:
            logger.error(f"Error performing risk check: {e}")
            return RiskCheckResponse(
                request_id=request.request_id,
                approved=False,
                recommended_quantity=0.0,
                max_loss_usd=0.0,
                confidence_score=0.0,
                risk_factors={'error': 10.0},
                warnings=[f"Risk check error: {str(e)}"],
                stop_loss_price=None,
                reason=f"Risk check failed: {str(e)}",
                timestamp=datetime.now(timezone.utc),
                price_prediction=None
            )
    
    async def _send_risk_check_response(self, response: RiskCheckResponse):
        """Send risk check response back to requesting service"""
        try:
            message_body = json.dumps(asdict(response), default=str)
            
            message = Message(
                message_body.encode(),
                delivery_mode=DeliveryMode.PERSISTENT,
                correlation_id=response.request_id,
                timestamp=datetime.now(timezone.utc)
            )
            
            await self.exchanges['risk_check'].publish(
                message,
                routing_key='risk.check.response'
            )
            
        except Exception as e:
            logger.error(f"Error sending risk check response: {e}")
            raise
    
    async def _handle_price_update(self, message: aio_pika.Message):
        """Handle real-time price updates"""
        try:
            async with message.process():
                # Parse price update
                price_data = json.loads(message.body.decode())
                
                # Update stop-loss orders
                await self.stop_loss_manager.update_stop_losses(price_data)
                
                # Check for stop-loss triggers
                triggered_orders = await self.stop_loss_manager.check_stop_triggers(price_data)
                
                # Send stop-loss trigger notifications
                for order in triggered_orders:
                    await self._send_stop_loss_trigger(order)
                
                # Update portfolio risk monitoring
                risk_summary = await self.portfolio_controller.monitor_real_time_risk(price_data)
                
                # Send portfolio update
                if 'portfolio_value' in risk_summary:
                    portfolio_update = PortfolioUpdate(
                        update_id=str(uuid.uuid4()),
                        portfolio_value=risk_summary['portfolio_value'],
                        total_exposure=risk_summary.get('total_exposure', 0),
                        leverage_ratio=risk_summary['leverage'],
                        var_1d=risk_summary['var_estimate'],
                        current_drawdown=risk_summary['drawdown'],
                        risk_score=risk_summary.get('risk_score', 50),
                        risk_level=risk_summary['risk_status'],
                        timestamp=datetime.now(timezone.utc)
                    )
                    
                    await self._send_portfolio_update(portfolio_update)
                
                # Send risk alerts for breaches
                for breach in risk_summary.get('breaches', []):
                    alert = RiskAlert(
                        alert_id=str(uuid.uuid4()),
                        alert_type=breach['type'],
                        severity='HIGH',
                        title=f"{breach['type'].title()} Limit Exceeded",
                        message=f"{breach['type'].title()} ({breach['current']:.2f}) exceeds limit ({breach['limit']:.2f})",
                        symbol=None,
                        current_value=breach['current'],
                        threshold_value=breach['limit'],
                        recommendation="Immediate position adjustment required",
                        timestamp=datetime.now(timezone.utc)
                    )
                    
                    await self._send_risk_alert(alert)
                
        except Exception as e:
            logger.error(f"Error handling price update: {e}")
    
    async def _handle_position_update(self, message: aio_pika.Message):
        """Handle position updates from portfolio service"""
        try:
            async with message.process():
                # Parse position update
                position_data = json.loads(message.body.decode())
                
                logger.info(
                    f"Received position update for {position_data.get('symbol', 'unknown')}",
                    update_type=position_data.get('update_type', 'unknown')
                )
                
                # Update internal position tracking
                await self.database.update_position_from_message(position_data)
                
                # Trigger portfolio risk recalculation
                risk_metrics = await self.portfolio_controller.calculate_portfolio_risk()
                
                # Check for new risk alerts
                alerts = await self.portfolio_controller.check_risk_limits()
                
                # Send new alerts
                for alert in alerts:
                    risk_alert = RiskAlert(
                        alert_id=alert.id,
                        alert_type=alert.alert_type.value,
                        severity=alert.severity.value,
                        title=alert.title,
                        message=alert.message,
                        symbol=alert.symbol,
                        current_value=alert.current_value,
                        threshold_value=alert.threshold_value,
                        recommendation=alert.recommendation,
                        timestamp=alert.created_at
                    )
                    
                    await self._send_risk_alert(risk_alert)
                
        except Exception as e:
            logger.error(f"Error handling position update: {e}")
    
    async def _send_stop_loss_trigger(self, order):
        """Send stop-loss trigger notification to order execution service"""
        try:
            trigger_data = {
                'order_id': order.id,
                'position_id': order.position_id,
                'symbol': order.symbol,
                'order_type': 'market_sell',
                'quantity': order.quantity,
                'trigger_price': order.current_price,
                'stop_price': order.stop_price,
                'reason': 'stop_loss_triggered',
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
            
            message_body = json.dumps(trigger_data)
            
            message = Message(
                message_body.encode(),
                delivery_mode=DeliveryMode.PERSISTENT,
                priority=9,  # High priority for stop-loss orders
                timestamp=datetime.now(timezone.utc)
            )
            
            await self.exchanges['order_execution'].publish(
                message,
                routing_key='order.stop_loss.trigger'
            )
            
            logger.warning(
                f"Stop-loss trigger sent to order execution",
                order_id=order.id,
                symbol=order.symbol,
                trigger_price=order.current_price
            )
            
        except Exception as e:
            logger.error(f"Error sending stop-loss trigger: {e}")
    
    async def _send_risk_alert(self, alert: RiskAlert):
        """Send risk alert to monitoring services"""
        try:
            message_body = json.dumps(asdict(alert), default=str)
            
            message = Message(
                message_body.encode(),
                delivery_mode=DeliveryMode.PERSISTENT,
                timestamp=datetime.now(timezone.utc)
            )
            
            await self.exchanges['risk_alerts'].publish(message, routing_key='')
            
            logger.warning(
                f"Risk alert sent: {alert.title}",
                alert_id=alert.alert_id,
                severity=alert.severity,
                symbol=alert.symbol
            )
            
        except Exception as e:
            logger.error(f"Error sending risk alert: {e}")
    
    async def _send_portfolio_update(self, update: PortfolioUpdate):
        """Send portfolio update to management interfaces"""
        try:
            message_body = json.dumps(asdict(update), default=str)
            
            message = Message(
                message_body.encode(),
                delivery_mode=DeliveryMode.NOT_PERSISTENT,  # Portfolio updates don't need persistence
                timestamp=datetime.now(timezone.utc)
            )
            
            await self.exchanges['portfolio_updates'].publish(
                message,
                routing_key=f'portfolio.risk.update'
            )
            
        except Exception as e:
            logger.error(f"Error sending portfolio update: {e}")
    
    # Public methods for sending messages from other parts of the system
    
    async def send_risk_check_request(
        self, 
        symbol: str, 
        strategy_id: str, 
        order_type: str,
        quantity: float, 
        price: float,
        signal_strength: float = 1.0,
        metadata: Dict = None
    ) -> str:
        """Send risk check request and return request ID"""
        try:
            request_id = str(uuid.uuid4())
            
            request = RiskCheckRequest(
                request_id=request_id,
                symbol=symbol,
                strategy_id=strategy_id,
                order_type=order_type,
                quantity=quantity,
                price=price,
                signal_strength=signal_strength,
                timestamp=datetime.now(timezone.utc),
                metadata=metadata or {}
            )
            
            message_body = json.dumps(asdict(request), default=str)
            
            message = Message(
                message_body.encode(),
                delivery_mode=DeliveryMode.PERSISTENT,
                correlation_id=request_id,
                timestamp=datetime.now(timezone.utc)
            )
            
            await self.exchanges['risk_check'].publish(
                message,
                routing_key='risk.check.request'
            )
            
            return request_id
            
        except Exception as e:
            logger.error(f"Error sending risk check request: {e}")
            raise
    
    async def broadcast_portfolio_alert(
        self,
        alert_type: str,
        severity: str,
        title: str,
        message: str,
        symbol: str = None,
        recommendation: str = None
    ):
        """Broadcast portfolio risk alert"""
        try:
            alert = RiskAlert(
                alert_id=str(uuid.uuid4()),
                alert_type=alert_type,
                severity=severity,
                title=title,
                message=message,
                symbol=symbol,
                current_value=0.0,
                threshold_value=0.0,
                recommendation=recommendation or "Review portfolio risk",
                timestamp=datetime.now(timezone.utc)
            )
            
            await self._send_risk_alert(alert)
            
        except Exception as e:
            logger.error(f"Error broadcasting portfolio alert: {e}")
    
    async def close(self):
        """Close RabbitMQ connection"""
        try:
            self.running = False
            if self.connection and not self.connection.is_closed:
                await self.connection.close()
            logger.info("RabbitMQ connection closed")
            
        except Exception as e:
            logger.error(f"Error closing RabbitMQ connection: {e}")
    
    def is_running(self) -> bool:
        """Check if message handler is running"""
        return self.running and self.connection and not self.connection.is_closed