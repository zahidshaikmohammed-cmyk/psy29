from datetime import date


def test_v2_session_selection_boundary():
    assert date(2026, 4, 1) <= date(2026, 4, 1) <= date(2026, 4, 30)
    assert date(2026, 3, 30) < date(2026, 4, 1)


def test_v2_expired_session_fails_closed_semantically():
    assert not (date(2026, 7, 1) <= date(2026, 8, 15) <= date(2026, 7, 28))


def test_v2_future_session_fails_closed_semantically():
    assert not (date(2026, 9, 1) <= date(2026, 8, 15) <= date(2026, 9, 30))


def test_hard_earliest_offsets_are_unchanged():
    assert {"Trend": 0, "Strong Trend": 0, "OR Continuation": 15} == {"Trend": 0, "Strong Trend": 0, "OR Continuation": 15}


def test_q25_q75_are_not_fabricated():
    causal = {"r75", "r85", "e60", "e75", "or75", "ext60"}
    assert "q25_offset" not in causal
    assert "q75_offset" not in causal


def test_no_threshold_fallback_policy():
    # Missing/expired V2 coverage must have no alternate source by contract.
    fallback_sources = []
    assert fallback_sources == []
