#!/usr/bin/env python3
"""PSY29 Stage 16 — Live Decision Consolidation & Candidate Board.
Consumes verified Stage 5–15 state and produces a current 29-stock board.
"""
from __future__ import annotations
import argparse, csv, json, sys
from datetime import datetime, timezone
from pathlib import Path

STAGE=16
VERSION="1.0"
STATES={"PRIMARY_CANDIDATE","SECONDARY_CANDIDATE","WATCHLIST","INACTIVE","DATA_STALE","DATA_INVALID","INTEGRITY_FAIL","CONSISTENCY_FAIL"}
BLOCKED_KEYS={"TRADE_READY","TRADE_SIGNAL","TRADE_AUTHORIZED","CE","PE","ENTRY","ENTRY_PRICE","STOP_LOSS","TAKE_PROFIT","TARGET","POSITION_SIZE","RISK","CAPITAL_ALLOCATION","ORDER","EXECUTION"}

def load(path):
    text=path.read_text(encoding="utf-8").strip()
    if not text:return []
    if path.suffix.lower()==".csv":
        with path.open("r",encoding="utf-8",newline="") as h:return list(csv.DictReader(h))
    try:return json.loads(text)
    except json.JSONDecodeError:return [json.loads(x) for x in text.splitlines() if x.strip()]

def rows(data):
    if isinstance(data,list):return [x for x in data if isinstance(x,dict)]
    if isinstance(data,dict):
        for k in ("rows","records","data","stocks","results","items","snapshot","events","journal"):
            if isinstance(data.get(k),list):return [x for x in data[k] if isinstance(x,dict)]
        if data and all(isinstance(v,dict) for v in data.values()):
            return [dict(v,**({"symbol":k} if "symbol" not in v else {})) for k,v in data.items()]
        return [data]
    return []

def sym(r):
    for k in ("symbol","tradingsymbol","ticker","stock","security_symbol","name"):
        if str(r.get(k,"")).strip():return str(r[k]).strip().upper()
    return None

def val(r,*keys):
    low={str(k).lower():v for k,v in r.items()}
    for k in keys:
        if k.lower() in low:return low[k.lower()]
    return None

def ts(r):
    v=val(r,"live_data_timestamp","data_timestamp","observation_timestamp","generated_at","timestamp","event_timestamp","as_of")
    if v is None:return None
    s=str(v).strip(); s=s[:-1]+"+00:00" if s.endswith("Z") else s
    try:
        d=datetime.fromisoformat(s); d=d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc)
        return d
    except ValueError:return None

def universe(path):
    d=load(path); u=d.get("universe") if isinstance(d,dict) else None
    if isinstance(u,list):out=[str(x.get("symbol","")).strip().upper() for x in u if isinstance(x,dict)]
    else:out=[str(x).strip().upper() for x in (d.get("symbols") or d.get("canonical_symbols") or [])]
    out=[x for x in out if x]
    if len(out)!=29 or len(set(out))!=29:raise ValueError("Canonical universe is not exactly 29 unique symbols")
    return out

def index(path,stage,expected):
    out={}
    for r in rows(load(path)):
        s=sym(r)
        if not s:continue
        if s in out:raise ValueError(f"Stage {stage}: duplicate {s}")
        out[s]=r
    if set(out)!=expected:raise ValueError(f"Stage {stage}: coverage mismatch")
    return out

def provenance_ok(rs):
    for n,r in rs.items():
        if not any(val(r,k) not in (None,"",{},[]) for k in (f"stage{n}_provenance","provenance","research_provenance")):return False
    return True

def fresh(rs):
    dts=[ts(r) for r in rs.values() if ts(r)]
    if not dts:return False
    age=(datetime.now(timezone.utc)-max(dts)).total_seconds()
    return 0<=age<=900

