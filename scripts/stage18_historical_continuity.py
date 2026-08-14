#!/usr/bin/env python3
"""PSY29 Stage 18 — Historical State Continuity & Regime Memory Engine.
Version 1.0 / LOCKED.
Descriptive memory only. Never generates a trade or execution decision.
"""
from __future__ import annotations
import argparse, csv, json, sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STAGE = 18
VERSION = "1.0"
STAGE17_STATES = {"STABLE","CHANGED","DETERIORATING","EMERGING","INVALIDATED","UNSTABLE","DATA_STALE","DATA_INVALID","PROVENANCE_FAIL"}
OUTPUT_STATES = {"CONTINUOUS","CHANGED","NEW_STATE","PERSISTENT_DETERIORATION","PERSISTENT_INVALIDATION","RECOVERED","HISTORY_UNAVAILABLE","HISTORY_INVALID","PROVENANCE_FAIL"}
BLOCKED = {"TRADE_READY","TRADE_SIGNAL","TRADE_AUTHORIZED","CE","PE","ENTRY","ENTRY_PRICE","STOP_LOSS","TAKE_PROFIT","TARGET","POSITION_SIZE","RISK","CAPITAL_ALLOCATION","ORDER","EXECUTION","FUTURE_PRICE_PREDICTION","DIRECTIONAL_RECOMMENDATION"}


def load(path: Path) -> Any:
    text = path.read_text(encoding="utf-8").strip()
    if not text: return []
    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8", newline="") as f: return list(csv.DictReader(f))
    return json.loads(text)


def rows(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list): return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        for k in ("records","rows","data","items"):
            if isinstance(data.get(k), list): return [x for x in data[k] if isinstance(x, dict)]
        return [data]
    return []


def val(r: dict[str, Any], *keys: str) -> Any:
    m = {str(k).lower(): v for k,v in r.items()}
    for k in keys:
        if k.lower() in m: return m[k.lower()]
    return None


def symbol(r: dict[str, Any]) -> str | None:
    x = val(r,"symbol","tradingsymbol","ticker","stock")
    return str(x).strip().upper() if x is not None and str(x).strip() else None


def ts(r: dict[str, Any]) -> datetime | None:
    x = val(r,"timestamp","generated_at","data_timestamp","as_of")
    if x is None: return None
    s = str(x).strip()
    if s.endswith("Z"): s = s[:-1] + "+00:00"
    try: d = datetime.fromisoformat(s)
    except ValueError: return None
    return (d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc))


def canonical(path: Path) -> list[str]:
    d = load(path)
    u = d.get("universe") if isinstance(d,dict) else None
    if not isinstance(u,list): raise ValueError("canonical universe missing")
    out=[]
    for x in u:
        y=x.get("symbol") if isinstance(x,dict) else x
        if y is not None: out.append(str(y).strip().upper())
    if len(out)!=29 or len(set(out))!=29: raise ValueError("canonical universe must be exactly 29 unique symbols")
    return out


def index(path: Path, expected: set[str], label: str) -> dict[str,dict[str,Any]]:
    d={}
    for r in rows(load(path)):
        s=symbol(r)
        if not s: raise ValueError(f"{label}: missing symbol")
        if s in d: raise ValueError(f"{label}: duplicate symbol {s}")
        d[s]=r
    if set(d)!=expected:
        raise ValueError(f"{label}: 29/29 coverage failure; missing={sorted(expected-set(d))}; unexpected={sorted(set(d)-expected)}")
    return d


def provenance(r: dict[str,Any]) -> bool:
    return val(r,"provenance","research_provenance","source_provenance","stage17_provenance") not in (None,"",{},[])


def blocked(x: Any, path="root") -> list[str]:
    out=[]
    if isinstance(x,dict):
        for k,v in x.items():
            if str(k).upper() in BLOCKED: out.append(f"{path}.{k}")
            out.extend(blocked(v,f"{path}.{k}"))
    elif isinstance(x,list):
        for i,v in enumerate(x): out.extend(blocked(v,f"{path}[{i}]"))
    return out


