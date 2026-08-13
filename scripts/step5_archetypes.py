"""PSY29 Step 5: discover behavioural archetypes from Step 4 V2 features.

Unsupervised clustering is intentionally used only to discover structure; it does
not select the final 29 stocks. Standardised feature space + deterministic KMeans
with several k values produces cluster assignments and per-cluster centroids.
"""
from __future__ import annotations
import argparse, json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import RobustScaler

FEATURES = [
    'median_abs_return','median_range_pct','median_path_length_pct',
    'median_directional_efficiency','trend_day_rate_20pct','trend_day_rate_30pct',
    'trend_day_rate_40pct','median_same_direction_rate','median_direction_switch_rate',
    'median_max_same_direction_run','median_trend_imbalance','median_max_path_drawdown_pct',
    'median_1m_volatility','median_opening_range_15m_pct',
    'opening_range_up_break_rate','opening_range_down_break_rate',
    'median_opening_range_followthrough','median_session_volume','median_bar_volume'
]

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--input',default='input/step4/stock_behaviour_features_v2.csv'); ap.add_argument('--output',default='output/step5'); a=ap.parse_args()
    inp,out=Path(a.input),Path(a.output); out.mkdir(parents=True,exist_ok=True)
    df=pd.read_csv(inp)
    required={'symbol',*FEATURES}; missing=required-set(df.columns)
    if missing: raise RuntimeError(f'missing features: {sorted(missing)}')
    X=df[FEATURES].apply(pd.to_numeric,errors='coerce')
    med=X.median(); X=X.fillna(med)
    scaler=RobustScaler(); Z=scaler.fit_transform(X)
    assignments=[]; metrics=[]
    for k in (4,5,6,7,8):
        model=KMeans(n_clusters=k,random_state=29,n_init=50,max_iter=500)
        labels=model.fit_predict(Z)
        outdf=df[['symbol']].copy(); outdf['cluster']=labels
        counts=outdf.cluster.value_counts().sort_index()
        metrics.append({'k':k,'inertia':float(model.inertia_),'min_cluster_size':int(counts.min()),'max_cluster_size':int(counts.max())})
        if k==6:
            assignments=outdf
            centers=pd.DataFrame(scaler.inverse_transform(model.cluster_centers_),columns=FEATURES); centers.insert(0,'cluster',range(k)); centers.to_csv(out/'cluster_centroids_k6.csv',index=False)
    assignments.to_csv(out/'archetype_assignments_k6.csv',index=False)
    df.merge(assignments,on='symbol').sort_values(['cluster','symbol']).to_csv(out/'archetype_members_k6.csv',index=False)
    summary={'project':'PSY29','step':5,'version':'1.0','generated_at_utc':datetime.now(timezone.utc).isoformat(),'stocks_input':int(len(df)),'features_used':FEATURES,'k_values_tested':[4,5,6,7,8],'selected_discovery_k':6,'metrics':metrics,'final_selection_performed':False,'status':'PASS'}
    (out/'step5_summary.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary,indent=2))
if __name__=='__main__': main()