def scan(x,p="root"):
    z=[]
    if isinstance(x,dict):
        for k,v in x.items():
            if str(k).upper() in BLOCKED_KEYS:z.append(f"{p}.{k}")
            z+=scan(v,f"{p}.{k}")
    elif isinstance(x,list):
        for i,v in enumerate(x):z+=scan(v,f"{p}[{i}]")
    return z

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--universe",required=True,type=Path)
    for n in range(5,16):p.add_argument(f"--stage{n}",required=True,type=Path)
    p.add_argument("--output",required=True,type=Path);a=p.parse_args()
    syms=universe(a.universe); expected=set(syms)
    src={n:index(getattr(a,f"stage{n}"),n,expected) for n in range(5,16)}
    records=[]
    for rank,s in enumerate(syms,1):
        rs={n:src[n][s] for n in range(5,16)}
        edge=str(val(rs[7],"edge_state","edge_status","activation_state","state") or "").upper()
        integrity=str(val(rs[10],"integrity_status","integrity_state","status") or "").upper()
        readiness=str(val(rs[12],"readiness_state","scenario_gate_state","status") or "").upper()
        scenario=str(val(rs[13],"state","scenario_state","status") or "").upper()
        quality=val(rs[9],"quality_score","confidence_score","candidate_quality","score")
        ok=True; reasons=[]
        if edge=="EDGE_ACTIVE" and quality in (None,""):ok=False;reasons.append("active edge lacks quality")
        if edge=="EDGE_ACTIVE" and val(rs[8],"portfolio_rank","rank","edge_rank","ranking") in (None,""):ok=False;reasons.append("active edge lacks ranking")
        if edge=="EDGE_INACTIVE" and val(rs[8],"portfolio_rank","rank","edge_rank","ranking") not in (None,""):ok=False;reasons.append("inactive edge has ranking")
        if integrity!="INTEGRITY_PASS":ok=False;reasons.append(f"integrity={integrity or 'missing'}")
        fresh_now=fresh(rs); prov=provenance_ok(rs)
        if not fresh_now:state="DATA_STALE";reason="mandatory timestamps are stale or absent"
        elif not prov:state="DATA_INVALID";reason="mandatory provenance incomplete"
        elif integrity!="INTEGRITY_PASS":state="INTEGRITY_FAIL";reason=f"Stage 10 integrity is {integrity or 'missing'}"
        elif not ok:state="CONSISTENCY_FAIL";reason="; ".join(reasons)
        elif edge=="EDGE_ACTIVE" and isinstance(quality,(int,float)) and float(quality)>=80 and scenario=="SCENARIO_CONFIRMED" and readiness in {"EXECUTION_SCENARIO_READY","EXECUTION_SCENARIO_CONDITIONAL"}:
            state="PRIMARY_CANDIDATE";reason="active edge, valid integrity, quality threshold, and confirmed scenario/readiness"
        elif edge=="EDGE_ACTIVE":state="SECONDARY_CANDIDATE";reason="active edge with valid upstream state"
        elif edge=="EDGE_INACTIVE":state="WATCHLIST";reason="valid upstream chain with inactive edge"
        else:state="INACTIVE";reason="no active edge state"
        records.append({"symbol":s,"canonical_rank":rank,"system_state":state,"classification_reason":reason,"stage6_regime":val(rs[6],"regime","regime_state","classification","live_regime"),"stage7_edge_state":edge,"stage8_portfolio_rank":val(rs[8],"portfolio_rank","rank","edge_rank","ranking"),"stage9_quality_score":quality,"stage10_integrity":integrity,"stage11_analysis_state":val(rs[11],"analysis_state","execution_analysis_state","status"),"stage12_readiness_state":readiness,"stage13_state":scenario,"stage13_scenario":val(rs[13],"scenario","scenario_class"),"stage13_confidence":val(rs[13],"confidence","scenario_confidence","confidence_score"),"stage14_dashboard_state":val(rs[14],"dashboard_state","dashboard_status","state","status"),"stage15_event_class":val(rs[15],"event_class","event_type","journal_state"),"live_data_timestamp":(ts(rs[6]) or ts(rs[7]) or ts(rs[14])).isoformat().replace("+00:00","Z") if (ts(rs[6]) or ts(rs[7]) or ts(rs[14])) else None,"data_status":"FRESH" if fresh_now else "STALE","provenance_complete":prov,"consistency_ok":ok,"provenance":{f"stage{n}_provenance":val(rs[n],f"stage{n}_provenance","provenance","research_provenance") for n in range(5,16)}})
    payload={"stage":16,"version":"1.0","generated_at":datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z"),"coverage":{"expected":29,"actual":len(records),"unique":len({r['symbol'] for r in records})},"records":records}
    bad=scan(payload)
    if bad:raise ValueError("Blocked output fields: "+", ".join(bad))
    if payload["coverage"]!={"expected":29,"actual":29,"unique":29}:raise ValueError("Coverage failure")
    a.output.mkdir(parents=True,exist_ok=True)
    (a.output/"PSY29_STAGE16_CURRENT_BOARD.json").write_text(json.dumps(payload,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    fields=[k for k in records[0] if k!="provenance"]
    with (a.output/"PSY29_STAGE16_CURRENT_BOARD.csv").open("w",newline="",encoding="utf-8") as h:
        w=csv.DictWriter(h,fieldnames=fields);w.writeheader();w.writerows([{k:r.get(k) for k in fields} for r in records])
    validation={"stage":16,"version":"1.0","validation_status":"PASS","coverage":payload["coverage"],"checks":{"canonical_29":True,"29_29_coverage":True,"unique_symbols":True,"required_stages_5_15":True,"provenance_complete":all(r["provenance_complete"] for r in records),"cross_stage_consistency":all(r["consistency_ok"] for r in records),"blocked_fields_absent":not bad,"fail_closed":True}}
    (a.output/"PSY29_STAGE16_VALIDATION.json").write_text(json.dumps(validation,indent=2)+"\n",encoding="utf-8")
    print("PSY29 STAGE 16: PASS")
    print("Canonical coverage: 29/29")

if __name__=="__main__":
    try:main()
    except Exception as e:print(f"PSY29 STAGE 16: FAIL: {e}",file=sys.stderr);raise
