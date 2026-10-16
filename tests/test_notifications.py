"""Persistent, account-owned transaction alerts; never expose private case content."""
import unittest
import time
import test_publishing as fixtures
from market import DomainError, Market


class NotificationTests(unittest.TestCase):
    setUp = fixtures.PublishingTests.setUp
    login = fixtures.PublishingTests.login
    photos = fixtures.PublishingTests.photos
    fields = fixtures.PublishingTests.fields
    draft = fixtures.PublishingTests.draft
    api = fixtures.PublishingTests.api

    def order(self):
        draft = self.draft()
        product = self.market.publish_draft(self.seller, draft['id'], draft['version'])
        return self.market.checkout(self.buyer, {'product_ids': [product['id']], 'delivery': 'pickup',
            'appointment': time.time() + 7200, 'key': 'test-new-order'})

    def alerts(self, user):
        return self.api('notifications')(user)

    def test_new_order_and_payment_notify_seller_once_and_survive_restart(self):
        order = self.order()
        self.assertEqual(self.alerts(self.seller)['unread_count'], 1)
        self.assertEqual(self.alerts(self.seller)['items'][0]['entity_id'], order['id'])
        for _ in range(2):
            self.market.order_action(self.buyer, order['id'], 'pay', {})
        result = self.alerts(self.seller)
        self.assertEqual(result['unread_count'], 2)
        self.assertTrue(any(item['event_key'].endswith(':paid') for item in result['items']))
        self.assertEqual(self.alerts(self.buyer)['unread_count'], 0)
        self.market = Market(self.tmp.name)
        self.assertEqual(self.alerts(self.seller)['unread_count'], 2)

    def test_read_marker_is_owned_and_mark_all_does_not_swallow_future_alerts(self):
        order = self.order()
        alert = self.alerts(self.seller)['items'][0]
        read = self.api('read_notifications')
        with self.assertRaises(DomainError):
            read(self.buyer, {'id': alert['id']})
        self.assertEqual(self.alerts(self.seller)['unread_count'], 1)
        self.market.order_action(self.buyer, order['id'], 'pay', {})
        read(self.seller, {'through_id': alert['id']})
        self.assertEqual(self.alerts(self.seller)['unread_count'], 1)
        newest = self.alerts(self.seller)['items'][0]
        read(self.seller, {'id': newest['id']})
        read(self.seller, {'id': newest['id']})
        self.assertEqual(self.alerts(self.seller)['unread_count'], 0)

    def test_failed_checkout_does_not_create_alert_or_double_booking(self):
        order = self.order()
        with self.assertRaises(DomainError):
            self.market.checkout(self.buyer, {'product_ids': [order['items'][0]['id']], 'delivery': 'pickup',
                'appointment': time.time() + 7200, 'key': 'duplicate-reserved'})
        self.assertEqual(self.alerts(self.seller)['unread_count'], 1)
        self.assertEqual(self.alerts(self.admin)['unread_count'], 0)

    def test_delivery_completion_and_reschedule_have_actionable_links(self):
        order = self.order()
        self.market.order_action(self.buyer, order['id'], 'pay', {})
        self.market.order_action(self.seller, order['id'], 'reschedule', {'appointment': time.time() + 9000, 'address': 'C1楼下入口'})
        self.assertTrue(any('改约' in item['title'] for item in self.alerts(self.buyer)['items']))
        self.market.order_action(self.seller, order['id'], 'deliver', {})
        self.market.order_action(self.buyer, order['id'], 'receive', {})
        self.assertTrue(any('收货' in item['title'] for item in self.alerts(self.seller)['items']))
        self.assertTrue(all(item['entity_type'] == 'order' for item in self.alerts(self.seller)['items']))

    def test_cancellation_notification_does_not_repeat_on_retry(self):
        order = self.order()
        self.market.order_action(self.buyer, order['id'], 'pay', {})
        for _ in range(2):
            self.market.order_action(self.buyer, order['id'], 'cancel', {})
        alerts = self.alerts(self.seller)['items']
        self.assertEqual(sum(item['event_key'].endswith(':cancelled') for item in alerts), 1)
        self.assertEqual(self.market.order(self.buyer, order['id'])['status'], 'cancelled')

    def test_background_expiry_is_persistent_and_not_repeated(self):
        order = self.order()
        for _ in range(2):
            self.market.tick(order['created'] + 1801)
        self.assertEqual(self.alerts(self.buyer)['unread_count'], 1)
        self.assertEqual(self.alerts(self.seller)['unread_count'], 2)
        self.assertEqual(self.alerts(self.buyer)['items'][0]['entity_id'], order['id'])

    def test_ticket_alerts_are_generic_internal_notes_do_not_notify_participants(self):
        order = self.order()
        self.market.order_action(self.buyer, order['id'], 'pay', {})
        ticket = self.market.create_ticket(self.buyer, {'type': 'refund', 'order_id': order['id'],
            'subject': '不能在锁屏暴露的标题', 'body': '隐私正文', 'refund_mode': 'refund_only'})
        seller_count = self.alerts(self.seller)['unread_count']
        admin_alert = self.alerts(self.admin)['items'][0]
        self.assertEqual(admin_alert['entity_type'], 'ticket')
        self.assertNotIn('隐私', str(admin_alert))
        self.assertNotIn('不能在锁屏', str(admin_alert))
        self.market.reply_ticket(self.admin, ticket['id'], {'body': '内部秘密', 'internal': True})
        self.assertEqual(self.alerts(self.seller)['unread_count'], seller_count)
        self.assertEqual(self.alerts(self.buyer)['unread_count'], 0)
        self.market.reply_ticket(self.admin, ticket['id'], {'body': '对外回复'})
        self.assertEqual(self.alerts(self.seller)['unread_count'], seller_count + 1)
        self.assertEqual(self.alerts(self.buyer)['unread_count'], 1)

    def test_notifications_paginate_and_validate_cursors(self):
        self.api('notifications')
        with self.market.tx() as c:
            for number in range(55):
                self.market.notify(c, [self.seller], 'test:' + str(number), '订单状态有更新', 'order', 1)
        first = self.market.notifications(self.seller)
        self.assertEqual(len(first['items']), 50)
        self.assertTrue(first['has_more'])
        second = self.market.notifications(self.seller, before=first['items'][-1]['id'])
        self.assertEqual(len(second['items']), 5)
        self.assertEqual(len({row['id'] for row in first['items'] + second['items']}), 55)
        with self.assertRaises(DomainError):
            self.market.read_notifications(self.seller, {'through_id': True})
        with self.assertRaises(DomainError):
            self.market.read_notifications(self.seller, {})


if __name__ == '__main__':
    unittest.main()
