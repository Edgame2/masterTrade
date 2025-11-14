"""
Flow Data Store - TimescaleDB-optimized storage for on-chain and exchange flow data

This module provides high-performance access to flow data:
- Whale wallet movements
- Exchange inflows/outflows
- Large transaction detection
- Net flow analysis

Features:
- Real-time flow tracking
- Whale activity monitoring
- Exchange flow analysis
- Net flow calculations
- Flow aggregation (hourly, daily)

Usage:
    store = FlowDataStore(database)
    
    # Store flow data
    await store.store_flow(
        asset="BTC",
        flow_type="exchange_inflow",
        amount=100.5,
        source="binance",
        timestamp=datetime.now()
    )
    
    # Get net flow
    net_flow = await store.get_net_flow(
        asset="BTC",
        hours=24
    )
"""

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
from decimal import Decimal
import structlog

from prometheus_client import Counter, Histogram

logger = structlog.get_logger()

# Metrics
flow_inserts = Counter('flow_data_inserts_total', 'Total flow inserts', ['asset', 'flow_type'])
flow_queries = Counter('flow_data_queries_total', 'Total flow queries', ['query_type'])
flow_query_duration = Histogram('flow_query_seconds', 'Flow query duration', ['query_type'])


class FlowDataStore:
    """
    TimescaleDB-optimized flow data storage
    
    Stores and analyzes on-chain and exchange flow data:
    - Whale movements (large wallet transactions)
    - Exchange inflows/outflows
    - Net flow calculations
    - Flow velocity and acceleration
    - Hourly and daily aggregates
    """
    
    FLOW_TYPES = [
        'exchange_inflow',
        'exchange_outflow',
        'whale_transfer',
        'large_transaction',
        'smart_money_flow',
        'miner_outflow'
    ]
    
    EXCHANGE_SOURCES = [
        'binance',
        'coinbase',
        'kraken',
        'bitfinex',
        'okx',
        'huobi',
        'bybit'
    ]
    
    def __init__(self, database):
        """
        Initialize flow data store
        
        Args:
            database: Database connection instance
        """
        self.database = database
    
    async def store_flow(
        self,
        asset: str,
        flow_type: str,
        timestamp: datetime,
        amount: float,
        source: Optional[str] = None,
        transaction_hash: Optional[str] = None,
        from_address: Optional[str] = None,
        to_address: Optional[str] = None,
        usd_value: Optional[float] = None,
        metadata: Optional[Dict] = None
    ) -> bool:
        """
        Store single flow data point
        
        Args:
            asset: Asset symbol (e.g., "BTC", "ETH")
            flow_type: Type of flow (exchange_inflow, whale_transfer, etc.)
            timestamp: Flow timestamp
            amount: Amount transferred
            source: Exchange or wallet source
            transaction_hash: On-chain transaction hash
            from_address: Source address
            to_address: Destination address
            usd_value: USD value of transfer
            metadata: Additional metadata
        
        Returns:
            True if successful, False otherwise
        """
        try:
            query = """
                INSERT INTO flow_data (
                    time, asset, flow_type, amount, source,
                    transaction_hash, from_address, to_address,
                    usd_value, metadata
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                ON CONFLICT (time, asset, flow_type, transaction_hash)
                DO UPDATE SET
                    amount = EXCLUDED.amount,
                    usd_value = EXCLUDED.usd_value,
                    metadata = EXCLUDED.metadata
            """
            
            await self.database.execute(
                query,
                timestamp, asset, flow_type,
                Decimal(str(amount)),
                source,
                transaction_hash,
                from_address,
                to_address,
                Decimal(str(usd_value)) if usd_value else None,
                metadata
            )
            
            flow_inserts.labels(asset=asset, flow_type=flow_type).inc()
            
            logger.debug(
                "Stored flow data",
                asset=asset,
                flow_type=flow_type,
                amount=amount,
                source=source
            )
            
            return True
            
        except Exception as e:
            logger.error(
                "Failed to store flow data",
                asset=asset,
                flow_type=flow_type,
                error=str(e),
                exc_info=True
            )
            return False
    
    async def store_flows_batch(
        self,
        flows: List[Dict[str, Any]]
    ) -> int:
        """
        Store multiple flow data points in batch
        
        Args:
            flows: List of flow dicts
        
        Returns:
            Number of records inserted
        """
        if not flows:
            return 0
        
        try:
            query = """
                INSERT INTO flow_data (
                    time, asset, flow_type, amount, source,
                    transaction_hash, from_address, to_address,
                    usd_value, metadata
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                ON CONFLICT (time, asset, flow_type, transaction_hash) DO NOTHING
            """
            
            batch_data = [
                (
                    flow['timestamp'],
                    flow['asset'],
                    flow['flow_type'],
                    Decimal(str(flow['amount'])),
                    flow.get('source'),
                    flow.get('transaction_hash'),
                    flow.get('from_address'),
                    flow.get('to_address'),
                    Decimal(str(flow['usd_value'])) if flow.get('usd_value') else None,
                    flow.get('metadata')
                )
                for flow in flows
            ]
            
            await self.database.executemany(query, batch_data)
            
            for flow in flows:
                flow_inserts.labels(asset=flow['asset'], flow_type=flow['flow_type']).inc()
            
            logger.info(
                "Stored flow batch",
                count=len(flows)
            )
            
            return len(flows)
            
        except Exception as e:
            logger.error(
                "Failed to store flow batch",
                count=len(flows),
                error=str(e),
                exc_info=True
            )
            return 0
    
    async def get_flow_history(
        self,
        asset: str,
        start_time: datetime,
        end_time: datetime,
        flow_type: Optional[str] = None,
        source: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get raw flow data for time range
        
        Args:
            asset: Asset symbol
            start_time: Start of time range
            end_time: End of time range
            flow_type: Filter by flow type (optional)
            source: Filter by source (optional)
        
        Returns:
            List of flow data dicts
        """
        with flow_query_duration.labels(query_type='history').time():
            try:
                conditions = ["asset = $1", "time >= $2", "time <= $3"]
                params = [asset, start_time, end_time]
                param_count = 3
                
                if flow_type:
                    param_count += 1
                    conditions.append(f"flow_type = ${param_count}")
                    params.append(flow_type)
                
                if source:
                    param_count += 1
                    conditions.append(f"source = ${param_count}")
                    params.append(source)
                
                query = f"""
                    SELECT 
                        time,
                        asset,
                        flow_type,
                        amount,
                        source,
                        transaction_hash,
                        usd_value
                    FROM flow_data
                    WHERE {' AND '.join(conditions)}
                    ORDER BY time ASC
                """
                
                rows = await self.database.fetch(query, *params)
                
                flow_queries.labels(query_type='history').inc()
                
                return [
                    {
                        'time': row['time'],
                        'asset': row['asset'],
                        'flow_type': row['flow_type'],
                        'amount': float(row['amount']),
                        'source': row['source'],
                        'transaction_hash': row['transaction_hash'],
                        'usd_value': float(row['usd_value']) if row.get('usd_value') else None
                    }
                    for row in rows
                ]
                
            except Exception as e:
                logger.error(
                    "Failed to get flow history",
                    asset=asset,
                    error=str(e)
                )
                return []
    
    async def get_flow_aggregated(
        self,
        asset: str,
        start_time: datetime,
        end_time: datetime,
        interval: str = '1h',
        flow_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get aggregated flow data (uses continuous aggregates)
        
        Args:
            asset: Asset symbol
            start_time: Start of time range
            end_time: End of time range
            interval: Aggregation interval ('1h' or '1d')
            flow_type: Filter by flow type (optional)
        
        Returns:
            List of aggregated flow dicts
        """
        with flow_query_duration.labels(query_type='aggregated').time():
            try:
                view_name = 'flow_hourly' if interval == '1h' else 'flow_daily'
                
                if flow_type:
                    query = f"""
                        SELECT 
                            bucket as time,
                            asset,
                            flow_type,
                            total_amount,
                            total_usd_value,
                            flow_count
                        FROM {view_name}
                        WHERE asset = $1 
                            AND flow_type = $2
                            AND bucket >= $3
                            AND bucket <= $4
                        ORDER BY bucket ASC
                    """
                    rows = await self.database.fetch(query, asset, flow_type, start_time, end_time)
                else:
                    query = f"""
                        SELECT 
                            bucket as time,
                            asset,
                            flow_type,
                            total_amount,
                            total_usd_value,
                            flow_count
                        FROM {view_name}
                        WHERE asset = $1 
                            AND bucket >= $2
                            AND bucket <= $3
                        ORDER BY bucket ASC
                    """
                    rows = await self.database.fetch(query, asset, start_time, end_time)
                
                flow_queries.labels(query_type='aggregated').inc()
                
                return [
                    {
                        'time': row['time'],
                        'asset': row['asset'],
                        'flow_type': row['flow_type'],
                        'total_amount': float(row['total_amount']),
                        'total_usd_value': float(row['total_usd_value']) if row['total_usd_value'] else 0,
                        'flow_count': row['flow_count']
                    }
                    for row in rows
                ]
                
            except Exception as e:
                logger.error(
                    "Failed to get aggregated flow",
                    asset=asset,
                    interval=interval,
                    error=str(e)
                )
                return []
    
    async def get_net_flow(
        self,
        asset: str,
        hours: int = 24,
        source: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Calculate net flow (inflow - outflow)
        
        Args:
            asset: Asset symbol
            hours: Hours to analyze
            source: Filter by source (optional)
        
        Returns:
            Dict with inflow, outflow, net_flow metrics
        """
        with flow_query_duration.labels(query_type='net_flow').time():
            try:
                if source:
                    query = """
                        SELECT 
                            SUM(CASE WHEN flow_type = 'exchange_inflow' THEN amount ELSE 0 END) as total_inflow,
                            SUM(CASE WHEN flow_type = 'exchange_outflow' THEN amount ELSE 0 END) as total_outflow,
                            SUM(CASE WHEN flow_type = 'exchange_inflow' THEN usd_value ELSE 0 END) as inflow_usd,
                            SUM(CASE WHEN flow_type = 'exchange_outflow' THEN usd_value ELSE 0 END) as outflow_usd,
                            COUNT(CASE WHEN flow_type = 'exchange_inflow' THEN 1 END) as inflow_count,
                            COUNT(CASE WHEN flow_type = 'exchange_outflow' THEN 1 END) as outflow_count
                        FROM flow_data
                        WHERE asset = $1
                            AND source = $2
                            AND time >= NOW() - ($3 || ' hours')::INTERVAL
                    """
                    row = await self.database.fetchrow(query, asset, source, hours)
                else:
                    query = """
                        SELECT 
                            SUM(CASE WHEN flow_type = 'exchange_inflow' THEN amount ELSE 0 END) as total_inflow,
                            SUM(CASE WHEN flow_type = 'exchange_outflow' THEN amount ELSE 0 END) as total_outflow,
                            SUM(CASE WHEN flow_type = 'exchange_inflow' THEN usd_value ELSE 0 END) as inflow_usd,
                            SUM(CASE WHEN flow_type = 'exchange_outflow' THEN usd_value ELSE 0 END) as outflow_usd,
                            COUNT(CASE WHEN flow_type = 'exchange_inflow' THEN 1 END) as inflow_count,
                            COUNT(CASE WHEN flow_type = 'exchange_outflow' THEN 1 END) as outflow_count
                        FROM flow_data
                        WHERE asset = $1
                            AND time >= NOW() - ($2 || ' hours')::INTERVAL
                    """
                    row = await self.database.fetchrow(query, asset, hours)
                
                flow_queries.labels(query_type='net_flow').inc()
                
                if not row:
                    return {}
                
                total_inflow = float(row['total_inflow'] or 0)
                total_outflow = float(row['total_outflow'] or 0)
                net_flow = total_inflow - total_outflow
                
                return {
                    'asset': asset,
                    'hours': hours,
                    'total_inflow': total_inflow,
                    'total_outflow': total_outflow,
                    'net_flow': net_flow,
                    'inflow_usd': float(row['inflow_usd'] or 0),
                    'outflow_usd': float(row['outflow_usd'] or 0),
                    'net_flow_usd': float(row['inflow_usd'] or 0) - float(row['outflow_usd'] or 0),
                    'inflow_count': row['inflow_count'],
                    'outflow_count': row['outflow_count'],
                    'flow_ratio': total_inflow / total_outflow if total_outflow > 0 else None
                }
                
            except Exception as e:
                logger.error(
                    "Failed to get net flow",
                    asset=asset,
                    error=str(e)
                )
                return {}
    
    async def get_whale_activity(
        self,
        asset: str,
        hours: int = 24,
        min_amount: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """
        Get whale transactions (large transfers)
        
        Args:
            asset: Asset symbol
            hours: Hours to analyze
            min_amount: Minimum amount threshold (optional)
        
        Returns:
            List of whale transaction dicts
        """
        with flow_query_duration.labels(query_type='whale').time():
            try:
                if min_amount:
                    query = """
                        SELECT 
                            time,
                            asset,
                            flow_type,
                            amount,
                            source,
                            transaction_hash,
                            usd_value
                        FROM flow_data
                        WHERE asset = $1
                            AND flow_type IN ('whale_transfer', 'large_transaction')
                            AND amount >= $2
                            AND time >= NOW() - ($3 || ' hours')::INTERVAL
                        ORDER BY amount DESC
                        LIMIT 100
                    """
                    rows = await self.database.fetch(query, asset, Decimal(str(min_amount)), hours)
                else:
                    query = """
                        SELECT 
                            time,
                            asset,
                            flow_type,
                            amount,
                            source,
                            transaction_hash,
                            usd_value
                        FROM flow_data
                        WHERE asset = $1
                            AND flow_type IN ('whale_transfer', 'large_transaction')
                            AND time >= NOW() - ($2 || ' hours')::INTERVAL
                        ORDER BY amount DESC
                        LIMIT 100
                    """
                    rows = await self.database.fetch(query, asset, hours)
                
                flow_queries.labels(query_type='whale').inc()
                
                return [
                    {
                        'time': row['time'],
                        'asset': row['asset'],
                        'flow_type': row['flow_type'],
                        'amount': float(row['amount']),
                        'source': row['source'],
                        'transaction_hash': row['transaction_hash'],
                        'usd_value': float(row['usd_value']) if row.get('usd_value') else None
                    }
                    for row in rows
                ]
                
            except Exception as e:
                logger.error(
                    "Failed to get whale activity",
                    asset=asset,
                    error=str(e)
                )
                return []
    
    async def get_exchange_flows(
        self,
        asset: str,
        hours: int = 24
    ) -> Dict[str, Dict[str, Any]]:
        """
        Get flow breakdown by exchange
        
        Args:
            asset: Asset symbol
            hours: Hours to analyze
        
        Returns:
            Dict mapping exchange name to flow metrics
        """
        with flow_query_duration.labels(query_type='by_exchange').time():
            try:
                query = """
                    SELECT 
                        source,
                        SUM(CASE WHEN flow_type = 'exchange_inflow' THEN amount ELSE 0 END) as total_inflow,
                        SUM(CASE WHEN flow_type = 'exchange_outflow' THEN amount ELSE 0 END) as total_outflow,
                        SUM(CASE WHEN flow_type = 'exchange_inflow' THEN usd_value ELSE 0 END) as inflow_usd,
                        SUM(CASE WHEN flow_type = 'exchange_outflow' THEN usd_value ELSE 0 END) as outflow_usd,
                        COUNT(*) as total_transactions
                    FROM flow_data
                    WHERE asset = $1
                        AND source IN ('binance', 'coinbase', 'kraken', 'bitfinex', 'okx', 'huobi', 'bybit')
                        AND time >= NOW() - ($2 || ' hours')::INTERVAL
                    GROUP BY source
                    ORDER BY total_inflow + total_outflow DESC
                """
                
                rows = await self.database.fetch(query, asset, hours)
                
                flow_queries.labels(query_type='by_exchange').inc()
                
                return {
                    row['source']: {
                        'total_inflow': float(row['total_inflow'] or 0),
                        'total_outflow': float(row['total_outflow'] or 0),
                        'net_flow': float(row['total_inflow'] or 0) - float(row['total_outflow'] or 0),
                        'inflow_usd': float(row['inflow_usd'] or 0),
                        'outflow_usd': float(row['outflow_usd'] or 0),
                        'total_transactions': row['total_transactions']
                    }
                    for row in rows
                }
                
            except Exception as e:
                logger.error(
                    "Failed to get exchange flows",
                    asset=asset,
                    error=str(e)
                )
                return {}
    
    async def get_flow_velocity(
        self,
        asset: str,
        hours: int = 24
    ) -> Dict[str, Any]:
        """
        Calculate flow velocity (rate of change in flows)
        
        Args:
            asset: Asset symbol
            hours: Hours to analyze
        
        Returns:
            Dict with velocity metrics
        """
        with flow_query_duration.labels(query_type='velocity').time():
            try:
                query = """
                    WITH hourly_flows AS (
                        SELECT 
                            time_bucket('1 hour', time) as hour,
                            SUM(CASE WHEN flow_type = 'exchange_inflow' THEN amount ELSE 0 END) as inflow,
                            SUM(CASE WHEN flow_type = 'exchange_outflow' THEN amount ELSE 0 END) as outflow
                        FROM flow_data
                        WHERE asset = $1
                            AND time >= NOW() - ($2 || ' hours')::INTERVAL
                        GROUP BY hour
                        ORDER BY hour DESC
                    ),
                    recent_vs_older AS (
                        SELECT 
                            AVG(CASE WHEN hour >= NOW() - INTERVAL '3 hours' THEN inflow END) as recent_inflow_avg,
                            AVG(CASE WHEN hour < NOW() - INTERVAL '3 hours' THEN inflow END) as older_inflow_avg,
                            AVG(CASE WHEN hour >= NOW() - INTERVAL '3 hours' THEN outflow END) as recent_outflow_avg,
                            AVG(CASE WHEN hour < NOW() - INTERVAL '3 hours' THEN outflow END) as older_outflow_avg
                        FROM hourly_flows
                    )
                    SELECT 
                        recent_inflow_avg,
                        older_inflow_avg,
                        recent_outflow_avg,
                        older_outflow_avg,
                        (recent_inflow_avg - older_inflow_avg) as inflow_velocity,
                        (recent_outflow_avg - older_outflow_avg) as outflow_velocity
                    FROM recent_vs_older
                """
                
                row = await self.database.fetchrow(query, asset, hours)
                
                flow_queries.labels(query_type='velocity').inc()
                
                if not row:
                    return {}
                
                return {
                    'asset': asset,
                    'recent_inflow_avg': float(row['recent_inflow_avg'] or 0),
                    'older_inflow_avg': float(row['older_inflow_avg'] or 0),
                    'recent_outflow_avg': float(row['recent_outflow_avg'] or 0),
                    'older_outflow_avg': float(row['older_outflow_avg'] or 0),
                    'inflow_velocity': float(row['inflow_velocity'] or 0),
                    'outflow_velocity': float(row['outflow_velocity'] or 0),
                    'net_velocity': float(row['inflow_velocity'] or 0) - float(row['outflow_velocity'] or 0)
                }
                
            except Exception as e:
                logger.error(
                    "Failed to get flow velocity",
                    asset=asset,
                    error=str(e)
                )
                return {}
