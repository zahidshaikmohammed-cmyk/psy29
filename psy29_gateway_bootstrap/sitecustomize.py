"""Startup hook that patches only the public PSY29 live-data interface."""
from __future__ import annotations

import builtins
import json
from urllib.parse import unquote, urlparse

_original_import = builtins.__import__
_patched = False


def _patch_service(module):
    global _patched
    if _patched:
        return
    base = module.Handler

    class GatewayHandler(base):
        def do_GET(self):
            path = urlparse(self.path).path
            if path in {"/", "/api/live", "/api/live-data"}:
                payload = module.signal_data()
                payload["gateway"] = "PSY29_DHAN_LIVE_DATA_GATEWAY"
                payload["access_contract"] = {
                    "provider": "DHAN",
                    "stock_endpoint": "/api/live/{SYMBOL}",
                    "stock_endpoint_alias": "/api/instrument/{SYMBOL}",
                    "all_stocks_endpoint": "/api/signals",
                    "universe_endpoint": "/api/universe",
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
                payload = module.instrument(symbol)
                payload["gateway"] = "PSY29_DHAN_LIVE_DATA_GATEWAY"
                return self._send(
                    json.dumps(payload, separators=(",", ":")).encode(),
                    "application/json; charset=utf-8",
                )
            return super().do_GET()

    module.Handler = GatewayHandler
    _patched = True


def _import(name, globals=None, locals=None, fromlist=(), level=0):
    module = _original_import(name, globals, locals, fromlist, level)
    if name == "psy29_integrated_service":
        try:
            _patch_service(module)
        except Exception:
            # Never block the trading/data service because the presentation-layer
            # gateway patch failed. The original service remains the fallback.
            pass
    return module


builtins.__import__ = _import
