#!/usr/bin/env python3
"""PSY29 Stage 10 integrity/provenance gate; never a trading decision."""
from __future__ import annotations
import argparse,json,math
from pathlib import Path
import pandas as pd

STATES={"INTEGRITY_PASS","INTEGRITY_FAIL","DATA_STALE","DATA_INVALID"}
ACTIVATIONS={"EDGE_ACTIVE","EDGE_INACTIVE","DATA_STALE","DATA_INVALID"}

def loadj(p): return json.loads(Path(p).read_text(encoding="utf-8"))
def canon(p):
 u=loadj(p)["universe"]
 if len(u)!=29: raise ValueError("canonical universe count != 29")
 s=[str(x["symbol"]).upper().strip() for x in u]
 if len(set(s))!=29 or [int(x["rank"]) for x in u]!=list(range(1,30)): raise ValueError("canonical universe invalid")
 return s

def profiles(p,s):
 r=loadj(p)["profiles"]
 d={str(x["symbol"]).upper().strip():x for x in r}
 if len(r)!=29 or len(d)!=29 or set(d)!=set(s): raise ValueError("Stage 5 coverage invalid")
 return d

def csv(p,req,name,s):
 d=pd.read_csv(p)
 miss=req-set(d.columns)
 if miss: raise ValueError(f"{name} missing {sorted(miss)}")
 d["symbol"]=d["symbol"].astype(str).str.upper().str.strip()
 if len(d)!=29 or d.symbol.nunique()!=29 or set(d.symbol)!=set(s): raise ValueError(f"{name} coverage invalid")
 return d.set_index("symbol")

def finite(x):
 try:return math.isfinite(float(x))
 except:return False

