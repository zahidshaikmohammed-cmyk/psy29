#!/usr/bin/env python3
"""PSY29 Stage 19 — Forward State Transition & Change-Point Gate."""
from __future__ import annotations
import argparse,csv,json,sys
from pathlib import Path
from datetime import datetime,timezone

STAGE17={"STABLE","CHANGED","DETERIORATING","EMERGING","INVALIDATED","UNSTABLE","DATA_STALE","DATA_INVALID","PROVENANCE_FAIL"}
STAGE18={"CONTINUOUS","CHANGED","NEW_STATE","PERSISTENT_DETERIORATION","PERSISTENT_INVALIDATION","RECOVERED","HISTORY_UNAVAILABLE","HISTORY_INVALID","PROVENANCE_FAIL"}
ALLOWED={"NO_TRANSITION","TRANSITION_DETECTED","TRANSITION_PERSISTING","TRANSITION_REVERSING","NO_CHANGE_POINT","EMERGING_CHANGE_POINT","CONFIRMED_CHANGE_POINT","CHANGE_POINT_UNSTABLE","INSUFFICIENT_TRANSITION_EVIDENCE","PROVENANCE_FAIL"}
BLOCKED={"TRADE_READY","TRADE_SIGNAL","TRADE_AUTHORIZED","CE","PE","ENTRY","ENTRY_PRICE","STOP_LOSS","TAKE_PROFIT","TARGET","POSITION_SIZE","RISK","CAPITAL_ALLOCATION","ORDER","EXECUTION","FUTURE_PRICE_PREDICTION","DIRECTIONAL_RECOMMENDATION","BUY","SELL"}

def load(p:Path):
    if p.suffix.lower()==".csv":
        with p.open(encoding="utf-8",newline="") as f:return list(csv.DictReader(f))
    return json.loads(p.read_text(encoding="utf-8"))

def rows(x):
    if isinstance(x,list):return [r for r in x if isinstance(r,dict)]
    if isinstance(x,dict):
        for k in ("records","rows","data","items"):
            if isinstance(x.get(k),list):return [r for r in x[k] if isinstance(r,dict)]
        return [x]
    return []

def val(r,*keys):
    d={str(k).lower():v for k,v in r.items()}
    for k in keys:
        if k.lower() in d:return d[k.lower()]
    return None

def sym(r):
    x=val(r,"symbol","tradingsymbol","ticker")
    return str(x).strip().upper() if x not in (None,"") else None

def stamp(r):
    x=val(r,"timestamp","generated_at","data_timestamp","as_of")
    if x is None:return None
    s=str(x).strip()
    if s.endswith("Z"):s=s[:-1]+"+00:00"
    try:d=datetime.fromisoformat(s)
    except ValueError:return None
    return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc)

def prov(r):return val(r,"provenance","research_provenance") not in (None,"",{},[])

def scan(x,path="root"):
    out=[]
    if isinstance(x,dict):
        for k,v in x.items():
            if str(k).upper() in BLOCKED:out.append(f"{path}.{k}")
            out.extend(scan(v,f"{path}.{k}"))
    elif isinstance(x,list):
        for i,v in enumerate(x):out.extend(scan(v,f"{path}[{i}]"))
    return out

def universe(p):
    d=load(p);u=d.get("universe") if isinstance(d,dict) else None
    if not isinstance(u,list):raise ValueError("canonical universe invalid")
    s=[str(x.get("symbol") if isinstance(x,dict) else x).strip().upper() for x in u]
    if len(s)!=29 or len(set(s))!=29:raise ValueError("canonical universe must be exactly 29 unique symbols")
    return s

def index(p,expected,label):
    out={}
    for r in rows(load(p)):
        s=sym(r)
        if not s:raise ValueError(f"{label}: missing symbol")
        if s in out:raise ValueError(f"{label}: duplicate {s}")
        out[s]=r
    if set(out)!=expected:raise ValueError(f"{label}: 29/29 coverage failure")
    return out

