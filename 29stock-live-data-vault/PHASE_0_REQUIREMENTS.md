# PSY29 — 29-STOCK LIVE DATA VAULT
## PHASE 0 — REQUIREMENTS FREEZE

**Status:** IN PROGRESS
**System boundary:** Independent subsystem inside `psy29`.
**Existing PSY29 systems:** MUST NOT be modified, imported, or used as runtime dependencies.

## Purpose

Pure market-data acquisition and persistence for the 29-stock PSY29 universe.

The collector's only runtime responsibility is:

DHAN market data → one official collection per minute → 09:15 IST through market close → persistent storage.

It does not generate signals, analyze markets, rank stocks, execute trades, or run specialist engines.

## Locked universe

1. NESTLEIND
2. VEDL
3. ICICIPRULI
4. KALYANKJIL
5. KOTAKBANK
6. BANDHANBNK
7. BANKBARODA
8. TITAN
9. INFY
10. DLF
11. TCS
12. MAXHEALTH
13. KFINTECH
14. PRESTIGE
15. BHEL
16. RBLBANK
17. HCLTECH
18. ICICIGI
19. HDFCLIFE
20. MARICO
21. LUPIN
22. COFORGE
23. TECHM
24. SWIGGY
25. PERSISTENT
26. OBEROIRLTY
27. SUPREMEIND
28. LAURUSLABS
29. AMBUJACEM

## Collection boundary

- Frequency: exactly one official snapshot per minute.
- Session start: 09:15 IST.
- Session end: market close; current PSY29 convention is 15:30 IST and must be verified against the intended market calendar before production lock.
- No 3-second acquisition loop.
- Every official snapshot is retained; historical snapshots are never overwritten.
- Collector does not interpret the data.

## Requirements identified so far

### Raw market data

The collector must evaluate and, where required by the 29 engines, retain:

- DHAN Security ID
- exchange / segment
- symbol mapping
- provider timestamp
- collector timestamp
- LTP
- last traded quantity
- last trade time
- average traded price
- volume
- total buy quantity
- total sell quantity
- day open
- day high
- day low
- day close / previous close where available
- market depth where required

### Canonical price series

The data product must support:

- 1-minute OHLCV
- 5-minute OHLCV
- 15-minute OHLCV
- 1-hour OHLCV
- daily OHLCV
- weekly OHLCV derived deterministically from daily data if a direct DHAN weekly series is not available/required

### Confirmed specialist live-input requirements

The specialist-engine material retrieved so far explicitly requests or prefers:

- 1-minute price/candle data
- 5-minute price/candle data
- volume
- VWAP
- EMA9
- EMA20
- opening-range high
- opening-range low
- previous-session reference levels
- current-session high/low
- volatility / range expansion
- breakout/retest information
- rejection behaviour
- momentum persistence

These are inputs to the specialist engines, not decisions made by this collector.

### Derived data boundary

DHAN is the raw market-data source. PSY29 must calculate deterministic derived fields when DHAN does not directly provide the required field, including indicators and session features.

The exact indicator union is NOT YET LOCKED. It must be derived from a complete audit of all 29 specialist-engine contracts.

## Derivatives / option-chain requirement

DHAN provides option-chain fields including LTP, OI, previous OI, volume, previous volume, IV, Greeks, average price, bid/ask prices and quantities, and Security IDs. The collector will pull these only if the Phase-0 specialist-engine audit establishes that one or more of the 29 engines actually require them.

Do not pull optional derivative data merely because DHAN offers it.

## Data-quality requirements

The eventual collector must preserve enough metadata to validate:

- source/provider
- source timestamp
- collection timestamp
- symbol/security identity
- candle timestamp
- candle completion status
- freshness
- duplicate status
- missing data
- calculation/version provenance for derived indicators

No fabricated market values are permitted.

## Phase-0 gate

Phase 0 is COMPLETE only when:

- [ ] all 29 specialist-engine contracts have been audited
- [ ] all raw-data requirements are identified
- [ ] all timeframe requirements are identified
- [ ] all indicator requirements are identified
- [ ] all session-feature requirements are identified
- [ ] all derivative/option requirements are identified
- [ ] every requirement is mapped to DHAN-direct vs PSY29-derived
- [ ] gaps/limitations are documented
- [ ] the universal 29-stock data contract is frozen

Until all boxes pass, Phase 0 remains IN PROGRESS.
