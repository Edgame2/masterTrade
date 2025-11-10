#!/usr/bin/env python3
"""
Test script to verify historical data download from Binance works
Saves data to JSON file for inspection
"""

import asyncio
import aiohttp
from datetime import datetime, timedelta
import json
import structlog

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.dev.ConsoleRenderer()
    ]
)

logger = structlog.get_logger()


class BinanceHistoricalDownloader:
    """Simple downloader to test Binance API connectivity"""
    
    def __init__(self):
        self.base_url = "https://api.binance.com"
        self.session = None
        
    async def __aenter__(self):
        timeout = aiohttp.ClientTimeout(total=30)
        self.session = aiohttp.ClientSession(timeout=timeout)
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
            
    async def get_klines(self, symbol: str, interval: str, limit: int = 100):
        """
        Fetch kline/candlestick data from Binance
        
        Args:
            symbol: Trading pair (e.g., BTCUSDC)
            interval: Timeframe (1m, 5m, 15m, 1h, 4h, 1d)
            limit: Number of candles to fetch (max 1000)
        """
        url = f"{self.base_url}/api/v3/klines"
        params = {
            'symbol': symbol,
            'interval': interval,
            'limit': min(limit, 1000)
        }
        
        logger.info("Fetching data from Binance", 
                   symbol=symbol, interval=interval, limit=limit)
        
        try:
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    logger.info("Successfully fetched data", 
                               symbol=symbol, records=len(data))
                    return data
                else:
                    error_text = await response.text()
                    logger.error("Binance API error", 
                                status=response.status, error=error_text)
                    return None
                    
        except Exception as e:
            logger.error("Error fetching data", error=str(e))
            return None
    
    def parse_kline(self, kline_data):
        """Parse Binance kline data into readable format"""
        return {
            'timestamp': datetime.fromtimestamp(kline_data[0] / 1000).isoformat(),
            'open': float(kline_data[1]),
            'high': float(kline_data[2]),
            'low': float(kline_data[3]),
            'close': float(kline_data[4]),
            'volume': float(kline_data[5]),
            'close_time': datetime.fromtimestamp(kline_data[6] / 1000).isoformat(),
            'quote_volume': float(kline_data[7]),
            'trades': int(kline_data[8]),
            'taker_buy_base': float(kline_data[9]),
            'taker_buy_quote': float(kline_data[10])
        }


async def test_download(symbols=['BTCUSDC', 'ETHUSDC'], 
                       intervals=['1h', '4h'], 
                       limit=168):  # 1 week of hourly data
    """
    Test downloading historical data from Binance
    
    Args:
        symbols: List of trading pairs to download
        intervals: List of timeframes to download
        limit: Number of candles per request
    """
    
    logger.info("=" * 60)
    logger.info("BINANCE HISTORICAL DATA DOWNLOAD TEST")
    logger.info("=" * 60)
    
    all_data = {}
    
    async with BinanceHistoricalDownloader() as downloader:
        for symbol in symbols:
            all_data[symbol] = {}
            
            for interval in intervals:
                logger.info(f"\nDownloading {symbol} - {interval}")
                
                raw_data = await downloader.get_klines(symbol, interval, limit)
                
                if raw_data:
                    # Parse the data
                    parsed_data = [downloader.parse_kline(k) for k in raw_data]
                    all_data[symbol][interval] = parsed_data
                    
                    # Show sample
                    logger.info(f"Sample data (first candle):")
                    logger.info(json.dumps(parsed_data[0], indent=2))
                    logger.info(f"Sample data (last candle):")
                    logger.info(json.dumps(parsed_data[-1], indent=2))
                    
                    # Calculate stats
                    closes = [k['close'] for k in parsed_data]
                    logger.info(f"Price range: ${min(closes):.2f} - ${max(closes):.2f}")
                    logger.info(f"Latest price: ${closes[-1]:.2f}")
                    
                else:
                    logger.error(f"Failed to download {symbol} - {interval}")
                    all_data[symbol][interval] = []
                
                # Rate limiting
                await asyncio.sleep(0.1)
    
    # Save to file
    output_file = 'historical_data_test.json'
    with open(output_file, 'w') as f:
        json.dump(all_data, f, indent=2)
    
    logger.info("=" * 60)
    logger.info(f"Data saved to: {output_file}")
    logger.info("=" * 60)
    
    # Summary
    total_records = sum(
        len(data) for symbol_data in all_data.values() 
        for data in symbol_data.values()
    )
    logger.info(f"\nSummary:")
    logger.info(f"  Symbols: {len(symbols)}")
    logger.info(f"  Intervals: {len(intervals)}")
    logger.info(f"  Total records downloaded: {total_records}")
    
    return all_data


async def quick_test():
    """Quick test with minimal data"""
    logger.info("Quick test - downloading 24h of hourly data for BTCUSDC")
    await test_download(symbols=['BTCUSDC'], intervals=['1h'], limit=24)


async def full_test():
    """Full test with multiple symbols and timeframes"""
    symbols = ['BTCUSDC', 'ETHUSDC', 'ADAUSDC', 'SOLUSDC']
    intervals = ['1h', '4h', '1d']
    logger.info(f"Full test - downloading 1 week of data")
    await test_download(symbols=symbols, intervals=intervals, limit=168)


if __name__ == "__main__":
    import sys
    
    print("\nBinance Historical Data Download Test")
    print("=" * 60)
    print("This script tests downloading historical data from Binance")
    print("No database required - data is saved to JSON file")
    print("=" * 60)
    
    if len(sys.argv) > 1 and sys.argv[1] == '--full':
        print("\nRunning FULL test (multiple symbols and timeframes)...")
        asyncio.run(full_test())
    else:
        print("\nRunning QUICK test (1 symbol, 24 hours)")
        print("Run with --full flag for complete test")
        asyncio.run(quick_test())
    
    print("\n✓ Test complete! Check 'historical_data_test.json' for results")
