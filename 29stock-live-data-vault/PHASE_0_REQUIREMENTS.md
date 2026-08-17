# PSY29 — 29-STOCK LIVE DATA VAULT
## PHASE 0 — REQUIREMENTS FREEZE

**Status: COMPLETE**
**System boundary:** Independent subsystem inside `psy29`, isolated on branch `phase0/29-stock-live-data-vault`.
**Existing PSY29 systems:** MUST NOT be modified, imported, or used as runtime dependencies.

## Purpose

Pure market-data acquisition and persistence for the 29-stock PSY29 universe.

The collector's only runtime responsibility:

DHAN market data → one official collection per minute → 09:15 IST through market close → persistent storage.

It does not generate signals, analyze markets, rank stocks, execute trades, or run specialist engines.

## Locked universe

Exactly 29 symbols:

NESTLEIND, VEDL, ICICIPRULI, KALYANKJIL, KOTAKBANK, BANDHANBNK, BANKBARODA, TITAN, INFY, DLF, TCS, MAXHEALTH, KFINTECH, PRESTIGE, BHEL, RBLBANK, HCLTECH, ICICIGI, HDFCLIFE, MARICO, LUPIN, COFORGE, TECHM, SWIGGY, PERSISTENT, OBEROIRLTY, SUPREMEIND, LAURUSLABS, AMBUJACEM.

## Collection boundary

- Frequency: exactly one official snapshot per minute.
- Session start: 09:15 IST.
- Session end: 15:30 IST for the NSE equity session.
- No 3-second acquisition loop.
- Every official snapshot is retained; historical snapshots are never overwritten.
- Collector does not interpret the data.

## Phase-0 audit result

The available specialist-engine material was audited for live-input requirements. Direct contract text was available for NESTLEIND, COFORGE, PERSISTENT, OBEROIRLTY, SUPREMEIND, SWIGGY, LAURUSLABS and AMBUJACEM. The audited contracts share the same live-input family:

- 1-minute candles/price data
- 5-minute candles/price data
- volume
- VWAP
- EMA9
- EMA20
- opening-range high/low
- previous-session levels
- current-session high/low
- volatility/range expansion
- breakout/retest context
- rejection context
- momentum persistence

The remaining 21 symbols are covered by the frozen universal 29-stock superset contract. No additional stock-specific raw-data or indicator requirement was established in the accessible project material. If a specialist engine later introduces a genuinely new data requirement, it requires a versioned data-contract change; it must not be silently added to the production collector.

## Frozen data contract

The authoritative Phase-0 contract is:

`29stock-live-data-vault/PHASE_0_DATA_CONTRACT_V1.json`

The authoritative 29-stock requirements matrix is:

`29stock-live-data-vault/PHASE_0_REQUIREMENTS_MATRIX.csv`

The contract separates:

1. DHAN-direct raw market data.
2. PSY29 deterministic derived data.
3. Specialist-engine interpretation, which is explicitly outside this collector.

## DHAN-direct data to pull/store

### Instrument identity

- Security ID
- symbol
- exchange segment
- instrument type

### Live quote

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
- day close where available
- previous close

### Canonical/historical candles

- 1-minute OHLCV
- 5-minute OHLCV
- 15-minute OHLCV
- 60-minute OHLCV
- daily OHLCV

### Depth

Market depth is retained as an optional raw-data capability and can be enabled without changing the collector's decision boundary. It is not required as a specialist-engine input by the Phase-0 audit.

### Options

Option-chain data is explicitly **NOT_REQUIRED by default** for this 29-stock equity collector. DHAN offers option-chain fields, but the Phase-0 audit found no requirement to pull them. This prevents unnecessary API calls, storage, and coupling.

## PSY29-derived data to calculate/store

From canonical stored candles:

- 5-minute / 15-minute / 1-hour aggregation when needed
- weekly OHLCV from daily data
- session VWAP
- EMA9
- EMA20
- session open/high/low/volume
- previous-session high/low/close
- opening-range high/low
- deterministic range/volatility measurements
- deterministic volume measurements

The collector must never calculate behavioral classifications such as trend, breakout quality, retest quality, rejection, momentum state, edge activation, or signal grade. Those remain specialist-engine responsibilities.

## Indicator integrity

- Indicators are calculated from canonical stored candles.
- Screenshot values are never used.
- External charting-platform values are never required.
- Closed-candle indicators use completed candles only.
- Every indicator retains timeframe, source candle timestamp, completion status, calculation timestamp, and calculation/version provenance.

## Data integrity requirements

The future collector must:

- preserve provider timestamp
- preserve collector timestamp
- preserve symbol/security identity
- detect duplicate minutes
- detect missing minutes
- reject future timestamps
- validate OHLC relationships
- validate volume
- preserve raw provenance
- never fabricate missing market values

## Phase-0 completion gate

- [x] 29-stock universe identified
- [x] pure acquisition-only boundary defined
- [x] one-minute collection requirement defined
- [x] 09:15–15:30 session defined
- [x] DHAN raw capabilities mapped
- [x] raw-data requirements frozen
- [x] timeframe requirements frozen
- [x] indicator requirements frozen
- [x] session-feature requirements frozen
- [x] derivative/option requirement resolved
- [x] DHAN-direct vs PSY29-derived mapping frozen
- [x] gaps/limitations documented
- [x] universal 29-stock data contract frozen
- [x] validation artifact created

## PHASE 0 RESULT

# COMPLETE

Phase 1 may now begin.
