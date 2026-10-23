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

    def test_tools_and_overview(self):
        data = self.m.work_tools(self.owner)
        names = {t['name'] for t in data['tools']}
        for name in ('overview', 'users', 'products', 'orders', 'tickets', 'audit', 'stats', 'user_role'):
            self.assertIn(name, names)
        r = self.m.work_chat(self.owner, '平台概览')
        self.assertIn('活跃用户', r['answer'])
        self.assertTrue(r['items'])

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

    def test_agent_routes_action_to_proposal(self):
        r = self.m.work_chat(self.owner, '把小陈同学降为客服')
        self.assertIsNotNone(r.get('proposal'))
        self.assertIsNotNone(r.get('token'))
        self.assertEqual(self.m.role_of(self.target), 'user')


if __name__ == '__main__':
    unittest.main()
