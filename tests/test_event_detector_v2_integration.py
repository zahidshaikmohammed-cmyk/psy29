from datetime import date

import pytest

from scripts.psy29_event_detector import SYMBOLS
from scripts.psy29_event_threshold_resolver import (
    CANONICAL_RESEARCH_COMMIT,
    ThresholdResolutionError,
    resolve_v2_for_session,
    validate_v2_artifact,
)

from tests.test_event_threshold_resolver import WINDOWS, make_artifact


def test_v2_artifact_is_validated_by_actual_resolver():
    artifact = make_artifact()
    validate_v2_artifact(artifact)
    assert artifact["schema"] == "PSY29_EVENT_DETECTOR_THRESHOLDS_V2"
    assert artifact["research_source"]["commit"] == CANONICAL_RESEARCH_COMMIT
    assert artifact["methodology"] == {"train_sessions": 60, "test_sessions": 20, "step_sessions": 20}
    assert len(artifact["threshold_sets"]) == 116


def test_actual_resolver_selects_each_real_window_for_all_stocks():
    artifact = make_artifact()
    for symbol in SYMBOLS:
        for _, _, effective, oos_end, suffix in WINDOWS:
            selected = resolve_v2_for_session(artifact, symbol, effective)
            assert selected["threshold_set_id"] == f"{symbol}|{suffix}"
            selected = resolve_v2_for_session(artifact, symbol, oos_end)
            assert selected["threshold_set_id"] == f"{symbol}|{suffix}"


def test_actual_resolver_rejects_session_before_first_window():
    artifact = make_artifact()
    with pytest.raises(ThresholdResolutionError, match="no valid V2 threshold set"):
        resolve_v2_for_session(artifact, "NESTLEIND", date(2026, 3, 31))


def test_actual_resolver_rejects_session_after_final_window():
    artifact = make_artifact()
    with pytest.raises(ThresholdResolutionError, match="no valid V2 threshold set"):
        resolve_v2_for_session(artifact, "NESTLEIND", date(2026, 7, 29))


def test_actual_resolver_preserves_all_six_causal_values():
    artifact = make_artifact()
    selected = resolve_v2_for_session(artifact, "NESTLEIND", "2026-04-01")
    stock = selected["stocks"]["NESTLEIND"]
    assert stock["Trend"]["r75"] == 0.01
    assert stock["Trend"]["e60"] == 0.50
    assert stock["Strong Trend"]["r85"] == 0.015
    assert stock["Strong Trend"]["e75"] == 0.80
    assert stock["OR Continuation"]["or75"] == 0.02
    assert stock["OR Continuation"]["ext60"] == 0.004
    assert stock["Trend"]["hard_earliest_offset"] == 0
    assert stock["Strong Trend"]["hard_earliest_offset"] == 0
    assert stock["OR Continuation"]["hard_earliest_offset"] == 15


def test_actual_resolver_rejects_missing_stock_coverage():
    artifact = make_artifact()
    artifact["threshold_sets"] = [x for x in artifact["threshold_sets"] if x["stock"] != "NESTLEIND"]
    artifact["threshold_set_count"] = len(artifact["threshold_sets"])
    with pytest.raises(ThresholdResolutionError, match="29 canonical stocks"):
        validate_v2_artifact(artifact)


def test_actual_resolver_rejects_overlap():
    artifact = make_artifact()
    bad = dict(next(x for x in artifact["threshold_sets"] if x["stock"] == "NESTLEIND"))
    bad["threshold_set_id"] = "NESTLEIND|BAD"
    bad["effective_nse_session_date"] = "2026-04-15"
    bad["oos_window"] = {"start": "2026-04-15", "end": "2026-05-15", "session_count": 20}
    artifact["threshold_sets"].append(bad)
    artifact["threshold_set_count"] = len(artifact["threshold_sets"])
    with pytest.raises(ThresholdResolutionError, match="overlapping OOS windows"):
        validate_v2_artifact(artifact)


def test_q25_q75_are_explicitly_unavailable_not_fabricated():
    artifact = make_artifact()
    selected = resolve_v2_for_session(artifact, "NESTLEIND", "2026-04-01")
    causal = selected["stocks"]["NESTLEIND"]
    assert "q25_offset" not in causal["Trend"]
    assert "q75_offset" not in causal["Trend"]
    with pytest.raises(ThresholdResolutionError, match="Q25/Q75 telemetry is required"):
        resolve_v2_for_session(artifact, "NESTLEIND", "2026-04-01", require_priority_telemetry=True)


def test_no_v1_or_edge_profile_fallback_is_enforced():
    artifact = make_artifact()
    with pytest.raises(ThresholdResolutionError):
        resolve_v2_for_session(artifact, "NESTLEIND", "2026-08-15")
