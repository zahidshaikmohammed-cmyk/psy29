"""PSY29 Phase 5 — Indicator Engine.

Locked indicators: VWAP, EMA9, EMA20. No other named indicator is required by
any of the 29 specialist contracts currently available to PSY29. Volatility,
range expansion and momentum are derived features and are intentionally left
for the feature layer rather than silently inventing indicators here.

Only candles with complete=true are eligible for indicator output.
"""
import json
import math
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CANDLE_ROOT = ROOT.parent / "phase4" / "candles"
OUT = ROOT / "indicators"
PERIODS = (9, 20)
INTRADAY_TIMEFRAMES = {"1m", "5m", "15m", "1h"}


def ema(values, period):
    if len(values) < period:
        return [None] * len(values)
    alpha = 2.0 / (period + 1.0)
    out = [None] * (period - 1)
    seed = sum(values[:period]) / period
    out.append(seed)
    prev = seed
    for value in values[period:]:
        prev = (value - prev) * alpha + prev
        out.append(prev)
    return out


def vwap(candles):
    cumulative_pv = 0.0
    cumulative_volume = 0.0
    result = []
    for candle in candles:
        typical = (candle["high"] + candle["low"] + candle["close"]) / 3.0
        volume = candle["volume"]
        cumulative_pv += typical * volume
        cumulative_volume += volume
        result.append(cumulative_pv / cumulative_volume if cumulative_volume else None)
    return result


def load_candles(symbol, timeframe):
    path = CANDLE_ROOT / f"{symbol}_{timeframe}.jsonl"
    if not path.exists():
        return []
    rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    rows.sort(key=lambda x: x["timestamp"])
    return [x for x in rows if x.get("complete") is True]


def calculate(symbol, timeframe, candles):
    closes = [float(x["close"]) for x in candles]
    vwaps = vwap(candles) if timeframe in INTRADAY_TIMEFRAMES else [None] * len(candles)
    ema9 = ema(closes, 9)
    ema20 = ema(closes, 20)
    rows = []
    for i, candle in enumerate(candles):
        rows.append({
            "symbol": symbol,
            "timeframe": timeframe,
            "timestamp": candle["timestamp"],
            "source_candle": "PSY29_PHASE4_CANONICAL",
            "complete_candle_required": True,
            "vwap": vwaps[i],
            "ema9": ema9[i],
            "ema20": ema20[i],
        })
    return rows


def persist(rows):
    OUT.mkdir(parents=True, exist_ok=True)
    if not rows:
        return None
    symbol, timeframe = rows[0]["symbol"], rows[0]["timeframe"]
    path = OUT / f"{symbol}_{timeframe}.jsonl"
    existing = set()
    if path.exists():
        existing = {json.loads(x)["timestamp"] for x in path.read_text().splitlines() if x.strip()}
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            if row["timestamp"] not in existing:
                handle.write(json.dumps(row, separators=(",", ":")) + "\n")
                existing.add(row["timestamp"])
        handle.flush()
        os.fsync(handle.fileno())
    return path


def run(symbols, timeframes):
    count = 0
    for symbol in symbols:
        for timeframe in timeframes:
            candles = load_candles(symbol, timeframe)
            rows = calculate(symbol, timeframe, candles)
            if rows:
                persist(rows)
                count += 1
    return count


if __name__ == "__main__":
    master = json.loads((ROOT.parent / "phase1" / "instrument_master.json").read_text())
    symbols = [x["symbol"] for x in master["instruments"]]
    run(symbols, ["1m", "5m", "15m", "1h", "1D", "1W"])
    print("PSY29 Phase 5 indicator calculation complete")
