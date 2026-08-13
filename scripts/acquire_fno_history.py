"""Acquire 1-minute cash-equity history for NSE stock-F&O underlyings."""

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


def load_fno_underlyings():
    response = requests.get(MASTER_URL, timeout=60)
    response.raise_for_status()
    df = pd.read_csv(StringIO(response.text), low_memory=False)
    fno = df[(df["EXCH_ID"] == "NSE") & (df["SEGMENT"] == "D") & (df["INSTRUMENT"] == "FUTSTK")]
    fno = fno[["UNDERLYING_SECURITY_ID", "UNDERLYING_SYMBOL"]].dropna().drop_duplicates()
    eq = df[(df["EXCH_ID"] == "NSE") & (df["SEGMENT"] == "E")]
    eq = eq[["SEM_SMST_SECURITY_ID", "SEM_TRADING_SYMBOL"]].drop_duplicates()
    fno["UNDERLYING_SECURITY_ID"] = fno["UNDERLYING_SECURITY_ID"].astype(str)
    eq["SEM_SMST_SECURITY_ID"] = eq["SEM_SMST_SECURITY_ID"].astype(str)
    return fno.merge(eq, left_on="UNDERLYING_SECURITY_ID", right_on="SEM_SMST_SECURITY_ID")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-date", required=True)
    parser.add_argument("--to-date", required=True)
    args = parser.parse_args()
    client = DhanClient()
    universe = load_fno_underlyings()
    OUT.mkdir(parents=True, exist_ok=True)
    for _, row in universe.iterrows():
        symbol = str(row["SEM_TRADING_SYMBOL"]).strip()
        security_id = str(row["UNDERLYING_SECURITY_ID"])
        rows = fetch_intraday(client, security_id, date.fromisoformat(args.from_date), date.fromisoformat(args.to_date), interval="1")
        if rows:
            pd.DataFrame(rows).drop_duplicates(["security_id", "timestamp"]).to_parquet(OUT / f"{symbol}.parquet", index=False)
        print(f"completed={symbol} rows={len(rows)}", flush=True)


if __name__ == "__main__":
    main()
