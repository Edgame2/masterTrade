"""
Mock Database for Strategy Service Development
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
            'strategies': [],
            'signals': [],
            'strategy_results': [],
            'strategy_configs': [],
            'positions': [],
            'trades': [],
            'reviews': [],
            'crypto_analysis': [],
            'activations': []
        }
        self.connected = False
        
    async def connect(self):
        """Mock connection - always succeeds"""
        logger.info("Connected to mock strategy database for development")
        self.connected = True
        return True
        
    async def disconnect(self):
        """Mock disconnection"""
        logger.info("Disconnected from mock strategy database")
        self.connected = False
        
    # Strategy operations
    async def create_strategy(self, strategy_data: dict) -> dict:
        """Mock strategy creation"""
        strategy_data['id'] = str(uuid.uuid4())
        strategy_data['created_at'] = datetime.now(timezone.utc).isoformat()
        strategy_data['_ts'] = datetime.utcnow().timestamp()
        self.containers['strategies'].append(strategy_data)
        logger.info("Created mock strategy", strategy_id=strategy_data['id'])
        return strategy_data
        
    async def get_strategy(self, strategy_id: str) -> Optional[dict]:
        """Mock get strategy by ID"""
        for strategy in self.containers['strategies']:
            if strategy.get('id') == strategy_id:
                return strategy
        return None
        
    async def get_strategies(self, **filters) -> List[dict]:
        """Mock get strategies with filters"""
        strategies = self.containers['strategies'].copy()
        
        # Apply filters
        if 'is_active' in filters:
            strategies = [s for s in strategies if s.get('is_active') == filters['is_active']]
        if 'type' in filters:
            strategies = [s for s in strategies if s.get('type') == filters['type']]
            
        return strategies
        
    async def update_strategy(self, strategy_id: str, updates: dict) -> dict:
        """Mock strategy update"""
        for i, strategy in enumerate(self.containers['strategies']):
            if strategy.get('id') == strategy_id:
                strategy.update(updates)
                strategy['updated_at'] = datetime.now(timezone.utc).isoformat()
                self.containers['strategies'][i] = strategy
                return strategy
        raise ValueError(f"Strategy {strategy_id} not found")
        
    async def delete_strategy(self, strategy_id: str) -> bool:
        """Mock strategy deletion"""
        for i, strategy in enumerate(self.containers['strategies']):
            if strategy.get('id') == strategy_id:
                del self.containers['strategies'][i]
                logger.info("Deleted mock strategy", strategy_id=strategy_id)
                return True
        return False
        
    # Signal operations
    async def create_signal(self, signal_data: dict) -> dict:
        """Mock signal creation"""
        signal_data['id'] = str(uuid.uuid4())
        signal_data['timestamp'] = datetime.now(timezone.utc).isoformat()
        signal_data['_ts'] = datetime.utcnow().timestamp()
        self.containers['signals'].append(signal_data)
        return signal_data
        
    async def get_recent_signals(self, strategy_id: str = None, limit: int = 100) -> List[dict]:
        """Mock get recent signals"""
        signals = self.containers['signals'].copy()
        if strategy_id:
            signals = [s for s in signals if s.get('strategy_id') == strategy_id]
        # Sort by timestamp descending and limit
        signals.sort(key=lambda x: x.get('_ts', 0), reverse=True)
        return signals[:limit]
        
    # Strategy Results operations
    async def create_strategy_result(self, result_data: dict) -> dict:
        """Mock strategy result creation"""
        result_data['id'] = str(uuid.uuid4())
        result_data['timestamp'] = datetime.now(timezone.utc).isoformat()
        result_data['_ts'] = datetime.utcnow().timestamp()
        self.containers['strategy_results'].append(result_data)
        return result_data
        
    async def get_strategy_results(self, strategy_id: str = None, days: int = 30) -> List[dict]:
        """Mock get strategy results"""
        results = self.containers['strategy_results'].copy()
        if strategy_id:
            results = [r for r in results if r.get('strategy_id') == strategy_id]
        return results
        
    # Configuration operations
    async def create_strategy_config(self, config_data: dict) -> dict:
        """Mock strategy config creation"""
        config_data['id'] = str(uuid.uuid4())
        config_data['created_at'] = datetime.now(timezone.utc).isoformat()
        config_data['_ts'] = datetime.utcnow().timestamp()
        self.containers['strategy_configs'].append(config_data)
        return config_data
        
    async def get_strategy_configs(self, strategy_type: str = None) -> List[dict]:
        """Mock get strategy configs"""
        configs = self.containers['strategy_configs'].copy()
        if strategy_type:
            configs = [c for c in configs if c.get('strategy_type') == strategy_type]
        return configs
        
    # Dashboard operations
    async def get_strategy_dashboard_data(self) -> dict:
        """Mock strategy dashboard data"""
        return {
            'total_strategies': len(self.containers['strategies']),
            'active_strategies': len([s for s in self.containers['strategies'] if s.get('is_active', True)]),
            'recent_signals': len(self.containers['signals']),
            'strategy_results': len(self.containers['strategy_results']),
            'last_updated': datetime.now(timezone.utc).isoformat()
        }
        
    # Review operations (for daily review system)
    async def create_strategy_review(self, review_data: dict) -> dict:
        """Mock strategy review creation"""
        review_data['id'] = str(uuid.uuid4())
        review_data['review_date'] = datetime.now(timezone.utc).isoformat()
        review_data['_ts'] = datetime.utcnow().timestamp()
        self.containers['reviews'].append(review_data)
        return review_data
        
    async def get_strategy_reviews(self, days: int = 7) -> List[dict]:
        """Mock get strategy reviews"""
        return self.containers['reviews'][-days:] if len(self.containers['reviews']) > days else self.containers['reviews']
        
    # Crypto analysis operations
    async def create_crypto_analysis(self, analysis_data: dict) -> dict:
        """Mock crypto analysis creation"""
        analysis_data['id'] = str(uuid.uuid4())
        analysis_data['timestamp'] = datetime.now(timezone.utc).isoformat()
        analysis_data['_ts'] = datetime.utcnow().timestamp()
        self.containers['crypto_analysis'].append(analysis_data)
        return analysis_data
        
    async def get_crypto_analysis(self, symbol: str = None, limit: int = 100) -> List[dict]:
        """Mock get crypto analysis"""
        analysis = self.containers['crypto_analysis'].copy()
        if symbol:
            analysis = [a for a in analysis if a.get('symbol') == symbol]
        return analysis[:limit]
        
    # Strategy activation operations
    async def create_activation(self, activation_data: dict) -> dict:
        """Mock activation creation"""
        activation_data['id'] = str(uuid.uuid4())
        activation_data['timestamp'] = datetime.now(timezone.utc).isoformat()
        activation_data['_ts'] = datetime.utcnow().timestamp()
        self.containers['activations'].append(activation_data)
        return activation_data
        
    async def get_recent_activations(self, limit: int = 50) -> List[dict]:
        """Mock get recent activations"""
        return self.containers['activations'][-limit:] if len(self.containers['activations']) > limit else self.containers['activations']
        
    # Position and trade operations
    async def create_position(self, position_data: dict) -> dict:
        """Mock position creation"""
        position_data['id'] = str(uuid.uuid4())
        position_data['opened_at'] = datetime.now(timezone.utc).isoformat()
        position_data['_ts'] = datetime.utcnow().timestamp()
        self.containers['positions'].append(position_data)
        return position_data
        
    async def get_active_positions(self, strategy_id: str = None) -> List[dict]:
        """Mock get active positions"""
        positions = self.containers['positions'].copy()
        if strategy_id:
            positions = [p for p in positions if p.get('strategy_id') == strategy_id]
        return [p for p in positions if p.get('status') == 'open']
        
    async def create_trade(self, trade_data: dict) -> dict:
        """Mock trade creation"""
        trade_data['id'] = str(uuid.uuid4())
        trade_data['timestamp'] = datetime.now(timezone.utc).isoformat()
        trade_data['_ts'] = datetime.utcnow().timestamp()
        self.containers['trades'].append(trade_data)
        return trade_data
        
    async def get_recent_trades(self, strategy_id: str = None, limit: int = 100) -> List[dict]:
        """Mock get recent trades"""
        trades = self.containers['trades'].copy()
        if strategy_id:
            trades = [t for t in trades if t.get('strategy_id') == strategy_id]
        trades.sort(key=lambda x: x.get('_ts', 0), reverse=True)
        return trades[:limit]
        
    # Health and stats
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