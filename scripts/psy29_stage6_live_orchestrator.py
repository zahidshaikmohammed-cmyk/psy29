#!/usr/bin/env python3
"""PSY29 live Stage 6 orchestration gate.

This wrapper deliberately leaves Stage 6 unchanged. It consumes only a bridge
manifest that proves the snapshot came from the real DHAN acquisition path,
resolves/validates the existing canonical 29-stock security-ID map, invokes the
existing Stage 6 engine, and publishes a small source-context sidecar only
after Stage 6 has passed all 29/29 gates.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
UNIVERSE = ROOT / "config/psy29_live_universe_contract.json"
PROFILES = ROOT / "config/psy29_edge_profiles_v1.json"
RESOLVER = ROOT / "scripts/stage4_resolve_dhan_security_ids.py"
STAGE6 = ROOT / "scripts/step9_live_regime_v2.py"
DEFAULT_OUT = ROOT / "runtime/live"
DEFAULT_STAGE6_OUT = DEFAULT_OUT / "stage6"
DEFAULT_MANIFEST = DEFAULT_OUT / "live_pipeline_input_validation.json"
DEFAULT_SNAPSHOT = DEFAULT_OUT / "live_pipeline_input.csv"
DEFAULT_SECURITY_MAP = ROOT / "output/stage4/psy29_dhan_security_id_map.json"

REQUIRED_MANIFEST = {"status":"PASS","mode":"live","live_data":True,"provider":"DHAN","fresh_count":29,"fixture_count":0}
REQUIRED_SNAPSHOT_COLUMNS = {"symbol","timestamp","last_price","vwap","ema9","ema20","first15_high","first15_low"}

def fail(message: str) -> None: raise RuntimeError(message)
def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file(): fail(f"missing required JSON: {path}")
    try: value = json.loads(path.read_text())
    except Exception as exc: fail(f"invalid JSON {path}: {exc}")
    if not isinstance(value, dict): fail(f"JSON object required: {path}")
    return value

def canonical_symbols() -> list[str]:
    symbols = [str(x["symbol"]).upper().strip() for x in load_json(UNIVERSE).get("universe", [])]
    if len(symbols) != 29 or len(set(symbols)) != 29: fail("canonical live universe is not exactly 29 unique symbols")
    return symbols

def require_live_manifest(path: Path) -> dict[str, Any]:
    manifest = load_json(path)
    for key, expected in REQUIRED_MANIFEST.items():
        if manifest.get(key) != expected: fail(f"live provenance gate failed: {key}={manifest.get(key)!r}, expected {expected!r}")
    return manifest

def read_snapshot(path: Path, symbols: list[str]) -> tuple[list[dict[str, str]], dict[str, Any]]:
    if not path.is_file(): fail(f"missing live snapshot: {path}")
    import csv
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle); fields = set(reader.fieldnames or []); missing = REQUIRED_SNAPSHOT_COLUMNS - fields
        if missing: fail(f"live snapshot missing Stage 6 fields: {sorted(missing)}")
        rows = list(reader)
    if len(rows) != 29: fail(f"live snapshot row count is {len(rows)}, expected 29")
    seen = [str(r.get("symbol","")).upper().strip() for r in rows]
    if len(set(seen)) != 29 or set(seen) != set(symbols): fail("live snapshot does not contain exactly the canonical 29 symbols")
    for row in rows:
        raw = str(row.get("timestamp","")).strip()
        if not raw: fail(f"missing source timestamp for {row.get('symbol')}")
        try: datetime.fromisoformat(raw.replace("Z","+00:00"))
        except ValueError: fail(f"invalid source timestamp for {row.get('symbol')}: {raw}")
    return rows, {"row_count":29,"symbols":seen}

def validate_security_map(path: Path, symbols: list[str]) -> dict[str, Any]:
    data = load_json(path); mapping = data.get("mapping")
    if not isinstance(mapping,list): fail("security map has no mapping list")
    if data.get("status") != "PASS": fail(f"security map status is not PASS: {data.get('status')!r}")
    if len(mapping) != 29: fail(f"security map contains {len(mapping)} rows, expected 29")
    map_symbols=[str(r.get("symbol","")).upper().strip() for r in mapping]; ids=[str(r.get("security_id","")).strip() for r in mapping]
    if len(set(map_symbols)) != 29 or set(map_symbols) != set(symbols): fail("security map does not cover exactly the canonical 29 symbols")
    if len(set(ids)) != 29 or any(not x for x in ids): fail("security map does not contain 29 unique non-empty security IDs")
    return data

def ensure_security_map(path: Path, symbols: list[str]) -> dict[str, Any]:
    if not path.is_file(): subprocess.run([sys.executable,str(RESOLVER)],cwd=ROOT,check=True,timeout=120)
    return validate_security_map(path,symbols)

def invoke_stage6(snapshot: Path, security_map: Path, output: Path) -> None:
    output.mkdir(parents=True,exist_ok=True)
    cmd=[sys.executable,str(STAGE6),"--universe",str(UNIVERSE),"--profiles",str(PROFILES),"--security-map",str(security_map),"--snapshot",str(snapshot),"--output",str(output)]
    print("PSY29 STAGE 6 INVOCATION:"," ".join(cmd),flush=True); subprocess.run(cmd,cwd=ROOT,check=True,timeout=240)

def validate_stage6_output(output: Path, symbols: list[str]) -> dict[str, Any]:
    summary=load_json(output/"stage6_summary.json"); csv_path=output/"PSY29_STAGE6_LIVE_REGIMES.csv"
    if summary.get("status") != "PASS" or summary.get("validation_status") != "PASS": fail("Stage 6 summary/validation status is not PASS")
    for key,expected in (("fresh_count",29),("stale_count",0),("invalid_count",0)):
        if summary.get(key) != expected: fail(f"Stage 6 {key}={summary.get(key)!r}, expected {expected!r}")
    if not csv_path.is_file(): fail(f"missing Stage 6 output: {csv_path}")
    import csv
    with csv_path.open(newline="") as handle: rows=list(csv.DictReader(handle))
    if len(rows)!=29: fail(f"Stage 6 output contains {len(rows)} rows, expected 29")
    out_symbols=[str(r.get("symbol","")).upper().strip() for r in rows]
    if len(set(out_symbols))!=29 or set(out_symbols)!=set(symbols): fail("Stage 6 output does not contain exactly the canonical 29 symbols")
    return summary

def write_context(output: Path, manifest: dict[str, Any], snapshot_rows: list[dict[str,str]], security_map: dict[str,Any], summary: dict[str,Any]) -> Path:
    context={"contract":"PSY29_STAGE6_LIVE_SOURCE_CONTEXT","version":"1.0","status":"PASS","source":{"provider":manifest.get("provider"),"mode":manifest.get("mode"),"live_data":manifest.get("live_data"),"fixture_count":manifest.get("fixture_count"),"source":manifest.get("source"),"validation_contract":manifest.get("contract")},"timestamps":[{"symbol":str(r["symbol"]).upper().strip(),"timestamp":str(r["timestamp"])} for r in snapshot_rows],"security_map":{"contract":security_map.get("contract"),"version":security_map.get("version"),"status":security_map.get("status"),"resolved_count":security_map.get("resolved_count"),"unique_security_id_count":security_map.get("unique_security_id_count")},"stage6":{"status":summary.get("status"),"validation_status":summary.get("validation_status"),"fresh_count":summary.get("fresh_count"),"stale_count":summary.get("stale_count"),"invalid_count":summary.get("invalid_count")}}
    path=output/"PSY29_STAGE6_LIVE_SOURCE_CONTEXT.json"; path.write_text(json.dumps(context,indent=2)+"\n"); return path

def run(manifest_path: Path, snapshot_path: Path, security_map_path: Path, stage6_output: Path) -> Path:
    symbols=canonical_symbols(); manifest=require_live_manifest(manifest_path); snapshot_rows,_=read_snapshot(snapshot_path,symbols); security_map=ensure_security_map(security_map_path,symbols); invoke_stage6(snapshot_path,security_map_path,stage6_output); summary=validate_stage6_output(stage6_output,symbols); return write_context(stage6_output,manifest,snapshot_rows,security_map,summary)

def main() -> None:
    parser=argparse.ArgumentParser(); parser.add_argument("--manifest",type=Path,default=DEFAULT_MANIFEST); parser.add_argument("--snapshot",type=Path,default=DEFAULT_SNAPSHOT); parser.add_argument("--security-map",type=Path,default=DEFAULT_SECURITY_MAP); parser.add_argument("--output",type=Path,default=DEFAULT_STAGE6_OUT); args=parser.parse_args()
    try: print(f"PSY29 STAGE 6 INTEGRATION: PASS ({run(args.manifest,args.snapshot,args.security_map,args.output)})",flush=True)
    except Exception as exc: print(f"PSY29 STAGE 6 INTEGRATION: FAIL — {exc}",file=sys.stderr,flush=True); raise SystemExit(1)

if __name__ == "__main__": main()
