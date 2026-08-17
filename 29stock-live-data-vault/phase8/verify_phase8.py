import json
import os
import tempfile
from pathlib import Path
from storage_engine import connect, install_schema, sha256_file, archive_verified, delete_day_after_verification

SYMBOL = '__PHASE8_VERIFY__'
DATE = '2026-08-17'
TS = '2026-08-17T09:15:00+05:30'

def cleanup(conn):
    for table in ('raw_market_snapshots','candles','indicators','session_features','derivative_data'):
        conn.execute(f'DELETE FROM {table} WHERE symbol = %s', (SYMBOL,))
    conn.execute('DELETE FROM archive_manifest WHERE trading_date = %s', (DATE,))
    conn.commit()

def main():
    if not os.environ.get('DATABASE_URL'):
        raise SystemExit('DATABASE_URL missing')
    print('GATE 1 schema + persistent database')
    with connect() as conn:
        install_schema(conn)
        cleanup(conn)
        conn.execute("INSERT INTO raw_market_snapshots(symbol,security_id,snapshot_minute,payload,provider) VALUES(%s,999991,%s,%s::jsonb,'TEST') ON CONFLICT DO NOTHING", (SYMBOL,TS,json.dumps({'last_price':123.45})))
        conn.execute("INSERT INTO candles(symbol,timeframe,candle_start,candle_end,open,high,low,close,volume,complete,source) VALUES(%s,'1m',%s,'2026-08-17T09:16:00+05:30',1,2,.5,1.5,10,true,'TEST') ON CONFLICT DO NOTHING", (SYMBOL,TS))
        conn.execute("INSERT INTO indicators(symbol,timeframe,candle_start,vwap,ema9,ema20) VALUES(%s,'1m',%s,1.2,1.1,1.0) ON CONFLICT DO NOTHING", (SYMBOL,TS))
        conn.execute("INSERT INTO session_features(symbol,trading_date,candle_start,session_open,session_high,session_low,session_close,session_volume,running_high,running_low,running_volume) VALUES(%s,%s,%s,1,2,.5,1.5,10,2,.5,10) ON CONFLICT DO NOTHING", (SYMBOL,DATE,TS))
        conn.execute("INSERT INTO derivative_data(symbol,observed_at,expiry,strike,option_type,last_price,oi,volume,iv,delta,gamma,theta,vega,bid_price,ask_price,bid_qty,ask_qty,payload) VALUES(%s,%s,'2026-08-27',100,'CE',2,10,5,20,.5,.01,-.02,.1,1.9,2.1,10,10,'{}')", (SYMBOL,TS))
        conn.commit()
        print('  raw/candle/indicator/feature/derivative persistence: PASS')
        conn.execute("INSERT INTO raw_market_snapshots(symbol,security_id,snapshot_minute,payload,provider) VALUES(%s,999991,%s,%s::jsonb,'ATTACK') ON CONFLICT(symbol,snapshot_minute) DO NOTHING", (SYMBOL,TS,json.dumps({'last_price':999999})))
        conn.commit()
        got = conn.execute("SELECT payload->>'last_price' FROM raw_market_snapshots WHERE symbol=%s AND snapshot_minute=%s", (SYMBOL,TS)).fetchone()[0]
        assert got == '123.45', 'historical overwrite protection failed'
        print('GATE 2 no historical overwrite: PASS')
        names = {r[0] for r in conn.execute("SELECT indexname FROM pg_indexes WHERE schemaname='public'").fetchall()}
        required = {'idx_raw_symbol_minute','idx_candles_symbol_tf_start','idx_indicators_symbol_tf_start','idx_features_symbol_date_start','idx_derivatives_symbol_observed','idx_derivatives_expiry_strike'}
        assert required <= names, f'missing indexes: {required-names}'
        print('GATE 3 symbol/timestamp indexing: PASS')

    with connect() as recovery:
        counts = {t: recovery.execute(f'SELECT count(*) FROM {t} WHERE symbol=%s',(SYMBOL,)).fetchone()[0] for t in ('raw_market_snapshots','candles','indicators','session_features','derivative_data')}
        assert counts == {'raw_market_snapshots':1,'candles':1,'indicators':1,'session_features':1,'derivative_data':1}, counts
        print('GATE 4 independent connection recovery persistence: PASS')
        cleanup(recovery)

    with tempfile.TemporaryDirectory() as d:
        archive = Path(d) / f'{DATE}.bin'
        archive.write_bytes(b'PSY29 verified daily archive')
        digest = sha256_file(archive)
        byte_size = archive.stat().st_size
        manifest = Path(d) / 'manifest.json'
        manifest.write_text(json.dumps({'trading_date':DATE,'sha256':digest,'byte_size':byte_size}))
        assert archive_verified(manifest, archive, DATE)
    print('GATE 5 archive checksum/manifest verification: PASS')

    class GuardConn:
        def transaction(self):
            raise AssertionError('destructive transaction should not start')
    try:
        delete_day_after_verification(GuardConn(), DATE, {'verified':False})
        raise AssertionError('unverified delete was not blocked')
    except RuntimeError:
        pass
    print('GATE 6 destructive-delete guard: PASS')

    with connect() as final:
        install_schema(final)
        final.execute("INSERT INTO archive_manifest(trading_date,object_uri,sha256,byte_size,verified_at,source_row_counts) VALUES(%s,%s,%s,%s,now(),%s::jsonb) ON CONFLICT(trading_date) DO UPDATE SET object_uri=excluded.object_uri,sha256=excluded.sha256,byte_size=excluded.byte_size,verified_at=excluded.verified_at,source_row_counts=excluded.source_row_counts", (DATE,'daily-archive-test',digest,byte_size,json.dumps({'raw_market_snapshots':1,'candles':1,'indicators':1,'session_features':1,'derivative_data':1})))
        final.commit()
        assert final.execute('SELECT verified_at FROM archive_manifest WHERE trading_date=%s',(DATE,)).fetchone() is not None
        print('GATE 7 archive manifest persistence: PASS')
        cleanup(final)
    print('PHASE8_DATABASE_VERIFICATION=PASS')

if __name__ == '__main__':
    main()
