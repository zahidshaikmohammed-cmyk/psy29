#!/usr/bin/env python3
"""PSY29 live DHAN acquisition with completed-candle and indicator integrity gates."""
from __future__ import annotations
import argparse,json,math,sys
from datetime import datetime,timedelta,timezone,time as dtime
from io import StringIO
from pathlib import Path
from zoneinfo import ZoneInfo
REPO_ROOT=Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:sys.path.insert(0,str(REPO_ROOT))
import pandas as pd,requests
from dhan.client import DhanClient
IST=ZoneInfo("Asia/Kolkata");MASTER_URL="https://images.dhan.co/api-data/api-scrip-master-detailed.csv";FRESH_MAX_AGE_SECONDS=90;WARMUP_CALENDAR_DAYS=10;SESSION_OPEN=dtime(9,15);SESSION_CLOSE=dtime(15,30);OPENING_RANGE_END=dtime(9,30)
REQUIRED_SNAPSHOT={"symbol","timestamp","last_price","vwap","ema9","ema20","first15_high","first15_low"}
def load_universe(path):
 d=json.loads(Path(path).read_text(encoding="utf-8"));u=d.get("universe",[]);s=[str(x["symbol"]).strip().upper() for x in u];r=[int(x.get("rank",0)) for x in u]
 if len(s)!=29 or len(set(s))!=29 or r!=list(range(1,30)):raise RuntimeError("Canonical live universe must contain exactly 29 unique ranked symbols")
 return s
def resolve_security_ids(symbols):
 m=pd.read_csv(StringIO(requests.get(MASTER_URL,timeout=90).text),low_memory=False);sym_col=next((c for c in ("UNDERLYING_SYMBOL","SEM_TRADING_SYMBOL","SYMBOL_NAME","DISPLAY_NAME") if c in m),None);id_col=next((c for c in ("SECURITY_ID","SECURITYID") if c in m),None)
 if "EXCH_ID" not in m or "SEGMENT" not in m or not sym_col or not id_col:raise RuntimeError("DHAN instrument master lacks required NSE equity fields")
 eq=m[(m.EXCH_ID=="NSE")&(m.SEGMENT=="E")].copy();eq["_symbol"]=eq[sym_col].astype(str).str.upper().str.strip();eq["_id"]=eq[id_col].astype(str).str.strip();out={};bad=[]
 for s in symbols:
  ids=sorted(set(eq.loc[(eq._symbol==s)&(eq._id!=""),"_id"].tolist()))
  if len(ids)!=1:bad.append({"symbol":s,"security_ids":ids})
  else:out[s]=ids[0]
 if bad or len(out)!=29 or len(set(out.values()))!=29:raise RuntimeError(f"Security-ID resolution failed: {bad}")
 return out
def parse_rows(obj):
 d=obj.get("data",obj) if isinstance(obj,dict) else obj
 if not isinstance(d,dict) or not d.get("timestamp"):return pd.DataFrame(columns=["timestamp","open","high","low","close","volume"])
 n=len(d["timestamp"]);rows=[]
 for i in range(n):
  row={"timestamp":int(float(d["timestamp"][i]))}
  for k in ("open","high","low","close","volume"):
   if k not in d or i>=len(d[k]):raise RuntimeError(f"DHAN candle field length mismatch: {k}")
   row[k]=float(d[k][i])
  rows.append(row)
 return pd.DataFrame(rows).sort_values("timestamp").drop_duplicates("timestamp",keep="last").reset_index(drop=True)
def fetch_bars(client,security_id,now,interval):
 start=(now-timedelta(days=WARMUP_CALENDAR_DAYS)).replace(hour=9,minute=15,second=0,microsecond=0)
 p={"securityId":str(security_id),"exchangeSegment":"NSE_EQ","instrument":"EQUITY","interval":interval,"oi":False,"fromDate":start.strftime("%Y-%m-%d %H:%M:%S"),"toDate":now.strftime("%Y-%m-%d %H:%M:%S")}
 return parse_rows(client.post("/charts/intraday",p,timeout=20,retries=2))
def epoch_to_ist(ts):return datetime.fromtimestamp(int(ts),tz=timezone.utc).astimezone(IST)
def validate_ohlcv(df,name):
 if df.empty:raise RuntimeError(f"{name}: no candles")
 for c in ("open","high","low","close","volume"):
  if not pd.to_numeric(df[c],errors="coerce").notna().all():raise RuntimeError(f"{name}: non-numeric {c}")
 if (df[["open","high","low","close"]]<=0).any().any():raise RuntimeError(f"{name}: non-positive price")
 if (df.volume<0).any():raise RuntimeError(f"{name}: negative volume")
 if (df.high<df[["open","close","low"]].max(axis=1)).any():raise RuntimeError(f"{name}: high below OHLC component")
 if (df.low>df[["open","close","high"]].min(axis=1)).any():raise RuntimeError(f"{name}: low above OHLC component")
