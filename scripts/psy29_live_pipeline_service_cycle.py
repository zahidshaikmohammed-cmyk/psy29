#!/usr/bin/env python3
"""PSY29 live service cycle: acquisition -> validated pipeline input."""
from __future__ import annotations
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runtime/live"
OUT.mkdir(parents=True, exist_ok=True)
UNIVERSE = ROOT / "config/psy29_live_universe_contract.json"

for cmd in [
    [ROOT / "scripts/psy29_live_dhan_acquisition.py", "--universe", UNIVERSE, "--output", OUT],
    [ROOT / "scripts/psy29_live_pipeline_bridge.py", "--snapshot", OUT / "live_snapshot.csv", "--validation", OUT / "live_acquisition_validation.json", "--universe", UNIVERSE, "--output", OUT],
]:
    subprocess.run([sys.executable, *map(str, cmd)], cwd=ROOT, check=True)

print("PSY29 LIVE PIPELINE INTEGRATION: PASS", flush=True)
