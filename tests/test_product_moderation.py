"""平台商品处置（强制下架 / 复核 / 恢复）与用户档案的测试。

覆盖 docs/工作台接口契约.md 第 4 节列出的验收点，其中最容易漏掉、
也最要紧的一条是：**平台下架后，卖家不能自己把商品重新上架**。
没有这条，管理员下架等于白做。
"""
import io
import sys
import tempfile
import time
import unittest
from contextlib import contextmanager
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Backend mission'))

from app.market import Market, DomainError
from PIL import Image


class ModerationActionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.m = Market(self.tmp.name)
        self.seller = self.login('13800000031')
        self.buyer = self.login('13800000032')
        self.staff = self.login('19065322759')          # 平台管理员
        # bootstrap_admin 只在 --trial 下可用（它带 _trial_only 守卫），
        # 演示库里直接改角色来造一个客服账号。
        self.support = self.login('13800000033')
        with self.m.tx() as c:
            c.execute("UPDATE users SET role='support' WHERE id=?", (self.support,))

    def tearDown(self):
        self.tmp.cleanup()

    def login(self, phone):
        code = self.m.request_code(phone)['demo_code']
        return self.m.login(phone, code)['user']['id']

    def photos(self, u):
        ids = []
        for angle, color in zip(['front', 'side', 'top'], ['red', 'green', 'blue']):
            buf = io.BytesIO()
            Image.new('RGB', (100, 100), color).save(buf, 'PNG')
            ids.append(self.m.add_upload(u, buf.getvalue(), angle)['id'])
        return ids

    def listing(self, u=None, **extra):
        u = u or self.seller
        data = dict(title='高等数学 第七版', category='books', price=1500, delivery_fee=300,
                    delivery='both', region='A1楼下', description='实拍教材',
                    photos=self.photos(u), college='计算机工程学院', edition='第七版',
                    publisher='高等教育出版社', condition='有少量笔记', notes='少量',
                    missing='无缺页', accessories='无附件', bought='2024-09', original_price=4500)
        data.update(extra)
        return self.m.publish(u, data)['id']

    def status_of(self, pid):
        return self.m.row('SELECT status,delisted_by FROM products WHERE id=?', (pid,))

    # --- 权限 -------------------------------------------------------------

    def test_ordinary_user_cannot_moderate(self):
        pid = self.listing()
        with self.assertRaises(DomainError) as ctx:
            self.m.moderate_product(self.buyer, pid, 'delist', '看不顺眼')
        self.assertEqual(ctx.exception.status, 403)
        self.assertEqual(self.status_of(pid)['status'], 'available')

    def test_support_role_can_moderate(self):
        """客服也应当能下架引流商品——治理不该卡在管理员一个人身上。"""
        pid = self.listing()
        self.m.moderate_product(self.support, pid, 'delist', '商品描述里留了微信号')
        self.assertEqual(self.status_of(pid)['status'], 'removed')

    def test_support_cannot_restore(self):
        """恢复上架是改判，客服不能自己推翻自己这一侧的处置，否则等于没处置。"""
        pid = self.listing()
        self.m.moderate_product(self.support, pid, 'delist', '疑似引流')
        with self.assertRaises(DomainError) as ctx:
            self.m.moderate_product(self.support, pid, 'restore', '我觉得没事')
        self.assertEqual(ctx.exception.status, 403)
        self.assertIn('管理员', str(ctx.exception))
        self.assertEqual(self.status_of(pid)['status'], 'removed')

    def test_support_can_delist_but_admin_who_restores_is_recorded(self):
        """客服下架、管理员恢复：两段操作各留一条审计，能看出是谁改判的。"""
        pid = self.listing()
        self.m.moderate_product(self.support, pid, 'delist', '疑似引流')
        self.m.moderate_product(self.staff, pid, 'restore', '申诉成立')
        actors = [r['actor'] for r in self.m.rows(
            "SELECT actor FROM audit WHERE type='product_moderate' AND target=? ORDER BY id", (self.seller,))]
        self.assertEqual(actors, [self.support, self.staff])

    def test_removed_products_list_is_staff_only(self):
        pid = self.listing()
        self.m.moderate_product(self.staff, pid, 'delist', '违规')
        self.assertIn(pid, [p['id'] for p in self.m.removed_products(self.staff)])
        self.assertIn(pid, [p['id'] for p in self.m.removed_products(self.support)])
        with self.assertRaises(DomainError) as ctx:
            self.m.removed_products(self.buyer)
        self.assertEqual(ctx.exception.status, 403)

    def test_removed_products_marks_who_delisted(self):
        pid = self.listing()
        self.m.set_product_status(self.seller, pid, 'delist')     # 卖家自己下架
        row = [p for p in self.m.removed_products(self.staff) if p['id'] == pid][0]
        self.assertEqual(row['delisted_by'], 0)
        self.m.set_product_status(self.seller, pid, 'relist')
        self.m.moderate_product(self.staff, pid, 'delist', '平台处置')   # 平台下架
        row = [p for p in self.m.removed_products(self.staff) if p['id'] == pid][0]
        self.assertEqual(row['delisted_by'], self.staff)

    def test_cannot_moderate_own_listing(self):
        pid = self.listing()
        with self.assertRaises(DomainError) as ctx:
            self.m.moderate_product(self.seller, pid, 'delist', '自己的东西')
        self.assertEqual(ctx.exception.status, 403)

    def test_admin_can_delist_own_listing_with_audit_and_reason(self):
        pid = self.listing(self.staff)
        self.m.moderate_product(self.staff, pid, 'delist', '管理员下架自己的测试商品')
        row = self.status_of(pid)
        self.assertEqual((row['status'], row['delisted_by']), ('removed', self.staff))
        audit = self.m.row("SELECT actor,target,reason FROM audit WHERE type='product_moderate' ORDER BY id DESC LIMIT 1")
        self.assertEqual((audit['actor'], audit['target']), (self.staff, self.staff))
        self.assertIn('测试商品', audit['reason'])

    def test_user_can_delist_own_but_not_others_and_admin_still_needs_reason(self):
        own = self.listing()
        other = self.listing(self.staff)
        with self.assertRaises(DomainError) as caught:
            self.m.set_product_status(self.seller, other, 'delist')
        self.assertEqual(caught.exception.status, 403)
        with self.assertRaises(DomainError):
            self.m.moderate_product(self.staff, other, 'delist', ' ')
        self.assertEqual(self.status_of(other)['status'], 'available')
        self.m.set_product_status(self.seller, own, 'delist')
        self.assertEqual((self.status_of(own)['status'], self.status_of(own)['delisted_by']), ('removed', 0))
        self.m.set_product_status(self.seller, own, 'relist')
        self.assertEqual(self.status_of(own)['status'], 'available')

    def test_support_cannot_force_delist_own_but_can_voluntarily_delist(self):
        pid = self.listing(self.support)
        with self.assertRaises(DomainError):
            self.m.moderate_product(self.support, pid, 'delist', '客服自己审核自己')
        self.m.set_product_status(self.support, pid, 'delist')
        self.assertEqual(self.status_of(pid)['delisted_by'], 0)

    def test_stale_delist_read_cannot_override_a_new_checkout(self):
        for management in [False, True]:
            with self.subTest(management=management):
                pid = self.listing()
                other = Market(self.tmp.name)
                original_tx = self.m.tx

                @contextmanager
                def checkout_before_write():
                    other.checkout(self.buyer, dict(product_ids=[pid], delivery='pickup',
                        appointment=time.time()+3600, key='race-'+str(pid)))
                    with original_tx() as connection:
                        yield connection

                with patch.object(self.m, 'tx', checkout_before_write):
                    with self.assertRaises(DomainError) as caught:
                        if management:
                            self.m.moderate_product(self.staff, pid, 'delist', '下架前已有订单')
                        else:
                            self.m.set_product_status(self.seller, pid, 'delist')
                self.assertEqual(caught.exception.status, 409)
                self.assertEqual(self.status_of(pid)['status'], 'reserved')

    def test_missing_product_is_404(self):
        with self.assertRaises(DomainError) as ctx:
            self.m.moderate_product(self.staff, 999999, 'delist', '不存在')
        self.assertEqual(ctx.exception.status, 404)

    # --- 强制下架与「卖家不能自行恢复」 ------------------------------------

    def test_delisted_product_leaves_the_feed(self):
        pid = self.listing()
        self.assertIn(pid, [p['id'] for p in self.m.products()])
        self.m.moderate_product(self.staff, pid, 'delist', '疑似引流')
        self.assertNotIn(pid, [p['id'] for p in self.m.products()])

    def test_seller_cannot_relist_what_platform_delisted(self):
        """这条是整件事的关键：没有它，卖家点一下「重新上架」就绕过去了。"""
        pid = self.listing()
        self.m.moderate_product(self.staff, pid, 'delist', '疑似引流')
        with self.assertRaises(DomainError) as ctx:
            self.m.set_product_status(self.seller, pid, 'relist')
        self.assertEqual(ctx.exception.status, 403)
        self.assertIn('平台处置', str(ctx.exception))
        self.assertEqual(self.status_of(pid)['status'], 'removed')

    def test_seller_can_still_relist_their_own_delisting(self):
        """卖家自己下架的商品不受影响，仍然可以自行恢复。"""
        pid = self.listing()
        self.m.set_product_status(self.seller, pid, 'delist')
        self.assertEqual(self.status_of(pid)['delisted_by'], 0)
        self.m.set_product_status(self.seller, pid, 'relist')
        self.assertEqual(self.status_of(pid)['status'], 'available')

    def test_restore_clears_the_flag_and_returns_control_to_seller(self):
        pid = self.listing()
        self.m.moderate_product(self.staff, pid, 'delist', '误判，先下架')
        self.m.moderate_product(self.staff, pid, 'restore', '申诉成立，恢复上架')
        row = self.status_of(pid)
        self.assertEqual(row['status'], 'available')
        self.assertEqual(row['delisted_by'], 0)
        self.m.set_product_status(self.seller, pid, 'delist')   # 卖家重新拿回控制权

    def test_reserved_product_cannot_be_force_delisted(self):
        pid = self.listing()
        self.m.checkout(self.buyer, dict(product_ids=[pid], delivery='pickup', address='',
            appointment=time.time() + 7200, key='k-mod-1'))
        with self.assertRaises(DomainError):
            self.m.moderate_product(self.staff, pid, 'delist', '想下架已预留的')

    def test_delist_clears_active_promotion(self):
        pid = self.listing()
        self.m.promote(self.seller, pid, '7d')
        self.m.moderate_product(self.staff, pid, 'delist', '违规')
        self.assertEqual(self.m.row('SELECT promoted_until FROM products WHERE id=?', (pid,))['promoted_until'], 0)

    # --- 留痕与通知 -------------------------------------------------------

    def test_delisting_writes_audit_and_notifies_the_seller(self):
        pid = self.listing()
        self.m.moderate_product(self.staff, pid, 'delist', '商品描述里留了微信号')
        record = self.m.row("SELECT * FROM audit WHERE type='product_moderate' ORDER BY id DESC")
        self.assertIsNotNone(record)
        self.assertEqual(record['actor'], self.staff)
        self.assertEqual(record['target'], self.seller)
        self.assertIn('微信号', record['reason'])
        notices = self.m.notifications(self.seller)['items']
        self.assertTrue(any(n['kind'] == 'product_moderate' and '下架' in n['body'] for n in notices))

    def test_reason_is_required(self):
        pid = self.listing()
        with self.assertRaises(DomainError):
            self.m.moderate_product(self.staff, pid, 'delist', '   ')

    # --- 人工复核 ---------------------------------------------------------

    def test_flagged_product_carries_review_marker(self):
        pid = self.listing(title='未拆封避孕套 3只装')
        self.assertTrue(self.m.product(pid, self.seller)['under_review'])

    def test_approve_clears_the_review_marker(self):
        pid = self.listing(title='未拆封避孕套 3只装')
        self.m.review_product(self.staff, pid, 'approve', '确认是普通日用品，放行')
        product = self.m.product(pid, self.seller)
        self.assertFalse(product['under_review'])
        self.assertIn('moderation', product)
        self.assertTrue(product['moderation']['reviewed'])

    def test_approve_notifies_the_seller(self):
        pid = self.listing(title='未拆封避孕套 3只装')
        self.m.review_product(self.staff, pid, 'approve', '放行')
        notices = self.m.notifications(self.seller)['items']
        self.assertTrue(any(n['kind'] == 'product_review' for n in notices))

    def test_reject_delists_and_notifies(self):
        pid = self.listing(title='未拆封避孕套 3只装')
        self.m.review_product(self.staff, pid, 'reject', '校园场景不宜出售')
        row = self.status_of(pid)
        self.assertEqual(row['status'], 'removed')
        self.assertEqual(row['delisted_by'], self.staff)
        notices = self.m.notifications(self.seller)['items']
        self.assertTrue(any(n['kind'] == 'product_moderate' and '下架' in n['body'] for n in notices))

    def test_review_requires_a_pending_marker(self):
        pid = self.listing()          # 干净商品，没有审核标记
        with self.assertRaises(DomainError):
            self.m.review_product(self.staff, pid, 'approve', '随便通过')

    def test_review_cannot_be_done_twice(self):
        pid = self.listing(title='未拆封避孕套 3只装')
        self.m.review_product(self.staff, pid, 'approve', '放行')
        with self.assertRaises(DomainError):
            self.m.review_product(self.staff, pid, 'approve', '再来一次')

    def test_reject_requires_a_reason(self):
        pid = self.listing(title='未拆封避孕套 3只装')
        with self.assertRaises(DomainError):
            self.m.review_product(self.staff, pid, 'reject', '  ')

    def test_invalid_decision_is_rejected(self):
        pid = self.listing(title='未拆封避孕套 3只装')
        with self.assertRaises(DomainError):
            self.m.review_product(self.staff, pid, 'maybe', '拿不准')

    def test_ordinary_user_cannot_review(self):
        pid = self.listing(title='未拆封避孕套 3只装')
        with self.assertRaises(DomainError) as ctx:
            self.m.review_product(self.buyer, pid, 'approve', '我是买家')
        self.assertEqual(ctx.exception.status, 403)


class DossierTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.m = Market(self.tmp.name)
        self.seller = self.login('13800000041')
        self.staff = self.login('19065322759')

    def tearDown(self):
        self.tmp.cleanup()

    def login(self, phone):
        code = self.m.request_code(phone)['demo_code']
        return self.m.login(phone, code)['user']['id']

    def test_ordinary_user_cannot_open_a_dossier(self):
        with self.assertRaises(DomainError) as ctx:
            self.m.dossier(self.seller, self.seller)
        self.assertEqual(ctx.exception.status, 403)

    def test_dossier_returns_profile_and_collections(self):
        data = self.m.dossier(self.staff, self.seller)
        for key in ('user', 'phone', 'orders', 'products', 'tickets', 'audit'):
            self.assertIn(key, data)
        self.assertEqual(data['user']['id'], self.seller)
        self.assertIn('role', data['user'])
        self.assertIn('status', data['user'])

    def test_phone_is_masked(self):
        data = self.m.dossier(self.staff, self.seller)
        self.assertNotIn('13800000041', data['phone'])
        self.assertIn('****', data['phone'])
        self.assertTrue(data['phone'].endswith('0041'))

    def test_viewing_a_dossier_leaves_an_audit_trail(self):
        self.m.dossier(self.staff, self.seller)
        record = self.m.row("SELECT * FROM audit WHERE type='dossier_view' ORDER BY id DESC")
        self.assertIsNotNone(record)
        self.assertEqual(record['actor'], self.staff)
        self.assertEqual(record['target'], self.seller)

    def test_each_view_is_recorded_separately(self):
        self.m.dossier(self.staff, self.seller)
        self.m.dossier(self.staff, self.seller)
        count = self.m.row("SELECT COUNT(*) n FROM audit WHERE type='dossier_view' AND target=?", (self.seller,))['n']
        self.assertEqual(count, 2)


if __name__ == '__main__':
    unittest.main()
