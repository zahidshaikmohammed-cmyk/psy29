#!/usr/bin/env python3
"""
PSY29 Stage 6 — Live Regime Engine V2

Purpose:
    Classify the current live market regime for the canonical PSY29 29-stock
    universe.

This engine:
    - validates the canonical 29 universe
    - validates DHAN security-ID mapping
    - validates Stage 5 research profiles
    - validates live snapshot freshness
    - validates required live fields
    - classifies market regime
    - FAILS CLOSED on invalid/stale data

This engine DOES NOT:
    - generate trade signals
    - authorize trades
    - select stocks
    - modify Step 2–8 research logic
    - interpret historical probabilities as live probabilities
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


FRESH_MAX_AGE_SECONDS = 90
STALE_MAX_AGE_SECONDS = 180

REQUIRED_LIVE_FIELDS = {
    "symbol", "timestamp", "last_price", "vwap", "ema9", "ema20",
    "first15_high", "first15_low",
}

REQUIRED_SECURITY_FIELDS = {"symbol", "security_id"}

ALLOWED_REGIMES = {
    "BULLISH_BREAKOUT_REGIME", "BEARISH_BREAKDOWN_REGIME",
    "BULLISH_ALIGNMENT_REGIME", "BEARISH_ALIGNMENT_REGIME",
    "BULLISH_WEAK_ALIGNMENT_REGIME", "BEARISH_WEAK_ALIGNMENT_REGIME",
    "NEUTRAL_MIXED_REGIME", "DATA_STALE", "DATA_INVALID",
}


def load_json(path: str | Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def canonical_symbols(universe: dict[str, Any]) -> list[str]:
    rows = universe.get("universe", [])
    symbols = [str(row.get("symbol", "")).upper().strip() for row in rows]
    symbols = [s for s in symbols if s]
    if len(symbols) != 29:
        raise ValueError(f"Canonical universe must contain exactly 29 symbols; got {len(symbols)}")
    if len(set(symbols)) != 29:
        raise ValueError("Canonical universe contains duplicate symbols")
    ranks = [int(row.get("rank", 0)) for row in rows]
    if ranks != list(range(1, 30)):
        raise ValueError("Canonical universe ranks must be exactly 1–29")
    return symbols


def validate_profiles(profiles: dict[str, Any], symbols: list[str]) -> None:
    rows = profiles.get("profiles", [])
    if len(rows) != 29:
        raise ValueError(f"Stage 5 profile count must be 29; got {len(rows)}")
    profile_symbols = [str(row.get("symbol", "")).upper().strip() for row in rows]
    if set(profile_symbols) != set(symbols):
        missing = sorted(set(symbols) - set(profile_symbols))
        unexpected = sorted(set(profile_symbols) - set(symbols))
        raise ValueError(f"Stage 5 profile mismatch; missing={missing}, unexpected={unexpected}")


def validate_security_map(security_map: dict[str, Any], symbols: list[str]) -> dict[str, str]:
    rows = security_map.get("mappings", [])
    if len(rows) != 29:
        raise ValueError(f"Security-ID map must contain exactly 29 mappings; got {len(rows)}")
    mapping: dict[str, str] = {}
    for row in rows:
        symbol = str(row.get("symbol", "")).upper().strip()
        security_id = str(row.get("security_id", "")).strip()
        if not symbol:
            raise ValueError("Security-ID map contains empty symbol")
        if not security_id:
            raise ValueError(f"Missing security_id for {symbol}")
        if symbol in mapping:
            raise ValueError(f"Duplicate security mapping for {symbol}")
        mapping[symbol] = security_id
    if set(mapping) != set(symbols):
        missing = sorted(set(symbols) - set(mapping))
        unexpected = sorted(set(mapping) - set(symbols))
        raise ValueError(f"Security-ID universe mismatch; missing={missing}, unexpected={unexpected}")
    if len(set(mapping.values())) != 29:
        raise ValueError("Security IDs are not unique")
    return mapping


def parse_timestamp(value: Any) -> datetime:
    if value is None:
        raise ValueError("Missing timestamp")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    text = str(value).strip()
    if not text:
        raise ValueError("Empty timestamp")
    dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("Timestamp must be timezone-aware")
    return dt.astimezone(timezone.utc)


def data_age_seconds(value: Any, now: datetime) -> float:
    timestamp = parse_timestamp(value)
    age = (now - timestamp).total_seconds()
    if age < -5:
        raise ValueError("Timestamp is materially in the future")
    return max(0.0, age)


def finite_number(value: Any) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("Non-finite numeric value")
    return number


def classify_regime(row: pd.Series) -> str:
    """Regime classification only. No trade authorization occurs here."""
    price = finite_number(row["last_price"])
    vwap = finite_number(row["vwap"])
    ema9 = finite_number(row["ema9"])
    ema20 = finite_number(row["ema20"])
    first15_high = finite_number(row["first15_high"])
    first15_low = finite_number(row["first15_low"])

    above_vwap = price > vwap
    below_vwap = price < vwap
    ema_bullish = ema9 > ema20
    ema_bearish = ema9 < ema20
    breakout_up = price > first15_high
    breakdown_down = price < first15_low
    bullish_score = int(above_vwap) + int(ema_bullish)
    bearish_score = int(below_vwap) + int(ema_bearish)

    if bullish_score == 2 and breakout_up:
        return "BULLISH_BREAKOUT_REGIME"
    if bearish_score == 2 and breakdown_down:
        return "BEARISH_BREAKDOWN_REGIME"
    if bullish_score == 2:
        return "BULLISH_ALIGNMENT_REGIME"
    if bearish_score == 2:
        return "BEARISH_ALIGNMENT_REGIME"
    if bullish_score == 1 and bearish_score == 0:
        return "BULLISH_WEAK_ALIGNMENT_REGIME"
    if bearish_score == 1 and bullish_score == 0:
        return "BEARISH_WEAK_ALIGNMENT_REGIME"
    return "NEUTRAL_MIXED_REGIME"


def validate_snapshot_columns(snapshot: pd.DataFrame) -> None:
    missing = REQUIRED_LIVE_FIELDS - set(snapshot.columns)
    if missing:
        raise ValueError(f"Live snapshot missing required fields: {sorted(missing)}")


def process(universe_path: str, profiles_path: str, security_map_path: str,
            snapshot_path: str, output_dir: str) -> dict[str, Any]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    universe = load_json(universe_path)
    profiles = load_json(profiles_path)
    security_map = load_json(security_map_path)

    symbols = canonical_symbols(universe)
    validate_profiles(profiles, symbols)
    resolved_security_ids = validate_security_map(security_map, symbols)
    snapshot = pd.read_csv(snapshot_path)
    validate_snapshot_columns(snapshot)

    snapshot["symbol"] = snapshot["symbol"].astype(str).str.upper().str.strip()
    unknown_symbols = sorted(set(snapshot["symbol"]) - set(symbols))
    if unknown_symbols:
        raise ValueError(f"Live snapshot contains symbols outside canonical 29: {unknown_symbols}")

    snapshot = snapshot.sort_values("timestamp").drop_duplicates(subset=["symbol"], keep="last")
    now = datetime.now(timezone.utc)
    profile_by_symbol = {str(row["symbol"]).upper().strip(): row for row in profiles["profiles"]}
    results: list[dict[str, Any]] = []

    for symbol in symbols:
        result: dict[str, Any] = {
            "symbol": symbol,
            "security_id": resolved_security_ids[symbol],
            "regime": "DATA_INVALID",
            "data_status": "INVALID",
            "data_age_seconds": None,
            "profile_attached": symbol in profile_by_symbol,
            "trade_authorized": False,
            "trade_signal_generated": False,
            "reason": None,
        }

        rows = snapshot[snapshot["symbol"] == symbol]
        if rows.empty:
            result["reason"] = "MISSING_LIVE_SNAPSHOT"
            results.append(result)
            continue

        row = rows.iloc[-1]
        try:
            age = data_age_seconds(row["timestamp"], now)
            result["data_age_seconds"] = round(age, 3)

            if age > STALE_MAX_AGE_SECONDS:
                result["reason"] = "DATA_OLDER_THAN_180_SECONDS"
                results.append(result)
                continue

            if age > FRESH_MAX_AGE_SECONDS:
                result["regime"] = "DATA_STALE"
                result["data_status"] = "STALE"
                result["reason"] = "DATA_OLDER_THAN_90_SECONDS"
                results.append(result)
                continue

            for field in REQUIRED_LIVE_FIELDS - {"symbol", "timestamp"}:
                finite_number(row[field])

            price = finite_number(row["last_price"])
            high = finite_number(row["first15_high"])
            low = finite_number(row["first15_low"])
            if price <= 0:
                raise ValueError("last_price must be positive")
            if high < low:
                raise ValueError("first15_high is below first15_low")

            result["regime"] = classify_regime(row)
            result["data_status"] = "FRESH"
            result["reason"] = "VALID_LIVE_DATA"
        except Exception as exc:
            result["reason"] = str(exc)

        results.append(result)

    output = pd.DataFrame(results)
    output["trade_authorized"] = False
    output["trade_signal_generated"] = False
    output.to_csv(out / "PSY29_STAGE6_LIVE_REGIMES.csv", index=False)

    fresh_count = int((output["data_status"] == "FRESH").sum())
    stale_count = int((output["data_status"] == "STALE").sum())
    invalid_count = int((output["data_status"] == "INVALID").sum())

    # Execution and validation are deliberately separate. The engine can execute
    # successfully while the data validation fails; overall status must not hide that.
    engine_execution_status = "PASS"
    validation_status = "PASS" if invalid_count == 0 and stale_count == 0 and fresh_count == 29 else "FAIL"

    summary = {
        "stage": 6,
        "engine": "PSY29_LIVE_REGIME_ENGINE_V2",
        "status": validation_status,
        "engine_execution_status": engine_execution_status,
        "validation_status": validation_status,
        "universe_size": len(symbols),
        "profiles_verified": len(profile_by_symbol),
        "security_ids_verified": len(resolved_security_ids),
        "fresh_count": fresh_count,
        "stale_count": stale_count,
        "invalid_count": invalid_count,
        "regime_counts": {regime: int((output["regime"] == regime).sum()) for regime in sorted(ALLOWED_REGIMES)},
        "trade_authorized": False,
        "trade_signal_generated": False,
        "fail_closed": True,
    }

    (out / "stage6_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--universe", required=True)
    parser.add_argument("--profiles", required=True)
    parser.add_argument("--security-map", required=True)
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    summary = process(args.universe, args.profiles, args.security_map, args.snapshot, args.output)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
