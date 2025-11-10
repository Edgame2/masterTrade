"""
Mock Database for Order Executor Development
Provides mock implementation of Cosmos DB operations for local development
"""

import asyncio
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List, Any
import structlog

logger = structlog.get_logger()


class MockDatabase:
    """Mock database for development that simulates Cosmos DB operations"""
    
    def __init__(self):
        self.containers: Dict[str, List[Dict]] = {
            'orders': [],
            'trades': [],
            'positions': [],
            'order_history': [],
            'execution_log': []
        }
        self.connected = False
        
    async def connect(self):
        """Mock connection - always succeeds"""
        logger.info("Connected to mock order executor database for development")
        self.connected = True
        return True
        
    async def disconnect(self):
        """Mock disconnection"""
        logger.info("Disconnected from mock order executor database")
        self.connected = False
        
    # Order operations
    async def create_order(self, order_data: dict) -> dict:
        """Mock order creation"""
        order_data['id'] = str(uuid.uuid4())
        order_data['created_at'] = datetime.now(timezone.utc).isoformat()
        order_data['status'] = 'pending'
        order_data['_ts'] = datetime.utcnow().timestamp()
        self.containers['orders'].append(order_data)
        logger.info("Created mock order", order_id=order_data['id'])
        return order_data
        
    async def get_order(self, order_id: str) -> Optional[dict]:
        """Mock get order by ID"""
        for order in self.containers['orders']:
            if order.get('id') == order_id:
                return order
        return None
        
    async def get_orders(self, **filters) -> List[dict]:
        """Mock get orders with filters"""
        orders = self.containers['orders'].copy()
        
        # Apply filters
        if 'status' in filters:
            orders = [o for o in orders if o.get('status') == filters['status']]
        if 'symbol' in filters:
            orders = [o for o in orders if o.get('symbol') == filters['symbol']]
        if 'strategy_id' in filters:
            orders = [o for o in orders if o.get('strategy_id') == filters['strategy_id']]
            
        return orders
        
    async def update_order(self, order_id: str, updates: dict) -> dict:
        """Mock order update"""
        for i, order in enumerate(self.containers['orders']):
            if order.get('id') == order_id:
                order.update(updates)
                order['updated_at'] = datetime.now(timezone.utc).isoformat()
                self.containers['orders'][i] = order
                return order
        raise ValueError(f"Order {order_id} not found")
        
    async def update_order_from_exchange(self, order_id: str, exchange_data: dict) -> dict:
        """Mock update order from exchange data"""
        updates = {
            'status': exchange_data.get('status', 'unknown'),
            'filled_quantity': exchange_data.get('filled', 0),
            'average_price': exchange_data.get('average', 0),
            'fee': exchange_data.get('fee', {}),
            'last_trade_timestamp': exchange_data.get('lastTradeTimestamp')
        }
        return await self.update_order(order_id, updates)
        
    async def get_active_orders(self, strategy_id: str = None) -> List[dict]:
        """Mock get active orders"""
        active_statuses = ['pending', 'open', 'partially_filled']
        orders = [o for o in self.containers['orders'] if o.get('status') in active_statuses]
        
        if strategy_id:
            orders = [o for o in orders if o.get('strategy_id') == strategy_id]
            
        return orders
        
    # Trade operations
    async def create_trade(self, trade_data: dict) -> dict:
        """Mock trade creation"""
        trade_data['id'] = str(uuid.uuid4())
        trade_data['timestamp'] = datetime.now(timezone.utc).isoformat()
        trade_data['_ts'] = datetime.utcnow().timestamp()
        self.containers['trades'].append(trade_data)
        logger.info("Created mock trade", trade_id=trade_data['id'])
        return trade_data
        
    async def get_trades(self, order_id: str = None, limit: int = 100) -> List[dict]:
        """Mock get trades"""
        trades = self.containers['trades'].copy()
        if order_id:
            trades = [t for t in trades if t.get('order_id') == order_id]
        trades.sort(key=lambda x: x.get('_ts', 0), reverse=True)
        return trades[:limit]
        
    # Position operations
    async def create_position(self, position_data: dict) -> dict:
        """Mock position creation"""
        position_data['id'] = str(uuid.uuid4())
        position_data['opened_at'] = datetime.now(timezone.utc).isoformat()
        position_data['_ts'] = datetime.utcnow().timestamp()
        self.containers['positions'].append(position_data)
        return position_data
        
    async def update_position(self, position_id: str, updates: dict) -> dict:
        """Mock position update"""
        for i, position in enumerate(self.containers['positions']):
            if position.get('id') == position_id:
                position.update(updates)
                position['updated_at'] = datetime.now(timezone.utc).isoformat()
                self.containers['positions'][i] = position
                return position
        raise ValueError(f"Position {position_id} not found")
        
    async def get_positions(self, strategy_id: str = None, is_open: bool = None) -> List[dict]:
        """Mock get positions"""
        positions = self.containers['positions'].copy()
        
        if strategy_id:
            positions = [p for p in positions if p.get('strategy_id') == strategy_id]
        if is_open is not None:
            positions = [p for p in positions if p.get('is_open') == is_open]
            
        return positions
        
    # Execution log operations
    async def log_execution(self, log_data: dict) -> dict:
        """Mock execution log"""
        log_data['id'] = str(uuid.uuid4())
        log_data['timestamp'] = datetime.now(timezone.utc).isoformat()
        log_data['_ts'] = datetime.utcnow().timestamp()
        self.containers['execution_log'].append(log_data)
        return log_data
        
    async def get_execution_logs(self, order_id: str = None, limit: int = 100) -> List[dict]:
        """Mock get execution logs"""
        logs = self.containers['execution_log'].copy()
        if order_id:
            logs = [l for l in logs if l.get('order_id') == order_id]
        logs.sort(key=lambda x: x.get('_ts', 0), reverse=True)
        return logs[:limit]
        
    # Dashboard and stats
    async def get_order_executor_dashboard(self) -> dict:
        """Mock dashboard data"""
        return {
            'total_orders': len(self.containers['orders']),
            'active_orders': len([o for o in self.containers['orders'] if o.get('status') in ['pending', 'open']]),
            'completed_orders': len([o for o in self.containers['orders'] if o.get('status') == 'filled']),
            'total_trades': len(self.containers['trades']),
            'active_positions': len([p for p in self.containers['positions'] if p.get('is_open', True)]),
            'last_updated': datetime.now(timezone.utc).isoformat()
        }
        
    async def get_execution_stats(self) -> dict:
        """Mock execution statistics"""
        orders = self.containers['orders']
        total_orders = len(orders)
        successful_orders = len([o for o in orders if o.get('status') == 'filled'])
        
        return {
            'total_orders': total_orders,
            'successful_orders': successful_orders,
            'success_rate': successful_orders / max(total_orders, 1),
            'average_execution_time': 2.5,  # Mock average in seconds
            'total_volume': sum(float(o.get('quantity', 0)) for o in orders),
            'last_update': datetime.now(timezone.utc).isoformat()
        }
        
    # Health status
    async def get_health_status(self) -> dict:
        """Mock health status"""
        return {
            'status': 'healthy',
            'database': 'mock',
            'containers': list(self.containers.keys()),
            'total_records': sum(len(container) for container in self.containers.values()),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }


# Database instance for the service
Database = MockDatabase