#!/usr/bin/env python3
"""Regression tests for the production 1-minute DHAN indicator contract.

These tests protect the live add_indicators_1m() semantics without changing the
PSY29 stage architecture:
- EMA9/EMA20 are seeded from completed historical 1m bars, not today's first bar.
- VWAP is reset to the current NSE session and accumulates only current-session bars.
- The opening range is exactly the completed 09:15-09:29 window.
- Only completed candles are eligible.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

from scripts.psy29_live_dhan_acquisition import add_indicators_1m


def make_fixture() -> tuple[pd.DataFrame, datetime]:
    session = datetime(2026, 8, 17, 9, 15, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    rows = []

    # Historical warm-up: 30 completed bars before today's session.
    for i in range(30):
        dt = session - timedelta(minutes=30 - i)
        price = 100.0 + i * 0.2
        rows.append(
            {
                "timestamp": int(dt.timestamp()),
                "open": price,
                "high": price + 0.5,
                "low": price - 0.5,
                "close": price + 0.2,
                "volume": 1000 + i,
            }
        )

    # Today's 09:15-09:31 completed bars.
    for i in range(17):
        dt = session + timedelta(minutes=i)
        price = 110.0 + i * 0.1
        rows.append(
            {
                "timestamp": int(dt.timestamp()),
                "open": price,
                "high": price + 0.4 + (0.1 if i == 4 else 0),
                "low": price - 0.4 - (0.1 if i == 7 else 0),
                "close": price + 0.1,
                "volume": 2000 + i * 10,
            }
        )

    # now is 09:32, so 09:31 is completed while 09:32 is not present.
    now = session + timedelta(minutes=17)
    return pd.DataFrame(rows), now


def test_ema_uses_historical_warmup() -> None:
    df, now = make_fixture()
    session_date = now.date()
    out = add_indicators_1m(df, session_date, now)

    assert len(out) == 17
    assert out["opening_range_complete"].all()

    # The first current-session EMA must include the pre-session history.
    all_completed = df.copy()
    all_completed["close"] = pd.to_numeric(all_completed["close"])
    expected_ema20 = all_completed["close"].ewm(span=20, adjust=False).mean().iloc[30]
    assert abs(float(out.iloc[0]["ema20"]) - float(expected_ema20)) < 1e-9

    # It must NOT equal an EMA seeded from today's first candle.
    session_only = out["close"].ewm(span=20, adjust=False).mean().iloc[0]
    assert abs(float(out.iloc[0]["ema20"]) - float(session_only)) > 1e-6


def test_vwap_is_current_session_only() -> None:
    df, now = make_fixture()
    out = add_indicators_1m(df, now.date(), now)

    first = out.iloc[0]
    expected_first_vwap = (float(first.high) + float(first.low) + float(first.close)) / 3.0
    assert abs(float(first.vwap) - expected_first_vwap) < 1e-9


def test_opening_range_is_exactly_first_15_minutes() -> None:
    df, now = make_fixture()
    out = add_indicators_1m(df, now.date(), now)
    opening = out.iloc[:15]

    assert float(out.iloc[-1]["first15_high"]) == float(opening.high.max())
    assert float(out.iloc[-1]["first15_low"]) == float(opening.low.min())


def main() -> None:
    test_ema_uses_historical_warmup()
    test_vwap_is_current_session_only()
    test_opening_range_is_exactly_first_15_minutes()
    print("PSY29 1M INDICATOR CONTRACT: PASS")


if __name__ == "__main__":
    main()
