#!/usr/bin/env python3
"""PSY29 Stage 14 - Live Dashboard.

Read-only aggregation/presentation layer for verified Stages 5-13.
It preserves upstream values and provenance and never creates a trade decision.
"""
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DASHBOARD_STATES={"ACTIVE_SCENARIO","CONDITIONAL_SCENARIO","INACTIVE","STALE","INVALID","UPSTREAM_ERROR"}
STAGE13_STATES={"SCENARIO_CONFIRMED","SCENARIO_CONDITIONAL","SCENARIO_UNCONFIRMED","SCENARIO_CONFLICTED","DATA_STALE","DATA_INVALID","UPSTREAM_INVALID"}
SCENARIOS={"CONTINUATION","BREAKOUT","BREAKDOWN","RETEST","REVERSAL_RISK","RANGE","TRANSITION","UNCLEAR"}
PROVENANCE=["research_provenance","stage6_provenance","stage7_provenance","stage8_provenance","stage9_provenance","stage10_provenance","stage11_provenance","stage12_provenance","stage13_provenance"]
SAFETY={"trade_ready_output":False,"trade_authorized":False,"trade_signal_generated":False,"ce_pe_selection":False,"entry_calculation":False,"stop_loss_calculation":False,"target_calculation":False,"position_size_calculation":False,"risk_calculation":False,"capital_allocation":False,"order_generation":False,"execution":False}

def load_json(path): return json.loads(Path(path).read_text(encoding="utf-8"))
def nonempty(value): return str(value).strip().lower() not in {"","nan","none","null"}
def fresh(timestamp,now,max_age=180):
    dt=datetime.fromisoformat(str(timestamp).replace("Z","+00:00"))
    if dt.tzinfo is None: raise ValueError("live_data_timestamp must be timezone-aware")
    age=(now-dt.astimezone(timezone.utc)).total_seconds()
    if age < -5: raise ValueError("live_data_timestamp is materially in the future")
    return age<=max_age

def read_csv(path):
    with Path(path).open(newline="",encoding="utf-8") as f:return list(csv.DictReader(f))

def index_stage(path,name,expected,required):
    rows=read_csv(path)
    if len(rows)!=29: raise ValueError(f"{name}: expected exactly 29 rows, got {len(rows)}")
    missing=required-set(rows[0])
    if missing: raise ValueError(f"{name}: missing columns {sorted(missing)}")
    result={}
    for row in rows:
        symbol=row.get("symbol","").upper().strip()
        if not symbol or symbol in result: raise ValueError(f"{name}: empty/duplicate symbol {symbol}")
        result[symbol]=row
    if set(result)!=expected: raise ValueError(f"{name}: canonical coverage mismatch")
    return result

def load_universe(path):
    rows=load_json(path).get("universe",[])
    if len(rows)!=29: raise ValueError("Canonical universe must contain exactly 29 rows")
    symbols=[];ranks={}
    for row in rows:
        symbol=str(row.get("symbol","")).upper().strip();rank=int(row.get("rank",0))
        if not symbol or symbol in ranks: raise ValueError("Canonical universe contains empty/duplicate symbol")
        symbols.append(symbol);ranks[symbol]=rank
    if sorted(ranks.values())!=list(range(1,30)): raise ValueError("Canonical ranks must be exactly 1-29")
    return symbols,ranks

def load_profiles(path,expected):
    rows=load_json(path).get("profiles",[])
    symbols=[str(r.get("symbol","")).upper().strip() for r in rows]
    if len(rows)!=29 or len(set(symbols))!=29 or set(symbols)!=expected: raise ValueError("Stage 5 profile coverage mismatch")

def dashboard_state(stage13,integrity,stage12):
    s13=stage13.upper().strip();integ=integrity.upper().strip();s12=stage12.upper().strip()
    if s13=="DATA_STALE":return "STALE"
    if s13=="DATA_INVALID" or integ=="DATA_INVALID":return "INVALID"
    if s13=="UPSTREAM_INVALID" or integ!="INTEGRITY_PASS":return "UPSTREAM_ERROR"
    if s13=="SCENARIO_CONFIRMED":return "ACTIVE_SCENARIO"
    if s13 in {"SCENARIO_CONDITIONAL","SCENARIO_CONFLICTED"}:return "CONDITIONAL_SCENARIO"
    if s13=="SCENARIO_UNCONFIRMED":return "INACTIVE"
    if s12 in {"DATA_STALE","STALE"}:return "STALE"
    return "UPSTREAM_ERROR"

def rank_key(row):
    # Stage 8 intentionally leaves portfolio_rank empty for EDGE_INACTIVE.
    # Preserve that meaning; only active rows participate in rank ordering.
    raw=str(row.get("stage8_portfolio_rank","")).strip()
    if raw.isdigit(): return (0,int(raw))
    return (1,int(row["canonical_rank"]))

