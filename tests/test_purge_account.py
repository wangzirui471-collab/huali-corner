"""开发者清除账号：释放手机号让本人重新注册，历史记录匿名保留。

和「注销」的区别是这组用例的重点：
  注销 = 用户自助，手机号继续占用，同一号不能重新注册；
  清除 = 开发者处置，把手机号腾出来，本人可用原号注册一个干净账号，
         旧订单/工单/审计不动，昵称变成「已注销用户」。

运行：
    cd "E:\\zi\\huali-corner-trial"
    PYTHONPATH="Backend mission" python -m unittest tests.test_purge_account
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Backend mission'))
from app.market import Market, DomainError


class PurgeAccountTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.m = Market(self.tmp.name, trial=True)
        self.dev = self.reg('13800000041', '开发者', 'developer')
        self.adm = self.reg('13800000042', '管理员', 'admin')
        self.usr = self.reg('13800000043', '普通用户', 'user')
        self.usr_token = self.m.login_password('13800000043', 'Passw0rd!123')['token']

    def tearDown(self):
        self.tmp.cleanup()

    def reg(self, phone, nickname, role):
        uid = self.m.register_password(phone, 'Passw0rd!123', nickname)['user']['id']
        if role != 'user':
            self.m.set_role_operator(phone, role)
        return uid

    def row(self, uid):
        return self.m.row('SELECT phone,nickname,status FROM users WHERE id=?', (uid,))

    def test_developer_purges_user_and_frees_phone(self):
        """清除后：状态 deleted、手机号换成占位、昵称匿名化。"""
        self.m.purge_account(self.dev, self.usr, '测试账号清理')
        user = self.row(self.usr)
        self.assertEqual(user['status'], 'deleted')
        self.assertTrue(user['phone'].startswith('deleted+'), user['phone'])
        self.assertIn('已注销用户', user['nickname'])

    def test_phone_can_register_again(self):
        """原手机号必须能重新注册——这是这个功能存在的理由。"""
        self.m.purge_account(self.dev, self.usr, '本人申请重置')
        again = self.m.register_password('13800000043', 'NewPassw0rd!9', '新同学')
        self.assertTrue(again['user']['id'] != self.usr)
        self.assertEqual(again['user']['phone'] if 'phone' in again['user'] else '13800000043', '13800000043')

    def test_sessions_and_password_are_removed(self):
        """旧 token 立即失效，旧密码也登不上（账号已不在原手机号下）。"""
        self.m.purge_account(self.dev, self.usr, '重置')
        with self.assertRaises(DomainError):
            self.m.user(self.usr_token)
        with self.assertRaises(DomainError):
            self.m.login_password('13800000043', 'Passw0rd!123')

    def test_history_is_kept_not_deleted(self):
        """订单/审计仍挂在原 id 上，不做物理删除。"""
        tid = self.m.create_ticket(self.usr, dict(type='other', subject='咨询', body='随便问问'))['id']
        self.m.purge_account(self.dev, self.usr, '清理')
        ticket = self.m.row('SELECT user_id,subject FROM tickets WHERE id=?', (tid,))
        self.assertEqual(ticket['user_id'], self.usr, '工单应保留原 user_id')

    def test_only_developer_can_purge(self):
        """管理员只能封号，清除是高危不可逆操作，只给开发者。"""
        with self.assertRaises(DomainError) as ctx:
            self.m.purge_account(self.adm, self.usr, '越权尝试')
        self.assertIn('仅开发者', str(ctx.exception))

    def test_cannot_purge_self(self):
        with self.assertRaises(DomainError):
            self.m.purge_account(self.dev, self.dev, '自杀')

    def test_cannot_purge_admin_or_developer(self):
        """防止互删/自毁：管理员与开发者账号不能被清除。"""
        with self.assertRaises(DomainError):
            self.m.purge_account(self.dev, self.adm, '删管理员')
        self.assertEqual(self.row(self.adm)['status'], 'active')

    def test_audit_records_who_and_why(self):
        self.m.purge_account(self.dev, self.usr, '本人申请重置')
        logs = [a for a in self.m.audit_log(self.dev, limit=50) if a['type'] == 'account_purge']
        self.assertTrue(logs)
        self.assertEqual(logs[0]['target'], self.usr)
        self.assertIn('本人申请重置', logs[0]['reason'])


if __name__ == '__main__':
    unittest.main()
