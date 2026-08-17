from production_lock import CONTRACT, validate_lock


def test_production_contract():
    validate_lock()
    assert CONTRACT.version == "1.0"
    assert len(CONTRACT.symbols) == 29
    assert CONTRACT.symbols[0] == "NESTLEIND"
    assert CONTRACT.symbols[-1] == "AMBUJACEM"
    assert CONTRACT.provider == "DHAN"
    assert CONTRACT.frequency == "1-minute"
    assert CONTRACT.session_start == "09:15 IST"
    assert CONTRACT.session_end == "NSE market close"


def test_safety_and_storage_contract():
    assert "Neon" in CONTRACT.storage
    assert "archive" in CONTRACT.storage
    assert "never fabricate" in CONTRACT.failure_policy
    assert "audit" in CONTRACT.failure_policy
    assert "provider timestamp" in CONTRACT.provenance_policy
