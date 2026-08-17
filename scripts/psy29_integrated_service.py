#!/usr/bin/env python3
"""PSY29 free Render service: live acquisition, validation, and live Stage 6-20 signal terminal."""
from __future__ import annotations

import csv
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone, time as dtime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runtime/live"
OUT.mkdir(parents=True, exist_ok=True)
STATE = {"status": "STARTING", "error": None, "last_cycle": None}
LOCK = threading.Lock()

UNIVERSE = ROOT / "config/psy29_live_universe_contract.json"
PIPELINE = OUT / "live_pipeline_input.csv"
PV = OUT / "live_pipeline_input_validation.json"
AV = OUT / "live_acquisition_validation.json"
RECENT = OUT / "recent_market_snapshot.csv"
RV = OUT / "recent_market_data_validation.json"
BOARD = OUT / "PSY29_STAGE20_FINAL_SIGNAL_BOARD.json"
SIGNALS = OUT / "PSY29_STAGE20_FINAL_SIGNALS.csv"
PAGE = ROOT / "web/psy29_signals.html"
CYCLE = OUT / "signal_cycle"
IST = ZoneInfo("Asia/Kolkata")

STAGE_ARTIFACTS = {
    6: "stage6/PSY29_STAGE6_LIVE_REGIMES.csv", 7: "stage7/PSY29_STAGE7_EDGE_ACTIVATION.csv",
    8: "stage8/PSY29_STAGE8_EDGE_RANKING.csv", 9: "stage9/PSY29_STAGE9_CANDIDATE_QUALITY.csv",
    10: "stage10/PSY29_STAGE10_INTEGRITY.csv", 11: "stage11/PSY29_STAGE11_EXECUTION_ANALYSIS.csv",
    12: "stage12/PSY29_STAGE12_EXECUTION_READINESS.csv", 13: "stage13/PSY29_STAGE13_SCENARIO_ADJUDICATION.csv",
    14: "stage14/PSY29_STAGE14_LIVE_DASHBOARD.csv", 15: "stage15/PSY29_STAGE15_EVENTS.csv",
    16: "stage16/PSY29_STAGE16_CURRENT_BOARD.csv", 17: "stage17/PSY29_STAGE17_STABILITY_BOARD.csv",
    18: "stage18/PSY29_STAGE18_HISTORICAL_BOARD.csv", 19: "stage19/PSY29_STAGE19_TRANSITION_BOARD.csv",
}
STAGE_NAMES = {6:"Regime",7:"Edge Activation",8:"Edge Ranking",9:"Candidate Quality",10:"Integrity",11:"Execution Analysis",12:"Readiness",13:"Scenario",14:"Dashboard",15:"Event Journal",16:"Decision Consolidation",17:"Stability",18:"Continuity",19:"Transition",20:"Final Authority"}


def rj(path: Path, default=None):
    try: return json.loads(path.read_text(encoding="utf-8"))
    except Exception: return default


def rc(path: Path):
    try:
        with path.open("r", encoding="utf-8", newline="") as handle: return list(csv.DictReader(handle))
    except Exception: return []


def symbols():
    data=rj(UNIVERSE,{}) or {}
    return [str(item["symbol"]).strip().upper() for item in data.get("universe",[]) if isinstance(item,dict) and item.get("symbol")]


def market_open_now():
    now=datetime.now(IST); return now.weekday()<5 and dtime(9,15)<=now.time()<=dtime(15,30)


def recent_ready():
    validation=rj(RV,{}) or {}
    if validation.get("status")!="PASS" or validation.get("provider")!="DHAN" or validation.get("live_data") is not False:return False
    coverage=validation.get("coverage") or {};rows=rc(RECENT)
    if coverage.get("expected")!=29 or coverage.get("actual")!=29 or coverage.get("unique")!=29 or len(rows)!=29:return False
    if str(validation.get("market_data_kind"))!="MOST_RECENT_COMPLETED_NSE_SESSION":return False
    if {str(row.get("market_data_kind")) for row in rows}!={"MOST_RECENT_COMPLETED_NSE_SESSION"}:return False
    if any(str(row.get("freshness_status"))!="RECENT_HISTORICAL" for row in rows):return False
    if len({str(row.get("session_date")) for row in rows})!=1:return False
    return str(rows[0].get("session_date"))==str(validation.get("session_date"))


def recent_stale(max_age_seconds=600):
    if not recent_ready():return True
    validation=rj(RV,{}) or {}
    try:
        generated=datetime.fromisoformat(str(validation["generated_at"]).replace("Z","+00:00"));return (datetime.now(timezone.utc)-generated).total_seconds()>max_age_seconds
    except Exception:return True


def sha256(path:Path):
    try:
        h=hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda:handle.read(1024*1024),b""):h.update(chunk)
        return h.hexdigest()
    except Exception:return None


def row_for_symbol(path:Path,symbol:str):
    for row in rc(path):
        if str(row.get("symbol","")).strip().upper()==symbol:return row
    return None


