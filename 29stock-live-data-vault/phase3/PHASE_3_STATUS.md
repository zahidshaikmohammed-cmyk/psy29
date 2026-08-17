# PSY29 — PHASE 3 ONE-MINUTE COLLECTION ENGINE

**STATUS: COMPLETE — IMPLEMENTED AND VERIFIED**

## Completion checklist

- [x] Automatic 1-minute collection implemented
- [x] 09:15 IST start implemented
- [x] Market-close stop implemented (15:30 IST exclusive; final official minute 15:29)
- [x] Exactly one official snapshot per minute
- [x] Duplicate-minute protection
- [x] Missing-minute detection / explicit MISSING records
- [x] Retry/recovery handling
- [x] No fabricated data
- [x] Full-session collection test passed

## Session contract

- Trading-session collection window: 09:15–15:30 IST
- Official minute count: 375
- First official snapshot: 09:15
- Last official snapshot: 15:29
- 15:30 is the hard stop boundary; no 15:30 snapshot is generated.

## Runtime

The automatic collector is split into two GitHub Actions windows so the complete
6h15m NSE session is not dependent on a single runner exceeding its execution
limit:

1. 09:15–12:30 IST (`45 3 * * 1-5` UTC)
2. 12:30–15:30 IST (`0 7 * * 1-5` UTC)

Both windows use the verified DHAN Actions secrets already used by Phase 2.
Snapshots are persisted into `29stock-live-data-vault/phase3/snapshots/`.

## Data integrity

A snapshot is written only after DHAN returns all 29 instruments and every
instrument contains both `last_price` and a `depth` object. Provider timestamps
are retained inside the raw provider payload. A failed minute is never filled
with synthetic values; it is recorded as `MISSING` after retry exhaustion.

## Verification evidence

GitHub Actions workflow `PSY29 Phase 3 Verification` run #2 completed
successfully. The full-session test validates all 375 official minutes,
uniqueness/duplicate protection, missing-minute behavior, and retry recovery.
