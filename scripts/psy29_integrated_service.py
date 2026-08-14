#!/usr/bin/env python3
"""PSY29 free Render service: live acquisition, validation, and read-only signal terminal."""
from __future__ import annotations
import csv,json,os,subprocess,sys,threading,time
from datetime import datetime,timezone
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/"runtime/live"; OUT.mkdir(parents=True,exist_ok=True)
STATE={"status":"STARTING","error":None,"last_cycle":None}; LOCK=threading.Lock()
UNIVERSE=ROOT/"config/psy29_live_universe_contract.json"
PIPELINE=OUT/"live_pipeline_input.csv"; PV=OUT/"live_pipeline_input_validation.json"; AV=OUT/"live_acquisition_validation.json"
RECENT=OUT/"recent_market_snapshot.csv"; RV=OUT/"recent_market_data_validation.json"
BOARD=OUT/"PSY29_STAGE20_FINAL_SIGNAL_BOARD.json"; SIGNALS=OUT/"PSY29_STAGE20_FINAL_SIGNALS.csv"

def rj(p,d=None):
 try:return json.loads(p.read_text(encoding="utf-8"))
 except Exception:return d

def rc(p):
 try:
  with p.open("r",encoding="utf-8",newline="") as f:return list(csv.DictReader(f))
 except Exception:return []

def symbols():
 d=rj(UNIVERSE,{}) or {}; return [str(x["symbol"]).strip().upper() for x in d.get("universe",[]) if isinstance(x,dict) and x.get("symbol")]

def recent_ready():
 v=rj(RV,{}) or {}
 if v.get("status")!="PASS" or v.get("provider")!="DHAN" or v.get("live_data") is not False:return False
 c=v.get("coverage") or {}
 return c.get("expected")==29 and c.get("actual")==29 and c.get("unique")==29 and len(rc(RECENT))==29

def recent_stale(max_age_seconds=600):
 if not recent_ready(): return True
 v=rj(RV,{}) or {}
 try:
  generated=datetime.fromisoformat(str(v["generated_at"]).replace("Z","+00:00"))
  return (datetime.now(timezone.utc)-generated).total_seconds()>max_age_seconds
 except Exception:return True

def signal_data():
 v=rj(PV,{}) or {}; b=rj(BOARD,{}) or {}; rows=rc(SIGNALS); live=v.get("live_data") is True
 ok=str(b.get("status","")).upper() in {"PASS","VALID","READY"}
 sig=[x for x in rows if str(x.get("signal_status","")).upper() not in {"","NO_SIGNAL","INVALID","REJECTED"}] if live and ok else []
 return {"service":"PSY29 LIVE SIGNAL BOARD","status":"LIVE" if live else "OFF_MARKET","live_data":live,"market_data_kind":"LIVE_DHAN" if live else (rj(RV,{}).get("market_data_kind") if recent_ready() else "UNAVAILABLE"),"live_session_data":live,"signal_generation":False,"order_execution":False,"coverage":v.get("coverage",{"expected":29,"actual":0,"unique":0}),"timestamp":b.get("timestamp") or v.get("timestamp"),"recent_session_date":rj(RV,{}).get("session_date") if recent_ready() else None,"signals":sig,"active_signal_count":len(sig),"message":None if sig else "NO ACTIVE PSY29 SIGNAL"}

def instrument(symbol):
 symbol=symbol.strip().upper(); v=rj(PV,{}) or {}; b=rj(BOARD,{}) or {}; sig=next((x for x in rc(SIGNALS) if str(x.get("symbol","")).strip().upper()==symbol),None)
 live=v.get("live_data") is True
 source_rows=rc(PIPELINE) if live else (rc(RECENT) if recent_ready() else [])
 row=next((x for x in source_rows if str(x.get("symbol","")).strip().upper()==symbol),None)
 if not row:return {"symbol":symbol,"found":False,"live_data":live,"message":"Recent DHAN market data is not available yet." if not live else "Live instrument data not available yet."}
 keys=["open_1m","high_1m","low_1m","close_1m","volume_1m","open_5m","high_5m","low_5m","close_5m","volume_5m","vwap_5m","ema9_5m","ema20_5m","first15_high","first15_low","swing_high","swing_low","timestamp","freshness_status","session_date","market_data_kind"]
 return {"symbol":symbol,"found":True,"live_data":live,"market_data_kind":"LIVE_DHAN" if live else "MOST_RECENT_COMPLETED_NSE_SESSION","recent_session_date":rj(RV,{}).get("session_date") if not live and recent_ready() else None,"coverage":v.get("coverage") if live else rj(RV,{}).get("coverage"),"data":{k:row.get(k) for k in keys},"signal":sig if live else None,"strategy":(sig or {}).get("strategy") if live else None,"stage20_board_status":b.get("status")}

