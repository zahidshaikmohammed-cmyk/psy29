#!/usr/bin/env python3
"""PSY29 Stage 11 — Live Execution-Analysis Engine.

Stage 11 analyses validated live structure only. It never generates,
authorizes, prices, sizes, or executes a trade.

Fix preserved in-place: session_high/session_low are consumed from the
canonical live acquisition snapshot. They are NOT reconstructed from the
latest 5-minute candle.
"""
from __future__ import annotations
import argparse,json,math
from datetime import datetime,timezone
from pathlib import Path
from typing import Any
import pandas as pd

ANALYSIS_STATES={"EXECUTION_ANALYSIS_VALID","EXECUTION_ANALYSIS_INCOMPLETE","DATA_STALE","DATA_INVALID","BLOCKED_UPSTREAM"}
STRUCTURE_STATES={"TRENDING_UP","TRENDING_DOWN","RANGE","BREAKOUT_STRUCTURE","BREAKDOWN_STRUCTURE","TRANSITION","UNCLEAR"}
QUALITY_STATES={"STRONG","MODERATE","WEAK","UNCONFIRMED"}
EVENT_STATES={"NO_EVENT","APPROACHING_LEVEL","BREAKOUT_OBSERVED","BREAKDOWN_OBSERVED","RETEST","CONTINUATION","FAILED_BREAK","UNCONFIRMED"}
ALIGNMENT_STATES={"HIGH","PARTIAL","LOW","NOT_APPLICABLE","UNCONFIRMED"}
FRESH_MAX_AGE_SECONDS=90
STALE_MAX_AGE_SECONDS=180
LIVE_REQUIRED_FIELDS={
 "symbol","timestamp","open_1m","high_1m","low_1m","close_1m","volume_1m","avg_volume_20_1m",
 "open_5m","high_5m","low_5m","close_5m","volume_5m","avg_volume_20_5m","vwap_5m","ema9_5m","ema20_5m",
 "first15_high","first15_low","swing_high","swing_low","session_high","session_low"
}

def load_json(path):
 p=Path(path)
 if not p.exists(): raise FileNotFoundError(f"Required JSON file does not exist: {p}")
 return json.loads(p.read_text(encoding="utf-8"))

def finite(v,name):
 try: x=float(v)
 except (TypeError,ValueError) as e: raise ValueError(f"{name} is not numeric") from e
 if not math.isfinite(x): raise ValueError(f"{name} is non-finite")
 return x

def parse_ts(v):
 if not str(v).strip(): raise ValueError("timestamp is empty")
 try: x=datetime.fromisoformat(str(v).replace("Z","+00:00"))
 except ValueError as e: raise ValueError(f"invalid timestamp: {v}") from e
 if x.tzinfo is None: raise ValueError("timestamp must be timezone-aware")
 return x.astimezone(timezone.utc)

def age_seconds(v,now):
 a=(now-parse_ts(v)).total_seconds()
 if a < -5: raise ValueError("timestamp is materially in the future")
 return max(0.0,a)

def norm(df,name):
 missing=LIVE_REQUIRED_FIELDS-set(df.columns)
 if missing: raise ValueError(f"{name} missing required fields: {sorted(missing)}")
 df=df.copy();df.symbol=df.symbol.astype(str).str.upper().str.strip()
 return df

def canonical(path):
 rows=load_json(path).get("universe",[])
 if len(rows)!=29: raise ValueError("Canonical universe must contain exactly 29 rows")
 syms=[str(r.get("symbol","")).upper().strip() for r in rows]
 ranks=[int(r.get("rank",0)) for r in rows]
 if not all(syms) or len(set(syms))!=29 or ranks!=list(range(1,30)): raise ValueError("Canonical universe must contain 29 unique symbols ranked 1-29")
 return syms

def load_table(path,required,name,syms):
 p=Path(path)
 if not p.exists(): raise FileNotFoundError(f"{name} output missing: {path}")
 d=pd.read_csv(p);missing=set(required)-set(d.columns)
 if missing: raise ValueError(f"{name} missing required fields: {sorted(missing)}")
 d["symbol"]=d.symbol.astype(str).str.upper().str.strip()
 if len(d)!=29 or d.symbol.nunique()!=29 or set(d.symbol)!=set(syms): raise ValueError(f"{name} must contain exactly the canonical 29 symbols")
 return d.set_index("symbol")

