#!/usr/bin/env python3
"""Create an explicit deterministic PSY29 pipeline fixture for off-market validation."""
from __future__ import annotations
import argparse,csv,json
from datetime import datetime,timezone
from pathlib import Path
FIXTURE_TIMESTAMP="2026-01-02T10:00:00+05:30"
def main()->None:
    p=argparse.ArgumentParser();p.add_argument("--universe",required=True,type=Path);p.add_argument("--output",required=True,type=Path);a=p.parse_args();universe=json.loads(a.universe.read_text(encoding="utf-8"));rows=universe.get("universe",[]);symbols=[str(x["symbol"]).strip().upper() for x in rows]
    if len(symbols)!=29 or len(set(symbols))!=29:raise ValueError("canonical universe must be exactly 29 unique symbols")
    a.output.mkdir(parents=True,exist_ok=True);snapshot_path=a.output/"live_snapshot.csv";execution_path=a.output/"execution_snapshot.csv"
    snapshot_fields=["symbol","timestamp","open","high","low","close","volume","last_price","vwap","ema9","ema20","first15_high","first15_low","security_id","exchange_segment","freshness_status"]
    execution_fields=["symbol","timestamp","open_1m","high_1m","low_1m","close_1m","volume_1m","avg_volume_20_1m","open_5m","high_5m","low_5m","close_5m","volume_5m","avg_volume_20_5m","vwap_5m","ema9_5m","ema20_5m","first15_high","first15_low","swing_high","swing_low","last_price","vwap","ema9","ema20","security_id","exchange_segment","freshness_status"]
    with snapshot_path.open("w",newline="",encoding="utf-8") as fh,execution_path.open("w",newline="",encoding="utf-8") as efh:
        writer=csv.DictWriter(fh,fieldnames=snapshot_fields);execution_writer=csv.DictWriter(efh,fieldnames=execution_fields);writer.writeheader();execution_writer.writeheader()
        for rank,symbol in enumerate(symbols,start=1):
            base=1000.0+rank*10.0;last=base+2.0;first_high=base+5.0;first_low=base-4.0;swing_high=base+8.0;swing_low=base-6.0;common={"symbol":symbol,"timestamp":FIXTURE_TIMESTAMP,"security_id":f"FIXTURE-{rank:02d}","exchange_segment":"NSE_EQ","freshness_status":"FIXTURE"}
            writer.writerow({**common,"open":base,"high":swing_high,"low":swing_low,"close":last,"volume":100000+rank*1000,"last_price":last,"vwap":base+1.5,"ema9":base+1.8,"ema20":base+1.0,"first15_high":first_high,"first15_low":first_low})
            execution_writer.writerow({**common,"open_1m":base,"high_1m":base+3.0,"low_1m":base-2.0,"close_1m":last,"volume_1m":100000+rank*1000,"avg_volume_20_1m":90000+rank*500,"open_5m":base,"high_5m":swing_high,"low_5m":swing_low,"close_5m":last,"volume_5m":500000+rank*5000,"avg_volume_20_5m":450000+rank*2500,"vwap_5m":base+1.5,"ema9_5m":base+1.8,"ema20_5m":base+1.0,"first15_high":first_high,"first15_low":first_low,"swing_high":swing_high,"swing_low":swing_low,"last_price":last,"vwap":base+1.5,"ema9":base+1.8,"ema20":base+1.0})
    validation={"contract":"PSY29_DETERMINISTIC_PIPELINE_FIXTURE","status":"PASS","generated_at":datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z"),"source":"PSY29 deterministic fixture","live_data":False,"provider":"DETERMINISTIC_FIXTURE","coverage":{"expected":29,"actual":29,"unique":29},"fixture_count":29,"signal_generation":False,"order_execution":False};(a.output/"live_acquisition_validation.json").write_text(json.dumps(validation,indent=2),encoding="utf-8");print(json.dumps(validation,indent=2))
if __name__=="__main__":main()
