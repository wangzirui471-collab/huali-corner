"""Order progress reads actual records without changing the trade state."""
import time
import unittest

import test_market as fixtures


class TradeProgressTests(unittest.TestCase):
    setUp = fixtures.MarketTests.setUp
    tearDown = fixtures.MarketTests.tearDown
    login = fixtures.MarketTests.login
    photos = fixtures.MarketTests.photos
    listing = fixtures.MarketTests.listing
    checkout = fixtures.MarketTests.checkout

    def test_payment_delivery_and_receipt_have_separate_progress(self):
        order = self.checkout()
        self.assertEqual(order['progress']['order']['next_actor'], 'buyer')
        self.assertEqual(order['progress']['funds']['state'], 'not_paid')
        oid = order['id']
        paid = self.m.order_action(self.b, oid, 'pay', {})
        self.assertEqual(paid['progress']['delivery']['next_actor'], 'seller')
        self.assertEqual(paid['progress']['funds']['held_cents'], paid['total'])
        delivered = self.m.order_action(self.a, oid, 'deliver', {})
        self.assertIsNone(delivered['progress']['delivery']['auto_receipt_at'])
        handover = self.m.order_action(self.b, oid, 'handover', {})
        self.assertEqual(handover['progress']['delivery']['auto_receipt_at'], handover['handover_at'] + 86400)
        completed = self.m.order_action(self.b, oid, 'receive', {})
        self.assertEqual(completed['progress']['funds']['state'], 'settled')
        self.assertEqual(completed['progress']['delivery']['state'], 'received')

    def test_dispute_preserves_handover_but_pauses_countdown(self):
        oid = self.checkout()['id']
        self.m.order_action(self.b, oid, 'pay', {})
        self.m.order_action(self.a, oid, 'deliver', {})
        self.m.order_action(self.b, oid, 'handover', {})
        ticket = self.m.create_ticket(self.b, dict(type='refund', order_id=oid, subject='缺页', body='申请核查'))
        progress = self.m.order(self.b, oid)['progress']
        self.assertEqual(progress['after_sales']['ticket_id'], ticket['id'])
        self.assertEqual(progress['after_sales']['next_actor'], 'staff')
        self.assertEqual(progress['delivery']['state'], 'handed_over')
        self.assertIsNone(progress['delivery']['auto_receipt_at'])
        self.assertIsNone(progress['delivery']['next_actor'])
        self.assertEqual(progress['funds']['state'], 'on_hold')

    def test_cancelled_paid_and_unpaid_are_distinct(self):
        for pay in [False, True]:
            oid = self.checkout()['id']
            if pay:
                self.m.order_action(self.b, oid, 'pay', {})
            progress = self.m.order_action(self.b, oid, 'cancel', {})['progress']
            self.assertEqual(progress['order']['state'], 'cancelled')
            self.assertEqual(progress['funds']['state'], 'refunded' if pay else 'not_paid')
            self.assertTrue(progress['funds']['consistent'])

    def test_progress_is_read_only_and_retains_original_fields(self):
        oid = self.checkout()['id']
        before = self.m.row('SELECT * FROM orders WHERE id=?', (oid,))
        count = self.m.row('SELECT COUNT(*) AS n FROM ledger')['n']
        for _ in range(3):
            order = self.m.order(self.b, oid)
            self.assertIn('items', order)
            self.assertIn('ledger', order)
            self.assertTrue(order['progress']['simulation'])
        self.assertEqual(before, self.m.row('SELECT * FROM orders WHERE id=?', (oid,)))
        self.assertEqual(count, self.m.row('SELECT COUNT(*) AS n FROM ledger')['n'])

    def test_completed_then_refunded_keeps_delivery_history_and_balance(self):
        oid = self.checkout()['id']
        self.m.order_action(self.b, oid, 'pay', {})
        self.m.order_action(self.a, oid, 'deliver', {})
        self.m.order_action(self.b, oid, 'receive', {})
        ticket = self.m.create_ticket(self.b, dict(type='refund', order_id=oid, subject='错版', body='双方协商仅退款'))
        self.m.resolve_ticket(self.staff, ticket['id'], dict(outcome='refund', amount=500, reason='核实部分退款'))
        progress = self.m.order(self.b, oid)['progress']
        self.assertEqual(progress['delivery']['state'], 'received')
        self.assertEqual(progress['funds']['state'], 'partially_refunded')
        self.assertTrue(progress['funds']['consistent'])
        self.assertEqual(progress['funds']['held_cents'], 0)

    def test_inconsistent_ledger_does_not_claim_success(self):
        oid = self.checkout()['id']
        self.m.order_action(self.b, oid, 'pay', {})
        with self.m.tx() as connection:
            connection.execute("UPDATE ledger SET amount=amount+1 WHERE order_id=? AND kind='payment'", (oid,))
        funds = self.m.order(self.b, oid)['progress']['funds']
        self.assertFalse(funds['consistent'])
        self.assertEqual(funds['state'], 'needs_review')


if __name__ == '__main__':
    unittest.main()
