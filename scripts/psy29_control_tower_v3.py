#!/usr/bin/env python3
"""PSY29 Control Tower V3: presentation layer over the existing live pipeline."""
from __future__ import annotations
import csv,json,os,subprocess,sys,threading,time
from datetime import datetime,timezone
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse,unquote
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'runtime/live'; OUT.mkdir(parents=True,exist_ok=True)
UNIVERSE=ROOT/'config/psy29_live_universe_contract.json'; PIPELINE=OUT/'live_pipeline_input.csv'; PV=OUT/'live_pipeline_input_validation.json'; RECENT=OUT/'recent_market_snapshot.csv'; RV=OUT/'recent_market_data_validation.json'; BOARD=OUT/'PSY29_STAGE20_FINAL_SIGNAL_BOARD.json'; SIGNALS=OUT/'PSY29_STAGE20_FINAL_SIGNALS.csv'; PAGE=ROOT/'web/psy29_control_tower_v3.html'
STATE={'status':'STARTING','error':None,'last_cycle':None}; LOCK=threading.Lock()
def rj(p,d=None):
    try:return json.loads(p.read_text(encoding='utf-8'))
    except Exception:return d
def rc(p):
    try:
        with p.open('r',encoding='utf-8',newline='') as f:return list(csv.DictReader(f))
    except Exception:return []
def symbols():
    d=rj(UNIVERSE,{}) or {};return [str(x['symbol']).strip().upper() for x in d.get('universe',[]) if isinstance(x,dict) and x.get('symbol')]
def recent_ready():
    v=rj(RV,{}) or {};c=v.get('coverage') or {};rows=rc(RECENT)
    if v.get('status')!='PASS' or v.get('provider')!='DHAN' or v.get('live_data') is not False:return False
    if c.get('expected')!=29 or c.get('actual')!=29 or c.get('unique')!=29 or len(rows)!=29:return False
    if str(v.get('market_data_kind'))!='MOST_RECENT_COMPLETED_NSE_SESSION':return False
    if {str(r.get('market_data_kind')) for r in rows}!={'MOST_RECENT_COMPLETED_NSE_SESSION'}:return False
    if any(str(r.get('freshness_status'))!='RECENT_HISTORICAL' for r in rows):return False
    if len({str(r.get('session_date')) for r in rows})!=1:return False
    return str(rows[0].get('session_date'))==str(v.get('session_date'))
def recent_stale(max_age_seconds=600):
    if not recent_ready():return True
    v=rj(RV,{}) or {}
    try:
        generated=datetime.fromisoformat(str(v['generated_at']).replace('Z','+00:00'));return (datetime.now(timezone.utc)-generated).total_seconds()>max_age_seconds
    except Exception:return True
def signal_data():
    v=rj(PV,{}) or {};b=rj(BOARD,{}) or {};rows=rc(SIGNALS);live=v.get('live_data') is True;recent_v=rj(RV,{}) or {};recent_ok=recent_ready();ok=str(b.get('status','')).upper() in {'PASS','VALID','READY'}
    sig=[x for x in rows if str(x.get('signal_status','')).upper() not in {'','NO_SIGNAL','INVALID','REJECTED'}] if live and ok else []
    if live:coverage=v.get('coverage',{'expected':29,'actual':0,'unique':0});timestamp=b.get('timestamp') or v.get('timestamp');kind='LIVE_DHAN';session_date=None
    else:coverage=recent_v.get('coverage',{'expected':29,'actual':0,'unique':0}) if recent_ok else {'expected':29,'actual':0,'unique':0};timestamp=recent_v.get('generated_at') if recent_ok else None;kind='MOST_RECENT_COMPLETED_NSE_SESSION' if recent_ok else 'UNAVAILABLE';session_date=recent_v.get('session_date') if recent_ok else None
    return {'service':'PSY29 LIVE SIGNAL BOARD','status':'LIVE' if live else 'OFF_MARKET','live_data':live,'provider':'DHAN','market_data_kind':kind,'live_session_data':live,'signal_generation':False,'order_execution':False,'coverage':coverage,'timestamp':timestamp,'recent_session_date':session_date,'recent_validation_status':'PASS' if recent_ok else 'UNAVAILABLE','signals':sig,'active_signal_count':len(sig),'message':None if sig else 'NO ACTIVE PSY29 SIGNAL'}
