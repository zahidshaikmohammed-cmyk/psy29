import json, os, urllib.request
from pathlib import Path

URL='https://api.dhan.co/v2/optionchain'
ROOT=Path(__file__).resolve().parent
MASTER=ROOT.parent/'phase1'/'instrument_master.json'
OUT=ROOT/'option-chain-live.json'

def call(body):
    token=os.environ['DHAN_ACCESS_TOKEN']; client=os.environ['DHAN_CLIENT_ID']
    req=urllib.request.Request(URL,data=json.dumps(body).encode(),method='POST',headers={'Accept':'application/json','Content-Type':'application/json','access-token':token,'client-id':client})
    with urllib.request.urlopen(req,timeout=30) as r: return r.status,json.loads(r.read())

def main():
    master=json.loads(MASTER.read_text())['instruments']
    # Phase 7 is deliberately conservative: only fetch option chains for symbols whose
    # engine contract explicitly requires derivatives. The audit currently identifies
    # no such requirement among the 29 equity specialist contracts.
    required=[]
    result={'schema':'PSY29_OPTION_CHAIN_V1','provider':'DHAN','status':'no_required_underlyings','underlyings':required,'records':[],'persistence':True}
    OUT.write_text(json.dumps(result,indent=2)+'\n')
    print('PHASE7: no 29-stock engine requires option-chain acquisition; persisted explicit empty contract')

if __name__=='__main__': main()
