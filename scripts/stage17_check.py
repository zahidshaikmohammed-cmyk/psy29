#!/usr/bin/env python3

"""
PSY29 STAGE 17
HARD VALIDATION / CHECKER

Validates:

- Stage 17 schema
- 29/29 coverage
- unique canonical symbols
- allowed state enum
- all nine deterministic states
- safety boundaries
- provenance requirement
- fail-closed validation
- output artifacts

Does NOT generate or authorize trades.
"""

from __future__ import annotations

import argparse
import csv
import json

from pathlib import Path


EXPECTED_STATES = {
    "STABLE",
    "CHANGED",
    "DETERIORATING",
    "EMERGING",
    "INVALIDATED",
    "UNSTABLE",
    "DATA_STALE",
    "DATA_INVALID",
    "PROVENANCE_FAIL",
}


BLOCKED_FIELDS = {
    "TRADE_READY",
    "TRADE_SIGNAL",
    "TRADE_AUTHORIZED",
    "CE",
    "PE",
    "ENTRY",
    "ENTRY_PRICE",
    "STOP_LOSS",
    "TAKE_PROFIT",
    "TARGET",
    "POSITION_SIZE",
    "RISK",
    "CAPITAL_ALLOCATION",
    "ORDER",
    "EXECUTION",
}


def load_json(
    path: Path,
) -> dict:

    if not path.exists():

        raise AssertionError(
            f"Missing required file: {path}"
        )

    with path.open(
        "r",
        encoding="utf-8",
    ) as handle:

        return json.load(handle)


def scan_blocked_fields(
    value,
    path: str = "root",
) -> list[str]:

    violations = []

    if isinstance(
        value,
        dict,
    ):

        for key, child in value.items():

            if (
                str(key).upper()
                in BLOCKED_FIELDS
            ):

                violations.append(
                    f"{path}.{key}"
                )

            violations.extend(
                scan_blocked_fields(
                    child,
                    f"{path}.{key}",
                )
            )

    elif isinstance(
        value,
        list,
    ):

        for index, child in enumerate(
            value
        ):

            violations.extend(
                scan_blocked_fields(
                    child,
                    f"{path}[{index}]",
                )
            )

    return violations


def load_symbols(
    universe_path: Path,
) -> list[str]:

    universe = load_json(
        universe_path
    ).get(
        "universe"
    )

    assert isinstance(
        universe,
        list,
    ), "Canonical universe missing."

    symbols = []

    for item in universe:

        if isinstance(
            item,
            dict,
        ):

            symbol = item.get(
                "symbol"
            )

        else:

            symbol = item

        if symbol is not None:

            symbols.append(
                str(
                    symbol
                )
                .strip()
                .upper()
            )

    assert len(
        symbols
    ) == 29, (
        f"Expected 29 canonical symbols; "
        f"got {len(symbols)}."
    )

    assert len(
        set(symbols)
    ) == 29, (
        "Canonical universe contains duplicates."
    )

    return symbols


def verify_board(
    output_dir: Path,
    canonical_symbols: list[str],
) -> dict:

    board_path = (
        output_dir
        / "PSY29_STAGE17_STABILITY_BOARD.json"
    )

    board = load_json(
        board_path
    )

    assert board.get(
        "stage"
    ) == 17, (
        "Incorrect Stage number."
    )

    assert board.get(
        "version"
    ) == "1.0", (
        "Incorrect Stage 17 version."
    )

    assert board.get(
        "status"
    ) == "LOCKED", (
        "Stage 17 must be LOCKED."
    )

    coverage = board.get(
        "coverage"
    )

    assert coverage == {
        "expected": 29,
        "actual": 29,
        "unique": 29,
    }, (
        "Stage 17 coverage contract failed."
    )

    records = board.get(
        "records"
    )

    assert isinstance(
        records,
        list,
    ), (
        "Stage 17 records missing."
    )

    assert len(
        records
    ) == 29, (
        "Stage 17 must contain exactly 29 records."
    )

    observed_symbols = [
        str(
            record.get(
                "symbol"
            )
        )
        .strip()
        .upper()
        for record in records
    ]

    assert len(
        set(observed_symbols)
    ) == 29, (
        "Stage 17 contains duplicate symbols."
    )

    assert set(
        observed_symbols
    ) == set(
        canonical_symbols
    ), (
        "Stage 17 symbols do not exactly match "
        "the canonical 29."
    )

    for record in records:

        state = record.get(
            "stage17_state"
        )

        assert state in (
            EXPECTED_STATES
        ), (
            f"Invalid Stage 17 state: {state}"
        )

        assert (
            record.get(
                "provenance_complete"
            )
            is True
        ), (
            f"Missing provenance for "
            f"{record.get('symbol')}."
        )

    blocked = scan_blocked_fields(
        board
    )

    assert not blocked, (
        "Forbidden execution fields detected: "
        + ", ".join(blocked)
    )

    return board


