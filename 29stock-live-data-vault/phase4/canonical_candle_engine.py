"""PSY29 Phase 4 — Canonical Candle Engine.

Canonical candles are built only from genuine DHAN OHLCV candle data. Phase 3
one-minute snapshots remain the raw audit layer; they are deliberately NOT
used to invent intraminute high/low/volume because a once-per-minute LTP quote
cannot reconstruct a true candle.
"""
import argparse
import json
import os
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
ROOT = Path(__file__).resolve().parent
VAULT = ROOT / "candles"
DHAN_INTRADAY = "https://api.dhan.co/v2/charts/intraday"
DHAN_DAILY = "https://api.dhan.co/v2/charts/historical"
TIMEFRAMES = {"1m": 1, "5m": 5, "15m": 15, "1h": 60}
SESSION_START = (9, 15)
SESSION_END = (15, 30)


def session_bounds(day):
    start = datetime(day.year, day.month, day.day, *SESSION_START, tzinfo=IST)
    end = datetime(day.year, day.month, day.day, *SESSION_END, tzinfo=IST)
    return start, end


def _post(url, payload, transport=None):
    if transport:
        return transport(url, payload)
    token = os.environ.get("DHAN_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("DHAN_ACCESS_TOKEN unavailable")
    request = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST", headers={
        "Accept": "application/json", "Content-Type": "application/json", "access-token": token,
        "User-Agent": "PSY29-Phase4/1.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        body = json.loads(response.read().decode("utf-8"))
    if response.status != 200:
        raise RuntimeError(f"DHAN historical failure: HTTP {response.status}")
    return body


def normalize(body, symbol, timeframe):
    required = ("timestamp", "open", "high", "low", "close", "volume")
    if any(k not in body for k in required):
        raise ValueError("historical response missing OHLCV arrays")
    n = len(body["timestamp"])
    if n == 0 or any(len(body[k]) != n for k in required):
        raise ValueError("historical OHLCV array length mismatch/empty response")
    result = []
    for i in range(n):
        ts = datetime.fromtimestamp(int(body["timestamp"][i]), tz=timezone.utc).astimezone(IST)
        candle = {
            "schema": "PSY29_CANONICAL_CANDLE_V1", "symbol": symbol, "timeframe": timeframe,
            "timestamp": ts.isoformat(), "open": float(body["open"][i]), "high": float(body["high"][i]),
            "low": float(body["low"][i]), "close": float(body["close"][i]), "volume": float(body["volume"][i]),
            "source": "DHAN_HISTORICAL", "complete": True,
        }
        validate_candle(candle)
        result.append(candle)
    return result


def validate_candle(candle):
    ts = datetime.fromisoformat(candle["timestamp"])
    if ts.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    o, h, l, c, v = (candle.get(k) for k in ("open", "high", "low", "close", "volume"))
    if any(x is None for x in (o, h, l, c, v)):
        raise ValueError("OHLCV contains null")
    if any(float(x) < 0 for x in (o, h, l, c, v)) or h < max(o, c) or l > min(o, c) or l > h:
        raise ValueError("OHLC/volume integrity violation")
    return True


def _bucket(ts, minutes):
    local = ts.astimezone(IST)
    start, _ = session_bounds(local.date())
    elapsed = int((local - start).total_seconds() // 60)
    return start + timedelta(minutes=(elapsed // minutes) * minutes)


def aggregate(rows, timeframe, complete=True):
    rows = sorted(rows, key=lambda x: x["timestamp"])
    if not rows:
        raise ValueError("cannot aggregate empty candle set")
    for row in rows:
        validate_candle(row)
    return {
        "schema": "PSY29_CANONICAL_CANDLE_V1", "symbol": rows[0]["symbol"], "timeframe": timeframe,
        "timestamp": rows[0]["timestamp"], "open": rows[0]["open"], "high": max(x["high"] for x in rows),
        "low": min(x["low"] for x in rows), "close": rows[-1]["close"], "volume": sum(x["volume"] for x in rows),
        "source": "PSY29_AGGREGATED_FROM_1M", "complete": complete,
    }


def build_from_1m(one_minute, timeframe):
    if timeframe == "1m":
        return list(sorted(one_minute, key=lambda x: x["timestamp"]))
    size = TIMEFRAMES[timeframe]
    buckets = defaultdict(list)
    for row in one_minute:
        buckets[_bucket(datetime.fromisoformat(row["timestamp"]), size).isoformat()].append(row)
    result = []
    for key in sorted(buckets):
        rows = buckets[key]
        result.append(aggregate(rows, timeframe, complete=(len(rows) == size)))
    return result


def build_weekly(daily_rows, symbol):
    buckets = defaultdict(list)
    for row in daily_rows:
        ts = datetime.fromisoformat(row["timestamp"])
        monday = (ts - timedelta(days=ts.weekday())).date().isoformat()
        buckets[monday].append(dict(row, symbol=symbol))
    return [aggregate(v, "1W", complete=True) for _, v in sorted(buckets.items())]


def fetch_intraday(security_id, symbol, from_date, to_date, interval=1, transport=None):
    payload = {"securityId": str(security_id), "exchangeSegment": "NSE_EQ", "instrument": "EQUITY",
               "interval": str(interval), "oi": False, "fromDate": from_date, "toDate": to_date}
    timeframe = "1h" if interval == 60 else f"{interval}m"
    return normalize(_post(DHAN_INTRADAY, payload, transport), symbol, timeframe)


def fetch_daily(security_id, symbol, from_date, to_date, transport=None):
    payload = {"securityId": str(security_id), "exchangeSegment": "NSE_EQ", "instrument": "EQUITY",
               "expiryCode": 0, "oi": False, "fromDate": from_date, "toDate": to_date}
    return normalize(_post(DHAN_DAILY, payload, transport), symbol, "1D")


def backfill(security_id, symbol, from_date, to_date, transport=None):
    start = datetime.strptime(from_date, "%Y-%m-%d").date()
    end = datetime.strptime(to_date, "%Y-%m-%d").date()
    one_minute = []
    cursor = start
    while cursor < end:
        chunk_end = min(cursor + timedelta(days=90), end)
        one_minute.extend(fetch_intraday(security_id, symbol, cursor.isoformat(), chunk_end.isoformat(), 1, transport))
        cursor = chunk_end
    daily = fetch_daily(security_id, symbol, from_date, to_date, transport)
    outputs = {"1m": one_minute, "5m": build_from_1m(one_minute, "5m"),
               "15m": build_from_1m(one_minute, "15m"), "1h": build_from_1m(one_minute, "1h"),
               "1D": daily, "1W": build_weekly(daily, symbol)}
    for timeframe, candles in outputs.items():
        persist(symbol, timeframe, candles)
    return outputs


def persist(symbol, timeframe, candles):
    VAULT.mkdir(parents=True, exist_ok=True)
    path = VAULT / f"{symbol}_{timeframe}.jsonl"
    seen = set()
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                seen.add(json.loads(line)["timestamp"])
    with path.open("a", encoding="utf-8") as handle:
        for candle in candles:
            validate_candle(candle)
            if candle["timestamp"] in seen:
                continue
            handle.write(json.dumps(candle, separators=(",", ":")) + "\n")
            seen.add(candle["timestamp"])
        handle.flush()
        os.fsync(handle.fileno())
    return path


def collect_completed_minute(security_id, symbol, minute, transport=None):
    start = minute.strftime("%Y-%m-%d %H:%M:%S")
    end = (minute + timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S")
    candles = fetch_intraday(security_id, symbol, start, end, 1, transport)
    if len(candles) != 1 or candles[0]["timestamp"] != minute.isoformat():
        raise RuntimeError("completed-minute candle unavailable or timestamp mismatch")
    return persist(symbol, "1m", candles)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--security-id", required=True)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--from-date", required=True)
    parser.add_argument("--to-date", required=True)
    parser.add_argument("--backfill", action="store_true")
    args = parser.parse_args()
    if args.backfill:
        outputs = backfill(args.security_id, args.symbol, args.from_date, args.to_date)
        print("PHASE4 OK: " + ", ".join(f"{k}={len(v)}" for k, v in outputs.items()))


if __name__ == "__main__":
    main()
