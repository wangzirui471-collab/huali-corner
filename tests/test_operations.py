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

    def test_private_evidence_is_only_readable_to_authorized_case_participants(self):
        import io
        from PIL import Image
        content = io.BytesIO()
        Image.new('RGB', (60, 60), 'orange').save(content, 'PNG')
        upload = self.market.add_upload(self.buyer, content.getvalue(), 'proof', True)
        _, order = self.order()
        ticket = self.market.create_ticket(self.buyer, {
            'type': 'refund', 'order_id': order['id'], 'subject': '图片证据', 'body': '已遮挡个人信息',
            'evidence': [upload['id']],
        })
        self.assertIn('evidence', ticket, 'Missing private case evidence')
        self.assertEqual(ticket['evidence'][0]['id'], upload['id'])
        self.assertTrue(self.api('can_view_evidence')(self.seller, upload['id']))
        stranger = self.login('13800000028')
        self.assertFalse(self.market.can_view_evidence(stranger, upload['id']))
        with self.assertRaises(DomainError):
            self.market.create_ticket(self.seller, {
                'type': 'other', 'subject': '不能借用他人证据', 'body': '越权', 'evidence': [upload['id']],
            })

    def test_admin_can_assign_case_but_not_to_its_own_participant(self):
        assign = self.api('assign_ticket')
        ticket = self.market.create_ticket(self.seller, {'type': 'other', 'subject': '咨询', 'body': '需要协助'})
        support = self.login('13800000029')
        with self.market.tx() as connection:
            connection.execute("UPDATE users SET role='support' WHERE id=?", (support,))
        assign(self.admin, ticket['id'], support, '排班转派')
        self.assertEqual(self.market.ticket(self.seller, ticket['id'])['assignee'], support)
        with self.assertRaises(DomainError):
            assign(self.seller, ticket['id'], support, '普通人不能转派')

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

    def test_review_and_refund_recommendation_cannot_steal_assignment(self):
        _, _, ticket = self.refund()
        workers = [self.login('13800000026'), self.login('13800000027')]
        with self.market.tx() as connection:
            connection.executemany("UPDATE users SET role='support' WHERE id=?", [(worker,) for worker in workers])
        self.market.resolve_ticket(workers[0], ticket['id'], {'outcome': 'claim', 'reason': '先认领'})
        for outcome in ['review', 'request_refund']:
            with self.assertRaises(DomainError):
                self.market.resolve_ticket(workers[1], ticket['id'], {'outcome': outcome, 'reason': '不能接管他人工单'})
        self.assertEqual(self.market.ticket(self.seller, ticket['id'])['assignee'], workers[0])

    def test_historical_return_cannot_relist_stock_kept_by_next_buyer(self):
        original_id, _, ticket = self.refund()
        self.market.return_action(self.buyer, ticket['id'], 'return_sent')
        self.market.return_action(self.seller, ticket['id'], 'confirm_return')
        self.market.resolve_ticket(self.admin, ticket['id'], {'outcome': 'refund', 'reason': '第一次已退回'})
        draft = self.market.relist_draft(self.seller, original_id)
        second = self.market.publish_draft(self.seller, draft['id'], draft['version'])
        order = self.market.checkout(self.buyer, {'product_ids': [second['id']], 'delivery': 'pickup',
            'appointment': time.time() + 7200, 'key': 'second-sale'})
        self.market.order_action(self.buyer, order['id'], 'pay', {})
        self.market.order_action(self.seller, order['id'], 'deliver', {})
        case = self.market.create_ticket(self.buyer, {'type': 'refund', 'order_id': order['id'],
            'subject': '第二次仅退款', 'body': '买家保留实物', 'refund_mode': 'refund_only'})
        self.market.resolve_ticket(self.admin, case['id'], {'outcome': 'refund', 'reason': '仅退款，不退回'})
        for product_id in [original_id, second['id']]:
            with self.assertRaises(DomainError):
                self.market.relist_draft(self.seller, product_id)

    def test_legacy_free_credit_endpoint_cannot_bypass_warning_rules(self):
        ticket = self.verified_report()
        self.market.apply_penalty(self.admin, self.seller, ticket['id'], 'no_show', '首次警告')
        with self.assertRaises(DomainError):
            self.market.credit_action(self.admin, self.seller, -50, '不能绕过规则扣分', ticket['id'])
        self.assertEqual(self.market.profile(self.seller)['score'], 100)

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
        copied = self.market.save_draft(self.seller, {
            'fields': draft['fields'], 'version': 0, 'copy_from_id': draft['id'],
        })
        self.assertEqual(copied['source_product_id'], product_id)
        new_product = self.market.publish_draft(self.seller, draft['id'], draft['version'])
        self.assertNotEqual(new_product['id'], product_id)
        self.assertEqual(self.market.order(self.buyer, order['id'])['items'][0]['id'], product_id)
        with self.assertRaises(DomainError):
            relist(self.seller, product_id)
        with self.assertRaises(DomainError):
            self.market.publish_draft(self.seller, copied['id'], copied['version'])

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
