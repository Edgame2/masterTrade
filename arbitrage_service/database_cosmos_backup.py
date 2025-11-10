"""
Azure Cosmos DB connection and operations for Arbitrage Service
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
from models import (
    ArbitrageOpportunity, ArbitrageExecution, DEXPrice, 
    FlashLoanOpportunity, TriangularArbitrageOpportunity, GasPrice
)

logger = structlog.get_logger()


class Database:
    """Azure Cosmos DB connection manager for Arbitrage Service"""
    
    def __init__(self):
        self.client: Optional[CosmosClient] = None
        self.database = None
        self.containers: Dict[str, Any] = {}
        self.credential = None
        
        # Container configuration with partition keys and indexing policies
        self.container_configs = {
            'arbitrage_opportunities': {
                'partition_key': PartitionKey(path="/pair"),
                'indexing_policy': {
                    'indexingMode': 'consistent',
                    'automatic': True,
                    'includedPaths': [
                        {'path': '/pair/?'},
                        {'path': '/profit_percent/?'},
                        {'path': '/timestamp/?'},
                        {'path': '/arbitrage_type/?'},
                        {'path': '/executed/?'}
                    ],
                    'excludedPaths': [
                        {'path': '/*'}
                    ],
                    'compositeIndexes': [
                        [
                            {'path': '/pair', 'order': 'ascending'},
                            {'path': '/timestamp', 'order': 'descending'}
                        ],
                        [
                            {'path': '/profit_percent', 'order': 'descending'},
                            {'path': '/timestamp', 'order': 'descending'}
                        ],
                        [
                            {'path': '/arbitrage_type', 'order': 'ascending'},
                            {'path': '/profit_percent', 'order': 'descending'}
                        ]
                    ]
                }
            },
            'arbitrage_executions': {
                'partition_key': PartitionKey(path="/opportunity_id"),
                'indexing_policy': {
                    'indexingMode': 'consistent',
                    'automatic': True,
                    'includedPaths': [
                        {'path': '/opportunity_id/?'},
                        {'path': '/status/?'},
                        {'path': '/start_time/?'},
                        {'path': '/execution_type/?'}
                    ],
                    'excludedPaths': [
                        {'path': '/*'}
                    ]
                }
            },
            'dex_prices': {
                'partition_key': PartitionKey(path="/pair"),
                'indexing_policy': {
                    'indexingMode': 'consistent',
                    'automatic': True,
                    'includedPaths': [
                        {'path': '/pair/?'},
                        {'path': '/dex/?'},
                        {'path': '/chain/?'},
                        {'path': '/timestamp/?'},
                        {'path': '/price/?'}
                    ],
                    'excludedPaths': [
                        {'path': '/*'}
                    ],
                    'compositeIndexes': [
                        [
                            {'path': '/pair', 'order': 'ascending'},
                            {'path': '/timestamp', 'order': 'descending'}
                        ],
                        [
                            {'path': '/dex', 'order': 'ascending'},
                            {'path': '/pair', 'order': 'ascending'},
                            {'path': '/timestamp', 'order': 'descending'}
                        ]
                    ]
                }
            },
            'flash_loan_opportunities': {
                'partition_key': PartitionKey(path="/protocol"),
                'indexing_policy': {
                    'indexingMode': 'consistent',
                    'automatic': True,
                    'includedPaths': [
                        {'path': '/protocol/?'},
                        {'path': '/token/?'},
                        {'path': '/estimated_profit/?'},
                        {'path': '/timestamp/?'}
                    ],
                    'excludedPaths': [
                        {'path': '/*'}
                    ]
                }
            },
            'triangular_arbitrage': {
                'partition_key': PartitionKey(path="/exchange"),
                'indexing_policy': {
                    'indexingMode': 'consistent',
                    'automatic': True,
                    'includedPaths': [
                        {'path': '/exchange/?'},
                        {'path': '/chain/?'},
                        {'path': '/profit_percent/?'},
                        {'path': '/timestamp/?'}
                    ],
                    'excludedPaths': [
                        {'path': '/*'}
                    ]
                }
            },
            'gas_prices': {
                'partition_key': PartitionKey(path="/chain"),
                'indexing_policy': {
                    'indexingMode': 'consistent',
                    'automatic': True,
                    'includedPaths': [
                        {'path': '/chain/?'},
                        {'path': '/timestamp/?'},
                        {'path': '/standard_gwei/?'}
                    ],
                    'excludedPaths': [
                        {'path': '/*'}
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
    
    # Arbitrage Opportunity Operations
    async def insert_arbitrage_opportunity(self, opportunity: ArbitrageOpportunity) -> bool:
        """Insert arbitrage opportunity into database"""
        try:
            container = self.containers.get('arbitrage_opportunities')
            if not container:
                return False
            
            opportunity_doc = {
                "id": str(uuid.uuid4()),
                "pair": opportunity.pair,
                "buy_venue": opportunity.buy_venue,
                "sell_venue": opportunity.sell_venue,
                "buy_price": float(opportunity.buy_price),
                "sell_price": float(opportunity.sell_price),
                "profit_percent": float(opportunity.profit_percent),
                "estimated_profit_usd": float(opportunity.estimated_profit_usd),
                "trade_amount": float(opportunity.trade_amount),
                "gas_cost": float(opportunity.gas_cost),
                "arbitrage_type": opportunity.arbitrage_type,
                "timestamp": opportunity.timestamp.isoformat(),
                "executed": opportunity.executed,
                "execution_id": opportunity.execution_id
            }
            
            await container.create_item(body=opportunity_doc)
            logger.info(f"Inserted arbitrage opportunity: {opportunity.pair} - {opportunity.profit_percent:.2f}%")
            return True
            
        except Exception as e:
            logger.error(f"Error inserting arbitrage opportunity for {opportunity.pair}", error=str(e))
            return False
    
    async def get_profitable_opportunities(self, min_profit_percent: float = 0.1) -> List[Dict[str, Any]]:
        """Get profitable arbitrage opportunities"""
        try:
            container = self.containers.get('arbitrage_opportunities')
            if not container:
                return []
            
            query = f"""
            SELECT * FROM c 
            WHERE c.profit_percent >= {min_profit_percent} 
                AND c.executed = false
            ORDER BY c.profit_percent DESC
            """
            
            items = []
            async for item in container.query_items(
                query=query,
                enable_cross_partition_query=True
            ):
                items.append(item)
            
            return items
            
        except Exception as e:
            logger.error("Error getting profitable opportunities", error=str(e))
            return []
    
    async def get_opportunities_by_type(self, arbitrage_type: str) -> List[Dict[str, Any]]:
        """Get opportunities by arbitrage type"""
        try:
            container = self.containers.get('arbitrage_opportunities')
            if not container:
                return []
            
            query = f"""
            SELECT * FROM c 
            WHERE c.arbitrage_type = @arbitrage_type
            ORDER BY c.timestamp DESC
            """
            
            items = []
            async for item in container.query_items(
                query=query,
                parameters=[{"name": "@arbitrage_type", "value": arbitrage_type}],
                enable_cross_partition_query=True
            ):
                items.append(item)
            
            return items
            
        except Exception as e:
            logger.error(f"Error getting opportunities by type {arbitrage_type}", error=str(e))
            return []
    
    # Arbitrage Execution Operations
    async def create_arbitrage_execution(self, opportunity: ArbitrageOpportunity) -> str:
        """Create arbitrage execution record"""
        try:
            container = self.containers.get('arbitrage_executions')
            if not container:
                return ""
            
            execution_id = str(uuid.uuid4())
            execution_doc = {
                "id": execution_id,
                "opportunity_id": opportunity.id or "",
                "execution_type": opportunity.arbitrage_type,
                "start_time": datetime.now(timezone.utc).isoformat(),
                "end_time": None,
                "status": "pending",
                "transactions": [],
                "actual_profit_usd": None,
                "gas_used": None,
                "error_message": None
            }
            
            await container.create_item(body=execution_doc)
            logger.info(f"Created arbitrage execution: {execution_id}")
            return execution_id
            
        except Exception as e:
            logger.error("Error creating arbitrage execution", error=str(e))
            return ""
    
    async def update_arbitrage_execution(self, execution_id: str, result: Dict[str, Any]) -> bool:
        """Update arbitrage execution with results"""
        try:
            container = self.containers.get('arbitrage_executions')
            if not container:
                return False
            
            # First get the execution
            query = f"SELECT * FROM c WHERE c.id = '{execution_id}'"
            items = []
            async for item in container.query_items(
                query=query,
                enable_cross_partition_query=True
            ):
                items.append(item)
            
            if not items:
                logger.warning(f"Execution not found: {execution_id}")
                return False
            
            execution = items[0]
            execution.update({
                "end_time": datetime.now(timezone.utc).isoformat(),
                "status": result.get("status", "failed"),
                "transactions": result.get("transactions", []),
                "actual_profit_usd": result.get("actual_profit_usd"),
                "gas_used": result.get("gas_used"),
                "error_message": result.get("error_message")
            })
            
            await container.replace_item(
                item=execution_id,
                body=execution
            )
            
            logger.info(f"Updated arbitrage execution {execution_id} with status {execution['status']}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating arbitrage execution: {execution_id}", error=str(e))
            return False
    
    async def get_execution_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get arbitrage execution history"""
        try:
            container = self.containers.get('arbitrage_executions')
            if not container:
                return []
            
            query = f"""
            SELECT TOP {limit} * FROM c
            ORDER BY c.start_time DESC
            """
            
            items = []
            async for item in container.query_items(
                query=query,
                enable_cross_partition_query=True
            ):
                items.append(item)
            
            return items
            
        except Exception as e:
            logger.error("Error getting execution history", error=str(e))
            return []
    
    # DEX Price Operations
    async def insert_dex_price(self, price: DEXPrice) -> bool:
        """Insert DEX price data"""
        try:
            container = self.containers.get('dex_prices')
            if not container:
                return False
            
            price_doc = {
                "id": str(uuid.uuid4()),
                "pair": price.pair,
                "dex": price.dex,
                "chain": price.chain,
                "price": float(price.price),
                "liquidity": float(price.liquidity),
                "reserve0": float(price.reserve0) if price.reserve0 else None,
                "reserve1": float(price.reserve1) if price.reserve1 else None,
                "timestamp": price.timestamp.isoformat()
            }
            
            await container.create_item(body=price_doc)
            return True
            
        except Exception as e:
            logger.error(f"Error inserting DEX price for {price.pair}", error=str(e))
            return False
    
    async def get_latest_dex_prices(self, pair: str) -> List[Dict[str, Any]]:
        """Get latest DEX prices for a pair"""
        try:
            container = self.containers.get('dex_prices')
            if not container:
                return []
            
            # Get latest price for each DEX
            query = f"""
            SELECT * FROM c
            WHERE c.pair = @pair
            ORDER BY c.timestamp DESC
            """
            
            items = []
            async for item in container.query_items(
                query=query,
                parameters=[{"name": "@pair", "value": pair}]
            ):
                items.append(item)
            
            return items
            
        except Exception as e:
            logger.error(f"Error getting DEX prices for {pair}", error=str(e))
            return []
    
    # Flash Loan Operations
    async def insert_flash_loan_opportunity(self, opportunity: FlashLoanOpportunity) -> bool:
        """Insert flash loan opportunity"""
        try:
            container = self.containers.get('flash_loan_opportunities')
            if not container:
                return False
            
            opportunity_doc = {
                "id": str(uuid.uuid4()),
                "protocol": opportunity.protocol,
                "token": opportunity.token,
                "amount": float(opportunity.amount),
                "fee_percent": float(opportunity.fee_percent),
                "arbitrage_path": opportunity.arbitrage_path,
                "estimated_profit": float(opportunity.estimated_profit),
                "gas_estimate": opportunity.gas_estimate,
                "timestamp": opportunity.timestamp.isoformat()
            }
            
            await container.create_item(body=opportunity_doc)
            logger.info(f"Inserted flash loan opportunity: {opportunity.protocol} - {opportunity.token}")
            return True
            
        except Exception as e:
            logger.error(f"Error inserting flash loan opportunity", error=str(e))
            return False
    
    # Gas Price Operations
    async def insert_gas_price(self, gas_price: GasPrice) -> bool:
        """Insert gas price data"""
        try:
            container = self.containers.get('gas_prices')
            if not container:
                return False
            
            gas_doc = {
                "id": str(uuid.uuid4()),
                "chain": gas_price.chain,
                "standard_gwei": float(gas_price.standard_gwei),
                "fast_gwei": float(gas_price.fast_gwei),
                "instant_gwei": float(gas_price.instant_gwei),
                "timestamp": gas_price.timestamp.isoformat()
            }
            
            await container.create_item(body=gas_doc)
            return True
            
        except Exception as e:
            logger.error(f"Error inserting gas price for {gas_price.chain}", error=str(e))
            return False
    
    async def get_latest_gas_price(self, chain: str) -> Optional[Dict[str, Any]]:
        """Get latest gas price for a chain"""
        try:
            container = self.containers.get('gas_prices')
            if not container:
                return None
            
            query = f"""
            SELECT TOP 1 * FROM c
            WHERE c.chain = @chain
            ORDER BY c.timestamp DESC
            """
            
            async for item in container.query_items(
                query=query,
                parameters=[{"name": "@chain", "value": chain}]
            ):
                return item
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting gas price for {chain}", error=str(e))
            return None
    
    # Analytics Operations
    async def get_arbitrage_stats(self, hours_back: int = 24) -> Dict[str, Any]:
        """Get arbitrage statistics"""
        try:
            stats = {
                "total_opportunities": 0,
                "profitable_opportunities": 0,
                "total_executions": 0,
                "successful_executions": 0,
                "total_profit_usd": 0.0,
                "avg_profit_percent": 0.0,
                "period_hours": hours_back,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            since_time = datetime.now(timezone.utc) - timedelta(hours=hours_back)
            
            # Get opportunities stats
            container = self.containers.get('arbitrage_opportunities')
            if container:
                query = f"""
                SELECT 
                    COUNT(1) as total_count,
                    AVG(c.profit_percent) as avg_profit
                FROM c 
                WHERE c.timestamp >= '{since_time.isoformat()}'
                """
                
                async for item in container.query_items(
                    query=query,
                    enable_cross_partition_query=True
                ):
                    stats["total_opportunities"] = item.get("total_count", 0)
                    stats["avg_profit_percent"] = item.get("avg_profit", 0.0)
                    break
            
            # Get executions stats
            container = self.containers.get('arbitrage_executions')
            if container:
                query = f"""
                SELECT 
                    COUNT(1) as total_executions,
                    SUM(c.actual_profit_usd) as total_profit
                FROM c 
                WHERE c.start_time >= '{since_time.isoformat()}'
                """
                
                async for item in container.query_items(
                    query=query,
                    enable_cross_partition_query=True
                ):
                    stats["total_executions"] = item.get("total_executions", 0)
                    stats["total_profit_usd"] = item.get("total_profit", 0.0) or 0.0
                    break
            
            return stats
            
        except Exception as e:
            logger.error("Error getting arbitrage stats", error=str(e))
            return {}