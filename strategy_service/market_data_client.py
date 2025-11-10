"""
Market Data Service Client for Strategy Service

This client handles communication with the market data service,
particularly for triggering historical data collection when new
cryptocurrencies are selected for trading.
"""

import asyncio
from typing import List, Dict, Optional
import aiohttp
import structlog

logger = structlog.get_logger()


class MarketDataClient:
    """Client for interacting with Market Data Service"""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url.rstrip('/')
        self.session: Optional[aiohttp.ClientSession] = None
        
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
            timeout = aiohttp.ClientTimeout(total=300)  # 5 minutes for data collection
            self.session = aiohttp.ClientSession(timeout=timeout)
            logger.info("Market Data Client connected", base_url=self.base_url)
            
    async def disconnect(self):
        """Close HTTP session"""
        if self.session:
            await self.session.close()
            self.session = None
            logger.info("Market Data Client disconnected")
    
    async def trigger_historical_data_collection(
        self,
        symbols: List[str],
        timeframes: List[str] = None,
        days_back: int = 30
    ) -> Dict:
        """
        Trigger historical data collection for specified symbols
        
        Args:
            symbols: List of trading symbols (e.g., ['BTCUSDC', 'ETHUSDC'])
            timeframes: List of timeframes to collect (default: ['1h', '4h', '1d'])
            days_back: Number of days of historical data to collect
            
        Returns:
            Dict with collection results
        """
        if timeframes is None:
            timeframes = ['1h', '4h', '1d']
            
        try:
            url = f"{self.base_url}/api/collect-historical-data"
            
            params = {
                'days_back': days_back
            }
            
            # Add symbols as query parameters
            for symbol in symbols:
                params.setdefault('symbols', []).append(symbol)
            
            # Add timeframes as query parameters  
            for timeframe in timeframes:
                params.setdefault('timeframes', []).append(timeframe)
            
            logger.info("Requesting historical data collection",
                       symbols=symbols, timeframes=timeframes, days_back=days_back)
            
            async with self.session.post(url, params=params) as response:
                if response.status == 200:
                    result = await response.json()
                    logger.info("Historical data collection completed",
                               total_records=result.get('total_records', 0),
                               symbols_processed=result.get('symbols_processed', 0))
                    return result
                else:
                    error_text = await response.text()
                    logger.error("Historical data collection failed",
                               status=response.status, error=error_text)
                    return {
                        'status': 'error',
                        'error': error_text,
                        'http_status': response.status
                    }
                    
        except asyncio.TimeoutError:
            logger.error("Historical data collection timed out", symbols=symbols)
            return {
                'status': 'error',
                'error': 'Request timed out'
            }
        except Exception as e:
            logger.error("Error triggering historical data collection", error=str(e))
            return {
                'status': 'error',
                'error': str(e)
            }
    
    async def check_historical_data_status(
        self,
        symbol: str,
        timeframe: str = '1h'
    ) -> Dict:
        """
        Check if sufficient historical data exists for a symbol
        
        Args:
            symbol: Trading symbol
            timeframe: Timeframe to check
            
        Returns:
            Dict with status information
        """
        try:
            url = f"{self.base_url}/api/historical-data-status/{symbol}"
            params = {'timeframe': timeframe}
            
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error_text = await response.text()
                    logger.error("Failed to check data status",
                               symbol=symbol, status=response.status, error=error_text)
                    return {
                        'symbol': symbol,
                        'has_sufficient_data': False,
                        'error': error_text
                    }
                    
        except Exception as e:
            logger.error("Error checking historical data status", symbol=symbol, error=str(e))
            return {
                'symbol': symbol,
                'has_sufficient_data': False,
                'error': str(e)
            }
    
    async def ensure_historical_data_available(
        self,
        symbols: List[str],
        timeframes: List[str] = None,
        days_back: int = 30,
        force_refresh: bool = False
    ) -> Dict:
        """
        Ensure historical data is available for symbols, collecting if necessary
        
        Args:
            symbols: List of trading symbols
            timeframes: List of timeframes
            days_back: Days of historical data needed
            force_refresh: Force re-collection even if data exists
            
        Returns:
            Dict with results for each symbol
        """
        if timeframes is None:
            timeframes = ['1h', '4h', '1d']
            
        results = {}
        symbols_needing_collection = []
        
        if not force_refresh:
            # Check which symbols need data collection
            for symbol in symbols:
                status = await self.check_historical_data_status(symbol, timeframes[0])
                
                if not status.get('has_sufficient_data', False):
                    symbols_needing_collection.append(symbol)
                    logger.info("Symbol needs historical data", symbol=symbol)
                else:
                    logger.info("Symbol has sufficient historical data", 
                               symbol=symbol, 
                               records=status.get('record_count', 0))
                    
                results[symbol] = status
        else:
            symbols_needing_collection = symbols
        
        # Collect data for symbols that need it
        if symbols_needing_collection:
            logger.info("Triggering historical data collection",
                       symbols=symbols_needing_collection, count=len(symbols_needing_collection))
            
            collection_result = await self.trigger_historical_data_collection(
                symbols=symbols_needing_collection,
                timeframes=timeframes,
                days_back=days_back
            )
            
            # Update results with collection info
            for symbol in symbols_needing_collection:
                if symbol in collection_result.get('results', {}):
                    results[symbol] = {
                        **results.get(symbol, {}),
                        'collection_result': collection_result['results'][symbol]
                    }
        
        return {
            'status': 'completed',
            'symbols_checked': len(symbols),
            'symbols_collected': len(symbols_needing_collection),
            'results': results
        }


async def test_market_data_client():
    """Test the market data client"""
    async with MarketDataClient() as client:
        # Test checking data status
        print("\n=== Checking Data Status ===")
        status = await client.check_historical_data_status('BTCUSDC', '1h')
        print(f"BTCUSDC Status: {status}")
        
        # Test triggering collection
        print("\n=== Triggering Historical Data Collection ===")
        result = await client.trigger_historical_data_collection(
            symbols=['BTCUSDC', 'ETHUSDC'],
            timeframes=['1h'],
            days_back=7
        )
        print(f"Collection Result: {result}")
        
        # Test ensure data available
        print("\n=== Ensuring Data Available ===")
        ensure_result = await client.ensure_historical_data_available(
            symbols=['BTCUSDC', 'ETHUSDC', 'ADAUSDC'],
            timeframes=['1h', '4h'],
            days_back=30
        )
        print(f"Ensure Result: {ensure_result}")


if __name__ == "__main__":
    print("Market Data Client Test")
    asyncio.run(test_market_data_client())
