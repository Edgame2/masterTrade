"""
Azure Cosmos DB connection and operations for Strategy Service
"""

import asyncio
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List, Any

import structlog
from azure.cosmos.aio import CosmosClient
from azure.cosmos import PartitionKey, exceptions
from azure.identity.aio import DefaultAzureCredential

from config import settings
from models import Strategy, Signal, StrategyResult, StrategyConfig

logger = structlog.get_logger()


class Database:
    """Azure Cosmos DB connection manager for Strategy Service"""
    
    def __init__(self):
        self.client: Optional[CosmosClient] = None
        self.database = None
        self.containers: Dict[str, Any] = {}
        self.credential = None
        
        # Container configuration with partition keys and indexing policies
        self.container_configs = {
            'strategies': {
                'partition_key': PartitionKey(path="/type"),
                'indexing_policy': {
                    'indexingMode': 'consistent',
                    'automatic': True,
                    'includedPaths': [
                        {'path': '/type/?'},
                        {'path': '/name/?'},
                        {'path': '/is_active/?'},
                        {'path': '/id/?'}
                    ],
                    'excludedPaths': [
                        {'path': '/*'}
                    ],
                    'compositeIndexes': [
                        [
                            {'path': '/type', 'order': 'ascending'},
                            {'path': '/is_active', 'order': 'ascending'},
                            {'path': '/id', 'order': 'ascending'}
                        ]
                    ]
                }
            },
            'signals': {
                'partition_key': PartitionKey(path="/symbol"),
                'indexing_policy': {
                    'indexingMode': 'consistent',
                    'automatic': True,
                    'includedPaths': [
                        {'path': '/symbol/?'},
                        {'path': '/strategy_id/?'},
                        {'path': '/timestamp/?'},
                        {'path': '/signal_type/?'},
                        {'path': '/confidence/?'}
                    ],
                    'excludedPaths': [
                        {'path': '/*'}
                    ],
                    'compositeIndexes': [
                        [
                            {'path': '/symbol', 'order': 'ascending'},
                            {'path': '/timestamp', 'order': 'descending'}
                        ],
                        [
                            {'path': '/strategy_id', 'order': 'ascending'},
                            {'path': '/timestamp', 'order': 'descending'}
                        ]
                    ]
                }
            },
            'strategy_performance': {
                'partition_key': PartitionKey(path="/strategy_id"),
                'indexing_policy': {
                    'indexingMode': 'consistent',
                    'automatic': True,
                    'includedPaths': [
                        {'path': '/strategy_id/?'},
                        {'path': '/symbol/?'},
                        {'path': '/timestamp/?'},
                        {'path': '/execution_time/?'}
                    ],
                    'excludedPaths': [
                        {'path': '/*'}
                    ]
                }
            },
            'crypto_selections': {
                'partition_key': PartitionKey(path="/selection_date"),
                'indexing_policy': {
                    'indexingMode': 'consistent',
                    'automatic': True,
                    'includedPaths': [
                        {'path': '/selection_date/?'},
                        {'path': '/selection_timestamp/?'},
                        {'path': '/selected_cryptos/?'},
                        {'path': '/total_selected/?'}
                    ],
                    'excludedPaths': [
                        {'path': '/*'}
                    ],
                    'compositeIndexes': [
                        [
                            {'path': '/selection_date', 'order': 'descending'},
                            {'path': '/selection_timestamp', 'order': 'descending'}
                        ]
                    ]
                }
            }
        }
    
    async def connect(self):
        """Establish Cosmos DB connection using best practices"""
        try:
            if settings.USE_MANAGED_IDENTITY:
                # Use Managed Identity for Azure-hosted applications (recommended)
                self.credential = DefaultAzureCredential()
                self.client = CosmosClient(
                    url=settings.COSMOS_ENDPOINT,
                    credential=self.credential
                )
                logger.info("Connected to Cosmos DB using Managed Identity")
            else:
                # Use connection string for local development
                self.client = CosmosClient(
                    url=settings.COSMOS_ENDPOINT,
                    credential=settings.COSMOS_KEY
                )
                logger.info("Connected to Cosmos DB using connection string")
            
            # Create database if it doesn't exist
            self.database = await self.client.create_database_if_not_exists(
                id=settings.COSMOS_DATABASE_NAME
            )
            
            # Create containers with optimized settings
            await self._create_containers()
            
            logger.info("Cosmos DB connection established successfully",
                       database=settings.COSMOS_DATABASE_NAME)
            
        except Exception as e:
            logger.error("Failed to connect to Cosmos DB", error=str(e))
            raise
    
    async def _create_containers(self):
        """Create containers with optimized partition keys and indexing policies"""
        for container_name, config in self.container_configs.items():
            try:
                container = await self.database.create_container_if_not_exists(
                    id=container_name,
                    partition_key=config['partition_key'],
                    indexing_policy=config.get('indexing_policy')
                )
                self.containers[container_name] = container
                
                logger.info(f"Container '{container_name}' ready")
                
            except Exception as e:
                logger.error(f"Failed to create container '{container_name}'", error=str(e))
                raise
    
    async def disconnect(self):
        """Close Cosmos DB connection"""
        if self.client:
            await self.client.close()
            logger.info("Cosmos DB connection closed")
    
    # Strategy Operations
    async def get_active_strategies(self) -> List[Strategy]:
        """Get all active strategies from database"""
        try:
            container = self.containers['strategies']
            query = "SELECT * FROM c WHERE c.is_active = true"
            items = []
            async for item in container.query_items(
                query=query,
                enable_cross_partition_query=True
            ):
                # Convert to Strategy model
                strategy = Strategy(
                    id=item['id'],
                    name=item['name'],
                    type=item['type'],
                    parameters=item.get('parameters', {}),
                    is_active=item.get('is_active', True),
                    symbols=item.get('symbols', [])
                )
                items.append(strategy)
            
            logger.info(f"Retrieved {len(items)} active strategies")
            return items
            
        except Exception as e:
            logger.error("Error getting active strategies", error=str(e))
            return []
    
    async def get_all_strategies(self) -> List[Dict[str, Any]]:
        """Get all strategies (active and inactive)"""
        try:
            container = self.containers.get('strategies')
            if not container:
                return []
            
            query = "SELECT * FROM c"
            items = []
            async for item in container.query_items(
                query=query,
                enable_cross_partition_query=True
            ):
                items.append(item)
            
            return items
            
        except Exception as e:
            logger.error("Error getting all strategies", error=str(e))
            return []
    
    async def create_strategy(self, strategy_config: StrategyConfig) -> bool:
        """Create a new trading strategy"""
        try:
            container = self.containers.get('strategies')
            if not container:
                return False
            
            strategy_doc = {
                "id": str(uuid.uuid4()),
                "name": strategy_config.name,
                "type": strategy_config.type,
                "parameters": strategy_config.parameters,
                "symbols": strategy_config.symbols,
                "is_active": strategy_config.is_active,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
            
            await container.create_item(body=strategy_doc)
            logger.info(f"Created strategy: {strategy_config.name}")
            return True
            
        except Exception as e:
            logger.error(f"Error creating strategy: {strategy_config.name}", error=str(e))
            return False
    
    async def toggle_strategy_status(self, strategy_id: str) -> bool:
        """Toggle strategy active status"""
        try:
            container = self.containers.get('strategies')
            if not container:
                return False
            
            # Get current strategy
            try:
                strategy = await container.read_item(
                    item=strategy_id,
                    partition_key=strategy_id  # Assuming strategy_id as partition key
                )
            except exceptions.CosmosResourceNotFoundError:
                logger.warning(f"Strategy not found: {strategy_id}")
                return False
            
            # Toggle status
            strategy['is_active'] = not strategy.get('is_active', False)
            strategy['updated_at'] = datetime.now(timezone.utc).isoformat()
            
            await container.replace_item(
                item=strategy_id,
                body=strategy
            )
            
            logger.info(f"Toggled strategy {strategy_id} status to {strategy['is_active']}")
            return True
            
        except Exception as e:
            logger.error(f"Error toggling strategy status: {strategy_id}", error=str(e))
            return False
    
    # Signal Operations
    async def insert_signal(self, signal: Signal) -> bool:
        """Insert trading signal into Cosmos DB"""
        try:
            container = self.containers.get('signals')
            if not container:
                logger.warning("Signals container not available")
                return False
            
            signal_doc = {
                "id": str(uuid.uuid4()),
                "strategy_id": signal.strategy_id,
                "symbol": signal.symbol,
                "signal_type": signal.signal_type,
                "confidence": signal.confidence,
                "price": signal.price,
                "quantity": signal.quantity,
                "metadata": signal.metadata,
                "timestamp": signal.timestamp.isoformat(),
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            
            await container.create_item(body=signal_doc)
            logger.info(f"Inserted signal: {signal.symbol} {signal.signal_type}")
            return True
            
        except Exception as e:
            logger.error(f"Error inserting signal for {signal.symbol}", error=str(e))
            return False
    
    async def get_recent_signals(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent trading signals"""
        try:
            container = self.containers.get('signals')
            if not container:
                return []
            
            query = f"""
            SELECT TOP {limit} * FROM c 
            ORDER BY c.timestamp DESC
            """
            
            items = []
            async for item in container.query_items(
                query=query,
                enable_cross_partition_query=True
            ):
                items.append(item)
            
            return items
            
        except Exception as e:
            logger.error("Error getting recent signals", error=str(e))
            return []
    
    async def get_signals_by_strategy(self, strategy_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Get signals for a specific strategy"""
        try:
            container = self.containers.get('signals')
            if not container:
                return []
            
            query = f"""
            SELECT TOP {limit} * FROM c 
            WHERE c.strategy_id = @strategy_id
            ORDER BY c.timestamp DESC
            """
            
            items = []
            async for item in container.query_items(
                query=query,
                parameters=[{"name": "@strategy_id", "value": strategy_id}],
                enable_cross_partition_query=True
            ):
                items.append(item)
            
            return items
            
        except Exception as e:
            logger.error(f"Error getting signals for strategy {strategy_id}", error=str(e))
            return []
    
    # Performance Operations
    async def insert_strategy_performance(self, result: StrategyResult) -> bool:
        """Insert strategy performance data"""
        try:
            container = self.containers.get('strategy_performance')
            if not container:
                return False
            
            performance_doc = {
                "id": str(uuid.uuid4()),
                "strategy_id": result.strategy_id,
                "symbol": result.symbol,
                "signals_count": len(result.signals),
                "execution_time": result.execution_time,
                "error": result.error,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "signals_summary": [
                    {
                        "type": signal.signal_type,
                        "confidence": signal.confidence,
                        "price": signal.price
                    }
                    for signal in result.signals
                ]
            }
            
            await container.create_item(body=performance_doc)
            logger.info(f"Inserted performance data for strategy {result.strategy_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error inserting performance data", error=str(e))
            return False
    
    async def get_strategy_performance_summary(self, strategy_id: str, hours_back: int = 24) -> Dict[str, Any]:
        """Get performance summary for a strategy"""
        try:
            container = self.containers.get('strategy_performance')
            if not container:
                return {}
            
            since_time = datetime.now(timezone.utc) - timedelta(hours=hours_back)
            
            query = """
            SELECT 
                COUNT(1) as execution_count,
                AVG(c.execution_time) as avg_execution_time,
                SUM(c.signals_count) as total_signals
            FROM c 
            WHERE c.strategy_id = @strategy_id 
                AND c.timestamp >= @since_time
            """
            
            items = []
            async for item in container.query_items(
                query=query,
                parameters=[
                    {"name": "@strategy_id", "value": strategy_id},
                    {"name": "@since_time", "value": since_time.isoformat()}
                ]
            ):
                items.append(item)
            
            return items[0] if items else {}
            
        except Exception as e:
            logger.error(f"Error getting performance summary for strategy {strategy_id}", error=str(e))
            return {}
    
    # Historical Data Operations (for backtesting)
    async def get_historical_data(self, symbol: str, interval: str, limit: int) -> List[Dict[str, Any]]:
        """Get historical market data from market_data_service containers"""
        try:
            # This will access the shared market_data container
            container = await self.database.get_container_client('market_data')
            
            query = f"""
            SELECT TOP {limit} * FROM c 
            WHERE c.symbol = @symbol 
                AND c.interval = @interval
            ORDER BY c.timestamp DESC
            """
            
            items = []
            async for item in container.query_items(
                query=query,
                parameters=[
                    {"name": "@symbol", "value": symbol.upper()},
                    {"name": "@interval", "value": interval}
                ]
            ):
                items.append(item)
            
            return items
            
        except Exception as e:
            logger.error(f"Error getting historical data for {symbol}", error=str(e))
            return []
    
    # Utility Operations
    async def get_dashboard_overview(self) -> Dict[str, Any]:
        """Get dashboard overview data"""
        try:
            active_strategies = await self.get_active_strategies()
            recent_signals = await self.get_recent_signals(limit=10)
            
            return {
                "active_strategies_count": len(active_strategies),
                "recent_signals_count": len(recent_signals),
                "last_updated": datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            logger.error("Error getting dashboard overview", error=str(e))
            return {}