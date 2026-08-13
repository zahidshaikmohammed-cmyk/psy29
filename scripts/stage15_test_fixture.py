#!/usr/bin/env python3

"""
PSY29 Stage 15 — Deterministic Test Fixture
Version: 1.0

Creates a deterministic 29-stock Stage 5–14 upstream fixture
for Stage 15 hard verification.

This fixture is CI-only.
It does not modify any Stage 5–14 research or engine logic.
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List


def load_json(path: Path) -> Dict[str, Any]:
    with path.open(
        "r",
        encoding="utf-8",
    ) as handle:
        return json.load(handle)


def write_json(
    path: Path,
    data: Any,
) -> None:

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open(
        "w",
        encoding="utf-8",
    ) as handle:

        json.dump(
            data,
            handle,
            indent=2,
            ensure_ascii=False,
        )

        handle.write("\n")


def write_csv(
    path: Path,
    rows: List[Dict[str, Any]],
) -> None:

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if not rows:
        raise ValueError(
            f"No rows supplied for {path}"
        )

    fieldnames = list(
        rows[0].keys()
    )

    with path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:

        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
        )

        writer.writeheader()
        writer.writerows(rows)


def canonical_symbols(
    universe_path: Path,
) -> List[str]:

    data = load_json(
        universe_path
    )

    candidates = [
        data.get("symbols"),
        data.get("universe"),
        data.get("stocks"),
        data.get("canonical_symbols"),
        data.get("exact_symbol_list"),
    ]

    symbols = None

    for candidate in candidates:

        if isinstance(
            candidate,
            list,
        ):
            symbols = candidate
            break

    if symbols is None:

        nested = data.get(
            "canonical_universe"
        )

        if isinstance(
            nested,
            dict,
        ):

            for key in (
                "symbols",
                "stocks",
                "canonical_symbols",
            ):

                if isinstance(
                    nested.get(key),
                    list,
                ):

                    symbols = nested[key]
                    break

    if symbols is None:

        raise ValueError(
            "Unable to locate canonical 29."
        )

    result = [
        str(symbol).strip().upper()
        for symbol in symbols
        if str(symbol).strip()
    ]

    if len(result) != 29:

        raise ValueError(
            f"Expected 29 symbols; "
            f"found {len(result)}"
        )

    if len(set(result)) != 29:

        raise ValueError(
            "Canonical universe contains duplicates."
        )

    return result


def fresh_timestamp() -> str:

    # Keep the fixture comfortably inside the normal
    # Stage 15 freshness window while avoiding a future
    # timestamp.

    timestamp = (
        datetime.now(timezone.utc)
        - timedelta(seconds=30)
    )

    return (
        timestamp
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def provenance(
    stage: int,
) -> str:

    return (
        f"PSY29 Stage {stage} verified upstream "
        f"fixture / provenance placeholder"
    )


def build_rows(
    symbols: List[str],
    timestamp: str,
) -> Dict[str, List[Dict[str, Any]]]:

    stage6 = []
    stage7 = []
    stage8 = []
    stage9 = []
    stage10 = []
    stage11 = []
    stage12 = []
    stage13 = []
    stage14 = []

    for rank, symbol in enumerate(
        symbols,
        start=1,
    ):

        # --------------------------------------------------
        # Deterministic scenario distribution
        # --------------------------------------------------

        if rank == 1:

            regime = "BULLISH_BREAKOUT_REGIME"
            edge = "EDGE_ACTIVE"
            portfolio_rank = 1
            quality = 95
            integrity = "INTEGRITY_PASS"
            analysis = "EXECUTION_ANALYSIS_VALID"
            readiness = "EXECUTION_SCENARIO_READY"
            scenario_state = "SCENARIO_CONFIRMED"
            scenario = "BREAKOUT"
            confidence = 0.95
            dashboard = "ACTIVE_SCENARIO"

        elif rank == 2:

            regime = "BULLISH_ALIGNMENT_REGIME"
            edge = "EDGE_ACTIVE"
            portfolio_rank = 2
            quality = 80
            integrity = "INTEGRITY_PASS"
            analysis = "EXECUTION_ANALYSIS_VALID"
            readiness = "EXECUTION_SCENARIO_CONDITIONAL"
            scenario_state = "SCENARIO_CONDITIONAL"
            scenario = "CONTINUATION"
            confidence = 0.75
            dashboard = "CONDITIONAL_SCENARIO"

        elif rank == 3:

            regime = "RANGE_REGIME"
            edge = "EDGE_INACTIVE"
            portfolio_rank = ""
            quality = ""
            integrity = "INTEGRITY_PASS"
            analysis = "EXECUTION_ANALYSIS_VALID"
            readiness = "EXECUTION_SCENARIO_BLOCKED"
            scenario_state = "SCENARIO_UNCONFIRMED"
            scenario = "RANGE"
            confidence = 0.40
            dashboard = "INACTIVE"

        else:

            regime = "RANGE_REGIME"
            edge = "EDGE_INACTIVE"
            portfolio_rank = ""
            quality = ""
            integrity = "INTEGRITY_PASS"
            analysis = "EXECUTION_ANALYSIS_VALID"
            readiness = "EXECUTION_SCENARIO_BLOCKED"
            scenario_state = "SCENARIO_UNCONFIRMED"
            scenario = "UNCLEAR"
            confidence = 0.20
            dashboard = "INACTIVE"

        # --------------------------------------------------
        # Stage 6
        # --------------------------------------------------

        stage6.append(
            {
                "symbol": symbol,
                "regime": regime,
                "data_status": "FRESH",
                "live_data_timestamp": timestamp,
                "stage6_provenance": provenance(6),
            }
        )

        # --------------------------------------------------
        # Stage 7
        # --------------------------------------------------

        stage7.append(
            {
                "symbol": symbol,
                "edge_state": edge,
                "activation_state": edge,
                "data_status": "FRESH",
                "live_data_timestamp": timestamp,
                "stage7_provenance": provenance(7),
            }
        )

        # --------------------------------------------------
        # Stage 8
        # --------------------------------------------------

        stage8.append(
            {
                "symbol": symbol,
                "portfolio_rank": portfolio_rank,
                "ranking": portfolio_rank,
                "data_status": "FRESH",
                "stage8_provenance": provenance(8),
            }
        )

        # --------------------------------------------------
        # Stage 9
        # --------------------------------------------------

        stage9.append(
            {
                "symbol": symbol,
                "quality_score": quality,
                "confidence_score": quality,
                "data_status": "FRESH",
                "stage9_provenance": provenance(9),
            }
        )

        # --------------------------------------------------
        # Stage 10
        # --------------------------------------------------

        stage10.append(
            {
                "symbol": symbol,
                "integrity_status": integrity,
                "integrity_state": integrity,
                "data_status": "FRESH",
                "stage10_provenance": provenance(10),
            }
        )

        # --------------------------------------------------
        # Stage 11
        # --------------------------------------------------

        stage11.append(
            {
                "symbol": symbol,
                "analysis_state": analysis,
                "live_data_timestamp": timestamp,
                "stage11_provenance": provenance(11),
            }
        )

        # --------------------------------------------------
        # Stage 12
        # --------------------------------------------------

        stage12.append(
            {
                "symbol": symbol,
                "readiness_state": readiness,
                "scenario_gate_state": readiness,
                "live_data_timestamp": timestamp,
                "stage12_provenance": provenance(12),
            }
        )

        # --------------------------------------------------
        # Stage 13
        # --------------------------------------------------

        stage13.append(
            {
                "symbol": symbol,
                "state": scenario_state,
                "scenario_state": scenario_state,
                "scenario": scenario,
                "scenario_class": scenario,
                "confidence": confidence,
                "scenario_confidence": confidence,
                "live_data_timestamp": timestamp,
                "stage13_provenance": provenance(13),
            }
        )

        # --------------------------------------------------
        # Stage 14
        # --------------------------------------------------

        stage14.append(
            {
                "symbol": symbol,
                "dashboard_state": dashboard,
                "dashboard_status": dashboard,
                "state": dashboard,
                "status": dashboard,
                "live_data_timestamp": timestamp,
                "stage14_provenance": provenance(14),
            }
        )

    return {
        "stage6": stage6,
        "stage7": stage7,
        "stage8": stage8,
        "stage9": stage9,
        "stage10": stage10,
        "stage11": stage11,
        "stage12": stage12,
        "stage13": stage13,
        "stage14": stage14,
    }


def main() -> int:

    parser = argparse.ArgumentParser(
        description=(
            "Create PSY29 Stage 15 deterministic "
            "29-stock test fixture."
        )
    )

    parser.add_argument(
        "--universe",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--output",
        required=True,
        type=Path,
    )

    args = parser.parse_args()

    symbols = canonical_symbols(
        args.universe
    )

    timestamp = fresh_timestamp()

    rows = build_rows(
        symbols,
        timestamp,
    )

    args.output.mkdir(
        parents=True,
        exist_ok=True,
    )

    for stage, stage_rows in rows.items():

        write_csv(
            args.output
            / f"{stage}.csv",
            stage_rows,
        )

    # Stage 5 is represented as a JSON fixture because
    # Stage 15 only requires its provenance to be preserved.

    profiles = []

    for rank, symbol in enumerate(
        symbols,
        start=1,
    ):

        profiles.append(
            {
                "symbol": symbol,
                "rank": rank,
                "research_provenance": provenance(5),
            }
        )

    write_json(
        args.output
        / "stage5.json",
        {
            "profiles": profiles
        },
    )

    write_json(
        args.output
        / "fixture_metadata.json",
        {
            "stage": 15,
            "version": "1.0",
            "generated_at": timestamp,
            "coverage": 29,
            "symbols": symbols,
            "fresh_fixture": True,
        },
    )

    print(
        "PSY29 STAGE 15 DETERMINISTIC FIXTURE: PASS"
    )

    print(
        f"Canonical coverage: {len(symbols)}/29"
    )

    print(
        f"Fixture timestamp: {timestamp}"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )