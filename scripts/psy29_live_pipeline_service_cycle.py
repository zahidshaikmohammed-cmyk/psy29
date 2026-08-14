#!/usr/bin/env python3
"""PSY29 service cycle: live DHAN during NSE session, explicit fixture off-market."""
from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runtime/live"
UNIVERSE = ROOT / "config/psy29_live_universe_contract.json"
THRESHOLDS = ROOT / "runtime/live/psy29_event_thresholds.json"
EVENT_STATE = ROOT / "runtime/live/PSY29_EVENT_DETECTOR_STATE.json"
EVENT_OUT = OUT / "event_detector"
IST = ZoneInfo("Asia/Kolkata")


def market_session() -> bool:
    now = datetime.now(IST)
    return now.weekday() < 5 and dtime(9, 15) <= now.time() <= dtime(15, 30)


def run(cmd: list[object]) -> None:
    print("PSY29 PIPELINE CYCLE:", " ".join(map(str, cmd)), flush=True)
    subprocess.run([sys.executable, *map(str, cmd)], cwd=ROOT, check=True, timeout=240)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=("auto", "live", "fixture"), default="auto")
    a = p.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    for name in (
        "live_snapshot.csv",
        "execution_snapshot.csv",
        "live_acquisition_validation.json",
        "live_pipeline_input.csv",
        "live_pipeline_input_validation.json",
    ):
        path = OUT / name
        if path.exists():
            path.unlink()

    mode = "live" if a.mode == "live" else "fixture" if a.mode == "fixture" else ("live" if market_session() else "fixture")

    if mode == "live":
        run([ROOT / "scripts/psy29_live_dhan_acquisition.py", "--universe", UNIVERSE, "--output", OUT])
    else:
        run([ROOT / "scripts/psy29_live_pipeline_fixture.py", "--universe", UNIVERSE, "--output", OUT])

    run([
        ROOT / "scripts/psy29_live_pipeline_bridge.py",
        "--snapshot", OUT / "execution_snapshot.csv",
        "--validation", OUT / "live_acquisition_validation.json",
        "--universe", UNIVERSE,
        "--output", OUT,
        "--mode", mode,
    ])

    # Fixture/off-market cycles deliberately stop at the bridge. The Event Detector
    # is a live-only layer and is never invoked for fixture input.
    if mode == "live":
        if not THRESHOLDS.exists():
            raise RuntimeError("PSY29 event detector thresholds are missing; fail closed before Stage 6")
        run([
            ROOT / "scripts/psy29_event_detector.py",
            "--snapshot", OUT / "live_pipeline_input.csv",
            "--validation", OUT / "live_pipeline_input_validation.json",
            "--thresholds", THRESHOLDS,
            "--state", EVENT_STATE,
            "--output", EVENT_OUT,
            "--mode", "live",
        ])
    print(f"PSY29 LIVE PIPELINE INTEGRATION: PASS ({mode})", flush=True)


if __name__ == "__main__":
    main()
