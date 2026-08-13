"""PSY29 Step 9: live intraday regime / edge activation gate."""
import argparse, json
from pathlib import Path
import numpy as np
import pandas as pd


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--universe',required=True)
    p.add_argument('--snapshot',required=True)
    p.add_argument('--output',required=True)
    a=p.parse_args()
    out=Path(a.output); out.mkdir(parents=True,exist_ok=True)
    u=pd.read_csv(a.universe)
    if 'symbol' not in u or 'final_psy29' not in u:
        raise SystemExit('Step 8 artifact must contain symbol and final_psy29')
    u['symbol']=u.symbol.astype(str).str.upper().str.strip()
    u=u[u.final_psy29.astype(str).str.lower().isin(['true','1','yes','y','pass'])].copy()
    if len(u)!=29: raise SystemExit(f'Expected exactly 29 locked stocks, got {len(u)}')
    s=pd.read_csv(a.snapshot)
    if 'symbol' not in s: raise SystemExit('Live snapshot must contain symbol')
    s['symbol']=s.symbol.astype(str).str.upper().str.strip(); s=s.drop_duplicates('symbol',keep='last')
    r=u.merge(s,on='symbol',how='left',suffixes=('','_live'))
    def n(x): return pd.to_numeric(r[x],errors='coerce') if x in r else pd.Series(np.nan,index=r.index)
    px=n('last_price'); vw=n('vwap'); e9=n('ema9'); e20=n('ema20'); ph=n('first15_high'); pl=n('first15_low')
    r['above_vwap']=px.gt(vw); r['below_vwap']=px.lt(vw); r['ema9_above_ema20']=e9.gt(e20); r['ema9_below_ema20']=e9.lt(e20)
    r['orb_up']=px.gt(ph); r['orb_down']=px.lt(pl)
    r['bull_score']=r[['above_vwap','ema9_above_ema20']].sum(axis=1,min_count=1)
    r['bear_score']=r[['below_vwap','ema9_below_ema20']].sum(axis=1,min_count=1)
    r['regime']='UNKNOWN'
    r.loc[(r.bull_score>=2)&r.orb_up,'regime']='BULLISH_EDGE_ACTIVE'
    r.loc[(r.bear_score>=2)&r.orb_down,'regime']='BEARISH_EDGE_ACTIVE'
    r.loc[(r.bull_score>=2)&(r.regime=='UNKNOWN'),'regime']='BULLISH_ALIGNMENT'
    r.loc[(r.bear_score>=2)&(r.regime=='UNKNOWN'),'regime']='BEARISH_ALIGNMENT'
    r['live_edge_active']=r.regime.isin(['BULLISH_EDGE_ACTIVE','BEARISH_EDGE_ACTIVE'])
    r['live_qualified']=r.live_edge_active & (r[['above_vwap','below_vwap','ema9_above_ema20','ema9_below_ema20']].notna().sum(axis=1)>=2)
    r.to_csv(out/'PSY29_STEP9_LIVE_REGIME.csv',index=False)
    q=r[r.live_qualified].copy(); q.to_csv(out/'PSY29_STEP9_ACTIVE_EDGES.csv',index=False)
    summary={'step':9,'status':'PASS','universe_size':len(r),'snapshot_symbols_matched':int(px.notna().sum()),'active_edge_count':len(q),'bullish_edge_active':int((r.regime=='BULLISH_EDGE_ACTIVE').sum()),'bearish_edge_active':int((r.regime=='BEARISH_EDGE_ACTIVE').sum()),'no_trade_signal_generated':True}
    (out/'step9_summary.json').write_text(json.dumps(summary,indent=2)); print(json.dumps(summary,indent=2))
if __name__=='__main__': main()
