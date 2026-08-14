#!/usr/bin/env python3
"""Causal PSY29 event detector; research-derived, live-only, no look-ahead."""
from __future__ import annotations

import argparse
import csv
import json
import os
import tempfile
from datetime import datetime, time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
SYMBOLS = ["NESTLEIND","VEDL","ICICIPRULI","KALYANKJIL","KOTAKBANK","BANDHANBNK","BANKBARODA","TITAN","INFY","DLF","TCS","MAXHEALTH","KFINTECH","PRESTIGE","BHEL","RBLBANK","HCLTECH","ICICIGI","HDFCLIFE","MARICO","LUPIN","COFORGE","TECHM","SWIGGY","PERSISTENT","OBEROIRLTY","SUPREMEIND","LAURUSLABS","AMBUJACEM"]
CUTOFF = dtime(15, 0, 0)
EVENT_TYPES = ("Trend", "Strong Trend", "OR Continuation")
REQUIRED = {"symbol", "timestamp", "open_1m", "high_1m", "low_1m", "close_1m", "volume_1m"}


def _atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(value, fh, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _parse_ts(value: str) -> datetime:
    ts = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if ts.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return ts.astimezone(IST).replace(second=0, microsecond=0)


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_provenance(validation: dict, mode: str) -> None:
    if mode != "live":
        raise ValueError("event detector is live-only; fixture/off-market mode is rejected")
    if validation.get("status") != "PASS":
        raise ValueError("upstream validation status is not PASS")
    if validation.get("mode") != "live" or validation.get("live_data") is not True:
        raise ValueError("event detector requires mode=live and live_data=true")
    if validation.get("fresh_count") != 29 or validation.get("fixture_count") != 0:
        raise ValueError("event detector requires fresh_count=29 and fixture_count=0")
    if validation.get("coverage", {}).get("actual") != 29 or validation.get("coverage", {}).get("unique") != 29:
        raise ValueError("event detector requires exact 29/29 upstream coverage")


def validate_thresholds(thresholds: dict) -> None:
    if thresholds.get("research_source_commit") != "988472889edfd51046731d72f68f2e96e095a2f1":
        raise ValueError("threshold artifact must cite canonical event-time research commit")
    stocks = thresholds.get("stocks", {})
    if set(stocks) != set(SYMBOLS):
        raise ValueError("threshold artifact must contain exactly the canonical 29 stocks")
    required = {
        "Trend": ("r75", "e60", "hard_earliest_offset"),
        "Strong Trend": ("r85", "e75", "hard_earliest_offset"),
        "OR Continuation": ("or75", "ext60", "hard_earliest_offset"),
    }
    for symbol in SYMBOLS:
        for evt, fields in required.items():
            cfg = stocks[symbol].get(evt)
            if not isinstance(cfg, dict) or any(f not in cfg for f in fields):
                raise ValueError(f"missing {evt} thresholds for {symbol}")
            if any(float(cfg[f]) != float(cfg[f]) for f in fields):
                raise ValueError(f"non-finite threshold for {symbol}/{evt}")


def _session_state(state: dict, symbol: str, date: str) -> dict:
    sessions = state.setdefault("sessions", {})
    key = f"{symbol}|{date}"
    return sessions.setdefault(key, {"bars": [], "events": {}})


def detect_current(symbol: str, session: dict, thresholds: dict, bar_ts: datetime) -> list[dict]:
    bars = session["bars"]
    if not bars:
        return []
    op = float(bars[0]["open"])
    c = float(bars[-1]["close"])
    if op == 0:
        return []
    closes = [float(x["close"]) for x in bars]
    abs_return = abs(c - op) / op
    cumulative = sum(abs(closes[i] / closes[i - 1] - 1.0) for i in range(1, len(closes)))
    efficiency = abs_return / (cumulative + 1e-12)
    cfg = thresholds[symbol]
    results: list[tuple[str, bool]] = [
        ("Trend", abs_return >= float(cfg["Trend"]["r75"]) and efficiency >= float(cfg["Trend"]["e60"])),
        ("Strong Trend", abs_return >= float(cfg["Strong Trend"]["r85"]) and efficiency >= float(cfg["Strong Trend"]["e75"])),
    ]
    if len(bars) >= 16:
        opening = bars[:15]
        orh = max(float(x["high"]) for x in opening)
        orl = min(float(x["low"]) for x in opening)
        or_pct = (orh - orl) / op
        cur = bars[-1]
        up = float(cur["high"]) > orh and c > orh and (c - orh) / op >= float(cfg["OR Continuation"]["ext60"])
        dn = float(cur["low"]) < orl and c < orl and (orl - c) / op >= float(cfg["OR Continuation"]["ext60"])
        results.append(("OR Continuation", or_pct <= float(cfg["OR Continuation"]["or75"]) and (up or dn)))
    return [{"event_type": evt, "timestamp": bar_ts.isoformat()} for evt, ok in results if ok]


def process(snapshot: Path, validation_path: Path, thresholds_path: Path, state_path: Path, output: Path, mode: str = "live") -> dict:
    validation = _load_json(validation_path)
    validate_provenance(validation, mode)
    thresholds = _load_json(thresholds_path)
    validate_thresholds(thresholds)
    with snapshot.open("r", encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    if len(rows) != 29 or {r.get("symbol", "").strip().upper() for r in rows} != set(SYMBOLS):
        raise ValueError("snapshot must contain exactly the canonical 29 symbols")
    state = _load_json(state_path) if state_path.exists() else {"schema": "PSY29_EVENT_DETECTOR_STATE_V1", "sessions": {}}
    detected = []
    for row in rows:
        symbol = row["symbol"].strip().upper()
        ts = _parse_ts(row["timestamp"])
        if ts.time() < dtime(9, 15) or ts.time() > dtime(15, 30):
            raise ValueError(f"bar timestamp outside NSE session for {symbol}: {ts.isoformat()}")
        date = ts.date().isoformat()
        sess = _session_state(state, symbol, date)
        if sess["bars"] and ts <= _parse_ts(sess["bars"][-1]["timestamp"]):
            if ts == _parse_ts(sess["bars"][-1]["timestamp"]):
                continue
            raise ValueError(f"non-monotonic bar timestamp for {symbol}")
        bar = {"timestamp": ts.isoformat(), "open": float(row["open_1m"]), "high": float(row["high_1m"]), "low": float(row["low_1m"]), "close": float(row["close_1m"]), "volume": float(row["volume_1m"])}
        if any(v != v or v in (float("inf"), float("-inf")) for v in bar.values() if isinstance(v, float)):
            raise ValueError(f"non-finite bar for {symbol}")
        sess["bars"].append(bar)
        for event in detect_current(symbol, sess, thresholds["stocks"], ts):
            evt = event["event_type"]
            cfg = thresholds["stocks"][symbol][evt]
            offset = (ts.hour * 60 + ts.minute) - 555
            if offset < int(cfg["hard_earliest_offset"]):
                continue
            if evt in sess["events"]:
                continue
            event_id = f"{symbol}|{evt}|{date}|{ts.isoformat()}"
            priority = "UNKNOWN"
            if "q25_offset" in cfg and "q75_offset" in cfg:
                q25, q75 = float(cfg["q25_offset"]), float(cfg["q75_offset"])
                priority = "HISTORICAL_PRIORITY" if q25 <= offset <= q75 else "OUTSIDE_HISTORICAL_PRIORITY"
            record = {
                "event_id": event_id,
                "instrument": symbol,
                "event_type": evt,
                "nse_session_date": date,
                "first_detectable_timestamp": ts.isoformat(),
                "source_bar_timestamp": ts.isoformat(),
                "provenance": {
                    "provider": "DHAN",
                    "mode": "live",
                    "live_data": True,
                    "fixture_count": 0,
                    "source_validation": str(validation_path),
                    "source_generated_at": validation.get("generated_at"),
                },
                "historical_priority": priority,
                "new_signal_eligible_by_cutoff": ts.time() <= CUTOFF,
            }
            sess["events"][evt] = record
            detected.append(record)
    _atomic_json(state_path, state)
    output.mkdir(parents=True, exist_ok=True)
    result = {"contract": "PSY29_CAUSAL_EVENT_DETECTOR_V1", "status": "PASS", "mode": "live", "detected_events": detected, "state_file": str(state_path), "research_source_commit": thresholds["research_source_commit"]}
    _atomic_json(output / "PSY29_EVENT_DETECTOR_RESULT.json", result)
    return result


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--snapshot", type=Path, required=True)
    p.add_argument("--validation", type=Path, required=True)
    p.add_argument("--thresholds", type=Path, required=True)
    p.add_argument("--state", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--mode", choices=("live", "fixture"), default="live")
    a = p.parse_args()
    print(json.dumps(process(a.snapshot, a.validation, a.thresholds, a.state, a.output, a.mode), indent=2))


if __name__ == "__main__":
    main()
