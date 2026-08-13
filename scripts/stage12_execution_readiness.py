#!/usr/bin/env python3

"""
PSY29 Stage 12 — Live Execution Readiness & Scenario Gate

Purpose:
    Evaluate whether each canonical stock has a sufficiently coherent,
    fresh, research-aligned live execution scenario for downstream
    decision evaluation.

Hard boundary:
    Stage 12 is NOT a trading engine.

It must never:
    - generate trade signals
    - authorize trades
    - output TRADE_READY
    - select CE/PE
    - calculate entry
    - calculate stop-loss
    - calculate target
    - calculate position size
    - calculate risk
    - allocate capital
    - generate orders
    - execute orders
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd


# ============================================================
# LOCKED STATES
# ============================================================

STAGE12_STATES = {
    "EXECUTION_SCENARIO_READY",
    "EXECUTION_SCENARIO_CONDITIONAL",
    "EXECUTION_SCENARIO_BLOCKED",
    "DATA_STALE",
    "DATA_INVALID",
    "UPSTREAM_INVALID",
}

SCENARIO_STATES = {
    "CONTINUATION_SCENARIO",
    "BREAKOUT_SCENARIO",
    "BREAKDOWN_SCENARIO",
    "RETEST_SCENARIO",
    "REVERSAL_RISK_SCENARIO",
    "RANGE_SCENARIO",
    "TRANSITION_SCENARIO",
    "UNCLEAR_SCENARIO",
}

MATCH_STATES = {
    "STRONG_MATCH",
    "PARTIAL_MATCH",
    "WEAK_MATCH",
    "NO_MATCH",
    "UNCONFIRMED",
}

ENVIRONMENT_STATES = {
    "HIGH",
    "MODERATE",
    "LOW",
    "INVALID",
}

QUALITY_STATES = {
    "HIGH",
    "MODERATE",
    "LOW",
    "UNCONFIRMED",
}


# ============================================================
# SAFETY CONSTANTS
# ============================================================

FORCED_FALSE_FIELDS = {
    "trade_ready_output",
    "trade_authorized",
    "trade_signal_generated",
    "ce_pe_selection",
    "entry_calculation",
    "stop_loss_calculation",
    "target_calculation",
    "position_size_calculation",
    "risk_calculation",
    "capital_allocation",
    "order_generation",
    "execution",
}


# ============================================================
# REQUIRED INPUT FIELDS
# ============================================================

STAGE6_REQUIRED = {
    "symbol",
    "regime",
    "data_status",
}

STAGE7_REQUIRED = {
    "symbol",
    "regime",
    "data_status",
    "activation",
    "reason_code",
}

STAGE8_REQUIRED = {
    "symbol",
    "activation",
    "regime",
    "data_status",
    "portfolio_rank",
    "ranking_score",
}

STAGE9_REQUIRED = {
    "symbol",
    "activation",
    "regime",
    "data_status",
    "candidate_quality_score",
}

STAGE10_REQUIRED = {
    "symbol",
    "integrity_state",
    "activation",
    "regime",
    "data_status",
    "research_provenance",
    "stage6_provenance",
    "stage7_provenance",
    "stage8_provenance",
    "stage9_provenance",
}

STAGE11_REQUIRED = {
    "symbol",
    "analysis_state",
    "structure_state",
    "price_volume_quality",
    "event_state",
    "research_live_alignment",
    "live_data_timestamp",
    "research_provenance",
    "stage6_provenance",
    "stage7_provenance",
    "stage8_provenance",
    "stage9_provenance",
    "stage10_provenance",
    "stage11_provenance",
}


# ============================================================
# HELPERS
# ============================================================

def load_json(path: str | Path) -> dict[str, Any]:
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(
            f"Required JSON file does not exist: {path}"
        )

    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


def normalize_symbol(value: Any) -> str:
    return (
        str(value)
        .upper()
        .strip()
    )


def load_table(
    path: str | Path,
    name: str,
    required_fields: set[str],
    canonical_symbols: set[str],
) -> pd.DataFrame:

    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(
            f"{name} output missing: {path}"
        )

    dataframe = pd.read_csv(path)

    missing = (
        required_fields
        - set(dataframe.columns)
    )

    if missing:
        raise ValueError(
            f"{name} missing required fields: "
            f"{sorted(missing)}"
        )

    dataframe["symbol"] = (
        dataframe["symbol"]
        .map(normalize_symbol)
    )

    if len(dataframe) != 29:
        raise ValueError(
            f"{name} must contain exactly 29 rows; "
            f"got {len(dataframe)}"
        )

    if dataframe["symbol"].nunique() != 29:
        raise ValueError(
            f"{name} contains duplicate symbols"
        )

    actual_symbols = set(
        dataframe["symbol"]
    )

    if actual_symbols != canonical_symbols:

        missing_symbols = sorted(
            canonical_symbols
            - actual_symbols
        )

        unexpected_symbols = sorted(
            actual_symbols
            - canonical_symbols
        )

        raise ValueError(
            f"{name} canonical universe mismatch: "
            f"missing={missing_symbols}; "
            f"unexpected={unexpected_symbols}"
        )

    return dataframe.set_index(
        "symbol"
    )


def load_canonical_universe(
    path: str | Path,
) -> tuple[list[str], dict[str, int]]:

    data = load_json(path)

    rows = data.get(
        "universe"
    )

    if not isinstance(rows, list):
        raise ValueError(
            "Canonical universe is missing "
            "the universe list"
        )

    if len(rows) != 29:
        raise ValueError(
            "Canonical universe must contain "
            f"exactly 29 stocks; got {len(rows)}"
        )

    symbols = [
        normalize_symbol(
            row.get("symbol")
        )
        for row in rows
    ]

    ranks = [
        int(
            row.get("rank")
        )
        for row in rows
    ]

    if any(
        not symbol
        for symbol in symbols
    ):
        raise ValueError(
            "Canonical universe contains "
            "an empty symbol"
        )

    if len(set(symbols)) != 29:
        raise ValueError(
            "Canonical universe contains "
            "duplicate symbols"
        )

    if ranks != list(
        range(1, 30)
    ):
        raise ValueError(
            "Canonical universe ranks "
            "must be exactly 1-29"
        )

    return (
        symbols,
        {
            symbol: rank
            for symbol, rank
            in zip(symbols, ranks)
        },
    )


def validate_stage5_profiles(
    path: str | Path,
    canonical_symbols: set[str],
) -> dict[str, dict[str, Any]]:

    data = load_json(path)

    profiles = data.get(
        "profiles"
    )

    if not isinstance(
        profiles,
        list,
    ):
        raise ValueError(
            "Stage 5 profiles list is missing"
        )

    if len(profiles) != 29:
        raise ValueError(
            "Stage 5 must contain "
            "exactly 29 profiles"
        )

    profile_map = {}

    for profile in profiles:

        symbol = normalize_symbol(
            profile.get("symbol")
        )

        if not symbol:
            raise ValueError(
                "Stage 5 contains an empty symbol"
            )

        if symbol in profile_map:
            raise ValueError(
                f"Duplicate Stage 5 profile: "
                f"{symbol}"
            )

        profile_map[symbol] = profile

    if set(profile_map) != canonical_symbols:
        raise ValueError(
            "Stage 5 profile universe does "
            "not match canonical universe"
        )

    return profile_map


def require_nonempty(
    value: Any,
    field_name: str,
) -> None:

    if (
        value is None
        or str(value).strip() == ""
        or str(value).strip().lower()
        in {"nan", "none"}
    ):
        raise ValueError(
            f"Missing provenance/value: "
            f"{field_name}"
        )


# ============================================================
# MODULE 12A
# UPSTREAM ELIGIBILITY
# ============================================================

def evaluate_upstream_eligibility(
    stage6: pd.Series,
    stage7: pd.Series,
    stage8: pd.Series,
    stage9: pd.Series,
    stage10: pd.Series,
    stage11: pd.Series,
) -> tuple[
    str,
    list[str],
]:

    reasons = []

    integrity_state = (
        str(
            stage10["integrity_state"]
        )
        .strip()
        .upper()
    )

    stage11_state = (
        str(
            stage11["analysis_state"]
        )
        .strip()
        .upper()
    )

    stage6_status = (
        str(
            stage6["data_status"]
        )
        .strip()
        .upper()
    )

    stage7_status = (
        str(
            stage7["data_status"]
        )
        .strip()
        .upper()
    )

    stage8_status = (
        str(
            stage8["data_status"]
        )
        .strip()
        .upper()
    )

    stage9_status = (
        str(
            stage9["data_status"]
        )
        .strip()
        .upper()
    )

    if integrity_state == "DATA_STALE":
        return (
            "DATA_STALE",
            [
                "Stage 10 integrity state is DATA_STALE"
            ],
        )

    if integrity_state == "DATA_INVALID":
        return (
            "DATA_INVALID",
            [
                "Stage 10 integrity state is DATA_INVALID"
            ],
        )

    if integrity_state != "INTEGRITY_PASS":
        return (
            "UPSTREAM_INVALID",
            [
                "Stage 10 integrity state is not INTEGRITY_PASS"
            ],
        )

    if stage11_state == "DATA_STALE":
        return (
            "DATA_STALE",
            [
                "Stage 11 analysis state is DATA_STALE"
            ],
        )

    if stage11_state == "DATA_INVALID":
        return (
            "DATA_INVALID",
            [
                "Stage 11 analysis state is DATA_INVALID"
            ],
        )

    if stage11_state == "BLOCKED_UPSTREAM":
        return (
            "UPSTREAM_INVALID",
            [
                "Stage 11 is BLOCKED_UPSTREAM"
            ],
        )

    stale_statuses = {
        "DATA_STALE",
        "STALE",
    }

    invalid_statuses = {
        "DATA_INVALID",
        "INVALID",
    }

    statuses = {
        "Stage 6": stage6_status,
        "Stage 7": stage7_status,
        "Stage 8": stage8_status,
        "Stage 9": stage9_status,
    }

    for name, status in statuses.items():

        if status in stale_statuses:
            return (
                "DATA_STALE",
                [
                    f"{name} data status is {status}"
                ],
            )

        if status in invalid_statuses:
            return (
                "DATA_INVALID",
                [
                    f"{name} data status is {status}"
                ],
            )

    if stage11_state not in {
        "EXECUTION_ANALYSIS_VALID",
        "EXECUTION_ANALYSIS_INCOMPLETE",
    }:
        return (
            "UPSTREAM_INVALID",
            [
                f"Unsupported Stage 11 state: "
                f"{stage11_state}"
            ],
        )

    return (
        "ELIGIBLE",
        reasons,
    )


# ============================================================
# MODULE 12B
# LIVE STRUCTURAL COHERENCE
# ============================================================

def evaluate_structural_coherence(
    stage11: pd.Series,
) -> tuple[
    str,
    list[str],
]:

    structure = (
        str(
            stage11["structure_state"]
        )
        .strip()
        .upper()
    )

    price_volume = (
        str(
            stage11["price_volume_quality"]
        )
        .strip()
        .upper()
    )

    event = (
        str(
            stage11["event_state"]
        )
        .strip()
        .upper()
    )

    alignment = (
        str(
            stage11[
                "research_live_alignment"
            ]
        )
        .strip()
        .upper()
    )

    reasons = []

    if structure in {
        "UNCLEAR",
    }:
        return (
            "LOW",
            [
                "Market structure is UNCLEAR"
            ],
        )

    if (
        structure == "TRANSITION"
        and alignment
        == "UNCONFIRMED"
    ):
        return (
            "LOW",
            [
                "Transition structure lacks "
                "research/live confirmation"
            ],
        )

    strong_structure = structure in {
        "TRENDING_UP",
        "TRENDING_DOWN",
        "BREAKOUT_STRUCTURE",
        "BREAKDOWN_STRUCTURE",
    }

    strong_event = event in {
        "BREAKOUT_OBSERVED",
        "BREAKDOWN_OBSERVED",
        "CONTINUATION",
        "RETEST",
    }

    strong_volume = (
        price_volume == "STRONG"
    )

    moderate_volume = (
        price_volume == "MODERATE"
    )

    strong_alignment = (
        alignment == "HIGH"
    )

    partial_alignment = (
        alignment == "PARTIAL"
    )

    if (
        strong_structure
        and strong_volume
        and (
            strong_event
            or strong_alignment
        )
        and strong_alignment
    ):
        return (
            "HIGH",
            [
                "Directional structure is coherent",
                "Price/volume quality is STRONG",
                "Research/live alignment is HIGH",
            ],
        )

    if (
        strong_structure
        and (
            strong_volume
            or moderate_volume
        )
        and (
            strong_event
            or strong_alignment
            or partial_alignment
        )
    ):
        return (
            "MODERATE",
            [
                "Live structure is identifiable",
                "Supporting live evidence is present",
            ],
        )

    if (
        structure == "RANGE"
        and price_volume
        in {"MODERATE", "STRONG"}
    ):
        return (
            "MODERATE",
            [
                "Range structure is internally identifiable"
            ],
        )

    return (
        "LOW",
        [
            "Live structural evidence is insufficiently coherent"
        ],
    )


# ============================================================
# MODULE 12C
# RESEARCH ↔ LIVE SCENARIO MATCH
# ============================================================

def evaluate_research_live_match(
    stage7: pd.Series,
    stage11: pd.Series,
) -> tuple[
    str,
    list[str],
]:

    activation = (
        str(
            stage7["activation"]
        )
        .strip()
        .upper()
    )

    alignment = (
        str(
            stage11[
                "research_live_alignment"
            ]
        )
        .strip()
        .upper()
    )

    if activation != "EDGE_ACTIVE":

        return (
            "NO_MATCH",
            [
                f"Stage 7 activation is {activation}"
            ],
        )

    mapping = {
        "HIGH": (
            "STRONG_MATCH",
            [
                "Stage 7 edge is active",
                "Stage 11 research/live alignment is HIGH",
            ],
        ),

        "PARTIAL": (
            "PARTIAL_MATCH",
            [
                "Stage 7 edge is active",
                "Stage 11 research/live alignment is PARTIAL",
            ],
        ),

        "LOW": (
            "WEAK_MATCH",
            [
                "Stage 7 edge is active",
                "Stage 11 research/live alignment is LOW",
            ],
        ),

        "NOT_APPLICABLE": (
            "NO_MATCH",
            [
                "Research/live alignment is not applicable"
            ],
        ),

        "UNCONFIRMED": (
            "UNCONFIRMED",
            [
                "Research/live alignment is unconfirmed"
            ],
        ),
    }

    return mapping.get(
        alignment,
        (
            "UNCONFIRMED",
            [
                "Unknown research/live alignment state"
            ],
        ),
    )


# ============================================================
# MODULE 12D
# EXECUTION ENVIRONMENT QUALITY
# ============================================================

def evaluate_environment_quality(
    upstream_state: str,
    structural_coherence: str,
    stage11: pd.Series,
) -> tuple[
    str,
    list[str],
]:

    if upstream_state in {
        "DATA_STALE",
        "DATA_INVALID",
        "UPSTREAM_INVALID",
    }:
        return (
            "INVALID",
            [
                f"Upstream state is {upstream_state}"
            ],
        )

    analysis_state = (
        str(
            stage11["analysis_state"]
        )
        .strip()
        .upper()
    )

    if analysis_state == "DATA_STALE":
        return (
            "INVALID",
            [
                "Stage 11 live analysis is stale"
            ],
        )

    if analysis_state == "DATA_INVALID":
        return (
            "INVALID",
            [
                "Stage 11 live analysis is invalid"
            ],
        )

    if analysis_state == "BLOCKED_UPSTREAM":
        return (
            "INVALID",
            [
                "Stage 11 is blocked upstream"
            ],
        )

    price_volume = (
        str(
            stage11["price_volume_quality"]
        )
        .strip()
        .upper()
    )

    alignment = (
        str(
            stage11[
                "research_live_alignment"
            ]
        )
        .strip()
        .upper()
    )

    if (
        structural_coherence == "HIGH"
        and price_volume == "STRONG"
        and alignment == "HIGH"
    ):
        return (
            "HIGH",
            [
                "High structural coherence",
                "Strong price/volume quality",
                "High research/live alignment",
            ],
        )

    if (
        structural_coherence
        in {"HIGH", "MODERATE"}
        and price_volume
        in {"STRONG", "MODERATE"}
        and alignment
        in {"HIGH", "PARTIAL"}
    ):
        return (
            "MODERATE",
            [
                "Sufficient live structural evidence",
                "Acceptable price/volume quality",
                "Research/live alignment is usable",
            ],
        )

    return (
        "LOW",
        [
            "Live execution environment lacks sufficient quality"
        ],
    )


# ============================================================
# MODULE 12E
# SCENARIO CLASSIFICATION
# ============================================================

def classify_scenario(
    stage11: pd.Series,
) -> tuple[
    str,
    list[str],
]:

    structure = (
        str(
            stage11["structure_state"]
        )
        .strip()
        .upper()
    )

    event = (
        str(
            stage11["event_state"]
        )
        .strip()
        .upper()
    )

    if event == "BREAKOUT_OBSERVED":

        return (
            "BREAKOUT_SCENARIO",
            [
                "Stage 11 observed a breakout event"
            ],
        )

    if (
        structure
        == "BREAKOUT_STRUCTURE"
    ):

        return (
            "BREAKOUT_SCENARIO",
            [
                "Stage 11 classified breakout structure"
            ],
        )

    if event == "BREAKDOWN_OBSERVED":

        return (
            "BREAKDOWN_SCENARIO",
            [
                "Stage 11 observed a breakdown event"
            ],
        )

    if (
        structure
        == "BREAKDOWN_STRUCTURE"
    ):

        return (
            "BREAKDOWN_SCENARIO",
            [
                "Stage 11 classified breakdown structure"
            ],
        )

    if event == "RETEST":

        return (
            "RETEST_SCENARIO",
            [
                "Stage 11 identified a retest event"
            ],
        )

    if event == "FAILED_BREAK":

        return (
            "REVERSAL_RISK_SCENARIO",
            [
                "Stage 11 identified a failed-break event"
            ],
        )

    if structure in {
        "TRENDING_UP",
        "TRENDING_DOWN",
    }:

        return (
            "CONTINUATION_SCENARIO",
            [
                "Stage 11 identified directional trend structure"
            ],
        )

    if structure == "RANGE":

        return (
            "RANGE_SCENARIO",
            [
                "Stage 11 identified range structure"
            ],
        )

    if structure == "TRANSITION":

        return (
            "TRANSITION_SCENARIO",
            [
                "Stage 11 identified transitional structure"
            ],
        )

    return (
        "UNCLEAR_SCENARIO",
        [
            "Stage 11 does not provide a sufficiently defined scenario"
        ],
    )


def classify_scenario_quality(
    environment: str,
    match: str,
    coherence: str,
    scenario: str,
) -> str:

    if (
        environment == "INVALID"
        or scenario == "UNCLEAR_SCENARIO"
    ):
        return "UNCONFIRMED"

    if (
        environment == "HIGH"
        and match == "STRONG_MATCH"
        and coherence == "HIGH"
    ):
        return "HIGH"

    if (
        environment
        in {"HIGH", "MODERATE"}
        and match
        in {"STRONG_MATCH", "PARTIAL_MATCH"}
        and coherence
        in {"HIGH", "MODERATE"}
    ):
        return "MODERATE"

    if (
        environment
        in {"MODERATE", "LOW"}
        and match
        in {
            "STRONG_MATCH",
            "PARTIAL_MATCH",
            "WEAK_MATCH",
        }
        and scenario
        != "UNCLEAR_SCENARIO"
    ):
        return "LOW"

    return "UNCONFIRMED"


# ============================================================
# MODULE 12F
# FINAL READINESS GATE
# ============================================================

def final_readiness_gate(
    upstream_state: str,
    stage7: pd.Series,
    stage11: pd.Series,
    coherence: str,
    match: str,
    environment: str,
    scenario: str,
) -> tuple[
    str,
    list[str],
    list[str],
]:

    supporting = []
    blocking = []

    if upstream_state == "DATA_STALE":

        return (
            "DATA_STALE",
            supporting,
            [
                "Required upstream live data is stale"
            ],
        )

    if upstream_state == "DATA_INVALID":

        return (
            "DATA_INVALID",
            supporting,
            [
                "Required upstream live data is invalid"
            ],
        )

    if upstream_state == "UPSTREAM_INVALID":

        return (
            "UPSTREAM_INVALID",
            supporting,
            [
                "Required upstream integrity condition failed"
            ],
        )

    activation = (
        str(
            stage7["activation"]
        )
        .strip()
        .upper()
    )

    analysis_state = (
        str(
            stage11["analysis_state"]
        )
        .strip()
        .upper()
    )

    if activation == "EDGE_ACTIVE":
        supporting.append(
            "Stage 7 edge is EDGE_ACTIVE"
        )
    else:
        blocking.append(
            f"Stage 7 activation is {activation}"
        )

    if analysis_state == "EXECUTION_ANALYSIS_VALID":
        supporting.append(
            "Stage 11 analysis is valid"
        )
    elif analysis_state == "EXECUTION_ANALYSIS_INCOMPLETE":
        blocking.append(
            "Stage 11 analysis is incomplete"
        )
    else:
        blocking.append(
            f"Stage 11 analysis state is {analysis_state}"
        )

    if coherence == "HIGH":
        supporting.append(
            "Structural coherence is HIGH"
        )
    elif coherence == "MODERATE":
        supporting.append(
            "Structural coherence is MODERATE"
        )
    else:
        blocking.append(
            "Structural coherence is LOW"
        )

    if match == "STRONG_MATCH":
        supporting.append(
            "Research/live scenario match is STRONG"
        )
    elif match == "PARTIAL_MATCH":
        blocking.append(
            "Research/live scenario match is PARTIAL"
        )
    else:
        blocking.append(
            f"Research/live scenario match is {match}"
        )

    if environment == "HIGH":
        supporting.append(
            "Execution environment quality is HIGH"
        )
    elif environment == "MODERATE":
        supporting.append(
            "Execution environment quality is MODERATE"
        )
    else:
        blocking.append(
            f"Execution environment quality is {environment}"
        )

    if scenario != "UNCLEAR_SCENARIO":
        supporting.append(
            f"Scenario is {scenario}"
        )
    else:
        blocking.append(
            "Scenario classification is unclear"
        )

    ready = (
        activation == "EDGE_ACTIVE"
        and analysis_state
        == "EXECUTION_ANALYSIS_VALID"
        and coherence
        in {"HIGH", "MODERATE"}
        and match == "STRONG_MATCH"
        and environment
        in {"HIGH", "MODERATE"}
        and scenario
        != "UNCLEAR_SCENARIO"
    )

    if ready:
        return (
            "EXECUTION_SCENARIO_READY",
            supporting,
            blocking,
        )

    if (
        analysis_state
        in {
            "EXECUTION_ANALYSIS_VALID",
            "EXECUTION_ANALYSIS_INCOMPLETE",
        }
        and environment
        in {"HIGH", "MODERATE"}
        and scenario
        != "UNCLEAR_SCENARIO"
    ):
        return (
            "EXECUTION_SCENARIO_CONDITIONAL",
            supporting,
            blocking,
        )

    return (
        "EXECUTION_SCENARIO_BLOCKED",
        supporting,
        blocking,
    )


# ============================================================
# PROVENANCE
# ============================================================

def validate_provenance(
    stage10: pd.Series,
    stage11: pd.Series,
) -> None:

    required_stage10 = [
        "research_provenance",
        "stage6_provenance",
        "stage7_provenance",
        "stage8_provenance",
        "stage9_provenance",
    ]

    for field in required_stage10:

        require_nonempty(
            stage10[field],
            f"Stage 10 {field}",
        )

    required_stage11 = [
        "research_provenance",
        "stage6_provenance",
        "stage7_provenance",
        "stage8_provenance",
        "stage9_provenance",
        "stage10_provenance",
        "stage11_provenance",
    ]

    for field in required_stage11:

        require_nonempty(
            stage11[field],
            f"Stage 11 {field}",
        )


# ============================================================
# HARD SAFETY
# ============================================================

def enforce_safety(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:

    dataframe = dataframe.copy()

    for field in [
        "trade_ready_output",
        "trade_authorized",
        "trade_signal_generated",
    ]:

        dataframe[field] = False

    return dataframe


def validate_safety(
    dataframe: pd.DataFrame,
) -> list[str]:

    errors = []

    for field in [
        "trade_ready_output",
        "trade_authorized",
        "trade_signal_generated",
    ]:

        if field not in dataframe.columns:

            errors.append(
                f"Missing safety field: {field}"
            )

            continue

        if not (
            dataframe[field] == False
        ).all():

            errors.append(
                f"Safety violation: {field}"
            )

    return errors


# ============================================================
# MAIN ENGINE
# ============================================================

def run_stage12(
    universe_path: str,
    profiles_path: str,
    stage6_path: str,
    stage7_path: str,
    stage8_path: str,
    stage9_path: str,
    stage10_path: str,
    stage11_path: str,
    contract_path: str,
    output_dir: str,
) -> dict[str, Any]:

    contract = load_json(
        contract_path
    )

    if (
        contract.get("contract")
        != "PSY29_LIVE_EXECUTION_READINESS_SCENARIO_GATE"
    ):
        raise ValueError(
            "Incorrect Stage 12 contract"
        )

    if contract.get("version") != "1.0":
        raise ValueError(
            "Unsupported Stage 12 contract version"
        )

    symbols, ranks = (
        load_canonical_universe(
            universe_path
        )
    )

    canonical_set = set(
        symbols
    )

    validate_stage5_profiles(
        profiles_path,
        canonical_set,
    )

    stage6 = load_table(
        stage6_path,
        "Stage 6",
        STAGE6_REQUIRED,
        canonical_set,
    )

    stage7 = load_table(
        stage7_path,
        "Stage 7",
        STAGE7_REQUIRED,
        canonical_set,
    )

    stage8 = load_table(
        stage8_path,
        "Stage 8",
        STAGE8_REQUIRED,
        canonical_set,
    )

    stage9 = load_table(
        stage9_path,
        "Stage 9",
        STAGE9_REQUIRED,
        canonical_set,
    )

    stage10 = load_table(
        stage10_path,
        "Stage 10",
        STAGE10_REQUIRED,
        canonical_set,
    )

    stage11 = load_table(
        stage11_path,
        "Stage 11",
        STAGE11_REQUIRED,
        canonical_set,
    )

    results = []
    validation_errors = []

    # ========================================================
    # PROCESS ALL 29
    # ========================================================

    for symbol in symbols:

        r6 = stage6.loc[symbol]
        r7 = stage7.loc[symbol]
        r8 = stage8.loc[symbol]
        r9 = stage9.loc[symbol]
        r10 = stage10.loc[symbol]
        r11 = stage11.loc[symbol]

        (
            upstream_state,
            upstream_reasons,
        ) = evaluate_upstream_eligibility(
            r6,
            r7,
            r8,
            r9,
            r10,
            r11,
        )

        # ----------------------------------------------------
        # Default fail-closed values
        # ----------------------------------------------------

        coherence = "LOW"

        coherence_reasons = []

        match = "UNCONFIRMED"

        match_reasons = []

        environment = "INVALID"

        environment_reasons = []

        scenario = "UNCLEAR_SCENARIO"

        scenario_reasons = []

        scenario_quality = "UNCONFIRMED"

        stage12_state = upstream_state

        supporting_reasons = []

        blocking_reasons = list(
            upstream_reasons
        )

        # ----------------------------------------------------
        # Continue only when upstream is eligible
        # ----------------------------------------------------

        if upstream_state == "ELIGIBLE":

            (
                coherence,
                coherence_reasons,
            ) = evaluate_structural_coherence(
                r11
            )

            (
                match,
                match_reasons,
            ) = evaluate_research_live_match(
                r7,
                r11,
            )

            (
                environment,
                environment_reasons,
            ) = evaluate_environment_quality(
                upstream_state,
                coherence,
                r11,
            )

            (
                scenario,
                scenario_reasons,
            ) = classify_scenario(
                r11
            )

            scenario_quality = (
                classify_scenario_quality(
                    environment,
                    match,
                    coherence,
                    scenario,
                )
            )

            (
                stage12_state,
                final_supporting,
                final_blocking,
            ) = final_readiness_gate(
                upstream_state,
                r7,
                r11,
                coherence,
                match,
                environment,
                scenario,
            )

            supporting_reasons = (
                coherence_reasons
                + match_reasons
                + environment_reasons
                + scenario_reasons
                + final_supporting
            )

            blocking_reasons = (
                final_blocking
            )

        # ----------------------------------------------------
        # Provenance validation
        # ----------------------------------------------------

        try:

            validate_provenance(
                r10,
                r11,
            )

        except Exception as exc:

            stage12_state = (
                "UPSTREAM_INVALID"
            )

            blocking_reasons.append(
                str(exc)
            )

        # ----------------------------------------------------
        # Output record
        # ----------------------------------------------------

        result = {
            "canonical_rank":
                ranks[symbol],

            "symbol":
                symbol,

            "stage12_state":
                stage12_state,

            "scenario_classification":
                scenario,

            "scenario_quality":
                scenario_quality,

            "research_live_match":
                match,

            "execution_environment_quality":
                environment,

            "upstream_integrity":
                str(
                    r10["integrity_state"]
                ),

            "live_analysis_state":
                str(
                    r11["analysis_state"]
                ),

            "supporting_reasons":
                " | ".join(
                    dict.fromkeys(
                        supporting_reasons
                    )
                )
                if supporting_reasons
                else "NONE",

            "blocking_reasons":
                " | ".join(
                    dict.fromkeys(
                        blocking_reasons
                    )
                )
                if blocking_reasons
                else "NONE",

            "research_provenance":
                str(
                    r10[
                        "research_provenance"
                    ]
                ),

            "stage6_provenance":
                str(
                    r10[
                        "stage6_provenance"
                    ]
                ),

            "stage7_provenance":
                str(
                    r10[
                        "stage7_provenance"
                    ]
                ),

            "stage8_provenance":
                str(
                    r10[
                        "stage8_provenance"
                    ]
                ),

            "stage9_provenance":
                str(
                    r10[
                        "stage9_provenance"
                    ]
                ),

            "stage10_provenance":
                (
                    str(
                        r11[
                            "stage10_provenance"
                        ]
                    )
                    if
                    "stage10_provenance"
                    in r11.index
                    else
                    "Stage 10 Candidate Integrity Provenance"
                ),

            "stage11_provenance":
                str(
                    r11[
                        "stage11_provenance"
                    ]
                ),

            "stage12_provenance":
                (
                    "PSY29 Stage 12 "
                    "Live Execution Readiness "
                    "& Scenario Gate v1.0"
                ),

            "live_data_timestamp":
                str(
                    r11[
                        "live_data_timestamp"
                    ]
                ),

            # ------------------------------------------------
            # HARD SAFETY
            # ------------------------------------------------

            "trade_ready_output":
                False,

            "trade_authorized":
                False,

            "trade_signal_generated":
                False,
        }

        results.append(
            result
        )

    # ========================================================
    # FINAL DATAFRAME
    # ========================================================

    output = pd.DataFrame(
        results
    )

    output = (
        output
        .sort_values(
            "canonical_rank"
        )
        .reset_index(
            drop=True
        )
    )

    output = enforce_safety(
        output
    )

    # ========================================================
    # HARD VALIDATION
    # ========================================================

    if len(output) != 29:

        validation_errors.append(
            "Output coverage is not 29"
        )

    if (
        output["symbol"].nunique()
        != 29
    ):

        validation_errors.append(
            "Output contains duplicate symbols"
        )

    if (
        set(output["symbol"])
        != canonical_set
    ):

        validation_errors.append(
            "Output symbols do not match "
            "canonical 29"
        )

    if not set(
        output["stage12_state"]
    ).issubset(
        STAGE12_STATES
    ):

        validation_errors.append(
            "Invalid Stage 12 state"
        )

    if not set(
        output["scenario_classification"]
    ).issubset(
        SCENARIO_STATES
    ):

        validation_errors.append(
            "Invalid scenario classification"
        )

    if not set(
        output["research_live_match"]
    ).issubset(
        MATCH_STATES
    ):

        validation_errors.append(
            "Invalid research/live match state"
        )

    if not set(
        output[
            "execution_environment_quality"
        ]
    ).issubset(
        ENVIRONMENT_STATES
    ):

        validation_errors.append(
            "Invalid execution environment quality"
        )

    if not set(
        output["scenario_quality"]
    ).issubset(
        QUALITY_STATES
    ):

        validation_errors.append(
            "Invalid scenario quality"
        )

    validation_errors.extend(
        validate_safety(
            output
        )
    )

    provenance_fields = [
        "research_provenance",
        "stage6_provenance",
        "stage7_provenance",
        "stage8_provenance",
        "stage9_provenance",
        "stage10_provenance",
        "stage11_provenance",
        "stage12_provenance",
    ]

    for field in provenance_fields:

        if field not in output.columns:

            validation_errors.append(
                f"Missing provenance field: {field}"
            )

            continue

        if (
            output[field]
            .astype(str)
            .str.strip()
            .eq("")
            .any()
        ):

            validation_errors.append(
                f"Empty provenance values: {field}"
            )

    # ========================================================
    # SUMMARY
    # ========================================================

    output_directory = Path(
        output_dir
    )

    output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path = (
        output_directory
        / "PSY29_STAGE12_EXECUTION_READINESS.csv"
    )

    output.to_csv(
        output_path,
        index=False,
    )

    state_counts = (
        output[
            "stage12_state"
        ]
        .value_counts()
        .to_dict()
    )

    summary = {

        "stage":
            12,

        "engine":
            "PSY29_LIVE_EXECUTION_READINESS_SCENARIO_GATE",

        "engine_execution_status":
            "PASS",

        "validation_status":
            (
                "PASS"
                if not validation_errors
                else "FAIL"
            ),

        "status":
            (
                "PASS"
                if not validation_errors
                else "FAIL"
            ),

        "coverage":
            len(output),

        "expected_coverage":
            29,

        "state_counts":
            state_counts,

        "validation_errors":
            validation_errors,

        # ----------------------------------------------------
        # HARD SAFETY
        # ----------------------------------------------------

        "trade_ready_output":
            False,

        "trade_authorized":
            False,

        "trade_signal_generated":
            False,

        "ce_pe_selection":
            False,

        "entry_calculation":
            False,

        "stop_loss_calculation":
            False,

        "target_calculation":
            False,

        "position_size_calculation":
            False,

        "risk_calculation":
            False,

        "capital_allocation":
            False,

        "order_generation":
            False,

        "execution":
            False,

        "fail_closed":
            True,
    }

    summary_path = (
        output_directory
        / "stage12_summary.json"
    )

    summary_path.write_text(
        json.dumps(
            summary,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(
        json.dumps(
            summary,
            indent=2,
        )
    )

    # ========================================================
    # CI HARD FAILURE
    # ========================================================

    if validation_errors:

        raise SystemExit(
            "PSY29 STAGE 12 HARD VALIDATION FAILED"
        )


# ============================================================
# CLI
# ============================================================

def main() -> None:

    parser = argparse.ArgumentParser(
        description=(
            "PSY29 Stage 12 — "
            "Live Execution Readiness "
            "& Scenario Gate"
        )
    )

    parser.add_argument(
        "--universe",
        required=True,
    )

    parser.add_argument(
        "--profiles",
        required=True,
    )

    parser.add_argument(
        "--stage6",
        required=True,
    )

    parser.add_argument(
        "--stage7",
        required=True,
    )

    parser.add_argument(
        "--stage8",
        required=True,
    )

    parser.add_argument(
        "--stage9",
        required=True,
    )

    parser.add_argument(
        "--stage10",
        required=True,
    )

    parser.add_argument(
        "--stage11",
        required=True,
    )

    parser.add_argument(
        "--contract",
        required=True,
    )

    parser.add_argument(
        "--output",
        required=True,
    )

    args = parser.parse_args()

    run_stage12(
        universe_path=args.universe,
        profiles_path=args.profiles,
        stage6_path=args.stage6,
        stage7_path=args.stage7,
        stage8_path=args.stage8,
        stage9_path=args.stage9,
        stage10_path=args.stage10,
        stage11_path=args.stage11,
        contract_path=args.contract,
        output_dir=args.output,
    )


if __name__ == "__main__":
    main()