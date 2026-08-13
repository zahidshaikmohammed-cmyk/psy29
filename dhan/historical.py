"""Historical intraday acquisition from DhanHQ v2.

Dhan's intraday endpoint supports 1-minute candles and permits up to 90 days
per request. This module chunks a requested date range into <=90-day windows.
"""

from __future__ import annotations

import time
from datetime import date, datetime, timedelta
from typing import Any

from .client import DhanClient

MAX_WINDOW_DAYS = 90


def _date_string(value: date | datetime) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return value.strftime("%Y-%m-%d 09:15:00")


def fetch_intraday(
    client: DhanClient,
    security_id: str,
    from_date: date,
    to_date: date,
    interval: str = "1",
    exchange_segment: str = "NSE_EQ",
    instrument: str = "EQUITY",
    sleep_seconds: float = 0.22,
) -> list[dict[str, Any]]:
    """Fetch and normalize Dhan candle arrays into row records."""
    rows: list[dict[str, Any]] = []
    cursor = from_date
    while cursor <= to_date:
        window_end = min(cursor + timedelta(days=MAX_WINDOW_DAYS - 1), to_date)
        payload = {
            "securityId": str(security_id),
            "exchangeSegment": exchange_segment,
            "instrument": instrument,
            "interval": str(interval),
            "oi": False,
            "fromDate": _date_string(cursor),
            "toDate": _date_string(window_end).replace("09:15:00", "15:30:00"),
        }
        data = client.post("/charts/intraday", payload)
        timestamps = data.get("timestamp", [])
        for i, ts in enumerate(timestamps):
            rows.append(
                {
                    "security_id": str(security_id),
                    "timestamp": ts,
                    "open": data.get("open", [])[i],
                    "high": data.get("high", [])[i],
                    "low": data.get("low", [])[i],
                    "close": data.get("close", [])[i],
                    "volume": data.get("volume", [])[i],
                }
            )
        cursor = window_end + timedelta(days=1)
        time.sleep(sleep_seconds)
    return rows
