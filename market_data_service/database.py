"""PostgreSQL-backed persistence layer for the Market Data service."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional

import structlog

from config import settings
from models import (
    IndicatorCalculationResult,
    IndicatorConfigurationDB,
    MarketData,
    OrderBookData,
    SymbolTracking,
    TradeData,
)
from shared.postgres_manager import PostgresManager, ensure_connection

logger = structlog.get_logger(__name__)


def _datetime_to_iso(value: datetime) -> str:
    if value.tzinfo is None:
        return value.replace(microsecond=0).isoformat() + "Z"
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def serialize_datetime_fields(data: Dict[str, Any]) -> Dict[str, Any]:
    for key, value in list(data.items()):
        if isinstance(value, datetime):
            data[key] = _datetime_to_iso(value)
        elif isinstance(value, dict):
            data[key] = serialize_datetime_fields(dict(value))
        elif isinstance(value, list):
            data[key] = [
                serialize_datetime_fields(item) if isinstance(item, dict)
                else _datetime_to_iso(item) if isinstance(item, datetime)
                else item
                for item in value
            ]
    return data


def _prepare_document(document: Dict[str, Any]) -> str:
    return json.dumps(serialize_datetime_fields(dict(document)))


class Database:
    """PostgreSQL persistence helper for market data, sentiment, symbols, and indicators."""

    def __init__(self) -> None:
        self._postgres = PostgresManager(
            settings.POSTGRES_DSN,
            min_size=settings.POSTGRES_POOL_MIN_SIZE,
            max_size=settings.POSTGRES_POOL_MAX_SIZE,
        )
        self._schema_initialized = False

    async def connect(self) -> None:
        """Establish the PostgreSQL connection pool and ensure schema is ready."""
        await ensure_connection(self._postgres)
        if not self._schema_initialized:
            await self._create_tables()
            await self._initialize_default_symbols()
            self._schema_initialized = True
            logger.info("PostgreSQL schema ready for market data service")

    async def disconnect(self) -> None:
        """Close the PostgreSQL connection pool."""
        await self._postgres.close()

    async def _create_tables(self) -> None:
        """Create required tables and indexes if they do not already exist."""
        statements: List[str] = [
            """
            CREATE TABLE IF NOT EXISTS market_data (
                id TEXT PRIMARY KEY,
                partition_key TEXT NOT NULL,
                data JSONB NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                ttl_seconds INTEGER
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_market_data_symbol_ts
                ON market_data ((data->>'symbol'), ((data->>'timestamp')::timestamptz))
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_market_data_interval
                ON market_data ((data->>'interval'))
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_market_data_asset_type
                ON market_data ((data->>'asset_type'))
            """,
            """
            CREATE TABLE IF NOT EXISTS trades_stream (
                id TEXT PRIMARY KEY,
                partition_key TEXT NOT NULL,
                data JSONB NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                ttl_seconds INTEGER
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_trades_stream_symbol_ts
                ON trades_stream ((data->>'symbol'), ((data->>'timestamp')::timestamptz))
            """,
            """
            CREATE TABLE IF NOT EXISTS order_book (
                id TEXT PRIMARY KEY,
                partition_key TEXT NOT NULL,
                data JSONB NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                ttl_seconds INTEGER
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_order_book_symbol_ts
                ON order_book ((data->>'symbol'), ((data->>'timestamp')::timestamptz))
            """,
            """
            CREATE TABLE IF NOT EXISTS sentiment_data (
                id TEXT PRIMARY KEY,
                partition_key TEXT,
                data JSONB NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                ttl_seconds INTEGER
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_sentiment_source_ts
                ON sentiment_data ((data->>'source'), ((data->>'timestamp')::timestamptz))
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_sentiment_type_ts
                ON sentiment_data ((data->>'type'), ((data->>'timestamp')::timestamptz))
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_sentiment_symbol
                ON sentiment_data ((data->>'symbol'))
            """,
            """
            CREATE TABLE IF NOT EXISTS symbols (
                id TEXT PRIMARY KEY,
                partition_key TEXT NOT NULL,
                data JSONB NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS symbol_tracking (
                id TEXT PRIMARY KEY,
                partition_key TEXT NOT NULL,
                data JSONB NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_symbol_tracking_asset_type
                ON symbol_tracking ((data->>'asset_type'))
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_symbol_tracking_exchange
                ON symbol_tracking ((data->>'exchange'))
            """,
            """
            CREATE TABLE IF NOT EXISTS indicator_configurations (
                id TEXT PRIMARY KEY,
                partition_key TEXT NOT NULL,
                data JSONB NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_indicator_config_strategy
                ON indicator_configurations ((data->>'strategy_id'))
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_indicator_config_active
                ON indicator_configurations ((data->>'active'))
            """,
            """
            CREATE TABLE IF NOT EXISTS indicator_results (
                id TEXT PRIMARY KEY,
                partition_key TEXT NOT NULL,
                data JSONB NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_indicator_results_config_ts
                ON indicator_results ((data->>'configuration_id'), ((data->>'timestamp')::timestamptz))
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_indicator_results_symbol_ts
                ON indicator_results ((data->>'symbol'), ((data->>'timestamp')::timestamptz))
            """,
        ]

        async with self._postgres.transaction() as conn:
            for statement in statements:
                await conn.execute(statement)

    async def _initialize_default_symbols(self) -> None:
        """Ensure a minimal set of symbols exist for downstream services."""
        default_symbols = [
            {
                "id": "BTCUSDC",
                "symbol": "BTCUSDC",
                "base_asset": "BTC",
                "quote_asset": "USDC",
                "is_active": True,
                "min_qty": 0.00001,
                "max_qty": 999999999,
                "step_size": 0.00001,
                "tick_size": 0.01,
                "created_at": _utc_now_iso(),
            },
            {
                "id": "ETHUSDC",
                "symbol": "ETHUSDC",
                "base_asset": "ETH",
                "quote_asset": "USDC",
                "is_active": True,
                "min_qty": 0.0001,
                "max_qty": 999999999,
                "step_size": 0.0001,
                "tick_size": 0.01,
                "created_at": _utc_now_iso(),
            },
        ]
        insert_query = """
            INSERT INTO symbols (id, partition_key, data, created_at, updated_at)
            VALUES ($1, $2, $3::jsonb, NOW(), NOW())
            ON CONFLICT (id) DO NOTHING
        """
        async with self._postgres.transaction() as conn:
            for document in default_symbols:
                payload = _prepare_document(document)
                await conn.execute(insert_query, document["id"], document["base_asset"], payload)

    async def _fetch_data(self, query: str, *params: Any) -> List[Dict[str, Any]]:
        rows = await self._postgres.fetch(query, *params)
        return [row["data"] for row in rows]

    async def _fetch_one_data(self, query: str, *params: Any) -> Optional[Dict[str, Any]]:
        row = await self._postgres.fetchrow(query, *params)
        return row["data"] if row else None

    async def _upsert_document(
        self,
        table: str,
        record_id: str,
        partition_key: str,
        document: Dict[str, Any],
        ttl_seconds: Optional[int] = None,
    ) -> None:
        document = dict(document)
        document["id"] = record_id
        payload = _prepare_document(document)
        query = f"""
            INSERT INTO {table} (id, partition_key, data, created_at, updated_at, ttl_seconds)
            VALUES ($1, $2, $3::jsonb, NOW(), NOW(), $4)
            ON CONFLICT (id)
            DO UPDATE SET data = EXCLUDED.data,
                          updated_at = NOW(),
                          ttl_seconds = EXCLUDED.ttl_seconds
        """
        await self._postgres.execute(query, record_id, partition_key, payload, ttl_seconds)

    # ------------------------------------------------------------------
    # Symbol metadata
    # ------------------------------------------------------------------

    async def get_symbol_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        return await self._fetch_one_data("SELECT data FROM symbols WHERE id = $1", symbol)

    # ------------------------------------------------------------------
    # Market data ingestion
    # ------------------------------------------------------------------

    async def insert_market_data(self, data: MarketData) -> None:
        document = {
            "id": f"{data.symbol}_{data.interval}_{int(data.timestamp.timestamp())}",
            "symbol": data.symbol,
            "timestamp": _datetime_to_iso(data.timestamp),
            "open_price": data.open_price,
            "high_price": data.high_price,
            "low_price": data.low_price,
            "close_price": data.close_price,
            "volume": data.volume,
            "quote_volume": data.quote_volume,
            "trades_count": data.trades_count,
            "interval": data.interval,
            "asset_type": getattr(data, "asset_type", "crypto"),
            "created_at": _utc_now_iso(),
        }
        ttl_seconds = 30 * 24 * 60 * 60  # 30 days
        await self._upsert_document("market_data", document["id"], data.symbol, document, ttl_seconds)

    async def upsert_market_data(self, data: MarketData) -> None:
        await self.insert_market_data(data)

    async def upsert_market_data_batch(self, data_list: Iterable[MarketData]) -> None:
        for record in data_list:
            await self.insert_market_data(record)

    async def insert_trade_data(self, data: TradeData) -> None:
        document = {
            "id": f"{data.symbol}_{int(data.timestamp.timestamp() * 1_000_000)}",
            "symbol": data.symbol,
            "timestamp": _datetime_to_iso(data.timestamp),
            "price": data.price,
            "quantity": data.quantity,
            "is_buyer_maker": data.is_buyer_maker,
            "created_at": _utc_now_iso(),
        }
        ttl_seconds = 7 * 24 * 60 * 60
        await self._upsert_document("trades_stream", document["id"], data.symbol, document, ttl_seconds)

    async def insert_orderbook_data(self, data: OrderBookData) -> None:
        document = {
            "id": f"{data.symbol}_{int(data.timestamp.timestamp() * 1000)}",
            "symbol": data.symbol,
            "timestamp": _datetime_to_iso(data.timestamp),
            "bids": data.bids,
            "asks": data.asks,
            "created_at": _utc_now_iso(),
        }
        ttl_seconds = 60 * 60  # 1 hour
        await self._upsert_document("order_book", document["id"], data.symbol, document, ttl_seconds)

    async def get_latest_market_data(self, symbol: str, limit: int = 100) -> List[Dict[str, Any]]:
        query = """
            SELECT data
            FROM market_data
            WHERE data->>'symbol' = $1
            ORDER BY (data->>'timestamp')::timestamptz DESC
            LIMIT $2
        """
        return await self._fetch_data(query, symbol, limit)

    async def get_market_data_for_analysis(
        self,
        symbol: str,
        interval: str = "1m",
        hours_back: int = 24,
    ) -> List[Dict[str, Any]]:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)
        query = """
            SELECT data
            FROM market_data
            WHERE data->>'symbol' = $1
              AND data->>'interval' = $2
              AND (data->>'timestamp')::timestamptz >= $3
            ORDER BY (data->>'timestamp')::timestamptz ASC
        """
        return await self._fetch_data(query, symbol, interval, cutoff)

    # ------------------------------------------------------------------
    # Sentiment data
    # ------------------------------------------------------------------

    async def upsert_sentiment_data(self, sentiment_data: Dict[str, Any]) -> Dict[str, Any]:
        document = dict(sentiment_data)
        sentiment_id = document.get("id") or f"sentiment_{int(datetime.now(timezone.utc).timestamp() * 1000)}"
        document["id"] = sentiment_id
        document.setdefault("timestamp", _utc_now_iso())
        document["updated_at"] = _utc_now_iso()
        ttl_seconds = 30 * 24 * 60 * 60
        await self._upsert_document(
            "sentiment_data",
            sentiment_id,
            document.get("source", "global"),
            document,
            ttl_seconds,
        )
        logger.info(
            "Sentiment data upserted",
            sentiment_id=sentiment_id,
            source=document.get("source"),
            sentiment_type=document.get("type"),
        )
        return document

    async def upsert_sentiment_data_batch(self, sentiment_batch: List[Dict[str, Any]]) -> int:
        success_count = 0
        for entry in sentiment_batch:
            try:
                await self.upsert_sentiment_data(entry)
                success_count += 1
            except Exception as error:
                logger.error(
                    "Error upserting sentiment data",
                    sentiment_id=entry.get("id"),
                    error=str(error),
                )
        return success_count

    async def get_sentiment_data(
        self,
        source: Optional[str] = None,
        sentiment_type: Optional[str] = None,
        symbol: Optional[str] = None,
        hours_back: int = 24,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)
        conditions: List[str] = ["(data->>'timestamp')::timestamptz >= $1"]
        params: List[Any] = [cutoff]
        param_idx = 2

        if source:
            conditions.append(f"data->>'source' = ${param_idx}")
            params.append(source)
            param_idx += 1
        if sentiment_type:
            conditions.append(f"data->>'type' = ${param_idx}")
            params.append(sentiment_type)
            param_idx += 1
        if symbol:
            conditions.append(f"data->>'symbol' = ${param_idx}")
            params.append(symbol)
            param_idx += 1

        conditions_clause = " AND ".join(conditions)
        params.append(limit)
        query = f"""
            SELECT data
            FROM sentiment_data
            WHERE {conditions_clause}
            ORDER BY (data->>'timestamp')::timestamptz DESC
            LIMIT ${param_idx}
        """
        return await self._fetch_data(query, *params)

    async def get_latest_sentiment_by_type(self, sentiment_type: str) -> Optional[Dict[str, Any]]:
        records = await self.get_sentiment_data(sentiment_type=sentiment_type, hours_back=24, limit=1)
        return records[0] if records else None

    async def get_sentiment_summary(self, hours_back: int = 24) -> Dict[str, Any]:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)
        rows = await self._postgres.fetch(
            """
            SELECT
                data->>'source' AS source,
                data->>'type' AS type,
                COUNT(*) AS count,
                AVG((data->>'polarity')::double precision) AS avg_polarity,
                MAX((data->>'timestamp')::timestamptz) AS latest_timestamp
            FROM sentiment_data
            WHERE (data->>'timestamp')::timestamptz >= $1
            GROUP BY source, type
            """,
            cutoff,
        )

        summary: Dict[str, Any] = {}
        for row in rows:
            latest_timestamp = row["latest_timestamp"]
            summary[f"{row['source']}_{row['type']}"] = {
                "source": row["source"],
                "type": row["type"],
                "count": row["count"],
                "avg_polarity": float(row["avg_polarity"]) if row["avg_polarity"] is not None else None,
                "latest_timestamp": _datetime_to_iso(latest_timestamp) if isinstance(latest_timestamp, datetime) else None,
            }
        return summary

    # ------------------------------------------------------------------
    # Stock market integration
    # ------------------------------------------------------------------

    async def get_stock_index_data(
        self,
        symbol: Optional[str] = None,
        asset_type: str = "stock_index",
        interval: str = "1d",
        hours_back: int = 24,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)
        conditions = ["data->>'asset_type' = $1", "(data->>'timestamp')::timestamptz >= $2"]
        params: List[Any] = [asset_type, cutoff]
        param_idx = 3

        if symbol:
            conditions.append(f"data->>'symbol' = ${param_idx}")
            params.append(symbol)
            param_idx += 1
        if interval:
            conditions.append(f"data->>'interval' = ${param_idx}")
            params.append(interval)
            param_idx += 1

        params.append(limit)
        query = f"""
            SELECT data
            FROM market_data
            WHERE {' AND '.join(conditions)}
            ORDER BY (data->>'timestamp')::timestamptz DESC
            LIMIT ${param_idx}
        """
        return await self._fetch_data(query, *params)

    async def get_all_current_stock_indices(self) -> List[Dict[str, Any]]:
        return await self.get_stock_index_data(
            asset_type="stock_index_current",
            hours_back=1,
            limit=50,
        )

    async def get_stock_market_summary(self) -> Dict[str, Any]:
        summary: Dict[str, Any] = {
            "timestamp": _utc_now_iso(),
            "indices": {},
            "market_sentiment": "neutral",
        }
        positive_count = 0
        negative_count = 0

        tracked_indices = ["^GSPC", "^IXIC", "^DJI", "^VIX"]
        for symbol in tracked_indices:
            data = await self.get_stock_index_data(
                symbol=symbol,
                asset_type="stock_index_current",
                hours_back=1,
                limit=1,
            )
            if not data:
                continue

            entry = data[0]
            change_percent = float(entry.get("change_percent", 0) or 0.0)
            summary["indices"][symbol] = {
                "current_price": entry.get("current_price"),
                "change": entry.get("change"),
                "change_percent": change_percent,
                "full_name": entry.get("metadata", {}).get("full_name", symbol),
            }

            if change_percent > 0:
                positive_count += 1
            elif change_percent < 0:
                negative_count += 1

        if positive_count > negative_count:
            summary["market_sentiment"] = "bullish"
        elif negative_count > positive_count:
            summary["market_sentiment"] = "bearish"

        summary["sentiment_details"] = {
            "positive_indices": positive_count,
            "negative_indices": negative_count,
            "total_indices": len(tracked_indices),
        }
        return summary

    async def get_market_correlation_indicators(self) -> Dict[str, Any]:
        vix_data = await self.get_stock_index_data(
            symbol="^VIX",
            asset_type="stock_index_current",
            hours_back=24,
            limit=24,
        )
        sp500_data = await self.get_stock_index_data(
            symbol="^GSPC",
            asset_type="stock_index_current",
            hours_back=24,
            limit=24,
        )
        crypto_data = await self.get_market_data_for_analysis(
            symbol="BTCUSDC",
            interval="1h",
            hours_back=24,
        )

        indicators: Dict[str, Any] = {
            "timestamp": _utc_now_iso(),
            "vix_level": "unknown",
            "market_volatility": "normal",
            "correlation_strength": "unknown",
            "risk_indicators": {},
        }

        if vix_data:
            latest_vix = float(vix_data[0].get("current_price", 20) or 20.0)
            if latest_vix > 30:
                indicators["vix_level"] = "high_fear"
                indicators["market_volatility"] = "high"
            elif latest_vix > 20:
                indicators["vix_level"] = "elevated"
                indicators["market_volatility"] = "elevated"
            else:
                indicators["vix_level"] = "low_fear"
                indicators["market_volatility"] = "normal"
            indicators["risk_indicators"]["vix_value"] = latest_vix

        if sp500_data:
            indicators["risk_indicators"]["sp500_change_24h"] = float(sp500_data[0].get("change_percent", 0) or 0.0)

        if crypto_data and len(crypto_data) > 1:
            latest_btc = float(crypto_data[-1]["close_price"])
            previous_btc = float(crypto_data[0]["close_price"])
            if previous_btc:
                btc_change = ((latest_btc - previous_btc) / previous_btc) * 100
                indicators["risk_indicators"]["btc_change_24h"] = btc_change

        return indicators

    # ------------------------------------------------------------------
    # Symbol tracking management
    # ------------------------------------------------------------------

    async def add_symbol_tracking(self, symbol_data: SymbolTracking) -> bool:
        document = serialize_datetime_fields(symbol_data.dict())
        document["id"] = symbol_data.symbol
        payload = json.dumps(document)
        row = await self._postgres.fetchrow(
            """
            INSERT INTO symbol_tracking (id, partition_key, data, created_at, updated_at)
            VALUES ($1, $2, $3::jsonb, NOW(), NOW())
            ON CONFLICT (id) DO NOTHING
            RETURNING 1
            """,
            symbol_data.symbol,
            symbol_data.symbol,
            payload,
        )
        if row:
            logger.info("Added symbol to tracking", symbol=symbol_data.symbol)
            return True
        logger.warning("Symbol already present in tracking", symbol=symbol_data.symbol)
        return False

    async def update_symbol_tracking(self, symbol: str, updates: Dict[str, Any]) -> bool:
        existing = await self.get_symbol_tracking_info(symbol)
        if not existing:
            logger.warning("Symbol not found for update", symbol=symbol)
            return False

        existing.update(serialize_datetime_fields(dict(updates)))
        existing["updated_at"] = _utc_now_iso()
        payload = json.dumps(existing)

        await self._postgres.execute(
            """
            UPDATE symbol_tracking
            SET data = $2::jsonb, updated_at = NOW()
            WHERE id = $1
            """,
            symbol,
            payload,
        )
        logger.info("Updated symbol tracking", symbol=symbol, updates=list(updates.keys()))
        return True

    async def ensure_symbol_tracking(self, symbol: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        if await self.get_symbol_tracking_info(symbol):
            return True

        metadata = metadata or {}
        quote_assets = ["USDC", "USDT", "USD", "BTC", "ETH"]
        base_asset = symbol
        quote_asset = "USDC"
        for quote in quote_assets:
            if symbol.endswith(quote):
                base_asset = symbol[:-len(quote)] or symbol
                quote_asset = quote
                break

        symbol_tracking = SymbolTracking(
            id=symbol,
            symbol=symbol,
            base_asset=base_asset,
            quote_asset=quote_asset,
            tracking=True,
            asset_type=metadata.get("asset_type", "crypto"),
            exchange=metadata.get("exchange", "binance"),
            priority=metadata.get("priority", 1),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            notes=metadata.get("notes", ""),
        )
        return await self.add_symbol_tracking(symbol_tracking)

    async def get_tracked_symbols(
        self,
        asset_type: Optional[str] = None,
        exchange: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        conditions = ["COALESCE((data->>'tracking')::boolean, false) = true"]
        params: List[Any] = []
        param_idx = 1

        if asset_type:
            conditions.append(f"data->>'asset_type' = ${param_idx}")
            params.append(asset_type)
            param_idx += 1
        if exchange:
            conditions.append(f"data->>'exchange' = ${param_idx}")
            params.append(exchange)
            param_idx += 1

        where_clause = " AND ".join(conditions) if conditions else "TRUE"
        query = f"""
            SELECT data
            FROM symbol_tracking
            WHERE {where_clause}
            ORDER BY COALESCE((data->>'priority')::int, 999), data->>'symbol'
        """
        return await self._fetch_data(query, *params)

    async def get_all_symbols(self, include_inactive: bool = False) -> List[Dict[str, Any]]:
        if include_inactive:
            query = """
                SELECT data
                FROM symbol_tracking
                ORDER BY COALESCE((data->>'priority')::int, 999), data->>'symbol'
            """
            return await self._fetch_data(query)
        return await self.get_tracked_symbols()

    async def set_symbol_tracking(self, symbol: str, tracking: bool) -> bool:
        return await self.update_symbol_tracking(symbol, {"tracking": tracking})

    async def remove_symbol_tracking(self, symbol: str) -> bool:
        row = await self._postgres.fetchrow(
            "DELETE FROM symbol_tracking WHERE id = $1 RETURNING 1",
            symbol,
        )
        if row:
            logger.info("Removed symbol from tracking", symbol=symbol)
            return True
        logger.warning("Symbol not found for removal", symbol=symbol)
        return False

    async def get_symbol_tracking_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        return await self._fetch_one_data("SELECT data FROM symbol_tracking WHERE id = $1", symbol)

    async def initialize_default_symbols(self) -> bool:
        existing = await self.get_all_symbols(include_inactive=True)
        if existing:
            logger.info("Symbol tracking already initialized", count=len(existing))
            return True

        success_count = 0
        for symbol in settings.DEFAULT_SYMBOLS:
            if symbol.endswith("USDC"):
                base_asset = symbol[:-4]
                quote_asset = "USDC"
            elif symbol.endswith("USDT"):
                base_asset = symbol[:-4]
                quote_asset = "USDT"
            else:
                base_asset = symbol[:-4] if len(symbol) > 4 else symbol
                quote_asset = symbol[-4:] if len(symbol) > 4 else "USDC"

            symbol_tracking = SymbolTracking(
                id=symbol,
                symbol=symbol,
                base_asset=base_asset,
                quote_asset=quote_asset,
                tracking=True,
                asset_type="crypto",
                exchange="binance",
                priority=1,
                notes="Default symbol from initial configuration",
            )
            if await self.add_symbol_tracking(symbol_tracking):
                success_count += 1

        logger.info("Initialized default symbols", inserted=success_count)
        return success_count > 0

    async def initialize_default_stock_indices(self) -> bool:
        existing_indices = await self.get_tracked_symbols(asset_type="stock_index", exchange="global_markets")
        if existing_indices:
            logger.info("Stock indices already initialized", count=len(existing_indices))
            return True

        success_count = 0
        for symbol in settings.STOCK_INDICES:
            region = "us"
            if symbol.startswith("^"):
                region_map = {
                    "^GSPC": "us",
                    "^IXIC": "us",
                    "^DJI": "us",
                    "^RUT": "us",
                    "^VIX": "us",
                    "^TNX": "us",
                    "^FTSE": "uk",
                    "^GDAXI": "germany",
                    "^N225": "japan",
                    "^HSI": "hong_kong",
                    "^BVSP": "brazil",
                }
                region = region_map.get(symbol, "us")
            elif symbol.endswith(".SS"):
                region = "china"

            category = "major"
            if symbol == "^VIX":
                category = "volatility"
            elif symbol == "^TNX":
                category = "bonds"
            elif symbol == "^RUT":
                category = "small_cap"

            full_name_map = {
                "^GSPC": "S&P 500",
                "^IXIC": "NASDAQ Composite",
                "^DJI": "Dow Jones Industrial Average",
                "^RUT": "Russell 2000",
                "^VIX": "CBOE Volatility Index",
                "^TNX": "10-Year Treasury Yield",
                "^FTSE": "FTSE 100",
                "^GDAXI": "DAX",
                "^N225": "Nikkei 225",
                "^HSI": "Hang Seng Index",
                "000001.SS": "Shanghai Composite",
                "^BVSP": "Bovespa",
            }
            full_name = full_name_map.get(symbol, symbol)

            index_tracking = SymbolTracking(
                id=symbol,
                symbol=symbol,
                base_asset=full_name,
                quote_asset=region.upper(),
                tracking=True,
                asset_type="stock_index",
                exchange="global_markets",
                priority=1 if category in ["major", "volatility"] else 2,
                intervals=["1d", "1h"] if category != "bonds" else ["1d"],
                notes=f"Default {category} {region} index from initial configuration",
            )
            if await self.add_symbol_tracking(index_tracking):
                success_count += 1

        logger.info("Initialized default stock indices", inserted=success_count)
        return success_count > 0

    async def get_tracked_stock_indices(
        self,
        region: Optional[str] = None,
        category: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        indices = await self.get_tracked_symbols(asset_type="stock_index", exchange="global_markets")
        if region:
            indices = [idx for idx in indices if region.lower() in idx.get("quote_asset", "").lower()]
        if category:
            indices = [idx for idx in indices if category.lower() in idx.get("notes", "").lower()]
        return indices

    async def get_stock_indices_by_category(self) -> Dict[str, List[str]]:
        all_indices = await self.get_tracked_stock_indices()
        categories: Dict[str, List[str]] = {
            "us_major": [],
            "us_indicators": [],
            "international": [],
            "volatility": [],
            "bonds": [],
        }

        for idx in all_indices:
            symbol = idx["symbol"]
            notes = idx.get("notes", "").lower()
            region = idx.get("quote_asset", "").lower()

            if region == "us":
                if "volatility" in notes:
                    categories["volatility"].append(symbol)
                    categories["us_indicators"].append(symbol)
                elif "bonds" in notes:
                    categories["bonds"].append(symbol)
                    categories["us_indicators"].append(symbol)
                else:
                    categories["us_major"].append(symbol)
            else:
                categories["international"].append(symbol)

        return categories

    async def update_stock_index_metadata(self, symbol: str, metadata: Dict[str, Any]) -> bool:
        existing = await self.get_symbol_tracking_info(symbol)
        if not existing or existing.get("asset_type") != "stock_index":
            return False

        updates: Dict[str, Any] = {}
        if "category" in metadata:
            updates["notes"] = f"{metadata['category']} index - {existing.get('notes', '')}"
        if "region" in metadata:
            updates["quote_asset"] = metadata["region"].upper()
        if "full_name" in metadata:
            updates["base_asset"] = metadata["full_name"]
        if "priority" in metadata:
            updates["priority"] = metadata["priority"]
        if "intervals" in metadata:
            updates["intervals"] = metadata["intervals"]

        if not updates:
            return True
        return await self.update_symbol_tracking(symbol, updates)

    # ------------------------------------------------------------------
    # Indicator configuration management
    # ------------------------------------------------------------------

    async def create_indicator_configuration(self, config: IndicatorConfigurationDB) -> bool:
        document = serialize_datetime_fields(config.dict())
        payload = json.dumps(document)
        row = await self._postgres.fetchrow(
            """
            INSERT INTO indicator_configurations (id, partition_key, data, created_at, updated_at)
            VALUES ($1, $2, $3::jsonb, NOW(), NOW())
            ON CONFLICT (id) DO NOTHING
            RETURNING 1
            """,
            config.id,
            config.strategy_id,
            payload,
        )
        if row:
            logger.info(
                "Created indicator configuration",
                config_id=config.id,
                strategy_id=config.strategy_id,
                indicator_type=config.indicator_type,
            )
            return True
        logger.warning("Indicator configuration already exists", config_id=config.id)
        return False

    async def get_indicator_configuration(self, config_id: str, strategy_id: str) -> Optional[Dict[str, Any]]:
        return await self._fetch_one_data(
            "SELECT data FROM indicator_configurations WHERE id = $1 AND partition_key = $2",
            config_id,
            strategy_id,
        )

    async def get_active_indicator_configurations(self, strategy_id: Optional[str] = None) -> List[Dict[str, Any]]:
        if strategy_id:
            query = """
                SELECT data
                FROM indicator_configurations
                WHERE partition_key = $1
                  AND COALESCE((data->>'active')::boolean, false) = true
                ORDER BY COALESCE((data->>'priority')::int, 999), data->>'created_at'
            """
            return await self._fetch_data(query, strategy_id)

        query = """
            SELECT data
            FROM indicator_configurations
            WHERE COALESCE((data->>'active')::boolean, false) = true
            ORDER BY COALESCE((data->>'priority')::int, 999),
                     data->>'strategy_id',
                     data->>'created_at'
        """
        return await self._fetch_data(query)

    async def get_configurations_by_symbol_interval(self, symbol: str, interval: str) -> List[Dict[str, Any]]:
        query = """
            SELECT data
            FROM indicator_configurations
            WHERE data->>'symbol' = $1
              AND data->>'interval' = $2
              AND COALESCE((data->>'active')::boolean, false) = true
            ORDER BY COALESCE((data->>'priority')::int, 999)
        """
        return await self._fetch_data(query, symbol, interval)

    async def update_indicator_configuration(
        self,
        config_id: str,
        strategy_id: str,
        updates: Dict[str, Any],
    ) -> bool:
        existing = await self.get_indicator_configuration(config_id, strategy_id)
        if not existing:
            return False

        existing.update(serialize_datetime_fields(dict(updates)))
        existing["updated_at"] = _utc_now_iso()
        payload = json.dumps(existing)

        await self._postgres.execute(
            """
            UPDATE indicator_configurations
            SET data = $3::jsonb, updated_at = NOW()
            WHERE id = $1 AND partition_key = $2
            """,
            config_id,
            strategy_id,
            payload,
        )
        logger.info("Updated indicator configuration", config_id=config_id, updates=list(updates.keys()))
        return True

    async def delete_indicator_configuration(self, config_id: str, strategy_id: str) -> bool:
        row = await self._postgres.fetchrow(
            "DELETE FROM indicator_configurations WHERE id = $1 AND partition_key = $2 RETURNING 1",
            config_id,
            strategy_id,
        )
        if row:
            logger.info("Deleted indicator configuration", config_id=config_id)
            return True
        logger.warning("Indicator configuration not found for deletion", config_id=config_id)
        return False

    async def update_calculation_statistics(
        self,
        config_id: str,
        strategy_id: str,
        calculation_time_ms: float,
        success: bool = True,
        error_message: str = "",
    ) -> bool:
        existing = await self.get_indicator_configuration(config_id, strategy_id)
        if not existing:
            return False

        existing["last_calculated"] = _utc_now_iso()
        existing["calculation_count"] = int(existing.get("calculation_count", 0)) + 1

        if success:
            current_avg = float(existing.get("avg_calculation_time_ms", 0.0))
            count = existing["calculation_count"]
            new_avg = ((current_avg * (count - 1)) + calculation_time_ms) / max(count, 1)
            existing["avg_calculation_time_ms"] = new_avg
            existing["last_error"] = ""
        else:
            existing["error_count"] = int(existing.get("error_count", 0)) + 1
            existing["last_error"] = error_message

        return await self.update_indicator_configuration(config_id, strategy_id, existing)

    async def get_configurations_due_for_calculation(self, max_age_seconds: int = 300) -> List[Dict[str, Any]]:
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=max_age_seconds)
        query = """
            SELECT data
            FROM indicator_configurations
            WHERE COALESCE((data->>'active')::boolean, false) = true
              AND COALESCE((data->>'continuous_calculation')::boolean, false) = true
              AND COALESCE((data->>'last_calculated')::timestamptz, '1970-01-01T00:00:00Z'::timestamptz) <= $1
            ORDER BY COALESCE((data->>'priority')::int, 999),
                     data->>'last_calculated'
        """
        return await self._fetch_data(query, cutoff)

    # ------------------------------------------------------------------
    # Indicator results storage
    # ------------------------------------------------------------------

    async def store_indicator_result(self, result: IndicatorCalculationResult) -> bool:
        document = serialize_datetime_fields(result.dict())
        payload = json.dumps(document)
        await self._postgres.execute(
            """
            INSERT INTO indicator_results (id, partition_key, data, created_at)
            VALUES ($1, $2, $3::jsonb, NOW())
            ON CONFLICT (id)
            DO UPDATE SET data = EXCLUDED.data,
                          created_at = NOW()
            """,
            result.id,
            result.symbol,
            payload,
        )
        logger.debug(
            "Stored indicator result",
            result_id=result.id,
            configuration_id=result.configuration_id,
        )
        return True

    async def get_latest_indicator_result(self, configuration_id: str, symbol: str) -> Optional[Dict[str, Any]]:
        query = """
            SELECT data
            FROM indicator_results
            WHERE data->>'configuration_id' = $1
              AND data->>'symbol' = $2
            ORDER BY (data->>'timestamp')::timestamptz DESC
            LIMIT 1
        """
        return await self._fetch_one_data(query, configuration_id, symbol)

    async def get_indicator_results_history(
        self,
        configuration_id: str,
        symbol: str,
        hours_back: int = 24,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)
        query = """
            SELECT data
            FROM indicator_results
            WHERE data->>'configuration_id' = $1
              AND data->>'symbol' = $2
              AND (data->>'timestamp')::timestamptz >= $3
            ORDER BY (data->>'timestamp')::timestamptz DESC
            LIMIT $4
        """
        return await self._fetch_data(query, configuration_id, symbol, cutoff, limit)

    async def cleanup_old_indicator_results(self, days_old: int = 7) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_old)
        rows = await self._postgres.fetch(
            """
            DELETE FROM indicator_results
            WHERE (data->>'timestamp')::timestamptz < $1
            RETURNING 1
            """,
            cutoff,
        )
        deleted = len(rows)
        logger.info("Cleaned up old indicator results", deleted_count=deleted, cutoff_days=days_old)
        return deleted

