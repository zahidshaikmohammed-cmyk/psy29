from datetime import datetime, timezone, timedelta
from data_quality import validate_snapshot, validate_candle, validate_complete_stock_set, audit_event

NOW = datetime(2026, 8, 17, 10, 0, tzinfo=timezone.utc)
BASE = {'symbol':'NESTLEIND','security_id':1001,'timestamp':'2026-08-17T09:59:00+00:00','last_price':2500}

def test_accept_valid_snapshot():
    assert validate_snapshot(BASE, expected_security_id=1001, expected_symbol='NESTLEIND', observed_at=NOW).accepted

def test_future_rejected():
    x = {**BASE, 'timestamp':(NOW+timedelta(minutes=1)).isoformat()}
    assert validate_snapshot(x, expected_security_id=1001, expected_symbol='NESTLEIND', observed_at=NOW).reason == 'future-timestamp'

def test_duplicate_rejected():
    key=(BASE['symbol'], '2026-08-17T09:59:00+00:00')
    assert validate_snapshot(BASE, expected_security_id=1001, expected_symbol='NESTLEIND', observed_at=NOW, seen_keys={key}).reason == 'duplicate'

def test_wrong_security_rejected():
    assert validate_snapshot({**BASE,'security_id':999}, expected_security_id=1001, expected_symbol='NESTLEIND', observed_at=NOW).reason == 'wrong-security'

def test_missing_data_rejected():
    assert validate_snapshot({k:v for k,v in BASE.items() if k!='last_price'}, expected_security_id=1001, expected_symbol='NESTLEIND', observed_at=NOW).reason == 'missing-data'

def test_invalid_ohlc_rejected():
    assert validate_candle({'open':10,'high':5,'low':4,'close':9,'volume':10}).reason == 'invalid-OHLC'

def test_invalid_volume_rejected():
    assert validate_candle({'open':10,'high':11,'low':9,'close':10,'volume':-1}).reason == 'invalid-volume'

def test_valid_candle():
    assert validate_candle({'open':10,'high':11,'low':9,'close':10,'volume':100}).accepted

def test_partial_stock_isolation():
    result=validate_complete_stock_set([{'symbol':'NESTLEIND'},{'symbol':'VEDL'}], {'NESTLEIND','VEDL','TITAN'})
    assert not result['complete'] and result['missing']==['TITAN']

def test_unexpected_security_is_detected():
    result=validate_complete_stock_set([{'symbol':'NESTLEIND'},{'symbol':'EVIL'}], {'NESTLEIND','VEDL'})
    assert not result['complete'] and result['unexpected']==['EVIL']

def test_audit_provenance():
    e=audit_event('snapshot_rejected', symbol='NESTLEIND', accepted=False, reason='future-timestamp', provider='DHAN', observed_at=NOW, source_timestamp=NOW+timedelta(minutes=1))
    assert e['provider']=='DHAN' and e['accepted'] is False and e['source_timestamp'] is not None
