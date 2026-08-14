#!/usr/bin/env python3
"""PSY29 live service cycle: acquisition -> validated pipeline input."""
from __future__ import annotations
import subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"runtime/live"
OUT.mkdir(parents=True,exist_ok=True)
for cmd in [
 [ROOT/"scripts/psy29_live_dhan_acquisition.py","--universe",ROOT/"config/canonical_universe.json","--output",OUT],
 [ROOT/"scripts/psy29_live_pipeline_bridge.py","--snapshot",OUT/"live_snapshot.csv","--validation",OUT/"live_acquisition_validation.json","--universe",ROOT/"config/canonical_universe.json","--output",OUT],
]:
 subprocess.run([sys.executable,*map(str,cmd)],cwd=ROOT,check=True)
print("PSY29 LIVE PIPELINE INTEGRATION: PASS",flush=True)
