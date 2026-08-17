import json
from pathlib import Path

EXPECTED = json.loads((Path(__file__).parent / "stock_universe.json").read_text())["symbols"]


def test_universe_is_exactly_29():
    assert len(EXPECTED) == 29
    assert len(set(EXPECTED)) == 29


def test_required_layers_are_declared():
    required = {"mapping", "raw", "candles", "indicators", "features", "persistence", "provenance", "minute_continuity"}
    manifest = json.loads((Path(__file__).parent / "completeness_contract.json").read_text())
    assert set(manifest["required_layers"]) == required


def test_all_layers_require_all_29_symbols():
    manifest = json.loads((Path(__file__).parent / "completeness_contract.json").read_text())
    assert manifest["minimum_symbol_coverage"] == 29
    for layer in manifest["required_layers"]:
        assert manifest["symbol_coverage_required"][layer] == 29


def test_closed_market_boundary_is_not_fabricated():
    manifest = json.loads((Path(__file__).parent / "completeness_contract.json").read_text())
    assert manifest["closed_market_policy"] == "do_not_fabricate_live_session_data"
