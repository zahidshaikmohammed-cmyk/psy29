"""PSY29 startup hooks: live-data gateway + self-healing Dhan authentication."""
from __future__ import annotations

import base64
import builtins
import json
import os
import threading
import time
from pathlib import Path
from urllib.parse import unquote, urlparse

import requests

_original_import = builtins.__import__
_patched_service = False
_patched_dhan = False
_auth_lock = threading.Lock()
TOKEN_FILE = Path(os.environ.get("PSY29_RUNTIME_TOKEN_FILE", "runtime/live/DHAN_ACCESS_TOKEN_RUNTIME.json"))


def _jwt_exp(token):
    try:
        payload = token.split(".")[1] + "=" * (-len(token.split(".")[1]) % 4)
        return float(json.loads(base64.urlsafe_b64decode(payload).decode())["exp"])
    except Exception:
        return None


def _read_token():
    try:
        token = json.loads(TOKEN_FILE.read_text(encoding="utf-8")).get("access_token")
        return str(token) if token else None
    except Exception:
        return None


def _write_token(token):
    try:
        TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_FILE.write_text(json.dumps({"access_token": token, "updated_at": time.time()}), encoding="utf-8")
    except Exception:
        pass


def _renew(client, token):
    r = requests.post(
        "https://api.dhan.co/v2/RenewToken",
        headers={"access-token": token, "dhanClientId": str(client.client_id or os.environ.get("DHAN_CLIENT_ID", ""))},
        timeout=20,
    )
    r.raise_for_status()
    token = r.json().get("accessToken") or r.json().get("access_token")
    if not token:
        raise RuntimeError("Dhan RenewToken returned no accessToken")
    _write_token(str(token))
    return str(token)


def _totp_generate(client):
    secret = os.environ.get("DHAN_TOTP_SECRET")
    pin = os.environ.get("DHAN_PIN")
    client_id = str(client.client_id or os.environ.get("DHAN_CLIENT_ID", ""))
    if not (secret and pin and client_id):
        return None
    import pyotp
    code = pyotp.TOTP(secret).now()
    r = requests.post(
        "https://auth.dhan.co/app/generateAccessToken",
        params={"dhanClientId": client_id, "pin": pin, "totp": code},
        timeout=20,
    )
    r.raise_for_status()
    token = r.json().get("accessToken")
    if not token:
        raise RuntimeError("Dhan TOTP generation returned no accessToken")
    _write_token(str(token))
    return str(token)


def _recover(client, force=False):
    """Return True only when the client has a usable token.

    Forced recovery is used after DHAN rejects a request. In that case we must
    not claim success merely because the old token exists; otherwise the worker
    would retry the same invalid credential forever.
    """
    with _auth_lock:
        token = _read_token() or client.access_token
        exp = _jwt_exp(token) if token else None
        now = time.time()
        if token and not force and exp and exp > now + 7200:
            client.access_token = token
            return True
        if token and not force and exp and exp > now:
            try:
                client.access_token = _renew(client, token)
                return True
            except Exception:
                pass
        try:
            new_token = _totp_generate(client)
            if new_token:
                client.access_token = new_token
                return True
        except Exception as exc:
            print(f"PSY29 DHAN TOTP recovery failed: {exc}", flush=True)
        if token and not force:
            client.access_token = token
            return True
        return False


def _patch_dhan(module):
    global _patched_dhan
    if _patched_dhan or not hasattr(module, "DhanClient"):
        return
    original_init = module.DhanClient.__init__
    original_post = module.DhanClient.post

    def patched_init(self, client_id=None, access_token=None):
        original_init(self, client_id, access_token)
        _recover(self, force=False)

    def patched_post(self, path, payload, timeout=15, retries=2, backoff_seconds=1.0):
        try:
            return original_post(self, path, payload, timeout, retries, backoff_seconds)
        except RuntimeError as exc:
            message = str(exc)
            token_error = any(marker in message for marker in ("DH-906", "Invalid Token", "DHAN_HTTP_401", "DHAN_HTTP_403"))
            if token_error and _recover(self, force=True):
                print("PSY29 DHAN authentication recovered; retrying failed request once.", flush=True)
                return original_post(self, path, payload, timeout, retries, backoff_seconds)
            raise
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status in (400, 401, 403) and _recover(self, force=True):
                print("PSY29 DHAN authentication recovered; retrying failed request once.", flush=True)
                return original_post(self, path, payload, timeout, retries, backoff_seconds)
            raise

    module.DhanClient.__init__ = patched_init
    module.DhanClient.post = patched_post
    _patched_dhan = True


def _patch_service(module):
    global _patched_service
    if _patched_service:
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
                return self._send(json.dumps(payload, separators=(",", ":")).encode(), "application/json; charset=utf-8")
            if path.startswith("/api/live/"):
                symbol = unquote(path.rsplit("/", 1)[-1]).strip().upper()
                payload = module.instrument(symbol)
                payload["gateway"] = "PSY29_DHAN_LIVE_DATA_GATEWAY"
                return self._send(json.dumps(payload, separators=(",", ":")).encode(), "application/json; charset=utf-8")
            return super().do_GET()

    module.Handler = GatewayHandler
    _patched_service = True


def _import(name, globals=None, locals=None, fromlist=(), level=0):
    module = _original_import(name, globals, locals, fromlist, level)
    if name == "dhan.client":
        try:
            _patch_dhan(module)
        except Exception as exc:
            print(f"PSY29 DHAN patch failed: {exc}", flush=True)
    elif name == "psy29_integrated_service":
        try:
            _patch_service(module)
        except Exception:
            pass
    return module


builtins.__import__ = _import
