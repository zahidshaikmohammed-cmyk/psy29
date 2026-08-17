#!/usr/bin/env python3
"""Fetch the most recent completed NSE session from real DHAN data for the read-only PSY29 terminal."""
from __future__ import annotations
import argparse,csv,json,sys,math
from datetime import datetime,timedelta,time as dtime,timezone
from pathlib import Path
from zoneinfo import ZoneInfo
REPO_ROOT=Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:sys.path.insert(0,str(REPO_ROOT))
from scripts.psy29_live_dhan_acquisition import add_indicators_1m,add_indicators_5m,completed_candles,load_universe,parse_rows,resolve_security_ids
from dhan.client import DhanClient
IST=ZoneInfo("Asia/Kolkata");MARKET_CLOSE=dtime(15,30);MARKET_OPEN=dtime(9,15);OPENING_RANGE_END=dtime(9,30);MAX_LOOKBACK_DAYS=10;STRUCTURAL_SWING_BARS=20

def candidate_dates(now,limit=MAX_LOOKBACK_DAYS):
 dates=[];day=now.date()
 if not(now.weekday()<5 and now.time()>MARKET_CLOSE):day-=timedelta(days=1)
 while len(dates)<limit:
  if day.weekday()<5:dates.append(day)
  day-=timedelta(days=1)
 return dates

def fetch_day(client,security_id,session_date):
 start=datetime.combine(session_date,MARKET_OPEN,tzinfo=IST);end=datetime.combine(session_date,MARKET_CLOSE,tzinfo=IST)+timedelta(minutes=1)
 return parse_rows(client.post("/charts/intraday",{"securityId":str(security_id),"exchangeSegment":"NSE_EQ","instrument":"EQUITY","interval":"1","oi":False,"fromDate":start.strftime("%Y-%m-%d %H:%M:%S"),"toDate":end.strftime("%Y-%m-%d %H:%M:%S")},timeout=20,retries=2))

def build_recent_row(symbol,security_id,df,session_date,now):
 raw1=completed_candles(df,1,now)
 if raw1.empty or len(raw1)<20:raise RuntimeError(f"{symbol}: insufficient historical 1m candles")
 x1=add_indicators_1m(df,session_date,now)
 if x1.empty:raise RuntimeError(f"{symbol}: no completed historical session candles")
 opening=x1[(x1.dt.dt.time>=MARKET_OPEN)&(x1.dt.dt.time<OPENING_RANGE_END)]
 if opening.empty:raise RuntimeError(f"{symbol}: no historical opening-range candles")
 x1["first15_high"]=float(opening.high.max());x1["first15_low"]=float(opening.low.min());x1["opening_range_complete"]=True
 bars=raw1.copy();bars["bucket"]=bars["dt"].dt.floor("5min")
 raw5=bars.groupby("bucket",sort=True).agg(open=("open","first"),high=("high","max"),low=("low","min"),close=("close","last"),volume=("volume","sum")).reset_index()
 raw5["timestamp"]=raw5["bucket"].map(lambda value:int(value.timestamp()));raw5=raw5[["timestamp","open","high","low","close","volume"]]
 if len(raw5)<20:raise RuntimeError(f"{symbol}: insufficient historical 5m candles")
 all5=completed_candles(raw5,5,now);x5=add_indicators_5m(raw5,session_date,now)
 if x5.empty:raise RuntimeError(f"{symbol}: no completed historical 5m candles")
 latest=x1.iloc[-1];latest5=x5.iloc[-1];latest_date=latest5["dt"].date();prior5=all5[all5["dt"].map(lambda d:d.date())<latest_date].sort_values("timestamp").tail(STRUCTURAL_SWING_BARS)
 if len(prior5)<STRUCTURAL_SWING_BARS:raise RuntimeError(f"{symbol}: insufficient historical 5m warm-up for structural swing window ({len(prior5)}/{STRUCTURAL_SWING_BARS})")
 avg1=float(raw1.volume.tail(20).mean());avg5=float(all5.volume.tail(20).mean())
 if not math.isfinite(avg1) or not math.isfinite(avg5) or avg1<=0 or avg5<=0:raise RuntimeError(f"{symbol}: insufficient warm-up volume history")
 ts=datetime.fromtimestamp(int(latest["timestamp"])+60,tz=timezone.utc).isoformat().replace("+00:00","Z")
 return {"symbol":symbol,"security_id":security_id,"exchange_segment":"NSE_EQ","timestamp":ts,"last_price":float(latest.close),"vwap":float(latest.vwap),"ema9":float(latest.ema9),"ema20":float(latest.ema20),"open_1m":float(latest.open),"high_1m":float(latest.high),"low_1m":float(latest.low),"close_1m":float(latest.close),"volume_1m":float(latest.volume),"avg_volume_20_1m":avg1,"open_5m":float(latest5.open),"high_5m":float(latest5.high),"low_5m":float(latest5.low),"close_5m":float(latest5.close),"volume_5m":float(latest5.volume),"avg_volume_20_5m":avg5,"vwap_5m":float(latest5.vwap5),"ema9_5m":float(latest5.ema9_5m),"ema20_5m":float(latest5.ema20_5m),"first15_high":float(latest.first15_high),"first15_low":float(latest.first15_low),"session_high":float(x5.high.max()),"session_low":float(x5.low.min()),"swing_high":float(prior5.high.max()),"swing_low":float(prior5.low.min()),"freshness_status":"RECENT_HISTORICAL","market_data_kind":"MOST_RECENT_COMPLETED_NSE_SESSION","session_date":str(session_date),"indicator_warmup":"10_CALENDAR_DAYS","structural_swing_warmup":"PRIOR_COMPLETED_SESSIONS","structural_swing_window_bars":STRUCTURAL_SWING_BARS,"structural_swing_policy":"PREVIOUS_SESSIONS_ONLY_EXCLUDE_CURRENT_SESSION","candle_completion_policy":"COMPLETED_CANDLES_ONLY","session_extreme_policy":"CURRENT_SESSION_COMPLETED_5M_RUNNING_EXTREMES"}

