#!/usr/bin/env python3
"""Crash-safe PSY29 runtime state with optional Neon durability.

Local atomic JSON is the hot cache. When PSY29_DATABASE_URL is configured,
Neon/PostgreSQL is the cross-restart/deploy authoritative copy.
"""
from __future__ import annotations

import json, os, tempfile
from datetime import datetime, timezone
from pathlib import Path

DEFAULT = {
    "schema_version": 2,
    "service": "PSY29 LIVE MARKET",
    "status": "STARTING",
    "error": None,
    "last_cycle": None,
    "last_cycle_id": None,
    "last_signal_count": 0,
    "last_history_depth": 0,
    "persistence": "LOCAL_ONLY",
    "updated_at": None,
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _db():
    try:
        from psy29_persistent_store import get_runtime_state, put_runtime_state
        return get_runtime_state, put_runtime_state
    except Exception:
        return None, None


def load(path: Path) -> dict:
    """Load DB state first, then local cache; never fail startup on DB outage."""
    local = dict(DEFAULT)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("schema_version") in (1, 2):
            local.update(data)
    except Exception:
        pass

    get_db, _ = _db()
    if os.environ.get("PSY29_DATABASE_URL") and get_db:
        try:
            durable = get_db()
            if isinstance(durable, dict):
                merged = dict(DEFAULT); merged.update(durable)
                merged["persistence"] = "NEON_POSTGRES"
                return merged
        except Exception:
            # Local cache remains a safe operational fallback.
            local["persistence"] = "LOCAL_FALLBACK_DB_UNAVAILABLE"
    return local


def save(path: Path, state: dict) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    out = dict(DEFAULT); out.update(state); out["updated_at"] = utc_now()
    get_db, put_db = _db()
    db_ok = False
    if os.environ.get("PSY29_DATABASE_URL") and put_db:
        try:
            db_ok = bool(put_db(out))
        except Exception:
            db_ok = False
    out["persistence"] = "NEON_POSTGRES" if db_ok else (
        "LOCAL_FALLBACK_DB_ERROR" if os.environ.get("PSY29_DATABASE_URL") else "LOCAL_ONLY"
    )

    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(out, handle, indent=2, sort_keys=True)
            handle.flush(); os.fsync(handle.fileno())
        os.replace(tmp, path)
        return out
    finally:
        try: os.unlink(tmp)
        except FileNotFoundError: pass