PAGE='''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>PSY29 Terminal</title><style>
:root{color-scheme:dark;font-family:ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;background:#212121;color:#ececec}*{box-sizing:border-box}body{margin:0;background:#212121}button{font:inherit;color:inherit}.app{display:grid;grid-template-columns:270px 1fr;min-height:100vh}.side{background:#171717;border-right:1px solid #333;padding:16px;overflow:auto}.brand{font-size:18px;font-weight:650;padding:8px 10px 18px}.sub{font-size:11px;color:#8e8e8e;text-transform:uppercase;letter-spacing:.12em;padding:0 10px 8px}.stock{display:flex;width:100%;align-items:center;justify-content:space-between;border:0;background:transparent;border-radius:9px;padding:9px 10px;margin:2px 0;text-align:left;cursor:pointer}.stock:hover,.stock.active{background:#2f2f2f}.dot{width:7px;height:7px;border-radius:50%;background:#666;display:inline-block;margin-right:8px}.main{padding:26px;max-width:1400px;width:100%;margin:auto}.top{display:flex;justify-content:space-between;gap:20px;align-items:flex-start}.eyebrow{font-size:12px;color:#9b9b9b;letter-spacing:.12em;text-transform:uppercase}.title{font-size:30px;font-weight:650;margin:5px 0}.muted{color:#999}.status{border:1px solid #3a3a3a;background:#2a2a2a;border-radius:20px;padding:8px 12px;font-size:12px}.notice{margin-top:10px;padding:10px 12px;border:1px solid #3a3a3a;border-radius:10px;background:#252525;color:#aaa;font-size:12px}.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:22px 0}.card{background:#2a2a2a;border:1px solid #3a3a3a;border-radius:13px;padding:15px}.label{color:#9b9b9b;font-size:11px;text-transform:uppercase;letter-spacing:.08em}.value{font-size:20px;margin-top:5px;font-variant-numeric:tabular-nums}.section{margin-top:14px}.section h2{font-size:15px;margin:0 0 10px}.table{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:1px;background:#3a3a3a;border:1px solid #3a3a3a;border-radius:12px;overflow:hidden}.cell{background:#242424;padding:12px}.k{font-size:11px;color:#909090}.v{font-variant-numeric:tabular-nums;margin-top:3px}.signal{border:1px solid #3a3a3a;border-radius:14px;padding:18px;background:#252525}.signalrow{display:grid;grid-template-columns:repeat(6,1fr);gap:10px}.empty{padding:30px;text-align:center;color:#999;border:1px dashed #444;border-radius:12px}.progress{display:flex;gap:6px;flex-wrap:wrap}.stage{padding:6px 9px;border-radius:7px;background:#23382c;color:#8be0a9;font-size:11px}@media(max-width:850px){.app{grid-template-columns:1fr}.side{max-height:260px;border-right:0;border-bottom:1px solid #333}.grid,.table{grid-template-columns:repeat(2,1fr)}.signalrow{grid-template-columns:repeat(2,1fr)}.main{padding:18px}}
</style></head><body><div class="app"><aside class="side"><div class="brand">PSY29 <span class="muted">Terminal</span></div><div class="sub">29 instruments</div><div id="stocks"></div></aside><main class="main"><div class="top"><div><div class="eyebrow">Final Trading Signal Engine</div><div class="title" id="title">Select an instrument</div><div class="muted">Read-only terminal · Stage 20 is the sole signal authority</div><div class="notice" id="notice">Loading market provenance…</div></div><div class="status" id="status">CONNECTING…</div></div><div class="grid" id="summary"></div><div class="section"><h2>Calculation map</h2><div class="progress" id="progress"></div></div><div class="section"><h2>Market map</h2><div class="table" id="market"></div></div><div class="section"><h2>Stage 20 signal</h2><div id="signal"></div></div></main></div><script>
let selected=null,universe=[];const esc=x=>String(x??'—').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));async function j(u){return (await fetch(u,{cache:'no-store'})).json()}function cell(k,v){return `<div class="cell"><div class="k">${esc(k)}</div><div class="v">${esc(v)}</div></div>`}
async function load(){let s=await j('/api/signals');document.getElementById('status').textContent=s.live_data?'● LIVE DHAN':'OFF-MARKET · RECENT DHAN';document.getElementById('notice').textContent=s.live_data?'Real-time DHAN session data.':'Real DHAN historical data from the most recent completed NSE session ('+(s.recent_session_date||'pending')+'). This is NOT live and is never the deterministic fixture.';if(!universe.length){universe=(await j('/api/universe')).symbols||[];document.getElementById('stocks').innerHTML=universe.map(x=>`<button class="stock" data-s="${esc(x)}" onclick="select('${esc(x)}')"><span><i class="dot"></i>${esc(x)}</span><span class="muted">›</span></button>`).join('')}if(selected)await select(selected);else if(universe[0])await select(universe[0])}
async function select(x){selected=x;document.querySelectorAll('.stock').forEach(b=>b.classList.toggle('active',b.dataset.s===x));let d=await j('/api/instrument/'+encodeURIComponent(x));document.getElementById('title').textContent=x;if(!d.found){document.getElementById('summary').innerHTML='';document.getElementById('market').innerHTML='<div class="empty">'+esc(d.message)+'</div>';return}let q=d.data;document.getElementById('summary').innerHTML=[['Last',q.close_1m],['VWAP',q.vwap_5m],['EMA 9',q.ema9_5m],['EMA 20',q.ema20_5m],['1m Volume',q.volume_1m],['5m Volume',q.volume_5m],['15m High',q.first15_high],['15m Low',q.first15_low]].map(a=>`<div class="card"><div class="label">${esc(a[0])}</div><div class="value">${esc(a[1])}</div></div>`).join('');document.getElementById('progress').innerHTML=['DHAN acquisition','29-stock validation','1m OHLC','5m OHLC','VWAP','EMA 9','EMA 20','Opening range','Swing structure'].map(x=>`<span class="stage">✓ ${x}</span>`).join('');document.getElementById('market').innerHTML=[['1m Open',q.open_1m],['1m High',q.high_1m],['1m Low',q.low_1m],['1m Close',q.close_1m],['5m Open',q.open_5m],['5m High',q.high_5m],['5m Low',q.low_5m],['5m Close',q.close_5m],['VWAP 5m',q.vwap_5m],['EMA 9 5m',q.ema9_5m],['EMA 20 5m',q.ema20_5m],['Swing High',q.swing_high],['Swing Low',q.swing_low],['First 15m High',q.first15_high],['First 15m Low',q.first15_low],['Session',q.session_date],['Timestamp',q.timestamp],['Provenance',q.market_data_kind]].map(a=>cell(a[0],a[1])).join('');let sig=d.signal;if(!d.live_data){document.getElementById('signal').innerHTML='<div class="empty">Market closed. Real recent DHAN data is shown for analysis only — <b>NOT LIVE</b>. Deterministic fixture data is not displayed here.</div>';return}if(!sig){document.getElementById('signal').innerHTML='<div class="empty">NO ACTIVE PSY29 SIGNAL</div>';return}document.getElementById('signal').innerHTML=`<div class="signal"><h3>${esc(sig.direction)} · ${esc(sig.strategy)}</h3><div class="signalrow">${[['Entry',sig.entry],['Stop Loss',sig.stop_loss],['Take Profit',sig.take_profit],['R:R',sig.risk_reward],['Score',sig.signal_score],['Status',sig.signal_status]].map(a=>`<div><div class="label">${esc(a[0])}</div><div class="value">${esc(a[1])}</div></div>`).join('')}</div></div>`}
load();setInterval(load,5000);</script></body></html>'''

