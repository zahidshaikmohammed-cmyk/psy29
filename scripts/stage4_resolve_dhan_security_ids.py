#!/usr/bin/env python3
"""PSY29 Stage 4: resolve the locked 29 symbols against Dhan's NSE equity master."""
from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
import pandas as pd
import requests

MASTER_URL = "https://images.dhan.co/api-data/api-scrip-master-detailed.csv"
UNIVERSE = Path("config/psy29_live_universe_contract.json")
OUT = Path("output/stage4")


def pick_symbol_column(df: pd.DataFrame) -> str:
    for col in ("UNDERLYING_SYMBOL", "SEM_TRADING_SYMBOL", "SYMBOL_NAME", "DISPLAY_NAME"):
        if col in df.columns:
            return col
    raise RuntimeError("Dhan master has no supported symbol column")


def main() -> None:
    contract = json.loads(UNIVERSE.read_text())
    symbols = [x["symbol"].upper().strip() for x in contract["universe"]]
    if len(symbols) != 29 or len(set(symbols)) != 29:
        raise RuntimeError("Canonical live universe is not exactly 29 unique symbols")

    response = requests.get(MASTER_URL, timeout=90)
    response.raise_for_status()
    master = pd.read_csv(StringIO(response.text), low_memory=False)

    required = {"EXCH_ID", "SEGMENT"}
    missing = required - set(master.columns)
    if missing:
        raise RuntimeError(f"Dhan master missing required columns: {sorted(missing)}")

    sym_col = pick_symbol_column(master)
    nse_eq = master[(master["EXCH_ID"] == "NSE") & (master["SEGMENT"] == "E")].copy()
    nse_eq["_symbol"] = nse_eq[sym_col].astype(str).str.upper().str.strip()

    id_col = next((c for c in ("SECURITY_ID", "SECURITYID") if c in nse_eq.columns), None)
    if not id_col:
        raise RuntimeError("Dhan master has no security ID column")
    nse_eq["_security_id"] = nse_eq[id_col].astype(str).str.strip()

    rows = []
    failures = []
    for rank, symbol in enumerate(symbols, 1):
        matches = nse_eq[(nse_eq["_symbol"] == symbol) & (nse_eq["_security_id"] != "")]
        ids = sorted(set(matches["_security_id"].tolist()))
        if len(ids) != 1:
            failures.append({"rank": rank, "symbol": symbol, "match_count": len(ids), "security_ids": ids})
            continue
        rows.append({
            "rank": rank,
            "symbol": symbol,
            "exchange_segment": "NSE_EQ",
            "security_id": ids[0],
            "instrument": "EQUITY",
            "source": "Dhan detailed instrument master",
        })

    OUT.mkdir(parents=True, exist_ok=True)
    result = {
        "contract": "PSY29_DHAN_SECURITY_ID_MAP",
        "version": "1.0",
        "status": "PASS" if len(rows) == 29 and not failures and len({r['security_id'] for r in rows}) == 29 else "FAIL",
        "canonical_count": 29,
        "resolved_count": len(rows),
        "unique_security_id_count": len({r['security_id'] for r in rows}),
        "symbol_column": sym_col,
        "failures": failures,
        "mapping": rows,
    }
    (OUT / "psy29_dhan_security_id_map.json").write_text(json.dumps(result, indent=2))
    pd.DataFrame(rows).to_csv(OUT / "psy29_dhan_security_id_map.csv", index=False)
    (OUT / "stage4_verification.json").write_text(json.dumps({
        "status": result["status"],
        "canonical_count": 29,
        "resolved_count": len(rows),
        "unique_security_id_count": result["unique_security_id_count"],
        "failures": failures,
        "exact_29_unique_nse_equity_ids": result["status"] == "PASS",
    }, indent=2))
    print(json.dumps(result, indent=2))
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
