"""
Mock Historical Data Collector for development
"""
import structlog

logger = structlog.get_logger()

class HistoricalDataCollector:
    def __init__(self, database):
        self.database = database
        
    async def connect(self):
        logger.info("Mock historical data collector initialized")
        
    async def collect_initial_data(self, symbols):
        logger.info("Mock historical data collection", symbols=symbols)
        return True
        
    async def collect_symbol_data(self, symbol, interval="1h", days=30):
        logger.info("Mock symbol data collection", symbol=symbol, interval=interval, days=days)
        return []