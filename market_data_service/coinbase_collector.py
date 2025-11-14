"""
Coinbase Exchange Collector

Collects market data from Coinbase Pro/Advanced Trade API:
- Order book snapshots (REST + WebSocket)
- Recent trades (REST + WebSocket)
- Ticker data
- Large trade detection
- Real-time streaming

API Documentation:
- REST: https://docs.cloud.coinbase.com/exchange/reference
- WebSocket: https://docs.cloud.coinbase.com/exchange/docs/websocket-overview
"""

import asyncio
import aiohttp
import websockets
import json
import hmac
import hashlib
import base64
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional
import structlog

from exchange_collector_base import (
    ExchangeCollectorBase,
    ExchangeType,
    LargeTrade
)
from database import Database

logger = structlog.get_logger()


class CoinbaseCollector(ExchangeCollectorBase):
    """
    Coinbase Pro/Advanced Trade data collector
    
    Features:
    - Order book snapshots (level 2)
    - Real-time trades
    - Ticker data
    - Large trade detection
    - WebSocket streaming for multiple products
    """
    
    # API endpoints
    REST_API_URL = "https://api.exchange.coinbase.com"
    REST_API_URL_SANDBOX = "https://api-public.sandbox.exchange.coinbase.com"
    WS_URL = "wss://ws-feed.exchange.coinbase.com"
    WS_URL_SANDBOX = "wss://ws-feed-public.sandbox.exchange.coinbase.com"
    
    # Major trading pairs to track
    DEFAULT_PRODUCTS = [
        "BTC-USD", "ETH-USD", "BTC-USDT", "ETH-USDT",
        "SOL-USD", "AVAX-USD", "MATIC-USD", "LINK-USD",
        "UNI-USD", "AAVE-USD", "ATOM-USD", "DOT-USD"
    ]
    
    def __init__(
        self,
        database: Database,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        passphrase: Optional[str] = None,
        testnet: bool = False
    ):
        super().__init__(
            database=database,
            exchange_type=ExchangeType.COINBASE,
            api_key=api_key,
            api_secret=api_secret,
            passphrase=passphrase,
            testnet=testnet
        )
        
        # Coinbase rate limits: 15 req/sec for public, 5 req/sec for private
        self.rate_limiter = asyncio.Semaphore(10)
        self.min_request_interval = 0.1  # 10 req/sec conservative
        
        # Products (symbols)
        self.products = self.DEFAULT_PRODUCTS.copy()
        
    def _build_url(self, endpoint: str) -> str:
        """Build full URL for endpoint"""
        base_url = self.REST_API_URL_SANDBOX if self.testnet else self.REST_API_URL
        return f"{base_url}{endpoint}"
        
    def _get_auth_headers(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict],
        data: Optional[Dict]
    ) -> Dict:
        """
        Get authentication headers for signed requests
        
        Coinbase uses HMAC-SHA256 signature with:
        - timestamp
        - method (GET, POST, etc.)
        - request path
        - body (empty string for GET)
        """
        if not all([self.api_key, self.api_secret, self.passphrase]):
            return {}
            
        timestamp = str(time.time())
        body = json.dumps(data) if data else ''
        message = timestamp + method.upper() + endpoint + body
        
        # Create signature
        hmac_key = base64.b64decode(self.api_secret)
        signature = hmac.new(hmac_key, message.encode(), hashlib.sha256)
        signature_b64 = base64.b64encode(signature.digest()).decode()
        
        return {
            'CB-ACCESS-KEY': self.api_key,
            'CB-ACCESS-SIGN': signature_b64,
            'CB-ACCESS-TIMESTAMP': timestamp,
            'CB-ACCESS-PASSPHRASE': self.passphrase,
            'Content-Type': 'application/json'
        }
        
    async def get_products(self) -> List[Dict]:
        """Get list of available trading products"""
        response = await self._http_request('GET', '/products')
        if response:
            # Filter for active products only
            return [p for p in response if p.get('status') == 'online']
        return []
        
    async def collect_orderbook(self, symbol: str, level: int = 2) -> Optional[Dict]:
        """
        Collect order book snapshot
        
        Args:
            symbol: Product ID (e.g., 'BTC-USD')
            level: 1 (best bid/ask), 2 (top 50), 3 (full orderbook)
        """
        endpoint = f"/products/{symbol}/book"
        params = {'level': level}
        
        response = await self._http_request('GET', endpoint, params=params)
        
        if response:
            # Store in database
            try:
                await self.database.store_exchange_orderbook(
                    exchange=self.exchange_type.value,
                    symbol=symbol,
                    bids=response.get('bids', []),
                    asks=response.get('asks', []),
                    timestamp=datetime.now(timezone.utc),
                    sequence=response.get('sequence')
                )
            except Exception as e:
                logger.error(
                    "Failed to store Coinbase orderbook",
                    symbol=symbol,
                    error=str(e)
                )
                
        return response
        
    async def collect_trades(self, symbol: str, limit: int = 100) -> List[Dict]:
        """
        Collect recent trades
        
        Args:
            symbol: Product ID (e.g., 'BTC-USD')
            limit: Number of trades to fetch (max 100)
        """
        endpoint = f"/products/{symbol}/trades"
        params = {'limit': min(limit, 100)}
        
        response = await self._http_request('GET', endpoint, params=params)
        
        if response and isinstance(response, list):
            # Check for large trades
            for trade in response:
                try:
                    price = float(trade['price'])
                    size = float(trade['size'])
                    
                    if self._is_large_trade(symbol, size, price):
                        large_trade = LargeTrade(
                            exchange=self.exchange_type.value,
                            symbol=symbol,
                            side=trade['side'],
                            price=price,
                            size=size,
                            value_usd=size * price,
                            timestamp=datetime.fromisoformat(trade['time'].replace('Z', '+00:00')),
                            trade_id=str(trade['trade_id']),
                            metadata={'maker_order_id': trade.get('maker_order_id'),
                                     'taker_order_id': trade.get('taker_order_id')}
                        )
                        await self._store_large_trade(large_trade)
                        
                except (KeyError, ValueError) as e:
                    logger.error("Failed to parse Coinbase trade", error=str(e))
                    
            return response
        return []
        
    async def get_ticker(self, symbol: str) -> Optional[Dict]:
        """Get current ticker for symbol"""
        endpoint = f"/products/{symbol}/ticker"
        response = await self._http_request('GET', endpoint)
        return response
        
    async def get_24h_stats(self, symbol: str) -> Optional[Dict]:
        """Get 24-hour stats for symbol"""
        endpoint = f"/products/{symbol}/stats"
        response = await self._http_request('GET', endpoint)
        return response
        
    async def start_realtime_stream(self, symbols: List[str] = None):
        """
        Start real-time WebSocket streams
        
        Args:
            symbols: List of product IDs to subscribe to (default: DEFAULT_PRODUCTS)
        """
        products = symbols or self.products
        
        ws_url = self.WS_URL_SANDBOX if self.testnet else self.WS_URL
        
        # Subscribe to ticker, trades, and level2 (orderbook updates)
        subscribe_msg = {
            "type": "subscribe",
            "product_ids": products,
            "channels": ["ticker", "matches", "level2"]
        }
        
        # Start WebSocket task
        task = asyncio.create_task(
            self._run_websocket(
                stream_id="coinbase_realtime",
                url=ws_url,
                subscribe_msg=subscribe_msg,
                handler=self._handle_ws_message
            )
        )
        self.ws_tasks["coinbase_realtime"] = task
        
        logger.info(
            "Coinbase WebSocket stream started",
            products=len(products)
        )
        
    async def _handle_ws_message(self, data: Dict):
        """Handle incoming WebSocket messages"""
        msg_type = data.get('type')
        
        try:
            if msg_type == 'ticker':
                await self._handle_ticker(data)
            elif msg_type == 'match':
                await self._handle_trade(data)
            elif msg_type in ['snapshot', 'l2update']:
                await self._handle_orderbook_update(data)
            elif msg_type == 'subscriptions':
                logger.info("Coinbase subscription confirmed", channels=data.get('channels'))
            elif msg_type == 'error':
                logger.error("Coinbase WebSocket error", message=data.get('message'))
                
        except Exception as e:
            logger.error("Failed to handle Coinbase WebSocket message", error=str(e))
            
    async def _handle_ticker(self, data: Dict):
        """Handle ticker update"""
        # Store ticker data if needed
        pass
        
    async def _handle_trade(self, data: Dict):
        """Handle trade (match) message"""
        try:
            product_id = data['product_id']
            price = float(data['price'])
            size = float(data['size'])
            side = data['side']  # 'buy' or 'sell'
            
            # Check if large trade
            if self._is_large_trade(product_id, size, price):
                large_trade = LargeTrade(
                    exchange=self.exchange_type.value,
                    symbol=product_id,
                    side=side,
                    price=price,
                    size=size,
                    value_usd=size * price,
                    timestamp=datetime.fromisoformat(data['time'].replace('Z', '+00:00')),
                    trade_id=str(data['trade_id']),
                    metadata={
                        'maker_order_id': data.get('maker_order_id'),
                        'taker_order_id': data.get('taker_order_id'),
                        'sequence': data.get('sequence')
                    }
                )
                await self._store_large_trade(large_trade)
                
        except (KeyError, ValueError) as e:
            logger.error("Failed to parse Coinbase trade message", error=str(e))
            
    async def _handle_orderbook_update(self, data: Dict):
        """Handle orderbook snapshot or update"""
        try:
            product_id = data['product_id']
            
            if data['type'] == 'snapshot':
                # Full orderbook snapshot
                await self.database.store_exchange_orderbook(
                    exchange=self.exchange_type.value,
                    symbol=product_id,
                    bids=data['bids'],
                    asks=data['asks'],
                    timestamp=datetime.now(timezone.utc)
                )
            elif data['type'] == 'l2update':
                # Incremental update - store changes
                # In production, you'd maintain local orderbook and apply updates
                pass
                
        except Exception as e:
            logger.error(
                "Failed to handle Coinbase orderbook update",
                error=str(e)
            )
            
    async def collect_all_orderbooks(self):
        """Collect orderbooks for all tracked products"""
        tasks = [self.collect_orderbook(product) for product in self.products]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        success_count = sum(1 for r in results if r and not isinstance(r, Exception))
        logger.info(
            "Coinbase orderbook collection complete",
            total=len(self.products),
            success=success_count
        )
        
    async def collect_all_trades(self):
        """Collect recent trades for all tracked products"""
        tasks = [self.collect_trades(product) for product in self.products]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        total_trades = sum(len(r) for r in results if isinstance(r, list))
        logger.info(
            "Coinbase trades collection complete",
            total=len(self.products),
            trades=total_trades
        )


