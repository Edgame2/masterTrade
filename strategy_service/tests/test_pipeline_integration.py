import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

sys.path.append(str(Path(__file__).resolve().parents[2] / "strategy_service"))
from automatic_pipeline import AutomaticStrategyPipeline  # type: ignore  # pylint: disable=wrong-import-position


class _StubDatabase:
    def __init__(self):
        self.created_strategies = []
        self.backtest_results = []
        self.status_updates = []
        self.learning_insights = []

    async def get_backtest_results(self, limit: int = 1000):
        return []

    async def get_sentiment_entries(self, **_kwargs):
        return []

    async def query_market_data(self, *_args, **_kwargs):
        return []

    async def create_strategy(self, strategy_config):
        self.created_strategies.append(strategy_config)
        return True

    async def store_backtest_result(self, strategy_id, result):
        self.backtest_results.append((strategy_id, result))
        return True

    async def update_strategy_status(self, strategy_id, status):
        self.status_updates.append((strategy_id, status))
        return True

    async def store_learning_insights(self, payload):
        self.learning_insights.append(payload)
        return True


class AutomaticPipelineIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.database = _StubDatabase()
        self.pipeline = AutomaticStrategyPipeline(self.database, market_data_consumer=None)
        self.pipeline.strategies_per_cycle = 2

        strategies = [
            {"id": "strategy-1", "symbols": ["BTCUSDT"], "type": "trend_following"},
            {"id": "strategy-2", "symbols": ["ETHUSDT"], "type": "mean_reversion"},
        ]
        self.pipeline.strategy_learner.generate_improved_strategies = AsyncMock(return_value=strategies)
        self.pipeline._fetch_backtest_data = AsyncMock(return_value={"BTCUSDT": None})

        backtest_results = [
            {
                "strategy_id": "strategy-1",
                "strategy_config": strategies[0],
                "strategy_type": strategies[0]["type"],
                "sharpe_ratio": 1.8,
                "win_rate": 0.55,
                "total_return": 32.0,
                "total_trades": 25,
                "price_prediction": {"predicted_change_pct": 1.2},
            },
            {
                "strategy_id": "strategy-2",
                "strategy_config": strategies[1],
                "strategy_type": strategies[1]["type"],
                "sharpe_ratio": 0.9,
                "win_rate": 0.48,
                "total_return": 21.0,
                "total_trades": 18,
            },
        ]
        self.pipeline._backtest_single_strategy = AsyncMock(side_effect=backtest_results)
        self.pipeline.strategy_learner.learn_from_backtests = AsyncMock(return_value={"insights": ["ok"]})

    async def test_full_cycle_persists_results(self):
        results = await self.pipeline.run_full_cycle()

        self.assertEqual(results["generated_count"], 2)
        self.assertEqual(results["backtested_count"], 2)
        self.assertEqual(len(self.database.created_strategies), 2)
        self.assertEqual(len(self.database.backtest_results), 2)
        self.assertIn(("strategy-1", "paper_trading"), self.database.status_updates)
        self.assertGreater(len(self.database.learning_insights), 0)
        self.pipeline.strategy_learner.learn_from_backtests.assert_called_once()


if __name__ == "__main__":
    unittest.main()
