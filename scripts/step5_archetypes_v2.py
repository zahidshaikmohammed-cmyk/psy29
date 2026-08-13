"""PSY29 Step 5 V2: robust behavioural archetype discovery.

No final stock selection. Evaluates K=3..10 using silhouette, Calinski-Harabasz,
Davies-Bouldin, minimum cluster size, and bootstrap stability. Outliers are
flagged separately. A K is accepted only when objective quality gates pass.
"""
from __future__ import annotations
import argparse,json
from datetime import datetime,timezone
from pathlib import Path
import numpy as np,pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import RobustScaler
from sklearn.metrics import silhouette_score,calinski_harabasz_score,davies_bouldin_score,adjusted_rand_score
from sklearn.ensemble import IsolationForest

FEATURES=['median_abs_return','median_range_pct','median_path_length_pct','median_directional_efficiency','trend_day_rate_20pct','trend_day_rate_30pct','trend_day_rate_40pct','median_same_direction_rate','median_direction_switch_rate','median_max_same_direction_run','median_trend_imbalance','median_max_path_drawdown_pct','median_1m_volatility','median_opening_range_15m_pct','opening_range_up_break_rate','opening_range_down_break_rate','median_opening_range_followthrough','median_session_volume','median_bar_volume']
MIN_CLUSTER=8

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--input',default='input/step4/stock_behaviour_features_v2.csv');ap.add_argument('--output',default='output/step5_v2');a=ap.parse_args();out=Path(a.output);out.mkdir(parents=True,exist_ok=True)
    df=pd.read_csv(a.input); missing=({'symbol',*FEATURES}-set(df.columns));
    if missing: raise RuntimeError(f'missing features: {sorted(missing)}')
    X=df[FEATURES].apply(pd.to_numeric,errors='coerce'); X=X.fillna(X.median()); Z=RobustScaler().fit_transform(X)
    metrics=[]; labels_by_k={}
    for k in range(3,11):
        m=KMeans(n_clusters=k,random_state=29,n_init=50,max_iter=500); lab=m.fit_predict(Z); c=np.bincount(lab,minlength=k)
        sil=float(silhouette_score(Z,lab)); ch=float(calinski_harabasz_score(Z,lab)); db=float(davies_bouldin_score(Z,lab))
        # Bootstrap stability: remove 10% repeatedly, refit, compare labels on retained points.
        st=[]; rng=np.random.default_rng(2900+k)
        for b in range(20):
            keep=np.sort(rng.choice(len(Z),size=max(k*MIN_CLUSTER,int(len(Z)*.9)),replace=False)); mb=KMeans(n_clusters=k,random_state=29000+b,n_init=20,max_iter=500); lb=mb.fit_predict(Z[keep]); st.append(adjusted_rand_score(lab[keep],lb))
        stability=float(np.mean(st)); p10=float(np.percentile(st,10));
        metrics.append({'k':k,'silhouette':sil,'calinski_harabasz':ch,'davies_bouldin':db,'min_cluster_size':int(c.min()),'max_cluster_size':int(c.max()),'bootstrap_ari_mean':stability,'bootstrap_ari_p10':p10,'quality_gate':bool(sil>=0.20 and db<=2.5 and c.min()>=MIN_CLUSTER and stability>=0.70 and p10>=0.50)});labels_by_k[k]=lab
    # Choose the best passing K by silhouette, then stability; otherwise no accepted K.
    passing=[x for x in metrics if x['quality_gate']]; chosen=None if not passing else max(passing,key=lambda x:(x['silhouette'],x['bootstrap_ari_mean']))['k']
    iso=IsolationForest(n_estimators=300,random_state=29,contamination='auto'); outlier=iso.fit_predict(Z); score=-iso.score_samples(Z)
    odf=df[['symbol']].copy();odf['outlier_flag']=outlier==-1;odf['outlier_score']=score;odf.sort_values('outlier_score',ascending=False).to_csv(out/'outlier_scores.csv',index=False)
    if chosen is not None:
        lab=labels_by_k[chosen]; adf=df[['symbol']].copy();adf['archetype']=lab;adf.to_csv(out/f'archetype_assignments_k{chosen}.csv',index=False)
        centers=pd.DataFrame(RobustScaler().fit(X).fit_transform(X)) if False else None
        # Refit scaler/model to export interpretable centroids in original feature units.
        scaler=RobustScaler().fit(X); z=scaler.transform(X); model=KMeans(n_clusters=chosen,random_state=29,n_init=50,max_iter=500).fit(z); centers=pd.DataFrame(scaler.inverse_transform(model.cluster_centers_),columns=FEATURES); centers.insert(0,'archetype',range(chosen)); centers.to_csv(out/f'cluster_centroids_k{chosen}.csv',index=False)
    summary={'project':'PSY29','step':5,'version':'2.0','generated_at_utc':datetime.now(timezone.utc).isoformat(),'stocks_input':int(len(df)),'features_used':FEATURES,'k_values_tested':list(range(3,11)),'minimum_cluster_size':MIN_CLUSTER,'metrics':metrics,'accepted_k':chosen,'outlier_count':int((outlier==-1).sum()),'final_selection_performed':False,'status':'PASS' if chosen is not None else 'NO_STABLE_ARCHETYPE_SOLUTION'}
    (out/'step5_v2_summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
