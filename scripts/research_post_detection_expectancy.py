from __future__ import annotations
import argparse,json
from pathlib import Path
import numpy as np,pandas as pd
S=["NESTLEIND","VEDL","ICICIPRULI","KALYANKJIL","KOTAKBANK","BANDHANBNK","BANKBARODA","TITAN","INFY","DLF","TCS","MAXHEALTH","KFINTECH","PRESTIGE","BHEL","RBLBANK","HCLTECH","ICICIGI","HDFCLIFE","MARICO","LUPIN","COFORGE","TECHM","SWIGGY","PERSISTENT","OBEROIRLTY","SUPREMEIND","LAURUSLABS","AMBUJACEM"]
ET=["Trend","Strong Trend","OR Continuation"]; H=[5,15,30,60]; TRAIN,TEST,STEP=60,20,20

def q(x,p,fb=np.nan):
 x=pd.to_numeric(pd.Series(x),errors='coerce').dropna(); return float(x.quantile(p)) if len(x) else float(fb)

def load(p):
 d=pd.read_parquet(p); t=d.timestamp
 t=pd.to_datetime(t,unit='s',errors='coerce',utc=True) if pd.api.types.is_numeric_dtype(t) else pd.to_datetime(t,errors='coerce',utc=True)
 d=d.copy(); d['ts']=t.dt.tz_convert('Asia/Kolkata'); d=d.dropna(subset=['ts']).sort_values('ts'); z=d.ts.dt.time
 d=d[(z>=pd.Timestamp('09:15').time())&(z<pd.Timestamp('15:30').time())].copy()
 for c in ['open','high','low','close','volume']: d[c]=pd.to_numeric(d[c],errors='coerce')
 return d.dropna(subset=['open','high','low','close'])

def sessions(d):
 out=[]
 for day,g in d.groupby(d.ts.dt.date,sort=True):
  g=g.sort_values('ts').reset_index(drop=True)
  if len(g)<30 or float(g.open.iloc[0])==0: continue
  op=float(g.open.iloc[0]); cl=float(g.close.iloc[-1]); r=g.close.pct_change().dropna(); dar=abs((cl-op)/op); eff=dar/(float(r.abs().sum())+1e-12)
  o=g.iloc[:15]; rem=g.iloc[15:]; orh=float(o.high.max()); orl=float(o.low.min()); orpct=(orh-orl)/op
  bu=bool((rem.high>orh).any()); bd=bool((rem.low<orl).any()); ore=bool((bu and cl>orh) or (bd and cl<orl)); ext=max((cl-orh)/op,(orl-cl)/op,0.0)
  out.append(dict(date=str(day),g=g,day_abs_return=dar,directional_efficiency=eff,opening_range_pct=orpct,orh=orh,orl=orl,opening_range_continuation=ore,breakout_extension_pct=ext))
 return out

def th(tr):
 return dict(r75=q([x['day_abs_return'] for x in tr],.75),r85=q([x['day_abs_return'] for x in tr],.85),e60=q([x['directional_efficiency'] for x in tr],.60),e75=q([x['directional_efficiency'] for x in tr],.75),or75=q([x['opening_range_pct'] for x in tr],.75),ext60=q([x['breakout_extension_pct'] for x in tr],.60,0.0))

def detect(x,t):
 g=x['g']; op=float(g.open.iloc[0]); c=g.close.astype(float); r=c.pct_change().fillna(0.0); dar=(c-op).abs()/op; eff=dar/(r.abs().cumsum()+1e-12)
 tm=(dar>=t['r75'])&(eff>=t['e60']); sm=(dar>=t['r85'])&(eff>=t['e75']); tt=g.loc[tm,'ts'].iloc[0] if tm.any() else None; st=g.loc[sm,'ts'].iloc[0] if sm.any() else None; ot=None
 if x['opening_range_pct']<=t['or75']:
  a=g.iloc[15:]; up=(a.high>x['orh'])&(a.close>x['orh'])&((a.close-x['orh'])/op>=t['ext60']); dn=(a.low<x['orl'])&(a.close<x['orl'])&(x['orl']-a.close)/op>=t['ext60']; m=up|dn
  if m.any(): ot=a.loc[m,'ts'].iloc[0]
 return tt,st,ot

