#!/usr/bin/env python3
"""Durable per-minute archive for the PSY29 live market pipeline.

Every successful live cycle writes the complete 29-row execution snapshot to
Neon/PostgreSQL. Render's local filesystem is only a cache; this database is the
cross-restart/cross-deploy source of truth for historical live observations.
"""
from __future__ import annotations

import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg

DATABASE_ENV = "PSY29_DATABASE_URL"
SCHEMA_VERSION = 1

def _database_url() -> str:
    value = os.environ.get(DATABASE_ENV, "").strip()
    if not value:
        raise RuntimeError(f"{DATABASE_ENV} is required for permanent live-data archival")
    return value

def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))

def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as fh:return list(csv.DictReader(fh))

def _ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))

def ensure_schema(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS psy29_live_market_minute (
                session_date date NOT NULL,
                cycle_timestamp timestamptz NOT NULL,
                candle_timestamp timestamptz NOT NULL,
                symbol text NOT NULL,
                security_id text NOT NULL,
                provider text NOT NULL,
                freshness_status text NOT NULL,
                payload jsonb NOT NULL,
                schema_version integer NOT NULL DEFAULT 1,
                created_at timestamptz NOT NULL DEFAULT now(),
                PRIMARY KEY (session_date, candle_timestamp, symbol)
            )
        """)
        cur.execute("""CREATE INDEX IF NOT EXISTS psy29_live_market_minute_symbol_ts ON psy29_live_market_minute (symbol, candle_timestamp DESC)""")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS psy29_live_cycles (
                cycle_timestamp timestamptz PRIMARY KEY,
                session_date date NOT NULL,
                coverage_expected integer NOT NULL,
                coverage_actual integer NOT NULL,
                validation jsonb NOT NULL,
                execution_snapshot jsonb NOT NULL,
                signal_board jsonb,
                schema_version integer NOT NULL DEFAULT 1,
                created_at timestamptz NOT NULL DEFAULT now()
            )
        """)
    conn.commit()

def archive_cycle(execution_path: Path, validation_path: Path, board_path: Path | None = None) -> dict[str, Any]:
    validation = _read_json(validation_path)
    if validation.get("status") != "PASS" or validation.get("live_data") is not True:raise RuntimeError("Permanent archive requires a PASS live DHAN validation")
    coverage = validation.get("coverage") or {}
    if coverage.get("expected") != 29 or coverage.get("actual") != 29 or coverage.get("unique") != 29:raise RuntimeError(f"Permanent archive requires 29/29/29 coverage: {coverage}")
    rows = _read_csv(execution_path)
    if len(rows) != 29 or len({str(r.get("symbol", "")).upper() for r in rows}) != 29:raise RuntimeError(f"Permanent archive requires exactly 29 unique execution rows; got {len(rows)}")
    if any(str(r.get("freshness_status", "")).upper() != "FRESH" for r in rows):raise RuntimeError("Permanent archive refuses non-FRESH rows")
    cycle_value=validation.get("timestamp") or validation.get("generated_at")
    if not cycle_value:raise RuntimeError("Live validation has no timestamp/generated_at for archival")
    cycle_timestamp=_ts(str(cycle_value));session_date=cycle_timestamp.astimezone(timezone.utc).date();board=_read_json(board_path) if board_path and board_path.exists() else None
    with psycopg.connect(_database_url(), connect_timeout=10) as conn:
        ensure_schema(conn)
        with conn.cursor() as cur:
            for row in rows:
                candle_timestamp=_ts(str(row["timestamp"]));payload=dict(row);payload["archive_schema_version"]=SCHEMA_VERSION
                cur.execute("""
                    INSERT INTO psy29_live_market_minute
                      (session_date, cycle_timestamp, candle_timestamp, symbol, security_id, provider, freshness_status, payload, schema_version)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (session_date, candle_timestamp, symbol) DO UPDATE SET
                      cycle_timestamp=EXCLUDED.cycle_timestamp, security_id=EXCLUDED.security_id,
                      provider=EXCLUDED.provider, freshness_status=EXCLUDED.freshness_status,
                      payload=EXCLUDED.payload, schema_version=EXCLUDED.schema_version
                """,(session_date,cycle_timestamp,candle_timestamp,str(row["symbol"]).strip().upper(),str(row["security_id"]),str(row.get("provider","DHAN")),str(row["freshness_status"]),json.dumps(payload),SCHEMA_VERSION))
            cur.execute("""
                INSERT INTO psy29_live_cycles
                  (cycle_timestamp, session_date, coverage_expected, coverage_actual, validation, execution_snapshot, signal_board, schema_version)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (cycle_timestamp) DO UPDATE SET
                  coverage_expected=EXCLUDED.coverage_expected, coverage_actual=EXCLUDED.coverage_actual,
                  validation=EXCLUDED.validation, execution_snapshot=EXCLUDED.execution_snapshot,
                  signal_board=EXCLUDED.signal_board, schema_version=EXCLUDED.schema_version
            """,(cycle_timestamp,session_date,int(coverage["expected"]),int(coverage["actual"]),json.dumps(validation),json.dumps(rows),json.dumps(board) if board is not None else None,SCHEMA_VERSION))
        conn.commit()
    return {"status":"PASS","provider":"DHAN","session_date":session_date.isoformat(),"cycle_timestamp":cycle_timestamp.isoformat().replace("+00:00","Z"),"rows_archived":len(rows),"storage":"NEON_POSTGRES","table":"psy29_live_market_minute","schema_version":SCHEMA_VERSION}

def latest_snapshot(limit: int = 29) -> list[dict[str, Any]]:
    with psycopg.connect(_database_url(), connect_timeout=10) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT ON (symbol) symbol, candle_timestamp, security_id, provider, freshness_status, payload
                FROM psy29_live_market_minute ORDER BY symbol, candle_timestamp DESC LIMIT %s
            """,(int(limit),))
            return [{"symbol":r[0],"candle_timestamp":r[1].isoformat().replace("+00:00","Z"),"security_id":r[2],"provider":r[3],"freshness_status":r[4],"data":r[5]} for r in cur.fetchall()]

def history(session_date: str, symbol: str | None = None, limit: int = 10000) -> list[dict[str, Any]]:
    with psycopg.connect(_database_url(), connect_timeout=10) as conn:
        with conn.cursor() as cur:
            if symbol:
                cur.execute("SELECT symbol,candle_timestamp,payload FROM psy29_live_market_minute WHERE session_date=%s AND symbol=%s ORDER BY candle_timestamp ASC LIMIT %s",(session_date,symbol.upper(),int(limit)))
            else:
                cur.execute("SELECT symbol,candle_timestamp,payload FROM psy29_live_market_minute WHERE session_date=%s ORDER BY candle_timestamp ASC,symbol ASC LIMIT %s",(session_date,int(limit)))
            return [{"symbol":r[0],"candle_timestamp":r[1].isoformat().replace("+00:00","Z"),"data":r[2]} for r in cur.fetchall()]

def main() -> None:
    import argparse
    p=argparse.ArgumentParser();p.add_argument("--execution",type=Path,required=True);p.add_argument("--validation",type=Path,required=True);p.add_argument("--board",type=Path);a=p.parse_args();print(json.dumps(archive_cycle(a.execution,a.validation,a.board),indent=2))
if __name__=="__main__":main()
