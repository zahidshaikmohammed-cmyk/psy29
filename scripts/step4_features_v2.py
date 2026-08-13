"""PSY29 Step 4 V2: intraday-only behavioural feature extraction.

All return/path calculations are reset at each NSE session. Overnight gaps and
jumps across missing minute bars are excluded from intraday path metrics.
"""
from __future__ import annotations
import argparse, json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd

SESSION_START = pd.Timestamp("09:15:00").time()
SESSION_END = pd.Timestamp("15:30:00").time()


def _num(s):
    return pd.to_numeric(s, errors="coerce")


def _session_features(g: pd.DataFrame) -> dict:
    g = g.sort_values("ts").copy()
    close = _num(g["close"]); op = _num(g["open"]); high = _num(g["high"]); low = _num(g["low"])
    vol = _num(g["volume"]).fillna(0)
    o = float(op.iloc[0]); c = float(close.iloc[-1]); h = float(high.max()); l = float(low.min())
    if not np.isfinite(o) or o == 0 or not np.isfinite(c):
        raise ValueError("invalid session open/close")

    dt = g["ts"].diff().dt.total_seconds()
    # Only adjacent minute observations are part of the intraday path.
    valid = dt.between(0, 90, inclusive="both")
    ret = close.pct_change().where(valid)
    ret = ret.replace([np.inf, -np.inf], np.nan).dropna()
    net = (c - o) / o
    path = float(ret.abs().sum())
    efficiency = abs(net) / path if path > 0 else np.nan
    signs = np.sign(ret.to_numpy())
    nonzero = signs[signs != 0]
    if len(nonzero) > 1:
        switches = int(np.sum(nonzero[1:] != nonzero[:-1]))
        switch_rate = switches / (len(nonzero) - 1)
        same_direction_rate = 1.0 - switch_rate
        runs = np.split(nonzero, np.where(nonzero[1:] != nonzero[:-1])[0] + 1)
        max_run = int(max(len(r) for r in runs))
    else:
        switches = 0; switch_rate = np.nan; same_direction_rate = np.nan; max_run = len(nonzero)

    cum = ret.fillna(0).cumsum()
    dd = cum - cum.cummax()
    max_drawdown = float(dd.min()) if len(dd) else np.nan
    rv = float(ret.std()) if len(ret) > 1 else np.nan

    # Opening-range follow-through: first 15 minutes, then the remainder.
    mins = ((g["ts"].dt.hour * 60 + g["ts"].dt.minute) - (9 * 60 + 15)).astype(int)
    opening = g[mins < 15]
    later = g[mins >= 15]
    if len(opening) and len(later):
        or_high = float(_num(opening.high).max()); or_low = float(_num(opening.low).min())
        later_close = float(_num(later.close).iloc[-1])
        or_up_break = bool(_num(later.high).max() > or_high)
        or_down_break = bool(_num(later.low).min() < or_low)
        or_width = (or_high - or_low) / o if o else np.nan
        or_follow = (later_close - float(_num(opening.open).iloc[0])) / o if o else np.nan
    else:
        or_width = np.nan; or_up_break = False; or_down_break = False; or_follow = np.nan

    up = int((ret > 0).sum()); down = int((ret < 0).sum())
    return {
        "day_return": float(net),
        "abs_day_return": float(abs(net)),
        "intraday_range_pct": float((h - l) / o),
        "path_length_pct": path,
        "directional_efficiency": float(efficiency) if np.isfinite(efficiency) else np.nan,
        "same_direction_rate": float(same_direction_rate) if np.isfinite(same_direction_rate) else np.nan,
        "direction_switch_rate": float(switch_rate) if np.isfinite(switch_rate) else np.nan,
        "max_same_direction_run": max_run,
        "max_path_drawdown_pct": abs(max_drawdown) if np.isfinite(max_drawdown) else np.nan,
        "up_minutes": up,
        "down_minutes": down,
        "trend_imbalance": float(abs(up - down) / (up + down)) if (up + down) else np.nan,
        "return_volatility_1m": rv,
        "opening_range_15m_pct": float(or_width) if np.isfinite(or_width) else np.nan,
        "opening_range_followthrough": float(or_follow) if np.isfinite(or_follow) else np.nan,
        "opening_range_up_break": int(or_up_break),
        "opening_range_down_break": int(or_down_break),
        "session_volume": float(vol.sum()),
        "median_bar_volume": float(vol.median()),
        "bars": int(len(g)),
        "valid_intraday_returns": int(len(ret)),
    }


