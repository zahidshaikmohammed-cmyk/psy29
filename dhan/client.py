"""Minimal DhanHQ v2 HTTP client for PSY29 production live-data acquisition.

The client preserves Dhan's structured error payload and can regenerate a fresh
24-hour access token with the documented TOTP flow when the current token is
invalid or expired. No token value is ever written to logs.
"""
from __future__ import annotations

import os
import random
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import requests

BASE_URL = "https://api.dhan.co/v2"
AUTH_URL = "https://auth.dhan.co/app/generateAccessToken"
MAX_RETRY_AFTER_SECONDS = 30.0


def _retry_after_seconds(response: requests.Response | None) -> float | None:
    if response is None:
        return None
    value = response.headers.get("Retry-After")
    if not value:
        return None
    try:
        return max(0.0, min(float(value), MAX_RETRY_AFTER_SECONDS))
    except ValueError:
        try:
            target = parsedate_to_datetime(value)
            if target.tzinfo is None:
                target = target.replace(tzinfo=timezone.utc)
            delay = (target - datetime.now(timezone.utc)).total_seconds()
            return max(0.0, min(delay, MAX_RETRY_AFTER_SECONDS))
        except (TypeError, ValueError, OverflowError):
            return None


def _backoff(attempt: int, base: float) -> float:
    return base * (2**attempt) + random.uniform(0.0, min(0.25, base))


def _response_error(response: requests.Response | None) -> str:
    if response is None:
        return "DHAN_HTTP_UNKNOWN"
    try:
        body = response.json()
    except ValueError:
        body = response.text.strip()
    return f"DHAN_HTTP_{response.status_code}: {body}"


def _is_invalid_token(response: requests.Response | None, body: Any = None) -> bool:
    if response is not None and response.status_code in (401, 403):
        return True
    text = str(body if body is not None else "")
    return any(code in text for code in ("DH-901", "DH-906", "807", "808", "809", "Invalid Token", "expired"))


