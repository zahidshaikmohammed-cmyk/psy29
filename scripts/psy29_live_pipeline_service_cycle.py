#!/usr/bin/env python3
"""PSY29 service cycle: live DHAN during NSE session, explicit fixture off-market."""
from __future__ import annotations
import argparse,subprocess,sys
from datetime import datetime,time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/"runtime/live";UNIVERSE=ROOT/"config/psy29_live_universe_contract.json";IST=ZoneInfo("Asia/Kolkata")
def market_session()->bool:
    now=datetime.now(IST);return now.weekday()<5 and dtime(9,15)<=now.time()<=dtime(15,30)
def run(cmd:list[object],timeout:int=900):
    print("PSY29 PIPELINE CYCLE:"," ".join(map(str,cmd)),flush=True);subprocess.run([sys.executable,*map(str,cmd)],cwd=ROOT,check=True,timeout=timeout)
def main():
    p=argparse.ArgumentParser();p.add_argument("--mode",choices=("auto","live","fixture"),default="auto");a=p.parse_args();OUT.mkdir(parents=True,exist_ok=True)
    base=("live_snapshot.csv","execution_snapshot.csv","live_acquisition_validation.json","live_pipeline_input.csv","live_pipeline_input_validation.json")
    mode="live" if a.mode=="live" else "fixture" if a.mode=="fixture" else ("live" if market_session() else "fixture")
    # Invalidate current-cycle signal artifacts before touching new live input.
    # This prevents a failed Stage 6-20 cycle from exposing the previous cycle's signal.
    if mode=="live":
        base=base+("PSY29_STAGE20_FINAL_SIGNAL_BOARD.json","PSY29_STAGE20_FINAL_SIGNALS.csv","PSY29_STAGE20_VALIDATION.json","signal_cycle")
    for name in base:
        path=OUT/name
        if path.is_dir():
            import shutil;shutil.rmtree(path,ignore_errors=True)
        elif path.exists():path.unlink()
    if mode=="live":run([ROOT/"scripts/psy29_live_dhan_acquisition.py","--universe",UNIVERSE,"--output",OUT])
    else:run([ROOT/"scripts/psy29_live_pipeline_fixture.py","--universe",UNIVERSE,"--output",OUT])
    run([ROOT/"scripts/psy29_live_pipeline_bridge.py","--snapshot",OUT/"execution_snapshot.csv","--validation",OUT/"live_acquisition_validation.json","--universe",UNIVERSE,"--output",OUT,"--mode",mode])
    if mode=="live":run([ROOT/"scripts/psy29_live_signal_cycle.py","--output",OUT],timeout=900)
    print(f"PSY29 LIVE PIPELINE INTEGRATION: PASS ({mode})",flush=True)
if __name__=="__main__":main()
