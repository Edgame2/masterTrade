"""
PostgreSQL-Based Feature Store

Manages ML features for trading strategies:
- Feature registration and versioning
- Time-series feature value storage
- Point-in-time feature retrieval
- Feature metadata management
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from decimal import Decimal

logger = logging.getLogger(__name__)


@dataclass
class FeatureDefinition:
    """Feature definition metadata"""
    id: int
    feature_name: str
    feature_type: str  # technical, onchain, social, macro, composite
    description: Optional[str]
    data_sources: List[str]
    computation_logic: Optional[str]
    version: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


@dataclass
class FeatureValue:
    """Time-series feature value"""
    feature_id: int
    symbol: str
    value: float
    timestamp: datetime


class PostgreSQLFeatureStore:
    """
    PostgreSQL-based feature store for ML trading features.
    
    Features:
    - Feature registration with versioning
    - Time-series storage of feature values
    - Point-in-time queries for backtesting
    - Bulk operations for efficiency
    - Feature metadata management
    - Integration with PostgresManager
    """
    
    def __init__(self, postgres_manager):
        """
        Initialize feature store.
        
        Args:
            postgres_manager: PostgresManager instance from shared/postgres_manager.py
        """
        self.db = postgres_manager
        logger.info("PostgreSQL feature store initialized")
    
    async def register_feature(
        self,
        feature_name: str,
        feature_type: str,
        description: Optional[str] = None,
        data_sources: Optional[List[str]] = None,
        computation_logic: Optional[str] = None,
        version: int = 1
    ) -> int:
        """
        Register a new feature definition.
        
        Args:
            feature_name: Unique feature identifier (e.g., 'rsi_14', 'nvt_ratio')
            feature_type: Category (technical, onchain, social, macro, composite)
            description: Human-readable description
            data_sources: List of data source services
            computation_logic: Description of computation method
            version: Version number (default 1)
            
        Returns:
            Feature ID
            
        Raises:
            ValueError: If feature already exists or invalid parameters
        """
        try:
            if not feature_name or not feature_type:
                raise ValueError("feature_name and feature_type are required")
            
            data_sources = data_sources or []
            
            query = """
                INSERT INTO feature_definitions (
                    feature_name, feature_type, description, data_sources,
                    computation_logic, version, is_active
                ) VALUES ($1, $2, $3, $4, $5, $6, TRUE)
                ON CONFLICT (feature_name) DO UPDATE SET
                    feature_type = EXCLUDED.feature_type,
                    description = EXCLUDED.description,
                    data_sources = EXCLUDED.data_sources,
                    computation_logic = EXCLUDED.computation_logic,
                    version = EXCLUDED.version,
                    updated_at = NOW()
                RETURNING id
            """
            
            async with self.db.acquire() as conn:
                feature_id = await conn.fetchval(
                    query,
                    feature_name,
                    feature_type,
                    description,
                    data_sources,
                    computation_logic,
                    version
                )
            
            logger.info(
                "Feature registered",
                feature_name=feature_name,
                feature_id=feature_id,
                version=version
            )
            
            return feature_id
            
        except Exception as e:
            logger.error(f"Error registering feature '{feature_name}': {e}")
            raise
    
    async def store_feature_value(
        self,
        feature_id: int,
        symbol: str,
        value: float,
        timestamp: Optional[datetime] = None
    ) -> bool:
        """
        Store a single feature value.
        
        Args:
            feature_id: Feature definition ID
            symbol: Trading symbol (e.g., 'BTCUSDT')
            value: Computed feature value
            timestamp: Time of computation (default: now)
            
        Returns:
            True if successful
        """
        try:
            timestamp = timestamp or datetime.utcnow()
            
            query = """
                INSERT INTO feature_values (feature_id, symbol, value, timestamp)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (feature_id, symbol, timestamp) DO UPDATE SET
                    value = EXCLUDED.value,
                    created_at = NOW()
            """
            
            async with self.db.acquire() as conn:
                await conn.execute(query, feature_id, symbol, value, timestamp)
            
            return True
            
        except Exception as e:
            logger.error(
                f"Error storing feature value",
                feature_id=feature_id,
                symbol=symbol,
                error=str(e)
            )
            return False
    
    async def store_feature_values_bulk(
        self,
        values: List[Dict[str, Any]]
    ) -> int:
        """
        Store multiple feature values in bulk.
        
        Args:
            values: List of dicts with keys: feature_id, symbol, value, timestamp
            
        Returns:
            Number of values stored
        """
        try:
            if not values:
                return 0
            
            query = """
                INSERT INTO feature_values (feature_id, symbol, value, timestamp)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (feature_id, symbol, timestamp) DO UPDATE SET
                    value = EXCLUDED.value
            """
            
            async with self.db.acquire() as conn:
                await conn.executemany(
                    query,
                    [
                        (
                            v['feature_id'],
                            v['symbol'],
                            v['value'],
                            v.get('timestamp', datetime.utcnow())
                        )
                        for v in values
                    ]
                )
            
            logger.info(f"Stored {len(values)} feature values in bulk")
            return len(values)
            
        except Exception as e:
            logger.error(f"Error storing bulk feature values: {e}")
            return 0
    
    async def get_feature(
        self,
        feature_id: int,
        symbol: str,
        as_of_time: Optional[datetime] = None
    ) -> Optional[float]:
        """
        Get a single feature value at a point in time.
        
        Args:
            feature_id: Feature definition ID
            symbol: Trading symbol
            as_of_time: Point in time (default: most recent)
            
        Returns:
            Feature value or None if not found
        """
        try:
            if as_of_time:
                query = """
                    SELECT value
                    FROM feature_values
                    WHERE feature_id = $1 AND symbol = $2 AND timestamp <= $3
                    ORDER BY timestamp DESC
                    LIMIT 1
                """
                params = (feature_id, symbol, as_of_time)
            else:
                query = """
                    SELECT value
                    FROM feature_values
                    WHERE feature_id = $1 AND symbol = $2
                    ORDER BY timestamp DESC
                    LIMIT 1
                """
                params = (feature_id, symbol)
            
            async with self.db.acquire() as conn:
                result = await conn.fetchval(query, *params)
            
            return float(result) if result is not None else None
            
        except Exception as e:
            logger.error(
                f"Error getting feature value",
                feature_id=feature_id,
                symbol=symbol,
                error=str(e)
            )
            return None
    
    async def get_features_bulk(
        self,
        feature_ids: List[int],
        symbol: str,
        as_of_time: Optional[datetime] = None
    ) -> Dict[int, float]:
        """
        Get multiple feature values at a point in time.
        
        Args:
            feature_ids: List of feature definition IDs
            symbol: Trading symbol
            as_of_time: Point in time (default: most recent)
            
        Returns:
            Dict mapping feature_id to value
        """
        try:
            if not feature_ids:
                return {}
            
            if as_of_time:
                query = """
                    SELECT DISTINCT ON (feature_id) feature_id, value
                    FROM feature_values
                    WHERE feature_id = ANY($1) AND symbol = $2 AND timestamp <= $3
                    ORDER BY feature_id, timestamp DESC
                """
                params = (feature_ids, symbol, as_of_time)
            else:
                query = """
                    SELECT DISTINCT ON (feature_id) feature_id, value
                    FROM feature_values
                    WHERE feature_id = ANY($1) AND symbol = $2
                    ORDER BY feature_id, timestamp DESC
                """
                params = (feature_ids, symbol)
            
            async with self.db.acquire() as conn:
                rows = await conn.fetch(query, *params)
            
            return {row['feature_id']: float(row['value']) for row in rows}
            
        except Exception as e:
            logger.error(f"Error getting bulk feature values: {e}")
            return {}
    
    async def get_feature_by_name(
        self,
        feature_name: str,
        symbol: str,
        as_of_time: Optional[datetime] = None
    ) -> Optional[float]:
        """
        Get a feature value by feature name (convenience method).
        
        Args:
            feature_name: Feature name (e.g., 'rsi_14')
            symbol: Trading symbol
            as_of_time: Point in time (default: most recent)
            
        Returns:
            Feature value or None if not found
        """
        try:
            # Get feature ID first
            feature_id = await self.get_feature_id(feature_name)
            if not feature_id:
                return None
            
            return await self.get_feature(feature_id, symbol, as_of_time)
            
        except Exception as e:
            logger.error(f"Error getting feature by name '{feature_name}': {e}")
            return None
    
    async def get_feature_id(self, feature_name: str) -> Optional[int]:
        """
        Get feature ID by name.
        
        Args:
            feature_name: Feature name
            
        Returns:
            Feature ID or None if not found
        """
        try:
            query = """
                SELECT id FROM feature_definitions
                WHERE feature_name = $1 AND is_active = TRUE
            """
            
            async with self.db.acquire() as conn:
                result = await conn.fetchval(query, feature_name)
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting feature ID for '{feature_name}': {e}")
            return None
    
    async def get_feature_definition(
        self,
        feature_id: int
    ) -> Optional[FeatureDefinition]:
        """
        Get feature definition metadata.
        
        Args:
            feature_id: Feature definition ID
            
        Returns:
            FeatureDefinition or None if not found
        """
        try:
            query = """
                SELECT id, feature_name, feature_type, description, data_sources,
                       computation_logic, version, is_active, created_at, updated_at
                FROM feature_definitions
                WHERE id = $1
            """
            
            async with self.db.acquire() as conn:
                row = await conn.fetchrow(query, feature_id)
            
            if not row:
                return None
            
            return FeatureDefinition(
                id=row['id'],
                feature_name=row['feature_name'],
                feature_type=row['feature_type'],
                description=row['description'],
                data_sources=row['data_sources'],
                computation_logic=row['computation_logic'],
                version=row['version'],
                is_active=row['is_active'],
                created_at=row['created_at'],
                updated_at=row['updated_at']
            )
            
        except Exception as e:
            logger.error(f"Error getting feature definition {feature_id}: {e}")
            return None
    
    async def list_features(
        self,
        feature_type: Optional[str] = None,
        active_only: bool = True
    ) -> List[FeatureDefinition]:
        """
        List all feature definitions.
        
        Args:
            feature_type: Filter by feature type (optional)
            active_only: Only return active features (default True)
            
        Returns:
            List of FeatureDefinition objects
        """
        try:
            conditions = []
            params = []
            param_idx = 1
            
            if active_only:
                conditions.append("is_active = TRUE")
            
            if feature_type:
                conditions.append(f"feature_type = ${param_idx}")
                params.append(feature_type)
                param_idx += 1
            
            where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
            
            query = f"""
                SELECT id, feature_name, feature_type, description, data_sources,
                       computation_logic, version, is_active, created_at, updated_at
                FROM feature_definitions
                {where_clause}
                ORDER BY feature_type, feature_name
            """
            
            async with self.db.acquire() as conn:
                rows = await conn.fetch(query, *params)
            
            return [
                FeatureDefinition(
                    id=row['id'],
                    feature_name=row['feature_name'],
                    feature_type=row['feature_type'],
                    description=row['description'],
                    data_sources=row['data_sources'],
                    computation_logic=row['computation_logic'],
                    version=row['version'],
                    is_active=row['is_active'],
                    created_at=row['created_at'],
                    updated_at=row['updated_at']
                )
                for row in rows
            ]
            
        except Exception as e:
            logger.error(f"Error listing features: {e}")
            return []
    
    async def get_feature_history(
        self,
        feature_id: int,
        symbol: str,
        start_time: datetime,
        end_time: Optional[datetime] = None,
        limit: int = 1000
    ) -> List[FeatureValue]:
        """
        Get feature value history for a symbol.
        
        Args:
            feature_id: Feature definition ID
            symbol: Trading symbol
            start_time: Start of time range
            end_time: End of time range (default: now)
            limit: Maximum number of values to return
            
        Returns:
            List of FeatureValue objects ordered by timestamp DESC
        """
        try:
            end_time = end_time or datetime.utcnow()
            
            query = """
                SELECT feature_id, symbol, value, timestamp
                FROM feature_values
                WHERE feature_id = $1 AND symbol = $2 
                    AND timestamp >= $3 AND timestamp <= $4
                ORDER BY timestamp DESC
                LIMIT $5
            """
            
            async with self.db.acquire() as conn:
                rows = await conn.fetch(
                    query, feature_id, symbol, start_time, end_time, limit
                )
            
            return [
                FeatureValue(
                    feature_id=row['feature_id'],
                    symbol=row['symbol'],
                    value=float(row['value']),
                    timestamp=row['timestamp']
                )
                for row in rows
            ]
            
        except Exception as e:
            logger.error(f"Error getting feature history: {e}")
            return []
    
    async def deactivate_feature(self, feature_id: int) -> bool:
        """
        Deactivate a feature (soft delete).
        
        Args:
            feature_id: Feature definition ID
            
        Returns:
            True if successful
        """
        try:
            query = """
                UPDATE feature_definitions
                SET is_active = FALSE, updated_at = NOW()
                WHERE id = $1
            """
            
            async with self.db.acquire() as conn:
                await conn.execute(query, feature_id)
            
            logger.info(f"Feature {feature_id} deactivated")
            return True
            
        except Exception as e:
            logger.error(f"Error deactivating feature {feature_id}: {e}")
            return False
    
    async def cleanup_old_values(self, days: int = 90) -> int:
        """
        Delete feature values older than specified days.
        
        Args:
            days: Delete values older than this many days
            
        Returns:
            Number of rows deleted
        """
        try:
            cutoff = datetime.utcnow() - timedelta(days=days)
            
            query = """
                DELETE FROM feature_values
                WHERE timestamp < $1
            """
            
            async with self.db.acquire() as conn:
                result = await conn.execute(query, cutoff)
            
            # Extract count from result string like "DELETE 1234"
            count = int(result.split()[-1]) if result else 0
            
            logger.info(f"Cleaned up {count} old feature values (older than {days} days)")
            return count
            
        except Exception as e:
            logger.error(f"Error cleaning up old values: {e}")
            return 0
    
    async def get_statistics(self) -> Dict[str, Any]:
        """
        Get feature store statistics.
        
        Returns:
            Dict with statistics
        """
        try:
            async with self.db.acquire() as conn:
                # Count features by type
                feature_counts = await conn.fetch("""
                    SELECT feature_type, COUNT(*) as count
                    FROM feature_definitions
                    WHERE is_active = TRUE
                    GROUP BY feature_type
                """)
                
                # Total feature values
                total_values = await conn.fetchval("""
                    SELECT COUNT(*) FROM feature_values
                """)
                
                # Recent values (last 24 hours)
                recent_values = await conn.fetchval("""
                    SELECT COUNT(*) FROM feature_values
                    WHERE timestamp > NOW() - INTERVAL '24 hours'
                """)
                
                # Unique symbols
                unique_symbols = await conn.fetchval("""
                    SELECT COUNT(DISTINCT symbol) FROM feature_values
                """)
            
            return {
                "features_by_type": {row['feature_type']: row['count'] for row in feature_counts},
                "total_feature_values": total_values,
                "recent_values_24h": recent_values,
                "unique_symbols": unique_symbols,
                "timestamp": datetime.utcnow()
            }
            
        except Exception as e:
            logger.error(f"Error getting statistics: {e}")
            return {}
