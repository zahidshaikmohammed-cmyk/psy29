from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

@dataclass(frozen=True)
class QualityResult:
    accepted: bool
    reason: str
    field: Optional[str] = None


def _dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        d = value
    else:
        d = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if d.tzinfo is None:
        raise ValueError('timestamp must be timezone-aware')
    return d.astimezone(timezone.utc)


def validate_snapshot(snapshot: dict, *, expected_security_id: int, expected_symbol: str,
                      observed_at: datetime, previous_minute: Optional[datetime] = None,
                      seen_keys: Optional[set] = None) -> QualityResult:
    if snapshot.get('symbol') != expected_symbol:
        return QualityResult(False, 'wrong-security', 'symbol')
    if int(snapshot.get('security_id', -1)) != int(expected_security_id):
        return QualityResult(False, 'wrong-security', 'security_id')
    try:
        ts = _dt(snapshot['timestamp'])
        now = _dt(observed_at)
    except Exception:
        return QualityResult(False, 'invalid-timestamp', 'timestamp')
    if ts > now:
        return QualityResult(False, 'future-timestamp', 'timestamp')
    if previous_minute is not None and ts < _dt(previous_minute):
        return QualityResult(False, 'stale-timestamp', 'timestamp')
    key = (snapshot['symbol'], ts.isoformat())
    if seen_keys is not None and key in seen_keys:
        return QualityResult(False, 'duplicate')
    if snapshot.get('last_price') is None:
        return QualityResult(False, 'missing-data', 'last_price')
    try:
        if Decimal(str(snapshot['last_price'])) <= 0:
            return QualityResult(False, 'invalid-price', 'last_price')
    except Exception:
        return QualityResult(False, 'invalid-price', 'last_price')
    return QualityResult(True, 'accepted')


def validate_candle(candle: dict) -> QualityResult:
    required = ('open', 'high', 'low', 'close', 'volume')
    if any(candle.get(k) is None for k in required):
        return QualityResult(False, 'missing-data')
    try:
        o, h, l, c = [Decimal(str(candle[k])) for k in ('open','high','low','close')]
        v = Decimal(str(candle['volume']))
    except Exception:
        return QualityResult(False, 'invalid-numeric')
    if min(o, h, l, c) <= 0 or h < max(o, c) or l > min(o, c) or h < l:
        return QualityResult(False, 'invalid-OHLC')
    if v < 0:
        return QualityResult(False, 'invalid-volume')
    return QualityResult(True, 'accepted')


def validate_complete_stock_set(records: list[dict], expected_symbols: set[str]) -> dict:
    received = {r.get('symbol') for r in records}
    missing = sorted(expected_symbols - received)
    unexpected = sorted(received - expected_symbols)
    return {'complete': not missing and not unexpected, 'missing': missing, 'unexpected': unexpected}


def audit_event(event: str, *, symbol: Optional[str], accepted: bool, reason: str,
                provider: str, observed_at: datetime, source_timestamp: Optional[Any] = None) -> dict:
    return {'event': event, 'symbol': symbol, 'accepted': accepted, 'reason': reason,
            'provider': provider, 'observed_at': _dt(observed_at).isoformat(),
            'source_timestamp': _dt(source_timestamp).isoformat() if source_timestamp else None}
