from datetime import datetime

from scripts.psy29_recent_dhan_snapshot import candidate_dates


def test_candidate_dates_are_prior_weekdays():
    dates = candidate_dates(datetime(2026, 8, 17), limit=5)
    assert [d.isoformat() for d in dates] == [
        "2026-08-14", "2026-08-13", "2026-08-12", "2026-08-11", "2026-08-10"
    ]


def test_candidate_dates_never_include_weekend():
    dates = candidate_dates(datetime(2026, 8, 16), limit=10)
    assert all(d.weekday() < 5 for d in dates)
    assert len(dates) == 10
