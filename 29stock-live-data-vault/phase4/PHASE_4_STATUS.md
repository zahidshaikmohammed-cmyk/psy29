# PHASE 4 — CANONICAL CANDLE ENGINE

Status: COMPLETE
Branch: `phase3/one-minute-collection`
Verification: GitHub Actions — PASS

## Locked checklist

- [x] 1-minute candles
- [x] 5-minute candles
- [x] 15-minute candles
- [x] 1-hour candles
- [x] Daily candles
- [x] Weekly candles
- [x] Candle completion logic
- [x] OHLC integrity validation
- [x] Volume validation
- [x] Timestamp validation
- [x] Historical backfill
- [x] Candle persistence verified

## Canonical source rule

Phase 3 one-minute snapshots are retained as raw audit data. They are not used to fabricate OHLC or volume because a once-per-minute LTP/depth quote cannot reconstruct the true intraminute high, low, open or traded volume.

Canonical 1-minute OHLCV candles therefore come from DHAN's Historical Intraday API. Higher intraday timeframes are aggregated from those canonical 1-minute candles. Daily candles come from DHAN Historical Daily Data, and weekly candles are aggregated from canonical daily candles.

## Completion rule

A candle is persisted only with genuine OHLCV data. Completed 5m/15m candles require all constituent 1m bars. The final NSE 1-hour bucket (15:15–15:29) is explicitly marked `complete=false` rather than being silently treated as a full hour.

## Backfill rule

Intraday backfill is chunked to at most 90 calendar days per DHAN request. All returned OHLCV arrays must have matching lengths and pass integrity validation before persistence.

## Persistence rule

Candle files are append-only JSONL under `phase4/candles/`, keyed by symbol and timeframe. Duplicate timestamps are ignored, preventing duplicate candle persistence.
