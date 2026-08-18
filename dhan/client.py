"""Minimal DhanHQ v2 HTTP client for PSY29 research/production.

The client deliberately preserves Dhan's complete error payload. A bare HTTP 400
is not actionable for a live-data service because Dhan returns the real cause in
JSON (for example invalid input, subscription/account, or data errors).
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


def _response_error(response: requests.Response) -> str:
    """Return Dhan's structured error plus HTTP status without leaking tokens."""
    try:
        body = response.json()
    except ValueError:
        body = response.text.strip()
    return f"DHAN_HTTP_{response.status_code}: {body}"


class DhanClient:
    def __init__(self, client_id: str | None = None, access_token: str | None = None):
        self.client_id = client_id or os.getenv("DHAN_CLIENT_ID")
        self.access_token = access_token or os.getenv("DHAN_ACCESS_TOKEN")
        if not self.access_token:
            raise RuntimeError("DHAN_ACCESS_TOKEN is not configured")

    @property
    def headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "access-token": self.access_token,
        }
        if self.client_id:
            headers["client-id"] = self.client_id
        return headers

    def post(
        self,
        path: str,
        payload: dict[str, Any],
        timeout: int = 15,
        retries: int = 2,
        backoff_seconds: float = 1.0,
    ) -> dict[str, Any]:
        """POST to Dhan with bounded retries and provider-aware diagnostics."""
        last_error: Exception | None = None

        for attempt in range(retries + 1):
            try:
                response = requests.post(
                    f"{BASE_URL}{path}",
                    headers=self.headers,
                    json=payload,
                    timeout=timeout,
                )

                # Always parse the body before raising. Dhan's HTTP 4xx response
                # contains the actionable error code/message.
                if response.status_code >= 400:
                    if response.status_code == 429 or response.status_code >= 500:
                        response.raise_for_status()
                    try:
                        data = response.json()
                    except ValueError:
                        data = None
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
                    raise RuntimeError(_response_error(response))

                data = response.json()
                if isinstance(data, dict) and data.get("status") == "failure":
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
