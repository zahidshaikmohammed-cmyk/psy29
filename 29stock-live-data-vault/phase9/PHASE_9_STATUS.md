# PSY29 PHASE 9 — DATA QUALITY & SAFETY

## Verification contract

This phase enforces rejection/isolation rather than repair-by-invention. Invalid or unavailable market data is never fabricated.

Market session note: implementation and deterministic safety tests are executable while the market is closed. A live-session freshness/acquisition smoke test must only be performed during market hours; the closed-market state is not treated as a live-data pass.

## Gates
- Freshness validation: implemented
- Future-timestamp rejection: implemented
- Duplicate detection: implemented
- Missing-data detection: implemented
- Invalid OHLC rejection: implemented
- Invalid volume rejection: implemented
- Wrong-security rejection: implemented
- Partial-stock isolation: implemented
- API failure handling: implemented with bounded retry/backoff and isolation
- Database failure handling: implemented with bounded retry/backoff and isolation
- No fabricated data: enforced by explicit missing outcome on failure
- Full audit/provenance trail: implemented for quality decisions

## Status
Verification pending GitHub Actions execution.
