#!/usr/bin/env python3
"""Capture the PSY29 1-minute DHAN candles from NSE open through 09:29 IST.

After 09:30 the validated PSY29 pipeline is the single acquisition source; this
worker stops to avoid duplicate DHAN requests.
"""
from __future__ import annotations
import time
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
from dhan.client import DhanClient
from psy29_live_archive import store_rows
from psy29_live_dhan_acquisition import load_universe, resolve_security_ids, fetch_bars, completed_candles, epoch_to_ist, IST, SESSION_OPEN, SESSION_CLOSE, OPENING_RANGE_END
ROOT = Path(__file__).resolve().parents[1]
UNIVERSE = ROOT / "config/canonical_universe.json"

def make_rows(symbol, sid, raw, now):
    x = completed_candles(raw, 1, now)
    if x.empty: return []
    session = x[(x.dt.dt.date == now.date()) & (x.dt.dt.time >= SESSION_OPEN) & (x.dt.dt.time <= SESSION_CLOSE)].copy()
    if session.empty: return []
    typ = (session.high + session.low + session.close) / 3.0
    vol = session.volume.clip(lower=0)
    session["vwap"] = (typ * vol).cumsum() / vol.cumsum().replace(0, pd.NA)
    session["ema9"] = session.close.ewm(span=9, adjust=False).mean()
    session["ema20"] = session.close.ewm(span=20, adjust=False).mean()
    latest = session.iloc[-1]
    opening = session[session.dt.dt.time < OPENING_RANGE_END]
    first15_high = float(opening.high.max()) if len(opening) >= 15 else None
    first15_low = float(opening.low.min()) if len(opening) >= 15 else None
    s5 = session.copy()
    mins = s5.dt.dt.hour * 60 + s5.dt.dt.minute
    s5["bucket"] = ((mins - 555) // 5) * 5 + 555
    g = s5.groupby("bucket", sort=True)
    bars = g.agg(open=("open","first"), high=("high","max"), low=("low","min"), close=("close","last"), volume=("volume","sum"))
    bars = bars[g.size() == 5]
    open5 = high5 = low5 = close5 = volume5 = vwap5 = ema9_5 = ema20_5 = None
    if not bars.empty:
        typ5 = (bars.high + bars.low + bars.close) / 3.0
        bars["vwap5"] = (typ5 * bars.volume).cumsum() / bars.volume.cumsum().replace(0, pd.NA)
        bars["ema9"] = bars.close.ewm(span=9, adjust=False).mean()
        bars["ema20"] = bars.close.ewm(span=20, adjust=False).mean()
        b = bars.iloc[-1]
        open5, high5, low5, close5, volume5 = map(float, (b.open,b.high,b.low,b.close,b.volume))
        vwap5, ema9_5, ema20_5 = (float(b[c]) for c in ("vwap5","ema9","ema20"))
    minute_ts = epoch_to_ist(int(latest.timestamp)).replace(second=0, microsecond=0)
    ts = minute_ts.astimezone(timezone.utc).isoformat().replace("+00:00","Z")
    return [{"session_date":str(now.date()),"minute_ts":ts,"symbol":symbol,"security_id":str(sid),"provider":"DHAN","market_data_kind":"LIVE_DHAN_MINUTE_ARCHIVE","timestamp":ts,"open_1m":float(latest.open),"high_1m":float(latest.high),"low_1m":float(latest.low),"close_1m":float(latest.close),"volume_1m":float(latest.volume),"open_5m":open5,"high_5m":high5,"low_5m":low5,"close_5m":close5,"volume_5m":volume5,"vwap_5m":vwap5,"ema9_5m":ema9_5,"ema20_5m":ema20_5,"vwap_1m":float(latest.vwap),"ema9_1m":float(latest.ema9),"ema20_1m":float(latest.ema20),"first15_high":first15_high,"first15_low":first15_low,"freshness_status":"FRESH","opening_range_complete":len(opening)>=15}]

def main():
    symbols = load_universe(UNIVERSE); mapping = resolve_security_ids(symbols); client = DhanClient()
    while True:
        now = datetime.now(IST)
        if now.weekday() < 5 and SESSION_OPEN <= now.time() < OPENING_RANGE_END:
            rows=[]
            for symbol in symbols:
                try: rows.extend(make_rows(symbol,mapping[symbol],fetch_bars(client,mapping[symbol],now,"1"),now))
                except Exception as exc: print(f"PREOPEN_ARCHIVE {symbol}: {exc}",flush=True)
            if rows:
                try: print(f"PREOPEN_ARCHIVE STORED {store_rows(rows)}/{len(symbols)} at {now.isoformat()}",flush=True)
                except Exception as exc: print(f"PREOPEN_ARCHIVE DB ERROR: {exc}",flush=True)
            time.sleep(max(1,61-datetime.now(IST).second))
        elif now.time() >= OPENING_RANGE_END or now.time() >= SESSION_CLOSE:
            return
        else:
            time.sleep(10)
if __name__ == "__main__": main()
