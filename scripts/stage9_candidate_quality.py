#!/usr/bin/env python3
"""PSY29 Stage 9 candidate quality/confidence index; never a trade signal."""
from __future__ import annotations
import argparse, json
from pathlib import Path
import pandas as pd

STATES={"EDGE_ACTIVE","EDGE_INACTIVE","DATA_STALE","DATA_INVALID"}
MATCH={"OR_CONTINUATION_MATCH":1.0,"TREND_RATE_MATCH":0.9}
WEIGHTS=(0.40,0.30,0.20,0.10)

def loadj(p): return json.loads(Path(p).read_text(encoding="utf-8"))
def symbols(p):
 r=loadj(p)["universe"]; s=[str(x["symbol"]).upper().strip() for x in r]
 if len(s)!=29 or len(set(s))!=29 or [int(x["rank"]) for x in r]!=list(range(1,30)): raise ValueError("canonical 29 invalid")
 return s

def profiles(p,s):
 r=loadj(p)["profiles"]
 if len(r)!=29: raise ValueError("Stage 5 must contain 29 profiles")
 d={str(x["symbol"]).upper().strip():x for x in r}
 if set(d)!=set(s): raise ValueError("Stage 5 symbols mismatch")
 return d

def csv(p,req,name,s):
 d=pd.read_csv(p); miss=req-set(d.columns)
 if miss: raise ValueError(f"{name} missing {sorted(miss)}")
 d["symbol"]=d["symbol"].astype(str).str.upper().str.strip()
 if len(d)!=29 or d["symbol"].nunique()!=29 or set(d.symbol)!=set(s): raise ValueError(f"{name} coverage invalid")
 return d

def main():
 ap=argparse.ArgumentParser();
 for n in ("universe","profiles","contract","stage6","stage7","stage8","output"): ap.add_argument("--"+n,required=True)
 a=ap.parse_args(); s=symbols(a.universe); p=profiles(a.profiles,s); c=loadj(a.contract)
 if c.get("trade_authorization") is not False or c.get("trade_signal_generation") is not False: raise ValueError("Stage 9 trade flags must be false")
 d6=csv(a.stage6,{"symbol","regime","data_status"},"Stage 6",s)
 d7=csv(a.stage7,{"symbol","activation","reason_code","match_reason"},"Stage 7",s)
 d8=csv(a.stage8,{"symbol","activation","regime","data_status","ranking_score","research_strength_score","live_regime_quality","portfolio_rank","research_profile_source","trade_authorized","trade_signal_generated"},"Stage 8",s)
 if not (d8.research_profile_source=="config/psy29_edge_profiles_v1.json").all() or not (d8.trade_authorized==False).all() or not (d8.trade_signal_generated==False).all(): raise ValueError("Stage 8 provenance/trade flags invalid")
 x6=d6.set_index("symbol"); x7=d7.set_index("symbol"); x8=d8.set_index("symbol"); active_count=int((d8.activation=="EDGE_ACTIVE").sum())
 if active_count==0: raise ValueError("No EDGE_ACTIVE candidates")
 out=[]
 for z in s:
  r=x6.loc[z]; q=x7.loc[z]; h=x8.loc[z]; state=str(q.activation)
  if state not in STATES or state!=str(h.activation) or str(r.regime)!=str(h.regime) or str(r.data_status)!=str(h.data_status): raise ValueError(f"cross-stage mismatch: {z}")
  row={"canonical_rank":int(p[z]["rank"]),"symbol":z,"activation":state,"regime":str(r.regime),"data_status":str(r.data_status),"reason_code":str(q.reason_code),"match_reason":str(q.match_reason),"portfolio_rank":None,"ranking_score":None,"research_strength_score":None,"live_regime_quality":None,"activation_match_quality":None,"portfolio_rank_quality":None,"candidate_quality_score":None,"quality_label":None,"research_profile_source":"config/psy29_edge_profiles_v1.json","research_profile_version":"1.0","stage6_source":"Stage 6 PSY29 Live Regime Engine V2","stage7_source":"Stage 7 PSY29 Research-Conditioned Edge Activation","stage8_source":"Stage 8 PSY29 Portfolio Edge Ranking","trade_authorized":False,"trade_signal_generated":False}
  if state=="EDGE_ACTIVE":
   if str(r.data_status)!="FRESH" or pd.isna(h.portfolio_rank) or pd.isna(h.ranking_score) or str(q.reason_code) not in MATCH: raise ValueError(f"invalid active candidate: {z}")
   research=float(h.research_strength_score); live=float(h.live_regime_quality); rank=int(float(h.portfolio_rank))
   if not (0<=research<=1 and 0<=live<=1 and 1<=rank<=active_count): raise ValueError(f"invalid Stage 8 component: {z}")
   rq=1.0-((rank-1)/max(active_count-1,1))*0.50; mq=MATCH[str(q.reason_code)]; score=100*(WEIGHTS[0]*research+WEIGHTS[1]*live+WEIGHTS[2]*mq+WEIGHTS[3]*rq)
   row.update(portfolio_rank=rank,ranking_score=float(h.ranking_score),research_strength_score=round(research,8),live_regime_quality=round(live,4),activation_match_quality=mq,portfolio_rank_quality=round(rq,4),candidate_quality_score=round(score,4),quality_label="HIGH" if score>=80 else "MEDIUM" if score>=60 else "LOW")
  out.append(row)
 df=pd.DataFrame(out).sort_values("canonical_rank").reset_index(drop=True); act=df.activation=="EDGE_ACTIVE"; non=~act
 ok=len(df)==29 and df.symbol.nunique()==29 and set(df.activation)<=STATES and df.loc[non,"candidate_quality_score"].isna().all() and df.loc[non,"portfolio_rank"].isna().all() and df.loc[act,"candidate_quality_score"].notna().all() and df.loc[act,"portfolio_rank"].notna().all() and (df.trade_authorized==False).all() and (df.trade_signal_generated==False).all()
 o=Path(a.output); o.mkdir(parents=True,exist_ok=True); df.to_csv(o/"PSY29_STAGE9_CANDIDATE_QUALITY.csv",index=False)
 ad=df[act].sort_values("candidate_quality_score",ascending=False)
 sm={"stage":9,"engine":"PSY29_LIVE_CANDIDATE_QUALITY_CONFIDENCE","engine_execution_status":"PASS","validation_status":"PASS" if ok else "FAIL","status":"PASS" if ok else "FAIL","coverage":len(df),"edge_active_count":int(act.sum()),"edge_inactive_count":int((df.activation=="EDGE_INACTIVE").sum()),"data_stale_count":int((df.activation=="DATA_STALE").sum()),"data_invalid_count":int((df.activation=="DATA_INVALID").sum()),"scored_count":int(act.sum()),"scored_symbols":ad.symbol.tolist(),"quality_score_is_probability":False,"trade_authorized":False,"trade_signal_generated":False,"fail_closed":True,"research_profile_source":"config/psy29_edge_profiles_v1.json","stage6_source":"Stage 6 PSY29 Live Regime Engine V2","stage7_source":"Stage 7 PSY29 Research-Conditioned Edge Activation","stage8_source":"Stage 8 PSY29 Portfolio Edge Ranking"}
 (o/"stage9_summary.json").write_text(json.dumps(sm,indent=2),encoding="utf-8")
 if not ok: raise SystemExit("STAGE 9 VALIDATION FAILED")
 print(json.dumps(sm,indent=2))
if __name__=="__main__": main()
