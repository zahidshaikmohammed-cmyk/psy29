from __future__ import annotations

import argparse
from pathlib import Path
import json
import math
import numpy as np
import pandas as pd

START = "09:15:00"
END = "15:30:00"
TRAIN, TEST, STEP = 60, 20, 20
BUCKETS = [("before_1430", "09:15", "14:30"), ("1430_1445", "14:30", "14:45"), ("1445_1500", "14:45", "15:00"), ("after_1500", "15:00", "15:30")]
HORIZONS = [5, 15, 30, 60]
SYMBOLS = ["NESTLEIND","VEDL","ICICIPRULI","KALYANKJIL","KOTAKBANK","BANDHANBNK","BANKBARODA","TITAN","INFY","DLF","TCS","MAXHEALTH","KFINTECH","PRESTIGE","BHEL","RBLBANK","HCLTECH","ICICIGI","HDFCLIFE","MARICO","LUPIN","COFORGE","TECHM","SWIGGY","PERSISTENT","OBEROIRLTY","SUPREMEIND","LAURUSLABS","AMBUJACEM"]
EXPECTED = {
"NESTLEIND":(26,17,29),"VEDL":(25,14,25),"ICICIPRULI":(28,16,31),"KALYANKJIL":(23,17,30),"KOTAKBANK":(26,13,29),"BANDHANBNK":(25,15,29),"BANKBARODA":(22,11,33),"TITAN":(26,13,30),"INFY":(22,16,29),"DLF":(24,11,32),"TCS":(26,18,21),"MAXHEALTH":(22,15,30),"KFINTECH":(23,12,34),"PRESTIGE":(20,13,35),"BHEL":(23,17,27),"RBLBANK":(25,15,25),"HCLTECH":(23,15,28),"ICICIGI":(22,15,30),"HDFCLIFE":(21,15,28),"MARICO":(20,15,29),"LUPIN":(24,14,25),"COFORGE":(20,14,33),"TECHM":(23,17,24),"SWIGGY":(23,13,27),"PERSISTENT":(21,12,32),"OBEROIRLTY":(26,13,30),"SUPREMEIND":(24,12,32),"LAURUSLABS":(20,13,31),"AMBUJACEM":(19,11,32)}


def q(s, p, fallback=np.nan):
    s = pd.to_numeric(s, errors="coerce").dropna()
    return float(s.quantile(p)) if len(s) else float(fallback)


def load(path):
    df = pd.read_parquet(path)
    need = ["timestamp","open","high","low","close","volume"]
    miss=[c for c in need if c not in df.columns]
    if miss: raise RuntimeError(f"{path.name}: missing {miss}")
    ts=df["timestamp"]
    if pd.api.types.is_numeric_dtype(ts): ts=pd.to_datetime(ts,unit="s",errors="coerce",utc=True)
    else: ts=pd.to_datetime(ts,errors="coerce",utc=True)
    df=df.copy(); df["ts"]=ts.dt.tz_convert("Asia/Kolkata")
    df=df.dropna(subset=["ts"]).sort_values("ts")
    t=df["ts"].dt.time
    df=df[(t>=pd.Timestamp(START).time())&(t<pd.Timestamp(END).time())].copy()
    for c in ["open","high","low","close","volume"]: df[c]=pd.to_numeric(df[c],errors="coerce")
    return df.dropna(subset=["open","high","low","close"])


def session_features(df):
    out=[]
    for d,g in df.groupby(df["ts"].dt.date,sort=True):
        g=g.sort_values("ts").reset_index(drop=True)
        if len(g)<30: continue
        op=float(g.open.iloc[0]); cl=float(g.close.iloc[-1])
        if op==0: continue
        dr=(cl-op)/op; absr=abs(dr)
        mr=g.close.pct_change().dropna(); path=float(mr.abs().sum()); eff=absr/(path+1e-12)
        direction=np.sign(g.close.diff()).replace(0,np.nan).ffill().dropna()
        switch=float(direction.diff().ne(0).mean()) if len(direction)>1 else np.nan
        o=g.iloc[:15]; rem=g.iloc[15:]
        orh=float(o.high.max()); orl=float(o.low.min()); orpct=(orh-orl)/op
        broke_up=bool((rem.high>orh).any()); broke_dn=bool((rem.low<orl).any())
        orcont=bool((broke_up and cl>orh) or (broke_dn and cl<orl))
        ext=max((cl-orh)/op,(orl-cl)/op,0.0)
        br=(g.high-g.low)/g.open.replace(0,np.nan)
        fr=float(br.iloc[:15].median()); lr=float(br.iloc[15:].median()) if len(rem) else np.nan
        expansion=lr/fr if np.isfinite(fr) and fr>0 and np.isfinite(lr) else np.nan
        out.append({"date":str(d),"group":g,"day_abs_return":absr,"directional_efficiency":eff,"direction_switch_rate":switch,"opening_range_pct":orpct,"opening_range_continuation":orcont,"breakout_extension_pct":ext,"range_expansion_ratio":expansion})
    return out


