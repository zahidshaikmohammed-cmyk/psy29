#!/usr/bin/env python3
"""Research-only PSY29 threshold generator.

The session construction and six threshold calculations intentionally mirror
research/event_time_discovery.py at CANONICAL_COMMIT. This file does not
calculate event labels and never consumes OOS bars when learning thresholds.
"""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
import numpy as np
import pandas as pd

CANONICAL_COMMIT = "988472889edfd51046731d72f68f2e96e095a2f1"
DATASET_RUN_ID = "31702235542"
TRAIN, TEST, STEP = 60, 20, 20
UNIVERSE = ["NESTLEIND","VEDL","ICICIPRULI","KALYANKJIL","KOTAKBANK","BANDHANBNK","BANKBARODA","TITAN","INFY","DLF","TCS","MAXHEALTH","KFINTECH","PRESTIGE","BHEL","RBLBANK","HCLTECH","ICICIGI","HDFCLIFE","MARICO","LUPIN","COFORGE","TECHM","SWIGGY","PERSISTENT","OBEROIRLTY","SUPREMEIND","LAURUSLABS","AMBUJACEM"]


def q(v, p, fallback=np.nan):
    s = pd.to_numeric(pd.Series(v), errors="coerce").dropna()
    return float(s.quantile(p)) if len(s) else float(fallback)


def sessions(path: Path, sym: str):
    df = pd.read_parquet(path)
    ts = df.timestamp
    ts = (pd.to_datetime(ts, unit="s", errors="coerce", utc=True)
          if pd.api.types.is_numeric_dtype(ts)
          else pd.to_datetime(ts, errors="coerce", utc=True))
    df = df.copy(); df["ts"] = ts.dt.tz_convert("Asia/Kolkata")
    df = df.dropna(subset=["ts"]).sort_values("ts")
    t = df.ts.dt.time
    df = df[(t >= pd.Timestamp("09:15").time()) & (t < pd.Timestamp("15:30").time())].copy()
    for c in ["open", "high", "low", "close", "volume"]:
        if c in df.columns: df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["open", "high", "low", "close"])
    df["date"] = df.ts.dt.date
    out = []
    for d, g in df.groupby("date", sort=True):
        g = g.sort_values("ts").copy()
        if len(g) < 30: continue
        op = float(g.open.iloc[0]); cl = float(g.close.iloc[-1]); hi = float(g.high.max()); lo = float(g.low.min())
        if op == 0: continue
        dar = abs((cl - op) / op)
        r = g.close.pct_change().dropna()
        eff = dar / (float(r.abs().sum()) + 1e-12)
        o = g.iloc[:15]; rem = g.iloc[15:]
        orh = float(o.high.max()); orl = float(o.low.min()); orpct = (orh - orl) / op
        bu = bool((rem.high > orh).any()); bd = bool((rem.low < orl).any())
        orc = bool((bu and cl > orh) or (bd and cl < orl))
        ext = max((cl - orh) / op, (orl - cl) / op, 0.0)
        out.append(dict(symbol=sym, date=str(d), g=g, day_abs_return=dar,
                        directional_efficiency=eff, opening_range_pct=orpct,
                        opening_range_continuation=orc,
                        breakout_extension_pct=ext))
    return out