def write_snapshot(out,rows,session_date):
 out.mkdir(parents=True,exist_ok=True);rows.sort(key=lambda r:r["symbol"]);fields=list(rows[0])
 with (out/"recent_market_snapshot.csv").open("w",encoding="utf-8",newline="") as fh:csv.DictWriter(fh,fieldnames=fields).writerows(rows)
 validation={"contract":"PSY29_RECENT_DHAN_MARKET_DATA","status":"PASS","provider":"DHAN","live_data":False,"market_data_kind":"MOST_RECENT_COMPLETED_NSE_SESSION","session_date":str(session_date),"coverage":{"expected":29,"actual":len(rows),"unique":len({r["symbol"] for r in rows})},"source":"DHAN /charts/intraday historical data","generated_at":datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z"),"signal_generation":False,"order_execution":False}
 (out/"recent_market_data_validation.json").write_text(json.dumps(validation,indent=2),encoding="utf-8")

def main():
 parser=argparse.ArgumentParser();parser.add_argument("--universe",required=True,type=Path);parser.add_argument("--output",required=True,type=Path);args=parser.parse_args();symbols=load_universe(str(args.universe));client=DhanClient();mapping=resolve_security_ids(symbols);now=datetime.now(IST)
 for session_date in candidate_dates(now):
  rows=[];failures=[]
  for symbol in symbols:
   try:rows.append(build_recent_row(symbol,mapping[symbol],fetch_day(client,mapping[symbol],session_date),session_date,now))
   except Exception as exc:failures.append({"symbol":symbol,"error":str(exc)})
  if len(rows)==29 and not failures and len({r["symbol"] for r in rows})==29:write_snapshot(args.output,rows,session_date);print(json.dumps({"status":"PASS","provider":"DHAN","session_date":str(session_date),"coverage":29},indent=2));return
 raise SystemExit(f"Unable to obtain a complete 29/29 recent DHAN session: {failures}")
if __name__=="__main__":main()
