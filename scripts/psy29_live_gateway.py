#!/usr/bin/env python3
"""PSY29 public live-data gateway with minute-by-minute durable storage."""
from __future__ import annotations
import json, os, sys, threading, time, importlib.util
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse
from zoneinfo import ZoneInfo

# Render starts this file from /scripts. Put the repository root first so
# root-level archive modules are importable reliably in production.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import psy29_integrated_service as svc

try:
    from psy29_live_archive import history as durable_history
    from psy29_live_archive import latest as durable_latest
    from psy29_live_archive import stats as durable_stats
    from psy29_live_archive import store_rows
    ARCHIVE_AVAILABLE = True
    ARCHIVE_IMPORT_ERROR = None
except (ModuleNotFoundError, ImportError) as exc:
    ARCHIVE_AVAILABLE = False
    ARCHIVE_IMPORT_ERROR = repr(exc)
    def durable_history(*a, **k): raise RuntimeError("Durable archive module is unavailable")
    def durable_latest(*a, **k): raise RuntimeError("Durable archive module is unavailable")
    def durable_stats(*a, **k): raise RuntimeError("Durable archive module is unavailable")
    def store_rows(*a, **k): raise RuntimeError("Durable archive module is unavailable")

IST = ZoneInfo("Asia/Kolkata")

def _archive_live_pipeline():
    last_key = None
    print(f"PSY29 ARCHIVE INIT: available={ARCHIVE_AVAILABLE} import_error={ARCHIVE_IMPORT_ERROR}", flush=True)
    while True:
        try:
            now = datetime.now(IST)
            mins = now.hour * 60 + now.minute
            if now.weekday() < 5 and 555 <= mins <= 930 and ARCHIVE_AVAILABLE:
                payload = svc.signal_data()
                if payload.get("live_data") is True:
                    rows = []
                    for item in payload.get("instruments") or []:
                        data = item.get("data") or {}
                        ts = data.get("timestamp")
                        symbol = str(item.get("symbol") or "").upper()
                        if not ts or not symbol or str(data.get("freshness_status", "")).upper() != "FRESH":
                            continue
                        try:
                            parsed = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
                        except Exception:
                            continue
                        if parsed.tzinfo is None:
                            parsed = parsed.replace(tzinfo=timezone.utc)
                        rows.append({
                            "session_date": str(parsed.astimezone(IST).date()),
                            "minute_ts": parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
                            "symbol": symbol,
                            "provider": "DHAN",
                            "market_data_kind": "LIVE_DHAN_MINUTE_ARCHIVE",
                            "timestamp": str(ts),
                            **data,
                        })
                    if len(rows) == 29:
                        key = rows[0]["minute_ts"]
                        if key != last_key and len({r["minute_ts"] for r in rows}) == 1:
                            n = store_rows(rows)
                            last_key = key
                            print(f"PSY29 MINUTE ARCHIVE STORED {n}/29 @ {key}", flush=True)
        except Exception as exc:
            print(f"PSY29 MINUTE ARCHIVE: {exc!r}", flush=True)
        time.sleep(5)

def _preopen_worker():
    try:
        path = os.path.join(PROJECT_ROOT, "scripts", "psy29_preopen_minute_archive.py")
        spec = importlib.util.spec_from_file_location("psy29_preopen_minute_archive", path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        module.main()
    except Exception as exc:
        print(f"PSY29 PREOPEN ARCHIVE: {exc!r}", flush=True)

class GatewayHandler(svc.Handler):
    def _json(self, payload):
        return self._send(json.dumps(payload, separators=(",", ":")).encode(), "application/json; charset=utf-8")

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path in {"/", "/live-data"}:
            try:
                return self._send((svc.ROOT / "web" / "psy29_live_data.html").read_bytes(), "text/html; charset=utf-8")
            except Exception as exc:
                return self._json({"status": "FAIL", "error": str(exc)})
        if path in {"/api/live", "/api/live-data"}:
            payload = svc.signal_data()
            payload["gateway"] = "PSY29_DHAN_LIVE_DATA_GATEWAY"
            payload["durable_archive"] = {"available": ARCHIVE_AVAILABLE, "import_error": ARCHIVE_IMPORT_ERROR}
            if ARCHIVE_AVAILABLE:
                try:
                    payload["durable_archive"].update(durable_stats(str(datetime.now(IST).date())))
                except Exception as exc:
                    payload["durable_archive"]["error"] = str(exc)
            return self._json(payload)
        if path == "/api/live-latest":
            try:
                rows = durable_latest(str(datetime.now(IST).date()))
                return self._json({"status": "PASS", "provider": "DHAN", "coverage": len({r.get('symbol') for r in rows}), "rows": rows})
            except Exception as exc:
                return self._json({"status": "UNAVAILABLE", "provider": "DHAN", "error": str(exc)})
        if path == "/api/live-stats":
            try:
                return self._json({"status": "PASS", "provider": "DHAN", "session_date": str(datetime.now(IST).date()), "stats": durable_stats(str(datetime.now(IST).date()))})
            except Exception as exc:
                return self._json({"status": "UNAVAILABLE", "provider": "DHAN", "error": str(exc)})
        if path == "/api/live-history":
            params = parse_qs(parsed.query)
            session_date = (params.get("date") or [str(datetime.now(IST).date())])[0].strip()
            symbol = (params.get("symbol") or [""])[0].strip().upper() or None
            limit = int((params.get("limit") or ["10000"])[0])
            try:
                rows = durable_history(session_date, symbol=symbol, limit=min(max(limit, 1), 20000))
                return self._json({"status": "PASS", "provider": "DHAN", "session_date": session_date, "symbol": symbol, "row_count": len(rows), "rows": rows})
            except Exception as exc:
                return self._json({"status": "UNAVAILABLE", "provider": "DHAN", "session_date": session_date, "symbol": symbol, "error": str(exc)})
        if path.startswith("/api/live/"):
            return self._json(svc.instrument(unquote(path.rsplit("/", 1)[-1]).strip().upper()))
        return super().do_GET()

if __name__ == "__main__":
    svc.save_runtime_state(svc.RUNTIME_STATE, {"status": svc.STATE.get("status", "STARTING"), "error": svc.STATE.get("error"), "last_cycle": svc.STATE.get("last_cycle")})
    threading.Thread(target=svc.worker, daemon=True, name="psy29-signal-worker").start()
    threading.Thread(target=_archive_live_pipeline, daemon=True, name="psy29-minute-archive").start()
    threading.Thread(target=_preopen_worker, daemon=True, name="psy29-preopen-archive").start()
    port = int(os.environ.get("PORT", "10000"))
    ThreadingHTTPServer(("0.0.0.0", port), GatewayHandler).serve_forever()
