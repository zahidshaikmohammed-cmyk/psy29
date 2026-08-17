#!/usr/bin/env python3
"""PSY29-only pipeline bridge.

Live mode consumes the validated DHAN execution snapshot. Fixture mode consumes
an explicit deterministic off-market execution fixture. Neither mode generates
signals or executes trades.

Stage 11 session_high/session_low are part of the mandatory bridge contract.
They must survive acquisition -> bridge -> Stage 11 unchanged; the bridge must
fail closed if either field is absent or non-numeric.
"""
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

REQUIRED_STAGE11_LIVE = {
    "symbol", "timestamp",
    "open_1m", "high_1m", "low_1m", "close_1m", "volume_1m", "avg_volume_20_1m",
    "open_5m", "high_5m", "low_5m", "close_5m", "volume_5m", "avg_volume_20_5m",
    "vwap_5m", "ema9_5m", "ema20_5m",
    "first15_high", "first15_low", "session_high", "session_low", "swing_high", "swing_low",
}

NUMERIC_FIELDS = REQUIRED_STAGE11_LIVE - {"symbol", "timestamp"}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


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

    records = read_csv(a.snapshot)
    if len(records) != 29:
        raise ValueError(f"pipeline snapshot must contain 29 rows; got {len(records)}")
    if not records:
        raise ValueError("pipeline snapshot is empty")

    missing = REQUIRED_STAGE11_LIVE - set(records[0])
    if missing:
        raise ValueError(f"pipeline snapshot missing Stage 11 live fields: {sorted(missing)}")

    actual = [str(row["symbol"]).strip().upper() for row in records]
    if len(set(actual)) != 29 or set(actual) != set(symbols):
        raise ValueError("pipeline snapshot 29/29 coverage mismatch")

    freshness = [str(row.get("freshness_status", "")).upper() for row in records]
    if a.mode == "live":
        if freshness != ["FRESH"] * 29:
            raise ValueError("live execution snapshot contains non-fresh rows")
    else:
        if freshness != ["FIXTURE"] * 29:
            raise ValueError("fixture execution snapshot must contain explicit FIXTURE freshness status")

    for row in records:
        for field in NUMERIC_FIELDS:
            try:
                value = float(row[field])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"non-numeric pipeline value in {field}") from exc
            if value != value or value in (float("inf"), float("-inf")):
                raise ValueError(f"non-finite pipeline value in {field}")
        if float(row["session_high"]) < float(row["session_low"]):
            raise ValueError(f"invalid session extremes for {row['symbol']}: session_high < session_low")

    out = a.output
    out.mkdir(parents=True, exist_ok=True)
    generated = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    records.sort(key=lambda row: str(row["symbol"]).upper())
    with (out / "live_pipeline_input.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)

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
        "session_extreme_handoff": "MANDATORY_PRESERVED",
        "fresh_count": 29 if a.mode == "live" else 0,
        "fixture_count": 0 if a.mode == "live" else 29,
        "signal_generation": False,
        "order_execution": False,
    }
    (out / "live_pipeline_input_validation.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
