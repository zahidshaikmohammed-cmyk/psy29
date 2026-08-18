#!/usr/bin/env python3
"""Crash-safe PSY29 runtime state stored only on the Render instance."""
from __future__ import annotations

import json, tempfile
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
    "persistence": "RENDER_LOCAL",
    "updated_at": None,
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load(path: Path) -> dict:
    """Load runtime state from Render-local storage only."""
    local = dict(DEFAULT)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("schema_version") in (1, 2):
            local.update(data)
    except Exception:
        pass
    local["persistence"] = "RENDER_LOCAL"
    return local


def save(path: Path, state: dict) -> dict:
    """Atomically save runtime state to Render-local storage."""
    path.parent.mkdir(parents=True, exist_ok=True)
    out = dict(DEFAULT)
    out.update(state)
    out["persistence"] = "RENDER_LOCAL"
    out["updated_at"] = utc_now()

    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with open(fd, "w", encoding="utf-8", closefd=True) as handle:
            json.dump(out, handle, indent=2, sort_keys=True)
            handle.flush()
        Path(tmp).replace(path)
        return out
    finally:
        try:
            Path(tmp).unlink()
        except FileNotFoundError:
            pass
