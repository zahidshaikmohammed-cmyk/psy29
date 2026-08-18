#!/usr/bin/env python3
"""PSY29 Render production service: live acquisition, validation, and Stage 6-20 terminal."""
from __future__ import annotations
import csv,hashlib,json,os,subprocess,sys,threading,time
from datetime import datetime,timezone,time as dtime
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote,urlparse
from zoneinfo import ZoneInfo
from psy29_runtime_state import load as load_runtime_state,save as save_runtime_state
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/"runtime/live";OUT.mkdir(parents=True,exist_ok=True)
RUNTIME_STATE=OUT/"PSY29_RUNTIME_STATE.json";STATE=load_runtime_state(RUNTIME_STATE);LOCK=threading.Lock()
UNIVERSE=ROOT/"config/psy29_live_universe_contract.json";PIPELINE=OUT/"live_pipeline_input.csv";PV=OUT/"live_pipeline_input_validation.json";AV=OUT/"live_acquisition_validation.json";RECENT=OUT/"recent_market_snapshot.csv";RV=OUT/"recent_market_data_validation.json";BOARD=OUT/"PSY29_STAGE20_FINAL_SIGNAL_BOARD.json";SIGNALS=OUT/"PSY29_STAGE20_FINAL_SIGNALS.csv";PAGE=ROOT/"web/psy29_signals.html";CYCLE=OUT/"signal_cycle";IST=ZoneInfo("Asia/Kolkata")
STAGE_ARTIFACTS={6:"stage6/PSY29_STAGE6_LIVE_REGIMES.csv",7:"stage7/PSY29_STAGE7_EDGE_ACTIVATION.csv",8:"stage8/PSY29_STAGE8_EDGE_RANKING.csv",9:"stage9/PSY29_STAGE9_CANDIDATE_QUALITY.csv",10:"stage10/PSY29_STAGE10_INTEGRITY.csv",11:"stage11/PSY29_STAGE11_EXECUTION_ANALYSIS.csv",12:"stage12/PSY29_STAGE12_EXECUTION_READINESS.csv",13:"stage13/PSY29_STAGE13_SCENARIO_ADJUDICATION.csv",14:"stage14/PSY29_STAGE14_LIVE_DASHBOARD.csv",15:"stage15/PSY29_STAGE15_EVENTS.csv",16:"stage16/PSY29_STAGE16_CURRENT_BOARD.csv",17:"stage17/PSY29_STAGE17_STABILITY_BOARD.csv",18:"stage18/PSY29_STAGE18_HISTORICAL_BOARD.csv",19:"stage19/PSY_STAGE19_TRANSITION_BOARD.csv"}
STAGE_ARTIFACTS[19]="stage19/PSY29_STAGE19_TRANSITION_BOARD.csv"
STAGE_NAMES={6:"Regime",7:"Edge Activation",8:"Edge Ranking",9:"Edge Ranking",10:"Integrity",11:"Execution Analysis",12:"Readiness",13:"Scenario",14:"Dashboard",15:"Event Journal",16:"Decision Consolidation",17:"Stability",18:"Continuity",19:"Transition",20:"Final Authority"}
def rj(path:Path,default=None):
    try:return json.loads(path.read_text(encoding="utf-8"))
    except Exception:return default
def rc(path:Path):
    try:
        with path.open("r",encoding="utf-8",newline="") as h:return list(csv.DictReader(h))
    except Exception:return []
def symbols():
    data=rj(UNIVERSE,{}) or {};return [str(x["symbol"]).strip().upper() for x in data.get("universe",[]) if isinstance(x,dict) and x.get("symbol")]
def market_open_now():
    now=datetime.now(IST);return now.weekday()<5 and dtime(9,15)<=now.time()<=dtime(15,30)
def recent_ready():
    v=rj(RV,{}) or {}
    if v.get("status")!="PASS" or v.get("provider")!="DHAN" or v.get("live_data") is not False:return False
    cov=v.get("coverage") or {};rows=rc(RECENT)
    return cov.get("expected")==29 and cov.get("actual")==29 and cov.get("unique")==29 and len(rows)==29 and str(v.get("market_data_kind"))=="MOST_RECENT_COMPLETED_NSE_SESSION" and {str(x.get("market_data_kind")) for x in rows}=={"MOST_RECENT_COMPLETED_NSE_SESSION"} and not any(str(x.get("freshness_status"))!="RECENT_HISTORICAL" for x in rows) and len({str(x.get("session_date")) for x in rows})==1 and str(rows[0].get("session_date"))==str(v.get("session_date"))
