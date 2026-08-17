#!/usr/bin/env python3
"""Regression tests for the production 1-minute DHAN indicator contract."""
from __future__ import annotations
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
from psy29_live_dhan_acquisition import add_indicators_1m  # noqa: E402

def make_fixture() -> tuple[pd.DataFrame, datetime]:
    session = datetime(2026, 8, 17, 9, 15, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    rows = []
    for i in range(30):
        dt = session - timedelta(minutes=30 - i); price = 100.0 + i * 0.2
        rows.append({"timestamp": int(dt.timestamp()), "open": price, "high": price + 0.5, "low": price - 0.5, "close": price + 0.2, "volume": 1000 + i})
    for i in range(17):
        dt = session + timedelta(minutes=i); price = 110.0 + i * 0.1
        rows.append({"timestamp": int(dt.timestamp()), "open": price, "high": price + 0.4 + (0.1 if i == 4 else 0), "low": price - 0.4 - (0.1 if i == 7 else 0), "close": price + 0.1, "volume": 2000 + i * 10})
    return pd.DataFrame(rows), session + timedelta(minutes=17)

def test_ema_uses_historical_warmup() -> None:
    df, now = make_fixture(); out = add_indicators_1m(df, now.date(), now)
    assert len(out) == 17 and out["opening_range_complete"].all()
    expected_ema20 = df["close"].ewm(span=20, adjust=False).mean().iloc[30]
    assert abs(float(out.iloc[0]["ema20"]) - float(expected_ema20)) < 1e-9
    session_only = out["close"].ewm(span=20, adjust=False).mean().iloc[0]
    assert abs(float(out.iloc[0]["ema20"]) - float(session_only)) > 1e-6

def test_vwap_is_current_session_only() -> None:
    df, now = make_fixture(); out = add_indicators_1m(df, now.date(), now); first = out.iloc[0]
    expected = (float(first.high) + float(first.low) + float(first.close)) / 3.0
    assert abs(float(first.vwap) - expected) < 1e-9

def test_opening_range_is_exactly_first_15_minutes() -> None:
    df, now = make_fixture(); out = add_indicators_1m(df, now.date(), now); opening = out.iloc[:15]
    assert float(out.iloc[-1]["first15_high"]) == float(opening.high.max())
    assert float(out.iloc[-1]["first15_low"]) == float(opening.low.min())

def main() -> None:
    test_ema_uses_historical_warmup(); test_vwap_is_current_session_only(); test_opening_range_is_exactly_first_15_minutes()
    print("PSY29 1M INDICATOR CONTRACT: PASS")

if __name__ == "__main__": main()
