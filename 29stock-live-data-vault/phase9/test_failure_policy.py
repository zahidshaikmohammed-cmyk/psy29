from failure_policy import *

def test_api_retry_recovers():
    state={'n':0}
    def op():
        state['n']+=1
        if state['n']<3: raise TransientAcquisitionError('temporary')
        return 'ok'
    assert retry_with_backoff(op)=='ok' and state['n']==3

def test_database_retry_recovers():
    state={'n':0}
    def op():
        state['n']+=1
        if state['n']==1: raise DatabaseWriteError('temporary')
        return 'written'
    assert retry_with_backoff(op)=='written'

def test_stock_failure_isolated():
    x=isolate_stock_failure('VEDL', TransientAcquisitionError())
    assert x['isolated'] and x['symbol']=='VEDL'

def test_failure_never_fabricates():
    x=no_fabrication_on_failure('TITAN', TransientAcquisitionError())
    assert x['fabricated'] is False and x['status']=='missing'
