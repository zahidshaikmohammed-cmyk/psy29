#!/usr/bin/env python3
"""PSY29 live DHAN acquisition with completed-candle and indicator integrity gates."""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timedelta, timezone, time as dtime
from io import StringIO
from pathlib import Path
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pandas as pd
import requests
from dhan.client import DhanClient

IST = ZoneInfo("Asia/Kolkata")
MASTER_URL = "https://images.dhan.co/api-data/api-scrip-master-detailed.csv"
FRESH_MAX_AGE_SECONDS = 90
WARMUP_CALENDAR_DAYS = 10
SESSION_OPEN = dtime(9, 15)
SESSION_CLOSE = dtime(15, 30)
OPENING_RANGE_END = dtime(9, 30)
REQUIRED_SNAPSHOT = {"symbol", "timestamp", "last_price", "vwap", "ema9", "ema20", "first15_high", "first15_low"}


def load_universe(path: str) -> list[str]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    symbols = [str(x["symbol"]).strip().upper() for x in data.get("universe", [])]
    ranks = [int(x.get("rank", 0)) for x in data.get("universe", [])]
    if len(symbols) != 29 or len(set(symbols)) != 29 or ranks != list(range(1, 30)):
        raise RuntimeError("Canonical live universe must contain exactly 29 unique ranked symbols")
    return symbols


def resolve_security_ids(symbols: list[str]) -> dict[str, str]:
    response = requests.get(MASTER_URL, timeout=90)
    response.raise_for_status()
    master = pd.read_csv(StringIO(response.text), low_memory=False)
    sym_col = next((c for c in ("UNDERLYING_SYMBOL", "SEM_TRADING_SYMBOL", "SYMBOL_NAME", "DISPLAY_NAME") if c in master), None)
    id_col = next((c for c in ("SECURITY_ID", "SECURITYID") if c in master), None)
    if "EXCH_ID" not in master or "SEGMENT" not in master or not sym_col or not id_col:
        raise RuntimeError("DHAN instrument master lacks required NSE equity fields")
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
    if failures or len(mapping) != 29 or len(set(mapping.values())) != 29:
        raise RuntimeError(f"Security-ID resolution failed: {failures}")
    return mapping


def parse_rows(obj: dict) -> pd.DataFrame:
    data = obj.get("data", obj) if isinstance(obj, dict) else obj
    if not isinstance(data, dict) or not data.get("timestamp"):
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
    n = len(data["timestamp"])
    rows = []
    for i in range(n):
        row = {"timestamp": int(float(data["timestamp"][i]))}
        for key in ("open", "high", "low", "close", "volume"):
            if key not in data or i >= len(data[key]):
                raise RuntimeError(f"DHAN candle field length mismatch: {key}")
            row[key] = float(data[key][i])
        rows.append(row)
    return pd.DataFrame(rows).sort_values("timestamp").drop_duplicates("timestamp", keep="last").reset_index(drop=True)


def fetch_bars(client: DhanClient, security_id: str, now: datetime, interval: str) -> pd.DataFrame:
    # Warm-up prevents EMA/20-volume statistics from being re-initialized at 09:15.
    start = now - timedelta(days=WARMUP_CALENDAR_DAYS)
    start = start.replace(hour=9, minute=15, second=0, microsecond=0)
    payload = {"securityId": str(security_id), "exchangeSegment": "NSE_EQ", "instrument": "EQUITY", "interval": interval, "oi": False, "fromDate": start.strftime("%Y-%m-%d %H:%M:%S"), "toDate": now.strftime("%Y-%m-%d %H:%M:%S")}
    return parse_rows(client.post("/charts/intraday", payload, timeout=20, retries=2))


def epoch_to_ist(ts: int) -> datetime:
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).astimezone(IST)


def validate_ohlcv(df: pd.DataFrame, name: str) -> None:
    if df.empty:
        raise RuntimeError(f"{name}: no candles")
    for col in ("open", "high", "low", "close", "volume"):
        if not pd.to_numeric(df[col], errors="coerce").notna().all():
            raise RuntimeError(f"{name}: non-numeric {col}")
    if (df[["open", "high", "low", "close"]] <= 0).any().any():
        raise RuntimeError(f"{name}: non-positive price")
    if (df["volume"] < 0).any():
        raise RuntimeError(f"{name}: negative volume")
    if (df["high"] < df[["open", "close", "low"]].max(axis=1)).any():
        raise RuntimeError(f"{name}: high below an OHLC component")
    if (df["low"] > df[["open", "close", "high"]].min(axis=1)).any():
        raise RuntimeError(f"{name}: low above an OHLC component")