class H(BaseHTTPRequestHandler):
 def do_GET(self):
  p=urlparse(self.path).path
  if p=="/signals":return self._send(PAGE.encode(),"text/html; charset=utf-8")
  if p=="/api/signals":return self._send(json.dumps(signal_data(),separators=(",",":")).encode())
  if p=="/api/universe":return self._send(json.dumps({"symbols":symbols()},separators=(",",":")).encode())
  if p.startswith("/api/instrument/"):return self._send(json.dumps(instrument(p.rsplit('/',1)[-1]),separators=(",",":")).encode())
  f=AV if p=="/live-validation" else PV if p=="/pipeline-validation" else RV if p=="/recent-market-validation" else None
  if f and f.exists():return self._send(f.read_bytes())
  with LOCK: body=json.dumps({"service":"PSY29 Live Market Pipeline","state":STATE,"repository_only":True,"provider":"DHAN","signal_generation":False,"order_execution":False},indent=2).encode()
  return self._send(body)
 def _send(self,b,ct="application/json; charset=utf-8"):
  self.send_response(200);self.send_header("Content-Type",ct);self.send_header("Cache-Control","no-store");self.end_headers();self.wfile.write(b)
 def log_message(self,*a):pass

def worker():
 while True:
  try:
   with LOCK:STATE["status"]="RUNNING";STATE["error"]=None
   subprocess.run([sys.executable,str(ROOT/"scripts/psy29_live_pipeline_service_cycle.py")],cwd=ROOT,check=True,timeout=240)
   if recent_stale():
    subprocess.run([sys.executable,str(ROOT/"scripts/psy29_recent_dhan_snapshot.py"),"--universe",UNIVERSE,"--output",OUT],cwd=ROOT,check=True,timeout=240)
   with LOCK:STATE["status"]="PASS";STATE["last_cycle"]=time.time()
  except Exception as e:
   with LOCK:STATE["status"]="FAIL";STATE["error"]=str(e)
  time.sleep(60)
threading.Thread(target=worker,daemon=True).start();ThreadingHTTPServer(("0.0.0.0",int(os.environ.get("PORT","10000"))),H).serve_forever()
