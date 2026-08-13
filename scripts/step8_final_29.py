"""
PSY29 STEP 8
FINAL 29 STOCK SELECTION ENGINE

Input:
- Step 6 V3 OOS edge ranking
- Step 7 liquidity audit

Output:
- Exactly 29 stocks
- No manual selection
- No future data
- No final selection before this stage

Selection philosophy:
1. Require liquidity pass.
2. Require sufficient OOS evidence.
3. Combine OOS edge with liquidity quality.
4. Avoid excessive concentration.
5. Select exactly 29 survivors.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


FINAL_COUNT = 29

# Minimum evidence requirement.
MIN_OOS_SESSIONS = 60
MIN_TREND_EVENTS = 5

# Maximum representation from one sector if sector data exists.
MAX_SECTOR_COUNT = 5


def minmax(series: pd.Series) -> pd.Series:
    series = pd.to_numeric(series, errors="coerce")

    low = series.min()
    high = series.max()

    if (
        not np.isfinite(low)
        or not np.isfinite(high)
        or high == low
    ):
        return pd.Series(
            np.ones(len(series)),
            index=series.index,
        )

    return (series - low) / (high - low)


def load_inputs(
    edge_path: Path,
    liquidity_path: Path,
) -> pd.DataFrame:

    edge = pd.read_csv(edge_path)
    liquidity = pd.read_csv(liquidity_path)

    if "symbol" not in edge.columns:
        raise RuntimeError(
            "Step 6 ranking missing symbol column."
        )

    if "symbol" not in liquidity.columns:
        raise RuntimeError(
            "Step 7 audit missing symbol column."
        )

    required_edge = [
        "oos_edge_score_v3",
        "oos_sessions",
        "oos_trend_event_count",
        "oos_trend_event_rate",
        "oos_strong_trend_event_rate",
        "oos_or_continuation_rate",
    ]

    for column in required_edge:
        if column not in edge.columns:
            raise RuntimeError(
                f"Missing Step 6 column: {column}"
            )

    required_liquidity = [
        "liquidity_pass",
        "liquidity_score",
        "edge_liquidity_score",
    ]

    for column in required_liquidity:
        if column not in liquidity.columns:
            raise RuntimeError(
                f"Missing Step 7 column: {column}"
            )

    columns_from_liquidity = [
        "symbol",
        "liquidity_pass",
        "liquidity_score",
        "edge_liquidity_score",
    ]

    liquidity = liquidity[
        columns_from_liquidity
    ].copy()

    merged = edge.merge(
        liquidity,
        on="symbol",
        how="inner",
        validate="one_to_one",
    )

    return merged


def prepare_candidates(
    df: pd.DataFrame,
) -> pd.DataFrame:

    df = df.copy()

    numeric_columns = [
        "oos_edge_score_v3",
        "oos_sessions",
        "oos_trend_event_count",
        "oos_trend_event_rate",
        "oos_strong_trend_event_rate",
        "oos_or_continuation_rate",
        "liquidity_score",
        "edge_liquidity_score",
    ]

    for column in numeric_columns:
        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        )

    df["liquidity_pass"] = (
        df["liquidity_pass"]
        .astype(bool)
    )

    # Mandatory gates.
    df["evidence_pass"] = (
        (df["oos_sessions"] >= MIN_OOS_SESSIONS)
        &
        (
            df["oos_trend_event_count"]
            >= MIN_TREND_EVENTS
        )
    )

    df["candidate_pass"] = (
        df["liquidity_pass"]
        &
        df["evidence_pass"]
    )

    candidates = df[
        df["candidate_pass"]
    ].copy()

    if candidates.empty:
        raise RuntimeError(
            "No stocks survived mandatory "
            "edge + liquidity gates."
        )

    # Normalised research components.
    candidates["edge_norm"] = minmax(
        candidates["oos_edge_score_v3"]
    )

    candidates["trend_norm"] = minmax(
        candidates["oos_trend_event_rate"]
    )

    candidates["strong_trend_norm"] = minmax(
        candidates[
            "oos_strong_trend_event_rate"
        ]
    )

    candidates["or_norm"] = minmax(
        candidates[
            "oos_or_continuation_rate"
        ]
    )

    candidates["liquidity_norm"] = minmax(
        candidates["liquidity_score"]
    )

    candidates["evidence_norm"] = minmax(
        candidates["oos_sessions"]
    )

    # Final selection score.
    #
    # Edge dominates.
    # Liquidity is a meaningful secondary gate.
    candidates["final_selection_score"] = (
        0.35 * candidates["edge_norm"]
        +
        0.20 * candidates["trend_norm"]
        +
        0.15 * candidates["strong_trend_norm"]
        +
        0.10 * candidates["or_norm"]
        +
        0.15 * candidates["liquidity_norm"]
        +
        0.05 * candidates["evidence_norm"]
    )

    candidates = candidates.sort_values(
        "final_selection_score",
        ascending=False,
    ).reset_index(drop=True)

    return candidates


def select_exactly_29(
    candidates: pd.DataFrame,
) -> pd.DataFrame:

    if len(candidates) < FINAL_COUNT:
        raise RuntimeError(
            f"Only {len(candidates)} stocks passed "
            f"mandatory gates; cannot select "
            f"exactly {FINAL_COUNT}."
        )

    selected_rows = []

    sector_counts = {}

    has_sector = (
        "sector" in candidates.columns
    )

    for _, row in candidates.iterrows():

        if len(selected_rows) >= FINAL_COUNT:
            break

        if has_sector:
            sector = str(
                row.get(
                    "sector",
                    "UNKNOWN",
                )
            )

            current_count = (
                sector_counts.get(
                    sector,
                    0,
                )
            )

            if (
                current_count
                >= MAX_SECTOR_COUNT
            ):
                continue

        selected_rows.append(row)

        if has_sector:
            sector_counts[
                sector
            ] = (
                sector_counts.get(
                    sector,
                    0,
                )
                + 1
            )

    # If sector diversification caused fewer
    # than 29 names, fill remaining slots strictly
    # by score. This guarantees exactly 29.
    if len(selected_rows) < FINAL_COUNT:

        already_selected = {
            row["symbol"]
            for row in selected_rows
        }

        remaining = candidates[
            ~candidates["symbol"].isin(
                already_selected
            )
        ]

        for _, row in remaining.iterrows():

            if len(selected_rows) >= FINAL_COUNT:
                break

            selected_rows.append(row)

    selected = pd.DataFrame(
        selected_rows
    ).copy()

    if len(selected) != FINAL_COUNT:
        raise RuntimeError(
            "Final selection did not produce "
            "exactly 29 stocks."
        )

    selected = selected.sort_values(
        "final_selection_score",
        ascending=False,
    ).reset_index(drop=True)

    selected.insert(
        0,
        "final_rank",
        np.arange(
            1,
            FINAL_COUNT + 1,
        ),
    )

    selected[
        "final_psy29"
    ] = True

    return selected


def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--edge-ranking",
        required=True,
    )

    parser.add_argument(
        "--liquidity-audit",
        required=True,
    )

    parser.add_argument(
        "--output",
        default="output/step8",
    )

    args = parser.parse_args()

    output = Path(args.output)

    output.mkdir(
        parents=True,
        exist_ok=True,
    )

    edge_path = Path(
        args.edge_ranking
    )

    liquidity_path = Path(
        args.liquidity_audit
    )

    merged = load_inputs(
        edge_path,
        liquidity_path,
    )

    candidates = prepare_candidates(
        merged
    )

    selected = select_exactly_29(
        candidates
    )

    # Full audit of all candidates.
    candidates.insert(
        0,
        "candidate_rank",
        np.arange(
            1,
            len(candidates) + 1,
        ),
    )

    candidates.to_csv(
        output
        / "step8_candidate_audit.csv",
        index=False,
    )

    # Final 29.
    selected.to_csv(
        output
        / "PSY29_FINAL_29.csv",
        index=False,
    )

    # Lightweight machine-readable output.
    final_symbols = selected[
        [
            "final_rank",
            "symbol",
            "final_selection_score",
            "oos_edge_score_v3",
            "oos_trend_event_rate",
            "oos_strong_trend_event_rate",
            "oos_or_continuation_rate",
            "liquidity_score",
            "edge_liquidity_score",
            "oos_sessions",
            "oos_trend_event_count",
        ]
    ].copy()

    final_symbols.to_json(
        output
        / "PSY29_FINAL_29.json",
        orient="records",
        indent=2,
    )

    summary = {
        "project": "PSY29",
        "step": 8,
        "version": "1.0",
        "input_universe": int(
            len(merged)
        ),
        "liquidity_passed": int(
            merged[
                "liquidity_pass"
            ].sum()
        ),
        "evidence_passed": int(
            merged[
                "evidence_pass"
            ].sum()
        ),
        "candidate_pool": int(
            len(candidates)
        ),
        "final_selection_count": int(
            len(selected)
        ),
        "final_selection_target": FINAL_COUNT,
        "exactly_29": (
            len(selected)
            == FINAL_COUNT
        ),
        "manual_selection": False,
        "selection_method": (
            "OOS edge + liquidity + "
            "evidence-weighted ranking"
        ),
        "status": (
            "PASS"
            if len(selected)
            == FINAL_COUNT
            else "FAIL"
        ),
        "generated_at_utc": (
            pd.Timestamp.utcnow()
            .isoformat()
        ),
    }

    (
        output
        / "step8_summary.json"
    ).write_text(
        json.dumps(
            summary,
            indent=2,
        )
    )

    print(
        json.dumps(
            summary,
            indent=2,
        )
    )

    print(
        "\nFINAL PSY29\n"
    )

    for _, row in selected.iterrows():
        print(
            f'{int(row["final_rank"]):02d}. '
            f'{row["symbol"]} '
            f'| score='
            f'{row["final_selection_score"]:.6f}'
        )


if __name__ == "__main__":
    main()
