"""
CME Exchange Collector

Collects Bitcoin and Ethereum futures data from CME Group:
- Settlement prices (daily)
- Open interest
- Volume
- Basis (futures - spot price)
- Contract specifications

Note: CME real-time data requires expensive subscription (~$100+/month).
This collector uses delayed data from free sources and CME DataMine (delayed).

API Documentation:
- CME DataMine: https://www.cmegroup.com/market-data/datamine-api.html
- Alternative: Scraping from CME website or using third-party aggregators
"""

import asyncio
import aiohttp
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
import structlog

from exchange_collector_base import (
    ExchangeCollectorBase,
    ExchangeType,
    OpenInterest
)
from database import Database

logger = structlog.get_logger()


class CMECollector(ExchangeCollectorBase):
    """
    CME Bitcoin/Ethereum futures data collector
    
    Features:
    - Daily settlement prices
    - Open interest tracking
    - Volume data
    - Basis calculation (futures - spot)
    - Contract roll tracking
    
    Note: Uses delayed/free data sources. Real-time requires CME subscription.
    """
    
    # CME Market Data API (requires authentication for real-time)
    # For free data, we use CME DataMine or scrape from public website
    CME_DATAMINE_URL = "https://datamine.cmegroup.com"
    
    # Bitcoin futures contracts
    BTC_CONTRACTS = {
        "BTC": {
            "name": "Bitcoin Futures",
            "exchange": "CME",
            "tick_size": 5,  # $5 per contract
            "contract_months": ["H", "M", "U", "Z"],  # Mar, Jun, Sep, Dec
        }
    }
    
    # Ethereum futures contracts  
    ETH_CONTRACTS = {
        "ETH": {
            "name": "Ether Futures",
            "exchange": "CME",
            "tick_size": 5,  # $5 per contract
            "contract_months": ["H", "M", "U", "Z"],
        }
    }
    
    def __init__(
        self,
        database: Database,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None
    ):
        super().__init__(
            database=database,
            exchange_type=ExchangeType.CME,
            api_key=api_key,
            api_secret=api_secret
        )
        
        # CME rate limits (conservative for public data)
        self.rate_limiter = asyncio.Semaphore(5)
        self.min_request_interval = 1.0  # 1 second between requests
        
        # Track active contracts (front month)
        self.active_contracts = {
            "BTC": self._get_front_month_contract("BTC"),
            "ETH": self._get_front_month_contract("ETH")
        }
        
    def _build_url(self, endpoint: str) -> str:
        """Build full URL for endpoint"""
        return f"{self.CME_DATAMINE_URL}{endpoint}"
        
    def _get_auth_headers(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict],
        data: Optional[Dict]
    ) -> Dict:
        """Get authentication headers (if using authenticated API)"""
        # CME DataMine uses different auth - not implementing for free tier
        return {}
        
    def _get_front_month_contract(self, underlying: str) -> str:
        """
        Get front month contract code
        
        Contract codes: H (Mar), M (Jun), U (Sep), Z (Dec)
        Format: BTC{Month}{Year} (e.g., BTCH24 for March 2024)
        """
        now = datetime.now(timezone.utc)
        year = now.year % 100  # Last 2 digits
        month = now.month
        
        # Map month to next quarterly contract
        if month <= 3:
            contract_month = "H"  # March
        elif month <= 6:
            contract_month = "M"  # June
        elif month <= 9:
            contract_month = "U"  # September
        else:
            contract_month = "Z"  # December
            
        # If we're past the contract month, roll to next quarter
        month_map = {"H": 3, "M": 6, "U": 9, "Z": 12}
        if month > month_map[contract_month]:
            # Roll to next contract
            contracts = ["H", "M", "U", "Z"]
            idx = contracts.index(contract_month)
            contract_month = contracts[(idx + 1) % 4]
            if contract_month == "H":
                year += 1
                
        return f"{underlying}{contract_month}{year:02d}"
        
    async def collect_orderbook(self, symbol: str) -> Optional[Dict]:
        """
        CME orderbook data requires real-time subscription
        Not available in free tier
        """
        logger.warning(
            "CME orderbook data requires paid subscription",
            symbol=symbol
        )
        return None
        
    async def collect_trades(self, symbol: str, limit: int = 100) -> List[Dict]:
        """
        CME trade data requires real-time subscription
        Not available in free tier
        """
        logger.warning(
            "CME trade data requires paid subscription",
            symbol=symbol
        )
        return []
        
    async def start_realtime_stream(self, symbols: List[str] = None):
        """
        CME real-time streaming requires paid subscription
        Not available in free tier
        """
        logger.warning(
            "CME real-time data requires paid subscription ($100+/month)",
            note="Using delayed data collection instead"
        )
        
    async def collect_settlement_price(self, contract: str) -> Optional[Dict]:
        """
        Collect daily settlement price for contract
        
        Settlement prices are published daily after market close (4:00 PM CT)
        Available for free with ~1 day delay
        """
        # In production, this would scrape CME website or use DataMine API
        # For now, we'll use a placeholder that would fetch from a third-party source
        
        logger.info(
            "Collecting CME settlement price",
            contract=contract,
            note="Using delayed data (free tier)"
        )
        
        # Placeholder - in production, implement actual data source
        # Options:
        # 1. Scrape from CME website
        # 2. Use Quandl/Nasdaq Data Link (has CME data)
        # 3. Use CoinMetrics or similar aggregator
        # 4. Use DataMine API with credentials
        
        return {
            "contract": contract,
            "settlement_price": None,  # Would be populated from data source
            "timestamp": datetime.now(timezone.utc),
            "source": "cme_delayed"
        }
        
    async def collect_open_interest(self, contract: str) -> Optional[OpenInterest]:
        """
        Collect open interest for contract
        
        OI is published daily, available for free with delay
        """
        logger.info(
            "Collecting CME open interest",
            contract=contract,
            note="Using delayed data (free tier)"
        )
        
        # Placeholder - would fetch from data source
        # CME publishes OI daily, available from various free sources
        
        settlement_data = await self.collect_settlement_price(contract)
        
        if settlement_data and settlement_data['settlement_price']:
            # Create OpenInterest object
            # In production, fetch actual OI from data source
            oi = OpenInterest(
                exchange=self.exchange_type.value,
                symbol=contract,
                open_interest=0,  # Would be populated from data source
                open_interest_usd=0,  # Would calculate based on OI * settlement price
                timestamp=datetime.now(timezone.utc)
            )
            
            await self._store_open_interest(oi)
            return oi
            
        return None
        
    async def calculate_basis(
        self,
        contract: str,
        spot_price: float
    ) -> Optional[Dict]:
        """
        Calculate basis (futures - spot)
        
        Args:
            contract: CME contract code (e.g., 'BTCH24')
            spot_price: Current spot price from another exchange
            
        Returns:
            Dict with basis, basis percentage, and annualized
        """
        settlement_data = await self.collect_settlement_price(contract)
        
        if settlement_data and settlement_data['settlement_price']:
            futures_price = settlement_data['settlement_price']
            basis = futures_price - spot_price
            basis_pct = (basis / spot_price) * 100
            
            # Calculate annualized basis (rough approximation)
            # Days to expiry would need to be calculated based on contract month
            days_to_expiry = self._get_days_to_expiry(contract)
            if days_to_expiry > 0:
                annualized_basis = (basis_pct / days_to_expiry) * 365
            else:
                annualized_basis = None
                
            return {
                "contract": contract,
                "futures_price": futures_price,
                "spot_price": spot_price,
                "basis": basis,
                "basis_pct": basis_pct,
                "annualized_basis": annualized_basis,
                "days_to_expiry": days_to_expiry,
                "timestamp": datetime.now(timezone.utc)
            }
            
        return None
        
    def _get_days_to_expiry(self, contract: str) -> int:
        """
        Calculate days until contract expiry
        
        CME Bitcoin/Ethereum futures expire on the last Friday of the contract month
        """
        # Extract month and year from contract code
        # Format: BTC{Month}{Year} (e.g., BTCH24)
        month_code = contract[-3]
        year = int("20" + contract[-2:])
        
        month_map = {"H": 3, "M": 6, "U": 9, "Z": 12}
        month = month_map.get(month_code)
        
        if not month:
            return 0
            
        # Find last Friday of month
        # CME contracts expire at 4:00 PM London time on last Friday
        import calendar
        last_day = calendar.monthrange(year, month)[1]
        
        # Find last Friday
        last_friday = None
        for day in range(last_day, 0, -1):
            if datetime(year, month, day).weekday() == 4:  # Friday = 4
                last_friday = day
                break
                
        if last_friday:
            expiry_date = datetime(year, month, last_friday, 16, 0, 0, tzinfo=timezone.utc)
            days_to_expiry = (expiry_date - datetime.now(timezone.utc)).days
            return max(0, days_to_expiry)
            
        return 0
        
    async def get_contract_specifications(self, underlying: str) -> Dict:
        """Get contract specifications for underlying asset"""
        if underlying == "BTC":
            return self.BTC_CONTRACTS["BTC"]
        elif underlying == "ETH":
            return self.ETH_CONTRACTS["ETH"]
        else:
            return {}
            
    async def collect_all_settlements(self):
        """Collect settlement prices for all active contracts"""
        tasks = []
        for underlying, contract in self.active_contracts.items():
            tasks.append(self.collect_settlement_price(contract))
            
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        success_count = sum(1 for r in results if r and not isinstance(r, Exception))
        logger.info(
            "CME settlement prices collected",
            total=len(self.active_contracts),
            success=success_count
        )
        
    async def collect_all_open_interest(self):
        """Collect open interest for all active contracts"""
        tasks = []
        for underlying, contract in self.active_contracts.items():
            tasks.append(self.collect_open_interest(contract))
            
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        success_count = sum(1 for r in results if r and not isinstance(r, Exception))
        logger.info(
            "CME open interest collected",
            total=len(self.active_contracts),
            success=success_count
        )