def recent_stale(max_age_seconds=600):
    if market_open_now():return False
    if not recent_ready():return True
    try:
        v=rj(RV,{}) or {};t=datetime.fromisoformat(str(v["generated_at"]).replace("Z","+00:00"));return (datetime.now(timezone.utc)-t).total_seconds()>max_age_seconds
    except Exception:return True
def sha256(path:Path):
    try:
        h=hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda:f.read(1024*1024),b""):h.update(chunk)
        return h.hexdigest()
    except Exception:return None
def row_for_symbol(path:Path,symbol:str):
    for row in rc(path):
        if str(row.get("symbol","")).strip().upper()==symbol:return row
    return None
def row_state(row):
    if not row:return None
    for key in ("stage20_state","stage19_state","stage18_state","stage17_state","stage16_state","stage13_state","system_state","state","decision","signal_status"):
        if row.get(key) not in (None,""):return str(row[key])
    return None
def row_timestamp(row):
    if not row:return None
    for key in ("timestamp","generated_at","live_data_timestamp","data_timestamp","as_of"):
        if row.get(key) not in (None,""):return str(row[key])
    return None
def provenance_present(row):
    if not row:return False
    keys={str(k).lower() for k,v in row.items() if v not in (None,"",{},[])};return any("provenance" in k or k in {"source","provider"} for k in keys)
def audit_for_symbol(symbol):
    symbol=symbol.strip().upper();board=rj(BOARD,{}) or {};audit=next((x for x in board.get("audit",[]) if str(x.get("symbol","")).strip().upper()==symbol),None);stages=[]
    for stage,rel in STAGE_ARTIFACTS.items():
        p=CYCLE/rel;row=row_for_symbol(p,symbol) if p.exists() else None;stages.append({"stage":stage,"name":STAGE_NAMES[stage],"artifact":rel,"artifact_exists":p.exists(),"row_present":row is not None,"state":row_state(row),"timestamp":row_timestamp(row),"provenance_present":provenance_present(row),"sha256":sha256(p) if p.exists() else None})
    stages.append({"stage":20,"name":STAGE_NAMES[20],"artifact":"runtime/live/PSY29_STAGE20_FINAL_SIGNAL_BOARD.json","artifact_exists":BOARD.exists(),"row_present":audit is not None,"state":(audit or {}).get("decision"),"timestamp":board.get("generated_at"),"provenance_present":bool(board.get("provenance")),"sha256":sha256(BOARD) if BOARD.exists() else None})
    return {"symbol":symbol,"cycle_id":board.get("generated_at"),"final_decision":(audit or {}).get("decision"),"final_reason":(audit or {}).get("reason"),"stage16_state":(audit or {}).get("stage16_state"),"stage19_state":(audit or {}).get("stage19_state"),"scenario":(audit or {}).get("scenario"),"memory_state":(audit or {}).get("memory_state"),"stages":stages}
def cycle_integrity():
    expected=list(STAGE_ARTIFACTS.values());present=sum((CYCLE/x).exists() for x in expected)+int(BOARD.exists());hashes=[sha256(CYCLE/x) for x in expected if (CYCLE/x).exists()];hashes+=([sha256(BOARD)] if BOARD.exists() else []);return {"cycle_id":(rj(BOARD,{}) or {}).get("generated_at"),"expected_artifacts":len(expected)+1,"present_artifacts":present,"complete":present==len(expected)+1,"artifact_hashes":hashes,"stage_range":"6-20"}
def market_payload_rows(live,recent_ok):
    source=PIPELINE if live else RECENT if recent_ok else None
    rows=rc(source) if source else []
    keys=["open_1m","high_1m","low_1m","close_1m","volume_1m","open_5m","high_5m","low_5m","close_5m","volume_5m","vwap_5m","ema9_5m","ema20_5m","first15_high","first15_low","swing_high","swing_low","timestamp","freshness_status","session_date","market_data_kind"]
    return {str(r.get("symbol","")).strip().upper():{k:r.get(k) for k in keys} for r in rows if str(r.get("symbol","")).strip()}
