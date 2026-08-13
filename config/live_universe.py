"""Canonical PSY29 live-universe contract.

This module is intentionally separate from the research discovery universe.
The live orchestrator consumes this locked 29-stock universe after research
selection has been verified.
"""

PSY29_LIVE_UNIVERSE_VERSION = "1.0"
PSY29_LIVE_UNIVERSE_SIZE = 29
PSY29_LIVE_UNIVERSE_SOURCE = "PSY29 Step 8 verified final selection"

PSY29_LIVE_SYMBOLS = [
    "NESTLEIND", "VEDL", "ICICIPRULI", "KALYANKJIL", "KOTAKBANK",
    "BANDHANBNK", "BANKBARODA", "TITAN", "INFY", "DLF", "TCS",
    "MAXHEALTH", "KFINTECH", "PRESTIGE", "BHEL", "RBLBANK", "HCLTECH",
    "ICICIGI", "HDFCLIFE", "MARICO", "LUPIN", "COFORGE", "TECHM",
    "SWIGGY", "PERSISTENT", "OBEROIRLTY", "SUPREMEIND", "LAURUSLABS",
    "AMBUJACEM",
]

if len(PSY29_LIVE_SYMBOLS) != PSY29_LIVE_UNIVERSE_SIZE:
    raise RuntimeError("PSY29 live-universe contract must contain exactly 29 symbols")
if len(set(PSY29_LIVE_SYMBOLS)) != PSY29_LIVE_UNIVERSE_SIZE:
    raise RuntimeError("PSY29 live-universe contract contains duplicate symbols")
