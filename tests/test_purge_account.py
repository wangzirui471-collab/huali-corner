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

    def test_developer_clears_admin_support_and_user(self):
        """开发者可以清除后三个等级：管理员、客服、普通用户。"""
        sup = self.reg('13800000044', '客服甲', 'support')
        adm2 = self.reg('13800000045', '管理员乙', 'admin')
        usr2 = self.reg('13800000046', '用户乙', 'user')
        for uid, label in ((sup, '客服'), (adm2, '管理员'), (usr2, '普通用户')):
            self.m.purge_account(self.dev, uid, '清理' + label)
            self.assertEqual(self.row(uid)['status'], 'deleted', label)

    def test_admin_clears_support_and_user_only(self):
        """管理员可以清除客服与普通用户，但不能清除同级管理员或开发者。"""
        sup = self.reg('13800000044', '客服甲', 'support')
        self.m.purge_account(self.adm, self.usr, '清理用户')
        self.assertEqual(self.row(self.usr)['status'], 'deleted')
        self.m.purge_account(self.adm, sup, '清理客服')
        self.assertEqual(self.row(sup)['status'], 'deleted')
        adm2 = self.reg('13800000045', '管理员乙', 'admin')
        with self.assertRaises(DomainError) as ctx:
            self.m.purge_account(self.adm, adm2, '管理员互删')
        self.assertIn('同级或更高', str(ctx.exception))
        with self.assertRaises(DomainError):
            self.m.purge_account(self.adm, self.dev, '删开发者')

    def test_cannot_purge_self_or_peer_developer(self):
        with self.assertRaises(DomainError):
            self.m.purge_account(self.dev, self.dev, '自杀')
        with self.assertRaises(DomainError):
            self.m.purge_account(self.adm, self.adm, '自杀')
        dev2 = self.reg('13800000047', '开发者乙', 'developer')
        with self.assertRaises(DomainError) as ctx:
            self.m.purge_account(self.dev, dev2, '删同级开发者')
        self.assertIn('同级或更高', str(ctx.exception))

    def test_support_cannot_purge(self):
        sup = self.reg('13800000048', '客服乙', 'support')
        with self.assertRaises(DomainError) as ctx:
            self.m.purge_account(sup, self.usr, '越权')
        self.assertIn('仅管理员、开发者或所有者', str(ctx.exception))

    def test_audit_records_who_and_why(self):
        self.m.purge_account(self.dev, self.usr, '本人申请重置')
        logs = [a for a in self.m.audit_log(self.dev, limit=50) if a['type'] == 'account_purge']
        self.assertTrue(logs)
        self.assertEqual(logs[0]['target'], self.usr)
        self.assertIn('本人申请重置', logs[0]['reason'])


if __name__ == '__main__':
    unittest.main()
