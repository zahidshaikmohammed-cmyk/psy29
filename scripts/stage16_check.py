#!/usr/bin/env python3
"""PSY29 Stage 16 hard verification."""
from __future__ import annotations
import argparse,json,csv
from pathlib import Path

BLOCKED={"TRADE_READY","TRADE_SIGNAL","TRADE_AUTHORIZED","CE","PE","ENTRY","ENTRY_PRICE","STOP_LOSS","TAKE_PROFIT","TARGET","POSITION_SIZE","RISK","CAPITAL_ALLOCATION","ORDER","EXECUTION"}

def load(p):return json.loads(p.read_text(encoding="utf-8"))

def scan(x,p="root"):
 out=[]
 if isinstance(x,dict):
  for k,v in x.items():
   if str(k).upper() in BLOCKED:out.append(f"{p}.{k}")
   out+=scan(v,f"{p}.{k}")
 elif isinstance(x,list):
  for i,v in enumerate(x):out+=scan(v,f"{p}[{i}]")
 return out

def main():
 ap=argparse.ArgumentParser();ap.add_argument("--universe",required=True,type=Path);ap.add_argument("--output",required=True,type=Path);a=ap.parse_args()
 u=load(a.universe);syms=[str(x["symbol"]).upper() for x in u["universe"]]
 assert len(syms)==29 and len(set(syms))==29,"canonical 29 failure"
 j=load(a.output/"PSY29_STAGE16_CURRENT_BOARD.json");r=j["records"]
 assert j["stage"]==16 and j["version"]=="1.0"
 assert j["coverage"]=={"expected":29,"actual":29,"unique":29}
 assert len(r)==29 and len({x["symbol"] for x in r})==29
 assert {x["symbol"] for x in r}==set(syms)
 assert all(x["system_state"] in {"PRIMARY_CANDIDATE","SECONDARY_CANDIDATE","WATCHLIST","INACTIVE","DATA_STALE","DATA_INVALID","INTEGRITY_FAIL","CONSISTENCY_FAIL"} for x in r)
 assert all(x["provenance_complete"] is True for x in r)
 assert all(x["consistency_ok"] is True for x in r)
 assert all(x["data_status"]=="FRESH" for x in r)
 bad=scan(j);assert not bad,"blocked fields: "+str(bad)
 v=load(a.output/"PSY29_STAGE16_VALIDATION.json");assert v["validation_status"]=="PASS"
 assert all(v["checks"].values())
 with (a.output/"PSY29_STAGE16_CURRENT_BOARD.csv").open(encoding="utf-8") as h:assert len(list(csv.DictReader(h)))==29
 print("PSY29 STAGE 16 HARD VERIFY: PASS");print("Canonical coverage: 29/29");print("All required provenance and consistency checks: PASS")
if __name__=="__main__":main()
