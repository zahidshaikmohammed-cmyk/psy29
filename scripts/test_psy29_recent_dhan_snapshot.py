from datetime import datetime
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.psy29_recent_dhan_snapshot import candidate_dates


def test_after_close_uses_today_as_latest_completed_session():
    dates = candidate_dates(datetime(2026, 8, 14, 23, 0), limit=5)
    assert [d.isoformat() for d in dates] == [
        "2026-08-14", "2026-08-13", "2026-08-12", "2026-08-11", "2026-08-10"
    ]


def test_before_open_uses_previous_weekday():
    dates = candidate_dates(datetime(2026, 8, 17, 8, 30), limit=5)
    assert [d.isoformat() for d in dates] == [
        "2026-08-14", "2026-08-13", "2026-08-12", "2026-08-11", "2026-08-10"
    ]


def test_candidate_dates_never_include_weekend():
    dates = candidate_dates(datetime(2026, 8, 16, 12, 0), limit=10)
    assert all(d.weekday() < 5 for d in dates)
    assert len(dates) == 10
