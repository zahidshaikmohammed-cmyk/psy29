#!/usr/bin/env python3
"""Research-only canonical PSY29 60/20/20 threshold generator."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
import numpy as np
import pandas as pd

CANONICAL_COMMIT = "988472889edfd51046731d72f68f2e96e095a2f1"
DATASET_RUN_ID = "31702235542"
TRAIN, TEST, STEP = 60, 20, 20
UNIVERSE = ["NESTLEIND","VEDL","ICICIPRULI","KALYANKJIL","KOTAKBANK","BANDHANBNK","BANKBARODA","TITAN","INFY","DLF","TCS","MAXHEALTH","KFINTECH","PRESTIGE","BHEL","RBLBANK","HCLTECH","ICICIGI","HDFCLIFE","MARICO","LUPIN","COFORGE","TECHM","SWIGGY","PERSISTENT","OBEROIRLTY","SUPREMEIND","LAURUSLABS","AMBUJACEM"]

def q(values, p):
    s = pd.Series(values, dtype=float).dropna()
    if s.empty: raise ValueError("empty threshold population")
    return float(s.quantile(p))

def session_metrics(g):
    g = g.sort_values("ts").copy()
    if len(g) < 15: return None
    op = float(g.iloc[0].open); cl = float(g.iloc[-1].close)
    abs_ret = abs(cl - op) / op if op else np.nan
    rets = g.close.pct_change().fillna(0.0)
    denom = float(rets.abs().sum()); eff = abs_ret / denom if denom > 0 else 0.0
    or15 = g.iloc[:15]; or_high = float(or15.high.max()); or_low = float(or15.low.min())
    or_pct = (or_high - or_low) / op if op else np.nan
    rem = g.iloc[15:]
    if rem.empty: ext = 0.0
    else:
        up = rem.loc[rem.high > or_high, "close"]; dn = rem.loc[rem.low < or_low, "close"]
        up_ext = float(((up - or_high) / op).max()) if len(up) else 0.0
        dn_ext = float(((or_low - dn) / op).max()) if len(dn) else 0.0
        ext = max(up_ext, dn_ext)
    return {"day_abs_return":abs_ret,"directional_efficiency":eff,"opening_range_pct":or_pct,"breakout_extension_pct":ext}

def load(data_dir):
    files = sorted(data_dir.rglob("*.parquet"))
    if not files: raise RuntimeError("No parquet files found")
    out=[]
    for p in files:
        df=pd.read_parquet(p); low={c.lower():c for c in df.columns}
        req={"symbol","timestamp","open","high","low","close"}
        if not req.issubset(low): continue
        df=df.rename(columns={low[k]:k for k in req}); df.symbol=df.symbol.astype(str).str.upper(); df=df[df.symbol.isin(UNIVERSE)].copy()
        if df.empty: continue
        df["ts"]=pd.to_datetime(df.timestamp,utc=True).dt.tz_convert("Asia/Kolkata")
        mins=df.ts.dt.hour*60+df.ts.dt.minute; df=df[(mins>=555)&(mins<=930)]
        out.append(df[["symbol","ts","open","high","low","close"]])
    if not out: raise RuntimeError("No canonical 29-stock rows found")
    return pd.concat(out,ignore_index=True).drop_duplicates(["symbol","ts"]).sort_values(["symbol","ts"])

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--data-dir",required=True); ap.add_argument("--out",required=True); ap.add_argument("--validation",required=True); a=ap.parse_args()
    df=load(Path(a.data_dir)); sessions={s:[] for s in UNIVERSE}
    for (sym,day),g in df.groupby(["symbol",df.ts.dt.date],sort=True):
        m=session_metrics(g)
        if m is not None: sessions[sym].append((pd.Timestamp(day),m))
    errors=[]; rows=[]; uh=hashlib.sha256("\n".join(UNIVERSE).encode()).hexdigest()
    for sym in UNIVERSE:
        ss=sessions[sym]
        if len(ss)<80: errors.append(f"{sym}: fewer than 80 sessions"); continue
        for start in range(0,len(ss)-TRAIN-TEST+1,STEP):
            train=ss[start:start+TRAIN]; test=ss[start+TRAIN:start+TRAIN+TEST]
            if len(train)!=60 or len(test)!=20: errors.append(f"{sym}: bad window length"); continue
            tr=[x[1] for x in train]; eff=test[0][0].date(); train_end=train[-1][0].date()
            if not train_end < eff: errors.append(f"{sym}: lookahead window")
            vals={"r75":q([x["day_abs_return"] for x in tr],.75),"r85":q([x["day_abs_return"] for x in tr],.85),"e60":q([x["directional_efficiency"] for x in tr],.60),"e75":q([x["directional_efficiency"] for x in tr],.75),"or75":q([x["opening_range_pct"] for x in tr],.75),"ext60":q([x["breakout_extension_pct"] for x in tr],.60)}
            if not all(np.isfinite(v) for v in vals.values()): errors.append(f"{sym}/{eff}: non-finite threshold")
            rows.append({"threshold_set_id":f"PSY29-EVD-V2|{uh[:12]}|{train[0][0].date()}|{train_end}","effective_nse_session_date":eff.isoformat(),"training_window":{"start":train[0][0].date().isoformat(),"end":train_end.isoformat(),"session_count":60},"oos_window":{"start":eff.isoformat(),"end":test[-1][0].date().isoformat(),"session_count":20},"stock":sym,"thresholds":vals,"hard_earliest_offset":{"Trend":0,"Strong Trend":0,"OR Continuation":15}})
    if errors: raise RuntimeError("VALIDATION FAILED: "+"; ".join(errors[:20]))
    artifact={"schema":"PSY29_EVENT_DETECTOR_THRESHOLDS_V2","artifact_type":"walk_forward_session_keyed","methodology":{"train_sessions":60,"test_sessions":20,"step_sessions":20,"timezone":"Asia/Kolkata"},"research_source":{"repository":"zahidshaikmohammed-cmyk/psy29","path":"research/event_time_discovery.py","commit":CANONICAL_COMMIT},"dataset_provenance":{"workflow_run_id":DATASET_RUN_ID},"universe":{"count":29,"symbols":UNIVERSE,"sha256":uh},"threshold_set_count":len(rows),"threshold_sets":rows}
    out=Path(a.out); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(artifact,indent=2,sort_keys=True),encoding="utf-8")
    Path(a.validation).write_text(json.dumps({"status":"PASS","threshold_set_count":len(rows),"stock_count":29,"canonical_commit":CANONICAL_COMMIT,"dataset_run_id":DATASET_RUN_ID},indent=2),encoding="utf-8")

if __name__ == "__main__": main()
