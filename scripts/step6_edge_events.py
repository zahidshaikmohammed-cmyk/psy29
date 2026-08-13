"""PSY29 Step 6 V2: adaptive intraday edge-event discovery.

Uses stock-specific empirical baselines instead of fixed universal thresholds.
This stage is descriptive/research-only and never selects the final 29.
"""
from __future__ import annotations
import argparse, json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd

START = pd.Timestamp("09:15:00").time()
END = pd.Timestamp("15:30:00").time()


def q(s: pd.Series, p: float, fallback: float) -> float:
    s = pd.to_numeric(s, errors="coerce").dropna()
    return float(s.quantile(p)) if len(s) else float(fallback)


def session_events(file_path: Path) -> list[dict]:
    df = pd.read_parquet(file_path)
    if "timestamp" not in df.columns:
        raise RuntimeError("missing timestamp")
    ts = (pd.to_datetime(df["timestamp"], unit="s", errors="coerce", utc=True)
          if pd.api.types.is_numeric_dtype(df["timestamp"])
          else pd.to_datetime(df["timestamp"], errors="coerce", utc=True))
    df = df.assign(ts=ts.dt.tz_convert("Asia/Kolkata")).dropna(subset=["ts"]).sort_values("ts")
    t = df.ts.dt.time
    df = df[(t >= START) & (t < END)].copy()
    if df.empty:
        return []
    for c in ["open", "high", "low", "close", "volume"]:
        if c not in df.columns:
            raise RuntimeError(f"missing {c}")
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["open", "high", "low", "close"])
    df["date"] = df.ts.dt.date
    out = []
    for d, g in df.groupby("date", sort=True):
        g = g.sort_values("ts").copy()
        if len(g) < 30:
            continue
        o = float(g.open.iloc[0]); c = float(g.close.iloc[-1])
        h = float(g.high.max()); l = float(g.low.min())
        returns = g.close.pct_change().dropna()
        path_length = float(returns.abs().sum())
        net = (c - o) / o if o else np.nan
        efficiency = abs(net) / (path_length + 1e-12)
        direction = np.sign(g.close.diff()).replace(0, np.nan).ffill().dropna()
        switch_rate = float(direction.diff().ne(0).mean()) if len(direction) > 1 else np.nan

        op = g.iloc[:15]
        orh = float(op.high.max()); orl = float(op.low.min())
        after = g.iloc[15:]
        up_break = bool((after.high > orh).any()) if len(after) else False
        down_break = bool((after.low < orl).any()) if len(after) else False
        close_beyond_up = bool(c > orh) if len(after) else False
        close_beyond_down = bool(c < orl) if len(after) else False
        or_width = (orh - orl) / o if o else np.nan
        breakout_extension = max(
            (c - orh) / o if o else 0.0,
            (orl - c) / o if o else 0.0,
            0.0,
        )
        or_cont = bool((up_break and close_beyond_up) or (down_break and close_beyond_down))

        bar_range = (g.high - g.low) / g.open.replace(0, np.nan)
        base = float(bar_range.iloc[:15].median())
        later = float(bar_range.iloc[15:].median()) if len(after) else np.nan
        expansion_ratio = later / base if np.isfinite(base) and base > 0 and np.isfinite(later) else np.nan

        out.append({
            "symbol": file_path.stem,
            "date": str(d),
            "day_return": net,
            "day_abs_return": abs(net),
            "day_range_pct": (h - l) / o if o else np.nan,
            "directional_efficiency": efficiency,
            "direction_switch_rate": switch_rate,
            "opening_range_pct": or_width,
            "or_up_break": up_break,
            "or_down_break": down_break,
            "or_continuation": or_cont,
            "breakout_extension_pct": breakout_extension,
            "range_expansion_ratio": expansion_ratio,
            "volume": float(g.volume.fillna(0).sum()),
        })
    return out


