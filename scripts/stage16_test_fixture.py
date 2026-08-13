#!/usr/bin/env python3
"""Create a deterministic, fresh 29-stock Stage 5–15 fixture for Stage 16 CI."""
from __future__ import annotations
import argparse,csv,json
from datetime import datetime,timezone,timedelta
from pathlib import Path

def universe(p):
 d=json.loads(p.read_text(encoding="utf-8"));u=d.get("universe",[]);s=[str(x["symbol"]).upper() for x in u]
 if len(s)!=29 or len(set(s))!=29:raise ValueError("canonical universe must be 29 unique symbols")
 return s

def write(p,data):
 p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(data,indent=2)+"\n",encoding="utf-8")

def csvwrite(p,rows):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open("w",newline="",encoding="utf-8") as h:
  w=csv.DictWriter(h,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def main():
 ap=argparse.ArgumentParser();ap.add_argument("--universe",required=True,type=Path);ap.add_argument("--output",required=True,type=Path);a=ap.parse_args()
 syms=universe(a.universe);t=(datetime.now(timezone.utc)-timedelta(seconds=30)).replace(microsecond=0).isoformat().replace("+00:00","Z")
 stages={n:[] for n in range(6,16)};profiles=[]
 for rank,s in enumerate(syms,1):
  active=rank==1;secondary=rank==2
  edge="EDGE_ACTIVE" if active or secondary else "EDGE_INACTIVE"
  quality=95 if active else (82 if secondary else "")
  pr=rank if edge=="EDGE_ACTIVE" else ""
  regime="BULLISH_BREAKOUT_REGIME" if active else ("BULLISH_ALIGNMENT_REGIME" if secondary else "RANGE_REGIME")
  integrity="INTEGRITY_PASS"
  readiness="EXECUTION_SCENARIO_READY" if active else ("EXECUTION_SCENARIO_CONDITIONAL" if secondary else "EXECUTION_SCENARIO_BLOCKED")
  scenario="SCENARIO_CONFIRMED" if active else ("SCENARIO_CONDITIONAL" if secondary else "SCENARIO_UNCONFIRMED")
  scenario_class="BREAKOUT" if active else ("CONTINUATION" if secondary else "UNCLEAR")
  dashboard="ACTIVE_SCENARIO" if active else ("CONDITIONAL_SCENARIO" if secondary else "INACTIVE")
  for n,row in {
   6:{"symbol":s,"regime":regime,"data_status":"FRESH","live_data_timestamp":t,"stage6_provenance":"verified-fixture-stage6"},
   7:{"symbol":s,"edge_state":edge,"activation_state":edge,"data_status":"FRESH","live_data_timestamp":t,"stage7_provenance":"verified-fixture-stage7"},
   8:{"symbol":s,"portfolio_rank":pr,"ranking":pr,"data_status":"FRESH","stage8_provenance":"verified-fixture-stage8"},
   9:{"symbol":s,"quality_score":quality,"confidence_score":quality,"data_status":"FRESH","stage9_provenance":"verified-fixture-stage9"},
   10:{"symbol":s,"integrity_status":integrity,"integrity_state":integrity,"data_status":"FRESH","stage10_provenance":"verified-fixture-stage10"},
   11:{"symbol":s,"analysis_state":"EXECUTION_ANALYSIS_VALID","live_data_timestamp":t,"stage11_provenance":"verified-fixture-stage11"},
   12:{"symbol":s,"readiness_state":readiness,"scenario_gate_state":readiness,"live_data_timestamp":t,"stage12_provenance":"verified-fixture-stage12"},
   13:{"symbol":s,"state":scenario,"scenario_state":scenario,"scenario":scenario_class,"scenario_class":scenario_class,"confidence":0.95 if active else (0.80 if secondary else 0.20),"live_data_timestamp":t,"stage13_provenance":"verified-fixture-stage13"},
   14:{"symbol":s,"dashboard_state":dashboard,"dashboard_status":dashboard,"state":dashboard,"status":dashboard,"live_data_timestamp":t,"stage14_provenance":"verified-fixture-stage14"},
   15:{"symbol":s,"event_class":"INITIAL_SNAPSHOT","event_timestamp":t,"stage15_provenance":"verified-fixture-stage15"}
  }.items():stages[n].append(row)
  profiles.append({"symbol":s,"research_provenance":"verified-fixture-stage5"})
 a.output.mkdir(parents=True,exist_ok=True);write(a.output/"stage5.json",profiles)
 for n,rs in stages.items():csvwrite(a.output/f"stage{n}.csv",rs)
 write(a.output/"fixture_metadata.json",{"stage":16,"generated_at":t,"coverage":29,"symbols":syms,"fresh_fixture":True})
 print("PSY29 STAGE 16 FIXTURE: PASS");print("Canonical coverage: 29/29");print("Fixture timestamp:",t)
if __name__=="__main__":main()
