"""Minimal DhanHQ v2 HTTP client for PSY29 research.

Credentials are read only from environment variables. Nothing in this module
should ever print or persist credentials.
"""

from __future__ import annotations

import os
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

    def post(self, path: str, payload: dict[str, Any], timeout: int = 30) -> dict[str, Any]:
        response = requests.post(
            f"{BASE_URL}{path}", headers=self.headers, json=payload, timeout=timeout
        )
        response.raise_for_status()
        data = response.json()
        if isinstance(data, dict) and data.get("status") == "failure":
            raise RuntimeError(data)
        return data
