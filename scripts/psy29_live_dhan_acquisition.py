#!/usr/bin/env python3
"""PSY29-only live DHAN acquisition and validation layer.

This module is the sole live-market input boundary for PSY29.
It reads the locked 29-stock universe and DHAN credentials from the PSY29
runtime, resolves NSE equity security IDs using the PSY29 instrument master,
fetches current-day 1-minute candles from DHAN, and derives the exact live
snapshot fields required by the locked PSY29 live-data contract.

It does not generate trade signals, calculate entries, stops or targets, or
place orders.
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests

from dhan.client import DhanClient

IST = ZoneInfo("Asia/Kolkata")
MASTER_URL = "https://images.dhan.co/api-data/api-scrip-master-detailed.csv"
FRESH_MAX_AGE_SECONDS = 90
STALE_MAX_AGE_SECONDS = 180
REQUIRED_SNAPSHOT = {
    "symbol", "timestamp", "last_price", "vwap", "ema9", "ema20",
    "first15_high", "first15_low",
}


def load_universe(path: str) -> list[str]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = data.get("universe", [])
    symbols = [str(x["symbol"]).strip().upper() for x in rows]
    if len(symbols) != 29 or len(set(symbols)) != 29:
        raise RuntimeError("Canonical live universe must contain exactly 29 unique symbols")
    return symbols


def resolve_security_ids(symbols: list[str]) -> dict[str, str]:
    response = requests.get(MASTER_URL, timeout=90)
    response.raise_for_status()
    master = pd.read_csv(StringIO(response.text), low_memory=False)
    if "EXCH_ID" not in master or "SEGMENT" not in master:
        raise RuntimeError("DHAN instrument master missing EXCH_ID/SEGMENT")
    sym_col = next((c for c in ("UNDERLYING_SYMBOL", "SEM_TRADING_SYMBOL", "SYMBOL_NAME", "DISPLAY_NAME") if c in master), None)
    id_col = next((c for c in ("SECURITY_ID", "SECURITYID") if c in master), None)
    if not sym_col or not id_col:
        raise RuntimeError("DHAN instrument master lacks supported symbol/security-id columns")
    eq = master[(master["EXCH_ID"] == "NSE") & (master["SEGMENT"] == "E")].copy()
    eq["_symbol"] = eq[sym_col].astype(str).str.upper().str.strip()
    eq["_id"] = eq[id_col].astype(str).str.strip()
    mapping: dict[str, str] = {}
    failures = []
    for symbol in symbols:
        ids = sorted(set(eq.loc[(eq["_symbol"] == symbol) & (eq["_id"] != ""), "_id"].tolist()))
        if len(ids) != 1:
            failures.append({"symbol": symbol, "security_ids": ids})
        else:
            mapping[symbol] = ids[0]
    if failures:
        raise RuntimeError(f"Security-ID resolution failed: {failures}")
    if len(mapping) != 29 or len(set(mapping.values())) != 29:
        raise RuntimeError("Security-ID map is not exactly 29 unique NSE equities")
    return mapping


def parse_rows(obj: dict) -> pd.DataFrame:
    data = obj.get("data", obj) if isinstance(obj, dict) else obj
    if not isinstance(data, dict) or not data.get("timestamp"):
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
    n = len(data["timestamp"])
    rows = []
    for i in range(n):
        row = {"timestamp": int(float(data["timestamp"][i]))}
        for k in ("open", "high", "low", "close", "volume"):
            if k in data and i < len(data[k]):
                row[k] = float(data[k][i])
        rows.append(row)
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.sort_values("timestamp").drop_duplicates("timestamp", keep="last").reset_index(drop=True)


def fetch_1m(client: DhanClient, security_id: str, now: datetime) -> pd.DataFrame:
    start = now.replace(hour=9, minute=0, second=0, microsecond=0)
    payload = {
        "securityId": str(security_id),
        "exchangeSegment": "NSE_EQ",
        "instrument": "EQUITY",
        "interval": "1",
        "oi": False,
        "fromDate": start.strftime("%Y-%m-%d %H:%M:%S"),
        "toDate": now.strftime("%Y-%m-%d %H:%M:%S"),
    }
    return parse_rows(client.post("/charts/intraday", payload, timeout=20, retries=2))


def epoch_to_ist(ts: int) -> datetime:
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).astimezone(IST)


def ema(series: pd.Series, period: int) -> float | None:
    if len(series) < period:
        return None
    return float(series.ewm(span=period, adjust=False).mean().iloc[-1])


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    x = df.copy()
    x["dt"] = x["timestamp"].map(epoch_to_ist)
    x = x[(x["dt"].dt.time >= datetime.strptime("09:15", "%H:%M").time()) & (x["dt"].dt.time <= datetime.strptime("15:30", "%H:%M").time())].copy()
    if x.empty:
        return x
    typical = (x["high"] + x["low"] + x["close"]) / 3.0
    vol = x["volume"].clip(lower=0)
    cumulative_vol = vol.cumsum()
    x["vwap"] = (typical * vol).cumsum() / cumulative_vol.replace(0, math.nan)
    x["ema9"] = x["close"].ewm(span=9, adjust=False).mean()
    x["ema20"] = x["close"].ewm(span=20, adjust=False).mean()
    opening = x[x["dt"].dt.time <= datetime.strptime("09:29", "%H:%M").time()]
    if opening.empty:
        opening = x.head(15)
    first15_high = float(opening["high"].max())
    first15_low = float(opening["low"].min())
    x["first15_high"] = first15_high
    x["first15_low"] = first15_low
    return x


def build_execution_row(symbol: str, df: pd.DataFrame, timestamp: str) -> dict:
    if len(df) < 20:
        raise RuntimeError(f"{symbol}: fewer than 20 live 1m candles")
    x = df.copy()
    x["bucket"] = x["dt"].dt.floor("5min")
    bars = x.groupby("bucket", sort=True).agg(
        open=("open", "first"), high=("high", "max"), low=("low", "min"),
        close=("close", "last"), volume=("volume", "sum"),
    ).reset_index()
    if len(bars) < 20:
        raise RuntimeError(f"{symbol}: fewer than 20 derived 5m candles")
    latest = x.iloc[-1]
    b5 = bars.iloc[-1]
    vol1 = float(latest["volume"])
    avg1 = float(x["volume"].tail(20).mean())
    avg5 = float(bars["volume"].tail(20).mean())
    recent = bars.tail(20)
    return {
        "symbol": symbol,
        "timestamp": timestamp,
        "open_1m": float(latest["open"]), "high_1m": float(latest["high"]),
        "low_1m": float(latest["low"]), "close_1m": float(latest["close"]),
        "volume_1m": vol1, "avg_volume_20_1m": avg1,
        "open_5m": float(b5["open"]), "high_5m": float(b5["high"]),
        "low_5m": float(b5["low"]), "close_5m": float(b5["close"]),
        "volume_5m": float(b5["volume"]), "avg_volume_20_5m": avg5,
        "vwap_5m": float(latest["vwap"]), "ema9_5m": float(latest["ema9"]),
        "ema20_5m": float(latest["ema20"]),
        "first15_high": float(latest["first15_high"]),
        "first15_low": float(latest["first15_low"]),
        "swing_high": float(recent["high"].max()),
        "swing_low": float(recent["low"].min()),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--universe", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    symbols = load_universe(args.universe)
    client = DhanClient()
    mapping = resolve_security_ids(symbols)
    now = datetime.now(IST)
    now_utc = now.astimezone(timezone.utc)

    snapshot_rows = []
    execution_rows = []
    errors = []
    for symbol in symbols:
        try:
            raw = fetch_1m(client, mapping[symbol], now)
            x = add_indicators(raw)
            if x.empty:
                raise RuntimeError("no current-session candles returned")
            latest_ts = int(x.iloc[-1]["timestamp"])
            age = (now_utc - datetime.fromtimestamp(latest_ts, tz=timezone.utc)).total_seconds()
            if age < -5:
                raise RuntimeError("provider returned a future timestamp")
            snapshot_rows.append({
                "symbol": symbol,
                "timestamp": datetime.fromtimestamp(latest_ts, tz=timezone.utc).isoformat().replace("+00:00", "Z"),
                "last_price": float(x.iloc[-1]["close"]),
                "vwap": float(x.iloc[-1]["vwap"]),
                "ema9": float(x.iloc[-1]["ema9"]),
                "ema20": float(x.iloc[-1]["ema20"]),
                "first15_high": float(x.iloc[-1]["first15_high"]),
                "first15_low": float(x.iloc[-1]["first15_low"]),
                "freshness_age_seconds": round(max(0.0, age), 3),
                "freshness_status": "FRESH" if age <= FRESH_MAX_AGE_SECONDS else ("STALE" if age <= STALE_MAX_AGE_SECONDS else "INVALID"),
                "provider": "DHAN",
                "security_id": mapping[symbol],
                "exchange_segment": "NSE_EQ",
            })
            execution_rows.append(build_execution_row(symbol, x, snapshot_rows[-1]["timestamp"]))
        except Exception as exc:
            errors.append({"symbol": symbol, "error": str(exc)})

    snapshot = pd.DataFrame(snapshot_rows)
    execution = pd.DataFrame(execution_rows)
    if not snapshot.empty:
        snapshot.to_csv(out / "live_snapshot.csv", index=False)
    if not execution.empty:
        execution.to_csv(out / "execution_snapshot.csv", index=False)

    status = "PASS" if len(snapshot_rows) == 29 and not errors and set(snapshot.columns) >= REQUIRED_SNAPSHOT and (snapshot["freshness_status"] == "FRESH").all() else "FAIL"
    validation = {
        "contract": "PSY29_LIVE_DHAN_ACQUISITION_VALIDATION",
        "status": status,
        "provider": "DHAN",
        "coverage": {"expected": 29, "actual": len(snapshot_rows), "unique": int(snapshot["symbol"].nunique()) if not snapshot.empty else 0},
        "fresh_count": int((snapshot["freshness_status"] == "FRESH").sum()) if not snapshot.empty else 0,
        "stale_count": int((snapshot["freshness_status"] == "STALE").sum()) if not snapshot.empty else 0,
        "invalid_count": int((snapshot["freshness_status"] == "INVALID").sum()) if not snapshot.empty else 0,
        "errors": errors,
        "timestamp": now_utc.isoformat().replace("+00:00", "Z"),
        "source": "PSY29/dhan/client.py + PSY29/dhan/instruments.py",
        "signal_generation": False,
        "order_execution": False,
    }
    (out / "live_acquisition_validation.json").write_text(json.dumps(validation, indent=2), encoding="utf-8")
    (out / "security_map.json").write_text(json.dumps({"status": "PASS", "canonical_count": 29, "mapping": [{"symbol": s, "security_id": mapping[s], "exchange_segment": "NSE_EQ"} for s in symbols]}, indent=2), encoding="utf-8")
    print(json.dumps(validation, indent=2))
    if status != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
