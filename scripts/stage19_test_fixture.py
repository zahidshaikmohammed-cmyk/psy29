#!/usr/bin/env python3
"""Create deterministic Stage 19 upstream/history fixtures."""
from __future__ import annotations
import argparse,csv,json
from pathlib import Path
from datetime import datetime,timezone,timedelta

S17=["STABLE","CHANGED","DETERIORATING","EMERGING","INVALIDATED","UNSTABLE","DATA_STALE","DATA_INVALID","PROVENANCE_FAIL"]
S18=["CONTINUOUS","CHANGED","NEW_STATE","PERSISTENT_DETERIORATION","PERSISTENT_INVALIDATION","RECOVERED","HISTORY_UNAVAILABLE","HISTORY_INVALID","PROVENANCE_FAIL"]

def main():
 p=argparse.ArgumentParser();p.add_argument("--universe",required=True,type=Path);p.add_argument("--output",required=True,type=Path);a=p.parse_args()
 u=json.loads(a.universe.read_text(encoding="utf-8"))["universe"]
 syms=[str(x["symbol"]).strip().upper() for x in u]
 if len(syms)!=29 or len(set(syms))!=29:raise ValueError("canonical universe must be 29 unique symbols")
 a.output.mkdir(parents=True,exist_ok=True); hist=a.output/"history";hist.mkdir(exist_ok=True)
 now=datetime.now(timezone.utc).replace(microsecond=0)
 # Three snapshots create distinct deterministic transition patterns.
 patterns=[
  ("STABLE","STABLE","STABLE"),
  ("STABLE","STABLE","EMERGING"),
  ("EMERGING","EMERGING","EMERGING"),
  ("EMERGING","STABLE","STABLE"),
  ("STABLE","STABLE","CHANGED"),
  ("CHANGED","STABLE","CHANGED"),
  ("STABLE","STABLE","UNSTABLE"),
  ("STABLE","EMERGING","STABLE"),
  ("INVALIDATED","INVALIDATED","INVALIDATED"),
  ("STABLE","CHANGED","CHANGED"),
 ]
 rows=[]
 for i,s in enumerate(syms):
  ptn=patterns[i%len(patterns)]
  rows.append({"symbol":s,"stage17_state":ptn[2],"timestamp":now.isoformat(),"provenance":"fixture-stage17"})
 with (a.output/"stage17.csv").open("w",encoding="utf-8",newline="") as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
 # Stage 18 fixture is deliberately descriptive and provenance-complete.
 r18=[]
 for i,s in enumerate(syms):
  r18.append({"symbol":s,"stage18_state":S18[i%len(S18)],"timestamp":now.isoformat(),"provenance":"fixture-stage18"})
 with (a.output/"stage18.csv").open("w",encoding="utf-8",newline="") as f:
  w=csv.DictWriter(f,fieldnames=list(r18[0]));w.writeheader();w.writerows(r18)
 # Upstream stage 5-16 fixtures: only the provenance contract is consumed by Stage 19.
 for n in range(5,17):
  rr=[{"symbol":s,"timestamp":now.isoformat(),"provenance":f"fixture-stage{n}"} for s in syms]
  with (a.output/f"stage{n}.csv").open("w",encoding="utf-8",newline="") as f:
   w=csv.DictWriter(f,fieldnames=list(rr[0]));w.writeheader();w.writerows(rr)
 # Three historical Stage 17 snapshots, strictly increasing.
 for j,delta in enumerate((3,2,1),1):
  t=now-timedelta(minutes=delta)
  rr=[]
  for i,s in enumerate(syms):
   ptn=patterns[i%len(patterns)]
   rr.append({"symbol":s,"stage17_state":ptn[j-1],"timestamp":t.isoformat(),"provenance":f"fixture-history-{j}"})
  with (hist/f"snapshot{j}.csv").open("w",encoding="utf-8",newline="") as f:
   w=csv.DictWriter(f,fieldnames=list(rr[0]));w.writeheader();w.writerows(rr)
 print("STAGE 19 FIXTURE: PASS")
 print("29/29 upstream coverage: PASS")
 print("3 historical snapshots: PASS")

if __name__=="__main__":main()
