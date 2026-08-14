#!/usr/bin/env python3
"""PSY29-only pipeline bridge.

Live mode consumes the validated DHAN snapshot. Fixture mode consumes an
explicit deterministic off-market fixture. Neither mode generates orders or
executes trades.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

REQUIRED = {
    "symbol", "timestamp", "last_price", "vwap", "ema9", "ema20",
    "first15_high", "first15_low", "security_id", "exchange_segment"
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
    if set(df.columns) < REQUIRED:
        raise ValueError("pipeline snapshot missing required fields")
    actual = df["symbol"].astype(str).str.upper().tolist()
    if len(actual) != 29 or len(set(actual)) != 29 or set(actual) != set(symbols):
        raise ValueError("pipeline snapshot 29/29 coverage mismatch")

    freshness = df["freshness_status"].astype(str).str.upper()
    if a.mode == "live":
        if not (freshness == "FRESH").all():
            raise ValueError("live snapshot contains non-fresh rows")
    else:
        if not (freshness == "FIXTURE").all():
            raise ValueError("fixture snapshot must contain explicit FIXTURE freshness status")

    if df["security_id"].astype(str).eq("").any():
        raise ValueError("missing security id")

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
        "source": "PSY29 live_snapshot.csv" if a.mode == "live" else "PSY29 deterministic pipeline fixture",
        "coverage": {"expected": 29, "actual": 29, "unique": 29},
        "fresh_count": 29 if a.mode == "live" else 0,
        "fixture_count": 0 if a.mode == "live" else 29,
        "signal_generation": False,
        "order_execution": False,
    }
    (out / "live_pipeline_input_validation.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