def structure(c,v,e9,e20,orh,orl):
 bull=c>v and e9>e20; bear=c<v and e9<e20
 if bull and c>orh: return "BREAKOUT_STRUCTURE","5m close above opening-range high with bullish VWAP/EMA alignment"
 if bear and c<orl: return "BREAKDOWN_STRUCTURE","5m close below opening-range low with bearish VWAP/EMA alignment"
 if bull: return "TRENDING_UP","price above VWAP and EMA9 above EMA20"
 if bear: return "TRENDING_DOWN","price below VWAP and EMA9 below EMA20"
 if c>v: return "TRANSITION","price above VWAP without full EMA alignment"
 if c<v: return "TRANSITION","price below VWAP without full EMA alignment"
 return "RANGE","price remains at VWAP / non-directional structure"

def quality(close,open_,high,low,vol,avg):
 rng=high-low
 if rng<=0 or avg<=0:return "UNCONFIRMED","invalid candle range or average volume"
 vr=vol/avg;br=abs(close-open_)/rng
 q="STRONG" if vr>=1.5 and br>=.6 else "MODERATE" if vr>=1 and br>=.4 else "WEAK" if vr>0 and br>=.2 else "UNCONFIRMED"
 return q,f"volume_ratio={vr:.2f}; body_ratio={br:.2f}"

def event(c,orh,orl,sh,sl):
 if c>orh:return "BREAKOUT_OBSERVED","5m close is above opening-range high"
 if c<orl:return "BREAKDOWN_OBSERVED","5m close is below opening-range low"
 scale=max(abs(c),abs(orh),abs(orl),1.0);p=scale*.0025
 if abs(c-orh)<=p or abs(c-orl)<=p:return "APPROACHING_LEVEL","5m close is near an opening-range boundary"
 if abs(c-sh)<=p or abs(c-sl)<=p:return "RETEST","5m close is near a recent swing level"
 return "NO_EVENT","no defined breakout, breakdown, or retest event"

def alignment(r7,regime,ev,struct):
 activation=str(r7.activation).strip().upper();reason=str(r7.reason_code).strip().upper();matched=[];missing=[];conflicts=[]
 if activation!="EDGE_ACTIVE": return "NOT_APPLICABLE","Stage 7 edge is not active",[],["Stage 7 edge is not active"],[]
 if reason=="OR_CONTINUATION_MATCH":
  matched.append("historical_or_continuation_condition")
  if ev in {"BREAKOUT_OBSERVED","BREAKDOWN_OBSERVED","CONTINUATION"}:matched.append("live_directional_event")
  else:missing.append("confirmed_directional_event")
  if regime in {"BULLISH_BREAKOUT_REGIME","BEARISH_BREAKDOWN_REGIME"}:matched.append("live_directional_regime")
  else:missing.append("strong_directional_regime")
 elif reason=="TREND_RATE_MATCH":
  matched.append("historical_trend_rate_condition")
  if struct in {"TRENDING_UP","TRENDING_DOWN","BREAKOUT_STRUCTURE","BREAKDOWN_STRUCTURE"}:matched.append("live_directional_structure")
  else:missing.append("directional_market_structure")
  if regime in {"BULLISH_ALIGNMENT_REGIME","BEARISH_ALIGNMENT_REGIME","BULLISH_WEAK_ALIGNMENT_REGIME","BEARISH_WEAK_ALIGNMENT_REGIME"}:matched.append("live_regime_alignment")
  else:missing.append("directional_live_regime")
 else:missing.append("recognized_stage7_activation_reason")
 state="LOW" if conflicts else "UNCONFIRMED" if not matched else "HIGH" if not missing else "PARTIAL"
 return state,f"matched={len(matched)}; missing={len(missing)}; conflicts={len(conflicts)}",matched,missing,conflicts

def validate_live(r):
 for f in LIVE_REQUIRED_FIELDS-{"symbol","timestamp"}:finite(r[f],f)
 for f in ("volume_1m","avg_volume_20_1m","volume_5m","avg_volume_20_5m"):
  if finite(r[f],f)<0:raise ValueError(f"{f} cannot be negative")
 if r.high_1m<r.low_1m or r.high_5m<r.low_5m:raise ValueError("invalid OHLC range")
 if r.first15_high<r.first15_low or r.swing_high<r.swing_low:raise ValueError("invalid structural range")
 if r.session_high<r.session_low:raise ValueError("session_high is below session_low")
 if r.avg_volume_20_1m<=0 or r.avg_volume_20_5m<=0:raise ValueError("average volume must be positive")

