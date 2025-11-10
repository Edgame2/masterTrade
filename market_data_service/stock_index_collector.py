"""
Stock Index Data Collector for Market Data Service

This module collects major stock index data from various sources:
- Yahoo Finance (primary, free)
- Alpha Vantage (backup, API key required)
- Finnhub (additional data, API key required)

Supports major global indices: S&P 500, NASDAQ, DOW, VIX, international indices
"""

import asyncio
import aiohttp
import yfinance as yf
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
import pandas as pd
import structlog

from config import settings
from database import Database

logger = structlog.get_logger()

class StockIndexDataCollector:
    """Collects stock index data from multiple sources"""
    
    def __init__(self, database: Database):
        self.database = database
        self.session: Optional[aiohttp.ClientSession] = None
        self.tracked_indices: List[str] = []  # Will be loaded from database
        self.index_categories: Dict[str, List[str]] = {}  # Will be loaded from database
        
    async def __aenter__(self):
        """Async context manager entry"""
        await self.connect()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.disconnect()
        
    async def connect(self):
        """Initialize HTTP session and load indices from database"""
        if not self.session:
            timeout = aiohttp.ClientTimeout(total=30)
            self.session = aiohttp.ClientSession(timeout=timeout)
            
        # Initialize default stock indices if database is empty
        await self.database.initialize_default_stock_indices()
        
        # Load tracked indices from database
        await self._load_indices_from_database()
            
    async def disconnect(self):
        """Close HTTP session"""
        if self.session:
            await self.session.close()
            
    async def _load_indices_from_database(self):
        """Load tracked stock indices from database"""
        try:
            tracked_indices_data = await self.database.get_tracked_stock_indices()
            
            # Extract symbol names
            self.tracked_indices = [idx_data['symbol'] for idx_data in tracked_indices_data]
            
            # Load categories from database
            self.index_categories = await self.database.get_stock_indices_by_category()
            
            if not self.tracked_indices:
                logger.warning("No tracked stock indices found in database")
                # Fallback to config if database is empty
                self.tracked_indices = settings.STOCK_INDICES
                self.index_categories = settings.STOCK_INDEX_CATEGORIES
            else:
                indices_list = ", ".join(self.tracked_indices)
                logger.info(f"Loaded stock indices for tracking: {indices_list}")
                
        except Exception as e:
            logger.error("Error loading stock indices from database", error=str(e))
            # Fallback to configuration
            self.tracked_indices = settings.STOCK_INDICES
            self.index_categories = settings.STOCK_INDEX_CATEGORIES
            logger.warning("Falling back to default stock indices from configuration")
            
    async def reload_indices(self):
        """Reload stock indices from database (for dynamic updates)"""
        old_indices = set(self.tracked_indices)
        await self._load_indices_from_database()
        new_indices = set(self.tracked_indices)
        
        added_indices = new_indices - old_indices
        removed_indices = old_indices - new_indices
        
        if added_indices:
            logger.info(f"New stock indices added: {', '.join(added_indices)}")
            
        if removed_indices:
            logger.info(f"Stock indices removed: {', '.join(removed_indices)}")
            
        return {
            "added": list(added_indices),
            "removed": list(removed_indices),
            "total": len(self.tracked_indices)
        }
        self.session = None
            
    def _normalize_symbol(self, symbol: str) -> str:
        """Normalize symbol for consistent storage"""
        # Remove special characters for ID generation
        return symbol.replace("^", "").replace(".", "_")
        
    async def fetch_yahoo_finance_data(self, symbol: str, period: str = "1d", interval: str = "5m") -> List[Dict]:
        """Fetch data from Yahoo Finance using yfinance"""
        try:
            logger.info("Fetching Yahoo Finance data", symbol=symbol, period=period, interval=interval)
            
            # Run yfinance in thread pool to avoid blocking
            def fetch_data():
                ticker = yf.Ticker(symbol)
                hist = ticker.history(period=period, interval=interval)
                return hist
            
            # Execute in thread pool
            loop = asyncio.get_event_loop()
            hist = await loop.run_in_executor(None, fetch_data)
            
            if hist.empty:
                logger.warning("No data returned from Yahoo Finance", symbol=symbol)
                return []
            
            market_data = []
            for timestamp, row in hist.iterrows():
                # Convert timestamp to datetime if it's not already
                if hasattr(timestamp, 'to_pydatetime'):
                    dt = timestamp.to_pydatetime()
                else:
                    dt = timestamp
                    
                normalized_symbol = self._normalize_symbol(symbol)
                
                market_data_item = {
                    "id": f"{normalized_symbol}_{interval}_{int(dt.timestamp())}",
                    "symbol": symbol,
                    "normalized_symbol": normalized_symbol,
                    "asset_type": "stock_index",
                    "interval": interval,
                    "timestamp": dt.isoformat() + "Z",
                    "open_price": str(row['Open']) if pd.notna(row['Open']) else "0",
                    "high_price": str(row['High']) if pd.notna(row['High']) else "0",
                    "low_price": str(row['Low']) if pd.notna(row['Low']) else "0",
                    "close_price": str(row['Close']) if pd.notna(row['Close']) else "0",
                    "volume": str(row['Volume']) if pd.notna(row['Volume']) else "0",
                    "source": "yahoo_finance",
                    "created_at": datetime.utcnow().isoformat() + "Z"
                }
                market_data.append(market_data_item)
                
            logger.info(
                "Yahoo Finance data fetched successfully",
                symbol=symbol,
                records_count=len(market_data)
            )
            
            return market_data
            
        except Exception as e:
            logger.error("Failed to fetch Yahoo Finance data", symbol=symbol, error=str(e))
            return []
            
    async def fetch_alpha_vantage_data(self, symbol: str, interval: str = "5min") -> List[Dict]:
        """Fetch data from Alpha Vantage API"""
        if not settings.ALPHA_VANTAGE_API_KEY:
            logger.debug("Alpha Vantage API key not configured, skipping")
            return []
            
        try:
            # Map interval to Alpha Vantage format
            av_interval_map = {
                "1m": "1min",
                "5m": "5min", 
                "15m": "15min",
                "30m": "30min",
                "1h": "60min"
            }
            av_interval = av_interval_map.get(interval, "5min")
            
            url = "https://www.alphavantage.co/query"
            params = {
                "function": "TIME_SERIES_INTRADAY",
                "symbol": symbol,
                "interval": av_interval,
                "apikey": settings.ALPHA_VANTAGE_API_KEY,
                "outputsize": "compact"
            }
            
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    time_series_key = f"Time Series ({av_interval})"
                    if time_series_key not in data:
                        logger.warning("No time series data in Alpha Vantage response", symbol=symbol)
                        return []
                    
                    market_data = []
                    time_series = data[time_series_key]
                    
                    for timestamp_str, values in time_series.items():
                        dt = datetime.fromisoformat(timestamp_str)
                        normalized_symbol = self._normalize_symbol(symbol)
                        
                        market_data_item = {
                            "id": f"{normalized_symbol}_{interval}_{int(dt.timestamp())}",
                            "symbol": symbol,
                            "normalized_symbol": normalized_symbol,
                            "asset_type": "stock_index",
                            "interval": interval,
                            "timestamp": dt.isoformat() + "Z",
                            "open_price": values["1. open"],
                            "high_price": values["2. high"],
                            "low_price": values["3. low"],
                            "close_price": values["4. close"],
                            "volume": values["5. volume"],
                            "source": "alpha_vantage",
                            "created_at": datetime.utcnow().isoformat() + "Z"
                        }
                        market_data.append(market_data_item)
                        
                    logger.info(
                        "Alpha Vantage data fetched successfully",
                        symbol=symbol,
                        records_count=len(market_data)
                    )
                    
                    return market_data
                else:
                    logger.error("Alpha Vantage API error", status=response.status, symbol=symbol)
                    return []
                    
        except Exception as e:
            logger.error("Failed to fetch Alpha Vantage data", symbol=symbol, error=str(e))
            return []
            
    async def fetch_current_index_values(self) -> List[Dict]:
        """Fetch current values for all tracked indices from database"""
        current_data = []
        
        for symbol in self.tracked_indices:
            try:
                # Use Yahoo Finance for real-time data
                def get_current_data():
                    ticker = yf.Ticker(symbol)
                    info = ticker.info
                    hist = ticker.history(period="1d", interval="1m")
                    return info, hist
                
                loop = asyncio.get_event_loop()
                info, hist = await loop.run_in_executor(None, get_current_data)
                
                if not hist.empty:
                    latest = hist.iloc[-1]
                    current_time = datetime.utcnow()
                    normalized_symbol = self._normalize_symbol(symbol)
                    
                    # Get additional info from ticker info
                    current_price = latest['Close']
                    previous_close = info.get('previousClose', latest['Open'])
                    change = current_price - previous_close
                    change_percent = (change / previous_close * 100) if previous_close != 0 else 0
                    
                    current_data_item = {
                        "id": f"{normalized_symbol}_current_{int(current_time.timestamp())}",
                        "symbol": symbol,
                        "normalized_symbol": normalized_symbol,
                        "asset_type": "stock_index_current",
                        "timestamp": current_time.isoformat() + "Z",
                        "current_price": float(current_price),
                        "previous_close": float(previous_close),
                        "change": float(change),
                        "change_percent": float(change_percent),
                        "volume": int(latest['Volume']) if pd.notna(latest['Volume']) else 0,
                        "market_cap": info.get('marketCap'),
                        "day_high": float(latest['High']) if pd.notna(latest['High']) else None,
                        "day_low": float(latest['Low']) if pd.notna(latest['Low']) else None,
                        "source": "yahoo_finance",
                        "metadata": {
                            "full_name": info.get('longName', symbol),
                            "currency": info.get('currency', 'USD'),
                            "exchange": info.get('exchange', 'Unknown'),
                            "market_state": info.get('marketState', 'Unknown')
                        },
                        "created_at": current_time.isoformat() + "Z"
                    }
                    
                    current_data.append(current_data_item)
                    
                    logger.info(
                        "Current index value fetched",
                        symbol=symbol,
                        price=current_price,
                        change_percent=round(change_percent, 2)
                    )
                
                # Small delay between requests
                await asyncio.sleep(0.1)
                
            except Exception as e:
                logger.error("Failed to fetch current data", symbol=symbol, error=str(e))
                
        return current_data
        
    async def collect_historical_index_data(self, symbol: str, days_back: int = None) -> int:
        """Collect historical data for a specific stock index"""
        if days_back is None:
            days_back = settings.STOCK_INDEX_HISTORICAL_DAYS
            
        logger.info(
            "Starting historical index data collection",
            symbol=symbol,
            days_back=days_back
        )
        
        total_records = 0
        
        try:
            # Collect daily data for longer periods
            if days_back > 30:
                daily_data = await self.fetch_yahoo_finance_data(symbol, f"{days_back}d", "1d")
                if daily_data:
                    # Store in batches
                    batch_size = 100
                    for i in range(0, len(daily_data), batch_size):
                        batch = daily_data[i:i + batch_size]
                        await self.database.upsert_market_data_batch(batch)
                        total_records += len(batch)
                        
            # Collect intraday data for recent periods (last 30 days)
            recent_data = await self.fetch_yahoo_finance_data(symbol, "30d", "5m")
            if recent_data:
                batch_size = 500
                for i in range(0, len(recent_data), batch_size):
                    batch = recent_data[i:i + batch_size]
                    await self.database.upsert_market_data_batch(batch)
                    total_records += len(batch)
                    
            logger.info(
                "Historical index data collection completed",
                symbol=symbol,
                total_records=total_records
            )
            
        except Exception as e:
            logger.error("Error collecting historical index data", symbol=symbol, error=str(e))
            
        return total_records
        
    async def collect_all_index_data(self) -> Dict[str, Any]:
        """Collect data for all configured stock indices"""
        results = {
            "historical_data": {},
            "current_data": [],
            "total_records": 0
        }
        
        if not settings.STOCK_INDEX_ENABLED:
            logger.info("Stock index data collection is disabled")
            return results
            
        logger.info("Starting comprehensive index data collection")
        
        # Collect current values for all indices
        try:
            current_data = await self.fetch_current_index_values()
            results["current_data"] = current_data
            
            # Store current data
            if current_data:
                for item in current_data:
                    await self.database.upsert_market_data(item)
                    
        except Exception as e:
            logger.error("Error collecting current index data", error=str(e))
            
        # Collect historical data for each tracked index
        for symbol in self.tracked_indices:
            try:
                # Check if we already have recent data
                existing_data = await self.database.get_market_data_for_analysis(
                    symbol=symbol,
                    interval="1d",
                    hours_back=48
                )
                
                if len(existing_data) < 2:  # If we don't have recent data
                    record_count = await self.collect_historical_index_data(symbol)
                    results["historical_data"][symbol] = record_count
                    results["total_records"] += record_count
                else:
                    logger.info(f"Recent data exists for {symbol}, skipping historical collection")
                    results["historical_data"][symbol] = 0
                    
                # Small delay between symbols
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error("Failed to collect data for index", symbol=symbol, error=str(e))
                results["historical_data"][symbol] = 0
                
        logger.info(
            "Index data collection completed",
            total_records=results["total_records"],
            current_data_count=len(results["current_data"]),
            indices_processed=len(results["historical_data"])
        )
        
        return results
        
    async def get_index_correlation_data(self, crypto_symbols: List[str] = None) -> Dict[str, Any]:
        """Get correlation data between stock indices and crypto markets"""
        try:
            if crypto_symbols is None:
                crypto_symbols = [symbol[:-4] for symbol in settings.DEFAULT_SYMBOLS[:5]]  # Top 5 cryptos
                
            correlation_data = {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "correlations": {},
                "market_summary": {}
            }
            
            # Get recent performance for stock indices
            for category, indices in self.index_categories.items():
                category_performance = []
                
                for index_symbol in indices:
                    try:
                        # Get last 24h data
                        recent_data = await self.database.get_market_data_for_analysis(
                            symbol=index_symbol,
                            interval="1h",
                            hours_back=24
                        )
                        
                        if len(recent_data) >= 2:
                            latest_price = float(recent_data[-1]['close_price'])
                            previous_price = float(recent_data[0]['close_price'])
                            change_24h = ((latest_price - previous_price) / previous_price) * 100
                            
                            category_performance.append({
                                "symbol": index_symbol,
                                "change_24h": change_24h,
                                "current_price": latest_price
                            })
                            
                    except Exception as e:
                        logger.error(f"Error calculating performance for {index_symbol}", error=str(e))
                        
                correlation_data["market_summary"][category] = category_performance
                
            # Simple correlation analysis (can be enhanced with more sophisticated methods)
            if correlation_data["market_summary"].get("us_major"):
                us_avg_change = sum(item["change_24h"] for item in correlation_data["market_summary"]["us_major"]) / len(correlation_data["market_summary"]["us_major"])
                correlation_data["correlations"]["us_market_trend"] = {
                    "direction": "bullish" if us_avg_change > 0 else "bearish",
                    "strength": abs(us_avg_change),
                    "avg_change_24h": us_avg_change
                }
                
            return correlation_data
            
        except Exception as e:
            logger.error("Error calculating index correlation data", error=str(e))
            return {}

# Example usage
async def main():
    """Example usage of the stock index data collector"""
    database = Database()
    
    async with database, StockIndexDataCollector(database) as collector:
        # Collect all index data
        results = await collector.collect_all_index_data()
        
        print("Stock index data collection results:")
        print(f"Total records: {results['total_records']}")
        print(f"Current data points: {len(results['current_data'])}")
        
        for symbol, count in results["historical_data"].items():
            print(f"{symbol}: {count} historical records")
            
        # Get correlation data
        correlation = await collector.get_index_correlation_data()
        print(f"\nMarket correlation analysis: {len(correlation.get('correlations', {}))} correlations calculated")

if __name__ == "__main__":
    asyncio.run(main())