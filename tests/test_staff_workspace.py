"""Staff actions use real SQLite, preserve orders and enforce role boundaries."""
import time
import unittest

import test_publishing as fixtures
from app.market import DomainError


class StaffWorkspaceTests(unittest.TestCase):
    setUp = fixtures.PublishingTests.setUp
    login = fixtures.PublishingTests.login
    photos = fixtures.PublishingTests.photos
    fields = fixtures.PublishingTests.fields
    draft = fixtures.PublishingTests.draft
    api = fixtures.PublishingTests.api

    def listing(self):
        draft = self.draft()
        return self.market.publish_draft(self.seller, draft['id'], draft['version'])['id']

    def support(self):
        uid = self.login('13800000981')
        with self.market.tx() as c:
            c.execute("UPDATE users SET role='support' WHERE id=?", (uid,))
        return uid

    def test_admin_and_support_delist_without_ticket_and_cannot_self_restore(self):
        remove = self.api('moderate_product')
        for actor in [self.admin, self.support()]:
            pid = self.listing()
            offer = self.market.offer(self.buyer, pid, 1000)
            remove(actor, pid, '实拍与描述不一致')
            product = self.market.product(pid)
            self.assertEqual((product['status'], product['removal_reason']), ('removed', 'staff_delist'))
            self.assertNotIn(pid, [p['id'] for p in self.market.products()])
            self.assertEqual(self.market.profile(self.seller)['score'], 100)
            audit = self.market.row("SELECT * FROM audit WHERE product_id=? AND type='product_delist'", (pid,))
            self.assertEqual((audit['actor'], audit['target'], audit['reason']), (actor, self.seller, '实拍与描述不一致'))
            self.assertTrue(any(n['entity_type'] == 'product' and n['entity_id'] == pid for n in self.market.notifications(self.seller)['items']))
            with self.assertRaises(DomainError):
                self.market.set_product_status(self.seller, pid, 'relist')
            with self.assertRaises(DomainError):
                self.market.accept_offer(self.seller, offer['id'], True)
            with self.assertRaises(DomainError):
                self.market.checkout(self.buyer, dict(product_ids=[pid], delivery='pickup', appointment=time.time()+3600, key=str(pid)))

    def test_delist_rejects_ordinary_inactive_blank_and_reserved_without_side_effects(self):
        remove = self.api('moderate_product')
        pid = self.listing()
        for actor, reason, status in [(self.buyer, '举报', 403), (self.seller, '举报', 403), (self.admin, ' ', 400)]:
            with self.assertRaises(DomainError) as caught:
                remove(actor, pid, reason)
            self.assertEqual(caught.exception.status, status)
        worker = self.support()
        with self.market.tx() as c:
            c.execute('UPDATE users SET is_active=0 WHERE id=?', (worker,))
        with self.assertRaises(DomainError):
            remove(worker, pid, '已停用')
        order = self.market.checkout(self.buyer, dict(product_ids=[pid], delivery='pickup', appointment=time.time()+3600, key='reserved'))
        with self.assertRaises(DomainError) as caught:
            remove(self.admin, pid, '交易中')
        self.assertEqual(caught.exception.status, 409)
        self.assertEqual(self.market.order(self.buyer, order['id']), order)
        self.assertEqual(self.market.product(pid)['status'], 'reserved')
        self.assertEqual(self.market.rows("SELECT id FROM audit WHERE type='product_delist'"), [])

    def test_queue_filters_paginates_names_and_preserves_private_case_boundary(self):
        queue = self.api('staff_queue')
        worker = self.support()
        for i in range(4):
            self.market.create_ticket(self.seller, dict(type='other', subject='咨询'+str(i), body='私密正文'))
        ticket = self.market.create_ticket(self.buyer, dict(type='report', subject='需要复核', body='私密举报'))
        self.market.assign_ticket(self.admin, ticket['id'], worker, '排班')
        result = queue(worker, {'scope': 'mine', 'page_size': '2'})
        self.assertEqual(result['total'], 1)
        self.assertEqual(result['items'][0]['assignee_name'], self.market.profile(worker)['nickname'])
        result = queue(worker, {'scope': 'unassigned', 'page_size': '2'})
        self.assertEqual((result['total'], len(result['items'])), (4, 2))
        self.assertTrue(result['items'][0]['restricted'])
        self.assertNotIn('body', result['items'][0])
        next_page = queue(worker, {'scope': 'unassigned', 'page_size': '2', 'page': '2'})
        self.assertFalse({t['id'] for t in result['items']} & {t['id'] for t in next_page['items']})
        with self.assertRaises(DomainError):
            queue(self.buyer, {})

    def test_report_preserves_source_snapshot_and_hides_it_from_unassigned_staff(self):
        pid = self.listing()
        ticket = self.market.create_ticket(self.buyer, dict(type='report', product_id=pid, subject='商品问题', body='核对描述'))
        self.assertIn('sources', ticket)
        original = ticket['sources']['product']['title']
        with self.market.tx() as c:
            c.execute("UPDATE products SET title='之后修改的标题' WHERE id=?", (pid,))
        detail = self.market.ticket(self.admin, ticket['id'])
        self.assertEqual(detail['sources']['product']['title'], original)
        self.assertTrue(detail['sources']['captured'])
        self.assertNotIn('sources', self.market.ticket(self.support(), ticket['id']))

    def test_deactivation_returns_pending_cases_to_queue_atomically(self):
        worker = self.support()
        ticket = self.market.create_ticket(self.buyer, dict(type='other', subject='等待接手', body='待办'))
        self.market.assign_ticket(self.admin, ticket['id'], worker, '排班')
        accounts = self.market.support_accounts(self.admin)
        self.assertEqual(next(u for u in accounts if u['id'] == worker)['pending_count'], 1)
        self.market.set_support_active(self.admin, worker, False)
        result = self.market.ticket(self.admin, ticket['id'])
        self.assertIsNone(result['assignee'])
        self.assertEqual(result['status'], 'open')
        self.assertTrue(self.market.rows("SELECT id FROM audit WHERE ticket_id=? AND type='ticket_handoff'", (ticket['id'],)))

    def test_credit_choices_only_include_verified_related_cases(self):
        choices = self.api('credit_options')
        pid = self.listing()
        report = self.market.create_ticket(self.buyer, dict(type='report', product_id=pid, subject='核实描述', body='证据'))
        unrelated = self.market.create_ticket(self.buyer, dict(type='other', subject='普通咨询', body='无关联'))
        for ticket in [report, unrelated]:
            self.market.resolve_ticket(self.admin, ticket['id'], dict(outcome='resolved', reason='已核实'))
        result = choices(self.admin, self.seller)
        self.assertEqual([t['id'] for t in result['penalty_cases']], [report['id']])
        self.assertEqual(result['user']['score'], 100)
        with self.assertRaises(DomainError):
            choices(self.support(), self.seller)

    def test_backup_status_reports_verified_completion(self):
        status = self.api('operations_status')
        self.assertIsNone(status(self.admin)['last_backup'])
        self.market.backup(self.admin)
        result = status(self.admin)
        self.assertTrue(result['last_backup']['file'].endswith('.zip'))
        self.assertGreater(result['last_backup']['bytes'], 0)
        with self.assertRaises(DomainError):
            status(self.support())
