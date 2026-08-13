#!/usr/bin/env python3
"""PSY29 Stage 7 — Research-Conditioned Live Edge Activation Engine.

Eligibility gate only. Never generates or authorizes a trade.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

OUTPUT_STATES = {"EDGE_ACTIVE", "EDGE_INACTIVE", "DATA_STALE", "DATA_INVALID"}
BREAKOUT_REGIMES = {"BULLISH_BREAKOUT_REGIME", "BEARISH_BREAKDOWN_REGIME"}
ALIGNMENT_REGIMES = {
    "BULLISH_ALIGNMENT_REGIME",
    "BEARISH_ALIGNMENT_REGIME",
    "BULLISH_WEAK_ALIGNMENT_REGIME",
    "BEARISH_WEAK_ALIGNMENT_REGIME",
}


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_profiles(path: str, symbols: list[str]) -> dict[str, dict[str, Any]]:
    data = load_json(path)
    rows = data.get("profiles", [])
    if len(rows) != 29:
        raise ValueError(f"Expected 29 Stage 5 profiles; got {len(rows)}")
    profiles = {str(r["symbol"]).upper().strip(): r for r in rows}
    if set(profiles) != set(symbols):
        raise ValueError("Stage 5 profile symbols do not exactly match canonical 29")
    return profiles


def load_contract(path: str) -> dict[str, Any]:
    contract = load_json(path)
    if contract.get("trade_authorization") is not False:
        raise ValueError("Stage 7 contract must hard-lock trade_authorization=false")
    if contract.get("trade_signal_generation") is not False:
        raise ValueError("Stage 7 contract must hard-lock trade_signal_generation=false")
    return contract


def canonical_symbols(path: str) -> list[str]:
    data = load_json(path)
    rows = data.get("universe", [])
    symbols = [str(r.get("symbol", "")).upper().strip() for r in rows]
    if len(symbols) != 29 or len(set(symbols)) != 29:
        raise ValueError("Canonical universe must contain exactly 29 unique symbols")
    if [int(r.get("rank", 0)) for r in rows] != list(range(1, 30)):
        raise ValueError("Canonical ranks must be 1–29")
    return symbols


def activate(regime: str, profile: dict[str, Any], contract: dict[str, Any]) -> tuple[str, str, str]:
    trend_rate = float(profile["trend_rate"])
    or_rate = float(profile["or_continuation_rate"])
    median_trend = float(contract["research_basis"]["cross_stock_reference"]["median_trend_rate"])
    median_or = float(contract["research_basis"]["cross_stock_reference"]["median_or_continuation_rate"])

    if regime in BREAKOUT_REGIMES:
        if or_rate >= median_or:
            return "EDGE_ACTIVE", "OR_CONTINUATION_MATCH", f"OR continuation rate {or_rate:.4f} >= 29-stock median {median_or:.4f}"
        return "EDGE_INACTIVE", "OR_CONTINUATION_BELOW_REFERENCE", f"OR continuation rate {or_rate:.4f} < 29-stock median {median_or:.4f}"

    if regime in ALIGNMENT_REGIMES:
        if trend_rate >= median_trend:
            return "EDGE_ACTIVE", "TREND_RATE_MATCH", f"Trend rate {trend_rate:.4f} >= 29-stock median {median_trend:.4f}"
        return "EDGE_INACTIVE", "TREND_RATE_BELOW_REFERENCE", f"Trend rate {trend_rate:.4f} < 29-stock median {median_trend:.4f}"

    if regime == "NEUTRAL_MIXED_REGIME":
        return "EDGE_INACTIVE", "NO_DIRECTIONAL_REGIME", "Stage 6 produced no directional live regime"

    if regime == "DATA_STALE":
        return "DATA_STALE", "LIVE_DATA_STALE", "Stage 6 marked live data stale"

    if regime == "DATA_INVALID":
        return "DATA_INVALID", "LIVE_DATA_INVALID", "Stage 6 marked live data invalid"

    return "DATA_INVALID", "UNKNOWN_REGIME", f"Unrecognized Stage 6 regime: {regime}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--universe", required=True)
    parser.add_argument("--profiles", required=True)
    parser.add_argument("--contract", required=True)
    parser.add_argument("--regimes", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    symbols = canonical_symbols(args.universe)
    profiles = load_profiles(args.profiles, symbols)
    contract = load_contract(args.contract)
    regimes = pd.read_csv(args.regimes)

    required = {"symbol", "regime", "data_status"}
    missing = required - set(regimes.columns)
    if missing:
        raise ValueError(f"Stage 6 regime output missing fields: {sorted(missing)}")

    regimes["symbol"] = regimes["symbol"].astype(str).str.upper().str.strip()
    if set(regimes["symbol"]) != set(symbols) or len(regimes) != 29 or regimes["symbol"].nunique() != 29:
        raise ValueError("Stage 6 coverage is not exactly the canonical 29")

    results = []
    for symbol in symbols:
        row = regimes.loc[regimes["symbol"] == symbol].iloc[-1]
        profile = profiles[symbol]
        state, reason_code, reason = activate(str(row["regime"]), profile, contract)
        results.append({
            "rank": int(profile["rank"]),
            "symbol": symbol,
            "regime": str(row["regime"]),
            "data_status": str(row["data_status"]),
            "activation": state,
            "reason_code": reason_code,
            "match_reason": reason,
            "trend_rate": float(profile["trend_rate"]),
            "strong_trend_rate": float(profile["strong_trend_rate"]),
            "or_continuation_rate": float(profile["or_continuation_rate"]),
            "median_event_return_pct": float(profile["median_event_return_pct"]),
            "research_profile_source": "config/psy29_edge_profiles_v1.json",
            "research_profile_version": "1.0",
            "trade_authorized": False,
            "trade_signal_generated": False,
        })

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(results).sort_values("rank")
    df.to_csv(out / "PSY29_STAGE7_EDGE_ACTIVATION.csv", index=False)

    validation = (
        len(df) == 29
        and df["symbol"].nunique() == 29
        and set(df["activation"]).issubset(OUTPUT_STATES)
        and (df["trade_authorized"] == False).all()
        and (df["trade_signal_generated"] == False).all()
        and (df["research_profile_source"] == "config/psy29_edge_profiles_v1.json").all()
    )

    summary = {
        "stage": 7,
        "engine": "PSY29_RESEARCH_CONDITIONED_EDGE_ACTIVATION",
        "engine_execution_status": "PASS",
        "validation_status": "PASS" if validation else "FAIL",
        "status": "PASS" if validation else "FAIL",
        "coverage": int(len(df)),
        "edge_active_count": int((df["activation"] == "EDGE_ACTIVE").sum()),
        "edge_inactive_count": int((df["activation"] == "EDGE_INACTIVE").sum()),
        "data_stale_count": int((df["activation"] == "DATA_STALE").sum()),
        "data_invalid_count": int((df["activation"] == "DATA_INVALID").sum()),
        "trade_authorized": False,
        "trade_signal_generated": False,
        "fail_closed": True,
        "research_profile_source": "config/psy29_edge_profiles_v1.json",
    }
    (out / "stage7_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    if not validation:
        raise SystemExit("STAGE 7 VALIDATION FAILED")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
