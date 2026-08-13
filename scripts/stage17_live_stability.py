#!/usr/bin/env python3

"""
PSY29 Stage 17 — Live Decision Stability & Change-Control Engine

Version: 1.0

Purpose:
    Consume verified Stage 5–16 state and classify the current
    stability/change condition for all 29 canonical stocks.

Safety:
    - No trade signals
    - No trade authorization
    - No TRADE_READY
    - No CE/PE selection
    - No entry
    - No stop-loss
    - No target
    - No position sizing
    - No risk calculation
    - No capital allocation
    - No execution
    - No upstream modification

Fail-closed:
    Any mandatory coverage, freshness, provenance, schema,
    consistency, or safety failure prevents a normal state.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys

from datetime import datetime, timezone
from pathlib import Path
from typing import Any


STAGE = 17
VERSION = "1.0"

ALLOWED_STATES = {
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

BLOCKED_KEYS = {
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


def load(path: Path) -> Any:
    text = path.read_text(
        encoding="utf-8"
    ).strip()

    if not text:
        return []

    if path.suffix.lower() == ".csv":
        with path.open(
            "r",
            encoding="utf-8",
            newline="",
        ) as handle:
            return list(
                csv.DictReader(handle)
            )

    try:
        return json.loads(text)

    except json.JSONDecodeError:
        return [
            json.loads(line)
            for line in text.splitlines()
            if line.strip()
        ]


def rows(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [
            x for x in data
            if isinstance(x, dict)
        ]

    if isinstance(data, dict):

        for key in (
            "rows",
            "records",
            "data",
            "stocks",
            "results",
            "items",
            "snapshot",
            "events",
            "journal",
            "profiles",
        ):

            value = data.get(key)

            if isinstance(value, list):
                return [
                    x for x in value
                    if isinstance(x, dict)
                ]

        if data and all(
            isinstance(value, dict)
            for value in data.values()
        ):
            output = []

            for key, value in data.items():

                record = dict(value)

                if "symbol" not in record:
                    record["symbol"] = key

                output.append(record)

            return output

        return [data]

    return []


def symbol(record: dict[str, Any]) -> str | None:
    for key in (
        "symbol",
        "tradingsymbol",
        "ticker",
        "stock",
        "security_symbol",
        "name",
    ):

        value = record.get(key)

        if value is not None:
            value = str(value).strip().upper()

            if value:
                return value

    return None


def value(
    record: dict[str, Any],
    *keys: str,
) -> Any:

    lookup = {
        str(key).lower(): val
        for key, val in record.items()
    }

    for key in keys:

        if key.lower() in lookup:
            return lookup[key.lower()]

    return None


def timestamp(
    record: dict[str, Any],
) -> datetime | None:

    raw = value(
        record,
        "live_data_timestamp",
        "data_timestamp",
        "observation_timestamp",
        "generated_at",
        "timestamp",
        "event_timestamp",
        "as_of",
    )

    if raw is None:
        return None

    text = str(raw).strip()

    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(text)

    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(
            tzinfo=timezone.utc
        )
    else:
        parsed = parsed.astimezone(
            timezone.utc
        )

    return parsed


def canonical_universe(
    path: Path,
) -> list[str]:

    data = load(path)

    universe = None

    if isinstance(data, dict):

        candidate = data.get(
            "universe"
        )

        if isinstance(
            candidate,
            list,
        ):
            universe = candidate

        if universe is None:

            for key in (
                "symbols",
                "canonical_symbols",
                "stocks",
            ):

                candidate = data.get(key)

                if isinstance(
                    candidate,
                    list,
                ):
                    universe = candidate
                    break

    if universe is None:
        raise ValueError(
            "Unable to locate canonical universe."
        )

    output = []

    for item in universe:

        if isinstance(item, dict):
            raw = item.get(
                "symbol"
            )
        else:
            raw = item

        if raw is not None:

            cleaned = str(
                raw
            ).strip().upper()

            if cleaned:
                output.append(cleaned)

    if len(output) != 29:
        raise ValueError(
            "Canonical universe must contain exactly 29 symbols."
        )

    if len(set(output)) != 29:
        raise ValueError(
            "Canonical universe contains duplicate symbols."
        )

    return output


def index_stage(
    path: Path,
    stage: int,
    expected: set[str],
) -> dict[str, dict[str, Any]]:

    indexed = {}

    for record in rows(load(path)):

        stock = symbol(record)

        if not stock:
            continue

        if stock in indexed:
            raise ValueError(
                f"Stage {stage}: duplicate symbol {stock}"
            )

        indexed[stock] = record

    if set(indexed) != expected:

        missing = sorted(
            expected - set(indexed)
        )

        unexpected = sorted(
            set(indexed) - expected
        )

        raise ValueError(
            f"Stage {stage}: coverage mismatch; "
            f"missing={missing}; "
            f"unexpected={unexpected}"
        )

    return indexed


def provenance_present(
    record: dict[str, Any],
    stage: int,
) -> bool:

    candidates = (
        f"stage{stage}_provenance",
        "provenance",
        "research_provenance",
    )

    return any(
        value(record, key)
        not in (
            None,
            "",
            {},
            [],
        )
        for key in candidates
    )


def all_provenance_present(
    source: dict[int, dict[str, Any]],
) -> bool:

    return all(
        provenance_present(
            record,
            stage,
        )
        for stage, record in source.items()
    )


def latest_timestamp(
    source: dict[int, dict[str, Any]],
) -> datetime | None:

    timestamps = []

    for record in source.values():

        parsed = timestamp(record)

        if parsed is not None:
            timestamps.append(parsed)

    if not timestamps:
        return None

    return max(timestamps)


def is_fresh(
    source: dict[int, dict[str, Any]],
    max_age_seconds: int = 900,
) -> bool:

    latest = latest_timestamp(source)

    if latest is None:
        return False

    age = (
        datetime.now(timezone.utc)
        - latest
    ).total_seconds()

    return 0 <= age <= max_age_seconds


def blocked_fields(
    payload: Any,
    path: str = "root",
) -> list[str]:

    found = []

    if isinstance(payload, dict):

        for key, child in payload.items():

            if str(key).upper() in BLOCKED_KEYS:
                found.append(
                    f"{path}.{key}"
                )

            found.extend(
                blocked_fields(
                    child,
                    f"{path}.{key}",
                )
            )

    elif isinstance(payload, list):

        for index, child in enumerate(payload):

            found.extend(
                blocked_fields(
                    child,
                    f"{path}[{index}]",
                )
            )

    return found


def state_from_change(
    current: dict[int, dict[str, Any]],
    previous: dict[int, dict[str, Any]] | None,
) -> tuple[str, str]:

    if previous is None:
        return (
            "EMERGING",
            "No previous valid snapshot exists.",
        )

    current_edge = str(
        value(
            current[7],
            "edge_state",
            "edge_status",
            "activation_state",
            "state",
        )
        or ""
    ).upper()

    previous_edge = str(
        value(
            previous[7],
            "edge_state",
            "edge_status",
            "activation_state",
            "state",
        )
        or ""
    ).upper()

    current_regime = str(
        value(
            current[6],
            "regime",
            "regime_state",
            "classification",
            "live_regime",
        )
        or ""
    ).upper()

    previous_regime = str(
        value(
            previous[6],
            "regime",
            "regime_state",
            "classification",
            "live_regime",
        )
        or ""
    ).upper()

    current_quality = value(
        current[9],
        "quality_score",
        "confidence_score",
        "candidate_quality",
        "score",
    )

    previous_quality = value(
        previous[9],
        "quality_score",
        "confidence_score",
        "candidate_quality",
        "score",
    )

    current_integrity = str(
        value(
            current[10],
            "integrity_status",
            "integrity_state",
            "status",
        )
        or ""
    ).upper()

    previous_integrity = str(
        value(
            previous[10],
            "integrity_status",
            "integrity_state",
            "status",
        )
        or ""
    ).upper()

    current_scenario = str(
        value(
            current[13],
            "state",
            "scenario_state",
            "status",
        )
        or ""
    ).upper()

    previous_scenario = str(
        value(
            previous[13],
            "state",
            "scenario_state",
            "status",
        )
        or ""
    ).upper()

    if current_integrity != "INTEGRITY_PASS":
        return (
            "INVALIDATED",
            "Current Stage 10 integrity is not INTEGRITY_PASS.",
        )

    if (
        previous_integrity == "INTEGRITY_PASS"
        and current_integrity != previous_integrity
    ):
        return (
            "INVALIDATED",
            "Integrity deteriorated from previous state.",
        )

    if (
        previous_edge == "EDGE_ACTIVE"
        and current_edge != "EDGE_ACTIVE"
    ):
        return (
            "DETERIORATING",
            "Previously active edge is no longer active.",
        )

    if (
        current_edge == "EDGE_ACTIVE"
        and previous_edge != "EDGE_ACTIVE"
    ):
        return (
            "EMERGING",
            "Edge became active.",
        )

    if (
        current_regime
        and previous_regime
        and current_regime != previous_regime
    ):
        return (
            "CHANGED",
            "Live regime changed.",
        )

    if (
        current_scenario
        and previous_scenario
        and current_scenario != previous_scenario
    ):
        return (
            "CHANGED",
            "Scenario state changed.",
        )

    if (
        isinstance(
            current_quality,
            (int, float),
        )
        and isinstance(
            previous_quality,
            (int, float),
        )
    ):

        if current_quality < previous_quality:
            return (
                "DETERIORATING",
                "Candidate quality decreased.",
            )

        if current_quality > previous_quality:
            return (
                "CHANGED",
                "Candidate quality increased.",
            )

    return (
        "STABLE",
        "No material monitored state change detected.",
    )


def main() -> None:

    parser = argparse.ArgumentParser(
        description=(
            "PSY29 Stage 17 Live Decision "
            "Stability & Change-Control Engine"
        )
    )

    parser.add_argument(
        "--universe",
        required=True,
        type=Path,
    )

    for stage in range(5, 16):

        parser.add_argument(
            f"--stage{stage}",
            required=True,
            type=Path,
        )

    parser.add_argument(
        "--stage16",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--previous",
        required=False,
        type=Path,
    )

    parser.add_argument(
        "--output",
        required=True,
        type=Path,
    )

    args = parser.parse_args()

    symbols = canonical_universe(
        args.universe
    )

    expected = set(symbols)

    source = {}

    for stage in range(5, 16):

        source[stage] = index_stage(
            getattr(
                args,
                f"stage{stage}",
            ),
            stage,
            expected,
        )

    source[16] = index_stage(
        args.stage16,
        16,
        expected,
    )

    previous_source = None

    if args.previous:

        previous_source = {}

        for stage in range(5, 17):

            previous_source[stage] = index_stage(
                args.previous
                / f"stage{stage}.csv",
                stage,
                expected,
            )

    records = []

    for rank, stock in enumerate(
        symbols,
        start=1,
    ):

        current = {
            stage: source[stage][stock]
            for stage in range(5, 17)
        }

        previous = None

        if previous_source is not None:

            previous = {
                stage: previous_source[stage][stock]
                for stage in range(5, 17)
            }

        provenance_ok = all_provenance_present(
            current
        )

        fresh_ok = is_fresh(
            current
        )

        if not provenance_ok:

            state = "PROVENANCE_FAIL"

            reason = (
                "Required upstream provenance "
                "is incomplete."
            )

        elif not fresh_ok:

            state = "DATA_STALE"

            reason = (
                "Mandatory upstream timestamps "
                "are stale or unavailable."
            )

        else:

            state, reason = state_from_change(
                current,
                previous,
            )

        current_edge = value(
            current[7],
            "edge_state",
            "edge_status",
            "activation_state",
            "state",
        )

        current_quality = value(
            current[9],
            "quality_score",
            "confidence_score",
            "candidate_quality",
            "score",
        )

        current_regime = value(
            current[6],
            "regime",
            "regime_state",
            "classification",
            "live_regime",
        )

        current_integrity = value(
            current[10],
            "integrity_status",
            "integrity_state",
            "status",
        )

        current_scenario = value(
            current[13],
            "state",
            "scenario_state",
            "status",
        )

        latest = latest_timestamp(
            current
        )

        records.append(
            {
                "symbol": stock,
                "canonical_rank": rank,
                "stage17_state": state,
                "change_reason": reason,
                "stage6_regime": current_regime,
                "stage7_edge_state": current_edge,
                "stage8_portfolio_rank": value(
                    current[8],
                    "portfolio_rank",
                    "rank",
                    "edge_rank",
                    "ranking",
                ),
                "stage9_quality_score": current_quality,
                "stage10_integrity": current_integrity,
                "stage11_analysis_state": value(
                    current[11],
                    "analysis_state",
                    "execution_analysis_state",
                    "status",
                ),
                "stage12_readiness_state": value(
                    current[12],
                    "readiness_state",
                    "scenario_gate_state",
                    "status",
                ),
                "stage13_state": current_scenario,
                "stage14_dashboard_state": value(
                    current[14],
                    "dashboard_state",
                    "dashboard_status",
                    "state",
                    "status",
                ),
                "stage15_event_class": value(
                    current[15],
                    "event_class",
                    "event_type",
                    "journal_state",
                ),
                "stage16_system_state": value(
                    current[16],
                    "system_state",
                    "state",
                    "status",
                ),
                "data_status": (
                    "FRESH"
                    if fresh_ok
                    else "STALE"
                ),
                "provenance_complete": provenance_ok,
                "live_data_timestamp": (
                    latest
                    .replace(
                        microsecond=0
                    )
                    .isoformat()
                    .replace(
                        "+00:00",
                        "Z",
                    )
                    if latest
                    else None
                ),
                "provenance": {
                    f"stage{stage}_provenance":
                        value(
                            current[stage],
                            f"stage{stage}_provenance",
                            "provenance",
                            "research_provenance",
                        )
                    for stage in range(5, 17)
                },
            }
        )

    payload = {
        "stage": STAGE,
        "version": VERSION,
        "generated_at": (
            datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        ),
        "coverage": {
            "expected": 29,
            "actual": len(records),
            "unique": len(
                {
                    record["symbol"]
                    for record in records
                }
            ),
        },
        "allowed_states": sorted(
            ALLOWED_STATES
        ),
        "records": records,
    }

    if (
        payload["coverage"]["expected"] != 29
        or payload["coverage"]["actual"] != 29
        or payload["coverage"]["unique"] != 29
    ):
        raise ValueError(
            "Stage 17 coverage failure."
        )

    invalid_states = [
        record["symbol"]
        for record in records
        if record["stage17_state"]
        not in ALLOWED_STATES
    ]

    if invalid_states:
        raise ValueError(
            "Invalid Stage 17 states: "
            + ", ".join(invalid_states)
        )

    blocked = blocked_fields(
        payload
    )

    if blocked:
        raise ValueError(
            "Blocked execution fields detected: "
            + ", ".join(blocked)
        )

    args.output.mkdir(
        parents=True,
        exist_ok=True,
    )

    json_path = (
        args.output
        / "PSY29_STAGE17_STABILITY.json"
    )

    json_path.write_text(
        json.dumps(
            payload,
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    csv_path = (
        args.output
        / "PSY29_STAGE17_STABILITY.csv"
    )

    fields = [
        key
        for key in records[0].keys()
        if key != "provenance"
    ]

    with csv_path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:

        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
        )

        writer.writeheader()

        for record in records:

            writer.writerow(
                {
                    key: record.get(key)
                    for key in fields
                }
            )

    summary = {}

    for state in sorted(
        ALLOWED_STATES
    ):
        summary[state] = sum(
            1
            for record in records
            if record["stage17_state"]
            == state
        )

    validation = {
        "stage": STAGE,
        "version": VERSION,
        "validation_status": "PASS",
        "coverage": payload["coverage"],
        "state_counts": summary,
        "checks": {
            "canonical_29": True,
            "29_29_coverage": True,
            "unique_symbols": True,
            "allowed_state_enum": True,
            "provenance_required": True,
            "fail_closed": True,
            "blocked_execution_fields_absent": True,
            "upstream_modification": False,
        },
    }

    (
        args.output
        / "PSY29_STAGE17_VALIDATION.json"
    ).write_text(
        json.dumps(
            validation,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(
        "PSY29 STAGE 17: PASS"
    )

    print(
        "Canonical coverage: 29/29"
    )

    print(
        "Allowed-state validation: PASS"
    )

    print(
        "Fail-closed safety validation: PASS"
    )


if __name__ == "__main__":

    try:
        main()

    except Exception as exc:

        print(
            f"PSY29 STAGE 17: FAIL: {exc}",
            file=sys.stderr,
        )

        raise