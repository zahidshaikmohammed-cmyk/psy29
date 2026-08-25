#!/usr/bin/env python3
"""PSY29 V4 machine-side retrieval/parse/validation/normalization boundary.

This module deliberately stops at a complete normalized dataset. It does not
implement or alter V4 trading, signal, grading, entry, stop, target or RR logic.
"""
from __future__ import annotations

import concurrent.futures
import json
import re
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any
from urllib.request import Request, urlopen

BASE = "https://raw.githubusercontent.com/zahidshaikmohammed-cmyk/psy29-live-data/main/live"
MASTER_URL = f"{BASE}/EXECUTION_MASTER.txt"
SYMBOLS = [
    "NESTLEIND","VEDL","ICICIPRULI","KALYANKJIL","KOTAKBANK","BANDHANBNK",
    "BANKBARODA","TITAN","INFY","DLF","TCS","MAXHEALTH","KFINTECH",
    "PRESTIGE","BHEL","RBLBANK","HCLTECH","ICICIGI","HDFCLIFE","MARICO",
    "LUPIN","COFORGE","TECHM","SWIGGY","PERSISTENT","OBEROIRLTY",
    "SUPREMEIND","LAURUSLABS","AMBUJACEM",
]

REQUIRED = {
    "SYMBOL", "TRADING_DATE", "SNAPSHOT_BUILT_AT_IST", "LIVE_LTP",
    "LIVE_LTP_FETCHED_AT_IST", "DATA_LAG_SECONDS", "SESSION_HIGH", "SESSION_LOW",
    "PREVIOUS_DAY_HIGH", "PREVIOUS_DAY_LOW", "PREVIOUS_DAY_CLOSE",
    "VWAP_1M", "VWAP_5M", "EMA9_1M", "EMA20_1M", "EMA9_5M", "EMA20_5M",
}

@dataclass
class StockResult:
    symbol: str
    fetch: str = "FAIL"
    parse: str = "FAIL"
    validate: str = "FAIL"
    fresh: str = "FAIL"
    complete: str = "FAIL"
    reason: str = ""
    data: dict[str, Any] | None = None


def fetch_text(url: str, timeout: int = 15) -> str:
    # Cache-control is explicit; query parameter prevents intermediary reuse.
    sep = "&" if "?" in url else "?"
    url = f"{url}{sep}_v4_fetch={time.time_ns()}"
    req = Request(url, headers={"Cache-Control": "no-cache", "Pragma": "no-cache"})
    with urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8")


def kv_parse(text: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for line in text.splitlines():
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip()
        if not k:
            continue
        try:
            out[k] = json.loads(v)
        except Exception:
            out[k] = v
    return out


def complete_payload(text: str, data: dict[str, Any]) -> bool:
    if not text.strip() or not data:
        return False
    if "PSY29_EXECUTION_SNAPSHOT" not in text:
        return False
    # A parser-complete payload must contain the canonical marker and required keys.
    return REQUIRED.issubset(data.keys())


def normalize(data: dict[str, Any]) -> dict[str, Any]:
    # Preserve every parsed field; add a stable envelope rather than discarding
    # candle/history fields that future V4 logic may require.
    return dict(data)


def validate(data: dict[str, Any], symbol: str, trading_date: str) -> tuple[bool, str, str]:
    if str(data.get("SYMBOL", "")).strip().upper() != symbol:
        return False, "symbol_mismatch", "FAIL"
    if str(data.get("TRADING_DATE", "")).strip() != trading_date:
        return False, "wrong_trading_date", "FAIL"
    missing = sorted(REQUIRED - data.keys())
    if missing:
        return False, "missing_required:" + ",".join(missing), "FAIL"
    if not str(data.get("LIVE_LTP_FETCHED_AT_IST", "")).strip():
        return False, "missing_live_ltp_timestamp", "FAIL"
    built = str(data.get("SNAPSHOT_BUILT_AT_IST", "")).strip()
    if not built or built[:10] != trading_date:
        return False, "wrong_snapshot_date", "FAIL"
    # Never substitute candle close for LTP; a missing/null LTP is a hard failure.
    if data.get("LIVE_LTP") in (None, "", "UNAVAILABLE"):
        return False, "missing_live_ltp", "FAIL"
    if data.get("DATA_LAG_SECONDS") in (None, ""):
        return False, "missing_data_lag", "FAIL"
    return True, "", "PASS"


def master_symbols(master: dict[str, Any]) -> list[str]:
    # Support common publication-list encodings without assuming a single one.
    for key in ("PUBLISHED_SYMBOLS", "PUBLISHED_STOCKS", "SYMBOLS", "STOCKS"):
        value = master.get(key)
        if isinstance(value, list):
            return [str(x).strip().upper() for x in value if str(x).strip()]
        if isinstance(value, str):
            return [x.strip().upper() for x in re.split(r"[,;|\s]+", value) if x.strip()]
    return []


def run(master_text: str | None = None, fetcher=fetch_text) -> dict[str, Any]:
    master_text = master_text if master_text is not None else fetcher(MASTER_URL)
    master = kv_parse(master_text)
    expected = int(master.get("EXPECTED_STOCKS", master.get("EXPECTED", 0)) or 0)
    published = int(master.get("PUBLISHED_STOCKS", master.get("PUBLISHED", 0)) or 0)
    failed = int(master.get("FAILED_STOCKS", master.get("FAILED", 0)) or 0)
    trading_date = str(master.get("TRADING_DATE", "")).strip()
    published_symbols = master_symbols(master)
    symbols = published_symbols if len(published_symbols) == published else SYMBOLS

    results: dict[str, StockResult] = {}
    def one(symbol: str) -> StockResult:
        r = StockResult(symbol)
        url = f"{BASE}/execution/{symbol}.txt"
        last_reason = "fetch_failed"
        for attempt in range(3):
            try:
                text = fetcher(url)
                r.fetch = "PASS"
                data = kv_parse(text)
                if not complete_payload(text, data):
                    last_reason = "payload_incomplete_or_missing_required_structure"
                    continue
                r.parse = "PASS"
                ok, reason, _ = validate(data, symbol, trading_date)
                if not ok:
                    last_reason = reason
                    continue
                r.validate = "PASS"
                r.fresh = "PASS"
                r.complete = "PASS"
                r.data = normalize(data)
                return r
            except Exception as exc:
                last_reason = f"{type(exc).__name__}:{exc}"
        r.reason = last_reason
        return r

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        for r in pool.map(one, symbols):
            results[r.symbol] = r

    validated = sum(r.validate == "PASS" for r in results.values())
    fetched = sum(r.fetch == "PASS" for r in results.values())
    parsed = sum(r.parse == "PASS" for r in results.values())
    failures = [s for s in symbols if results.get(s, StockResult(s)).validate != "PASS"]
    status = "COMPLETE" if (expected == published == fetched == parsed == validated == 29 and failed == 0) else "INCOMPLETE"
    return {
        "status": status,
        "trading_date": trading_date,
        "master_publication_time": master.get("MASTER_PUBLISHED_AT", master.get("MASTER_PUBLICATION_TIME")),
        "expected": expected,
        "published": published,
        "fetched": fetched,
        "parsed": parsed,
        "validated": validated,
        "failed": len(failures),
        "failed_symbols": failures,
        "master": master,
        "audit": [
            {k: v for k, v in asdict(results.get(s, StockResult(s))).items() if k != "data"}
            for s in symbols
        ],
        "stocks": {s: results[s].data for s in symbols if results[s].data is not None},
        "v4_analysis_permitted": status == "COMPLETE",
    }


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, ensure_ascii=False))
