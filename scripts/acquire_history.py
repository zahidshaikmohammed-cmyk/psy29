"""Acquire Dhan 1-minute history for the configured research universe.

Usage:
  python scripts/acquire_history.py --from-date 2021-01-01 --to-date 2026-08-13

This script is intentionally research-only: it downloads market data and does
not place, modify, or cancel orders.
"""

import argparse
from datetime import date
from pathlib import Path

import pandas as pd

from dhan.client import DhanClient
from dhan.historical import fetch_intraday
from dhan.instruments import nse_equities

OUT = Path("data/raw/intraday")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-date", required=True)
    parser.add_argument("--to-date", required=True)
    args = parser.parse_args()

    client = DhanClient()
    instruments = nse_equities()
    OUT.mkdir(parents=True, exist_ok=True)

    for _, row in instruments.iterrows():
        symbol = str(row.get("SEM_TRADING_SYMBOL", row.get("SYMBOL_NAME", ""))).strip()
        security_id = str(row["SEM_SMST_SECURITY_ID"])
        if not symbol or not security_id:
            continue
        rows = fetch_intraday(
            client,
            security_id,
            date.fromisoformat(args.from_date),
            date.fromisoformat(args.to_date),
            interval="1",
        )
        if rows:
            pd.DataFrame(rows).drop_duplicates(["security_id", "timestamp"]).to_parquet(
                OUT / f"{symbol}.parquet", index=False
            )
        print(f"completed={symbol} rows={len(rows)}", flush=True)


if __name__ == "__main__":
    main()
