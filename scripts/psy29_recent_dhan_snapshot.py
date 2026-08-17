#!/usr/bin/env python3
"""Fetch the most recent completed NSE session from real DHAN data for the read-only PSY29 terminal.

This is display data only. It never feeds the off-market deterministic validation
contract and never enables signal generation or order execution.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timedelta, time as dtime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.psy29_live_dhan_acquisition import add_indicators_1m, add_indicators_5m, build_execution_row, load_universe, parse_rows, resolve_security_ids
from dhan.client import DhanClient

IST = ZoneInfo("Asia/Kolkata")
MARKET_CLOSE = dtime(15, 30)
MARKET_OPEN = dtime(9, 15)
MAX_LOOKBACK_DAYS = 10


def candidate_dates(now: datetime, limit: int = MAX_LOOKBACK_DAYS) -> list:
    dates = []
    day = now.date()
    if not (now.weekday() < 5 and now.time() > MARKET_CLOSE):
        day -= timedelta(days=1)
    while len(dates) < limit:
        if day.weekday() < 5:
            dates.append(day)
        day -= timedelta(days=1)
    return dates


def fetch_day(client: DhanClient, security_id: str, session_date):
    start = datetime.combine(session_date, MARKET_OPEN, tzinfo=IST)
    end = start + timedelta(days=1)
    payload = {
        "securityId": str(security_id),
        "exchangeSegment": "NSE_EQ",
        "instrument": "EQUITY",
        "interval": "1",
        "oi": False,
        "fromDate": start.strftime("%Y-%m-%d %H:%M:%S"),
        "toDate": end.strftime("%Y-%m-%d %H:%M:%S"),
    }
    return parse_rows(client.post("/charts/intraday", payload, timeout=20, retries=2))


def build_recent_row(symbol: str, security_id: str, df) -> dict:
    x1 = add_indicators_1m(df)
    if x1.empty or len(x1) < 20:
        raise RuntimeError(f"{symbol}: insufficient historical 1m candles")
    bars = x1.copy()
    bars["bucket"] = bars["dt"].dt.floor("5min")
    x5 = bars.groupby("bucket", sort=True).agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
    ).reset_index()
    x5["timestamp"] = x5["bucket"].map(lambda value: int(value.timestamp()))
    x5 = add_indicators_5m(x5)
    if x5.empty or len(x5) < 20:
        raise RuntimeError(f"{symbol}: insufficient historical 5m candles")
    latest = x1.iloc[-1]
    ts = datetime.fromtimestamp(int(latest["timestamp"]), tz=timezone.utc).isoformat().replace("+00:00", "Z")
    row = build_execution_row(symbol, security_id, x1, x5, ts)
    row.update({
        "security_id": security_id,
        "exchange_segment": "NSE_EQ",
        "freshness_status": "RECENT_HISTORICAL",
        "market_data_kind": "MOST_RECENT_COMPLETED_NSE_SESSION",
        "session_date": str(latest["dt"].date()),
    })
    return row


def write_snapshot(out: Path, rows: list[dict], session_date) -> None:
    out.mkdir(parents=True, exist_ok=True)
    rows.sort(key=lambda r: r["symbol"])
    fields = list(rows[0])
    with (out / "recent_market_snapshot.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    validation = {
        "contract": "PSY29_RECENT_DHAN_MARKET_DATA",
        "status": "PASS",
        "provider": "DHAN",
        "live_data": False,
        "market_data_kind": "MOST_RECENT_COMPLETED_NSE_SESSION",
        "session_date": str(session_date),
        "coverage": {"expected": 29, "actual": len(rows), "unique": len({r["symbol"] for r in rows})},
        "source": "DHAN /charts/intraday historical data",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "signal_generation": False,
        "order_execution": False,
    }
    (out / "recent_market_data_validation.json").write_text(json.dumps(validation, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--universe", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    symbols = load_universe(str(args.universe))
    client = DhanClient()
    mapping = resolve_security_ids(symbols)
    now = datetime.now(IST)
    failures = []
    for session_date in candidate_dates(now):
        rows = []
        failures.clear()
        for symbol in symbols:
            try:
                rows.append(build_recent_row(symbol, mapping[symbol], fetch_day(client, mapping[symbol], session_date)))
            except Exception as exc:
                failures.append({"symbol": symbol, "error": str(exc)})
        if len(rows) == 29 and not failures and len({r["symbol"] for r in rows}) == 29:
            write_snapshot(args.output, rows, session_date)
            print(json.dumps({"status": "PASS", "provider": "DHAN", "session_date": str(session_date), "coverage": 29}, indent=2))
            return
    raise SystemExit(f"Unable to obtain a complete 29/29 recent DHAN session: {failures}")


if __name__ == "__main__":
    main()
