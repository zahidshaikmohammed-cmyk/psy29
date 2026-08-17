import csv
import json
from pathlib import Path

ROOT = Path(__file__).parent
CONTRACT = json.loads((ROOT / "PHASE_0_DATA_CONTRACT_V1.json").read_text())
with (ROOT / "PHASE_0_REQUIREMENTS_MATRIX.csv").open(newline="") as f:
    rows = list(csv.DictReader(f))

assert CONTRACT["status"] == "PHASE_0_FROZEN"
assert CONTRACT["runtime_boundary"]["universe_size"] == 29
assert CONTRACT["runtime_boundary"]["official_collection_frequency_seconds"] == 60
assert CONTRACT["runtime_boundary"]["session_start"] == "09:15"
assert CONTRACT["runtime_boundary"]["session_end"] == "15:30"
assert CONTRACT["runtime_boundary"]["no_three_second_collection_loop"] is True
assert CONTRACT["runtime_boundary"]["no_signal_generation"] is True
assert CONTRACT["runtime_boundary"]["no_market_interpretation"] is True
assert CONTRACT["runtime_boundary"]["no_trade_execution"] is True
assert CONTRACT["runtime_boundary"]["no_specialist_engine_execution"] is True

universe = CONTRACT["universe"]
assert len(universe) == 29
assert len(set(universe)) == 29
assert len(rows) == 29
assert [r["stock"] for r in rows] == universe

required_indicators = set(CONTRACT["psy29_derived"]["indicators"])
assert required_indicators == {"session_vwap", "ema9", "ema20"}

for row in rows:
    assert row["1m_ohlcv"] == "REQUIRED"
    assert row["5m_ohlcv"] == "REQUIRED"
    assert row["volume"] == "REQUIRED"
    assert row["vwap"] == "REQUIRED"
    assert row["ema9"] == "REQUIRED"
    assert row["ema20"] == "REQUIRED"
    assert row["opening_range"] == "REQUIRED"
    assert row["option_chain"] == "NOT_REQUIRED"

for forbidden in CONTRACT["explicit_non_requirements"]:
    assert forbidden not in CONTRACT["dhann_direct"].get("live_quote", [])

print("PHASE 0 VALIDATION: PASS")
print("29-stock contract: PASS")
print("1-minute / 09:15-15:30 boundary: PASS")
print("indicator minimum: PASS")
print("no-signal/no-execution boundary: PASS")
print("option-chain default exclusion: PASS")
