"""Order cache and coordination helpers for the Order Executor service."""

from __future__ import annotations

import asyncio
from typing import Dict, List, Optional

import structlog

from models import Order

logger = structlog.get_logger(__name__)


class OrderManager:
    """Maintain an in-memory view of active orders for fast lookups."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._orders: Dict[str, Order] = {}
        self.database = None
        self.exchange_manager = None
        self._initialized = False

    async def initialize(self, database, exchange_manager) -> None:
        """Warm the order cache from the database and retain dependencies."""
        self.database = database
        self.exchange_manager = exchange_manager
        await self.refresh()
        self._initialized = True
        logger.info("Order manager initialized", cached_orders=len(self._orders))

    async def refresh(self) -> None:
        """Refresh the in-memory cache from the database."""
        if self.database is None:
            return
        active_orders = await self.database.get_active_orders()
        async with self._lock:
            self._orders = {str(order.id): order for order in active_orders}
        logger.debug("Order cache refreshed", active=len(self._orders))

    async def update_from_snapshot(self, orders: List[Order]) -> None:
        """Replace the cache using a provided list of orders."""
        async with self._lock:
            self._orders = {str(order.id): order for order in orders}
        logger.debug("Order cache snapshot applied", active=len(self._orders))

    async def track(self, order: Order) -> None:
        """Track a new or updated active order in the cache."""
        async with self._lock:
            self._orders[str(order.id)] = order
        logger.debug("Tracked order", order_id=str(order.id))

    async def discard(self, order_id: str) -> None:
        """Remove an order from the cache when it is no longer active."""
        async with self._lock:
            self._orders.pop(str(order_id), None)
        logger.debug("Discarded order", order_id=str(order_id))

    async def get(self, order_id: str) -> Optional[Order]:
        """Retrieve a tracked order if it exists."""
        async with self._lock:
            return self._orders.get(str(order_id))

    async def snapshot(self) -> List[Order]:
        """Return a snapshot of the currently tracked orders."""
        async with self._lock:
            return list(self._orders.values())