def metrics(g,ts,d):
 i=int(g.index[g.ts.eq(ts)][0]); e=float(g.close.iloc[i]); f=g.iloc[i+1:]; sign=1 if d=='LONG' else -1
 if e<=0:return None
 r={'entry_price':e,'remaining_minutes':len(f),'mfe_to_close':np.nan,'mae_to_close':np.nan}
 for h in H:r[f'return_{h}m']=(float(g.close.iloc[i+h])/e-1)*sign if i+h<len(g) else np.nan
 if len(f):
  fav=(f.high/e-1) if d=='LONG' else (1-f.low/e); adv=(f.low/e-1) if d=='LONG' else (1-f.high/e); r['mfe_to_close']=float(fav.max()); r['mae_to_close']=float(adv.min()); r['time_to_mfe_min']=float((f.ts.iloc[int(fav.argmax())]-ts).total_seconds()/60); r['time_to_mae_min']=float((f.ts.iloc[int(adv.argmin())]-ts).total_seconds()/60); r['close_return']=(float(f.close.iloc[-1])/e-1)*sign
 else:r['time_to_mfe_min']=r['time_to_mae_min']=r['close_return']=np.nan
 r['win_close']=bool(r['close_return']>0) if np.isfinite(r['close_return']) else False; return r

def bucket(ts):
 m=ts.hour*60+ts.minute
 return 'before_1430' if m<870 else '1430_1445' if m<885 else '1445_1500' if m<900 else 'after_1500'

def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--input',required=True); ap.add_argument('--summary',required=True); ap.add_argument('--output',required=True); a=ap.parse_args(); out=Path(a.output); out.mkdir(parents=True,exist_ok=True)
 sm=pd.read_csv(a.summary); expected={(r.symbol,r.event_type):int(r.sample_count) for _,r in sm.iterrows()}; assert len(expected)==87
 rows=[]
 for sym in S:
  ss=sessions(load(next(Path(a.input).rglob(f'{sym}.parquet')))); assert len(ss)>=80
  for k in range(0,len(ss)-TRAIN-TEST+1,STEP):
   tr=ss[k:k+TRAIN]; t=th(tr)
   for x in ss[k+TRAIN:k+TRAIN+TEST]:
    final=(x['day_abs_return']>=t['r75'] and x['directional_efficiency']>=t['e60'], x['day_abs_return']>=t['r85'] and x['directional_efficiency']>=t['e75'], x['opening_range_continuation'] and x['opening_range_pct']<=t['or75'] and x['breakout_extension_pct']>=t['ext60'])
    times=detect(x,t)
    for j,(ts,qual) in enumerate(zip(times,final)):
     if ts is None or not qual: continue
     d='LONG' if (float(x['g'].loc[x['g'].ts.eq(ts),'close'].iloc[0])>=float(x['g'].open.iloc[0])) else 'SHORT'
     if j==2: d='LONG' if float(x['g'].loc[x['g'].ts.eq(ts),'close').iloc[0])>x['orh'] else 'SHORT'
     m=metrics(x['g'],ts,d)
     if m: rows.append({'symbol':sym,'date':x['date'],'event_type':ET[j],'detection_timestamp':ts.isoformat(),'bucket':bucket(ts),'direction':d,**m})
 ev=pd.DataFrame(rows); val=[]
 for sym in S:
  for et in ET:
   got=int(((ev.symbol==sym)&(ev.event_type==et)).sum()); exp=expected[(sym,et)]; val.append({'symbol':sym,'event_type':et,'expected_sample_count':exp,'observed_sample_count':got,'match':exp==got})
 val=pd.DataFrame(val); val.to_csv(out/'sample_count_validation.csv',index=False)
 if len(val)!=87 or not val.match.all(): val[~val.match].to_csv(out/'sample_count_mismatches.csv',index=False); raise RuntimeError('Event-count validation failed')
 ev.to_csv(out/'event_level_expectancy.csv',index=False)
 agg=[]
 for (b,e),g in ev.groupby(['bucket','event_type']):
  r={'bucket':b,'event_type':e,'n':len(g)}
  for c in ['return_5m','return_15m','return_30m','return_60m','mfe_to_close','mae_to_close','time_to_mfe_min','time_to_mae_min','remaining_minutes','close_return']:r[c+'_mean']=float(g[c].mean());r[c+'_median']=float(g[c].median())
  r['win_rate_close']=float(g.win_close.mean());agg.append(r)
 pd.DataFrame(agg).to_csv(out/'expectancy_by_bucket_event.csv',index=False)
 bs=[]
 for (s,b,e),g in ev.groupby(['symbol','bucket','event_type']):bs.append({'symbol':s,'bucket':b,'event_type':e,'n':len(g),'median_return_30m':float(g.return_30m.median()),'median_close_return':float(g.close_return.median()),'median_mfe':float(g.mfe_to_close.median()),'median_mae':float(g.mae_to_close.median()),'median_remaining_minutes':float(g.remaining_minutes.median()),'win_rate_close':float(g.win_close.mean())})
 pd.DataFrame(bs).to_csv(out/'expectancy_by_stock_bucket_event.csv',index=False); (out/'study_manifest.json').write_text(json.dumps({'method':'non-hindsight first-detection outcome study','walk_forward':'60 train / 20 test / 20 step','symbols':29,'event_types':3,'events':len(ev),'validation_pass':True,'horizons_minutes':H},indent=2))
 print('PASS',len(ev))
if __name__=='__main__':main()
