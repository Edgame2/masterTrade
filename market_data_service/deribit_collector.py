"""
Deribit Exchange Collector

Collects derivatives data from Deribit (options + futures):
- Funding rates (perpetual futures)
- Open interest
- Order book snapshots
- Recent trades
- Volatility surface
- Liquidations
- Real-time streaming

API Documentation:
- REST: https://docs.deribit.com/
- WebSocket: https://docs.deribit.com/#subscriptions
"""

import asyncio
import aiohttp
import websockets
import json
import hmac
import hashlib
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
import structlog

from exchange_collector_base import (
    ExchangeCollectorBase,
    ExchangeType,
    LargeTrade,
    FundingRate,
    OpenInterest
)
from database import Database

logger = structlog.get_logger()


class DeribitCollector(ExchangeCollectorBase):
    """
    Deribit derivatives data collector
    
    Features:
    - Funding rates for perpetual futures
    - Open interest tracking
    - Order book snapshots
    - Real-time trades with liquidation detection
    - Volatility index (DVOL)
    - Options data
    """
    
    # API endpoints
    REST_API_URL = "https://www.deribit.com/api/v2"
    REST_API_URL_TESTNET = "https://test.deribit.com/api/v2"
    WS_URL = "wss://www.deribit.com/ws/api/v2"
    WS_URL_TESTNET = "wss://test.deribit.com/ws/api/v2"
    
    # Major instruments to track
    DEFAULT_INSTRUMENTS = [
        "BTC-PERPETUAL",   # Bitcoin perpetual future
        "ETH-PERPETUAL",   # Ethereum perpetual future
        "BTC-USD",          # BTC index
        "ETH-USD",          # ETH index
    ]
    
    def __init__(
        self,
        database: Database,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        testnet: bool = False
    ):
        super().__init__(
            database=database,
            exchange_type=ExchangeType.DERIBIT,
            api_key=api_key,
            api_secret=api_secret,
            testnet=testnet
        )
        
        # Deribit rate limits: 20 req/sec for public, varies for private
        self.rate_limiter = asyncio.Semaphore(15)
        self.min_request_interval = 0.05  # 20 req/sec
        
        # Instruments (contracts)
        self.instruments = self.DEFAULT_INSTRUMENTS.copy()
        
        # WebSocket message ID counter
        self.ws_msg_id = 0
        
    def _build_url(self, endpoint: str) -> str:
        """Build full URL for endpoint"""
        base_url = self.REST_API_URL_TESTNET if self.testnet else self.REST_API_URL
        return f"{base_url}{endpoint}"
        
    def _get_auth_headers(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict],
        data: Optional[Dict]
    ) -> Dict:
        """
        Deribit uses different auth - handled in request body/params
        """
        # Deribit uses auth in request parameters, not headers
        return {}
        
    async def _deribit_request(
        self,
        method: str,
        params: Dict = None,
        signed: bool = False
    ) -> Optional[Dict]:
        """
        Make Deribit API request
        
        Deribit uses JSON-RPC 2.0 format
        """
        if params is None:
            params = {}
            
        # Add authentication if needed
        if signed and self.api_key and self.api_secret:
            # Get access token first (Deribit requires OAuth-like flow)
            # For simplicity, we'll use public endpoints only
            pass
            
        url = self._build_url(f"/public/{method}")
        
        try:
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    result = await response.json()
                    return result.get('result')
                else:
                    logger.error(
                        "Deribit API error",
                        method=method,
                        status=response.status
                    )
                    return None
        except Exception as e:
            logger.error(
                "Deribit request failed",
                method=method,
                error=str(e)
            )
            return None
            
    async def get_instruments(
        self,
        currency: str = "BTC",
        kind: str = None
    ) -> List[Dict]:
        """
        Get available instruments
        
        Args:
            currency: 'BTC' or 'ETH'
            kind: 'future', 'option', or None for all
        """
        params = {'currency': currency}
        if kind:
            params['kind'] = kind
            
        result = await self._deribit_request('get_instruments', params)
        return result if result else []
        
    async def collect_funding_rate(self, instrument: str = "BTC-PERPETUAL") -> Optional[FundingRate]:
        """
        Get current funding rate for perpetual contract
        
        Deribit funding happens every 8 hours
        """
        params = {'instrument_name': instrument}
        result = await self._deribit_request('get_funding_rate_value', params)
        
        if result is not None:
            funding_rate = FundingRate(
                exchange=self.exchange_type.value,
                symbol=instrument,
                rate=float(result) / 100,  # Convert from percentage
                timestamp=datetime.now(timezone.utc),
                # Next funding in 8 hours from last funding
                next_funding_time=self._get_next_funding_time()
            )
            
            await self._store_funding_rate(funding_rate)
            return funding_rate
            
        return None
        
    def _get_next_funding_time(self) -> datetime:
        """Calculate next funding time (every 8 hours: 00:00, 08:00, 16:00 UTC)"""
        now = datetime.now(timezone.utc)
        hour = now.hour
        next_hour = ((hour // 8) + 1) * 8
        
        if next_hour >= 24:
            next_funding = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        else:
            next_funding = now.replace(hour=next_hour, minute=0, second=0, microsecond=0)
            
        return next_funding
        
    async def collect_open_interest(self, instrument: str) -> Optional[OpenInterest]:
        """Get current open interest for instrument"""
        params = {'instrument_name': instrument}
        result = await self._deribit_request('get_book_summary_by_instrument', params)
        
        if result and len(result) > 0:
            data = result[0]
            oi = OpenInterest(
                exchange=self.exchange_type.value,
                symbol=instrument,
                open_interest=float(data.get('open_interest', 0)),
                open_interest_usd=float(data.get('estimated_delivery_price', 0)) * float(data.get('open_interest', 0)),
                timestamp=datetime.fromtimestamp(data['creation_timestamp'] / 1000, tz=timezone.utc)
            )
            
            await self._store_open_interest(oi)
            return oi
            
        return None
        
    async def collect_orderbook(self, symbol: str, depth: int = 10) -> Optional[Dict]:
        """
        Collect order book snapshot
        
        Args:
            symbol: Instrument name (e.g., 'BTC-PERPETUAL')
            depth: Number of levels (1-100)
        """
        params = {
            'instrument_name': symbol,
            'depth': min(depth, 100)
        }
        
        result = await self._deribit_request('get_order_book', params)
        
        if result:
            # Store in database
            try:
                await self.database.store_exchange_orderbook(
                    exchange=self.exchange_type.value,
                    symbol=symbol,
                    bids=[[str(b[0]), str(b[1])] for b in result.get('bids', [])],
                    asks=[[str(a[0]), str(a[1])] for a in result.get('asks', [])],
                    timestamp=datetime.fromtimestamp(result['timestamp'] / 1000, tz=timezone.utc)
                )
            except Exception as e:
                logger.error(
                    "Failed to store Deribit orderbook",
                    symbol=symbol,
                    error=str(e)
                )
                
        return result
        
    async def collect_trades(self, symbol: str, limit: int = 100) -> List[Dict]:
        """
        Collect recent trades
        
        Args:
            symbol: Instrument name
            limit: Number of trades (max 1000)
        """
        params = {
            'instrument_name': symbol,
            'count': min(limit, 1000),
            'include_old': True
        }
        
        result = await self._deribit_request('get_last_trades_by_instrument', params)
        
        if result and isinstance(result, dict) and 'trades' in result:
            trades = result['trades']
            
            # Check for large trades and liquidations
            for trade in trades:
                try:
                    price = float(trade['price'])
                    amount = float(trade['amount'])  # In contracts
                    
                    # Convert contracts to USD value (for BTC perpetual: 1 contract = $10)
                    if 'BTC-PERPETUAL' in symbol:
                        size_usd = amount * 10
                    elif 'ETH-PERPETUAL' in symbol:
                        size_usd = amount * 10
                    else:
                        size_usd = amount * price
                        
                    is_liquidation = trade.get('liquidation') is not None
                    
                    if self._is_large_trade(symbol, size_usd / price, price) or is_liquidation:
                        large_trade = LargeTrade(
                            exchange=self.exchange_type.value,
                            symbol=symbol,
                            side='buy' if trade['direction'] == 'buy' else 'sell',
                            price=price,
                            size=amount,
                            value_usd=size_usd,
                            timestamp=datetime.fromtimestamp(trade['timestamp'] / 1000, tz=timezone.utc),
                            trade_id=trade['trade_id'],
                            is_liquidation=is_liquidation,
                            metadata={
                                'iv': trade.get('iv'),  # Implied volatility for options
                                'index_price': trade.get('index_price'),
                                'instrument_name': trade.get('instrument_name')
                            }
                        )
                        await self._store_large_trade(large_trade)
                        
                except (KeyError, ValueError) as e:
                    logger.error("Failed to parse Deribit trade", error=str(e))
                    
            return trades
        return []
        
    async def get_volatility_index(self, currency: str = "BTC") -> Optional[Dict]:
        """
        Get Deribit Volatility Index (DVOL)
        
        Returns current implied volatility
        """
        params = {'currency': currency}
        result = await self._deribit_request('get_historical_volatility', params)
        return result
        
    async def start_realtime_stream(self, symbols: List[str] = None):
        """
        Start real-time WebSocket streams
        
        Subscribes to:
        - trades (with liquidations)
        - ticker (includes funding rate, open interest)
        - book (orderbook updates)
        """
        instruments = symbols or self.instruments
        
        ws_url = self.WS_URL_TESTNET if self.testnet else self.WS_URL
        
        # Build subscription channels
        channels = []
        for instrument in instruments:
            channels.extend([
                f"trades.{instrument}.raw",        # All trades including liquidations
                f"ticker.{instrument}.raw",        # Ticker with funding/OI
                f"book.{instrument}.none.10.100ms" # Orderbook top 10, 100ms updates
            ])
            
        subscribe_msg = {
            "jsonrpc": "2.0",
            "id": self._get_ws_msg_id(),
            "method": "public/subscribe",
            "params": {
                "channels": channels
            }
        }
        
        # Start WebSocket task
        task = asyncio.create_task(
            self._run_websocket(
                stream_id="deribit_realtime",
                url=ws_url,
                subscribe_msg=subscribe_msg,
                handler=self._handle_ws_message
            )
        )
        self.ws_tasks["deribit_realtime"] = task
        
        logger.info(
            "Deribit WebSocket stream started",
            instruments=len(instruments),
            channels=len(channels)
        )
        
    def _get_ws_msg_id(self) -> int:
        """Get next WebSocket message ID"""
        self.ws_msg_id += 1
        return self.ws_msg_id
        
    async def _handle_ws_message(self, data: Dict):
        """Handle incoming WebSocket messages"""
        try:
            # Check if subscription confirmation
            if 'id' in data and 'result' in data:
                logger.info("Deribit subscription confirmed", channels=len(data['result']))
                return
                
            # Handle channel notifications
            if 'params' in data and 'channel' in data['params']:
                channel = data['params']['channel']
                msg_data = data['params']['data']
                
                if channel.startswith('trades.'):
                    await self._handle_trade(msg_data)
                elif channel.startswith('ticker.'):
                    await self._handle_ticker(msg_data)
                elif channel.startswith('book.'):
                    await self._handle_orderbook(msg_data)
                    
        except Exception as e:
            logger.error("Failed to handle Deribit WebSocket message", error=str(e))
            
    async def _handle_trade(self, data: Dict):
        """Handle trade message from WebSocket"""
        try:
            instrument = data['instrument_name']
            price = float(data['price'])
            amount = float(data['amount'])
            
            # Convert to USD value
            if 'BTC-PERPETUAL' in instrument:
                size_usd = amount * 10
            elif 'ETH-PERPETUAL' in instrument:
                size_usd = amount * 10
            else:
                size_usd = amount * price
                
            is_liquidation = data.get('liquidation') is not None
            
            if self._is_large_trade(instrument, size_usd / price, price) or is_liquidation:
                large_trade = LargeTrade(
                    exchange=self.exchange_type.value,
                    symbol=instrument,
                    side='buy' if data['direction'] == 'buy' else 'sell',
                    price=price,
                    size=amount,
                    value_usd=size_usd,
                    timestamp=datetime.fromtimestamp(data['timestamp'] / 1000, tz=timezone.utc),
                    trade_id=data['trade_id'],
                    is_liquidation=is_liquidation,
                    metadata={'iv': data.get('iv'), 'index_price': data.get('index_price')}
                )
                await self._store_large_trade(large_trade)
                
        except (KeyError, ValueError) as e:
            logger.error("Failed to parse Deribit trade", error=str(e))
            
    async def _handle_ticker(self, data: Dict):
        """Handle ticker update with funding rate and open interest"""
        try:
            instrument = data['instrument_name']
            
            # Store funding rate if available
            if 'current_funding' in data and data['current_funding'] is not None:
                funding_rate = FundingRate(
                    exchange=self.exchange_type.value,
                    symbol=instrument,
                    rate=float(data['current_funding']) / 100,
                    timestamp=datetime.fromtimestamp(data['timestamp'] / 1000, tz=timezone.utc),
                    next_funding_time=self._get_next_funding_time()
                )
                await self._store_funding_rate(funding_rate)
                
            # Store open interest if available
            if 'open_interest' in data:
                oi = OpenInterest(
                    exchange=self.exchange_type.value,
                    symbol=instrument,
                    open_interest=float(data['open_interest']),
                    open_interest_usd=float(data.get('mark_price', 0)) * float(data['open_interest']),
                    timestamp=datetime.fromtimestamp(data['timestamp'] / 1000, tz=timezone.utc)
                )
                await self._store_open_interest(oi)
                
        except (KeyError, ValueError) as e:
            logger.error("Failed to parse Deribit ticker", error=str(e))
            
    async def _handle_orderbook(self, data: Dict):
        """Handle orderbook update"""
        try:
            instrument = data['instrument_name']
            
            # Store orderbook snapshot
            await self.database.store_exchange_orderbook(
                exchange=self.exchange_type.value,
                symbol=instrument,
                bids=[[str(b[1]), str(b[2])] for b in data.get('bids', [])],  # [price, amount]
                asks=[[str(a[1]), str(a[2])] for a in data.get('asks', [])],
                timestamp=datetime.fromtimestamp(data['timestamp'] / 1000, tz=timezone.utc)
            )
        except Exception as e:
            logger.error("Failed to handle Deribit orderbook", error=str(e))
            
    async def collect_all_funding_rates(self):
        """Collect funding rates for all perpetual contracts"""
        perpetuals = [i for i in self.instruments if 'PERPETUAL' in i]
        tasks = [self.collect_funding_rate(inst) for inst in perpetuals]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        success_count = sum(1 for r in results if r and not isinstance(r, Exception))
        logger.info(
            "Deribit funding rates collected",
            total=len(perpetuals),
            success=success_count
        )
        
    async def collect_all_open_interest(self):
        """Collect open interest for all instruments"""
        tasks = [self.collect_open_interest(inst) for inst in self.instruments]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        success_count = sum(1 for r in results if r and not isinstance(r, Exception))
        logger.info(
            "Deribit open interest collected",
            total=len(self.instruments),
            success=success_count
        )


async def main():
    """Test Deribit collector"""
    from database import Database
    from config import settings
    
    database = Database()
    await database.connect()
    
    collector = DeribitCollector(
        database=database,
        api_key=getattr(settings, 'DERIBIT_API_KEY', None),
        api_secret=getattr(settings, 'DERIBIT_API_SECRET', None),
        testnet=False
    )
    
    await collector.start()
    
    try:
        # Test REST API
        print("Fetching Deribit instruments...")
        instruments = await collector.get_instruments('BTC', 'future')
        print(f"Found {len(instruments)} BTC futures")
        
        print("\nFetching BTC-PERPETUAL funding rate...")
        funding = await collector.collect_funding_rate('BTC-PERPETUAL')
        if funding:
            print(f"Funding rate: {funding.rate * 100:.4f}%")
            
        print("\nFetching BTC-PERPETUAL open interest...")
        oi = await collector.collect_open_interest('BTC-PERPETUAL')
        if oi:
            print(f"Open Interest: {oi.open_interest} contracts (${oi.open_interest_usd:,.0f})")
            
        print("\nFetching BTC-PERPETUAL trades...")
        trades = await collector.collect_trades('BTC-PERPETUAL', limit=10)
        print(f"Fetched {len(trades)} trades")
        
        # Start WebSocket stream
        print("\nStarting WebSocket stream...")
        await collector.start_realtime_stream(['BTC-PERPETUAL', 'ETH-PERPETUAL'])
        
        # Run for 30 seconds
        print("Collecting data for 30 seconds...")
        await asyncio.sleep(30)
        
    finally:
        await collector.stop()
        await database.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
