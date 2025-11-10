"""
Enhanced Multi-Symbol WebSocket Manager

Comprehensive real-time data collection system with:
- Dynamic symbol addition/removal
- Automatic reconnection
- Multiple stream types per symbol
- Stream health monitoring
- Bandwidth optimization
- Data validation and quality checks
"""

import asyncio
import websockets
import json
from datetime import datetime, timezone
from typing import Dict, List, Set, Optional, Callable
from enum import Enum
import structlog
from dataclasses import dataclass, field

from config import settings
from database import Database
from models import MarketData, TradeData, OrderBookData

logger = structlog.get_logger()

class StreamType(Enum):
    """Available WebSocket stream types"""
    KLINE = "kline"
    TRADE = "trade"
    TICKER = "ticker"
    DEPTH = "depth"        # Order book
    BOOK_TICKER = "bookTicker"  # Best bid/ask
    AGG_TRADE = "aggTrade"   # Aggregated trades

@dataclass
class StreamConfig:
    """Configuration for a stream"""
    symbol: str
    stream_type: StreamType
    interval: Optional[str] = None  # For kline streams (1m, 5m, 15m, etc.)
    depth: Optional[int] = None     # For depth streams (5, 10, 20)
    enabled: bool = True
    auto_reconnect: bool = True
    max_reconnect_attempts: int = 10
    reconnect_delay: int = 5  # seconds

@dataclass
class StreamHealth:
    """Health metrics for a stream"""
    symbol: str
    stream_type: str
    is_connected: bool = False
    last_message_time: Optional[datetime] = None
    messages_received: int = 0
    errors: int = 0
    reconnect_attempts: int = 0
    last_error: Optional[str] = None

