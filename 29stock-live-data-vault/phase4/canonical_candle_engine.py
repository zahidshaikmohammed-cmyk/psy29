"""PSY29 Phase 4 — Canonical Candle Engine.

Builds canonical OHLCV candles from genuine Phase 3 one-minute snapshots.
Higher intraday timeframes are aggregated from canonical 1-minute bars so the
entire candle hierarchy has one source of truth. Daily/weekly candles are
session-aware and never fabricated.
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
PHASE3 = ROOT.parent / "phase3"
SNAPSHOTS = PHASE3 / "snapshots"
VAULT = ROOT / "candles"
DHAN_INTRADAY = "https://api.dhan.co/v2/charts/intraday"
DHAN_DAILY = "https://api.dhan.co/v2/charts/historical"
SESSION_START = (9, 15)
SESSION_END = (15, 30)
TIMEFRAMES = {"1m": 1, "5m": 5, "15m": 15, "1h": 60}


def official_minutes(day):
    start = datetime(day.year, day.month, day.day, *SESSION_START, tzinfo=IST)
    end = datetime(day.year, day.month, day.day, *SESSION_END, tzinfo=IST)
    result = []
    cur = start
    while cur < end:
        result.append(cur)
        cur += timedelta(minutes=1)
    return result


def _num(value):
    return float(value) if value is not None else None


def _volume(quote):
    for key in ("volume", "traded_volume"):
        if key in quote:
            return float(quote[key])
    ohlc = quote.get("ohlc") if isinstance(quote.get("ohlc"), dict) else {}
    for key in ("volume", "traded_volume"):
        if key in ohlc:
            return float(ohlc[key])
    return None


def read_one_minute(day):
    path = SNAPSHOTS / f"{day.isoformat()}.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"Phase 3 snapshot file missing: {path}")
    expected = {x.isoformat() for x in official_minutes(day)}
    by_symbol = defaultdict(dict)
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        minute = row["official_minute"]
        if minute not in expected:
            raise ValueError(f"snapshot outside official session: {minute}")
        for rec in row["records"]:
            quote = rec["provider_data"]
            price = _num(quote.get("last_price"))
            if price is None or price <= 0:
                raise ValueError(f"invalid LTP for {rec['symbol']} at {minute}")
            by_symbol[rec["symbol"]][minute] = {
                "timestamp": minute,
                "open": price,
                "high": price,
                "low": price,
                "close": price,
                "volume": _volume(quote),
            }
    if len(by_symbol) != 29:
        raise ValueError(f"expected 29 stocks, got {len(by_symbol)}")
    return by_symbol


def _bucket(ts, minutes):
    local = ts.astimezone(IST)
    elapsed = (local.hour * 60 + local.minute) - (9 * 60 + 15)
    start_elapsed = (elapsed // minutes) * minutes
    return local.replace(hour=9, minute=15, second=0, microsecond=0) + timedelta(minutes=start_elapsed)


def _aggregate(rows, label, require_complete=True):
    if not rows:
        raise ValueError("cannot aggregate empty rows")
    rows = sorted(rows, key=lambda x: x["timestamp"])
    if require_complete:
        expected = None
        if label.endswith("m"):
            n = int(label[:-1])
            expected = n
        elif label == "1h":
            expected = 60
        if expected:
            start = datetime.fromisoformat(rows[0]["timestamp"])
            actual = len(rows)
            if actual != expected:
                raise ValueError(f"incomplete {label} candle at {start.isoformat()}: {actual}/{expected} minutes")
    volumes = [x["volume"] for x in rows]
    if any(v is None for v in volumes):
        raise ValueError(f"missing volume in {label} candle")
    return {
        "timeframe": label,
        "timestamp": rows[0]["timestamp"],
        "open": rows[0]["open"],
        "high": max(x["high"] for x in rows),
        "low": min(x["low"] for x in rows),
        "close": rows[-1]["close"],
        "volume": sum(volumes),
        "source": "PSY29_PHASE3_1M",
        "complete": True,
    }


def build_intraday(day, symbol, timeframe):
    if timeframe == "1m":
        data = read_one_minute(day)[symbol]
        result = []
        for minute in official_minutes(day):
            row = data.get(minute.isoformat())
            if row is None:
                raise ValueError(f"missing 1m minute for {symbol}: {minute.isoformat()}")
            result.append(_aggregate([row], "1m", require_complete=False))
        return result
    minutes = read_one_minute(day)[symbol]
    buckets = defaultdict(list)
    size = TIMEFRAMES[timeframe]
    for minute in official_minutes(day):
        row = minutes.get(minute.isoformat())
        if row is None:
            raise ValueError(f"missing 1m minute for {symbol}: {minute.isoformat()}")
        buckets[_bucket(minute, size).isoformat()].append(row)
    return [_aggregate(buckets[k], timeframe) for k in sorted(buckets)]


def build_daily(day, symbol):
    return [_aggregate(read_one_minute(day)[symbol].values(), "1D")]


def build_weekly(days, symbol):
    rows = []
    for day in sorted(days):
        rows.extend(build_daily(day, symbol))
    by_week = defaultdict(list)
    for row in rows:
        ts = datetime.fromisoformat(row["timestamp"])
        monday = (ts - timedelta(days=ts.weekday())).date()
        by_week[monday.isoformat()].append(row)
    result = []
    for key in sorted(by_week):
        result.append(_aggregate(by_week[key], "1W", require_complete=False))
    return result


def validate_candle(candle):
    ts = datetime.fromisoformat(candle["timestamp"])
    if ts.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    o, h, l, c, v = (candle.get(k) for k in ("open", "high", "low", "close", "volume"))
    if any(x is None for x in (o, h, l, c, v)) or v < 0:
        raise ValueError("OHLCV contains null/invalid values")
    if h < max(o, c) or l > min(o, c) or l > h:
        raise ValueError("OHLC integrity violation")
    return True


def persist(symbol, timeframe, candles):
    VAULT.mkdir(parents=True, exist_ok=True)
    path = VAULT / f"{symbol}_{timeframe}.jsonl"
    seen = set()
    if path.exists():
        seen = {json.loads(x)["timestamp"] for x in path.read_text().splitlines() if x.strip()}
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


def _dhan_post(url, payload):
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


def normalize_dhan(body, symbol, timeframe):
    keys = ("timestamp", "open", "high", "low", "close", "volume")
    if any(k not in body for k in keys):
        raise ValueError("historical response missing OHLCV arrays")
    n = len(body["timestamp"])
    if not all(len(body[k]) == n for k in keys):
        raise ValueError("historical OHLCV array length mismatch")
    result = []
    for i in range(n):
        ts = datetime.fromtimestamp(int(body["timestamp"][i]), tz=timezone.utc).astimezone(IST)
        candle = {"timeframe": timeframe, "timestamp": ts.isoformat(), "open": float(body["open"][i]),
                  "high": float(body["high"][i]), "low": float(body["low"][i]), "close": float(body["close"][i]),
                  "volume": float(body["volume"][i]), "source": "DHAN_HISTORICAL", "complete": True, "symbol": symbol}
        validate_candle(candle)
        result.append(candle)
    return result


def historical_backfill(security_id, symbol, from_date, to_date, interval=1):
    payload = {"securityId": str(security_id), "exchangeSegment": "NSE_EQ", "instrument": "EQUITY",
               "interval": str(interval), "oi": False, "fromDate": from_date, "toDate": to_date}
    body = _dhan_post(DHAN_INTRADAY, payload)
    timeframe = "1h" if interval == 60 else f"{interval}m"
    return normalize_dhan(body, symbol, timeframe)


def historical_daily_backfill(security_id, symbol, from_date, to_date):
    payload = {"securityId": str(security_id), "exchangeSegment": "NSE_EQ", "instrument": "EQUITY",
               "expiryCode": 0, "oi": False, "fromDate": from_date, "toDate": to_date}
    return normalize_dhan(_dhan_post(DHAN_DAILY, payload), symbol, "1D")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--timeframe", choices=["1m", "5m", "15m", "1h", "1D"], default="1m")
    args = parser.parse_args()
    day = datetime.strptime(args.date, "%Y-%m-%d").date()
    candles = build_daily(day, args.symbol) if args.timeframe == "1D" else build_intraday(day, args.symbol, args.timeframe)
    persist(args.symbol, args.timeframe, candles)
    print(f"PHASE4 OK: {args.symbol} {args.timeframe} {len(candles)} candles persisted")


if __name__ == "__main__":
    main()
