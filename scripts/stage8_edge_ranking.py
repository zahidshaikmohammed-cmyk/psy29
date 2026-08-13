#!/usr/bin/env python3
"""PSY29 Stage 8 — Portfolio-Level Edge Ranking and Prioritization.

Ranks only stocks already marked EDGE_ACTIVE by Stage 7.
Never generates or authorizes a trade.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

STATES = {"EDGE_ACTIVE", "EDGE_INACTIVE", "DATA_STALE", "DATA_INVALID"}
LIVE_QUALITY = {
    "BULLISH_BREAKOUT_REGIME": 1.00,
    "BEARISH_BREAKDOWN_REGIME": 1.00,
    "BULLISH_ALIGNMENT_REGIME": 0.85,
    "BEARISH_ALIGNMENT_REGIME": 0.85,
    "BULLISH_WEAK_ALIGNMENT_REGIME": 0.65,
    "BEARISH_WEAK_ALIGNMENT_REGIME": 0.65,
}
REFS = {
    "trend_rate": 0.2875,
    "or_continuation_rate": 0.375,
    "strong_trend_rate": 0.175,
    "median_event_return_pct": 2.69,
}
WEIGHTS = {
    "trend_rate": 0.35,
    "or_continuation_rate": 0.25,
    "strong_trend_rate": 0.20,
    "median_event_return_pct": 0.20,
}


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def canonical_symbols(path: str) -> list[str]:
    rows = load_json(path).get("universe", [])
    symbols = [str(r.get("symbol", "")).upper().strip() for r in rows]
    if len(symbols) != 29 or len(set(symbols)) != 29:
        raise ValueError("Canonical universe must contain exactly 29 unique symbols")
    if [int(r.get("rank", 0)) for r in rows] != list(range(1, 30)):
        raise ValueError("Canonical ranks must be 1–29")
    return symbols


def validate_contract(contract: dict[str, Any]) -> None:
    if contract.get("trade_authorization") is not False:
        raise ValueError("Stage 8 must hard-lock trade_authorization=false")
    if contract.get("trade_signal_generation") is not False:
        raise ValueError("Stage 8 must hard-lock trade_signal_generation=false")


def load_profiles(path: str, symbols: list[str]) -> dict[str, dict[str, Any]]:
    rows = load_json(path).get("profiles", [])
    if len(rows) != 29:
        raise ValueError(f"Expected 29 Stage 5 profiles; got {len(rows)}")
    profiles = {str(r["symbol"]).upper().strip(): r for r in rows}
    if set(profiles) != set(symbols):
        raise ValueError("Stage 5 profile symbols do not exactly match canonical 29")
    return profiles


def normalized(value: float, reference: float) -> float:
    if reference <= 0 or value < 0:
        raise ValueError("Invalid ranking feature/reference")
    return min(value / reference, 1.50) / 1.50


def research_strength(profile: dict[str, Any]) -> float:
    components = {
        "trend_rate": normalized(float(profile["trend_rate"]), REFS["trend_rate"]),
        "or_continuation_rate": normalized(float(profile["or_continuation_rate"]), REFS["or_continuation_rate"]),
        "strong_trend_rate": normalized(float(profile["strong_trend_rate"]), REFS["strong_trend_rate"]),
        "median_event_return_pct": normalized(float(profile["median_event_return_pct"]), REFS["median_event_return_pct"]),
    }
    return sum(WEIGHTS[k] * components[k] for k in WEIGHTS)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--universe", required=True)
    parser.add_argument("--profiles", required=True)
    parser.add_argument("--contract", required=True)
    parser.add_argument("--edge-activation", required=True)
    parser.add_argument("--regimes", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    symbols = canonical_symbols(args.universe)
    profiles = load_profiles(args.profiles, symbols)
    validate_contract(load_json(args.contract))

    activation = pd.read_csv(args.edge_activation)
    regimes = pd.read_csv(args.regimes)

    required_activation = {"symbol", "activation", "reason_code", "match_reason"}
    required_regimes = {"symbol", "regime", "data_status"}
    missing_activation = required_activation - set(activation.columns)
    missing_regimes = required_regimes - set(regimes.columns)
    if missing_activation:
        raise ValueError(f"Stage 7 output missing fields: {sorted(missing_activation)}")
    if missing_regimes:
        raise ValueError(f"Stage 6 output missing fields: {sorted(missing_regimes)}")

    for frame, name in ((activation, "Stage 7"), (regimes, "Stage 6")):
        frame["symbol"] = frame["symbol"].astype(str).str.upper().str.strip()
        if len(frame) != 29 or frame["symbol"].nunique() != 29 or set(frame["symbol"]) != set(symbols):
            raise ValueError(f"{name} coverage is not exactly the canonical 29")

    activation_by_symbol = activation.set_index("symbol")
    regime_by_symbol = regimes.set_index("symbol")

    results = []
    for symbol in symbols:
        a = activation_by_symbol.loc[symbol]
        r = regime_by_symbol.loc[symbol]
        profile = profiles[symbol]
        state = str(a["activation"])
        regime = str(r["regime"])
        data_status = str(r["data_status"])

        if state not in STATES:
            raise ValueError(f"Unknown Stage 7 activation state for {symbol}: {state}")

        research_score = research_strength(profile)
        live_quality = LIVE_QUALITY.get(regime, 0.0)

        if state == "EDGE_ACTIVE":
            if data_status != "FRESH":
                raise ValueError(f"EDGE_ACTIVE cannot coexist with non-fresh data for {symbol}")
            if live_quality <= 0:
                raise ValueError(f"EDGE_ACTIVE requires a directional Stage 6 regime for {symbol}")
            final_score = research_score * live_quality
        else:
            final_score = None
            live_quality = live_quality if state == "EDGE_INACTIVE" else 0.0

        results.append({
            "canonical_rank": int(profile["rank"]),
            "symbol": symbol,
            "activation": state,
            "regime": regime,
            "data_status": data_status,
            "reason_code": str(a["reason_code"]),
            "match_reason": str(a["match_reason"]),
            "research_strength_score": round(research_score, 8),
            "live_regime_quality": round(live_quality, 4),
            "ranking_score": None if final_score is None else round(final_score, 8),
            "trend_rate": float(profile["trend_rate"]),
            "strong_trend_rate": float(profile["strong_trend_rate"]),
            "or_continuation_rate": float(profile["or_continuation_rate"]),
            "median_event_return_pct": float(profile["median_event_return_pct"]),
            "research_profile_source": "config/psy29_edge_profiles_v1.json",
            "research_profile_version": "1.0",
            "portfolio_rank": None,
            "trade_authorized": False,
            "trade_signal_generated": False,
        })

    df = pd.DataFrame(results)
    active = df[df["activation"] == "EDGE_ACTIVE"].copy()
    active = active.sort_values(
        ["ranking_score", "research_strength_score", "trend_rate", "median_event_return_pct", "canonical_rank"],
        ascending=[False, False, False, False, True],
        kind="mergesort",
    )
    for rank, idx in enumerate(active.index, start=1):
        df.loc[idx, "portfolio_rank"] = rank

    df = df.sort_values("canonical_rank").reset_index(drop=True)
    non_active = df["activation"] != "EDGE_ACTIVE"
    validation = (
        len(df) == 29
        and df["symbol"].nunique() == 29
        and set(df["activation"]).issubset(STATES)
        and df.loc[non_active, "portfolio_rank"].isna().all()
        and df["trade_authorized"].eq(False).all()
        and df["trade_signal_generated"].eq(False).all()
        and df["research_profile_source"].eq("config/psy29_edge_profiles_v1.json").all()
        and df.loc[~non_active, "ranking_score"].notna().all()
    )

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    df.to_csv(out / "PSY29_STAGE8_EDGE_RANKING.csv", index=False)

    ranked = active.sort_values("portfolio_rank")
    summary = {
        "stage": 8,
        "engine": "PSY29_PORTFOLIO_EDGE_RANKING",
        "engine_execution_status": "PASS",
        "validation_status": "PASS" if validation else "FAIL",
        "status": "PASS" if validation else "FAIL",
        "coverage": int(len(df)),
        "edge_active_count": int((df["activation"] == "EDGE_ACTIVE").sum()),
        "edge_inactive_count": int((df["activation"] == "EDGE_INACTIVE").sum()),
        "data_stale_count": int((df["activation"] == "DATA_STALE").sum()),
        "data_invalid_count": int((df["activation"] == "DATA_INVALID").sum()),
        "ranked_count": int(len(ranked)),
        "ranked_symbols": ranked["symbol"].tolist(),
        "trade_authorized": False,
        "trade_signal_generated": False,
        "fail_closed": True,
        "research_profile_source": "config/psy29_edge_profiles_v1.json",
    }
    (out / "stage8_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    if not validation:
        raise SystemExit("STAGE 8 VALIDATION FAILED")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
