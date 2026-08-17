#!/usr/bin/env python3
"""PSY29 production live signal cycle: validated DHAN pipeline -> Stage 6..20."""
from __future__ import annotations
import argparse,csv,json,shutil,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"runtime/live"
U=ROOT/"config/psy29_live_universe_contract.json"
P=ROOT/"config/psy29_edge_profiles_v1.json"
C={n:ROOT/f"config/psy29_stage{n}_{name}.json" for n,name in {
    7:"edge_activation_contract",8:"edge_ranking_contract",9:"candidate_quality_contract",
    10:"integrity_gate_contract",11:"execution_analysis_contract",12:"execution_readiness_contract",
    13:"scenario_adjudication_contract",14:"live_dashboard_contract"}.items()}
C[19]=ROOT/"config/psy29_stage19_forward_state_transition_contract.json"
HISTORY=OUT/"stage17_history"

def run(cmd:list[object],timeout:int=300):
    print("PSY29 SIGNAL:"," ".join(map(str,cmd)),flush=True)
    subprocess.run([sys.executable,*map(str,cmd)],cwd=ROOT,check=True,timeout=timeout)

def csv_rows(p:Path):
    with p.open(encoding="utf-8",newline="") as f:return list(csv.DictReader(f))

def verify29(p:Path,exp:set[str],label:str):
    r=csv_rows(p);syms=[str(x.get("symbol","")).strip().upper() for x in r]
    if len(r)!=29 or len(set(syms))!=29 or set(syms)!=exp:raise RuntimeError(f"{label}: 29/29 coverage failure")

def stamp_provenance(src:Path,stage:int,label:str):
    """Attach explicit machine-readable provenance to the canonical stage artifact.

    The stage engines remain authoritative for their calculations; this adapter only
    records the producing engine at the row boundary so downstream stages and the
    audit terminal can verify the complete evidence chain.
    """
    rows=csv_rows(src)
    if len(rows)!=29:raise RuntimeError(f"Stage {stage} provenance adapter: expected 29 rows")
    fields=list(rows[0]) if rows else ["symbol"]
    if "provenance" not in fields:fields.append("provenance")
    if f"stage{stage}_provenance" not in fields:fields.append(f"stage{stage}_provenance")
    for row in rows:
        row["provenance"]=label
        row[f"stage{stage}_provenance"]=label
    with src.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)

def add_s11_prov(src:Path,dst:Path):
    stamp_provenance(src,11,"PSY29 Stage 11 Live Execution-Analysis Engine v1.0")
    shutil.copy2(src,dst)

def add_s15_prov(src:Path,dst:Path):
    stamp_provenance(src,15,"PSY29 Stage 15 Trade/Event Journal v1.0")
    shutil.copy2(src,dst)

def stage5(out:Path,syms:list[str],stamp:str):
    profiles=json.loads(P.read_text(encoding="utf-8"))["profiles"]
    b={str(x["symbol"]).upper().strip():x for x in profiles}
    if len(profiles)!=29 or set(b)!=set(syms):raise RuntimeError("Stage 5 profile coverage failure")
    rows=[{"symbol":s,"canonical_rank":int(b[s]["rank"]),"timestamp":stamp,
           "provenance":"config/psy29_edge_profiles_v1.json",
           "research_provenance":"config/psy29_edge_profiles_v1.json"} for s in syms]
    with out.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def stage15_universe_view(out:Path,syms:list[str]):
    out.write_text(json.dumps({"symbols":syms},indent=2),encoding="utf-8")

def write_history_snapshot(src:Path,dst:Path,stamp:str):
    rows=csv_rows(src)
    if not rows:raise RuntimeError("Stage 17 history snapshot empty")
    fields=list(rows[0]);
    if "timestamp" not in fields:fields.append("timestamp")
    for row in rows:row["timestamp"]=stamp
    with dst.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)

