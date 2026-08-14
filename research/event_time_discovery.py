import pandas as pd
import numpy as np
from pathlib import Path

SYMBOLS = ["NESTLEIND","VEDL","ICICIPRULI","KALYANKJIL","KOTAKBANK","BANDHANBNK","BANKBARODA","TITAN","INFY","DLF","TCS","MAXHEALTH","KFINTECH","PRESTIGE","BHEL","RBLBANK","HCLTECH","ICICIGI","HDFCLIFE","MARICO","LUPIN","COFORGE","TECHM","SWIGGY","PERSISTENT","OBEROIRLTY","SUPREMEIND","LAURUSLABS","AMBUJACEM"]
TRAIN, TEST, STEP = 60, 20, 20

def q(v,p,fb=np.nan):
    s=pd.to_numeric(pd.Series(v),errors='coerce').dropna()
    return float(s.quantile(p)) if len(s) else float(fb)

def sessions(path,sym):
    df=pd.read_parquet(path)
    ts=df.timestamp
    ts=pd.to_datetime(ts,unit='s',errors='coerce',utc=True) if pd.api.types.is_numeric_dtype(ts) else pd.to_datetime(ts,errors='coerce',utc=True)
    df=df.copy(); df['ts']=ts.dt.tz_convert('Asia/Kolkata'); df=df.dropna(subset=['ts']).sort_values('ts')
    t=df.ts.dt.time; df=df[(t>=pd.Timestamp('09:15').time())&(t<pd.Timestamp('15:30').time())].copy()
    for c in ['open','high','low','close','volume']: df[c]=pd.to_numeric(df[c],errors='coerce')
    df=df.dropna(subset=['open','high','low','close']); df['date']=df.ts.dt.date
    out=[]
    for d,g in df.groupby('date',sort=True):
        g=g.sort_values('ts').copy()
        if len(g)<30: continue
        op=float(g.open.iloc[0]); cl=float(g.close.iloc[-1]); hi=float(g.high.max()); lo=float(g.low.min())
        if op==0: continue
        dar=abs((cl-op)/op); r=g.close.pct_change().dropna(); eff=dar/(float(r.abs().sum())+1e-12)
        o=g.iloc[:15]; rem=g.iloc[15:]; orh=float(o.high.max()); orl=float(o.low.min()); orpct=(orh-orl)/op
        bu=bool((rem.high>orh).any()); bd=bool((rem.low<orl).any()); orc=bool((bu and cl>orh) or (bd and cl<orl))
        ext=max((cl-orh)/op,(orl-cl)/op,0.0)
        out.append(dict(symbol=sym,date=str(d),g=g,day_abs_return=dar,directional_efficiency=eff,opening_range_pct=orpct,orh=orh,orl=orl,opening_range_continuation=orc,breakout_extension_pct=ext))
    return out

def thresholds(train):
    return dict(r75=q([x['day_abs_return'] for x in train],.75),r85=q([x['day_abs_return'] for x in train],.85),e60=q([x['directional_efficiency'] for x in train],.60),e75=q([x['directional_efficiency'] for x in train],.75),or75=q([x['opening_range_pct'] for x in train],.75),ext60=q([x['breakout_extension_pct'] for x in train],.60,0.0))

def detect(s,t):
    g=s['g']; op=float(g.open.iloc[0]); c=g.close.astype(float); r=c.pct_change().fillna(0.0)
    dar=(c-op).abs()/op; eff=dar/(r.abs().cumsum()+1e-12)
    tm=(dar>=t['r75'])&(eff>=t['e60']); sm=(dar>=t['r85'])&(eff>=t['e75'])
    tt=g.loc[tm,'ts'].iloc[0] if tm.any() else None; st=g.loc[sm,'ts'].iloc[0] if sm.any() else None; ot=None
    if s['opening_range_pct']<=t['or75']:
        a=g.iloc[15:]
        up=(a.high>s['orh'])&(a.close>s['orh'])&(((a.close-s['orh'])/op)>=t['ext60'])
        dn=(a.low<s['orl'])&(a.close<s['orl'])&(((s['orl']-a.close)/op)>=t['ext60'])
        m=up|dn
        if m.any(): ot=a.loc[m,'ts'].iloc[0]
    return tt,st,ot

rows=[]; validation=[]
root=Path('data/raw/intraday')
for sym in SYMBOLS:
    ss=sessions(root/f'{sym}.parquet',sym)
    if len(ss)<80: raise RuntimeError(f'{sym}: {len(ss)} sessions')
    ss=sorted(ss,key=lambda x:x['date']); start=0; vc=[]
    while start+TRAIN+TEST<=len(ss):
        tr=ss[start:start+TRAIN]; te=ss[start+TRAIN:start+TRAIN+TEST]; th=thresholds(tr)
        for s in te:
            trend=s['day_abs_return']>=th['r75'] and s['directional_efficiency']>=th['e60']
            strong=s['day_abs_return']>=th['r85'] and s['directional_efficiency']>=th['e75']
            ore=s['opening_range_continuation'] and s['opening_range_pct']<=th['or75'] and s['breakout_extension_pct']>=th['ext60']
            tt,st,ot=detect(s,th)
            if trend and tt is not None: rows.append([sym,'Trend',s['date'],tt])
            if strong and st is not None: rows.append([sym,'Strong Trend',s['date'],st])
            if ore and ot is not None: rows.append([sym,'OR Continuation',s['date'],ot])
            vc.append([trend,strong,ore])
        start+=STEP
    a=np.array(vc,dtype=bool); validation.append([sym,len(vc),int(a[:,0].sum()),int(a[:,1].sum()),int(a[:,2].sum())])

df=pd.DataFrame(rows,columns=['symbol','event_type','date','timestamp']); df['timestamp']=pd.to_datetime(df.timestamp); df['minute_offset']=df.timestamp.dt.hour*60+df.timestamp.dt.minute-555
summary=[]
for (sym,evt),g in df.groupby(['symbol','event_type'],sort=False):
    x=g.minute_offset.astype(float); summary.append([sym,evt,len(x),x.min(),x.quantile(.25),x.median(),x.quantile(.75),x.quantile(.90),x.max()])
summary=pd.DataFrame(summary,columns=['symbol','event_type','sample_count','earliest_offset','q25_offset','median_offset','q75_offset','p90_offset','maximum_offset'])
for c in summary.columns[3:]: summary[c]=summary[c].round(1)
summary.to_csv('event_time_summary.csv',index=False); pd.DataFrame(validation,columns=['symbol','oos_sessions','trend_count','strong_trend_count','or_continuation_count']).to_csv('event_time_validation.csv',index=False)
print(summary.to_string(index=False)); print(pd.DataFrame(validation,columns=['symbol','oos_sessions','trend_count','strong_trend_count','or_continuation_count']).to_string(index=False))
