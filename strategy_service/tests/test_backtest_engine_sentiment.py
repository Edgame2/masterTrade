import unittest
from datetime import datetime, timedelta

from strategy_service.backtest_engine import BacktestEngine


class BacktestSentimentGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = BacktestEngine()

    def _build_timeline(self, profile, *, symbol_score, symbol_age_hours=0, global_score=None):
        candle_time = datetime.utcnow()
        candles = [
            {
                "datetime": candle_time,
                "timestamp": candle_time.isoformat(),
                "open": 1.0,
                "high": 1.0,
                "low": 1.0,
                "close": 1.0,
                "volume": 1.0,
            }
        ]
        symbol_timestamp = candle_time - timedelta(hours=symbol_age_hours)
        symbol_entries = [
            {
                "timestamp": symbol_timestamp.isoformat(),
                "aggregated_score": symbol_score,
            }
        ]
        global_entries = []
        if global_score is not None:
            global_entries.append(
                {
                    "timestamp": candle_time.isoformat(),
                    "aggregated_score": global_score,
                }
            )

        timeline, metrics = self.engine._align_sentiment_series(
            candles,
            profile,
            symbol_entries,
            global_entries,
        )
        return timeline[0], metrics

    def test_fear_buy_bias_allows_negative_sentiment(self):
        profile = self.engine._normalise_sentiment_profile(
            {
                "bias": "fear_buy",
                "negative_buy_threshold": 0.6,
                "symbol_weight": 0.7,
                "global_weight": 0.3,
            }
        )
        point, metrics = self._build_timeline(profile, symbol_score=-0.7)

        allowed, multiplier = self.engine._evaluate_sentiment_gate(profile, point, metrics)

        self.assertTrue(allowed)
        self.assertGreaterEqual(multiplier, 1.0)
        self.assertEqual(metrics["negative_triggers"], 1)
        self.assertEqual(metrics["positive_triggers"], 0)

    def test_risk_on_bias_blocks_negative_sentiment(self):
        profile = self.engine._normalise_sentiment_profile(
            {
                "bias": "risk_on",
                "min_alignment": 0.65,
                "symbol_weight": 0.8,
                "global_weight": 0.2,
            }
        )
        point, metrics = self._build_timeline(profile, symbol_score=-0.8)

        allowed, multiplier = self.engine._evaluate_sentiment_gate(profile, point, metrics)

        self.assertFalse(allowed)
        self.assertLessEqual(multiplier, 1.0)
        self.assertEqual(metrics["blocked"], 1)

    def test_stale_sentiment_penalty_reduces_multiplier(self):
        profile = self.engine._normalise_sentiment_profile(
            {
                "bias": "balanced",
                "min_alignment": 0.55,
                "symbol_weight": 0.6,
                "global_weight": 0.4,
            }
        )
        point, metrics = self._build_timeline(profile, symbol_score=0.8, symbol_age_hours=48)

        allowed, multiplier = self.engine._evaluate_sentiment_gate(profile, point, metrics)

        self.assertTrue(allowed)
        self.assertLess(multiplier, 1.0)
        self.assertGreater(metrics["stale_penalty_events"], 0)


if __name__ == "__main__":
    unittest.main()
