# Phase 8 — Permanent Data Storage

Neon/PostgreSQL is the hot operational database. Daily historical exports are immutable compressed archives. The database is never treated as the sole long-term archive.

A DATABASE_URL secret must point to the approved Neon database. The workflow refuses to report success without a live database connection.
