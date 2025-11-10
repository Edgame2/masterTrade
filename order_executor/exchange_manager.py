"""
Enhanced Exchange Manager with Testnet and Production Support

This module manages multiple exchange connections (Binance testnet and production)
and routes orders to the appropriate environment based on strategy configuration.
"""

import asyncio
import ccxt.async_support as ccxt
from typing import Dict, Optional, Any
import structlog

from config import settings

logger = structlog.get_logger()


class ExchangeManager:
    """Manages multiple exchange connections for testnet and production"""
    
    def __init__(self):
        self.exchanges: Dict[str, ccxt.Exchange] = {}
        self.initialized = False
        
    async def initialize(self):
        """Initialize exchange connections"""
        try:
            # Initialize Binance testnet
            if settings.BINANCE_TESTNET_API_KEY and settings.BINANCE_TESTNET_API_SECRET:
                self.exchanges['testnet'] = ccxt.binance({
                    'apiKey': settings.BINANCE_TESTNET_API_KEY,
                    'secret': settings.BINANCE_TESTNET_API_SECRET,
                    'sandbox': True,
                    'enableRateLimit': True,
                    'options': {
                        'defaultType': 'spot',
                    }
                })
                logger.info("Binance testnet exchange initialized")
            else:
                logger.warning("Binance testnet credentials not configured")
                
            # Initialize Binance production
            if settings.BINANCE_API_KEY and settings.BINANCE_API_SECRET:
                self.exchanges['production'] = ccxt.binance({
                    'apiKey': settings.BINANCE_API_KEY,
                    'secret': settings.BINANCE_API_SECRET,
                    'sandbox': False,
                    'enableRateLimit': True,
                    'options': {
                        'defaultType': 'spot',
                    }
                })
                logger.info("Binance production exchange initialized")
            else:
                logger.warning("Binance production credentials not configured")
                
            # Test connectivity
            for env, exchange in self.exchanges.items():
                try:
                    await exchange.load_markets()
                    logger.info(f"{env} exchange connected successfully", 
                              markets_count=len(exchange.markets))
                except Exception as e:
                    logger.error(f"Failed to connect to {env} exchange", error=str(e))
                    
            self.initialized = True
            logger.info("Exchange manager initialized", 
                       environments=list(self.exchanges.keys()))
                       
        except Exception as e:
            logger.error("Failed to initialize exchange manager", error=str(e))
            raise
            
    async def close(self):
        """Close all exchange connections"""
        for env, exchange in self.exchanges.items():
            try:
                await exchange.close()
                logger.info(f"Closed {env} exchange connection")
            except Exception as e:
                logger.error(f"Error closing {env} exchange", error=str(e))
        self.exchanges.clear()
        
    def get_exchange(self, environment: str = "testnet") -> Optional[ccxt.Exchange]:
        """Get exchange instance for specified environment"""
        if not self.initialized:
            raise RuntimeError("Exchange manager not initialized")
            
        if environment not in self.exchanges:
            logger.error(f"Exchange environment not available: {environment}")
            return None
            
        return self.exchanges[environment]
        
    async def get_balance(self, environment: str = "testnet") -> Dict[str, Any]:
        """Get account balance for specified environment"""
        exchange = self.get_exchange(environment)
        if not exchange:
            raise ValueError(f"Exchange not available for environment: {environment}")
            
        try:
            balance = await exchange.fetch_balance()
            logger.info(f"Retrieved balance for {environment}", 
                       total_balance_keys=len(balance.get('total', {})))
            return balance
        except Exception as e:
            logger.error(f"Failed to get balance for {environment}", error=str(e))
            raise
            
    async def create_order(self, symbol: str, order_type: str, side: str, 
                          amount: float, price: Optional[float] = None, 
                          environment: str = "testnet", **params) -> Dict[str, Any]:
        """Create order on specified environment"""
        exchange = self.get_exchange(environment)
        if not exchange:
            raise ValueError(f"Exchange not available for environment: {environment}")
            
        try:
            # Create order parameters
            order_params = {
                'symbol': symbol,
                'type': order_type.lower(),
                'side': side.lower(),
                'amount': amount,
                **params
            }
            
            if price is not None and order_type.upper() in ['LIMIT', 'STOP_LOSS_LIMIT', 'TAKE_PROFIT_LIMIT']:
                order_params['price'] = price
                
            logger.info(f"Creating order on {environment}", 
                       symbol=symbol, side=side, amount=amount, 
                       order_type=order_type, environment=environment)
            
            # Create the order
            order = await exchange.create_order(**order_params)
            
            logger.info(f"Order created successfully on {environment}", 
                       order_id=order.get('id'), 
                       client_order_id=order.get('clientOrderId'),
                       status=order.get('status'))
            
            return order
            
        except Exception as e:
            logger.error(f"Failed to create order on {environment}", 
                        symbol=symbol, side=side, amount=amount, error=str(e))
            raise
            
    async def cancel_order(self, order_id: str, symbol: str, 
                          environment: str = "testnet") -> Dict[str, Any]:
        """Cancel order on specified environment"""
        exchange = self.get_exchange(environment)
        if not exchange:
            raise ValueError(f"Exchange not available for environment: {environment}")
            
        try:
            result = await exchange.cancel_order(order_id, symbol)
            logger.info(f"Order cancelled on {environment}", 
                       order_id=order_id, symbol=symbol)
            return result
        except Exception as e:
            logger.error(f"Failed to cancel order on {environment}", 
                        order_id=order_id, symbol=symbol, error=str(e))
            raise
            
    async def get_order_status(self, order_id: str, symbol: str, 
                              environment: str = "testnet") -> Dict[str, Any]:
        """Get order status from specified environment"""
        exchange = self.get_exchange(environment)
        if not exchange:
            raise ValueError(f"Exchange not available for environment: {environment}")
            
        try:
            order = await exchange.fetch_order(order_id, symbol)
            return order
        except Exception as e:
            logger.error(f"Failed to get order status on {environment}", 
                        order_id=order_id, symbol=symbol, error=str(e))
            raise
            
    async def get_open_orders(self, symbol: Optional[str] = None, 
                             environment: str = "testnet") -> list:
        """Get open orders from specified environment"""
        exchange = self.get_exchange(environment)
        if not exchange:
            raise ValueError(f"Exchange not available for environment: {environment}")
            
        try:
            orders = await exchange.fetch_open_orders(symbol)
            return orders
        except Exception as e:
            logger.error(f"Failed to get open orders on {environment}", 
                        symbol=symbol, error=str(e))
            raise
            
    def get_available_environments(self) -> list:
        """Get list of available exchange environments"""
        return list(self.exchanges.keys())
        
    async def test_connectivity(self) -> Dict[str, bool]:
        """Test connectivity to all configured exchanges"""
        results = {}
        
        for environment in self.exchanges:
            try:
                exchange = self.get_exchange(environment)
                await exchange.fetch_markets()
                results[environment] = True
                logger.info(f"{environment} exchange connectivity test passed")
            except Exception as e:
                results[environment] = False
                logger.error(f"{environment} exchange connectivity test failed", error=str(e))
                
        return results


# Global exchange manager instance
exchange_manager = ExchangeManager()