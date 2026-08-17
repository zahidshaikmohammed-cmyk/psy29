from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from universe import STOCKS

MASTER_URL = "https://images.dhan.co/api-data/api-scrip-master.csv"
OUT = Path(__file__).resolve().parent / "instrument_master.json"


def fetch_master() -> tuple[bytes, str]:
    req = urllib.request.Request(MASTER_URL, headers={"User-Agent": "PSY29-29Stock-DataVault/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read()
    if not data:
        raise RuntimeError("DHAN instrument master returned empty data")
    return data, hashlib.sha256(data).hexdigest()


def _pick(row: dict, *names: str) -> str:
    for name in names:
        value = row.get(name)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def resolve(data: bytes) -> list[dict]:
    text = data.decode("utf-8-sig", errors="replace")
    rows = csv.DictReader(io.StringIO(text))
    result: dict[str, dict] = {}
    for row in rows:
        segment = _pick(row, "SEM_SEGMENT", "SEGMENT")
        exchange = _pick(row, "SEM_EXM_EXCH_ID", "EXCH_ID")
        instrument = _pick(row, "SEM_INSTRUMENT_NAME", "INSTRUMENT")
        symbol = _pick(row, "SEM_TRADING_SYMBOL", "SYMBOL_NAME", "SM_SYMBOL_NAME")
        security_id = _pick(row, "SEM_SMST_SECURITY_ID", "SECURITY_ID")
        underlying = _pick(row, "UNDERLYING_SYMBOL")
        if exchange != "NSE" or segment != "E" or instrument != "EQUITY":
            continue
        for candidate in (symbol, underlying):
            if candidate in STOCKS and candidate not in result:
                result[candidate] = {
                    "symbol": candidate,
                    "security_id": security_id,
                    "exchange_segment": "NSE_EQ",
                    "instrument_type": "EQUITY",
                    "exchange": exchange,
                }
    missing = [s for s in STOCKS if s not in result]
    invalid = [s for s, v in result.items() if not v["security_id"]]
    if missing:
        raise RuntimeError(f"Missing DHAN NSE_EQ instruments: {missing}")
    if invalid:
        raise RuntimeError(f"Missing Security IDs: {invalid}")
    if len(result) != 29 or len({v["security_id"] for v in result.values()}) != 29:
        raise RuntimeError("29/29 uniqueness check failed")
    return [result[s] for s in STOCKS]


def persist(records: list[dict], master_sha256: str) -> Path:
    payload = {
        "schema": "PSY29_29STOCK_INSTRUMENT_MASTER_V1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": MASTER_URL,
        "source_sha256": master_sha256,
        "universe_size": 29,
        "instruments": records,
    }
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return OUT


def verify_credentials() -> dict:
    token = os.getenv("DHAN_ACCESS_TOKEN", "").strip()
    client_id = os.getenv("DHAN_CLIENT_ID", "").strip()
    if not token or not client_id:
        return {"verified": False, "reason": "DHAN_ACCESS_TOKEN/DHAN_CLIENT_ID not configured"}
    payload = json.loads(OUT.read_text(encoding="utf-8"))
    expected = {x["security_id"] for x in payload["instruments"]}
    body = json.dumps({"NSE_EQ": [int(x) for x in expected]}).encode()
    req = urllib.request.Request(
        "https://api.dhan.co/v2/marketfeed/ltp",
        data=body,
        method="POST",
        headers={"access-token": token, "client-id": client_id, "Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            response = json.loads(r.read().decode())
        returned = set(str(k) for k in response.get("data", {}).get("NSE_EQ", {}).keys())
        missing = sorted(expected - returned)
        if response.get("status") != "success" or missing:
            return {"verified": False, "response_status": response.get("status"), "missing_security_ids": missing}
        return {"verified": True, "response_status": response.get("status"), "verified_security_ids": 29}
    except Exception as e:
        return {"verified": False, "error": type(e).__name__}


if __name__ == "__main__":
    raw, digest = fetch_master()
    records = resolve(raw)
    path = persist(records, digest)
    print(f"29/29 instrument mappings persisted: {path}")
    print(json.dumps(verify_credentials(), indent=2))
