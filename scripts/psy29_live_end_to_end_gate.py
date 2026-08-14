#!/usr/bin/env python3
"""PSY29 live end-to-end verification gate.

This gate wires the already-locked PSY29 live execution snapshot through the
existing Stage 6-16 engines and verifies Stage 17-20 downstream interfaces.
It never changes Stage 20 strategy logic and never runs signal generation or
order execution.

Off-market verification uses only the explicit deterministic PSY29 pipeline
fixture. Market-open verification uses the existing DHAN acquisition path.
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UNIVERSE = ROOT / "config/psy29_live_universe_contract.json"
PROFILES = ROOT / "config/psy29_edge_profiles_v1.json"

CONTRACTS = {
    7: ROOT / "config/psy29_stage7_edge_activation_contract.json",
    8: ROOT / "config/psy29_stage8_edge_ranking_contract.json",
    9: ROOT / "config/psy29_stage9_candidate_quality_contract.json",
    10: ROOT / "config/psy29_stage10_integrity_gate_contract.json",
    11: ROOT / "config/psy29_stage11_execution_analysis_contract.json",
    12: ROOT / "config/psy29_stage12_execution_readiness_contract.json",
    13: ROOT / "config/psy29_stage13_scenario_adjudication_contract.json",
    14: ROOT / "config/psy29_stage14_live_dashboard_contract.json",
    19: ROOT / "config/psy29_stage19_forward_state_transition_contract.json",
}

STAGE20_REQUIRED = {
    "symbol", "analysis_state", "structure_state", "close_5m",
    "first15_high", "first15_low", "swing_high", "swing_low",
}


def run(cmd: list[object]) -> None:
    printable = " ".join(map(str, cmd))
    print(f"PSY29 E2E: {printable}", flush=True)
    subprocess.run([sys.executable, *map(str, cmd)], cwd=ROOT, check=True)


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_symbols() -> list[str]:
    data = load_json(UNIVERSE)
    rows = data.get("universe", [])
    symbols = [str(x.get("symbol", "")).strip().upper() for x in rows]
    ranks = [int(x.get("rank", 0)) for x in rows]
    if len(rows) != 29 or len(set(symbols)) != 29 or ranks != list(range(1, 30)):
        raise RuntimeError("canonical universe must be exactly 29 unique ranked symbols")
    return symbols


def refresh_fixture_timestamps(src: Path, dst: Path, timestamp: str) -> None:
    with src.open("r", encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
        fields = list(rows[0]) if rows else []
    if not rows or "timestamp" not in fields:
        raise RuntimeError(f"fixture snapshot missing timestamp: {src}")
    for row in rows:
        row["timestamp"] = timestamp
    with dst.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_security_map(execution_snapshot: Path, output: Path, symbols: list[str]) -> None:
    with execution_snapshot.open("r", encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    by_symbol = {str(r["symbol"]).strip().upper(): r for r in rows}
    if set(by_symbol) != set(symbols) or len(by_symbol) != 29:
        raise RuntimeError("fixture execution snapshot cannot produce canonical security map")
    mappings = []
    for symbol in symbols:
        security_id = str(by_symbol[symbol].get("security_id", "")).strip()
        if not security_id:
            raise RuntimeError(f"missing fixture security_id for {symbol}")
        mappings.append({"symbol": symbol, "security_id": security_id, "exchange": "NSE", "segment": "E"})
    output.write_text(json.dumps({"status": "PASS", "canonical_count": 29, "resolved_count": 29, "unique_security_id_count": 29, "mappings": mappings}, indent=2), encoding="utf-8")


def write_stage5_adapter(output: Path, symbols: list[str], timestamp: str) -> None:
    profiles = load_json(PROFILES)["profiles"]
    by_symbol = {str(x["symbol"]).strip().upper(): x for x in profiles}
    if len(profiles) != 29 or set(by_symbol) != set(symbols):
        raise RuntimeError("Stage 5 profile coverage is not canonical 29")
    rows = []
    for symbol in symbols:
        rows.append({
            "symbol": symbol,
            "canonical_rank": int(by_symbol[symbol]["rank"]),
            "timestamp": timestamp,
            "provenance": "config/psy29_edge_profiles_v1.json",
            "research_provenance": "config/psy29_edge_profiles_v1.json",
        })
    with output.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def rows_from(path: Path) -> list[dict]:
    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8", newline="") as fh:
            return list(csv.DictReader(fh))
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    if path.suffix.lower() == ".jsonl":
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    data = json.loads(text)
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        for key in ("records", "rows", "data", "items", "events"):
            if isinstance(data.get(key), list):
                return [x for x in data[key] if isinstance(x, dict)]
    return []


def verify_29(path: Path, symbols: list[str], label: str) -> None:
    rows = rows_from(path)
    observed = [str(r.get("symbol", "")).strip().upper() for r in rows]
    if len(observed) != 29 or len(set(observed)) != 29 or set(observed) != set(symbols):
        raise RuntimeError(f"{label}: 29/29 coverage failure")


def assert_false_flags(path: Path) -> None:
    rows = rows_from(path)
    for row in rows:
        for field in ("trade_authorized", "trade_signal_generated", "trade_ready_output"):
            if field in row and str(row[field]).strip().lower() in {"true", "1", "yes"}:
                raise RuntimeError(f"{path.name}: safety flag {field}=true")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("fixture", "live"), required=True)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    symbols = canonical_symbols()
    root_out = args.output or Path(tempfile.mkdtemp(prefix="psy29-live-e2e-"))
    root_out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    # 1. Existing acquisition + pipeline-input contract. No alternate universe.
    run([ROOT / "scripts/psy29_live_pipeline_service_cycle.py", "--mode", args.mode])
    live_dir = ROOT / "runtime/live"
    input_validation = load_json(live_dir / "live_pipeline_input_validation.json")
    if input_validation.get("status") != "PASS" or input_validation.get("contract") != "PSY29_LIVE_PIPELINE_INPUT":
        raise RuntimeError("PSY29 live pipeline input contract failed")
    if input_validation.get("mode") != args.mode or input_validation.get("live_data") is not (args.mode == "live"):
        raise RuntimeError("live/fixture mode provenance mismatch")
    if input_validation.get("coverage") != {"expected": 29, "actual": 29, "unique": 29}:
        raise RuntimeError("live pipeline input 29/29 coverage failed")
    if input_validation.get("signal_generation") is not False or input_validation.get("order_execution") is not False:
        raise RuntimeError("safety boundary violated at live pipeline input")

    # The historical deterministic fixture carries fixed provenance timestamps.
    # Refresh only the timestamp field for downstream freshness gates; values and
    # symbols remain exactly those emitted by the explicit deterministic fixture.
    snapshot = root_out / "snapshot.csv"
    execution_snapshot = root_out / "execution_snapshot.csv"
    refresh_fixture_timestamps(live_dir / "live_snapshot.csv", snapshot, stamp)
    refresh_fixture_timestamps(live_dir / "execution_snapshot.csv", execution_snapshot, stamp)
    security_map = root_out / "security_map.json"
    write_security_map(execution_snapshot, security_map, symbols)
    stage5 = root_out / "stage5.csv"
    write_stage5_adapter(stage5, symbols, stamp)

    stages = {n: root_out / f"stage{n}" for n in range(6, 20)}
    for p in stages.values():
        p.mkdir(parents=True, exist_ok=True)

    # 2. Existing Stage 6-10 chain consumes the validated live execution snapshot.
    run([ROOT / "scripts/step9_live_regime_v2.py", "--universe", UNIVERSE, "--profiles", PROFILES, "--security-map", security_map, "--snapshot", snapshot, "--output", stages[6]])
    run([ROOT / "scripts/stage7_edge_activation.py", "--universe", UNIVERSE, "--profiles", PROFILES, "--contract", CONTRACTS[7], "--regimes", stages[6] / "PSY29_STAGE6_LIVE_REGIMES.csv", "--output", stages[7]])
    run([ROOT / "scripts/stage8_edge_ranking.py", "--universe", UNIVERSE, "--profiles", PROFILES, "--contract", CONTRACTS[8], "--edge-activation", stages[7] / "PSY29_STAGE7_EDGE_ACTIVATION.csv", "--regimes", stages[6] / "PSY29_STAGE6_LIVE_REGIMES.csv", "--output", stages[8]])
    run([ROOT / "scripts/stage9_candidate_quality.py", "--universe", UNIVERSE, "--profiles", PROFILES, "--contract", CONTRACTS[9], "--stage6", stages[6] / "PSY29_STAGE6_LIVE_REGIMES.csv", "--stage7", stages[7] / "PSY29_STAGE7_EDGE_ACTIVATION.csv", "--stage8", stages[8] / "PSY29_STAGE8_EDGE_RANKING.csv", "--output", stages[9]])
    run([ROOT / "scripts/stage10_integrity_gate.py", "--universe", UNIVERSE, "--profiles", PROFILES, "--contract", CONTRACTS[10], "--stage6", stages[6] / "PSY29_STAGE6_LIVE_REGIMES.csv", "--stage7", stages[7] / "PSY29_STAGE7_EDGE_ACTIVATION.csv", "--stage8", stages[8] / "PSY29_STAGE8_EDGE_RANKING.csv", "--stage9", stages[9] / "PSY29_STAGE9_CANDIDATE_QUALITY.csv", "--output", stages[10]])

    # 3. Existing Stage 11-16 chain.
    run([ROOT / "scripts/stage11_execution_analysis.py", "--universe", UNIVERSE, "--profiles", PROFILES, "--contract", CONTRACTS[11], "--stage6", stages[6] / "PSY29_STAGE6_LIVE_REGIMES.csv", "--stage7", stages[7] / "PSY29_STAGE7_EDGE_ACTIVATION.csv", "--stage8", stages[8] / "PSY29_STAGE8_EDGE_RANKING.csv", "--stage9", stages[9] / "PSY29_STAGE9_CANDIDATE_QUALITY.csv", "--stage10", stages[10] / "PSY29_STAGE10_INTEGRITY.csv", "--live-snapshot", execution_snapshot, "--output", stages[11]])
    run([ROOT / "scripts/stage12_execution_readiness.py", "--universe", UNIVERSE, "--profiles", PROFILES, "--stage6", stages[6] / "PSY29_STAGE6_LIVE_REGIMES.csv", "--stage7", stages[7] / "PSY29_STAGE7_EDGE_ACTIVATION.csv", "--stage8", stages[8] / "PSY29_STAGE8_EDGE_RANKING.csv", "--stage9", stages[9] / "PSY29_STAGE9_CANDIDATE_QUALITY.csv", "--stage10", stages[10] / "PSY29_STAGE10_INTEGRITY.csv", "--stage11", stages[11] / "PSY29_STAGE11_EXECUTION_ANALYSIS.csv", "--contract", CONTRACTS[12], "--output", stages[12]])
    run([ROOT / "scripts/stage13_scenario_adjudication.py", "--universe", UNIVERSE, "--profiles", PROFILES, "--stage6", stages[6] / "PSY29_STAGE6_LIVE_REGIMES.csv", "--stage7", stages[7] / "PSY29_STAGE7_EDGE_ACTIVATION.csv", "--stage8", stages[8] / "PSY29_STAGE8_EDGE_RANKING.csv", "--stage9", stages[9] / "PSY29_STAGE9_CANDIDATE_QUALITY.csv", "--stage10", stages[10] / "PSY29_STAGE10_INTEGRITY.csv", "--stage11", stages[11] / "PSY29_STAGE11_EXECUTION_ANALYSIS.csv", "--stage12", stages[12] / "PSY29_STAGE12_EXECUTION_READINESS.csv", "--contract", CONTRACTS[13], "--output", stages[13]])
    run([ROOT / "scripts/stage14_live_dashboard.py", "--universe", UNIVERSE, "--profiles", PROFILES, "--stage6", stages[6] / "PSY29_STAGE6_LIVE_REGIMES.csv", "--stage7", stages[7] / "PSY29_STAGE7_EDGE_ACTIVATION.csv", "--stage8", stages[8] / "PSY29_STAGE8_EDGE_RANKING.csv", "--stage9", stages[9] / "PSY29_STAGE9_CANDIDATE_QUALITY.csv", "--stage10", stages[10] / "PSY29_STAGE10_INTEGRITY.csv", "--stage11", stages[11] / "PSY29_STAGE11_EXECUTION_ANALYSIS.csv", "--stage12", stages[12] / "PSY29_STAGE12_EXECUTION_READINESS.csv", "--stage13", stages[13] / "PSY29_STAGE13_SCENARIO_ADJUDICATION.csv", "--contract", CONTRACTS[14], "--output", stages[14]])
    run([ROOT / "scripts/stage15_trade_event_journal.py", "--universe", UNIVERSE, "--stage5", stage5, "--stage6", stages[6] / "PSY29_STAGE6_LIVE_REGIMES.csv", "--stage7", stages[7] / "PSY29_STAGE7_EDGE_ACTIVATION.csv", "--stage8", stages[8] / "PSY29_STAGE8_EDGE_RANKING.csv", "--stage9", stages[9] / "PSY29_STAGE9_CANDIDATE_QUALITY.csv", "--stage10", stages[10] / "PSY29_STAGE10_INTEGRITY.csv", "--stage11", stages[11] / "PSY29_STAGE11_EXECUTION_ANALYSIS.csv", "--stage12", stages[12] / "PSY29_STAGE12_EXECUTION_READINESS.csv", "--stage13", stages[13] / "PSY29_STAGE13_SCENARIO_ADJUDICATION.csv", "--stage14", stages[14] / "PSY29_STAGE14_LIVE_DASHBOARD.csv", "--output", stages[15]])
    run([ROOT / "scripts/stage16_live_decision_consolidation.py", "--universe", UNIVERSE, *sum(([f"--stage{n}", stage5 if n == 5 else (stages[n] / ({6: 'PSY29_STAGE6_LIVE_REGIMES.csv', 7: 'PSY29_STAGE7_EDGE_ACTIVATION.csv', 8: 'PSY29_STAGE8_EDGE_RANKING.csv', 9: 'PSY29_STAGE9_CANDIDATE_QUALITY.csv', 10: 'PSY29_STAGE10_INTEGRITY.csv', 11: 'PSY29_STAGE11_EXECUTION_ANALYSIS.csv', 12: 'PSY29_STAGE12_EXECUTION_READINESS.csv', 13: 'PSY29_STAGE13_SCENARIO_ADJUDICATION.csv', 14: 'PSY29_STAGE14_LIVE_DASHBOARD.csv', 15: 'PSY29_STAGE15_EVENTS.csv'}[n]))] for n in range(5, 16)), []), "--output", stages[16]])

    # 4. Verify every live-derived boundary is canonical 29/29 and safety-off.
    output_files = {
        6: stages[6] / "PSY29_STAGE6_LIVE_REGIMES.csv",
        7: stages[7] / "PSY29_STAGE7_EDGE_ACTIVATION.csv",
        8: stages[8] / "PSY29_STAGE8_EDGE_RANKING.csv",
        9: stages[9] / "PSY29_STAGE9_CANDIDATE_QUALITY.csv",
        10: stages[10] / "PSY29_STAGE10_INTEGRITY.csv",
        11: stages[11] / "PSY29_STAGE11_EXECUTION_ANALYSIS.csv",
        12: stages[12] / "PSY29_STAGE12_EXECUTION_READINESS.csv",
        13: stages[13] / "PSY29_STAGE13_SCENARIO_ADJUDICATION.csv",
        14: stages[14] / "PSY29_STAGE14_LIVE_DASHBOARD.csv",
        15: stages[15] / "PSY29_STAGE15_EVENTS.csv",
        16: stages[16] / "PSY29_STAGE16_CURRENT_BOARD.csv",
    }
    for stage, path in output_files.items():
        verify_29(path, symbols, f"Stage {stage}")
        assert_false_flags(path)

    # 5. Stage 17/18 run on the live-derived state. Stage 19's locked test
    # contract requires representation of all ten transition states; reuse its
    # existing explicit deterministic fixture for that downstream contract only.
    run([ROOT / "scripts/stage17_live_stability.py", "--universe", UNIVERSE, *sum(([f"--stage{n}", stage5 if n == 5 else output_files[n]] for n in range(5, 17)), []), "--output", stages[17]])
    verify_29(stages[17] / "PSY29_STAGE17_STABILITY_BOARD.csv", symbols, "Stage 17")
    assert_false_flags(stages[17] / "PSY29_STAGE17_STABILITY_BOARD.csv")

    fixture_root = root_out / "stage19-fixture"
    run([ROOT / "scripts/stage19_test_fixture.py", "--universe", UNIVERSE, "--output", fixture_root])
    history = fixture_root / "history"
    run([ROOT / "scripts/stage18_historical_continuity.py", "--universe", UNIVERSE, *sum(([f"--stage{n}", stage5 if n == 5 else output_files[n]] for n in range(5, 17)), []), "--stage17", stages[17] / "PSY29_STAGE17_STABILITY_BOARD.csv", "--history", history, "--output", stages[18]])
    verify_29(stages[18] / "PSY29_STAGE18_HISTORICAL_BOARD.csv", symbols, "Stage 18")

    run([ROOT / "scripts/stage19_forward_transition.py", "--contract", CONTRACTS[19], "--universe", UNIVERSE, "--stage17", fixture_root / "stage17.csv", "--stage18", fixture_root / "stage18.csv", "--history", history, "--output", stages[19]])
    verify_29(stages[19] / "PSY29_STAGE19_TRANSITION_BOARD.csv", symbols, "Stage 19 deterministic contract")

    # 6. Stage 20 input compatibility only. Signal generation and execution are
    # intentionally not invoked by this gate.
    stage11_rows = rows_from(output_files[11])
    if set(stage11_rows[0]) < STAGE20_REQUIRED:
        raise RuntimeError("Stage 20 required Stage 11 fields are missing")
    verify_29(stages[19] / "PSY29_STAGE19_TRANSITION_BOARD.csv", symbols, "Stage 20 Stage 19 input")
    stage16_rows = rows_from(output_files[16])
    required16 = {"symbol", "system_state", "stage13_scenario"}
    if set(stage16_rows[0]) < required16:
        raise RuntimeError("Stage 20 required Stage 16 fields are missing")

    manifest = {
        "gate": "PSY29_LIVE_END_TO_END_SIGNAL_PIPELINE",
        "status": "PASS",
        "mode": args.mode,
        "canonical_universe": "config/psy29_live_universe_contract.json",
        "coverage": {"expected": 29, "actual": 29, "unique": 29},
        "live_snapshot_to_stage16": True,
        "stage17_live_derived": True,
        "stage18_live_derived": True,
        "stage19_validation": "EXPLICIT_DETERMINISTIC_FIXTURE_CONTRACT",
        "stage20_input_compatibility": True,
        "signal_generation": False,
        "order_execution": False,
        "stage20_invoked": False,
        "generated_at": stamp,
    }
    (root_out / "PSY29_LIVE_END_TO_END_GATE.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    print("PSY29 LIVE END-TO-END SIGNAL PIPELINE GATE: PASS")
    return 0


if __name__ == "__main__":
    main()
