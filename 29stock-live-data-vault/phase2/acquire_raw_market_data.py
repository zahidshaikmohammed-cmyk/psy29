import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MASTER = ROOT.parent / "phase1" / "instrument_master.json"
OUT = ROOT / "market-live.json"
URL = "https://api.dhan.co/v2/marketfeed/quote"


def dhan_quote(instruments):
    token = os.environ.get("DHAN_ACCESS_TOKEN")
    client_id = os.environ.get("DHAN_CLIENT_ID")
    if not token or not client_id:
        raise RuntimeError("DHAN_ACCESS_TOKEN and DHAN_CLIENT_ID are required")
    payload = json.dumps({"NSE_EQ": [int(x["security_id"]) for x in instruments]}).encode()
    req = urllib.request.Request(
        URL,
        data=payload,
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "access-token": token,
            "client-id": client_id,
            "User-Agent": "PSY29-Phase2/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        status = r.status
        body = json.loads(r.read().decode("utf-8"))
    if status != 200 or body.get("status") != "success":
        raise RuntimeError(f"DHAN market quote failed: http={status}, body={body}")
    return body


def main():
    master = json.loads(MASTER.read_text())
    instruments = master["instruments"]
    if len(instruments) != 29 or len({x["security_id"] for x in instruments}) != 29:
        raise RuntimeError("Phase 1 instrument master is not a verified 29-instrument universe")

    provider_request_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    body = dhan_quote(instruments)
    provider_response_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    rows = body.get("data", {}).get("NSE_EQ", {})
    if len(rows) != 29:
        raise RuntimeError(f"DHAN returned {len(rows)}/29 NSE_EQ instruments")

    by_id = {x["security_id"]: x["symbol"] for x in instruments}
    records = []
    for security_id, quote in rows.items():
        if security_id not in by_id:
            raise RuntimeError(f"Unexpected Security ID returned by DHAN: {security_id}")
        records.append({
            "symbol": by_id[security_id],
            "security_id": security_id,
            "exchange_segment": "NSE_EQ",
            "instrument_type": "EQUITY",
            "provider": "DHAN",
            "provider_data": quote,
        })
    records.sort(key=lambda x: instruments.index(next(i for i in instruments if i["security_id"] == x["security_id"])))

    missing_ltp = [r["symbol"] for r in records if "last_price" not in r["provider_data"]]
    missing_depth = [r["symbol"] for r in records if not isinstance(r["provider_data"].get("depth"), dict)]
    if missing_ltp or missing_depth:
        raise RuntimeError(f"Required data missing: ltp={missing_ltp}, depth={missing_depth}")

    out = {
        "schema": "PSY29_RAW_MARKET_DATA_V1",
        "generated_at": provider_request_at,
        "provider_response_at": provider_response_at,
        "provider": "DHAN",
        "endpoint": URL,
        "exchange_segment": "NSE_EQ",
        "instrument_type": "EQUITY",
        "universe_size": 29,
        "acquisition": {
            "connection": "REST_MARKET_QUOTE",
            "quote": True,
            "market_depth": True,
            "provider_timestamps_preserved": True,
        },
        "instruments": records,
    }
    OUT.write_text(json.dumps(out, indent=2) + "\n")
    print(f"29/29 raw market records persisted: {OUT}")
    print(json.dumps({"status": "success", "records": 29, "provider": "DHAN"}))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"PHASE2 ERROR: {exc}", file=sys.stderr)
        raise