def signal_data():
    validation=rj(PV,{}) or {};board=rj(BOARD,{}) or {};rows=rc(SIGNALS);live=validation.get("live_data") is True;recent_validation=rj(RV,{}) or {};recent_ok=recent_ready();board_ok=str(board.get("status","")).upper() in {"PASS","VALID","READY"};active=[r for r in rows if str(r.get("signal_status","")).upper() not in {"","NO_SIGNAL","INVALID","REJECTED"}] if live and board_ok else [];audit=board.get("audit") if isinstance(board.get("audit"),list) else [];audit_map={str(x.get("symbol","")).strip().upper():x for x in audit if isinstance(x,dict)};market=market_payload_rows(live,recent_ok);instruments=[]
    for s in symbols():
        item=audit_map.get(s,{})
        instruments.append({"symbol":s,"decision":item.get("decision","NO_SIGNAL"),"reason":item.get("reason","No Stage 20 signal"),"stage16_state":item.get("stage16_state"),"stage19_state":item.get("stage19_state"),"scenario":item.get("scenario"),"memory_state":item.get("memory_state"),"signal":next((z for z in active if str(z.get("symbol","")).strip().upper()==s),None),"data":market.get(s),"data_found":s in market})
    if live:coverage=validation.get("coverage",{"expected":29,"actual":0,"unique":0});timestamp=board.get("generated_at") or validation.get("timestamp");kind="LIVE_DHAN";session_date=None;status="LIVE"
    elif market_open_now():coverage={"expected":29,"actual":0,"unique":0};timestamp=None;kind="LIVE_DHAN_AWAITING_CYCLE";session_date=None;status="LIVE_AWAITING_DATA"
    else:coverage=recent_validation.get("coverage",{"expected":29,"actual":0,"unique":0}) if recent_ok else {"expected":29,"actual":0,"unique":0};timestamp=recent_validation.get("generated_at") if recent_ok else None;kind="MOST_RECENT_COMPLETED_NSE_SESSION" if recent_ok else "UNAVAILABLE";session_date=recent_validation.get("session_date") if recent_ok else None;status="OFF_MARKET"
    return {"service":"PSY29 LIVE SIGNAL BOARD","status":status,"live_data":live,"provider":"DHAN","market_data_kind":kind,"live_session_data":live,"signal_generation":live,"order_execution":False,"coverage":coverage,"timestamp":timestamp,"recent_session_date":session_date,"recent_validation_status":"PASS" if recent_ok else "UNAVAILABLE","signals":active,"active_signal_count":len(active),"instruments":instruments,"cycle_integrity":cycle_integrity(),"runtime_state":load_runtime_state(RUNTIME_STATE),"stage20":{"status":board.get("status"),"generated_at":board.get("generated_at"),"signal_count":board.get("signal_count",len(active)),"coverage":board.get("coverage"),"provenance":board.get("provenance")},"message":None if active else ("WAITING FOR FRESH LIVE DHAN CYCLE" if status=="LIVE_AWAITING_DATA" else "NO ACTIVE PSY29 SIGNAL")}