def thresholds(train):
    return dict(
        r75=q([x["day_abs_return"] for x in train], .75),
        r85=q([x["day_abs_return"] for x in train], .85),
        e60=q([x["directional_efficiency"] for x in train], .60),
        e75=q([x["directional_efficiency"] for x in train], .75),
        or75=q([x["opening_range_pct"] for x in train], .75),
        ext60=q([x["breakout_extension_pct"] for x in train], .60, 0.0),
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--validation", required=True)
    ap.add_argument("--dataset-sha256", required=True)
    ap.add_argument("--generator-commit", required=True)
    a = ap.parse_args()
    root = Path(a.data_dir)
    all_sessions = {}
    errors = []
    for sym in UNIVERSE:
        p = root / f"{sym}.parquet"
        if not p.exists(): errors.append(f"missing canonical file: {p}"); continue
        ss = sessions(p, sym)
        if len(ss) < TRAIN + TEST: errors.append(f"{sym}: {len(ss)} sessions < 80")
        all_sessions[sym] = sorted(ss, key=lambda x: x["date"])
    if errors: raise RuntimeError("VALIDATION FAILED: " + "; ".join(errors))

    universe_hash = hashlib.sha256("\n".join(UNIVERSE).encode()).hexdigest()
    threshold_sets = []
    window_count = None
    for sym in UNIVERSE:
        ss = all_sessions[sym]
        starts = list(range(0, len(ss) - TRAIN - TEST + 1, STEP))
        if window_count is None: window_count = len(starts)
        if len(starts) != window_count: errors.append(f"{sym}: inconsistent window count")
        for start in starts:
            train = ss[start:start + TRAIN]; test = ss[start + TRAIN:start + TRAIN + TEST]
            if len(train) != TRAIN or len(test) != TEST: errors.append(f"{sym}: bad 60/20 window") ; continue
            train_dates = [x["date"] for x in train]; test_dates = [x["date"] for x in test]
            if train_dates[-1] >= test_dates[0]: errors.append(f"{sym}: training_end >= effective")
            if len(set(train_dates)) != 60 or len(set(test_dates)) != 20: errors.append(f"{sym}: duplicate session dates")
            if set(train_dates) & set(test_dates): errors.append(f"{sym}: train/OOS overlap")
            th = thresholds(train)
            if not all(np.isfinite(v) for v in th.values()): errors.append(f"{sym}: non-finite threshold")
            train_start, train_end, effective, oos_end = train_dates[0], train_dates[-1], test_dates[0], test_dates[-1]
            threshold_sets.append({
                "threshold_set_id": f"PSY29-EVD-V2|{universe_hash[:12]}|{sym}|{train_start}|{train_end}",
                "effective_nse_session_date": effective,
                "training_window": {"start": train_start, "end": train_end, "session_count": 60},
                "oos_window": {"start": effective, "end": oos_end, "session_count": 20},
                "stock": sym,
                "thresholds": th,
                "hard_earliest_offset": {"Trend": 0, "Strong Trend": 0, "OR Continuation": 15},
            })
    if errors: raise RuntimeError("VALIDATION FAILED: " + "; ".join(errors[:50]))
    artifact = {
        "schema": "PSY29_EVENT_DETECTOR_THRESHOLDS_V2",
        "artifact_type": "walk_forward_session_keyed",
        "methodology": {"train_sessions": 60, "test_sessions": 20, "step_sessions": 20, "timezone": "Asia/Kolkata"},
        "research_source": {"repository": "zahidshaikmohammed-cmyk/psy29", "path": "research/event_time_discovery.py", "commit": CANONICAL_COMMIT},
        "dataset_provenance": {"workflow_run_id": DATASET_RUN_ID, "dataset_sha256": a.dataset_sha256},
        "generator_provenance": {"generator_commit": a.generator_commit},
        "universe": {"count": 29, "symbols": UNIVERSE, "sha256": universe_hash},
        "threshold_set_count": len(threshold_sets),
        "walk_forward_window_count_per_stock": window_count,
        "threshold_sets": threshold_sets,
    }
    out = Path(a.out); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")
    validation = {"status":"PASS","threshold_set_count":len(threshold_sets),"stock_count":29,"window_count_per_stock":window_count,"canonical_commit":CANONICAL_COMMIT,"dataset_run_id":DATASET_RUN_ID,"dataset_sha256":a.dataset_sha256,"generator_commit":a.generator_commit}
    Path(a.validation).write_text(json.dumps(validation, indent=2, sort_keys=True), encoding="utf-8")

if __name__ == "__main__": main()
