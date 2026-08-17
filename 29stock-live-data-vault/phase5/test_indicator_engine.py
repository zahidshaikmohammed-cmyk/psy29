import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from indicator_engine import calculate, ema, vwap

SYMBOLS = ["NESTLEIND","VEDL","ICICIPRULI","KALYANKJIL","KOTAKBANK","BANDHANBNK","BANKBARODA","TITAN","INFY","DLF","TCS","MAXHEALTH","KFINTECH","PRESTIGE","BHEL","RBLBANK","HCLTECH","ICICIGI","HDFCLIFE","MARICO","LUPIN","COFORGE","TECHM","SWIGGY","PERSISTENT","OBEROIRLTY","SUPREMEIND","LAURUSLABS","AMBUJACEM"]


def candles(n=25, complete=True):
    out=[]
    for i in range(n):
        p=100.0+i
        out.append({"timestamp":f"2026-08-17T09:{15+i:02d}:00+05:30","open":p,"high":p+1,"low":p-1,"close":p+0.5,"volume":100+i,"complete":complete})
    return out

class Phase5Tests(unittest.TestCase):
    def test_ema9_formula(self):
        vals=list(range(1,10))
        self.assertAlmostEqual(ema(vals,9)[-1],5.0)

    def test_ema20_available_after_seed(self):
        result=ema(list(range(1,21)),20)
        self.assertIsNone(result[18])
        self.assertAlmostEqual(result[19],10.5)

    def test_vwap_formula(self):
        rows=candles(2)
        expected=((100.5*100)+(101.5*101))/(100+101)
        self.assertAlmostEqual(vwap(rows)[1],expected)

    def test_incomplete_candles_are_excluded(self):
        rows=calculate("NESTLEIND","5m",candles(25,complete=True)+candles(1,complete=False))
        self.assertEqual(len(rows),25)
        self.assertTrue(all(r["complete_candle_required"] for r in rows))

    def test_29_of_29_requirement(self):
        for symbol in SYMBOLS:
            rows=calculate(symbol,"5m",candles(25))
            self.assertEqual(len(rows),25)
            self.assertEqual(rows[-1]["symbol"],symbol)
            self.assertIsNotNone(rows[-1]["vwap"])
            self.assertIsNotNone(rows[-1]["ema9"])
            self.assertIsNotNone(rows[-1]["ema20"])
            for row in rows:
                self.assertIn("timestamp",row)

if __name__ == "__main__":
    unittest.main()
