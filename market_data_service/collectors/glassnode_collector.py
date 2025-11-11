"""
Glassnode On-Chain Metrics Collector

Collects on-chain analytics and metrics from Glassnode API:
- Network Value to Transactions (NVT) Ratio
- Market Value to Realized Value (MVRV) Ratio
- Exchange NetFlow (inflows/outflows)
- Active Addresses
- Net Unrealized Profit/Loss (NUPL)
- Supply Distribution metrics
- Miner activity and hash rate

API Documentation: https://docs.glassnode.com/api/
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any
import structlog

from database import Database
from collectors.onchain_collector import OnChainCollector, CollectorStatus

logger = structlog.get_logger()


class GlassnodeCollector(OnChainCollector):
    """Collector for Glassnode on-chain metrics"""
    
    # Supported assets
    SUPPORTED_ASSETS = ["BTC", "ETH"]
    
    # Metric configurations
    METRICS = {
        "nvt": {
            "endpoint": "/v1/metrics/indicators/nvt",
            "description": "Network Value to Transactions Ratio",
            "category": "valuation"
        },
        "mvrv": {
            "endpoint": "/v1/metrics/market/mvrv",
            "description": "Market Value to Realized Value Ratio",
            "category": "valuation"
        },
        "nupl": {
            "endpoint": "/v1/metrics/indicators/net_unrealized_profit_loss",
            "description": "Net Unrealized Profit/Loss",
            "category": "profitability"
        },
        "exchange_netflow": {
            "endpoint": "/v1/metrics/transactions/transfers_volume_exchanges_net",
            "description": "Net flow of coins to/from exchanges",
            "category": "exchange_flows"
        },
        "exchange_inflow": {
            "endpoint": "/v1/metrics/transactions/transfers_volume_to_exchanges",
            "description": "Total inflow to exchanges",
            "category": "exchange_flows"
        },
        "exchange_outflow": {
            "endpoint": "/v1/metrics/transactions/transfers_volume_from_exchanges",
            "description": "Total outflow from exchanges",
            "category": "exchange_flows"
        },
        "active_addresses": {
            "endpoint": "/v1/metrics/addresses/active_count",
            "description": "Number of unique active addresses",
            "category": "network_activity"
        },
        "whale_addresses": {
            "endpoint": "/v1/metrics/addresses/count_greater_10k",
            "description": "Number of addresses holding >10k coins",
            "category": "supply_distribution"
        },
        "supply_profit": {
            "endpoint": "/v1/metrics/supply/profit_relative",
            "description": "Percentage of supply in profit",
            "category": "profitability"
        },
        "realized_cap": {
            "endpoint": "/v1/metrics/market/marketcap_realized_usd",
            "description": "Realized Market Cap (USD)",
            "category": "valuation"
        },
        "hash_rate": {
            "endpoint": "/v1/metrics/mining/hash_rate_mean",
            "description": "Mean hash rate (BTC only)",
            "category": "mining",
            "assets": ["BTC"]
        },
        "difficulty": {
            "endpoint": "/v1/metrics/mining/difficulty_latest",
            "description": "Mining difficulty (BTC only)",
            "category": "mining",
            "assets": ["BTC"]
        }
    }
    
    def __init__(
        self,
        database: Database,
        api_key: str,
        rate_limit: float = 1.0,  # Glassnode rate limit varies by tier
        timeout: int = 30
    ):
        """
        Initialize Glassnode collector
        
        Args:
            database: Database instance
            api_key: Glassnode API key
            rate_limit: Requests per second
            timeout: Request timeout in seconds
        """
        super().__init__(
            database=database,
            api_key=api_key,
            api_url="https://api.glassnode.com",
            collector_name="glassnode",
            rate_limit=rate_limit,
            timeout=timeout
        )
        
    async def collect(
        self,
        symbols: List[str] = None,
        metrics: List[str] = None,
        interval: str = "24h"
    ) -> bool:
        """
        Collect on-chain metrics from Glassnode
        
        Args:
            symbols: List of symbols to collect (default: BTC, ETH)
            metrics: List of metric names to collect (default: all)
            interval: Data interval (1h, 24h, 1w, 1month)
            
        Returns:
            True if collection successful, False otherwise
        """
        if symbols is None:
            symbols = self.SUPPORTED_ASSETS
            
        if metrics is None:
            metrics = list(self.METRICS.keys())
            
        try:
            logger.info(
                "Starting Glassnode data collection",
                symbols=symbols,
                metrics=metrics,
                interval=interval
            )
            
            collection_start = datetime.now(timezone.utc)
            total_metrics_collected = 0
            
            # Collect metrics for each symbol
            for symbol in symbols:
                if symbol not in self.SUPPORTED_ASSETS:
                    logger.warning(f"Unsupported asset: {symbol}")
                    continue
                    
                for metric_name in metrics:
                    if metric_name not in self.METRICS:
                        logger.warning(f"Unknown metric: {metric_name}")
                        continue
                        
                    metric_config = self.METRICS[metric_name]
                    
                    # Check if metric supports this asset
                    if "assets" in metric_config and symbol not in metric_config["assets"]:
                        continue
                        
                    # Collect metric
                    success = await self._collect_metric(
                        symbol,
                        metric_name,
                        metric_config,
                        interval
                    )
                    
                    if success:
                        total_metrics_collected += 1
                        
                    # Small delay between requests
                    await asyncio.sleep(0.5)
                    
            # Update collection stats
            self.stats["last_collection_time"] = collection_start.isoformat()
            self.stats["data_points_collected"] += total_metrics_collected
            
            # Log health status
            await self._log_health(CollectorStatus.HEALTHY, "Collection completed successfully")
            
            logger.info(
                "Glassnode data collection completed",
                symbols=symbols,
                metrics_collected=total_metrics_collected,
                duration_seconds=(datetime.now(timezone.utc) - collection_start).total_seconds()
            )
            
            return True
            
        except Exception as e:
            logger.error("Glassnode collection failed", error=str(e))
            await self._log_health(CollectorStatus.FAILED, str(e))
            return False
            
    async def _collect_metric(
        self,
        symbol: str,
        metric_name: str,
        metric_config: Dict,
        interval: str
    ) -> bool:
        """
        Collect a specific metric for a symbol
        
        Args:
            symbol: Asset symbol
            metric_name: Metric name
            metric_config: Metric configuration
            interval: Data interval
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Build request parameters
            params = {
                "a": symbol,  # Asset
                "i": interval,  # Interval
                "api_key": self.api_key
            }
            
            # Make request (don't pass api_key in headers as it's in params)
            response = await self._make_request(
                metric_config["endpoint"],
                params=params
            )
            
            if not response:
                logger.warning(
                    f"No data for {metric_name}",
                    symbol=symbol,
                    interval=interval
                )
                return False
                
            # Process response (Glassnode returns array of {t: timestamp, v: value})
            if not isinstance(response, list) or len(response) == 0:
                logger.warning(
                    f"Empty response for {metric_name}",
                    symbol=symbol
                )
                return False
                
            # Get latest data point
            latest_data = response[-1]
            
            # Prepare metric data
            metric_data = {
                "symbol": symbol,
                "metric_name": metric_name,
                "metric_category": metric_config["category"],
                "value": latest_data.get("v"),
                "timestamp": datetime.fromtimestamp(latest_data.get("t"), tz=timezone.utc),
                "interval": interval,
                "source": "glassnode",
                "description": metric_config["description"],
                "metadata": {
                    "data_points": len(response),
                    "endpoint": metric_config["endpoint"]
                }
            }
            
            # Store in database
            success = await self.database.store_onchain_metrics([metric_data])
            
            if success:
                logger.debug(
                    f"Stored {metric_name} for {symbol}",
                    value=metric_data["value"],
                    timestamp=metric_data["timestamp"].isoformat()
                )
            else:
                logger.warning(
                    f"Failed to store {metric_name} for {symbol}"
                )
                
            return success
            
        except Exception as e:
            logger.error(
                f"Error collecting {metric_name} for {symbol}",
                error=str(e)
            )
            return False
            
    async def get_metric_history(
        self,
        symbol: str,
        metric_name: str,
        since: datetime,
        until: Optional[datetime] = None,
        interval: str = "24h"
    ) -> Optional[List[Dict]]:
        """
        Get historical data for a metric
        
        Args:
            symbol: Asset symbol
            metric_name: Metric name
            since: Start datetime
            until: End datetime (default: now)
            interval: Data interval
            
        Returns:
            List of metric data points or None if failed
        """
        try:
            if metric_name not in self.METRICS:
                logger.error(f"Unknown metric: {metric_name}")
                return None
                
            metric_config = self.METRICS[metric_name]
            
            # Build request parameters
            params = {
                "a": symbol,
                "i": interval,
                "s": int(since.timestamp()),
                "api_key": self.api_key
            }
            
            if until:
                params["u"] = int(until.timestamp())
                
            # Make request
            response = await self._make_request(
                metric_config["endpoint"],
                params=params
            )
            
            if not response or not isinstance(response, list):
                return None
                
            # Format response
            history = []
            for data_point in response:
                history.append({
                    "timestamp": datetime.fromtimestamp(data_point.get("t"), tz=timezone.utc),
                    "value": data_point.get("v"),
                    "metric_name": metric_name,
                    "symbol": symbol
                })
                
            return history
            
        except Exception as e:
            logger.error(
                f"Error getting metric history",
                metric=metric_name,
                symbol=symbol,
                error=str(e)
            )
            return None
            
    async def get_exchange_flows_summary(self, symbol: str) -> Optional[Dict]:
        """
        Get comprehensive exchange flow summary
        
        Args:
            symbol: Asset symbol
            
        Returns:
            Summary dict with inflow, outflow, netflow
        """
        try:
            summary = {
                "symbol": symbol,
                "timestamp": datetime.now(timezone.utc)
            }
            
            # Collect all flow metrics
            for flow_type in ["exchange_netflow", "exchange_inflow", "exchange_outflow"]:
                metric_config = self.METRICS[flow_type]
                
                params = {
                    "a": symbol,
                    "i": "24h",
                    "api_key": self.api_key
                }
                
                response = await self._make_request(
                    metric_config["endpoint"],
                    params=params
                )
                
                if response and isinstance(response, list) and len(response) > 0:
                    latest = response[-1]
                    summary[flow_type] = latest.get("v")
                else:
                    summary[flow_type] = None
                    
                await asyncio.sleep(0.5)
                
            return summary
            
        except Exception as e:
            logger.error(
                f"Error getting exchange flows summary",
                symbol=symbol,
                error=str(e)
            )
            return None
            
    async def get_valuation_metrics(self, symbol: str) -> Optional[Dict]:
        """
        Get comprehensive valuation metrics
        
        Args:
            symbol: Asset symbol
            
        Returns:
            Dict with NVT, MVRV, NUPL, realized cap
        """
        try:
            valuation = {
                "symbol": symbol,
                "timestamp": datetime.now(timezone.utc)
            }
            
            # Valuation metrics
            valuation_metrics = ["nvt", "mvrv", "nupl", "realized_cap"]
            
            for metric_name in valuation_metrics:
                metric_config = self.METRICS[metric_name]
                
                params = {
                    "a": symbol,
                    "i": "24h",
                    "api_key": self.api_key
                }
                
                response = await self._make_request(
                    metric_config["endpoint"],
                    params=params
                )
                
                if response and isinstance(response, list) and len(response) > 0:
                    latest = response[-1]
                    valuation[metric_name] = latest.get("v")
                else:
                    valuation[metric_name] = None
                    
                await asyncio.sleep(0.5)
                
            return valuation
            
        except Exception as e:
            logger.error(
                f"Error getting valuation metrics",
                symbol=symbol,
                error=str(e)
            )
            return None
