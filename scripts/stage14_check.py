#!/usr/bin/env python3
import json
import sys
from pathlib import Path

root = Path(sys.argv[1] if len(sys.argv) > 1 else "output/stage14")
summary = json.loads((root / "PSY29_STAGE14_SUMMARY.json").read_text())
rows = json.loads((root / "PSY29_STAGE14_LIVE_DASHBOARD.json").read_text())
assert summary["engine_execution_status"] == "PASS"
assert summary["validation_status"] == "PASS"
assert summary["status"] == "PASS"
assert summary["coverage"] == 29
assert len(rows) == 29
assert len({r["symbol"] for r in rows}) == 29
assert {r["dashboard_state"] for r in rows} == {"ACTIVE_SCENARIO"}
assert {r["stage13_state"] for r in rows} == {"SCENARIO_CONFIRMED"}
assert {r["dominant_scenario"] for r in rows} == {"BREAKOUT"}
assert all(float(r["scenario_confidence"]) >= 0.90 for r in rows)
for r in rows:
    assert str(r["stage14_provenance"]).strip()
    assert all(r[k] is False for k in ["trade_ready_output","trade_authorized","trade_signal_generated","ce_pe_selection","entry_calculation","stop_loss_calculation","target_calculation","position_size_calculation","risk_calculation","capital_allocation","order_generation","execution"])
print("PSY29 STAGE 14 CHECK: PASS | 29/29")
