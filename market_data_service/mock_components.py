"""
Mock components for development
"""
import structlog

logger = structlog.get_logger()

class SentimentDataCollector:
    def __init__(self, database):
        self.database = database
        
    async def connect(self):
        logger.info("Mock sentiment data collector initialized")

class StockIndexDataCollector:
    def __init__(self, database):
        self.database = database
        
    async def connect(self):
        logger.info("Mock stock index collector initialized")

class IndicatorCalculator:
    def __init__(self, database):
        self.database = database
        
    async def connect(self):
        logger.info("Mock indicator calculator initialized")

class IndicatorConfigurationManager:
    def __init__(self, database):
        self.database = database
        
    async def connect(self):
        logger.info("Mock indicator config manager initialized")
        
    async def load_configurations(self):
        return []

class StrategyDataRequestHandler:
    def __init__(self, database):
        self.database = database
        
    async def connect(self):
        logger.info("Mock strategy request handler initialized")