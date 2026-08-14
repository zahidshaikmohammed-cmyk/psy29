#!/usr/bin/env python3
"""Isolated resolver for canonical PSY29_EVENT_DETECTOR_THRESHOLDS_V2 artifacts.

This module only resolves and normalizes an already-generated threshold artifact.
It does not calculate thresholds, mutate event-detector formulas, or provide fallbacks.
"""
from __future__ import annotations

from datetime import date
from math import isfinite
from typing import Any

from scripts.psy29_event_detector import EVENT_TYPES, SYMBOLS

CANONICAL_RESEARCH_COMMIT = "988472889edfd51046731d72f68f2e96e095a2f1"
V2_SCHEMA = "PSY29_EVENT_DETECTOR_THRESHOLDS_V2"


class ThresholdResolutionError(ValueError):
    """Raised when a V2 threshold artifact cannot be safely resolved."""


def _d(value: Any, field: str) -> date:
    try:
        return date.fromisoformat(str(value))
    except Exception as exc:
        raise ThresholdResolutionError(f"invalid {field}: {value!r}") from exc


def _finite(value: Any, field: str) -> float:
    try:
        result = float(value)
    except Exception as exc:
        raise ThresholdResolutionError(f"invalid numeric {field}: {value!r}") from exc
    if not isfinite(result):
        raise ThresholdResolutionError(f"non-finite {field}")
    return result


def validate_v2_artifact(artifact: dict) -> None:
    if artifact.get("schema") != V2_SCHEMA:
        raise ThresholdResolutionError("threshold artifact schema is not V2")
    source = artifact.get("research_source", {})
    if source.get("commit") != CANONICAL_RESEARCH_COMMIT:
        raise ThresholdResolutionError("threshold artifact does not cite canonical research commit")
    if artifact.get("methodology", {}).get("train_sessions") != 60:
        raise ThresholdResolutionError("V2 methodology must use 60 training sessions")
    if artifact.get("methodology", {}).get("test_sessions") != 20:
        raise ThresholdResolutionError("V2 methodology must use 20 OOS sessions")
    if artifact.get("methodology", {}).get("step_sessions") != 20:
        raise ThresholdResolutionError("V2 methodology must use 20-session steps")

    sets = artifact.get("threshold_sets")
    if not isinstance(sets, list) or not sets:
        raise ThresholdResolutionError("V2 threshold_sets is empty or malformed")

    expected = set(SYMBOLS)
    by_symbol: dict[str, list[dict]] = {s: [] for s in SYMBOLS}
    seen_ids: set[str] = set()
    for item in sets:
        if not isinstance(item, dict):
            raise ThresholdResolutionError("malformed threshold set")
        symbol = str(item.get("stock", "")).strip().upper()
        if symbol not in expected:
            raise ThresholdResolutionError(f"unknown or missing stock: {symbol!r}")
        threshold_id = str(item.get("threshold_set_id", ""))
        if not threshold_id or threshold_id in seen_ids:
            raise ThresholdResolutionError(f"duplicate/missing threshold_set_id for {symbol}")
        seen_ids.add(threshold_id)

        effective = _d(item.get("effective_nse_session_date"), "effective_nse_session_date")
        train = item.get("training_window")
        oos = item.get("oos_window")
        if not isinstance(train, dict) or not isinstance(oos, dict):
            raise ThresholdResolutionError(f"missing training/OOS window for {symbol}")
        train_start = _d(train.get("start"), "training_window.start")
        train_end = _d(train.get("end"), "training_window.end")
        oos_start = _d(oos.get("start"), "oos_window.start")
        oos_end = _d(oos.get("end"), "oos_window.end")
        if train.get("session_count") != 60 or oos.get("session_count") != 20:
            raise ThresholdResolutionError(f"invalid 60/20 counts for {symbol}")
        if not (train_start <= train_end < effective == oos_start <= oos_end):
            raise ThresholdResolutionError(f"invalid chronological window for {symbol}/{threshold_id}")

        vals = item.get("thresholds")
        if not isinstance(vals, dict):
            raise ThresholdResolutionError(f"missing thresholds for {symbol}/{threshold_id}")
        required = {
            "Trend": ("r75", "e60"),
            "Strong Trend": ("r85", "e75"),
            "OR Continuation": ("or75", "ext60"),
        }
        for evt, fields in required.items():
            cfg = vals.get(evt)
            if not isinstance(cfg, dict):
                raise ThresholdResolutionError(f"missing {evt} for {symbol}/{threshold_id}")
            for field in fields:
                _finite(cfg.get(field), f"{symbol}/{threshold_id}/{evt}/{field}")
        hard = item.get("hard_earliest_offset")
        if hard is None:
            raise ThresholdResolutionError(f"missing hard_earliest_offset for {symbol}/{threshold_id}")
        if int(hard) not in (0, 15):
            raise ThresholdResolutionError(f"invalid hard_earliest_offset for {symbol}/{threshold_id}")
        by_symbol[symbol].append(item)

    if set(by_symbol) != expected or any(not by_symbol[s] for s in SYMBOLS):
        raise ThresholdResolutionError("V2 artifact does not cover all 29 canonical stocks")

    for symbol, items in by_symbol.items():
        items.sort(key=lambda x: _d(x["effective_nse_session_date"], "effective_nse_session_date"))
        previous_end: date | None = None
        for item in items:
            start = _d(item["oos_window"]["start"], "oos_window.start")
            end = _d(item["oos_window"]["end"], "oos_window.end")
            if previous_end is not None and start <= previous_end:
                raise ThresholdResolutionError(f"overlapping OOS windows for {symbol}")
            previous_end = end

    declared = artifact.get("threshold_set_count")
    if declared is not None and int(declared) != len(sets):
        raise ThresholdResolutionError("threshold_set_count does not match threshold_sets")