def completed_candles(df,minutes,now):
 x=df.copy();x["dt"]=x.timestamp.map(epoch_to_ist);cutoff=now.astimezone(IST);x=x[x.dt.map(lambda d:d+timedelta(minutes=minutes)<=cutoff)].copy();return x.sort_values("timestamp").drop_duplicates("timestamp",keep="last").reset_index(drop=True)
def current_session(df,session_date):
 return df[(df.dt.dt.date==session_date)&(df.dt.dt.time>=SESSION_OPEN)&(df.dt.dt.time<=SESSION_CLOSE)].sort_values("timestamp").reset_index(drop=True)
def add_indicators_1m(df,session_date,now):
 x=completed_candles(df,1,now);validate_ohlcv(x,"1m history");x["ema9_all"]=x.close.ewm(span=9,adjust=False).mean();x["ema20_all"]=x.close.ewm(span=20,adjust=False).mean();cur=current_session(x,session_date)
 if cur.empty:return cur
 typ=(cur.high+cur.low+cur.close)/3.0;v=cur.volume.clip(lower=0);cur["vwap"]=(typ*v).cumsum()/v.cumsum().replace(0,math.nan);cur["ema9"]=cur.ema9_all;cur["ema20"]=cur.ema20_all;opening=cur[cur.dt.dt.time<OPENING_RANGE_END]
 if len(opening)<15:cur["opening_range_complete"]=False;return cur
 cur["first15_high"]=float(opening.high.max());cur["first15_low"]=float(opening.low.min());cur["opening_range_complete"]=True;return cur
def add_indicators_5m(df,session_date,now):
 x=completed_candles(df,5,now);validate_ohlcv(x,"5m history");x["ema9_all"]=x.close.ewm(span=9,adjust=False).mean();x["ema20_all"]=x.close.ewm(span=20,adjust=False).mean();cur=current_session(x,session_date)
 if cur.empty:return cur
 typ=(cur.high+cur.low+cur.close)/3.0;v=cur.volume.clip(lower=0);cur["vwap5"]=(typ*v).cumsum()/v.cumsum().replace(0,math.nan);cur["ema9_5m"]=cur.ema9_all;cur["ema20_5m"]=cur.ema20_all;return cur
def build_execution_row(symbol,security_id,x1,x5,all1,all5,timestamp):
 if x1.empty or x5.empty:raise RuntimeError(f"{symbol}: no completed current-session candles")
 if not bool(x1.iloc[-1]["opening_range_complete"]):raise RuntimeError(f"{symbol}: opening range incomplete before 09:30 IST")
 latest=x1.iloc[-1];latest5=x5.iloc[-1];prior5=x5.iloc[:-1].tail(20) or x5.tail(1);avg1=all1.volume.tail(20).mean();avg5=all5.volume.tail(20).mean()
 if not math.isfinite(float(avg1)) or not math.isfinite(float(avg5)) or float(avg1)<=0 or float(avg5)<=0:raise RuntimeError(f"{symbol}: insufficient warm-up volume history")
 return {"symbol":symbol,"security_id":security_id,"exchange_segment":"NSE_EQ","timestamp":timestamp,"last_price":float(latest.close),"vwap":float(latest.vwap),"ema9":float(latest.ema9),"ema20":float(latest.ema20),"open_1m":float(latest.open),"high_1m":float(latest.high),"low_1m":float(latest.low),"close_1m":float(latest.close),"volume_1m":float(latest.volume),"avg_volume_20_1m":float(avg1),"open_5m":float(latest5.open),"high_5m":float(latest5.high),"low_5m":float(latest5.low),"close_5m":float(latest5.close),"volume_5m":float(latest5.volume),"avg_volume_20_5m":float(avg5),"vwap_5m":float(latest5.vwap5),"ema9_5m":float(latest5.ema9_5m),"ema20_5m":float(latest5.ema20_5m),"first15_high":float(latest.first15_high),"first15_low":float(latest.first15_low),"swing_high":float(prior5.high.max()),"swing_low":float(prior5.low.min()),"freshness_status":"FRESH","indicator_warmup":"10_CALENDAR_DAYS","candle_completion_policy":"COMPLETED_CANDLES_ONLY"}