def row_state(row):
    if not row:return None
    for key in ("stage20_state","stage19_state","stage18_state","stage17_state","stage16_state","stage13_state","system_state","state","decision","signal_status"):
        value=row.get(key)
        if value not in (None,""):return str(value)
    return None


def row_timestamp(row):
    if not row:return None
    for key in ("timestamp","generated_at","live_data_timestamp","data_timestamp","as_of"):
        value=row.get(key)
        if value not in (None,""):return str(value)
    return None


def provenance_present(row):
    if not row:return False
    keys={str(k).lower() for k,v in row.items() if v not in (None,"",{},[])}
    return any("provenance" in key or key in {"source","provider"} for key in keys)


def audit_for_symbol(symbol):
    symbol=symbol.strip().upper();board=rj(BOARD,{}) or {}
    audit=next((x for x in board.get("audit",[]) if str(x.get("symbol","")).strip().upper()==symbol),None);stages=[]
    for stage,rel in STAGE_ARTIFACTS.items():
        path=CYCLE/rel;row=row_for_symbol(path,symbol) if path.exists() else None
        stages.append({"stage":stage,"name":STAGE_NAMES[stage],"artifact":rel,"artifact_exists":path.exists(),"row_present":row is not None,"state":row_state(row),"timestamp":row_timestamp(row),"provenance_present":provenance_present(row),"sha256":sha256(path) if path.exists() else None})
    final_path=BOARD
    stages.append({"stage":20,"name":STAGE_NAMES[20],"artifact":str(final_path.relative_to(ROOT)) if final_path.exists() else "runtime/live/PSY29_STAGE20_FINAL_SIGNAL_BOARD.json","artifact_exists":final_path.exists(),"row_present":audit is not None,"state":(audit or {}).get("decision") if isinstance(audit,dict) else None,"timestamp":board.get("generated_at"),"provenance_present":bool(board.get("provenance")),"sha256":sha256(final_path) if final_path.exists() else None})
    return {"symbol":symbol,"cycle_id":board.get("generated_at"),"final_decision":(audit or {}).get("decision") if isinstance(audit,dict) else None,"final_reason":(audit or {}).get("reason") if isinstance(audit,dict) else None,"stage16_state":(audit or {}).get("stage16_state") if isinstance(audit,dict) else None,"stage19_state":(audit or {}).get("stage19_state") if isinstance(audit,dict) else None,"scenario":(audit or {}).get("scenario") if isinstance(audit,dict) else None,"memory_state":(audit or {}).get("memory_state") if isinstance(audit,dict) else None,"stages":stages}


def cycle_integrity():
    expected=list(STAGE_ARTIFACTS.values());present=sum((CYCLE/rel).exists() for rel in expected)+int(BOARD.exists());expected_count=len(expected)+1
    hashes=[sha256(CYCLE/rel) for rel in expected if (CYCLE/rel).exists()]
    if BOARD.exists():hashes.append(sha256(BOARD))
    return {"cycle_id":(rj(BOARD,{}) or {}).get("generated_at"),"expected_artifacts":expected_count,"present_artifacts":present,"complete":present==expected_count,"artifact_hashes":hashes,"stage_range":"6-20"}


def signal_data():
    validation=rj(PV,{}) or {};board=rj(BOARD,{}) or {};rows=rc(SIGNALS);live=validation.get("live_data") is True;recent_validation=rj(RV,{}) or {};recent_ok=recent_ready();board_ok=str(board.get("status","")).upper() in {"PASS","VALID","READY"}
    active=[row for row in rows if str(row.get("signal_status","")).upper() not in {"","NO_SIGNAL","INVALID","REJECTED"}] if live and board_ok else []
    audit=board.get("audit") if isinstance(board.get("audit"),list) else [];instruments=[]
    for item in audit:
        if not isinstance(item,dict):continue
        x=dict(item);x["symbol"]=str(x.get("symbol","")).strip().upper();x["signal"]=next((s for s in active if str(s.get("symbol","")).strip().upper()==x["symbol"]),None);x["audit"]=audit_for_symbol(x["symbol"]);instruments.append(x)
    if live:coverage=validation.get("coverage",{"expected":29,"actual":0,"unique":0});timestamp=board.get("generated_at") or validation.get("timestamp");kind="LIVE_DHAN";session_date=None;status="LIVE"
    elif market_open_now():coverage={"expected":29,"actual":0,"unique":0};timestamp=None;kind="LIVE_DHAN_AWAITING_CYCLE";session_date=None;status="LIVE_AWAITING_DATA"
    else:coverage=recent_validation.get("coverage",{"expected":29,"actual":0,"unique":0}) if recent_ok else {"expected":29,"actual":0,"unique":0};timestamp=recent_validation.get("generated_at") if recent_ok else None;kind="MOST_RECENT_COMPLETED_NSE_SESSION" if recent_ok else "UNAVAILABLE";session_date=recent_validation.get("session_date") if recent_ok else None;status="OFF_MARKET"
    return {"service":"PSY29 LIVE SIGNAL BOARD","status":status,"live_data":live,"provider":"DHAN","market_data_kind":kind,"live_session_data":live,"signal_generation":live,"order_execution":False,"coverage":coverage,"timestamp":timestamp,"recent_session_date":session_date,"recent_validation_status":"PASS" if recent_ok else "UNAVAILABLE","signals":active,"active_signal_count":len(active),"instruments":instruments,"cycle_integrity":cycle_integrity(),"stage20":{"status":board.get("status"),"generated_at":board.get("generated_at"),"signal_count":board.get("signal_count",len(active)),"coverage":board.get("coverage"),"provenance":board.get("provenance")},"message":None if active else ("WAITING FOR FRESH LIVE DHAN CYCLE" if status=="LIVE_AWAITING_DATA" else "NO ACTIVE PSY29 SIGNAL")}


