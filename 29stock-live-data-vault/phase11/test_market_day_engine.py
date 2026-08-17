from full_market_day_engine import FailureMode, SessionContract, SessionRunner

SYMBOLS = tuple(f"S{i:02d}" for i in range(29))


class MemoryStore:
    def __init__(self, failures=0):
        self.rows = []
        self.failures = failures

    def commit(self, snapshot):
        if self.failures:
            self.failures -= 1
            raise ConnectionError("simulated database failure")
        if not self.contains(snapshot["symbol"], snapshot["minute"]):
            self.rows.append(snapshot)

    def contains(self, symbol, minute):
        return any(r["symbol"] == symbol and r["minute"] == minute for r in self.rows)

    def last_committed_minute(self, symbol, session_date):
        rows = [r for r in self.rows if r["symbol"] == symbol and r["session_date"] == session_date]
        return max((r["minute"] for r in rows), default=None)


class FakeProvider:
    def __init__(self, failures=0):
        self.failures = failures
        self.calls = 0

    def fetch_minute(self, symbol, minute):
        self.calls += 1
        if self.failures:
            self.failures -= 1
            raise ConnectionError("simulated transient API/network failure")
        return {
            "symbol": symbol,
            "source": "DHAN",
            "provider_timestamp": minute,
            "raw": {"security_id": symbol, "quote": {"ltp": 100.0}},
            "fabricated": False,
            "minute": minute,
            "session_date": minute.date().isoformat(),
        }


def test_engine_collects_complete_simulated_session():
    store = MemoryStore()
    provider = FakeProvider()
    result = SessionRunner(SessionContract(SYMBOLS), provider, store).run("2026-08-17")
    assert result == {"session_date": "2026-08-17", "symbols": 29, "minutes": 376, "snapshots": 29 * 376, "fabricated": False}
    assert len(store.rows) == 29 * 376


def test_transient_api_network_failures_recover_without_fabrication():
    store = MemoryStore()
    provider = FakeProvider(failures=3)
    result = SessionRunner(SessionContract(SYMBOLS), provider, store, retry_limit=4).run("2026-08-17")
    assert result["snapshots"] == 29 * 376
    assert all(row["fabricated"] is False for row in store.rows)


def test_transient_database_failures_recover_without_duplicates():
    store = MemoryStore(failures=3)
    result = SessionRunner(SessionContract(SYMBOLS), FakeProvider(), store, retry_limit=4).run("2026-08-17")
    assert result["snapshots"] == 29 * 376
    assert len(store.rows) == len({(r["symbol"], r["minute"]) for r in store.rows})


def test_wrong_security_is_rejected():
    minute = SessionContract(SYMBOLS).minutes("2026-08-17")[0]
    bad = {"symbol": "OTHER", "source": "DHAN", "provider_timestamp": minute, "raw": {"x": 1}, "fabricated": False}
    try:
        SessionRunner._validate_real_snapshot(bad, "S00", minute)
        assert False
    except ValueError as exc:
        assert "wrong security" in str(exc)


def test_fabricated_snapshot_is_rejected():
    minute = SessionContract(SYMBOLS).minutes("2026-08-17")[0]
    bad = {"symbol": "S00", "source": "DHAN", "provider_timestamp": minute, "raw": {"x": 1}, "fabricated": True}
    try:
        SessionRunner._validate_real_snapshot(bad, "S00", minute)
        assert False
    except ValueError as exc:
        assert "fabricated" in str(exc)


def test_future_timestamp_is_rejected():
    minute = SessionContract(SYMBOLS).minutes("2026-08-17")[0]
    bad = {"symbol": "S00", "source": "DHAN", "provider_timestamp": minute.replace(minute=minute.minute + 1), "raw": {"x": 1}, "fabricated": False}
    try:
        SessionRunner._validate_real_snapshot(bad, "S00", minute)
        assert False
    except ValueError as exc:
        assert "future" in str(exc)
