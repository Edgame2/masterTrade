"""PostgreSQL persistence layer for the Strategy Service."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence

import asyncpg
import structlog

from config import settings
from models import Signal, Strategy, StrategyConfig, StrategyResult
from shared.postgres_manager import PostgresManager, ensure_connection

logger = structlog.get_logger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_uuid(value: str) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


def _json(value: Any) -> Any:
    return value if value is not None else {}


class Database:
    """Async PostgreSQL-backed persistence facade."""

    def __init__(self) -> None:
        self._postgres = PostgresManager(
            settings.POSTGRES_DSN,
            min_size=settings.POSTGRES_POOL_MIN_SIZE,
            max_size=settings.POSTGRES_POOL_MAX_SIZE,
        )
        self._connected = False

    async def connect(self) -> None:
        if self._connected:
            return
        await ensure_connection(self._postgres)
        self._connected = True
        logger.info("Strategy service connected to PostgreSQL")

    async def disconnect(self) -> None:
        if not self._connected:
            return
        await self._postgres.close()
        self._connected = False
        logger.info("Strategy service PostgreSQL connection closed")

    # ------------------------------------------------------------------
    # Generic database operations (proxies to PostgresManager)
    # ------------------------------------------------------------------
    async def execute(self, query: str, *args) -> str:
        """Execute a query and return the status string"""
        return await self._postgres.execute(query, *args)
    
    async def fetch(self, query: str, *args) -> List[asyncpg.Record]:
        """Fetch multiple rows"""
        return await self._postgres.fetch(query, *args)
    
    async def fetchrow(self, query: str, *args) -> Optional[asyncpg.Record]:
        """Fetch a single row"""
        return await self._postgres.fetchrow(query, *args)
    
    async def fetchval(self, query: str, *args) -> Any:
        """Fetch a single value"""
        return await self._postgres.fetchval(query, *args)

    # ------------------------------------------------------------------
    # Strategy helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _normalise_strategy_record(record: asyncpg.Record) -> Dict[str, Any]:
        import json
        data = dict(record)
        data["id"] = str(data["id"])
        
        # Handle JSONB columns - asyncpg returns them as dicts, but dict(record) might serialize them
        for key in ["parameters", "configuration", "metadata"]:
            value = data.get(key)
            if value is None:
                data[key] = {}
            elif isinstance(value, str):
                # If it's a string, parse it
                try:
                    data[key] = json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    data[key] = {}
            elif not isinstance(value, dict):
                # If it's not a dict, make it an empty dict
                data[key] = {}
            # else: it's already a dict, keep it
        
        # Parse symbols - it comes as a JSON string from the aggregation
        symbols = data.get("symbols")
        if isinstance(symbols, str):
            try:
                data["symbols"] = json.loads(symbols)
            except (json.JSONDecodeError, TypeError):
                data["symbols"] = []
        else:
            data["symbols"] = symbols or []
        return data

    async def _fetch_strategies(self, where: str = "", *args: Any) -> List[Dict[str, Any]]:
        clause = f"WHERE {where}" if where else ""
        query = f"""
            SELECT
                s.*,
                COALESCE(
                    json_agg(
                        json_build_object(
                            'symbol', ss.symbol,
                            'weight', ss.weight
                        )
                    ) FILTER (WHERE ss.symbol IS NOT NULL),
                    '[]'::json
                ) AS symbols
            FROM strategies s
            LEFT JOIN strategy_symbols ss ON ss.strategy_id = s.id
            {clause}
            GROUP BY s.id
            ORDER BY s.created_at DESC
        """
        records = await self._postgres.fetch(query, *args)
        return [self._normalise_strategy_record(record) for record in records]

    async def get_active_strategies(self) -> List[Strategy]:
        records = await self._fetch_strategies("s.is_active = true AND s.enabled = true")
        return [
            Strategy(
                id=record["id"],
                name=record["name"],
                type=record["type"],
                parameters=record["parameters"],
                is_active=record["is_active"],
                symbols=record["symbols"],
            )
            for record in records
        ]

    async def get_all_strategies(self) -> List[Dict[str, Any]]:
        return await self._fetch_strategies()

    async def get_strategy(self, strategy_id: str) -> Optional[Dict[str, Any]]:
        strategies = await self._fetch_strategies("s.id = $1", _as_uuid(strategy_id))
        return strategies[0] if strategies else None

    async def create_strategy(self, strategy_config: StrategyConfig) -> bool:
        now = _utcnow()
        async with self._postgres.transaction() as conn:
            record = await conn.fetchrow(
                """
                INSERT INTO strategies (name, type, parameters, configuration, is_active, status, enabled, allocation, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, TRUE, $7, $8, $8)
                RETURNING id
                """,
                strategy_config.name,
                strategy_config.type,
                json.dumps(strategy_config.parameters),
                json.dumps({}),
                strategy_config.is_active,
                "active" if strategy_config.is_active else "inactive",
                1.0,
                now,
            )
            if record is None:
                logger.error("Failed to insert strategy", name=strategy_config.name)
                return False
            strategy_id = record["id"]
            if strategy_config.symbols:
                await conn.executemany(
                    """
                    INSERT INTO strategy_symbols (strategy_id, symbol)
                    VALUES ($1, $2)
                    ON CONFLICT (strategy_id, symbol) DO NOTHING
                    """,
                    [(strategy_id, symbol.upper()) for symbol in strategy_config.symbols],
                )
        logger.info("Strategy created", strategy_id=str(strategy_id), name=strategy_config.name)
        return True

    async def delete_strategy(self, strategy_id: str) -> bool:
        deleted = await self._postgres.fetchval(
            "DELETE FROM strategies WHERE id = $1 RETURNING 1",
            _as_uuid(strategy_id),
        )
        return bool(deleted)

    async def update_strategy(self, strategy_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        allowed_fields = {
            "name": "name",
            "type": "type",
            "parameters": "parameters",
            "configuration": "configuration",
            "metadata": "metadata",
            "is_active": "is_active",
            "status": "status",
            "enabled": "enabled",
            "allocation": "allocation",
        }
        set_clauses: List[str] = []
        values: List[Any] = []
        for key, column in allowed_fields.items():
            if key in updates:
                set_clauses.append(f"{column} = ${len(values) + 2}")
                value = updates[key]
                if column in {"parameters", "configuration", "metadata"}:
                    value = json.dumps(value)
                values.append(value)
        symbols = updates.get("symbols") if "symbols" in updates else None
        if not set_clauses and symbols is None:
            return await self.get_strategy(strategy_id)
        set_clauses.append(f"updated_at = ${len(values) + 2}")
        values.append(_utcnow())
        query = f"""
            UPDATE strategies
            SET {', '.join(set_clauses)}
            WHERE id = $1
            RETURNING *
        """
        async with self._postgres.transaction() as conn:
            record = await conn.fetchrow(query, _as_uuid(strategy_id), *values)
            if record is None:
                return None
            if symbols is not None:
                await conn.execute("DELETE FROM strategy_symbols WHERE strategy_id = $1", _as_uuid(strategy_id))
                if symbols:
                    await conn.executemany(
                        "INSERT INTO strategy_symbols (strategy_id, symbol, metadata) VALUES ($1, $2, $3)",
                        [
                            (
                                _as_uuid(strategy_id),
                                symbol.get("symbol") if isinstance(symbol, dict) else str(symbol),
                                json.dumps(symbol.get("metadata", {})) if isinstance(symbol, dict) else json.dumps({}),
                            )
                            for symbol in symbols
                        ],
                    )
        refreshed = await self.get_strategy(strategy_id)
        return refreshed

    async def toggle_strategy_status(self, strategy_id: str) -> bool:
        record = await self._postgres.fetchrow(
            """
            UPDATE strategies
            SET is_active = NOT is_active,
                status = CASE WHEN is_active THEN 'active' ELSE 'inactive' END,
                updated_at = $2
            WHERE id = $1
            RETURNING is_active
            """,
            _as_uuid(strategy_id),
            _utcnow(),
        )
        if record:
            logger.info("Strategy status toggled", strategy_id=strategy_id, is_active=record["is_active"])
            return True
        logger.warning("Strategy toggle attempted on missing strategy", strategy_id=strategy_id)
        return False

    async def update_strategy_status(self, strategy_id: str, status: str) -> bool:
        record = await self._postgres.fetchrow(
            """
            UPDATE strategies
            SET status = $2,
                is_active = CASE WHEN $2 = 'active' THEN TRUE ELSE is_active END,
                updated_at = $3
            WHERE id = $1
            RETURNING 1
            """,
            _as_uuid(strategy_id),
            status,
            _utcnow(),
        )
        return bool(record)

    async def update_strategy_parameters(self, strategy_id: str, parameters: Dict[str, Any]) -> bool:
        record = await self._postgres.fetchrow(
            """
            UPDATE strategies
            SET configuration = configuration || $2::jsonb,
                updated_at = $3
            WHERE id = $1
            RETURNING 1
            """,
            _as_uuid(strategy_id),
            json.dumps(parameters),
            _utcnow(),
        )
        return bool(record)

    async def update_strategy_allocation(self, strategy_id: str, allocation_change: float) -> bool:
        record = await self._postgres.fetchrow(
            """
            UPDATE strategies
            SET allocation = GREATEST(0, allocation * (1 + $2)),
                updated_at = $3
            WHERE id = $1
            RETURNING 1
            """,
            _as_uuid(strategy_id),
            allocation_change,
            _utcnow(),
        )
        return bool(record)

    async def activate_replacement_strategy(self, old_strategy_id: str, new_strategy_id: str) -> bool:
        now = _utcnow()
        async with self._postgres.transaction() as conn:
            old_record = await conn.fetchrow(
                """
                UPDATE strategies
                SET status = 'replaced',
                    is_active = FALSE,
                    replaced_by = $2,
                    replaced_at = $3,
                    updated_at = $3
                WHERE id = $1
                RETURNING 1
                """,
                _as_uuid(old_strategy_id),
                _as_uuid(new_strategy_id),
                now,
            )
            new_record = await conn.fetchrow(
                """
                UPDATE strategies
                SET status = 'active',
                    is_active = TRUE,
                    replaces = $2,
                    activated_at = $3,
                    updated_at = $3
                WHERE id = $1
                RETURNING 1
                """,
                _as_uuid(new_strategy_id),
                _as_uuid(old_strategy_id),
                now,
            )
        return bool(old_record and new_record)

    async def get_similar_strategies(
        self,
        strategy_type: str,
        symbols: Sequence[str],
        timeframes: Sequence[str],
    ) -> List[Dict[str, Any]]:
        del timeframes  # Not tracked in schema yet
        if not symbols:
            return []
        query = """
            SELECT DISTINCT s.*
            FROM strategies s
            JOIN strategy_symbols ss ON ss.strategy_id = s.id
            WHERE s.type = $1
              AND s.status = 'active'
              AND ss.symbol = ANY($2::text[])
        """
        records = await self._postgres.fetch(query, strategy_type, symbols)
        return [self._normalise_strategy_record(record) for record in records]

    async def get_current_active_strategies_count(self) -> int:
        count = await self._postgres.fetchval(
            "SELECT COUNT(1) FROM strategies WHERE status = 'active' AND enabled = TRUE",
        )
        return int(count or 0)

    # ------------------------------------------------------------------
    # Signal operations
    # ------------------------------------------------------------------
    async def insert_signal(self, signal: Signal) -> bool:
        record = await self._postgres.fetchrow(
            """
            INSERT INTO signals (
                strategy_id, symbol, signal_type, confidence, price, quantity,
                metadata, timestamp, created_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            RETURNING 1
            """,
            _as_uuid(signal.strategy_id),
            signal.symbol,
            signal.signal_type,
            signal.confidence,
            signal.price,
            signal.quantity,
            json.dumps(signal.metadata),
            signal.timestamp,
            _utcnow(),
        )
        if record:
            logger.info("Signal stored", strategy_id=signal.strategy_id, symbol=signal.symbol)
            return True
        logger.error("Failed to store signal", strategy_id=signal.strategy_id)
        return False

    async def get_recent_signals(self, limit: int = 100) -> List[Dict[str, Any]]:
        records = await self._postgres.fetch(
            """
            SELECT *
            FROM signals
            ORDER BY timestamp DESC
            LIMIT $1
            """,
            limit,
        )
        return [self._normalise_signal(record) for record in records]

    async def get_signals_by_strategy(self, strategy_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        records = await self._postgres.fetch(
            """
            SELECT *
            FROM signals
            WHERE strategy_id = $1
            ORDER BY timestamp DESC
            LIMIT $2
            """,
            _as_uuid(strategy_id),
            limit,
        )
        return [self._normalise_signal(record) for record in records]

    @staticmethod
    def _normalise_signal(record: asyncpg.Record) -> Dict[str, Any]:
        data = dict(record)
        data["id"] = str(data["id"])
        data["strategy_id"] = str(data["strategy_id"])
        data["metadata"] = _json(data.get("metadata"))
        if isinstance(data.get("timestamp"), datetime):
            data["timestamp"] = data["timestamp"].isoformat()
        if isinstance(data.get("created_at"), datetime):
            data["created_at"] = data["created_at"].isoformat()
        return data

    # ------------------------------------------------------------------
    # Performance and analytics
    # ------------------------------------------------------------------
    async def insert_strategy_performance(self, result: StrategyResult) -> bool:
        record = await self._postgres.fetchrow(
            """
            INSERT INTO strategy_performance (
                strategy_id, symbol, signals_count, execution_time, error,
                signals_summary, timestamp
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING 1
            """,
            _as_uuid(result.strategy_id),
            result.symbol,
            len(result.signals),
            result.execution_time,
            result.error,
            json.dumps(
                [
                    {
                        "type": signal.signal_type,
                        "confidence": signal.confidence,
                        "price": signal.price,
                    }
                    for signal in result.signals
                ]
            ),
            _utcnow(),
        )
        return bool(record)

    async def get_strategy_performance_summary(self, strategy_id: str, hours_back: int = 24) -> Dict[str, Any]:
        since_time = _utcnow() - timedelta(hours=hours_back)
        record = await self._postgres.fetchrow(
            """
            SELECT
                COUNT(*) AS execution_count,
                AVG(execution_time) AS avg_execution_time,
                SUM(signals_count) AS total_signals
            FROM strategy_performance
            WHERE strategy_id = $1
              AND timestamp >= $2
            """,
            _as_uuid(strategy_id),
            since_time,
        )
        return dict(record) if record else {}

    # ------------------------------------------------------------------
    # Backtesting and learning
    # ------------------------------------------------------------------
    async def store_backtest_result(self, strategy_id: str, result: Dict[str, Any]) -> None:
        await self._postgres.execute(
            """
            INSERT INTO backtest_results (
                strategy_id, backtest_id, metrics, parameters,
                period_start, period_end, created_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            """,
            _as_uuid(strategy_id),
            result.get("backtest_id"),
            json.dumps(result.get("metrics", {})),
            json.dumps(result.get("parameters", {})),
            result.get("period_start"),
            result.get("period_end"),
            _utcnow(),
        )

    async def get_backtest_results(self, limit: int = 100) -> List[Dict[str, Any]]:
        records = await self._postgres.fetch(
            """
            SELECT *
            FROM backtest_results
            ORDER BY created_at DESC
            LIMIT $1
            """,
            limit,
        )
        return [self._normalise_backtest(record) for record in records]

    async def get_strategy_backtest_results(self, strategy_id: str) -> Optional[Dict[str, Any]]:
        record = await self._postgres.fetchrow(
            """
            SELECT *
            FROM backtest_results
            WHERE strategy_id = $1
            ORDER BY created_at DESC
            LIMIT 1
            """,
            _as_uuid(strategy_id),
        )
        return self._normalise_backtest(record) if record else None

    @staticmethod
    def _normalise_backtest(record: asyncpg.Record) -> Dict[str, Any]:
        data = dict(record)
        data["id"] = str(data["id"])
        data["strategy_id"] = str(data["strategy_id"])
        data["metrics"] = _json(data.get("metrics"))
        data["parameters"] = _json(data.get("parameters"))
        if isinstance(data.get("created_at"), datetime):
            data["created_at"] = data["created_at"].isoformat()
        return data

    async def store_learning_insights(self, payload: Dict[str, Any]) -> None:
        await self._postgres.execute(
            """
            INSERT INTO learning_insights (timestamp, insights, generation_stats)
            VALUES ($1, $2, $3)
            """,
            payload.get("timestamp", _utcnow()),
            json.dumps(payload.get("insights", {})),
            json.dumps(payload.get("generation_stats", {})),
        )

    # ------------------------------------------------------------------
    # Reviews and notifications
    # ------------------------------------------------------------------
    async def store_strategy_review(self, review_data: Dict[str, Any]) -> bool:
        record = await self._postgres.fetchrow(
            """
            INSERT INTO strategy_reviews (
                strategy_id, reviewer, performance_grade, decision, confidence_score,
                scores, summary, recommendations, review_payload, review_date, created_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            RETURNING 1
            """,
            _as_uuid(review_data["strategy_id"]),
            review_data.get("reviewer"),
            review_data.get("performance_grade"),
            review_data.get("decision"),
            review_data.get("confidence_score"),
            json.dumps(review_data.get("scores", {})),
            review_data.get("summary"),
            review_data.get("recommendations"),
            json.dumps(review_data),
            review_data.get("review_timestamp", _utcnow()),
            _utcnow(),
        )
        return bool(record)

    async def get_strategy_review_history(self, strategy_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        records = await self._postgres.fetch(
            """
            SELECT *
            FROM strategy_reviews
            WHERE strategy_id = $1
            ORDER BY review_date DESC
            LIMIT $2
            """,
            _as_uuid(strategy_id),
            limit,
        )
        return [self._normalise_review(record) for record in records]

    async def get_recent_strategy_reviews(self, limit: int = 20) -> List[Dict[str, Any]]:
        records = await self._postgres.fetch(
            """
            SELECT *
            FROM strategy_reviews
            ORDER BY review_date DESC
            LIMIT $1
            """,
            limit,
        )
        return [self._normalise_review(record) for record in records]

    @staticmethod
    def _normalise_review(record: asyncpg.Record) -> Dict[str, Any]:
        data = dict(record)
        data["id"] = str(data["id"])
        data["strategy_id"] = str(data["strategy_id"])
        data["scores"] = _json(data.get("scores"))
        data["review_payload"] = _json(data.get("review_payload"))
        if isinstance(data.get("review_date"), datetime):
            data["review_date"] = data["review_date"].isoformat()
        if isinstance(data.get("created_at"), datetime):
            data["created_at"] = data["created_at"].isoformat()
        return data

    async def store_daily_review_summary(self, summary: Dict[str, Any]) -> bool:
        record = await self._postgres.fetchrow(
            """
            INSERT INTO daily_review_summaries (
                review_date, grade_distribution, decision_distribution,
                total_strategies_reviewed, avg_confidence, top_performers,
                strategies_needing_attention, market_regime, created_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ON CONFLICT (review_date) DO UPDATE SET
                grade_distribution = EXCLUDED.grade_distribution,
                decision_distribution = EXCLUDED.decision_distribution,
                total_strategies_reviewed = EXCLUDED.total_strategies_reviewed,
                avg_confidence = EXCLUDED.avg_confidence,
                top_performers = EXCLUDED.top_performers,
                strategies_needing_attention = EXCLUDED.strategies_needing_attention,
                market_regime = EXCLUDED.market_regime,
                created_at = EXCLUDED.created_at
            RETURNING 1
            """,
            summary.get("review_date"),
            json.dumps(summary.get("grade_distribution", {})),
            json.dumps(summary.get("decision_distribution", {})),
            summary.get("total_strategies_reviewed", 0),
            summary.get("avg_confidence"),
            json.dumps(summary.get("top_performers", [])),
            json.dumps(summary.get("strategies_needing_attention", [])),
            json.dumps(summary.get("market_regime", {})),
            _utcnow(),
        )
        return bool(record)

    async def get_daily_review_summary(self, date: str) -> Optional[Dict[str, Any]]:
        record = await self._postgres.fetchrow(
            "SELECT * FROM daily_review_summaries WHERE review_date = $1",
            date,
        )
        if not record:
            return None
        data = dict(record)
        data["grade_distribution"] = _json(data.get("grade_distribution"))
        data["decision_distribution"] = _json(data.get("decision_distribution"))
        data["top_performers"] = data.get("top_performers") or []
        data["strategies_needing_attention"] = data.get("strategies_needing_attention") or []
        data["market_regime"] = _json(data.get("market_regime"))
        return data

    async def store_notification(self, notification: Dict[str, Any]) -> bool:
        record = await self._postgres.fetchrow(
            """
            INSERT INTO notifications (notification_type, payload, created_at)
            VALUES ($1, $2, $3)
            RETURNING 1
            """,
            notification.get("type"),
            json.dumps(notification),
            notification.get("timestamp", _utcnow()),
        )
        return bool(record)

    # ------------------------------------------------------------------
    # Trading history helpers
    # ------------------------------------------------------------------
    async def get_strategy_trades(
        self,
        strategy_id: str,
        start_date: datetime,
        end_date: datetime,
    ) -> List[Dict[str, Any]]:
        records = await self._postgres.fetch(
            """
            SELECT *
            FROM strategy_trades
            WHERE strategy_id = $1
              AND executed_at BETWEEN $2 AND $3
            ORDER BY executed_at DESC
            """,
            _as_uuid(strategy_id),
            start_date,
            end_date,
        )
        items: List[Dict[str, Any]] = []
        for record in records:
            data = dict(record)
            data["id"] = str(data["id"])
            data["strategy_id"] = str(data["strategy_id"])
            data["metadata"] = _json(data.get("metadata"))
            if isinstance(data.get("executed_at"), datetime):
                data["timestamp"] = data["executed_at"].isoformat()
            items.append(data)
        return items

    # ------------------------------------------------------------------
    # Crypto selection
    # ------------------------------------------------------------------
    async def store_crypto_selection(self, selection: Dict[str, Any]) -> bool:
        record = await self._postgres.fetchrow(
            """
            INSERT INTO crypto_selections (
                selection_date, selection_timestamp, selected_cryptos,
                total_selected
            )
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (selection_date) DO UPDATE SET
                selection_timestamp = EXCLUDED.selection_timestamp,
                selected_cryptos = EXCLUDED.selected_cryptos,
                total_selected = EXCLUDED.total_selected
            RETURNING 1
            """,
            selection.get("selection_date"),
            selection.get("selection_timestamp", _utcnow()),
            json.dumps(selection.get("selected_cryptos", [])),
            selection.get("total_selected", 0),
        )
        return bool(record)

    async def get_current_crypto_selection(self) -> Optional[Dict[str, Any]]:
        today = _utcnow().date()
        record = await self._postgres.fetchrow(
            """
            SELECT *
            FROM crypto_selections
            WHERE selection_date = $1
            ORDER BY selection_timestamp DESC
            LIMIT 1
            """,
            today,
        )
        return self._normalise_crypto_selection(record) if record else None

    async def get_crypto_selection_history(self, days_back: int) -> List[Dict[str, Any]]:
        start_date = (_utcnow() - timedelta(days=days_back)).date()
        records = await self._postgres.fetch(
            """
            SELECT *
            FROM crypto_selections
            WHERE selection_date >= $1
            ORDER BY selection_timestamp DESC
            """,
            start_date,
        )
        return [self._normalise_crypto_selection(record) for record in records]

    @staticmethod
    def _normalise_crypto_selection(record: asyncpg.Record) -> Dict[str, Any]:
        data = dict(record)
        data["id"] = str(data["id"])
        data["selected_cryptos"] = data.get("selected_cryptos") or []
        if isinstance(data.get("selection_timestamp"), datetime):
            data["selection_timestamp"] = data["selection_timestamp"].isoformat()
        return data

    # ------------------------------------------------------------------
    # Activation log and settings
    # ------------------------------------------------------------------
    async def log_activation_changes(
        self,
        activated: Sequence[str],
        deactivated: Sequence[str],
        max_active: int,
        reason: Optional[str] = None,
    ) -> None:
        await self._postgres.execute(
            """
            INSERT INTO strategy_activation_log (
                timestamp, activated_strategies, deactivated_strategies,
                max_active_strategies, activation_reason
            )
            VALUES ($1, $2, $3, $4, $5)
            """,
            _utcnow(),
            json.dumps(list(activated)),
            json.dumps(list(deactivated)),
            max_active,
            reason,
        )

    async def get_activation_log(self, limit: int = 100) -> List[Dict[str, Any]]:
        records = await self._postgres.fetch(
            "SELECT * FROM strategy_activation_log ORDER BY timestamp DESC LIMIT $1",
            limit,
        )
        items: List[Dict[str, Any]] = []
        for record in records:
            data = dict(record)
            data["id"] = str(data["id"])
            data["activated_strategies"] = data.get("activated_strategies") or []
            data["deactivated_strategies"] = data.get("deactivated_strategies") or []
            if isinstance(data.get("timestamp"), datetime):
                data["timestamp"] = data["timestamp"].isoformat()
            items.append(data)
        return items

    async def upsert_setting(
        self,
        key: str,
        value: str,
        *,
        description: Optional[str] = None,
        value_type: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        await self._postgres.execute(
            """
            INSERT INTO settings (key, value, type, description, metadata, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (key) DO UPDATE SET
                value = EXCLUDED.value,
                type = EXCLUDED.type,
                description = EXCLUDED.description,
                metadata = EXCLUDED.metadata,
                updated_at = EXCLUDED.updated_at
            """,
            key,
            value,
            value_type,
            description,
            json.dumps(metadata or {}),
            _utcnow(),
        )

    async def get_setting(self, key: str) -> Optional[Dict[str, Any]]:
        record = await self._postgres.fetchrow("SELECT * FROM settings WHERE key = $1", key)
        if not record:
            return None
        data = dict(record)
        data["metadata"] = _json(data.get("metadata"))
        return data

    # ------------------------------------------------------------------
    # Dashboard utilities
    # ------------------------------------------------------------------
    async def get_dashboard_overview(self) -> Dict[str, Any]:
        active_count = await self._postgres.fetchval(
            "SELECT COUNT(1) FROM strategies WHERE is_active = TRUE",
        )
        recent_signals = await self._postgres.fetchval(
            "SELECT COUNT(1) FROM signals WHERE timestamp >= $1",
            _utcnow() - timedelta(hours=24),
        )
        return {
            "active_strategies_count": int(active_count or 0),
            "recent_signals_count": int(recent_signals or 0),
            "last_updated": _utcnow().isoformat(),
        }

    # ------------------------------------------------------------------
    # Sentiment data operations
    # ------------------------------------------------------------------
    async def get_sentiment_entries(
        self,
        *,
        symbol: Optional[str] = None,
        sentiment_types: Optional[Sequence[str]] = None,
        hours_back: int = 24,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        cutoff = _utcnow() - timedelta(hours=hours_back)
        conditions = ["(data->>'timestamp')::timestamptz >= $1"]
        params: List[Any] = [cutoff]
        param_index = 2

        if symbol:
            conditions.append(f"COALESCE(data->>'symbol', '') = ${param_index}")
            params.append(symbol.upper())
            param_index += 1

        if sentiment_types:
            conditions.append(f"(data->>'type') = ANY(${param_index}::text[])")
            params.append(list(sentiment_types))
            param_index += 1

        params.append(limit)
        query = f"""
            SELECT data
            FROM sentiment_data
            WHERE {' AND '.join(conditions)}
            ORDER BY (data->>'timestamp')::timestamptz DESC
            LIMIT ${param_index}
        """

        try:
            records = await self._postgres.fetch(query, *params)
        except asyncpg.exceptions.UndefinedTableError:
            logger.warning("Sentiment data table not available", table="sentiment_data")
            return []
        except Exception as error:
            logger.error("Failed to fetch sentiment entries", error=str(error))
            return []

        entries: List[Dict[str, Any]] = []
        for record in records:
            data = record.get("data") if hasattr(record, "get") else record["data"]
            if isinstance(data, dict):
                entries.append(dict(data))
            else:
                entries.append(data)
        return entries

    # ------------------------------------------------------------------
    # Placeholder methods for future integration
    # ------------------------------------------------------------------
    async def get_historical_data(self, symbol: str, interval: str, limit: int) -> List[Dict[str, Any]]:
        logger.warning(
            "Historical data retrieval not yet wired to market data database",
            symbol=symbol,
            interval=interval,
        )
        return []

    async def get_market_data_for_analysis(self, symbol: str, interval: str = "1h", hours_back: int = 168) -> List[Dict[str, Any]]:
        logger.warning("Market data analysis fallback in use", symbol=symbol, interval=interval)
        end_time = _utcnow()
        start_time = end_time - timedelta(hours=hours_back)
        points: List[Dict[str, Any]] = []
        current = start_time
        price = 45000.0
        while current <= end_time:
            price *= 1 + (((hash((symbol, current.isoformat())) % 200) - 100) / 10000)
            points.append(
                {
                    "symbol": symbol,
                    "timestamp": current,
                    "close_price": price,
                    "volume": 1_000_000,
                    "quote_volume": price * 1_000_000,
                    "interval": interval,
                }
            )
            current += timedelta(hours=1)
        return points

    async def get_all_symbols(self, include_inactive: bool = False) -> List[Dict[str, Any]]:
        del include_inactive
        return [
            {
                "symbol": "BTCUSDC",
                "base_asset": "BTC",
                "quote_asset": "USDC",
                "tracking": True,
                "priority": 1,
            },
            {
                "symbol": "ETHUSDC",
                "base_asset": "ETH",
                "quote_asset": "USDC",
                "tracking": True,
                "priority": 1,
            },
        ]

    async def update_symbol_tracking(self, symbol: str, updates: Dict[str, Any]) -> bool:
        logger.info("Symbol tracking update placeholder", symbol=symbol, updates=updates)
        return True

    async def query_market_data(self, query: str, limit: int = 100) -> List[Dict[str, Any]]:
        del query, limit
        logger.warning("Market data query placeholder invoked")
        return []
