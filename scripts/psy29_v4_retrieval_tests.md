## Verification note

The deterministic retrieval tests cover complete 29/29, one failed/truncated payload, wrong trading date, and missing LIVE_LTP. Production integration remains downstream: this module exposes only the normalized dataset and a hard completeness gate; it does not generate trades or alter Stage 6-20/V4 strategy logic.
