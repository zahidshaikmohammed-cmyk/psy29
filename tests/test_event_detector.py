from __future__ import annotations

import csv
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from scripts.psy29_event_detector import SYMBOLS, process

IST = ZoneInfo("Asia/Kolkata")


def _weekdays(start: date, count: int):
    out = []
    cur = start
    while len(out) < count:
        if cur.weekday() < 5:
            out.append(cur)
        cur += timedelta(days=1)
    return out


def thresholds():
    effective_blocks = _weekdays(date(2026, 8, 17), 80)
    sets = []
    for symbol in SYMBOLS:
        for block in range(4):
            oos_dates = effective_blocks[block * 20:(block + 1) * 20]
            effective = oos_dates[0]
            training_end = effective - timedelta(days=1)
            training_dates = []
            cur = training_end
            while len(training_dates) < 60:
                if cur.weekday() < 5:
                    training_dates.append(cur)
                cur -= timedelta(days=1)
            training_dates.reverse()
            sets.append({
                "threshold_set_id": f"TEST_{symbol}_{block + 1}",
                "stock": symbol,
                "effective_nse_session_date": effective.isoformat(),
                "training_window": {"start": training_dates[0].isoformat(), "end": training_dates[-1].isoformat(), "session_count": 60},
                "oos_window": {"start": oos_dates[0].isoformat(), "end": oos_dates[-1].isoformat(), "session_count": 20},
                "hard_earliest_offset": 0 if block < 4 else 15,
                "thresholds": {
                    "Trend": {"r75": 0.01, "e60": 0.5},
                    "Strong Trend": {"r85": 0.015, "e75": 0.8},
                    "OR Continuation": {"or75": 0.02, "ext60": 0.004},
                },
            })
            sets[-1]["hard_earliest_offset"] = 0
            # OR Continuation has its own canonical earliest offset.
            sets[-1]["thresholds"]["Trend"]["hard_earliest_offset"] = 0
            sets[-1]["thresholds"]["Strong Trend"]["hard_earliest_offset"] = 0
            sets[-1]["thresholds"]["OR Continuation"]["hard_earliest_offset"] = 15
    return {
        "schema": "PSY29_EVENT_DETECTOR_THRESHOLDS_V2",
        "research_source": {"commit": "988472889edfd51046731d72f68f2e96e095a2f1"},
        "methodology": {"train_sessions": 60, "test_sessions": 20, "step_sessions": 20},
        "threshold_set_count": len(sets),
        "threshold_sets": sets,
    }


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
        "generated_at": "2026-08-17T06:00:00Z",
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
    base = datetime(2026, 8, 17, 9, 15, tzinfo=IST)
    state = tmp_path / "state.json"
    run_one(tmp_path, base, close=100.0, state=state)
    result, _ = run_one(tmp_path, base + timedelta(minutes=1), close=102.0, state=state)
    events = {(e["instrument"], e["event_type"], e["first_detectable_timestamp"]) for e in result["detected_events"]}
    assert ("NESTLEIND", "Trend", (base + timedelta(minutes=1)).isoformat()) in events
    assert ("NESTLEIND", "Strong Trend", (base + timedelta(minutes=1)).isoformat()) in events


def test_no_lookahead_and_first_timestamp_immutable(tmp_path):
    base = datetime(2026, 8, 17, 9, 15, tzinfo=IST)
    state = tmp_path / "state.json"
    result, _ = run_one(tmp_path, base, close=100.0, state=state)
    assert result["detected_events"] == []
    result, _ = run_one(tmp_path, base + timedelta(minutes=1), close=102.0, state=state)
    assert len([e for e in result["detected_events"] if e["instrument"] == "NESTLEIND"]) == 2
    result, _ = run_one(tmp_path, base + timedelta(minutes=2), close=104.0, state=state)
    assert result["detected_events"] == []
    saved = json.loads(state.read_text())
    evt = saved["sessions"]["NESTLEIND|2026-08-17"]["events"]["Trend"]
    assert evt["first_detectable_timestamp"] == (base + timedelta(minutes=1)).isoformat()


def test_duplicate_current_bar_does_not_create_duplicate(tmp_path):
    base = datetime(2026, 8, 17, 9, 15, tzinfo=IST)
    state = tmp_path / "state.json"
    run_one(tmp_path, base, state=state)
    first, _ = run_one(tmp_path, base + timedelta(minutes=1), close=102, state=state)
    second, _ = run_one(tmp_path, base + timedelta(minutes=1), close=102, state=state)
    assert len(first["detected_events"]) > 0
    assert second["detected_events"] == []


def test_or_continuation_requires_completed_opening_range(tmp_path):
    base = datetime(2026, 8, 17, 9, 15, tzinfo=IST)
    state = tmp_path / "state.json"
    for i in range(15):
        run_one(tmp_path, base + timedelta(minutes=i), close=100, high=100, low=99, state=state)
    result, _ = run_one(tmp_path, base + timedelta(minutes=15), close=100.5, high=101, low=100, state=state)
    assert any(e["event_type"] == "OR Continuation" and e["instrument"] == "NESTLEIND" for e in result["detected_events"])


def test_cutoff_is_inclusive_and_priority_is_non_blocking(tmp_path):
    base = datetime(2026, 8, 17, 15, 0, tzinfo=IST)
    state = tmp_path / "state.json"
    run_one(tmp_path, base - timedelta(minutes=1), close=100, state=state)
    snap, validation, threshold_path = write_inputs(tmp_path, base, close=102)
    result = process(snap, validation, threshold_path, state, tmp_path / "out", "live")
    evt = next(e for e in result["detected_events"] if e["instrument"] == "NESTLEIND" and e["event_type"] == "Trend")
    assert evt["new_signal_eligible_by_cutoff"] is True
    assert evt["historical_priority"] == "UNAVAILABLE_Q25_Q75_NOT_IN_V2"


def test_fixture_and_invalid_provenance_fail_closed(tmp_path):
    base = datetime(2026, 8, 17, 9, 15, tzinfo=IST)
    snap, validation, threshold_path = write_inputs(tmp_path, base, close=102)
    data = json.loads(validation.read_text()); data.update({"mode": "fixture", "live_data": False, "fixture_count": 29}); validation.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="live-only"):
        process(snap, validation, threshold_path, tmp_path / "state.json", tmp_path / "out", "fixture")
    data.update({"mode": "live", "live_data": True, "fixture_count": 0, "status": "FAIL"}); validation.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="status"):
        process(snap, validation, threshold_path, tmp_path / "state2.json", tmp_path / "out2", "live")


def test_event_state_is_separate_from_emission_state(tmp_path):
    base = datetime(2026, 8, 17, 9, 15, tzinfo=IST)
    result, state = run_one(tmp_path, base, close=102)
    assert state.name == "state.json"
    assert not (tmp_path / "emission_ledger.json").exists()
    assert result["contract"] == "PSY29_CAUSAL_EVENT_DETECTOR_V1"
