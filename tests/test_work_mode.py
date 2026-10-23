"""工作模式：工具目录、全量查询、写操作二次确认、owner 权限。"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Backend mission'))

from app.market import Market, DomainError


class WorkModeTests(unittest.TestCase):
    def setUp(self):
        self.m = Market(tempfile.mkdtemp())
        code = self.m.request_code('13800000001')['demo_code']
        self.owner = self.m.login('13800000001', code)['user']['id']
        code2 = self.m.request_code('13800000002')['demo_code']
        self.target = self.m.login('13800000002', code2)['user']['id']
        with self.m.tx() as c:
            c.execute("UPDATE users SET role='owner' WHERE id=?", (self.owner,))
        self.m.create_ticket(self.target, {'type': 'other', 'subject': '演示工单', 'body': '工作模式测试'})
        self.post_id = self.m.add_post(self.target, {'topic': '交流', 'body': '工作模式测试帖'})['id']
        # 造一件在售商品，覆盖置顶/整店下架等写工具的 proposal
        self.m.ai_office_publish(self.owner, self.m.ai_office_generate(self.owner, '宿舍好物', 1)['items'])

    def test_tools_and_overview(self):
        data = self.m.work_tools(self.owner)
        names = {t['name'] for t in data['tools']}
        for name in ('overview', 'users', 'products', 'orders', 'tickets', 'audit', 'stats', 'user_role'):
            self.assertIn(name, names)
        r = self.m.work_chat(self.owner, '平台概览')
        self.assertIn('活跃用户', r['answer'])
        self.assertTrue(r['items'])

    def test_extended_read_tools(self):
        for tool in ('rooms', 'posts', 'ledger', 'sellers', 'offers', 'moderation', 'credit'):
            r = self.m.work_call(self.owner, tool, {})
            self.assertIn('answer', r, tool)
            self.assertIn('items', r, tool)

    def test_extended_write_tools_need_token(self):
        product = self.m.row("SELECT id,promoted_until,status FROM products WHERE status='available' LIMIT 1")
        if not product:
            self.skipTest('no available product in seed')
        cases = [
            ('user_ban', {'target': self.target, 'banned': True, 'reason': '测试'}),
            ('product_promote', {'id': product['id'], 'tier': '1d', 'reason': '测试'}),
            ('product_batch_delist', {'seller': self.target, 'reason': '测试'}),
            ('content_remove', {'kind': 'post', 'id': self.post_id, 'reason': '测试'}),
            ('demo_cleanup', {}),
            ('backup', {}),
        ]
        for tool, args in cases:
            r = self.m.work_call(self.owner, tool, args)
            self.assertIsNotNone(r.get('token'), tool)
            self.assertIsNotNone(r.get('proposal'), tool)
        # proposal 阶段不写库
        self.assertEqual(self.m.row('SELECT status FROM users WHERE id=?', (self.target,))['status'], 'active')
        self.assertEqual(self.m.row('SELECT removed FROM posts WHERE id=?', (self.post_id,))['removed'], 0)
        self.assertEqual(self.m.row('SELECT promoted_until FROM products WHERE id=?', (product['id'],))['promoted_until'] or 0, product['promoted_until'] or 0)

    def test_read_tools(self):
        users = self.m.work_call(self.owner, 'users', {'q': '小陈'})
        self.assertTrue(users['items'])
        tickets = self.m.work_call(self.owner, 'tickets', {'status': 'open'})
        self.assertIn('演示工单', tickets['answer'] + str(tickets['items']))
        stats = self.m.work_call(self.owner, 'stats', {'days': 7})
        self.assertIn('最近 7 天新增', stats['answer'])

    def test_write_requires_token_then_executes(self):
        r = self.m.work_call(self.owner, 'user_role', {'target': self.target, 'role': 'support'})
        self.assertIsNotNone(r.get('token'))
        self.assertEqual(self.m.role_of(self.target), 'user')
        out = self.m.work_confirm(self.owner, r['token'])
        self.assertTrue(out['ok'])
        self.assertEqual(self.m.role_of(self.target), 'support')

    def test_owner_target_blocked_before_proposal(self):
        with self.assertRaises(DomainError):
            self.m.work_call(self.owner, 'user_role', {'target': self.owner, 'role': 'support'})
        with self.assertRaises(DomainError):
            self.m.work_call(self.owner, 'user_disable', {'target': self.owner})
        with self.assertRaises(DomainError):
            self.m.work_call(self.owner, 'user_role', {'target': self.target, 'role': 'owner'})

    def test_non_owner_forbidden(self):
        with self.assertRaises(DomainError):
            self.m.work_tools(self.target)
        with self.assertRaises(DomainError):
            self.m.work_chat(self.target, '平台概览')
        with self.assertRaises(DomainError):
            self.m.work_call(self.target, 'users', {})

    def test_invalid_token(self):
        with self.assertRaises(DomainError):
            self.m.work_confirm(self.owner, 'not-a-token')

    def test_ban_is_not_disable(self):
        r = self.m.work_chat(self.owner, '封禁 小陈同学')
        self.assertIn('封禁', r['proposal']['summary'])
        self.assertEqual(self.m.row('SELECT status FROM users WHERE id=?', (self.target,))['status'], 'active')

    def test_agent_routes_action_to_proposal(self):
        r = self.m.work_chat(self.owner, '把小陈同学降为客服')
        self.assertIsNotNone(r.get('proposal'))
        self.assertIsNotNone(r.get('token'))
        self.assertEqual(self.m.role_of(self.target), 'user')


if __name__ == '__main__':
    unittest.main()
