#!/usr/bin/env python3
"""PSY29 Stage 19 hard verifier."""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path

ALLOWED={"NO_TRANSITION","TRANSITION_DETECTED","TRANSITION_PERSISTING","TRANSITION_REVERSING","NO_CHANGE_POINT","EMERGING_CHANGE_POINT","CONFIRMED_CHANGE_POINT","CHANGE_POINT_UNSTABLE","INSUFFICIENT_TRANSITION_EVIDENCE","PROVENANCE_FAIL"}
BLOCKED={"TRADE_READY","TRADE_SIGNAL","TRADE_AUTHORIZED","CE","PE","ENTRY","ENTRY_PRICE","STOP_LOSS","TAKE_PROFIT","TARGET","POSITION_SIZE","RISK","CAPITAL_ALLOCATION","ORDER","EXECUTION","FUTURE_PRICE_PREDICTION","DIRECTIONAL_RECOMMENDATION","BUY","SELL"}

def scan(x,path="root"):
    out=[]
    if isinstance(x,dict):
        for k,v in x.items():
            if str(k).upper() in BLOCKED:out.append(f"{path}.{k}")
            out.extend(scan(v,f"{path}.{k}"))
    elif isinstance(x,list):
        for i,v in enumerate(x):out.extend(scan(v,f"{path}[{i}]"))
    return out

def load(p):return json.loads(p.read_text(encoding="utf-8"))

def main():
    p=argparse.ArgumentParser();p.add_argument("--contract",required=True,type=Path);p.add_argument("--universe",required=True,type=Path);p.add_argument("--output",required=True,type=Path);a=p.parse_args()
    c=load(a.contract);u=load(a.universe);b=load(a.output/"PSY29_STAGE19_TRANSITION_BOARD.json");v=load(a.output/"PSY29_STAGE19_VALIDATION.json")
    assert c["stage"]==19 and c["version"]=="1.0" and c["status"]=="LOCKED"
    syms=[str(x["symbol"]).strip().upper() for x in u["universe"]];assert len(syms)==29 and len(set(syms))==29
    rows=b["records"];assert len(rows)==29 and len({r["symbol"] for r in rows})==29 and {r["symbol"] for r in rows}==set(syms)
    assert all(r["stage19_state"] in ALLOWED for r in rows)
    assert all(r["provenance_complete"] is True or r["stage19_state"]=="PROVENANCE_FAIL" for r in rows)
    assert b["coverage"]=={"expected":29,"actual":29,"unique":29}
    assert v["validation_status"]=="PASS" and v["coverage"]=={"expected":29,"actual":29,"unique":29}
    assert v["blocked_fields"]==[] and v["fail_closed"] is True
    assert scan(b)==[] and scan(v)==[]
    assert set(v["output_states_observed"])==ALLOWED, f"Canonical 10-state coverage failed: {set(v['output_states_observed']) ^ ALLOWED}"
    assert c["coverage"]=={"expected":29,"required":True,"partial_pass":False}
    assert c["fail_closed"] is True and c["provenance_required"] is True and c["cross_stage_consistency_required"] is True
    for key,value in c["safety_boundaries"].items():assert value is True,f"Safety boundary not locked: {key}"
    print("PSY29 STAGE 19 HARD VERIFY: PASS")
    print("29/29 coverage: PASS")
    print("10/10 canonical states: PASS")
    print("Provenance gate: PASS")
    print("Safety boundaries: PASS")
    print("Fail-closed contract: PASS")

if __name__=="__main__":
    try:main()
    except Exception as e:print(f"PSY29 STAGE 19 HARD VERIFY FAIL: {e}",file=sys.stderr);raise