def thresholds(train):
    return {"rq75":q(train.day_abs_return,.75),"rq85":q(train.day_abs_return,.85),"eq60":q(train.directional_efficiency,.60),"eq75":q(train.directional_efficiency,.75),"orq75":q(train.opening_range_pct,.75),"extq60":q(train.breakout_extension_pct,.60,0.0)}


def detect_session(rec, th):
    g=rec["group"]; op=float(g.open.iloc[0]); closes=g.close.to_numpy(); highs=g.high.to_numpy(); lows=g.low.to_numpy(); times=g.ts.to_numpy()
    # Partial-session trend/strong trend: only information available through current bar.
    path=0.0
    prev=closes[0]
    trend_at=strong_at=or_at=None; trend_dir=strong_dir=or_dir=None
    for i in range(1,len(g)):
        path += abs((closes[i]-prev)/(prev if prev else np.nan)); prev=closes[i]
        absr=abs((closes[i]-op)/op) if op else np.nan
        eff=absr/(path+1e-12)
        if trend_at is None and absr>=th["rq75"] and eff>=th["eq60"]:
            trend_at=pd.Timestamp(times[i]); trend_dir="LONG" if closes[i]>=op else "SHORT"
        if strong_at is None and absr>=th["rq85"] and eff>=th["eq75"]:
            strong_at=pd.Timestamp(times[i]); strong_dir="LONG" if closes[i]>=op else "SHORT"
        # OR is only eligible after first 15 completed bars; require a close beyond OR plus extension threshold.
        if i>=15 and or_at is None:
            orh=float(highs[:15].max()); orl=float(lows[:15].min()); orpct=(orh-orl)/op
            up=(highs[15:i+1]>orh).any(); dn=(lows[15:i+1]<orl).any()
            ext=max((closes[i]-orh)/op,(orl-closes[i])/op,0.0)
            if ((up and closes[i]>orh) or (dn and closes[i]<orl)) and orpct<=th["orq75"] and ext>=th["extq60"]:
                or_at=pd.Timestamp(times[i]); or_dir="LONG" if closes[i]>orh else "SHORT"
    return [("Trend",trend_at,trend_dir),("Strong Trend",strong_at,strong_dir),("OR Continuation",or_at,or_dir)]


def bucket(ts):
    t=ts.time();
    if t<pd.Timestamp("14:30").time(): return "before_1430"
    if t<pd.Timestamp("14:45").time(): return "1430_1445"
    if t<pd.Timestamp("15:00").time(): return "1445_1500"
    return "after_1500"


def event_metrics(g, ts, direction):
    idx=int(g.index[g.ts.eq(ts)][0]) if (g.ts==ts).any() else int(np.searchsorted(g.ts.values, ts.to_datetime64()))
    entry=float(g.close.iloc[idx]); future=g.iloc[idx+1:].copy()
    remaining=max(0,(len(g)-1-idx))
    if entry<=0: return None
    sign=1 if direction=="LONG" else -1
    mfe=float((future.high/entry-1).max()) if direction=="LONG" and len(future) else float((1-future.low/entry).max()) if len(future) else np.nan
    mae=float((future.low/entry-1).min()) if direction=="LONG" and len(future) else float((1-future.high/entry).min()) if len(future) else np.nan
    row={"entry_price":entry,"remaining_bars":remaining,"remaining_minutes":remaining,"mfe_to_close":mfe,"mae_to_close":mae}
    for h in HORIZONS:
        if idx+h < len(g):
            c=float(g.close.iloc[idx+h]); row[f"return_{h}m"]=(c/entry-1)*sign
        else: row[f"return_{h}m"]=np.nan
    if len(future):
        if direction=="LONG": fav=(future.high/entry-1); adv=(future.low/entry-1)
        else: fav=(1-future.low/entry); adv=(1-future.high/entry)
        row["time_to_mfe_min"]=float((future.ts.iloc[int(fav.argmax())]-ts).total_seconds()/60)
        row["time_to_mae_min"]=float((future.ts.iloc[int(adv.argmin())]-ts).total_seconds()/60)
        row["close_return"]=(float(future.close.iloc[-1])/entry-1)*sign
    else:
        row["time_to_mfe_min"]=np.nan; row["time_to_mae_min"]=np.nan; row["close_return"]=0.0
    row["win_close"]=bool(row["close_return"]>0)
    return row


