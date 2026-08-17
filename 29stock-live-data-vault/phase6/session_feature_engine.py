"""PSY29 Phase 6 — Session & Market Feature Engine."""
import json
import os
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "features"
SESSION_START = 9 * 60 + 15


def minute_of_day(ts):
    d = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return d.hour * 60 + d.minute


def session_date(ts):
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).date().isoformat()


def calculate(symbol, timeframe, candles):
    eligible = sorted((c for c in candles if c.get("complete") is True), key=lambda c: c["timestamp"])
    groups = {}
    for c in eligible:
        day = session_date(c["timestamp"])
        minute = minute_of_day(c["timestamp"])
        if minute >= SESSION_START:
            groups.setdefault(day, []).append(c)

    rows = []
    for day, cs in groups.items():
        first5 = [c for c in cs if minute_of_day(c["timestamp"]) < SESSION_START + 5]
        first15 = [c for c in cs if minute_of_day(c["timestamp"]) < SESSION_START + 15]
        f5h = max((float(c["high"]) for c in first5), default=None)
        f5l = min((float(c["low"]) for c in first5), default=None)
        f15h = max((float(c["high"]) for c in first15), default=None)
        f15l = min((float(c["low"]) for c in first15), default=None)
        running_h = running_l = running_v = None
        for c in cs:
            high, low, vol = float(c["high"]), float(c["low"]), float(c["volume"])
            running_h = high if running_h is None else max(running_h, high)
            running_l = low if running_l is None else min(running_l, low)
            running_v = vol if running_v is None else running_v + vol
            rows.append({
                "symbol": symbol, "timeframe": timeframe, "timestamp": c["timestamp"],
                "session_date": day, "source_candle": "PSY29_PHASE4_CANONICAL",
                "complete_candle_required": True,
                "session_open": float(cs[0]["open"]),
                "session_high": running_h, "session_low": running_l,
                "session_close": float(c["close"]), "session_volume": running_v,
                "first_5m_high": f5h, "first_5m_low": f5l,
                "first_5m_range": None if f5h is None else f5h - f5l,
                "first_15m_high": f15h, "first_15m_low": f15l,
                "first_15m_range": None if f15h is None else f15h - f15l,
                "running_high": running_h, "running_low": running_l,
                "running_volume": running_v,
            })
    return rows


def persist(rows):
    OUT.mkdir(parents=True, exist_ok=True)
    if not rows:
        return None
    path = OUT / f"{rows[0]['symbol']}_{rows[0]['timeframe']}.jsonl"
    existing = set()
    if path.exists():
        existing = {json.loads(x)["timestamp"] for x in path.read_text(encoding="utf-8").splitlines() if x.strip()}
    with path.open("a", encoding="utf-8") as f:
        for row in rows:
            if row["timestamp"] not in existing:
                f.write(json.dumps(row, separators=(",", ":")) + "\n")
                existing.add(row["timestamp"])
        f.flush(); os.fsync(f.fileno())
    return path
