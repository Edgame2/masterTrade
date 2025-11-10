"""PostgreSQL persistence layer for the Order Executor service."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

import structlog

from config import settings
from models import Order, OrderRequest, Trade
from shared.postgres_manager import PostgresManager, ensure_connection

logger = structlog.get_logger(__name__)


def _to_float(value: Any) -> Optional[float]:
	if value is None:
		return None
	if isinstance(value, Decimal):
		return float(value)
	if isinstance(value, (int, float)):
		return float(value)
	return value


def _order_record_to_dict(record: Any) -> Dict[str, Any]:
	return {
		"id": str(record["id"]),
		"strategy_id": record["strategy_id"],
		"symbol": record["symbol"],
		"signal_id": record["signal_id"],
		"exchange_order_id": record["exchange_order_id"],
		"client_order_id": record["client_order_id"],
		"order_type": record["order_type"],
		"side": record["side"],
		"quantity": _to_float(record["quantity"]),
		"price": _to_float(record["price"]),
		"stop_price": _to_float(record["stop_price"]),
		"status": record["status"],
		"filled_quantity": _to_float(record["filled_quantity"]),
		"avg_fill_price": _to_float(record["avg_fill_price"]),
		"commission": _to_float(record["commission"]),
		"commission_asset": record["commission_asset"],
		"environment": record["environment"],
		"order_time": record["order_time"].isoformat() if record["order_time"] else None,
		"update_time": record["update_time"].isoformat() if record["update_time"] else None,
		"metadata": record["metadata"] or {},
	}


def _trade_record_to_dict(record: Any) -> Dict[str, Any]:
	return {
		"id": str(record["id"]),
		"order_id": str(record["order_id"]),
		"exchange_trade_id": record["exchange_trade_id"],
		"symbol": record["symbol"],
		"side": record["side"],
		"quantity": _to_float(record["quantity"]),
		"price": _to_float(record["price"]),
		"commission": _to_float(record["commission"]),
		"commission_asset": record["commission_asset"],
		"is_maker": record["is_maker"],
		"trade_time": record["trade_time"].isoformat() if record["trade_time"] else None,
	}


def _env_record_to_dict(record: Any) -> Dict[str, Any]:
	return {
		"strategy_id": record["strategy_id"],
		"environment": record["environment"],
		"max_position_size": _to_float(record["max_position_size"]),
		"max_daily_trades": record["max_daily_trades"],
		"risk_multiplier": _to_float(record["risk_multiplier"]),
		"enabled": record["enabled"],
		"metadata": record.get("metadata") or {},
		"created_at": record["created_at"],
		"updated_at": record["updated_at"],
	}


class Database:
	"""Async PostgreSQL-backed persistence for orders, trades, and configuration."""

	def __init__(self) -> None:
		self._postgres = PostgresManager(
			settings.POSTGRES_DSN,
			min_size=settings.POSTGRES_POOL_MIN_SIZE,
			max_size=settings.POSTGRES_POOL_MAX_SIZE,
		)
		self._schema_ready = False

	async def connect(self) -> None:
		await ensure_connection(self._postgres)
		if not self._schema_ready:
			await self._create_tables()
			await self._seed_defaults()
			self._schema_ready = True
			logger.info("PostgreSQL schema ready for order executor service")

	async def disconnect(self) -> None:
		await self._postgres.close()

	async def _create_tables(self) -> None:
		statements: List[str] = [
			"""
			CREATE TABLE IF NOT EXISTS orders (
				id UUID PRIMARY KEY,
				strategy_id INTEGER NOT NULL,
				symbol TEXT NOT NULL,
				signal_id INTEGER,
				exchange_order_id TEXT,
				client_order_id TEXT NOT NULL,
				order_type TEXT NOT NULL,
				side TEXT NOT NULL,
				quantity NUMERIC NOT NULL,
				price NUMERIC,
				stop_price NUMERIC,
				status TEXT NOT NULL,
				filled_quantity NUMERIC NOT NULL DEFAULT 0,
				avg_fill_price NUMERIC,
				commission NUMERIC NOT NULL DEFAULT 0,
				commission_asset TEXT,
				environment TEXT NOT NULL DEFAULT 'testnet',
				order_time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
				update_time TIMESTAMPTZ,
				metadata JSONB NOT NULL DEFAULT '{}'::JSONB
			)
			""",
			"""
			CREATE INDEX IF NOT EXISTS idx_orders_status
				ON orders (status)
			""",
			"""
			CREATE INDEX IF NOT EXISTS idx_orders_symbol_time
				ON orders (symbol, order_time DESC)
			""",
			"""
			CREATE TABLE IF NOT EXISTS trades (
				id UUID PRIMARY KEY,
				order_id UUID NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
				exchange_trade_id TEXT NOT NULL,
				symbol TEXT NOT NULL,
				side TEXT NOT NULL,
				quantity NUMERIC NOT NULL,
				price NUMERIC NOT NULL,
				commission NUMERIC NOT NULL DEFAULT 0,
				commission_asset TEXT,
				is_maker BOOLEAN NOT NULL DEFAULT FALSE,
				trade_time TIMESTAMPTZ NOT NULL
			)
			""",
			"""
			CREATE INDEX IF NOT EXISTS idx_trades_symbol_time
				ON trades (symbol, trade_time DESC)
			""",
			"""
			CREATE TABLE IF NOT EXISTS portfolio_balances (
				asset TEXT PRIMARY KEY,
				free_balance NUMERIC NOT NULL DEFAULT 0,
				locked_balance NUMERIC NOT NULL DEFAULT 0,
				updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
			)
			""",
			"""
			CREATE TABLE IF NOT EXISTS trading_config (
				config_type TEXT PRIMARY KEY,
				enabled BOOLEAN NOT NULL,
				created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
				updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
			)
			""",
			"""
			CREATE TABLE IF NOT EXISTS strategy_environment_configs (
				strategy_id INTEGER PRIMARY KEY,
				environment TEXT NOT NULL,
				max_position_size NUMERIC,
				max_daily_trades INTEGER,
				risk_multiplier NUMERIC NOT NULL DEFAULT 1,
				enabled BOOLEAN NOT NULL DEFAULT TRUE,
				metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
				created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
				updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
			)
			""",
		]

		for statement in statements:
			await self._postgres.execute(statement)

	async def _seed_defaults(self) -> None:
		await self._postgres.execute(
			"""
			INSERT INTO trading_config (config_type, enabled)
			VALUES ('trading_enabled', TRUE)
			ON CONFLICT (config_type) DO NOTHING
			"""
		)

	# ------------------------------------------------------------------
	# Order operations
	# ------------------------------------------------------------------
	async def create_order(self, order_request: OrderRequest) -> Optional[Order]:
		order_id = uuid.uuid4()
		now = datetime.now(timezone.utc)

		record = await self._postgres.fetchrow(
			"""
			INSERT INTO orders (
				id, strategy_id, symbol, signal_id, exchange_order_id, client_order_id,
				order_type, side, quantity, price, stop_price, status, filled_quantity,
				avg_fill_price, commission, commission_asset, environment, order_time, metadata
			)
			VALUES (
				$1, $2, $3, $4, NULL, $5, $6, $7, $8, $9, $10, 'NEW', 0, NULL, 0,
				NULL, $11, $12, $13
			)
			RETURNING *
			""",
			order_id,
			order_request.strategy_id,
			order_request.symbol,
			order_request.signal_id,
			order_request.client_order_id,
			order_request.order_type,
			order_request.side,
			float(order_request.quantity),
			float(order_request.price) if order_request.price is not None else None,
			float(order_request.stop_price) if order_request.stop_price is not None else None,
			order_request.environment,
			now,
			order_request.metadata or {},
		)

		if record is None:
			logger.error("Failed to insert order", symbol=order_request.symbol)
			return None

		logger.info(
			"Created order",
			order_id=str(order_id),
			symbol=order_request.symbol,
			side=order_request.side,
		)

		return Order(
			id=record["id"],
			strategy_id=record["strategy_id"],
			symbol=record["symbol"],
			signal_id=record["signal_id"],
			exchange_order_id=record["exchange_order_id"],
			client_order_id=record["client_order_id"],
			order_type=record["order_type"],
			side=record["side"],
			quantity=float(record["quantity"]),
			price=_to_float(record["price"]),
			stop_price=_to_float(record["stop_price"]),
			status=record["status"],
			filled_quantity=_to_float(record["filled_quantity"]),
			avg_fill_price=_to_float(record["avg_fill_price"]),
			commission=_to_float(record["commission"]),
			commission_asset=record["commission_asset"],
			environment=record["environment"],
			order_time=record["order_time"],
			update_time=record["update_time"],
		)

	async def update_order_exchange_info(self, order_id: str, exchange_order_id: str) -> bool:
		try:
			parsed_order_id = uuid.UUID(order_id)
		except ValueError:
			logger.warning("Invalid order ID supplied", order_id=order_id)
			return False

		updated = await self._postgres.fetchval(
			"""
			UPDATE orders
			SET exchange_order_id = $1,
				update_time = $2
			WHERE id = $3
			RETURNING 1
			""",
			exchange_order_id,
			datetime.now(timezone.utc),
			parsed_order_id,
		)

		if updated:
			logger.info(
				"Updated exchange order info",
				order_id=order_id,
				exchange_order_id=exchange_order_id,
			)
			return True

		logger.warning("Order not found while updating exchange info", order_id=order_id)
		return False

	async def update_order_status(self, order_id: str, status: str) -> bool:
		try:
			parsed_order_id = uuid.UUID(order_id)
		except ValueError:
			logger.warning("Invalid order ID supplied", order_id=order_id)
			return False

		updated = await self._postgres.fetchval(
			"""
			UPDATE orders
			SET status = $1,
				update_time = $2
			WHERE id = $3
			RETURNING 1
			""",
			status,
			datetime.now(timezone.utc),
			parsed_order_id,
		)

		if updated:
			logger.info("Order status updated", order_id=order_id, status=status)
			return True

		logger.warning("Order not found while updating status", order_id=order_id)
		return False

	async def update_order_from_exchange(self, order_id: str, exchange_order: Dict[str, Any]) -> bool:
		try:
			parsed_order_id = uuid.UUID(order_id)
		except ValueError:
			logger.warning("Invalid order ID supplied", order_id=order_id)
			return False

		filled_quantity = exchange_order.get("executedQty")
		if filled_quantity is not None:
			filled_quantity = float(filled_quantity)

		avg_fill_price = exchange_order.get("price")
		if avg_fill_price is not None and avg_fill_price != "0":
			avg_fill_price = float(avg_fill_price)
		else:
			avg_fill_price = None

		updated = await self._postgres.fetchval(
			"""
			UPDATE orders
			SET status = COALESCE($1, status),
				filled_quantity = COALESCE($2, filled_quantity),
				avg_fill_price = COALESCE($3, avg_fill_price),
				update_time = $4
			WHERE id = $5
			RETURNING 1
			""",
			exchange_order.get("status"),
			filled_quantity,
			avg_fill_price,
			datetime.now(timezone.utc),
			parsed_order_id,
		)

		if updated:
			logger.info("Order updated from exchange payload", order_id=order_id)
			return True

		logger.warning("Order not found while syncing exchange payload", order_id=order_id)
		return False

	async def get_active_orders(self) -> List[Order]:
		records = await self._postgres.fetch(
			"""
			SELECT *
			FROM orders
			WHERE status IN ('NEW', 'PARTIALLY_FILLED')
			ORDER BY order_time DESC
			"""
		)
		return [
			Order(
				id=record["id"],
				strategy_id=record["strategy_id"],
				symbol=record["symbol"],
				signal_id=record["signal_id"],
				exchange_order_id=record["exchange_order_id"],
				client_order_id=record["client_order_id"],
				order_type=record["order_type"],
				side=record["side"],
				quantity=_to_float(record["quantity"]),
				price=_to_float(record["price"]),
				stop_price=_to_float(record["stop_price"]),
				status=record["status"],
				filled_quantity=_to_float(record["filled_quantity"]),
				avg_fill_price=_to_float(record["avg_fill_price"]),
				commission=_to_float(record["commission"]),
				commission_asset=record["commission_asset"],
				environment=record["environment"],
				order_time=record["order_time"],
				update_time=record["update_time"],
			)
			for record in records
		]

	async def get_recent_orders(self, limit: int = 100) -> List[Dict[str, Any]]:
		records = await self._postgres.fetch(
			"""
			SELECT *
			FROM orders
			ORDER BY order_time DESC
			LIMIT $1
			""",
			limit,
		)
		return [_order_record_to_dict(record) for record in records]

	# ------------------------------------------------------------------
	# Strategy environment configuration
	# ------------------------------------------------------------------
	async def upsert_strategy_environment_config(
		self,
		*,
		strategy_id: int,
		environment: str,
		max_position_size: Optional[float] = None,
		max_daily_trades: Optional[int] = None,
		risk_multiplier: float = 1.0,
		enabled: bool = True,
		metadata: Optional[Dict[str, Any]] = None,
	) -> Dict[str, Any]:
		now = datetime.now(timezone.utc)
		record = await self._postgres.fetchrow(
			"""
			INSERT INTO strategy_environment_configs (
				strategy_id,
				environment,
				max_position_size,
				max_daily_trades,
				risk_multiplier,
				enabled,
				metadata,
				created_at,
				updated_at
			)
			VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $8)
			ON CONFLICT (strategy_id) DO UPDATE SET
				environment = EXCLUDED.environment,
				max_position_size = EXCLUDED.max_position_size,
				max_daily_trades = EXCLUDED.max_daily_trades,
				risk_multiplier = EXCLUDED.risk_multiplier,
				enabled = EXCLUDED.enabled,
				metadata = EXCLUDED.metadata,
				updated_at = EXCLUDED.updated_at
			RETURNING *
			""",
			strategy_id,
			environment,
			max_position_size,
			max_daily_trades,
			risk_multiplier,
			enabled,
			metadata or {},
			now,
		)
		return _env_record_to_dict(record)

	async def get_strategy_environment_config(self, strategy_id: int) -> Optional[Dict[str, Any]]:
		record = await self._postgres.fetchrow(
			"""
			SELECT *
			FROM strategy_environment_configs
			WHERE strategy_id = $1
			""",
			strategy_id,
		)
		return _env_record_to_dict(record) if record else None

	async def get_all_strategy_environment_configs(self) -> List[Dict[str, Any]]:
		records = await self._postgres.fetch(
			"""
			SELECT *
			FROM strategy_environment_configs
			ORDER BY updated_at DESC
			"""
		)
		return [_env_record_to_dict(record) for record in records]

	# ------------------------------------------------------------------
	# Trade operations
	# ------------------------------------------------------------------
	async def insert_trade(self, trade: Trade) -> bool:
		trade_id = uuid.uuid4()
		record = await self._postgres.fetchval(
			"""
			INSERT INTO trades (
				id, order_id, exchange_trade_id, symbol, side, quantity,
				price, commission, commission_asset, is_maker, trade_time
			)
			VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
			RETURNING 1
			""",
			trade_id,
			trade.order_id,
			trade.exchange_trade_id,
			trade.symbol,
			trade.side,
			float(trade.quantity),
			float(trade.price),
			float(trade.commission),
			trade.commission_asset,
			trade.is_maker,
			trade.trade_time,
		)

		if record:
			logger.info("Inserted trade", trade_id=str(trade_id), symbol=trade.symbol)
			return True

		logger.error("Failed to insert trade", symbol=trade.symbol)
		return False

	async def get_recent_trades(self, limit: int = 100) -> List[Dict[str, Any]]:
		records = await self._postgres.fetch(
			"""
			SELECT *
			FROM trades
			ORDER BY trade_time DESC
			LIMIT $1
			""",
			limit,
		)
		return [_trade_record_to_dict(record) for record in records]

	# ------------------------------------------------------------------
	# Portfolio operations
	# ------------------------------------------------------------------
	async def update_portfolio_from_trade(self, order: Order, exchange_order: Dict[str, Any]) -> bool:
		# Placeholder for future portfolio logic; keep behaviour consistent with legacy implementation.
		logger.info(
			"Portfolio update placeholder",
			order_id=str(order.id),
			symbol=order.symbol,
		)
		return True

	async def get_portfolio_balance(self) -> List[Dict[str, Any]]:
		records = await self._postgres.fetch("SELECT * FROM portfolio_balances ORDER BY asset")
		balances: List[Dict[str, Any]] = []
		for record in records:
			balances.append(
				{
					"asset": record["asset"],
					"free_balance": _to_float(record["free_balance"]),
					"locked_balance": _to_float(record["locked_balance"]),
					"total_balance": _to_float(record["free_balance"] + record["locked_balance"]),
					"updated_at": record["updated_at"].isoformat() if record["updated_at"] else None,
				}
			)
		return balances

	# ------------------------------------------------------------------
	# Configuration operations
	# ------------------------------------------------------------------
	async def is_trading_enabled(self) -> bool:
		value = await self._postgres.fetchval(
			"SELECT enabled FROM trading_config WHERE config_type = 'trading_enabled'"
		)
		return bool(value) if value is not None else False

	async def toggle_trading_enabled(self) -> bool:
		current = await self._postgres.fetchrow(
			"SELECT enabled FROM trading_config WHERE config_type = 'trading_enabled'"
		)

		new_value = True
		if current is not None:
			new_value = not current["enabled"]

		await self._postgres.execute(
			"""
			INSERT INTO trading_config (config_type, enabled)
			VALUES ('trading_enabled', $1)
			ON CONFLICT (config_type) DO UPDATE
			SET enabled = EXCLUDED.enabled,
				updated_at = NOW()
			""",
			new_value,
		)

		logger.info("Trading enabled flag updated", enabled=new_value)
		return new_value

	async def get_position_size_for_strategy(self, strategy_id: int, symbol: str) -> float:
		# Placeholder for richer position sizing logic. Maintains existing default behaviour.
		logger.debug(
			"Using default position sizing",
			strategy_id=strategy_id,
			symbol=symbol,
		)
		return 0.1
