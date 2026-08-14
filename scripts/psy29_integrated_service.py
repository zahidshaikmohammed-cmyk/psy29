#!/usr/bin/env python3
"""PSY29 free Render service: HTTP health + live acquisition/pipeline bridge."""
from __future__ import annotations
import json,os,subprocess,sys,threading,time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/"runtime/live"; STATE={"status":"STARTING","error":None}; LOCK=threading.Lock()
class H(BaseHTTPRequestHandler):
 def do_GET(self):
  if self.path=="/live-validation": f=OUT/"live_acquisition_validation.json"
  elif self.path=="/pipeline-validation": f=OUT/"live_pipeline_input_validation.json"
  else: f=None
  if f and f.exists(): body=f.read_bytes()
  else:
   with LOCK: body=json.dumps({"service":"PSY29 Live Market Pipeline","state":STATE,"repository_only":True,"provider":"DHAN","signal_generation":False,"order_execution":False},indent=2).encode()
  self.send_response(200);self.send_header("Content-Type","application/json");self.end_headers();self.wfile.write(body)
 def log_message(self,*a): pass
def worker():
 while True:
  try:
   with LOCK: STATE["status"]="RUNNING";STATE["error"]=None
   subprocess.run([sys.executable,str(ROOT/"scripts/psy29_live_pipeline_service_cycle.py")],cwd=ROOT,check=True,timeout=240)
   with LOCK: STATE["status"]="PASS"
  except Exception as e:
   with LOCK: STATE["status"]="FAIL";STATE["error"]=str(e)
  time.sleep(60)
threading.Thread(target=worker,daemon=True).start()
ThreadingHTTPServer(("0.0.0.0",int(os.environ.get("PORT","10000"))),H).serve_forever()
