#!/usr/bin/env python3
"""Create an explicit deterministic PSY29 pipeline fixture for off-market validation.

This fixture is never presented as live/DHAN data and never enables signal
 generation or order execution. It validates the pipeline-input contract only.
"""
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_TIMESTAMP = "2026-01-02T10:00:00+05:30"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--universe", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    a = p.parse_args()

    universe = json.loads(a.universe.read_text(encoding="utf-8"))
    rows = universe.get("universe", [])
    symbols = [str(x["symbol"]).strip().upper() for x in rows]
    if len(symbols) != 29 or len(set(symbols)) != 29:
        raise ValueError("canonical universe must be exactly 29 unique symbols")

    a.output.mkdir(parents=True, exist_ok=True)
    path = a.output / "live_snapshot.csv"
    fields = [
        "symbol", "timestamp", "open", "high", "low", "close", "volume",
        "last_price", "vwap", "ema9", "ema20", "first15_high", "first15_low",
        "security_id", "exchange_segment", "freshness_status",
    ]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for rank, symbol in enumerate(symbols, start=1):
            base = 1000.0 + rank * 10.0
            writer.writerow({
                "symbol": symbol,
                "timestamp": FIXTURE_TIMESTAMP,
                "open": base,
                "high": base + 8.0,
                "low": base - 6.0,
                "close": base + 2.0,
                "volume": 100000 + rank * 1000,
                "last_price": base + 2.0,
                "vwap": base + 1.5,
                "ema9": base + 1.8,
                "ema20": base + 1.0,
                "first15_high": base + 5.0,
                "first15_low": base - 4.0,
                "security_id": f"FIXTURE-{rank:02d}",
                "exchange_segment": "NSE_EQ",
                "freshness_status": "FIXTURE",
            })

    validation = {
        "contract": "PSY29_DETERMINISTIC_PIPELINE_FIXTURE",
        "status": "PASS",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "source": "PSY29 deterministic fixture",
        "live_data": False,
        "provider": "DETERMINISTIC_FIXTURE",
        "coverage": {"expected": 29, "actual": 29, "unique": 29},
        "fixture_count": 29,
        "signal_generation": False,
        "order_execution": False,
    }
    (a.output / "live_acquisition_validation.json").write_text(json.dumps(validation, indent=2), encoding="utf-8")
    print(json.dumps(validation, indent=2))


if __name__ == "__main__":
    main()
