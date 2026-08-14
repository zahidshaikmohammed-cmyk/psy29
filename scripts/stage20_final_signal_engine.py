#!/usr/bin/env python3
from __future__ import annotations
import argparse,csv,hashlib,json,sys
from pathlib import Path
from datetime import datetime,timezone

DIRECTIONS={"LONG","SHORT"}
MEMORY={"AVAILABLE","ACTIVE_SIGNAL","TRADED","INVALIDATED","COMPLETED"}
BLOCKED={"ORDER_SUBMISSION","BROKER_ORDER","AUTO_EXECUTE","AUTOMATIC_EXECUTION","CAPITAL_DEPLOYMENT"}

def load(p):
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

def v(r,*keys):
    d={str(k).lower():x for k,x in r.items()}
    for k in keys:
        if k.lower() in d:return d[k.lower()]
    return None

def s(r,*keys):
    x=v(r,*keys);return "" if x is None else str(x).strip()

def n(r,*keys):
    x=v(r,*keys)
    if x in (None,""):return None
    try:return float(x)
    except (TypeError,ValueError):return None

def sym(r):return s(r,"symbol","ticker","tradingsymbol").upper() or None

def prov(r):return v(r,"provenance","research_provenance") not in (None,"",{},[])

def ts(r):
    x=s(r,"timestamp","generated_at","as_of","data_timestamp")
    if not x:return None
    if x.endswith("Z"):x=x[:-1]+"+00:00"
    try:d=datetime.fromisoformat(x)
    except ValueError:return None
    return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc)

def universe(p):
    d=load(p);u=d.get("universe") if isinstance(d,dict) else None
    if not isinstance(u,list):raise ValueError("canonical universe missing")
    a=[str(x.get("symbol") if isinstance(x,dict) else x).strip().upper() for x in u]
    if len(a)!=29 or len(set(a))!=29:raise ValueError("canonical universe must be exactly 29 unique symbols")
    return a

def index(p,expected,label):
    out={}
    for r in rows(load(p)):
        z=sym(r)
        if not z:raise ValueError(f"{label}: missing symbol")
        if z in out:raise ValueError(f"{label}: duplicate {z}")
        out[z]=r
    if set(out)!=expected:raise ValueError(f"{label}: 29/29 coverage failure")
    return out

def mem(path):
    if path is None or not path.exists():return {}
    out={}
    for r in rows(load(path)):
        z=sym(r)
        if not z or z in out:raise ValueError("memory duplicate/missing symbol")
        state=s(r,"memory_state","state").upper() or "AVAILABLE"
        if state not in MEMORY:raise ValueError(f"invalid memory state: {z}")
        out[z]=r
    return out

def scan(x,path="root"):
    hit=[]
    if isinstance(x,dict):
        for k,z in x.items():
            if str(k).upper() in BLOCKED:hit.append(f"{path}.{k}")
            hit+=scan(z,f"{path}.{k}")
    elif isinstance(x,list):
        for i,z in enumerate(x):hit+=scan(z,f"{path}[{i}]")
    return hit

