from datetime import datetime, timedelta
import json
import sys
from pathlib import Path
import pandas as pd
from zoneinfo import ZoneInfo
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.psy29_live_dhan_acquisition import completed_candles, add_indicators_1m, add_indicators_5m, build_execution_row, STRUCTURAL_SWING_BARS
from scripts.psy29_live_pipeline_bridge import REQUIRED_STAGE11_LIVE
IST=ZoneInfo("Asia/Kolkata")
BASE=datetime(2026,8,17,9,15,tzinfo=IST)
def frame(start,n,minutes,offset=0):
 rows=[]
 for i in range(n):
  t=start+timedelta(minutes=minutes*i);p=100+offset+i*0.1
  rows.append({"timestamp":int(t.timestamp()),"open":p,"high":p+0.2,"low":p-0.2,"close":p+0.1,"volume":1000+i})
 return pd.DataFrame(rows)
raw=frame(BASE,16,1);now=BASE+timedelta(minutes=15,seconds=30)
assert completed_candles(raw,1,now)["dt"].iloc[-1].strftime("%H:%M")=="09:29"
raw_warm=pd.concat([frame(BASE-timedelta(days=1),30,1,20),frame(BASE,15,1)],ignore_index=True)
x=add_indicators_1m(raw_warm,BASE.date(),BASE+timedelta(minutes=15,seconds=1));assert bool(x.iloc[-1]["opening_range_complete"]) is True
current_only=frame(BASE,15,1).assign(ema20=lambda d:d.close.ewm(span=20,adjust=False).mean());assert abs(float(x.iloc[-1].ema20)-float(current_only.iloc[-1].ema20))>1e-9
# Structural swing warm-up: prior completed sessions only. The current session is
# intentionally given extreme highs/lows that must NOT contaminate the swing levels.
warm5=frame(BASE-timedelta(days=1),STRUCTURAL_SWING_BARS,5,30)
cur5=frame(BASE,4,5,40)
cur5.loc[:,"high"]=1000.0
cur5.loc[:,"low"]=1.0
all5=pd.concat([warm5,cur5],ignore_index=True)
x5=add_indicators_5m(all5,BASE.date(),BASE+timedelta(minutes=20,seconds=1));x1=add_indicators_1m(raw_warm,BASE.date(),BASE+timedelta(minutes=15,seconds=1));complete5=completed_candles(all5,5,BASE+timedelta(minutes=20,seconds=1))
row=build_execution_row("TEST","1",x1,x5,complete5,complete5,"2026-08-17T03:45:00Z")
assert row["avg_volume_20_5m"]>0 and row["candle_completion_policy"]=="COMPLETED_CANDLES_ONLY"
assert row["session_high"]==float(x5.high.max()) and row["session_low"]==float(x5.low.min())
assert row["swing_high"]==float(warm5.high.max()) and row["swing_low"]==float(warm5.low.min())
assert row["structural_swing_warmup"]=="PRIOR_COMPLETED_SESSIONS"
assert row["structural_swing_window_bars"]==STRUCTURAL_SWING_BARS
assert row["structural_swing_policy"]=="PREVIOUS_SESSIONS_ONLY_EXCLUDE_CURRENT_SESSION"
assert {"session_high","session_low"}.issubset(REQUIRED_STAGE11_LIVE)
assert len(REQUIRED_STAGE11_LIVE)==23
root=Path(__file__).resolve().parents[1]
stage11=json.loads((root/"config/psy29_stage11_execution_analysis_contract.json").read_text(encoding="utf-8"))
dhan=json.loads((root/"config/psy29_live_dhan_data_contract.json").read_text(encoding="utf-8"))
assert stage11["version"]=="1.1" and dhan["version"]=="1.1"
assert set(stage11["live_execution_snapshot_required_fields"])==REQUIRED_STAGE11_LIVE
assert {"session_high","session_low"}.issubset(set(dhan["required_live_snapshot_fields"]))
assert stage11["live_data_source"]["contract"]=="config/psy29_live_dhan_data_contract.json"
print("PSY29 ACCURACY UNIT TESTS: PASS")
print("Partial-candle exclusion: PASS")
print("EMA warm-up: PASS")
print("20-bar volume warm-up: PASS")
print("Historical structural swing warm-up: PASS")
print("Current-session swing contamination guard: PASS")
print("Session-extreme acquisition: PASS")
print("Session-extreme bridge contract: PASS")
print("Stage 11/DHAN contract parity: PASS")