async def main():
    """Test Coinbase collector"""
    from database import Database
    from config import settings
    
    database = Database()
    await database.connect()
    
    collector = CoinbaseCollector(
        database=database,
        api_key=getattr(settings, 'COINBASE_API_KEY', None),
        api_secret=getattr(settings, 'COINBASE_API_SECRET', None),
        passphrase=getattr(settings, 'COINBASE_PASSPHRASE', None),
        testnet=False
    )
    
    await collector.start()
    
    try:
        # Test REST API
        print("Fetching Coinbase products...")
        products = await collector.get_products()
        print(f"Found {len(products)} products")
        
        print("\nFetching BTC-USD orderbook...")
        orderbook = await collector.collect_orderbook('BTC-USD')
        if orderbook:
            print(f"Bids: {len(orderbook['bids'])}, Asks: {len(orderbook['asks'])}")
            
        print("\nFetching BTC-USD trades...")
        trades = await collector.collect_trades('BTC-USD', limit=10)
        print(f"Fetched {len(trades)} trades")
        
        # Start WebSocket stream
        print("\nStarting WebSocket stream...")
        await collector.start_realtime_stream(['BTC-USD', 'ETH-USD'])
        
        # Run for 30 seconds
        print("Collecting data for 30 seconds...")
        await asyncio.sleep(30)
        
    finally:
        await collector.stop()
        await database.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
