# PSY29 — 29-STOCK LIVE DATA VAULT
## PHASE 0 — REQUIREMENTS FREEZE

**Status:** IN PROGRESS
**System boundary:** Independent subsystem inside `psy29`, isolated on branch `phase0/29-stock-live-data-vault`.
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

The research artifact independently confirms a 29-symbol universe and the exact symbol list above.

## Collection boundary

- Frequency: exactly one official snapshot per minute.
- Session start: 09:15 IST.
- Session end: intended market-close boundary; current PSY29 convention is 15:30 IST and must be verified against the intended market calendar before production lock.
- No 3-second acquisition loop.
- Every official snapshot is retained; historical snapshots are never overwritten.
- Collector does not interpret the data.

## Specialist-engine audit status

**Verified engine-contract evidence currently retrieved:** NESTLEIND, COFORGE, PERSISTENT, OBEROIRLTY, SUPREMEIND, SWIGGY, LAURUSLABS, AMBUJACEM.

Across these verified contracts, the live-data section consistently requests/prefer:

- 1-minute candles/price data
- 5-minute candles/price data
- volume
- VWAP
- EMA9
- EMA20
- opening-range high
- opening-range low
- previous-session levels/reference levels
- current-session high/low
- volatility/range expansion
- breakout/retest behaviour
- rejection behaviour
- momentum persistence

These are engine inputs. The new collector stores/provides them; it does not interpret them.

**Important:** Similarity across the audited contracts is evidence of a common minimum input set, but Phase 0 is NOT complete until all 29 current specialist contracts are directly audited for stock-specific requirements.

## Raw market data requirements

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
- day close where DHAN supplies it post-market
- previous close
- market depth where required

## DHAN capability verification

Verified against current DhanHQ v2 documentation.

### Live Market Feed / WebSocket

DHAN provides tick-by-tick WebSocket market data and supports Ticker, Quote and Full modes. Quote data includes LTP, last traded quantity, last trade time, average trade price, volume, total sell quantity, total buy quantity, day open, day high, day low and day close (post-market). Full mode additionally includes OI and 5-level market depth. DHAN documents up to 5,000 subscribed instruments per WebSocket connection.

### Historical candles

DHAN provides daily OHLCV and intraday OHLC/OI/volume at 1, 5, 15, 25 and 60-minute intervals. The historical API documents up to 5 years for intraday data and recommends storing data at the user's end.

### Market Quote

DHAN provides REST market-quote endpoints for snapshot-style LTP/OHLC/quote/depth data and supports bulk instrument requests. This is a reconciliation/fallback capability, not the primary continuous acquisition mechanism.

### Option Chain

DHAN provides real-time option-chain data including OI, Greeks, volume, LTP, best bid/ask and IV across strikes. The option-chain endpoint has a unique-request rate limit of one request every 3 seconds. Option-chain collection will be included only if the 29-engine audit proves it is required.

### Full Market Depth

DHAN separately offers 20-level and 200-level full market depth over WebSocket for NSE Equity and Derivatives. This will NOT be pulled merely because it exists; it must be justified by the Phase-0 engine requirement matrix and storage-cost/benefit assessment.

## Canonical price series

The data product must support:

- 1-minute OHLCV
- 5-minute OHLCV
- 15-minute OHLCV
- 1-hour OHLCV
- daily OHLCV
- weekly OHLCV derived deterministically from daily data if a direct DHAN weekly series is not available/required

The 1-minute series is the canonical intraday foundation. Higher intraday timeframes must not introduce inconsistent alternate price histories.

## Indicator requirements

Confirmed minimum indicator set from the audited specialist contracts:

- VWAP
- EMA9
- EMA20

Additional indicators remain **UNKNOWN — REQUIRES VERIFICATION** until all 29 specialist contracts are audited.

The collector must calculate derived indicators from canonical stored candles rather than depending on screenshot values or an external charting platform.

Indicator values must preserve source timeframe, source candle timestamp, completion status, calculation timestamp, and calculation/version provenance.

## Session / derived features

The collector must support deterministic derivation of any verified engine-required features, including:

- opening-range high/low
- previous-session reference levels
- current-session high/low
- volatility/range expansion
- other deterministic session features proven necessary by the 29-engine audit

Research statistics, event rates, behavioural DNA, and threshold tables are NOT automatically live-market fields. They remain separate research/configuration artifacts unless an engine contract explicitly requires a value from them.

## Derivatives / option-chain requirement

DHAN capability is confirmed, but the requirement for this new collector remains **PENDING**.

Do not pull option chains for all 29 stocks merely because DHAN offers them.

Phase 0 must determine exactly which engines require derivative data, which underlyings/expiries/strikes are required, and the minimum fields required.

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
- [x] 29-stock universe identified
- [x] pure acquisition-only system boundary defined
- [x] 1-minute collection requirement defined
- [x] 09:15-to-close collection window defined
- [x] DHAN raw-data capabilities verified
- [ ] all raw-data requirements are identified
- [ ] all timeframe requirements are identified
- [ ] all indicator requirements are identified
- [ ] all session-feature requirements are identified
- [ ] all derivative/option requirements are identified
- [ ] every requirement is mapped to DHAN-direct vs PSY29-derived
- [ ] gaps/limitations are documented
- [ ] universal 29-stock data contract is frozen

**Current Phase 0 result: IN PROGRESS.**

Do not proceed to Phase 1 until the remaining boxes pass.
