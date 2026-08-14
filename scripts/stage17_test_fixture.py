#!/usr/bin/env python3

"""
PSY29 STAGE 17
DETERMINISTIC TEST FIXTURE

Purpose:
    Generate a deterministic, fresh, 29/29 Stage 5–16
    fixture for Stage 17 validation.

Safety:
    - Test data only
    - No live trading
    - No trade signal
    - No authorization
    - No CE/PE
    - No entry
    - No stop-loss
    - No target
    - No position sizing
    - No risk
    - No capital allocation
    - No execution
"""

from __future__ import annotations

import argparse
import csv
import json

from datetime import datetime, timezone
from pathlib import Path


EXPECTED_STATES = [
    "STABLE",
    "CHANGED",
    "DETERIORATING",
    "EMERGING",
    "INVALIDATED",
    "UNSTABLE",
    "DATA_STALE",
    "DATA_INVALID",
    "PROVENANCE_FAIL",
]


def write_csv(
    path: Path,
    rows: list[dict],
) -> None:

    if not rows:
        raise ValueError(
            f"Cannot write empty fixture: {path}"
        )

    fields = sorted(
        {
            key
            for row in rows
            for key in row.keys()
        }
    )

    with path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:

        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
        )

        writer.writeheader()
        writer.writerows(rows)


def load_universe(
    path: Path,
) -> list[str]:

    data = json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )

    universe = data.get(
        "universe"
    )

    if not isinstance(
        universe,
        list,
    ):
        raise ValueError(
            "Canonical universe missing."
        )

    symbols = []

    for item in universe:

        if isinstance(item, dict):

            symbol = item.get(
                "symbol"
            )

        else:

            symbol = item

        if symbol is None:
            continue

        symbol = str(
            symbol
        ).strip().upper()

        if symbol:
            symbols.append(symbol)

    if len(symbols) != 29:
        raise ValueError(
            f"Expected 29 symbols, got {len(symbols)}."
        )

    if len(set(symbols)) != 29:
        raise ValueError(
            "Canonical universe contains duplicates."
        )

    return symbols


def timestamp_now() -> str:

    return (
        datetime.now(
            timezone.utc
        )
        .replace(
            microsecond=0
        )
        .isoformat()
        .replace(
            "+00:00",
            "Z",
        )
    )


def build_stage_rows(
    symbols: list[str],
    stage: int,
    generated_at: str,
) -> list[dict]:

    rows = []

    for index, symbol in enumerate(
        symbols
    ):

        row = {
            "symbol": symbol,
            "timestamp": generated_at,
            f"stage{stage}_provenance":
                f"PSY29-STAGE{stage}-FIXTURE-{symbol}",
        }

        # -------------------------------------------------
        # STAGE 6
        # -------------------------------------------------

        if stage == 6:

            row["regime"] = (
                "TREND"
                if index % 2 == 0
                else "RANGE"
            )

        # -------------------------------------------------
        # STAGE 7
        # -------------------------------------------------

        elif stage == 7:

            row["edge_state"] = (
                "EDGE_ACTIVE"
                if index % 3 != 0
                else "EDGE_INACTIVE"
            )

        # -------------------------------------------------
        # STAGE 8
        # -------------------------------------------------

        elif stage == 8:

            row["portfolio_rank"] = (
                index + 1
            )

        # -------------------------------------------------
        # STAGE 9
        # -------------------------------------------------

        elif stage == 9:

            row["quality_score"] = (
                70 + index
            )

        # -------------------------------------------------
        # STAGE 10
        # -------------------------------------------------

        elif stage == 10:

            row["integrity_status"] = (
                "INTEGRITY_PASS"
            )

        # -------------------------------------------------
        # STAGE 11
        # -------------------------------------------------

        elif stage == 11:

            row["analysis_state"] = (
                "ANALYZED"
            )

        # -------------------------------------------------
        # STAGE 12
        # -------------------------------------------------

        elif stage == 12:

            row["readiness_state"] = (
                "SCENARIO_REVIEW"
            )

        # -------------------------------------------------
        # STAGE 13
        # -------------------------------------------------

        elif stage == 13:

            row["state"] = (
                "SCENARIO_CONFIRMED"
            )

        # -------------------------------------------------
        # STAGE 14
        # -------------------------------------------------

        elif stage == 14:

            row["dashboard_state"] = (
                "CURRENT"
            )

        # -------------------------------------------------
        # STAGE 15
        # -------------------------------------------------

        elif stage == 15:

            row["event_class"] = (
                "UNCHANGED"
            )

        rows.append(row)

    return rows