def main():
 ap=argparse.ArgumentParser()
 for n in ("universe","profiles","contract","stage6","stage7","stage8","stage9","output"): ap.add_argument("--"+n,required=True)
 a=ap.parse_args(); s=canon(a.universe); p=profiles(a.profiles,s); c=loadj(a.contract)
 if any(c.get(k) is not False for k in ("trade_authorization","trade_signal_generation")): raise ValueError("contract safety flags invalid")
 d6=csv(a.stage6,{"symbol","regime","data_status"},"Stage 6",s)
 d7=csv(a.stage7,{"symbol","activation","reason_code","match_reason"},"Stage 7",s)
 d8=csv(a.stage8,{"symbol","activation","regime","data_status","portfolio_rank","ranking_score","research_profile_source","trade_authorized","trade_signal_generated"},"Stage 8",s)
 d9=csv(a.stage9,{"symbol","activation","regime","data_status","candidate_quality_score","research_profile_source","stage6_source","stage7_source","stage8_source","trade_authorized","trade_signal_generated"},"Stage 9",s)
 out=[]; run_invalid=False
 for z in s:
  r=d6.loc[z]; q=d7.loc[z]; h=d8.loc[z]; j=d9.loc[z]; gates={}; reasons=[]
  research_ok=z in p and str(j.research_profile_source)=="config/psy29_edge_profiles_v1.json" and str(h.research_profile_source)=="config/psy29_edge_profiles_v1.json"
  gates["research_profile_integrity"]=research_ok
  if not research_ok: reasons.append("Stage 5 profile/provenance mismatch")
  live_status=str(r.data_status)
  live_ok=live_status in {"FRESH","DATA_STALE","DATA_INVALID"}
  gates["live_data_integrity"]=live_ok
  if not live_ok: reasons.append(f"invalid Stage 6 data_status={live_status}")
  edge=str(q.activation) in ACTIVATIONS
  gates["edge_state_integrity"]=edge
  if not edge: reasons.append("invalid Stage 7 activation state")
  rank_ok=True
  if str(h.activation)=="EDGE_ACTIVE": rank_ok=finite(h.ranking_score) and 0<=float(h.ranking_score)<=1 and str(h.portfolio_rank).strip() not in {"","nan","None"} and int(float(h.portfolio_rank))>=1
  else: rank_ok=pd.isna(h.portfolio_rank) and pd.isna(h.ranking_score)
  gates["ranking_integrity"]=rank_ok
  if not rank_ok: reasons.append("Stage 8 ranking fields inconsistent with activation")
  quality_ok=True
  if str(j.activation)=="EDGE_ACTIVE": quality_ok=finite(j.candidate_quality_score) and 0<=float(j.candidate_quality_score)<=100
  else: quality_ok=pd.isna(j.candidate_quality_score)
  gates["quality_integrity"]=quality_ok
  if not quality_ok: reasons.append("Stage 9 quality fields inconsistent with activation")
  cross=(str(q.activation)==str(h.activation)==str(j.activation) and str(r.regime)==str(h.regime)==str(j.regime) and str(r.data_status)==str(h.data_status)==str(j.data_status) and bool(h.trade_authorized) is False and bool(h.trade_signal_generated) is False and bool(j.trade_authorized) is False and bool(j.trade_signal_generated) is False)
  gates["cross_stage_consistency"]=cross
  if not cross: reasons.append("Stage 6-9 state/regime/trade-flag contradiction")
  prov=all(str(j[k]).strip() for k in ("stage6_source","stage7_source","stage8_source"))
  gates["provenance_integrity"]=prov
  if not prov: reasons.append("Stage 9 provenance incomplete")
  if live_status=="DATA_INVALID" or str(q.activation)=="DATA_INVALID": state="DATA_INVALID"
  elif live_status=="DATA_STALE" or str(q.activation)=="DATA_STALE": state="DATA_STALE"
  elif all(gates.values()): state="INTEGRITY_PASS"
  else: state="INTEGRITY_FAIL"
  if state=="DATA_INVALID": run_invalid=True
  out.append({"canonical_rank":int(p[z]["rank"]),"symbol":z,"integrity_state":state,"activation":str(q.activation),"regime":str(r.regime),"data_status":live_status,"gate_results":json.dumps(gates,sort_keys=True),"gate_reasons":"PASS" if not reasons else "; ".join(reasons),"research_provenance":"config/psy29_edge_profiles_v1.json","stage6_provenance":str(j.stage6_source),"stage7_provenance":str(j.stage7_source),"stage8_provenance":str(j.stage8_source),"stage9_provenance":"Stage 9 PSY29 Candidate Quality Confidence","trade_ready_output":False,"trade_authorized":False,"trade_signal_generated":False})
 df=pd.DataFrame(out).sort_values("canonical_rank").reset_index(drop=True)
 ok=len(df)==29 and df.symbol.nunique()==29 and not run_invalid and (df.integrity_state.isin(STATES)).all() and (df.trade_ready_output==False).all() and (df.trade_authorized==False).all() and (df.trade_signal_generated==False).all()
 o=Path(a.output); o.mkdir(parents=True,exist_ok=True); df.to_csv(o/"PSY29_STAGE10_INTEGRITY.csv",index=False)
 sm={"stage":10,"engine":"PSY29_LIVE_CANDIDATE_INTEGRITY_PROVENANCE_GATE","engine_execution_status":"PASS","validation_status":"PASS" if ok else "FAIL","status":"PASS" if ok else "FAIL","coverage":len(df),"integrity_pass_count":int((df.integrity_state=="INTEGRITY_PASS").sum()),"integrity_fail_count":int((df.integrity_state=="INTEGRITY_FAIL").sum()),"data_stale_count":int((df.integrity_state=="DATA_STALE").sum()),"data_invalid_count":int((df.integrity_state=="DATA_INVALID").sum()),"trade_ready_output":False,"trade_authorized":False,"trade_signal_generated":False,"fail_closed":True}
 (o/"stage10_summary.json").write_text(json.dumps(sm,indent=2),encoding="utf-8")
 if not ok: raise SystemExit("STAGE 10 INTEGRITY VALIDATION FAILED")
 print(json.dumps(sm,indent=2))
if __name__=="__main__": main()
