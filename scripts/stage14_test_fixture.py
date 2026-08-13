#!/usr/bin/env python3
"""Create a deterministic, fresh 29-stock Stage 14 upstream fixture."""
from __future__ import annotations

import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit("usage: stage14_test_fixture.py <universe.json> <output_dir>")
    universe_path = Path(sys.argv[1])
    root = Path(sys.argv[2])
    root.mkdir(parents=True, exist_ok=True)
    universe = json.loads(universe_path.read_text(encoding="utf-8"))["universe"]
    symbols = [str(x["symbol"]).upper().strip() for x in universe]
    assert len(symbols) == 29 and len(set(symbols)) == 29
    (root / "profiles.json").write_text(json.dumps({"profiles": [{"symbol": s} for s in symbols]}), encoding="utf-8")
    ts = (datetime.now(timezone.utc) - timedelta(seconds=30)).isoformat(timespec="seconds").replace("+00:00", "Z")
    prov = {k: f"{k}-fixture" for k in [
        "research_provenance", "stage6_provenance", "stage7_provenance", "stage8_provenance",
        "stage9_provenance", "stage10_provenance", "stage11_provenance", "stage12_provenance", "stage13_provenance"
    ]}
    safety = {k: False for k in [
        "trade_ready_output", "trade_authorized", "trade_signal_generated", "ce_pe_selection",
        "entry_calculation", "stop_loss_calculation", "target_calculation", "position_size_calculation",
        "risk_calculation", "capital_allocation", "order_generation", "execution"
    ]}

    def write(name: str, rows: list[dict[str, object]]) -> None:
        with (root / name).open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

    s6 = [{"symbol": s, "regime": "BULLISH_BREAKOUT_REGIME", "data_status": "FRESH"} for s in symbols]
    s7 = [{"symbol": s, "activation": "EDGE_ACTIVE", "data_status": "FRESH"} for s in symbols]
    s8 = [{"symbol": s, "activation": "EDGE_ACTIVE", "data_status": "FRESH", "portfolio_rank": i} for i, s in enumerate(symbols, 1)]
    s9 = [{"symbol": s, "activation": "EDGE_ACTIVE", "data_status": "FRESH", "candidate_quality_score": 90} for s in symbols]
    s10 = [{"symbol": s, "integrity_state": "INTEGRITY_PASS", "data_status": "FRESH", **{k: prov[k] for k in ["research_provenance", "stage6_provenance", "stage7_provenance", "stage8_provenance"]}} for s in symbols]
    s11 = [{"symbol": s, "analysis_state": "EXECUTION_ANALYSIS_VALID", "live_data_timestamp": ts, "stage10_provenance": prov["stage10_provenance"], "stage11_provenance": prov["stage11_provenance"]} for s in symbols]
    s12 = [{"symbol": s, "stage12_state": "EXECUTION_SCENARIO_READY", "live_data_timestamp": ts, "stage12_provenance": prov["stage12_provenance"]} for s in symbols]
    s13 = [{
        "symbol": s, "stage13_state": "SCENARIO_CONFIRMED", "dominant_scenario": "BREAKOUT", "scenario_confidence": "0.90",
        "stage10_integrity": "INTEGRITY_PASS", "stage11_analysis_state": "EXECUTION_ANALYSIS_VALID", "stage12_readiness_state": "EXECUTION_SCENARIO_READY",
        "confirmation_condition": "Breakout structure remains intact with confirming live price/volume behaviour.",
        "invalidation_condition": "Breakout structure fails and price returns into the prior structural range.",
        "supporting_evidence": "stage6/stage11/stage12 coherent", "conflicting_evidence": "", "live_data_timestamp": ts,
        **prov, **safety
    } for s in symbols]
    for name, rows in [("stage6.csv", s6), ("stage7.csv", s7), ("stage8.csv", s8), ("stage9.csv", s9), ("stage10.csv", s10), ("stage11.csv", s11), ("stage12.csv", s12), ("stage13.csv", s13)]:
        write(name, rows)
    print(f"Stage 14 fixture PASS: 29/29 fresh at {ts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
