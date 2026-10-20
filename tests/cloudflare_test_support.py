"""Local in-memory D1/R2 adapters for isolated cloud domain tests."""
import json
from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'Backend mission'))

class TestResponse:
    def __init__(self,body='',status=200,headers=None):
        self.body=body;self.status=status;self.headers=headers or {}
    @classmethod
    def from_json(cls,body,status=200,headers=None):return cls(body,status,headers)

sys.modules.setdefault('workers',SimpleNamespace(Response=TestResponse))

class Statement:
    def __init__(self,db,sql):self.db=db;self.sql=sql;self.params=()
    def bind(self,*params):self.params=params;return self
    def execute(self):
        cur=self.db.execute(self.sql,self.params)
        rows=[dict(x) for x in cur.fetchall()] if cur.description else []
        return SimpleNamespace(results=rows,meta=SimpleNamespace(changes=max(0,cur.rowcount),size_after=1024,last_row_id=cur.lastrowid))
    async def all(self):return self.execute()
    async def first(self):
        rows=self.execute().results
        return rows[0] if rows else None
    async def run(self):return self.execute()

class Binding:
    def __init__(self,db):self.db=db
    def prepare(self,sql):return Statement(self.db,sql)
    async def batch(self,statements):
        self.db.execute('SAVEPOINT cloud_batch')
        try:
            result=[s.execute() for s in statements]
            self.db.execute('RELEASE cloud_batch')
            return result
        except BaseException:
            self.db.execute('ROLLBACK TO cloud_batch')
            self.db.execute('RELEASE cloud_batch')
            raise

class MemoryObject:
    def __init__(self,payload):self.payload=payload
    async def arrayBuffer(self):return self.payload

class MemoryBucket:
    def __init__(self):self.objects={}
    async def put(self,key,payload,options=None):
        self.objects[key]=bytes(payload);return MemoryObject(bytes(payload))
    async def get(self,key):
        return MemoryObject(self.objects[key]) if key in self.objects else None
    async def head(self,key):return await self.get(key)
    async def delete(self,key):self.objects.pop(key,None)

class CloudCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        from app.cloudflare.api import Api
        from app.cloudflare.crypto import session_digest
        self.db=sqlite3.connect(':memory:');self.db.row_factory=sqlite3.Row
        self.addCleanup(self.db.close)
        self.db.executescript((ROOT/'Backend mission/app/cloudflare/schema.sql').read_text(encoding='utf-8'))
        for uid,role in [(1,'admin'),(2,'user'),(3,'user'),(4,'support'),(5,'developer')]:
            self.db.execute('INSERT INTO users(id,phone,nickname,role) VALUES(?,?,?,?)',(uid,f'u{uid}@test.invalid',f'测试用户{uid}',role))
            self.db.execute('INSERT INTO sessions VALUES(?,?,?)',(session_digest(f'test-{uid}'),uid,9999999999))
        self.db.execute("INSERT INTO rooms(id,kind,name) VALUES(1,'general','广州校区总聊')")
        self.db.commit()
        self.bucket=MemoryBucket()
        self.api=Api(SimpleNamespace(DB=Binding(self.db),MEDIA=self.bucket))
    async def req(self,path,uid=2,method='GET',body=None):
        from app.cloudflare.http import guard
        async def text():return json.dumps(body or {},ensure_ascii=False)
        request=SimpleNamespace(url='https://test.invalid'+path,method=method,headers={'Authorization':f'Bearer test-{uid}'} if uid else {},text=text)
        return await guard(lambda:self.api.dispatch(request))
