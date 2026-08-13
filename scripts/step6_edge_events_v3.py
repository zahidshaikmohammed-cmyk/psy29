"""
PSY29 STEP 6 V3
WALK-FORWARD OUT-OF-SAMPLE INTRADAY EDGE ENGINE
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd


START_TIME = pd.Timestamp("09:15:00").time()
END_TIME = pd.Timestamp("15:30:00").time()

TRAIN_SESSIONS = 60
TEST_SESSIONS = 20
STEP_SESSIONS = 20


def quantile(series: pd.Series, percentile: float, fallback=np.nan) -> float:
    values = pd.to_numeric(series, errors="coerce").dropna()
    if values.empty:
        return float(fallback)
    return float(values.quantile(percentile))


def build_session_features(file_path: Path) -> list[dict]:
    df = pd.read_parquet(file_path)

    required = ["timestamp", "open", "high", "low", "close", "volume"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise RuntimeError("Missing required columns: " + ", ".join(missing))

    timestamp = df["timestamp"]
    if pd.api.types.is_numeric_dtype(timestamp):
        ts = pd.to_datetime(timestamp, unit="s", errors="coerce", utc=True)
    else:
        ts = pd.to_datetime(timestamp, errors="coerce", utc=True)

    df = df.copy()
    df["ts"] = ts.dt.tz_convert("Asia/Kolkata")
    df = df.dropna(subset=["ts"]).sort_values("ts")

    intraday_time = df["ts"].dt.time
    df = df[(intraday_time >= START_TIME) & (intraday_time < END_TIME)].copy()

    for column in ["open", "high", "low", "close", "volume"]:
        df[column] = pd.to_numeric(df[column], errors="coerce")

    df = df.dropna(subset=["open", "high", "low", "close"])
    if df.empty:
        return []

    df["date"] = df["ts"].dt.date
    sessions = []

    for session_date, group in df.groupby("date", sort=True):
        group = group.sort_values("ts").copy()
        if len(group) < 30:
            continue

        opening_price = float(group["open"].iloc[0])
        closing_price = float(group["close"].iloc[-1])
        high_price = float(group["high"].max())
        low_price = float(group["low"].min())

        if opening_price == 0:
            continue

        day_return = (closing_price - opening_price) / opening_price
        day_abs_return = abs(day_return)
        day_range_pct = (high_price - low_price) / opening_price

        minute_returns = group["close"].pct_change().dropna()
        path_length = float(minute_returns.abs().sum())
        directional_efficiency = day_abs_return / (path_length + 1e-12)

        direction = np.sign(group["close"].diff()).replace(0, np.nan).ffill().dropna()
        direction_switch_rate = (
            float(direction.diff().ne(0).mean())
            if len(direction) > 1
            else np.nan
        )

        opening_range = group.iloc[:15]
        remainder = group.iloc[15:]
        if len(opening_range) == 0:
            continue

        opening_range_high = float(opening_range["high"].max())
        opening_range_low = float(opening_range["low"].min())
        opening_range_pct = (opening_range_high - opening_range_low) / opening_price

        broke_up = bool((remainder["high"] > opening_range_high).any()) if len(remainder) else False
        broke_down = bool((remainder["low"] < opening_range_low).any()) if len(remainder) else False

        opening_range_continuation = bool(
            (broke_up and closing_price > opening_range_high)
            or (broke_down and closing_price < opening_range_low)
        )

        upward_extension = (closing_price - opening_range_high) / opening_price
        downward_extension = (opening_range_low - closing_price) / opening_price
        breakout_extension_pct = max(upward_extension, downward_extension, 0.0)

        bar_range_pct = (group["high"] - group["low"]) / group["open"].replace(0, np.nan)
        first_range = float(bar_range_pct.iloc[:15].median())
        later_range = float(bar_range_pct.iloc[15:].median()) if len(remainder) else np.nan

        if np.isfinite(first_range) and first_range > 0 and np.isfinite(later_range):
            range_expansion_ratio = later_range / first_range
        else:
            range_expansion_ratio = np.nan

        sessions.append({
            "symbol": file_path.stem,
            "date": str(session_date),
            "day_return": day_return,
            "day_abs_return": day_abs_return,
            "day_range_pct": day_range_pct,
            "directional_efficiency": directional_efficiency,
            "direction_switch_rate": direction_switch_rate,
            "opening_range_pct": opening_range_pct,
            "opening_range_continuation": opening_range_continuation,
            "breakout_extension_pct": breakout_extension_pct,
            "range_expansion_ratio": range_expansion_ratio,
            "volume": float(group["volume"].fillna(0).sum()),
        })

    return sessions


def evaluate_test_window(train: pd.DataFrame, test: pd.DataFrame) -> list[dict]:
    thresholds = {
        "return_q75": quantile(train["day_abs_return"], 0.75),
        "return_q85": quantile(train["day_abs_return"], 0.85),
        "efficiency_q60": quantile(train["directional_efficiency"], 0.60),
        "efficiency_q75": quantile(train["directional_efficiency"], 0.75),
        "switch_q25": quantile(train["direction_switch_rate"], 0.25, 1.0),
        "expansion_q75": quantile(
            train["range_expansion_ratio"].replace([np.inf, -np.inf], np.nan),
            0.75,
            1.0,
        ),
        "or_q75": quantile(train["opening_range_pct"], 0.75),
        "extension_q60": quantile(train["breakout_extension_pct"], 0.60, 0.0),
    }

    output = []
    for _, row in test.iterrows():
        trend_event = bool(
            row["day_abs_return"] >= thresholds["return_q75"]
            and row["directional_efficiency"] >= thresholds["efficiency_q60"]
        )
        strong_trend_event = bool(
            row["day_abs_return"] >= thresholds["return_q85"]
            and row["directional_efficiency"] >= thresholds["efficiency_q75"]
        )
        low_chop_event = bool(row["direction_switch_rate"] <= thresholds["switch_q25"])
        range_expansion_event = bool(
            np.isfinite(row["range_expansion_ratio"])
            and row["range_expansion_ratio"] >= thresholds["expansion_q75"]
        )
        adaptive_or_event = bool(
            row["opening_range_continuation"]
            and row["opening_range_pct"] <= thresholds["or_q75"]
            and row["breakout_extension_pct"] >= thresholds["extension_q60"]
        )

        output.append({
            **row.to_dict(),
            "trend_event": trend_event,
            "strong_trend_event": strong_trend_event,
            "low_chop_event": low_chop_event,
            "range_expansion_event": range_expansion_event,
            "adaptive_or_event": adaptive_or_event,
        })

    return output


def walk_forward(sessions: pd.DataFrame) -> list[dict]:
    sessions = sessions.sort_values("date").reset_index(drop=True)

    if len(sessions) < TRAIN_SESSIONS + TEST_SESSIONS:
        return []

    results = []
    start = 0

    while start + TRAIN_SESSIONS + TEST_SESSIONS <= len(sessions):
        train = sessions.iloc[start:start + TRAIN_SESSIONS]
        test = sessions.iloc[
            start + TRAIN_SESSIONS:
            start + TRAIN_SESSIONS + TEST_SESSIONS
        ]

        results.extend(evaluate_test_window(train, test))
        start += STEP_SESSIONS

    return results


def build_stock_summary(oos: pd.DataFrame) -> pd.DataFrame:
    rows = []

    for symbol, group in oos.groupby("symbol", sort=True):
        n = len(group)
        trend_rate = float(group["trend_event"].mean())
        strong_rate = float(group["strong_trend_event"].mean())
        or_rate = float(group["adaptive_or_event"].mean())
        low_chop_rate = float(group["low_chop_event"].mean())
        expansion_rate = float(group["range_expansion_event"].mean())

        trend_events = group[group["trend_event"]]
        if len(trend_events):
            median_event_return = float(trend_events["day_abs_return"].median())
            median_event_efficiency = float(trend_events["directional_efficiency"].median())
        else:
            median_event_return = 0.0
            median_event_efficiency = 0.0

        event_count = int(group["trend_event"].sum())
        event_coverage = min(event_count / 10.0, 1.0)

        edge_score = (
            0.28 * trend_rate
            + 0.22 * strong_rate
            + 0.18 * or_rate
            + 0.10 * low_chop_rate
            + 0.10 * expansion_rate
            + 0.07 * median_event_return
            + 0.05 * event_coverage
        )

        rows.append({
            "symbol": symbol,
            "oos_sessions": n,
            "oos_trend_event_count": event_count,
            "oos_trend_event_rate": trend_rate,
            "oos_strong_trend_event_rate": strong_rate,
            "oos_or_continuation_rate": or_rate,
            "oos_low_chop_rate": low_chop_rate,
            "oos_range_expansion_rate": expansion_rate,
            "median_oos_event_return": median_event_return,
            "median_oos_event_efficiency": median_event_efficiency,
            "event_coverage_score": event_coverage,
            "oos_edge_score_v3": float(edge_score),
        })

    summary = pd.DataFrame(rows)
    if summary.empty:
        return summary

    summary = summary.sort_values(
        ["oos_edge_score_v3", "oos_trend_event_rate", "oos_strong_trend_event_rate"],
        ascending=False,
    ).reset_index(drop=True)

    summary.insert(0, "research_rank_v3", np.arange(1, len(summary) + 1))
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="input/data/raw/intraday")
    parser.add_argument("--output", default="output/step6_v3")
    args = parser.parse_args()

    input_root = Path(args.input)
    output_root = Path(args.output)
    output_root.mkdir(parents=True, exist_ok=True)

    files = sorted(input_root.rglob("*.parquet"))
    if not files:
        raise RuntimeError("No parquet files found.")

    all_oos = []
    errors = []

    for index, file_path in enumerate(files, start=1):
        try:
            sessions = build_session_features(file_path)
            if not sessions:
                print(f"[{index}/{len(files)}] {file_path.stem}: no valid sessions")
                continue

            session_df = pd.DataFrame(sessions)
            oos = walk_forward(session_df)
            all_oos.extend(oos)

            print(
                f"[{index}/{len(files)}] "
                f"{file_path.stem} "
                f"sessions={len(sessions)} "
                f"oos={len(oos)}"
            )

        except Exception as exc:
            errors.append({"symbol": file_path.stem, "error": str(exc)})
            print(f"FAILED {file_path.stem}: {exc}")

    if not all_oos:
        raise RuntimeError("No walk-forward OOS events generated.")

    oos_df = pd.DataFrame(all_oos)
    summary_df = build_stock_summary(oos_df)

    oos_df.to_csv(
        output_root / "edge_events_oos_by_session.csv",
        index=False,
    )

    summary_df.to_csv(
        output_root / "edge_event_oos_research_ranking.csv",
        index=False,
    )

    summary = {
        "project": "PSY29",
        "step": 6,
        "version": "3.0",
        "method": "walk-forward out-of-sample validation",
        "training_sessions": TRAIN_SESSIONS,
        "test_sessions": TEST_SESSIONS,
        "step_sessions": STEP_SESSIONS,
        "stocks_input": len(files),
        "stocks_with_oos_events": int(summary_df["symbol"].nunique()),
        "oos_sessions_analyzed": int(len(oos_df)),
        "errors": len(errors),
        "errors_detail": errors,
        "thresholds_learned_only_from_past": True,
        "same_sample_threshold_leakage": False,
        "final_selection_performed": False,
        "status": "PASS" if not errors else "PASS_WITH_ERRORS",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }

    (output_root / "step6_v3_summary.json").write_text(
        json.dumps(summary, indent=2)
    )

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
