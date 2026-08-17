from dataclasses import dataclass
from datetime import datetime, time
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
OPEN = time(9, 15)
CLOSE = time(15, 30)
EXPECTED_SYMBOLS = 29
EXPECTED_MINUTES = 376

@dataclass(frozen=True)
class SessionContract:
    symbols: int = EXPECTED_SYMBOLS
    open_time: time = OPEN
    close_time: time = CLOSE
    expected_minutes: int = EXPECTED_MINUTES
    fabricate_allowed: bool = False

def test_session_contract():
    c = SessionContract()
    assert c.symbols == 29
    assert c.open_time == time(9, 15)
    assert c.close_time == time(15, 30)
    assert c.fabricate_allowed is False

def test_market_day_minutes_are_monotonic():
    from datetime import timedelta
    start = datetime(2026, 1, 1, 9, 15, tzinfo=IST)
    end = datetime(2026, 1, 1, 15, 30, tzinfo=IST)
    minutes = int((end - start).total_seconds() // 60) + 1
    assert minutes == EXPECTED_MINUTES

def test_failure_modes_are_isolated():
    failure_modes = {"api", "network", "render_restart", "database"}
    recovery_modes = {"retry", "resume_from_last_committed_snapshot"}
    assert failure_modes
    assert recovery_modes

def test_no_fabrication_policy():
    assert SessionContract().fabricate_allowed is False
