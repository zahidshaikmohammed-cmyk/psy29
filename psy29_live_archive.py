"""Durable minute archive for the PSY29 live 29-stock universe."""
from __future__ import annotations
import json, os

_TABLE = "psy29_live_minute_snapshots"

def _url():
    value = os.environ.get("DATABASE_URL") or os.environ.get("PSY29_DATABASE_URL")
    if not value:
        raise RuntimeError("DATABASE_URL is not configured for the live archive")
    return value

def _connect():
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError("psycopg is not installed") from exc
    return psycopg.connect(_url())

def ensure_schema():
    with _connect() as conn:
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {_TABLE} (
                session_date DATE NOT NULL,
                minute_ts TIMESTAMPTZ NOT NULL,
                symbol TEXT NOT NULL,
                payload JSONB NOT NULL,
                stored_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (session_date, minute_ts, symbol)
            );
            CREATE INDEX IF NOT EXISTS psy29_live_minute_idx
            ON {_TABLE} (session_date, minute_ts DESC);
            CREATE INDEX IF NOT EXISTS psy29_live_symbol_idx
            ON {_TABLE} (symbol, session_date, minute_ts DESC);
        """)

def store_rows(rows):
    rows = list(rows)
    if not rows:
        return 0
    ensure_schema()
    sql = f"""
        INSERT INTO {_TABLE} (session_date, minute_ts, symbol, payload)
        VALUES (%s, %s, %s, %s::jsonb)
        ON CONFLICT (session_date, minute_ts, symbol)
        DO UPDATE SET payload=EXCLUDED.payload, stored_at=NOW()
    """
    with _connect() as conn:
        with conn.cursor() as cur:
            for row in rows:
                cur.execute(sql, (row["session_date"], row["minute_ts"], row["symbol"], json.dumps(row, separators=(",", ":"))))
    return len(rows)

def history(session_date, symbol=None, limit=10000):
    ensure_schema()
    if symbol:
        sql = f"SELECT payload FROM {_TABLE} WHERE session_date=%s AND symbol=%s ORDER BY minute_ts ASC LIMIT %s"
        params = (session_date, symbol.upper(), limit)
    else:
        sql = f"SELECT payload FROM {_TABLE} WHERE session_date=%s ORDER BY minute_ts ASC, symbol ASC LIMIT %s"
        params = (session_date, limit)
    with _connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [r[0] for r in rows]

def latest(session_date=None):
    ensure_schema()
    if session_date:
        sql = f"SELECT payload FROM {_TABLE} WHERE session_date=%s AND minute_ts=(SELECT MAX(minute_ts) FROM {_TABLE} WHERE session_date=%s) ORDER BY symbol"
        params = (session_date, session_date)
    else:
        sql = f"SELECT payload FROM {_TABLE} WHERE minute_ts=(SELECT MAX(minute_ts) FROM {_TABLE}) ORDER BY symbol"
        params = ()
    with _connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [r[0] for r in rows]

def stats(session_date=None):
    ensure_schema()
    where, params = (("WHERE session_date=%s", (session_date,)) if session_date else ("", ()))
    with _connect() as conn:
        row = conn.execute(f"SELECT COUNT(*)::int, COUNT(DISTINCT symbol)::int, COUNT(DISTINCT minute_ts)::int, MIN(minute_ts), MAX(minute_ts) FROM {_TABLE} {where}", params).fetchone()
    return {"rows": row[0], "symbols": row[1], "minutes": row[2], "first_timestamp": row[3].isoformat() if row[3] else None, "last_timestamp": row[4].isoformat() if row[4] else None}
