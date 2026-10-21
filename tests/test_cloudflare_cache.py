import time
from types import SimpleNamespace

from cloudflare_test_support import CloudCase, Binding


class MemoryKV:
    def __init__(self):
        self.store = {}

    async def get(self, key):
        return self.store.get(key)

    async def put(self, key, value):
        self.store[key] = value


class CacheTests(CloudCase):
    def setUp(self):
        super().setUp()
        from app.cloudflare.api import Api
        self.kv = MemoryKV()
        self.api = Api(SimpleNamespace(DB=Binding(self.db), MEDIA=self.bucket, CACHE=self.kv))
        self.db.execute(
            "INSERT INTO products(id,seller_id,title,category,price,delivery_fee,delivery,region,status,data,created) "
            "VALUES(1,2,'测试书','books',1000,0,'meet','A1','available','{}',?)", (time.time(),))
        self.db.commit()

    async def test_anonymous_products_are_cached(self):
        first = await self.req('/api/products?limit=40', uid=None)
        self.assertEqual(first.status, 200, first.body)
        self.assertTrue(any(k.startswith('products:') for k in self.kv.store), list(self.kv.store))
        # 清空库里的商品；若仍返回原数据，说明命中缓存而不是重新查库
        self.db.execute('DELETE FROM products')
        self.db.commit()
        second = await self.req('/api/products?limit=40', uid=None)
        self.assertEqual(second.status, 200, second.body)
        self.assertGreaterEqual(len(second.body), 1)
        self.assertEqual(len(second.body), len(first.body))

    async def test_logged_in_products_are_not_cached(self):
        r = await self.req('/api/products?limit=40', uid=2)
        self.assertEqual(r.status, 200, r.body)
        self.assertFalse(any(k.startswith('products:') for k in self.kv.store), list(self.kv.store))

    async def test_cache_expires(self):
        self.api.CACHE_TTL = 0
        await self.req('/api/products?limit=40', uid=None)
        self.db.execute('DELETE FROM products')
        self.db.commit()
        r = await self.req('/api/products?limit=40', uid=None)
        self.assertEqual(r.status, 200, r.body)
        self.assertEqual(len(r.body), 0)
