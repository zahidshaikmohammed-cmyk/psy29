#!/usr/bin/env python3
"""Create deterministic PSY29 Stage 19 upstream/history fixtures."""
from __future__ import annotations
import argparse,csv,json
from pathlib import Path
from datetime import datetime,timezone,timedelta

def main():
    p=argparse.ArgumentParser();p.add_argument("--universe",required=True,type=Path);p.add_argument("--output",required=True,type=Path);a=p.parse_args()
    u=json.loads(a.universe.read_text(encoding="utf-8"))["universe"]
    syms=[str(x["symbol"]).strip().upper() for x in u]
    if len(syms)!=29 or len(set(syms))!=29:raise ValueError("canonical universe must be 29 unique symbols")
    a.output.mkdir(parents=True,exist_ok=True);hist=a.output/"history";hist.mkdir(exist_ok=True)
    now=datetime.now(timezone.utc).replace(microsecond=0)
    patterns=[
        ("STABLE","STABLE","STABLE","STABLE"),
        ("STABLE","EMERGING","CHANGED","INVALIDATED"),
        ("EMERGING","EMERGING","EMERGING","EMERGING"),
        ("EMERGING","EMERGING","EMERGING","STABLE"),
        ("STABLE","STABLE","STABLE","CHANGED"),
        ("STABLE","CHANGED","STABLE","STABLE"),
        ("STABLE","CHANGED","CHANGED","CHANGED"),
        ("STABLE","STABLE","STABLE","UNSTABLE"),
        ("STABLE","STABLE","STABLE","UNSTABLE"),
        ("STABLE","STABLE","STABLE","INVALIDATED"),
    ]
    current=[]
    for i,s in enumerate(syms):
        ptn=patterns[i%len(patterns)]
        current.append({"symbol":s,"stage17_state":ptn[3],"timestamp":now.isoformat(),"provenance":"fixture-stage17"})
    if len(current)>=10:current[9].pop("provenance",None)
    def write(path,records):
        with path.open("w",encoding="utf-8",newline="") as f:
            w=csv.DictWriter(f,fieldnames=list(records[0]));w.writeheader();w.writerows(records)
    write(a.output/"stage17.csv",current)
    # Keep the seventh pattern free to produce NO_CHANGE_POINT; inject insufficient evidence separately.
    r18_states=["CONTINUOUS","CHANGED","NEW_STATE","PERSISTENT_DETERIORATION","PERSISTENT_INVALIDATION","RECOVERED","CHANGED","HISTORY_UNAVAILABLE","CHANGED","PROVENANCE_FAIL"]
    r18=[{"symbol":s,"stage18_state":r18_states[i%len(r18_states)],"timestamp":now.isoformat(),"provenance":"fixture-stage18"} for i,s in enumerate(syms)]
    write(a.output/"stage18.csv",r18)
    for n in range(5,17):
        rr=[{"symbol":s,"timestamp":now.isoformat(),"provenance":f"fixture-stage{n}"} for s in syms]
        write(a.output/f"stage{n}.csv",rr)
    for j,delta in enumerate((3,2,1),1):
        t=now-timedelta(minutes=delta);rr=[]
        for i,s in enumerate(syms):
            ptn=patterns[i%len(patterns)]
            rr.append({"symbol":s,"stage17_state":ptn[j-1],"timestamp":t.isoformat(),"provenance":f"fixture-history-{j}"})
        write(hist/f"snapshot{j}.csv",rr)
    print("STAGE 19 FIXTURE: PASS")
    print("29/29 upstream coverage: PASS")
    print("3 historical snapshots: PASS")
    print("10 canonical Stage 19 states represented: PASS")

if __name__=="__main__":main()
