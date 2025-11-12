"""PostgreSQL persistence layer for the Risk Management service."""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, TYPE_CHECKING

import asyncpg
import structlog

from config import settings
from shared.postgres_manager import PostgresManager, ensure_connection

if TYPE_CHECKING:  # pragma: no cover - used only for typing hints
    from stop_loss_manager import StopLossOrder, StopLossConfig, StopLossStatus, StopLossType
    from portfolio_risk_controller import AlertType, RiskAlert, RiskLevel

logger = structlog.get_logger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_uuid(value: Any) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


def _ensure_text_identifier(identifier: Optional[str]) -> str:
    return identifier or str(uuid.uuid4())


def _row_to_dict(record: asyncpg.Record) -> Dict[str, Any]:
    data = dict(record)
    for key, value in data.items():
        if isinstance(value, uuid.UUID):
            data[key] = str(value)
    return data

def _to_serializable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if hasattr(value, 'value'):  # Handle Enum objects
        return value.value
    if isinstance(value, dict):
        return {k: _to_serializable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_serializable(item) for item in value]
    return value


def _normalise_json_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {key: _to_serializable(value) for key, value in payload.items()}


class AttrDict(dict):
    """Dictionary wrapper with attribute-style access for historical data."""

    def __getattr__(self, item: str) -> Any:
        try:
            return self[item]
        except KeyError as exc:  # pragma: no cover - defensive path
            raise AttributeError(item) from exc

    def __setattr__(self, key: str, value: Any) -> None:  # pragma: no cover - rarely used
        self[key] = value


def _parse_datetime(value: Any) -> Any:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return value
    return value


def _get_attr(source: Any, attribute: str, default: Any = None) -> Any:
    if isinstance(source, dict):
        return source.get(attribute, default)
    return getattr(source, attribute, default)


def _coerce_risk_level(value: Any) -> Any:
    try:
        from portfolio_risk_controller import RiskLevel

        if isinstance(value, RiskLevel):
            return value
        if value is None:
            return None
        return RiskLevel(value)
    except Exception:  # pragma: no cover - best-effort conversion
        return value


def _serialise_stop_loss_config(config: Any) -> str:
    if config is None:
        return json.dumps({})
    if isinstance(config, dict):
        payload = dict(config)
    else:
        payload = {key: getattr(config, key) for key in getattr(config, "__dataclass_fields__", {})}
    stop_type_value = payload.get("stop_type")
    if hasattr(stop_type_value, "value"):
        payload["stop_type"] = stop_type_value.value
    return json.dumps({key: _to_serializable(value) for key, value in payload.items()})


def _deserialise_stop_loss_record(record: asyncpg.Record) -> "StopLossOrder":
    from stop_loss_manager import StopLossConfig, StopLossOrder, StopLossStatus, StopLossType

    data = _row_to_dict(record)
    metadata = data.get("metadata") or {}
    if isinstance(metadata, str):
        metadata = json.loads(metadata)
    config_payload = data.get("config") or {}

    stop_type = StopLossType(data["stop_type"])
    config_stop_type = config_payload.get("stop_type")
    try:
        config_stop_type = StopLossType(config_stop_type) if config_stop_type else stop_type
    except ValueError:
        config_stop_type = stop_type

    config = StopLossConfig(
        stop_type=config_stop_type,
        initial_stop_percent=config_payload.get("initial_stop_percent", 0.0),
        trailing_distance_percent=config_payload.get("trailing_distance_percent"),
        max_loss_percent=config_payload.get("max_loss_percent"),
        min_profit_before_trail=config_payload.get("min_profit_before_trail"),
        volatility_multiplier=config_payload.get("volatility_multiplier"),
        support_resistance_buffer=config_payload.get("support_resistance_buffer"),
        time_decay_enabled=config_payload.get("time_decay_enabled", False),
        breakeven_protection=config_payload.get("breakeven_protection", True),
    )

    created_at = _parse_datetime(data.get("created_at")) or _utcnow()
    updated_at = _parse_datetime(data.get("updated_at")) or created_at

    highest_price = metadata.get("highest_price", data.get("entry_price", 0.0)) or 0.0
    lowest_price = metadata.get("lowest_price", data.get("entry_price", 0.0)) or 0.0

    return StopLossOrder(
        id=data["id"],
        position_id=data["position_id"],
        symbol=data["symbol"],
        stop_type=stop_type,
        status=StopLossStatus(data["status"]),
        entry_price=float(data.get("entry_price", 0.0) or 0.0),
        current_price=float(data.get("current_price", 0.0) or 0.0),
        stop_price=float(data.get("stop_price", 0.0) or 0.0),
        initial_stop_price=float(data.get("initial_stop_price", 0.0) or 0.0),
        quantity=float(data.get("quantity", 0.0) or 0.0),
        created_at=created_at,
        last_updated=updated_at,
        config=config,
        profit_loss=float(data.get("profit_loss", 0.0) or 0.0),
        highest_price=float(highest_price),
        lowest_price=float(lowest_price),
        trigger_count=int(data.get("trigger_count", 0) or 0),
        metadata=metadata,
    )


