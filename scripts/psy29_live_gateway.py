#!/usr/bin/env python3
"""PSY29 public live-data gateway.

The gateway preserves the existing PSY29 acquisition worker and exposes both the
current pipeline state and the durable per-minute Neon archive. It is intended
as the Render web-service entrypoint.
"""
from __future__ import annotations

import json
import os
import threading
from http.server import ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

import psy29_integrated_service as svc
from psy29_live_archive import history as durable_history
from psy29_live_archive import latest_snapshot as durable_latest


class GatewayHandler(svc.Handler):
    """Expose the existing service plus durable DHAN live-data endpoints."""

    def _json(self, payload):
        return self._send(
            json.dumps(payload, separators=(",", ":")).encode(),
            "application/json; charset=utf-8",
        )

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/live-data":
            try:
                return self._send(
                    (svc.ROOT / "web" / "psy29_live_data.html").read_bytes(),
                    "text/html; charset=utf-8",
                )
            except Exception as exc:
                return self._json({"status": "FAIL", "error": str(exc)})

        if path in {"/", "/api/live", "/api/live-data"}:
            payload = svc.signal_data()
            try:
                latest = durable_latest(29)
                archive_status = {
                    "storage": "NEON_POSTGRES",
                    "rows_latest": len(latest),
                    "latest": latest,
                }
            except Exception as exc:
                archive_status = {
                    "storage": "NEON_POSTGRES",
                    "rows_latest": 0,
                    "error": str(exc),
                }
            payload["gateway"] = "PSY29_DHAN_LIVE_DATA_GATEWAY"
            payload["access_contract"] = {
                "provider": "DHAN",
                "market_hours_source": "/api/instrument/{SYMBOL}",
                "all_stocks_source": "/api/signals",
                "universe_source": "/api/universe",
                "durable_current_source": "/api/live-latest",
                "durable_history_source": "/api/live-history?date=YYYY-MM-DD&symbol=SYMBOL",
                "freshness_required": "FRESH",
                "coverage_required": 29,
                "archive_frequency": "ONE_SUCCESSFUL_CYCLE_PER_MINUTE",
                "archive_until": "NSE_SESSION_CLOSE_15:30_IST",
                "cache_control": "no-store",
            }
            payload["durable_archive"] = archive_status
            return self._json(payload)

        if path == "/api/live-latest":
            try:
                return self._json({"status": "PASS", "provider": "DHAN", "coverage": 29, "rows": durable_latest(29)})
            except Exception as exc:
                return self._json({"status": "FAIL", "provider": "DHAN", "coverage": 0, "error": str(exc)})

        if path == "/api/live-history":
            params = parse_qs(parsed.query)
            session_date = (params.get("date") or [""])[0].strip()
            symbol = (params.get("symbol") or [""])[0].strip().upper() or None
            if not session_date:
                return self._json({"status": "ERROR", "error": "date=YYYY-MM-DD is required"})
            try:
                rows = durable_history(session_date, symbol=symbol)
                return self._json({
                    "status": "PASS",
                    "provider": "DHAN",
                    "session_date": session_date,
                    "symbol": symbol,
                    "row_count": len(rows),
                    "rows": rows,
                })
            except Exception as exc:
                return self._json({"status": "FAIL", "provider": "DHAN", "session_date": session_date, "error": str(exc)})

        if path.startswith("/api/live/"):
            symbol = unquote(path.rsplit("/", 1)[-1]).strip().upper()
            payload = svc.instrument(symbol)
            payload["gateway"] = "PSY29_DHAN_LIVE_DATA_GATEWAY"
            try:
                payload["durable_history_today"] = durable_history(
                    str(svc.datetime.now(svc.IST).date()), symbol=symbol
                )
            except Exception as exc:
                payload["durable_history_error"] = str(exc)
            return self._json(payload)

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
