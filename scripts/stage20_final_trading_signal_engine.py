#!/usr/bin/env python3
"""PSY29 Stage 20 — Final Trading Signal & Strategy Engine v1.0."""
from __future__ import annotations
import argparse,csv,json,hashlib,sys
from datetime import datetime,timezone
from pathlib import Path
SCENARIOS={"BREAKOUT","BREAKDOWN","CONTINUATION","RETEST"}
BLOCKED={"ORDER","BROKER_ORDER","EXECUTE","EXECUTION","CAPITAL_ALLOCATION","POSITION_SIZE"}
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
    x=val(r,"symbol","ticker","tradingsymbol")
    return str(x).strip().upper() if x not in (None,"") else None
def num(r,*ks):
    x=val(r,*ks)
    try:return float(x)
    except (TypeError,ValueError):return None
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
    d=load(p);u=d.get("universe") if isinstance(d,dict) else None
    s=[str(x.get("symbol","")).strip().upper() for x in u]
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
    if st=="TRENDING_UP":return "LONG"
    if st=="TRENDING_DOWN":return "SHORT"
    return None
def strategy_levels(r11,direction,sc):
    close=num(r11,"close_5m");orh=num(r11,"first15_high");orl=num(r11,"first15_low");sh=num(r11,"swing_high");sl=num(r11,"swing_low")
    if any(x is None for x in (close,orh,orl,sh,sl)):return None
    if sc=="BREAKOUT" and direction=="LONG":entry,stop,target=orh,orl,sh
    elif sc=="BREAKDOWN" and direction=="SHORT":entry,stop,target=orl,orh,sl
    elif sc in {"CONTINUATION","RETEST"} and direction=="LONG":entry,stop,target=close,sl,sh
    elif sc in {"CONTINUATION","RETEST"} and direction=="SHORT":entry,stop,target=close,sh,sl
    else:return None
    if direction=="LONG" and not stop<entry<target:return None
    if direction=="SHORT" and not target<entry<stop:return None
    rr=abs(target-entry)/abs(entry-stop)
    return (entry,stop,target,rr) if rr>0 else None
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
    ap=argparse.ArgumentParser();ap.add_argument("--contract",required=True,type=Path);ap.add_argument("--universe",required=True,type=Path);ap.add_argument("--stage11",required=True,type=Path);ap.add_argument("--stage16",required=True,type=Path);ap.add_argument("--stage19",required=True,type=Path);ap.add_argument("--memory",type=Path,default=Path("missing-memory.json"));ap.add_argument("--output",required=True,type=Path);a=ap.parse_args()
    c=load(a.contract)
    if c.get("stage")!=20 or c.get("version")!="1.0" or c.get("status")!="LOCKED":raise ValueError("Stage 20 contract invalid")
    syms=universe(a.universe);expected=set(syms);s11=index(a.stage11,expected,"Stage 11");s16=index(a.stage16,expected,"Stage 16");s19=index(a.stage19,expected,"Stage 19");mem=memory(a.memory,expected);now=datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z");signals=[];audit=[]
    for rank,s in enumerate(syms,1):
        r11,r16,r19=s11[s],s16[s],s19[s];sc=scenario(r16);state=str(val(r16,"system_state","stage16_state") or "").upper();trans=str(val(r19,"stage19_state","state") or "").upper();m=mem[s];reason="";decision="NO_SIGNAL"
        if m in {"ACTIVE_SIGNAL","TRADED"}:reason=f"memory={m}"
        elif state not in {"PRIMARY_CANDIDATE","SECONDARY_CANDIDATE"}:reason=f"stage16={state}"
        elif trans in {"CHANGE_POINT_UNSTABLE","INSUFFICIENT_TRANSITION_EVIDENCE","PROVENANCE_FAIL"}:reason=f"stage19={trans}"
        elif sc not in SCENARIOS:reason=f"scenario={sc or 'NONE'}"
        else:
            d=direction(r11,sc);levels=strategy_levels(r11,d,sc) if d else None
            if not d:reason="strategy direction unavailable"
            elif not levels:reason="strategy-owned entry/SL/TP geometry unavailable"
            else:
                entry,stop,target,rr=levels;score=num(r16,"stage13_confidence","confidence","scenario_confidence") or 0.0;score=min(99.0,50.0+float(score)*50.0);seed=f"{s}|{sc}|{entry:.6f}|{stop:.6f}|{target:.6f}|{now}";sid="PSY29-"+hashlib.sha256(seed.encode()).hexdigest()[:16].upper()
                signals.append({"signal_id":sid,"symbol":s,"canonical_rank":rank,"direction":d,"strategy":sc,"entry":entry,"stop_loss":stop,"take_profit":target,"risk_reward":round(rr,4),"signal_score":round(score,4),"signal_status":"NEW_SIGNAL","timestamp":now,"memory_state":m,"stage16_state":state,"stage19_state":trans,"provenance":"PSY29 Stage 20 strategy-owned signal; Stage 11 live levels + Stage 16 candidate + Stage 19 transition"});reason="qualifying new strategy-owned opportunity";decision="SIGNAL"
        audit.append({"symbol":s,"stage16_state":state,"stage19_state":trans,"scenario":sc,"memory_state":m,"decision":decision,"reason":reason})
    payload={"stage":20,"version":"1.0","status":"PASS","generated_at":now,"coverage":{"expected":29,"actual":29,"unique":29},"signal_count":len(signals),"signals":signals,"audit":audit,"daily_signal_cap":None,"provenance":"PSY29 Stage 20 Final Trading Signal & Strategy Engine v1.0"}
    bad=scan_blocked(payload)
    if bad:raise ValueError("blocked execution fields: "+str(bad))
    a.output.mkdir(parents=True,exist_ok=True);(a.output/"PSY29_STAGE20_FINAL_SIGNAL_BOARD.json").write_text(json.dumps(payload,indent=2),encoding="utf-8")
    fields=list(signals[0]) if signals else ["signal_id","symbol","direction","strategy","entry","stop_loss","take_profit","risk_reward","signal_score","signal_status","timestamp","provenance"]
    with (a.output/"PSY29_STAGE20_FINAL_SIGNALS.csv").open("w",encoding="utf-8",newline="") as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(signals)
    (a.output/"PSY29_STAGE20_SIGNAL_MEMORY.json").write_text(json.dumps({"stage":20,"updated_at":now,"records":[{"symbol":s,"state":("ACTIVE_SIGNAL" if any(x["symbol"]==s for x in signals) else mem[s])} for s in syms]},indent=2),encoding="utf-8")
    validation={"stage":20,"version":"1.0","validation_status":"PASS","canonical_29":True,"multiple_signals_allowed":True,"signal_count":len(signals),"daily_cap":None,"strategy_owned_levels":all(all(k in x for k in ("entry","stop_loss","take_profit","strategy")) for x in signals),"no_generic_fallback":True,"blocked_execution_fields":[],"fail_closed":True};(a.output/"PSY29_STAGE20_VALIDATION.json").write_text(json.dumps(validation,indent=2),encoding="utf-8")
    print("PSY29 STAGE 20: PASS");print("Canonical 29/29: PASS");print(f"Signals emitted: {len(signals)}");print("Strategy-owned Entry/SL/TP: PASS");print("No daily signal cap: PASS")
if __name__=="__main__":
    try:main()
    except Exception as e:print(f"PSY29 STAGE 20 FAIL-CLOSED: {e}",file=sys.stderr);raise
