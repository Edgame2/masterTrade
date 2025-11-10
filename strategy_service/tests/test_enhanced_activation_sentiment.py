import sys
import unittest
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

if "scipy" not in sys.modules:
    import math

    def _euclidean(left, right):
        pairs = zip(left, right)
        return math.sqrt(sum((float(a) - float(b)) ** 2 for a, b in pairs))

    spatial_distance = SimpleNamespace(euclidean=_euclidean)
    spatial_module = SimpleNamespace(distance=spatial_distance)
    sys.modules["scipy"] = SimpleNamespace(spatial=spatial_module)
    sys.modules["scipy.spatial"] = spatial_module
    sys.modules["scipy.spatial.distance"] = spatial_distance

if "sklearn" not in sys.modules:
    class _StandardScaler:
        def fit(self, data):
            return self

        def transform(self, data):
            return data

    preprocessing_module = SimpleNamespace(StandardScaler=_StandardScaler)
    sys.modules["sklearn"] = SimpleNamespace(preprocessing=preprocessing_module)
    sys.modules["sklearn.preprocessing"] = preprocessing_module

if "postgres_database" not in sys.modules:
    class _PlaceholderDatabase:
        pass

    sys.modules["postgres_database"] = SimpleNamespace(Database=_PlaceholderDatabase)

if "config" not in sys.modules:
    class _Settings:
        MAX_ACTIVE_STRATEGIES = 5

    sys.modules["config"] = SimpleNamespace(settings=_Settings())

if "structlog" not in sys.modules:
    class _MockLogger:
        def info(self, *args, **kwargs) -> None:
            pass

        def warning(self, *args, **kwargs) -> None:
            pass

        def error(self, *args, **kwargs) -> None:
            pass

        def bind(self, *args, **kwargs):
            return self

    sys.modules["structlog"] = SimpleNamespace(get_logger=lambda: _MockLogger())

from strategy_service.enhanced_strategy_activation import EnhancedStrategyActivationSystem


class FakeDatabase:
    """Lightweight stub providing sentiment data for activation tests."""

    def __init__(self) -> None:
        self.symbol_data: Dict[str, List[Dict[str, Any]]] = {}
        self.global_data: List[Dict[str, Any]] = []

    async def get_sentiment_entries(
        self,
        symbol: Optional[str] = None,
        sentiment_types: Optional[List[str]] = None,
        hours_back: int = 24,
        limit: int = 60,
    ) -> List[Dict[str, Any]]:
        if symbol:
            entries = list(self.symbol_data.get(symbol.upper(), []))
        elif sentiment_types:
            sentiment_filter = set(sentiment_types)
            entries = [
                entry
                for entry in self.global_data
                if entry.get("sentiment_type") in sentiment_filter
                or not sentiment_filter
            ]
        else:
            entries = []

        if limit is not None and limit < len(entries):
            return entries[:limit]
        return entries


class SentimentAlignmentTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.database = FakeDatabase()
        self.activation_system = EnhancedStrategyActivationSystem(self.database)

    async def test_positive_sentiment_alignment(self) -> None:
        now = datetime.now(timezone.utc)
        self.database.symbol_data["BTCUSDT"] = [
            {"aggregated_score": 0.8, "timestamp": (now - timedelta(hours=1)).isoformat()},
            {"aggregated_score": 0.6, "timestamp": (now - timedelta(hours=2)).isoformat()},
        ]
        self.database.global_data = [
            {
                "aggregated_score": 0.4,
                "sentiment_type": "global_crypto_sentiment",
                "timestamp": (now - timedelta(hours=3)).isoformat(),
            }
        ]

        score, context = await self.activation_system._calculate_sentiment_alignment(
            {
                "id": "strategy-positive",
                "symbols": [{"symbol": "BTCUSDT"}],
                "parameters": {},
            }
        )

        self.assertGreater(score, 0.78)
        self.assertAlmostEqual(context["combined_polarity"], 0.58, delta=0.05)
        self.assertEqual(context["symbols"], ["BTCUSDT"])

    async def test_stale_sentiment_penalty(self) -> None:
        now = datetime.now(timezone.utc)
        self.database.symbol_data["ETHUSDT"] = [
            {"aggregated_score": 0.9, "timestamp": (now - timedelta(hours=30)).isoformat()}
        ]
        self.database.global_data = []

        score, context = await self.activation_system._calculate_sentiment_alignment(
            {
                "id": "strategy-stale",
                "symbols": [{"symbol": "ethusdt"}],
                "parameters": {},
            }
        )

        self.assertLess(score, 0.5)
        self.assertGreater(score, 0.3)
        self.assertAlmostEqual(context["combined_polarity"], 0.225, delta=0.05)

    async def test_missing_sentiment_defaults_to_neutral(self) -> None:
        self.database.symbol_data.clear()
        self.database.global_data.clear()

        score, context = await self.activation_system._calculate_sentiment_alignment(
            {
                "id": "strategy-neutral",
                "symbols": [],
                "parameters": {},
            }
        )

        self.assertAlmostEqual(score, 0.5, delta=0.01)
        self.assertIsNone(context["avg_symbol_polarity"])
        self.assertIsNone(context["avg_global_polarity"])


if __name__ == "__main__":
    unittest.main()
