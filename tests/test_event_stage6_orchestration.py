from pathlib import Path
import json

import scripts.psy29_live_pipeline_service_cycle as cycle


def _result(tmp_path: Path, events):
    cycle.EVENT_OUT = tmp_path
    path = tmp_path / "PSY29_EVENT_DETECTOR_RESULT.json"
    path.write_text(json.dumps({"status":"PASS","mode":"live","detected_events":events}))
    return path


def test_zero_new_events_skips_stage6(tmp_path, monkeypatch):
    _result(tmp_path, [])
    calls = []
    monkeypatch.setattr(cycle, "run", lambda cmd: calls.append(cmd))
    assert cycle.run_stage6_on_new_events() == 0
    assert calls == []


def test_new_event_invokes_unchanged_stage6(tmp_path, monkeypatch):
    _result(tmp_path, [{"event_id":"NESTLEIND|Trend|2026-08-15|09:30:00+05:30"}])
    cycle.STAGE6 = tmp_path / "psy29_stage6_live_orchestrator.py"
    cycle.STAGE6.write_text("unchanged-stage6-wrapper")
    calls = []
    monkeypatch.setattr(cycle, "run", lambda cmd: calls.append(cmd))
    assert cycle.run_stage6_on_new_events() == 1
    assert len(calls) == 1
    assert Path(calls[0][0]) == cycle.STAGE6
    assert "--manifest" in calls[0] and "--snapshot" in calls[0] and "--output" in calls[0]


def test_malformed_detector_result_fails_closed(tmp_path):
    cycle.EVENT_OUT = tmp_path
    (tmp_path / "PSY29_EVENT_DETECTOR_RESULT.json").write_text("[]")
    try:
        cycle.run_stage6_on_new_events()
    except RuntimeError as exc:
        assert "invalid event detector result" in str(exc) or "did not return" in str(exc)
    else:
        raise AssertionError("malformed detector result must fail closed")
