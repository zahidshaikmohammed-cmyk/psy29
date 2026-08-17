# PHASE 5 — INDICATOR ENGINE

Status: COMPLETE
Branch: `phase5/indicator-engine-impl2`
Verification: GitHub Actions run `32037276820` — PASS

## Locked checklist

- [x] Master indicator matrix completed
- [x] VWAP
- [x] EMA9
- [x] EMA20
- [x] All additional required indicators — none additionally named in the audited 29-stock specialist contracts
- [x] Indicator formulas locked
- [x] Completed-candle rule enforced
- [x] Indicator timestamps preserved
- [x] Indicator accuracy tests passed
- [x] 29/29 indicator requirements satisfied

## Formula lock

VWAP = cumulative typical-price × volume / cumulative volume, using `(high + low + close) / 3` and the canonical intraday session stream.

EMA9 and EMA20 use standard EMA alpha `2 / (period + 1)` with the initial seed equal to the SMA of the first period closes.

## Scope lock

The audited specialist contracts explicitly require VWAP, EMA9 and EMA20. Volatility, range expansion, momentum, opening-range measurements, breakout/retest behaviour and structural events are derived features rather than additional named indicators; they remain outside Phase 5.

## Data integrity lock

Only Phase 4 canonical candles with `complete=true` are eligible. Indicator timestamps equal the source candle timestamps. No indicator value is generated from incomplete candles.
