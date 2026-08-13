#!/usr/bin/env python3
"""PSY29 Stage 17 hard verification."""
from __future__ import annotations
import argparse,csv,json
from pathlib import Path

STATES={"STABLE","CHANGED","DETERIORATING","EMERGING","INVALIDATED","UNSTABLE","DATA_STALE","DATA_INVALID","PROVENANCE_FAIL"}
BLOCKED={"TRADE_READY","TRADE_SIGNAL","TRADE_AUTHORIZED","CE","PE","ENTRY","ENTRY_PRICE","STOP_LOSS","TAKE_PROFIT","TARGET","POSITION_SIZE","RISK","CAPITAL_ALLOCATION","ORDER","EXECUTION"}

def load(p):return json.loads(p.read_text(encoding="utf-8"))
def scan(x,p="root"):
    bad=[]
    if isinstance(x,dict):
        for k,v in x.items():
            if str(k).upper() in BLOCKED:bad.append(f"{p}.{k}")
            bad+=scan(v,f"{p}.{k}")
    elif isinstance(x,list):
        for i,v in enumerate(x):bad+=scan(v,f"{p}[{i}]")
    return bad

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--universe",required=True,type=Path);ap.add_argument("--output",required=True,type=Path);a=ap.parse_args()
    u=load(a.universe);syms=[x["symbol"] for x in u["universe"]]
    assert len(syms)==29 and len(set(syms))==29
    p=a.output/"PSY29_STAGE17_STABILITY_BOARD.json";j=load(p);r=j["records"]
    assert j["stage"]==17 and j["version"]=="1.0" and j["status"]=="LOCKED"
    assert j["coverage"]=={"expected":29,"actual":29,"unique":29}
    assert len(r)==29 and {x["symbol"] for x in r}==set(syms)
    assert all(x["stage17_state"] in STATES for x in r)
    bad=scan(j);assert not bad,"blocked fields: "+str(bad)
    v=load(a.output/"PSY29_STAGE17_VALIDATION.json");assert v["validation_status"]=="PASS"
    assert all(v["checks"].values())
    with (a.output/"PSY29_STAGE17_STABILITY_BOARD.csv").open(encoding="utf-8") as h:assert len(list(csv.DictReader(h)))==29
    observed={x["stage17_state"] for x in r}
    required={"STABLE","CHANGED","DETERIORATING","EMERGING","INVALIDATED","UNSTABLE","DATA_STALE","DATA_INVALID","PROVENANCE_FAIL"}
    assert required<=observed,f"fixture did not cover all states: {sorted(observed)}"
    print("PSY29 STAGE 17 HARD VERIFY: PASS")
    print("Canonical coverage: 29/29")
    print("All nine state classes exercised: PASS")
if __name__=="__main__":main()
