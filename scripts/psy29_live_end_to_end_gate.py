#!/usr/bin/env python3
"""PSY29 live end-to-end verification gate."""
from __future__ import annotations
import argparse,csv,json,subprocess,sys,tempfile
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];U=ROOT/"config/psy29_live_universe_contract.json";P=ROOT/"config/psy29_edge_profiles_v1.json"
C={n:ROOT/f"config/psy29_stage{n}_{name}.json" for n,name in {7:"edge_activation_contract",8:"edge_ranking_contract",9:"candidate_quality_contract",10:"integrity_gate_contract",11:"execution_analysis_contract",12:"execution_readiness_contract",13:"scenario_adjudication_contract",14:"live_dashboard_contract"}.items()};C[19]=ROOT/"config/psy29_stage19_forward_state_transition_contract.json"
def run(cmd): print("PSY29 E2E:"," ".join(map(str,cmd)),flush=True);subprocess.run([sys.executable,*map(str,cmd)],cwd=ROOT,check=True)
def symbols():
 r=json.loads(U.read_text(encoding="utf-8"))["universe"];s=[str(x["symbol"]).strip().upper() for x in r]
 if len(r)!=29 or len(set(s))!=29 or [int(x["rank"]) for x in r]!=list(range(1,30)):raise RuntimeError("canonical universe must be exactly 29 unique ranked symbols")
 return s
def csv_rows(p):
 with Path(p).open(encoding="utf-8",newline="") as f:return list(csv.DictReader(f))
def verify29(p,exp,label):
 r=csv_rows(p);g=[str(x.get("symbol","")).strip().upper() for x in r]
 if len(g)!=29 or len(set(g))!=29 or set(g)!=set(exp):raise RuntimeError(f"{label}: 29/29 coverage failure")
 for x in r:
  for k in ("trade_authorized","trade_signal_generated","trade_ready_output"):
   if str(x.get(k,"false")).lower() in {"true","1","yes"}:raise RuntimeError(f"{label}: safety flag {k}=true")
def refresh(src,dst,stamp):
 r=csv_rows(src)
 if not r or "timestamp" not in r[0]:raise RuntimeError(f"fixture snapshot missing timestamp: {src}")
 for x in r:x["timestamp"]=stamp
 with Path(dst).open("w",encoding="utf-8",newline="") as f:w=csv.DictWriter(f,fieldnames=list(r[0]));w.writeheader();w.writerows(r)
def security_map(exe,out,exp):
 r=csv_rows(exe);b={x["symbol"].upper().strip():x for x in r}
 if set(b)!=set(exp) or len(b)!=29:raise RuntimeError("fixture security map coverage failure")
 m=[{"symbol":s,"security_id":str(b[s].get("security_id","")).strip(),"exchange":"NSE","segment":"E"} for s in exp]
 if any(not x["security_id"] for x in m):raise RuntimeError("fixture security map missing security_id")
 Path(out).write_text(json.dumps({"status":"PASS","canonical_count":29,"resolved_count":29,"unique_security_id_count":29,"mappings":m},indent=2),encoding="utf-8")
def stage5(out,exp,stamp):
 r=json.loads(P.read_text(encoding="utf-8"))["profiles"];b={str(x["symbol"]).upper().strip():x for x in r}
 if len(r)!=29 or set(b)!=set(exp):raise RuntimeError("Stage 5 profile coverage failure")
 d=[{"symbol":s,"canonical_rank":int(b[s]["rank"]),"timestamp":stamp,"provenance":"config/psy29_edge_profiles_v1.json","research_provenance":"config/psy29_edge_profiles_v1.json"} for s in exp]
 with Path(out).open("w",encoding="utf-8",newline="") as f:w=csv.DictWriter(f,fieldnames=list(d[0]));w.writeheader();w.writerows(d)
def stage15_universe_view(out,exp):Path(out).write_text(json.dumps({"symbols":exp},indent=2),encoding="utf-8")
def add_s11_prov(src,dst):
 r=csv_rows(src)
 if not r:raise RuntimeError("Stage 11 output empty")
 for x in r:x["stage11_provenance"]="PSY29 Stage 11 Live Execution-Analysis Engine v1.0"
 with Path(dst).open("w",encoding="utf-8",newline="") as f:w=csv.DictWriter(f,fieldnames=list(r[0]));w.writeheader();w.writerows(r)
