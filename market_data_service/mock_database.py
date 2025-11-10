"""
Development Database Mock for Market Data Service
Mock implementation that simulates Cosmos DB without requiring Azure authentication
"""

import asyncio
import uuid
from datetime import datetime
from typing import Optional, Dict, List, Any
import structlog

logger = structlog.get_logger()


class MockDatabase:
    """Mock database for development that simulates Cosmos DB operations"""
    
    def __init__(self):
        self.containers: Dict[str, List[Dict]] = {
            'market_data': [],
            'order_book': [],
            'trades': [],
            'symbols': [],
            'indicator_configs': [],
            'indicator_results': []
        }
        self.connected = False
        
    async def connect(self):
        """Mock connection - always succeeds"""
        logger.info("Connected to mock database for development")
        self.connected = True
        return True
        
    async def disconnect(self):
        """Mock disconnection"""
        logger.info("Disconnected from mock database")
        self.connected = False
        
    async def create_market_data(self, market_data: dict) -> dict:
        """Mock market data creation"""
        market_data['id'] = str(uuid.uuid4())
        market_data['_ts'] = datetime.utcnow().timestamp()
        self.containers['market_data'].append(market_data)
        logger.info("Created mock market data", symbol=market_data.get('symbol'))
        return market_data
        
    async def get_latest_market_data(self, symbol: str, limit: int = 100) -> List[dict]:
        """Mock get latest market data"""
        # Filter by symbol and return latest entries
        symbol_data = [d for d in self.containers['market_data'] if d.get('symbol') == symbol]
        # Sort by timestamp descending and limit
        symbol_data.sort(key=lambda x: x.get('_ts', 0), reverse=True)
        return symbol_data[:limit]
        
    async def create_order_book(self, order_book_data: dict) -> dict:
        """Mock order book creation"""
        order_book_data['id'] = str(uuid.uuid4())
        order_book_data['_ts'] = datetime.utcnow().timestamp()
        self.containers['order_book'].append(order_book_data)
        return order_book_data
        
    async def create_trade(self, trade_data: dict) -> dict:
        """Mock trade creation"""
        trade_data['id'] = str(uuid.uuid4())
        trade_data['_ts'] = datetime.utcnow().timestamp()
        self.containers['trades'].append(trade_data)
        return trade_data
        
    async def ensure_symbol_tracking(self, symbol: str, symbol_data: dict = None) -> dict:
        """Mock symbol tracking"""
        existing_symbol = next((s for s in self.containers['symbols'] if s.get('symbol') == symbol), None)
        if existing_symbol:
            return existing_symbol
            
        new_symbol = {
            'id': str(uuid.uuid4()),
            'symbol': symbol,
            'is_active': True,
            'created_at': datetime.utcnow().isoformat(),
            '_ts': datetime.utcnow().timestamp()
        }
        if symbol_data:
            new_symbol.update(symbol_data)
        
        self.containers['symbols'].append(new_symbol)
        logger.info("Created mock symbol tracking", symbol=symbol)
        return new_symbol
        
    async def get_all_active_symbols(self) -> List[dict]:
        """Mock get all active symbols"""
        return [s for s in self.containers['symbols'] if s.get('is_active', True)]
        
    async def create_indicator_config(self, config: dict) -> dict:
        """Mock indicator config creation"""
        config['id'] = str(uuid.uuid4())
        config['_ts'] = datetime.utcnow().timestamp()
        self.containers['indicator_configs'].append(config)
        return config
        
    async def get_indicator_configs(self, symbol: str = None) -> List[dict]:
        """Mock get indicator configs"""
        if symbol:
            return [c for c in self.containers['indicator_configs'] if c.get('symbol') == symbol]
        return self.containers['indicator_configs']
        
    async def create_indicator_result(self, result: dict) -> dict:
        """Mock indicator result creation"""
        result['id'] = str(uuid.uuid4())
        result['_ts'] = datetime.utcnow().timestamp()
        self.containers['indicator_results'].append(result)
        return result
        
    async def get_dashboard_overview(self) -> dict:
        """Mock dashboard overview"""
        return {
            'total_symbols': len(self.containers['symbols']),
            'active_symbols': len([s for s in self.containers['symbols'] if s.get('is_active', True)]),
            'recent_market_data': len(self.containers['market_data']),
            'recent_trades': len(self.containers['trades']),
            'last_updated': datetime.utcnow().isoformat()
        }
        
    async def get_market_data_stats(self) -> dict:
        """Mock market data stats"""
        return {
            'total_records': len(self.containers['market_data']),
            'symbols_tracked': len(set(d.get('symbol') for d in self.containers['market_data'])),
            'last_update': datetime.utcnow().isoformat()
        }
        
    async def initialize_default_stock_indices(self):
        """Mock initialize stock indices"""
        logger.info("Mock stock indices initialized")
        
    async def get_tracked_symbols(self, asset_type=None, exchange=None):
        """Mock get tracked symbols"""
        # Filter symbols by criteria
        filtered_symbols = []
        for symbol in self.containers['symbols']:
            if asset_type and symbol.get('asset_type') != asset_type:
                continue
            if exchange and symbol.get('exchange') != exchange:
                continue
            if symbol.get('is_active', True):
                filtered_symbols.append(symbol)
        return filtered_symbols
        
    async def get_tracked_stock_indices(self):
        """Mock get tracked stock indices"""
        return []
        
    async def initialize_default_symbols(self):
        """Mock initialize default symbols"""
        logger.info("Mock default symbols initialized")


# Database instance for the service
database = MockDatabase()