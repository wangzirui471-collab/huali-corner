"""本地 owner（L1）与 AI 办公助手：权限、待确认动作、演示商品入库。"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Backend mission'))

from app.market import Market, DomainError


class OwnerOfficeTests(unittest.TestCase):
    def setUp(self):
        self.m = Market(tempfile.mkdtemp())
        code = self.m.request_code('13800000001')['demo_code']
        self.owner = self.m.login('13800000001', code)['user']['id']
        code2 = self.m.request_code('13800000002')['demo_code']
        self.target = self.m.login('13800000002', code2)['user']['id']
        with self.m.tx() as c:
            c.execute("UPDATE users SET role='owner' WHERE id=?", (self.owner,))
        self.m.create_ticket(self.target, {'type': 'other', 'subject': '演示工单', 'body': '用于办公助手测试'})

    def test_office_snapshot_and_query(self):
        r = self.m.ai_office(self.owner, '平台数据')
        self.assertIn('待处理工单', r['answer'])
        self.assertEqual(r['mode'], 'rule')
        for key in ('pending_tickets', 'processing_tickets', 'users', 'products', 'orders_24h'):
            self.assertIn(key, r['stats'])
        r2 = self.m.ai_office(self.owner, '待处理工单')
        self.assertTrue(r2['items'])

    def test_role_action_needs_confirmation(self):
        r = self.m.ai_office(self.owner, '把小陈同学降为客服')
        self.assertIsNotNone(r['proposal'])
        self.assertEqual(r['proposal']['kind'], 'role')
        self.assertEqual(r['proposal']['target'], self.target)
        # 未确认前不写库
        self.assertEqual(self.m.role_of(self.target), 'user')
        out = self.m.ai_office_confirm(self.owner, 'role', self.target, 'support')
        self.assertTrue(out['ok'])
        self.assertEqual(self.m.role_of(self.target), 'support')

    def test_owner_cannot_be_demoted_or_disabled(self):
        with self.assertRaises(DomainError):
            self.m.ai_office_confirm(self.owner, 'disable', self.owner)
        with self.assertRaises(DomainError):
            self.m.change_role(self.owner, {'target': self.owner, 'role': 'support'})
        with self.assertRaises(DomainError):
            self.m.ban_user(self.owner, self.owner, True, 'test')
        with self.assertRaises(DomainError):
            self.m.purge_account(self.owner, self.owner, 'test')
        with self.assertRaises(DomainError):
            self.m.deactivate(self.owner)

    def test_non_owner_cannot_use_office(self):
        with self.assertRaises(DomainError):
            self.m.ai_office(self.target, '平台数据')
        with self.assertRaises(DomainError):
            self.m.ai_office_generate(self.target, '宿舍好物', 2)
        with self.assertRaises(DomainError):
            self.m.ai_office_publish(self.target, [])

    def test_generate_preview_then_publish(self):
        r = self.m.ai_office_generate(self.owner, '宿舍好物', 3)
        self.assertEqual(len(r['items']), 3)
        self.assertEqual(r['mode'], 'rule')
        # 预览不写库
        before = len(self.m.products(None, {'seller': str(self.owner)}))
        out = self.m.ai_office_publish(self.owner, r['items'])
        self.assertEqual(out['count'], 3)
        after = self.m.products(None, {'seller': str(self.owner)})
        self.assertEqual(len(after), before + 3)
        self.assertTrue(any(str(p.get('virtual')) in ('True', '1') for p in after))

    def test_owner_can_manage_developer_but_not_assign_owner(self):
        self.m.change_role(self.owner, {'target': self.target, 'role': 'developer'})
        self.assertEqual(self.m.role_of(self.target), 'developer')
        with self.assertRaises(DomainError):
            self.m.change_role(self.owner, {'target': self.target, 'role': 'owner'})


if __name__ == '__main__':
    unittest.main()
