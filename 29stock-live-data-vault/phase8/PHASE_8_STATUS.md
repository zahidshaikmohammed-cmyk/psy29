# PHASE 8 — PERMANENT DATA STORAGE

Status: VERIFICATION RUNNING.

Architecture:
- PostgreSQL hot operational store (Neon-compatible DATABASE_URL)
- Immutable raw/candle/indicator/feature/derivative tables
- Symbol + timestamp indexes
- INSERT-only uniqueness protection
- Verified archive manifest before destructive deletion
- Long-term daily archive is outside the 0.5 GB hot database

Completion requires a live PostgreSQL connection plus restart/recovery verification. No phase completion is claimed until CI passes those gates.
