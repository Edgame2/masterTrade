"""
Centralized price prediction access for the strategy service.

This module exposes an async service wrapper that keeps a shared instance of the
BTCUSDC price predictor warm, handles data retrieval, and provides short-lived
caching so other microservices can request 1-hour ahead forecasts via the
strategy API without directly importing ML components.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import pandas as pd
import structlog

from data_utils import fetch_symbol_history
from ml_models.price_predictor import BTCUSDCPredictor, TORCH_AVAILABLE

logger = structlog.get_logger()


@dataclass
class CachedPrediction:
    """Internal cache structure for predictions."""

    data: Dict
    cached_at: datetime

    def is_expired(self, ttl: timedelta) -> bool:
        return datetime.now(timezone.utc) - self.cached_at > ttl


class PricePredictionUnavailableError(RuntimeError):
    """Raised when price predictions cannot be generated."""


class PricePredictionService:
    """Facade around the BTCUSDC price predictor with caching and retries."""

    def __init__(
        self,
        database,
        price_predictor: Optional[BTCUSDCPredictor] = None,
        *,
        supported_symbols: Optional[List[str]] = None,
        cache_ttl_seconds: int = 300,
        training_days: int = 120,
    ) -> None:
        self.database = database
        self.price_predictor = price_predictor or BTCUSDCPredictor()
        self.supported_symbols = supported_symbols or ["BTCUSDC", "BTCUSDT"]
        self.cache_ttl = timedelta(seconds=max(cache_ttl_seconds, 0))
        self.training_days = training_days
        self._prediction_cache: Dict[str, CachedPrediction] = {}
        self._lock = asyncio.Lock()
        self._last_training_result: Optional[Dict] = None

    async def initialize(self) -> None:
        """Train or load model weights so predictions are available."""
        try:
            await self._ensure_model_ready()
        except Exception as exc:
            logger.warning(
                "Price prediction service initialization encountered an issue",
                error=str(exc),
            )

    async def refresh_model(self, *, force: bool = False) -> Optional[Dict]:
        """Force retraining of the underlying model."""
        if not TORCH_AVAILABLE:
            logger.warning("Cannot retrain price predictor because PyTorch is unavailable")
            return None

        async with self._lock:
            if not force and getattr(self.price_predictor, "model", None) is not None:
                return self._last_training_result

            historical_data = await fetch_symbol_history(
                self.database,
                "BTCUSDC",
                days=self.training_days,
            )

            if len(historical_data) < self.price_predictor.sequence_length:
                raise PricePredictionUnavailableError(
                    "Insufficient historical data to train price predictor"
                )

            training_result = await self.price_predictor.train(historical_data)
            self._last_training_result = training_result
            self._prediction_cache.clear()
            logger.info("Price prediction model trained", result=training_result)
            return training_result

    async def get_supported_symbols(self) -> List[str]:
        """Return the list of symbols with prediction support."""
        return list(self.supported_symbols)

    async def get_prediction(
        self,
        symbol: str,
        *,
        force_refresh: bool = False,
    ) -> Optional[Dict]:
        """Return the most recent prediction for the supplied symbol."""
        normalized_symbol = symbol.upper()
        if normalized_symbol not in self.supported_symbols:
            logger.warning(
                "Unsupported symbol requested for price prediction",
                symbol=normalized_symbol,
            )
            return None

        await self._ensure_model_ready()

        if not force_refresh and self.cache_ttl.total_seconds() > 0:
            cached = self._prediction_cache.get(normalized_symbol)
            if cached and not cached.is_expired(self.cache_ttl):
                return cached.data

        async with self._lock:
            if not force_refresh and self.cache_ttl.total_seconds() > 0:
                cached = self._prediction_cache.get(normalized_symbol)
                if cached and not cached.is_expired(self.cache_ttl):
                    return cached.data

            historical_data = await fetch_symbol_history(
                self.database,
                normalized_symbol,
                days=max(90, self.price_predictor.sequence_length // 2),
            )

            if len(historical_data) < self.price_predictor.sequence_length:
                logger.warning(
                    "Not enough data for price prediction",
                    symbol=normalized_symbol,
                    rows=len(historical_data),
                )
                return None

            prediction = await self.price_predictor.predict(
                historical_data,
                return_confidence=True,
            )

            if not isinstance(prediction, dict):
                logger.warning(
                    "Unexpected prediction result type",
                    result_type=type(prediction).__name__,
                )
                return None

            enriched_prediction = {
                **prediction,
                "symbol": normalized_symbol,
                "horizon": f"{self.price_predictor.prediction_horizon}h",
                "generated_at": datetime.now(timezone.utc),
                "training_result": self._last_training_result,
            }

            if self.cache_ttl.total_seconds() > 0:
                self._prediction_cache[normalized_symbol] = CachedPrediction(
                    data=enriched_prediction,
                    cached_at=enriched_prediction["generated_at"],
                )

            logger.info(
                "Generated price prediction",
                symbol=normalized_symbol,
                predicted_change=enriched_prediction.get("predicted_change_pct"),
            )

            return enriched_prediction

    async def invalidate_cache(self, symbol: Optional[str] = None) -> None:
        """Invalidate cached predictions for a symbol or all symbols."""
        if symbol is None:
            self._prediction_cache.clear()
        else:
            self._prediction_cache.pop(symbol.upper(), None)

    async def _ensure_model_ready(self) -> None:
        """Ensure the underlying model is loaded or trained."""
        if getattr(self.price_predictor, "model", None) is not None:
            return

        if not TORCH_AVAILABLE:
            logger.warning("Price predictor running in mock mode (PyTorch unavailable)")
            return

        await self.refresh_model(force=True)
