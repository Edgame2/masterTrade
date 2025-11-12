"""
Database module for Alert System
Handles PostgreSQL connections and alert storage
"""

import asyncpg
import structlog
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone, timedelta

logger = structlog.get_logger()


class Database:
    """PostgreSQL database manager for alerts"""
    
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.pool: Optional[asyncpg.Pool] = None
        
    async def connect(self):
        """Establish database connection pool"""
        try:
            self.pool = await asyncpg.create_pool(
                self.database_url,
                min_size=2,
                max_size=10,
                command_timeout=60,
            )
            logger.info("database_pool_created", min_size=2, max_size=10)
        except Exception as e:
            logger.error("database_connection_failed", error=str(e))
            raise
            
    async def close(self):
        """Close database connection pool"""
        if self.pool:
            await self.pool.close()
            logger.info("database_pool_closed")
            
    async def check_connection(self) -> bool:
        """Check if database is connected"""
        if not self.pool:
            return False
        try:
            async with self.pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            return True
        except Exception:
            return False
            
    async def initialize_alerts_schema(self):
        """Create alerts tables if they don't exist"""
        try:
            async with self.pool.acquire() as conn:
                # Alerts table
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS alerts (
                        alert_id TEXT PRIMARY KEY,
                        alert_type TEXT NOT NULL,
                        priority TEXT NOT NULL,
                        status TEXT NOT NULL,
                        title TEXT NOT NULL,
                        message TEXT NOT NULL,
                        created_at TIMESTAMP WITH TIME ZONE NOT NULL,
                        triggered_at TIMESTAMP WITH TIME ZONE,
                        sent_at TIMESTAMP WITH TIME ZONE,
                        acknowledged_at TIMESTAMP WITH TIME ZONE,
                        resolved_at TIMESTAMP WITH TIME ZONE,
                        expires_at TIMESTAMP WITH TIME ZONE,
                        trigger_count INTEGER DEFAULT 0,
                        channels TEXT[] NOT NULL,
                        symbol TEXT,
                        strategy_id TEXT,
                        metadata JSONB DEFAULT '{}'::jsonb,
                        condition_data JSONB DEFAULT '{}'::jsonb
                    )
                """)
                
                # Create indexes
                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_alerts_status 
                    ON alerts(status)
                """)
                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_alerts_priority 
                    ON alerts(priority)
                """)
                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_alerts_type 
                    ON alerts(alert_type)
                """)
                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_alerts_created 
                    ON alerts(created_at DESC)
                """)
                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_alerts_symbol 
                    ON alerts(symbol)
                """)
                
                # Alert suppressions table
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS alert_suppressions (
                        id SERIAL PRIMARY KEY,
                        symbol TEXT NOT NULL,
                        suppressed_until TIMESTAMP WITH TIME ZONE NOT NULL,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                    )
                """)
                
                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_suppressions_symbol_until 
                    ON alert_suppressions(symbol, suppressed_until)
                """)
                
                logger.info("alert_schema_initialized")
                
        except Exception as e:
            logger.error("schema_initialization_failed", error=str(e))
            raise
            
    async def save_alert(self, alert_data: Dict[str, Any]) -> bool:
        """Save alert to database"""
        try:
            async with self.pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO alerts (
                        alert_id, alert_type, priority, status, title, message,
                        created_at, triggered_at, sent_at, acknowledged_at, 
                        resolved_at, expires_at, trigger_count, channels,
                        symbol, strategy_id, metadata, condition_data
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18)
                    ON CONFLICT (alert_id) DO UPDATE SET
                        status = EXCLUDED.status,
                        triggered_at = EXCLUDED.triggered_at,
                        sent_at = EXCLUDED.sent_at,
                        acknowledged_at = EXCLUDED.acknowledged_at,
                        resolved_at = EXCLUDED.resolved_at,
                        trigger_count = EXCLUDED.trigger_count
                """,
                    alert_data["alert_id"],
                    alert_data["alert_type"],
                    alert_data["priority"],
                    alert_data["status"],
                    alert_data["title"],
                    alert_data["message"],
                    alert_data["created_at"],
                    alert_data.get("triggered_at"),
                    alert_data.get("sent_at"),
                    alert_data.get("acknowledged_at"),
                    alert_data.get("resolved_at"),
                    alert_data.get("expires_at"),
                    alert_data.get("trigger_count", 0),
                    alert_data["channels"],
                    alert_data.get("symbol"),
                    alert_data.get("strategy_id"),
                    alert_data.get("metadata", {}),
                    alert_data.get("condition_data", {})
                )
                return True
        except Exception as e:
            logger.error("save_alert_failed", error=str(e), alert_id=alert_data.get("alert_id"))
            return False
            
    async def get_alert(self, alert_id: str) -> Optional[Dict[str, Any]]:
        """Get alert by ID"""
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow("SELECT * FROM alerts WHERE alert_id = $1", alert_id)
                if row:
                    return dict(row)
                return None
        except Exception as e:
            logger.error("get_alert_failed", error=str(e), alert_id=alert_id)
            return None
            
    async def list_alerts(
        self,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        alert_type: Optional[str] = None,
        symbol: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """List alerts with filters"""
        try:
            query = "SELECT * FROM alerts WHERE 1=1"
            params = []
            param_count = 1
            
            if status:
                query += f" AND status = ${param_count}"
                params.append(status)
                param_count += 1
                
            if priority:
                query += f" AND priority = ${param_count}"
                params.append(priority)
                param_count += 1
                
            if alert_type:
                query += f" AND alert_type = ${param_count}"
                params.append(alert_type)
                param_count += 1
                
            if symbol:
                query += f" AND symbol = ${param_count}"
                params.append(symbol)
                param_count += 1
                
            query += f" ORDER BY created_at DESC LIMIT ${param_count}"
            params.append(limit)
            
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query, *params)
                return [dict(row) for row in rows]
                
        except Exception as e:
            logger.error("list_alerts_failed", error=str(e))
            return []
            
    async def update_alert_status(
        self,
        alert_id: str,
        status: str,
        timestamp_field: Optional[str] = None
    ) -> bool:
        """Update alert status"""
        try:
            async with self.pool.acquire() as conn:
                if timestamp_field:
                    await conn.execute(
                        f"UPDATE alerts SET status = $1, {timestamp_field} = $2 WHERE alert_id = $3",
                        status, datetime.now(timezone.utc), alert_id
                    )
                else:
                    await conn.execute(
                        "UPDATE alerts SET status = $1 WHERE alert_id = $2",
                        status, alert_id
                    )
                return True
        except Exception as e:
            logger.error("update_alert_status_failed", error=str(e), alert_id=alert_id)
            return False
            
    async def delete_old_alerts(self, days: int = 30) -> int:
        """Delete alerts older than specified days"""
        try:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
            async with self.pool.acquire() as conn:
                result = await conn.execute(
                    "DELETE FROM alerts WHERE created_at < $1 AND status IN ('resolved', 'expired')",
                    cutoff_date
                )
                deleted = int(result.split()[-1])
                logger.info("old_alerts_deleted", count=deleted, days=days)
                return deleted
        except Exception as e:
            logger.error("delete_old_alerts_failed", error=str(e))
            return 0
            
    async def add_suppression(self, symbol: str, duration_minutes: int) -> bool:
        """Add alert suppression for symbol"""
        try:
            suppressed_until = datetime.now(timezone.utc) + timedelta(minutes=duration_minutes)
            async with self.pool.acquire() as conn:
                await conn.execute(
                    "INSERT INTO alert_suppressions (symbol, suppressed_until) VALUES ($1, $2)",
                    symbol, suppressed_until
                )
                return True
        except Exception as e:
            logger.error("add_suppression_failed", error=str(e), symbol=symbol)
            return False
            
    async def is_suppressed(self, symbol: str) -> bool:
        """Check if alerts for symbol are suppressed"""
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT 1 FROM alert_suppressions WHERE symbol = $1 AND suppressed_until > $2",
                    symbol, datetime.now(timezone.utc)
                )
                return row is not None
        except Exception as e:
            logger.error("check_suppression_failed", error=str(e), symbol=symbol)
            return False
