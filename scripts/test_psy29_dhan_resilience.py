#!/usr/bin/env python3
"""Offline regression tests for DHAN retry and pipeline completeness gates."""
from __future__ import annotations

import csv
import json
import sys
import tempfile
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import dhan.client as dhan_client  # noqa: E402
from scripts import psy29_live_pipeline_bridge as bridge  # noqa: E402


class FakeResponse:
    def __init__(self, status_code: int, headers: dict[str, str] | None = None, payload=None):
        self.status_code = status_code
        self.headers = headers or {}
        self._payload = payload if payload is not None else {"status": "success"}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}", response=self)

    def json(self):
        return self._payload


def test_429_retry_after(monkeypatch) -> None:
    responses = [FakeResponse(429, {"Retry-After": "2"}), FakeResponse(200)]
    sleeps: list[float] = []

    def fake_post(*args, **kwargs):
        return responses.pop(0)

    monkeypatch.setattr(dhan_client.requests, "post", fake_post)
    monkeypatch.setattr(dhan_client.time, "sleep", lambda delay: sleeps.append(delay))
    client = dhan_client.DhanClient(access_token="test-token")
    result = client.post("/charts/intraday", {}, retries=2, backoff_seconds=1)

    assert result["status"] == "success"
    assert sleeps == [2.0], sleeps


def test_429_retry_is_bounded(monkeypatch) -> None:
    responses = [FakeResponse(429), FakeResponse(429), FakeResponse(200)]
    sleeps: list[float] = []

    def fake_post(*args, **kwargs):
        return responses.pop(0)

    monkeypatch.setattr(dhan_client.requests, "post", fake_post)
    monkeypatch.setattr(dhan_client.time, "sleep", lambda delay: sleeps.append(delay))
    monkeypatch.setattr(dhan_client, "_backoff", lambda attempt, base: 0.5 * (attempt + 1))
    client = dhan_client.DhanClient(access_token="test-token")
    result = client.post("/charts/intraday", {}, retries=2, backoff_seconds=1)

    assert result["status"] == "success"
    assert sleeps == [0.5, 1.0], sleeps


def test_pipeline_bridge_rejects_incomplete_coverage() -> None:
    required = sorted(bridge.REQUIRED_STAGE11_LIVE)
    symbols = [f"S{i:02d}" for i in range(28)]
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        snapshot = root / "execution_snapshot.csv"
        validation = root / "validation.json"
        universe = root / "universe.json"
        output = root / "out"

        rows = []
        for symbol in symbols:
            row = {field: "1" for field in required}
            row["symbol"] = symbol
            row["timestamp"] = "2026-08-17T09:30:00Z"
            row["freshness_status"] = "FRESH"
            rows.append(row)
        with snapshot.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=required + ["freshness_status"])
            writer.writeheader()
            writer.writerows(rows)

        validation.write_text(json.dumps({
            "contract": "PSY29_LIVE_DHAN_ACQUISITION_VALIDATION",
            "status": "PASS",
            "provider": "DHAN",
        }), encoding="utf-8")
        universe.write_text(json.dumps({
            "universe": [{"symbol": f"S{i:02d}", "rank": i + 1} for i in range(29)]
        }), encoding="utf-8")

        argv = [
            "bridge", "--snapshot", str(snapshot), "--validation", str(validation),
            "--universe", str(universe), "--output", str(output), "--mode", "live",
        ]
        old = sys.argv
        sys.argv = argv
        try:
            try:
                bridge.main()
            except ValueError as exc:
                assert "29 rows" in str(exc), exc
            else:
                raise AssertionError("Completeness gate accepted a 28/29 snapshot")
        finally:
            sys.argv = old


def main() -> None:
    # Minimal monkeypatch fixture without pytest dependency.
    class MonkeyPatch:
        def __init__(self):
            self.originals = []

        def setattr(self, target, name, value):
            self.originals.append((target, name, getattr(target, name)))
            setattr(target, name, value)

        def undo(self):
            for target, name, value in reversed(self.originals):
                setattr(target, name, value)

    # Run the first two tests using the same assertions, but without requiring pytest.
    mp = MonkeyPatch()
    try:
        test_429_retry_after(mp)
    finally:
        mp.undo()
    mp = MonkeyPatch()
    try:
        test_429_retry_is_bounded(mp)
    finally:
        mp.undo()
    test_pipeline_bridge_rejects_incomplete_coverage()
    print("PSY29 DHAN RESILIENCE + COMPLETENESS: PASS")


if __name__ == "__main__":
    main()