def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--input",required=True); ap.add_argument("--summary",required=True); ap.add_argument("--output",required=True); args=ap.parse_args()
    root=Path(args.input); out=Path(args.output); out.mkdir(parents=True,exist_ok=True)
    summary=pd.read_csv(args.summary)
    # The completed study is stock/event-type level; validate its N against our reconstructed event counts.
    expected_summary={}
    for _,r in summary.iterrows(): expected_summary[(r["symbol"],r["event_type"])] = int(r["sample_count"])
    events=[]; validation=[]
    for sym in SYMBOLS:
        files=list(root.rglob(f"{sym}.parquet"))
        if not files: raise RuntimeError(f"Missing canonical parquet for {sym}")
        df=load(files[0]); sessions=session_features(df)
        if len(sessions)<80: raise RuntimeError(f"{sym}: insufficient sessions {len(sessions)}")
        # Same walk-forward segmentation as Step 6 V3: 60 train / 20 test / step 20.
        for start in range(0,len(sessions)-TRAIN-TEST+1,STEP):
            train=pd.DataFrame([{k:v for k,v in r.items() if k!="group"} for r in sessions[start:start+TRAIN]])
            test=sessions[start+TRAIN:start+TRAIN+TEST]
            th=thresholds(train)
            for rec in test:
                for et,ts,direction in detect_session(rec,th):
                    if ts is None: continue
                    m=event_metrics(rec["group"],ts,direction)
                    if m is None: continue
                    events.append({"symbol":sym,"date":rec["date"],"event_type":et,"detection_timestamp":ts.isoformat(),"bucket":bucket(ts),"direction":direction,**m})
        counts=pd.Series([e["event_type"] for e in events if e["symbol"]==sym]).value_counts().to_dict()
        for et, expected_et in [("Trend","Trend"),("Strong Trend","Strong Trend"),("OR Continuation","OR Continuation")]:
            key=(sym,et); exp=expected_summary.get(key)
            got=int(counts.get(et,0)); validation.append({"symbol":sym,"event_type":et,"expected_sample_count":exp,"observed_sample_count":got,"match":bool(exp==got)})
    ev=pd.DataFrame(events); val=pd.DataFrame(validation)
    if not val.match.all():
        bad=val[~val.match]; bad.to_csv(out/"sample_count_mismatches.csv",index=False); raise RuntimeError("Event-count validation failed")
    ev.to_csv(out/"event_level_expectancy.csv",index=False); val.to_csv(out/"sample_count_validation.csv",index=False)
    agg=[]
    for (b,et),g in ev.groupby(["bucket","event_type"]):
        row={"bucket":b,"event_type":et,"n":len(g)}
        for c in ["return_5m","return_15m","return_30m","return_60m","mfe_to_close","mae_to_close","time_to_mfe_min","time_to_mae_min","remaining_minutes","close_return"]:
            row[c+"_mean"]=float(g[c].mean()); row[c+"_median"]=float(g[c].median())
        row["win_rate_close"]=float(g.win_close.mean())
        agg.append(row)
    pd.DataFrame(agg).to_csv(out/"expectancy_by_bucket_event.csv",index=False)
    bystock=[]
    for (sym,b,et),g in ev.groupby(["symbol","bucket","event_type"]):
        bystock.append({"symbol":sym,"bucket":b,"event_type":et,"n":len(g),"median_return_30m":float(g.return_30m.median()),"median_close_return":float(g.close_return.median()),"median_mfe":float(g.mfe_to_close.median()),"median_mae":float(g.mae_to_close.median()),"median_remaining_minutes":float(g.remaining_minutes.median()),"win_rate_close":float(g.win_close.mean())})
    pd.DataFrame(bystock).to_csv(out/"expectancy_by_stock_bucket_event.csv",index=False)
    meta={"method":"non-hindsight first-detection outcome study","walk_forward":"60 train / 20 test / 20 step","symbols":len(SYMBOLS),"events":len(ev),"validation_pass":bool(val.match.all()),"horizons_minutes":HORIZONS,"buckets":[b[0] for b in BUCKETS],"source_event_summary":str(args.summary)}
    (out/"study_manifest.json").write_text(json.dumps(meta,indent=2))
    print(json.dumps(meta,indent=2))

if __name__=="__main__": main()
