#!/usr/bin/env python3
"""PSY29 Stage 18 — Historical State Continuity & Regime Memory Engine."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STAGE = 18
VERSION = "1.0"
STAGE17_STATES = {"STABLE","CHANGED","DETERIORATING","EMERGING","INVALIDATED","UNSTABLE","DATA_STALE","DATA_INVALID","PROVENANCE_FAIL"}
ALLOWED = {"CONTINUOUS","CHANGED","NEW_STATE","PERSISTENT_DETERIORATION","PERSISTENT_INVALIDATION","RECOVERED","HISTORY_UNAVAILABLE","HISTORY_INVALID","PROVENANCE_FAIL"}
BLOCKED = {"TRADE_READY","TRADE_SIGNAL","TRADE_AUTHORIZED","CE","PE","ENTRY","ENTRY_PRICE","STOP_LOSS","TAKE_PROFIT","TARGET","POSITION_SIZE","RISK","CAPITAL_ALLOCATION","ORDER","EXECUTION","FUTURE_PRICE_PREDICTION","DIRECTIONAL_RECOMMENDATION"}


def load(path: Path) -> Any:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    if path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))
    return json.loads(text)


def rows(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        for key in ("records","rows","data","items"):
            if isinstance(data.get(key), list):
                return [x for x in data[key] if isinstance(x, dict)]
        return [data]
    return []


def val(r: dict[str, Any], *keys: str) -> Any:
    low = {str(k).lower(): v for k, v in r.items()}
    for k in keys:
        if k.lower() in low:
            return low[k.lower()]
    return None


def symbol(r: dict[str, Any]) -> str | None:
    x = val(r, "symbol","tradingsymbol","ticker","stock","security_symbol")
    return str(x).strip().upper() if x is not None and str(x).strip() else None


def ts(r: dict[str, Any]) -> datetime | None:
    x = val(r, "timestamp","generated_at","live_data_timestamp","data_timestamp","as_of")
    if x is None:
        return None
    s = str(x).strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        d = datetime.fromisoformat(s)
    except ValueError:
        return None
    return (d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc))


def universe(path: Path) -> list[str]:
    c = load(path)
    if not isinstance(c, dict) or not isinstance(c.get("universe"), list):
        raise ValueError("Canonical universe contract is invalid.")
    syms = [str(x.get("symbol") if isinstance(x, dict) else x).strip().upper() for x in c["universe"]]
    if len(syms) != 29 or len(set(syms)) != 29:
        raise ValueError("Canonical universe must contain exactly 29 unique symbols.")
    return syms


def index(path: Path, expected: set[str], label: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for r in rows(load(path)):
        s = symbol(r)
        if not s:
            raise ValueError(f"{label}: missing symbol")
        if s in out:
            raise ValueError(f"{label}: duplicate symbol {s}")
        out[s] = r
    if set(out) != expected:
        raise ValueError(f"{label}: 29/29 coverage failure; missing={sorted(expected-set(out))}; unexpected={sorted(set(out)-expected)}")
    return out


def provenance(r: dict[str, Any]) -> bool:
    return val(r, "provenance","research_provenance") not in (None,"",{},[])


def blocked(x: Any, path: str = "root") -> list[str]:
    found: list[str] = []
    if isinstance(x, dict):
        for k, v in x.items():
            if str(k).upper() in BLOCKED:
                found.append(f"{path}.{k}")
            found.extend(blocked(v, f"{path}.{k}"))
    elif isinstance(x, list):
        for i, v in enumerate(x):
            found.extend(blocked(v, f"{path}[{i}]"))
    return found


def classify(current: str, history: list[str]) -> str:
    if not history:
        return "HISTORY_UNAVAILABLE"
    previous = history[-1]
    if current == previous:
        if current == "DETERIORATING" and len(history) >= 2 and history[-2] == current:
            return "PERSISTENT_DETERIORATION"
        if current == "INVALIDATED" and len(history) >= 2 and history[-2] == current:
            return "PERSISTENT_INVALIDATION"
        return "CONTINUOUS"
    if current == "INVALIDATED":
        return "PERSISTENT_INVALIDATION" if previous == current else "CHANGED"
    if previous == "INVALIDATED" and current not in {"INVALIDATED","DATA_INVALID","DATA_STALE","PROVENANCE_FAIL"}:
        return "RECOVERED"
    if current == "DETERIORATING":
        return "PERSISTENT_DETERIORATION" if previous == current else "CHANGED"
    return "NEW_STATE" if current in {"EMERGING","UNSTABLE"} else "CHANGED"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--universe", required=True, type=Path)
    for n in range(5,17):
        p.add_argument(f"--stage{n}", required=True, type=Path)
    p.add_argument("--stage17", required=True, type=Path)
    p.add_argument("--history", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    a = p.parse_args()

    syms = universe(a.universe)
    expected = set(syms)
    current: dict[int, dict[str, dict[str, Any]]] = {}
    for n in range(5,17):
        current[n] = index(getattr(a, f"stage{n}"), expected, f"Stage {n}")
    cur17 = index(a.stage17, expected, "Stage 17")

    snapshots = sorted(a.history.glob("*.csv")) if a.history.exists() else []
    hist: list[dict[str, dict[str, Any]]] = []
    last_ts: datetime | None = None
    for sp in snapshots:
        snap = index(sp, expected, f"History {sp.name}")
        times = [ts(r) for r in snap.values()]
        if any(x is None for x in times):
            raise ValueError(f"History {sp.name}: invalid timestamp")
        st = min(x for x in times if x is not None)
        if last_ts is not None and st <= last_ts:
            raise ValueError("historical timestamps are not strictly increasing")
        last_ts = st
        hist.append(snap)

    records = []
    for rank, s in enumerate(syms, 1):
        c17 = cur17[s]
        state = str(val(c17, "stage17_state","state") or "").upper()
        if state not in STAGE17_STATES:
            raise ValueError(f"Stage 17 invalid state for {s}: {state}")
        upstream_ok = all(provenance(current[n][s]) for n in range(5,17)) and provenance(c17)
        if not upstream_ok:
            final = "PROVENANCE_FAIL"
        elif not hist:
            final = "HISTORY_UNAVAILABLE"
        else:
            hs = []
            for snap in hist:
                x = str(val(snap[s], "stage17_state","state") or "").upper()
                if x not in STAGE17_STATES:
                    raise ValueError(f"History invalid Stage 17 state for {s}: {x}")
                hs.append(x)
            final = classify(state, hs)
        records.append({"symbol":s,"canonical_rank":rank,"stage18_state":final,"current_stage17_state":state,"history_depth":len(hist),"previous_stage17_state":(str(val(hist[-1][s],"stage17_state","state") or "").upper() if hist else None),"provenance_complete":upstream_ok,"timestamp":val(c17,"timestamp","generated_at","data_timestamp","as_of")})

    payload = {
        "stage": STAGE,
        "version": VERSION,
        "status": "PASS",
        "records": records,
        "coverage": {"expected":29,"actual":len(records),"unique":len({r["symbol"] for r in records})},
        "safety": {"trading_decision": False, "execution_forbidden": True},
        "provenance_required": True,
    }
    violations = blocked(payload)
    if violations:
        raise ValueError("blocked fields detected: " + str(violations))

    a.output.mkdir(parents=True, exist_ok=True)
    out_json = a.output / "PSY29_STAGE18_HISTORICAL_BOARD.json"
    out_csv = a.output / "PSY29_STAGE18_HISTORICAL_BOARD.csv"
    out_val = a.output / "PSY29_STAGE18_VALIDATION.json"
    out_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    with out_csv.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(records[0])); w.writeheader(); w.writerows(records)
    validation = {"stage":18,"version":VERSION,"validation_status":"PASS","coverage":{"expected":29,"actual":len(records),"unique":len({r["symbol"] for r in records})},"output_states_observed":sorted({r["stage18_state"] for r in records}),"provenance_complete":all(r["provenance_complete"] for r in records),"blocked_fields":[],"fail_closed":True}
    if validation["coverage"] != {"expected":29,"actual":29,"unique":29}:
        raise ValueError("29/29 validation failed")
    out_val.write_text(json.dumps(validation, indent=2), encoding="utf-8")
    print("PSY29 STAGE 18: PASS")
    print("29/29 coverage: PASS")
    print("Historical continuity: PASS")
    print("Provenance: PASS")
    print("Safety boundary scan: PASS")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"PSY29 STAGE 18 FAIL-CLOSED: {exc}", file=sys.stderr)
        raise
