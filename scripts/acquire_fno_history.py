"""PSY29 Step 2: acquire 1-minute NSE cash-equity history for stock-F&O underlyings."""

import argparse
import json
import re
from datetime import date, datetime, timezone
from io import StringIO
from pathlib import Path

import pandas as pd
import requests

from dhan.client import DhanClient
from dhan.historical import fetch_intraday

MASTER_URL = "https://images.dhan.co/api-data/api-scrip-master-detailed.csv"
OUT = Path("data/raw/intraday")
CHECKPOINT = Path("output/step2_checkpoint.json")
FAILURES = Path("output/step2_failures.jsonl")


def normalize_security_id(value: object) -> str:
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "<na>"}:
        raise ValueError(f"Invalid empty security ID: {value!r}")
    if re.fullmatch(r"\d+\.0+", text):
        text = text.split(".", 1)[0]
    if not text.isdigit():
        raise ValueError(f"Invalid non-numeric Dhan security ID: {value!r}")
    return text


def load_fno_underlyings() -> pd.DataFrame:
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
    fno["UNDERLYING_SYMBOL"] = fno["UNDERLYING_SYMBOL"].astype(str).str.strip()
    fno = fno[
        ~fno["UNDERLYING_SYMBOL"].str.upper().str.contains("NSETEST", na=False)
    ].copy()
    fno["UNDERLYING_SECURITY_ID"] = fno["UNDERLYING_SECURITY_ID"].map(
        normalize_security_id
    )
    fno = fno[
        (fno["UNDERLYING_SECURITY_ID"] != "")
        & (fno["UNDERLYING_SYMBOL"] != "")
    ].drop_duplicates(subset=["UNDERLYING_SECURITY_ID"])

    if fno.empty:
        raise RuntimeError("No NSE FUTSTK underlyings found in Dhan instrument master")

    return fno.sort_values("UNDERLYING_SYMBOL").reset_index(drop=True)


def load_checkpoint() -> dict:
    if not CHECKPOINT.exists():
        return {"completed": [], "failed": [], "updated_at_utc": None}
    try:
        return json.loads(CHECKPOINT.read_text(encoding="utf-8"))
    except Exception:
        return {"completed": [], "failed": [], "updated_at_utc": None}


def save_checkpoint(
    universe_size: int,
    from_date: date,
    to_date: date,
    completed: list[str],
    failed: list[dict],
) -> None:
    CHECKPOINT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "project": "PSY29",
        "step": 2,
        "from_date": str(from_date),
        "to_date": str(to_date),
        "universe_size": universe_size,
        "completed_count": len(completed),
        "failed_count": len(failed),
        "completed": sorted(set(completed)),
        "failed": failed,
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    temp = CHECKPOINT.with_suffix(".tmp")
    temp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temp.replace(CHECKPOINT)


def record_failure(symbol: str, security_id: str, error: Exception) -> dict:
    failure = {
        "symbol": symbol,
        "security_id": security_id,
        "error": str(error),
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }
    FAILURES.parent.mkdir(parents=True, exist_ok=True)
    with FAILURES.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(failure) + "\n")
    return failure


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
    CHECKPOINT.parent.mkdir(parents=True, exist_ok=True)

    checkpoint = load_checkpoint()
    completed = set(checkpoint.get("completed", []))
    failed_records = list(checkpoint.get("failed", []))

    for parquet in OUT.glob("*.parquet"):
        if parquet.stat().st_size > 0:
            completed.add(parquet.stem)

    # A resumed run may contain failures from an earlier attempt. They remain
    # retryable until the corresponding stock succeeds.
    failed_by_symbol = {
        item["symbol"]: item for item in failed_records if item.get("symbol")
    }

    save_checkpoint(len(universe), from_date, to_date, list(completed), list(failed_by_symbol.values()))

    total = len(universe)

    for i, row in universe.iterrows():
        symbol = str(row["UNDERLYING_SYMBOL"])
        security_id = normalize_security_id(row["UNDERLYING_SECURITY_ID"])

        if symbol in completed and (OUT / f"{symbol}.parquet").exists():
            failed_by_symbol.pop(symbol, None)
            print(f"[{i + 1}/{total}] {symbol} — RESUME SKIP (already acquired)", flush=True)
            continue

        print(f"[{i + 1}/{total}] {symbol} ({security_id})", flush=True)

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
                raise RuntimeError("Dhan returned zero candles")

            data = pd.DataFrame(rows)
            if data.empty:
                raise RuntimeError("Dhan returned an empty dataframe")

            data = data.drop_duplicates(
                subset=["security_id", "timestamp"]
            ).sort_values("timestamp").reset_index(drop=True)

            if data.empty:
                raise RuntimeError("No usable candles after normalization")

            data.to_parquet(OUT / f"{symbol}.parquet", index=False)
            completed.add(symbol)
            failed_by_symbol.pop(symbol, None)
            print(f"SUCCESS: {symbol} rows={len(data):,}", flush=True)

        except Exception as exc:
            failed_by_symbol[symbol] = record_failure(symbol, security_id, exc)
            print(f"FAILED: {symbol}: {exc}", flush=True)

        finally:
            save_checkpoint(
                total,
                from_date,
                to_date,
                list(completed),
                list(failed_by_symbol.values()),
            )

    failed_symbols = set(failed_by_symbol)
    print(
        f"Acquisition summary: universe={total} completed={len(completed)} "
        f"failed={len(failed_symbols)}",
        flush=True,
    )

    if len(completed) == 0:
        raise RuntimeError("PSY29 acquired zero datasets")

    if failed_symbols:
        raise RuntimeError(
            f"PSY29 Step 2 incomplete: {len(failed_symbols)} stocks failed. "
            "Rerun with the partial-run artifact to resume."
        )


if __name__ == "__main__":
    main()
