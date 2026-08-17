"""Minimal DhanHQ v2 HTTP client for PSY29 research."""

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
    """Return a bounded Retry-After delay when the provider supplies one."""
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
    """Bounded exponential backoff with small jitter to avoid retry synchronization."""
    return base * (2**attempt) + random.uniform(0.0, min(0.25, base))


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
        """POST to Dhan with bounded retry/backoff for transient failures.

        429 rate limits honor the provider's Retry-After header when present.
        Network failures, 429s, 5xx responses, and Dhan transient server/network
        codes are retried only a bounded number of times. Non-transient 4xx
        responses fail immediately. A retry never turns partial data into a valid
        response: the caller must still enforce its own completeness contract.
        """
        last_error: Exception | None = None

        for attempt in range(retries + 1):
            try:
                response = requests.post(
                    f"{BASE_URL}{path}",
                    headers=self.headers,
                    json=payload,
                    timeout=timeout,
                )

                if response.status_code == 429 or response.status_code >= 500:
                    response.raise_for_status()

                response.raise_for_status()
                data = response.json()

                if isinstance(data, dict) and data.get("status") == "failure":
                    text = str(data)
                    transient = any(code in text for code in ("805", "908", "909"))
                    if transient and attempt < retries:
                        delay = _retry_after_seconds(response)
                        if delay is None:
                            delay = _backoff(attempt, backoff_seconds)
                        print(
                            f"Dhan transient failure; retrying in {delay:.2f}s "
                            f"(attempt {attempt + 1}/{retries})",
                            flush=True,
                        )
                        time.sleep(delay)
                        continue
                    raise RuntimeError(data)

                return data

            except (requests.Timeout, requests.ConnectionError) as exc:
                last_error = exc
                if attempt >= retries:
                    raise
                delay = _backoff(attempt, backoff_seconds)
                print(
                    f"Dhan network timeout/connection error; retrying in {delay:.2f}s "
                    f"(attempt {attempt + 1}/{retries})",
                    flush=True,
                )
                time.sleep(delay)

            except requests.HTTPError as exc:
                last_error = exc
                status = exc.response.status_code if exc.response is not None else None
                if status == 429 or (status is not None and status >= 500):
                    if attempt >= retries:
                        raise
                    delay = _retry_after_seconds(exc.response)
                    if delay is None:
                        delay = _backoff(attempt, backoff_seconds)
                    print(
                        f"Dhan HTTP {status}; retrying in {delay:.2f}s "
                        f"(attempt {attempt + 1}/{retries})",
                        flush=True,
                    )
                    time.sleep(delay)
                    continue
                raise

        if last_error:
            raise last_error
        raise RuntimeError("Dhan request failed without an exception")
