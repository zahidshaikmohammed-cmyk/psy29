# PSY29 Phase 6 — Session & Market Features

STATUS: COMPLETE

Verified by GitHub Actions run 32038228154.

- Session OHLC: PASS
- Session high/low: PASS
- Session volume: PASS
- First 5-minute range: PASS
- First 15-minute range: PASS
- Running high/low: PASS
- Running volume: PASS
- Engine-required session features: PASS for the frozen Phase 0 contract
- Feature persistence: PASS (deterministic feature output is persisted as the phase-6 data product)

Rules:
- Completed canonical candles only.
- NSE session is 09:15 to before 15:30 IST.
- No synthetic/incomplete-candle session features.
