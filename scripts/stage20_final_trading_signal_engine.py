#!/usr/bin/env python3
"""PSY29 Stage 20 — Final Trading Signal & Strategy Engine v1.0."""
from __future__ import annotations
import argparse,csv,hashlib,json,math,sys
from datetime import datetime,timezone
from pathlib import Path
SCENARIOS={"BREAKOUT","BREAKDOWN","CONTINUATION","RETEST"};BLOCKED={"ORDER","BROKER_ORDER","EXECUTE","EXECUTION","CAPITAL_ALLOCATION","POSITION_SIZE"};FRESH_MAX_AGE_SECONDS=90

def load(p):
 text=p.read_text(encoding="utf-8").strip()
 if not text:return []
 if p.suffix.lower()==".csv":
  with p.open(encoding="utf-8",newline="") as f:return list(csv.DictReader(f))
 return json.loads(text)

def rows(x):
 if isinstance(x,list):return [r for r in x if isinstance(r,dict)]
 if isinstance(x,dict):
  for k in ("records","rows","data","items","snapshot"):
   if isinstance(x.get(k),list):return [r for r in x[k] if isinstance(r,dict)]
  return [x]
 return []

def val(r,*ks):
 d={str(k).lower():v for k,v in r.items()}
 for k in ks:
  if k.lower() in d:return d[k.lower()]
 return None

def sym(r):
 x=val(r,"symbol","ticker","tradingsymbol");return str(x).strip().upper() if x not in (None,"") else None

def num(r,*ks):
 x=val(r,*ks)
 try:return float(x)
 except (TypeError,ValueError):return None

def parse_ts(x):
 if x in (None,""):return None
 try:d=datetime.fromisoformat(str(x).strip().replace("Z","+00:00"))
 except ValueError:return None
 return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc)

def record_ts(r,*keys):
 for k in keys:
  d=parse_ts(val(r,k))
  if d:return d
 return None

def fresh(r,now):
 t=record_ts(r,"live_data_timestamp","timestamp","generated_at","as_of","data_timestamp")
 if t is None:return False,None,"missing timestamp"
 age=(now-t).total_seconds()
 if age < -5:return False,age,"future timestamp"
 if age > FRESH_MAX_AGE_SECONDS:return False,age,f"timestamp age {age:.1f}s exceeds {FRESH_MAX_AGE_SECONDS}s"
 return True,age,"fresh"

def index(p,expected,name):
 out={}
 for r in rows(load(p)):
  s=sym(r)
  if not s:raise ValueError(f"{name}: missing symbol")
  if s in out:raise ValueError(f"{name}: duplicate {s}")
  out[s]=r
 if set(out)!=expected:raise ValueError(f"{name}: canonical 29 coverage failure")
 return out

def universe(p):
 d=load(p);u=d.get("universe") if isinstance(d,dict) else None;s=[str(x["symbol"]).strip().upper() for x in u]
 if len(s)!=29 or len(set(s))!=29:raise ValueError("canonical universe must be exactly 29 unique symbols")
 return s

def memory(p,expected):
 if not p.exists():return {s:"NONE" for s in expected}
 out={s:"NONE" for s in expected}
 for r in rows(load(p)):
  s=sym(r)
  if s in expected:out[s]=str(val(r,"state","memory_state","status") or "NONE").upper()
 return out

def scenario(r):
 x=str(val(r,"stage13_scenario","scenario","dominant_scenario") or "").upper()
 if "BREAKOUT" in x:return "BREAKOUT"
 if "BREAKDOWN" in x:return "BREAKDOWN"
 if "RETEST" in x:return "RETEST"
 if "CONTINUATION" in x or x in {"TRENDING_UP","TRENDING_DOWN"}:return "CONTINUATION"
 return x

def direction(r11,sc):
 st=str(val(r11,"structure_state") or "").upper()
 if sc=="BREAKOUT":return "LONG" if st=="BREAKOUT_STRUCTURE" else None
 if sc=="BREAKDOWN":return "SHORT" if st=="BREAKDOWN_STRUCTURE" else None
 if sc in {"CONTINUATION","RETEST"}:
  if st in {"TRENDING_UP","BREAKOUT_STRUCTURE"}:return "LONG"
  if st in {"TRENDING_DOWN","BREAKDOWN_STRUCTURE"}:return "SHORT"
 return None

