"""在线客服门槛：先提交问题，才允许进入客服会话。

背景：原来「在线客服」谁点谁进，等于一个绕过工单的免费咨询窗口，
客服池被闲聊占满，真正要售后的用户排不上。现在的规则是：
  1. 用户名下有未结案工单 → 才能开会话；
  2. 会话绑定到那张工单（rooms.ticket_id），客服点开就知道在聊什么；
  3. 工单结案后不再放行，需要继续协助要新提交问题。

运行：
    cd "E:\\zi\\huali-corner-trial"
    PYTHONPATH="Backend mission" python -m unittest tests.test_support_gate
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Backend mission'))
from app.market import Market, DomainError


class SupportGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.m = Market(self.tmp.name)
        self.user = self.login('13800000011')
        self.other = self.login('13800000012')

    def tearDown(self):
        self.tmp.cleanup()

    def login(self, phone):
        return self.m.login(phone, self.m.request_code(phone)['demo_code'])['user']['id']

    def ticket(self, uid=None, subject='登录不上'):
        return self.m.create_ticket(uid or self.user,
                                    dict(type='other', subject=subject, body='点登录没反应'))['id']

    def close_ticket(self, tid):
        with self.m.tx() as c:
            c.execute("UPDATE tickets SET status='resolved' WHERE id=?", (tid,))

    def test_chat_requires_a_ticket(self):
        """没有任何工单：直接拒绝，并给出可执行的提示。"""
        with self.assertRaises(DomainError) as ctx:
            self.m.support_room(self.user, None)
        self.assertIn('先提交问题', str(ctx.exception))

    def test_chat_opens_after_ticket(self):
        """提交工单后可以进客服会话，且会话绑定这张工单。"""
        tid = self.ticket()
        room = self.m.support_room(self.user, None)
        self.assertEqual(room['support'], 1)
        self.assertEqual(room['ticket_id'], tid)

    def test_explicit_ticket_is_bound(self):
        """从某张工单页进来时，会话绑定的是那一张，而不是「最近一张」。"""
        first = self.ticket(subject='第一张')
        second = self.ticket(subject='第二张')
        room = self.m.support_room(self.user, first)
        self.assertEqual(room['ticket_id'], first)
        # 再从第二张进来，绑定跟着更新
        room = self.m.support_room(self.user, second)
        self.assertEqual(room['ticket_id'], second)

    def test_closed_ticket_blocks_chat(self):
        """工单结案后不再放行：要聊得重新提交问题。"""
        tid = self.ticket()
        self.m.support_room(self.user, tid)
        self.close_ticket(tid)
        with self.assertRaises(DomainError):
            self.m.support_room(self.user, None)

    def test_cannot_bind_someone_elses_ticket(self):
        """不能拿别人的工单开自己的客服会话。"""
        other_tid = self.ticket(self.other, subject='别人的问题')
        with self.assertRaises(DomainError):
            self.m.support_room(self.user, other_tid)

    def test_reuses_single_room(self):
        """同一用户反复进入只有一个客服会话，不刷房间。"""
        self.ticket()
        first = self.m.support_room(self.user, None)
        second = self.m.support_room(self.user, None)
        self.assertEqual(first['id'], second['id'])


if __name__ == '__main__':
    unittest.main()
