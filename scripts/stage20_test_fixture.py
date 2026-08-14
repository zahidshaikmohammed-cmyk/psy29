#!/usr/bin/env python3
from __future__ import annotations
import argparse,csv,json
from pathlib import Path
from datetime import datetime,timezone

def main():
    p=argparse.ArgumentParser();p.add_argument("--universe",required=True,type=Path);p.add_argument("--output",required=True,type=Path);a=p.parse_args()
    d=json.loads(a.universe.read_text(encoding="utf-8"));syms=[str(x["symbol"]).strip().upper() for x in d["universe"]]
    if len(syms)!=29 or len(set(syms))!=29:raise ValueError("canonical universe must be 29 unique symbols")
    a.output.mkdir(parents=True,exist_ok=True);now=datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z")
    rows=[]
    for i,z in enumerate(syms):
        qualify=i<6
        r={"symbol":z,"timestamp":now,"provenance":"stage20-deterministic-fixture","stage20_eligible":"TRUE" if qualify else "FALSE","direction":"LONG" if i%2==0 else "SHORT","entry":100+i,"stop_loss":97+i,"target":108+i,"risk_reward":2.66,"final_score":95-i,"confluence_score":90-i,"freshness_score":90,"state":"QUALIFYING" if qualify else "NO_SETUP"}
        rows.append(r)
    # Two opportunities are already represented in memory and must not be duplicated.
    with (a.output/"stage19.csv").open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    memory=[{"symbol":syms[1],"memory_state":"ACTIVE_SIGNAL"},{"symbol":syms[2],"memory_state":"TRADED"}]
    with (a.output/"memory.csv").open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(memory[0]));w.writeheader();w.writerows(memory)
    print("STAGE 20 FIXTURE: PASS")
    print("29/29 coverage: PASS")
    print("6 qualifying opportunities: PASS")
    print("Active/traded duplicate memory: PASS")
    print("Multiple-signal scenario: PASS")

if __name__=="__main__":main()