def main():
    parser=argparse.ArgumentParser()
    for name in ("universe","profiles","stage6","stage7","stage8","stage9","stage10","stage11","stage12","stage13","contract","output"): parser.add_argument(f"--{name}",required=True)
    args=parser.parse_args();output=Path(args.output);output.mkdir(parents=True,exist_ok=True)
    engine="FAIL";validation="FAIL";rows=[];error=""
    try:
        contract=load_json(args.contract)
        if contract.get("locked") is not True or contract.get("coverage")!=29: raise ValueError("Stage 14 contract is not locked at 29-stock coverage")
        symbols,ranks=load_universe(args.universe);expected=set(symbols);load_profiles(args.profiles,expected)
        s6=index_stage(args.stage6,"Stage 6",expected,{"symbol","regime","data_status"})
        s7=index_stage(args.stage7,"Stage 7",expected,{"symbol","activation","data_status"})
        s8=index_stage(args.stage8,"Stage 8",expected,{"symbol","activation","data_status","portfolio_rank"})
        s9=index_stage(args.stage9,"Stage 9",expected,{"symbol","activation","data_status","candidate_quality_score"})
        s10=index_stage(args.stage10,"Stage 10",expected,{"symbol","integrity_state","data_status","research_provenance","stage6_provenance","stage7_provenance","stage8_provenance"})
        s11=index_stage(args.stage11,"Stage 11",expected,{"symbol","analysis_state","live_data_timestamp","stage10_provenance","stage11_provenance"})
        s12=index_stage(args.stage12,"Stage 12",expected,{"symbol","stage12_state","live_data_timestamp","stage12_provenance"})
        s13=index_stage(args.stage13,"Stage 13",expected,{"symbol","stage13_state","dominant_scenario","scenario_confidence","stage10_integrity","stage11_analysis_state","stage12_readiness_state",*PROVENANCE,"live_data_timestamp",*SAFETY.keys()})
        now=datetime.now(timezone.utc)
        for symbol in symbols:
            r6,r7,r8,r9=s6[symbol],s7[symbol],s8[symbol],s9[symbol];r10,r11,r12,r13=s10[symbol],s11[symbol],s12[symbol],s13[symbol]
            for field in PROVENANCE:
                if not nonempty(r13[field]):raise ValueError(f"{symbol}: missing {field}")
            state="STALE" if not fresh(r13["live_data_timestamp"],now) else dashboard_state(r13["stage13_state"],r13["stage10_integrity"],r13["stage12_readiness_state"])
            scenario=str(r13["dominant_scenario"]).upper().strip()
            if scenario not in SCENARIOS:raise ValueError(f"{symbol}: invalid scenario {scenario}")
            confidence=float(r13["scenario_confidence"])
            if not 0.0<=confidence<=1.0:raise ValueError(f"{symbol}: scenario confidence outside 0..1")
            rows.append({"canonical_rank":ranks[symbol],"symbol":symbol,"dashboard_state":state,"stage13_state":r13["stage13_state"],"dominant_scenario":scenario,"scenario_confidence":confidence,"stage6_regime":r6["regime"],"stage7_edge_state":r7["activation"],"stage8_portfolio_rank":r8["portfolio_rank"],"stage9_quality_score":r9["candidate_quality_score"],"stage10_integrity":r10["integrity_state"],"stage11_analysis_state":r11["analysis_state"],"stage12_readiness_state":r12["stage12_state"],"confirmation_condition":r13.get("confirmation_condition",""),"invalidation_condition":r13.get("invalidation_condition",""),"supporting_evidence":r13.get("supporting_evidence",""),"conflicting_evidence":r13.get("conflicting_evidence",""),"live_data_timestamp":r13["live_data_timestamp"],**{p:r13[p] for p in PROVENANCE},"stage14_provenance":"PSY29 Stage 14 Live Dashboard v1.0",**SAFETY})
        rows.sort(key=rank_key)
        if len(rows)!=29 or len({r["symbol"] for r in rows})!=29 or {r["symbol"] for r in rows}!=expected:raise ValueError("29/29 dashboard coverage failed")
        if any(r["dashboard_state"] not in DASHBOARD_STATES for r in rows):raise ValueError("Invalid dashboard state")
        for row in rows:
            for flag in SAFETY:
                if row[flag] is not False:raise ValueError(f"Safety boundary violation: {row['symbol']} {flag}")
        engine=validation="PASS"
    except Exception as exc:
        error=str(exc);(output/"stage14_error.txt").write_text(error,encoding="utf-8")
    summary={"stage":14,"name":"LIVE DASHBOARD","status":"PASS" if engine=="PASS" and validation=="PASS" else "FAIL","engine_execution_status":engine,"validation_status":validation,"coverage":len(rows),"expected_coverage":29,"dashboard_state_counts":{},"error":error,"provenance_complete":bool(rows) and all(nonempty(r.get("stage14_provenance")) for r in rows),"safety_boundaries_pass":bool(rows) and all(all(r[k] is False for k in SAFETY) for r in rows),"generated_at":datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z")}
    for row in rows:summary["dashboard_state_counts"][row["dashboard_state"]]=summary["dashboard_state_counts"].get(row["dashboard_state"],0)+1
    (output/"PSY29_STAGE14_LIVE_DASHBOARD.json").write_text(json.dumps(rows,indent=2),encoding="utf-8");(output/"PSY29_STAGE14_SUMMARY.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
    if rows:
        with (output/"PSY29_STAGE14_LIVE_DASHBOARD.csv").open("w",newline="",encoding="utf-8") as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    md=["# PSY29 Stage 14 — Live Dashboard","",f"Generated: {summary['generated_at']}","",f"**Status:** {summary['status']}",f"**Coverage:** {summary['coverage']}/29","","| Rank | Symbol | Dashboard | Scenario | Confidence | Stage 8 Rank | Stage 9 Quality | Integrity |","|---:|---|---|---|---:|---:|---:|---|"]
    for r in rows:md.append(f"| {r['canonical_rank']} | {r['symbol']} | {r['dashboard_state']} | {r['dominant_scenario']} | {r['scenario_confidence']:.2f} | {r['stage8_portfolio_rank']} | {r['stage9_quality_score']} | {r['stage10_integrity']} |")
    (output/"PSY29_STAGE14_DASHBOARD.md").write_text("\n".join(md)+"\n",encoding="utf-8")
    return 0 if engine=="PASS" and validation=="PASS" else 1

if __name__=="__main__":raise SystemExit(main())
