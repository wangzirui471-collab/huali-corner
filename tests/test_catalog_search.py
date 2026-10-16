import json
import unittest
import test_catalog_editing as fixtures
from app.market import DomainError

class CatalogSearchTests(unittest.TestCase):
    setUp=fixtures.CatalogEditingTests.setUp
    login=fixtures.CatalogEditingTests.login
    photos=fixtures.CatalogEditingTests.photos
    fields=fixtures.CatalogEditingTests.fields
    api=fixtures.CatalogEditingTests.api
    draft=fixtures.CatalogEditingTests.draft
    listing=fixtures.CatalogEditingTests.listing
    def search(self,**filters):return self.market.search_products(self.buyer,filters)
    def test_combination_applies_before_pagination_past_old100_limit(self):
        pid=self.listing(edition='第二版',major='软件工程',course='数据结构',college='计算机工程学院')
        with self.market.tx() as c:
            for n in range(500):
                c.execute("INSERT INTO products(seller_id,title,category,price,delivery_fee,delivery,region,data,created,stock_key) SELECT seller_id,?,category,price,delivery_fee,delivery,region,data,created,? FROM products WHERE id=?",('无关教材'+str(n),'search-copy-'+str(n),pid))
        result=self.search(q='数据结构',category='books',edition='第二版',major='软件工程',course='数据结构',college='计算机工程学院',delivery='pickup',min_price='1250',max_price='1250')
        self.assertEqual([x['id'] for x in result['items']],[pid])
        self.assertFalse(result['has_more'])
    def test_stable_price_cursor_excludes_insertions_and_binds_conditions(self):
        for _ in range(5):self.listing(price='12.50')
        first=self.search(sort='price',page_size='2')
        self.assertEqual(len(first['items']),2)
        newer=self.listing(price='0')
        second=self.search(sort='price',page_size='2',cursor=first['next_cursor'])
        third=self.search(sort='price',page_size='2',cursor=second['next_cursor'])
        ids=[x['id'] for p in [first,second,third] for x in p['items']]
        self.assertEqual(len(set(ids)),5);self.assertNotIn(newer,ids)
        with self.assertRaises(DomainError):self.search(sort='price',q='更改查询',cursor=first['next_cursor'])
    def test_delivery_price_includes_fee_for_both_and_free_is_allowed(self):
        a=self.listing(price='0',delivery='both',delivery_fee='8')
        b=self.listing(price='5',delivery='both',delivery_fee='1')
        self.assertEqual([x['id'] for x in self.search(delivery='pickup',sort='price')['items']],[a,b])
        self.assertEqual([x['id'] for x in self.search(delivery='delivery',sort='price')['items']],[b,a])
        self.assertEqual(self.search(delivery='delivery',max_price='600')['items'][0]['id'],b)
    def test_unknown_edition_is_queryable_and_electronics_has_no_book_filters(self):
        a=self.listing();b=self.listing(category='electronics',title='键盘')
        self.assertEqual([x['id'] for x in self.search(category='books',edition='unknown')['items']],[a])
        self.assertEqual([x['id'] for x in self.search(category='electronics')['items']],[b])
    def test_bad_cursors_money_and_empty_result(self):
        for kwargs in [dict(cursor='invalid'),dict(min_price='1.5'),dict(min_price='100',max_price='50'),dict(sort='raw sql'),dict(page_size='-1')]:
            with self.assertRaises(DomainError):self.search(**kwargs)
        self.assertEqual(self.search(q='nothing')['items'],[])
