"""
Base Exchange Collector

Abstract base class for exchange-specific data collectors with common functionality
for REST + WebSocket connections, rate limiting, and error handling.
"""

import asyncio
import aiohttp
import websockets
import json
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass
import structlog
from enum import Enum

from database import Database

logger = structlog.get_logger()


class ExchangeType(Enum):
    """Supported exchange types"""
    BINANCE = "binance"
    COINBASE = "coinbase"
    DERIBIT = "deribit"
    CME = "cme"


class DataType(Enum):
    """Types of market data"""
    TRADE = "trade"
    ORDERBOOK = "orderbook"
    TICKER = "ticker"
    FUNDING_RATE = "funding_rate"
    OPEN_INTEREST = "open_interest"
    SETTLEMENT = "settlement"
    VOLATILITY = "volatility"


@dataclass
class LargeTrade:
    """Large trade detection"""
    exchange: str
    symbol: str
    side: str  # 'buy' or 'sell'
    price: float
    size: float
    value_usd: float
    timestamp: datetime
    trade_id: str
    is_liquidation: bool = False
    metadata: Dict = None


@dataclass
class FundingRate:
    """Funding rate for perpetual contracts"""
    exchange: str
    symbol: str
    rate: float
    predicted_rate: Optional[float] = None
    timestamp: datetime
    next_funding_time: Optional[datetime] = None


@dataclass
class OpenInterest:
    """Open interest for derivatives"""
    exchange: str
    symbol: str
    open_interest: float
    open_interest_usd: float
    timestamp: datetime


