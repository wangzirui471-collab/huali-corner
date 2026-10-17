"""四级角色权限：开发者 / 管理员 / 客服 / 用户 的分权回归测试。

对应 2026-10-17 新增的角色层级（AccountService.ROLE_RANK）：
  user(0) < support(1) < admin(2) < developer(3)

权限约定：
  - 开发者：任命/降级管理员、设/废客服、封号等全部管理员权限；
  - 管理员：设置/废除客服、封号；不能动管理员与开发者、不能任命管理员；
  - 客服：日常处置；用户：无后台权限。
运行：python -m unittest discover -s tests -p "test_role_hierarchy.py"
"""
import sys, tempfile, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Backend mission'))
from app.market import Market, DomainError


class RoleHierarchyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.m = Market(self.tmp.name, trial=True)
        self.dev = self.reg('13800000031', '开发者', 'developer')
        self.adm = self.reg('13800000032', '管理员', 'admin')
        self.sup = self.reg('13800000033', '客服', 'support')
        self.usr = self.reg('13800000034', '用户', 'user')

    def tearDown(self):
        self.tmp.cleanup()

    def reg(self, phone, nickname, role):
        uid = self.m.register_password(phone, 'Passw0rd!123', nickname)['user']['id']
        if role != 'user':
            self.m.set_role_operator(phone, role)
        return uid

    def role(self, uid):
        return self.m.profile(uid)['role']

    # --- 角色授予 ----------------------------------------------------------

    def test_developer_can_promote_user_to_admin(self):
        self.m.change_role(self.dev, {'target': self.usr, 'role': 'admin'})
        self.assertEqual(self.role(self.usr), 'admin')

    def test_developer_can_demote_admin_to_user(self):
        self.m.change_role(self.dev, {'target': self.adm, 'role': 'user'})
        self.assertEqual(self.role(self.adm), 'user')

    def test_admin_can_set_and_revoke_support(self):
        self.m.change_role(self.adm, {'target': self.usr, 'role': 'support'})
        self.assertEqual(self.role(self.usr), 'support')
        self.m.change_role(self.adm, {'target': self.usr, 'role': 'user'})
        self.assertEqual(self.role(self.usr), 'user')

    def test_admin_cannot_appoint_admin(self):
        with self.assertRaises(DomainError):
            self.m.change_role(self.adm, {'target': self.sup, 'role': 'admin'})

    def test_admin_cannot_touch_developer(self):
        with self.assertRaises(DomainError):
            self.m.change_role(self.adm, {'target': self.dev, 'role': 'user'})

    def test_admin_cannot_touch_peer_admin(self):
        other = self.reg('13800000035', '管理员2', 'admin')
        with self.assertRaises(DomainError):
            self.m.change_role(self.adm, {'target': other, 'role': 'user'})

    def test_support_cannot_change_roles(self):
        with self.assertRaises(DomainError):
            self.m.change_role(self.sup, {'target': self.usr, 'role': 'support'})

    def test_cannot_change_self(self):
        with self.assertRaises(DomainError):
            self.m.change_role(self.dev, {'target': self.dev, 'role': 'user'})

    # --- 最后一名开发者保护 --------------------------------------------------

    def test_last_developer_cannot_be_demoted(self):
        with self.assertRaises(DomainError):
            self.m.change_role(self.dev, {'target': self.dev, 'role': 'admin'})

    def test_developer_can_demote_another_developer(self):
        other = self.reg('13800000036', '开发者2', 'developer')
        self.m.change_role(self.dev, {'target': other, 'role': 'admin'})
        self.assertEqual(self.role(other), 'admin')

    # --- 封禁与门卫扩展 ------------------------------------------------------

    def test_admin_cannot_ban_developer(self):
        with self.assertRaises(DomainError):
            self.m.ban_user(self.adm, self.dev, True, '试图封开发者')

    def test_developer_can_ban_user(self):
        self.m.ban_user(self.dev, self.usr, True, '违规')
        self.assertEqual(self.m.profile(self.usr)['status'], 'banned')

    def test_create_staff_admin_cannot_create_admin(self):
        with self.assertRaises(DomainError):
            self.m.create_staff(self.adm, {'phone': '13800000037', 'nickname': '新管理员',
                                           'role': 'admin', 'password': 'Passw0rd!123'})

    def test_create_staff_developer_can_create_admin(self):
        r = self.m.create_staff(self.dev, {'phone': '13800000038', 'nickname': '新管理员',
                                           'role': 'admin', 'password': 'Passw0rd!123'})
        self.assertEqual(self.m.profile(r['id'])['role'], 'admin')

    def test_staff_accounts_include_developer(self):
        rows = self.m.staff_accounts(self.dev)
        roles = {r['role'] for r in rows}
        self.assertIn('developer', roles)
        self.assertIn('admin', roles)


if __name__ == '__main__':
    unittest.main()
