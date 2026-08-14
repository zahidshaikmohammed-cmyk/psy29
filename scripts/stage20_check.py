#!/usr/bin/env python3
from __future__ import annotations
import argparse,csv,json
from pathlib import Path

REQUIRED={"symbol","direction","entry","stop_loss","target","risk_reward","final_score","status","signal_id","provenance_complete"}
DIRECTIONS={"LONG","SHORT"}
BLOCKED={"ORDER_SUBMISSION","BROKER_ORDER","AUTO_EXECUTE","AUTOMATIC_EXECUTION","CAPITAL_DEPLOYMENT"}

def load(p):return json.loads(p.read_text(encoding="utf-8"))

def scan(x,path="root"):
    hit=[]
    if isinstance(x,dict):
        for k,v in x.items():
            if str(k).upper() in BLOCKED:hit.append(f"{path}.{k}")
            hit+=scan(v,f"{path}.{k}")
    elif isinstance(x,list):
        for i,v in enumerate(x):hit+=scan(v,f"{path}[{i}]")
    return hit

def main():
    p=argparse.ArgumentParser();p.add_argument("--contract",required=True,type=Path);p.add_argument("--universe",required=True,type=Path);p.add_argument("--output",required=True,type=Path);a=p.parse_args()
    c=load(a.contract);u=load(a.universe);b=load(a.output/"PSY29_FINAL_SIGNAL_BOARD.json");v=load(a.output/"PSY29_STAGE20_VALIDATION.json")
    assert c["stage"]==20 and c["version"]=="1.0" and c["status"]=="LOCKED"
    assert c["signal_policy"]["multiple_signals_allowed"] is True
    assert c["signal_policy"]["daily_signal_cap"] is None
    syms=[str(x["symbol"] if isinstance(x,dict) else x).strip().upper() for x in u["universe"]]
    assert len(syms)==29 and len(set(syms))==29
    assert b["coverage"]=={"expected":29,"actual":29,"unique":29}
    signals=b["signals"]
    assert b["signal_count"]==len(signals)
    assert len({r["symbol"] for r in signals})==len(signals)
    assert set(r["symbol"] for r in signals)<=set(syms)
    for r in signals:
        assert REQUIRED<=set(r)
        assert r["direction"] in DIRECTIONS
        assert r["status"]=="SIGNAL"
        assert r["provenance_complete"] is True
        assert float(r["entry"])>0 and float(r["stop_loss"])>0 and float(r["target"])>0 and float(r["risk_reward"])>0
        assert float(r["final_score"])>=float(c["minimum_score"])
    sorted_copy=sorted(signals,key=lambda r:(-float(r["final_score"]),-float(r["confluence_score"]),-float(r["freshness_score"]),r["symbol"]))
    assert [r["symbol"] for r in signals]==[r["symbol"] for r in sorted_copy]
    assert b["policy"]["multiple_signals_allowed"] is True and b["policy"]["daily_signal_cap"] is None
    assert b["policy"]["forced_trade"] is False and b["policy"]["broker_execution"] is False
    assert all(x.get("memory_state") not in {"ACTIVE_SIGNAL","TRADED"} for x in signals)
    assert v["validation_status"]=="PASS" and v["coverage"]==b["coverage"] and v["broker_execution"] is False
    assert not scan(b)
    print("STAGE 20 HARD VERIFY: PASS")
    print("29/29 coverage: PASS")
    print(f"Signals: {len(signals)}")
    print("Multiple signals: PASS")
    print("Deterministic ranking: PASS")
    print("Trade memory: PASS")
    print("No daily cap: PASS")
    print("Safety boundary: PASS")
    print("Provenance: PASS")

if __name__=="__main__":main()
