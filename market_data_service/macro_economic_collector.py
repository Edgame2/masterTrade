"""
Macro-Economic Data Collector for Market Data Service

This module collects macro-economic indicators from various free and paid sources:
- Interest rates (Federal Reserve, ECB, Bank of England, Bank of Japan)
- Inflation data (CPI, PPI)
- GDP growth rates
- Central bank policy decisions
- Commodity prices (Gold, Silver, Oil, Natural Gas)
- Currency strength indices (DXY, EUR, JPY, GBP)
- Economic calendar events
- Treasury yields

Data Sources:
- FRED API (Federal Reserve Economic Data) - Primary, free
- Yahoo Finance - Commodities and currencies
- Alpha Vantage - Economic indicators (requires API key)
- Financial Modeling Prep - Economic calendar (requires API key)
"""

import asyncio
import aiohttp
import yfinance as yf
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any, Tuple
import pandas as pd
import structlog
from enum import Enum

from config import settings
from database import Database

logger = structlog.get_logger()


class IndicatorCategory(str, Enum):
    """Categories of macro-economic indicators"""
    INTEREST_RATE = "interest_rate"
    INFLATION = "inflation"
    GDP = "gdp"
    EMPLOYMENT = "employment"
    COMMODITY = "commodity"
    CURRENCY = "currency"
    CENTRAL_BANK = "central_bank"
    TREASURY = "treasury_yield"
    ECONOMIC_CALENDAR = "economic_calendar"


class IndicatorImportance(str, Enum):
    """Importance level of economic indicators"""
    CRITICAL = "critical"      # Fed rate decisions, NFP
    HIGH = "high"              # CPI, GDP
    MEDIUM = "medium"          # PMI, retail sales
    LOW = "low"                # Minor releases