def strategy_levels(r11,direction,sc,config):
 close=num(r11,"close_5m");orh=num(r11,"first15_high");orl=num(r11,"first15_low");sh=num(r11,"swing_high");sl=num(r11,"swing_low");session_high=num(r11,"session_high");session_low=num(r11,"session_low")
 if any(x is None or not math.isfinite(x) for x in (close,orh,orl,sh,sl)):return None
 spec=config.get("strategies",{}).get(sc,{})
 if spec.get("required_levels")!=["entry","stop_loss","take_profit"]:return None
 try:buffer_pct=float(spec.get("confirmation_buffer_pct",0.0))
 except (TypeError,ValueError):return None
 if buffer_pct<0 or not math.isfinite(buffer_pct):return None
 if sc=="BREAKOUT" and direction=="LONG":
  entry=orh*(1+buffer_pct/100.0);stop=orl;target=session_high if session_high is not None and math.isfinite(session_high) and session_high>entry else None
 elif sc=="BREAKDOWN" and direction=="SHORT":
  entry=orl*(1-buffer_pct/100.0);stop=orh;target=session_low if session_low is not None and math.isfinite(session_low) and session_low<entry else None
 elif sc in {"CONTINUATION","RETEST"} and direction=="LONG":entry,stop,target=close,sl,sh
 elif sc in {"CONTINUATION","RETEST"} and direction=="SHORT":entry,stop,target=close,sh,sl
 else:return None
 if target is None:return None
 if direction=="LONG" and not stop<entry<target:return None
 if direction=="SHORT" and not target<entry<stop:return None
 rr=abs(target-entry)/abs(entry-stop)
 return (entry,stop,target,rr) if math.isfinite(rr) and rr>0 else None

def scan_blocked(x,p="root"):
 bad=[]
 if isinstance(x,dict):
  for k,v in x.items():
   if str(k).upper() in BLOCKED:bad.append(f"{p}.{k}")
   bad+=scan_blocked(v,f"{p}.{k}")
 elif isinstance(x,list):
  for i,v in enumerate(x):bad+=scan_blocked(v,f"{p}[{i}]")
 return bad

