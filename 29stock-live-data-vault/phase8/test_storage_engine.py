import json
import os
import tempfile
import unittest
from pathlib import Path
from storage_engine import sha256_file, archive_verified


class Phase8StorageTests(unittest.TestCase):
    def test_checksum_and_manifest_verification(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "archive.bin"
            payload = b"PSY29 archive"
            p.write_bytes(payload)
            digest = sha256_file(p)
            manifest = Path(d) / "manifest.json"
            manifest.write_text(json.dumps({"trading_date": "2026-08-17", "sha256": digest, "byte_size": len(payload)}))
            self.assertTrue(archive_verified(manifest, p, "2026-08-17"))

    def test_database_url_required(self):
        old = os.environ.pop("DATABASE_URL", None)
        try:
            from storage_engine import connect
            with self.assertRaises(RuntimeError):
                connect()
        finally:
            if old is not None:
                os.environ["DATABASE_URL"] = old

    def test_archive_verification_blocks_unverified_delete(self):
        from storage_engine import delete_day_after_verification
        class FakeConn:
            def transaction(self):
                raise AssertionError("transaction must not start for unverified archive")
        with self.assertRaises(RuntimeError):
            delete_day_after_verification(FakeConn(), "2026-08-17", {"verified": False})


class Phase8LivePostgresTests(unittest.TestCase):
    """Runs against the configured Neon/PostgreSQL database in CI."""

    @classmethod
    def setUpClass(cls):
        if not os.environ.get("DATABASE_URL"):
            raise unittest.SkipTest("DATABASE_URL not configured")
        from storage_engine import connect, install_schema
        cls.connect = connect
        with connect() as conn:
            install_schema(conn)

    def _cleanup(self, conn, symbol):
        for table in ("raw_market_snapshots", "candles", "indicators", "session_features", "derivative_data"):
            conn.execute(f"DELETE FROM {table} WHERE symbol = %s", (symbol,))
        conn.commit()

    def test_schema_indexes_and_persistence(self):
        symbol = "__PHASE8_TEST__"
        try:
            with self.connect() as conn:
                conn.execute("""
                    INSERT INTO raw_market_snapshots(symbol, security_id, snapshot_minute, payload, provider)
                    VALUES (%s, 999999, '2026-08-17T09:15:00+05:30', %s::jsonb, 'TEST')
                    ON CONFLICT DO NOTHING
                """, (symbol, json.dumps({"last_price": 123.45})))
                conn.execute("""
                    INSERT INTO candles(symbol,timeframe,candle_start,candle_end,open,high,low,close,volume,complete,source)
                    VALUES (%s,'1m','2026-08-17T09:15:00+05:30','2026-08-17T09:16:00+05:30',1,2,0.5,1.5,10,true,'TEST')
                    ON CONFLICT DO NOTHING
                """, (symbol,))
                conn.execute("""
                    INSERT INTO indicators(symbol,timeframe,candle_start,vwap,ema9,ema20)
                    VALUES (%s,'1m','2026-08-17T09:15:00+05:30',1.2,1.1,1.0)
                    ON CONFLICT DO NOTHING
                """, (symbol,))
                conn.execute("""
                    INSERT INTO session_features(symbol,trading_date,candle_start,session_open,session_high,session_low,session_close,session_volume,running_high,running_low,running_volume)
                    VALUES (%s,'2026-08-17','2026-08-17T09:15:00+05:30',1,2,0.5,1.5,10,2,0.5,10)
                    ON CONFLICT DO NOTHING
                """, (symbol,))
                conn.execute("""
                    INSERT INTO derivative_data(symbol,observed_at,expiry,strike,option_type,last_price,oi,volume,iv,delta,gamma,theta,vega,bid_price,ask_price,bid_qty,ask_qty,payload)
                    VALUES (%s,'2026-08-17T09:15:00+05:30','2026-08-27',100,'CE',2,10,5,20,0.5,0.01,-0.02,0.1,1.9,2.1,10,10,'{}')
                """, (symbol,))
                conn.commit()

                # Duplicate protection: attempted replacement cannot overwrite the original.
                conn.execute("""
                    INSERT INTO raw_market_snapshots(symbol, security_id, snapshot_minute, payload, provider)
                    VALUES (%s, 999999, '2026-08-17T09:15:00+05:30', %s::jsonb, 'ATTACK')
                    ON CONFLICT(symbol, snapshot_minute) DO NOTHING
                """, (symbol, json.dumps({"last_price": 999999})))
                conn.commit()
                value = conn.execute("SELECT payload->>'last_price' FROM raw_market_snapshots WHERE symbol=%s", (symbol,)).fetchone()[0]
                self.assertEqual(value, "123.45")

            # Persistence/recovery: close the first connection and reopen from a fresh process-equivalent connection.
            with self.connect() as conn2:
                counts = {table: conn2.execute(f"SELECT count(*) FROM {table} WHERE symbol=%s", (symbol,)).fetchone()[0]
                          for table in ("raw_market_snapshots", "candles", "indicators", "session_features", "derivative_data")}
                self.assertEqual(counts, {
                    "raw_market_snapshots": 1, "candles": 1, "indicators": 1,
                    "session_features": 1, "derivative_data": 1,
                })
                indexes = conn2.execute("""
                    SELECT indexname FROM pg_indexes
                    WHERE schemaname='public' AND tablename IN ('raw_market_snapshots','candles','indicators','session_features','derivative_data')
                """).fetchall()
                names = {r[0] for r in indexes}
                for required in {
                    "idx_raw_symbol_minute", "idx_candles_symbol_tf_start", "idx_indicators_symbol_tf_start",
                    "idx_features_symbol_date_start", "idx_derivatives_symbol_observed", "idx_derivatives_expiry_strike"
                }:
                    self.assertIn(required, names)
        finally:
            with self.connect() as conn3:
                self._cleanup(conn3, symbol)


if __name__ == "__main__":
    unittest.main()