def completed_candles(df: pd.DataFrame, interval_minutes: int, now: datetime) -> pd.DataFrame:
    x = df.copy()
    x["dt"] = x["timestamp"].map(epoch_to_ist)
    cutoff = now.astimezone(IST)
    # DHAN timestamps identify candle timestamps; require the full interval to elapse.
    x = x[x["dt"].map(lambda d: d + timedelta(minutes=interval_minutes) <= cutoff)].copy()
    return x.sort_values("timestamp").drop_duplicates("timestamp", keep="last").reset_index(drop=True)


def current_session(df: pd.DataFrame, session_date) -> pd.DataFrame:
    x = df[(df["dt"].dt.date == session_date) & (df["dt"].dt.time >= SESSION_OPEN) & (df["dt"].dt.time <= SESSION_CLOSE)].copy()
    return x.sort_values("timestamp").reset_index(drop=True)


def add_indicators_1m(df: pd.DataFrame, session_date, now: datetime) -> pd.DataFrame:
    x = completed_candles(df, 1, now)
    validate_ohlcv(x, "1m history")
    x["ema9_all"] = x["close"].ewm(span=9, adjust=False).mean()
    x["ema20_all"] = x["close"].ewm(span=20, adjust=False).mean()
    cur = current_session(x, session_date)
    if cur.empty:
        return cur
    typical = (cur["high"] + cur["low"] + cur["close"]) / 3.0
    volume = cur["volume"].clip(lower=0)
    cur["vwap"] = (typical * volume).cumsum() / volume.cumsum().replace(0, math.nan)
    cur["ema9"] = cur["ema9_all"]
    cur["ema20"] = cur["ema20_all"]
    opening = cur[cur["dt"].dt.time < OPENING_RANGE_END]
    if len(opening) < 15:
        cur["opening_range_complete"] = False
        return cur
    cur["first15_high"] = float(opening["high"].max())
    cur["first15_low"] = float(opening["low"].min())
    cur["opening_range_complete"] = True
    return cur


def add_indicators_5m(df: pd.DataFrame, session_date, now: datetime) -> pd.DataFrame:
    x = completed_candles(df, 5, now)
    validate_ohlcv(x, "5m history")
    x["ema9_all"] = x["close"].ewm(span=9, adjust=False).mean()
    x["ema20_all"] = x["close"].ewm(span=20, adjust=False).mean()
    cur = current_session(x, session_date)
    if cur.empty:
        return cur
    typical = (cur["high"] + cur["low"] + cur["close"]) / 3.0
    volume = cur["volume"].clip(lower=0)
    cur["vwap5"] = (typical * volume).cumsum() / volume.cumsum().replace(0, math.nan)
    cur["ema9_5m"] = cur["ema9_all"]
    cur["ema20_5m"] = cur["ema20_all"]
    return cur