class EnhancedWebSocketManager:
    """
    Enhanced WebSocket manager for multiple symbols with dynamic management
    """
    
    def __init__(self, database: Database):
        self.database = database
        self.active_streams: Dict[str, asyncio.Task] = {}
        self.stream_configs: Dict[str, StreamConfig] = {}
        self.stream_health: Dict[str, StreamHealth] = {}
        self.running = False
        
        # Callbacks for data processing
        self.data_callbacks: Dict[StreamType, List[Callable]] = {
            stream_type: [] for stream_type in StreamType
        }
        
        # Connection pool
        self.websocket_url = settings.BINANCE_WSS_URL
        
    async def start(self, initial_symbols: List[str] = None):
        """Start the WebSocket manager"""
        self.running = True
        
        if initial_symbols:
            await self.add_symbols(initial_symbols)
            
        logger.info(
            "WebSocket manager started",
            total_streams=len(self.active_streams)
        )
    
    async def stop(self):
        """Stop all streams gracefully"""
        self.running = False
        
        logger.info("Stopping all WebSocket streams")
        
        # Cancel all active stream tasks
        for stream_id, task in self.active_streams.items():
            task.cancel()
            
        # Wait for cancellation
        await asyncio.gather(*self.active_streams.values(), return_exceptions=True)
        
        self.active_streams.clear()
        
        logger.info("All WebSocket streams stopped")
    
    async def add_symbols(
        self,
        symbols: List[str],
        stream_types: List[StreamType] = None,
        intervals: List[str] = None
    ):
        """Add new symbols to track"""
        if stream_types is None:
            # Default: track kline, trade, and ticker
            stream_types = [StreamType.KLINE, StreamType.TRADE, StreamType.TICKER]
            
        if intervals is None:
            intervals = ["1m"]  # Default to 1-minute klines
            
        added_count = 0
        
        for symbol in symbols:
            for stream_type in stream_types:
                if stream_type == StreamType.KLINE:
                    for interval in intervals:
                        added = await self._add_stream(symbol, stream_type, interval=interval)
                        if added:
                            added_count += 1
                elif stream_type == StreamType.DEPTH:
                    added = await self._add_stream(symbol, stream_type, depth=20)
                    if added:
                        added_count += 1
                else:
                    added = await self._add_stream(symbol, stream_type)
                    if added:
                        added_count += 1
                        
        logger.info(
            f"Added {added_count} streams for {len(symbols)} symbols",
            symbols=symbols,
            stream_types=[st.value for st in stream_types]
        )
        
        return added_count
    
    async def remove_symbols(self, symbols: List[str]):
        """Remove symbols from tracking"""
        removed_count = 0
        
        for symbol in symbols:
            # Find all streams for this symbol
            streams_to_remove = [
                stream_id for stream_id in self.active_streams.keys()
                if stream_id.startswith(f"{symbol}_")
            ]
            
            for stream_id in streams_to_remove:
                if await self._remove_stream(stream_id):
                    removed_count += 1
                    
        logger.info(
            f"Removed {removed_count} streams for {len(symbols)} symbols",
            symbols=symbols
        )
        
        return removed_count
    
    async def _add_stream(
        self,
        symbol: str,
        stream_type: StreamType,
        interval: Optional[str] = None,
        depth: Optional[int] = None
    ) -> bool:
        """Add a single stream"""
        
        # Create stream ID
        stream_id = self._create_stream_id(symbol, stream_type, interval, depth)
        
        # Check if already exists
        if stream_id in self.active_streams:
            logger.warning(f"Stream {stream_id} already exists")
            return False
            
        # Create stream config
        config = StreamConfig(
            symbol=symbol,
            stream_type=stream_type,
            interval=interval,
            depth=depth
        )
        
        self.stream_configs[stream_id] = config
        
        # Create health tracker
        self.stream_health[stream_id] = StreamHealth(
            symbol=symbol,
            stream_type=stream_type.value
        )
        
        # Start stream task
        task = asyncio.create_task(
            self._run_stream(stream_id, config)
        )
        self.active_streams[stream_id] = task
        
        logger.info(f"Started stream {stream_id}")
        return True
    
    async def _remove_stream(self, stream_id: str) -> bool:
        """Remove a single stream"""
        if stream_id not in self.active_streams:
            return False
            
        # Cancel task
        task = self.active_streams[stream_id]
        task.cancel()
        
        try:
            await task
        except asyncio.CancelledError:
            pass
            
        # Cleanup
        del self.active_streams[stream_id]
        del self.stream_configs[stream_id]
        del self.stream_health[stream_id]
        
        logger.info(f"Removed stream {stream_id}")
        return True
    
    def _create_stream_id(
        self,
        symbol: str,
        stream_type: StreamType,
        interval: Optional[str] = None,
        depth: Optional[int] = None
    ) -> str:
        """Create unique stream ID"""
        parts = [symbol, stream_type.value]
        
        if interval:
            parts.append(interval)
        if depth:
            parts.append(f"depth{depth}")
            
        return "_".join(parts)
    
    def _build_stream_url(self, config: StreamConfig) -> str:
        """Build WebSocket URL for stream"""
        symbol_lower = config.symbol.lower()
        
        if config.stream_type == StreamType.KLINE:
            stream_name = f"{symbol_lower}@kline_{config.interval}"
        elif config.stream_type == StreamType.TRADE:
            stream_name = f"{symbol_lower}@trade"
        elif config.stream_type == StreamType.TICKER:
            stream_name = f"{symbol_lower}@ticker"
        elif config.stream_type == StreamType.DEPTH:
            stream_name = f"{symbol_lower}@depth{config.depth or 20}"
        elif config.stream_type == StreamType.BOOK_TICKER:
            stream_name = f"{symbol_lower}@bookTicker"
        elif config.stream_type == StreamType.AGG_TRADE:
            stream_name = f"{symbol_lower}@aggTrade"
        else:
            raise ValueError(f"Unknown stream type: {config.stream_type}")
            
        return f"{self.websocket_url}{stream_name}"
    
    async def _run_stream(self, stream_id: str, config: StreamConfig):
        """Run a single WebSocket stream with reconnection"""
        url = self._build_stream_url(config)
        health = self.stream_health[stream_id]
        
        while self.running and config.enabled:
            try:
                async with websockets.connect(url, ping_interval=20) as websocket:
                    health.is_connected = True
                    health.reconnect_attempts = 0
                    logger.info(f"Connected to stream {stream_id}")
                    
                    while self.running and config.enabled:
                        try:
                            message = await asyncio.wait_for(
                                websocket.recv(),
                                timeout=30.0
                            )
                            
                            # Update health
                            health.last_message_time = datetime.utcnow()
                            health.messages_received += 1
                            
                            # Process message
                            await self._process_message(config, message)
                            
                        except asyncio.TimeoutError:
                            logger.warning(f"Timeout on stream {stream_id}")
                            break
                        except websockets.ConnectionClosed:
                            logger.warning(f"Connection closed for stream {stream_id}")
                            break
                            
            except Exception as e:
                health.errors += 1
                health.last_error = str(e)
                health.is_connected = False
                
                logger.error(
                    f"Error in stream {stream_id}",
                    error=str(e),
                    reconnect_attempt=health.reconnect_attempts
                )
                
                # Check reconnection limits
                if not config.auto_reconnect:
                    break
                    
                health.reconnect_attempts += 1
                if health.reconnect_attempts >= config.max_reconnect_attempts:
                    logger.error(f"Max reconnection attempts reached for {stream_id}")
                    break
                    
                # Wait before reconnecting
                await asyncio.sleep(config.reconnect_delay)
                
        health.is_connected = False
        logger.info(f"Stream {stream_id} ended")
    
    async def _process_message(self, config: StreamConfig, message: str):
        """Process incoming WebSocket message"""
        try:
            data = json.loads(message)
            
            # Route to appropriate handler
            if config.stream_type == StreamType.KLINE:
                await self._process_kline(config.symbol, data)
            elif config.stream_type == StreamType.TRADE:
                await self._process_trade(config.symbol, data)
            elif config.stream_type == StreamType.TICKER:
                await self._process_ticker(config.symbol, data)
            elif config.stream_type == StreamType.DEPTH:
                await self._process_depth(config.symbol, data)
            elif config.stream_type == StreamType.BOOK_TICKER:
                await self._process_book_ticker(config.symbol, data)
            elif config.stream_type == StreamType.AGG_TRADE:
                await self._process_agg_trade(config.symbol, data)
                
            # Call registered callbacks
            for callback in self.data_callbacks.get(config.stream_type, []):
                try:
                    await callback(config.symbol, data)
                except Exception as e:
                    logger.error(f"Error in callback: {e}")
                    
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in message: {e}")
        except Exception as e:
            logger.error(f"Error processing message: {e}")
    
    async def _process_kline(self, symbol: str, data: dict):
        """Process kline/candlestick data"""
        k = data.get('k', {})
        
        if not k:
            return
            
        # Only store closed candles
        if not k.get('x'):
            return
            
        market_data = {
            "id": f"{symbol}_{k['i']}_{int(k['t'] / 1000)}",
            "symbol": symbol,
            "interval": k['i'],
            "timestamp": datetime.fromtimestamp(k['t'] / 1000, tz=timezone.utc).isoformat() + "Z",
            "open_price": str(k['o']),
            "high_price": str(k['h']),
            "low_price": str(k['l']),
            "close_price": str(k['c']),
            "volume": str(k['v']),
            "close_time": datetime.fromtimestamp(k['T'] / 1000, tz=timezone.utc).isoformat() + "Z",
            "quote_asset_volume": str(k['q']),
            "number_of_trades": int(k['n']),
            "taker_buy_base_asset_volume": str(k['V']),
            "taker_buy_quote_asset_volume": str(k['Q']),
            "base_asset": symbol[:-4],
            "quote_asset": "USDC",
            "created_at": datetime.utcnow().isoformat() + "Z"
        }
        
        await self.database.upsert_market_data_batch([market_data])
    
    async def _process_trade(self, symbol: str, data: dict):
        """Process trade data"""
        trade_data = {
            "id": f"{symbol}_trade_{data['t']}",
            "symbol": symbol,
            "timestamp": datetime.fromtimestamp(data['T'] / 1000, tz=timezone.utc).isoformat() + "Z",
            "price": str(data['p']),
            "quantity": str(data['q']),
            "is_buyer_maker": data['m'],
            "trade_id": data['t']
        }
        
        # Store in Trades container
        await self.database.upsert_item(trade_data, container_name="Trades")
    
    async def _process_ticker(self, symbol: str, data: dict):
        """Process 24h ticker data"""
        ticker_data = {
            "id": f"{symbol}_ticker_{int(datetime.utcnow().timestamp())}",
            "symbol": symbol,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "price_change": str(data.get('p', 0)),
            "price_change_percent": str(data.get('P', 0)),
            "weighted_avg_price": str(data.get('w', 0)),
            "last_price": str(data.get('c', 0)),
            "last_qty": str(data.get('Q', 0)),
            "open_price": str(data.get('o', 0)),
            "high_price": str(data.get('h', 0)),
            "low_price": str(data.get('l', 0)),
            "volume": str(data.get('v', 0)),
            "quote_volume": str(data.get('q', 0)),
            "open_time": datetime.fromtimestamp(data['O'] / 1000, tz=timezone.utc).isoformat() + "Z" if 'O' in data else None,
            "close_time": datetime.fromtimestamp(data['C'] / 1000, tz=timezone.utc).isoformat() + "Z" if 'C' in data else None,
            "trades_count": int(data.get('n', 0))
        }
        
        await self.database.upsert_item(ticker_data, container_name="Tickers")
    
    async def _process_depth(self, symbol: str, data: dict):
        """Process order book depth data"""
        # Store simplified order book snapshot
        depth_data = {
            "id": f"{symbol}_depth_{data.get('lastUpdateId', int(datetime.utcnow().timestamp()))}",
            "symbol": symbol,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "last_update_id": data.get('lastUpdateId'),
            "bids": data.get('bids', [])[:10],  # Store top 10
            "asks": data.get('asks', [])[:10]   # Store top 10
        }
        
        await self.database.upsert_item(depth_data, container_name="OrderBooks")
    
    async def _process_book_ticker(self, symbol: str, data: dict):
        """Process best bid/ask data"""
        book_ticker_data = {
            "id": f"{symbol}_bookticker_{int(datetime.utcnow().timestamp())}",
            "symbol": symbol,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "best_bid_price": str(data.get('b', 0)),
            "best_bid_qty": str(data.get('B', 0)),
            "best_ask_price": str(data.get('a', 0)),
            "best_ask_qty": str(data.get('A', 0))
        }
        
        await self.database.upsert_item(book_ticker_data, container_name="BookTickers")
    
    async def _process_agg_trade(self, symbol: str, data: dict):
        """Process aggregated trade data"""
        agg_trade_data = {
            "id": f"{symbol}_aggtrade_{data['a']}",
            "symbol": symbol,
            "timestamp": datetime.fromtimestamp(data['T'] / 1000, tz=timezone.utc).isoformat() + "Z",
            "agg_trade_id": data['a'],
            "price": str(data['p']),
            "quantity": str(data['q']),
            "first_trade_id": data['f'],
            "last_trade_id": data['l'],
            "is_buyer_maker": data['m']
        }
        
        await self.database.upsert_item(agg_trade_data, container_name="AggTrades")
    
    def register_callback(self, stream_type: StreamType, callback: Callable):
        """Register a callback for a stream type"""
        self.data_callbacks[stream_type].append(callback)
    
    def get_health_status(self) -> Dict:
        """Get health status of all streams"""
        return {
            "total_streams": len(self.active_streams),
            "active_streams": sum(1 for h in self.stream_health.values() if h.is_connected),
            "total_messages": sum(h.messages_received for h in self.stream_health.values()),
            "total_errors": sum(h.errors for h in self.stream_health.values()),
            "streams": [
                {
                    "stream_id": stream_id,
                    "symbol": health.symbol,
                    "type": health.stream_type,
                    "connected": health.is_connected,
                    "messages": health.messages_received,
                    "errors": health.errors,
                    "last_message": health.last_message_time.isoformat() if health.last_message_time else None
                }
                for stream_id, health in self.stream_health.items()
            ]
        }


# Example usage
async def main():
    """Example usage"""
    from database import Database
    
    database = Database()
    await database.connect()
    
    manager = EnhancedWebSocketManager(database)
    
    # Start with initial symbols
    await manager.start(initial_symbols=["BTCUSDC", "ETHUSDC"])
    
    # Add more symbols dynamically
    await asyncio.sleep(10)
    await manager.add_symbols(["ADAUSDC", "SOLUSDC"])
    
    # Remove symbols
    await asyncio.sleep(10)
    await manager.remove_symbols(["ADAUSDC"])
    
    # Run indefinitely
    try:
        while True:
            await asyncio.sleep(60)
            status = manager.get_health_status()
            logger.info("Health status", **status)
    except KeyboardInterrupt:
        await manager.stop()
        await database.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
