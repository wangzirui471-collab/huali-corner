"""全量账号清单：管理员/开发者能看到所有注册用户，并把任意人改成任意等级。

背景：原来的「人员与权限」只列运营账号（客服/管理员/开发者），普通同学
在后台完全不可见，想把人提成客服只能靠手改库。这里锁住三条：
  1. all_accounts 返回普通用户；
  2. 搜索能按昵称/手机号命中；
  3. 只有管理员/开发者能看，客服与普通用户不行；改身份按四级规则走。

运行：
    cd "E:\\zi\\huali-corner-trial"
    PYTHONPATH="Backend mission" python -m unittest tests.test_all_accounts
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Backend mission'))
from app.market import Market, DomainError


class AllAccountsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.m = Market(self.tmp.name, trial=True)
        self.dev = self.reg('13800000051', '开发者', 'developer')
        self.adm = self.reg('13800000052', '管理员', 'admin')
        self.sup = self.reg('13800000053', '客服', 'support')
        self.usr = self.reg('13800000054', '张同学', 'user')

    def tearDown(self):
        self.tmp.cleanup()

    def reg(self, phone, nickname, role):
        uid = self.m.register_password(phone, 'Passw0rd!123', nickname)['user']['id']
        if role != 'user':
            self.m.set_role_operator(phone, role)
        return uid

    def test_lists_ordinary_users(self):
        """普通用户必须出现在清单里——这才是「看到所有人注册的账号」。"""
        rows = self.m.all_accounts(self.dev)
        ids = [r['id'] for r in rows]
        self.assertIn(self.usr, ids)
        self.assertIn(self.sup, ids)
        # 运营账号与普通用户共用一个字段结构，前端一套渲染即可
        user_row = next(r for r in rows if r['id'] == self.usr)
        self.assertEqual(user_row['role_name'], '普通用户')
        # 在线标记与运营账号视图同名字段，前端一套渲染就能复用
        self.assertIn('online', user_row)

    def test_search_by_nickname_and_phone(self):
        by_nick = self.m.all_accounts(self.dev, '张同学')
        self.assertEqual([r['id'] for r in by_nick], [self.usr])
        by_phone = self.m.all_accounts(self.dev, '13800000054')
        self.assertEqual([r['id'] for r in by_phone], [self.usr])
        none = self.m.all_accounts(self.dev, '不存在的人')
        self.assertEqual(none, [])

    def test_admin_can_view_but_support_cannot(self):
        """管理员也能看；客服不行——他们不需要知道全平台有多少用户。"""
        self.assertTrue(self.m.all_accounts(self.adm))
        with self.assertRaises(DomainError):
            self.m.all_accounts(self.sup)

    def test_promote_user_to_support(self):
        """从全部用户清单把普通同学提成客服，然后能正常降回。"""
        self.m.change_role(self.dev, {'target': self.usr, 'role': 'support'})
        self.assertEqual(self.m.profile(self.usr)['role'], 'support')
        # 提成客服后应出现在运营账号清单里
        staff_ids = [r['id'] for r in self.m.staff_accounts(self.adm)]
        self.assertIn(self.usr, staff_ids)
        self.m.change_role(self.dev, {'target': self.usr, 'role': 'user'})
        self.assertEqual(self.m.profile(self.usr)['role'], 'user')

    def test_developer_can_appoint_admin(self):
        """开发者能授予管理员——「变成任何等级」的核心路径。"""
        self.m.change_role(self.dev, {'target': self.usr, 'role': 'admin'})
        self.assertEqual(self.m.profile(self.usr)['role'], 'admin')

    def test_cannot_change_self(self):
        with self.assertRaises(DomainError):
            self.m.change_role(self.dev, {'target': self.dev, 'role': 'user'})


if __name__ == '__main__':
    unittest.main()
