#!/usr/bin/env python3
"""PSY29 production entrypoint with truthful persistence health telemetry.

The core integrated service remains unchanged. This wrapper reuses its worker,
state handling, routes, and Stage 6-20 pipeline while correcting the /health
persistence field so it reflects the actual runtime persistence mode.
"""
from __future__ import annotations

import json
import os
import threading
from http.server import ThreadingHTTPServer

import psy29_integrated_service as core
from psy29_runtime_state import load as load_runtime_state, save as save_runtime_state


class Handler(core.Handler):
    def do_GET(self):
        path = core.urlparse(self.path).path
        if path in {"/health", "/healthz"}:
            runtime = load_runtime_state(core.RUNTIME_STATE)
            healthy = runtime.get("status") in {"PASS", "RUNNING", "STARTING"}
            code = 200 if healthy else 503
            persistence = str(runtime.get("persistence", "LOCAL_ONLY"))
            durable = persistence == "NEON_POSTGRES"
            body = json.dumps(
                {
                    "status": "ok" if healthy else "degraded",
                    "service": "PSY29 LIVE MARKET",
                    "runtime_state": runtime,
                    "render_ephemeral_storage": True,
                    "durable_external_state": durable,
                    "persistence": persistence,
                    "database_configured": bool(os.environ.get("PSY29_DATABASE_URL")),
                },
                separators=(",", ":"),
            ).encode()
            return self._send(body, "application/json; charset=utf-8", code)
        return super().do_GET()


if __name__ == "__main__":
    core.save_runtime_state(
        core.RUNTIME_STATE,
        {
            "status": core.STATE.get("status", "STARTING"),
            "error": core.STATE.get("error"),
            "last_cycle": core.STATE.get("last_cycle"),
        },
    )
    threading.Thread(target=core.worker, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("PORT", "10000"))), Handler).serve_forever()
