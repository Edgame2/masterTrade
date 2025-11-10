"""
Async client for retrieving price predictions from the Strategy Service.

This client provides lightweight caching and graceful error handling so that
services like the order executor and risk manager can easily incorporate
1-hour ahead price forecasts into their decision logic.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import aiohttp
import structlog

logger = structlog.get_logger()


@dataclass
class _CachedPrediction:
    """Internal structure for cached prediction responses."""

    data: Dict[str, Any]
    cached_at: datetime

    def is_expired(self, ttl: timedelta) -> bool:
        return datetime.now(timezone.utc) - self.cached_at > ttl


class PricePredictionClient:
    """Async HTTP client for interacting with the strategy price prediction API."""

    def __init__(
        self,
        base_url: str,
        *,
        service_name: str = "shared_client",
        request_timeout: float = 5.0,
        cache_ttl_seconds: int = 300,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.service_name = service_name
        self._timeout = aiohttp.ClientTimeout(total=request_timeout)
        self._cache_ttl = timedelta(seconds=max(cache_ttl_seconds, 0))
        self._session: Optional[aiohttp.ClientSession] = None
        self._cache: Dict[str, _CachedPrediction] = {}
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Create the underlying HTTP session if it does not exist."""
        if self._session is None:
            self._session = aiohttp.ClientSession(timeout=self._timeout)
            logger.info(
                "Price prediction client session initialized",
                service=self.service_name,
                base_url=self.base_url,
            )

    async def close(self) -> None:
        """Close the HTTP session and clear cached state."""
        if self._session is not None:
            await self._session.close()
            self._session = None
        self._cache.clear()
        logger.info("Price prediction client session closed", service=self.service_name)

    async def get_prediction(
        self,
        symbol: str,
        *,
        force_refresh: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """Retrieve the latest price prediction for the given symbol."""
        await self.initialize()
        if self._session is None:
            return None

        normalized_symbol = symbol.upper()

        # Return cached value when appropriate to reduce API load.
        if not force_refresh and self._cache_ttl.total_seconds() > 0:
            cached = self._cache.get(normalized_symbol)
            if cached and not cached.is_expired(self._cache_ttl):
                return cached.data

        url = f"{self.base_url}/api/v1/predictions/{normalized_symbol}"
        params = {"force_refresh": str(force_refresh).lower()}

        async with self._lock:
            # Re-check cache after waiting for lock to avoid duplicate refreshes.
            if not force_refresh and self._cache_ttl.total_seconds() > 0:
                cached = self._cache.get(normalized_symbol)
                if cached and not cached.is_expired(self._cache_ttl):
                    return cached.data

            try:
                async with self._session.get(url, params=params) as response:
                    if response.status == 200:
                        payload = await response.json()
                        prediction = {
                            **payload,
                            "fetched_at": datetime.now(timezone.utc).isoformat(),
                            "source_service": self.service_name,
                        }
                        if self._cache_ttl.total_seconds() > 0:
                            self._cache[normalized_symbol] = _CachedPrediction(
                                data=prediction,
                                cached_at=datetime.now(timezone.utc),
                            )
                        return prediction

                    logger.warning(
                        "Price prediction request failed",
                        service=self.service_name,
                        symbol=normalized_symbol,
                        status=response.status,
                    )
                    return None
            except asyncio.TimeoutError:
                logger.error(
                    "Price prediction request timed out",
                    service=self.service_name,
                    symbol=normalized_symbol,
                )
                return None
            except aiohttp.ClientError as exc:
                logger.error(
                    "Price prediction HTTP error",
                    service=self.service_name,
                    symbol=normalized_symbol,
                    error=str(exc),
                )
                return None
        return None