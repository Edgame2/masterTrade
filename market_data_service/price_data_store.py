"""
Price Data Store - TimescaleDB-optimized storage for OHLCV market data

This module provides high-performance access to price data with:
- Automatic timeframe routing (uses continuous aggregates when possible)
- Efficient time-range queries
- Batch insert operations
- Real-time and historical data access
- Performance metrics tracking

Usage:
    store = PriceDataStore(database)
    
    # Store real-time data
    await store.store_price(symbol="BTCUSDT", exchange="binance", 
                           open=50000, high=50100, low=49900, close=50050,
                           volume=100.5, timestamp=datetime.now())
    
    # Query OHLCV data (automatically uses best source)
    data = await store.get_ohlcv(symbol="BTCUSDT", exchange="binance",
                                 interval="1h", start_time=start, end_time=end)
"""

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
from decimal import Decimal
import structlog

from prometheus_client import Counter, Histogram, Gauge

logger = structlog.get_logger()

# Prometheus metrics
price_inserts = Counter('price_data_inserts_total', 'Total price data inserts', ['symbol', 'exchange'])
price_queries = Counter('price_data_queries_total', 'Total price data queries', ['interval', 'source'])
query_duration = Histogram('price_data_query_seconds', 'Query duration', ['interval'])
batch_size_metric = Histogram('price_data_batch_size', 'Batch insert size')


