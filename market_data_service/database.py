"""PostgreSQL-backed persistence layer for the Market Data service."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Union

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
                ON market_data ((data->>'symbol'), (data->>'timestamp'))
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
                ON trades_stream ((data->>'symbol'), (data->>'timestamp'))
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
                ON order_book ((data->>'symbol'), (data->>'timestamp'))
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
                ON sentiment_data ((data->>'source'), (data->>'timestamp'))
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_sentiment_type_ts
                ON sentiment_data ((data->>'type'), (data->>'timestamp'))
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
                ON indicator_results ((data->>'configuration_id'), (data->>'timestamp'))
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_indicator_results_symbol_ts
                ON indicator_results ((data->>'symbol'), (data->>'timestamp'))
            """,
            # On-chain data tables
            """
            CREATE TABLE IF NOT EXISTS whale_transactions (
                id TEXT PRIMARY KEY,
                partition_key TEXT NOT NULL,
                data JSONB NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                ttl_seconds INTEGER
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_whale_tx_symbol_ts
                ON whale_transactions ((data->>'symbol'), (data->>'timestamp'))
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_whale_tx_hash
                ON whale_transactions ((data->>'tx_hash'))
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_whale_tx_from
                ON whale_transactions ((data->>'from_address'))
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_whale_tx_to
                ON whale_transactions ((data->>'to_address'))
            """,
            """
            CREATE TABLE IF NOT EXISTS onchain_metrics (
                id TEXT PRIMARY KEY,
                partition_key TEXT NOT NULL,
                data JSONB NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                ttl_seconds INTEGER
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_onchain_metrics_symbol_ts
                ON onchain_metrics ((data->>'symbol'), (data->>'timestamp'))
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_onchain_metrics_name
                ON onchain_metrics ((data->>'metric_name'))
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_onchain_metrics_category
                ON onchain_metrics ((data->>'metric_category'))
            """,
            """
            CREATE TABLE IF NOT EXISTS wallet_labels (
                id TEXT PRIMARY KEY,
                partition_key TEXT NOT NULL,
                data JSONB NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_wallet_labels_address
                ON wallet_labels ((data->>'address'))
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_wallet_labels_category
                ON wallet_labels ((data->>'category'))
            """,
            """
            CREATE TABLE IF NOT EXISTS wallet_clusters (
                id TEXT PRIMARY KEY,
                partition_key TEXT NOT NULL,
                data JSONB NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_wallet_clusters_address
                ON wallet_clusters USING gin ((data->'addresses'))
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_wallet_clusters_category
                ON wallet_clusters ((data->>'category'))
            """,
            """
            CREATE TABLE IF NOT EXISTS collector_health (
                id TEXT PRIMARY KEY,
                partition_key TEXT NOT NULL,
                data JSONB NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_collector_health_name_ts
                ON collector_health ((data->>'collector_name'), created_at DESC)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_collector_health_status
                ON collector_health ((data->>'status'))
            """,
            # Social sentiment tables
            """
            CREATE TABLE IF NOT EXISTS social_sentiment (
                id TEXT PRIMARY KEY,
                partition_key TEXT NOT NULL,
                data JSONB NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                ttl_seconds INTEGER
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_social_sentiment_symbol_ts
                ON social_sentiment ((data->>'symbol'), (data->>'timestamp'))
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_social_sentiment_source
                ON social_sentiment ((data->>'source'))
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_social_sentiment_category
                ON social_sentiment ((data->>'sentiment_category'))
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_social_sentiment_influencer
                ON social_sentiment ((data->>'is_influencer'))
            """,
            """
            CREATE TABLE IF NOT EXISTS social_metrics_aggregated (
                id TEXT PRIMARY KEY,
                partition_key TEXT NOT NULL,
                data JSONB NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                ttl_seconds INTEGER
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_social_metrics_agg_symbol_ts
                ON social_metrics_aggregated ((data->>'symbol'), (data->>'timestamp'))
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_social_metrics_agg_source
                ON social_metrics_aggregated ((data->>'source'))
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_social_metrics_agg_altrank
                ON social_metrics_aggregated ((data->>'altrank'))
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
        result = []
        for row in rows:
            data = row["data"]
            # Parse JSON string if necessary
            if isinstance(data, str):
                data = json.loads(data)
            result.append(data)
        return result

    async def _fetch_one_data(self, query: str, *params: Any) -> Optional[Dict[str, Any]]:
        row = await self._postgres.fetchrow(query, *params)
        if not row:
            return None
        data = row["data"]
        # Parse JSON string if necessary
        if isinstance(data, str):
            data = json.loads(data)
        return data

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

    async def upsert_market_data_batch(self, data_list: Iterable[Union[MarketData, Dict[str, Any]]]) -> None:
        """Insert batch of market data - accepts both MarketData objects and dicts"""
        for record in data_list:
            if isinstance(record, dict):
                # Convert dict to MarketData object
                try:
                    # Handle timestamp conversion
                    timestamp = record.get('timestamp')
                    if isinstance(timestamp, str):
                        timestamp = datetime.fromisoformat(timestamp.rstrip('Z'))
                    elif not isinstance(timestamp, datetime):
                        raise ValueError(f"Invalid timestamp type: {type(timestamp)}")
                    
                    market_data = MarketData(
                        symbol=record['symbol'],
                        timestamp=timestamp,
                        open_price=float(record.get('open_price', 0)),
                        high_price=float(record.get('high_price', 0)),
                        low_price=float(record.get('low_price', 0)),
                        close_price=float(record.get('close_price', 0)),
                        volume=float(record.get('volume', 0)),
                        quote_volume=float(record.get('quote_asset_volume', record.get('quote_volume', 0))),
                        trades_count=int(record.get('number_of_trades', record.get('trades_count', 0))),
                        interval=record.get('interval', '1m')
                    )
                    await self.insert_market_data(market_data)
                except Exception as e:
                    logger.error(f"Error converting dict to MarketData: {e}", record=record)
                    continue
            else:
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
    # NOTE: Social sentiment methods (store_social_sentiment, store_social_metrics_aggregated,
    # get_social_sentiment, get_social_metrics_aggregated, get_trending_topics, 
    # get_social_sentiment_summary) are implemented below in the "Social Sentiment Data Methods" 
    # section (around line 2040+)
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # On-chain data methods
    # ------------------------------------------------------------------

    async def store_whale_transaction(self, tx_data: Dict[str, Any]) -> bool:
        """
        Store whale transaction data
        
        Args:
            tx_data: Transaction data dict containing tx_hash, symbol, amount, etc.
            
        Returns:
            True if successful, False otherwise
        """
        try:
            tx_id = tx_data.get("tx_hash", "")
            if not tx_id:
                logger.error("Cannot store whale transaction without tx_hash")
                return False
                
            symbol = tx_data.get("symbol", "UNKNOWN")
            document = serialize_datetime_fields(tx_data)
            payload = json.dumps(document)
            
            await self._postgres.execute(
                """
                INSERT INTO whale_transactions (id, partition_key, data, created_at)
                VALUES ($1, $2, $3::jsonb, NOW())
                ON CONFLICT (id)
                DO UPDATE SET data = EXCLUDED.data
                """,
                tx_id,
                symbol,
                payload,
            )
            
            logger.debug(
                "Stored whale transaction",
                tx_hash=tx_id,
                symbol=symbol,
                amount=tx_data.get("amount")
            )
            return True
            
        except Exception as e:
            logger.error("Error storing whale transaction", error=str(e))
            return False

    async def store_onchain_metrics(self, metrics: List[Dict[str, Any]]) -> bool:
        """
        Store on-chain metrics data
        
        Args:
            metrics: List of metric dicts containing metric_name, symbol, value, etc.
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if not metrics:
                return True
                
            for metric_data in metrics:
                metric_id = f"{metric_data['symbol']}_{metric_data['metric_name']}_{int(metric_data['timestamp'].timestamp())}"
                partition_key = metric_data['symbol']
                
                document = serialize_datetime_fields(metric_data)
                payload = json.dumps(document)
                
                await self._postgres.execute(
                    """
                    INSERT INTO onchain_metrics (id, partition_key, data, created_at, updated_at)
                    VALUES ($1, $2, $3::jsonb, NOW(), NOW())
                    ON CONFLICT (id)
                    DO UPDATE SET data = EXCLUDED.data, updated_at = NOW()
                    """,
                    metric_id,
                    partition_key,
                    payload,
                )
                
            logger.debug(
                "Stored on-chain metrics",
                count=len(metrics)
            )
            return True
            
        except Exception as e:
            logger.error("Error storing on-chain metrics", error=str(e))
            return False

    async def store_defi_protocol_metrics(self, metrics: Dict[str, Any]) -> bool:
        """
        Store DeFi protocol metrics (TVL, volume, fees, etc.)
        
        Args:
            metrics: Dictionary containing protocol metrics
                Required fields: protocol, category, timestamp
                Optional: tvl_usd, volume_24h_usd, fees_24h_usd, etc.
            
        Returns:
            True if successful, False otherwise
        """
        try:
            protocol = metrics.get("protocol")
            timestamp = metrics.get("timestamp")
            
            if not protocol or not timestamp:
                logger.error("Missing required fields for DeFi metrics")
                return False
                
            # Parse timestamp if string
            if isinstance(timestamp, str):
                from datetime import datetime
                timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                
            metric_id = f"defi_{protocol}_{int(timestamp.timestamp())}"
            partition_key = metrics.get("category", "defi")
            
            document = serialize_datetime_fields(metrics)
            payload = json.dumps(document)
            
            await self._postgres.execute(
                """
                INSERT INTO defi_protocol_metrics (id, partition_key, data, created_at, updated_at)
                VALUES ($1, $2, $3::jsonb, NOW(), NOW())
                ON CONFLICT (id)
                DO UPDATE SET data = EXCLUDED.data, updated_at = NOW()
                """,
                metric_id,
                partition_key,
                payload,
            )
            
            logger.debug(
                "Stored DeFi protocol metrics",
                protocol=protocol,
                tvl_usd=metrics.get("tvl_usd", 0)
            )
            return True
            
        except Exception as e:
            logger.error("Error storing DeFi protocol metrics", error=str(e), protocol=metrics.get("protocol"))
            return False

    async def get_defi_protocol_metrics(
        self, 
        protocol: Optional[str] = None,
        category: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Retrieve DeFi protocol metrics
        
        Args:
            protocol: Optional protocol name filter
            category: Optional category filter (dex, lending, etc.)
            start_time: Optional start time filter
            end_time: Optional end time filter
            limit: Maximum number of results
            
        Returns:
            List of DeFi metrics dictionaries
        """
        try:
            conditions = []
            params = []
            param_count = 1
            
            if protocol:
                conditions.append(f"data->>'protocol' = ${param_count}")
                params.append(protocol)
                param_count += 1
                
            if category:
                conditions.append(f"partition_key = ${param_count}")
                params.append(category)
                param_count += 1
                
            if start_time:
                conditions.append(f"created_at >= ${param_count}")
                params.append(start_time)
                param_count += 1
                
            if end_time:
                conditions.append(f"created_at <= ${param_count}")
                params.append(end_time)
                param_count += 1
                
            where_clause = " AND ".join(conditions) if conditions else "TRUE"
            
            query = f"""
                SELECT data
                FROM defi_protocol_metrics
                WHERE {where_clause}
                ORDER BY created_at DESC
                LIMIT ${param_count}
            """
            params.append(limit)
            
            rows = await self._postgres.fetch(query, *params)
            
            return [dict(row['data']) for row in rows]
            
        except Exception as e:
            logger.error("Error fetching DeFi protocol metrics", error=str(e))
            return []

    async def store_wallet_label(self, address: str, label: str, category: str, metadata: Dict = None) -> bool:
        """
        Store wallet label/categorization
        
        Args:
            address: Wallet address
            label: Wallet label/name
            category: Category (e.g., 'exchange', 'whale', 'smart_money')
            metadata: Optional additional metadata
            
        Returns:
            True if successful, False otherwise
        """
        try:
            wallet_data = {
                "address": address.lower(),
                "label": label,
                "category": category,
                "metadata": metadata or {},
                "updated_at": _utc_now_iso()
            }
            
            payload = json.dumps(wallet_data)
            
            await self._postgres.execute(
                """
                INSERT INTO wallet_labels (id, partition_key, data, created_at, updated_at)
                VALUES ($1, $2, $3::jsonb, NOW(), NOW())
                ON CONFLICT (id)
                DO UPDATE SET data = EXCLUDED.data, updated_at = NOW()
                """,
                address.lower(),
                category,
                payload,
            )
            
            logger.debug(
                "Stored wallet label",
                address=address,
                label=label,
                category=category
            )
            return True
            
        except Exception as e:
            logger.error("Error storing wallet label", error=str(e))
            return False

    async def get_whale_transactions(
        self,
        symbol: str = None,
        hours: int = 24,
        min_amount: float = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get recent whale transactions
        
        Args:
            symbol: Filter by symbol (optional)
            hours: Hours of history to retrieve
            min_amount: Minimum transaction amount filter
            limit: Maximum number of results
            
        Returns:
            List of whale transaction dicts
        """
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
            
            if symbol:
                if min_amount:
                    query = """
                        SELECT data
                        FROM whale_transactions
                        WHERE data->>'symbol' = $1
                          AND (data->>'timestamp')::timestamptz >= $2
                          AND (data->>'amount')::float >= $3
                        ORDER BY (data->>'timestamp')::timestamptz DESC
                        LIMIT $4
                    """
                    return await self._fetch_data(query, symbol, cutoff, min_amount, limit)
                else:
                    query = """
                        SELECT data
                        FROM whale_transactions
                        WHERE data->>'symbol' = $1
                          AND (data->>'timestamp')::timestamptz >= $2
                        ORDER BY (data->>'timestamp')::timestamptz DESC
                        LIMIT $3
                    """
                    return await self._fetch_data(query, symbol, cutoff, limit)
            else:
                if min_amount:
                    query = """
                        SELECT data
                        FROM whale_transactions
                        WHERE (data->>'timestamp')::timestamptz >= $1
                          AND (data->>'amount')::float >= $2
                        ORDER BY (data->>'timestamp')::timestamptz DESC
                        LIMIT $3
                    """
                    return await self._fetch_data(query, cutoff, min_amount, limit)
                else:
                    query = """
                        SELECT data
                        FROM whale_transactions
                        WHERE (data->>'timestamp')::timestamptz >= $1
                        ORDER BY (data->>'timestamp')::timestamptz DESC
                        LIMIT $2
                    """
                    return await self._fetch_data(query, cutoff, limit)
                    
        except Exception as e:
            logger.error("Error getting whale transactions", error=str(e))
            return []

    async def get_onchain_metrics(
        self,
        symbol: str,
        metric_name: str = None,
        hours: int = 24,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get on-chain metrics
        
        Args:
            symbol: Symbol to get metrics for
            metric_name: Specific metric name (optional)
            hours: Hours of history to retrieve
            limit: Maximum number of results
            
        Returns:
            List of metric dicts
        """
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
            
            if metric_name:
                query = """
                    SELECT data
                    FROM onchain_metrics
                    WHERE data->>'symbol' = $1
                      AND data->>'metric_name' = $2
                      AND (data->>'timestamp')::timestamptz >= $3
                    ORDER BY (data->>'timestamp')::timestamptz DESC
                    LIMIT $4
                """
                return await self._fetch_data(query, symbol, metric_name, cutoff, limit)
            else:
                query = """
                    SELECT data
                    FROM onchain_metrics
                    WHERE data->>'symbol' = $1
                      AND (data->>'timestamp')::timestamptz >= $2
                    ORDER BY (data->>'timestamp')::timestamptz DESC
                    LIMIT $3
                """
                return await self._fetch_data(query, symbol, cutoff, limit)
                
        except Exception as e:
            logger.error("Error getting on-chain metrics", error=str(e))
            return []

    async def get_wallet_label(self, address: str) -> Optional[Dict[str, Any]]:
        """
        Get wallet label information
        
        Args:
            address: Wallet address
            
        Returns:
            Wallet label dict or None
        """
        return await self._fetch_one_data(
            "SELECT data FROM wallet_labels WHERE id = $1",
            address.lower()
        )

    async def get_wallet_labels_by_category(self, category: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get wallet labels by category
        
        Args:
            category: Category to filter by
            limit: Maximum number of results
            
        Returns:
            List of wallet label dicts
        """
        query = """
            SELECT data
            FROM wallet_labels
            WHERE data->>'category' = $1
            LIMIT $2
        """
        return await self._fetch_data(query, category, limit)

    async def store_wallet_cluster(self, cluster_data: Dict[str, Any]) -> bool:
        """
        Store wallet cluster data.
        
        Args:
            cluster_data: Cluster data dictionary
            
        Returns:
            True if stored successfully
        """
        cluster_id = cluster_data.get("cluster_id")
        if not cluster_id:
            return False
            
        partition_key = f"cluster#{cluster_id[:4]}"
        
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO wallet_clusters (id, partition_key, data, created_at, updated_at)
                VALUES ($1, $2, $3, NOW(), NOW())
                ON CONFLICT (id) DO UPDATE SET
                    data = EXCLUDED.data,
                    updated_at = NOW()
                """,
                cluster_id,
                partition_key,
                json.dumps(cluster_data)
            )
        return True

    async def get_cluster_by_address(self, address: str) -> Optional[Dict[str, Any]]:
        """
        Get cluster containing a specific address.
        
        Args:
            address: Wallet address
            
        Returns:
            Cluster data or None
        """
        query = """
            SELECT data
            FROM wallet_clusters
            WHERE data->'addresses' ? $1
            LIMIT 1
        """
        return await self._fetch_one_data(query, address.lower())

    async def update_cluster_metrics(self, cluster_id: str, transaction_amount: float) -> bool:
        """
        Update cluster metrics with new transaction.
        
        Args:
            cluster_id: Cluster ID
            transaction_amount: Transaction amount in USD
            
        Returns:
            True if updated successfully
        """
        async with self.pool.acquire() as conn:
            result = await conn.fetchrow(
                "SELECT data FROM wallet_clusters WHERE id = $1",
                cluster_id
            )
            
            if not result:
                return False
                
            cluster_data = json.loads(result['data'])
            
            # Update metrics
            cluster_data['transaction_count'] = cluster_data.get('transaction_count', 0) + 1
            cluster_data['total_volume_usd'] = cluster_data.get('total_volume_usd', 0) + transaction_amount
            cluster_data['average_volume_usd'] = (
                cluster_data['total_volume_usd'] / cluster_data['transaction_count']
            )
            cluster_data['last_seen'] = datetime.utcnow().isoformat()
            
            await conn.execute(
                """
                UPDATE wallet_clusters
                SET data = $1, updated_at = NOW()
                WHERE id = $2
                """,
                json.dumps(cluster_data),
                cluster_id
            )
            
        return True

    async def add_address_to_cluster(self, cluster_id: str, address: str) -> bool:
        """
        Add an address to an existing cluster.
        
        Args:
            cluster_id: Cluster ID
            address: Address to add
            
        Returns:
            True if added successfully
        """
        async with self.pool.acquire() as conn:
            result = await conn.fetchrow(
                "SELECT data FROM wallet_clusters WHERE id = $1",
                cluster_id
            )
            
            if not result:
                return False
                
            cluster_data = json.loads(result['data'])
            
            # Add address if not already present
            addresses = set(cluster_data.get('addresses', []))
            if address.lower() not in addresses:
                addresses.add(address.lower())
                cluster_data['addresses'] = list(addresses)
                cluster_data['address_count'] = len(addresses)
                
                await conn.execute(
                    """
                    UPDATE wallet_clusters
                    SET data = $1, updated_at = NOW()
                    WHERE id = $2
                    """,
                    json.dumps(cluster_data),
                    cluster_id
                )
                
        return True

    async def get_all_clusters(self, limit: int = 100, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get all wallet clusters.
        
        Args:
            limit: Maximum number of clusters
            category: Optional category filter
            
        Returns:
            List of cluster data
        """
        if category:
            query = """
                SELECT data
                FROM wallet_clusters
                WHERE data->>'category' = $1
                ORDER BY updated_at DESC
                LIMIT $2
            """
            return await self._fetch_data(query, category, limit)
        else:
            query = """
                SELECT data
                FROM wallet_clusters
                ORDER BY updated_at DESC
                LIMIT $1
            """
            return await self._fetch_data(query, limit)

    async def log_collector_health(
        self,
        collector_name: str,
        status: str,
        error_msg: str = None,
        metadata: Dict = None
    ) -> bool:
        """
        Log collector health status
        
        Args:
            collector_name: Name of the collector
            status: Status (healthy, degraded, failed, circuit_open)
            error_msg: Optional error message
            metadata: Optional additional metadata
            
        Returns:
            True if successful, False otherwise
        """
        try:
            health_id = f"{collector_name}_{int(datetime.now(timezone.utc).timestamp())}"
            
            health_data = {
                "collector_name": collector_name,
                "status": status,
                "error_msg": error_msg,
                "metadata": metadata or {},
                "timestamp": _utc_now_iso()
            }
            
            payload = json.dumps(health_data)
            
            await self._postgres.execute(
                """
                INSERT INTO collector_health (id, partition_key, data, created_at)
                VALUES ($1, $2, $3::jsonb, NOW())
                """,
                health_id,
                collector_name,
                payload,
            )
            
            return True
            
        except Exception as e:
            logger.error("Error logging collector health", error=str(e))
            return False

    async def get_collector_health(
        self,
        collector_name: str = None,
        hours: int = 24,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get collector health history
        
        Args:
            collector_name: Specific collector name (optional, returns all if None)
            hours: Hours of history to retrieve
            limit: Maximum number of results
            
        Returns:
            List of health status dicts
        """
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
            
            if collector_name:
                query = """
                    SELECT data
                    FROM collector_health
                    WHERE data->>'collector_name' = $1
                      AND created_at >= $2
                    ORDER BY created_at DESC
                    LIMIT $3
                """
                return await self._fetch_data(query, collector_name, cutoff, limit)
            else:
                query = """
                    SELECT data
                    FROM collector_health
                    WHERE created_at >= $1
                    ORDER BY created_at DESC
                    LIMIT $2
                """
                return await self._fetch_data(query, cutoff, limit)
                
        except Exception as e:
            logger.error("Error getting collector health", error=str(e))
            return []

    # ========== Social Sentiment Data Methods ==========

    async def store_social_sentiment(self, sentiment_data: Dict[str, Any]) -> bool:
        """
        Store social sentiment data (Twitter, Reddit, etc.)
        
        Args:
            sentiment_data: Sentiment data dict with keys:
                - symbol: Cryptocurrency symbol
                - source: Source platform (twitter, reddit, etc.)
                - text: Original text
                - sentiment_score: Compound sentiment score (-1 to 1)
                - sentiment_category: Category (very_negative, negative, neutral, positive, very_positive)
                - sentiment_positive: Positive score (0 to 1)
                - sentiment_negative: Negative score (0 to 1)
                - sentiment_neutral: Neutral score (0 to 1)
                - timestamp: When the post was created
                - author_id: Author identifier
                - author_username: Author username
                - is_influencer: Boolean indicating if author is an influencer
                - engagement_score: Engagement metric (likes + retweets + comments)
                - like_count: Number of likes
                - retweet_count: Number of retweets/shares
                - reply_count: Number of replies/comments
                - post_id: Unique post identifier
                - metadata: Additional platform-specific data
                
        Returns:
            True if successful, False otherwise
        """
        try:
            sentiment_id = f"{sentiment_data['source']}_{sentiment_data['post_id']}"
            partition_key = f"{sentiment_data['symbol']}_{sentiment_data['source']}"
            
            # Ensure timestamp is ISO format
            timestamp = sentiment_data.get('timestamp')
            if isinstance(timestamp, datetime):
                sentiment_data['timestamp'] = timestamp.isoformat()
            
            payload = json.dumps(sentiment_data, default=str)
            
            # Set TTL to 90 days for social sentiment data
            ttl_seconds = 90 * 24 * 3600
            
            await self._postgres.execute(
                """
                INSERT INTO social_sentiment (id, partition_key, data, created_at, ttl_seconds)
                VALUES ($1, $2, $3::jsonb, NOW(), $4)
                ON CONFLICT (id)
                DO UPDATE SET data = EXCLUDED.data
                """,
                sentiment_id,
                partition_key,
                payload,
                ttl_seconds,
            )
            
            logger.debug(
                "Stored social sentiment",
                symbol=sentiment_data['symbol'],
                source=sentiment_data['source'],
                sentiment=sentiment_data['sentiment_category']
            )
            return True
            
        except Exception as e:
            logger.error("Error storing social sentiment", error=str(e), data=sentiment_data)
            return False

    async def store_social_metrics_aggregated(self, metrics_data: Dict[str, Any]) -> bool:
        """
        Store aggregated social metrics (e.g., from LunarCrush)
        
        Args:
            metrics_data: Metrics data dict with keys:
                - symbol: Cryptocurrency symbol
                - timestamp: Metric timestamp
                - altrank: AltRank score
                - altrank_30d: 30-day AltRank
                - galaxy_score: Galaxy Score
                - volatility: Volatility metric
                - social_volume: Social volume count
                - social_volume_24h: 24h social volume
                - social_dominance: Social dominance percentage
                - social_contributors: Number of unique contributors
                - sentiment_score: Aggregated sentiment (1-5 scale)
                - average_sentiment: Average sentiment score
                - tweets_24h: Tweets in last 24h
                - reddit_posts_24h: Reddit posts in last 24h
                - reddit_comments_24h: Reddit comments in last 24h
                - price: Current price
                - price_btc: Price in BTC
                - volume_24h: Trading volume
                - market_cap: Market capitalization
                - percent_change_24h: 24h price change percentage
                - correlation_rank: Correlation rank
                - source: Data source (lunarcrush, etc.)
                - metadata: Additional metadata
                
        Returns:
            True if successful, False otherwise
        """
        try:
            metrics_id = f"{metrics_data['symbol']}_{metrics_data['source']}_{_utc_now_iso()}"
            partition_key = f"{metrics_data['symbol']}_{metrics_data['source']}"
            
            # Ensure timestamp is ISO format
            timestamp = metrics_data.get('timestamp')
            if isinstance(timestamp, datetime):
                metrics_data['timestamp'] = timestamp.isoformat()
            
            payload = json.dumps(metrics_data, default=str)
            
            # Set TTL to 90 days
            ttl_seconds = 90 * 24 * 3600
            
            await self._postgres.execute(
                """
                INSERT INTO social_metrics_aggregated (id, partition_key, data, created_at, updated_at, ttl_seconds)
                VALUES ($1, $2, $3::jsonb, NOW(), NOW(), $4)
                ON CONFLICT (id)
                DO UPDATE SET data = EXCLUDED.data, updated_at = NOW()
                """,
                metrics_id,
                partition_key,
                payload,
                ttl_seconds,
            )
            
            logger.debug(
                "Stored aggregated social metrics",
                symbol=metrics_data['symbol'],
                source=metrics_data['source'],
                altrank=metrics_data.get('altrank'),
                galaxy_score=metrics_data.get('galaxy_score')
            )
            return True
            
        except Exception as e:
            logger.error("Error storing aggregated social metrics", error=str(e))
            return False

    async def get_social_sentiment(
        self,
        symbol: str = None,
        source: str = None,
        hours: int = 24,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get social sentiment data
        
        Args:
            symbol: Filter by cryptocurrency symbol (optional)
            source: Filter by source platform (twitter, reddit, etc.) (optional)
            hours: Hours of history to retrieve
            limit: Maximum number of results
            
        Returns:
            List of sentiment dicts
        """
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
            
            if symbol and source:
                query = """
                    SELECT data
                    FROM social_sentiment
                    WHERE data->>'symbol' = $1
                      AND data->>'source' = $2
                      AND (data->>'timestamp')::timestamptz >= $3
                    ORDER BY (data->>'timestamp')::timestamptz DESC
                    LIMIT $4
                """
                return await self._fetch_data(query, symbol, source, cutoff, limit)
            elif symbol:
                query = """
                    SELECT data
                    FROM social_sentiment
                    WHERE data->>'symbol' = $1
                      AND (data->>'timestamp')::timestamptz >= $2
                    ORDER BY (data->>'timestamp')::timestamptz DESC
                    LIMIT $3
                """
                return await self._fetch_data(query, symbol, cutoff, limit)
            elif source:
                query = """
                    SELECT data
                    FROM social_sentiment
                    WHERE data->>'source' = $1
                      AND (data->>'timestamp')::timestamptz >= $2
                    ORDER BY (data->>'timestamp')::timestamptz DESC
                    LIMIT $3
                """
                return await self._fetch_data(query, source, cutoff, limit)
            else:
                query = """
                    SELECT data
                    FROM social_sentiment
                    WHERE (data->>'timestamp')::timestamptz >= $1
                    ORDER BY (data->>'timestamp')::timestamptz DESC
                    LIMIT $2
                """
                return await self._fetch_data(query, cutoff, limit)
                
        except Exception as e:
            logger.error("Error getting social sentiment", error=str(e))
            return []

    async def get_social_metrics_aggregated(
        self,
        symbol: str = None,
        hours: int = 24,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get aggregated social metrics
        
        Args:
            symbol: Filter by cryptocurrency symbol (optional)
            hours: Hours of history to retrieve
            limit: Maximum number of results
            
        Returns:
            List of aggregated metrics dicts
        """
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
            
            if symbol:
                query = """
                    SELECT data
                    FROM social_metrics_aggregated
                    WHERE data->>'symbol' = $1
                      AND (data->>'timestamp')::timestamptz >= $2
                    ORDER BY (data->>'timestamp')::timestamptz DESC
                    LIMIT $3
                """
                return await self._fetch_data(query, symbol, cutoff, limit)
            else:
                query = """
                    SELECT data
                    FROM social_metrics_aggregated
                    WHERE (data->>'timestamp')::timestamptz >= $1
                    ORDER BY (data->>'timestamp')::timestamptz DESC
                    LIMIT $2
                """
                return await self._fetch_data(query, cutoff, limit)
                
        except Exception as e:
            logger.error("Error getting aggregated social metrics", error=str(e))
            return []

    async def get_trending_topics(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get trending cryptocurrency topics based on social volume
        
        Args:
            limit: Number of trending topics to return
            
        Returns:
            List of trending topics with metrics
        """
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
            
            query = """
                SELECT 
                    data->>'symbol' as symbol,
                    COUNT(*) as mention_count,
                    AVG((data->>'sentiment_score')::float) as avg_sentiment,
                    SUM((data->>'engagement_score')::int) as total_engagement,
                    COUNT(DISTINCT data->>'author_id') as unique_authors
                FROM social_sentiment
                WHERE (data->>'timestamp')::timestamptz >= $1
                GROUP BY data->>'symbol'
                ORDER BY mention_count DESC, total_engagement DESC
                LIMIT $2
            """
            
            rows = await self._postgres.fetch(query, cutoff, limit)
            
            trending = []
            for row in rows:
                trending.append({
                    "symbol": row["symbol"],
                    "mention_count": row["mention_count"],
                    "avg_sentiment": float(row["avg_sentiment"]) if row["avg_sentiment"] else 0.0,
                    "total_engagement": row["total_engagement"],
                    "unique_authors": row["unique_authors"],
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })
                
            logger.debug("Retrieved trending topics", count=len(trending))
            return trending
            
        except Exception as e:
            logger.error("Error getting trending topics", error=str(e))
            return []

    # ==========================================
    # Exchange Data Collection Methods
    # ==========================================

    async def store_exchange_orderbook(
        self,
        exchange: str,
        symbol: str,
        bids: List[List[str]],
        asks: List[List[str]],
        timestamp: datetime,
        sequence: int = None,
        metadata: Dict = None
    ) -> bool:
        """
        Store order book snapshot from exchange
        
        Args:
            exchange: Exchange name (binance, coinbase, deribit, cme)
            symbol: Trading pair/instrument symbol
            bids: List of [price, size] bid levels
            asks: List of [price, size] ask levels
            timestamp: Order book timestamp
            sequence: Optional sequence number from exchange
            metadata: Optional additional metadata
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Generate unique ID
            orderbook_id = f"{exchange}_{symbol}_{timestamp.isoformat()}"
            
            # Convert lists to JSONB
            bids_json = json.dumps(bids)
            asks_json = json.dumps(asks)
            metadata_json = json.dumps(metadata) if metadata else None
            
            await self._postgres.execute(
                """
                INSERT INTO exchange_orderbooks (
                    id, exchange, symbol, bids, asks, timestamp, sequence, metadata, created_at
                )
                VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, $6, $7, $8::jsonb, NOW())
                ON CONFLICT (id)
                DO UPDATE SET
                    bids = EXCLUDED.bids,
                    asks = EXCLUDED.asks,
                    sequence = EXCLUDED.sequence,
                    metadata = EXCLUDED.metadata
                """,
                orderbook_id, exchange, symbol, bids_json, asks_json, 
                timestamp, sequence, metadata_json
            )
            
            logger.debug(
                "Stored exchange orderbook",
                exchange=exchange,
                symbol=symbol,
                bid_levels=len(bids),
                ask_levels=len(asks)
            )
            return True
            
        except Exception as e:
            logger.error(
                "Error storing exchange orderbook",
                exchange=exchange,
                symbol=symbol,
                error=str(e)
            )
            return False
            
    async def store_large_trade(
        self,
        exchange: str,
        symbol: str,
        side: str,
        price: float,
        size: float,
        value_usd: float,
        timestamp: datetime,
        trade_id: str,
        is_liquidation: bool = False,
        metadata: Dict = None
    ) -> bool:
        """
        Store large trade detection
        
        Args:
            exchange: Exchange name
            symbol: Trading pair/instrument
            side: 'buy' or 'sell'
            price: Trade price
            size: Trade size in base currency
            value_usd: Trade value in USD
            timestamp: Trade timestamp
            trade_id: Exchange trade ID
            is_liquidation: True if forced liquidation
            metadata: Optional additional data
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Generate unique ID
            large_trade_id = f"{exchange}_{symbol}_{trade_id}"
            
            metadata_json = json.dumps(metadata) if metadata else None
            
            await self._postgres.execute(
                """
                INSERT INTO large_trades (
                    id, exchange, symbol, side, price, size, value_usd,
                    timestamp, trade_id, is_liquidation, metadata, created_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11::jsonb, NOW())
                ON CONFLICT (id) DO NOTHING
                """,
                large_trade_id, exchange, symbol, side, price, size, value_usd,
                timestamp, trade_id, is_liquidation, metadata_json
            )
            
            logger.info(
                "Large trade detected",
                exchange=exchange,
                symbol=symbol,
                side=side,
                value_usd=value_usd,
                is_liquidation=is_liquidation
            )
            return True
            
        except Exception as e:
            logger.error(
                "Error storing large trade",
                exchange=exchange,
                symbol=symbol,
                error=str(e)
            )
            return False
            
    async def store_funding_rate(
        self,
        exchange: str,
        symbol: str,
        rate: float,
        timestamp: datetime,
        predicted_rate: float = None,
        next_funding_time: datetime = None,
        metadata: Dict = None
    ) -> bool:
        """
        Store funding rate for perpetual contract
        
        Args:
            exchange: Exchange name
            symbol: Perpetual contract symbol
            rate: Current funding rate (decimal)
            timestamp: Data timestamp
            predicted_rate: Optional predicted next rate
            next_funding_time: Optional next funding time
            metadata: Optional additional data
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Generate unique ID
            funding_id = f"{exchange}_{symbol}_{timestamp.isoformat()}"
            
            metadata_json = json.dumps(metadata) if metadata else None
            
            await self._postgres.execute(
                """
                INSERT INTO funding_rates (
                    id, exchange, symbol, rate, predicted_rate, timestamp,
                    next_funding_time, metadata, created_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, NOW())
                ON CONFLICT (id)
                DO UPDATE SET
                    rate = EXCLUDED.rate,
                    predicted_rate = EXCLUDED.predicted_rate,
                    next_funding_time = EXCLUDED.next_funding_time,
                    metadata = EXCLUDED.metadata
                """,
                funding_id, exchange, symbol, rate, predicted_rate,
                timestamp, next_funding_time, metadata_json
            )
            
            logger.debug(
                "Stored funding rate",
                exchange=exchange,
                symbol=symbol,
                rate=rate
            )
            return True
            
        except Exception as e:
            logger.error(
                "Error storing funding rate",
                exchange=exchange,
                symbol=symbol,
                error=str(e)
            )
            return False
            
    async def store_open_interest(
        self,
        exchange: str,
        symbol: str,
        open_interest: float,
        open_interest_usd: float,
        timestamp: datetime,
        metadata: Dict = None
    ) -> bool:
        """
        Store open interest for derivatives
        
        Args:
            exchange: Exchange name
            symbol: Contract symbol
            open_interest: OI in number of contracts
            open_interest_usd: OI value in USD
            timestamp: Data timestamp
            metadata: Optional additional data
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Generate unique ID
            oi_id = f"{exchange}_{symbol}_{timestamp.isoformat()}"
            
            metadata_json = json.dumps(metadata) if metadata else None
            
            await self._postgres.execute(
                """
                INSERT INTO open_interest (
                    id, exchange, symbol, open_interest, open_interest_usd,
                    timestamp, metadata, created_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, NOW())
                ON CONFLICT (id)
                DO UPDATE SET
                    open_interest = EXCLUDED.open_interest,
                    open_interest_usd = EXCLUDED.open_interest_usd,
                    metadata = EXCLUDED.metadata
                """,
                oi_id, exchange, symbol, open_interest, open_interest_usd,
                timestamp, metadata_json
            )
            
            logger.debug(
                "Stored open interest",
                exchange=exchange,
                symbol=symbol,
                oi_usd=open_interest_usd
            )
            return True
            
        except Exception as e:
            logger.error(
                "Error storing open interest",
                exchange=exchange,
                symbol=symbol,
                error=str(e)
            )
            return False
            
    async def get_large_trades(
        self,
        exchange: str = None,
        symbol: str = None,
        hours: int = 24,
        min_value_usd: float = None,
        only_liquidations: bool = False,
        limit: int = 100
    ) -> List[Dict]:
        """
        Get large trades with optional filters
        
        Args:
            exchange: Filter by exchange (optional)
            symbol: Filter by symbol (optional)
            hours: Hours of history
            min_value_usd: Minimum USD value filter
            only_liquidations: Only return liquidations
            limit: Maximum results
            
        Returns:
            List of large trade dicts
        """
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
            
            # Build query dynamically based on filters
            conditions = ["timestamp >= $1"]
            params = [cutoff]
            param_idx = 2
            
            if exchange:
                conditions.append(f"exchange = ${param_idx}")
                params.append(exchange)
                param_idx += 1
                
            if symbol:
                conditions.append(f"symbol = ${param_idx}")
                params.append(symbol)
                param_idx += 1
                
            if min_value_usd:
                conditions.append(f"value_usd >= ${param_idx}")
                params.append(min_value_usd)
                param_idx += 1
                
            if only_liquidations:
                conditions.append("is_liquidation = TRUE")
                
            where_clause = " AND ".join(conditions)
            params.append(limit)
            
            query = f"""
                SELECT 
                    exchange, symbol, side, price, size, value_usd,
                    timestamp, trade_id, is_liquidation, metadata
                FROM large_trades
                WHERE {where_clause}
                ORDER BY timestamp DESC
                LIMIT ${param_idx}
            """
            
            rows = await self._postgres.fetch(query, *params)
            
            trades = []
            for row in rows:
                trades.append({
                    "exchange": row["exchange"],
                    "symbol": row["symbol"],
                    "side": row["side"],
                    "price": float(row["price"]),
                    "size": float(row["size"]),
                    "value_usd": float(row["value_usd"]),
                    "timestamp": row["timestamp"].isoformat(),
                    "trade_id": row["trade_id"],
                    "is_liquidation": row["is_liquidation"],
                    "metadata": row["metadata"]
                })
                
            return trades
            
        except Exception as e:
            logger.error("Error getting large trades", error=str(e))
            return []
            
    async def get_funding_rates(
        self,
        exchange: str = None,
        symbol: str = None,
        hours: int = 24,
        limit: int = 100
    ) -> List[Dict]:
        """
        Get funding rates with optional filters
        
        Args:
            exchange: Filter by exchange
            symbol: Filter by symbol
            hours: Hours of history
            limit: Maximum results
            
        Returns:
            List of funding rate dicts
        """
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
            
            conditions = ["timestamp >= $1"]
            params = [cutoff]
            param_idx = 2
            
            if exchange:
                conditions.append(f"exchange = ${param_idx}")
                params.append(exchange)
                param_idx += 1
                
            if symbol:
                conditions.append(f"symbol = ${param_idx}")
                params.append(symbol)
                param_idx += 1
                
            where_clause = " AND ".join(conditions)
            params.append(limit)
            
            query = f"""
                SELECT 
                    exchange, symbol, rate, predicted_rate, timestamp,
                    next_funding_time, metadata
                FROM funding_rates
                WHERE {where_clause}
                ORDER BY timestamp DESC
                LIMIT ${param_idx}
            """
            
            rows = await self._postgres.fetch(query, *params)
            
            rates = []
            for row in rows:
                rates.append({
                    "exchange": row["exchange"],
                    "symbol": row["symbol"],
                    "rate": float(row["rate"]),
                    "predicted_rate": float(row["predicted_rate"]) if row["predicted_rate"] else None,
                    "timestamp": row["timestamp"].isoformat(),
                    "next_funding_time": row["next_funding_time"].isoformat() if row["next_funding_time"] else None,
                    "metadata": row["metadata"]
                })
                
            return rates
            
        except Exception as e:
            logger.error("Error getting funding rates", error=str(e))
            return []
            
    async def get_open_interest(
        self,
        exchange: str = None,
        symbol: str = None,
        hours: int = 24,
        limit: int = 100
    ) -> List[Dict]:
        """
        Get open interest with optional filters
        
        Args:
            exchange: Filter by exchange
            symbol: Filter by symbol
            hours: Hours of history
            limit: Maximum results
            
        Returns:
            List of open interest dicts
        """
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
            
            conditions = ["timestamp >= $1"]
            params = [cutoff]
            param_idx = 2
            
            if exchange:
                conditions.append(f"exchange = ${param_idx}")
                params.append(exchange)
                param_idx += 1
                
            if symbol:
                conditions.append(f"symbol = ${param_idx}")
                params.append(symbol)
                param_idx += 1
                
            where_clause = " AND ".join(conditions)
            params.append(limit)
            
            query = f"""
                SELECT 
                    exchange, symbol, open_interest, open_interest_usd,
                    timestamp, metadata
                FROM open_interest
                WHERE {where_clause}
                ORDER BY timestamp DESC
                LIMIT ${param_idx}
            """
            
            rows = await self._postgres.fetch(query, *params)
            
            oi_data = []
            for row in rows:
                oi_data.append({
                    "exchange": row["exchange"],
                    "symbol": row["symbol"],
                    "open_interest": float(row["open_interest"]),
                    "open_interest_usd": float(row["open_interest_usd"]),
                    "timestamp": row["timestamp"].isoformat(),
                    "metadata": row["metadata"]
                })
                
            return oi_data
            
        except Exception as e:
            logger.error("Error getting open interest", error=str(e))
            return []

    # ==========================================
    # Collector Health Monitoring Methods
    # ==========================================

    @ensure_connection
    async def log_collector_health(
        self, 
        collector_name: str, 
        status: str, 
        error_msg: Optional[str] = None,
        metrics: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Log collector health status to the database.
        
        Args:
            collector_name: Name of the collector (e.g., 'moralis', 'glassnode')
            status: Health status ('healthy', 'degraded', 'failed')
            error_msg: Optional error message if status is not healthy
            metrics: Optional dict of collector-specific metrics
            
        Returns:
            bool: True if logged successfully, False otherwise
        """
        try:
            health_id = f"{collector_name}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
            
            health_data = {
                "collector_name": collector_name,
                "status": status,
                "timestamp": _utc_now_iso(),
                "error_message": error_msg,
                "metrics": metrics or {}
            }
            
            query = """
                INSERT INTO collector_health (id, partition_key, data, created_at)
                VALUES ($1, $2, $3, NOW())
            """
            
            await self._postgres.execute(
                query,
                health_id,
                collector_name,
                _prepare_document(health_data)
            )
            
            logger.debug(
                "Logged collector health",
                collector=collector_name,
                status=status,
                has_error=error_msg is not None
            )
            return True
            
        except Exception as e:
            logger.error(
                "Failed to log collector health",
                collector=collector_name,
                error=str(e)
            )
            return False

    @ensure_connection
    async def get_collector_health(
        self, 
        collector_name: Optional[str] = None,
        limit: int = 100,
        hours_back: int = 24
    ) -> List[Dict[str, Any]]:
        """
        Retrieve collector health records.
        
        Args:
            collector_name: Optional specific collector name to filter by
            limit: Maximum number of records to return
            hours_back: How many hours of history to retrieve
            
        Returns:
            List of health records with collector status information
        """
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)
            
            if collector_name:
                query = """
                    SELECT 
                        id,
                        data->>'collector_name' as collector_name,
                        data->>'status' as status,
                        data->>'timestamp' as timestamp,
                        data->>'error_message' as error_message,
                        data->'metrics' as metrics,
                        created_at
                    FROM collector_health
                    WHERE data->>'collector_name' = $1
                        AND created_at >= $2
                    ORDER BY created_at DESC
                    LIMIT $3
                """
                rows = await self._postgres.fetch(query, collector_name, cutoff, limit)
            else:
                query = """
                    SELECT 
                        id,
                        data->>'collector_name' as collector_name,
                        data->>'status' as status,
                        data->>'timestamp' as timestamp,
                        data->>'error_message' as error_message,
                        data->'metrics' as metrics,
                        created_at
                    FROM collector_health
                    WHERE created_at >= $1
                    ORDER BY created_at DESC
                    LIMIT $2
                """
                rows = await self._postgres.fetch(query, cutoff, limit)
            
            health_records = []
            for row in rows:
                health_records.append({
                    "id": row["id"],
                    "collector_name": row["collector_name"],
                    "status": row["status"],
                    "timestamp": row["timestamp"],
                    "error_message": row["error_message"],
                    "metrics": json.loads(row["metrics"]) if row["metrics"] else {},
                    "created_at": row["created_at"].isoformat() if row["created_at"] else None
                })
            
            logger.debug(
                "Retrieved collector health records",
                collector=collector_name or "all",
                count=len(health_records)
            )
            return health_records
            
        except Exception as e:
            logger.error(
                "Failed to get collector health",
                collector=collector_name,
                error=str(e)
            )
            return []

    @ensure_connection
    async def get_collector_health_summary(self) -> Dict[str, Any]:
        """
        Get a summary of all collector health statuses.
        
        Returns:
            Dictionary with collector names as keys and their latest status info
        """
        try:
            # Get the most recent health record for each collector
            query = """
                WITH latest_health AS (
                    SELECT DISTINCT ON (data->>'collector_name')
                        data->>'collector_name' as collector_name,
                        data->>'status' as status,
                        data->>'timestamp' as timestamp,
                        data->>'error_message' as error_message,
                        created_at
                    FROM collector_health
                    ORDER BY data->>'collector_name', created_at DESC
                )
                SELECT * FROM latest_health
                ORDER BY collector_name
            """
            
            rows = await self._postgres.fetch(query)
            
            summary = {}
            for row in rows:
                collector_name = row["collector_name"]
                summary[collector_name] = {
                    "status": row["status"],
                    "last_check": row["timestamp"],
                    "error_message": row["error_message"],
                    "created_at": row["created_at"].isoformat() if row["created_at"] else None
                }
            
            logger.debug("Retrieved collector health summary", collectors=len(summary))
            return summary
            
        except Exception as e:
            logger.error("Failed to get collector health summary", error=str(e))
            return {}

    @ensure_connection
    async def update_collector_metrics(
        self, 
        collector_name: str, 
        metric_name: str, 
        value: float
    ) -> bool:
        """
        Update a specific metric for a collector by logging it as a health check.
        
        Args:
            collector_name: Name of the collector
            metric_name: Name of the metric (e.g., 'success_rate', 'avg_response_time')
            value: Metric value
            
        Returns:
            bool: True if updated successfully
        """
        try:
            metrics = {metric_name: value}
            return await self.log_collector_health(
                collector_name=collector_name,
                status="healthy",  # Metrics updates assume healthy status
                metrics=metrics
            )
            
        except Exception as e:
            logger.error(
                "Failed to update collector metrics",
                collector=collector_name,
                metric=metric_name,
                error=str(e)
            )
            return False







