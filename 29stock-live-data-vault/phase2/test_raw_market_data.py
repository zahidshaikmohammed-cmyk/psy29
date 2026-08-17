import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "market-live.json"
MASTER = ROOT.parent / "phase1" / "instrument_master.json"


class Phase2AcquisitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.master = json.loads(MASTER.read_text())
        cls.data = json.loads(OUT.read_text())

    def test_29_records(self):
        self.assertEqual(self.data["universe_size"], 29)
        self.assertEqual(len(self.data["instruments"]), 29)
        self.assertEqual(len({x["security_id"] for x in self.data["instruments"]}), 29)

    def test_quote_and_depth_present_for_all(self):
        for row in self.data["instruments"]:
            q = row["provider_data"]
            self.assertIn("last_price", q)
            self.assertIsInstance(q.get("depth"), dict)
            self.assertTrue(q["depth"].get("buy") is not None)
            self.assertTrue(q["depth"].get("sell") is not None)

    def test_provider_timestamps_preserved(self):
        self.assertTrue(self.data["acquisition"]["provider_timestamps_preserved"])
        for row in self.data["instruments"]:
            self.assertIn("last_trade_time", row["provider_data"])


if __name__ == "__main__":
    unittest.main()
