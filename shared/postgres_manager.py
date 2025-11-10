"""Async PostgreSQL connection manager shared across services."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Iterable, Optional

import asyncpg
import structlog

logger = structlog.get_logger(__name__)


class PostgresManager:
    """Lightweight wrapper around an asyncpg connection pool."""

    def __init__(
        self,
        dsn: str,
        *,
        min_size: int = 1,
        max_size: int = 10,
        statement_cache_size: int = 0,
        init: Optional[Any] = None,
    ) -> None:
        self._dsn = dsn
        self._min_size = min_size
        self._max_size = max_size
        self._statement_cache_size = statement_cache_size
        self._init = init
        self._pool: Optional[asyncpg.pool.Pool] = None

    async def connect(self) -> None:
        """Create the underlying connection pool if needed."""
        if self._pool is not None:
            return

        logger.info(
            "Initializing PostgreSQL connection pool",
            dsn=self._dsn,
            min_size=self._min_size,
            max_size=self._max_size,
        )

        self._pool = await asyncpg.create_pool(
            dsn=self._dsn,
            min_size=self._min_size,
            max_size=self._max_size,
            init=self._init,
            statement_cache_size=self._statement_cache_size,
        )

    async def close(self) -> None:
        """Dispose the connection pool."""
        if self._pool is None:
            return

        await self._pool.close()
        self._pool = None
        logger.info("Closed PostgreSQL connection pool")

    @property
    def pool(self) -> asyncpg.pool.Pool:
        if self._pool is None:
            raise RuntimeError("PostgresManager not connected; call connect() first")
        return self._pool

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[asyncpg.Connection]:
        """Acquire a connection from the pool."""
        conn = await self.pool.acquire()
        try:
            yield conn
        finally:
            await self.pool.release(conn)

    async def execute(self, query: str, *args: Any) -> str:
        async with self.acquire() as conn:
            return await conn.execute(query, *args)

    async def executemany(self, query: str, args_iter: Iterable[Iterable[Any]]) -> None:
        async with self.acquire() as conn:
            await conn.executemany(query, args_iter)

    async def fetch(self, query: str, *args: Any) -> list[asyncpg.Record]:
        async with self.acquire() as conn:
            return await conn.fetch(query, *args)

    async def fetchrow(self, query: str, *args: Any) -> Optional[asyncpg.Record]:
        async with self.acquire() as conn:
            return await conn.fetchrow(query, *args)

    async def fetchval(self, query: str, *args: Any) -> Any:
        async with self.acquire() as conn:
            return await conn.fetchval(query, *args)

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[asyncpg.Connection]:
        async with self.acquire() as conn:
            async with conn.transaction():
                yield conn


async def ensure_connection(manager: PostgresManager, retries: int = 5, delay: float = 1.0) -> None:
    """Utility to retry connecting to PostgreSQL when startup ordering is uncertain."""

    for attempt in range(1, retries + 1):
        try:
            await manager.connect()
            return
        except Exception as error:  # pragma: no cover - defensive logging path
            logger.warning(
                "PostgreSQL connection attempt failed",
                attempt=attempt,
                retries=retries,
                error=str(error),
            )
            if attempt == retries:
                raise
            await asyncio.sleep(delay)
            delay *= 2  # Exponential backoff to give Postgres time to boot