def instrument(symbol):
    symbol=symbol.strip().upper();validation=rj(PV,{}) or {};board=rj(BOARD,{}) or {};signal=next((row for row in rc(SIGNALS) if str(row.get("symbol","")).strip().upper()==symbol),None);live=validation.get("live_data") is True;source_rows=rc(PIPELINE) if live else (rc(RECENT) if recent_ready() else []);row=next((item for item in source_rows if str(item.get("symbol","")).strip().upper()==symbol),None);audit=next((x for x in (board.get("audit") or []) if str(x.get("symbol","")).strip().upper()==symbol),None)
    if not row:return {"symbol":symbol,"found":False,"live_data":live,"message":"Fresh live DHAN cycle is still pending." if market_open_now() and not live else ("Recent DHAN market data is not available yet." if not live else "Live instrument data not available yet."),"condition":audit,"audit":audit_for_symbol(symbol)}
    keys=["open_1m","high_1m","low_1m","close_1m","volume_1m","open_5m","high_5m","low_5m","close_5m","volume_5m","vwap_5m","ema9_5m","ema20_5m","first15_high","first15_low","swing_high","swing_low","timestamp","freshness_status","session_date","market_data_kind"]
    return {"symbol":symbol,"found":True,"live_data":live,"market_data_kind":"LIVE_DHAN" if live else "MOST_RECENT_COMPLETED_NSE_SESSION","recent_session_date":rj(RV,{}).get("session_date") if not live and recent_ready() else None,"coverage":validation.get("coverage") if live else rj(RV,{}).get("coverage"),"data":{key:row.get(key) for key in keys},"signal":signal if live else None,"condition":audit,"audit":audit_for_symbol(symbol),"strategy":(signal or {}).get("strategy") if live else None,"stage20_board_status":board.get("status")}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path=urlparse(self.path).path
        if path=="/signals":
            try:return self._send(PAGE.read_bytes(),"text/html; charset=utf-8")
            except Exception as exc:return self._send(json.dumps({"error":"signals_ui_unavailable","detail":str(exc)}).encode(),"application/json; charset=utf-8")
        if path=="/api/signals":return self._send(json.dumps(signal_data(),separators=(",",":")).encode())
        if path=="/api/universe":return self._send(json.dumps({"symbols":symbols()},separators=(",",":")).encode())
        if path.startswith("/api/instrument/"):return self._send(json.dumps(instrument(unquote(path.rsplit("/",1)[-1])),separators=(",",":")).encode())
        if path.startswith("/api/audit/"):return self._send(json.dumps(audit_for_symbol(unquote(path.rsplit("/",1)[-1])),separators=(",",":")).encode())
        source=AV if path=="/live-validation" else PV if path=="/pipeline-validation" else RV if path=="/recent-market-validation" else None
        if source and source.exists():return self._send(source.read_bytes())
        with LOCK:payload={"service":"PSY29 Live Market Pipeline","state":STATE,"repository_only":True,"provider":"DHAN","signal_generation":False,"order_execution":False}
        return self._send(json.dumps(payload,indent=2).encode())
    def _send(self,body,content_type="application/json; charset=utf-8"):
        self.send_response(200);self.send_header("Content-Type",content_type);self.send_header("Cache-Control","no-store, no-cache, must-revalidate");self.send_header("Pragma","no-cache");self.send_header("X-Content-Type-Options","nosniff");self.send_header("Content-Length",str(len(body)));self.end_headers();self.wfile.write(body)
    def log_message(self,*args):return


def worker():
    while True:
        try:
            with LOCK:STATE["status"]="RUNNING";STATE["error"]=None
            subprocess.run([sys.executable,str(ROOT/"scripts/psy29_live_pipeline_service_cycle.py")],cwd=ROOT,check=True,timeout=900)
            if recent_stale():subprocess.run([sys.executable,str(ROOT/"scripts/psy29_recent_dhan_snapshot.py"),"--universe",str(UNIVERSE),"--output",str(OUT)],cwd=ROOT,check=True,timeout=240)
            with LOCK:STATE["status"]="PASS";STATE["last_cycle"]=time.time()
        except Exception as exc:
            with LOCK:STATE["status"]="FAIL";STATE["error"]=str(exc)
        time.sleep(60)


if __name__=="__main__":
    threading.Thread(target=worker,daemon=True).start();ThreadingHTTPServer(("0.0.0.0",int(os.environ.get("PORT","10000"))),Handler).serve_forever()
