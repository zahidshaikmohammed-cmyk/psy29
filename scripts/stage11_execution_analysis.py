#!/usr/bin/env python3
"""
PSY29 Stage 11 — Live Execution-Analysis Engine

Purpose:
    Convert integrity-verified PSY29 candidates into structured,
    research-conditioned live execution analysis.

Hard boundaries:
    - No trade signals
    - No trade authorization
    - No CE/PE selection
    - No entry calculation
    - No stop-loss calculation
    - No target calculation
    - No position sizing
    - No order generation
    - No execution

Stage 11 modules:
    11A — Market Structure
    11B — Price / Volume Quality
    11C — Structural Levels
    11D — Event State
    11E — Research ↔ Live Alignment
    11F — Execution-Analysis Synthesis
    11G — Integrity + Provenance Validation
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


# ============================================================
# CONSTANTS
# ============================================================

ANALYSIS_STATES = {
    "EXECUTION_ANALYSIS_VALID",
    "EXECUTION_ANALYSIS_INCOMPLETE",
    "DATA_STALE",
    "DATA_INVALID",
    "BLOCKED_UPSTREAM",
}

STRUCTURE_STATES = {
    "TRENDING_UP",
    "TRENDING_DOWN",
    "RANGE",
    "BREAKOUT_STRUCTURE",
    "BREAKDOWN_STRUCTURE",
    "TRANSITION",
    "UNCLEAR",
}

QUALITY_STATES = {
    "STRONG",
    "MODERATE",
    "WEAK",
    "UNCONFIRMED",
}

EVENT_STATES = {
    "NO_EVENT",
    "APPROACHING_LEVEL",
    "BREAKOUT_OBSERVED",
    "BREAKDOWN_OBSERVED",
    "RETEST",
    "CONTINUATION",
    "FAILED_BREAK",
    "UNCONFIRMED",
}

ALIGNMENT_STATES = {
    "HIGH",
    "PARTIAL",
    "LOW",
    "NOT_APPLICABLE",
    "UNCONFIRMED",
}

FRESH_MAX_AGE_SECONDS = 90
STALE_MAX_AGE_SECONDS = 180


LIVE_REQUIRED_FIELDS = {
    "symbol",
    "timestamp",

    "open_1m",
    "high_1m",
    "low_1m",
    "close_1m",
    "volume_1m",
    "avg_volume_20_1m",

    "open_5m",
    "high_5m",
    "low_5m",
    "close_5m",
    "volume_5m",
    "avg_volume_20_5m",

    "vwap_5m",
    "ema9_5m",
    "ema20_5m",

    "first15_high",
    "first15_low",

    "swing_high",
    "swing_low",
}


# ============================================================
# GENERIC HELPERS
# ============================================================

def load_json(path: str | Path) -> dict[str, Any]:
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(
            f"Required JSON file does not exist: {path}"
        )

    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def finite_number(value: Any, field_name: str = "value") -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{field_name} is not numeric"
        ) from exc

    if not math.isfinite(number):
        raise ValueError(
            f"{field_name} is non-finite"
        )

    return number


def parse_timestamp(value: Any) -> datetime:
    if value is None:
        raise ValueError("timestamp is missing")

    text = str(value).strip()

    if not text:
        raise ValueError("timestamp is empty")

    try:
        timestamp = datetime.fromisoformat(
            text.replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise ValueError(
            f"invalid timestamp: {text}"
        ) from exc

    if timestamp.tzinfo is None:
        raise ValueError(
            "timestamp must be timezone-aware"
        )

    return timestamp.astimezone(timezone.utc)


def timestamp_age_seconds(
    value: Any,
    now: datetime,
) -> float:
    timestamp = parse_timestamp(value)

    age = (
        now - timestamp
    ).total_seconds()

    if age < -5:
        raise ValueError(
            "timestamp is materially in the future"
        )

    return max(0.0, age)


def require_columns(
    dataframe: pd.DataFrame,
    required: set[str],
    name: str,
) -> None:

    missing = required - set(dataframe.columns)

    if missing:
        raise ValueError(
            f"{name} missing required fields: "
            f"{sorted(missing)}"
        )


def normalize_symbols(
    dataframe: pd.DataFrame,
    name: str,
) -> pd.DataFrame:

    if "symbol" not in dataframe.columns:
        raise ValueError(
            f"{name} has no symbol column"
        )

    dataframe = dataframe.copy()

    dataframe["symbol"] = (
        dataframe["symbol"]
        .astype(str)
        .str.upper()
        .str.strip()
    )

    return dataframe


# ============================================================
# CANONICAL UNIVERSE
# ============================================================

def load_canonical_symbols(
    universe_path: str,
) -> list[str]:

    universe = load_json(universe_path)

    rows = universe.get("universe", [])

    if len(rows) != 29:
        raise ValueError(
            "Canonical universe must contain exactly 29 rows; "
            f"got {len(rows)}"
        )

    symbols = [
        str(row.get("symbol", ""))
        .upper()
        .strip()
        for row in rows
    ]

    if any(not symbol for symbol in symbols):
        raise ValueError(
            "Canonical universe contains an empty symbol"
        )

    if len(set(symbols)) != 29:
        raise ValueError(
            "Canonical universe contains duplicate symbols"
        )

    ranks = [
        int(row.get("rank", 0))
        for row in rows
    ]

    if ranks != list(range(1, 30)):
        raise ValueError(
            "Canonical universe ranks must be exactly 1–29"
        )

    return symbols


# ============================================================
# STAGE 5
# ============================================================

def load_stage5_profiles(
    profiles_path: str,
    symbols: list[str],
) -> dict[str, dict[str, Any]]:

    data = load_json(profiles_path)

    rows = data.get("profiles", [])

    if len(rows) != 29:
        raise ValueError(
            "Stage 5 profile count must be exactly 29; "
            f"got {len(rows)}"
        )

    profiles = {}

    for row in rows:

        symbol = (
            str(row.get("symbol", ""))
            .upper()
            .strip()
        )

        if not symbol:
            raise ValueError(
                "Stage 5 contains an empty symbol"
            )

        if symbol in profiles:
            raise ValueError(
                f"Duplicate Stage 5 profile: {symbol}"
            )

        profiles[symbol] = row

    if set(profiles) != set(symbols):

        missing = sorted(
            set(symbols) - set(profiles)
        )

        unexpected = sorted(
            set(profiles) - set(symbols)
        )

        raise ValueError(
            "Stage 5 universe mismatch: "
            f"missing={missing}; "
            f"unexpected={unexpected}"
        )

    return profiles


# ============================================================
# STAGE OUTPUT LOADING
# ============================================================

def load_stage_table(
    path: str,
    required_fields: set[str],
    name: str,
    symbols: list[str],
) -> pd.DataFrame:

    path_obj = Path(path)

    if not path_obj.exists():
        raise FileNotFoundError(
            f"{name} output missing: {path}"
        )

    dataframe = pd.read_csv(path_obj)

    require_columns(
        dataframe,
        required_fields,
        name,
    )

    dataframe = normalize_symbols(
        dataframe,
        name,
    )

    if len(dataframe) != 29:
        raise ValueError(
            f"{name} must contain 29 rows; "
            f"got {len(dataframe)}"
        )

    if dataframe["symbol"].nunique() != 29:
        raise ValueError(
            f"{name} contains duplicate symbols"
        )

    if set(dataframe["symbol"]) != set(symbols):

        missing = sorted(
            set(symbols)
            - set(dataframe["symbol"])
        )

        unexpected = sorted(
            set(dataframe["symbol"])
            - set(symbols)
        )

        raise ValueError(
            f"{name} universe mismatch: "
            f"missing={missing}; "
            f"unexpected={unexpected}"
        )

    return dataframe.set_index("symbol")


# ============================================================
# MODULE 11A
# MARKET STRUCTURE
# ============================================================

def classify_market_structure(
    close_5m: float,
    vwap_5m: float,
    ema9_5m: float,
    ema20_5m: float,
    first15_high: float,
    first15_low: float,
    swing_high: float,
    swing_low: float,
) -> tuple[str, str]:

    bullish_alignment = (
        close_5m > vwap_5m
        and ema9_5m > ema20_5m
    )

    bearish_alignment = (
        close_5m < vwap_5m
        and ema9_5m < ema20_5m
    )

    bullish_partial = (
        close_5m > vwap_5m
    )

    bearish_partial = (
        close_5m < vwap_5m
    )

    if bullish_alignment and close_5m > first15_high:
        return (
            "BREAKOUT_STRUCTURE",
            "5m close above opening-range high with bullish VWAP/EMA alignment",
        )

    if bearish_alignment and close_5m < first15_low:
        return (
            "BREAKDOWN_STRUCTURE",
            "5m close below opening-range low with bearish VWAP/EMA alignment",
        )

    if bullish_alignment:
        return (
            "TRENDING_UP",
            "price above VWAP and EMA9 above EMA20",
        )

    if bearish_alignment:
        return (
            "TRENDING_DOWN",
            "price below VWAP and EMA9 below EMA20",
        )

    if bullish_partial and not bearish_partial:
        return (
            "TRANSITION",
            "price above VWAP without full EMA alignment",
        )

    if bearish_partial and not bullish_partial:
        return (
            "TRANSITION",
            "price below VWAP without full EMA alignment",
        )

    if (
        first15_low <= close_5m <= first15_high
        and swing_low <= close_5m <= swing_high
    ):
        return (
            "RANGE",
            "price remains within opening-range and recent swing boundaries",
        )

    return (
        "UNCLEAR",
        "no sufficiently coherent structural classification",
    )


# ============================================================
# MODULE 11B
# PRICE / VOLUME QUALITY
# ============================================================

def classify_price_volume_quality(
    close_1m: float,
    open_1m: float,
    high_1m: float,
    low_1m: float,
    volume_1m: float,
    avg_volume_20_1m: float,
) -> tuple[str, str]:

    candle_range = (
        high_1m - low_1m
    )

    if candle_range <= 0:
        return (
            "UNCONFIRMED",
            "1m candle range is zero or invalid",
        )

    if avg_volume_20_1m <= 0:
        return (
            "UNCONFIRMED",
            "20-period average volume is not positive",
        )

    volume_ratio = (
        volume_1m
        / avg_volume_20_1m
    )

    body_ratio = (
        abs(close_1m - open_1m)
        / candle_range
    )

    if (
        volume_ratio >= 1.50
        and body_ratio >= 0.60
    ):
        quality = "STRONG"

    elif (
        volume_ratio >= 1.00
        and body_ratio >= 0.40
    ):
        quality = "MODERATE"

    elif (
        volume_ratio > 0
        and body_ratio >= 0.20
    ):
        quality = "WEAK"

    else:
        quality = "UNCONFIRMED"

    reason = (
        f"volume_ratio={volume_ratio:.2f}; "
        f"body_ratio={body_ratio:.2f}"
    )

    return quality, reason


# ============================================================
# MODULE 11C
# STRUCTURAL LEVELS
# ============================================================

def structural_levels(
    row: pd.Series,
) -> dict[str, float]:

    return {
        "session_high": finite_number(
            row["high_5m"],
            "high_5m",
        ),

        "session_low": finite_number(
            row["low_5m"],
            "low_5m",
        ),

        "opening_range_high": finite_number(
            row["first15_high"],
            "first15_high",
        ),

        "opening_range_low": finite_number(
            row["first15_low"],
            "first15_low",
        ),

        "swing_high": finite_number(
            row["swing_high"],
            "swing_high",
        ),

        "swing_low": finite_number(
            row["swing_low"],
            "swing_low",
        ),
    }


# ============================================================
# MODULE 11D
# EVENT STATE
# ============================================================

def classify_event_state(
    close_5m: float,
    first15_high: float,
    first15_low: float,
    swing_high: float,
    swing_low: float,
) -> tuple[str, str]:

    if close_5m > first15_high:
        return (
            "BREAKOUT_OBSERVED",
            "5m close is above opening-range high",
        )

    if close_5m < first15_low:
        return (
            "BREAKDOWN_OBSERVED",
            "5m close is below opening-range low",
        )

    price_scale = max(
        abs(close_5m),
        abs(first15_high),
        abs(first15_low),
        1.0,
    )

    proximity = (
        price_scale * 0.0025
    )

    near_opening_range = (
        abs(close_5m - first15_high)
        <= proximity
        or
        abs(close_5m - first15_low)
        <= proximity
    )

    if near_opening_range:
        return (
            "APPROACHING_LEVEL",
            "5m close is near an opening-range boundary",
        )

    near_swing = (
        abs(close_5m - swing_high)
        <= proximity
        or
        abs(close_5m - swing_low)
        <= proximity
    )

    if near_swing:
        return (
            "RETEST",
            "5m close is near a recent swing level",
        )

    return (
        "NO_EVENT",
        "no defined breakout, breakdown, or retest event",
    )


# ============================================================
# MODULE 11E
# RESEARCH ↔ LIVE ALIGNMENT
# ============================================================

def classify_research_live_alignment(
    stage7_row: pd.Series,
    regime: str,
    event_state: str,
    structure_state: str,
) -> tuple[
    str,
    str,
    list[str],
    list[str],
    list[str],
]:

    activation = str(
        stage7_row["activation"]
    ).strip().upper()

    reason_code = str(
        stage7_row["reason_code"]
    ).strip().upper()

    matched = []
    missing = []
    conflicts = []

    if activation != "EDGE_ACTIVE":

        return (
            "NOT_APPLICABLE",
            "Stage 7 edge is not active",
            [],
            ["Stage 7 edge is not active"],
            [],
        )

    if reason_code == "OR_CONTINUATION_MATCH":

        matched.append(
            "historical_or_continuation_condition"
        )

        if event_state in {
            "BREAKOUT_OBSERVED",
            "BREAKDOWN_OBSERVED",
            "CONTINUATION",
        }:

            matched.append(
                "live_directional_event"
            )

        else:

            missing.append(
                "confirmed_directional_event"
            )

        if regime in {
            "BULLISH_BREAKOUT_REGIME",
            "BEARISH_BREAKDOWN_REGIME",
        }:

            matched.append(
                "live_directional_regime"
            )

        else:

            missing.append(
                "strong_directional_regime"
            )

    elif reason_code == "TREND_RATE_MATCH":

        matched.append(
            "historical_trend_rate_condition"
        )

        if structure_state in {
            "TRENDING_UP",
            "TRENDING_DOWN",
            "BREAKOUT_STRUCTURE",
            "BREAKDOWN_STRUCTURE",
        }:

            matched.append(
                "live_directional_structure"
            )

        else:

            missing.append(
                "directional_market_structure"
            )

        if regime in {
            "BULLISH_ALIGNMENT_REGIME",
            "BEARISH_ALIGNMENT_REGIME",
            "BULLISH_WEAK_ALIGNMENT_REGIME",
            "BEARISH_WEAK_ALIGNMENT_REGIME",
        }:

            matched.append(
                "live_regime_alignment"
            )

        else:

            missing.append(
                "directional_live_regime"
            )

    else:

        missing.append(
            "recognized_stage7_activation_reason"
        )

    if conflicts:

        alignment = "LOW"

    elif not matched:

        alignment = "UNCONFIRMED"

    elif not missing:

        alignment = "HIGH"

    else:

        alignment = "PARTIAL"

    reason = (
        f"matched={len(matched)}; "
        f"missing={len(missing)}; "
        f"conflicts={len(conflicts)}"
    )

    return (
        alignment,
        reason,
        matched,
        missing,
        conflicts,
    )


# ============================================================
# MODULE 11F
# EXECUTION-ANALYSIS SYNTHESIS
# ============================================================

def synthesize_analysis_state(
    upstream_integrity: str,
    live_data_status: str,
    structure_state: str,
    quality_state: str,
    event_state: str,
    alignment_state: str,
) -> str:

    if upstream_integrity != "INTEGRITY_PASS":

        if upstream_integrity == "DATA_STALE":
            return "DATA_STALE"

        if upstream_integrity == "DATA_INVALID":
            return "DATA_INVALID"

        return "BLOCKED_UPSTREAM"

    if live_data_status == "DATA_STALE":
        return "DATA_STALE"

    if live_data_status == "DATA_INVALID":
        return "DATA_INVALID"

    components = [
        structure_state in STRUCTURE_STATES,
        quality_state in QUALITY_STATES,
        event_state in EVENT_STATES,
        alignment_state in ALIGNMENT_STATES,
    ]

    if all(components):
        return "EXECUTION_ANALYSIS_VALID"

    return "EXECUTION_ANALYSIS_INCOMPLETE"


# ============================================================
# MODULE 11G
# INTEGRITY + PROVENANCE
# ============================================================

def validate_provenance(
    row: pd.Series,
) -> None:

    required = [
        "research_provenance",
        "stage6_provenance",
        "stage7_provenance",
        "stage8_provenance",
        "stage9_provenance",
        "stage10_provenance",
    ]

    for field in required:

        value = str(
            row[field]
        ).strip()

        if not value:
            raise ValueError(
                f"missing provenance: {field}"
            )


def validate_live_row(
    row: pd.Series,
) -> None:

    for field in LIVE_REQUIRED_FIELDS:

        if field in {
            "symbol",
            "timestamp",
        }:
            continue

        finite_number(
            row[field],
            field,
        )

    volumes = [
        "volume_1m",
        "avg_volume_20_1m",
        "volume_5m",
        "avg_volume_20_5m",
    ]

    for field in volumes:

        value = finite_number(
            row[field],
            field,
        )

        if value < 0:
            raise ValueError(
                f"{field} cannot be negative"
            )

    if (
        row["high_1m"]
        < row["low_1m"]
    ):
        raise ValueError(
            "1m high is below 1m low"
        )

    if (
        row["high_5m"]
        < row["low_5m"]
    ):
        raise ValueError(
            "5m high is below 5m low"
        )

    if (
        row["first15_high"]
        < row["first15_low"]
    ):
        raise ValueError(
            "opening-range high is below opening-range low"
        )

    if (
        row["swing_high"]
        < row["swing_low"]
    ):
        raise ValueError(
            "swing high is below swing low"
        )

    if (
        finite_number(
            row["avg_volume_20_1m"],
            "avg_volume_20_1m",
        )
        <= 0
    ):
        raise ValueError(
            "avg_volume_20_1m must be positive"
        )

    if (
        finite_number(
            row["avg_volume_20_5m"],
            "avg_volume_20_5m",
        )
        <= 0
    ):
        raise ValueError(
            "avg_volume_20_5m must be positive"
        )


# ============================================================
# SAFETY
# ============================================================

def apply_hard_safety(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:

    dataframe = dataframe.copy()

    dataframe[
        "trade_ready_output"
    ] = False

    dataframe[
        "trade_authorized"
    ] = False

    dataframe[
        "trade_signal_generated"
    ] = False

    return dataframe


def validate_safety(
    dataframe: pd.DataFrame,
) -> None:

    safety_fields = [
        "trade_ready_output",
        "trade_authorized",
        "trade_signal_generated",
    ]

    for field in safety_fields:

        if field not in dataframe.columns:
            raise ValueError(
                f"missing safety field: {field}"
            )

        if not (
            dataframe[field] == False
        ).all():

            raise ValueError(
                f"safety violation: {field}"
            )


# ============================================================
# MAIN PROCESS
# ============================================================

def process(
    universe_path: str,
    profiles_path: str,
    contract_path: str,
    stage6_path: str,
    stage7_path: str,
    stage8_path: str,
    stage9_path: str,
    stage10_path: str,
    live_snapshot_path: str,
    output_dir: str,
) -> dict[str, Any]:

    output_directory = Path(
        output_dir
    )

    output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    contract = load_json(
        contract_path
    )

    symbols = load_canonical_symbols(
        universe_path
    )

    profiles = load_stage5_profiles(
        profiles_path,
        symbols,
    )

    # --------------------------------------------------------
    # STAGE 6
    # --------------------------------------------------------

    stage6 = load_stage_table(
        stage6_path,

        {
            "symbol",
            "regime",
            "data_status",
        },

        "Stage 6",
        symbols,
    )

    # --------------------------------------------------------
    # STAGE 7
    # --------------------------------------------------------

    stage7 = load_stage_table(
        stage7_path,

        {
            "symbol",
            "regime",
            "data_status",
            "activation",
            "reason_code",
            "match_reason",
        },

        "Stage 7",
        symbols,
    )

    # --------------------------------------------------------
    # STAGE 8
    # --------------------------------------------------------

    stage8 = load_stage_table(
        stage8_path,

        {
            "symbol",
            "activation",
            "regime",
            "data_status",
            "portfolio_rank",
            "ranking_score",
            "research_profile_source",
            "trade_authorized",
            "trade_signal_generated",
        },

        "Stage 8",
        symbols,
    )

    # --------------------------------------------------------
    # STAGE 9
    # --------------------------------------------------------

    stage9 = load_stage_table(
        stage9_path,

        {
            "symbol",
            "activation",
            "regime",
            "data_status",
            "candidate_quality_score",
            "research_profile_source",
            "stage6_source",
            "stage7_source",
            "stage8_source",
            "trade_authorized",
            "trade_signal_generated",
        },

        "Stage 9",
        symbols,
    )

    # --------------------------------------------------------
    # STAGE 10
    # --------------------------------------------------------

    stage10 = load_stage_table(
        stage10_path,

        {
            "symbol",
            "integrity_state",
            "activation",
            "regime",
            "data_status",
            "gate_results",
            "gate_reasons",
            "research_provenance",
            "stage6_provenance",
            "stage7_provenance",
            "stage8_provenance",
            "stage9_provenance",
            "trade_ready_output",
            "trade_authorized",
            "trade_signal_generated",
        },

        "Stage 10",
        symbols,
    )

    # --------------------------------------------------------
    # LIVE EXECUTION SNAPSHOT
    # --------------------------------------------------------

    live_path = Path(
        live_snapshot_path
    )

    if not live_path.exists():
        raise FileNotFoundError(
            f"Live execution snapshot missing: "
            f"{live_snapshot_path}"
        )

    live = pd.read_csv(
        live_path
    )

    require_columns(
        live,
        LIVE_REQUIRED_FIELDS,
        "Stage 11 live snapshot",
    )

    live = normalize_symbols(
        live,
        "Stage 11 live snapshot",
    )

    if len(live) != 29:
        raise ValueError(
            "Stage 11 live snapshot must contain "
            f"29 rows; got {len(live)}"
        )

    if live["symbol"].nunique() != 29:
        raise ValueError(
            "Stage 11 live snapshot contains duplicate symbols"
        )

    if set(live["symbol"]) != set(symbols):

        missing = sorted(
            set(symbols)
            - set(live["symbol"])
        )

        unexpected = sorted(
            set(live["symbol"])
            - set(symbols)
        )

        raise ValueError(
            "Stage 11 live snapshot universe mismatch: "
            f"missing={missing}; "
            f"unexpected={unexpected}"
        )

    live = live.set_index(
        "symbol"
    )

    now = datetime.now(
        timezone.utc
    )

    results: list[dict[str, Any]] = []

    # ========================================================
    # PROCESS EACH CANONICAL STOCK
    # ========================================================

    for symbol in symbols:

        profile = profiles[symbol]

        r6 = stage6.loc[symbol]
        r7 = stage7.loc[symbol]
        r8 = stage8.loc[symbol]
        r9 = stage9.loc[symbol]
        r10 = stage10.loc[symbol]
        live_row = live.loc[symbol]

        result = {
            "canonical_rank": int(
                profile.get("rank", 0)
            ),

            "symbol": symbol,

            "analysis_state":
                "BLOCKED_UPSTREAM",

            "structure_state":
                "UNCLEAR",

            "structure_reason":
                None,

            "price_volume_quality":
                "UNCONFIRMED",

            "price_volume_reason":
                None,

            "session_high":
                None,

            "session_low":
                None,

            "opening_range_high":
                None,

            "opening_range_low":
                None,

            "swing_high":
                None,

            "swing_low":
                None,

            "event_state":
                "UNCONFIRMED",

            "event_reason":
                None,

            "research_live_alignment":
                "UNCONFIRMED",

            "alignment_reason":
                None,

            "matched_conditions":
                "NONE",

            "missing_conditions":
                "NONE",

            "conflicting_conditions":
                "NONE",

            "research_provenance":
                str(
                    r10["research_provenance"]
                ),

            "stage6_provenance":
                str(
                    r10["stage6_provenance"]
                ),

            "stage7_provenance":
                str(
                    r10["stage7_provenance"]
                ),

            "stage8_provenance":
                str(
                    r10["stage8_provenance"]
                ),

            "stage9_provenance":
                str(
                    r10["stage9_provenance"]
                ),

            "stage10_provenance":
                "Stage 10 PSY29 Candidate Integrity Provenance",

            "live_data_timestamp":
                str(
                    live_row["timestamp"]
                ),

            "trade_ready_output":
                False,

            "trade_authorized":
                False,

            "trade_signal_generated":
                False,
        }

        # ----------------------------------------------------
        # UPSTREAM GATE
        # ----------------------------------------------------

        integrity_state = str(
            r10["integrity_state"]
        ).strip().upper()

        if integrity_state != "INTEGRITY_PASS":

            if integrity_state == "DATA_STALE":

                result[
                    "analysis_state"
                ] = "DATA_STALE"

            elif integrity_state == "DATA_INVALID":

                result[
                    "analysis_state"
                ] = "DATA_INVALID"

            else:

                result[
                    "analysis_state"
                ] = "BLOCKED_UPSTREAM"

            result[
                "event_reason"
            ] = (
                "Stage 10 did not return "
                "INTEGRITY_PASS"
            )

            results.append(
                result
            )

            continue

        # ----------------------------------------------------
        # LIVE DATA VALIDATION
        # ----------------------------------------------------

        try:

            age = timestamp_age_seconds(
                live_row["timestamp"],
                now,
            )

            if age > STALE_MAX_AGE_SECONDS:

                result[
                    "analysis_state"
                ] = "DATA_INVALID"

                result[
                    "event_reason"
                ] = (
                    "live execution snapshot "
                    "exceeds invalid-data threshold"
                )

                results.append(
                    result
                )

                continue

            if age > FRESH_MAX_AGE_SECONDS:

                result[
                    "analysis_state"
                ] = "DATA_STALE"

                result[
                    "event_reason"
                ] = (
                    "live execution snapshot "
                    "exceeds freshness threshold"
                )

                results.append(
                    result
                )

                continue

            validate_live_row(
                live_row
            )

            # ------------------------------------------------
            # 11A
            # ------------------------------------------------

            close_5m = finite_number(
                live_row["close_5m"],
                "close_5m",
            )

            vwap_5m = finite_number(
                live_row["vwap_5m"],
                "vwap_5m",
            )

            ema9_5m = finite_number(
                live_row["ema9_5m"],
                "ema9_5m",
            )

            ema20_5m = finite_number(
                live_row["ema20_5m"],
                "ema20_5m",
            )

            first15_high = finite_number(
                live_row["first15_high"],
                "first15_high",
            )

            first15_low = finite_number(
                live_row["first15_low"],
                "first15_low",
            )

            swing_high = finite_number(
                live_row["swing_high"],
                "swing_high",
            )

            swing_low = finite_number(
                live_row["swing_low"],
                "swing_low",
            )

            structure_state, structure_reason = (
                classify_market_structure(
                    close_5m,
                    vwap_5m,
                    ema9_5m,
                    ema20_5m,
                    first15_high,
                    first15_low,
                    swing_high,
                    swing_low,
                )
            )

            # ------------------------------------------------
            # 11B
            # ------------------------------------------------

            close_1m = finite_number(
                live_row["close_1m"],
                "close_1m",
            )

            open_1m = finite_number(
                live_row["open_1m"],
                "open_1m",
            )

            high_1m = finite_number(
                live_row["high_1m"],
                "high_1m",
            )

            low_1m = finite_number(
                live_row["low_1m"],
                "low_1m",
            )

            volume_1m = finite_number(
                live_row["volume_1m"],
                "volume_1m",
            )

            avg_volume_20_1m = finite_number(
                live_row["avg_volume_20_1m"],
                "avg_volume_20_1m",
            )

            price_volume_quality, price_volume_reason = (
                classify_price_volume_quality(
                    close_1m,
                    open_1m,
                    high_1m,
                    low_1m,
                    volume_1m,
                    avg_volume_20_1m,
                )
            )

            # ------------------------------------------------
            # 11C
            # ------------------------------------------------

            levels = structural_levels(
                live_row
            )

            # ------------------------------------------------
            # 11D
            # ------------------------------------------------

            event_state, event_reason = (
                classify_event_state(
                    close_5m,
                    first15_high,
                    first15_low,
                    swing_high,
                    swing_low,
                )
            )

            # ------------------------------------------------
            # 11E
            # ------------------------------------------------

            (
                alignment_state,
                alignment_reason,
                matched_conditions,
                missing_conditions,
                conflicting_conditions,
            ) = classify_research_live_alignment(
                r7,
                str(r6["regime"]),
                event_state,
                structure_state,
            )

            # ------------------------------------------------
            # 11F
            # ------------------------------------------------

            analysis_state = (
                synthesize_analysis_state(
                    integrity_state,
                    "FRESH",
                    structure_state,
                    price_volume_quality,
                    event_state,
                    alignment_state,
                )
            )

            result.update(
                {
                    "analysis_state":
                        analysis_state,

                    "structure_state":
                        structure_state,

                    "structure_reason":
                        structure_reason,

                    "price_volume_quality":
                        price_volume_quality,

                    "price_volume_reason":
                        price_volume_reason,

                    "session_high":
                        levels["session_high"],

                    "session_low":
                        levels["session_low"],

                    "opening_range_high":
                        levels[
                            "opening_range_high"
                        ],

                    "opening_range_low":
                        levels[
                            "opening_range_low"
                        ],

                    "swing_high":
                        levels["swing_high"],

                    "swing_low":
                        levels["swing_low"],

                    "event_state":
                        event_state,

                    "event_reason":
                        event_reason,

                    "research_live_alignment":
                        alignment_state,

                    "alignment_reason":
                        alignment_reason,

                    "matched_conditions":
                        ";".join(
                            matched_conditions
                        )
                        if matched_conditions
                        else "NONE",

                    "missing_conditions":
                        ";".join(
                            missing_conditions
                        )
                        if missing_conditions
                        else "NONE",

                    "conflicting_conditions":
                        ";".join(
                            conflicting_conditions
                        )
                        if conflicting_conditions
                        else "NONE",
                }
            )

        except Exception as exc:

            result[
                "analysis_state"
            ] = "DATA_INVALID"

            result[
                "event_reason"
            ] = str(exc)

        # ----------------------------------------------------
        # 11G
        # ----------------------------------------------------

        try:

            validate_provenance(
                r10
            )

        except Exception as exc:

            result[
                "analysis_state"
            ] = "BLOCKED_UPSTREAM"

            result[
                "event_reason"
            ] = str(exc)

        results.append(
            result
        )

    # ========================================================
    # FINAL DATAFRAME
    # ========================================================

    output = pd.DataFrame(
        results
    )

    output = output.sort_values(
        "canonical_rank"
    ).reset_index(
        drop=True
    )

    # Hard safety overwrite.
    output = apply_hard_safety(
        output
    )

    # ========================================================
    # VALIDATION
    # ========================================================

    validation_errors = []

    if len(output) != 29:
        validation_errors.append(
            f"coverage={len(output)}"
        )

    if output["symbol"].nunique() != 29:
        validation_errors.append(
            "symbol uniqueness failure"
        )

    if set(output["symbol"]) != set(symbols):
        validation_errors.append(
            "canonical symbol mismatch"
        )

    if not set(
        output["analysis_state"]
    ).issubset(
        ANALYSIS_STATES
    ):
        validation_errors.append(
            "invalid analysis state"
        )

    if not set(
        output["structure_state"]
    ).issubset(
        STRUCTURE_STATES
    ):
        validation_errors.append(
            "invalid structure state"
        )

    if not set(
        output["price_volume_quality"]
    ).issubset(
        QUALITY_STATES
    ):
        validation_errors.append(
            "invalid quality state"
        )

    if not set(
        output["event_state"]
    ).issubset(
        EVENT_STATES
    ):
        validation_errors.append(
            "invalid event state"
        )

    if not set(
        output["research_live_alignment"]
    ).issubset(
        ALIGNMENT_STATES
    ):
        validation_errors.append(
            "invalid alignment state"
        )

    try:

        validate_safety(
            output
        )

    except Exception as exc:

        validation_errors.append(
            str(exc)
        )

    # --------------------------------------------------------
    # Provenance validation
    # --------------------------------------------------------

    provenance_fields = [
        "research_provenance",
        "stage6_provenance",
        "stage7_provenance",
        "stage8_provenance",
        "stage9_provenance",
        "stage10_provenance",
    ]

    for field in provenance_fields:

        if field not in output.columns:

            validation_errors.append(
                f"missing provenance column: {field}"
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
                f"empty provenance: {field}"
            )

    # ========================================================
    # OUTPUT
    # ========================================================

    output_path = (
        output_directory
        / "PSY29_STAGE11_EXECUTION_ANALYSIS.csv"
    )

    output.to_csv(
        output_path,
        index=False,
    )

    execution_analysis_valid_count = int(
        (
            output["analysis_state"]
            == "EXECUTION_ANALYSIS_VALID"
        ).sum()
    )

    execution_analysis_incomplete_count = int(
        (
            output["analysis_state"]
            == "EXECUTION_ANALYSIS_INCOMPLETE"
        ).sum()
    )

    blocked_upstream_count = int(
        (
            output["analysis_state"]
            == "BLOCKED_UPSTREAM"
        ).sum()
    )

    stale_count = int(
        (
            output["analysis_state"]
            == "DATA_STALE"
        ).sum()
    )

    invalid_count = int(
        (
            output["analysis_state"]
            == "DATA_INVALID"
        ).sum()
    )

    validation_status = (
        "PASS"
        if not validation_errors
        else "FAIL"
    )

    summary = {

        "stage": 11,

        "engine":
            "PSY29_LIVE_EXECUTION_ANALYSIS_ENGINE",

        "engine_execution_status":
            "PASS",

        "validation_status":
            validation_status,

        "status":
            validation_status,

        "coverage":
            len(output),

        "expected_coverage":
            29,

        "execution_analysis_valid_count":
            execution_analysis_valid_count,

        "execution_analysis_incomplete_count":
            execution_analysis_incomplete_count,

        "blocked_upstream_count":
            blocked_upstream_count,

        "data_stale_count":
            stale_count,

        "data_invalid_count":
            invalid_count,

        "validation_errors":
            validation_errors,

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

        "position_sizing":
            False,

        "execution":
            False,

        "capital_allocation":
            False,

        "order_generation":
            False,

        "fail_closed":
            True,
    }

    summary_path = (
        output_directory
        / "stage11_summary.json"
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

    # Hard failure for CI.
    if validation_errors:

        raise SystemExit(
            "PSY29 STAGE 11 HARD VALIDATION FAILED"
        )

    return summary


# ============================================================
# CLI
# ============================================================

def main() -> None:

    parser = argparse.ArgumentParser(
        description=(
            "PSY29 Stage 11 — "
            "Live Execution-Analysis Engine"
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
        "--contract",
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
        "--live-snapshot",
        required=True,
    )

    parser.add_argument(
        "--output",
        required=True,
    )

    args = parser.parse_args()

    process(
        universe_path=args.universe,
        profiles_path=args.profiles,
        contract_path=args.contract,
        stage6_path=args.stage6,
        stage7_path=args.stage7,
        stage8_path=args.stage8,
        stage9_path=args.stage9,
        stage10_path=args.stage10,
        live_snapshot_path=args.live_snapshot,
        output_dir=args.output,
    )


if __name__ == "__main__":
    main()