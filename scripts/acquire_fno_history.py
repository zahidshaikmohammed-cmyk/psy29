"""
PSY29 STEP 2
Acquire 1-minute NSE cash-equity historical data for stocks
that have an NSE stock-futures (FUTSTK) contract.

Research-only.
NO ORDER / TRADING functionality.
"""

import argparse
from datetime import date
from io import StringIO
from pathlib import Path

import pandas as pd
import requests

from dhan.client import DhanClient
from dhan.historical import fetch_intraday


MASTER_URL = "https://images.dhan.co/api-data/api-scrip-master-detailed.csv"

OUT = Path("data/raw/intraday")


def download_master() -> pd.DataFrame:
    """Download the current Dhan detailed instrument master."""

    print("Downloading current Dhan instrument master...", flush=True)

    response = requests.get(
        MASTER_URL,
        timeout=60,
    )

    response.raise_for_status()

    df = pd.read_csv(
        StringIO(response.text),
        low_memory=False,
    )

    print(
        f"Instrument master downloaded: {len(df):,} rows",
        flush=True,
    )

    print(
        "Columns detected:",
        ", ".join(df.columns.tolist()),
        flush=True,
    )

    return df


def load_fno_underlyings() -> pd.DataFrame:
    """
    Build the research universe directly from FUTSTK contracts.

    We intentionally use:
        SECURITY_ID
        UNDERLYING_SECURITY_ID
        UNDERLYING_SYMBOL

    instead of the deprecated SEM_* fields.
    """

    df = download_master()

    required = {
        "EXCH_ID",
        "SEGMENT",
        "INSTRUMENT",
        "UNDERLYING_SECURITY_ID",
        "UNDERLYING_SYMBOL",
    }

    missing = required - set(df.columns)

    if missing:
        raise RuntimeError(
            "Dhan instrument master is missing required columns: "
            + ", ".join(sorted(missing))
        )

    # NSE derivatives
    fno = df[
        (df["EXCH_ID"].astype(str).str.upper() == "NSE")
        & (df["SEGMENT"].astype(str).str.upper() == "D")
        & (
            df["INSTRUMENT"]
            .astype(str)
            .str.upper()
            .eq("FUTSTK")
        )
    ].copy()

    if fno.empty:
        raise RuntimeError(
            "No NSE FUTSTK instruments were found in Dhan's current master."
        )

    # Keep only the underlying equity identifiers.
    universe = fno[
        [
            "UNDERLYING_SECURITY_ID",
            "UNDERLYING_SYMBOL",
        ]
    ].copy()

    universe = universe.dropna(
        subset=[
            "UNDERLYING_SECURITY_ID",
            "UNDERLYING_SYMBOL",
        ]
    )

    universe["UNDERLYING_SECURITY_ID"] = (
        universe["UNDERLYING_SECURITY_ID"]
        .astype(str)
        .str.strip()
    )

    universe["UNDERLYING_SYMBOL"] = (
        universe["UNDERLYING_SYMBOL"]
        .astype(str)
        .str.strip()
    )

    universe = universe[
        (universe["UNDERLYING_SECURITY_ID"] != "")
        & (universe["UNDERLYING_SYMBOL"] != "")
    ]

    universe = universe.drop_duplicates(
        subset=["UNDERLYING_SECURITY_ID"]
    )

    universe = universe.sort_values(
        "UNDERLYING_SYMBOL"
    ).reset_index(drop=True)

    print(
        f"NSE stock-F&O underlying universe: {len(universe):,} stocks",
        flush=True,
    )

    print(
        "First candidates:",
        ", ".join(
            universe["UNDERLYING_SYMBOL"]
            .head(20)
            .tolist()
        ),
        flush=True,
    )

    return universe


def main() -> None:

    parser = argparse.ArgumentParser(
        description=(
            "PSY29 Step 2 - "
            "Acquire 1-minute NSE equity history"
        )
    )

    parser.add_argument(
        "--from-date",
        required=True,
        help="YYYY-MM-DD",
    )

    parser.add_argument(
        "--to-date",
        required=True,
        help="YYYY-MM-DD",
    )

    args = parser.parse_args()

    from_date = date.fromisoformat(
        args.from_date
    )

    to_date = date.fromisoformat(
        args.to_date
    )

    if from_date > to_date:
        raise ValueError(
            "--from-date cannot be after --to-date"
        )

    print(
        "",
        flush=True,
    )

    print(
        "==============================================",
        flush=True,
    )

    print(
        "PSY29 STEP 2 - HISTORICAL ACQUISITION",
        flush=True,
    )

    print(
        "==============================================",
        flush=True,
    )

    print(
        f"Date range: {from_date} → {to_date}",
        flush=True,
    )

    # Build universe
    universe = load_fno_underlyings()

    # Create output directory
    OUT.mkdir(
        parents=True,
        exist_ok=True,
    )

    # Initialize Dhan client
    client = DhanClient()

    total = len(universe)

    completed = 0
    failed = 0

    for index, row in universe.iterrows():

        symbol = str(
            row["UNDERLYING_SYMBOL"]
        ).strip()

        security_id = str(
            row["UNDERLYING_SECURITY_ID"]
        ).strip()

        position = index + 1

        print(
            "",
            flush=True,
        )

        print(
            f"[{position}/{total}] {symbol} "
            f"(security_id={security_id})",
            flush=True,
        )

        try:

            rows = fetch_intraday(
                client=client,
                security_id=security_id,
                from_date=from_date,
                to_date=to_date,
                interval="1",
                exchange_segment="NSE_EQ",
                instrument="EQUITY",
            )

            if not rows:
                print(
                    f"WARNING: {symbol} returned 0 candles",
                    flush=True,
                )

                failed += 1
                continue

            df = pd.DataFrame(rows)

            if df.empty:
                failed += 1
                continue

            # Remove duplicate candles.
            df = df.drop_duplicates(
                subset=[
                    "security_id",
                    "timestamp",
                ]
            )

            # Sort chronologically.
            df = df.sort_values(
                "timestamp"
            ).reset_index(drop=True)

            output_file = (
                OUT / f"{symbol}.parquet"
            )

            df.to_parquet(
                output_file,
                index=False,
            )

            completed += 1

            print(
                f"SUCCESS: {symbol} "
                f"candles={len(df):,}",
                flush=True,
            )

        except Exception as exc:

            failed += 1

            print(
                f"FAILED: {symbol}: {exc}",
                flush=True,
            )

            # Continue with the next stock.
            continue

    print(
        "",
        flush=True,
    )

    print(
        "==============================================",
        flush=True,
    )

    print(
        "PSY29 STEP 2 ACQUISITION SUMMARY",
        flush=True,
    )

    print(
        "==============================================",
        flush=True,
    )

    print(
        f"Universe:   {total}",
        flush=True,
    )

    print(
        f"Completed:  {completed}",
        flush=True,
    )

    print(
        f"Failed:     {failed}",
        flush=True,
    )

    print(
        "==============================================",
        flush=True,
    )

    # We require at least one successful dataset.
    if completed == 0:
        raise RuntimeError(
            "PSY29 acquired zero datasets."
        )


if __name__ == "__main__":
    main()
