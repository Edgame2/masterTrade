"""
Shared data utilities for the strategy service.

Provides convenience helpers for fetching historical OHLCV data with a fallback
synthetic generator so components like the automatic pipeline and price
prediction service can reuse the same logic.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, TYPE_CHECKING

import numpy as np
import structlog

logger = structlog.get_logger()

try:  # Optional dependency guard for lightweight test environments
    import pandas as _pd
except ModuleNotFoundError:  # pragma: no cover - dependency resolution
    _pd = None

if TYPE_CHECKING:
    import pandas as pd  # type: ignore
else:
    pd = _pd


def _ensure_pandas() -> None:
    if pd is None:
        raise RuntimeError(
            "pandas is required for strategy_service.data_utils. Install it via "
            "pip install -r strategy_service/requirements.txt before running the "
            "full strategy pipeline."
        )


async def fetch_symbol_history(
    database,
    symbol: str,
    *,
    days: int = 90,
    interval_hours: int = 1,
) -> pd.DataFrame:
    """Fetch OHLCV history for a symbol, falling back to synthetic data."""
    try:
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)

        query = {
            "symbol": symbol,
            "timestamp": {
                "$gte": start_date.isoformat(),
                "$lte": end_date.isoformat(),
            },
        }

        limit = days * int(24 / interval_hours)
        results = await database.query_market_data(query, limit=limit)

        if results:
            _ensure_pandas()
            df = pd.DataFrame(results)
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df = df.sort_values("timestamp")
            columns = ["timestamp", "open", "high", "low", "close", "volume"]
            return df[columns]

        logger.warning(
            "No historical market data found, using synthetic fallback",
            symbol=symbol,
            days=days,
        )
    except Exception as exc:
        logger.warning(
            "Failed to fetch historical market data, using synthetic fallback",
            symbol=symbol,
            days=days,
            error=str(exc),
        )

    return generate_synthetic_data(symbol, days=days, interval_hours=interval_hours)


def generate_synthetic_data(
    symbol: str,
    *,
    days: int,
    interval_hours: int = 1,
) -> pd.DataFrame:
    """Generate synthetic OHLCV data for development environments."""
    _ensure_pandas()
    periods = days * int(24 / interval_hours)
    freq = f"{interval_hours}H"
    dates = pd.date_range(end=datetime.now(timezone.utc), periods=periods, freq=freq)

    base_price = 40000 if "BTC" in symbol else 2000
    trend = np.linspace(0, 0.15, periods)
    noise = np.random.normal(0, 0.015, periods)
    returns = trend + noise
    prices = base_price * (1 + returns).cumprod()

    data = {
        "timestamp": dates,
        "open": prices,
        "high": prices * (1 + np.random.uniform(0, 0.02, periods)),
        "low": prices * (1 - np.random.uniform(0, 0.02, periods)),
        "close": prices * (1 + np.random.uniform(-0.01, 0.01, periods)),
        "volume": np.random.uniform(100, 1000, periods),
    }

    df = pd.DataFrame(data)
    logger.info(
        "Generated synthetic market data",
        symbol=symbol,
        periods=periods,
        interval_hours=interval_hours,
    )
    return df