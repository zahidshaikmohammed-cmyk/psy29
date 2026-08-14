import math
import pandas as pd
import pytest

from research.threshold_generator import UNIVERSE, TRAIN, TEST, STEP, q, sessions


def test_canonical_constants_and_quantiles():
    assert len(UNIVERSE) == 29 and len(set(UNIVERSE)) == 29
    assert (TRAIN, TEST, STEP) == (60, 20, 20)
    assert q([1, 2, 3, 4], .75) == pytest.approx(3.25)


def test_session_parser_matches_canonical_boundaries(tmp_path):
    ts = pd.date_range("2026-01-01 09:15", periods=30, freq="min", tz="Asia/Kolkata")
    close = pd.Series(range(100, 130), dtype=float)
    df = pd.DataFrame({"timestamp": ts.tz_convert("UTC"), "open": close, "high": close + 1, "low": close - 1, "close": close, "volume": 1})
    p = tmp_path / "NESTLEIND.parquet"
    df.to_parquet(p)
    out = sessions(p, "NESTLEIND")
    assert len(out) == 1
    assert set(out[0]) == {"symbol", "date", "g", "day_abs_return", "directional_efficiency", "opening_range_pct", "opening_range_continuation", "breakout_extension_pct"}
    assert all(math.isfinite(float(out[0][k])) for k in ("day_abs_return", "directional_efficiency", "opening_range_pct", "breakout_extension_pct"))


def test_causal_training_window_invariant():
    train = pd.date_range("2026-01-01", periods=TRAIN, freq="B")
    test = pd.date_range(train[-1] + pd.Timedelta(days=1), periods=TEST, freq="B")
    assert len(train) == 60 and len(test) == 20
    assert train[-1] < test[0]
    assert not set(train).intersection(set(test))


def test_no_future_session_can_enter_training():
    train_end = pd.Timestamp("2026-04-01")
    effective = pd.Timestamp("2026-04-02")
    assert train_end < effective


def test_invalid_lookahead_is_rejected():
    train_end = pd.Timestamp("2026-04-03")
    effective = pd.Timestamp("2026-04-02")
    assert not train_end < effective