def _deserialise_risk_alert_record(record: asyncpg.Record) -> "RiskAlert":
    from portfolio_risk_controller import AlertType, RiskAlert, RiskLevel

    data = _row_to_dict(record)
    metadata = data.get("metadata") or {}

    created_at = _parse_datetime(data.get("timestamp")) or _utcnow()
    resolved_at = _parse_datetime(data.get("updated_at")) if data.get("status") == "resolved" else None

    alert_type = AlertType(data["alert_type"])
    severity = RiskLevel(data["severity"])

    recommendation = data.get("recommendation") or metadata.get("recommendation") or ""

    return RiskAlert(
        id=data["id"],
        alert_type=alert_type,
        severity=severity,
        title=data.get("title", ""),
        message=data.get("message", ""),
        symbol=data.get("symbol"),
        current_value=float(data.get("current_value", 0.0) or 0.0),
        threshold_value=float(data.get("threshold_value", 0.0) or 0.0),
        recommendation=recommendation,
        created_at=created_at,
        resolved_at=resolved_at,
        metadata=metadata,
    )


class RiskPostgresDatabase:
    """Async PostgreSQL adapter replacing the legacy Cosmos integration."""

    def __init__(self) -> None:
        self._postgres = PostgresManager(
            settings.POSTGRES_DSN,
            min_size=settings.POSTGRES_POOL_MIN_SIZE,
            max_size=settings.POSTGRES_POOL_MAX_SIZE,
        )
        self._connected = False

    async def initialize(self) -> None:
        if self._connected:
            return
        await ensure_connection(self._postgres)
        self._connected = True
        logger.info("Risk manager connected to PostgreSQL")

    async def close(self) -> None:
        if not self._connected:
            return
        await self._postgres.close()
        self._connected = False
        logger.info("Risk manager PostgreSQL connection closed")

    # ------------------------------------------------------------------
    # Position management
    # ------------------------------------------------------------------
    async def get_current_positions(self, strategy_id: Optional[str] = None) -> List[Dict[str, Any]]:
        where = "WHERE status = 'open'"
        params: List[Any] = []
        if strategy_id:
            where += " AND strategy_id = $1"
            params.append(_ensure_uuid(strategy_id))
        query = f"""
            SELECT
                id,
                strategy_id,
                symbol,
                side,
                quantity,
                entry_price,
                current_price,
                unrealized_pnl,
                realized_pnl,
                stop_loss_price,
                take_profit_price,
                status,
                position_value_usd,
                risk_score,
                metadata,
                created_at,
                updated_at,
                closed_at
            FROM risk_positions
            {where}
            ORDER BY created_at DESC
        """
        records = await self._postgres.fetch(query, *params)
        positions = [_row_to_dict(record) for record in records]
        for position in positions:
            position.setdefault("metadata", {})
            position.setdefault("current_value_usd", position.get("position_value_usd", 0.0))
        return positions

    async def get_all_active_positions(self) -> List[Dict[str, Any]]:
        return await self.get_current_positions()

    async def get_portfolio_value(self) -> float:
        """
        Get current portfolio value (sum of all open positions).
        
        Returns:
            Total portfolio value in USD
        """
        query = """
            SELECT COALESCE(SUM(quantity * entry_price), 0) as total_value
            FROM risk_positions
            WHERE status = 'open'
        """
        record = await self._postgres.fetchrow(query)
        return float(record['total_value']) if record else 0.0

    async def get_position(self, position_id: str) -> Optional[Dict[str, Any]]:
        record = await self._postgres.fetchrow(
            "SELECT * FROM risk_positions WHERE id = $1",
            position_id,
        )
        if record is None:
            return None
        result = _row_to_dict(record)
        result.setdefault("metadata", {})
        result.setdefault("current_value_usd", result.get("position_value_usd", 0.0))
        return result

    async def create_position(self, position_data: Dict[str, Any]) -> Optional[str]:
        position_id = _ensure_text_identifier(position_data.get("id"))
        query = """
            INSERT INTO risk_positions (
                id,
                strategy_id,
                symbol,
                side,
                quantity,
                entry_price,
                current_price,
                unrealized_pnl,
                realized_pnl,
                stop_loss_price,
                take_profit_price,
                status,
                position_value_usd,
                risk_score,
                metadata,
                created_at,
                updated_at
            )
            VALUES (
                $1,
                $2,
                $3,
                $4,
                $5,
                $6,
                $7,
                $8,
                $9,
                $10,
                $11,
                $12,
                $13,
                $14,
                $15::jsonb,
                $16,
                $16
            )
            ON CONFLICT (id) DO NOTHING
        """
        now = _utcnow()
        await self._postgres.execute(
            query,
            position_id,
            _ensure_uuid(position_data["strategy_id"]) if position_data.get("strategy_id") else None,
            position_data["symbol"],
            position_data["side"],
            position_data["quantity"],
            position_data["entry_price"],
            position_data.get("current_price", position_data["entry_price"]),
            position_data.get("unrealized_pnl", 0.0),
            position_data.get("realized_pnl", 0.0),
            position_data.get("stop_loss_price"),
            position_data.get("take_profit_price"),
            position_data.get("status", "open"),
            position_data.get("position_value_usd", 0.0),
            position_data.get("risk_score", 0.0),
            json.dumps(position_data.get("metadata", {}), default=_to_serializable),
            now,
        )
        logger.info("Position created", position_id=position_id, symbol=position_data["symbol"])
        return position_id

    async def update_position(self, position_id: str, updates: Dict[str, Any]) -> bool:
        assignments: List[str] = []
        values: List[Any] = []
        for column, value in updates.items():
            if column == "metadata":
                assignments.append("metadata = $%d" % (len(values) + 2))
                values.append(json.dumps(value or {}, default=_to_serializable))
            elif column == "strategy_id" and value is not None:
                assignments.append("strategy_id = $%d" % (len(values) + 2))
                values.append(_ensure_uuid(value))
            else:
                assignments.append(f"{column} = $%d" % (len(values) + 2))
                values.append(value)
        if not assignments:
            return True
        assignments.append("updated_at = $%d" % (len(values) + 2))
        values.append(_utcnow())
        query = f"""
            UPDATE risk_positions
               SET {', '.join(assignments)}
             WHERE id = $1
        """
        await self._postgres.execute(query, position_id, *values)
        return True

    async def close_position(self, position_id: str, realized_pnl: float, close_price: Optional[float] = None) -> bool:
        query = """
            UPDATE risk_positions
               SET status = 'closed',
                   realized_pnl = $2,
                   current_price = COALESCE($3, current_price),
                   closed_at = $4,
                   updated_at = $4
             WHERE id = $1
        """
        await self._postgres.execute(
            query,
            position_id,
            realized_pnl,
            close_price,
            _utcnow(),
        )
        return True

    async def reduce_position(self, position_id: str, reduction_percent: float, reason: str) -> bool:
        async with self._postgres.transaction() as conn:
            record = await conn.fetchrow(
                "SELECT quantity, metadata FROM risk_positions WHERE id = $1",
                position_id,
            )
            if record is None:
                return False
            new_quantity = record["quantity"] * max(0.0, 1.0 - reduction_percent / 100.0)
            metadata = dict(record["metadata"] or {})
            adjustments: List[Dict[str, Any]] = metadata.setdefault("adjustments", [])
            adjustments.append({
                "timestamp": _utcnow().isoformat(),
                "reduction_percent": reduction_percent,
                "reason": reason,
            })
            await conn.execute(
                """
                    UPDATE risk_positions
                       SET quantity = $2,
                           metadata = $3,
                           updated_at = $4
                     WHERE id = $1
                """,
                position_id,
                new_quantity,
                json.dumps(metadata, default=_to_serializable),
                _utcnow(),
            )
        return True

    async def update_position_from_message(self, position_data: Dict[str, Any]) -> bool:
        position_id = position_data["id"]
        updates = {key: value for key, value in position_data.items() if key != "id"}
        return await self.update_position(position_id, updates)

    # ------------------------------------------------------------------
    # Stop-loss management
    # ------------------------------------------------------------------
    async def create_stop_loss_order(self, order: Any) -> None:
        query = """
            INSERT INTO stop_losses (
                id,
                position_id,
                strategy_id,
                symbol,
                stop_type,
                status,
                entry_price,
                current_price,
                stop_price,
                initial_stop_price,
                quantity,
                trigger_count,
                config,
                profit_loss,
                metadata,
                created_at,
                updated_at
            )
            VALUES (
                $1,
                $2,
                $3,
                $4,
                $5,
                $6,
                $7,
                $8,
                $9,
                $10,
                $11,
                $12,
                $13::jsonb,
                $14,
                $15::jsonb,
                $16,
                $16
            )
            ON CONFLICT (id) DO NOTHING
        """
        now = _utcnow()
        order_id = _ensure_text_identifier(_get_attr(order, "id"))
        position_id = _ensure_text_identifier(_get_attr(order, "position_id"))

        raw_strategy_id = _get_attr(order, "strategy_id")
        metadata = dict(_get_attr(order, "metadata", {}) or {})
        if not raw_strategy_id:
            raw_strategy_id = metadata.get("strategy_id")
        strategy_uuid = _ensure_uuid(raw_strategy_id) if raw_strategy_id else None

        stop_type_value = _get_attr(order, "stop_type", "fixed")
        stop_type_str = stop_type_value.value if hasattr(stop_type_value, "value") else str(stop_type_value)

        status_value = _get_attr(order, "status", "active")
        status_str = status_value.value if hasattr(status_value, "value") else str(status_value)

        entry_price = float(_get_attr(order, "entry_price", 0.0) or 0.0)
        current_price = float(_get_attr(order, "current_price", entry_price) or entry_price)
        stop_price = float(_get_attr(order, "stop_price", entry_price) or entry_price)
        initial_stop_price = float(_get_attr(order, "initial_stop_price", stop_price) or stop_price)
        quantity = float(_get_attr(order, "quantity", 0.0) or 0.0)
        trigger_count = int(_get_attr(order, "trigger_count", 0) or 0)
        profit_loss = float(_get_attr(order, "profit_loss", 0.0) or 0.0)

        metadata.setdefault("highest_price", _get_attr(order, "highest_price", entry_price))
        metadata.setdefault("lowest_price", _get_attr(order, "lowest_price", entry_price))

        config_json = _serialise_stop_loss_config(_get_attr(order, "config"))
        metadata_json = json.dumps(metadata, default=_to_serializable)

        created_at = _parse_datetime(_get_attr(order, "created_at")) or now
        updated_at = _parse_datetime(_get_attr(order, "last_updated") or _get_attr(order, "updated_at")) or created_at

        await self._postgres.execute(
            query,
            order_id,
            position_id,
            strategy_uuid,
            _get_attr(order, "symbol"),
            stop_type_str,
            status_str,
            entry_price,
            current_price,
            stop_price,
            initial_stop_price,
            quantity,
            trigger_count,
            config_json,
            profit_loss,
            metadata_json,
            created_at,
            updated_at,
        )

    async def update_stop_loss_order(self, order: Any) -> None:
        query = """
            UPDATE stop_losses
               SET status = $2,
                   current_price = $3,
                   stop_price = $4,
                   trigger_count = $5,
                   profit_loss = $6,
                   metadata = $7::jsonb,
                   updated_at = $8
             WHERE id = $1
        """
        status_value = _get_attr(order, "status", "active")
        status_str = status_value.value if hasattr(status_value, "value") else str(status_value)
        metadata_dict = dict(_get_attr(order, "metadata", {}) or {})
        if _get_attr(order, "highest_price") is not None:
            metadata_dict["highest_price"] = _get_attr(order, "highest_price")
        if _get_attr(order, "lowest_price") is not None:
            metadata_dict["lowest_price"] = _get_attr(order, "lowest_price")
        metadata = json.dumps(metadata_dict, default=_to_serializable)
        updated_at = _parse_datetime(_get_attr(order, "last_updated") or _get_attr(order, "updated_at")) or _utcnow()
        await self._postgres.execute(
            query,
            _get_attr(order, "id"),
            status_str,
            _get_attr(order, "current_price"),
            _get_attr(order, "stop_price"),
            _get_attr(order, "trigger_count", 0),
            _get_attr(order, "profit_loss", 0.0),
            metadata,
            updated_at,
        )

    async def get_active_stop_loss_orders(self) -> List["StopLossOrder"]:
        query = """
            SELECT *
              FROM stop_losses
             WHERE status = 'active'
             ORDER BY updated_at DESC
        """
        records = await self._postgres.fetch(query)
        return [_deserialise_stop_loss_record(record) for record in records]

    async def get_active_stop_loss_by_position(self, position_id: str) -> Optional["StopLossOrder"]:
        record = await self._postgres.fetchrow(
            "SELECT * FROM stop_losses WHERE position_id = $1 AND status = 'active'",
            position_id,
        )
        if record is None:
            return None
        return _deserialise_stop_loss_record(record)

    async def update_trailing_stop(self, stop_loss_id: str, new_stop_price: float) -> bool:
        await self._postgres.execute(
            """
                UPDATE stop_losses
                   SET stop_price = $2,
                       updated_at = $3
                 WHERE id = $1
            """,
            stop_loss_id,
            new_stop_price,
            _utcnow(),
        )
        return True

    async def update_stop_loss_status(self, stop_loss_id: str, status: str) -> bool:
        await self._postgres.execute(
            """
                UPDATE stop_losses
                   SET status = $2,
                       updated_at = $3
                 WHERE id = $1
            """,
            stop_loss_id,
            status,
            _utcnow(),
        )
        return True

    # ------------------------------------------------------------------
    # Risk metrics and analytics
    # ------------------------------------------------------------------
    async def store_risk_metrics(self, metrics: Any) -> bool:
        query = """
            INSERT INTO risk_metrics (id, date, timestamp, metrics)
            VALUES (uuid_generate_v4(), $1, $2, $3::jsonb)
            ON CONFLICT (date) DO UPDATE
                SET timestamp = EXCLUDED.timestamp,
                    metrics = EXCLUDED.metrics
        """
        timestamp_value = _parse_datetime(getattr(metrics, "timestamp", None))
        if timestamp_value is None and isinstance(metrics, dict):
            timestamp_value = _parse_datetime(metrics.get("timestamp"))
        if timestamp_value is None:
            timestamp_value = _utcnow()

        metrics_payload = metrics.__dict__ if hasattr(metrics, "__dict__") else metrics
        await self._postgres.execute(
            query,
            timestamp_value.date(),
            timestamp_value,
            json.dumps(metrics_payload, default=_to_serializable),
        )
        return True

    async def get_historical_risk_metrics(self, days: int = 30) -> List[Any]:
        query = """
            SELECT metrics
              FROM risk_metrics
             WHERE date >= (CURRENT_DATE - $1::integer)
             ORDER BY timestamp DESC
        """
        records = await self._postgres.fetch(query, days)
        results = []
        for record in records:
            payload = record["metrics"]
            if isinstance(payload, str):
                payload = json.loads(payload)
            if isinstance(payload, dict):
                processed: Dict[str, Any] = {}
                for key, value in payload.items():
                    if key in {"timestamp", "created_at", "updated_at"}:
                        processed[key] = _parse_datetime(value)
                    elif key == "risk_level":
                        processed[key] = _coerce_risk_level(value)
                    else:
                        processed[key] = value
                payload = AttrDict(processed)
            results.append(payload)
        return results

    async def get_active_risk_alerts(self) -> List[Dict[str, Any]]:
        query = """
            SELECT *
              FROM risk_alerts
             WHERE status = 'open'
             ORDER BY timestamp DESC
        """
        records = await self._postgres.fetch(query)
        results: List[Dict[str, Any]] = []
        for record in records:
            data = _row_to_dict(record)
            if "timestamp" in data:
                data["timestamp"] = _parse_datetime(data["timestamp"])
            if "updated_at" in data:
                data["updated_at"] = _parse_datetime(data["updated_at"])
            if data.get("metadata") is None:
                data["metadata"] = {}
            results.append(AttrDict(data))
        return results

    async def get_risk_alerts(self, days: int = 30, status: Optional[str] = None) -> List["RiskAlert"]:
        interval_literal = f"{max(days, 0)} days"
        params: List[Any] = [interval_literal]
        status_clause = ""
        if status:
            status_clause = " AND status = $2"
            params.append(status)

        query = f"""
            SELECT *
              FROM risk_alerts
             WHERE timestamp >= NOW() - $1::interval
             {status_clause}
             ORDER BY timestamp DESC
        """
        records = await self._postgres.fetch(query, *params)
        return [_deserialise_risk_alert_record(record) for record in records]

    async def store_risk_alert(self, alert: Any) -> bool:
        query = """
            INSERT INTO risk_alerts (
                id,
                timestamp,
                alert_type,
                severity,
                title,
                message,
                strategy_id,
                symbol,
                current_value,
                threshold_value,
                recommendation,
                metadata,
                status,
                updated_at
            )
            VALUES (
                $1,
                $2,
                $3,
                $4,
                $5,
                $6,
                $7,
                $8,
                $9,
                $10,
                $11,
                $12::jsonb,
                $13,
                $14
            )
            ON CONFLICT (id) DO UPDATE
                SET timestamp = EXCLUDED.timestamp,
                    alert_type = EXCLUDED.alert_type,
                    severity = EXCLUDED.severity,
                    title = EXCLUDED.title,
                    message = EXCLUDED.message,
                    strategy_id = EXCLUDED.strategy_id,
                    symbol = EXCLUDED.symbol,
                    current_value = EXCLUDED.current_value,
                    threshold_value = EXCLUDED.threshold_value,
                    recommendation = EXCLUDED.recommendation,
                    metadata = EXCLUDED.metadata,
                    status = EXCLUDED.status,
                    updated_at = EXCLUDED.updated_at
        """
        alert_id = _get_attr(alert, "id")
        timestamp_value = _parse_datetime(_get_attr(alert, "timestamp"))
        if timestamp_value is None:
            timestamp_value = _parse_datetime(_get_attr(alert, "created_at"))
        if timestamp_value is None:
            timestamp_value = _utcnow()

        alert_type_value = _get_attr(alert, "alert_type")
        if hasattr(alert_type_value, "value"):
            alert_type_value = alert_type_value.value

        severity_value = _get_attr(alert, "severity")
        if hasattr(severity_value, "value"):
            severity_value = severity_value.value

        strategy_reference = _get_attr(alert, "strategy_id")
        metadata_payload = _get_attr(alert, "metadata", {}) or {}
        status_value = _get_attr(alert, "status", "open")
        updated_at = _utcnow()
        identifier = _ensure_text_identifier(alert_id)
        if alert_id is None:
            if isinstance(alert, dict):
                alert.setdefault("id", identifier)
            else:
                setattr(alert, "id", identifier)
        if not isinstance(alert, dict) and getattr(alert, "created_at", None) is None:
            setattr(alert, "created_at", timestamp_value)
        elif isinstance(alert, dict):
            alert.setdefault("created_at", timestamp_value)

        await self._postgres.execute(
            query,
            identifier,
            timestamp_value,
            alert_type_value,
            severity_value,
            _get_attr(alert, "title"),
            _get_attr(alert, "message"),
            _ensure_uuid(strategy_reference) if strategy_reference else None,
            _get_attr(alert, "symbol"),
            _get_attr(alert, "current_value"),
            _get_attr(alert, "threshold_value"),
            _get_attr(alert, "recommendation"),
            json.dumps(metadata_payload, default=_to_serializable),
            status_value,
            updated_at,
        )
        return True

    async def resolve_risk_alert(self, alert_id: str) -> bool:
        await self._postgres.execute(
            "UPDATE risk_alerts SET status = 'resolved', updated_at = NOW() WHERE id = $1",
            alert_id,
        )
        return True

    async def store_correlation_matrix(self, correlation_data: Dict[str, Any]) -> bool:
        query = """
            INSERT INTO correlation_matrices (id, date, timestamp, correlations)
            VALUES (uuid_generate_v4(), $1, $2, $3::jsonb)
            ON CONFLICT (date) DO UPDATE
                SET timestamp = EXCLUDED.timestamp,
                    correlations = EXCLUDED.correlations
        """
        now = _utcnow()
        await self._postgres.execute(
            query,
            now.date(),
            now,
            json.dumps(correlation_data, default=_to_serializable),
        )
        return True

    async def get_latest_correlation_matrix(self) -> Dict[str, Any]:
        record = await self._postgres.fetchrow(
            "SELECT correlations FROM correlation_matrices ORDER BY timestamp DESC LIMIT 1"
        )
        if record is None:
            return {}
        data = record["correlations"]
        if isinstance(data, str):
            data = json.loads(data)
        return data or {}

    async def store_var_calculation(self, var_data: Dict[str, Any]) -> bool:
        query = """
            INSERT INTO var_calculations (id, date, timestamp, values, method)
            VALUES (uuid_generate_v4(), $1, $2, $3::jsonb, COALESCE($4, 'historical_simulation'))
            ON CONFLICT (date) DO UPDATE
                SET timestamp = EXCLUDED.timestamp,
                    values = EXCLUDED.values,
                    method = EXCLUDED.method
        """
        now = _utcnow()
        await self._postgres.execute(
            query,
            now.date(),
            now,
            json.dumps(var_data, default=_to_serializable),
            var_data.get("method"),
        )
        return True

    async def update_drawdown_tracking(self, current_portfolio_value: float) -> bool:
        query = """
            INSERT INTO drawdown_tracking (
                date,
                peak_value,
                current_value,
                current_drawdown,
                max_drawdown,
                drawdown_duration_days,
                created_at,
                updated_at
            )
            VALUES (
                CURRENT_DATE,
                $1,
                $1,
                0,
                0,
                0,
                NOW(),
                NOW()
            )
            ON CONFLICT (date) DO UPDATE
                SET current_value = $1,
                    current_drawdown = GREATEST(0, (drawdown_tracking.peak_value - $1) / NULLIF(drawdown_tracking.peak_value, 0)),
                    max_drawdown = GREATEST(drawdown_tracking.max_drawdown, (drawdown_tracking.peak_value - $1) / NULLIF(drawdown_tracking.peak_value, 0)),
                    drawdown_duration_days = CASE
                        WHEN $1 > drawdown_tracking.peak_value THEN 0
                        ELSE drawdown_tracking.drawdown_duration_days + 1
                    END,
                    updated_at = NOW()
        """
        await self._postgres.execute(query, current_portfolio_value)
        return True

    async def get_max_drawdown(self) -> float:
        record = await self._postgres.fetchrow("SELECT MAX(max_drawdown) AS value FROM drawdown_tracking")
        return float(record["value"]) if record and record["value"] is not None else 0.0

    async def get_portfolio_high_water_mark(self) -> float:
        record = await self._postgres.fetchrow("SELECT MAX(peak_value) AS value FROM drawdown_tracking")
        return float(record["value"]) if record and record["value"] is not None else 0.0

    async def get_total_portfolio_value(self) -> float:
        record = await self._postgres.fetchrow("SELECT SUM(position_value_usd) AS value FROM risk_positions WHERE status = 'open'")
        return float(record["value"]) if record and record["value"] is not None else 0.0

    async def update_peak_portfolio_value(self, portfolio_value: float) -> bool:
        await self._postgres.execute(
            """
                INSERT INTO drawdown_tracking (date, peak_value, current_value, created_at, updated_at)
                VALUES (CURRENT_DATE, $1, $1, NOW(), NOW())
                ON CONFLICT (date) DO UPDATE
                    SET peak_value = GREATEST(drawdown_tracking.peak_value, EXCLUDED.peak_value),
                        updated_at = NOW()
            """,
            portfolio_value,
        )
        return True

    # ------------------------------------------------------------------
    # Liquidity, volatility, and analytics helpers
    # ------------------------------------------------------------------
    async def get_symbol_volatility(self, symbol: str, days: int = 20) -> float:
        record = await self._postgres.fetchrow(
            "SELECT volatility, refreshed_at FROM symbol_volatility_cache WHERE symbol = $1",
            symbol.upper(),
        )
        if record:
            return float(record["volatility"])
        return settings.HIGH_VOLATILITY_THRESHOLD

    async def get_symbol_liquidity(self, symbol: str) -> float:
        record = await self._postgres.fetchrow(
            "SELECT liquidity_score FROM symbol_liquidity_cache WHERE symbol = $1",
            symbol.upper(),
        )
        if record:
            return float(record["liquidity_score"])
        return settings.LOW_LIQUIDITY_THRESHOLD

    async def get_account_balance(self) -> Dict[str, float]:
        # Placeholder until exchange integration writes into PostgreSQL
        return {
            "total_balance_usd": 10000.0,
            "available_balance_usd": 8000.0,
            "reserved_balance_usd": 2000.0,
            "unrealized_pnl": 0.0,
            "margin_used": 0.0,
            "margin_available": 10000.0,
        }

    async def store_portfolio_snapshot(self, snapshot_data: Dict[str, Any]) -> bool:
        query = """
            INSERT INTO portfolio_snapshots (id, timestamp, snapshot)
            VALUES ($1, $2, $3::jsonb)
            ON CONFLICT (id) DO NOTHING
        """
        snapshot_id = _ensure_text_identifier(snapshot_data.get("id") if isinstance(snapshot_data, dict) else None)
        timestamp_raw = snapshot_data.get("timestamp") if isinstance(snapshot_data, dict) else None
        timestamp = _parse_datetime(timestamp_raw) if timestamp_raw is not None else None
        await self._postgres.execute(
            query,
            snapshot_id,
            timestamp or _utcnow(),
            json.dumps(snapshot_data, default=_to_serializable),
        )
        return True

    # ------------------------------------------------------------------
    # Administrative logging helpers
    # ------------------------------------------------------------------
    async def log_admin_action(self, **details: Any) -> None:
        await self._postgres.execute(
            "INSERT INTO risk_admin_actions (id, action, details, created_at) VALUES (uuid_generate_v4(), $1, $2::jsonb, $3)",
            details.get("action", "unspecified"),
            json.dumps(details, default=_to_serializable),
            _utcnow(),
        )

    async def save_portfolio_limits(self, limits: Any) -> None:
        await self._postgres.execute(
            "INSERT INTO risk_configuration_changes (id, changes, created_at) VALUES (uuid_generate_v4(), $1::jsonb, $2)",
            json.dumps(limits.__dict__ if hasattr(limits, "__dict__") else limits, default=_to_serializable),
            _utcnow(),
        )

    async def save_adjustment_history(self, adjustments: Dict[str, Any]) -> None:
        await self._postgres.execute(
            "INSERT INTO risk_adjustment_history (id, timestamp, adjustments) VALUES (uuid_generate_v4(), $1, $2::jsonb)",
            _utcnow(),
            json.dumps(adjustments, default=_to_serializable),
        )

    async def store_configuration_change(self, changes: Dict[str, Any]) -> None:
        await self._postgres.execute(
            "INSERT INTO risk_configuration_changes (id, changes, created_at) VALUES (uuid_generate_v4(), $1::jsonb, $2)",
            json.dumps(changes, default=_to_serializable),
            _utcnow(),
        )

    async def get_recent_market_returns(self, days: int = 30) -> List[Dict[str, Any]]:
        # Placeholder until market data persists returns
        return []

    async def get_market_volatility(self) -> float:
        # Placeholder stubs for advanced controllers
        return settings.HIGH_VOLATILITY_THRESHOLD
    
    # ============================================================================
    # Goal-Oriented Trading Methods
    # ============================================================================
    
    @ensure_connection
    async def get_current_goal_progress(self) -> Dict[str, float]:
        """
        Get current progress toward financial goals
        
        Returns:
            Dictionary with:
            - monthly_return_progress: Progress toward 10% monthly return (0.0 to 1.0+)
            - monthly_income_progress: Progress toward €4k monthly income (0.0 to 1.0+)
            - portfolio_value: Current total portfolio value in EUR
        """
        try:
            # Get current month's start and end
            now = datetime.now(timezone.utc)
            month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            
            # Get portfolio value from positions
            portfolio_query = """
                SELECT COALESCE(SUM(current_value), 0) as total_value
                FROM portfolio_positions
                WHERE status = 'open'
            """
            portfolio_result = await self._postgres.fetchrow(portfolio_query)
            portfolio_value = float(portfolio_result['total_value']) if portfolio_result else 0.0
            
            # Get month start portfolio value
            month_start_query = """
                SELECT portfolio_value
                FROM goal_progress_history
                WHERE snapshot_date = $1
                ORDER BY created_at DESC
                LIMIT 1
            """
            month_start_result = await self._postgres.fetchrow(month_start_query, month_start.date())
            month_start_value = float(month_start_result['portfolio_value']) if month_start_result else portfolio_value
            
            # Calculate monthly return progress
            if month_start_value > 0:
                monthly_return = (portfolio_value - month_start_value) / month_start_value
                monthly_return_progress = monthly_return / 0.10  # Target is 10%
            else:
                monthly_return_progress = 0.0
            
            # Get monthly realized P&L (income)
            income_query = """
                SELECT COALESCE(SUM(realized_pnl), 0) as total_income
                FROM trades
                WHERE exit_timestamp >= $1
                AND exit_timestamp < $2
                AND realized_pnl > 0
            """
            income_result = await self._postgres.fetchrow(income_query, month_start, now)
            monthly_income = float(income_result['total_income']) if income_result else 0.0
            monthly_income_progress = monthly_income / 4000.0  # Target is €4,000
            
            return {
                'monthly_return_progress': monthly_return_progress,
                'monthly_income_progress': monthly_income_progress,
                'portfolio_value': portfolio_value,
                'monthly_return_actual': monthly_return if month_start_value > 0 else 0.0,
                'monthly_income_actual': monthly_income
            }
            
        except Exception as e:
            logger.error("Error getting goal progress", error=str(e))
            return {
                'monthly_return_progress': 0.0,
                'monthly_income_progress': 0.0,
                'portfolio_value': 0.0,
                'monthly_return_actual': 0.0,
                'monthly_income_actual': 0.0
            }
    
    @ensure_connection
    async def log_goal_adjustment(
        self,
        portfolio_value: float,
        adjustment_factor: float,
        reason: str
    ) -> None:
        """
        Log position sizing adjustment decision for audit trail
        
        Args:
            portfolio_value: Current portfolio value
            adjustment_factor: Applied adjustment factor
            reason: Reason for adjustment
        """
        try:
            query = """
                INSERT INTO goal_adjustment_log 
                (id, timestamp, portfolio_value, adjustment_factor, reason)
                VALUES (uuid_generate_v4(), $1, $2, $3, $4)
            """
            await self._postgres.execute(
                query,
                _utcnow(),
                Decimal(str(portfolio_value)),
                Decimal(str(adjustment_factor)),
                reason
            )
        except Exception as e:
            logger.error("Error logging goal adjustment", error=str(e))
    
    async def update_goal_progress_snapshot(
        self,
        goal_type: str,
        target_value: float,
        actual_value: float
    ) -> None:
        """
        Store daily snapshot of goal progress
        
        Args:
            goal_type: Type of goal (monthly_return, monthly_income, portfolio_value)
            target_value: Target value for the goal
            actual_value: Current actual value
        """
        try:
            # Get or create goal
            goal_query = """
                INSERT INTO financial_goals (goal_type, target_value, current_value, progress_percent, status, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, $6)
                ON CONFLICT (goal_type)
                DO UPDATE SET
                    current_value = EXCLUDED.current_value,
                    progress_percent = EXCLUDED.progress_percent,
                    status = EXCLUDED.status,
                    updated_at = EXCLUDED.updated_at
                RETURNING id
            """
            
            progress_percent = (actual_value / target_value * 100) if target_value > 0 else 0
            status = self._get_goal_status(progress_percent)
            
            goal_result = await self._postgres.fetchrow(
                goal_query,
                goal_type,
                Decimal(str(target_value)),
                Decimal(str(actual_value)),
                Decimal(str(progress_percent)),
                status,
                _utcnow()
            )
            
            goal_id = goal_result['id']
            
            # Store progress history
            history_query = """
                INSERT INTO goal_progress_history 
                (goal_id, snapshot_date, actual_value, target_value, variance_percent, created_at)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (goal_id, snapshot_date)
                DO UPDATE SET
                    actual_value = EXCLUDED.actual_value,
                    variance_percent = EXCLUDED.variance_percent
            """
            
            variance_percent = ((actual_value - target_value) / target_value * 100) if target_value > 0 else 0
            
            await self._postgres.execute(
                history_query,
                goal_id,
                date.today(),
                Decimal(str(actual_value)),
                Decimal(str(target_value)),
                Decimal(str(variance_percent)),
                _utcnow()
            )
            
        except Exception as e:
            logger.error("Error updating goal progress snapshot", error=str(e), goal_type=goal_type)
    
    def _get_goal_status(self, progress_percent: float) -> str:
        """Determine goal status based on progress percentage"""
        if progress_percent >= 100:
            return "achieved"
        elif progress_percent >= 85:
            return "on_track"
        elif progress_percent >= 70:
            return "at_risk"
        else:
            return "behind"
    
    async def get_all_goals_status(self) -> List[Dict[str, Any]]:
        """Get status of all financial goals"""
        if not self._connected:
            await self.initialize()
        
        query = """
            SELECT 
                goal_type,
                target_value,
                current_value,
                progress_percent,
                status,
                updated_at
            FROM financial_goals
            ORDER BY goal_type
        """
        
        rows = await self._postgres.fetch(query)
        
        goals = []
        for row in rows:
            goals.append({
                "goal_type": row['goal_type'],
                "target_value": float(row['target_value']),
                "current_value": float(row['current_value']),
                "progress_percent": float(row['progress_percent']),
                "status": row['status'],
                "updated_at": row['updated_at'].isoformat() if row['updated_at'] else None
            })
        
        return goals
    
    async def get_goal_history(self, goal_type: str, days: int = 30) -> List[Dict[str, Any]]:
        """Get historical progress for a specific goal"""
        if not self._connected:
            await self.initialize()
        
        query = """
            SELECT 
                h.snapshot_date,
                h.actual_value,
                h.variance_percent,
                g.target_value,
                g.status
            FROM goal_progress_history h
            JOIN financial_goals g ON h.goal_id = g.id
            WHERE g.goal_type = $1
                AND h.snapshot_date >= CURRENT_DATE - $2::integer
            ORDER BY h.snapshot_date DESC
        """
        
        rows = await self._postgres.fetch(query, goal_type, days)
        
        history = []
        for row in rows:
            history.append({
                "date": row['snapshot_date'].isoformat(),
                "actual_value": float(row['actual_value']),
                "target_value": float(row['target_value']),
                "variance_percent": float(row['variance_percent']),
                "status": row['status']
            })
        
        return history


# Global database instance for compatibility with existing imports
postgres_database = RiskPostgresDatabase()
