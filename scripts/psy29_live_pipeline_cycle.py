#!/usr/bin/env python3
"""Run one validated PSY29 live acquisition -> pipeline-input cycle."""
from __future__ import annotations
import argparse, json, subprocess, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def run(cmd):
    print("PSY29 LIVE CYCLE:"," ".join(map(str,cmd)),flush=True)
    subprocess.run([sys.executable,*map(str,cmd)],cwd=ROOT,check=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--universe",default="config/canonical_universe.json")
    p.add_argument("--output",default="runtime/live")
    a=p.parse_args()
    out=ROOT/a.output
    out.mkdir(parents=True,exist_ok=True)
    run([ROOT/"scripts/psy29_live_dhan_acquisition.py","--universe",ROOT/a.universe,"--output",out])
    run([ROOT/"scripts/psy29_live_pipeline_bridge.py","--snapshot",out/"live_snapshot.csv","--validation",out/"live_acquisition_validation.json","--universe",ROOT/a.universe,"--output",out])
    print("PSY29 LIVE PIPELINE INPUT: PASS",flush=True)
    print(json.dumps(json.loads((out/"live_pipeline_input_validation.json").read_text()),indent=2),flush=True)

if __name__=="__main__": main()
