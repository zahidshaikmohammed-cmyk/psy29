"""PSY29 Step 6: discover repeatable intraday edge-event behaviour.

This stage describes recurring intraday event patterns. It does not select the
final 29 and does not use future/live information.
"""
from __future__ import annotations
import argparse, json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd

START = pd.Timestamp("09:15:00").time()
END = pd.Timestamp("15:30:00").time()

def session_events(path: Path) -> list[dict]:
    df = pd.read_parquet(path)
    if "timestamp" not in df.columns:
        raise RuntimeError("missing timestamp")
    ts = pd.to_datetime(df["timestamp"], unit="s", errors="coerce", utc=True) if pd.api.types.is_numeric_dtype(df["timestamp"]) else pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
    df = df.assign(ts=ts.dt.tz_convert("Asia/Kolkata")).dropna(subset=["ts"]).sort_values("ts")
    t = df.ts.dt.time
    df = df[(t >= START) & (t < END)].copy()
    if df.empty:
        return []
    for c in ["open","high","low","close","volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["open","high","low","close"])
    df["date"] = df.ts.dt.date
    out=[]
    for d,g in df.groupby("date", sort=True):
        g=g.sort_values("ts").copy()
        if len(g)<30: continue
        o=float(g.open.iloc[0]); c=float(g.close.iloc[-1]); h=float(g.high.max()); l=float(g.low.min())
        r=g.close.pct_change(); path=float(r.abs().sum()); net=(c-o)/o if o else np.nan
        eff=abs(net)/(path+1e-12)
        same=(np.sign(g.close.diff()).replace(0,np.nan).ffill().diff().fillna(0)!=0).mean()
        # Opening range: first 15 one-minute bars.
        op=g.iloc[:15]; orh=float(op.high.max()); orl=float(op.low.min()); ormid=(orh+orl)/2
        after=g.iloc[15:]
        up_break=bool((after.high>orh).any()) if len(after) else False
        down_break=bool((after.low<orl).any()) if len(after) else False
        final_or_dir = 1 if c>orh else (-1 if c<orl else 0)
        # A continuation event requires an OR break and a close beyond that same side.
        or_cont = (c>orh and up_break) or (c<orl and down_break)
        # Range expansion compares the second half's median bar range with the opening range bars.
        bar_range=(g.high-g.low)/g.open.replace(0,np.nan)
        base=float(bar_range.iloc[:15].median()) if len(op) else np.nan
        later=float(bar_range.iloc[15:].median()) if len(after) else np.nan
        expansion=bool(later >= 1.5*base) if np.isfinite(base) and base>0 and np.isfinite(later) else False
        out.append({
            "symbol":path.stem,"date":str(d),"day_return":net,"day_abs_return":abs(net),
            "day_range_pct":(h-l)/o if o else np.nan,"directional_efficiency":eff,
            "direction_switch_rate":float(same),"opening_range_pct":(orh-orl)/o if o else np.nan,
            "or_up_break":up_break,"or_down_break":down_break,"or_continuation":bool(or_cont),
            "range_expansion":expansion,"final_or_direction":final_or_dir,
            "volume":float(g.volume.fillna(0).sum())
        })
    return out

def summarize(events: pd.DataFrame) -> pd.DataFrame:
    rows=[]
    for sym,g in events.groupby("symbol",sort=True):
        def rate(col): return float(g[col].mean())
        def med(col): return float(g[col].median())
        trend=((g.day_abs_return>=0.0075)&(g.directional_efficiency>=0.15))
        strong=((g.day_abs_return>=0.01)&(g.directional_efficiency>=0.25))
        low_chop=(g.direction_switch_rate<=0.10)
        rows.append({"symbol":sym,"sessions":len(g),
            "trend_event_rate":float(trend.mean()),"strong_trend_event_rate":float(strong.mean()),
            "or_continuation_rate":rate("or_continuation"),"range_expansion_rate":rate("range_expansion"),
            "low_chop_rate":float(low_chop.mean()),"or_up_break_rate":rate("or_up_break"),
            "or_down_break_rate":rate("or_down_break"),"median_event_return":med("day_abs_return"),
            "median_efficiency":med("directional_efficiency"),"median_range_pct":med("day_range_pct"),
            "median_switch_rate":med("direction_switch_rate"),"median_opening_range_pct":med("opening_range_pct"),
            "event_consistency":float(np.mean([trend.mean(),strong.mean(),g.or_continuation.mean(),g.range_expansion.mean(),low_chop.mean()]))})
    return pd.DataFrame(rows)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--input",default="input/data/raw/intraday"); ap.add_argument("--output",default="output/step6"); a=ap.parse_args()
    root,out=Path(a.input),Path(a.output); out.mkdir(parents=True,exist_ok=True)
    files=sorted(root.rglob("*.parquet"))
    if not files: raise RuntimeError("No parquet files found")
    all_events=[]; errors=[]
    for i,p in enumerate(files,1):
        try:
            ev=session_events(p); all_events.extend(ev); print(f"[{i}/{len(files)}] {p.stem} sessions={len(ev)}")
        except Exception as e: errors.append({"symbol":p.stem,"error":str(e)}); print(f"FAILED {p.stem}: {e}")
    if not all_events: raise RuntimeError("No intraday events generated")
    edf=pd.DataFrame(all_events); s=summarize(edf)
    edf.to_csv(out/"edge_events_by_session.csv",index=False); s.to_csv(out/"stock_edge_event_summary.csv",index=False)
    # Research ranking only: explicitly not the final 29.
    s.sort_values(["event_consistency","trend_event_rate","or_continuation_rate"],ascending=False).to_csv(out/"edge_event_research_ranking.csv",index=False)
    summary={"project":"PSY29","step":6,"version":"1.0","generated_at_utc":datetime.now(timezone.utc).isoformat(),"stocks_input":len(files),"stocks_with_events":int(s.symbol.nunique()),"sessions_analyzed":int(len(edf)),"errors":len(errors),"errors_detail":errors,"event_definitions":{"trend":"abs(day return)>=0.75% AND efficiency>=15%","strong_trend":"abs(day return)>=1% AND efficiency>=25%","opening_range_continuation":"post-15m OR break followed by close beyond same OR side","range_expansion":"median later bar range >=1.5x first-15m median","low_chop":"direction switch rate<=10%"},"final_selection_performed":False,"status":"PASS" if not errors else "PASS_WITH_ERRORS"}
    (out/"step6_summary.json").write_text(json.dumps(summary,indent=2)); print(json.dumps(summary,indent=2))
if __name__=="__main__": main()