class DhanClient:
    def __init__(self, client_id: str | None = None, access_token: str | None = None):
        self.client_id = client_id or os.getenv("DHAN_CLIENT_ID")
        self.access_token = access_token or os.getenv("DHAN_ACCESS_TOKEN")
        self._last_auth_refresh = 0.0
        if not self.access_token:
            raise RuntimeError("DHAN_ACCESS_TOKEN is not configured")

    @property
    def headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "access-token": self.access_token or "",
        }
        if self.client_id:
            headers["client-id"] = self.client_id
        return headers

    def _generate_totp_token(self) -> str:
        """Generate a fresh Dhan access token using the documented TOTP flow."""
        client_id = self.client_id or os.getenv("DHAN_CLIENT_ID")
        pin = os.getenv("DHAN_PIN")
        secret = os.getenv("DHAN_TOTP_SECRET")
        if not client_id:
            raise RuntimeError("DHAN_CLIENT_ID is required for automatic token recovery")
        if not pin or not secret:
            raise RuntimeError(
                "DHAN token is invalid and automatic recovery is unavailable: "
                "configure DHAN_PIN and DHAN_TOTP_SECRET on Render"
            )
        try:
            import pyotp
        except ImportError as exc:
            raise RuntimeError("pyotp is required for automatic Dhan token recovery") from exc
        totp = pyotp.TOTP(secret).now()
        response = requests.post(
            AUTH_URL,
            params={"dhanClientId": client_id, "pin": pin, "totp": totp},
            timeout=20,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"DHAN_AUTH_HTTP_{response.status_code}: {response.text.strip()}")
        try:
            body = response.json()
        except ValueError as exc:
            raise RuntimeError("DHAN_AUTH_INVALID_RESPONSE") from exc
        token = body.get("accessToken")
        if not token:
            raise RuntimeError(f"DHAN_AUTH_NO_ACCESS_TOKEN: {body}")
        self.access_token = str(token)
        self._last_auth_refresh = time.time()
        print("PSY29 DHAN authentication: fresh 24-hour access token generated.", flush=True)
        return self.access_token

    def _recover_authentication(self) -> None:
        # Prevent a burst of 29 simultaneous refreshes. A single fresh token is
        # enough for all instruments in the current acquisition cycle.
        if time.time() - self._last_auth_refresh < 10:
            return
        self._generate_totp_token()

    def post(
        self,
        path: str,
        payload: dict[str, Any],
        timeout: int = 15,
        retries: int = 2,
        backoff_seconds: float = 1.0,
    ) -> dict[str, Any]:
        """POST to Dhan with retries and automatic invalid-token recovery."""
        auth_retried = False
        last_error: Exception | None = None

        for attempt in range(retries + 1):
            try:
                response = requests.post(
                    f"{BASE_URL}{path}",
                    headers=self.headers,
                    json=payload,
                    timeout=timeout,
                )

                if response.status_code >= 400:
                    try:
                        data = response.json()
                    except ValueError:
                        data = None

                    if _is_invalid_token(response, data):
                        if not auth_retried:
                            auth_retried = True
                            print("PSY29 DHAN authentication rejected; generating a fresh token and retrying.", flush=True)
                            self._recover_authentication()
                            continue
                        raise RuntimeError(_response_error(response))

                    if response.status_code == 429 or response.status_code >= 500:
                        response.raise_for_status()

                    if isinstance(data, dict) and data.get("status") == "failure":
                        text = str(data)
                        transient = any(code in text for code in ("805", "904", "908", "909"))
                        if transient and attempt < retries:
                            delay = _retry_after_seconds(response) or _backoff(attempt, backoff_seconds)
                            print(
                                f"Dhan transient failure; retrying in {delay:.2f}s "
                                f"(attempt {attempt + 1}/{retries}): {_response_error(response)}",
                                flush=True,
                            )
                            time.sleep(delay)
                            continue
                    raise RuntimeError(_response_error(response))

                data = response.json()
                if isinstance(data, dict) and data.get("status") == "failure":
                    if _is_invalid_token(response, data) and not auth_retried:
                        auth_retried = True
                        print("PSY29 DHAN authentication rejected; generating a fresh token and retrying.", flush=True)
                        self._recover_authentication()
                        continue
                    text = str(data)
                    transient = any(code in text for code in ("805", "904", "908", "909"))
                    if transient and attempt < retries:
                        delay = _retry_after_seconds(response) or _backoff(attempt, backoff_seconds)
                        print(
                            f"Dhan transient failure; retrying in {delay:.2f}s "
                            f"(attempt {attempt + 1}/{retries}): {data}",
                            flush=True,
                        )
                        time.sleep(delay)
                        continue
                    raise RuntimeError(f"DHAN_RESPONSE_FAILURE: {data}")

                if not isinstance(data, dict):
                    raise RuntimeError(f"DHAN_INVALID_RESPONSE: expected object, got {type(data).__name__}")
                return data

            except (requests.Timeout, requests.ConnectionError) as exc:
                last_error = exc
                if attempt >= retries:
                    raise
                delay = _backoff(attempt, backoff_seconds)
                print(
                    f"Dhan network error; retrying in {delay:.2f}s "
                    f"(attempt {attempt + 1}/{retries}): {exc}",
                    flush=True,
                )
                time.sleep(delay)

            except requests.HTTPError as exc:
                last_error = exc
                status = exc.response.status_code if exc.response is not None else None
                if status == 429 or (status is not None and status >= 500):
                    if attempt >= retries:
                        raise RuntimeError(_response_error(exc.response)) from exc
                    delay = _retry_after_seconds(exc.response) or _backoff(attempt, backoff_seconds)
                    print(
                        f"Dhan HTTP {status}; retrying in {delay:.2f}s "
                        f"(attempt {attempt + 1}/{retries})",
                        flush=True,
                    )
                    time.sleep(delay)
                    continue
                raise RuntimeError(_response_error(exc.response)) from exc

        if last_error:
            raise last_error
        raise RuntimeError("Dhan request failed without an exception")