def sid(symbol,direction,entry,stamp):
    return "PSY20-"+hashlib.sha256(f"{symbol}|{direction}|{entry}|{stamp}".encode()).hexdigest()[:16].upper()

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--contract",required=True,type=Path);p.add_argument("--universe",required=True,type=Path)
    p.add_argument("--stage19",required=True,type=Path);p.add_argument("--memory",type=Path);p.add_argument("--output",required=True,type=Path)
    a=p.parse_args();c=load(a.contract)
    if c.get("stage")!=20 or c.get("version")!="1.0" or c.get("status")!="LOCKED":raise ValueError("Stage 20 contract invalid")
    if c.get("signal_policy",{}).get("daily_signal_cap",0) is not None:raise ValueError("daily signal cap must be null")
    syms=universe(a.universe);expected=set(syms);up=index(a.stage19,expected,"Stage 19");memory=mem(a.memory)
    now=datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z");signals=[];suppressed=[]
    for rank,z in enumerate(syms,1):
        r=up[z]
        if not prov(r):raise ValueError(f"provenance failure: {z}")
        t=ts(r)
        if t is None:raise ValueError(f"invalid timestamp: {z}")
        direction=s(r,"direction","signal_direction").upper();score=n(r,"final_score","score","quality_score")
        entry=n(r,"entry","entry_price");stop=n(r,"stop_loss","stop");target=n(r,"target","take_profit");rr=n(r,"risk_reward","rr")
        eligible=s(r,"stage20_eligible","signal_eligible","eligible").upper()
        if eligible in {"FALSE","NO","0"}:continue
        if direction not in DIRECTIONS:continue
        if score is None or entry is None or stop is None or target is None or rr is None:raise ValueError(f"qualifying candidate missing required trade fields: {z}")
        if score<float(c["minimum_score"]):continue
        if min(entry,stop,target,rr)<=0:raise ValueError(f"invalid trade geometry: {z}")
        state=s(memory.get(z,{}),"memory_state","state").upper() if z in memory else "AVAILABLE"
        if state not in MEMORY:raise ValueError(f"invalid memory state: {z}")
        if state in {"ACTIVE_SIGNAL","TRADED"}:
            suppressed.append({"symbol":z,"reason":"DUPLICATE_OR_ALREADY_TRADED","memory_state":state});continue
        signals.append({"symbol":z,"universe_rank":rank,"direction":direction,"entry":entry,"stop_loss":stop,"target":target,"risk_reward":rr,"final_score":score,"confluence_score":n(r,"confluence_score","confluence") or 0,"freshness_score":n(r,"freshness_score","freshness") or 0,"memory_state":state,"provenance_complete":True,"source_timestamp":t.isoformat()})
    signals.sort(key=lambda r:(-r["final_score"],-r["confluence_score"],-r["freshness_score"],r["symbol"]))
    for r in signals:r.update(status="SIGNAL",signal_id=sid(r["symbol"],r["direction"],r["entry"],r["source_timestamp"]),generated_at=now)
    status="SIGNAL" if signals else "NO_TRADE"
    payload={"stage":20,"version":"1.0","status":status,"generated_at":now,"coverage":{"expected":29,"actual":29,"unique":29},"signals":signals,"signal_count":len(signals),"suppressed":suppressed,"policy":{"multiple_signals_allowed":True,"daily_signal_cap":None,"forced_trade":False,"broker_execution":False},"provenance_complete":True}
    hit=scan(payload)
    if hit:raise ValueError("forbidden execution fields detected: "+str(hit))
    a.output.mkdir(parents=True,exist_ok=True)
    (a.output/"PSY29_FINAL_SIGNAL_BOARD.json").write_text(json.dumps(payload,indent=2),encoding="utf-8")
    with (a.output/"PSY29_FINAL_SIGNAL_BOARD.csv").open("w",encoding="utf-8",newline="") as f:
        fields=list(signals[0]) if signals else ["symbol","status"];w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(signals)
    (a.output/"PSY29_STAGE20_VALIDATION.json").write_text(json.dumps({"stage":20,"version":"1.0","validation_status":"PASS","coverage":payload["coverage"],"signal_count":len(signals),"multiple_signals_allowed":True,"daily_signal_cap":None,"duplicate_memory_enforced":True,"provenance_complete":True,"broker_execution":False,"blocked_fields":[]},indent=2),encoding="utf-8")
    print(f"PSY29 STAGE 20: {status}");print("29/29 coverage: PASS");print(f"Signals emitted: {len(signals)}");print("Multiple-signal policy: PASS");print("Trade-memory policy: PASS");print("Provenance: PASS");print("Execution boundary: PASS")

if __name__=="__main__":
    try:main()
    except Exception as e:print(f"PSY29 STAGE 20 FAIL-CLOSED: {e}",file=sys.stderr);raise
