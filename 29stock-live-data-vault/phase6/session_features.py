from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
SESSION_OPEN = time(9, 15)
SESSION_CLOSE = time(15, 30)


@dataclass
class SessionFeatures:
    symbol: str
    session_date: str
    session_open: float
    session_high: float
    session_low: float
    session_close: float
    session_volume: float
    first_5m_high: float | None
    first_5m_low: float | None
    first_5m_range: float | None
    first_15m_high: float | None
    first_15m_low: float | None
    first_15m_range: float | None
    running_high: float
    running_low: float
    running_volume: float


def _minute(ts: datetime) -> int:
    return ts.astimezone(IST).hour * 60 + ts.astimezone(IST).minute


def build_session_features(symbol: str, candles: list[dict]) -> list[dict]:
    """Build deterministic session features from completed 1-minute candles only."""
    rows = [r for r in candles if r.get("complete") is True]
    rows.sort(key=lambda r: r["timestamp"])
    if not rows:
        return []

    state = None
    output = []
    for row in rows:
        ts = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00")).astimezone(IST)
        if ts.time() < SESSION_OPEN or ts.time() >= SESSION_CLOSE:
            continue
        if state is None or state["session_date"] != ts.date().isoformat():
            state = {
                "session_date": ts.date().isoformat(),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row["volume"]),
                "first5": [],
                "first15": [],
            }
        else:
            state["high"] = max(state["high"], float(row["high"]))
            state["low"] = min(state["low"], float(row["low"]))
            state["close"] = float(row["close"])
            state["volume"] += float(row["volume"])

        minute = _minute(ts)
        if minute < 9 * 60 + 20:
            state["first5"].append(row)
        if minute < 9 * 60 + 30:
            state["first15"].append(row)

        def rng(items):
            if not items:
                return (None, None, None)
            hi = max(float(x["high"]) for x in items)
            lo = min(float(x["low"]) for x in items)
            return hi, lo, hi - lo

        f5h, f5l, f5r = rng(state["first5"])
        f15h, f15l, f15r = rng(state["first15"])
        output.append({
            "symbol": symbol,
            "session_date": state["session_date"],
            "timestamp": row["timestamp"],
            "session_open": state["open"],
            "session_high": state["high"],
            "session_low": state["low"],
            "session_close": state["close"],
            "session_volume": state["volume"],
            "first_5m_high": f5h,
            "first_5m_low": f5l,
            "first_5m_range": f5r,
            "first_15m_high": f15h,
            "first_15m_low": f15l,
            "first_15m_range": f15r,
            "running_high": state["high"],
            "running_low": state["low"],
            "running_volume": state["volume"],
        })
    return output
