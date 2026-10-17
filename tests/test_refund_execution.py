"""Refund execution failures roll back funds, remain visible and allow a safe retry."""
import unittest
from unittest.mock import patch

import test_market as fixtures
from app.market import DomainError, Market


class RefundExecutionTests(unittest.TestCase):
    setUp = fixtures.MarketTests.setUp
    tearDown = fixtures.MarketTests.tearDown
    login = fixtures.MarketTests.login
    photos = fixtures.MarketTests.photos
    listing = fixtures.MarketTests.listing
    checkout = fixtures.MarketTests.checkout

    def refund_case(self):
        order = self.checkout()
        self.m.order_action(self.b, order['id'], 'pay', {})
        ticket = self.m.create_ticket(self.b, dict(type='refund', order_id=order['id'], subject='未交付退款', body='双方同意取消'))
        return order, ticket

    def test_success_repeat_and_amount_conflict(self):
        order, ticket = self.refund_case()
        payload = dict(outcome='refund', reason='核实未交付', amount=order['total'])
        self.m.resolve_ticket(self.staff, ticket['id'], payload)
        self.m.resolve_ticket(self.staff, ticket['id'], payload)
        execution = self.m.ticket(self.b, ticket['id'])['refund_execution']
        self.assertEqual(execution['state'], 'succeeded')
        self.assertEqual(execution['attempts'], 1)
        self.assertTrue(execution['ledger_consistent'])
        with self.assertRaises(DomainError) as caught:
            self.m.resolve_ticket(self.staff, ticket['id'], {**payload, 'amount': 1})
        self.assertEqual(caught.exception.status, 409)
        self.assertEqual(len([x for x in self.m.order(self.b, order['id'])['ledger'] if x['kind']=='refund']), 1)

    def test_failure_rolls_back_then_retry_records_second_attempt(self):
        order, ticket = self.refund_case()
        journal = self.m.journal

        def failing_journal(connection, oid, kind, amount):
            journal(connection, oid, kind, amount)
            if kind == 'refund':
                raise RuntimeError('injected failure after journal; secret detail must not escape')

        payload = dict(outcome='refund', reason='双方同意未交付取消')
        with patch.object(self.m, 'journal', side_effect=failing_journal):
            with self.assertRaises(RuntimeError):
                self.m.resolve_ticket(self.staff, ticket['id'], payload)
        execution = self.m.ticket(self.b, ticket['id'])['refund_execution']
        self.assertEqual(execution['state'], 'failed')
        self.assertEqual(execution['attempts'], 1)
        self.assertEqual(execution['error_code'], 'SIMULATION_EXECUTION_FAILED')
        self.assertNotIn('secret', str(execution))
        self.assertEqual(self.m.order(self.b, order['id'])['status'], 'disputed')
        self.assertFalse(any(x['kind']=='refund' for x in self.m.order(self.b, order['id'])['ledger']))
        self.m.resolve_ticket(self.staff, ticket['id'], payload)
        execution = self.m.ticket(self.b, ticket['id'])['refund_execution']
        self.assertEqual((execution['state'], execution['attempts']), ('succeeded', 2))
        self.assertIsNone(execution['error_code'])

    def test_invalid_or_unauthorized_attempt_is_not_an_execution(self):
        order, ticket = self.refund_case()
        for actor, amount in [(self.b, order['total']), (self.staff, order['total'] + 1)]:
            with self.assertRaises(DomainError):
                self.m.resolve_ticket(actor, ticket['id'], dict(outcome='refund', reason='无效请求', amount=amount))
        execution = self.m.ticket(self.b, ticket['id'])['refund_execution']
        self.assertEqual((execution['state'], execution['attempts']), ('not_started', 0))

    def test_restart_preserves_execution_and_legacy_refund_is_not_fabricated(self):
        order, ticket = self.refund_case()
        self.m.resolve_ticket(self.staff, ticket['id'], dict(outcome='refund', reason='核实退款'))
        restarted = Market(self.tmp.name)
        self.assertEqual(restarted.ticket(self.b, ticket['id'])['refund_execution']['attempts'], 1)
        with self.m.tx() as connection:
            connection.execute('DELETE FROM refund_executions WHERE ticket_id=?', (ticket['id'],))
        legacy = restarted.ticket(self.b, ticket['id'])['refund_execution']
        self.assertEqual(legacy['state'], 'legacy_recorded')
        self.assertTrue(legacy['ledger_consistent'])
        self.assertIsNone(legacy['executed_at'])


if __name__ == '__main__':
    unittest.main()
