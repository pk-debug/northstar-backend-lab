"""Black-box contract test for any running language backend; stdlib only.

Usage: python contracts/smoke.py http://localhost:8000
The script intentionally places one sample BUY order; use a disposable DB.
"""
import json,sys,uuid
from urllib.request import Request,urlopen
from urllib.error import HTTPError

base=(sys.argv[1] if len(sys.argv)>1 else 'http://localhost:8000').rstrip('/')

def call(path, body=None, key=None):
    """Decode both successful JSON and HTTP errors without extra dependencies."""
    data=None if body is None else json.dumps(body).encode()
    headers={'Content-Type':'application/json'}
    if key: headers['Idempotency-Key']=key
    req=Request(base+path,headers=headers,data=data,method='GET' if body is None else 'POST')
    try:
        with urlopen(req,timeout=15) as r:return r.status,json.load(r)
    except HTTPError as e:return e.code,json.load(e)

assert call('/health')[1]['status']=='ok'
assert len(call('/api/v1/assets')[1])==7
assert call('/api/v1/assets/aapl')[1]['symbol']=='AAPL'
assert len(call('/api/v1/indexes')[1])==3
assert call('/api/v1/assets/UNKNOWN')[0]==404
assert call('/api/v1/assets?q=apple')[1][0]['symbol']=='AAPL'
original=call('/api/v1/portfolio')[1]
key='test-'+uuid.uuid4().hex
buy={'symbol':'AAPL','side':'BUY','quantity':1}
status,result=call('/api/v1/orders',buy,key)
assert status==201,(status,result)
assert result['order']['price']==228.87
status,replayed=call('/api/v1/orders',buy,key)
assert status==200 and replayed['order']['id']==result['order']['id']
assert call('/api/v1/orders',{**buy,'quantity':2},key)[0]==409
updated=call('/api/v1/portfolio')[1]
assert round(updated['cash']-original['cash'],2)==-228.87
assert len(call('/api/v1/orders')[1])>=1
status,_=call('/api/v1/orders',{'symbol':'TSLA','side':'SELL','quantity':1},'test-'+uuid.uuid4().hex)
assert status==409
print('PASS:',base,'fixtures, portfolio, order, idempotency, rejection')
