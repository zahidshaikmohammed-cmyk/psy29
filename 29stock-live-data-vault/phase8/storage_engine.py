"""Phase 8 storage primitives. PostgreSQL is the hot operational store.
Permanent history is archived before any deletion. No destructive operation occurs
unless the archive manifest has been verified.
"""
import hashlib
import os
from pathlib import Path
import json

try:
    import psycopg
except ImportError:  # CI installs it; keeps local import failure explicit.
    psycopg = None

SCHEMA = Path(__file__).with_name("schema.sql")


def connect():
    if psycopg is None:
        raise RuntimeError("psycopg is required")
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is required")
    return psycopg.connect(url)


def install_schema(conn):
    conn.execute(SCHEMA.read_text())
    conn.commit()


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def archive_verified(manifest_path, archive_path, expected_date):
    manifest = json.loads(Path(manifest_path).read_text())
    if manifest["trading_date"] != expected_date:
        raise RuntimeError("archive trading date mismatch")
    if manifest["sha256"] != sha256_file(archive_path):
        raise RuntimeError("archive checksum mismatch")
    if manifest["byte_size"] != Path(archive_path).stat().st_size:
        raise RuntimeError("archive byte-size mismatch")
    return True


def delete_day_after_verification(conn, trading_date, manifest):
    """Delete only after caller has independently verified archive + manifest."""
    if not manifest.get("verified"):
        raise RuntimeError("refusing destructive delete: archive not verified")
    with conn.transaction():
        for table, column in [
            ("raw_market_snapshots", "snapshot_minute"),
            ("candles", "candle_start"),
            ("indicators", "candle_start"),
            ("session_features", "trading_date"),
            ("derivative_data", "observed_at"),
        ]:
            # Deletion policy is intentionally explicit and executed only after verification.
            if table == "session_features":
                conn.execute(f"DELETE FROM {table} WHERE trading_date = %s", (trading_date,))
            else:
                conn.execute(f"DELETE FROM {table} WHERE ({column})::date = %s", (trading_date,))
