"""PSY29 Step 2: acquire 1-minute NSE cash-equity history for stock-F&O underlyings."""

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


def load_fno_underlyings() -> pd.DataFrame:
    """Build the NSE stock-F&O underlying universe from Dhan's current master."""
    response = requests.get(MASTER_URL, timeout=60)
    response.raise_for_status()
    df = pd.read_csv(StringIO(response.text), low_memory=False)

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
            "Dhan instrument master missing required columns: "
            + ", ".join(sorted(missing))
        )

    fno = df[
        (df["EXCH_ID"].astype(str).str.upper() == "NSE")
        & (df["SEGMENT"].astype(str).str.upper() == "D")
        & (df["INSTRUMENT"].astype(str).str.upper() == "FUTSTK")
    ][["UNDERLYING_SECURITY_ID", "UNDERLYING_SYMBOL"]].copy()

    fno = fno.dropna().drop_duplicates()
    fno["UNDERLYING_SECURITY_ID"] = fno["UNDERLYING_SECURITY_ID"].astype(str).str.strip()
    fno["UNDERLYING_SYMBOL"] = fno["UNDERLYING_SYMBOL"].astype(str).str.strip()
    fno = fno[
        (fno["UNDERLYING_SECURITY_ID"] != "")
        & (fno["UNDERLYING_SYMBOL"] != "")
    ].drop_duplicates(subset=["UNDERLYING_SECURITY_ID"])

    if fno.empty:
        raise RuntimeError("No NSE FUTSTK underlyings found in Dhan instrument master")

    return fno.sort_values("UNDERLYING_SYMBOL").reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-date", required=True)
    parser.add_argument("--to-date", required=True)
    args = parser.parse_args()

    from_date = date.fromisoformat(args.from_date)
    to_date = date.fromisoformat(args.to_date)
    if from_date > to_date:
        raise ValueError("--from-date cannot be after --to-date")

    universe = load_fno_underlyings()
    print(f"Dhan NSE stock-F&O universe: {len(universe)} stocks", flush=True)

    client = DhanClient()
    OUT.mkdir(parents=True, exist_ok=True)

    completed = 0
    failed = 0

    for i, row in universe.iterrows():
        symbol = row["UNDERLYING_SYMBOL"]
        security_id = row["UNDERLYING_SECURITY_ID"]
        print(f"[{i + 1}/{len(universe)}] {symbol} ({security_id})", flush=True)

        try:
            rows = fetch_intraday(
                client,
                security_id,
                from_date,
                to_date,
                interval="1",
                exchange_segment="NSE_EQ",
                instrument="EQUITY",
            )

            if not rows:
                print(f"WARNING: {symbol}: 0 candles", flush=True)
                failed += 1
                continue

            data = pd.DataFrame(rows)
            if data.empty:
                failed += 1
                continue

            data = data.drop_duplicates(
                subset=["security_id", "timestamp"]
            ).sort_values("timestamp").reset_index(drop=True)

            data.to_parquet(OUT / f"{symbol}.parquet", index=False)
            completed += 1
            print(f"SUCCESS: {symbol} rows={len(data):,}", flush=True)

        except Exception as exc:
            failed += 1
            print(f"FAILED: {symbol}: {exc}", flush=True)
            continue

    print(
        f"Acquisition summary: universe={len(universe)} "
        f"completed={completed} failed={failed}",
        flush=True,
    )

    if completed == 0:
        raise RuntimeError("PSY29 acquired zero datasets")


if __name__ == "__main__":
    main()
