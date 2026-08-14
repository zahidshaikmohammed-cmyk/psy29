#!/usr/bin/env python3
"""PSY29 free Render live service.

Provides a tiny HTTP health/data surface for Render while a background worker
runs the PSY29-only DHAN acquisition during the NSE session.  This service is
an acquisition/runtime layer only: it never generates signals and never places
orders.
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

IST = ZoneInfo("Asia/Kolkata")
HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", "10000"))
INTERVAL_SECONDS = int(os.environ.get("PSY29_LIVE_INTERVAL_SECONDS", "60"))
UNIVERSE = os.environ.get("PSY29_UNIVERSE", "config/psy29_live_universe_contract.json")
OUTPUT = os.environ.get("PSY29_LIVE_OUTPUT", "output/live")
STATE = Path(OUTPUT) / "live_acquisition_validation.json"

RUN_LOCK = threading.Lock()
LAST_RUN = {"status": "NOT_RUN", "started_at": None, "finished_at": None, "error": None}


def market_session() -> bool:
    now = datetime.now(IST)
    if now.weekday() >= 5:
        return False
    return dtime(9, 15) <= now.time() <= dtime(15, 30)


def run_once() -> None:
    if not market_session():
        return
    if not RUN_LOCK.acquire(blocking=False):
        return
    try:
        started = datetime.now(IST).isoformat()
        LAST_RUN.update(status="RUNNING", started_at=started, finished_at=None, error=None)
        import sys
        old = sys.argv
        try:
            sys.argv = ["psy29_live_dhan_acquisition.py", "--universe", UNIVERSE, "--output", OUTPUT]
            acquisition_main()
            LAST_RUN.update(status="PASS", finished_at=datetime.now(IST).isoformat())
        finally:
            sys.argv = old
    except Exception as exc:
        LAST_RUN.update(status="FAIL", finished_at=datetime.now(IST).isoformat(), error=str(exc))
    finally:
        RUN_LOCK.release()


def worker() -> None:
    while True:
        try:
            run_once()
        except Exception as exc:
            LAST_RUN.update(status="FAIL", finished_at=datetime.now(IST).isoformat(), error=str(exc))
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
    threading.Thread(target=worker, name="psy29-live-worker", daemon=True).start()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"PSY29 live service listening on {HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
