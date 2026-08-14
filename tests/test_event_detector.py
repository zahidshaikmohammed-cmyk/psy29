from __future__ import annotations

import csv
import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from scripts.psy29_event_detector import SYMBOLS, process
from tests.test_event_threshold_resolver import make_artifact

IST = ZoneInfo("Asia/Kolkata")
TEST_SESSION = "2026-07-28"


def thresholds():
    return make_artifact()


def write_inputs(tmp_path: Path, ts: datetime, close: float = 100.0, high: float = 100.0, low: float = 100.0):
    snap = tmp_path / "live_pipeline_input.csv"
    rows = []
    for s in SYMBOLS:
        rows.append({
            "symbol": s, "timestamp": ts.isoformat(), "open_1m": 100, "high_1m": high,
            "low_1m": low, "close_1m": close, "volume_1m": 1000,
        })
    with snap.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=rows[0].keys()); writer.writeheader(); writer.writerows(rows)
    validation = tmp_path / "validation.json"
    validation.write_text(json.dumps({
        "status": "PASS", "mode": "live", "live_data": True, "provider": "DHAN",
        "fresh_count": 29, "fixture_count": 0, "coverage": {"actual": 29, "unique": 29},
        "generated_at": "2026-07-28T06:00:00Z",
    }), encoding="utf-8")
    threshold_path = tmp_path / "thresholds.json"
    threshold_path.write_text(json.dumps(thresholds()), encoding="utf-8")
    return snap, validation, threshold_path


def run_one(tmp_path, ts, close=100.0, high=100.0, low=100.0, state=None):
    snap, validation, threshold_path = write_inputs(tmp_path, ts, close, high, low)
    state = state or tmp_path / "state.json"
    out = tmp_path / "out"
    return process(snap, validation, threshold_path, state, out, "live"), state


def test_trend_and_strong_first_detection_are_current_bar_only(tmp_path):
    base = datetime(2026, 7, 28, 9, 15, tzinfo=IST)
    state = tmp_path / "state.json"
    run_one(tmp_path, base, close=100.0, state=state)
    result, _ = run_one(tmp_path, base + timedelta(minutes=1), close=102.0, state=state)
    events = {(e["instrument"], e["event_type"], e["first_detectable_timestamp"]) for e in result["detected_events"]}
    assert ("NESTLEIND", "Trend", (base + timedelta(minutes=1)).isoformat()) in events
    assert ("NESTLEIND", "Strong Trend", (base + timedelta(minutes=1)).isoformat()) in events


def test_no_lookahead_and_first_timestamp_immutable(tmp_path):
    base = datetime(2026, 7, 28, 9, 15, tzinfo=IST)
    state = tmp_path / "state.json"
    result, _ = run_one(tmp_path, base, close=100.0, state=state)
    assert result["detected_events"] == []
    result, _ = run_one(tmp_path, base + timedelta(minutes=1), close=102.0, state=state)
    assert len([e for e in result["detected_events"] if e["instrument"] == "NESTLEIND"]) == 2
    result, _ = run_one(tmp_path, base + timedelta(minutes=2), close=104.0, state=state)
    assert result["detected_events"] == []
    saved = json.loads(state.read_text())
    evt = saved["sessions"]["NESTLEIND|2026-07-28"]["events"]["Trend"]
    assert evt["first_detectable_timestamp"] == (base + timedelta(minutes=1)).isoformat()


def test_duplicate_current_bar_does_not_create_duplicate(tmp_path):
    base = datetime(2026, 7, 28, 9, 15, tzinfo=IST)
    state = tmp_path / "state.json"
    run_one(tmp_path, base, state=state)
    first, _ = run_one(tmp_path, base + timedelta(minutes=1), close=102, state=state)
    second, _ = run_one(tmp_path, base + timedelta(minutes=1), close=102, state=state)
    assert len(first["detected_events"]) > 0
    assert second["detected_events"] == []


def test_or_continuation_requires_completed_opening_range(tmp_path):
    base = datetime(2026, 7, 28, 9, 15, tzinfo=IST)
    state = tmp_path / "state.json"
    for i in range(15):
        run_one(tmp_path, base + timedelta(minutes=i), close=100, high=100, low=99, state=state)
    result, _ = run_one(tmp_path, base + timedelta(minutes=15), close=100.5, high=101, low=100, state=state)
    assert any(e["event_type"] == "OR Continuation" and e["instrument"] == "NESTLEIND" for e in result["detected_events"])


def test_cutoff_is_inclusive_and_q25_q75_are_not_fabricated(tmp_path):
    base = datetime(2026, 7, 28, 15, 0, tzinfo=IST)
    state = tmp_path / "state.json"
    run_one(tmp_path, base - timedelta(minutes=1), close=100, state=state)
    snap, validation, threshold_path = write_inputs(tmp_path, base, close=102)
    result = process(snap, validation, threshold_path, state, tmp_path / "out", "live")
    evt = next(e for e in result["detected_events"] if e["instrument"] == "NESTLEIND" and e["event_type"] == "Trend")
    assert evt["new_signal_eligible_by_cutoff"] is True
    assert evt["historical_priority"] == "UNAVAILABLE_Q25_Q75_NOT_IN_V2"


def test_fixture_and_invalid_provenance_fail_closed(tmp_path):
    base = datetime(2026, 7, 28, 9, 15, tzinfo=IST)
    snap, validation, threshold_path = write_inputs(tmp_path, base, close=102)
    data = json.loads(validation.read_text()); data.update({"mode": "fixture", "live_data": False, "fixture_count": 29}); validation.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="live-only"):
        process(snap, validation, threshold_path, tmp_path / "state.json", tmp_path / "out", "fixture")
    data.update({"mode": "live", "live_data": True, "fixture_count": 0, "status": "FAIL"}); validation.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="status"):
        process(snap, validation, threshold_path, tmp_path / "state2.json", tmp_path / "out2", "live")


def test_event_state_is_separate_from_emission_state(tmp_path):
    base = datetime(2026, 7, 28, 9, 15, tzinfo=IST)
    result, state = run_one(tmp_path, base, close=102)
    assert state.name == "state.json"
    assert not (tmp_path / "emission_ledger.json").exists()
    assert result["contract"] == "PSY29_CAUSAL_EVENT_DETECTOR_V1"
