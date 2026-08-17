#!/usr/bin/env python3
"""PSY29 pre-opening-range live collector."""
from __future__ import annotations
import argparse,csv,json,math
from datetime import datetime,timezone,time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo
from scripts.psy29_live_dhan_acquisition import FRESH_MAX_AGE_SECONDS,add_indicators_1m,current_session,fetch_bars,load_universe,resolve_security_ids
from dhan.client import DhanClient
IST=ZoneInfo("Asia/Kolkata");SESSION_OPEN=dtime(9,15);OPENING_RANGE_END=dtime(9,30)
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--universe',required=True,type=Path);ap.add_argument('--output',required=True,type=Path);a=ap.parse_args();now=datetime.now(IST)
 if now.weekday()>=5 or not(SESSION_OPEN<=now.time()<OPENING_RANGE_END):raise SystemExit('PSY29 pre-open collector is only valid during 09:15-09:29 IST')
 symbols=load_universe(str(a.universe));client=DhanClient();mapping=resolve_security_ids(symbols);rows=[];errors=[]
 for symbol in symbols:
  try:
   raw1=fetch_bars(client,mapping[symbol],now,'1');x1=add_indicators_1m(raw1,now.date(),now)
   if x1.empty:raise RuntimeError('no completed current-session 1m candle yet')
   latest=x1.iloc[-1];candle_start=int(latest['timestamp']);candle_end=candle_start+60;age=(datetime.now(timezone.utc)-datetime.fromtimestamp(candle_end,tz=timezone.utc)).total_seconds()
   if age < -5:raise RuntimeError('provider returned a future timestamp')
   if age > FRESH_MAX_AGE_SECONDS:raise RuntimeError(f'live data freshness is STALE: {age:.1f}s')
   cur=current_session(x1,now.date());session_high=float(cur.high.max());session_low=float(cur.low.min());opening=cur[cur.dt.dt.time<OPENING_RANGE_END];complete=len(opening)>=15
   if not(math.isfinite(session_high) and math.isfinite(session_low)):raise RuntimeError('invalid current-session extremes')
   ts=datetime.fromtimestamp(candle_end,tz=timezone.utc).isoformat().replace('+00:00','Z')
   rows.append({'symbol':symbol,'security_id':mapping[symbol],'exchange_segment':'NSE_EQ','candle_start_timestamp':datetime.fromtimestamp(candle_start,tz=timezone.utc).isoformat().replace('+00:00','Z'),'timestamp':ts,'last_price':float(latest.close),'vwap':float(latest.vwap),'ema9':float(latest.ema9),'ema20':float(latest.ema20),'open_1m':float(latest.open),'high_1m':float(latest.high),'low_1m':float(latest.low),'close_1m':float(latest.close),'volume_1m':float(latest.volume),'session_high':session_high,'session_low':session_low,'first15_high':float(opening.high.max()) if complete else '','first15_low':float(opening.low.min()) if complete else '','opening_range_complete':complete,'freshness_age_seconds':round(max(0.0,age),3),'freshness_status':'FRESH','provider':'DHAN','market_data_kind':'LIVE_DHAN_PRE_OPENING_RANGE','session_date':str(now.date()),'candle_completion_policy':'COMPLETED_CANDLES_ONLY'})
  except Exception as exc:errors.append({'symbol':symbol,'error':str(exc)})
 a.output.mkdir(parents=True,exist_ok=True);rows.sort(key=lambda r:str(r['symbol']))
 if rows:
  with (a.output/'live_snapshot.csv').open('w',encoding='utf-8',newline='') as fh: w=csv.DictWriter(fh,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
 status='PASS' if len(rows)==29 and len({str(r['symbol']) for r in rows})==29 and not errors else 'FAIL';v={'contract':'PSY29_LIVE_DHAN_ACQUISITION_VALIDATION','status':status,'provider':'DHAN','live_data':True,'market_data_kind':'LIVE_DHAN_PRE_OPENING_RANGE','coverage':{'expected':29,'actual':len(rows),'unique':len({str(r["symbol"]) for r in rows})},'fresh_count':sum(str(r.get('freshness_status'))=='FRESH' for r in rows),'stale_count':sum('STALE' in str(e.get('error','')).upper() for e in errors),'invalid_count':len(errors),'errors':errors,'opening_range_complete':all(bool(r.get('opening_range_complete')) for r in rows) if rows else False,'timestamp_policy':'CANDLE_END_TIMESTAMP','candle_completion_policy':'COMPLETED_CANDLES_ONLY','signal_generation':False,'order_execution':False,'generated_at':datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z')};(a.output/'live_acquisition_validation.json').write_text(json.dumps(v,indent=2),encoding='utf-8');print(json.dumps(v,indent=2));
 if status!='PASS':raise SystemExit(1)
if __name__=='__main__':main()
