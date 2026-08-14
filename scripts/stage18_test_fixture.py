#!/usr/bin/env python3
"""Deterministic PSY29 Stage 18 fixture generator."""
from __future__ import annotations
import argparse,csv,json
from datetime import datetime,timezone,timedelta
from pathlib import Path

STATES=["STABLE","CHANGED","DETERIORATING","EMERGING","INVALIDATED","UNSTABLE","DATA_STALE","DATA_INVALID","PROVENANCE_FAIL"]

def universe(path):
 d=json.loads(path.read_text(encoding="utf-8")); return [x["symbol"] for x in d["universe"]]

def write(path,rows):
 path.parent.mkdir(parents=True,exist_ok=True)
 with path.open("w",encoding="utf-8",newline="") as f:
  w=csv.DictWriter(f,fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)

def main():
 p=argparse.ArgumentParser(); p.add_argument("--universe",required=True,type=Path); p.add_argument("--output",required=True,type=Path); a=p.parse_args()
 syms=universe(a.universe); base=datetime.now(timezone.utc)-timedelta(seconds=20)
 for n in range(5,17):
  rows=[]
  for i,s in enumerate(syms): rows.append({"symbol":s,"timestamp":(base+timedelta(seconds=i)).isoformat(),"provenance":f"stage{n}-fixture-v1","stage":n,"integrity_status":"INTEGRITY_PASS","regime":"FIXTURE_REGIME"})
  write(a.output/f"stage{n}.csv",rows)
 current=[]
 for i,s in enumerate(syms):
  current.append({"symbol":s,"timestamp":(base+timedelta(seconds=i)).isoformat(),"provenance":"stage17-fixture-v1","stage":17,"stage17_state":STATES[i%len(STATES)]})
 write(a.output/"stage17.csv",current)
 hist=a.output/"history"; hist.mkdir(parents=True,exist_ok=True)
 for j,offset in enumerate((40,30),1):
  rows=[]
  t=base-timedelta(seconds=offset)
  for i,s in enumerate(syms):
   current_state=STATES[i%len(STATES)]
   if i==0: state="STABLE"
   elif i==1: state="STABLE"
   elif i==2: state="DETERIORATING"
   elif i==3: state="EMERGING"
   elif i==4: state="INVALIDATED"
   elif i==5: state="UNSTABLE"
   elif i==6: state="DATA_STALE"
   elif i==7: state="DATA_INVALID"
   elif i==8: state="PROVENANCE_FAIL"
   else: state=current_state
   rows.append({"symbol":s,"timestamp":(t+timedelta(seconds=i)).isoformat(),"provenance":f"stage17-history-fixture-{j}","stage17_state":state})
  write(hist/f"snapshot_{j:02d}.csv",rows)
 print(f"Fixture ready: {a.output}")

if __name__=="__main__": main()
