"""
Historical Data Collector for Market Data Service

This module handles fetching historical market data from Binance REST API
and populating the Azure Cosmos DB with historical OHLCV data.
"""

import asyncio
import aiohttp
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import time
import structlog
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from shared.cache_decorators import cached, simple_key

from config import settings
from database import Database

logger = structlog.get_logger()

class HistoricalDataCollector:
    """Collects historical market data from Binance REST API"""
    
    def __init__(self, database: Database, redis_cache=None):
        self.database = database
        self.redis_cache = redis_cache
        self.session: Optional[aiohttp.ClientSession] = None
        self.rate_limit_delay = 0.1  # 100ms between requests
        self.cache_hits = 0
        self.cache_misses = 0
        
    async def __aenter__(self):
        """Async context manager entry"""
        await self.connect()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.disconnect()
        
    async def connect(self):
        """Initialize HTTP session"""
        if not self.session:
            timeout = aiohttp.ClientTimeout(total=30)
            self.session = aiohttp.ClientSession(timeout=timeout)
            
    async def disconnect(self):
        """Close HTTP session"""
        if self.session:
            await self.session.close()
            self.session = None
            
    async def _make_request(self, url: str, params: Dict) -> Dict:
        """Make HTTP request with rate limiting"""
        if not self.session:
            await self.connect()
            
        try:
            # Rate limiting
            await asyncio.sleep(self.rate_limit_delay)
            
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    return await response.json()
                elif response.status == 429:  # Rate limit exceeded
                    retry_after = int(response.headers.get('Retry-After', 60))
                    logger.warning("Rate limit hit, waiting", retry_after=retry_after)
                    await asyncio.sleep(retry_after)
                    return await self._make_request(url, params)
                else:
                    error_text = await response.text()
                    logger.error(
                        "API request failed",
                        url=url,
                        status=response.status,
                        error=error_text
                    )
                    raise Exception(f"API request failed: {response.status}")
                    
        except aiohttp.ClientError as e:
            logger.error("Network error during API request", url=url, error=str(e))
            raise Exception(f"Network error: {str(e)}")
            
    def _convert_interval_to_ms(self, interval: str) -> int:
        """Convert interval string to milliseconds"""
        interval_map = {
            "1m": 60 * 1000,
            "3m": 3 * 60 * 1000,
            "5m": 5 * 60 * 1000,
            "15m": 15 * 60 * 1000,
            "30m": 30 * 60 * 1000,
            "1h": 60 * 60 * 1000,
            "2h": 2 * 60 * 60 * 1000,
            "4h": 4 * 60 * 60 * 1000,
            "6h": 6 * 60 * 60 * 1000,
            "8h": 8 * 60 * 60 * 1000,
            "12h": 12 * 60 * 60 * 1000,
            "1d": 24 * 60 * 60 * 1000,
            "3d": 3 * 24 * 60 * 60 * 1000,
            "1w": 7 * 24 * 60 * 60 * 1000
        }
        return interval_map.get(interval, 60 * 1000)  # Default to 1 minute
        
    @cached(prefix='historical_klines', ttl=300, key_func=simple_key(0, 1))  # Cache for 5 minutes
    async def fetch_historical_klines(
        self,
        symbol: str,
        interval: str,
        start_time: datetime,
        end_time: datetime,
        limit: int = 1000
    ) -> List[Dict]:
        """Fetch historical klines from Binance API"""
        
        url = f"{settings.BINANCE_REST_API_URL}/api/v3/klines"
        
        params = {
            "symbol": symbol,
            "interval": interval,
            "startTime": int(start_time.timestamp() * 1000),
            "endTime": int(end_time.timestamp() * 1000),
            "limit": limit
        }
        
        logger.info(
            "Fetching historical data",
            symbol=symbol,
            interval=interval,
            start_time=start_time.isoformat(),
            end_time=end_time.isoformat(),
            limit=limit
        )
        
        try:
            response = await self._make_request(url, params)
            
            market_data = []
            for kline in response:
                # Binance kline format: [open_time, open, high, low, close, volume, close_time, ...]
                open_time = datetime.fromtimestamp(kline[0] / 1000)
                
                market_data_item = {
                    "id": f"{symbol}_{interval}_{int(kline[0] / 1000)}",
                    "symbol": symbol,
                    "interval": interval,
                    "timestamp": open_time.isoformat() + "Z",
                    "open_price": str(kline[1]),
                    "high_price": str(kline[2]),
                    "low_price": str(kline[3]),
                    "close_price": str(kline[4]),
                    "volume": str(kline[5]),
                    "close_time": datetime.fromtimestamp(kline[6] / 1000).isoformat() + "Z",
                    "quote_asset_volume": str(kline[7]),
                    "number_of_trades": int(kline[8]),
                    "taker_buy_base_asset_volume": str(kline[9]),
                    "taker_buy_quote_asset_volume": str(kline[10]),
                    "base_asset": symbol[:-4],  # Remove USDC suffix
                    "quote_asset": "USDC",
                    "created_at": datetime.utcnow().isoformat() + "Z"
                }
                market_data.append(market_data_item)
                
            logger.info(
                "Historical data fetched successfully",
                symbol=symbol,
                interval=interval,
                records_count=len(market_data)
            )
            
            return market_data
            
        except Exception as e:
            logger.error(
                "Failed to fetch historical data",
                symbol=symbol,
                interval=interval,
                error=str(e)
            )
            raise
            
    async def collect_historical_data_for_symbol(
        self,
        symbol: str,
        interval: str,
        days_back: int = None
    ) -> int:
        """Collect historical data for a specific symbol and interval"""
        
        if days_back is None:
            days_back = settings.HISTORICAL_DATA_DAYS
            
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=days_back)
        
        total_records = 0
        interval_ms = self._convert_interval_to_ms(interval)
        max_records_per_request = 1000
        
        logger.info(
            "Starting historical data collection",
            symbol=symbol,
            interval=interval,
            days_back=days_back,
            start_time=start_time.isoformat(),
            end_time=end_time.isoformat()
        )
        
        current_start = start_time
        
        while current_start < end_time:
            # Calculate end time for this batch (max 1000 records)
            max_end_time = current_start + timedelta(milliseconds=interval_ms * max_records_per_request)
            batch_end_time = min(max_end_time, end_time)
            
            try:
                # Fetch data for this batch
                klines = await self.fetch_historical_klines(
                    symbol=symbol,
                    interval=interval,
                    start_time=current_start,
                    end_time=batch_end_time,
                    limit=max_records_per_request
                )
                
                if not klines:
                    logger.warning(
                        "No historical data returned",
                        symbol=symbol,
                        interval=interval,
                        start_time=current_start.isoformat()
                    )
                    break
                    
                # Store data in batches
                batch_size = settings.HISTORICAL_BATCH_SIZE
                for i in range(0, len(klines), batch_size):
                    batch = klines[i:i + batch_size]
                    await self.database.upsert_market_data_batch(batch)
                    total_records += len(batch)
                    
                    logger.info(
                        "Stored historical data batch",
                        symbol=symbol,
                        interval=interval,
                        batch_size=len(batch),
                        total_records=total_records
                    )
                
                # Move to next batch
                if klines:
                    # Use the close time of the last kline as the start of the next batch
                    last_kline_close_time = datetime.fromisoformat(klines[-1]["close_time"].rstrip("Z"))
                    current_start = last_kline_close_time + timedelta(milliseconds=interval_ms)
                else:
                    current_start = batch_end_time
                    
            except Exception as e:
                logger.error(
                    "Error collecting historical data batch",
                    symbol=symbol,
                    interval=interval,
                    start_time=current_start.isoformat(),
                    error=str(e)
                )
                # Move forward to avoid infinite loop
                current_start += timedelta(hours=1)
                
        logger.info(
            "Historical data collection completed",
            symbol=symbol,
            interval=interval,
            total_records=total_records
        )
        
        return total_records
        
    async def collect_all_historical_data(self, symbols: List[str] = None) -> Dict[str, Dict[str, int]]:
        """Collect historical data for all symbols and intervals"""
        
        if symbols is None:
            symbols = settings.DEFAULT_SYMBOLS
            
        results = {}
        
        for symbol in symbols:
            results[symbol] = {}
            
            for interval in settings.HISTORICAL_INTERVALS:
                try:
                    record_count = await self.collect_historical_data_for_symbol(
                        symbol=symbol,
                        interval=interval
                    )
                    results[symbol][interval] = record_count
                    
                    # Small delay between intervals to avoid rate limiting
                    await asyncio.sleep(1)
                    
                except Exception as e:
                    logger.error(
                        "Failed to collect historical data",
                        symbol=symbol,
                        interval=interval,
                        error=str(e)
                    )
                    results[symbol][interval] = 0
                    
            # Longer delay between symbols
            await asyncio.sleep(2)
            
        return results
        
    async def backfill_missing_data(
        self,
        symbol: str,
        interval: str,
        check_days: int = 7
    ) -> int:
        """Check for missing data and backfill gaps"""
        
        logger.info(
            "Checking for missing data",
            symbol=symbol,
            interval=interval,
            check_days=check_days
        )
        
        # Get existing data for the last N days
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=check_days)
        
        existing_data = await self.database.get_market_data_for_analysis(
            symbol=symbol,
            interval=interval,
            hours_back=check_days * 24
        )
        
        if not existing_data:
            logger.info("No existing data found, collecting historical data")
            return await self.collect_historical_data_for_symbol(symbol, interval, check_days)
            
        # Find gaps in the data
        interval_ms = self._convert_interval_to_ms(interval)
        interval_seconds = interval_ms / 1000
        
        gaps = []
        existing_times = [datetime.fromisoformat(item["timestamp"].rstrip("Z")) for item in existing_data]
        existing_times.sort()
        
        current_expected = start_time
        for existing_time in existing_times:
            # Check if there's a gap
            if (existing_time - current_expected).total_seconds() > interval_seconds * 1.5:
                gaps.append((current_expected, existing_time))
            current_expected = existing_time + timedelta(seconds=interval_seconds)
            
        # Check for gap at the end
        if (end_time - existing_times[-1]).total_seconds() > interval_seconds * 1.5:
            gaps.append((existing_times[-1] + timedelta(seconds=interval_seconds), end_time))
            
        # Fill gaps
        total_filled = 0
        for gap_start, gap_end in gaps:
            logger.info(
                "Filling data gap",
                symbol=symbol,
                interval=interval,
                gap_start=gap_start.isoformat(),
                gap_end=gap_end.isoformat()
            )
            
            try:
                klines = await self.fetch_historical_klines(
                    symbol=symbol,
                    interval=interval,
                    start_time=gap_start,
                    end_time=gap_end
                )
                
                if klines:
                    await self.database.upsert_market_data_batch(klines)
                    total_filled += len(klines)
                    
            except Exception as e:
                logger.error(
                    "Failed to fill data gap",
                    symbol=symbol,
                    interval=interval,
                    gap_start=gap_start.isoformat(),
                    gap_end=gap_end.isoformat(),
                    error=str(e)
                )
                
        logger.info(
            "Gap filling completed",
            symbol=symbol,
            interval=interval,
            gaps_found=len(gaps),
            records_filled=total_filled
        )
        
        return total_filled

# Example usage
async def main():
    """Example usage of the historical data collector"""
    database = Database()
    
    async with database, HistoricalDataCollector(database) as collector:
        # Collect historical data for all symbols
        results = await collector.collect_all_historical_data()
        
        print("Historical data collection results:")
        for symbol, intervals in results.items():
            print(f"{symbol}:")
            for interval, count in intervals.items():
                print(f"  {interval}: {count} records")

if __name__ == "__main__":
    asyncio.run(main())