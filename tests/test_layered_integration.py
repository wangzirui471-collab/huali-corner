"""Contracts shared by the user refactor and the earlier feature branch."""
import json
import time
import unittest
import test_publishing as fixtures
from app.market import Market

class LayeredIntegrationTests(unittest.TestCase):
    setUp = fixtures.PublishingTests.setUp
    login = fixtures.PublishingTests.login
    photos = fixtures.PublishingTests.photos
    fields = fixtures.PublishingTests.fields
    api = fixtures.PublishingTests.api
    draft = fixtures.PublishingTests.draft

    def test_electronics_draft_order_edit_and_notifications_coexist(self):
        draft = self.draft(self.fields(category='electronics', title='机械键盘'))
        product = self.market.publish_draft(self.seller, draft['id'], draft['version'])
        other = self.market.publish_draft(self.seller, self.draft()['id'], 1)
        order = self.market.checkout(self.buyer, dict(product_ids=[product['id'],other['id']], delivery='pickup',
            appointment=time.time()+7200, key='layered-order'))
        updated = self.market.update_order(self.buyer, order['id'], dict(appointment=time.time()+10800,
            delivery='pickup', address='', product_ids=[product['id']]))
        self.assertEqual(self.market.product(product['id'])['category'], 'electronics')
        self.assertTrue(updated['notes'])
        self.assertEqual(self.market.notifications(self.seller)['unread_count'], 1)
        self.assertEqual(self.market.list_drafts(self.seller), [])
        restored = Market(self.tmp.name)
        self.assertEqual(restored.order(self.buyer, order['id'])['notes'], updated['notes'])
        self.assertEqual(restored.row('PRAGMA journal_mode')['journal_mode'], 'delete')
