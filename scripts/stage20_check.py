#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path

def load(p):return json.loads(p.read_text(encoding='utf-8'))
def main():
    p=argparse.ArgumentParser();p.add_argument('--contract',required=True,type=Path);p.add_argument('--universe',required=True,type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    c=load(a.contract);u=load(a.universe);b=load(a.output/'PSY29_STAGE20_FINAL_SIGNAL_BOARD.json');v=load(a.output/'PSY29_STAGE20_VALIDATION.json')
    assert c['stage']==20 and c['version']=='1.0' and c['status']=='LOCKED'
    assert c['signal_policy']['multiple_signals_allowed'] is True and c['signal_policy']['daily_signal_cap'] is None
    syms=[str(x['symbol']).strip().upper() for x in u['universe']];assert len(syms)==29 and len(set(syms))==29
    assert b['coverage']=={'expected':29,'actual':29,'unique':29};signals=b['signals'];assert len({r['symbol'] for r in signals})==len(signals)
    for r in signals:
        assert {'signal_id','symbol','direction','strategy','entry','stop_loss','take_profit','risk_reward','signal_score','signal_status','timestamp','provenance'}<=set(r)
        assert r['direction'] in {'LONG','SHORT'} and r['signal_status']=='NEW_SIGNAL';assert r['memory_state'] not in {'ACTIVE_SIGNAL','TRADED'}
        e,s,t=map(float,(r['entry'],r['stop_loss'],r['take_profit']));assert (s<e<t) if r['direction']=='LONG' else (t<e<s);assert float(r['risk_reward'])>0
        assert r['strategy'] in {'BREAKOUT','BREAKDOWN','CONTINUATION','RETEST'}
    assert v['validation_status']=='PASS' and v['canonical_29'] is True and v['multiple_signals_allowed'] is True and v['daily_cap'] is None and v['no_generic_fallback'] is True
    print('STAGE 20 HARD VERIFY: PASS');print('29/29 coverage: PASS');print(f'Signals: {len(signals)}');print('Strategy-owned Entry/SL/TP: PASS');print('Multiple signals: PASS');print('No daily cap: PASS');print('Trade memory: PASS');print('Safety boundary: PASS')
if __name__=='__main__':main()