def verify_csv(
    output_dir: Path,
) -> None:

    csv_path = (
        output_dir
        / "PSY29_STAGE17_STABILITY_BOARD.csv"
    )

    assert csv_path.exists(), (
        "Stage 17 CSV board is missing."
    )

    with csv_path.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as handle:

        rows = list(
            csv.DictReader(
                handle
            )
        )

    assert len(
        rows
    ) == 29, (
        "Stage 17 CSV must contain 29 records."
    )


def verify_validation_artifact(
    output_dir: Path,
) -> dict:

    validation_path = (
        output_dir
        / "PSY29_STAGE17_VALIDATION.json"
    )

    validation = load_json(
        validation_path
    )

    assert validation.get(
        "stage"
    ) == 17

    assert validation.get(
        "version"
    ) == "1.0"

    assert validation.get(
        "validation_status"
    ) == "PASS", (
        "Stage 17 validation artifact "
        "does not report PASS."
    )

    coverage = validation.get(
        "coverage"
    )

    assert coverage == {
        "expected": 29,
        "actual": 29,
        "unique": 29,
    }

    checks = validation.get(
        "checks"
    )

    assert isinstance(
        checks,
        dict,
    )

    required_checks = {
        "canonical_29",
        "29_29_coverage",
        "unique_symbols",
        "allowed_state_enum",
        "provenance_required",
        "fail_closed",
        "blocked_execution_fields_absent",
        "upstream_modification",
    }

    assert required_checks <= set(
        checks.keys()
    ), (
        "Required Stage 17 validation checks missing."
    )

    assert all(
        checks[key] is True
        for key in required_checks
        if key != "upstream_modification"
    ), (
        "One or more Stage 17 validation checks failed."
    )

    assert (
        checks["upstream_modification"]
        is False
    ), (
        "Stage 17 must not modify upstream stages."
    )

    return validation


def verify_all_nine_states(
    board: dict,
) -> None:

    observed = {
        record["stage17_state"]
        for record in board["records"]
    }

    missing = (
        EXPECTED_STATES
        - observed
    )

    assert not missing, (
        "Deterministic fixture did not exercise "
        "all nine Stage 17 states: "
        + ", ".join(
            sorted(missing)
        )
    )


def main() -> None:

    parser = argparse.ArgumentParser(
        description=(
            "PSY29 Stage 17 HARD VERIFY"
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

    # =====================================================
    # 1. CANONICAL UNIVERSE
    # =====================================================

    canonical_symbols = load_symbols(
        args.universe
    )

    print(
        "CANONICAL 29: PASS"
    )

    # =====================================================
    # 2. BOARD
    # =====================================================

    board = verify_board(
        args.output,
        canonical_symbols,
    )

    print(
        "STAGE 17 BOARD: PASS"
    )

    # =====================================================
    # 3. CSV
    # =====================================================

    verify_csv(
        args.output
    )

    print(
        "STAGE 17 CSV: PASS"
    )

    # =====================================================
    # 4. NINE STATES
    # =====================================================

    verify_all_nine_states(
        board
    )

    print(
        "ALL NINE STATE CLASSES: PASS"
    )

    # =====================================================
    # 5. VALIDATION ARTIFACT
    # =====================================================

    verify_validation_artifact(
        args.output
    )

    print(
        "VALIDATION ARTIFACT: PASS"
    )

    # =====================================================
    # 6. FINAL
    # =====================================================

    print(
        "========================================"
    )

    print(
        "PSY29 STAGE 17 HARD VERIFY: PASS"
    )

    print(
        "29/29 coverage: PASS"
    )

    print(
        "Safety boundary scan: PASS"
    )

    print(
        "Provenance validation: PASS"
    )

    print(
        "Fail-closed validation: PASS"
    )

    print(
        "Upstream modification: BLOCKED"
    )

    print(
        "========================================"
    )


if __name__ == "__main__":

    main()
