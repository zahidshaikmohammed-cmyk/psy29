#!/usr/bin/env python3
"""Durable PSY29 persistence adapter.

Neon/PostgreSQL is authoritative when PSY29_DATABASE_URL is configured. The
existing local files remain the hot cache/fallback so the trading pipeline does
not become dependent on a network round-trip for every calculation.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

try:
    import psycopg
except ImportError:  # pragma: no cover - exercised by the dependency check
    psycopg = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS psy29_runtime_state (
    state_key TEXT PRIMARY KEY,
    state_json JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS psy29_artifacts (
    artifact_key TEXT PRIMARY KEY,
    artifact_json JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS psy29_stage17_history (
    history_key TEXT PRIMARY KEY,
    history_json JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""


def enabled() -> bool:
    return bool(os.environ.get("PSY29_DATABASE_URL")) and psycopg is not None


def _connect():
    if not enabled():
        return None
    return psycopg.connect(os.environ["PSY29_DATABASE_URL"], connect_timeout=10)


def ensure_schema() -> bool:
    """Create only PSY29-owned tables; never alter strategy tables."""
    if not enabled():
        return False
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(SCHEMA)
        conn.commit()
    return True


def put_runtime_state(state: dict[str, Any]) -> bool:
    if not enabled():
        return False
    ensure_schema()
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO psy29_runtime_state(state_key,state_json)
                   VALUES ('primary', %s::jsonb)
                   ON CONFLICT (state_key) DO UPDATE SET
                     state_json=EXCLUDED.state_json, updated_at=NOW()""",
                (json.dumps(state, separators=(",", ":")),),
            )
        conn.commit()
    return True


def get_runtime_state() -> dict[str, Any] | None:
    if not enabled():
        return None
    ensure_schema()
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT state_json FROM psy29_runtime_state WHERE state_key='primary'")
            row = cur.fetchone()
    return dict(row[0]) if row and isinstance(row[0], dict) else None


def put_artifact(key: str, value: Any) -> bool:
    if not enabled():
        return False
    ensure_schema()
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO psy29_artifacts(artifact_key,artifact_json)
                   VALUES (%s,%s::jsonb)
                   ON CONFLICT (artifact_key) DO UPDATE SET
                     artifact_json=EXCLUDED.artifact_json, updated_at=NOW()""",
                (key, json.dumps(value, separators=(",", ":"))),
            )
        conn.commit()
    return True


def get_artifact(key: str) -> Any | None:
    if not enabled():
        return None
    ensure_schema()
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT artifact_json FROM psy29_artifacts WHERE artifact_key=%s", (key,))
            row = cur.fetchone()
    return row[0] if row else None


def sync_json_file(key: str, path: Path) -> bool:
    if not path.exists():
        return False
    try:
        return put_artifact(key, json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError):
        return False


def restore_json_file(key: str, path: Path) -> bool:
    value = get_artifact(key)
    if value is None:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".dbtmp")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)
    return True


def sync_stage17_history(history_dir: Path) -> bool:
    if not enabled() or not history_dir.exists():
        return False
    records = []
    for path in sorted(history_dir.glob("*.csv")):
        try:
            records.append({"name": path.name, "csv": path.read_text(encoding="utf-8")})
        except OSError:
            continue
    return put_artifact("stage17_history", records) if records else False


def restore_stage17_history(history_dir: Path) -> bool:
    records = get_artifact("stage17_history")
    if not records or not isinstance(records, list):
        return False
    history_dir.mkdir(parents=True, exist_ok=True)
    for record in records:
        if not isinstance(record, dict) or not record.get("name") or not isinstance(record.get("csv"), str):
            continue
        name = Path(str(record["name"])).name
        if not name.endswith(".csv"):
            continue
        tmp = history_dir / (name + ".dbtmp")
        tmp.write_text(record["csv"], encoding="utf-8")
        os.replace(tmp, history_dir / name)
    return True
