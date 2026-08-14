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
    print(f"PSY29 LIVE PIPELINE INTEGRATION: PASS ({mode})", flush=True)


if __name__ == "__main__":
    main()
