import unittest
from datetime import datetime, timezone
from session_features import build_session_features


class SessionFeatureTests(unittest.TestCase):
    def test_full_feature_set_and_running_values(self):
        candles = []
        for i in range(20):
            h = 101 + i
            l = 99 + i
            candles.append({
                "timestamp": f"2026-08-17T09:{15+i:02d}:00+05:30",
                "open": 100 + i,
                "high": h,
                "low": l,
                "close": 100.5 + i,
                "volume": 10 + i,
                "complete": True,
            })
        rows = build_session_features("NESTLEIND", candles)
        self.assertEqual(len(rows), 20)
        last = rows[-1]
        self.assertEqual(last["session_open"], 100)
        self.assertEqual(last["session_high"], 120)
        self.assertEqual(last["session_low"], 99)
        self.assertEqual(last["running_high"], 120)
        self.assertEqual(last["running_low"], 99)
        self.assertEqual(last["running_volume"], sum(10 + i for i in range(20)))
        self.assertIsNotNone(last["first_5m_high"])
        self.assertIsNotNone(last["first_15m_high"])

    def test_incomplete_candles_are_excluded(self):
        candles = [{
            "timestamp": "2026-08-17T09:15:00+05:30", "open": 100, "high": 101,
            "low": 99, "close": 100, "volume": 10, "complete": False,
        }]
        self.assertEqual(build_session_features("VEDL", candles), [])

    def test_out_of_session_candles_are_excluded(self):
        candles = [{
            "timestamp": "2026-08-17T15:30:00+05:30", "open": 100, "high": 101,
            "low": 99, "close": 100, "volume": 10, "complete": True,
        }]
        self.assertEqual(build_session_features("TCS", candles), [])


if __name__ == "__main__":
    unittest.main()
