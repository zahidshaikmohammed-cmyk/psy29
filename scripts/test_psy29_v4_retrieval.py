from psy29_v4_retrieval import REQUIRED, run

SYMBOLS = ["NESTLEIND","VEDL","ICICIPRULI","KALYANKJIL","KOTAKBANK","BANDHANBNK","BANKBARODA","TITAN","INFY","DLF","TCS","MAXHEALTH","KFINTECH","PRESTIGE","BHEL","RBLBANK","HCLTECH","ICICIGI","HDFCLIFE","MARICO","LUPIN","COFORGE","TECHM","SWIGGY","PERSISTENT","OBEROIRLTY","SUPREMEIND","LAURUSLABS","AMBUJACEM"]

def payload(symbol, date="2026-08-25"):
    d={k:"1" for k in REQUIRED}
    d.update({"SYMBOL":symbol,"TRADING_DATE":date,"SNAPSHOT_BUILT_AT_IST":date+" 10:00:00 IST","LIVE_LTP":"100","LIVE_LTP_FETCHED_AT_IST":date+" 10:00:00 IST","DATA_LAG_SECONDS":"1"})
    return "PSY29_EXECUTION_SNAPSHOT=1\n"+"\n".join(f"{k}={v}" for k,v in d.items())

def master():
    return "TRADING_DATE=2026-08-25\nEXPECTED_STOCKS=29\nPUBLISHED_STOCKS=29\nFAILED_STOCKS=0\nPUBLISHED_SYMBOLS="+",".join(SYMBOLS)+"\n"

def test_complete_29():
    def f(url):
        return master() if url.endswith("EXECUTION_MASTER.txt") else payload(url.split("/")[-1][:-4])
    x=run(fetcher=f)
    assert x["status"]=="COMPLETE" and x["validated"]==29 and x["v4_analysis_permitted"]

def test_one_failed_blocks():
    def f(url):
        if url.endswith("EXECUTION_MASTER.txt"): return master()
        s=url.split("/")[-1][:-4]
        return "BROKEN" if s=="TCS" else payload(s)
    x=run(fetcher=f)
    assert x["status"]=="INCOMPLETE" and "TCS" in x["failed_symbols"] and not x["v4_analysis_permitted"]

def test_wrong_date_blocks():
    def f(url):
        if url.endswith("EXECUTION_MASTER.txt"): return master()
        s=url.split("/")[-1][:-4]
        return payload(s,"2026-08-24") if s=="VEDL" else payload(s)
    x=run(fetcher=f)
    assert x["status"]=="INCOMPLETE" and "VEDL" in x["failed_symbols"]

def test_missing_ltp_blocks():
    def f(url):
        if url.endswith("EXECUTION_MASTER.txt"): return master()
        s=url.split("/")[-1][:-4]
        return payload(s).replace("LIVE_LTP=100","LIVE_LTP=UNAVAILABLE") if s=="BHEL" else payload(s)
    x=run(fetcher=f)
    assert x["status"]=="INCOMPLETE" and "BHEL" in x["failed_symbols"]
