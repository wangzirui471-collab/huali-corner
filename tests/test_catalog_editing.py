import concurrent.futures
import json
import time
import unittest
import test_publishing as fixtures
from app.market import DomainError

class CatalogEditingTests(unittest.TestCase):
    setUp=fixtures.PublishingTests.setUp
    login=fixtures.PublishingTests.login
    photos=fixtures.PublishingTests.photos
    fields=fixtures.PublishingTests.fields
    api=fixtures.PublishingTests.api
    draft=fixtures.PublishingTests.draft
    def listing(self,**changes):
        draft=self.draft(self.fields(**changes))
        return self.market.publish_draft(self.seller,draft['id'],draft['version'])['id']
    def test_owned_edit_strict_money_three_photos_and_version_conflict(self):
        pid=self.listing();dto=self.market.product_edit(self.seller,pid)
        with self.assertRaises(DomainError):self.market.product_edit(self.buyer,pid)
        fields={**dto['fields'],'price':'18.25'}
        self.market.edit_product(self.seller,pid,dto['version'],fields)
        self.assertEqual(self.market.product(pid)['price'],1825)
        for fields in [{**fields,'price':'1.001'},{**fields,'photos':self.photos(self.buyer)},{**fields,'photos':fields['photos'][:2]}]:
            with self.assertRaises(DomainError):self.market.edit_product(self.seller,pid,dto['version']+1,fields)
        with self.assertRaises(DomainError) as error:self.market.edit_product(self.seller,pid,dto['version'],dto['fields'])
        self.assertEqual(error.exception.status,409)
    def test_reserved_snapshot_is_immutable_and_not_editable(self):
        pid=self.listing();dto=self.market.product_edit(self.seller,pid)
        order=self.market.checkout(self.buyer,dict(product_ids=[pid],delivery='pickup',appointment=time.time()+3600,key='reserved'))
        with self.assertRaises(DomainError):self.market.edit_product(self.seller,pid,dto['version'],{**dto['fields'],'price':'999'})
        self.assertEqual(self.market.order(self.buyer,order['id'])['items'],order['items'])
        with self.assertRaises(DomainError):self.market.set_product_status(self.seller,pid,'delist')
    def test_delist_can_restore_but_low_credit_and_refund_cannot_bypass(self):
        pid=self.listing();self.market.set_product_status(self.seller,pid,'delist')
        self.assertEqual(self.market.product(pid)['removal_reason'],'seller_delist')
        self.market.set_product_status(self.seller,pid,'relist')
        self.market.set_product_status(self.seller,pid,'delist')
        with self.market.tx() as c:c.execute('UPDATE users SET score=59 WHERE id=?',(self.seller,))
        with self.assertRaises(DomainError):self.market.set_product_status(self.seller,pid,'relist')
        with self.market.tx() as c:
            c.execute('UPDATE users SET score=100 WHERE id=?',(self.seller,))
            c.execute("UPDATE products SET removal_reason='refund_removed' WHERE id=?",(pid,))
        with self.assertRaises(DomainError):self.market.set_product_status(self.seller,pid,'relist')
        with self.assertRaises(DomainError):self.market.edit_product(self.seller,pid,self.market.product(pid)['version'],self.fields())
    def test_price_edit_invalidates_pending_and_accepted_unbound_quotes(self):
        pid=self.listing();offer=self.market.offer(self.buyer,pid,100);self.market.accept_offer(self.seller,offer['id'],True)
        dto=self.market.product_edit(self.seller,pid)
        self.market.edit_product(self.seller,pid,dto['version'],{**dto['fields'],'price':'20'})
        with self.assertRaises(DomainError):self.market.accept_offer(self.seller,offer['id'],True)
        order=self.market.checkout(self.buyer,dict(product_ids=[pid],delivery='pickup',appointment=time.time()+3600,key='new-price'))
        self.assertEqual(order['total'],2000)
    def test_distinct_checkout_and_edit_compete_without_mutating_order_snapshot(self):
        pid=self.listing();dto=self.market.product_edit(self.seller,pid)
        def checkout():
            try:return self.market.checkout(self.buyer,dict(product_ids=[pid],delivery='pickup',appointment=time.time()+3600,key='racing-buyer'))
            except DomainError:return None
        def edit():
            try:self.market.edit_product(self.seller,pid,dto['version'],{**dto['fields'],'price':'21'})
            except DomainError:pass
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            a=pool.submit(checkout);b=pool.submit(edit);order=a.result();b.result()
        self.assertTrue(order)
        self.assertEqual(order['total'],self.market.product(pid)['price'])
        self.assertEqual(len(self.market.rows('SELECT id FROM orders')),1)

    def test_cancellation_does_not_reactivate_inventory_of_fraud_blocked_seller(self):
        pid=self.listing();order=self.market.checkout(self.buyer,dict(product_ids=[pid],delivery='pickup',appointment=time.time()+3600,key='blocked'))
        with self.market.tx() as c:c.execute('UPDATE users SET trading_blocked=1 WHERE id=?',(self.seller,))
        self.market.order_action(self.buyer,order['id'],'cancel',{})
        self.assertEqual(self.market.product(pid)['status'],'removed')
        self.assertEqual(self.market.product(pid)['removal_reason'],'credit_block')
