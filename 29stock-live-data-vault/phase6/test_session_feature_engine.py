import unittest
from session_feature_engine import calculate, persist


def candles():
    out = []
    for i in range(20):
        minute = 15 + i
        out.append({
            "timestamp": f"2026-08-17T09:{minute:02d}:00+05:30",
            "open": 100+i, "high": 101+i, "low": 99+i,
            "close": 100.5+i, "volume": 100+i, "complete": True,
        })
    out.append({"timestamp":"2026-08-17T09:35:00+05:30","open":120,"high":125,"low":118,"close":124,"volume":500,"complete":False})
    return out

class Phase6Tests(unittest.TestCase):
    def test_session_features_and_first_ranges(self):
        rows = calculate("NESTLEIND", "1m", candles())
        self.assertEqual(len(rows), 20)
        r = rows[4]
        self.assertEqual(r["session_open"], 100)
        self.assertEqual(r["first_5m_high"], 105)
        self.assertEqual(r["first_5m_low"], 99)
        self.assertEqual(r["first_5m_range"], 6)
        self.assertEqual(r["running_volume"], sum(100+i for i in range(5)))

    def test_first_15m_range_persists_after_window(self):
        rows = calculate("NESTLEIND", "1m", candles())
        self.assertEqual(rows[14]["first_15m_high"], 115)
        self.assertEqual(rows[14]["first_15m_low"], 99)
        self.assertEqual(rows[-1]["first_15m_range"], 16)
        self.assertEqual(rows[-1]["running_high"], 120)
        self.assertEqual(rows[-1]["running_low"], 99)

    def test_completed_candle_rule(self):
        rows = calculate("NESTLEIND", "1m", candles())
        self.assertTrue(all(r["complete_candle_required"] for r in rows))
        self.assertNotIn("09:35:00", [r["timestamp"] for r in rows])

    def test_feature_persistence(self):
        rows = calculate("PHASE6TEST", "1m", candles()[:3])
        path = persist(rows)
        self.assertTrue(path.exists())
        self.assertEqual(len(path.read_text(encoding="utf-8").splitlines()), 3)

if __name__ == "__main__":
    unittest.main()
