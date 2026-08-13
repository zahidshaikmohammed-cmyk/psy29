"""PSY29 Step 7 - Intraday Liquidity Gate.

Uses historical 1-minute OHLCV to measure executable-liquidity proxies.
This is a research gate, not a live bid/ask-depth measurement.
"""
from __future__ import annotations
import argparse, json
from pathlib import Path
import numpy as np
import pandas as pd

MIN_SESSION_COVERAGE = 0.90
MIN_ACTIVE_BAR_RATE = 0.90
MAX_ZERO_VOLUME_RATE = 0.05
MIN_AVG_DAILY_TRADED_VALUE_INR = 5e7
MIN_MEDIAN_1M_TRADED_VALUE_INR = 1e5
MIN_P10_1M_TRADED_VALUE_INR = 2e4


def load_sessions(path: Path) -> pd.DataFrame:
    df = pd.read_parquet(path)
    required = ["timestamp", "open", "high", "low", "close", "volume"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise RuntimeError("Missing columns: " + ",".join(missing))
    ts = df["timestamp"]
    if pd.api.types.is_numeric_dtype(ts):
        ts = pd.to_datetime(ts, unit="s", errors="coerce", utc=True)
    else:
        ts = pd.to_datetime(ts, errors="coerce", utc=True)
    df = df.copy()
    df["ts"] = ts.dt.tz_convert("Asia/Kolkata")
    df = df.dropna(subset=["ts"])
    t = df["ts"].dt.time
    df = df[(t >= pd.Timestamp("09:15:00").time()) & (t < pd.Timestamp("15:30:00").time())].copy()
    for c in ["open","high","low","close","volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["open","close","volume"])
    df = df[df["close"] > 0]
    df["date"] = df["ts"].dt.date
    df["bar_value"] = df["close"] * df["volume"]
    return df


def stock_metrics(path: Path) -> dict:
    df = load_sessions(path)
    if df.empty:
        raise RuntimeError("No valid intraday rows")
    daily = df.groupby("date").agg(
        traded_value=("bar_value", "sum"),
        bars=("close", "size"),
        active_bars=("volume", lambda s: int((s > 0).sum())),
    )
    daily["active_rate"] = daily["active_bars"] / daily["bars"]
    daily_value = daily["traded_value"]
    bar_value = df["bar_value"]
    expected_sessions = len(daily)
    full_session_rate = float((daily["bars"] >= 300).mean()) if expected_sessions else 0.0
    active_bar_rate = float((daily["active_rate"] >= MIN_ACTIVE_BAR_RATE).mean()) if expected_sessions else 0.0
    zero_volume_rate = float((df["volume"] <= 0).mean())
    return {
        "symbol": path.stem,
        "sessions": int(expected_sessions),
        "session_coverage_rate": full_session_rate,
        "active_session_rate": active_bar_rate,
        "zero_volume_bar_rate": zero_volume_rate,
        "avg_daily_traded_value_inr": float(daily_value.mean()),
        "median_daily_traded_value_inr": float(daily_value.median()),
        "p10_daily_traded_value_inr": float(daily_value.quantile(0.10)),
        "median_1m_traded_value_inr": float(bar_value.median()),
        "p10_1m_traded_value_inr": float(bar_value.quantile(0.10)),
        "median_1m_volume": float(df["volume"].median()),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="input/data/raw/intraday")
    ap.add_argument("--edge-ranking", required=True)
    ap.add_argument("--output", default="output/step7")
    args = ap.parse_args()
    root, out = Path(args.input), Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    ranking = pd.read_csv(args.edge_ranking)
    if "symbol" not in ranking.columns:
        raise RuntimeError("Step 6 ranking missing symbol column")
    rows, errors = [], []
    files = sorted(root.rglob("*.parquet"))
    for p in files:
        try:
            rows.append(stock_metrics(p))
        except Exception as e:
            errors.append({"symbol": p.stem, "error": str(e)})
    liq = pd.DataFrame(rows)
    if liq.empty:
        raise RuntimeError("No liquidity metrics generated")
    merged = ranking.merge(liq, on="symbol", how="left", validate="one_to_one")
    merged["liquidity_pass"] = (
        (merged["session_coverage_rate"] >= MIN_SESSION_COVERAGE) &
        (merged["active_session_rate"] >= MIN_ACTIVE_BAR_RATE) &
        (merged["zero_volume_bar_rate"] <= MAX_ZERO_VOLUME_RATE) &
        (merged["avg_daily_traded_value_inr"] >= MIN_AVG_DAILY_TRADED_VALUE_INR) &
        (merged["median_1m_traded_value_inr"] >= MIN_MEDIAN_1M_TRADED_VALUE_INR) &
        (merged["p10_1m_traded_value_inr"] >= MIN_P10_1M_TRADED_VALUE_INR)
    )
    merged["liquidity_score"] = (
        np.minimum(merged["avg_daily_traded_value_inr"] / MIN_AVG_DAILY_TRADED_VALUE_INR, 10) / 10 * 0.35 +
        np.minimum(merged["median_1m_traded_value_inr"] / MIN_MEDIAN_1M_TRADED_VALUE_INR, 10) / 10 * 0.25 +
        np.minimum(merged["p10_1m_traded_value_inr"] / MIN_P10_1M_TRADED_VALUE_INR, 10) / 10 * 0.20 +
        merged["active_session_rate"] * 0.20
    )
    merged["edge_liquidity_score"] = merged["oos_edge_score_v3"].fillna(0) * (0.5 + 0.5 * merged["liquidity_score"].fillna(0))
    merged = merged.sort_values(["liquidity_pass", "edge_liquidity_score"], ascending=[False, False]).reset_index(drop=True)
    merged.insert(0, "liquidity_research_rank", np.arange(1, len(merged)+1))
    merged.to_csv(out / "step7_liquidity_audit.csv", index=False)
    passed = merged[merged["liquidity_pass"]].copy()
    passed.to_csv(out / "step7_liquidity_passed.csv", index=False)
    summary = {
        "project":"PSY29","step":7,"version":"1.0",
        "input_stocks":int(len(merged)),
        "liquidity_pass_count":int(len(passed)),
        "liquidity_fail_count":int(len(merged)-len(passed)),
        "final_29_selection_performed":False,
        "gate_type":"historical intraday OHLCV liquidity proxy",
        "live_order_book_depth_measured":False,
        "thresholds":{
            "min_session_coverage":MIN_SESSION_COVERAGE,
            "min_active_bar_rate":MIN_ACTIVE_BAR_RATE,
            "max_zero_volume_rate":MAX_ZERO_VOLUME_RATE,
            "min_avg_daily_traded_value_inr":MIN_AVG_DAILY_TRADED_VALUE_INR,
            "min_median_1m_traded_value_inr":MIN_MEDIAN_1M_TRADED_VALUE_INR,
            "min_p10_1m_traded_value_inr":MIN_P10_1M_TRADED_VALUE_INR,
        },
        "errors":errors,
        "status":"PASS" if not errors else "PASS_WITH_ERRORS"
    }
    (out/"step7_summary.json").write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary,indent=2))

if __name__ == "__main__": main()
