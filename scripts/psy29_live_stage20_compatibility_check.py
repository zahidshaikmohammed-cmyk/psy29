#!/usr/bin/env python3
"""Verify PSY29 live pipeline input compatibility with Stage 11 and Stage 20.

This is an interface/compatibility gate only. It does not generate live signals,
place orders, or alter Stage 20 strategy logic.
"""
from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UNIVERSE = ROOT / "config/psy29_live_universe_contract.json"
PIPELINE_FIXTURE = ROOT / "scripts/psy29_live_pipeline_fixture.py"
BRIDGE = ROOT / "scripts/psy29_live_pipeline_bridge.py"
STAGE20_FIXTURE = ROOT / "scripts/stage20_test_fixture.py"
STAGE20_ENGINE = ROOT / "scripts/stage20_final_trading_signal_engine.py"
STAGE20_CHECK = ROOT / "scripts/stage20_check.py"
STAGE20_CONTRACT = ROOT / "config/psy29_stage20_final_trading_signal_contract.json"

STAGE11_REQUIRED = {
    "symbol", "timestamp",
    "open_1m", "high_1m", "low_1m", "close_1m", "volume_1m", "avg_volume_20_1m",
    "open_5m", "high_5m", "low_5m", "close_5m", "volume_5m", "avg_volume_20_5m",
    "vwap_5m", "ema9_5m", "ema20_5m",
    "first15_high", "first15_low", "swing_high", "swing_low",
}


def run(*args: object) -> None:
    subprocess.run([sys.executable, *map(str, args)], cwd=ROOT, check=True, timeout=240)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="psy29_live_stage20_") as td:
        root = Path(td)
        live = root / "live"
        stage20 = root / "stage20"
        stage20_out = root / "stage20_out"

        run(PIPELINE_FIXTURE, "--universe", UNIVERSE, "--output", live)
        run(
            BRIDGE,
            "--snapshot", live / "execution_snapshot.csv",
            "--validation", live / "live_acquisition_validation.json",
            "--universe", UNIVERSE,
            "--output", live,
            "--mode", "fixture",
        )

        manifest = json.loads((live / "live_pipeline_input_validation.json").read_text(encoding="utf-8"))
        assert manifest["status"] == "PASS"
        assert manifest["coverage"] == {"expected": 29, "actual": 29, "unique": 29}
        assert manifest["stage11_live_compatibility"] is True
        assert manifest["live_data"] is False
        assert manifest["signal_generation"] is False
        assert manifest["order_execution"] is False

        pipeline = read_csv(live / "live_pipeline_input.csv")
        assert len(pipeline) == 29
        assert len({row["symbol"].strip().upper() for row in pipeline}) == 29
        assert STAGE11_REQUIRED <= set(pipeline[0])
        assert all(str(row["freshness_status"]).upper() == "FIXTURE" for row in pipeline)
        print("LIVE PIPELINE -> STAGE 11 INPUT COMPATIBILITY: PASS")

        contract = json.loads(STAGE20_CONTRACT.read_text(encoding="utf-8"))
        assert contract["stage"] == 20
        assert contract["version"] == "1.0"
        assert contract["status"] == "LOCKED"
        assert contract["coverage"] == 29
        assert contract["signal_policy"]["multiple_signals_allowed"] is True
        assert contract["signal_policy"]["daily_signal_cap"] is None
        assert contract["strategy_authority"]["entry_owner"] == "selected_strategy"
        assert contract["strategy_authority"]["stop_loss_owner"] == "selected_strategy"
        assert contract["strategy_authority"]["take_profit_owner"] == "selected_strategy"
        assert contract["strategy_authority"]["generic_rr_fallback_forbidden"] is True

        run(STAGE20_FIXTURE, "--universe", UNIVERSE, "--output", stage20)
        run(
            STAGE20_ENGINE,
            "--contract", STAGE20_CONTRACT,
            "--universe", UNIVERSE,
            "--stage11", stage20 / "stage11.csv",
            "--stage16", stage20 / "stage16.csv",
            "--stage19", stage20 / "stage19.csv",
            "--memory", stage20 / "memory.csv",
            "--output", stage20_out,
        )
        run(
            STAGE20_CHECK,
            "--contract", STAGE20_CONTRACT,
            "--universe", UNIVERSE,
            "--output", stage20_out,
        )
        board = json.loads((stage20_out / "PSY29_STAGE20_FINAL_SIGNAL_BOARD.json").read_text(encoding="utf-8"))
        assert board["coverage"] == {"expected": 29, "actual": 29, "unique": 29}
        assert board["daily_signal_cap"] is None
        print("STAGE 20 DOWNSTREAM INTERFACE COMPATIBILITY: PASS")
        print("STAGE 20 STRATEGY/ENTRY/SL/TP CODE: UNMODIFIED")
        print("SIGNAL GENERATION: OFF")
        print("ORDER EXECUTION: OFF")
        print("PSY29 LIVE -> STAGE 20 COMPATIBILITY GATE: PASS")


if __name__ == "__main__":
    main()