def main():
 ap=argparse.ArgumentParser();ap.add_argument("--mode",choices=("fixture","live"),required=True);ap.add_argument("--output",type=Path);a=ap.parse_args();exp=symbols();out=a.output or Path(tempfile.mkdtemp(prefix="psy29-live-e2e-"));out.mkdir(parents=True,exist_ok=True);stamp=datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z")
 run([ROOT/"scripts/psy29_live_pipeline_service_cycle.py","--mode",a.mode]);live=ROOT/"runtime/live";v=json.loads((live/"live_pipeline_input_validation.json").read_text(encoding="utf-8"))
 if v.get("status")!="PASS" or v.get("contract")!="PSY29_LIVE_PIPELINE_INPUT" or v.get("mode")!=a.mode or v.get("coverage")!={"expected":29,"actual":29,"unique":29}:raise RuntimeError("PSY29_LIVE_PIPELINE_INPUT gate failed")
 if v.get("signal_generation") is not False or v.get("order_execution") is not False or v.get("live_data") is not (a.mode=="live"):raise RuntimeError("live pipeline safety/provenance boundary failed")
 snap=out/"snapshot.csv";exe=out/"execution_snapshot.csv";refresh(live/"live_snapshot.csv",snap,stamp);refresh(live/"execution_snapshot.csv",exe,stamp);smap=out/"security_map.json";security_map(exe,smap,exp);s5=out/"stage5.csv";stage5(s5,exp,stamp);s15u=out/"stage15_universe_view.json";stage15_universe_view(s15u,exp);d={n:out/f"stage{n}" for n in range(6,20)}
 for x in d.values():x.mkdir(parents=True,exist_ok=True)
 s6=d[6]/"PSY29_STAGE6_LIVE_REGIMES.csv";run([ROOT/"scripts/step9_live_regime_v2.py","--universe",U,"--profiles",P,"--security-map",smap,"--snapshot",snap,"--output",d[6]])
 s7=d[7]/"PSY29_STAGE7_EDGE_ACTIVATION.csv";run([ROOT/"scripts/stage7_edge_activation.py","--universe",U,"--profiles",P,"--contract",C[7],"--regimes",s6,"--output",d[7]])
 s8=d[8]/"PSY29_STAGE8_EDGE_RANKING.csv";run([ROOT/"scripts/stage8_edge_ranking.py","--universe",U,"--profiles",P,"--contract",C[8],"--edge-activation",s7,"--regimes",s6,"--output",d[8]])
 s9=d[9]/"PSY29_STAGE9_CANDIDATE_QUALITY.csv";run([ROOT/"scripts/stage9_candidate_quality.py","--universe",U,"--profiles",P,"--contract",C[9],"--stage6",s6,"--stage7",s7,"--stage8",s8,"--output",d[9]])
 s10=d[10]/"PSY29_STAGE10_INTEGRITY.csv";run([ROOT/"scripts/stage10_integrity_gate.py","--universe",U,"--profiles",P,"--contract",C[10],"--stage6",s6,"--stage7",s7,"--stage8",s8,"--stage9",s9,"--output",d[10]])
 s11=d[11]/"PSY29_STAGE11_EXECUTION_ANALYSIS.csv";run([ROOT/"scripts/stage11_execution_analysis.py","--universe",U,"--profiles",P,"--contract",C[11],"--stage6",s6,"--stage7",s7,"--stage8",s8,"--stage9",s9,"--stage10",s10,"--live-snapshot",exe,"--output",d[11]]);s11c=out/"stage11_compat.csv";add_s11_prov(s11,s11c)
 s12=d[12]/"PSY29_STAGE12_EXECUTION_READINESS.csv";run([ROOT/"scripts/stage12_execution_readiness.py","--universe",U,"--profiles",P,"--stage6",s6,"--stage7",s7,"--stage8",s8,"--stage9",s9,"--stage10",s10,"--stage11",s11c,"--contract",C[12],"--output",d[12]])
 s13=d[13]/"PSY29_STAGE13_SCENARIO_ADJUDICATION.csv";run([ROOT/"scripts/stage13_scenario_adjudication.py","--universe",U,"--profiles",P,"--stage6",s6,"--stage7",s7,"--stage8",s8,"--stage9",s9,"--stage10",s10,"--stage11",s11c,"--stage12",s12,"--contract",C[13],"--output",d[13]])
 s14=d[14]/"PSY29_STAGE14_LIVE_DASHBOARD.csv";run([ROOT/"scripts/stage14_live_dashboard.py","--universe",U,"--profiles",P,"--stage6",s6,"--stage7",s7,"--stage8",s8,"--stage9",s9,"--stage10",s10,"--stage11",s11c,"--stage12",s12,"--stage13",s13,"--contract",C[14],"--output",d[14]])
 s15=d[15]/"PSY29_STAGE15_EVENTS.csv";run([ROOT/"scripts/stage15_trade_event_journal.py","--universe",s15u,"--stage5",s5,"--stage6",s6,"--stage7",s7,"--stage8",s8,"--stage9",s9,"--stage10",s10,"--stage11",s11c,"--stage12",s12,"--stage13",s13,"--stage14",s14,"--output",d[15]])
 s16=d[16]/"PSY29_STAGE16_CURRENT_BOARD.csv";run([ROOT/"scripts/stage16_live_decision_consolidation.py","--universe",U,"--stage5",s5,"--stage6",s6,"--stage7",s7,"--stage8",s8,"--stage9",s9,"--stage10",s10,"--stage11",s11c,"--stage12",s12,"--stage13",s13,"--stage14",s14,"--stage15",s15,"--output",d[16]])
 for n,p in ((6,s6),(7,s7),(8,s8),(9,s9),(10,s10),(11,s11),(12,s12),(13,s13),(14,s14),(15,s15),(16,s16)):verify29(p,exp,f"Stage {n}")
 verify29(s11c,exp,"Stage 11 compatibility")
 s17=d[17]/"PSY29_STAGE17_STABILITY_BOARD.csv";run([ROOT/"scripts/stage17_live_stability.py","--universe",U,"--stage5",s5,"--stage6",s6,"--stage7",s7,"--stage8",s8,"--stage9",s9,"--stage10",s10,"--stage11",s11c,"--stage12",s12,"--stage13",s13,"--stage14",s14,"--stage15",s15,"--stage16",s16,"--output",d[17]]);verify29(s17,exp,"Stage 17")
 fixture=out/"stage19_fixture";run([ROOT/"scripts/stage19_test_fixture.py","--universe",U,"--output",fixture]);run([ROOT/"scripts/stage18_historical_continuity.py","--universe",U,"--stage5",s5,"--stage6",s6,"--stage7",s7,"--stage8",s8,"--stage9",s9,"--stage10",s10,"--stage11",s11c,"--stage12",s12,"--stage13",s13,"--stage14",s14,"--stage15",s15,"--stage16",s16,"--stage17",s17,"--history",fixture/"history","--output",d[18]]);s18=d[18]/"PSY29_STAGE18_HISTORICAL_BOARD.csv";verify29(s18,exp,"Stage 18")
 s19=d[19]/"PSY29_STAGE19_TRANSITION_BOARD.csv";run([ROOT/"scripts/stage19_forward_transition.py","--contract",C[19],"--universe",U,"--stage17",fixture/"stage17.csv","--stage18",fixture/"stage18.csv","--history",fixture/"history","--output",d[19]]);verify29(s19,exp,"Stage 19 deterministic contract")
 r11=csv_rows(s11c)[0];r16=csv_rows(s16)[0];r19=csv_rows(s19)[0]
 if not {"symbol","analysis_state","structure_state","close_5m","first15_high","first15_low","swing_high","swing_low"}.issubset(r11):raise RuntimeError("Stage 20 Stage 11 interface failed")
 if not {"symbol","system_state","stage13_scenario"}.issubset(r16):raise RuntimeError("Stage 20 Stage 16 interface failed")
 if "stage19_state" not in r19:raise RuntimeError("Stage 20 Stage 19 interface failed")
 m={"gate":"PSY29_LIVE_END_TO_END_SIGNAL_PIPELINE","status":"PASS","mode":a.mode,"canonical_universe":"config/psy29_live_universe_contract.json","coverage":{"expected":29,"actual":29,"unique":29},"live_snapshot_to_stage16":True,"stage17_live_derived":True,"stage18_live_derived":True,"stage19_validation":"EXPLICIT_DETERMINISTIC_FIXTURE_CONTRACT","stage20_input_compatibility":True,"signal_generation":False,"order_execution":False,"stage20_invoked":False,"generated_at":stamp};(out/"PSY29_LIVE_END_TO_END_GATE.json").write_text(json.dumps(m,indent=2),encoding="utf-8");print(json.dumps(m,indent=2));print("PSY29 LIVE END-TO-END SIGNAL PIPELINE GATE: PASS")
if __name__=="__main__":main()