class ExchangeCollectorBase(ABC):
    """
    Abstract base class for exchange data collectors
    
    Provides common functionality:
    - REST API client with rate limiting
    - WebSocket management with auto-reconnect
    - Large trade detection
    - Error handling and circuit breaker
    - Database storage
    """
    
    def __init__(
        self,
        database: Database,
        exchange_type: ExchangeType,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        passphrase: Optional[str] = None,
        testnet: bool = False
    ):
        self.database = database
        self.exchange_type = exchange_type
        self.api_key = api_key
        self.api_secret = api_secret
        self.passphrase = passphrase
        self.testnet = testnet
        
        # HTTP session for REST API
        self.session: Optional[aiohttp.ClientSession] = None
        
        # WebSocket connections
        self.ws_connections: Dict[str, Any] = {}
        self.ws_tasks: Dict[str, asyncio.Task] = {}
        
        # Rate limiting
        self.rate_limiter = asyncio.Semaphore(10)  # Override in subclass
        self.min_request_interval = 0.1  # seconds
        self.last_request_time = 0
        
        # Circuit breaker
        self.error_count = 0
        self.max_errors = 50
        self.circuit_open = False
        self.circuit_reset_time = None
        
        # Large trade thresholds (USD value)
        self.large_trade_threshold_btc = 100000  # $100K
        self.large_trade_threshold_eth = 50000   # $50K
        self.large_trade_threshold_alt = 20000   # $20K
        
        # Running state
        self.running = False
        
    async def start(self):
        """Start the collector"""
        self.running = True
        self.session = aiohttp.ClientSession()
        logger.info(f"{self.exchange_type.value} collector started")
        
    async def stop(self):
        """Stop the collector gracefully"""
        self.running = False
        
        # Close WebSocket connections
        for ws_id, task in self.ws_tasks.items():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
                
        # Close HTTP session
        if self.session:
            await self.session.close()
            
        logger.info(f"{self.exchange_type.value} collector stopped")
        
    async def _http_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        data: Optional[Dict] = None,
        signed: bool = False
    ) -> Optional[Dict]:
        """
        Make HTTP request with rate limiting and error handling
        """
        # Rate limiting
        async with self.rate_limiter:
            # Minimum interval between requests
            now = asyncio.get_event_loop().time()
            time_since_last = now - self.last_request_time
            if time_since_last < self.min_request_interval:
                await asyncio.sleep(self.min_request_interval - time_since_last)
            self.last_request_time = asyncio.get_event_loop().time()
            
            # Circuit breaker check
            if self.circuit_open:
                if datetime.now(timezone.utc) < self.circuit_reset_time:
                    logger.warning(f"Circuit breaker open for {self.exchange_type.value}")
                    return None
                else:
                    self.circuit_open = False
                    self.error_count = 0
                    logger.info(f"Circuit breaker reset for {self.exchange_type.value}")
            
            try:
                # Add authentication if needed
                headers = {}
                if signed:
                    headers = self._get_auth_headers(method, endpoint, params, data)
                
                url = self._build_url(endpoint)
                
                async with self.session.request(
                    method,
                    url,
                    params=params,
                    json=data,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        self.error_count = 0
                        return await response.json()
                    elif response.status == 429:
                        # Rate limit hit
                        logger.warning(
                            f"Rate limit hit on {self.exchange_type.value}",
                            endpoint=endpoint
                        )
                        await asyncio.sleep(5)
                        return None
                    else:
                        logger.error(
                            f"HTTP error on {self.exchange_type.value}",
                            status=response.status,
                            endpoint=endpoint
                        )
                        self._handle_error()
                        return None
                        
            except asyncio.TimeoutError:
                logger.error(f"Timeout on {self.exchange_type.value}", endpoint=endpoint)
                self._handle_error()
                return None
            except Exception as e:
                logger.error(
                    f"Request error on {self.exchange_type.value}",
                    endpoint=endpoint,
                    error=str(e)
                )
                self._handle_error()
                return None
                
    def _handle_error(self):
        """Handle errors with circuit breaker"""
        self.error_count += 1
        if self.error_count >= self.max_errors:
            self.circuit_open = True
            from datetime import timedelta
            self.circuit_reset_time = datetime.now(timezone.utc) + timedelta(minutes=5)
            logger.error(
                f"Circuit breaker opened for {self.exchange_type.value}",
                errors=self.error_count
            )
            
    async def _run_websocket(
        self,
        stream_id: str,
        url: str,
        subscribe_msg: Dict,
        handler: Callable
    ):
        """
        Run WebSocket connection with auto-reconnect
        """
        reconnect_attempts = 0
        max_reconnects = 10
        
        while self.running and reconnect_attempts < max_reconnects:
            try:
                async with websockets.connect(url, ping_interval=20) as ws:
                    # Subscribe to stream
                    await ws.send(json.dumps(subscribe_msg))
                    logger.info(
                        f"WebSocket connected: {self.exchange_type.value}",
                        stream_id=stream_id
                    )
                    reconnect_attempts = 0
                    
                    # Process messages
                    while self.running:
                        try:
                            msg = await asyncio.wait_for(ws.recv(), timeout=30)
                            data = json.loads(msg)
                            await handler(data)
                        except asyncio.TimeoutError:
                            # Send ping to keep connection alive
                            await ws.ping()
                        except websockets.ConnectionClosed:
                            logger.warning(
                                f"WebSocket closed: {self.exchange_type.value}",
                                stream_id=stream_id
                            )
                            break
                            
            except Exception as e:
                logger.error(
                    f"WebSocket error: {self.exchange_type.value}",
                    stream_id=stream_id,
                    error=str(e)
                )
                reconnect_attempts += 1
                if reconnect_attempts < max_reconnects:
                    await asyncio.sleep(5 * reconnect_attempts)
                    
        logger.info(
            f"WebSocket stopped: {self.exchange_type.value}",
            stream_id=stream_id
        )
        
    def _is_large_trade(self, symbol: str, size: float, price: float) -> bool:
        """
        Detect if trade is considered "large"
        """
        value_usd = size * price
        
        if 'BTC' in symbol.upper():
            return value_usd >= self.large_trade_threshold_btc
        elif 'ETH' in symbol.upper():
            return value_usd >= self.large_trade_threshold_eth
        else:
            return value_usd >= self.large_trade_threshold_alt
            
    async def _store_large_trade(self, trade: LargeTrade):
        """Store large trade in database"""
        try:
            await self.database.store_large_trade(
                exchange=trade.exchange,
                symbol=trade.symbol,
                side=trade.side,
                price=trade.price,
                size=trade.size,
                value_usd=trade.value_usd,
                timestamp=trade.timestamp,
                trade_id=trade.trade_id,
                is_liquidation=trade.is_liquidation,
                metadata=trade.metadata
            )
            logger.info(
                f"Large trade stored: {self.exchange_type.value}",
                symbol=trade.symbol,
                value_usd=trade.value_usd,
                side=trade.side
            )
        except Exception as e:
            logger.error(
                f"Failed to store large trade: {self.exchange_type.value}",
                error=str(e)
            )
            
    async def _store_funding_rate(self, funding: FundingRate):
        """Store funding rate in database"""
        try:
            await self.database.store_funding_rate(
                exchange=funding.exchange,
                symbol=funding.symbol,
                rate=funding.rate,
                predicted_rate=funding.predicted_rate,
                timestamp=funding.timestamp,
                next_funding_time=funding.next_funding_time
            )
        except Exception as e:
            logger.error(
                f"Failed to store funding rate: {self.exchange_type.value}",
                error=str(e)
            )
            
    async def _store_open_interest(self, oi: OpenInterest):
        """Store open interest in database"""
        try:
            await self.database.store_open_interest(
                exchange=oi.exchange,
                symbol=oi.symbol,
                open_interest=oi.open_interest,
                open_interest_usd=oi.open_interest_usd,
                timestamp=oi.timestamp
            )
        except Exception as e:
            logger.error(
                f"Failed to store open interest: {self.exchange_type.value}",
                error=str(e)
            )
    
    # Abstract methods to be implemented by subclasses
    
    @abstractmethod
    def _build_url(self, endpoint: str) -> str:
        """Build full URL for endpoint"""
        pass
        
    @abstractmethod
    def _get_auth_headers(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict],
        data: Optional[Dict]
    ) -> Dict:
        """Get authentication headers for signed requests"""
        pass
        
    @abstractmethod
    async def collect_orderbook(self, symbol: str) -> Optional[Dict]:
        """Collect order book snapshot"""
        pass
        
    @abstractmethod
    async def collect_trades(self, symbol: str, limit: int = 100) -> List[Dict]:
        """Collect recent trades"""
        pass
        
    @abstractmethod
    async def start_realtime_stream(self, symbols: List[str]):
        """Start real-time WebSocket streams"""
        pass