def main():
 ap=argparse.ArgumentParser();ap.add_argument("--universe",required=True);ap.add_argument("--output",required=True);a=ap.parse_args();out=Path(a.output);out.mkdir(parents=True,exist_ok=True);symbols=load_universe(a.universe);client=DhanClient();mapping=resolve_security_ids(symbols);now=datetime.now(IST);session_date=now.date();snap=[];exe=[];errors=[]
 for s in symbols:
  try:
   raw1=fetch_bars(client,mapping[s],now,"1");raw5=fetch_bars(client,mapping[s],now,"5");x1=add_indicators_1m(raw1,session_date,now);x5=add_indicators_5m(raw5,session_date,now)
   if x1.empty or x5.empty:raise RuntimeError("no current-session completed candles returned")
   if not bool(x1.iloc[-1]["opening_range_complete"]):raise RuntimeError("OPENING_RANGE_INCOMPLETE")
   latest_ts=int(x1.iloc[-1].timestamp);candle_end_ts=latest_ts+60;age=(datetime.now(timezone.utc)-datetime.fromtimestamp(candle_end_ts,tz=timezone.utc)).total_seconds()
   if age< -5:raise RuntimeError("provider returned a future timestamp")
   if age>FRESH_MAX_AGE_SECONDS:raise RuntimeError(f"live data freshness is STALE: {age:.1f}s")
   ts=datetime.fromtimestamp(candle_end_ts,tz=timezone.utc).isoformat().replace("+00:00","Z")
   snap.append({"symbol":s,"candle_start_timestamp":datetime.fromtimestamp(latest_ts,tz=timezone.utc).isoformat().replace("+00:00","Z"),"timestamp":ts,"last_price":float(x1.iloc[-1].close),"vwap":float(x1.iloc[-1].vwap),"ema9":float(x1.iloc[-1].ema9),"ema20":float(x1.iloc[-1].ema20),"first15_high":float(x1.iloc[-1].first15_high),"first15_low":float(x1.iloc[-1].first15_low),"freshness_age_seconds":round(max(0.0,age),3),"freshness_status":"FRESH","provider":"DHAN","security_id":mapping[s],"exchange_segment":"NSE_EQ","indicator_warmup":"10_CALENDAR_DAYS","candle_completion_policy":"COMPLETED_CANDLES_ONLY","opening_range_complete":True})
   exe.append(build_execution_row(s,mapping[s],x1,x5,completed_candles(raw1,1,now),completed_candles(raw5,5,now),ts))
  except Exception as exc:errors.append({"symbol":s,"error":str(exc)})
 snapshot=pd.DataFrame(snap);execution=pd.DataFrame(exe)
 if not snapshot.empty:snapshot.to_csv(out/"live_snapshot.csv",index=False)
 if not execution.empty:execution.to_csv(out/"execution_snapshot.csv",index=False)
 stale=sum("STALE" in e["error"].upper() for e in errors);invalid=len(errors)-stale;status="PASS" if len(snap)==29 and len(exe)==29 and not errors and set(snapshot.columns)>=REQUIRED_SNAPSHOT and (snapshot.freshness_status=="FRESH").all() and (snapshot.opening_range_complete==True).all() else "FAIL"
 validation={"contract":"PSY29_LIVE_DHAN_ACQUISITION_VALIDATION","status":status,"provider":"DHAN","coverage":{"expected":29,"actual":len(snap),"unique":int(snapshot.symbol.nunique()) if not snapshot.empty else 0},"fresh_count":int((snapshot.freshness_status=="FRESH").sum()) if not snapshot.empty else 0,"stale_count":stale,"invalid_count":invalid,"errors":errors,"timestamp":datetime.now(timezone.utc).isoformat().replace("+00:00","Z"),"source":"PSY29/dhan/client.py + DHAN v2 intraday historical data","indicator_warmup":"10_CALENDAR_DAYS","candle_completion_policy":"COMPLETED_CANDLES_ONLY","freshness_timestamp_policy":"CANDLE_END_TIMESTAMP","opening_range_policy":"09:15-09:29 IST, complete before pipeline acceptance","signal_generation":False,"order_execution":False}
 (out/"live_acquisition_validation.json").write_text(json.dumps(validation,indent=2),encoding="utf-8");(out/"security_map.json").write_text(json.dumps({"status":"PASS","canonical_count":29,"resolved_count":29,"unique_security_id_count":29,"mappings":[{"symbol":s,"security_id":mapping[s],"exchange":"NSE","segment":"E","exchange_segment":"NSE_EQ"} for s in symbols]},indent=2),encoding="utf-8");print(json.dumps(validation,indent=2))
 if status!="PASS":raise SystemExit(1)
if __name__=="__main__":main()
