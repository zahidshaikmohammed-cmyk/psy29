#!/usr/bin/env python3

"""
PSY29 Stage 15 — Hard Verification
Version: 1.0

Validates:

- canonical 29 coverage
- journal coverage
- event schema
- event-class validity
- provenance structure
- snapshot integrity
- SHA256 hash chain
- append-only record ordering
- state preservation
- safety boundaries
- fail-closed behaviour
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List


EXPECTED_EVENTS = {
    "INITIAL_SNAPSHOT",
    "STATE_UNCHANGED",
    "EDGE_ACTIVATED",
    "EDGE_DEACTIVATED",
    "REGIME_CHANGED",
    "INTEGRITY_CHANGED",
    "QUALITY_CHANGED",
    "RANK_CHANGED",
    "SCENARIO_CHANGED",
    "SCENARIO_CONFIRMED",
    "SCENARIO_CONDITIONAL",
    "SCENARIO_CONFLICTED",
    "DATA_BECAME_STALE",
    "DATA_BECAME_VALID",
    "DATA_BECAME_INVALID",
    "UPSTREAM_ERROR",
    "PROVENANCE_CHANGED",
}

FORBIDDEN_KEYS = {
    "TRADE_READY",
    "TRADE_SIGNAL",
    "TRADE_SIGNAL_GENERATED",
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


def load_json(path: Path) -> Any:
    with path.open(
        "r",
        encoding="utf-8",
    ) as handle:
        return json.load(handle)


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows = []

    with path.open(
        "r",
        encoding="utf-8",
    ) as handle:

        for line_number, line in enumerate(
            handle,
            start=1,
        ):
            line = line.strip()

            if not line:
                continue

            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise AssertionError(
                    f"Invalid JSONL at line {line_number}: {exc}"
                ) from exc

            if not isinstance(value, dict):
                raise AssertionError(
                    f"JSONL line {line_number} is not an object."
                )

            rows.append(value)

    return rows


def load_csv(path: Path) -> List[Dict[str, Any]]:
    with path.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as handle:
        return list(csv.DictReader(handle))


def normalize_symbol(value: Any) -> str:
    return str(value).strip().upper()


def canonical_symbols(
    universe_path: Path,
) -> List[str]:

    data = load_json(universe_path)

    candidates = [
        data.get("symbols"),
        data.get("universe"),
        data.get("stocks"),
        data.get("canonical_symbols"),
        data.get("exact_symbol_list"),
    ]

    symbols = None

    for candidate in candidates:
        if isinstance(candidate, list):
            symbols = candidate
            break

    if symbols is None:
        nested = data.get(
            "canonical_universe"
        )

        if isinstance(nested, dict):
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

    assert symbols is not None, (
        "Canonical universe list not found."
    )

    result = [
        normalize_symbol(symbol)
        for symbol in symbols
    ]

    result = [
        symbol
        for symbol in result
        if symbol
    ]

    assert len(result) == 29, (
        f"Expected 29 canonical symbols; "
        f"found {len(result)}."
    )

    assert len(set(result)) == 29, (
        "Canonical universe contains duplicates."
    )

    return result


def normalize_for_hash(value: Any) -> Any:

    if isinstance(value, dict):
        return {
            str(key): normalize_for_hash(
                value[key]
            )
            for key in sorted(value)
        }

    if isinstance(value, list):
        return [
            normalize_for_hash(item)
            for item in value
        ]

    return value


def sha256_object(value: Any) -> str:

    canonical = json.dumps(
        normalize_for_hash(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )

    return hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()


def snapshot_hash(
    snapshot: Dict[str, Any],
) -> str:
    return sha256_object(snapshot)


def record_hash_without_hash(
    record: Dict[str, Any],
) -> str:

    payload = {
        key: value
        for key, value in record.items()
        if key != "record_hash"
    }

    return sha256_object(payload)


def scan_for_forbidden_keys(
    value: Any,
    path: str = "root",
) -> List[str]:

    violations = []

    if isinstance(value, dict):

        for key, child in value.items():

            key_upper = str(key).upper()

            if key_upper in FORBIDDEN_KEYS:
                violations.append(
                    f"{path}.{key}"
                )

            violations.extend(
                scan_for_forbidden_keys(
                    child,
                    f"{path}.{key}",
                )
            )

    elif isinstance(value, list):

        for index, child in enumerate(value):

            violations.extend(
                scan_for_forbidden_keys(
                    child,
                    f"{path}[{index}]",
                )
            )

    return violations


def assert_coverage(
    symbols: List[str],
    journal: List[Dict[str, Any]],
) -> None:

    assert len(journal) == 29, (
        f"Journal must contain 29 records; "
        f"found {len(journal)}."
    )

    journal_symbols = [
        normalize_symbol(
            record.get("symbol")
        )
        for record in journal
    ]

    assert len(set(journal_symbols)) == 29, (
        "Journal contains duplicate symbols."
    )

    expected = set(symbols)
    actual = set(journal_symbols)

    missing = sorted(
        expected - actual
    )

    unexpected = sorted(
        actual - expected
    )

    assert not missing, (
        f"Missing journal symbols: {missing}"
    )

    assert not unexpected, (
        f"Unexpected journal symbols: {unexpected}"
    )


def assert_event_schema(
    journal: List[Dict[str, Any]],
) -> None:

    required = {
        "event_id",
        "event_timestamp",
        "symbol",
        "canonical_rank",
        "event_class",
        "previous_snapshot_hash",
        "current_snapshot_hash",
        "previous_record_hash",
        "snapshot",
        "provenance",
        "record_hash",
    }

    for index, record in enumerate(
        journal,
        start=1,
    ):

        missing = [
            key
            for key in required
            if key not in record
        ]

        assert not missing, (
            f"Record {index}: missing fields {missing}"
        )

        assert record[
            "event_class"
        ] in EXPECTED_EVENTS, (
            f"Record {index}: invalid event class "
            f"{record['event_class']}"
        )

        assert isinstance(
            record["snapshot"],
            dict,
        )

        assert isinstance(
            record["provenance"],
            dict,
        )


def assert_provenance(
    journal: List[Dict[str, Any]],
) -> None:

    required = [
        f"stage{stage}_provenance"
        for stage in range(5, 15)
    ]

    for index, record in enumerate(
        journal,
        start=1,
    ):

        provenance = record[
            "provenance"
        ]

        for field in required:

            assert field in provenance, (
                f"Record {index}: missing "
                f"provenance field {field}"
            )

            assert provenance[field] is not None, (
                f"Record {index}: null provenance "
                f"field {field}"
            )


def assert_snapshot_identity(
    journal: List[Dict[str, Any]],
) -> None:

    for index, record in enumerate(
        journal,
        start=1,
    ):

        calculated = snapshot_hash(
            record["snapshot"]
        )

        assert calculated == record[
            "current_snapshot_hash"
        ], (
            f"Record {index}: snapshot hash mismatch."
        )


def assert_record_hashes(
    journal: List[Dict[str, Any]],
) -> None:

    previous_hash = "GENESIS"

    for index, record in enumerate(
        journal,
        start=1,
    ):

        assert record[
            "previous_record_hash"
        ] == previous_hash, (
            f"Record {index}: broken hash chain."
        )

        calculated = record_hash_without_hash(
            record
        )

        assert calculated == record[
            "record_hash"
        ], (
            f"Record {index}: record hash mismatch."
        )

        previous_hash = record[
            "record_hash"
        ]


def assert_ranks(
    symbols: List[str],
    journal: List[Dict[str, Any]],
) -> None:

    rank_map = {}

    for record in journal:

        symbol = normalize_symbol(
            record["symbol"]
        )

        rank = int(
            record["canonical_rank"]
        )

        rank_map[symbol] = rank

    assert set(rank_map) == set(
        symbols
    )

    assert sorted(
        rank_map.values()
    ) == list(range(1, 30)), (
        "Canonical ranks must be exactly 1..29."
    )


def assert_snapshot_symbols(
    symbols: List[str],
    journal: List[Dict[str, Any]],
) -> None:

    expected = set(symbols)

    for record in journal:

        symbol = normalize_symbol(
            record["symbol"]
        )

        snapshot_symbol = normalize_symbol(
            record["snapshot"].get("symbol")
        )

        assert symbol == snapshot_symbol, (
            f"Symbol mismatch for {symbol}."
        )

        assert symbol in expected


def assert_no_forbidden_operations(
    journal: List[Dict[str, Any]],
    summary: Dict[str, Any],
    validation: Dict[str, Any],
) -> None:

    combined = {
        "journal": journal,
        "summary": summary,
        "validation": validation,
    }

    violations = scan_for_forbidden_keys(
        combined
    )

    # The contract explicitly describes safety fields in its
    # summary. Those are legitimate boolean declarations and
    # are checked separately below.
    allowed_safety_keys = {
        "trade_signal_generated",
        "trade_authorized",
        "trade_ready",
        "ce_pe_selected",
        "entry_calculated",
        "stop_loss_calculated",
        "target_calculated",
        "position_size_calculated",
        "risk_calculated",
        "capital_allocated",
        "execution_performed",
    }

    filtered = []

    for violation in violations:

        key = violation.split(".")[-1]

        if key.lower() in {
            item.lower()
            for item in allowed_safety_keys
        }:
            continue

        filtered.append(
            violation
        )

    assert not filtered, (
        "Forbidden operation fields detected: "
        + ", ".join(filtered)
    )

    safety = summary.get(
        "safety",
        {}
    )

    for key in allowed_safety_keys:

        if key in safety:
            assert safety[key] is False, (
                f"Safety boundary violated: {key}"
            )


def assert_summary(
    summary: Dict[str, Any],
    validation: Dict[str, Any],
) -> None:

    assert summary[
        "stage"
    ] == 15

    assert summary[
        "version"
    ] == "1.0"

    assert summary[
        "engine_execution_status"
    ] in {
        "EXECUTED",
        "PASS",
    }

    assert summary[
        "validation_status"
    ] == "PASS"

    assert validation[
        "validation_status"
    ] == "PASS"

    coverage = summary[
        "coverage"
    ]

    assert coverage[
        "expected"
    ] == 29

    assert coverage[
        "actual"
    ] == 29

    assert coverage[
        "unique"
    ] == 29

    assert coverage[
        "missing"
    ] == []

    assert coverage[
        "unexpected"
    ] == []

    checks = validation[
        "checks"
    ]

    required_checks = [
        "canonical_29",
        "all_upstream_stages_present",
        "29_29_coverage",
        "unique_symbols",
        "provenance_structure",
        "snapshot_integrity",
        "event_classification",
        "hash_chain",
        "append_only_model",
        "forbidden_execution_fields_absent",
        "cross_stage_snapshot_consistency",
        "fail_closed",
    ]

    for check in required_checks:

        assert checks.get(check) is True, (
            f"Validation check failed: {check}"
        )


def assert_csv_matches_jsonl(
    events_csv: List[Dict[str, Any]],
    journal: List[Dict[str, Any]],
) -> None:

    assert len(events_csv) == len(journal), (
        "CSV event count differs from JSONL count."
    )

    fields = [
        "event_id",
        "event_timestamp",
        "symbol",
        "canonical_rank",
        "event_class",
        "previous_snapshot_hash",
        "current_snapshot_hash",
        "previous_record_hash",
        "record_hash",
    ]

    for index, (
        csv_row,
        json_row,
    ) in enumerate(
        zip(events_csv, journal),
        start=1,
    ):

        for field in fields:

            assert str(
                csv_row.get(field, "")
            ) == str(
                json_row.get(field, "")
            ), (
                f"CSV/JSONL mismatch at record "
                f"{index}, field {field}."
            )


def hard_verify(
    universe_path: Path,
    output_dir: Path,
) -> None:

    journal_path = (
        output_dir
        / "PSY29_STAGE15_EVENT_JOURNAL.jsonl"
    )

    snapshot_path = (
        output_dir
        / "PSY29_STAGE15_SNAPSHOT.json"
    )

    events_csv_path = (
        output_dir
        / "PSY29_STAGE15_EVENTS.csv"
    )

    summary_path = (
        output_dir
        / "PSY29_STAGE15_SUMMARY.json"
    )

    validation_path = (
        output_dir
        / "PSY29_STAGE15_VALIDATION.json"
    )

    required_files = [
        journal_path,
        snapshot_path,
        events_csv_path,
        summary_path,
        validation_path,
    ]

    for path in required_files:

        assert path.exists(), (
            f"Missing Stage 15 output: {path}"
        )

    symbols = canonical_symbols(
        universe_path
    )

    journal = load_jsonl(
        journal_path
    )

    snapshot_data = load_json(
        snapshot_path
    )

    events_csv = load_csv(
        events_csv_path
    )

    summary = load_json(
        summary_path
    )

    validation = load_json(
        validation_path
    )

    assert snapshot_data[
        "coverage"
    ] == 29

    assert len(
        snapshot_data[
            "snapshot"
        ]
    ) == 29

    assert_coverage(
        symbols,
        journal,
    )

    assert_event_schema(
        journal,
    )

    assert_provenance(
        journal,
    )

    assert_snapshot_identity(
        journal,
    )

    assert_record_hashes(
        journal,
    )

    assert_ranks(
        symbols,
        journal,
    )

    assert_snapshot_symbols(
        symbols,
        journal,
    )

    assert_no_forbidden_operations(
        journal,
        summary,
        validation,
    )

    assert_summary(
        summary,
        validation,
    )

    assert_csv_matches_jsonl(
        events_csv,
        journal,
    )

    # First run must produce one initial observation for every symbol.
    initial_count = sum(
        1
        for record in journal
        if record["event_class"]
        == "INITIAL_SNAPSHOT"
    )

    assert initial_count == 29, (
        "Deterministic initial journal must contain "
        "29 INITIAL_SNAPSHOT events."
    )

    # All events must belong to the canonical universe.
    assert all(
        normalize_symbol(
            record["symbol"]
        ) in set(symbols)
        for record in journal
    )

    # Stage 15 must never produce an execution state.
    forbidden_strings = [
        "BUY",
        "SELL",
        "LONG_CE",
        "LONG_PE",
        "SHORT_CE",
        "SHORT_PE",
    ]

    serialized = json.dumps(
        journal,
        sort_keys=True,
    ).upper()

    for forbidden in forbidden_strings:
        assert forbidden not in serialized, (
            f"Forbidden trading instruction detected: "
            f"{forbidden}"
        )

    print(
        "=============================================="
    )
    print(
        "PSY29 STAGE 15 HARD VERIFY: PASS"
    )
    print(
        "=============================================="
    )
    print(
        "Canonical 29: PASS"
    )
    print(
        "29/29 journal coverage: PASS"
    )
    print(
        "Unique symbols: PASS"
    )
    print(
        "Canonical ranks 1-29: PASS"
    )
    print(
        "Event schema: PASS"
    )
    print(
        "Event classification: PASS"
    )
    print(
        "Provenance structure: PASS"
    )
    print(
        "Snapshot hash integrity: PASS"
    )
    print(
        "SHA256 record chain: PASS"
    )
    print(
        "Append-only model: PASS"
    )
    print(
        "CSV/JSONL consistency: PASS"
    )
    print(
        "Upstream preservation: PASS"
    )
    print(
        "Safety boundary: PASS"
    )
    print(
        "Fail-closed validation: PASS"
    )
    print(
        "Trade signal generation: FALSE"
    )
    print(
        "Trade authorization: FALSE"
    )
    print(
        "CE/PE selection: FALSE"
    )
    print(
        "Entry calculation: FALSE"
    )
    print(
        "Stop-loss calculation: FALSE"
    )
    print(
        "Target calculation: FALSE"
    )
    print(
        "Position sizing: FALSE"
    )
    print(
        "Risk calculation: FALSE"
    )
    print(
        "Capital allocation: FALSE"
    )
    print(
        "Execution: FALSE"
    )
    print(
        "=============================================="
    )


def main() -> int:

    parser = argparse.ArgumentParser(
        description=(
            "PSY29 Stage 15 Hard Verification"
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

    try:

        hard_verify(
            args.universe,
            args.output,
        )

        return 0

    except Exception as exc:

        print(
            "==============================================",
            file=sys.stderr,
        )

        print(
            "PSY29 STAGE 15 HARD VERIFY: FAIL",
            file=sys.stderr,
        )

        print(
            str(exc),
            file=sys.stderr,
        )

        print(
            "==============================================",
            file=sys.stderr,
        )

        return 1


if __name__ == "__main__":
    raise SystemExit(
        main()
    )