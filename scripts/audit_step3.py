"""PSY29 Step 3: data-quality and survivorship-control audit."""
from __future__ import annotations
import argparse, json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd

REQUIRED = ["security_id", "timestamp", "open", "high", "low", "close", "volume"]

def parse_ts(s):
    n = pd.to_numeric(s, errors="coerce")
    if n.notna().sum() == 0:
        return pd.to_datetime(s, errors="coerce", utc=True).dt.tz_convert("Asia/Kolkata")
    unit = "ms" if float(n.dropna().abs().median()) > 1e12 else "s"
    return pd.to_datetime(n, unit=unit, errors="coerce", utc=True).dt.tz_convert("Asia/Kolkata")

def audit(path):
    r={"symbol":path.stem,"rows":0,"schema_ok":False,"null_cells":0,"invalid_timestamp":0,"duplicate_timestamps":0,"non_monotonic_steps":0,"out_of_session_rows":0,"invalid_ohlc_rows":0,"negative_volume_rows":0,"sessions":0,"missing_minute_gaps":0,"status":"FAIL","issues":[]}
    try: df=pd.read_parquet(path)
    except Exception as e: r["issues"].append(f"PARQUET_READ_ERROR: {e}"); return r
    r["rows"]=len(df); missing=[c for c in REQUIRED if c not in df.columns]
    if missing: r["issues"].append("MISSING_COLUMNS: "+",".join(missing)); return r
    r["schema_ok"]=True; r["null_cells"]=int(df[REQUIRED].isna().sum().sum())
    ts=parse_ts(df.timestamp); r["invalid_timestamp"]=int(ts.isna().sum())
    valid=ts.notna()
    if valid.any():
        clean=ts[valid]; r["duplicate_timestamps"]=int(clean.duplicated().sum()); r["non_monotonic_steps"]=int((clean.diff().dropna().dt.total_seconds()<0).sum())
        ins=(clean.dt.time>=pd.Timestamp("09:15:00").time())&(clean.dt.time<pd.Timestamp("15:30:00").time()); r["out_of_session_rows"]=int((~ins).sum()); sess=clean[ins]; dates=sess.dt.date; r["sessions"]=int(pd.Series(dates).nunique())
        if len(sess):
            gaps=pd.DataFrame({"ts":sess,"d":dates}).sort_values("ts").groupby("d")["ts"].diff().dt.total_seconds().div(60).dropna(); r["missing_minute_gaps"]=int((gaps>1).sum())
    x=df[["open","high","low","close","volume"]].apply(pd.to_numeric,errors="coerce"); o,h,l,c,v=(x[z] for z in ["open","high","low","close","volume"])
    bad=(h<np.maximum(o,c))|(l>np.minimum(o,c))|(h<l)|(o<=0)|(h<=0)|(l<=0)|(c<=0); r["invalid_ohlc_rows"]=int(bad.fillna(True).sum()); r["negative_volume_rows"]=int((v<0).fillna(True).sum())
    if r["null_cells"]: r["issues"].append(f"NULL_CELLS: {r['null_cells']}")
    if r["invalid_timestamp"]: r["issues"].append(f"INVALID_TIMESTAMP: {r['invalid_timestamp']}")
    if r["duplicate_timestamps"]: r["issues"].append(f"DUPLICATE_TIMESTAMPS: {r['duplicate_timestamps']}")
    if r["non_monotonic_steps"]: r["issues"].append(f"NON_MONOTONIC: {r['non_monotonic_steps']}")
    if r["out_of_session_rows"]: r["issues"].append(f"OUT_OF_SESSION_ROWS: {r['out_of_session_rows']}")
    if r["invalid_ohlc_rows"]: r["issues"].append(f"INVALID_OHLC: {r['invalid_ohlc_rows']}")
    if r["negative_volume_rows"]: r["issues"].append(f"NEGATIVE_VOLUME: {r['negative_volume_rows']}")
    hard=(not r["schema_ok"] or r["rows"]==0 or r["null_cells"]>0 or r["invalid_timestamp"]>0 or r["duplicate_timestamps"]>0 or r["invalid_ohlc_rows"]>0 or r["negative_volume_rows"]>0 or r["sessions"]<10)
    r["status"]="FAIL" if hard else "PASS"; return r

def main():
    p=argparse.ArgumentParser(); p.add_argument("--input",default="input/data/raw/intraday"); p.add_argument("--output",default="output/step3"); a=p.parse_args(); root,out=Path(a.input),Path(a.output); out.mkdir(parents=True,exist_ok=True)
    files=sorted(root.glob("*.parquet"));
    if not files: raise RuntimeError(f"No parquet files found under {root}")
    rep=pd.DataFrame([audit(x) for x in files]); rep["issues"]=rep["issues"].apply(lambda x:" | ".join(x)); rep.to_csv(out/"symbol_quality_report.csv",index=False); fail=int((rep.status=="FAIL").sum()); passed=int((rep.status=="PASS").sum())
    summary={"project":"PSY29","step":3,"audited_at_utc":datetime.now(timezone.utc).isoformat(),"files_found":len(files),"quality_pass":passed,"quality_fail":fail,"raw_data_modified":False,"survivorship_control":{"status":"LIMITED","reason":"Universe is based on the current Dhan FUTSTK master; historical F&O membership snapshots were not part of Step 2.","action_required_before_final_selection":True},"step3_status":"PASS_WITH_SURVIVORSHIP_LIMITATION" if fail==0 else "FAIL"}
    (out/"step3_summary.json").write_text(json.dumps(summary,indent=2)); print(json.dumps(summary,indent=2));
    if fail: raise SystemExit(1)
if __name__=="__main__": main()
