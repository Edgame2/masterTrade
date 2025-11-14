"""
DeFi Protocol Metrics Collector

Collects TVL (Total Value Locked), fees, liquidity, and other metrics from major DeFi protocols
using TheGraph and Dune Analytics APIs.

Supported Protocols:
- Uniswap V2/V3
- Aave V2/V3
- Compound
- Curve
- MakerDAO
- Lido
- Balancer
- SushiSwap
"""

import asyncio
import aiohttp
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from decimal import Decimal

logger = logging.getLogger(__name__)


class DeFiProtocolCollector:
    """
    Collects DeFi protocol metrics from TheGraph and Dune Analytics.
    """
    
    # TheGraph API endpoints
    THEGRAPH_ENDPOINTS = {
        "uniswap_v2": "https://api.thegraph.com/subgraphs/name/uniswap/uniswap-v2",
        "uniswap_v3": "https://api.thegraph.com/subgraphs/name/uniswap/uniswap-v3",
        "aave_v2": "https://api.thegraph.com/subgraphs/name/aave/protocol-v2",
        "aave_v3": "https://api.thegraph.com/subgraphs/name/aave/protocol-v3",
        "compound": "https://api.thegraph.com/subgraphs/name/graphprotocol/compound-v2",
        "curve": "https://api.thegraph.com/subgraphs/name/convex-community/curve-pools",
        "balancer": "https://api.thegraph.com/subgraphs/name/balancer-labs/balancer-v2",
        "sushiswap": "https://api.thegraph.com/subgraphs/name/sushiswap/exchange",
    }
    
    # Dune Analytics base URL
    DUNE_API_BASE = "https://api.dune.com/api/v1"
    
    # Protocol categories
    PROTOCOL_CATEGORIES = {
        "dex": ["uniswap_v2", "uniswap_v3", "sushiswap", "curve", "balancer"],
        "lending": ["aave_v2", "aave_v3", "compound"],
        "staking": ["lido"],
        "stablecoin": ["maker"],
    }
    
    def __init__(self, database, dune_api_key: Optional[str] = None):
        """
        Initialize DeFi Protocol Collector.
        
        Args:
            database: Database instance for storing metrics
            dune_api_key: Optional Dune Analytics API key for premium features
        """
        self.database = database
        self.dune_api_key = dune_api_key
        self.session: Optional[aiohttp.ClientSession] = None
        
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session
        
    async def close(self):
        """Close aiohttp session."""
        if self.session and not self.session.closed:
            await self.session.close()
            
    async def _query_thegraph(self, endpoint: str, query: str) -> Dict[str, Any]:
        """
        Execute GraphQL query against TheGraph endpoint.
        
        Args:
            endpoint: TheGraph subgraph endpoint URL
            query: GraphQL query string
            
        Returns:
            Query results as dictionary
        """
        session = await self._get_session()
        
        try:
            async with session.post(
                endpoint,
                json={"query": query},
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    if "errors" in data:
                        logger.error(f"TheGraph query errors: {data['errors']}")
                        return {}
                    return data.get("data", {})
                else:
                    logger.error(f"TheGraph API error: {response.status}")
                    return {}
        except Exception as e:
            logger.error(f"Error querying TheGraph: {e}")
            return {}
            
    async def _query_dune(self, query_id: int, parameters: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Execute query against Dune Analytics API.
        
        Args:
            query_id: Dune query ID
            parameters: Optional query parameters
            
        Returns:
            Query results as dictionary
        """
        if not self.dune_api_key:
            logger.warning("Dune API key not configured, skipping Dune query")
            return {}
            
        session = await self._get_session()
        headers = {"X-Dune-API-Key": self.dune_api_key}
        
        try:
            # Execute query
            execute_url = f"{self.DUNE_API_BASE}/query/{query_id}/execute"
            async with session.post(
                execute_url,
                json={"query_parameters": parameters or {}},
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status != 200:
                    logger.error(f"Dune execute error: {response.status}")
                    return {}
                    
                execute_data = await response.json()
                execution_id = execute_data.get("execution_id")
                
            if not execution_id:
                return {}
                
            # Poll for results
            status_url = f"{self.DUNE_API_BASE}/execution/{execution_id}/status"
            for _ in range(30):  # Max 30 attempts (30 seconds)
                await asyncio.sleep(1)
                
                async with session.get(status_url, headers=headers) as response:
                    if response.status != 200:
                        continue
                        
                    status_data = await response.json()
                    state = status_data.get("state")
                    
                    if state == "QUERY_STATE_COMPLETED":
                        # Get results
                        results_url = f"{self.DUNE_API_BASE}/execution/{execution_id}/results"
                        async with session.get(results_url, headers=headers) as results_response:
                            if results_response.status == 200:
                                return await results_response.json()
                        break
                    elif state == "QUERY_STATE_FAILED":
                        logger.error("Dune query failed")
                        break
                        
            return {}
            
        except Exception as e:
            logger.error(f"Error querying Dune: {e}")
            return {}
            
    # ============================================================================
    # Uniswap Metrics
    # ============================================================================
    
    async def collect_uniswap_metrics(self, version: str = "v3") -> Dict[str, Any]:
        """
        Collect Uniswap DEX metrics.
        
        Args:
            version: Uniswap version ("v2" or "v3")
            
        Returns:
            Metrics dictionary with TVL, volume, fees
        """
        endpoint_key = f"uniswap_{version}"
        endpoint = self.THEGRAPH_ENDPOINTS.get(endpoint_key)
        
        if not endpoint:
            logger.error(f"Unknown Uniswap version: {version}")
            return {}
            
        # Query for factory data (global metrics)
        query = """
        {
          factories(first: 1) {
            id
            totalVolumeUSD
            totalValueLockedUSD
            totalFeesUSD
            txCount
          }
        }
        """
        
        data = await self._query_thegraph(endpoint, query)
        
        if not data or "factories" not in data:
            return {}
            
        factory = data["factories"][0] if data["factories"] else {}
        
        metrics = {
            "protocol": f"uniswap_{version}",
            "category": "dex",
            "timestamp": datetime.utcnow().isoformat(),
            "tvl_usd": float(factory.get("totalValueLockedUSD", 0)),
            "volume_24h_usd": None,  # Need separate query for 24h
            "total_volume_usd": float(factory.get("totalVolumeUSD", 0)),
            "fees_24h_usd": None,
            "total_fees_usd": float(factory.get("totalFeesUSD", 0)),
            "transaction_count": int(factory.get("txCount", 0)),
            "metadata": factory
        }
        
        # Store in database
        await self.database.store_defi_protocol_metrics(metrics)
        
        logger.info(f"Collected Uniswap {version} metrics: TVL=${metrics['tvl_usd']:,.2f}")
        
        return metrics
        
    # ============================================================================
    # Aave Metrics
    # ============================================================================
    
    async def collect_aave_metrics(self, version: str = "v3") -> Dict[str, Any]:
        """
        Collect Aave lending protocol metrics.
        
        Args:
            version: Aave version ("v2" or "v3")
            
        Returns:
            Metrics dictionary with TVL, borrows, deposits
        """
        endpoint_key = f"aave_{version}"
        endpoint = self.THEGRAPH_ENDPOINTS.get(endpoint_key)
        
        if not endpoint:
            logger.error(f"Unknown Aave version: {version}")
            return {}
            
        # Query for protocol data
        query = """
        {
          protocols(first: 1) {
            totalValueLockedUSD
            totalDepositBalanceUSD
            totalBorrowBalanceUSD
          }
        }
        """
        
        data = await self._query_thegraph(endpoint, query)
        
        if not data or "protocols" not in data:
            return {}
            
        protocol = data["protocols"][0] if data["protocols"] else {}
        
        metrics = {
            "protocol": f"aave_{version}",
            "category": "lending",
            "timestamp": datetime.utcnow().isoformat(),
            "tvl_usd": float(protocol.get("totalValueLockedUSD", 0)),
            "total_deposits_usd": float(protocol.get("totalDepositBalanceUSD", 0)),
            "total_borrows_usd": float(protocol.get("totalBorrowBalanceUSD", 0)),
            "utilization_rate": 0.0,
            "metadata": protocol
        }
        
        # Calculate utilization rate
        if metrics["total_deposits_usd"] > 0:
            metrics["utilization_rate"] = metrics["total_borrows_usd"] / metrics["total_deposits_usd"]
            
        # Store in database
        await self.database.store_defi_protocol_metrics(metrics)
        
        logger.info(f"Collected Aave {version} metrics: TVL=${metrics['tvl_usd']:,.2f}, Util={metrics['utilization_rate']:.1%}")
        
        return metrics
        
    # ============================================================================
    # Curve Metrics
    # ============================================================================
    
    async def collect_curve_metrics(self) -> Dict[str, Any]:
        """
        Collect Curve DEX/stableswap metrics.
        
        Returns:
            Metrics dictionary with TVL, volume, fees
        """
        endpoint = self.THEGRAPH_ENDPOINTS.get("curve")
        
        if not endpoint:
            return {}
            
        # Query for platform data
        query = """
        {
          platforms(first: 1) {
            poolCount
            totalVolumeUSD
            totalValueLockedUSD
          }
        }
        """
        
        data = await self._query_thegraph(endpoint, query)
        
        if not data or "platforms" not in data:
            return {}
            
        platform = data["platforms"][0] if data["platforms"] else {}
        
        metrics = {
            "protocol": "curve",
            "category": "dex",
            "timestamp": datetime.utcnow().isoformat(),
            "tvl_usd": float(platform.get("totalValueLockedUSD", 0)),
            "total_volume_usd": float(platform.get("totalVolumeUSD", 0)),
            "pool_count": int(platform.get("poolCount", 0)),
            "metadata": platform
        }
        
        # Store in database
        await self.database.store_defi_protocol_metrics(metrics)
        
        logger.info(f"Collected Curve metrics: TVL=${metrics['tvl_usd']:,.2f}, Pools={metrics['pool_count']}")
        
        return metrics
        
    # ============================================================================
    # Compound Metrics
    # ============================================================================
    
    async def collect_compound_metrics(self) -> Dict[str, Any]:
        """
        Collect Compound lending protocol metrics.
        
        Returns:
            Metrics dictionary with TVL, borrows, deposits
        """
        endpoint = self.THEGRAPH_ENDPOINTS.get("compound")
        
        if not endpoint:
            return {}
            
        # Query for comptroller data
        query = """
        {
          comptrollers(first: 1) {
            totalBorrowValueInEth
            totalSupplyValueInEth
          }
        }
        """
        
        data = await self._query_thegraph(endpoint, query)
        
        if not data or "comptrollers" not in data:
            return {}
            
        comptroller = data["comptrollers"][0] if data["comptrollers"] else {}
        
        # Estimate USD values (using approximate ETH price)
        eth_price = 2000.0  # TODO: Get real-time ETH price
        
        metrics = {
            "protocol": "compound",
            "category": "lending",
            "timestamp": datetime.utcnow().isoformat(),
            "total_supply_usd": float(comptroller.get("totalSupplyValueInEth", 0)) * eth_price,
            "total_borrow_usd": float(comptroller.get("totalBorrowValueInEth", 0)) * eth_price,
            "tvl_usd": float(comptroller.get("totalSupplyValueInEth", 0)) * eth_price,
            "utilization_rate": 0.0,
            "metadata": comptroller
        }
        
        # Calculate utilization rate
        if metrics["total_supply_usd"] > 0:
            metrics["utilization_rate"] = metrics["total_borrow_usd"] / metrics["total_supply_usd"]
            
        # Store in database
        await self.database.store_defi_protocol_metrics(metrics)
        
        logger.info(f"Collected Compound metrics: TVL=${metrics['tvl_usd']:,.2f}, Util={metrics['utilization_rate']:.1%}")
        
        return metrics
        
    # ============================================================================
    # Batch Collection
    # ============================================================================
    
    async def collect_all_protocols(self) -> Dict[str, Any]:
        """
        Collect metrics from all supported protocols.
        
        Returns:
            Summary of collected metrics
        """
        results = {
            "timestamp": datetime.utcnow().isoformat(),
            "protocols": {},
            "total_tvl_usd": 0.0,
            "success_count": 0,
            "error_count": 0
        }
        
        # Collect from each protocol
        collectors = [
            ("uniswap_v2", lambda: self.collect_uniswap_metrics("v2")),
            ("uniswap_v3", lambda: self.collect_uniswap_metrics("v3")),
            ("aave_v2", lambda: self.collect_aave_metrics("v2")),
            ("aave_v3", lambda: self.collect_aave_metrics("v3")),
            ("curve", self.collect_curve_metrics),
            ("compound", self.collect_compound_metrics),
        ]
        
        for protocol_name, collector in collectors:
            try:
                metrics = await collector()
                if metrics:
                    results["protocols"][protocol_name] = metrics
                    results["total_tvl_usd"] += metrics.get("tvl_usd", 0)
                    results["success_count"] += 1
                else:
                    results["error_count"] += 1
            except Exception as e:
                logger.error(f"Error collecting {protocol_name}: {e}")
                results["error_count"] += 1
                
        logger.info(
            f"Collected DeFi metrics: {results['success_count']} protocols, "
            f"Total TVL=${results['total_tvl_usd']:,.2f}"
        )
        
        return results


# ============================================================================
# Scheduler Function
# ============================================================================

async def run_defi_collector_scheduler(database, dune_api_key: Optional[str] = None, interval_minutes: int = 60):
    """
    Run DeFi protocol collector on a schedule.
    
    Args:
        database: Database instance
        dune_api_key: Optional Dune Analytics API key
        interval_minutes: Collection interval in minutes (default: 60)
    """
    collector = DeFiProtocolCollector(database, dune_api_key)
    
    logger.info(f"Starting DeFi protocol collector (interval: {interval_minutes}m)")
    
    try:
        while True:
            try:
                results = await collector.collect_all_protocols()
                logger.info(f"DeFi collection complete: {results['success_count']} protocols")
            except Exception as e:
                logger.error(f"Error in DeFi collector cycle: {e}")
                
            await asyncio.sleep(interval_minutes * 60)
    finally:
        await collector.close()