class MacroEconomicCollector:
    """Collects macro-economic data from multiple sources"""
    
    # Commodity symbols for Yahoo Finance
    COMMODITY_SYMBOLS = {
        "GC=F": {"name": "Gold", "unit": "USD/oz"},
        "SI=F": {"name": "Silver", "unit": "USD/oz"},
        "CL=F": {"name": "Crude Oil WTI", "unit": "USD/barrel"},
        "BZ=F": {"name": "Brent Crude Oil", "unit": "USD/barrel"},
        "NG=F": {"name": "Natural Gas", "unit": "USD/MMBtu"},
        "HG=F": {"name": "Copper", "unit": "USD/lb"},
    }
    
    # Currency indices and pairs
    CURRENCY_SYMBOLS = {
        "DX-Y.NYB": {"name": "US Dollar Index (DXY)", "type": "index"},
        "EURUSD=X": {"name": "EUR/USD", "type": "pair"},
        "GBPUSD=X": {"name": "GBP/USD", "type": "pair"},
        "USDJPY=X": {"name": "USD/JPY", "type": "pair"},
        "AUDUSD=X": {"name": "AUD/USD", "type": "pair"},
        "USDCAD=X": {"name": "USD/CAD", "type": "pair"},
        "USDCHF=X": {"name": "USD/CHF", "type": "pair"},
    }
    
    # Treasury yields
    TREASURY_SYMBOLS = {
        "^IRX": {"name": "13 Week Treasury", "maturity": "3M"},
        "^FVX": {"name": "5 Year Treasury", "maturity": "5Y"},
        "^TNX": {"name": "10 Year Treasury", "maturity": "10Y"},
        "^TYX": {"name": "30 Year Treasury", "maturity": "30Y"},
    }
    
    # FRED API indicators (if FRED_API_KEY is set)
    FRED_INDICATORS = {
        # Interest Rates
        "DFF": {"name": "Federal Funds Rate", "category": IndicatorCategory.INTEREST_RATE, "importance": IndicatorImportance.CRITICAL},
        "FEDFUNDS": {"name": "Effective Federal Funds Rate", "category": IndicatorCategory.INTEREST_RATE, "importance": IndicatorImportance.CRITICAL},
        
        # Inflation
        "CPIAUCSL": {"name": "Consumer Price Index (CPI)", "category": IndicatorCategory.INFLATION, "importance": IndicatorImportance.HIGH},
        "CPILFESL": {"name": "Core CPI (Ex Food & Energy)", "category": IndicatorCategory.INFLATION, "importance": IndicatorImportance.HIGH},
        "PPIACO": {"name": "Producer Price Index (PPI)", "category": IndicatorCategory.INFLATION, "importance": IndicatorImportance.HIGH},
        
        # GDP
        "GDP": {"name": "Gross Domestic Product", "category": IndicatorCategory.GDP, "importance": IndicatorImportance.HIGH},
        "A191RL1Q225SBEA": {"name": "Real GDP Growth Rate", "category": IndicatorCategory.GDP, "importance": IndicatorImportance.HIGH},
        
        # Employment
        "UNRATE": {"name": "Unemployment Rate", "category": IndicatorCategory.EMPLOYMENT, "importance": IndicatorImportance.HIGH},
        "PAYEMS": {"name": "Nonfarm Payrolls", "category": IndicatorCategory.EMPLOYMENT, "importance": IndicatorImportance.CRITICAL},
        "ICSA": {"name": "Initial Jobless Claims", "category": IndicatorCategory.EMPLOYMENT, "importance": IndicatorImportance.MEDIUM},
        
        # Other
        "VIXCLS": {"name": "VIX Volatility Index", "category": IndicatorCategory.COMMODITY, "importance": IndicatorImportance.HIGH},
    }
    
    def __init__(self, database: Database):
        self.database = database
        self.session: Optional[aiohttp.ClientSession] = None
        self.fred_api_key = settings.FRED_API_KEY if hasattr(settings, 'FRED_API_KEY') else None
        self.alpha_vantage_key = settings.ALPHA_VANTAGE_API_KEY if hasattr(settings, 'ALPHA_VANTAGE_API_KEY') else None
        
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
            
        logger.info("Macro-economic collector initialized")
            
    async def disconnect(self):
        """Close HTTP session"""
        if self.session:
            await self.session.close()
            self.session = None
            
    async def fetch_commodities_data(self) -> List[Dict[str, Any]]:
        """Fetch current commodity prices from Yahoo Finance"""
        try:
            logger.info("Fetching commodity prices")
            
            commodity_data = []
            current_time = datetime.utcnow()
            
            for symbol, info in self.COMMODITY_SYMBOLS.items():
                try:
                    # Fetch current price
                    def get_commodity_data():
                        ticker = yf.Ticker(symbol)
                        hist = ticker.history(period="1d", interval="1m")
                        ticker_info = ticker.info
                        return hist, ticker_info
                    
                    loop = asyncio.get_event_loop()
                    hist, ticker_info = await loop.run_in_executor(None, get_commodity_data)
                    
                    if not hist.empty:
                        latest = hist.iloc[-1]
                        previous_close = ticker_info.get('previousClose', hist.iloc[0]['Close'])
                        current_price = latest['Close']
                        
                        change = current_price - previous_close
                        change_percent = (change / previous_close * 100) if previous_close != 0 else 0
                        
                        commodity_item = {
                            "id": f"commodity_{symbol.replace('=', '_').replace('-', '_')}_{int(current_time.timestamp())}",
                            "doc_type": "macro_economic_data",
                            "category": IndicatorCategory.COMMODITY,
                            "symbol": symbol,
                            "name": info["name"],
                            "unit": info["unit"],
                            "current_value": float(current_price),
                            "previous_value": float(previous_close),
                            "change": float(change),
                            "change_percent": float(change_percent),
                            "day_high": float(latest['High']) if pd.notna(latest['High']) else None,
                            "day_low": float(latest['Low']) if pd.notna(latest['Low']) else None,
                            "volume": int(latest['Volume']) if pd.notna(latest['Volume']) else 0,
                            "timestamp": current_time.isoformat() + "Z",
                            "source": "yahoo_finance",
                            "created_at": current_time.isoformat() + "Z"
                        }
                        
                        commodity_data.append(commodity_item)
                        
                        logger.info(
                            "Commodity data fetched",
                            symbol=symbol,
                            name=info["name"],
                            price=round(current_price, 2),
                            change_percent=round(change_percent, 2)
                        )
                    
                    await asyncio.sleep(0.5)
                    
                except Exception as e:
                    logger.error(f"Error fetching commodity {symbol}", error=str(e))
            
            return commodity_data
            
        except Exception as e:
            logger.error("Error fetching commodities data", error=str(e))
            return []
    
    async def fetch_currencies_data(self) -> List[Dict[str, Any]]:
        """Fetch currency indices and pairs from Yahoo Finance"""
        try:
            logger.info("Fetching currency data")
            
            currency_data = []
            current_time = datetime.utcnow()
            
            for symbol, info in self.CURRENCY_SYMBOLS.items():
                try:
                    def get_currency_data():
                        ticker = yf.Ticker(symbol)
                        hist = ticker.history(period="1d", interval="1m")
                        ticker_info = ticker.info
                        return hist, ticker_info
                    
                    loop = asyncio.get_event_loop()
                    hist, ticker_info = await loop.run_in_executor(None, get_currency_data)
                    
                    if not hist.empty:
                        latest = hist.iloc[-1]
                        previous_close = ticker_info.get('previousClose', hist.iloc[0]['Close'])
                        current_price = latest['Close']
                        
                        change = current_price - previous_close
                        change_percent = (change / previous_close * 100) if previous_close != 0 else 0
                        
                        currency_item = {
                            "id": f"currency_{symbol.replace('=', '_').replace('-', '_').replace('.', '_')}_{int(current_time.timestamp())}",
                            "doc_type": "macro_economic_data",
                            "category": IndicatorCategory.CURRENCY,
                            "symbol": symbol,
                            "name": info["name"],
                            "type": info["type"],
                            "current_value": float(current_price),
                            "previous_value": float(previous_close),
                            "change": float(change),
                            "change_percent": float(change_percent),
                            "day_high": float(latest['High']) if pd.notna(latest['High']) else None,
                            "day_low": float(latest['Low']) if pd.notna(latest['Low']) else None,
                            "timestamp": current_time.isoformat() + "Z",
                            "source": "yahoo_finance",
                            "created_at": current_time.isoformat() + "Z"
                        }
                        
                        currency_data.append(currency_item)
                        
                        logger.info(
                            "Currency data fetched",
                            symbol=symbol,
                            name=info["name"],
                            price=round(current_price, 4),
                            change_percent=round(change_percent, 2)
                        )
                    
                    await asyncio.sleep(0.5)
                    
                except Exception as e:
                    logger.error(f"Error fetching currency {symbol}", error=str(e))
            
            return currency_data
            
        except Exception as e:
            logger.error("Error fetching currencies data", error=str(e))
            return []
    
    async def fetch_treasury_yields(self) -> List[Dict[str, Any]]:
        """Fetch US Treasury yields from Yahoo Finance"""
        try:
            logger.info("Fetching treasury yields")
            
            treasury_data = []
            current_time = datetime.utcnow()
            
            for symbol, info in self.TREASURY_SYMBOLS.items():
                try:
                    def get_treasury_data():
                        ticker = yf.Ticker(symbol)
                        hist = ticker.history(period="5d", interval="1d")
                        return hist
                    
                    loop = asyncio.get_event_loop()
                    hist = await loop.run_in_executor(None, get_treasury_data)
                    
                    if len(hist) >= 2:
                        latest = hist.iloc[-1]
                        previous = hist.iloc[-2]
                        
                        current_yield = latest['Close']
                        previous_yield = previous['Close']
                        change = current_yield - previous_yield
                        
                        treasury_item = {
                            "id": f"treasury_{symbol.replace('^', '')}_{int(current_time.timestamp())}",
                            "doc_type": "macro_economic_data",
                            "category": IndicatorCategory.TREASURY,
                            "symbol": symbol,
                            "name": info["name"],
                            "maturity": info["maturity"],
                            "current_yield": float(current_yield),
                            "previous_yield": float(previous_yield),
                            "change_bps": float(change * 100),  # Convert to basis points
                            "timestamp": current_time.isoformat() + "Z",
                            "source": "yahoo_finance",
                            "importance": IndicatorImportance.HIGH,
                            "created_at": current_time.isoformat() + "Z"
                        }
                        
                        treasury_data.append(treasury_item)
                        
                        logger.info(
                            "Treasury yield fetched",
                            symbol=symbol,
                            maturity=info["maturity"],
                            yield_value=round(current_yield, 3),
                            change_bps=round(change * 100, 1)
                        )
                    
                    await asyncio.sleep(0.5)
                    
                except Exception as e:
                    logger.error(f"Error fetching treasury {symbol}", error=str(e))
            
            return treasury_data
            
        except Exception as e:
            logger.error("Error fetching treasury yields", error=str(e))
            return []
    
    async def fetch_fred_indicators(self) -> List[Dict[str, Any]]:
        """Fetch economic indicators from FRED API"""
        if not self.fred_api_key:
            logger.debug("FRED API key not configured, skipping FRED data")
            return []
        
        try:
            logger.info("Fetching FRED economic indicators")
            
            fred_data = []
            current_time = datetime.utcnow()
            
            # FRED API base URL
            base_url = "https://api.stlouisfed.org/fred/series/observations"
            
            for series_id, info in self.FRED_INDICATORS.items():
                try:
                    # Get last 2 observations to calculate change
                    params = {
                        "series_id": series_id,
                        "api_key": self.fred_api_key,
                        "file_type": "json",
                        "sort_order": "desc",
                        "limit": 2
                    }
                    
                    async with self.session.get(base_url, params=params) as response:
                        if response.status == 200:
                            data = await response.json()
                            observations = data.get("observations", [])
                            
                            if observations:
                                latest = observations[0]
                                previous = observations[1] if len(observations) > 1 else latest
                                
                                current_value = float(latest["value"]) if latest["value"] != "." else None
                                previous_value = float(previous["value"]) if previous["value"] != "." else None
                                
                                if current_value is not None:
                                    change = (current_value - previous_value) if previous_value else 0
                                    change_percent = ((change / previous_value) * 100) if previous_value and previous_value != 0 else 0
                                    
                                    fred_item = {
                                        "id": f"fred_{series_id}_{int(current_time.timestamp())}",
                                        "doc_type": "macro_economic_data",
                                        "category": info["category"],
                                        "series_id": series_id,
                                        "name": info["name"],
                                        "current_value": current_value,
                                        "previous_value": previous_value,
                                        "change": change,
                                        "change_percent": change_percent,
                                        "observation_date": latest["date"],
                                        "importance": info["importance"],
                                        "timestamp": current_time.isoformat() + "Z",
                                        "source": "fred",
                                        "created_at": current_time.isoformat() + "Z"
                                    }
                                    
                                    fred_data.append(fred_item)
                                    
                                    logger.info(
                                        "FRED indicator fetched",
                                        series_id=series_id,
                                        name=info["name"],
                                        value=round(current_value, 2)
                                    )
                        else:
                            logger.warning(f"FRED API error for {series_id}", status=response.status)
                    
                    await asyncio.sleep(0.5)  # Rate limiting
                    
                except Exception as e:
                    logger.error(f"Error fetching FRED indicator {series_id}", error=str(e))
            
            return fred_data
            
        except Exception as e:
            logger.error("Error fetching FRED indicators", error=str(e))
            return []
    
    async def fetch_crypto_fear_greed_index(self) -> Optional[Dict[str, Any]]:
        """Fetch Crypto Fear & Greed Index from alternative.me"""
        try:
            logger.info("Fetching Crypto Fear & Greed Index")
            
            url = "https://api.alternative.me/fng/"
            
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    if data.get("data"):
                        latest = data["data"][0]
                        
                        current_time = datetime.utcnow()
                        
                        fear_greed_item = {
                            "id": f"fear_greed_{int(current_time.timestamp())}",
                            "doc_type": "macro_economic_data",
                            "category": "sentiment",
                            "name": "Crypto Fear & Greed Index",
                            "value": int(latest["value"]),
                            "classification": latest["value_classification"],
                            "timestamp": current_time.isoformat() + "Z",
                            "source": "alternative.me",
                            "importance": IndicatorImportance.HIGH,
                            "created_at": current_time.isoformat() + "Z"
                        }
                        
                        logger.info(
                            "Fear & Greed Index fetched",
                            value=latest["value"],
                            classification=latest["value_classification"]
                        )
                        
                        return fear_greed_item
                else:
                    logger.warning("Fear & Greed API error", status=response.status)
                    
        except Exception as e:
            logger.error("Error fetching Fear & Greed Index", error=str(e))
        
        return None
    
    async def collect_all_macro_data(self) -> Dict[str, Any]:
        """Collect all macro-economic data from all sources"""
        results = {
            "commodities": [],
            "currencies": [],
            "treasuries": [],
            "fred_indicators": [],
            "fear_greed": None,
            "total_indicators": 0,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
        
        logger.info("Starting comprehensive macro-economic data collection")
        
        try:
            # Collect from all sources concurrently
            commodities_task = self.fetch_commodities_data()
            currencies_task = self.fetch_currencies_data()
            treasuries_task = self.fetch_treasury_yields()
            fred_task = self.fetch_fred_indicators()
            fear_greed_task = self.fetch_crypto_fear_greed_index()
            
            # Await all tasks
            commodities, currencies, treasuries, fred_data, fear_greed = await asyncio.gather(
                commodities_task,
                currencies_task,
                treasuries_task,
                fred_task,
                fear_greed_task,
                return_exceptions=True
            )
            
            # Handle results (check for exceptions)
            results["commodities"] = commodities if not isinstance(commodities, Exception) else []
            results["currencies"] = currencies if not isinstance(currencies, Exception) else []
            results["treasuries"] = treasuries if not isinstance(treasuries, Exception) else []
            results["fred_indicators"] = fred_data if not isinstance(fred_data, Exception) else []
            results["fear_greed"] = fear_greed if not isinstance(fear_greed, Exception) else None
            
            # Store all data in database
            all_data = (
                results["commodities"] +
                results["currencies"] +
                results["treasuries"] +
                results["fred_indicators"]
            )
            
            if results["fear_greed"]:
                all_data.append(results["fear_greed"])
            
            # Batch insert
            if all_data:
                batch_size = 50
                for i in range(0, len(all_data), batch_size):
                    batch = all_data[i:i + batch_size]
                    await self.database.upsert_market_data_batch(batch)
            
            results["total_indicators"] = len(all_data)
            
            logger.info(
                "Macro-economic data collection completed",
                commodities=len(results["commodities"]),
                currencies=len(results["currencies"]),
                treasuries=len(results["treasuries"]),
                fred_indicators=len(results["fred_indicators"]),
                fear_greed=1 if results["fear_greed"] else 0,
                total=results["total_indicators"]
            )
            
        except Exception as e:
            logger.error("Error in macro-economic data collection", error=str(e))
        
        return results
    
    async def get_macro_summary(self) -> Dict[str, Any]:
        """Get a summary of current macro-economic conditions"""
        try:
            summary = {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "risk_environment": "unknown",
                "inflation_trend": "unknown",
                "growth_outlook": "unknown",
                "key_indicators": {},
                "market_sentiment": "neutral"
            }
            
            # Query recent macro data
            query = """
            SELECT * FROM c 
            WHERE c.doc_type = 'macro_economic_data' 
            AND c.timestamp > @since
            ORDER BY c.timestamp DESC
            """
            
            one_day_ago = (datetime.utcnow() - timedelta(days=1)).isoformat() + "Z"
            
            results = list(self.database.container.query_items(
                query=query,
                parameters=[{"name": "@since", "value": one_day_ago}],
                enable_cross_partition_query=True
            ))
            
            if results:
                # Analyze VIX for risk environment
                vix_data = [r for r in results if r.get("series_id") == "VIXCLS" or r.get("symbol") == "^VIX"]
                if vix_data:
                    vix_value = vix_data[0].get("current_value", 20)
                    if vix_value < 15:
                        summary["risk_environment"] = "low_risk"
                    elif vix_value < 25:
                        summary["risk_environment"] = "moderate_risk"
                    else:
                        summary["risk_environment"] = "high_risk"
                    summary["key_indicators"]["VIX"] = vix_value
                
                # Analyze DXY for dollar strength
                dxy_data = [r for r in results if "DX-Y" in r.get("symbol", "")]
                if dxy_data:
                    dxy_value = dxy_data[0].get("current_value")
                    dxy_change = dxy_data[0].get("change_percent", 0)
                    summary["key_indicators"]["DXY"] = {
                        "value": dxy_value,
                        "change_percent": dxy_change,
                        "trend": "strengthening" if dxy_change > 0 else "weakening"
                    }
                
                # Analyze Gold for safe haven demand
                gold_data = [r for r in results if "GC=F" in r.get("symbol", "")]
                if gold_data:
                    gold_value = gold_data[0].get("current_value")
                    gold_change = gold_data[0].get("change_percent", 0)
                    summary["key_indicators"]["Gold"] = {
                        "value": gold_value,
                        "change_percent": gold_change,
                        "trend": "rising" if gold_change > 0 else "falling"
                    }
                
                # Get Fear & Greed
                fg_data = [r for r in results if r.get("name") == "Crypto Fear & Greed Index"]
                if fg_data:
                    fg_value = fg_data[0].get("value")
                    fg_class = fg_data[0].get("classification", "neutral")
                    summary["market_sentiment"] = fg_class.lower()
                    summary["key_indicators"]["Fear_Greed"] = fg_value
            
            return summary
            
        except Exception as e:
            logger.error("Error generating macro summary", error=str(e))
            return {"error": str(e)}


# Example usage
async def main():
    """Example usage of the macro-economic collector"""
    database = Database()
    
    async with database, MacroEconomicCollector(database) as collector:
        # Collect all macro data
        results = await collector.collect_all_macro_data()
        
        print("\nMacro-Economic Data Collection Results:")
        print(f"Commodities: {len(results['commodities'])}")
        print(f"Currencies: {len(results['currencies'])}")
        print(f"Treasury Yields: {len(results['treasuries'])}")
        print(f"FRED Indicators: {len(results['fred_indicators'])}")
        print(f"Fear & Greed: {'Yes' if results['fear_greed'] else 'No'}")
        print(f"Total Indicators: {results['total_indicators']}")
        
        # Get macro summary
        summary = await collector.get_macro_summary()
        print(f"\nMacro Summary:")
        print(f"Risk Environment: {summary.get('risk_environment')}")
        print(f"Market Sentiment: {summary.get('market_sentiment')}")
        print(f"Key Indicators: {summary.get('key_indicators')}")


if __name__ == "__main__":
    asyncio.run(main())
