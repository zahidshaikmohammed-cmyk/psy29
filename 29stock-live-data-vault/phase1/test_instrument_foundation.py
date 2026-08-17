import json
from pathlib import Path

from instrument_foundation import resolve
from universe import STOCKS


def test_29_stock_universe():
    assert len(STOCKS) == 29
    assert len(set(STOCKS)) == 29


def test_resolve_exactly_29_nse_equities():
    rows = [
        {
            "SEM_EXM_EXCH_ID": "NSE",
            "SEM_SEGMENT": "E",
            "SEM_INSTRUMENT_NAME": "EQUITY",
            "SEM_TRADING_SYMBOL": s,
            "SEM_SMST_SECURITY_ID": str(10000 + i),
        }
        for i, s in enumerate(STOCKS)
    ]
    import csv, io
    fields = list(rows[0])
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fields)
    w.writeheader(); w.writerows(rows)
    result = resolve(buf.getvalue().encode())
    assert [r["symbol"] for r in result] == list(STOCKS)
    assert len({r["security_id"] for r in result}) == 29
    assert all(r["exchange_segment"] == "NSE_EQ" for r in result)
    assert all(r["instrument_type"] == "EQUITY" for r in result)


def test_persisted_fixture_shape_if_present():
    p = Path(__file__).with_name("instrument_master.json")
    if p.exists():
        data = json.loads(p.read_text())
        assert data["universe_size"] == 29
        assert len(data["instruments"]) == 29
