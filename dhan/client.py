"""Minimal DhanHQ v2 HTTP client for PSY29 research."""

from __future__ import annotations

import os
import time
from typing import Any

import requests


BASE_URL = "https://api.dhan.co/v2"


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

        Non-transient 4xx errors are raised immediately. Network timeouts,
        429 rate-limit responses, 5xx responses, and Dhan transient server/network
        error codes are retried at most ``retries`` times.
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
                        delay = backoff_seconds * (2**attempt)
                        print(
                            f"Dhan transient failure; retrying in {delay:.1f}s "
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
                delay = backoff_seconds * (2**attempt)
                print(
                    f"Dhan network timeout/connection error; retrying in {delay:.1f}s "
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
                    delay = backoff_seconds * (2**attempt)
                    print(
                        f"Dhan HTTP {status}; retrying in {delay:.1f}s "
                        f"(attempt {attempt + 1}/{retries})",
                        flush=True,
                    )
                    time.sleep(delay)
                    continue
                raise

        if last_error:
            raise last_error
        raise RuntimeError("Dhan request failed without an exception")
