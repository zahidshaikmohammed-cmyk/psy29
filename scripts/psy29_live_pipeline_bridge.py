#!/usr/bin/env python3
"""PSY29-only live pipeline bridge.

Consumes the validated live acquisition snapshot and prepares a canonical
live-input bundle for the existing Stage 5-19 -> Stage 20 pipeline.
This bridge never generates orders or executes trades.
"""
from __future__ import annotations
import argparse, json
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd

REQUIRED = {
    "symbol","timestamp","last_price","vwap","ema9","ema20",
    "first15_high","first15_low","security_id","exchange_segment"
}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--snapshot",required=True,type=Path)
    p.add_argument("--validation",required=True,type=Path)
    p.add_argument("--universe",required=True,type=Path)
    p.add_argument("--output",required=True,type=Path)
    a=p.parse_args()
    validation=json.loads(a.validation.read_text(encoding="utf-8"))
    if validation.get("status") != "PASS": raise ValueError("live acquisition validation is not PASS")
    u=json.loads(a.universe.read_text(encoding="utf-8"))
    symbols=[str(x["symbol"]).strip().upper() for x in u.get("universe",[])]
    if len(symbols)!=29 or len(set(symbols))!=29: raise ValueError("canonical universe must be exactly 29 unique symbols")
    df=pd.read_csv(a.snapshot)
    if set(df.columns)<REQUIRED: raise ValueError("live snapshot missing required fields")
    actual=df["symbol"].astype(str).str.upper().tolist()
    if len(actual)!=29 or len(set(actual))!=29 or set(actual)!=set(symbols): raise ValueError("live snapshot 29/29 coverage mismatch")
    if not (df["freshness_status"].astype(str).str.upper()=="FRESH").all(): raise ValueError("live snapshot contains non-fresh rows")
    if df["security_id"].astype(str).eq("").any(): raise ValueError("missing security id")
    out=a.output; out.mkdir(parents=True,exist_ok=True)
    generated=datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z")
    df=df.sort_values("symbol").reset_index(drop=True)
    df.to_csv(out/"live_pipeline_input.csv",index=False)
    manifest={"contract":"PSY29_LIVE_PIPELINE_INPUT","status":"PASS","generated_at":generated,"source":"PSY29 live_snapshot.csv","coverage":{"expected":29,"actual":29,"unique":29},"fresh_count":29,"signal_generation":False,"order_execution":False}
    (out/"live_pipeline_input_validation.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    print(json.dumps(manifest,indent=2))

if __name__=="__main__":
    main()
