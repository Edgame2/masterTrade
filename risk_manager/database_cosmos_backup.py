"""Compatibility shim that delegates to the PostgreSQL implementation."""

from typing import Any, Dict, List, Optional

import structlog

from config import settings
from postgres_database import postgres_database, RiskPostgresDatabase

logger = structlog.get_logger(__name__)


class RiskManagementDatabase(RiskPostgresDatabase):
    """Backwards-compatible alias that now uses PostgreSQL."""

    async def connect(self) -> None:  # pragma: no cover - legacy name
        await self.initialize()

    async def initialize(self) -> None:
        await super().initialize()

    async def close(self) -> None:
        await super().close()

    # Compatibility wrappers -------------------------------------------------
    async def create_stop_loss(self, stop_loss_data: Dict[str, Any]) -> bool:
        # Legacy callers expected a bool; reuse new helper
        await self.create_stop_loss_order(stop_loss_data)
        return True

    async def create_risk_alert(self, alert_data: Dict[str, Any]) -> bool:
        await self.store_risk_alert(alert_data)
        return True

    async def get_risk_metrics_history(self, days: int = 30) -> List[Dict[str, Any]]:
        return await super().get_historical_risk_metrics(days)


# Preserve global instance expected by imports
database = RiskManagementDatabase()