from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, time
from enum import Enum
from hashlib import sha256
from typing import Callable, Protocol
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
OPEN = time(9, 15)
CLOSE = time(15, 30)
EXPECTED_MINUTES = 376


class FailureMode(str, Enum):
    API = "api"
    NETWORK = "network"
    RENDER_RESTART = "render_restart"
    DATABASE = "database"


class MarketDataProvider(Protocol):
    def fetch_minute(self, symbol: str, minute: datetime) -> dict: ...


class SnapshotStore(Protocol):
    def commit(self, snapshot: dict) -> None: ...
    def last_committed_minute(self, symbol: str, session_date: str) -> datetime | None: ...
    def contains(self, symbol: str, minute: datetime) -> bool: ...


@dataclass(frozen=True)
class SessionContract:
    symbols: tuple[str, ...]
    open_time: time = OPEN
    close_time: time = CLOSE
    expected_minutes: int = EXPECTED_MINUTES
    fabricate_allowed: bool = False

    def minutes(self, session_date: str) -> list[datetime]:
        start = datetime.fromisoformat(f"{session_date}T09:15:00+05:30").astimezone(IST)
        return [start + timedelta(minutes=i) for i in range(self.expected_minutes)]

    def validate_clock(self, minute: datetime) -> None:
        local = minute.astimezone(IST)
        if not (self.open_time <= local.time() <= self.close_time):
            raise ValueError("minute outside NSE session window")


@dataclass
class AuditTrail:
    events: list[dict] = field(default_factory=list)

    def record(self, event: str, **details) -> None:
        self.events.append({"event": event, "details": details})


@dataclass
class SessionRunner:
    contract: SessionContract
    provider: MarketDataProvider
    store: SnapshotStore
    audit: AuditTrail = field(default_factory=AuditTrail)
    retry_limit: int = 3
    failure_hook: Callable[[FailureMode, str, datetime], None] | None = None

    def run(self, session_date: str) -> dict:
        minutes = self.contract.minutes(session_date)
        self.audit.record("session_start", session_date=session_date, start=minutes[0].isoformat())
        committed = 0
        for minute in minutes:
            self.contract.validate_clock(minute)
            for symbol in self.contract.symbols:
                if self.store.contains(symbol, minute):
                    self.audit.record("snapshot_already_committed", symbol=symbol, minute=minute.isoformat())
                    continue
                snapshot = self._fetch_with_recovery(symbol, minute)
                self._validate_real_snapshot(snapshot, symbol, minute)
                self._commit_with_recovery(snapshot, symbol, minute)
                committed += 1
                self.audit.record("snapshot_committed", symbol=symbol, minute=minute.isoformat(), source=snapshot["source"])
        self.audit.record("session_shutdown", session_date=session_date, close=minutes[-1].isoformat())
        return {"session_date": session_date, "symbols": len(self.contract.symbols), "minutes": len(minutes), "snapshots": committed, "fabricated": False}

    def _fetch_with_recovery(self, symbol: str, minute: datetime) -> dict:
        last_error = None
        for attempt in range(1, self.retry_limit + 1):
            try:
                if self.failure_hook:
                    self.failure_hook(FailureMode.API, symbol, minute)
                snapshot = self.provider.fetch_minute(symbol, minute)
                if not snapshot:
                    raise RuntimeError("empty provider response")
                self.audit.record("provider_success", symbol=symbol, minute=minute.isoformat(), attempt=attempt)
                return snapshot
            except Exception as exc:
                last_error = exc
                self.audit.record("provider_failure", symbol=symbol, minute=minute.isoformat(), attempt=attempt, error=type(exc).__name__)
        raise RuntimeError(f"provider recovery exhausted for {symbol} {minute.isoformat()}") from last_error

    def _commit_with_recovery(self, snapshot: dict, symbol: str, minute: datetime) -> None:
        last_error = None
        for attempt in range(1, self.retry_limit + 1):
            try:
                if self.failure_hook:
                    self.failure_hook(FailureMode.DATABASE, symbol, minute)
                self.store.commit(snapshot)
                self.audit.record("database_commit_success", symbol=symbol, minute=minute.isoformat(), attempt=attempt)
                return
            except Exception as exc:
                last_error = exc
                self.audit.record("database_commit_failure", symbol=symbol, minute=minute.isoformat(), attempt=attempt, error=type(exc).__name__)
        raise RuntimeError(f"database recovery exhausted for {symbol} {minute.isoformat()}") from last_error

    @staticmethod
    def _validate_real_snapshot(snapshot: dict, symbol: str, minute: datetime) -> None:
        if snapshot.get("symbol") != symbol:
            raise ValueError("wrong security")
        if snapshot.get("source") != "DHAN":
            raise ValueError("snapshot source must be DHAN")
        provider_ts = snapshot.get("provider_timestamp")
        if not provider_ts:
            raise ValueError("provider timestamp missing")
        if not snapshot.get("raw"):
            raise ValueError("raw provider payload missing")
        if snapshot.get("fabricated") is True:
            raise ValueError("fabricated snapshots are forbidden")
        if provider_ts > minute:
            raise ValueError("future provider timestamp")


def audit_checksum(audit: AuditTrail) -> str:
    return sha256(repr(audit.events).encode("utf-8")).hexdigest()
