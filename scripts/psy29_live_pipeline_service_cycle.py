#!/usr/bin/env python3
"""PSY29 service cycle: live DHAN during NSE session, explicit fixture off-market."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runtime/live"
UNIVERSE = ROOT / "config/psy29_live_universe_contract.json"
THRESHOLDS = ROOT / "research/PSY29_EVENT_DETECTOR_THRESHOLDS_V2.json"
EVENT_STATE = ROOT / "runtime/live/PSY29_EVENT_DETECTOR_STATE.json"
EVENT_OUT = OUT / "event_detector"
STAGE6 = ROOT / "scripts/psy29_stage6_live_orchestrator.py"
IST = ZoneInfo("Asia/Kolkata")


def market_session() -> bool:
    now = datetime.now(IST)
    return now.weekday() < 5 and dtime(9, 15) <= now.time() <= dtime(15, 30)


def run(cmd: list[object]) -> None:
    print("PSY29 PIPELINE CYCLE:", " ".join(map(str, cmd)), flush=True)
    subprocess.run([sys.executable, *map(str, cmd)], cwd=ROOT, check=True, timeout=240)


def run_stage6_on_new_events() -> int:
    result_path = EVENT_OUT / "PSY29_EVENT_DETECTOR_RESULT.json"
    if not result_path.is_file():
        raise RuntimeError("event detector result missing; fail closed before Stage 6")
    try:
        result = json.loads(result_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"invalid event detector result; fail closed before Stage 6: {exc}") from exc
    if result.get("status") != "PASS" or result.get("mode") != "live":
        raise RuntimeError("event detector did not return PASS/live; fail closed before Stage 6")
    events = result.get("detected_events")
    if not isinstance(events, list):
        raise RuntimeError("event detector detected_events is malformed; fail closed before Stage 6")
    if not events:
        print("PSY29 STAGE 6: SKIP — no NEW FIRST_DETECTED events", flush=True)
        return 0
    if not STAGE6.is_file():
        raise RuntimeError(f"existing Stage 6 orchestrator missing: {STAGE6}")
    run([
        STAGE6,
        "--manifest", OUT / "live_pipeline_input_validation.json",
        "--snapshot", OUT / "live_pipeline_input.csv",
        "--output", OUT / "stage6",
    ])
    return len(events)


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
            raise RuntimeError("PSY29 canonical V2 event detector thresholds are missing; fail closed before Stage 6")
        run([
            ROOT / "scripts/psy29_event_detector.py",
            "--snapshot", OUT / "live_pipeline_input.csv",
            "--validation", OUT / "live_pipeline_input_validation.json",
            "--thresholds", THRESHOLDS,
            "--state", EVENT_STATE,
            "--output", EVENT_OUT,
            "--mode", "live",
        ])
        new_events = run_stage6_on_new_events()
        print(f"PSY29 LIVE PIPELINE INTEGRATION: PASS (live, new_events={new_events})", flush=True)
    else:
        print(f"PSY29 LIVE PIPELINE INTEGRATION: PASS ({mode})", flush=True)


if __name__ == "__main__":
    main()
