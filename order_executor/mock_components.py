"""
Mock components for Order Executor development
"""
import structlog

logger = structlog.get_logger()


class ExchangeManager:
    """Mock exchange manager for development"""
    
    def __init__(self):
        self.exchanges = {}
        self.connected = False
        
    async def initialize(self):
        """Mock initialization"""
        logger.info("Mock exchange manager initialized")
        self.connected = True
        
    async def close(self):
        """Mock close"""
        logger.info("Mock exchange manager closed")
        self.connected = False
        
    def get_exchange(self, environment: str = 'testnet'):
        """Get mock exchange"""
        return MockExchange(environment)
        
    async def create_order(self, environment: str, symbol: str, order_type: str, 
                          side: str, quantity: float, price: float = None, **kwargs):
        """Mock order creation"""
        import uuid
        import random
        
        order_id = f"mock_order_{uuid.uuid4().hex[:8]}"
        
        # Simulate some randomness in order execution
        status = random.choice(['open', 'filled', 'partially_filled'])
        filled = quantity if status == 'filled' else (quantity * 0.5 if status == 'partially_filled' else 0)
        
        return {
            'id': order_id,
            'symbol': symbol,
            'type': order_type,
            'side': side,
            'amount': quantity,
            'price': price or 50000.0,  # Mock price
            'status': status,
            'filled': filled,
            'remaining': quantity - filled,
            'fee': {'cost': 0.001 * quantity, 'currency': 'USDT'},
            'timestamp': 1699401600000,  # Mock timestamp
            'datetime': '2025-11-07T19:50:00.000Z'
        }
        
    async def fetch_order(self, order_id: str, symbol: str):
        """Mock fetch order"""
        import random
        
        # Simulate order status updates
        statuses = ['open', 'filled', 'partially_filled', 'canceled']
        status = random.choice(statuses)
        
        return {
            'id': order_id,
            'symbol': symbol,
            'status': status,
            'filled': 1.0 if status == 'filled' else (0.5 if status == 'partially_filled' else 0),
            'average': 50000.0 + random.uniform(-1000, 1000),  # Mock average price
            'fee': {'cost': 0.001, 'currency': 'USDT'},
            'lastTradeTimestamp': 1699401600000
        }


class MockExchange:
    """Mock exchange for testing"""
    
    def __init__(self, environment: str = 'testnet'):
        self.environment = environment
        self.id = 'binance'
        
    async def fetch_order(self, order_id: str, symbol: str):
        """Mock fetch order from exchange"""
        import random
        
        return {
            'id': order_id,
            'symbol': symbol,
            'status': random.choice(['open', 'filled', 'partially_filled']),
            'filled': random.uniform(0, 1),
            'average': 50000.0,
            'fee': {'cost': 0.001, 'currency': 'USDT'},
            'lastTradeTimestamp': 1699401600000
        }


class EnvironmentConfigManager:
    """Mock environment config manager"""
    
    def __init__(self):
        self.configs = {
            'testnet': {'api_key': 'test_key', 'secret': 'test_secret', 'sandbox': True},
            'production': {'api_key': 'prod_key', 'secret': 'prod_secret', 'sandbox': False}
        }
        
    def get_config(self, environment: str) -> dict:
        """Get configuration for environment"""
        return self.configs.get(environment, self.configs['testnet'])
        
    def get_available_environments(self) -> list:
        """Get list of available environments"""
        return list(self.configs.keys())


class OrderManager:
    """Mock order manager"""
    
    def __init__(self):
        self.initialized = False
        
    async def initialize(self, database, exchange_manager):
        """Mock initialization"""
        self.database = database
        self.exchange_manager = exchange_manager
        self.initialized = True
        logger.info("Mock order manager initialized")
        
    async def process_order(self, order_data: dict):
        """Mock order processing"""
        logger.info("Mock processing order", order_id=order_data.get('id', 'unknown'))
        return {"status": "processed", "message": "Order processed successfully"}
        
    async def cancel_order(self, order_id: str):
        """Mock order cancellation"""
        logger.info("Mock canceling order", order_id=order_id)
        return {"status": "canceled", "order_id": order_id}


# Mock models if not available
class Order:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

class Signal:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

class Trade:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

class OrderRequest:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)