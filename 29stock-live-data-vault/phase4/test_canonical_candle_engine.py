import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import canonical_candle_engine as engine


class Phase4Tests(unittest.TestCase):
    def make_1m(self, count=375):
        start = datetime(2026, 8, 17, 9, 15, tzinfo=engine.IST)
        rows = []
        for i in range(count):
            price = 100 + i / 10
            rows.append({
                "schema": "PSY29_CANONICAL_CANDLE_V1", "symbol": "TCS", "timeframe": "1m",
                "timestamp": (start + timedelta(minutes=i)).isoformat(), "open": price,
                "high": price + 0.5, "low": price - 0.5, "close": price + 0.2,
                "volume": 100 + i, "source": "TEST", "complete": True,
            })
        return rows

    def dhan_body(self, count=375):
        start = datetime(2026, 8, 17, 9, 15, tzinfo=engine.IST)
        ts = [int((start + timedelta(minutes=i)).timestamp()) for i in range(count)]
        return {
            "timestamp": ts,
            "open": [100 + i / 10 for i in range(count)],
            "high": [100.5 + i / 10 for i in range(count)],
            "low": [99.5 + i / 10 for i in range(count)],
            "close": [100.2 + i / 10 for i in range(count)],
            "volume": [100 + i for i in range(count)],
        }

    def test_all_intraday_timeframes_and_completion(self):
        rows = self.make_1m()
        one = engine.build_from_1m(rows, "1m")
        five = engine.build_from_1m(rows, "5m")
        fifteen = engine.build_from_1m(rows, "15m")
        hour = engine.build_from_1m(rows, "1h")
        self.assertEqual(len(one), 375)
        self.assertEqual(len(five), 75)
        self.assertEqual(len(fifteen), 25)
        self.assertEqual(len(hour), 7)
        self.assertTrue(all(x["complete"] for x in five + fifteen))
        self.assertEqual([x["complete"] for x in hour], [True] * 6 + [False])
        self.assertEqual(five[0]["open"], rows[0]["open"])
        self.assertEqual(five[0]["close"], rows[4]["close"])
        self.assertEqual(five[0]["volume"], sum(x["volume"] for x in rows[:5]))

    def test_normalization_and_validation(self):
        candles = engine.normalize(self.dhan_body(2), "TCS", "1m")
        self.assertEqual(len(candles), 2)
        self.assertTrue(all(x["source"] == "DHAN_HISTORICAL" for x in candles))
        bad = dict(candles[0], high=1, low=200)
        with self.assertRaises(ValueError):
            engine.validate_candle(bad)

    def test_historical_backfill_uses_90_day_chunks_and_persists(self):
        calls = []
        def transport(url, payload):
            calls.append(payload)
            if "historical" in url:
                return {
                    "timestamp": [int(datetime(2026, 1, 2, 9, 15, tzinfo=engine.IST).timestamp())],
                    "open": [100], "high": [101], "low": [99], "close": [100.5], "volume": [1000],
                }
            return self.dhan_body(2)
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(engine, "VAULT", Path(tmp)):
                outputs = engine.backfill("11536", "TCS", "2026-01-01", "2026-04-05", transport)
                self.assertEqual(len(outputs["1m"]), 4)
                self.assertGreaterEqual(len([x for x in calls if "interval" in x]), 2)
                self.assertTrue((Path(tmp) / "TCS_1m.jsonl").exists())
                self.assertTrue((Path(tmp) / "TCS_1W.jsonl").exists())

    def test_completed_minute_requires_exact_timestamp(self):
        minute = datetime(2026, 8, 17, 9, 15, tzinfo=engine.IST)
        body = self.dhan_body(1)
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(engine, "VAULT", Path(tmp)):
                path = engine.collect_completed_minute("11536", "TCS", minute, lambda u, p: body)
                self.assertTrue(path.exists())
                self.assertEqual(len(path.read_text().splitlines()), 1)


if __name__ == "__main__":
    unittest.main()
