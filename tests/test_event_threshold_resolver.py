from __future__ import annotations

from copy import deepcopy

import pytest

from scripts.psy29_event_detector import SYMBOLS
from scripts.psy29_event_threshold_resolver import (
    CANONICAL_RESEARCH_COMMIT,
    ThresholdResolutionError,
    resolve_v2_for_session,
    validate_v2_artifact,
)


def make_artifact():
    sets = []
    windows = [
        ("2026-01-01", "2026-03-30", "2026-04-01", "2026-04-30", "A"),
        ("2026-02-01", "2026-04-30", "2026-05-04", "2026-06-01", "B"),
    ]
    for symbol in SYMBOLS:
        for train_start, train_end, effective, oos_end, suffix in windows:
            sets.append({
                "threshold_set_id": f"{symbol}|{suffix}",
                "stock": symbol,
                "effective_nse_session_date": effective,
                "training_window": {"start": train_start, "end": train_end, "session_count": 60},
                "oos_window": {"start": effective, "end": oos_end, "session_count": 20},
                "hard_earliest_offset": 15,
                "thresholds": {
                    "Trend": {"r75": 0.01, "e60": 0.50},
                    "Strong Trend": {"r85": 0.015, "e75": 0.80},
                    "OR Continuation": {"or75": 0.02, "ext60": 0.004},
                },
            })
    return {
        "schema": "PSY29_EVENT_DETECTOR_THRESHOLDS_V2",
        "research_source": {"commit": CANONICAL_RESEARCH_COMMIT},
        "methodology": {"train_sessions": 60, "test_sessions": 20, "step_sessions": 20},
        "threshold_set_count": len(sets),
        "threshold_sets": sets,
    }


def test_selects_exact_effective_oos_window():
    artifact = make_artifact()
    result = resolve_v2_for_session(artifact, "NESTLEIND", "2026-05-04")
    assert result["threshold_set_id"] == "NESTLEIND|B"
    assert result["stocks"]["NESTLEIND"]["Trend"]["r75"] == 0.01
    assert result["stocks"]["NESTLEIND"]["OR Continuation"]["hard_earliest_offset"] == 15


def test_first_and_last_valid_oos_dates():
    artifact = make_artifact()
    assert resolve_v2_for_session(artifact, "NESTLEIND", "2026-04-01")["threshold_set_id"] == "NESTLEIND|A"
    assert resolve_v2_for_session(artifact, "NESTLEIND", "2026-04-30")["threshold_set_id"] == "NESTLEIND|A"
    assert resolve_v2_for_session(artifact, "NESTLEIND", "2026-05-04")["threshold_set_id"] == "NESTLEIND|B"
    assert resolve_v2_for_session(artifact, "NESTLEIND", "2026-06-01")["threshold_set_id"] == "NESTLEIND|B"


def test_expired_threshold_is_rejected():
    with pytest.raises(ThresholdResolutionError, match="no valid V2 threshold set"):
        resolve_v2_for_session(make_artifact(), "NESTLEIND", "2026-06-02")


def test_future_threshold_is_rejected():
    with pytest.raises(ThresholdResolutionError, match="no valid V2 threshold set"):
        resolve_v2_for_session(make_artifact(), "NESTLEIND", "2026-03-31")


def test_missing_threshold_is_fail_closed():
    artifact = make_artifact()
    artifact["threshold_sets"] = [x for x in artifact["threshold_sets"] if x["stock"] != "NESTLEIND"]
    artifact["threshold_set_count"] = len(artifact["threshold_sets"])
    with pytest.raises(ThresholdResolutionError, match="29 canonical stocks"):
        validate_v2_artifact(artifact)


def test_overlapping_windows_are_rejected():
    artifact = make_artifact()
    bad = deepcopy(next(x for x in artifact["threshold_sets"] if x["stock"] == "NESTLEIND"))
    bad["threshold_set_id"] = "NESTLEIND|OVERLAP"
    bad["effective_nse_session_date"] = "2026-04-15"
    bad["oos_window"] = {"start": "2026-04-15", "end": "2026-05-15", "session_count": 20}
    artifact["threshold_sets"].append(bad)
    artifact["threshold_set_count"] = len(artifact["threshold_sets"])
    with pytest.raises(ThresholdResolutionError, match="overlapping OOS windows"):
        validate_v2_artifact(artifact)


def test_malformed_training_boundary_is_rejected():
    artifact = make_artifact()
    artifact["threshold_sets"][0]["training_window"]["end"] = "2026-04-01"
    with pytest.raises(ThresholdResolutionError, match="invalid chronological window"):
        validate_v2_artifact(artifact)


def test_no_static_or_v1_fallback():
    artifact = make_artifact()
    with pytest.raises(ThresholdResolutionError):
        resolve_v2_for_session(artifact, "NESTLEIND", "2026-08-15")


def test_priority_telemetry_boundary_fails_only_when_required():
    artifact = make_artifact()
    causal = resolve_v2_for_session(artifact, "NESTLEIND", "2026-04-01")
    assert "q25_offset" not in causal["stocks"]["NESTLEIND"]["Trend"]
    with pytest.raises(ThresholdResolutionError, match="Q25/Q75 telemetry is required"):
        resolve_v2_for_session(artifact, "NESTLEIND", "2026-04-01", require_priority_telemetry=True)


def test_exact_29_stock_coverage():
    artifact = make_artifact()
    validate_v2_artifact(artifact)
    assert {x["stock"] for x in artifact["threshold_sets"]} == set(SYMBOLS)
    assert len(artifact["threshold_sets"]) == 58