def summarize(events: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for sym, g in events.groupby("symbol", sort=True):
        # Empirical, stock-specific baselines. Fixed thresholds are deliberately avoided.
        r60, r75, r85 = (q(g.day_abs_return, p, 0.0) for p in (0.60, 0.75, 0.85))
        e60, e75 = (q(g.directional_efficiency, p, 0.0) for p in (0.60, 0.75))
        sw25 = q(g.direction_switch_rate, 0.25, 1.0)
        ex75 = q(g.range_expansion_ratio.replace([np.inf, -np.inf], np.nan), 0.75, 1.0)
        or75 = q(g.opening_range_pct, 0.75, 0.0)
        bx60 = q(g.breakout_extension_pct, 0.60, 0.0)

        trend = (g.day_abs_return >= r75) & (g.directional_efficiency >= e60)
        strong = (g.day_abs_return >= r85) & (g.directional_efficiency >= e75)
        low_chop = g.direction_switch_rate <= sw25
        range_expansion = g.range_expansion_ratio >= ex75
        adaptive_or = g.or_continuation & (g.opening_range_pct <= or75) & (g.breakout_extension_pct >= bx60)

        # Stability: split chronologically into first/second half and compare event rates.
        mid = len(g) // 2
        g1, g2 = g.iloc[:mid], g.iloc[mid:]
        def split_rate(mask1, mask2):
            a = float(mask1.mean()) if len(mask1) else 0.0
            b = float(mask2.mean()) if len(mask2) else 0.0
            return a, b, 1.0 - abs(a - b)
        t1 = (g1.day_abs_return >= r75) & (g1.directional_efficiency >= e60)
        t2 = (g2.day_abs_return >= r75) & (g2.directional_efficiency >= e60)
        s1 = (g1.day_abs_return >= r85) & (g1.directional_efficiency >= e75)
        s2 = (g2.day_abs_return >= r85) & (g2.directional_efficiency >= e75)
        tr_a, tr_b, tr_stab = split_rate(t1, t2)
        st_a, st_b, st_stab = split_rate(s1, s2)

        # Composite research score only; it is NOT the final stock selector.
        components = {
            "trend_rate": float(trend.mean()),
            "strong_rate": float(strong.mean()),
            "adaptive_or_rate": float(adaptive_or.mean()),
            "range_expansion_rate": float(range_expansion.mean()),
            "low_chop_rate": float(low_chop.mean()),
            "trend_stability": tr_stab,
            "strong_stability": st_stab,
        }
        edge_score = float(
            0.22 * components["trend_rate"]
            + 0.18 * components["strong_rate"]
            + 0.16 * components["adaptive_or_rate"]
            + 0.12 * components["range_expansion_rate"]
            + 0.10 * components["low_chop_rate"]
            + 0.12 * components["trend_stability"]
            + 0.10 * components["strong_stability"]
        )
        rows.append({
            "symbol": sym,
            "sessions": len(g),
            "adaptive_trend_event_rate": components["trend_rate"],
            "adaptive_strong_trend_rate": components["strong_rate"],
            "adaptive_or_continuation_rate": components["adaptive_or_rate"],
            "adaptive_range_expansion_rate": components["range_expansion_rate"],
            "adaptive_low_chop_rate": components["low_chop_rate"],
            "trend_stability": tr_stab,
            "strong_trend_stability": st_stab,
            "trend_rate_first_half": tr_a,
            "trend_rate_second_half": tr_b,
            "strong_rate_first_half": st_a,
            "strong_rate_second_half": st_b,
            "median_event_return": float(g.day_abs_return.median()),
            "median_efficiency": float(g.directional_efficiency.median()),
            "median_range_pct": float(g.day_range_pct.median()),
            "median_switch_rate": float(g.direction_switch_rate.median()),
            "median_opening_range_pct": float(g.opening_range_pct.median()),
            "trend_return_q75": r75,
            "trend_return_q85": r85,
            "efficiency_q60": e60,
            "efficiency_q75": e75,
            "switch_rate_q25": sw25,
            "range_expansion_q75": ex75,
            "edge_score_v2": edge_score,
        })
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="input/data/raw/intraday")
    ap.add_argument("--output", default="output/step6")
    a = ap.parse_args()
    root, out = Path(a.input), Path(a.output)
    out.mkdir(parents=True, exist_ok=True)
    files = sorted(root.rglob("*.parquet"))
    if not files:
        raise RuntimeError("No parquet files found")

    all_events = []
    errors = []
    for i, p in enumerate(files, 1):
        try:
            ev = session_events(p)
            all_events.extend(ev)
            print(f"[{i}/{len(files)}] {p.stem} sessions={len(ev)}")
        except Exception as e:
            errors.append({"symbol": p.stem, "error": str(e)})
            print(f"FAILED {p.stem}: {e}")

    if not all_events:
        raise RuntimeError("No intraday events generated")
    edf = pd.DataFrame(all_events)
    summary_df = summarize(edf).sort_values(
        ["edge_score_v2", "adaptive_strong_trend_rate", "adaptive_trend_event_rate"],
        ascending=False,
    ).reset_index(drop=True)
    summary_df.insert(0, "research_rank_v2", np.arange(1, len(summary_df) + 1))

    edf.to_csv(out / "edge_events_by_session.csv", index=False)
    summary_df.to_csv(out / "stock_edge_event_summary.csv", index=False)
    summary_df.to_csv(out / "edge_event_research_ranking.csv", index=False)

    summary = {
        "project": "PSY29",
        "step": 6,
        "version": "2.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "stocks_input": len(files),
        "stocks_with_events": int(summary_df.symbol.nunique()),
        "sessions_analyzed": int(len(edf)),
        "errors": len(errors),
        "errors_detail": errors,
        "threshold_method": "stock-specific empirical quantiles",
        "quantiles": {
            "trend_return": 0.75,
            "strong_return": 0.85,
            "trend_efficiency": 0.60,
            "strong_efficiency": 0.75,
            "low_chop_switch_rate": 0.25,
            "range_expansion": 0.75,
            "opening_range": 0.75,
            "breakout_extension": 0.60,
        },
        "stability_method": "chronological first-half vs second-half event-rate agreement",
        "final_selection_performed": False,
        "status": "PASS" if not errors else "PASS_WITH_ERRORS",
    }
    (out / "step6_summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