class PriceDataStore:
    """
    TimescaleDB-optimized price data storage
    
    Automatically routes queries to the most efficient data source:
    - Raw data (price_data table) for 1m interval
    - Continuous aggregates (price_data_5m, etc.) for higher timeframes
    
    Supports:
    - Single and batch inserts
    - Time-range queries with automatic source selection
    - Latest price queries
    - Price change calculations
    - Volume analysis
    """
    
    # Mapping of intervals to continuous aggregate views
    INTERVAL_VIEWS = {
        '1m': 'price_data',  # Raw data
        '5m': 'price_data_5m',
        '15m': 'price_data_15m',
        '1h': 'price_data_1h',
        '4h': 'price_data_4h',
        '1d': 'price_data_1d'
    }
    
    def __init__(self, database):
        """
        Initialize price data store
        
        Args:
            database: Database connection instance with execute/fetch methods
        """
        self.database = database
        
    async def store_price(
        self,
        symbol: str,
        exchange: str,
        timestamp: datetime,
        open_price: float,
        high: float,
        low: float,
        close: float,
        volume: float,
        quote_volume: Optional[float] = None,
        trades_count: Optional[int] = None,
        metadata: Optional[Dict] = None
    ) -> bool:
        """
        Store single price data point
        
        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")
            exchange: Exchange name (e.g., "binance")
            timestamp: Data timestamp
            open_price: Opening price
            high: High price
            low: Low price
            close: Closing price
            volume: Base volume
            quote_volume: Quote volume (optional)
            trades_count: Number of trades (optional)
            metadata: Additional metadata (optional)
        
        Returns:
            True if successful, False otherwise
        """
        try:
            query = """
                INSERT INTO price_data (
                    time, symbol, exchange, open, high, low, close, 
                    volume, quote_volume, trades_count, metadata
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                ON CONFLICT (time, symbol, exchange) 
                DO UPDATE SET
                    open = EXCLUDED.open,
                    high = EXCLUDED.high,
                    low = EXCLUDED.low,
                    close = EXCLUDED.close,
                    volume = EXCLUDED.volume,
                    quote_volume = EXCLUDED.quote_volume,
                    trades_count = EXCLUDED.trades_count,
                    metadata = EXCLUDED.metadata
            """
            
            await self.database.execute(
                query,
                timestamp, symbol, exchange,
                Decimal(str(open_price)), Decimal(str(high)), 
                Decimal(str(low)), Decimal(str(close)),
                Decimal(str(volume)),
                Decimal(str(quote_volume)) if quote_volume else None,
                trades_count,
                metadata
            )
            
            price_inserts.labels(symbol=symbol, exchange=exchange).inc()
            
            logger.debug(
                "Stored price data",
                symbol=symbol,
                exchange=exchange,
                time=timestamp.isoformat(),
                close=close
            )
            
            return True
            
        except Exception as e:
            logger.error(
                "Failed to store price data",
                symbol=symbol,
                exchange=exchange,
                error=str(e),
                exc_info=True
            )
            return False
    
    async def store_prices_batch(
        self,
        prices: List[Dict[str, Any]]
    ) -> int:
        """
        Store multiple price data points in a single transaction
        
        Args:
            prices: List of price data dicts with keys:
                    symbol, exchange, timestamp, open, high, low, close, volume, etc.
        
        Returns:
            Number of records inserted
        """
        if not prices:
            return 0
        
        try:
            batch_size_metric.observe(len(prices))
            
            query = """
                INSERT INTO price_data (
                    time, symbol, exchange, open, high, low, close,
                    volume, quote_volume, trades_count, metadata
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                ON CONFLICT (time, symbol, exchange) DO NOTHING
            """
            
            # Prepare batch data
            batch_data = []
            for price in prices:
                batch_data.append((
                    price['timestamp'],
                    price['symbol'],
                    price['exchange'],
                    Decimal(str(price['open'])),
                    Decimal(str(price['high'])),
                    Decimal(str(price['low'])),
                    Decimal(str(price['close'])),
                    Decimal(str(price['volume'])),
                    Decimal(str(price.get('quote_volume', 0))) if price.get('quote_volume') else None,
                    price.get('trades_count'),
                    price.get('metadata')
                ))
            
            # Execute batch insert
            await self.database.executemany(query, batch_data)
            
            # Update metrics
            for price in prices:
                price_inserts.labels(
                    symbol=price['symbol'],
                    exchange=price['exchange']
                ).inc()
            
            logger.info(
                "Stored price batch",
                count=len(prices),
                symbols=list(set(p['symbol'] for p in prices[:10]))  # Sample
            )
            
            return len(prices)
            
        except Exception as e:
            logger.error(
                "Failed to store price batch",
                count=len(prices),
                error=str(e),
                exc_info=True
            )
            return 0
    
    async def get_ohlcv(
        self,
        symbol: str,
        exchange: str,
        interval: str,
        start_time: datetime,
        end_time: datetime,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Get OHLCV data for time range
        
        Automatically selects optimal data source:
        - Uses continuous aggregates for 5m+ intervals (much faster)
        - Uses raw data for 1m interval
        
        Args:
            symbol: Trading pair symbol
            exchange: Exchange name
            interval: Time interval (1m, 5m, 15m, 1h, 4h, 1d)
            start_time: Start of time range
            end_time: End of time range
            limit: Maximum number of records (optional)
        
        Returns:
            List of OHLCV dicts with keys: time, open, high, low, close, volume
        """
        with query_duration.labels(interval=interval).time():
            try:
                # Determine which table/view to query
                view_name = self.INTERVAL_VIEWS.get(interval, 'price_data')
                time_column = 'bucket' if view_name != 'price_data' else 'time'
                
                # Build query
                query = f"""
                    SELECT 
                        {time_column} as time,
                        open,
                        high,
                        low,
                        close,
                        volume,
                        quote_volume,
                        trades_count
                    FROM {view_name}
                    WHERE symbol = $1 
                        AND exchange = $2
                        AND {time_column} >= $3
                        AND {time_column} <= $4
                    ORDER BY {time_column} ASC
                """
                
                if limit:
                    query += f" LIMIT {limit}"
                
                rows = await self.database.fetch(
                    query,
                    symbol, exchange, start_time, end_time
                )
                
                price_queries.labels(interval=interval, source=view_name).inc()
                
                result = [
                    {
                        'time': row['time'],
                        'open': float(row['open']),
                        'high': float(row['high']),
                        'low': float(row['low']),
                        'close': float(row['close']),
                        'volume': float(row['volume']),
                        'quote_volume': float(row['quote_volume']) if row.get('quote_volume') else None,
                        'trades_count': row.get('trades_count')
                    }
                    for row in rows
                ]
                
                logger.debug(
                    "Retrieved OHLCV data",
                    symbol=symbol,
                    exchange=exchange,
                    interval=interval,
                    source=view_name,
                    count=len(result)
                )
                
                return result
                
            except Exception as e:
                logger.error(
                    "Failed to get OHLCV data",
                    symbol=symbol,
                    exchange=exchange,
                    interval=interval,
                    error=str(e),
                    exc_info=True
                )
                return []
    
    async def get_latest_price(
        self,
        symbol: str,
        exchange: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get latest price data for symbol
        
        Args:
            symbol: Trading pair symbol
            exchange: Exchange name
        
        Returns:
            Dict with latest price data or None if not found
        """
        try:
            query = """
                SELECT 
                    time,
                    open,
                    high,
                    low,
                    close,
                    volume,
                    quote_volume,
                    trades_count
                FROM price_data
                WHERE symbol = $1 AND exchange = $2
                ORDER BY time DESC
                LIMIT 1
            """
            
            row = await self.database.fetchrow(query, symbol, exchange)
            
            if not row:
                return None
            
            return {
                'time': row['time'],
                'open': float(row['open']),
                'high': float(row['high']),
                'low': float(row['low']),
                'close': float(row['close']),
                'volume': float(row['volume']),
                'quote_volume': float(row['quote_volume']) if row.get('quote_volume') else None,
                'trades_count': row.get('trades_count')
            }
            
        except Exception as e:
            logger.error(
                "Failed to get latest price",
                symbol=symbol,
                exchange=exchange,
                error=str(e)
            )
            return None
    
    async def get_price_change(
        self,
        symbol: str,
        exchange: str,
        hours: int = 24
    ) -> Optional[Dict[str, Any]]:
        """
        Calculate price change over time period
        
        Args:
            symbol: Trading pair symbol
            exchange: Exchange name
            hours: Number of hours to look back
        
        Returns:
            Dict with current_price, old_price, change, change_percent
        """
        try:
            query = """
                WITH current AS (
                    SELECT close as current_price
                    FROM price_data
                    WHERE symbol = $1 AND exchange = $2
                    ORDER BY time DESC
                    LIMIT 1
                ),
                historical AS (
                    SELECT close as old_price
                    FROM price_data
                    WHERE symbol = $1 AND exchange = $2
                        AND time <= NOW() - ($3 || ' hours')::INTERVAL
                    ORDER BY time DESC
                    LIMIT 1
                )
                SELECT 
                    current_price,
                    old_price,
                    (current_price - old_price) as change,
                    ((current_price - old_price) / NULLIF(old_price, 0) * 100) as change_percent
                FROM current, historical
            """
            
            row = await self.database.fetchrow(query, symbol, exchange, hours)
            
            if not row:
                return None
            
            return {
                'current_price': float(row['current_price']),
                'old_price': float(row['old_price']),
                'change': float(row['change']),
                'change_percent': float(row['change_percent'])
            }
            
        except Exception as e:
            logger.error(
                "Failed to get price change",
                symbol=symbol,
                exchange=exchange,
                hours=hours,
                error=str(e)
            )
            return None
    
    async def get_volume_profile(
        self,
        symbol: str,
        exchange: str,
        start_time: datetime,
        end_time: datetime
    ) -> Dict[str, Any]:
        """
        Get volume profile (total, average, high, low) for time range
        
        Args:
            symbol: Trading pair symbol
            exchange: Exchange name
            start_time: Start of time range
            end_time: End of time range
        
        Returns:
            Dict with volume statistics
        """
        try:
            query = """
                SELECT 
                    SUM(volume) as total_volume,
                    AVG(volume) as avg_volume,
                    MAX(volume) as max_volume,
                    MIN(volume) as min_volume,
                    STDDEV(volume) as volume_stddev,
                    COUNT(*) as candles_count
                FROM price_data
                WHERE symbol = $1 
                    AND exchange = $2
                    AND time >= $3
                    AND time <= $4
            """
            
            row = await self.database.fetchrow(
                query,
                symbol, exchange, start_time, end_time
            )
            
            if not row:
                return {}
            
            return {
                'total_volume': float(row['total_volume']) if row['total_volume'] else 0,
                'avg_volume': float(row['avg_volume']) if row['avg_volume'] else 0,
                'max_volume': float(row['max_volume']) if row['max_volume'] else 0,
                'min_volume': float(row['min_volume']) if row['min_volume'] else 0,
                'volume_stddev': float(row['volume_stddev']) if row['volume_stddev'] else 0,
                'candles_count': row['candles_count']
            }
            
        except Exception as e:
            logger.error(
                "Failed to get volume profile",
                symbol=symbol,
                exchange=exchange,
                error=str(e)
            )
            return {}
    
    async def get_price_range(
        self,
        symbol: str,
        exchange: str,
        start_time: datetime,
        end_time: datetime
    ) -> Optional[Dict[str, Any]]:
        """
        Get price range (high, low, range) for time period
        
        Args:
            symbol: Trading pair symbol
            exchange: Exchange name
            start_time: Start of time range
            end_time: End of time range
        
        Returns:
            Dict with high, low, range, range_percent
        """
        try:
            query = """
                SELECT 
                    MAX(high) as highest,
                    MIN(low) as lowest,
                    (MAX(high) - MIN(low)) as price_range,
                    ((MAX(high) - MIN(low)) / NULLIF(MIN(low), 0) * 100) as range_percent
                FROM price_data
                WHERE symbol = $1 
                    AND exchange = $2
                    AND time >= $3
                    AND time <= $4
            """
            
            row = await self.database.fetchrow(
                query,
                symbol, exchange, start_time, end_time
            )
            
            if not row:
                return None
            
            return {
                'highest': float(row['highest']),
                'lowest': float(row['lowest']),
                'price_range': float(row['price_range']),
                'range_percent': float(row['range_percent'])
            }
            
        except Exception as e:
            logger.error(
                "Failed to get price range",
                symbol=symbol,
                exchange=exchange,
                error=str(e)
            )
            return None
    
    async def get_symbols(
        self,
        exchange: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get all available symbols (with latest price)
        
        Args:
            exchange: Filter by exchange (optional)
        
        Returns:
            List of dicts with symbol, exchange, latest_price, latest_time
        """
        try:
            if exchange:
                query = """
                    SELECT DISTINCT ON (symbol)
                        symbol,
                        exchange,
                        close as latest_price,
                        time as latest_time
                    FROM price_data
                    WHERE exchange = $1
                    ORDER BY symbol, time DESC
                """
                rows = await self.database.fetch(query, exchange)
            else:
                query = """
                    SELECT DISTINCT ON (symbol, exchange)
                        symbol,
                        exchange,
                        close as latest_price,
                        time as latest_time
                    FROM price_data
                    ORDER BY symbol, exchange, time DESC
                """
                rows = await self.database.fetch(query)
            
            return [
                {
                    'symbol': row['symbol'],
                    'exchange': row['exchange'],
                    'latest_price': float(row['latest_price']),
                    'latest_time': row['latest_time']
                }
                for row in rows
            ]
            
        except Exception as e:
            logger.error(
                "Failed to get symbols",
                exchange=exchange,
                error=str(e)
            )
            return []
