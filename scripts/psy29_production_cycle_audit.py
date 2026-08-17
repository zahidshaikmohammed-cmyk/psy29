#!/usr/bin/env python3
"""PSY29 Fix 4 production-cycle audit.

Runs the existing production service cycle and independently verifies the
published DHAN -> Stage 6..20 chain. This is an audit layer only: it does not
change Stage 6-20 mathematics and never places orders.
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from datetime import datetime, time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runtime/live"
UNIVERSE = ROOT / "config/psy29_live_universe_contract.json"
IST = ZoneInfo("Asia/Kolkata")


def market_session() -> bool:
    now = datetime.now(IST)
    return now.weekday() < 5 and dtime(9, 15) <= now.time() <= dtime(15, 30)


def run_cycle(mode: str) -> None:
    subprocess.run(
        [sys.executable, str(ROOT / "scripts/psy29_live_pipeline_service_cycle.py"), "--mode", mode],
        cwd=ROOT,
        check=True,
        timeout=1800,
    )


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def canonical_symbols() -> set[str]:
    rows = read_json(UNIVERSE)["universe"]
    symbols = [str(x["symbol"]).strip().upper() for x in rows]
    ranks = [int(x["rank"]) for x in rows]
    if len(symbols) != 29 or len(set(symbols)) != 29 or ranks != list(range(1, 30)):
        raise RuntimeError("canonical universe is not exactly 29 unique ranked symbols")
    return set(symbols)


def verify_29(path: Path, expected: set[str], label: str) -> None:
    rows = read_csv(path)
    symbols = [str(r.get("symbol", "")).strip().upper() for r in rows]
    if len(rows) != 29 or len(set(symbols)) != 29 or set(symbols) != expected:
        raise RuntimeError(f"{label}: 29/29 coverage failure")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("live", "fixture", "auto"), default="auto")
    ap.add_argument("--report", type=Path, default=OUT / "PSY29_PRODUCTION_CYCLE_AUDIT.json")
    args = ap.parse_args()

    if args.mode == "auto":
        mode = "live" if market_session() else "fixture"
    else:
        mode = args.mode

    if mode == "live" and not market_session():
        raise SystemExit("PSY29 FIX 4 AUDIT: live mode is allowed only during NSE market hours")
    if mode == "fixture" and market_session():
        raise SystemExit("PSY29 FIX 4 AUDIT: fixture mode is forbidden during NSE market hours")

    expected = canonical_symbols()
    run_cycle(mode)

    validation = read_json(OUT / "live_pipeline_input_validation.json")
    required_validation = {
        "status": "PASS",
        "contract": "PSY29_LIVE_PIPELINE_INPUT",
        "mode": mode,
        "coverage": {"expected": 29, "actual": 29, "unique": 29},
        "signal_generation": False,
        "order_execution": False,
    }
    for key, value in required_validation.items():
        if validation.get(key) != value:
            raise RuntimeError(f"pipeline validation mismatch: {key}={validation.get(key)!r}")
    if validation.get("live_data") is not (mode == "live"):
        raise RuntimeError("live_data provenance mismatch")

    acquisition = read_json(OUT / "live_acquisition_validation.json")
    if mode == "live":
        if acquisition.get("status") != "PASS" or acquisition.get("provider") != "DHAN":
            raise RuntimeError("live acquisition is not a PASS/DHAN result")
        if acquisition.get("coverage") != {"expected": 29, "actual": 29, "unique": 29}:
            raise RuntimeError("DHAN acquisition coverage is not 29/29")
        if acquisition.get("fresh_count") != 29 or acquisition.get("stale_count") != 0 or acquisition.get("invalid_count") != 0:
            raise RuntimeError("DHAN acquisition freshness/completeness gate failed")
        if acquisition.get("signal_generation") is not False or acquisition.get("order_execution") is not False:
            raise RuntimeError("DHAN acquisition safety boundary failed")

    verify_29(OUT / "execution_snapshot.csv", expected, "execution snapshot")

    if mode == "live":
        execution = read_csv(OUT / "execution_snapshot.csv")
        if any(str(r.get("freshness_status", "")).upper() != "FRESH" for r in execution):
            raise RuntimeError("execution snapshot contains a non-FRESH row")
        for r in execution:
            for field in ("session_high", "session_low"):
                try:
                    value = float(r[field])
                except (TypeError, ValueError) as exc:
                    raise RuntimeError(f"{field} is not numeric for {r.get('symbol')}") from exc
                if value != value or value in (float("inf"), float("-inf")):
                    raise RuntimeError(f"{field} is non-finite for {r.get('symbol')}")

    signal_cycle = OUT / "signal_cycle"
    for n in range(6, 20):
        files = list((signal_cycle / f"stage{n}").glob("*.csv"))
        if not files:
            raise RuntimeError(f"Stage {n} production-cycle artifact missing")
        verify_29(files[0], expected, f"Stage {n}")

    if mode == "live":
        board = read_json(OUT / "PSY29_STAGE20_FINAL_SIGNAL_BOARD.json")
        if board.get("coverage") != {"expected": 29, "actual": 29, "unique": 29}:
            raise RuntimeError("Stage 20 coverage is not 29/29")
        if len(board.get("audit", [])) != 29:
            raise RuntimeError("Stage 20 audit is not 29/29")
        if board.get("daily_signal_cap") is not None:
            raise RuntimeError("Stage 20 daily signal cap is not null")
        production = board.get("production_cycle", {})
        if production.get("live_data") is not True or production.get("provider") != "DHAN":
            raise RuntimeError("Stage 20 production provenance is not live DHAN")
        if production.get("stage6_to_stage20") is not True:
            raise RuntimeError("Stage 20 production-cycle provenance missing")
        if production.get("stage17_history_frozen_before_cycle") is not True:
            raise RuntimeError("Stage 17 temporal freeze not recorded")
        if production.get("stage17_current_appended_after_cycle_success") is not True:
            raise RuntimeError("Stage 17 post-success history commit not recorded")

    report = {
        "contract": "PSY29_FIX_4_PRODUCTION_CYCLE_AUDIT",
        "status": "PASS",
        "mode": mode,
        "provider": "DHAN" if mode == "live" else "DETERMINISTIC_FIXTURE",
        "coverage": {"expected": 29, "actual": 29, "unique": 29},
        "chain": "DHAN -> acquisition -> bridge -> Stage 6 -> Stage 7 -> Stage 8 -> Stage 9 -> Stage 10 -> Stage 11 -> Stage 12 -> Stage 13 -> Stage 14 -> Stage 15 -> Stage 16 -> Stage 17 -> Stage 18 -> Stage 19 -> Stage 20",
        "stage20_verified": mode == "live",
        "signal_generation": False,
        "order_execution": False,
        "generated_at": datetime.now(IST).isoformat(),
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