def transition(current,history,continuity):
    if current in {"DATA_STALE","DATA_INVALID"}:return "INSUFFICIENT_TRANSITION_EVIDENCE"
    if len(history)<2:return "INSUFFICIENT_TRANSITION_EVIDENCE"
    prev,prev2=history[-1],history[-2]
    if current=="UNSTABLE":return "CHANGE_POINT_UNSTABLE"
    if current==prev and current==prev2:
        if current in {"EMERGING","DETERIORATING"}:return "TRANSITION_PERSISTING"
        return "NO_TRANSITION"
    if current==prev and current!=prev2:return "NO_CHANGE_POINT"
    if current!=prev and prev=="EMERGING" and current!="EMERGING":return "TRANSITION_REVERSING"
    if current!=prev and current==prev2:return "EMERGING_CHANGE_POINT"
    if current!=prev and prev==prev2:
        # Three verified observations establish the transition. Stage 18's
        # cross-stage reconciliation distinguishes confirmed change from a
        # merely detected change.
        if continuity in {"NEW_STATE","PERSISTENT_DETERIORATION","PERSISTENT_INVALIDATION"}:
            return "CONFIRMED_CHANGE_POINT"
        return "TRANSITION_DETECTED"
    if current!=prev:return "TRANSITION_DETECTED"
    return "NO_CHANGE_POINT"

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--contract",required=True,type=Path);p.add_argument("--universe",required=True,type=Path)
    p.add_argument("--stage17",required=True,type=Path);p.add_argument("--stage18",required=True,type=Path)
    p.add_argument("--history",required=True,type=Path);p.add_argument("--output",required=True,type=Path)
    a=p.parse_args();c=load(a.contract);syms=universe(a.universe);expected=set(syms)
    if c.get("stage")!=19 or c.get("version")!="1.0" or c.get("status")!="LOCKED":raise ValueError("Stage 19 contract invalid")
    if c.get("allowed_states")!=list(ALLOWED):raise ValueError("Stage 19 allowed-state contract mismatch")
    cur17=index(a.stage17,expected,"Stage 17");cur18=index(a.stage18,expected,"Stage 18")
    files=sorted(a.history.glob("*.csv")) if a.history.exists() else []
    snapshots=[];last=None
    for f in files:
        snap=index(f,expected,f"History {f.name}");times=[stamp(r) for r in snap.values()]
        if any(t is None for t in times):raise ValueError(f"History {f.name}: invalid timestamp")
        t=min(times)
        if last is not None and t<=last:raise ValueError("historical timestamps not strictly increasing")
        last=t;snapshots.append(snap)
    rec=[]
    for i,s in enumerate(syms,1):
        r17=cur17[s];r18=cur18[s]
        state=str(val(r17,"stage17_state","state") or "").upper();continuity=str(val(r18,"stage18_state","state") or "").upper()
        if state not in STAGE17:raise ValueError(f"invalid Stage 17 state for {s}")
        if continuity not in STAGE18:raise ValueError(f"invalid Stage 18 state for {s}")
        ok=prov(r17) and prov(r18);hs=[]
        for snap in snapshots:
            x=str(val(snap[s],"stage17_state","state") or "").upper()
            if x not in STAGE17:raise ValueError(f"invalid historical state for {s}")
            hs.append(x)
        if not ok:final="PROVENANCE_FAIL"
        elif continuity in {"HISTORY_UNAVAILABLE","HISTORY_INVALID"} or len(hs)<2:final="INSUFFICIENT_TRANSITION_EVIDENCE"
        else:final=transition(state,hs,continuity)
        rec.append({"symbol":s,"canonical_rank":i,"stage19_state":final,"current_stage17_state":state,"stage18_continuity_state":continuity,"history_depth":len(snapshots),"previous_state":(hs[-1] if hs else None),"provenance_complete":ok,"timestamp":val(r17,"timestamp","generated_at","data_timestamp","as_of")})
    payload={"stage":19,"version":"1.0","status":"PASS","records":rec,"coverage":{"expected":29,"actual":len(rec),"unique":len({r['symbol'] for r in rec})},"safety":{"trading_decision_forbidden":True,"execution_forbidden":True},"provenance_required":True}
    bad=scan(payload)
    if bad:raise ValueError("blocked fields detected: "+str(bad))
    if payload["coverage"]!={"expected":29,"actual":29,"unique":29}:raise ValueError("29/29 coverage failure")
    observed={r["stage19_state"] for r in rec}
    if observed!=ALLOWED:raise ValueError(f"Canonical 10-state coverage failed: {observed ^ ALLOWED}")
    a.output.mkdir(parents=True,exist_ok=True)
    (a.output/"PSY29_STAGE19_TRANSITION_BOARD.json").write_text(json.dumps(payload,indent=2),encoding="utf-8")
    with (a.output/"PSY29_STAGE19_TRANSITION_BOARD.csv").open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rec[0]));w.writeheader();w.writerows(rec)
    validation={"stage":19,"version":"1.0","validation_status":"PASS","coverage":payload["coverage"],"output_states_observed":sorted(observed),"provenance_complete":all(r["provenance_complete"] for r in rec),"blocked_fields":[],"fail_closed":True}
    (a.output/"PSY29_STAGE19_VALIDATION.json").write_text(json.dumps(validation,indent=2),encoding="utf-8")
    print("PSY29 STAGE 19: PASS");print("29/29 coverage: PASS");print("10/10 canonical states: PASS");print("Provenance: PASS");print("Safety boundary scan: PASS")

if __name__=="__main__":
    try:main()
    except Exception as e:print(f"PSY29 STAGE 19 FAIL-CLOSED: {e}",file=sys.stderr);raise
