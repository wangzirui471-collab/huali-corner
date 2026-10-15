"""Refund inventory, independent staff and evidence-linked credit workflows."""

import time
import unittest
from pathlib import Path

from market import DomainError, Market
import test_publishing as fixtures


class OperationsTests(unittest.TestCase):
    setUp = fixtures.PublishingTests.setUp
    login = fixtures.PublishingTests.login
    photos = fixtures.PublishingTests.photos
    fields = fixtures.PublishingTests.fields
    draft = fixtures.PublishingTests.draft
    api = fixtures.PublishingTests.api

    def order(self):
        draft = self.draft()
        product = self.market.publish_draft(self.seller, draft['id'], draft['version'])
        order = self.market.checkout(self.buyer, {
            'product_ids': [product['id']], 'delivery': 'pickup',
            'appointment': time.time() + 7200, 'key': 'order-' + str(time.time_ns()),
        })
        self.market.order_action(self.buyer, order['id'], 'pay', {})
        self.market.order_action(self.seller, order['id'], 'deliver', {})
        return product['id'], order

    def refund(self, mode='return_refund'):
        product_id, order = self.order()
        ticket = self.market.create_ticket(self.buyer, {
            'type': 'refund', 'order_id': order['id'], 'subject': '申请退款',
            'body': '双方协商退货', 'refund_mode': mode,
        })
        return product_id, order, ticket

    def verified_report(self):
        product_id = self.market.publish_draft(self.seller, self.draft()['id'], 1)['id']
        ticket = self.market.create_ticket(self.buyer, {
            'type': 'report', 'product_id': product_id, 'subject': '交易违规', 'body': '已提交可核查材料',
        })
        self.market.resolve_ticket(self.admin, ticket['id'], {'outcome': 'resolved', 'reason': '核实独立事件'})
        return ticket

    def appeal(self):
        ticket = self.market.create_ticket(self.seller, {'type': 'appeal', 'subject': '申请复核', 'body': '提交整改或纠错依据'})
        self.market.resolve_ticket(self.admin, ticket['id'], {'outcome': 'resolved', 'reason': '复核依据成立'})
        return ticket

    def test_support_account_is_independent_and_can_be_disabled(self):
        self.assertTrue(callable(getattr(self.market, 'create_support', None)), 'Missing dedicated support accounts')
        self.market = Market(Path(self.tmp.name) / 'trial', trial=True)
        admin = self.market.bootstrap_admin('13900000080', 'OperatorPassword2026!')['id']
        result = self.market.create_support(admin, {'phone': '13900000081', 'password': 'SupportPassword2026!', 'nickname': '客服甲'})
        self.assertEqual(result['role'], 'support')
        self.assertNotIn('password', result)
        session = self.market.login_password('13900000081', 'SupportPassword2026!')
        self.assertEqual(self.market.user(session['token']), result['id'])
        self.market.set_support_active(admin, result['id'], False)
        with self.assertRaises(DomainError):
            self.market.user(session['token'])
        with self.assertRaises(DomainError):
            self.market.login_password('13900000081', 'SupportPassword2026!')
        self.assertEqual(self.market.profile(admin)['role'], 'admin')

    def test_ordinary_user_cannot_provision_support(self):
        create = self.api('create_support')
        with self.assertRaises(DomainError):
            create(self.seller, {'phone': '13900000081', 'password': 'SupportPassword2026!', 'nickname': '越权客服'})

    def test_support_recommends_but_cannot_approve_refund(self):
        _, order, ticket = self.refund('refund_only')
        support_id = self.login('13800000025')
        with self.market.tx() as connection:
            connection.execute("UPDATE users SET role='support' WHERE id=?", (support_id,))
        support = self.market.row("SELECT id FROM users WHERE role='support'")['id']
        with self.assertRaises(DomainError):
            self.market.resolve_ticket(support, ticket['id'], {'outcome': 'refund', 'reason': '越权退款'})
        self.market.resolve_ticket(support, ticket['id'], {
            'outcome': 'request_refund', 'reason': '证据支持退款，提交管理员', 'amount': order['total'],
        })
        self.assertEqual(self.market.ticket(self.buyer, ticket['id'])['status'], 'review')
        self.assertEqual(self.market.rows("SELECT id FROM ledger WHERE kind='refund'"), [])

    def test_claim_cannot_be_stolen_by_another_support_worker(self):
        ticket = self.market.create_ticket(self.seller, {'type': 'other', 'subject': '咨询', 'body': '需要帮助'})
        workers = [self.login('13800000026'), self.login('13800000027')]
        with self.market.tx() as connection:
            connection.executemany("UPDATE users SET role='support' WHERE id=?", [(user_id,) for user_id in workers])
        self.market.resolve_ticket(workers[0], ticket['id'], {'outcome': 'claim', 'reason': '认领'})
        with self.assertRaises(DomainError):
            self.market.resolve_ticket(workers[1], ticket['id'], {'outcome': 'claim', 'reason': '不能抢走'})
        self.assertEqual(self.market.ticket(self.seller, ticket['id'])['assignee'], workers[0])

    def test_return_confirmation_required_before_refund_and_relisting(self):
        product_id, order, ticket = self.refund()
        relist = self.api('relist_draft')
        with self.assertRaises(DomainError):
            relist(self.seller, product_id)
        with self.assertRaises(DomainError):
            self.market.resolve_ticket(self.admin, ticket['id'], {'outcome': 'refund', 'reason': '还没收到实物'})
        action = self.api('return_action')
        with self.assertRaises(DomainError):
            action(self.buyer, ticket['id'], 'confirm_return')
        action(self.buyer, ticket['id'], 'return_sent')
        action(self.seller, ticket['id'], 'confirm_return')
        self.market.resolve_ticket(self.admin, ticket['id'], {'outcome': 'refund', 'reason': '已核实退回实物'})
        draft = relist(self.seller, product_id)
        self.assertEqual(draft['fields']['price'], '12.50')
        new_product = self.market.publish_draft(self.seller, draft['id'], draft['version'])
        self.assertNotEqual(new_product['id'], product_id)
        self.assertEqual(self.market.order(self.buyer, order['id'])['items'][0]['id'], product_id)
        with self.assertRaises(DomainError):
            relist(self.seller, product_id)

    def test_refund_only_does_not_give_seller_inventory(self):
        product_id, _, ticket = self.refund('refund_only')
        self.market.resolve_ticket(self.admin, ticket['id'], {'outcome': 'refund', 'reason': '买家保留物品'})
        with self.assertRaises(DomainError):
            self.api('relist_draft')(self.seller, product_id)

    def test_only_verified_events_penalize_and_duplicates_do_not_stack(self):
        ticket = self.verified_report()
        apply = self.api('apply_penalty')
        result = apply(self.admin, self.seller, ticket['id'], 'hidden_defect', '隐瞒缺页证据成立')
        self.assertEqual(result['credit_score'], 85)
        with self.assertRaises(DomainError):
            apply(self.admin, self.seller, ticket['id'], 'hidden_defect', '重复处理')
        self.assertEqual(self.market.profile(self.seller)['score'], 85)
        with self.assertRaises(DomainError):
            apply(self.admin, self.buyer, ticket['id'], 'fraud', '不能处罚无关举报人')

    def test_first_no_show_warns_then_independent_repeat_deducts(self):
        apply = self.api('apply_penalty')
        result = apply(self.admin, self.seller, self.verified_report()['id'], 'no_show', '首次核实爽约')
        self.assertEqual(result['score_delta'], 0)
        result = apply(self.admin, self.seller, self.verified_report()['id'], 'no_show', '30天内再次核实爽约')
        self.assertEqual(result['score_delta'], -5)
        self.assertEqual(result['credit_score'], 95)

    def test_successful_appeal_reverses_original_event_once(self):
        result = self.api('apply_penalty')(self.admin, self.seller, self.verified_report()['id'], 'hidden_defect', '核实后处理')
        appeal = self.appeal()
        reversed_event = self.api('reverse_penalty')(self.admin, result['audit_id'], appeal['id'], '新证据证明原认定错误')
        self.assertEqual(reversed_event['credit_score'], 100)
        with self.assertRaises(DomainError):
            self.market.reverse_penalty(self.admin, result['audit_id'], appeal['id'], '再次冲回')

    def test_recovery_requires_30_clean_days_and_is_not_repeatable(self):
        self.api('apply_penalty')(self.admin, self.seller, self.verified_report()['id'], 'hidden_defect', '核实')
        recover = self.api('recover_credit')
        appeal = self.appeal()
        with self.assertRaises(DomainError):
            recover(self.admin, self.seller, appeal['id'], '时间不足')
        with self.market.tx() as connection:
            connection.execute("UPDATE audit SET created=? WHERE target=? AND type='credit'", (time.time() - 31 * 86400, self.seller))
        result = recover(self.admin, self.seller, appeal['id'], '整改后30天无新增核实违规')
        self.assertEqual(result['credit_score'], 90)
        with self.assertRaises(DomainError):
            recover(self.admin, self.seller, self.appeal()['id'], '不能重复恢复')


if __name__ == '__main__':
    unittest.main()