def build(path: Path) -> dict:
    df = pd.read_parquet(path)
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"missing columns: {sorted(missing)}")
    raw = df["timestamp"]
    if pd.api.types.is_numeric_dtype(raw):
        ts = pd.to_datetime(raw, unit="s", errors="coerce", utc=True)
    else:
        ts = pd.to_datetime(raw, errors="coerce", utc=True)
    df = df.assign(ts=ts.dt.tz_convert("Asia/Kolkata")).dropna(subset=["ts"]).sort_values("ts")
    t = df["ts"].dt.time
    df = df[(t >= SESSION_START) & (t < SESSION_END)].copy()
    if df.empty:
        return {"symbol": path.stem, "sessions": 0, "rows": 0}
    df["date"] = df["ts"].dt.date
    days = []
    for d, g in df.groupby("date", sort=True):
        f = _session_features(g)
        f["date"] = str(d)
        days.append(f)
    x = pd.DataFrame(days)
    def med(col): return float(x[col].median()) if len(x) else np.nan
    def mean(col): return float(x[col].mean()) if len(x) else np.nan
    return {
        "symbol": path.stem,
        "sessions": int(len(x)),
        "rows": int(len(df)),
        "mean_abs_return": mean("abs_day_return"),
        "median_abs_return": med("abs_day_return"),
        "mean_range_pct": mean("intraday_range_pct"),
        "median_range_pct": med("intraday_range_pct"),
        "mean_path_length_pct": mean("path_length_pct"),
        "median_path_length_pct": med("path_length_pct"),
        "mean_directional_efficiency": mean("directional_efficiency"),
        "median_directional_efficiency": med("directional_efficiency"),
        "trend_day_rate_20pct": float((x.directional_efficiency >= 0.20).mean()),
        "trend_day_rate_30pct": float((x.directional_efficiency >= 0.30).mean()),
        "trend_day_rate_40pct": float((x.directional_efficiency >= 0.40).mean()),
        "median_same_direction_rate": med("same_direction_rate"),
        "median_direction_switch_rate": med("direction_switch_rate"),
        "median_max_same_direction_run": med("max_same_direction_run"),
        "median_trend_imbalance": med("trend_imbalance"),
        "median_max_path_drawdown_pct": med("max_path_drawdown_pct"),
        "median_1m_volatility": med("return_volatility_1m"),
        "median_opening_range_15m_pct": med("opening_range_15m_pct"),
        "opening_range_up_break_rate": float(x.opening_range_up_break.mean()),
        "opening_range_down_break_rate": float(x.opening_range_down_break.mean()),
        "median_opening_range_followthrough": med("opening_range_followthrough"),
        "positive_day_rate": float((x.day_return > 0).mean()),
        "negative_day_rate": float((x.day_return < 0).mean()),
        "median_session_volume": med("session_volume"),
        "median_bar_volume": med("median_bar_volume"),
        "median_bars": med("bars"),
        "median_valid_intraday_returns": med("valid_intraday_returns"),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="input/data/raw/intraday")
    ap.add_argument("--output", default="output/step4")
    a = ap.parse_args()
    root, out = Path(a.input), Path(a.output)
    out.mkdir(parents=True, exist_ok=True)
    files = sorted(root.glob("*.parquet"))
    if not files:
        raise RuntimeError("No parquet files found")
    rows, errors = [], []
    for i, f in enumerate(files, 1):
        try:
            r = build(f); rows.append(r)
            print(f"[{i}/{len(files)}] {f.stem} sessions={r.get('sessions', 0)}")
        except Exception as e:
            errors.append({"symbol": f.stem, "error": str(e)})
            print(f"FAILED {f.stem}: {e}")
    pd.DataFrame(rows).to_csv(out / "stock_behaviour_features_v2.csv", index=False)
    summary = {
        "project": "PSY29", "step": 4, "version": "2.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "files_found": len(files), "features_generated": len(rows), "errors": len(errors),
        "errors_detail": errors, "raw_data_modified": False,
        "intraday_only": True,
        "overnight_gaps_in_path": False,
        "missing_bar_jumps_in_path": False,
        "status": "PASS" if not errors else "PASS_WITH_ERRORS",
    }
    (out / "step4_v2_summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    if not rows:
        raise SystemExit(1)

if __name__ == "__main__":
    main()