def instrument(symbol):
    symbol=symbol.strip().upper();validation=rj(PV,{}) or {};board=rj(BOARD,{}) or {};signal=next((r for r in rc(SIGNALS) if str(r.get("symbol","")).strip().upper()==symbol),None);live=validation.get("live_data") is True;source_rows=rc(PIPELINE) if live else (rc(RECENT) if recent_ready() else []);row=next((x for x in source_rows if str(x.get("symbol","")).strip().upper()==symbol),None);audit=next((x for x in (board.get("audit") or []) if str(x.get("symbol","")).strip().upper()==symbol),None)
    if not row:return {"symbol":symbol,"found":False,"live_data":live,"message":"Fresh live DHAN cycle is still pending." if market_open_now() and not live else ("Recent DHAN market data is not available yet." if not live else "Live instrument data not available yet."),"condition":audit,"audit":audit_for_symbol(symbol)}
    keys=["open_1m","high_1m","low_1m","close_1m","volume_1m","open_5m","high_5m","low_5m","close_5m","volume_5m","vwap_5m","ema9_5m","ema20_5m","first15_high","first15_low","swing_high","swing_low","timestamp","freshness_status","session_date","market_data_kind"]
    return {"symbol":symbol,"found":True,"live_data":live,"market_data_kind":"LIVE_DHAN" if live else "MOST_RECENT_COMPLETED_NSE_SESSION","recent_session_date":rj(RV,{}).get("session_date") if not live and recent_ready() else None,"coverage":validation.get("coverage") if live else rj(RV,{}).get("coverage"),"data":{k:row.get(k) for k in keys},"signal":signal if live else None,"condition":audit,"audit":audit_for_symbol(symbol),"strategy":(signal or {}).get("strategy") if live else None,"stage20_board_status":board.get("status")}
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path=urlparse(self.path).path
        if path in {"/health","/healthz"}:
            runtime=load_runtime_state(RUNTIME_STATE);healthy=runtime.get("status") in {"PASS","RUNNING"} or runtime.get("status")=="STARTING";code=200 if healthy else 503;body=json.dumps({"status":"ok" if healthy else "degraded","service":"PSY29 LIVE MARKET","runtime_state":runtime,"render_ephemeral_storage":True,"durable_external_state":runtime.get("persistence") == "NEON_POSTGRES"},separators=(",",":")).encode();return self._send(body,"application/json; charset=utf-8",code)
        if path=="/signals":
            try:return self._send(PAGE.read_bytes(),"text/html; charset=utf-8")
            except Exception as exc:return self._send(json.dumps({"error":"signals_ui_unavailable","detail":str(exc)}).encode(),"application/json; charset=utf-8")
        if path=="/api/signals":return self._send(json.dumps(signal_data(),separators=(",",":")).encode())
        if path=="/api/universe":return self._send(json.dumps({"symbols":symbols()},separators=(",",":")).encode())
        if path.startswith("/api/instrument/"):return self._send(json.dumps(instrument(unquote(path.rsplit("/",1)[-1])),separators=(",",":")).encode())
        if path.startswith("/api/audit/"):return self._send(json.dumps(audit_for_symbol(unquote(path.rsplit("/",1)[-1])),separators=(",",":")).encode())
        source=AV if path=="/live-validation" else PV if path=="/pipeline-validation" else RV if path=="/recent-market-validation" else None
        if source and source.exists():return self._send(source.read_bytes())
        with LOCK:payload={"service":"PSY29 Live Market Pipeline","state":STATE,"runtime_state":load_runtime_state(RUNTIME_STATE),"repository_only":True,"provider":"DHAN","signal_generation":False,"order_execution":False}
        return self._send(json.dumps(payload,indent=2).encode())
    def _send(self,body,content_type="application/json; charset=utf-8",code=200):
        try:
            self.send_response(code);self.send_header("Content-Type",content_type);self.send_header("Cache-Control","no-store, no-cache, must-revalidate");self.send_header("Pragma","no-cache");self.send_header("X-Content-Type-Options","nosniff");self.send_header("Content-Length",str(len(body)));self.end_headers();self.wfile.write(body)
        except (BrokenPipeError,ConnectionResetError):pass
    def log_message(self,*args):return
def worker():
    while True:
        try:
            with LOCK:STATE.update({"status":"RUNNING","error":None});save_runtime_state(RUNTIME_STATE,{"status":"RUNNING","error":None})
            subprocess.run([sys.executable,str(ROOT/"scripts/psy29_live_pipeline_service_cycle.py")],cwd=ROOT,check=True,timeout=900)
            if (not market_open_now()) and recent_stale():subprocess.run([sys.executable,str(ROOT/"scripts/psy29_recent_dhan_snapshot.py"),"--universe",str(UNIVERSE),"--output",str(OUT)],cwd=ROOT,check=True,timeout=240)
            board=rj(BOARD,{}) or {};signals=board.get("signal_count",0);history=(board.get("production_cycle") or {}).get("history_depth",0);cycle_id=board.get("generated_at")
            with LOCK:STATE.update({"status":"PASS","error":None,"last_cycle":time.time()});save_runtime_state(RUNTIME_STATE,{"status":"PASS","error":None,"last_cycle":time.time(),"last_cycle_id":cycle_id,"last_signal_count":signals,"last_history_depth":history})
        except Exception as exc:
            with LOCK:STATE.update({"status":"FAIL","error":str(exc)});save_runtime_state(RUNTIME_STATE,{"status":"FAIL","error":str(exc)})
        next_minute=(int(time.time())//60+1)*60
        time.sleep(max(1.0,next_minute-time.time()))
if __name__=="__main__":
    save_runtime_state(RUNTIME_STATE,{"status":STATE.get("status","STARTING"),"error":STATE.get("error"),"last_cycle":STATE.get("last_cycle")});threading.Thread(target=worker,daemon=True).start();ThreadingHTTPServer(("0.0.0.0",int(os.environ.get("PORT","10000"))),Handler).serve_forever()
