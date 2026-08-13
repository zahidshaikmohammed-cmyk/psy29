#!/usr/bin/env python3
"""Create deterministic PSY29 Stage 17 upstream/current/previous fixtures."""
from __future__ import annotations
import argparse,csv,json
from datetime import datetime,timezone,timedelta
from pathlib import Path

def load(p): return json.loads(p.read_text(encoding="utf-8"))
def write_csv(p,rows):
    fields=sorted({k for r in rows for k in r})
    with p.open("w",newline="",encoding="utf-8") as h:
        w=csv.DictWriter(h,fieldnames=fields);w.writeheader();w.writerows(rows)

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--universe",required=True,type=Path);ap.add_argument("--output",required=True,type=Path);a=ap.parse_args()
    syms=[x["symbol"] for x in load(a.universe)["universe"]]
    assert len(syms)==29 and len(set(syms))==29
    a.output.mkdir(parents=True,exist_ok=True)
    now=datetime.now(timezone.utc).replace(microsecond=0)
    stale=(now-timedelta(hours=2)).isoformat().replace("+00:00","Z")
    fresh=now.isoformat().replace("+00:00","Z")
    stage_rows={n:[] for n in range(5,16)}
    for i,s in enumerate(syms,1):
        ts=stale if i==7 else fresh
        for n in range(5,16):
            r={"symbol":s,"timestamp":ts,f"stage{n}_provenance":f"fixture-stage{n}-{s}"}
            if i==8 and n==9: r.pop("stage9_provenance")
            if n==6:r["regime"]="TREND" if i%2 else "RANGE"
            if n==7:r["edge_state"]="EDGE_ACTIVE" if i%3 else "EDGE_INACTIVE"
            if n==8:r["portfolio_rank"]=i if r.get("edge_state")!="EDGE_INACTIVE" else ""
            if n==9:r["quality_score"]=70+i
            if n==10:r["integrity_status"]="INTEGRITY_PASS"
            if n==11:r["analysis_state"]="ANALYZED"
            if n==12:r["readiness_state"]="SCENARIO_REVIEW"
            if n==13:r["state"]="SCENARIO_CONFIRMED"
            if n==14:r["dashboard_state"]="CURRENT"
            if n==15:r["event_class"]="UNCHANGED"
            stage_rows[n].append(r)
    for n,rows in stage_rows.items():
        if n==5:
            (a.output/"stage5.json").write_text(json.dumps({"records":rows},indent=2)+"\n",encoding="utf-8")
        else: write_csv(a.output/f"stage{n}.csv",rows)

    def board(previous=False):
        rec=[]
        for i,s in enumerate(syms,1):
            edge="EDGE_ACTIVE" if i%3 else "EDGE_INACTIVE"
            quality=70+i
            state="PRIMARY_CANDIDATE" if edge=="EDGE_ACTIVE" else "WATCHLIST"
            rank=i if edge=="EDGE_ACTIVE" else ""
            scenario="SCENARIO_CONFIRMED"
            if previous:
                if i==2: rank=99
                if i==3: quality=90
                if i==4: edge="EDGE_INACTIVE";state="WATCHLIST";rank=""
                if i==5: state="PRIMARY_CANDIDATE"
            if i==5 and not previous: state="DATA_INVALID"
            if i==6 and not previous: scenario="SCENARIO_CONFLICT"
            if i==9 and not previous: edge="EDGE_ACTIVE"
            rec.append({
                "symbol":s,"canonical_rank":i,"system_state":state,
                "stage6_regime":"TREND" if i%2 else "RANGE",
                "stage7_edge_state":edge,"stage8_portfolio_rank":rank,
                "stage9_quality_score":quality,"stage10_integrity":"INTEGRITY_PASS",
                "stage11_analysis_state":"ANALYZED","stage12_readiness_state":"SCENARIO_REVIEW",
                "stage13_state":scenario,"stage13_scenario":"BASE",
                "stage14_dashboard_state":"CURRENT","stage15_event_class":"UNCHANGED",
                "provenance":{"stage16_provenance":f"fixture-stage16-{s}"},"timestamp":fresh
            })
        return {"stage":16,"version":"1.0","coverage":{"expected":29,"actual":29,"unique":29},"records":rec}
    (a.output/"stage16_current.json").write_text(json.dumps(board(False),indent=2)+"\n",encoding="utf-8")
    (a.output/"stage16_previous.json").write_text(json.dumps(board(True),indent=2)+"\n",encoding="utf-8")
    print("STAGE17 FIXTURE: PASS")
if __name__=="__main__":main()