def instrument(symbol):
    symbol=symbol.strip().upper();v=rj(PV,{}) or {};b=rj(BOARD,{}) or {};sig=next((x for x in rc(SIGNALS) if str(x.get('symbol','')).strip().upper()==symbol),None);live=v.get('live_data') is True
    source=rc(PIPELINE) if live else (rc(RECENT) if recent_ready() else []);row=next((x for x in source if str(x.get('symbol','')).strip().upper()==symbol),None)
    if not row:return {'symbol':symbol,'found':False,'live_data':live,'message':'Recent DHAN market data is not available yet.' if not live else 'Live instrument data not available yet.'}
    keys=['open_1m','high_1m','low_1m','close_1m','volume_1m','open_5m','high_5m','low_5m','close_5m','volume_5m','vwap_5m','ema9_5m','ema20_5m','first15_high','first15_low','swing_high','swing_low','timestamp','freshness_status','session_date','market_data_kind']
    return {'symbol':symbol,'found':True,'live_data':live,'market_data_kind':'LIVE_DHAN' if live else 'MOST_RECENT_COMPLETED_NSE_SESSION','recent_session_date':rj(RV,{}).get('session_date') if not live and recent_ready() else None,'coverage':v.get('coverage') if live else rj(RV,{}).get('coverage'),'data':{k:row.get(k) for k in keys},'signal':sig if live else None,'strategy':(sig or {}).get('strategy') if live else None,'stage20_board_status':b.get('status')}
def run_cycle():
    subprocess.run([sys.executable,str(ROOT/'scripts/psy29_live_pipeline_service_cycle.py')],cwd=ROOT,check=True,timeout=240)
    if recent_stale():subprocess.run([sys.executable,str(ROOT/'scripts/psy29_recent_dhan_snapshot.py'),'--universe',str(UNIVERSE),'--output',str(OUT)],cwd=ROOT,check=True,timeout=240)
def worker():
    while True:
        try:
            with LOCK:STATE['status']='RUNNING';STATE['error']=None
            run_cycle()
            with LOCK:STATE['status']='PASS';STATE['last_cycle']=time.time()
        except Exception as e:
            with LOCK:STATE['status']='FAIL';STATE['error']=str(e)
        time.sleep(60)
class H(BaseHTTPRequestHandler):
    def _send(self,b,ct='application/json; charset=utf-8',status=200):
        self.send_response(status);self.send_header('Content-Type',ct);self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(b)
    def do_GET(self):
        p=urlparse(self.path).path
        try:
            if p=='/':return self._send(PAGE.read_bytes(),'text/html; charset=utf-8')
            if p=='/api/universe':return self._send(json.dumps({'symbols':symbols()}).encode())
            if p=='/api/signals':return self._send(json.dumps(signal_data(),default=str).encode())
            if p=='/api/health':
                with LOCK:s=dict(STATE)
                return self._send(json.dumps({'service':'PSY29 Control Tower V3','state':s,'provider':'DHAN','signal_generation':False,'order_execution':False}).encode())
            if p.startswith('/api/instrument/'):
                sym=unquote(p.rsplit('/',1)[-1]);return self._send(json.dumps(instrument(sym),default=str).encode())
            return self._send(b'{"error":"not found"}',status=404)
        except Exception as e:return self._send(json.dumps({'error':str(e)}).encode(),status=500)
    def log_message(self,*args):pass
threading.Thread(target=worker,daemon=True).start();ThreadingHTTPServer(('0.0.0.0',int(os.environ.get('PORT','10000'))),H).serve_forever()
