"""Regressions for the independently reproduced functional audit findings."""
import time
import unittest
import test_publishing as fixtures
from app.market import DomainError


class FunctionalFixTests(unittest.TestCase):
    setUp = fixtures.PublishingTests.setUp
    login = fixtures.PublishingTests.login
    photos = fixtures.PublishingTests.photos
    fields = fixtures.PublishingTests.fields
    draft = fixtures.PublishingTests.draft
    api = fixtures.PublishingTests.api

    def order(self):
        draft = self.draft()
        product = self.market.publish_draft(self.seller, draft['id'], draft['version'])
        return self.market.checkout(self.buyer, dict(product_ids=[product['id']], delivery='pickup',
            appointment=time.time()+7200, key=str(time.time_ns())))

    def worker(self, suffix):
        user = self.login('138000000' + suffix)
        with self.market.tx() as c:
            c.execute("UPDATE users SET role='support' WHERE id=?", (user,))
        return user

    def test_unassigned_support_sees_only_case_summary_and_no_order(self):
        order = self.order()
        ticket = self.market.create_ticket(self.buyer, dict(type='other', order_id=order['id'], subject='咨询', body='私密正文'))
        self.market.reply_ticket(self.admin, ticket['id'], dict(body='内部备注', internal=True))
        worker = self.worker('61')
        summary = self.market.ticket(worker, ticket['id'])
        self.assertTrue(summary.get('restricted'))
        self.assertEqual(summary['messages'], [])
        self.assertNotIn('私密正文', str(summary))
        with self.assertRaises(DomainError): self.market.order(worker, order['id'])
        with self.assertRaises(DomainError): self.market.reply_ticket(worker, ticket['id'], dict(body='未认领不得回复'))
        self.market.resolve_ticket(worker, ticket['id'], dict(outcome='claim', reason='认领咨询'))
        self.assertFalse(self.market.ticket(worker, ticket['id'])['restricted'])
        self.assertEqual(self.market.order(worker, order['id'])['id'], order['id'])
        other = self.worker('62')
        self.market.assign_ticket(self.admin, ticket['id'], other, '转派')
        with self.assertRaises(DomainError): self.market.order(worker, order['id'])
        self.assertTrue(self.market.ticket(worker, ticket['id'])['restricted'])

    def test_seller_cancellation_notifies_buyer_not_actor(self):
        order = self.order()
        seller_count = self.market.notifications(self.seller)['unread_count']
        self.market.order_action(self.seller, order['id'], 'cancel', {})
        notices = self.market.notifications(self.buyer)
        self.assertEqual(notices['unread_count'], 1)
        self.assertIn('卖家', notices['items'][0]['title'])
        self.assertEqual(self.market.notifications(self.seller)['unread_count'], seller_count)

    def test_support_cannot_bypass_scope_using_global_finance_or_backup(self):
        worker=self.worker('64')
        with self.assertRaises(DomainError):self.market.reconcile(worker)
        with self.assertRaises(DomainError):self.market.backup(worker)

    def test_undelivered_return_request_is_normalized_and_can_refund(self):
        order = self.order()
        self.market.order_action(self.buyer, order['id'], 'pay', {})
        ticket = self.market.create_ticket(self.buyer, dict(type='refund', order_id=order['id'],
            subject='未交付退款', body='无需退回', refund_mode='return_refund'))
        self.assertEqual(ticket['refund_mode'], 'refund_only')
        self.market.resolve_ticket(self.admin, ticket['id'], dict(outcome='refund', reason='核实未交付'))
        self.assertEqual(self.market.order(self.buyer, order['id'])['status'], 'refunded')
        with self.assertRaises(DomainError): self.market.relist_draft(self.seller, order['items'][0]['id'])

    def test_legacy_undelivered_return_request_is_not_stuck(self):
        order = self.order()
        self.market.order_action(self.buyer, order['id'], 'pay', {})
        ticket = self.market.create_ticket(self.buyer, dict(type='refund', order_id=order['id'], subject='旧方式', body='旧工单'))
        with self.market.tx() as c: c.execute("UPDATE tickets SET refund_mode='return_refund' WHERE id=?",(ticket['id'],))
        self.market.resolve_ticket(self.admin, ticket['id'], dict(outcome='refund', reason='未交付无需退货'))
        self.assertEqual(self.market.ticket(self.buyer, ticket['id'])['refund_mode'], 'refund_only')

    def test_closed_case_requires_linked_appeal_and_does_not_fake_claim(self):
        order = self.order()
        ticket = self.market.create_ticket(self.buyer, dict(type='other', order_id=order['id'], subject='咨询', body='原问题'))
        self.market.resolve_ticket(self.admin, ticket['id'], dict(outcome='resolved', reason='原处理'))
        with self.assertRaises(DomainError): self.market.reply_ticket(self.buyer, ticket['id'], dict(body='新材料'))
        with self.assertRaises(DomainError): self.market.resolve_ticket(self.admin, ticket['id'], dict(outcome='claim', reason='假重开'))
        appeal = self.market.create_ticket(self.buyer, dict(type='appeal', related_ticket_id=ticket['id'], subject='申请复核', body='新材料'))
        self.assertEqual(appeal['related_ticket_id'], ticket['id'])
        self.assertEqual(appeal['status'], 'open')
        stranger = self.login('13800000063')
        with self.assertRaises(DomainError):
            self.market.create_ticket(stranger, dict(type='appeal', related_ticket_id=ticket['id'], subject='越权', body='不可关联他人工单'))

    def test_private_chat_names_and_unread_are_per_viewer_and_idempotent(self):
        room = self.market.private_room(self.seller, self.buyer)
        for _ in range(2): self.market.send_message(self.seller, room['id'], '你好', 'same-message')
        buyer_room = next(r for r in self.market.rooms(self.buyer)['joined'] if r['id']==room['id'])
        seller_room = next(r for r in self.market.rooms(self.seller)['joined'] if r['id']==room['id'])
        self.assertEqual(buyer_room['name'], self.market.profile(self.seller)['nickname'])
        self.assertEqual(seller_room['name'], self.market.profile(self.buyer)['nickname'])
        self.assertEqual(buyer_room['unread_count'], 1)
        self.assertEqual(seller_room['unread_count'], 0)
        self.assertEqual(self.market.notifications(self.buyer)['unread_count'], 1)
        message = self.market.messages(self.buyer, room['id'])[0]
        self.market.send_message(self.seller, room['id'], '后来消息', 'second')
        self.market.read_messages(self.buyer, room['id'], message['id'])
        self.assertEqual(self.market.notifications(self.buyer)['unread_count'], 1)
        self.assertEqual(self.market.rooms(self.buyer)['joined'][0]['unread_count'], 1)
        with self.assertRaises(DomainError): self.market.read_messages(self.admin, room['id'], message['id'])
        with self.assertRaises(DomainError): self.market.read_messages(self.buyer, room['id'], 999999)


if __name__ == '__main__': unittest.main()
