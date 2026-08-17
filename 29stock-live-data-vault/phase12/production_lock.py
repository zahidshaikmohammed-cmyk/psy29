from dataclasses import dataclass

LOCK_VERSION = "1.0"
SYMBOLS = (
    "NESTLEIND","VEDL","ICICIPRULI","KALYANKJIL","KOTAKBANK","BANDHANBNK",
    "BANKBARODA","TITAN","INFY","DLF","TCS","MAXHEALTH","KFINTECH",
    "PRESTIGE","BHEL","RBLBANK","HCLTECH","ICICIGI","HDFCLIFE","MARICO",
    "LUPIN","COFORGE","TECHM","SWIGGY","PERSISTENT","OBEROIRLTY",
    "SUPREMEIND","LAURUSLABS","AMBUJACEM",
)

@dataclass(frozen=True)
class ProductionContract:
    version: str = LOCK_VERSION
    symbols: tuple[str, ...] = SYMBOLS
    provider: str = "DHAN"
    frequency: str = "1-minute"
    session_start: str = "09:15 IST"
    session_end: str = "NSE market close"
    candle_methodology: str = "canonical completed-candle aggregation"
    indicator_methodology: str = "completed-candle indicators with locked formulas"
    storage: str = "Neon hot operational DB + verified permanent daily archive"
    failure_policy: str = "retry, isolate, preserve, audit; never fabricate"
    provenance_policy: str = "provider timestamp + source + symbol/security identity + audit trail"

CONTRACT = ProductionContract()


def validate_lock() -> None:
    assert len(CONTRACT.symbols) == 29
    assert len(set(CONTRACT.symbols)) == 29
    assert CONTRACT.provider == "DHAN"
    assert CONTRACT.frequency == "1-minute"
    assert CONTRACT.session_start == "09:15 IST"
    assert CONTRACT.candle_methodology
    assert CONTRACT.indicator_methodology
    assert CONTRACT.storage
    assert "never fabricate" in CONTRACT.failure_policy
    assert "provider timestamp" in CONTRACT.provenance_policy
