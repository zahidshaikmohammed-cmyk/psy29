#!/usr/bin/env python3
"""PSY29-only pipeline bridge.

Live mode consumes the validated DHAN execution snapshot. Fixture mode consumes
an explicit deterministic off-market execution fixture. Neither mode generates
signals or executes trades.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

REQUIRED_STAGE11_LIVE = {
    "symbol", "timestamp",
    "open_1m", "high_1m", "low_1m", "close_1m", "volume_1m", "avg_volume_20_1m",
    "open_5m", "high_5m", "low_5m", "close_5m", "volume_5m", "avg_volume_20_5m",
    "vwap_5m", "ema9_5m", "ema20_5m",
    "first15_high", "first15_low", "swing_high", "swing_low",
}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--snapshot", required=True, type=Path)
    p.add_argument("--validation", required=True, type=Path)
    p.add_argument("--universe", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--mode", choices=("live", "fixture"), default="live")
    a = p.parse_args()

    validation = json.loads(a.validation.read_text(encoding="utf-8"))
    if validation.get("status") != "PASS":
        raise ValueError("pipeline input validation source is not PASS")
    if a.mode == "live":
        if validation.get("contract") != "PSY29_LIVE_DHAN_ACQUISITION_VALIDATION":
            raise ValueError("live mode requires the PSY29 DHAN acquisition validation contract")
        if validation.get("provider") != "DHAN":
            raise ValueError("live mode requires provider=DHAN")
    else:
        if validation.get("contract") != "PSY29_DETERMINISTIC_PIPELINE_FIXTURE":
            raise ValueError("fixture mode requires the deterministic fixture contract")
        if validation.get("live_data") is not False:
            raise ValueError("fixture mode must be explicitly non-live")

    u = json.loads(a.universe.read_text(encoding="utf-8"))
    symbols = [str(x["symbol"]).strip().upper() for x in u.get("universe", [])]
    if len(symbols) != 29 or len(set(symbols)) != 29:
        raise ValueError("canonical universe must be exactly 29 unique symbols")

    df = pd.read_csv(a.snapshot)
    missing = REQUIRED_STAGE11_LIVE - set(df.columns)
    if missing:
        raise ValueError(f"pipeline snapshot missing Stage 11 live fields: {sorted(missing)}")

    actual = df["symbol"].astype(str).str.upper().tolist()
    if len(actual) != 29 or len(set(actual)) != 29 or set(actual) != set(symbols):
        raise ValueError("pipeline snapshot 29/29 coverage mismatch")

    freshness = df.get("freshness_status", pd.Series(dtype=str)).astype(str).str.upper()
    if a.mode == "live":
        if len(freshness) != 29 or not (freshness == "FRESH").all():
            raise ValueError("live execution snapshot contains non-fresh rows")
    else:
        if len(freshness) != 29 or not (freshness == "FIXTURE").all():
            raise ValueError("fixture execution snapshot must contain explicit FIXTURE freshness status")

    for field in REQUIRED_STAGE11_LIVE - {"symbol", "timestamp"}:
        numeric = pd.to_numeric(df[field], errors="coerce")
        if numeric.isna().any():
            raise ValueError(f"pipeline snapshot contains non-numeric values in {field}")

    out = a.output
    out.mkdir(parents=True, exist_ok=True)
    generated = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    df = df.sort_values("symbol").reset_index(drop=True)
    df.to_csv(out / "live_pipeline_input.csv", index=False)

    manifest = {
        "contract": "PSY29_LIVE_PIPELINE_INPUT",
        "status": "PASS",
        "mode": a.mode,
        "live_data": a.mode == "live",
        "generated_at": generated,
        "source": "PSY29 execution_snapshot.csv" if a.mode == "live" else "PSY29 deterministic execution fixture",
        "coverage": {"expected": 29, "actual": 29, "unique": 29},
        "stage11_live_compatibility": True,
        "stage11_required_fields": sorted(REQUIRED_STAGE11_LIVE),
        "fresh_count": 29 if a.mode == "live" else 0,
        "fixture_count": 0 if a.mode == "live" else 29,
        "signal_generation": False,
        "order_execution": False,
    }
    (out / "live_pipeline_input_validation.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