def main():
 ap=argparse.ArgumentParser();ap.add_argument("--universe",required=True);ap.add_argument("--profiles",required=True);ap.add_argument("--contract",required=True);ap.add_argument("--stage6",required=True);ap.add_argument("--stage7",required=True);ap.add_argument("--stage8",required=True);ap.add_argument("--stage9",required=True);ap.add_argument("--stage10",required=True);ap.add_argument("--live-snapshot",required=True);ap.add_argument("--output",required=True);a=ap.parse_args()
 out=Path(a.output);out.mkdir(parents=True,exist_ok=True);syms=canonical(a.universe);profiles=load_json(a.profiles).get("profiles",[])
 if len(profiles)!=29:raise ValueError("Stage 5 profile count must be exactly 29")
 s6=load_table(a.stage6,{"symbol","regime","data_status"},"Stage 6",syms);s7=load_table(a.stage7,{"symbol","regime","data_status","activation","reason_code","match_reason"},"Stage 7",syms);s8=load_table(a.stage8,{"symbol","activation","regime","data_status","portfolio_rank","ranking_score","research_profile_source","trade_authorized","trade_signal_generated"},"Stage 8",syms);s9=load_table(a.stage9,{"symbol","activation","regime","data_status","candidate_quality_score","research_profile_source","stage6_source","stage7_source","stage8_source","trade_authorized","trade_signal_generated"},"Stage 9",syms);s10=load_table(a.stage10,{"symbol","integrity_state","activation","regime","data_status","gate_results","gate_reasons","research_provenance","stage6_provenance","stage7_provenance","stage8_provenance","stage9_provenance","trade_ready_output","trade_authorized","trade_signal_generated"},"Stage 10",syms)
 live=norm(pd.read_csv(a.live_snapshot),"Stage 11 live snapshot")
 if len(live)!=29 or live.symbol.nunique()!=29 or set(live.symbol)!=set(syms):raise ValueError("Stage 11 live snapshot must contain canonical 29 symbols")
 live=live.set_index("symbol");now=datetime.now(timezone.utc);rows=[]
 for sym in syms:
  r10=s10.loc[sym];r7=s7.loc[sym];r6=s6.loc[sym];lr=live.loc[sym]
  prov={"research_provenance":str(r10.research_provenance),"stage6_provenance":str(r10.stage6_provenance),"stage7_provenance":str(r10.stage7_provenance),"stage8_provenance":str(r10.stage8_provenance),"stage9_provenance":str(r10.stage9_provenance),"stage10_provenance":"Stage 10 PSY29 Candidate Integrity Provenance","stage11_provenance":"PSY29 Stage 11 Live Execution-Analysis Engine v1.1"}
  result={"canonical_rank":int(next(x["rank"] for x in profiles if str(x["symbol"]).upper().strip()==sym)),"symbol":sym,"analysis_state":"BLOCKED_UPSTREAM","structure_state":"UNCLEAR","structure_reason":None,"price_volume_quality":"UNCONFIRMED","price_volume_reason":None,"session_high":None,"session_low":None,"opening_range_high":None,"opening_range_low":None,"swing_high":None,"swing_low":None,"event_state":"UNCONFIRMED","event_reason":None,"research_live_alignment":"UNCONFIRMED","alignment_reason":None,"matched_conditions":"NONE","missing_conditions":"NONE","conflicting_conditions":"NONE","live_data_timestamp":str(lr.timestamp),**prov,"trade_ready_output":False,"trade_authorized":False,"trade_signal_generated":False}
  integrity=str(r10.integrity_state).strip().upper()
  if integrity!="INTEGRITY_PASS":
   result["analysis_state"]={"DATA_STALE":"DATA_STALE","DATA_INVALID":"DATA_INVALID"}.get(integrity,"BLOCKED_UPSTREAM");result["event_reason"]="Stage 10 did not return INTEGRITY_PASS";rows.append(result);continue
  try:
   age=age_seconds(lr.timestamp,now)
   if age>STALE_MAX_AGE_SECONDS:raise RuntimeError("STALE_INVALID_THRESHOLD")
   if age>FRESH_MAX_AGE_SECONDS:raise RuntimeError("STALE_FRESHNESS_THRESHOLD")
   validate_live(lr)
   ss,sr=structure(finite(lr.close_5m,"close_5m"),finite(lr.vwap_5m,"vwap_5m"),finite(lr.ema9_5m,"ema9_5m"),finite(lr.ema20_5m,"ema20_5m"),finite(lr.first15_high,"first15_high"),finite(lr.first15_low,"first15_low"))
   pq,pqr=quality(finite(lr.close_1m,"close_1m"),finite(lr.open_1m,"open_1m"),finite(lr.high_1m,"high_1m"),finite(lr.low_1m,"low_1m"),finite(lr.volume_1m,"volume_1m"),finite(lr.avg_volume_20_1m,"avg_volume_20_1m"))
   ev,er=event(finite(lr.close_5m,"close_5m"),finite(lr.first15_high,"first15_high"),finite(lr.first15_low,"first15_low"),finite(lr.swing_high,"swing_high"),finite(lr.swing_low,"swing_low"))
   al,ar,matched,missing,conflicts=alignment(r7,str(r6.regime),ev,ss)
   state="EXECUTION_ANALYSIS_VALID" if all([ss in STRUCTURE_STATES,pq in QUALITY_STATES,ev in EVENT_STATES,al in ALIGNMENT_STATES]) else "EXECUTION_ANALYSIS_INCOMPLETE"
   result.update({"analysis_state":state,"structure_state":ss,"structure_reason":sr,"price_volume_quality":pq,"price_volume_reason":pqr,"session_high":finite(lr.session_high,"session_high"),"session_low":finite(lr.session_low,"session_low"),"opening_range_high":finite(lr.first15_high,"first15_high"),"opening_range_low":finite(lr.first15_low,"first15_low"),"swing_high":finite(lr.swing_high,"swing_high"),"swing_low":finite(lr.swing_low,"swing_low"),"event_state":ev,"event_reason":er,"research_live_alignment":al,"alignment_reason":ar,"matched_conditions":";".join(matched) or "NONE","missing_conditions":";".join(missing) or "NONE","conflicting_conditions":";".join(conflicts) or "NONE"})
  except RuntimeError as e:
   msg=str(e);result["analysis_state"]="DATA_INVALID" if "INVALID" in msg else "DATA_STALE";result["event_reason"]=msg
  except Exception as e:
   result["analysis_state"]="DATA_INVALID";result["event_reason"]=str(e)
  rows.append(result)
 df=pd.DataFrame(rows).sort_values("canonical_rank").reset_index(drop=True)
 for f in ("trade_ready_output","trade_authorized","trade_signal_generated"):df[f]=False
 errors=[]
 if len(df)!=29 or df.symbol.nunique()!=29 or set(df.symbol)!=set(syms):errors.append("canonical 29-row coverage failure")
 for col,allowed in (("analysis_state",ANALYSIS_STATES),("structure_state",STRUCTURE_STATES),("price_volume_quality",QUALITY_STATES),("event_state",EVENT_STATES),("research_live_alignment",ALIGNMENT_STATES)):
  if not set(df[col]).issubset(allowed):errors.append(f"invalid {col}")
 if not (df[["trade_ready_output","trade_authorized","trade_signal_generated"]]==False).all().all():errors.append("safety violation")
 df.to_csv(out/"PSY29_STAGE11_EXECUTION_ANALYSIS.csv",index=False)
 summary={"stage":11,"engine":"PSY29_LIVE_EXECUTION_ANALYSIS_ENGINE","engine_execution_status":"PASS","validation_status":"PASS" if not errors else "FAIL","status":"PASS" if not errors else "FAIL","coverage":len(df),"expected_coverage":29,"execution_analysis_valid_count":int((df.analysis_state=="EXECUTION_ANALYSIS_VALID").sum()),"execution_analysis_incomplete_count":int((df.analysis_state=="EXECUTION_ANALYSIS_INCOMPLETE").sum()),"blocked_upstream_count":int((df.analysis_state=="BLOCKED_UPSTREAM").sum()),"data_stale_count":int((df.analysis_state=="DATA_STALE").sum()),"data_invalid_count":int((df.analysis_state=="DATA_INVALID").sum()),"validation_errors":errors,"session_extreme_policy":"CONSUME_ACQUISITION_SESSION_EXTREMES","trade_ready_output":False,"trade_authorized":False,"trade_signal_generated":False,"ce_pe_selection":False,"entry_calculation":False,"stop_loss_calculation":False,"target_calculation":False,"position_sizing":False,"execution":False,"capital_allocation":False,"order_generation":False,"fail_closed":True}
 (out/"stage11_summary.json").write_text(json.dumps(summary,indent=2),encoding="utf-8");print(json.dumps(summary,indent=2))
 if errors:raise SystemExit("PSY29 STAGE 11 HARD VALIDATION FAILED")
if __name__=="__main__":main()
