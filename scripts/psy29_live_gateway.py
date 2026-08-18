#!/usr/bin/env python3
"""PSY29 public live-data gateway.

This wrapper preserves the existing PSY29 acquisition worker and all existing
pipeline behavior. It only makes the DHAN live-data state directly readable
from the service root and stable stock-specific endpoints.
"""
from __future__ import annotations

import json
import os
import threading
from http.server import ThreadingHTTPServer
from urllib.parse import unquote, urlparse

import psy29_integrated_service as svc


class GatewayHandler(svc.Handler):
    """Expose the existing service plus an unambiguous live-data root payload."""

    def do_GET(self):
        path = urlparse(self.path).path

        if path in {"/", "/api/live", "/api/live-data"}:
            payload = svc.signal_data()
            payload["gateway"] = "PSY29_DHAN_LIVE_DATA_GATEWAY"
            payload["access_contract"] = {
                "provider": "DHAN",
                "market_hours_source": "/api/instrument/{SYMBOL}",
                "all_stocks_source": "/api/signals",
                "universe_source": "/api/universe",
                "freshness_required": "FRESH",
                "coverage_required": 29,
                "cache_control": "no-store",
            }
            return self._send(
                json.dumps(payload, separators=(",", ":")).encode(),
                "application/json; charset=utf-8",
            )

        if path.startswith("/api/live/"):
            symbol = unquote(path.rsplit("/", 1)[-1]).strip().upper()
            payload = svc.instrument(symbol)
            payload["gateway"] = "PSY29_DHAN_LIVE_DATA_GATEWAY"
            return self._send(
                json.dumps(payload, separators=(",", ":")).encode(),
                "application/json; charset=utf-8",
            )

        return super().do_GET()


if __name__ == "__main__":
    svc.save_runtime_state(
        svc.RUNTIME_STATE,
        {
            "status": svc.STATE.get("status", "STARTING"),
            "error": svc.STATE.get("error"),
            "last_cycle": svc.STATE.get("last_cycle"),
        },
    )
    threading.Thread(target=svc.worker, daemon=True).start()
    port = int(os.environ.get("PORT", "10000"))
    ThreadingHTTPServer(("0.0.0.0", port), GatewayHandler).serve_forever()
