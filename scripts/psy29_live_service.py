#!/usr/bin/env python3
"""PSY29 production live service.

DHAN acquisition remains the live-data layer. Neon/PostgreSQL is an optional
persistent state layer; local atomic files remain the hot cache/fallback.
This service never generates signals and never places orders.
"""
from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, time as dtime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from zoneinfo import ZoneInfo

from psy29_live_dhan_acquisition import main as acquisition_main
from psy29_persistent_store import enabled as persistence_enabled, ensure_schema, sync_json_file, sync_stage17_history
from psy29_runtime_state import load as load_runtime_state, save as save_runtime_state

IST = ZoneInfo("Asia/Kolkata")
HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", "10000"))
INTERVAL_SECONDS = int(os.environ.get("PSY29_LIVE_INTERVAL_SECONDS", "60"))
UNIVERSE = os.environ.get("PSY29_UNIVERSE", "config/psy29_live_universe_contract.json")
OUTPUT = os.environ.get("PSY29_LIVE_OUTPUT", "output/live")
STATE = Path(OUTPUT) / "live_acquisition_validation.json"
RUNTIME_STATE = Path(OUTPUT) / "PSY29_RUNTIME_STATE.json"
HISTORY = Path("runtime/live/stage17_history")

RUN_LOCK = threading.Lock()
LAST_RUN = {"status": "NOT_RUN", "started_at": None, "finished_at": None, "error": None}
RUNTIME = load_runtime_state(RUNTIME_STATE)


def market_session() -> bool:
    now = datetime.now(IST)
    if now.weekday() >= 5:
        return False
    return dtime(9, 15) <= now.time() <= dtime(15, 30)


def persist_outputs() -> None:
    """Back up durable machine state without changing pipeline semantics."""
    if not persistence_enabled():
        return
    try:
        ensure_schema()
        sync_json_file("stage20_signal_memory", Path(OUTPUT) / "PSY29_STAGE20_SIGNAL_MEMORY.json")
        sync_json_file("stage20_final_board", Path(OUTPUT) / "PSY29_STAGE20_FINAL_SIGNAL_BOARD.json")
        sync_json_file("stage20_validation", Path(OUTPUT) / "PSY29_STAGE20_VALIDATION.json")
        sync_stage17_history(HISTORY)
    except Exception as exc:
        print(f"PSY29 persistence sync warning: {exc}", flush=True)


def save_runtime(**changes) -> None:
    RUNTIME.update(changes)
    RUNTIME.update({"market_session": market_session(), "database_configured": persistence_enabled()})
    saved = save_runtime_state(RUNTIME_STATE, RUNTIME)
    RUNTIME.clear(); RUNTIME.update(saved)


def run_once() -> None:
    if not market_session():
        return
    if not RUN_LOCK.acquire(blocking=False):
        return
    try:
        started = datetime.now(IST).isoformat()
        LAST_RUN.update(status="RUNNING", started_at=started, finished_at=None, error=None)
        save_runtime(status="RUNNING", last_cycle=started, error=None)
        import sys
        old = sys.argv
        try:
            sys.argv = ["psy29_live_dhan_acquisition.py", "--universe", UNIVERSE, "--output", OUTPUT]
            acquisition_main()
            LAST_RUN.update(status="PASS", finished_at=datetime.now(IST).isoformat())
            save_runtime(status="PASS", last_cycle=started, error=None)
            persist_outputs()
        finally:
            sys.argv = old
    except Exception as exc:
        LAST_RUN.update(status="FAIL", finished_at=datetime.now(IST).isoformat(), error=str(exc))
        save_runtime(status="FAIL", error=str(exc))
    finally:
        RUN_LOCK.release()


def worker() -> None:
    while True:
        try:
            run_once()
            persist_outputs()
        except Exception as exc:
            LAST_RUN.update(status="FAIL", finished_at=datetime.now(IST).isoformat(), error=str(exc))
            save_runtime(status="FAIL", error=str(exc))
        time.sleep(INTERVAL_SECONDS)


class Handler(BaseHTTPRequestHandler):
    def _json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path in ("/", "/health", "/healthz"):
            validation = None
            if STATE.exists():
                try:
                    validation = json.loads(STATE.read_text(encoding="utf-8"))
                except Exception:
                    validation = None
            self._json(200, {
                "service": "PSY29 Live Market Acquisition",
                "repository_only": True,
                "provider": "DHAN",
                "market_session": market_session(),
                "last_run": LAST_RUN,
                "runtime_state": RUNTIME,
                "persistence": {
                    "configured": persistence_enabled(),
                    "authoritative": persistence_enabled(),
                    "mode": RUNTIME.get("persistence", "LOCAL_ONLY"),
                },
                "validation": validation,
                "signal_generation": False,
                "order_execution": False,
            })
            return
        if self.path == "/live-validation":
            if not STATE.exists():
                self._json(404, {"status": "NO_SNAPSHOT"})
                return
            self._json(200, json.loads(STATE.read_text(encoding="utf-8")))
            return
        self._json(404, {"error": "not_found"})

    def log_message(self, fmt: str, *args) -> None:
        print("PSY29 HTTP", fmt % args)


def main() -> None:
    Path(OUTPUT).mkdir(parents=True, exist_ok=True)
    try:
        if persistence_enabled():
            ensure_schema()
    except Exception as exc:
        print(f"PSY29 durable persistence unavailable; local fallback active: {exc}", flush=True)
    save_runtime(status="STARTING")
    persist_outputs()
    threading.Thread(target=worker, name="psy29-live-worker", daemon=True).start()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"PSY29 live service listening on {HOST}:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
