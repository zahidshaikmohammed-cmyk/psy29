"""PSY29 Phase 3 — One-Minute Collection Engine.

Production mode uses only successful DHAN responses. Missing minutes are
recorded as missing events; no synthetic market values are ever generated.
"""
import argparse
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
ROOT = Path(__file__).resolve().parent
MASTER = ROOT.parent / "phase1" / "instrument_master.json"
VAULT = ROOT / "snapshots"
URL = "https://api.dhan.co/v2/marketfeed/quote"
SESSION_START = (9, 15)
SESSION_END_EXCLUSIVE = (15, 30)


def official_minutes(day):
    start = datetime(day.year, day.month, day.day, *SESSION_START, tzinfo=IST)
    end = datetime(day.year, day.month, day.day, *SESSION_END_EXCLUSIVE, tzinfo=IST)
    cur, result = start, []
    while cur < end:
        result.append(cur)
        cur += timedelta(minutes=1)
    return result


def dhan_quote(instruments):
    token = os.environ.get("DHAN_ACCESS_TOKEN")
    client_id = os.environ.get("DHAN_CLIENT_ID")
    if not token or not client_id:
        raise RuntimeError("DHAN credentials unavailable")
    payload = json.dumps({"NSE_EQ": [int(x["security_id"]) for x in instruments]}).encode()
    request = urllib.request.Request(URL, data=payload, method="POST", headers={
        "Accept": "application/json", "Content-Type": "application/json",
        "access-token": token, "client-id": client_id, "User-Agent": "PSY29-Phase3/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        body = json.loads(response.read().decode("utf-8"))
    if response.status != 200 or body.get("status") != "success":
        raise RuntimeError(f"DHAN quote failure: HTTP {response.status}")
    rows = body.get("data", {}).get("NSE_EQ", {})
    if len(rows) != 29:
        raise RuntimeError(f"DHAN returned {len(rows)}/29 instruments")
    return rows


def snapshot_path(day):
    return VAULT / f"{day.isoformat()}.jsonl"


def load_seen(path):
    if not path.exists():
        return set()
    return {json.loads(line)["official_minute"] for line in path.read_text().splitlines() if line.strip()}


def collect_minute(minute, instruments, provider=dhan_quote):
    VAULT.mkdir(parents=True, exist_ok=True)
    path = snapshot_path(minute.date())
    key = minute.isoformat()
    if key in load_seen(path):
        return "duplicate-protected"
    acquisition_started = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    rows = provider(instruments)
    provider_received = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    by_id = {x["security_id"]: x["symbol"] for x in instruments}
    records = []
    for security_id, quote in rows.items():
        if security_id not in by_id:
            raise RuntimeError(f"unexpected Security ID {security_id}")
        if "last_price" not in quote or not isinstance(quote.get("depth"), dict):
            raise RuntimeError(f"incomplete quote/depth for {security_id}")
        records.append({"symbol": by_id[security_id], "security_id": security_id, "provider_data": quote})
    if len(records) != 29:
        raise RuntimeError(f"snapshot contains {len(records)}/29 stocks")
    record = {
        "schema": "PSY29_ONE_MINUTE_SNAPSHOT_V1", "official_minute": key,
        "provider": "DHAN", "exchange_segment": "NSE_EQ", "instrument_count": 29,
        "acquisition_started_at": acquisition_started, "provider_received_at": provider_received,
        "records": records}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, separators=(",", ":")) + "\n")
        handle.flush(); os.fsync(handle.fileno())
    return "collected"


def run_window(day=None, start_time=SESSION_START, end_time=SESSION_END_EXCLUSIVE,
               sleep=True, provider=dhan_quote, retry_count=3):
    master = json.loads(MASTER.read_text())
    instruments = master["instruments"]
    if len(instruments) != 29 or len({x["security_id"] for x in instruments}) != 29:
        raise RuntimeError("invalid Phase 1 29-stock master")
    day = day or datetime.now(IST).date()
    start = datetime(day.year, day.month, day.day, *start_time, tzinfo=IST)
    end = datetime(day.year, day.month, day.day, *end_time, tzinfo=IST)
    minute = start
    while minute < end:
        if sleep:
            while True:
                now = datetime.now(IST)
                if now >= minute:
                    break
                time.sleep(min(1.0, (minute - now).total_seconds()))
        last_error = None
        for attempt in range(retry_count):
            try:
                collect_minute(minute, instruments, provider)
                last_error = None
                break
            except Exception as error:
                last_error = error
                if attempt + 1 < retry_count:
                    time.sleep(2 ** attempt)
        if last_error is not None:
            missing = VAULT / f"{day.isoformat()}-missing.jsonl"
            with missing.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps({"official_minute": minute.isoformat(), "status": "MISSING", "reason": str(last_error)}) + "\n")
        minute += timedelta(minutes=1)
    return True


def run_session(day=None, sleep=True, provider=dhan_quote, retry_count=3):
    return run_window(day, SESSION_START, SESSION_END_EXCLUSIVE, sleep, provider, retry_count)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="09:15")
    parser.add_argument("--end", default="15:30")
    parser.add_argument("--date", default=None)
    args = parser.parse_args()
    try:
        day = datetime.strptime(args.date, "%Y-%m-%d").date() if args.date else None
        start = tuple(map(int, args.start.split(":")))
        end = tuple(map(int, args.end.split(":")))
        run_window(day, start, end)
    except Exception as exc:
        print(f"PHASE3 ERROR: {exc}", file=sys.stderr)
        raise
