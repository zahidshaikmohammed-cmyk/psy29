import csv
import io
import json
import unittest
from pathlib import Path

from instrument_foundation import resolve
from universe import STOCKS


class InstrumentFoundationTests(unittest.TestCase):
    def test_29_stock_universe(self):
        self.assertEqual(len(STOCKS), 29)
        self.assertEqual(len(set(STOCKS)), 29)

    def test_resolve_exactly_29_nse_equities(self):
        rows = [
            {
                "SEM_EXM_EXCH_ID": "NSE",
                "SEM_SEGMENT": "E",
                "SEM_INSTRUMENT_NAME": "EQUITY",
                "SEM_TRADING_SYMBOL": s,
                "SEM_SMST_SECURITY_ID": str(10000 + i),
            }
            for i, s in enumerate(STOCKS)
        ]
        fields = list(rows[0])
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
        result = resolve(buf.getvalue().encode())
        self.assertEqual([r["symbol"] for r in result], list(STOCKS))
        self.assertEqual(len({r["security_id"] for r in result}), 29)
        self.assertTrue(all(r["exchange_segment"] == "NSE_EQ" for r in result))
        self.assertTrue(all(r["instrument_type"] == "EQUITY" for r in result))

    def test_persisted_fixture_shape_if_present(self):
        p = Path(__file__).with_name("instrument_master.json")
        if p.exists():
            data = json.loads(p.read_text())
            self.assertEqual(data["universe_size"], 29)
            self.assertEqual(len(data["instruments"]), 29)


if __name__ == "__main__":
    unittest.main()