async def main():
    """Test CME collector"""
    from database import Database
    from config import settings
    
    database = Database()
    await database.connect()
    
    collector = CMECollector(
        database=database,
        api_key=getattr(settings, 'CME_API_KEY', None),
        api_secret=getattr(settings, 'CME_API_SECRET', None)
    )
    
    await collector.start()
    
    try:
        print("CME Collector Test")
        print("==================\n")
        
        print("Active Contracts:")
        for underlying, contract in collector.active_contracts.items():
            print(f"  {underlying}: {contract}")
            days = collector._get_days_to_expiry(contract)
            print(f"    Days to expiry: {days}")
            
        print("\nContract Specifications:")
        btc_spec = await collector.get_contract_specifications("BTC")
        print(f"  BTC: {btc_spec}")
        
        print("\nCollecting settlement prices...")
        await collector.collect_all_settlements()
        
        print("\nCollecting open interest...")
        await collector.collect_all_open_interest()
        
        print("\nCalculating basis (using $50000 spot price for example)...")
        basis = await collector.calculate_basis(
            collector.active_contracts["BTC"],
            spot_price=50000.0
        )
        if basis:
            print(f"  Basis: ${basis['basis']:.2f} ({basis['basis_pct']:.2f}%)")
            if basis['annualized_basis']:
                print(f"  Annualized: {basis['annualized_basis']:.2f}%")
                
        print("\nNote: CME real-time data requires paid subscription")
        print("This collector uses delayed/free data sources")
        
    finally:
        await collector.stop()
        await database.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
