"""PostgreSQL-backed minimal persistence for API Gateway Service.

NOTE: The API Gateway should primarily aggregate data via HTTP calls to backend services
(strategy_service, market_data_service, order_executor, risk_manager) rather than direct
database access. This module provides session/cache storage if needed.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import structlog

from config import settings
from shared.postgres_manager import PostgresManager, ensure_connection

logger = structlog.get_logger(__name__)


class Database:
    """Minimal PostgreSQL facade for API Gateway (primarily uses HTTP APIs)."""

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
        logger.info("API Gateway connected to PostgreSQL")

    async def disconnect(self) -> None:
        if not self._connected:
            return
        await self._postgres.close()
        self._connected = False
        logger.info("API Gateway disconnected from PostgreSQL")

    # Dashboard overview should be fetched from backend services via HTTP
    async def get_dashboard_overview(self) -> Dict[str, Any]:
        """
        Placeholder: In production, aggregate from service APIs.
        Returns empty overview for now.
        """
        return {
            "total_strategies": 0,
            "active_strategies": 0,
            "recent_signals": 0,
            "active_orders": 0,
            "recent_trades": 0,
            "portfolio_value": 0.0,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }

    # Similarly for other gateway operations: delegate to service HTTP endpoints
    async def get_portfolio_summary(self) -> Dict[str, Any]:
        """Placeholder: fetch from risk_manager/order_executor APIs."""
        return {"positions": [], "total_value": 0.0}

    async def get_strategies(
        self, limit: int = 100, strategy_type: Optional[str] = None, is_active: Optional[bool] = None
    ) -> List[Dict[str, Any]]:
        """Placeholder: fetch from strategy_service API."""
        return []

    async def get_strategy(self, strategy_id: str) -> Optional[Dict[str, Any]]:
        """Placeholder: fetch from strategy_service API."""
        return None

    async def get_recent_signals(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Placeholder: fetch from strategy_service API."""
        return []

    async def get_active_orders(self) -> List[Dict[str, Any]]:
        """Placeholder: fetch from order_executor API."""
        return []

    async def get_recent_trades(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Placeholder: fetch from order_executor API."""
        return []

    async def get_market_data(self, symbol: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Placeholder: fetch from market_data_service API."""
        return []

    async def get_portfolio_balance(self) -> Dict[str, Any]:
        """Get current portfolio balance from database."""
        if not self._connected:
            await self.connect()
        
        try:
            query = """
                SELECT 
                    asset,
                    free_balance,
                    locked_balance,
                    (free_balance + locked_balance) as total_balance,
                    updated_at
                FROM portfolio_balances
                ORDER BY (free_balance + locked_balance) DESC
            """
            rows = await self._postgres.fetch(query)
            
            balances = []
            total_value = 0.0
            
            for row in rows:
                balance = {
                    "asset": row["asset"],
                    "free": float(row["free_balance"]),
                    "locked": float(row["locked_balance"]),
                    "total": float(row["total_balance"]),
                    "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
                }
                balances.append(balance)
                # For now, assume USDT/USD equivalence for total value
                if row["asset"] in ("USDT", "USD", "USDC", "BUSD"):
                    total_value += float(row["total_balance"])
            
            return {
                "balances": balances,
                "total_value_usd": total_value,
                "last_updated": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as e:
            logger.error("Error fetching portfolio balance", error=str(e))
            # Return empty balance instead of raising
            return {
                "balances": [],
                "total_value_usd": 0.0,
                "last_updated": datetime.now(timezone.utc).isoformat(),
            }

    async def get_all_strategies(self) -> List[Dict[str, Any]]:
        """Get all strategies from database."""
        if not self._connected:
            await self.connect()
        
        try:
            query = """
                SELECT 
                    id,
                    name,
                    type,
                    is_active,
                    status,
                    allocation,
                    created_at,
                    updated_at
                FROM strategies
                ORDER BY created_at DESC
            """
            rows = await self._postgres.fetch(query)
            
            strategies = []
            for row in rows:
                strategy = {
                    "id": str(row["id"]),
                    "name": row["name"],
                    "type": row["type"],
                    "is_active": row["is_active"],
                    "status": row["status"],
                    "allocation": float(row["allocation"]) if row["allocation"] else 0.0,
                    "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                    "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
                }
                strategies.append(strategy)
            
            return strategies
        except Exception as e:
            logger.error("Error fetching strategies", error=str(e))
            return []

    async def get_all_symbols(self, include_inactive: bool = False) -> List[Dict[str, Any]]:
        """Get all trading symbols from database."""
        if not self._connected:
            await self.connect()
        
        try:
            # Query the symbols table which stores data in JSONB format
            if include_inactive:
                query = """
                    SELECT 
                        id,
                        data,
                        created_at,
                        updated_at
                    FROM symbols
                    ORDER BY id
                """
            else:
                query = """
                    SELECT 
                        id,
                        data,
                        created_at,
                        updated_at
                    FROM symbols
                    WHERE (data->>'is_active')::boolean = TRUE
                    ORDER BY id
                """
            
            rows = await self._postgres.fetch(query)
            
            symbols = []
            for row in rows:
                # Extract symbol data from JSONB (parse if string)
                data = row["data"]
                if isinstance(data, str):
                    import json
                    data = json.loads(data)
                
                symbol = {
                    "symbol": row["id"],  # id is the symbol name
                    "exchange": data.get("exchange", "binance"),
                    "is_active": data.get("is_active", True),
                    "base_asset": data.get("base_asset"),
                    "quote_asset": data.get("quote_asset"),
                    "price_precision": data.get("price_precision"),
                    "quantity_precision": data.get("quantity_precision"),
                    "min_notional": float(data["min_notional"]) if data.get("min_notional") else None,
                    "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                    "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
                }
                symbols.append(symbol)
            
            return symbols
        except Exception as e:
            logger.error("Error fetching symbols", error=str(e))
            return []