def resolve_v2_for_session(
    artifact: dict,
    symbol: str,
    target_session_date: str | date,
    *,
    require_priority_telemetry: bool = False,
) -> dict:
    """Return a V1-shaped threshold object for one stock/session, or fail closed.

    The returned structure is intentionally compatible with the existing causal
    detector's formula reader. No detector code is changed by this adapter.
    """
    validate_v2_artifact(artifact)
    symbol = str(symbol).strip().upper()
    if symbol not in SYMBOLS:
        raise ThresholdResolutionError(f"unknown canonical stock: {symbol}")
    target = target_session_date if isinstance(target_session_date, date) else _d(target_session_date, "target_session_date")

    candidates = []
    for item in artifact["threshold_sets"]:
        if str(item["stock"]).strip().upper() != symbol:
            continue
        effective = _d(item["effective_nse_session_date"], "effective_nse_session_date")
        train_end = _d(item["training_window"]["end"], "training_window.end")
        oos_end = _d(item["oos_window"]["end"], "oos_window.end")
        if not train_end < effective:
            raise ThresholdResolutionError(f"training window reaches effective session for {symbol}")
        if effective <= target <= oos_end:
            candidates.append(item)

    if not candidates:
        raise ThresholdResolutionError(f"no valid V2 threshold set covers {symbol} on {target.isoformat()}; fail closed")
    if len(candidates) != 1:
        raise ThresholdResolutionError(f"ambiguous V2 threshold coverage for {symbol} on {target.isoformat()}")

    item = candidates[0]
    vals = item["thresholds"]
    result = {
        "schema": "PSY29_EVENT_DETECTOR_THRESHOLDS_V1_ADAPTER",
        "research_source_commit": CANONICAL_RESEARCH_COMMIT,
        "threshold_set_id": item["threshold_set_id"],
        "effective_nse_session_date": item["effective_nse_session_date"],
        "training_window": item["training_window"],
        "oos_window": item["oos_window"],
        "stocks": {
            symbol: {
                "Trend": {"r75": _finite(vals["Trend"]["r75"], "Trend.r75"), "e60": _finite(vals["Trend"]["e60"], "Trend.e60"), "hard_earliest_offset": 0},
                "Strong Trend": {"r85": _finite(vals["Strong Trend"]["r85"], "Strong Trend.r85"), "e75": _finite(vals["Strong Trend"]["e75"], "Strong Trend.e75"), "hard_earliest_offset": 0},
                "OR Continuation": {"or75": _finite(vals["OR Continuation"]["or75"], "OR Continuation.or75"), "ext60": _finite(vals["OR Continuation"]["ext60"], "OR Continuation.ext60"), "hard_earliest_offset": 15},
            }
        },
    }

    # Historical timing telemetry is deliberately not fabricated. If a caller
    # requires Q25/Q75, it must be supplied by a separate canonical telemetry
    # artifact; causal threshold resolution itself remains unaffected.
    if require_priority_telemetry:
        missing = [evt for evt in EVENT_TYPES if not all(k in vals.get(evt, {}) for k in ("q25_offset", "q75_offset"))]
        if missing:
            raise ThresholdResolutionError("Q25/Q75 telemetry is required but unavailable for: " + ", ".join(missing))
    return result