def main():
 ap=argparse.ArgumentParser();ap.add_argument("--contract",required=True,type=Path);ap.add_argument("--universe",required=True,type=Path);ap.add_argument("--stage11",required=True,type=Path);ap.add_argument("--stage16",required=True,type=Path);ap.add_argument("--stage19",required=True,type=Path);ap.add_argument("--memory",type=Path,default=Path("missing-memory.json"));ap.add_argument("--output",required=True,type=Path);a=ap.parse_args();c=load(a.contract)
 if c.get("stage")!=20 or c.get("version")!="1.0" or c.get("status")!="LOCKED":raise ValueError("Stage 20 contract invalid")
 if c.get("signal_policy",{}).get("daily_signal_cap",0) is not None:raise ValueError("daily signal cap must be null")
 if c.get("strategy_authority",{}).get("generic_rr_fallback_forbidden") is not True:raise ValueError("generic RR fallback must be forbidden")
 startup=c.get("stage19_startup_policy",{})
 if startup.get("insufficient_transition_state")!="INSUFFICIENT_TRANSITION_EVIDENCE" or startup.get("transition_evidence_status")!="UNAVAILABLE" or startup.get("independent_setup_may_proceed") is not True or startup.get("fabrication_forbidden") is not True:raise ValueError("Stage 19 startup policy contract invalid")
 syms=universe(a.universe);expected=set(syms);s11=index(a.stage11,expected,"Stage 11");s16=index(a.stage16,expected,"Stage 16");s19=index(a.stage19,expected,"Stage 19");mem=memory(a.memory,expected);now=datetime.now(timezone.utc);stamp=now.replace(microsecond=0).isoformat().replace("+00:00","Z");signals=[];audit=[]
 for rank,s in enumerate(syms,1):
  r11,r16,r19=s11[s],s16[s],s19[s];sc=scenario(r16);state=str(val(r16,"system_state","stage16_state") or "").upper();trans=str(val(r19,"stage19_state","state") or "").upper();evidence=str(val(r19,"transition_evidence_status") or ("UNAVAILABLE" if trans=="INSUFFICIENT_TRANSITION_EVIDENCE" else "INVALID" if trans=="PROVENANCE_FAIL" else "AVAILABLE")).upper();m=mem[s];reason="";decision="NO_SIGNAL";ok11,_,why11=fresh(r11,now);ok16,_,why16=fresh(r16,now);ok19,_,why19=fresh(r19,now);prov11=bool(val(r11,"stage11_provenance","provenance","research_provenance"));prov16=bool(val(r16,"stage16_provenance","provenance"));prov19=bool(val(r19,"stage19_provenance","provenance"))
  if not (ok11 and ok16 and ok19):reason=f"freshness: S11={why11}; S16={why16}; S19={why19}"
  elif not (prov11 and prov16 and prov19):reason="required Stage 11/16/19 provenance missing"
  elif m in {"ACTIVE_SIGNAL","TRADED"}:reason=f"memory={m}"
  elif state not in {"PRIMARY_CANDIDATE","SECONDARY_CANDIDATE"}:reason=f"stage16={state}"
  elif evidence=="INVALID" or trans in {"CHANGE_POINT_UNSTABLE","PROVENANCE_FAIL"}:reason=f"stage19={trans}"
  elif sc not in SCENARIOS:reason=f"scenario={sc or 'NONE'}"
  else:
   d=direction(r11,sc);levels=strategy_levels(r11,d,sc,c) if d else None;conf=num(r16,"stage13_confidence","confidence","scenario_confidence")
   if conf is None or not 0<=conf<=1:reason="scenario confidence missing or outside 0..1"
   elif not d:reason="strategy direction unavailable"
   elif not levels:reason="strategy-owned entry/SL/TP geometry unavailable"
   else:
    entry,stop,target,rr=levels;score=round(conf*100.0,4);seed=f"{s}|{sc}|{entry:.6f}|{stop:.6f}|{target:.6f}|{stamp}";sid="PSY29-"+hashlib.sha256(seed.encode()).hexdigest()[:16].upper();signals.append({"signal_id":sid,"symbol":s,"canonical_rank":rank,"direction":d,"strategy":sc,"entry":entry,"stop_loss":stop,"take_profit":target,"risk_reward":round(rr,4),"signal_score":score,"signal_status":"NEW_SIGNAL","timestamp":stamp,"memory_state":m,"stage16_state":state,"stage19_state":trans,"transition_evidence_status":evidence,"provenance":"PSY29 Stage 20 strategy-owned signal; Stage 11 live levels + Stage 16 candidate + Stage 19 transition evidence"});reason="qualifying new strategy-owned opportunity" if evidence=="AVAILABLE" else "qualifying independent opportunity; Stage 19 transition evidence unavailable";decision="SIGNAL"
  audit.append({"symbol":s,"stage16_state":state,"stage19_state":trans,"transition_evidence_status":evidence,"scenario":sc,"memory_state":m,"decision":decision,"reason":reason})
 payload={"stage":20,"version":"1.0","status":"PASS","generated_at":stamp,"coverage":{"expected":29,"actual":29,"unique":29},"signal_count":len(signals),"signals":signals,"audit":audit,"daily_signal_cap":None,"provenance":"PSY29 Stage 20 Final Trading Signal & Strategy Engine v1.0","stage19_startup_policy":{"insufficient_transition_state":"INSUFFICIENT_TRANSITION_EVIDENCE","transition_evidence_status":"UNAVAILABLE","independent_setup_may_proceed":True,"fabrication_forbidden":True}};bad=scan_blocked(payload)
 if bad:raise ValueError("blocked execution fields: "+str(bad))
 a.output.mkdir(parents=True,exist_ok=True);(a.output/"PSY29_STAGE20_FINAL_SIGNAL_BOARD.json").write_text(json.dumps(payload,indent=2),encoding="utf-8");fields=list(signals[0]) if signals else ["signal_id","symbol","direction","strategy","entry","stop_loss","take_profit","risk_reward","signal_score","signal_status","timestamp","provenance"]
 with (a.output/"PSY29_STAGE20_FINAL_SIGNALS.csv").open("w",encoding="utf-8",newline="") as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(signals)
 (a.output/"PSY29_STAGE20_SIGNAL_MEMORY.json").write_text(json.dumps({"stage":20,"updated_at":stamp,"records":[{"symbol":s,"state":("ACTIVE_SIGNAL" if any(x["symbol"]==s for x in signals) else mem[s])} for s in syms]},indent=2),encoding="utf-8");validation={"stage":20,"version":"1.0","validation_status":"PASS","canonical_29":True,"multiple_signals_allowed":True,"signal_count":len(signals),"daily_cap":None,"strategy_owned_levels":all(all(k in x for k in ("entry","stop_loss","take_profit","strategy")) for x in signals),"no_generic_fallback":True,"freshness_gate":True,"provenance_gate":True,"breakout_target_policy":"STAGE11_SESSION_HIGH_AFTER_CONFIRMED_BREAKOUT","breakdown_target_policy":"STAGE11_SESSION_LOW_AFTER_CONFIRMED_BREAKDOWN","stage19_startup_policy":"INSUFFICIENT_TRANSITION_EVIDENCE_IS_UNAVAILABLE_NOT_INVALID","blocked_execution_fields":[],"fail_closed":True};(a.output/"PSY29_STAGE20_VALIDATION.json").write_text(json.dumps(validation,indent=2),encoding="utf-8");print("PSY29 STAGE 20: PASS");print("Canonical 29/29: PASS");print(f"Signals emitted: {len(signals)}");print("Strategy-owned Entry/SL/TP: PASS");print("Freshness + provenance gates: PASS");print("Stage 19 insufficient-history is non-blocking: PASS");print("Breakout target geometry: PASS");print("Breakdown target geometry: PASS");print("No daily signal cap: PASS")
if __name__=="__main__":
 try:main()
 except Exception as e:print(f"PSY29 STAGE 20 FAIL-CLOSED: {e}",file=sys.stderr);raise
