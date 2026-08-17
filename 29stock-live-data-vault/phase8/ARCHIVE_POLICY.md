# Phase 8 Archive Policy

1. During the session, Neon/PostgreSQL is the hot operational store.
2. At session close, export the complete day's raw, candle, indicator, feature and derivative records to a compressed permanent archive.
3. Write SHA-256, byte size and row counts to archive_manifest.
4. Re-open and validate the archive before deletion.
5. Delete database rows only after verification succeeds.
6. If export or verification fails, retain the database rows and retry; never fabricate or silently discard data.
7. Historical archives are immutable and are never overwritten.