def build_execution_row(symbol: str, security_id: str, x1: pd.DataFrame, x5: pd.DataFrame, all1: pd.DataFrame, all5: pd.DataFrame, timestamp: str) -> dict:
    if x1.empty or x5.empty:
        raise RuntimeError(f"{symbol}: no completed current-session candles")
    if not bool(x1.iloc[-1]["opening_range_complete"]):
        raise RuntimeError(f"{symbol}: opening range incomplete before 09:30 IST")
    latest = x1.iloc[-1]
    latest5 = x5.iloc[-1]
    prior5 = x5.iloc[:-1].tail(20)
    if prior5.empty:
        prior5 = x5.tail(1)
    avg1 = all1["volume"].tail(20).mean()
    avg5 = all5["volume"].tail(20).mean()
    if not math.isfinite(float(avg1)) or not math.isfinite(float(avg5)) or float(avg1) <= 0 or float(avg5) <= 0:
        raise RuntimeError(f"{symbol}: insufficient warm-up volume history")
    return {
        "symbol": symbol, "security_id": security_id, "exchange_segment": "NSE_EQ", "timestamp": timestamp,
        "last_price": float(latest["close"]), "vwap": float(latest["vwap"]), "ema9": float(latest["ema9"]), "ema20": float(latest["ema20"]),
        "open_1m": float(latest["open"]), "high_1m": float(latest["high"]), "low_1m": float(latest["low"]), "close_1m": float(latest["close"]), "volume_1m": float(latest["volume"]), "avg_volume_20_1m": float(avg1),
        "open_5m": float(latest5["open"]), "high_5m": float(latest5["high"]), "low_5m": float(latest5["low"]), "close_5m": float(latest5["close"]), "volume_5m": float(latest5["volume"]), "avg_volume_20_5m": float(avg5),
        "vwap_5m": float(latest5["vwap5"]), "ema9_5m": float(latest5["ema9_5m"]), "ema20_5m": float(latest5["ema20_5m"]),
        "first15_high": float(latest["first15_high"]), "first15_low": float(latest["first15_low"]), "swing_high": float(prior5["high"].max()), "swing_low": float(prior5["low"].min()),
        "freshness_status": "FRESH", "indicator_warmup": "10_CALENDAR_DAYS", "candle_completion_policy": "COMPLETED_CANDLES_ONLY",
    }


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--universe", required=True); parser.add_argument("--output", required=True); args = parser.parse_args()
    out = Path(args.output); out.mkdir(parents=True, exist_ok=True); symbols = load_universe(args.universe)
    client = DhanClient(); mapping = resolve_security_ids(symbols); now = datetime.now(IST); session_date = now.date()
    snapshot_rows = []; execution_rows = []; errors = []
    for symbol in symbols:
        try:
            raw1 = fetch_bars(client, mapping[symbol], now, "1"); raw5 = fetch_bars(client, mapping[symbol], now, "5")
            x1 = add_indicators_1m(raw1, session_date, now); x5 = add_indicators_5m(raw5, session_date, now)
            if x1.empty or x5.empty: raise RuntimeError("no current-session completed candles returned")
            if not bool(x1.iloc[-1]["opening_range_complete"]): raise RuntimeError("OPENING_RANGE_INCOMPLETE")
            latest_ts = int(x1.iloc[-1]["timestamp"]); observed_utc = datetime.now(timezone.utc)
            age = (observed_utc - datetime.fromtimestamp(latest_ts, tz=timezone.utc)).total_seconds()
            if age < -5: raise RuntimeError("provider returned a future timestamp")
            if age > FRESH_MAX_AGE_SECONDS: raise RuntimeError(f"live data freshness is STALE: {age:.1f}s")
            ts = datetime.fromtimestamp(latest_ts, tz=timezone.utc).isoformat().replace("+00:00", "Z")
            snapshot_rows.append({"symbol": symbol, "timestamp": ts, "last_price": float(x1.iloc[-1]["close"]), "vwap": float(x1.iloc[-1]["vwap"]), "ema9": float(x1.iloc[-1]["ema9"]), "ema20": float(x1.iloc[-1]["ema20"]), "first15_high": float(x1.iloc[-1]["first15_high"]), "first15_low": float(x1.iloc[-1]["first15_low"]), "freshness_age_seconds": round(max(0.0, age), 3), "freshness_status": "FRESH", "provider": "DHAN", "security_id": mapping[symbol], "exchange_segment": "NSE_EQ", "indicator_warmup": "10_CALENDAR_DAYS", "candle_completion_policy": "COMPLETED_CANDLES_ONLY", "opening_range_complete": True})
            all1 = completed_candles(raw1, 1, now); all5 = completed_candles(raw5, 5, now)
            execution_rows.append(build_execution_row(symbol, mapping[symbol], x1, x5, all1, all5, ts))
        except Exception as exc:
            errors.append({"symbol": symbol, "error": str(exc)})
    snapshot = pd.DataFrame(snapshot_rows); execution = pd.DataFrame(execution_rows)
    if not snapshot.empty: snapshot.to_csv(out / "live_snapshot.csv", index=False)
    if not execution.empty: execution.to_csv(out / "execution_snapshot.csv", index=False)
    status = "PASS" if len(snapshot_rows) == 29 and len(execution_rows) == 29 and not errors and set(snapshot.columns) >= REQUIRED_SNAPSHOT and (snapshot["freshness_status"] == "FRESH").all() and (snapshot["opening_range_complete"] == True).all() else "FAIL"
    validation = {"contract": "PSY29_LIVE_DHAN_ACQUISITION_VALIDATION", "status": status, "provider": "DHAN", "coverage": {"expected": 29, "actual": len(snapshot_rows), "unique": int(snapshot["symbol"].nunique()) if not snapshot.empty else 0}, "fresh_count": int((snapshot["freshness_status"] == "FRESH").sum()) if not snapshot.empty else 0, "stale_count": 0, "invalid_count": 0, "errors": errors, "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), "source": "PSY29/dhan/client.py + DHAN v2 intraday historical data", "indicator_warmup": "10_CALENDAR_DAYS", "candle_completion_policy": "COMPLETED_CANDLES_ONLY", "opening_range_policy": "09:15-09:29 IST, complete before pipeline acceptance", "signal_generation": False, "order_execution": False}
    (out / "live_acquisition_validation.json").write_text(json.dumps(validation, indent=2), encoding="utf-8")
    (out / "security_map.json").write_text(json.dumps({"status": "PASS", "canonical_count": 29, "resolved_count": 29, "unique_security_id_count": 29, "mappings": [{"symbol": s, "security_id": mapping[s], "exchange": "NSE", "segment": "E", "exchange_segment": "NSE_EQ"} for s in symbols]}, indent=2), encoding="utf-8")
    print(json.dumps(validation, indent=2))
    if status != "PASS": raise SystemExit(1)


if __name__ == "__main__": main()
