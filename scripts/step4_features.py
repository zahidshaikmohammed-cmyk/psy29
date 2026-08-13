"""PSY29 Step 4: intraday behavioural feature engine."""
from __future__ import annotations
import argparse, json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd

START=pd.Timestamp("09:15:00").time(); END=pd.Timestamp("15:30:00").time()

def build(path: Path) -> dict:
    df=pd.read_parquet(path)
    raw=df["timestamp"]
    if pd.api.types.is_numeric_dtype(raw):
        ts=pd.to_datetime(raw,unit="s",errors="coerce",utc=True)
    else:
        ts=pd.to_datetime(raw,errors="coerce",utc=True)
    df=df.assign(ts=ts.dt.tz_convert("Asia/Kolkata")).dropna(subset=["ts"]).sort_values("ts")
    t=df.ts.dt.time; df=df[(t>=START)&(t<END)].copy()
    if df.empty: return {"symbol":path.stem,"sessions":0,"rows":0}
    df["date"]=df.ts.dt.date
    df["ret1"]=pd.to_numeric(df.close,errors="coerce").pct_change()
    days=[]
    for d,g in df.groupby("date",sort=True):
        o=float(g.open.iloc[0]); c=float(g.close.iloc[-1]); h=float(g.high.max()); l=float(g.low.min())
        pathlen=float(g.ret1.abs().sum()); net=(c-o)/o if o else np.nan
        days.append({"day_return":net,"range_pct":(h-l)/o if o else np.nan,"efficiency":abs(net)/(pathlen+1e-12),"volume":float(pd.to_numeric(g.volume,errors="coerce").fillna(0).sum()),"volatility":float(g.ret1.std()) if len(g)>1 else np.nan})
    x=pd.DataFrame(days)
    return {"symbol":path.stem,"sessions":len(x),"rows":len(df),"mean_abs_return":float(x.day_return.abs().mean()),"median_abs_return":float(x.day_return.abs().median()),"mean_range_pct":float(x.range_pct.mean()),"median_range_pct":float(x.range_pct.median()),"mean_directional_efficiency":float(x.efficiency.mean()),"median_directional_efficiency":float(x.efficiency.median()),"trend_day_rate_20pct":float((x.efficiency>=.20).mean()),"trend_day_rate_30pct":float((x.efficiency>=.30).mean()),"positive_day_rate":float((x.day_return>0).mean()),"negative_day_rate":float((x.day_return<0).mean()),"median_session_volume":float(x.volume.median()),"mean_1m_volatility":float(x.volatility.mean())}

def main():
    p=argparse.ArgumentParser(); p.add_argument('--input',default='input/data/raw/intraday'); p.add_argument('--output',default='output/step4'); a=p.parse_args()
    root,out=Path(a.input),Path(a.output); out.mkdir(parents=True,exist_ok=True); files=sorted(root.glob('*.parquet'))
    if not files: raise RuntimeError('No parquet files found')
    rows=[]; errors=[]
    for i,f in enumerate(files,1):
        try:
            r=build(f); rows.append(r); print(f'[{i}/{len(files)}] {f.stem} sessions={r["sessions"]}')
        except Exception as e:
            errors.append({'symbol':f.stem,'error':str(e)}); print(f'FAILED {f.stem}: {e}')
    pd.DataFrame(rows).to_csv(out/'stock_behaviour_features.csv',index=False)
    summary={'project':'PSY29','step':4,'generated_at_utc':datetime.now(timezone.utc).isoformat(),'files_found':len(files),'features_generated':len(rows),'errors':len(errors),'errors_detail':errors,'raw_data_modified':False,'status':'PASS' if not errors else 'PASS_WITH_ERRORS'}
    (out/'step4_summary.json').write_text(json.dumps(summary,indent=2)); print(json.dumps(summary,indent=2))
    if not rows: raise SystemExit(1)
if __name__=='__main__': main()
