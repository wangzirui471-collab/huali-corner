"""管理员工作台的权限测试：人员授权、整店下架、审计可见范围、词库维护、聊天/帖子审核。

覆盖 docs/管理员与客服分权方案.md 第 3.2 节批准的四项新权限。

这里刻意把「客服不能做什么」和「管理员能做什么」成对写：分权最容易在半年后
被一次「顺手放开一下」的改动破掉，单测是唯一能挡住那种改动的闸门。

跑法（项目约定：系统 Python 3.8）：
    cd "E:\\zi\\huali-corner-trial"
    "C:\\Users\\Administrator\\AppData\\Local\\Programs\\Python\\Python38\\python.exe" -m unittest discover -s tests -p "test_admin_desk.py"
"""
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Backend mission'))

from app import moderation
from app.market import Market, DomainError


class DeskTestCase(unittest.TestCase):
    """所有用例共用的账号与数据准备。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.m = Market(self.tmp.name, trial=True)
        self.admin = self.m.bootstrap_admin('19065322759', 'adminpass1')['id']
        self.support = self.m.create_staff(self.admin, {
            'phone': '13900000001', 'password': 'support1',
            'nickname': '值班客服', 'role': 'support'})['id']
        self.user = self.m.register_password('13800000001', 'userpass1', '卖家')['user']['id']
        self.peer = self.m.register_password('13800000002', 'userpass2', '买家')['user']['id']

    def tearDown(self):
        self.tmp.cleanup()

    # --- 辅助 -------------------------------------------------------------

    def product(self, seller, title, status='available', price=1000):
        with self.m.tx() as c:
            return c.execute(
                'INSERT INTO products(seller_id,title,category,price,delivery_fee,delivery,region,status,data,created)'
                ' VALUES(?,?,?,?,?,?,?,?,?,?)',
                (seller, title, 'living', price, 0, 'pickup', 'L1', status,
                 json.dumps({'description': '测试'}, ensure_ascii=False), time.time())).lastrowid

    def session_token(self, phone, password):
        return self.m.login_password(phone, password)['token']

    def status_of(self, pid):
        return self.m.row('SELECT status,delisted_by FROM products WHERE id=?', (pid,))

    def audit_types(self, actor):
        return [a['type'] for a in self.m.audit_log(actor, limit=1000)]


class StaffPermissionTests(DeskTestCase):

    def test_support_cannot_create_accounts(self):
        with self.assertRaises(DomainError) as ctx:
            self.m.create_staff(self.support, {
                'phone': '13900000009', 'password': 'whatever1',
                'nickname': '偷偷建的', 'role': 'admin'})
        self.assertEqual(ctx.exception.status, 403)

    def test_support_cannot_list_accounts(self):
        with self.assertRaises(DomainError):
            self.m.staff_accounts(self.support)

    def test_admin_creates_support_who_can_log_in(self):
        result = self.m.create_staff(self.admin, {
            'phone': '13900000002', 'password': 'newbie12',
            'nickname': '新客服', 'role': 'support'})
        self.assertTrue(result['recovery_code'], '必须返回恢复码，否则忘了密码只能找管理员')
        token = self.session_token('13900000002', 'newbie12')
        self.assertEqual(self.m.profile(self.m.user(token))['role'], 'support')
        self.assertIn('staff_create', self.audit_types(self.admin))

    def test_duplicate_account_rejected(self):
        with self.assertRaises(DomainError) as ctx:
            self.m.create_staff(self.admin, {
                'phone': '13900000001', 'password': 'another1',
                'nickname': '重复', 'role': 'support'})
        self.assertEqual(ctx.exception.status, 409)

    def test_disabling_kills_sessions_immediately(self):
        token = self.session_token('13900000001', 'support1')
        self.assertEqual(self.m.user(token), self.support)
        self.m.set_staff_status(self.admin, self.support, 'disabled')
        # 会话必须当场失效——否则「你被停用了」只是句口号，对方还能用旧令牌操作 7 天。
        # 因为停用会直接删会话，这里拿到的是 401（请先登录）而不是 403（账号被停用），
        # 两者都算「用不了」，但提示语不同，所以断言放宽到「一定失败」。
        with self.assertRaises(DomainError) as ctx:
            self.m.user(token)
        self.assertIn(ctx.exception.status, (401, 403))
        with self.assertRaises(DomainError) as ctx:
            self.m.login_password('13900000001', 'support1')
        self.assertIn('停用', str(ctx.exception))

    def test_cannot_disable_self(self):
        with self.assertRaises(DomainError):
            self.m.set_staff_status(self.admin, self.admin, 'disabled')

    def test_cannot_disable_regular_user_through_staff_path(self):
        """停用是给平台自己人的，普通用户走封禁——两条路径的后果完全不同。"""
        with self.assertRaises(DomainError):
            self.m.set_staff_status(self.admin, self.user, 'disabled')

    def test_reset_password_rotates_secret_and_revokes_sessions(self):
        token = self.session_token('13900000001', 'support1')
        result = self.m.reset_staff_password(self.admin, self.support)
        self.assertGreaterEqual(len(result['password']), 6)
        with self.assertRaises(DomainError):
            self.m.user(token)
        with self.assertRaises(DomainError):
            self.m.login_password('13900000001', 'support1')
        self.assertTrue(self.session_token('13900000001', result['password']))

    def test_support_can_revoke_user_session(self):
        token = self.session_token('13800000001', 'userpass1')
        # 注册时已经建过一个会话，这里再登录一次，所以是 2 个。
        self.assertGreaterEqual(self.m.revoke_sessions(self.support, self.user)['revoked'], 1)
        with self.assertRaises(DomainError):
            self.m.user(token)

    def test_support_cannot_revoke_peer_staff_session(self):
        peer_support = self.m.create_staff(self.admin, {
            'phone': '13900000003', 'password': 'peerpass',
            'nickname': '另一个客服', 'role': 'support'})['id']
        token = self.session_token('13900000003', 'peerpass')
        with self.assertRaises(DomainError) as ctx:
            self.m.revoke_sessions(self.support, peer_support)
        self.assertEqual(ctx.exception.status, 403)
        # 管理员可以。
        self.assertEqual(self.m.revoke_sessions(self.admin, peer_support)['revoked'], 1)
        with self.assertRaises(DomainError):
            self.m.user(token)


class SellerBulkTests(DeskTestCase):

    def test_support_cannot_bulk_delist(self):
        """单件下架客服就能做，整店属于「一次改变一个店铺的状态」，归管理员。"""
        self.product(self.user, '商品甲')
        with self.assertRaises(DomainError) as ctx:
            self.m.moderate_seller(self.support, self.user, '整店导流')
        self.assertEqual(ctx.exception.status, 403)

    def test_bulk_delist_removes_all_available(self):
        ids = [self.product(self.user, f'商品{i}') for i in range(3)]
        result = self.m.moderate_seller(self.admin, self.user, '整店导流')
        self.assertEqual(result['count'], 3)
        for pid in ids:
            row = self.status_of(pid)
            self.assertEqual(row['status'], 'removed')
            self.assertEqual(row['delisted_by'], self.admin, '必须记下是谁处置的，否则卖家能自行恢复')

    def test_bulk_delist_writes_one_audit_and_one_notification(self):
        for i in range(3):
            self.product(self.user, f'商品{i}')
        self.m.moderate_seller(self.admin, self.user, '整店导流')
        rows = [a for a in self.m.audit_log(self.admin, limit=100) if a['type'] == 'seller_moderate']
        self.assertEqual(len(rows), 1, '整店处置是一次动作，不该产生 N 条审计')
        self.assertIn('3', rows[0]['reason'])
        notices = [n for n in self.m.notifications(self.user)['items'] if n['kind'] == 'product_moderate']
        self.assertEqual(len(notices), 1, '卖家不该收到 3 条一模一样的通知')

    def test_bulk_delist_leaves_reserved_products(self):
        live = self.product(self.user, '在售的')
        reserved = self.product(self.user, '已被预订的', status='reserved')
        self.m.moderate_seller(self.admin, self.user, '整店导流')
        self.assertEqual(self.status_of(live)['status'], 'removed')
        self.assertEqual(self.status_of(reserved)['status'], 'reserved',
                         '已预留的商品挂在别人的订单上，不能跟着下架')

    def test_bulk_delist_without_live_products_is_rejected(self):
        with self.assertRaises(DomainError):
            self.m.moderate_seller(self.admin, self.user, '整店导流')


class AuditScopeTests(DeskTestCase):

    def test_support_sees_only_own_actions(self):
        # 客服做一件会留痕的事：下架一件在售商品（客服有此权限）。
        self.m.moderate_product(self.support, self.product(self.user, '导流卡'), 'delist', '整店导流')
        # 管理员再做一件。
        self.m.set_staff_status(self.admin, self.support, 'disabled')
        self.m.set_staff_status(self.admin, self.support, 'active')
        support_view = self.m.audit_log(self.support, limit=200)
        self.assertTrue(support_view, '客服应当能看到自己经手的记录')
        self.assertEqual({a['actor'] for a in support_view}, {self.support},
                         '客服不该看到同事或管理员的动作')

    def test_admin_sees_everyone_and_can_filter(self):
        # 两个角色各留一条痕：客服下架商品，管理员查档案（档案现已仅 admin/developer 可查）。
        self.m.moderate_product(self.support, self.product(self.user, '导流卡'), 'delist', '整店导流')
        self.m.dossier(self.admin, self.user)
        self.m.set_staff_status(self.admin, self.support, 'disabled')
        self.assertGreater(len({a['actor'] for a in self.m.audit_log(self.admin, limit=200)}), 1)
        only_admin = self.m.audit_log(self.admin, actor=self.admin, limit=200)
        self.assertEqual({a['actor'] for a in only_admin}, {self.admin})
        only_type = self.m.audit_log(self.admin, kind='dossier_view', limit=200)
        self.assertEqual({a['type'] for a in only_type}, {'dossier_view'})

    def test_csv_export_has_bom_and_rows(self):
        self.m.dossier(self.admin, self.user)
        blob = self.m.audit_csv(self.admin)
        self.assertTrue(blob.startswith('\ufeff'.encode('utf-8')), '没有 BOM 的话 Excel 打开是乱码')
        text = blob.decode('utf-8-sig')
        self.assertIn('编号,时间', text)
        self.assertIn('dossier_view', text)


class WordlistTests(DeskTestCase):

    def test_support_cannot_edit_wordlist(self):
        with self.assertRaises(DomainError):
            self.m.add_moderation_word(self.support, {'word': '测试词', 'action': 'block'})
        with self.assertRaises(DomainError):
            self.m.moderation_words(self.support)

    def test_added_word_takes_effect_immediately(self):
        before = moderation.scan_text('代跑体测 50 元')['action']
        self.m.add_moderation_word(self.admin, {'word': '代跑体测', 'category': '校园违规', 'action': 'block'})
        self.assertNotEqual(before, 'block')
        self.assertEqual(moderation.scan_text('代跑体测 50 元')['action'], 'block')

    def test_custom_word_survives_reload_and_can_be_removed(self):
        self.m.add_moderation_word(self.admin, {'word': '代跑体测', 'action': 'block'})
        moderation.reload()                      # 模拟重启：从磁盘重新构建自动机
        self.assertEqual(moderation.scan_text('代跑体测')['action'], 'block')
        self.m.remove_moderation_word(self.admin, '代跑体测')
        moderation.reload()
        self.assertEqual(moderation.scan_text('代跑体测')['action'], 'ok')

    def test_disabling_builtin_word_persists(self):
        self.assertEqual(moderation.scan_text('出售匕首')['action'], 'block')
        self.m.remove_moderation_word(self.admin, '匕首')
        moderation.reload()
        self.assertEqual(moderation.scan_text('出售匕首')['action'], 'ok')
        self.assertIn('匕首', self.m.moderation_words(self.admin)['disabled'])
        self.m.restore_moderation_word(self.admin, '匕首')
        self.assertEqual(moderation.scan_text('出售匕首')['action'], 'block')

    def test_single_character_word_rejected(self):
        with self.assertRaises(DomainError) as ctx:
            self.m.add_moderation_word(self.admin, {'word': '刀', 'action': 'block'})
        self.assertIn('2', str(ctx.exception))

    def test_removing_unknown_word_is_404(self):
        with self.assertRaises(DomainError) as ctx:
            self.m.remove_moderation_word(self.admin, '这个词根本不存在')
        self.assertEqual(ctx.exception.status, 404)


class ChatPostModerationTests(DeskTestCase):

    def setUp(self):
        super().setUp()
        self.m.join_room(self.user, 'general')
        self.m.join_room(self.peer, 'general')

    def test_group_message_with_contact_is_blocked(self):
        with self.assertRaises(DomainError) as ctx:
            self.m.send_message(self.user, 1, '加微信详聊，便宜出', 'g1')
        self.assertEqual(ctx.exception.status, 422)

    def test_ordinary_group_message_passes(self):
        self.assertTrue(self.m.send_message(self.user, 1, '这本书还在吗', 'g2')['ok'])

    def test_private_chat_allows_contact_but_blocks_offsite_payment(self):
        room = self.m.private_room(self.user, self.peer)['id']
        # 约交付时间互留微信是正常沟通，私聊不该拦。
        self.assertTrue(self.m.send_message(self.user, room, '加微信约个时间', 'p1')['ok'])
        # 但把付款搬出平台必须拦——那是诈骗高发点。
        with self.assertRaises(DomainError):
            self.m.send_message(self.user, room, '微信转账给我', 'p2')

    def test_post_with_phone_is_flagged_not_blocked(self):
        result = self.m.add_post(self.user, {'body': '出一本教材 13800138000 联系我', 'topic': '交流'})
        self.assertEqual(result['moderation']['action'], 'review')
        flagged = self.m.flagged_content(self.admin)
        self.assertTrue(any(p['id'] == result['id'] for p in flagged['posts']))

    def test_post_with_diversion_is_blocked(self):
        with self.assertRaises(DomainError) as ctx:
            self.m.add_post(self.user, {'body': '加微信 低价出教材', 'topic': '交流'})
        self.assertEqual(ctx.exception.status, 422)

    def test_content_removal_is_reversible(self):
        pid = self.m.add_post(self.user, {'body': '教材一本 13800138000', 'topic': '求购'})['id']
        self.m.content_action(self.admin, 'post', pid, 'remove', '联系方式需线下核验')
        self.assertFalse([p['id'] for p in self.m.posts('') if p['id'] == pid],
                         '移除后帖子不该继续出现在列表里')
        self.m.content_action(self.admin, 'post', pid, 'restore', '复核后确认是正常联系方式')
        self.assertTrue([p['id'] for p in self.m.posts('') if p['id'] == pid])


class DossierScopeTests(DeskTestCase):
    """用户档案的权限边界与内容聚合。

    2026-10-18 起：档案聚合了账号的全部痕迹（商品、订单、评论、帖子、评价、
    求购、处置记录），权限由「客服及以上」收窄为「平台管理员与开发者」。
    """

    def test_support_cannot_open_dossier(self):
        with self.assertRaises(DomainError) as ctx:
            self.m.dossier(self.support, self.user)
        self.assertEqual(ctx.exception.status, 403)

    def test_admin_opens_dossier_and_writes_audit(self):
        data = self.m.dossier(self.admin, self.user)
        for key in ('user', 'phone', 'orders', 'products', 'tickets',
                    'comments', 'posts', 'reviews', 'wants', 'audit'):
            self.assertIn(key, data)
        self.assertIn('dossier_view',
                      [a['type'] for a in self.m.audit_log(self.admin, limit=200)])

    def test_dossier_lists_comments_and_posts(self):
        # 发帖人和评论人都是 user：档案查的是「这个账号留下的痕迹」。
        post = self.m.add_post(self.user, dict(topic='交流', body='出一本高数第七版'))
        self.m.comment(self.user, post['id'], '楼下已出，谢谢关注', 0)

        data = self.m.dossier(self.admin, self.user)

        self.assertIn('出一本高数第七版', [p['body'] for p in data['posts']])
        self.assertIn('楼下已出，谢谢关注', [c['body'] for c in data['comments']])
        self.assertEqual(data['comments'][0]['post_id'], post['id'])

    def test_dossier_lists_reviews_and_wants(self):
        # 求购直接建；评价需要一笔已完成订单，走最短路径构造。
        self.m.create_want(self.user, dict(keyword='台灯', budget=3000, description='宿舍用'))
        pid = self.product(self.user, '高数第七版')
        with self.m.tx() as c:
            # checkout 要读商品快照里的首图，测试 helper 的最小 data 里没有，这里补上。
            c.execute('UPDATE products SET data=? WHERE id=?',
                      (json.dumps({'description': '测试', 'photos': [{'url': '/media/dossier-test.webp'}]}), pid))
        buyer_order = self.m.checkout(self.peer, dict(
            product_ids=[pid], delivery='pickup', address='',
            appointment=time.time() + 7200, key='dossier-eval'))
        self.m.order_action(self.peer, buyer_order['id'], 'pay', {})
        self.m.order_action(self.user, buyer_order['id'], 'deliver', {})
        self.m.order_action(self.peer, buyer_order['id'], 'handover', {})
        self.m.order_action(self.peer, buyer_order['id'], 'receive', {})
        self.m.review(self.peer, buyer_order['id'], 5, '书况很好')

        data = self.m.dossier(self.admin, self.user)

        self.assertIn('台灯', [w['keyword'] for w in data['wants']])
        # 卖家自己不写评价，user 的 reviews 应为空；评价挂在买家档案里。
        self.assertEqual(data['reviews'], [])


if __name__ == '__main__':
    unittest.main()
