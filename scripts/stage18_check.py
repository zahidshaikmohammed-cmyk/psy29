#!/usr/bin/env python3
"""Hard verifier for PSY29 Stage 18."""
from __future__ import annotations
import argparse,csv,json,sys
from pathlib import Path

ALLOWED={"CONTINUOUS","CHANGED","NEW_STATE","PERSISTENT_DETERIORATION","PERSISTENT_INVALIDATION","RECOVERED","HISTORY_UNAVAILABLE","HISTORY_INVALID","PROVENANCE_FAIL"}
BLOCKED={"TRADE_READY","TRADE_SIGNAL","TRADE_AUTHORIZED","CE","PE","ENTRY","ENTRY_PRICE","STOP_LOSS","TAKE_PROFIT","TARGET","POSITION_SIZE","RISK","CAPITAL_ALLOCATION","ORDER","EXECUTION","FUTURE_PRICE_PREDICTION","DIRECTIONAL_RECOMMENDATION"}

def scan(x,path="root"):
 out=[]
 if isinstance(x,dict):
  for k,v in x.items():
   if str(k).upper() in BLOCKED: out.append(f"{path}.{k}")
   out.extend(scan(v,f"{path}.{k}"))
 elif isinstance(x,list):
  for i,v in enumerate(x): out.extend(scan(v,f"{path}[{i}]"))
 return out

def main():
 p=argparse.ArgumentParser(); p.add_argument("--contract",required=True,type=Path); p.add_argument("--universe",required=True,type=Path); p.add_argument("--output",required=True,type=Path); a=p.parse_args()
 c=json.loads(a.contract.read_text(encoding="utf-8")); u=json.loads(a.universe.read_text(encoding="utf-8"))
 assert c["stage"]==18 and c["version"]=="1.0" and c["status"]=="LOCKED"
 syms=[x["symbol"] for x in u["universe"]]; assert len(syms)==29 and len(set(syms))==29
 board=json.loads((a.output/"PSY29_STAGE18_HISTORICAL_BOARD.json").read_text(encoding="utf-8"))
 val=json.loads((a.output/"PSY29_STAGE18_VALIDATION.json").read_text(encoding="utf-8"))
 rows=board["records"]; assert len(rows)==29 and len({r["symbol"] for r in rows})==29
 assert {r["symbol"] for r in rows}==set(syms)
 assert all(r["stage18_state"] in ALLOWED for r in rows)
 assert all(r["provenance_complete"] is True for r in rows)
 assert val["validation_status"]=="PASS"
 assert val["coverage"]=={"expected":29,"actual":29,"unique":29}
 assert val["blocked_fields"]==[]
 assert scan(board)==[]
 assert c["coverage"]["expected"]==29 and c["coverage"]["partial_pass"] is False
 assert c["fail_closed"] is True and c["provenance_required"] is True and c["cross_stage_consistency_required"] is True
 for k,v in c["safety_boundaries"].items(): assert v is False, f"Safety boundary enabled: {k}"
 print("PSY29 STAGE 18 HARD VERIFY: PASS")
 print("29/29 coverage: PASS")
 print("Allowed-state integrity: PASS")
 print("Provenance: PASS")
 print("Safety boundaries: PASS")
 print("Fail-closed contract: PASS")

if __name__=="__main__":
 try: main()
 except Exception as e: print(f"PSY29 STAGE 18 HARD VERIFY FAIL: {e}",file=sys.stderr); raise
