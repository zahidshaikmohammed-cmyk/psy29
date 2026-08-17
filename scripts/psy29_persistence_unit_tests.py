#!/usr/bin/env python3
"""Offline tests for PSY29 durable persistence integration."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from psy29_persistent_store import enabled
from psy29_runtime_state import DEFAULT, load, save


def main() -> None:
    original = os.environ.pop("PSY29_DATABASE_URL", None)
    try:
        assert not enabled(), "DB must be optional for offline/CI runs"
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "runtime.json"
            state = save(path, {"status": "PASS", "last_cycle_id": "fixture-1"})
            assert state["status"] == "PASS"
            assert state["schema_version"] == 2
            restored = load(path)
            assert restored["status"] == "PASS"
            assert restored["last_cycle_id"] == "fixture-1"
            assert restored["persistence"] == "LOCAL_ONLY"
        print("PSY29 persistence unit tests: PASS")
    finally:
        if original is not None:
            os.environ["PSY29_DATABASE_URL"] = original


if __name__ == "__main__":
    main()