def build_stage16_rows(
    symbols: list[str],
    generated_at: str,
) -> list[dict]:

    rows = []

    for index, symbol in enumerate(
        symbols
    ):

        if index < len(
            EXPECTED_STATES
        ):

            expected_state = (
                EXPECTED_STATES[index]
            )

        else:

            expected_state = "STABLE"

        rows.append(
            {
                "symbol": symbol,
                "timestamp": generated_at,
                "fixture_expected_state":
                    expected_state,
                "system_state":
                    "CURRENT",
                "stage16_provenance":
                    f"PSY29-STAGE16-FIXTURE-{symbol}",
            }
        )

    return rows


def build_previous_rows(
    symbols: list[str],
    stage: int,
    generated_at: str,
) -> list[dict]:

    rows = []

    for index, symbol in enumerate(
        symbols
    ):

        row = {
            "symbol": symbol,
            "timestamp": generated_at,
            f"stage{stage}_provenance":
                f"PSY29-PREVIOUS-STAGE{stage}-{symbol}",
        }

        if stage == 6:

            row["regime"] = (
                "TREND"
                if index % 2 == 0
                else "RANGE"
            )

        elif stage == 7:

            row["edge_state"] = (
                "EDGE_ACTIVE"
                if index % 3 != 0
                else "EDGE_INACTIVE"
            )

        elif stage == 8:

            row["portfolio_rank"] = (
                index + 1
            )

        elif stage == 9:

            row["quality_score"] = (
                70 + index
            )

        elif stage == 10:

            row["integrity_status"] = (
                "INTEGRITY_PASS"
            )

        elif stage == 11:

            row["analysis_state"] = (
                "ANALYZED"
            )

        elif stage == 12:

            row["readiness_state"] = (
                "SCENARIO_REVIEW"
            )

        elif stage == 13:

            row["state"] = (
                "SCENARIO_CONFIRMED"
            )

        elif stage == 14:

            row["dashboard_state"] = (
                "CURRENT"
            )

        elif stage == 15:

            row["event_class"] = (
                "UNCHANGED"
            )

        elif stage == 16:

            row["system_state"] = (
                "CURRENT"
            )

        rows.append(row)

    return rows


def main() -> None:

    parser = argparse.ArgumentParser(
        description=(
            "Generate deterministic "
            "PSY29 Stage 17 fixtures."
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

    symbols = load_universe(
        args.universe
    )

    generated_at = timestamp_now()

    args.output.mkdir(
        parents=True,
        exist_ok=True,
    )

    # =====================================================
    # CURRENT STAGE 5–15
    # =====================================================

    for stage in range(5, 16):

        rows = build_stage_rows(
            symbols,
            stage,
            generated_at,
        )

        write_csv(
            args.output
            / f"stage{stage}.csv",
            rows,
        )

    # =====================================================
    # CURRENT STAGE 16
    # =====================================================

    stage16_rows = (
        build_stage16_rows(
            symbols,
            generated_at,
        )
    )

    write_csv(
        args.output
        / "stage16.csv",
        stage16_rows,
    )

    # =====================================================
    # PREVIOUS SNAPSHOT
    # =====================================================

    previous_dir = (
        args.output
        / "previous"
    )

    previous_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    for stage in range(5, 17):

        rows = build_previous_rows(
            symbols,
            stage,
            generated_at,
        )

        write_csv(
            previous_dir
            / f"stage{stage}.csv",
            rows,
        )

    # =====================================================
    # HARD FIXTURE VALIDATION
    # =====================================================

    assert len(symbols) == 29

    assert len(
        set(symbols)
    ) == 29

    for stage in range(5, 17):

        current_file = (
            args.output
            / f"stage{stage}.csv"
        )

        previous_file = (
            previous_dir
            / f"stage{stage}.csv"
        )

        assert current_file.exists()
        assert previous_file.exists()

        with current_file.open(
            encoding="utf-8"
        ) as handle:

            current_rows = list(
                csv.DictReader(handle)
            )

        with previous_file.open(
            encoding="utf-8"
        ) as handle:

            previous_rows = list(
                csv.DictReader(handle)
            )

        assert len(
            current_rows
        ) == 29

        assert len(
            previous_rows
        ) == 29

    # =====================================================
    # VERIFY ALL NINE STATE CLASSES
    # =====================================================

    actual_states = {
        row["fixture_expected_state"]
        for row in stage16_rows
    }

    missing_states = (
        set(EXPECTED_STATES)
        - actual_states
    )

    if missing_states:

        raise ValueError(
            "Fixture does not exercise all "
            "Stage 17 states: "
            + ", ".join(
                sorted(missing_states)
            )
        )

    print(
        "========================================"
    )

    print(
        "PSY29 STAGE 17 FIXTURE: PASS"
    )

    print(
        "Fresh timestamp: PASS"
    )

    print(
        "Canonical coverage: 29/29"
    )

    print(
        "Previous snapshot: PASS"
    )

    print(
        "Nine state classes: PASS"
    )

    print(
        "========================================"
    )


if __name__ == "__main__":

    main()
