"""PostgreSQL persistence layer for the Arbitrage Service."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

import asyncpg
import structlog

from config import settings

logger = structlog.get_logger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_uuid(value: Any) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


def _row_to_dict(record: asyncpg.Record) -> Dict[str, Any]:
    data = dict(record)
    for key, value in data.items():
        if isinstance(value, uuid.UUID):
            data[key] = str(value)
        elif isinstance(value, Decimal):
            data[key] = float(value)
    return data


def _to_serializable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


class ArbitragePostgresDatabase:
    """Async PostgreSQL adapter for the Arbitrage service."""

    def __init__(self):
        self._pool: Optional[asyncpg.Pool] = None
        self._connected = False

    async def connect(self) -> None:
        """Establish PostgreSQL connection pool"""
        if self._connected:
            return

        try:
            dsn = (
                f"postgresql://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}"
                f"@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
            )

            self._pool = await asyncpg.create_pool(
                dsn=dsn,
                min_size=1,
                max_size=10,
                command_timeout=60,
            )
            self._connected = True
            logger.info("Arbitrage service connected to PostgreSQL")
        except Exception as e:
            logger.error(f"Failed to connect to PostgreSQL: {e}")
            raise

    async def disconnect(self) -> None:
        """Close PostgreSQL connection pool"""
        if not self._connected or not self._pool:
            return

        await self._pool.close()
        self._connected = False
        logger.info("Arbitrage service PostgreSQL connection closed")

    async def insert_arbitrage_opportunity(self, opportunity: Any) -> bool:
        """Store a new arbitrage opportunity"""
        query = """
            INSERT INTO arbitrage_opportunities (
                id, pair, buy_venue, sell_venue, buy_price, sell_price,
                profit_percent, estimated_profit_usd, trade_amount, gas_cost,
                arbitrage_type, executed, execution_id, metadata, timestamp
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14::jsonb, $15)
        """
        try:
            opportunity_id = _ensure_uuid(opportunity.id if hasattr(opportunity, 'id') else uuid.uuid4())
            metadata = opportunity.metadata if hasattr(opportunity, 'metadata') else {}

            async with self._pool.acquire() as conn:
                await conn.execute(
                    query,
                    opportunity_id,
                    opportunity.pair,
                    opportunity.buy_venue,
                    opportunity.sell_venue,
                    opportunity.buy_price,
                    opportunity.sell_price,
                    opportunity.profit_percent,
                    opportunity.estimated_profit_usd,
                    opportunity.trade_amount,
                    getattr(opportunity, 'gas_cost', 0.0),
                    opportunity.arbitrage_type,
                    False,
                    None,
                    json.dumps(metadata, default=_to_serializable),
                    opportunity.timestamp if hasattr(opportunity, 'timestamp') else _utcnow(),
                )
            return True
        except Exception as e:
            logger.error(f"Failed to insert arbitrage opportunity: {e}")
            return False

    async def get_profitable_opportunities(self, min_profit_percent: float = 0.1) -> List[Dict[str, Any]]:
        """Get profitable opportunities above minimum threshold"""
        query = """
            SELECT * FROM arbitrage_opportunities
            WHERE executed = false AND profit_percent >= $1
            ORDER BY profit_percent DESC, timestamp DESC
            LIMIT 100
        """
        try:
            async with self._pool.acquire() as conn:
                records = await conn.fetch(query, min_profit_percent)
                return [_row_to_dict(record) for record in records]
        except Exception as e:
            logger.error(f"Failed to get profitable opportunities: {e}")
            return []

    async def get_opportunities_by_type(self, arbitrage_type: str) -> List[Dict[str, Any]]:
        """Get opportunities by type"""
        query = """
            SELECT * FROM arbitrage_opportunities
            WHERE arbitrage_type = $1 AND executed = false
            ORDER BY timestamp DESC
            LIMIT 100
        """
        try:
            async with self._pool.acquire() as conn:
                records = await conn.fetch(query, arbitrage_type)
                return [_row_to_dict(record) for record in records]
        except Exception as e:
            logger.error(f"Failed to get opportunities by type: {e}")
            return []

    async def create_arbitrage_execution(self, opportunity: Any) -> str:
        """Create an execution record for an opportunity"""
        query = """
            INSERT INTO arbitrage_executions (
                id, opportunity_id, execution_type, start_time, status,
                transactions, actual_profit_usd, gas_used, error_message
            )
            VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8, $9)
            RETURNING id
        """
        try:
            execution_id = uuid.uuid4()
            opportunity_id = _ensure_uuid(opportunity.id if hasattr(opportunity, 'id') else opportunity['id'])

            async with self._pool.acquire() as conn:
                record = await conn.fetchrow(
                    query,
                    execution_id,
                    opportunity_id,
                    opportunity.arbitrage_type if hasattr(opportunity, 'arbitrage_type') else 'simple',
                    _utcnow(),
                    'pending',
                    json.dumps([]),
                    None,
                    None,
                    None,
                )
                return str(record['id'])
        except Exception as e:
            logger.error(f"Failed to create execution: {e}")
            raise

    async def update_arbitrage_execution(self, execution_id: str, result: Dict[str, Any]) -> bool:
        """Update execution with results"""
        query = """
            UPDATE arbitrage_executions
            SET end_time = $2,
                status = $3,
                transactions = $4::jsonb,
                actual_profit_usd = $5,
                gas_used = $6,
                error_message = $7
            WHERE id = $1
        """
        try:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    query,
                    _ensure_uuid(execution_id),
                    _utcnow(),
                    result.get('status', 'completed'),
                    json.dumps(result.get('transactions', []), default=_to_serializable),
                    result.get('actual_profit_usd'),
                    result.get('gas_used'),
                    result.get('error_message'),
                )
            return True
        except Exception as e:
            logger.error(f"Failed to update execution: {e}")
            return False

    async def get_execution_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get execution history"""
        query = """
            SELECT * FROM arbitrage_executions
            ORDER BY start_time DESC
            LIMIT $1
        """
        try:
            async with self._pool.acquire() as conn:
                records = await conn.fetch(query, limit)
                return [_row_to_dict(record) for record in records]
        except Exception as e:
            logger.error(f"Failed to get execution history: {e}")
            return []

    async def insert_dex_price(self, price: Any) -> bool:
        """Store DEX price data"""
        query = """
            INSERT INTO dex_prices (
                id, pair, dex, chain, price, volume, liquidity, metadata, timestamp
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9)
        """
        try:
            price_id = uuid.uuid4()
            metadata = price.metadata if hasattr(price, 'metadata') else {}

            async with self._pool.acquire() as conn:
                await conn.execute(
                    query,
                    price_id,
                    price.pair,
                    price.dex,
                    price.chain,
                    price.price,
                    getattr(price, 'volume', None),
                    getattr(price, 'liquidity', None),
                    json.dumps(metadata, default=_to_serializable),
                    price.timestamp if hasattr(price, 'timestamp') else _utcnow(),
                )
            return True
        except Exception as e:
            logger.error(f"Failed to insert DEX price: {e}")
            return False

    async def get_latest_dex_prices(self, pair: str) -> List[Dict[str, Any]]:
        """Get latest prices for a pair across DEXs"""
        query = """
            SELECT DISTINCT ON (dex) *
            FROM dex_prices
            WHERE pair = $1
            ORDER BY dex, timestamp DESC
        """
        try:
            async with self._pool.acquire() as conn:
                records = await conn.fetch(query, pair)
                return [_row_to_dict(record) for record in records]
        except Exception as e:
            logger.error(f"Failed to get latest DEX prices: {e}")
            return []

    async def insert_flash_loan_opportunity(self, opportunity: Any) -> bool:
        """Store flash loan opportunity"""
        query = """
            INSERT INTO flash_loan_opportunities (
                id, protocol, token, estimated_profit, capital_required, metadata, timestamp
            )
            VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7)
        """
        try:
            opp_id = uuid.uuid4()
            metadata = opportunity.metadata if hasattr(opportunity, 'metadata') else {}

            async with self._pool.acquire() as conn:
                await conn.execute(
                    query,
                    opp_id,
                    opportunity.protocol,
                    opportunity.token,
                    opportunity.estimated_profit,
                    opportunity.capital_required,
                    json.dumps(metadata, default=_to_serializable),
                    opportunity.timestamp if hasattr(opportunity, 'timestamp') else _utcnow(),
                )
            return True
        except Exception as e:
            logger.error(f"Failed to insert flash loan opportunity: {e}")
            return False

    async def insert_gas_price(self, gas_price: Any) -> bool:
        """Store gas price data"""
        query = """
            INSERT INTO gas_prices (
                id, chain, standard_gwei, fast_gwei, safe_gwei, metadata, timestamp
            )
            VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7)
        """
        try:
            gas_id = uuid.uuid4()
            metadata = gas_price.metadata if hasattr(gas_price, 'metadata') else {}

            async with self._pool.acquire() as conn:
                await conn.execute(
                    query,
                    gas_id,
                    gas_price.chain,
                    gas_price.standard_gwei,
                    getattr(gas_price, 'fast_gwei', None),
                    getattr(gas_price, 'safe_gwei', None),
                    json.dumps(metadata, default=_to_serializable),
                    gas_price.timestamp if hasattr(gas_price, 'timestamp') else _utcnow(),
                )
            return True
        except Exception as e:
            logger.error(f"Failed to insert gas price: {e}")
            return False

    async def get_latest_gas_price(self, chain: str) -> Optional[Dict[str, Any]]:
        """Get latest gas price for a chain"""
        query = """
            SELECT * FROM gas_prices
            WHERE chain = $1
            ORDER BY timestamp DESC
            LIMIT 1
        """
        try:
            async with self._pool.acquire() as conn:
                record = await conn.fetchrow(query, chain)
                return _row_to_dict(record) if record else None
        except Exception as e:
            logger.error(f"Failed to get latest gas price: {e}")
            return None

    async def get_arbitrage_stats(self, hours_back: int = 24) -> Dict[str, Any]:
        """Get arbitrage statistics"""
        query = """
            SELECT
                COUNT(*) as total_opportunities,
                COUNT(*) FILTER (WHERE executed = true) as executed_count,
                AVG(profit_percent) as avg_profit_percent,
                MAX(profit_percent) as max_profit_percent,
                SUM(estimated_profit_usd) as total_estimated_profit
            FROM arbitrage_opportunities
            WHERE timestamp >= NOW() - INTERVAL '%s hours'
        """ % hours_back

        try:
            async with self._pool.acquire() as conn:
                record = await conn.fetchrow(query)
                return _row_to_dict(record) if record else {}
        except Exception as e:
            logger.error(f"Failed to get arbitrage stats: {e}")
            return {}


# Global instance
postgres_database = ArbitragePostgresDatabase()
