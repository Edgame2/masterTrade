"""
Market Data Consumer - Example client for accessing market data from the Data Access API

This module provides a convenient client for other services to consume market data
from the centralized Data Access API.
"""

import asyncio
import aiohttp
from typing import Dict, List, Optional, Any
from datetime import datetime
import structlog

logger = structlog.get_logger()

class MarketDataConsumer:
    """Client for consuming market data from the Data Access API"""
    
    def __init__(self, api_base_url: str = "http://localhost:8005"):
        self.api_base_url = api_base_url.rstrip('/')
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
            timeout = aiohttp.ClientTimeout(total=30)
            self.session = aiohttp.ClientSession(timeout=timeout)
            
    async def disconnect(self):
        """Close HTTP session"""
        if self.session:
            await self.session.close()
            self.session = None
            
    async def _make_request(self, endpoint: str, params: Optional[Dict] = None) -> Dict:
        """Make HTTP request to the API"""
        if not self.session:
            await self.connect()
            
        url = f"{self.api_base_url}{endpoint}"
        
        try:
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error_text = await response.text()
                    logger.error(
                        "API request failed",
                        url=url,
                        status=response.status,
                        error=error_text
                    )
                    raise Exception(f"API request failed: {response.status} - {error_text}")
                    
        except aiohttp.ClientError as e:
            logger.error("Network error during API request", url=url, error=str(e))
            raise Exception(f"Network error: {str(e)}")
            
    async def get_latest_price(self, symbol: str) -> Dict[str, Any]:
        """Get latest price and 24h statistics for a symbol"""
        endpoint = f"/api/latest-price/{symbol}"
        return await self._make_request(endpoint)
        
    async def get_market_data(
        self,
        symbol: str,
        interval: str = "1m",
        limit: int = 100,
        hours_back: int = 24
    ) -> List[Dict[str, Any]]:
        """Get historical market data for a symbol"""
        endpoint = f"/api/market-data/{symbol}"
        params = {
            "interval": interval,
            "limit": limit,
            "hours_back": hours_back
        }
        result = await self._make_request(endpoint, params)
        return result.get("data", [])
        
    async def get_ohlcv_data(
        self,
        symbol: str,
        interval: str = "1m",
        limit: int = 500
    ) -> List[Dict[str, Any]]:
        """Get OHLCV data in charting format"""
        endpoint = f"/api/ohlcv/{symbol}"
        params = {
            "interval": interval,
            "limit": limit
        }
        result = await self._make_request(endpoint, params)
        return result.get("data", [])
        
    async def get_symbol_stats(self, symbol: str) -> Dict[str, Any]:
        """Get comprehensive statistics for a symbol"""
        endpoint = f"/api/stats/{symbol}"
        return await self._make_request(endpoint)
        
    async def get_multiple_prices(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        """Get latest prices for multiple symbols"""
        tasks = [self.get_latest_price(symbol) for symbol in symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        prices = {}
        for symbol, result in zip(symbols, results):
            if isinstance(result, Exception):
                logger.warning("Failed to get price for symbol", symbol=symbol, error=str(result))
                continue
            prices[symbol] = result
            
        return prices
        
    async def wait_for_price_change(
        self,
        symbol: str,
        threshold_percent: float,
        check_interval: int = 5,
        timeout: int = 300
    ) -> Optional[Dict[str, Any]]:
        """Wait for a price change above threshold"""
        initial_price_data = await self.get_latest_price(symbol)
        initial_price = initial_price_data["price"]
        
        start_time = datetime.now()
        
        while (datetime.now() - start_time).seconds < timeout:
            await asyncio.sleep(check_interval)
            
            try:
                current_price_data = await self.get_latest_price(symbol)
                current_price = current_price_data["price"]
                
                price_change = abs((current_price - initial_price) / initial_price) * 100
                
                if price_change >= threshold_percent:
                    logger.info(
                        "Price change threshold reached",
                        symbol=symbol,
                        initial_price=initial_price,
                        current_price=current_price,
                        change_percent=price_change
                    )
                    return current_price_data
                    
            except Exception as e:
                logger.warning("Error checking price change", symbol=symbol, error=str(e))
                
        return None
        
    async def get_price_trend(
        self,
        symbol: str,
        interval: str = "5m",
        periods: int = 20
    ) -> Dict[str, Any]:
        """Analyze price trend over recent periods"""
        data = await self.get_market_data(
            symbol=symbol,
            interval=interval,
            limit=periods,
            hours_back=24
        )
        
        if len(data) < periods:
            raise Exception(f"Insufficient data for trend analysis: {len(data)} < {periods}")
            
        prices = [float(item["close_price"]) for item in data]
        
        # Simple trend analysis
        trend_direction = "sideways"
        if prices[-1] > prices[0]:
            trend_direction = "up"
        elif prices[-1] < prices[0]:
            trend_direction = "down"
            
        # Calculate volatility (standard deviation)
        mean_price = sum(prices) / len(prices)
        variance = sum((price - mean_price) ** 2 for price in prices) / len(prices)
        volatility = variance ** 0.5
        
        # Calculate momentum (rate of change)
        momentum = ((prices[-1] - prices[0]) / prices[0]) * 100
        
        return {
            "symbol": symbol,
            "trend_direction": trend_direction,
            "momentum_percent": momentum,
            "volatility": volatility,
            "current_price": prices[-1],
            "period_high": max(prices),
            "period_low": min(prices),
            "periods_analyzed": len(prices),
            "interval": interval
        }

# Example usage for other services
async def example_usage():
    """Example of how other services can use the MarketDataConsumer"""
    
    async with MarketDataConsumer() as consumer:
        
        # Get latest price
        btc_price = await consumer.get_latest_price("BTCUSDC")
        print(f"BTC Price: ${btc_price['price']}")
        
        # Get historical data
        btc_history = await consumer.get_market_data("BTCUSDC", "1h", 24)
        print(f"Got {len(btc_history)} hours of BTC data")
        
        # Get multiple prices at once
        prices = await consumer.get_multiple_prices(["BTCUSDC", "ETHUSDC", "ADAUSDC"])
        for symbol, price_data in prices.items():
            print(f"{symbol}: ${price_data['price']} ({price_data['price_change_24h']:.2f}%)")
            
        # Analyze trend
        trend = await consumer.get_price_trend("BTCUSDC", "5m", 20)
        print(f"BTC Trend: {trend['trend_direction']} with {trend['momentum_percent']:.2f}% momentum")

if __name__ == "__main__":
    asyncio.run(example_usage())