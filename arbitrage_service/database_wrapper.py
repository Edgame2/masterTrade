"""
Compatibility shim for Arbitrage Service database

Delegates to PostgreSQL implementation while maintaining API compatibility.
"""

from typing import Any, Dict, List, Optional

import structlog

from postgres_database import ArbitragePostgresDatabase, postgres_database

logger = structlog.get_logger(__name__)


class Database(ArbitragePostgresDatabase):
    """Backwards-compatible database wrapper using PostgreSQL"""

    async def initialize(self) -> None:
        """Alias for connect() for consistency"""
        await self.connect()

    # All methods inherited from ArbitragePostgresDatabase
    pass


# Global database instance
database = Database()
