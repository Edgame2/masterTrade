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