def purge_invalid_history():
    HISTORY.mkdir(parents=True,exist_ok=True)
    for f in HISTORY.glob("*.csv"):
        try:
            rows=csv_rows(f)
            if not rows or any(not str(r.get("timestamp","")).strip() for r in rows):f.unlink()
        except Exception:f.unlink()

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--output",type=Path,default=OUT);a=ap.parse_args()
    out=a.output;out.mkdir(parents=True,exist_ok=True)
    syms=[str(x["symbol"]).strip().upper() for x in json.loads(U.read_text())["universe"]];exp=set(syms)
    if len(syms)!=29 or len(exp)!=29:raise RuntimeError("canonical universe invalid")
    validation=json.loads((out/"live_pipeline_input_validation.json").read_text(encoding="utf-8"))
    if validation.get("status")!="PASS" or validation.get("mode")!="live" or validation.get("live_data") is not True or validation.get("coverage")!={"expected":29,"actual":29,"unique":29}:
        raise RuntimeError("live pipeline input is not a valid 29/29 DHAN PASS")
    exe=out/"execution_snapshot.csv"
    if not exe.exists():raise RuntimeError("live execution snapshot missing")
    verify29(exe,exp,"Live execution snapshot")
    stamp=datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z")
    work=out/"signal_cycle";shutil.rmtree(work,ignore_errors=True);work.mkdir(parents=True)
    d={n:work/f"stage{n}" for n in range(6,20)}
    for x in d.values():x.mkdir(parents=True,exist_ok=True)
    snap=work/"snapshot.csv";shutil.copy2(exe,snap);raw=csv_rows(exe)
    smap=work/"security_map.json"
    mappings=[{"symbol":s,"security_id":str(next(r for r in raw if str(r["symbol"]).upper().strip()==s).get("security_id","")).strip(),"exchange":"NSE","segment":"E"} for s in syms]
    if any(not x["security_id"] for x in mappings):raise RuntimeError("live security map missing security_id")
    smap.write_text(json.dumps({"status":"PASS","canonical_count":29,"resolved_count":29,"unique_security_id_count":29,"mappings":mappings},indent=2),encoding="utf-8")
    s5=work/"stage5.csv";stage5(s5,syms,stamp);s15u=work/"stage15_universe_view.json";stage15_universe_view(s15u,syms)

    s6=d[6]/"PSY29_STAGE6_LIVE_REGIMES.csv"
    run([ROOT/"scripts/step9_live_regime_v2.py","--universe",U,"--profiles",P,"--security-map",smap,"--snapshot",snap,"--output",d[6]])
    stamp_provenance(s6,6,"PSY29 Stage 6 Live Regime Engine V2")

    s7=d[7]/"PSY29_STAGE7_EDGE_ACTIVATION.csv"
    run([ROOT/"scripts/stage7_edge_activation.py","--universe",U,"--profiles",P,"--contract",C[7],"--regimes",s6,"--output",d[7]])
    stamp_provenance(s7,7,"PSY29 Stage 7 Research-Conditioned Edge Activation")

    s8=d[8]/"PSY29_STAGE8_EDGE_RANKING.csv"
    run([ROOT/"scripts/stage8_edge_ranking.py","--universe",U,"--profiles",P,"--contract",C[8],"--edge-activation",s7,"--regimes",s6,"--output",d[8]])
    stamp_provenance(s8,8,"PSY29 Stage 8 Portfolio Edge Ranking")

    s9=d[9]/"PSY29_STAGE9_CANDIDATE_QUALITY.csv"
    run([ROOT/"scripts/stage9_candidate_quality.py","--universe",U,"--profiles",P,"--contract",C[9],"--stage6",s6,"--stage7",s7,"--stage8",s8,"--output",d[9]])
    stamp_provenance(s9,9,"PSY29 Stage 9 Live Candidate Quality Engine")

    s10=d[10]/"PSY29_STAGE10_INTEGRITY.csv"
    run([ROOT/"scripts/stage10_integrity_gate.py","--universe",U,"--profiles",P,"--contract",C[10],"--stage6",s6,"--stage7",s7,"--stage8",s8,"--stage9",s9,"--output",d[10]])
    stamp_provenance(s10,10,"PSY29 Stage 10 Integrity Gate")

    s11=d[11]/"PSY29_STAGE11_EXECUTION_ANALYSIS.csv"
    run([ROOT/"scripts/stage11_execution_analysis.py","--universe",U,"--profiles",P,"--contract",C[11],"--stage6",s6,"--stage7",s7,"--stage8",s8,"--stage9",s9,"--stage10",s10,"--live-snapshot",exe,"--output",d[11]])
    s11c=work/"stage11_compat.csv";add_s11_prov(s11,s11c)

    s12=d[12]/"PSY29_STAGE12_EXECUTION_READINESS.csv"
    run([ROOT/"scripts/stage12_execution_readiness.py","--universe",U,"--profiles",P,"--stage6",s6,"--stage7",s7,"--stage8",s8,"--stage9",s9,"--stage10",s10,"--stage11",s11c,"--contract",C[12],"--output",d[12]])
    stamp_provenance(s12,12,"PSY29 Stage 12 Execution Readiness")

    s13=d[13]/"PSY29_STAGE13_SCENARIO_ADJUDICATION.csv"
    run([ROOT/"scripts/stage13_scenario_adjudication.py","--universe",U,"--profiles",P,"--stage6",s6,"--stage7",s7,"--stage8",s8,"--stage9",s9,"--stage10",s10,"--stage11",s11c,"--stage12",s12,"--contract",C[13],"--output",d[13]])
    stamp_provenance(s13,13,"PSY29 Stage 13 Scenario Adjudication")

    s14=d[14]/"PSY29_STAGE14_LIVE_DASHBOARD.csv"
    run([ROOT/"scripts/stage14_live_dashboard.py","--universe",U,"--profiles",P,"--stage6",s6,"--stage7",s7,"--stage8",s8,"--stage9",s9,"--stage10",s10,"--stage11",s11c,"--stage12",s12,"--stage13",s13,"--contract",C[14],"--output",d[14]])
    stamp_provenance(s14,14,"PSY29 Stage 14 Live Dashboard")

    s15=d[15]/"PSY29_STAGE15_EVENTS.csv"
    run([ROOT/"scripts/stage15_trade_event_journal.py","--universe",s15u,"--stage5",s5,"--stage6",s6,"--stage7",s7,"--stage8",s8,"--stage9",s9,"--stage10",s10,"--stage11",s11c,"--stage12",s12,"--stage13",s13,"--stage14",s14,"--output",d[15]])
    s15c=work/"stage15_compat.csv";add_s15_prov(s15,s15c)

    s16=d[16]/"PSY29_STAGE16_CURRENT_BOARD.csv"
    run([ROOT/"scripts/stage16_live_decision_consolidation.py","--universe",U,"--stage5",s5,"--stage6",s6,"--stage7",s7,"--stage8",s8,"--stage9",s9,"--stage10",s10,"--stage11",s11c,"--stage12",s12,"--stage13",s13,"--stage14",s14,"--stage15",s15c,"--output",d[16]])
    stamp_provenance(s16,16,"PSY29 Stage 16 Decision Consolidation")
    for n,p in ((6,s6),(7,s7),(8,s8),(9,s9),(10,s10),(11,s11),(12,s12),(13,s13),(14,s14),(15,s15),(16,s16)):verify29(p,exp,f"Stage {n}")

    s17=d[17]/"PSY29_STAGE17_STABILITY_BOARD.csv"
    run([ROOT/"scripts/stage17_live_stability.py","--universe",U,"--stage5",s5,"--stage6",s6,"--stage7",s7,"--stage8",s8,"--stage9",s9,"--stage10",s10,"--stage11",s11c,"--stage12",s12,"--stage13",s13,"--stage14",s14,"--stage15",s15c,"--stage16",s16,"--output",d[17]])
    stamp_provenance(s17,17,"PSY29 Stage 17 Live Decision Stability Engine")
    verify29(s17,exp,"Stage 17")
    HISTORY.mkdir(parents=True,exist_ok=True)
    history_file=HISTORY/f"stage17_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.csv";write_history_snapshot(s17,history_file,stamp)

    s18=d[18]/"PSY29_STAGE18_HISTORICAL_BOARD.csv"
    run([ROOT/"scripts/stage18_historical_continuity.py","--universe",U,"--stage5",s5,"--stage6",s6,"--stage7",s7,"--stage8",s8,"--stage9",s9,"--stage10",s10,"--stage11",s11c,"--stage12",s12,"--stage13",s13,"--stage14",s14,"--stage15",s15c,"--stage16",s16,"--stage17",s17,"--history",HISTORY,"--output",d[18]])
    stamp_provenance(s18,18,"PSY29 Stage 18 Historical Continuity Engine")
    verify29(s18,exp,"Stage 18")

    purge_invalid_history()
    s19=d[19]/"PSY29_STAGE19_TRANSITION_BOARD.csv"
    run([ROOT/"scripts/stage19_forward_transition.py","--contract",C[19],"--universe",U,"--stage17",s17,"--stage18",s18,"--history",HISTORY,"--output",d[19]])
    stamp_provenance(s19,19,"PSY29 Stage 19 Forward State Transition Engine")
    verify29(s19,exp,"Stage 19")

    memory=out/"PSY29_STAGE20_SIGNAL_MEMORY.json";stage20=out/"stage20";shutil.rmtree(stage20,ignore_errors=True);stage20.mkdir(parents=True)
    run([ROOT/"scripts/stage20_final_trading_signal_engine.py","--contract",ROOT/"config/psy29_stage20_final_trading_signal_contract.json","--universe",U,"--stage11",s11,"--stage16",s16,"--stage19",s19,"--memory",memory,"--output",stage20],timeout=900)
    for name in ("PSY29_STAGE20_FINAL_SIGNAL_BOARD.json","PSY29_STAGE20_FINAL_SIGNALS.csv","PSY29_STAGE20_SIGNAL_MEMORY.json","PSY29_STAGE20_VALIDATION.json"):shutil.copy2(stage20/name,out/name)
    board=json.loads((out/"PSY29_STAGE20_FINAL_SIGNAL_BOARD.json").read_text(encoding="utf-8"));board["production_cycle"]={"generated_at":stamp,"live_data":True,"provider":"DHAN","stage6_to_stage20":True,"history_depth":len(list(HISTORY.glob("*.csv")))};(out/"PSY29_STAGE20_FINAL_SIGNAL_BOARD.json").write_text(json.dumps(board,indent=2),encoding="utf-8")
    print(f"PSY29 LIVE SIGNAL CYCLE: PASS | signals={board.get('signal_count',0)} | history_depth={len(list(HISTORY.glob('*.csv')))}",flush=True)

if __name__=="__main__":
    try:main()
    except Exception as exc:print(f"PSY29 LIVE SIGNAL CYCLE FAIL-CLOSED: {exc}",file=sys.stderr);raise
