#!/usr/bin/env python3
"""Crash-safe local runtime state for the PSY29 Render process.

The file is deliberately local and atomic. It survives a process restart while the
Render instance retains its filesystem, but it is not presented as cross-deploy
persistent storage. Durable cross-deploy storage requires a Render persistent disk,
Postgres, or Key Value service.
"""
from __future__ import annotations
import json, os, tempfile
from datetime import datetime, timezone
from pathlib import Path

DEFAULT = {
    "schema_version": 1,
    "service": "PSY29 LIVE MARKET",
    "status": "STARTING",
    "error": None,
    "last_cycle": None,
    "last_cycle_id": None,
    "last_signal_count": 0,
    "last_history_depth": 0,
    "updated_at": None,
}

def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

def load(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("schema_version") == 1:
            out = dict(DEFAULT); out.update(data); return out
    except Exception:
        pass
    return dict(DEFAULT)

def save(path: Path, state: dict) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    out = dict(DEFAULT); out.update(state); out["updated_at"] = utc_now()
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