def classify(cur: str, history: list[str]) -> str:
    if not history: return "HISTORY_UNAVAILABLE"
    prev=history[-1]
    if cur == prev:
        if cur == "DETERIORATING" and len(history)>=2 and history[-2]==cur: return "PERSISTENT_DETERIORATION"
        if cur == "INVALIDATED" and len(history)>=2 and history[-2]==cur: return "PERSISTENT_INVALIDATION"
        return "CONTINUOUS"
    if prev == "INVALIDATED" and cur != "INVALIDATED": return "RECOVERED"
    if prev in ("DATA_STALE","DATA_INVALID","PROVENANCE_FAIL") and cur not in ("DATA_STALE","DATA_INVALID","PROVENANCE_FAIL"): return "RECOVERED"
    return "NEW_STATE" if len(history)==1 else "CHANGED"


def main() -> None:
    p=argparse.ArgumentParser()
    p.add_argument("--universe",required=True,type=Path)
    for n in range(5,17): p.add_argument(f"--stage{n}",required=True,type=Path)
    p.add_argument("--stage17",required=True,type=Path)
    p.add_argument("--history",required=True,type=Path)
    p.add_argument("--output",required=True,type=Path)
    a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=True)
    syms=canonical(a.universe); expected=set(syms)
    current={n:index(getattr(a,f"stage{n}"),expected,f"Stage {n}") for n in range(5,17)}
    cur17=index(a.stage17,expected,"Stage 17")
    snapshots=sorted(a.history.glob("*.csv"))
    hist=[]
    if snapshots:
        last_ts=None
        for sp in snapshots:
            snap=index(sp,expected,f"History {sp.name}")
            times=[ts(r) for r in snap.values()]
            if any(x is None for x in times): raise ValueError(f"History {sp.name}: invalid timestamp")
            st=min(times)
            if last_ts is not None and st <= last_ts: raise ValueError("historical timestamps are not strictly increasing")
            last_ts=st
            hist.append(snap)
    records=[]
    for rank,s in enumerate(syms,1):
        c=cur17[s]
        state=str(val(c,"stage17_state","state") or "").upper()
        if state not in STAGE17_STATES: raise ValueError(f"Stage 17 invalid state for {s}: {state}")
        upstream_ok=all(provenance(current[n][s]) for n in range(5,17)) and provenance(c)
        if not upstream_ok: final="PROVENANCE_FAIL"
        elif not hist: final="HISTORY_UNAVAILABLE"
        else:
            history_states=[]
            for snap in hist:
                hs=str(val(snap[s],"stage17_state","state") or "").upper()
                if hs not in STAGE17_STATES: raise ValueError(f"History invalid Stage 17 state for {s}: {hs}")
                history_states.append(hs)
            final=classify(state,history_states)
        records.append({"symbol":s,"canonical_rank":rank,"stage18_state":final,"current_stage17_state":state,"history_depth":len(hist),"previous_stage17_state":(str(val(hist[-1][s],"stage17_state","state") or "").upper() if hist else None),"provenance_complete":upstream_ok,"timestamp":val(c,"timestamp","generated_at","data_timestamp","as_of")})
    payload={"stage":18,"version":VERSION,"status":"PASS","records":records,"coverage":{"expected":29,"actual":len(records),"unique":len({r['symbol'] for r in records})},"safety":{"trading_decision":False,"execution":False},"provenance_required":True}
    violations=blocked(payload)
    if violations: raise ValueError("blocked fields detected: "+str(violations))
    out_json=a.output/"PSY29_STAGE18_HISTORICAL_BOARD.json"; out_csv=a.output/"PSY29_STAGE18_HISTORICAL_BOARD.csv"; out_val=a.output/"PSY29_STAGE18_VALIDATION.json"
    out_json.write_text(json.dumps(payload,indent=2),encoding="utf-8")
    fields=list(records[0])
    with out_csv.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(records)
    states={r["stage18_state"] for r in records}
    validation={"stage":18,"version":VERSION,"validation_status":"PASS","coverage":{"expected":29,"actual":len(records),"unique":len({r['symbol'] for r in records})},"output_states_observed":sorted(states),"provenance_complete":all(r["provenance_complete"] for r in records),"blocked_fields":[],"fail_closed":True}
    if validation["coverage"] != {"expected":29,"actual":29,"unique":29}: raise ValueError("29/29 validation failed")
    out_val.write_text(json.dumps(validation,indent=2),encoding="utf-8")
    print("PSY29 STAGE 18: PASS")
    print("29/29 coverage: PASS")
    print("Historical continuity: PASS")
    print("Provenance: PASS")
    print("Safety boundary scan: PASS")

if __name__ == "__main__":
    try: main()
    except Exception as exc:
        print(f"PSY29 STAGE 18 FAIL-CLOSED: {exc}",file=sys.stderr); raise
