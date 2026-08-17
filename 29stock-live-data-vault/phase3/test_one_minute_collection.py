import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import one_minute_collector as engine


class Phase3CollectionTests(unittest.TestCase):
    @staticmethod
    def fake_provider(instruments):
        return {
            x["security_id"]: {
                "last_price": 100.0,
                "last_trade_time": "2026-08-17T03:45:00Z",
                "depth": {"buy": [{"quantity": 1, "price": 99.9}], "sell": [{"quantity": 1, "price": 100.1}]},
            }
            for x in instruments
        }

    def test_official_session_is_exactly_375_minutes(self):
        minutes = engine.official_minutes(date(2026, 8, 17))
        self.assertEqual(len(minutes), 375)
        self.assertEqual(minutes[0].strftime("%H:%M"), "09:15")
        self.assertEqual(minutes[-1].strftime("%H:%M"), "15:29")

    def test_full_session_collection_and_duplicate_protection(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(engine, "VAULT", Path(tmp)):
            minutes = engine.official_minutes(date(2026, 8, 17))
            engine.run_window(date(2026, 8, 17), (9, 15), (15, 30), sleep=False, provider=self.fake_provider)
            path = Path(tmp) / "2026-08-17.jsonl"
            rows = [json.loads(x) for x in path.read_text().splitlines()]
            self.assertEqual(len(rows), 375)
            self.assertEqual(len({r["official_minute"] for r in rows}), 375)
            self.assertEqual(engine.collect_minute(minutes[100], json.loads(engine.MASTER.read_text())["instruments"], self.fake_provider), "duplicate-protected")

    def test_missing_minute_is_detectable_without_fabrication(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(engine, "VAULT", Path(tmp)):
            minutes = engine.official_minutes(date(2026, 8, 17))
            master = json.loads(engine.MASTER.read_text())["instruments"]
            for minute in minutes[:10]:
                engine.collect_minute(minute, master, self.fake_provider)
            rows = [json.loads(x) for x in (Path(tmp) / "2026-08-17.jsonl").read_text().splitlines()]
            expected = {m.isoformat() for m in minutes[:10]}
            self.assertEqual({r["official_minute"] for r in rows}, expected)
            self.assertNotIn(minutes[10].isoformat(), expected)

    def test_retry_recovery(self):
        calls = {"n": 0}
        master = json.loads(engine.MASTER.read_text())["instruments"]
        def flaky(instruments):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("temporary provider failure")
            return self.fake_provider(instruments)
        with tempfile.TemporaryDirectory() as tmp, patch.object(engine, "VAULT", Path(tmp)):
            last_error = None
            for attempt in range(3):
                try:
                    engine.collect_minute(engine.official_minutes(date(2026, 8, 17))[0], master, flaky)
                    last_error = None
                    break
                except RuntimeError as exc:
                    last_error = exc
            self.assertIsNone(last_error)
            self.assertEqual(calls["n"], 2)


if __name__ == "__main__":
    unittest.main()
