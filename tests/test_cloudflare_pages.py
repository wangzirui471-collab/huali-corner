"""Exercise cloud read routes against isolated SQLite, without any real accounts."""
import asyncio
import json
from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'Backend mission'))

class Response:
    def __init__(self, body='',status=200,headers=None):
        self.status=status; self.body=body
    @classmethod
    def from_json(cls, value,status=200,headers=None):
        return cls(value,status,headers)

sys.modules.setdefault('workers',SimpleNamespace(Response=Response))
from app.cloudflare.api import Api
from app.cloudflare.http import guard
from app.cloudflare.crypto import session_digest

class Statement:
    def __init__(self, connection, sql):
        self.connection=connection; self.sql=sql; self.params=()
    def bind(self,*params): self.params=params; return self
    async def all(self):
        return SimpleNamespace(results=[dict(r) for r in self.connection.execute(self.sql,self.params)])
    async def first(self):
        row=self.connection.execute(self.sql,self.params).fetchone()
        return dict(row) if row else None
    async def run(self):
        c=self.connection.execute(self.sql,self.params)
        return SimpleNamespace(meta=SimpleNamespace(changes=c.rowcount,size_after=1024))

class Binding:
    def __init__(self,connection): self.connection=connection
    def prepare(self,sql): return Statement(self.connection,sql)

class CloudPagesTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:'); self.db.row_factory=sqlite3.Row
        self.addCleanup(self.db.close)
        self.db.executescript((ROOT/'Backend mission/app/cloudflare/schema.sql').read_text())
        for uid,role in [(1,'admin'),(2,'user'),(3,'user'),(4,'support')]:
            self.db.execute('INSERT INTO users(id,phone,nickname,role) VALUES(?,?,?,?)',(uid,f'user{uid}@example.invalid',f'同学{uid}',role))
            self.db.execute('INSERT INTO sessions VALUES(?,?,?)',(session_digest(f'test-{uid}'),uid,9999999999))
        self.db.executemany("INSERT INTO products(id,seller_id,title,category,price,delivery_fee,delivery,region,status,data) VALUES(?,?,'测试物品','living',100,0,'pickup','A1',?,'{}')",[(1,2,'available'),(2,3,'available'),(3,2,'removed')])
        for oid,buyer,seller in [(1,2,3),(2,3,1)]:
            self.db.execute("INSERT INTO orders(id,buyer_id,seller_id,items,total,status) VALUES(?,?,?,? ,100,'paid')",(oid,buyer,seller,json.dumps([{'id':2,'title':'测试物品','price':100}])))
        self.db.execute("INSERT INTO notifications(id,user_id,kind,body,created) VALUES(1,2,'test','本人通知',1),(2,3,'test','他人通知',1)")
        self.db.execute("INSERT INTO tickets(id,user_id,type,subject,body) VALUES(1,2,'other','本人咨询','测试'),(2,3,'other','他人咨询','测试')")
        self.db.commit()
        self.api=Api(SimpleNamespace(DB=Binding(self.db),MEDIA=object()))
    async def req(self,path,uid=2,method='GET',body=None):
        async def text(): return json.dumps(body or {})
        request=SimpleNamespace(url='https://test.invalid'+path,method=method,
            headers={'Authorization':f'Bearer test-{uid}'} if uid else {},text=text)
        return await guard(lambda:self.api.dispatch(request))
    async def test_my_products_lists_owned_records_without_exposing_other_sellers(self):
        r=await self.req('/api/my-products')
        self.assertEqual(r.status,200); self.assertEqual({x['id'] for x in r.body},{1,3})
        self.assertTrue(next(x for x in r.body if x['id']==3).get('relist_locked') is False)
    async def test_orders_and_offers_are_scoped_to_current_user(self):
        r=await self.req('/api/orders')
        self.assertEqual(r.status,200); self.assertEqual([x['id'] for x in r.body],[1])
        self.assertIsInstance(r.body[0]['items'],list)
        self.assertEqual((await self.req('/api/offers')).status,200)
    async def test_notifications_are_private_and_mark_read_cannot_touch_another_user(self):
        r=await self.req('/api/notifications'); self.assertEqual(r.status,200)
        self.assertEqual(r.body['unread'],1); self.assertEqual([x['id'] for x in r.body['items']],[1])
        self.assertEqual((await self.req('/api/notifications',method='POST',body={'id':2})).status,200)
        self.assertIsNone(self.db.execute('SELECT read_at FROM notifications WHERE id=2').fetchone()[0])
    async def test_staff_overview_routes_require_active_staff(self):
        for path in ['/api/admin','/api/product/removed','/api/reconcile','/api/admin/content']:
            with self.subTest(path=path):
                self.assertEqual((await self.req(path,uid=2)).status,403)
                self.assertEqual((await self.req(path,uid=0)).status,401)
                self.assertEqual((await self.req(path,uid=1)).status,200)
    async def test_staff_overview_contains_real_users_and_tickets(self):
        r=await self.req('/api/admin',uid=1)
        self.assertEqual(r.status,200); self.assertEqual(len(r.body['users']),4)
        self.assertNotIn('phone',r.body['users'][0])
        self.assertEqual(len((await self.req('/api/tickets',uid=1)).body),2)
        self.assertEqual([x['id'] for x in (await self.req('/api/tickets',uid=2)).body],[1])
    async def test_badges_and_health_work_and_guests_cannot_read_private_pages(self):
        r=await self.req('/api/badges'); self.assertEqual(r.status,200)
        self.assertEqual(r.body,{'notifications':1,'chat':0})
        self.assertEqual((await self.req('/api/health',uid=0)).status,200)
        for path in ['/api/my-products','/api/orders','/api/notifications','/api/badges','/api/tickets']:
            self.assertEqual((await self.req(path,uid=0)).status,401)
    async def test_public_profile_never_contains_contact_or_governance_fields(self):
        r=await self.req('/api/profile?id=2',uid=0)
        self.assertEqual(r.status,200)
        self.assertFalse({'phone','role','status'} & set(r.body['user']))
        self.assertEqual([x['id'] for x in r.body['products']],[1])
        self.assertEqual(r.body['products'][0].get('nickname'),'同学2')
        self.assertTrue({'likes','liked','favorited','seller_trusted'}.issubset(r.body['products'][0]))

    async def test_self_profile_requires_session_and_contains_version(self):
        self.assertEqual((await self.req('/api/user/profile',uid=0)).status,401)
        response=await self.req('/api/user/profile')
        self.assertEqual(response.status,200)
        self.assertEqual(response.body['id'],2)
        self.assertIn('profile_version',response.body)

if __name__=='__main__': unittest.main()
