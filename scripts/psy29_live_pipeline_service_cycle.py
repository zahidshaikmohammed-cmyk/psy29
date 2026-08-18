#!/usr/bin/env python3
"""PSY29 service cycle: live DHAN during NSE session, explicit fixture off-market only."""
from __future__ import annotations
import argparse,subprocess,sys
from datetime import datetime,time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"runtime/live"
UNIVERSE=ROOT/"config/psy29_live_universe_contract.json"
IST=ZoneInfo("Asia/Kolkata")
OPENING_RANGE_END=dtime(9,30)

def market_session() -> bool:
    now=datetime.now(IST)
    return now.weekday()<5 and dtime(9,15)<=now.time()<=dtime(15,30)

def run(cmd:list[object],timeout:int=900):
    print("PSY29 PIPELINE CYCLE:"," ".join(map(str,cmd)),flush=True)
    subprocess.run([sys.executable,*map(str,cmd)],cwd=ROOT,check=True,timeout=timeout)

def main():
    p=argparse.ArgumentParser();p.add_argument("--mode",choices=("auto","live","fixture"),default="auto");a=p.parse_args();OUT.mkdir(parents=True,exist_ok=True)
    in_market=market_session()
    if in_market and a.mode=="fixture":raise SystemExit("PSY29 SAFETY BLOCK: fixture mode is forbidden during NSE market hours")
    if a.mode=="live":mode="live"
    elif a.mode=="fixture":mode="fixture"
    else:mode="live" if in_market else "fixture"
    base=("live_snapshot.csv","execution_snapshot.csv","live_acquisition_validation.json","live_pipeline_input.csv","live_pipeline_input_validation.json")
    if mode=="live":base=base+("PSY29_STAGE20_FINAL_SIGNAL_BOARD.json","PSY29_STAGE20_FINAL_SIGNALS.csv","PSY29_STAGE20_VALIDATION.json","signal_cycle")
    for name in base:
        path=OUT/name
        if path.is_dir():
            import shutil;shutil.rmtree(path,ignore_errors=True)
        elif path.exists():path.unlink()
    if mode=="live":
        now=datetime.now(IST)
        if now.time()<OPENING_RANGE_END:
            run([ROOT/"scripts/psy29_live_preopen_capture.py","--universe",UNIVERSE,"--output",OUT],timeout=600)
            print("PSY29 LIVE PIPELINE INTEGRATION: PASS (live pre-opening-range collection)",flush=True)
            return
        run([ROOT/"scripts/psy29_live_dhan_acquisition.py","--universe",UNIVERSE,"--output",OUT])
    else:run([ROOT/"scripts/psy29_live_pipeline_fixture.py","--universe",UNIVERSE,"--output",OUT])
    run([ROOT/"scripts/psy29_live_pipeline_bridge.py","--snapshot",OUT/"execution_snapshot.csv","--validation",OUT/"live_acquisition_validation.json","--universe",UNIVERSE,"--output",OUT,"--mode",mode])
    if mode=="live":
        # Durable archive happens before Stage 6-20. If Neon is unavailable or
        # coverage is not exactly 29/29, this cycle fails instead of silently
        # claiming that permanent minute history was captured.
        run([ROOT/"scripts/psy29_live_archive.py","--execution",OUT/"execution_snapshot.csv","--validation",OUT/"live_acquisition_validation.json","--board",OUT/"PSY29_STAGE20_FINAL_SIGNAL_BOARD.json"],timeout=120)
        run([ROOT/"scripts/psy29_live_signal_cycle.py","--output",OUT],timeout=900)
    print(f"PSY29 LIVE PIPELINE INTEGRATION: PASS ({mode})",flush=True)
if __name__=="__main__":main()
