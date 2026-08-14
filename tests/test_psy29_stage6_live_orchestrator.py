from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import psy29_stage6_live_orchestrator as orch


class Stage6LiveOrchestratorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.manifest = self.root / "manifest.json"
        self.snapshot = self.root / "snapshot.csv"
        self.security_map = self.root / "security_map.json"
        self.stage6 = self.root / "stage6"
        self.symbols = [f"STOCK{i:02d}" for i in range(1, 30)]

        # Patch canonical universe so the tests exercise wrapper logic without
        # changing any production contract file.
        self.universe_patch = patch.object(orch, "canonical_symbols", return_value=self.symbols)
        self.universe_patch.start()

    def tearDown(self) -> None:
        self.universe_patch.stop()
        self.tmp.cleanup()

    def write_manifest(self, **overrides: object) -> None:
        data = {
            "status": "PASS",
            "mode": "live",
            "live_data": True,
            "provider": "DHAN",
            "fresh_count": 29,
            "fixture_count": 0,
            "source": "PSY29 execution_snapshot.csv",
            "contract": "PSY29_LIVE_DHAN_ACQUISITION_VALIDATION",
        }
        data.update(overrides)
        self.manifest.write_text(json.dumps(data))

    def write_snapshot(self) -> None:
        fields = sorted(orch.REQUIRED_SNAPSHOT_COLUMNS)
        with self.snapshot.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for i, symbol in enumerate(self.symbols, 1):
                writer.writerow({
                    "symbol": symbol,
                    "timestamp": f"2026-08-15T09:{15 + i // 60:02d}:{i % 60:02d}+05:30",
                    "last_price": "100",
                    "vwap": "99",
                    "ema9": "99",
                    "ema20": "98",
                    "first15_high": "101",
                    "first15_low": "98",
                })

    def write_security_map(self) -> None:
        mapping = [
            {"symbol": s, "security_id": str(1000 + i)}
            for i, s in enumerate(self.symbols, 1)
        ]
        self.security_map.write_text(json.dumps({
            "contract": "PSY29_DHAN_SECURITY_ID_MAP",
            "version": "1.0",
            "status": "PASS",
            "canonical_count": 29,
            "resolved_count": 29,
            "unique_security_id_count": 29,
            "mapping": mapping,
        }))

    def test_live_gate_rejects_fixture_manifest(self) -> None:
        self.write_manifest(mode="fixture", live_data=False, provider="fixture", fixture_count=29)
        with self.assertRaisesRegex(RuntimeError, "live provenance gate failed"):
            orch.require_live_manifest(self.manifest)

    def test_live_gate_rejects_missing_dhan_provenance(self) -> None:
        self.write_manifest(provider="fixture", fixture_count=0)
        with self.assertRaisesRegex(RuntimeError, "live provenance gate failed"):
            orch.require_live_manifest(self.manifest)

    def test_security_map_requires_exact_29(self) -> None:
        self.write_security_map()
        data = json.loads(self.security_map.read_text())
        data["mapping"] = data["mapping"][:-1]
        self.security_map.write_text(json.dumps(data))
        with self.assertRaisesRegex(RuntimeError, "expected 29"):
            orch.validate_security_map(self.security_map, self.symbols)

    def test_snapshot_preserves_source_timestamps(self) -> None:
        self.write_snapshot()
        rows, meta = orch.read_snapshot(self.snapshot, self.symbols)
        self.assertEqual(meta["row_count"], 29)
        self.assertEqual(rows[0]["timestamp"], "2026-08-15T09:15:01+05:30")
        self.assertEqual(rows[-1]["timestamp"], "2026-08-15T09:15:29+05:30")

    def test_wrapper_invokes_existing_stage6_only_after_live_gates(self) -> None:
        self.write_manifest()
        self.write_snapshot()
        self.write_security_map()
        summary = {
            "status": "PASS",
            "validation_status": "PASS",
            "fresh_count": 29,
            "stale_count": 0,
            "invalid_count": 0,
        }
        out_csv = self.stage6 / "PSY29_STAGE6_LIVE_REGIMES.csv"
        self.stage6.mkdir(parents=True)
        with out_csv.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["symbol"])
            writer.writeheader()
            for symbol in self.symbols:
                writer.writerow({"symbol": symbol})
        (self.stage6 / "stage6_summary.json").write_text(json.dumps(summary))

        with patch.object(orch, "invoke_stage6") as invoke:
            context = orch.run(self.manifest, self.snapshot, self.security_map, self.stage6)
            invoke.assert_called_once()

        context_data = json.loads(context.read_text())
        self.assertEqual(context_data["status"], "PASS")
        self.assertEqual(len(context_data["timestamps"]), 29)
        self.assertEqual(context_data["source"]["provider"], "DHAN")


if __name__ == "__main__":
    unittest.main()
