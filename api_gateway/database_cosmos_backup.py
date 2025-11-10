"""
Azure Cosmos DB connection and operations for API Gateway Service
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

logger = structlog.get_logger()


class Database:
    """Azure Cosmos DB connection manager for API Gateway Service"""
    
    def __init__(self):
        self.client: Optional[CosmosClient] = None
        self.database = None
        self.credential = None
    
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
            
            # Get database reference
            self.database = self.client.get_database_client(settings.COSMOS_DATABASE_NAME)
            
            logger.info("Cosmos DB connection established successfully",
                       database=settings.COSMOS_DATABASE_NAME)
            
        except Exception as e:
            logger.error("Failed to connect to Cosmos DB", error=str(e))
            raise
    
    async def disconnect(self):
        """Close Cosmos DB connection"""
        if self.client:
            await self.client.close()
            logger.info("Cosmos DB connection closed")
    
    # Dashboard Operations
    async def get_dashboard_overview(self) -> Dict[str, Any]:
        """Get dashboard overview data from all services"""
        try:
            overview = {
                "total_strategies": 0,
                "active_strategies": 0,
                "recent_signals": 0,
                "active_orders": 0,
                "recent_trades": 0,
                "portfolio_value": 0.0,
                "last_updated": datetime.now(timezone.utc).isoformat()
            }
            
            # Get strategies data
            try:
                strategies_container = self.database.get_container_client('strategies')
                
                # Count total strategies
                query = "SELECT VALUE COUNT(1) FROM c"
                async for item in strategies_container.query_items(
                    query=query,
                    enable_cross_partition_query=True
                ):
                    overview["total_strategies"] = item
                    break
                
                # Count active strategies
                query = "SELECT VALUE COUNT(1) FROM c WHERE c.is_active = true"
                async for item in strategies_container.query_items(
                    query=query,
                    enable_cross_partition_query=True
                ):
                    overview["active_strategies"] = item
                    break
                    
            except Exception as e:
                logger.warning("Error getting strategies data for dashboard", error=str(e))
            
            # Get signals data
            try:
                signals_container = self.database.get_container_client('signals')
                
                # Count recent signals (last 24 hours)
                since_time = datetime.now(timezone.utc) - timedelta(hours=24)
                query = f"SELECT VALUE COUNT(1) FROM c WHERE c.timestamp >= '{since_time.isoformat()}'"
                async for item in signals_container.query_items(
                    query=query,
                    enable_cross_partition_query=True
                ):
                    overview["recent_signals"] = item
                    break
                    
            except Exception as e:
                logger.warning("Error getting signals data for dashboard", error=str(e))
            
            # Get orders data
            try:
                orders_container = self.database.get_container_client('orders')
                
                # Count active orders
                query = "SELECT VALUE COUNT(1) FROM c WHERE c.status IN ('NEW', 'PARTIALLY_FILLED')"
                async for item in orders_container.query_items(
                    query=query,
                    enable_cross_partition_query=True
                ):
                    overview["active_orders"] = item
                    break
                    
            except Exception as e:
                logger.warning("Error getting orders data for dashboard", error=str(e))
            
            # Get trades data
            try:
                trades_container = self.database.get_container_client('trades')
                
                # Count recent trades (last 24 hours)
                since_time = datetime.now(timezone.utc) - timedelta(hours=24)
                query = f"SELECT VALUE COUNT(1) FROM c WHERE c.trade_time >= '{since_time.isoformat()}'"
                async for item in trades_container.query_items(
                    query=query,
                    enable_cross_partition_query=True
                ):
                    overview["recent_trades"] = item
                    break
                    
            except Exception as e:
                logger.warning("Error getting trades data for dashboard", error=str(e))
            
            return overview
            
        except Exception as e:
            logger.error("Error getting dashboard overview", error=str(e))
            return {
                "error": "Failed to get dashboard overview",
                "last_updated": datetime.now(timezone.utc).isoformat()
            }
    
    # Portfolio Operations
    async def get_portfolio_balance(self) -> List[Dict[str, Any]]:
        """Get portfolio balance from order executor"""
        try:
            container = self.database.get_container_client('portfolio_balance')
            
            query = "SELECT * FROM c ORDER BY c.updated_at DESC"
            items = []
            async for item in container.query_items(
                query=query,
                enable_cross_partition_query=True
            ):
                items.append(item)
            
            return items
            
        except Exception as e:
            logger.error("Error getting portfolio balance", error=str(e))
            return []
    
    # Strategy Operations
    async def get_all_strategies(self) -> List[Dict[str, Any]]:
        """Get all strategies from strategy service"""
        try:
            container = self.database.get_container_client('strategies')
            
            query = "SELECT * FROM c ORDER BY c.created_at DESC"
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
    
    async def toggle_strategy_status(self, strategy_id: str) -> bool:
        """Toggle strategy status"""
        try:
            container = self.database.get_container_client('strategies')
            
            # First find the strategy
            query = f"SELECT * FROM c WHERE c.id = '{strategy_id}'"
            items = []
            async for item in container.query_items(
                query=query,
                enable_cross_partition_query=True
            ):
                items.append(item)
            
            if not items:
                logger.warning(f"Strategy not found: {strategy_id}")
                return False
            
            strategy = items[0]
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
    
    # Order Operations
    async def get_active_orders(self) -> List[Dict[str, Any]]:
        """Get active orders from order executor"""
        try:
            container = self.database.get_container_client('orders')
            
            query = """
            SELECT * FROM c 
            WHERE c.status IN ('NEW', 'PARTIALLY_FILLED')
            ORDER BY c.order_time DESC
            """
            
            items = []
            async for item in container.query_items(
                query=query,
                enable_cross_partition_query=True
            ):
                items.append(item)
            
            return items
            
        except Exception as e:
            logger.error("Error getting active orders", error=str(e))
            return []
    
    async def get_recent_orders(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent orders from order executor"""
        try:
            container = self.database.get_container_client('orders')
            
            query = f"""
            SELECT TOP {limit} * FROM c
            ORDER BY c.order_time DESC
            """
            
            items = []
            async for item in container.query_items(
                query=query,
                enable_cross_partition_query=True
            ):
                items.append(item)
            
            return items
            
        except Exception as e:
            logger.error("Error getting recent orders", error=str(e))
            return []
    
    # Trade Operations
    async def get_recent_trades(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent trades from order executor"""
        try:
            container = self.database.get_container_client('trades')
            
            query = f"""
            SELECT TOP {limit} * FROM c
            ORDER BY c.trade_time DESC
            """
            
            items = []
            async for item in container.query_items(
                query=query,
                enable_cross_partition_query=True
            ):
                items.append(item)
            
            return items
            
        except Exception as e:
            logger.error("Error getting recent trades", error=str(e))
            return []
    
    # Signal Operations
    async def get_recent_signals(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent signals from strategy service"""
        try:
            container = self.database.get_container_client('signals')
            
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
    
    # Market Data Operations
    async def get_market_data(self, symbol: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Get market data from market data service"""
        try:
            container = self.database.get_container_client('market_data')
            
            query = f"""
            SELECT TOP {limit} * FROM c
            WHERE c.symbol = @symbol
            ORDER BY c.timestamp DESC
            """
            
            items = []
            async for item in container.query_items(
                query=query,
                parameters=[{"name": "@symbol", "value": symbol.upper()}]
            ):
                items.append(item)
            
            return items
            
        except Exception as e:
            logger.error(f"Error getting market data for {symbol}", error=str(e))
            return []
    
    # Trading Configuration
    async def toggle_trading_enabled(self) -> bool:
        """Toggle global trading enabled status"""
        try:
            container = self.database.get_container_client('trading_config')
            
            # Get current status
            query = "SELECT * FROM c WHERE c.config_type = 'trading_enabled'"
            items = []
            async for item in container.query_items(query=query):
                items.append(item)
            
            if items:
                config = items[0]
                config['enabled'] = not config.get('enabled', False)
                config['updated_at'] = datetime.now(timezone.utc).isoformat()
                
                await container.replace_item(
                    item=config['id'],
                    body=config
                )
            else:
                # Create new config
                config = {
                    "id": str(uuid.uuid4()),
                    "config_type": "trading_enabled",
                    "enabled": True,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }
                
                await container.create_item(body=config)
            
            return config['enabled']
            
        except Exception as e:
            logger.error("Error toggling trading enabled status", error=str(e))
            return False
    
    # Strategy Environment Management
    async def set_strategy_environment(self, strategy_id: int, environment_config: dict) -> bool:
        """Set environment configuration for a strategy"""
        try:
            container = self.database.get_container_client('configuration')
            
            config_doc = {
                "id": f"strategy_env_config_{strategy_id}",
                "type": "strategy_environment_config",
                "strategy_id": strategy_id,
                "environment": environment_config.get("environment", "testnet"),
                "max_position_size": environment_config.get("max_position_size"),
                "max_daily_trades": environment_config.get("max_daily_trades"),
                "risk_multiplier": environment_config.get("risk_multiplier", 1.0),
                "enabled": environment_config.get("enabled", True),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
            
            await container.upsert_item(body=config_doc)
            logger.info(f"Strategy environment config saved", 
                       strategy_id=strategy_id, 
                       environment=config_doc["environment"])
            
            return True
            
        except Exception as e:
            logger.error("Error setting strategy environment", 
                        strategy_id=strategy_id, error=str(e))
            return False
    
    async def get_strategy_environment_config(self, strategy_id: int) -> Optional[dict]:
        """Get environment configuration for a specific strategy"""
        try:
            container = self.database.get_container_client('configuration')
            
            try:
                item = await container.read_item(
                    item=f"strategy_env_config_{strategy_id}",
                    partition_key=f"strategy_env_config_{strategy_id}"
                )
                return {
                    "strategy_id": item["strategy_id"],
                    "environment": item["environment"],
                    "max_position_size": item.get("max_position_size"),
                    "max_daily_trades": item.get("max_daily_trades"),
                    "risk_multiplier": item.get("risk_multiplier", 1.0),
                    "enabled": item.get("enabled", True),
                    "updated_at": item.get("updated_at")
                }
            except exceptions.CosmosResourceNotFoundError:
                # Return default config if not found
                return None
                
        except Exception as e:
            logger.error("Error getting strategy environment config", 
                        strategy_id=strategy_id, error=str(e))
            return None
    
    async def get_all_strategy_environment_configs(self) -> List[dict]:
        """Get all strategy environment configurations"""
        try:
            container = self.database.get_container_client('configuration')
            
            query = "SELECT * FROM c WHERE c.type = 'strategy_environment_config'"
            
            configs = []
            async for item in container.query_items(query=query, enable_cross_partition_query=True):
                configs.append({
                    "strategy_id": item["strategy_id"],
                    "environment": item["environment"],
                    "max_position_size": item.get("max_position_size"),
                    "max_daily_trades": item.get("max_daily_trades"),
                    "risk_multiplier": item.get("risk_multiplier", 1.0),
                    "enabled": item.get("enabled", True),
                    "updated_at": item.get("updated_at")
                })
            
            return configs
            
        except Exception as e:
            logger.error("Error getting all strategy environment configs", error=str(e))
            return []
    
    # Symbol/Crypto Management Operations
    async def get_all_symbols(self, include_inactive: bool = False) -> List[Dict[str, Any]]:
        """Get all tracked trading symbols/crypto pairs"""
        try:
            container = self.database.get_container_client('symbol_tracking')
            
            if include_inactive:
                query = "SELECT * FROM c ORDER BY c.symbol ASC"
            else:
                query = "SELECT * FROM c WHERE c.tracking = true ORDER BY c.symbol ASC"
            
            symbols = []
            async for item in container.query_items(
                query=query,
                enable_cross_partition_query=True
            ):
                symbols.append(item)
            
            return symbols
            
        except Exception as e:
            logger.error("Error getting all symbols", error=str(e))
            return []
    
    async def get_symbol_tracking_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get tracking information for a specific symbol"""
        try:
            container = self.database.get_container_client('symbol_tracking')
            
            try:
                item = await container.read_item(
                    item=symbol,
                    partition_key=symbol
                )
                return item
            except exceptions.CosmosResourceNotFoundError:
                return None
                
        except Exception as e:
            logger.error("Error getting symbol tracking info", symbol=symbol, error=str(e))
            return None
    
    async def toggle_symbol_tracking(self, symbol: str) -> bool:
        """Toggle tracking status for a symbol"""
        try:
            container = self.database.get_container_client('symbol_tracking')
            
            try:
                item = await container.read_item(
                    item=symbol,
                    partition_key=symbol
                )
                
                item['tracking'] = not item.get('tracking', False)
                item['updated_at'] = datetime.now(timezone.utc).isoformat()
                
                await container.replace_item(
                    item=symbol,
                    body=item
                )
                
                logger.info(f"Toggled tracking for {symbol} to {item['tracking']}")
                return True
                
            except exceptions.CosmosResourceNotFoundError:
                logger.warning(f"Symbol {symbol} not found in tracking")
                return False
                
        except Exception as e:
            logger.error("Error toggling symbol tracking", symbol=symbol, error=str(e))
            return False
    
    async def update_symbol_tracking(self, symbol: str, updates: Dict[str, Any]) -> bool:
        """Update symbol tracking configuration"""
        try:
            container = self.database.get_container_client('symbol_tracking')
            
            try:
                item = await container.read_item(
                    item=symbol,
                    partition_key=symbol
                )
                
                # Update fields
                for key, value in updates.items():
                    if key not in ['id', 'symbol']:  # Don't allow changing id or symbol
                        item[key] = value
                
                item['updated_at'] = datetime.now(timezone.utc).isoformat()
                
                await container.replace_item(
                    item=symbol,
                    body=item
                )
                
                logger.info(f"Updated tracking info for {symbol}")
                return True
                
            except exceptions.CosmosResourceNotFoundError:
                logger.warning(f"Symbol {symbol} not found in tracking")
                return False
                
        except Exception as e:
            logger.error("Error updating symbol tracking", symbol=symbol, error=str(e))
            return False
    
    async def get_symbol_historical_stats(self, symbol: str) -> Dict[str, Any]:
        """Get historical data availability statistics for a symbol"""
        try:
            market_data_container = self.database.get_container_client('market_data')
            
            # Get count and date range for each interval
            intervals = ['1m', '5m', '15m', '1h', '4h', '1d']
            stats = {
                "symbol": symbol,
                "intervals": {}
            }
            
            for interval in intervals:
                query = f"""
                SELECT 
                    COUNT(1) as count,
                    MIN(c.timestamp) as earliest,
                    MAX(c.timestamp) as latest
                FROM c 
                WHERE c.symbol = @symbol AND c.interval = @interval
                """
                
                params = [
                    {"name": "@symbol", "value": symbol},
                    {"name": "@interval", "value": interval}
                ]
                
                async for item in market_data_container.query_items(
                    query=query,
                    parameters=params,
                    enable_cross_partition_query=True
                ):
                    stats["intervals"][interval] = {
                        "record_count": item.get("count", 0),
                        "earliest_data": item.get("earliest"),
                        "latest_data": item.get("latest"),
                        "has_data": item.get("count", 0) > 0
                    }
                    break
            
            return stats
            
        except Exception as e:
            logger.error("Error getting symbol historical stats", symbol=symbol, error=str(e))
            return {
                "symbol": symbol,
                "error": "Failed to retrieve statistics",
                "intervals": {}
            }