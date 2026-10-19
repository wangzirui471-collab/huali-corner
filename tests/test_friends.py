"""好友系统回归：申请 → 同意 → 聊天；附言 ≤15 字；非好友禁聊。

规则（2026-10 用户确认）：
  · 加好友要先申请，同意前只能带一条 ≤15 字的文字附言（无图片）；
  · 同意后才能自由私聊；
  · 客服会话不受此限（找平台求助不该先加好友）。
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Backend mission'))
from app.market import Market, DomainError


class FriendTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.m = Market(self.tmp.name)
        self.a = self.login('13800000061')
        self.b = self.login('13800000062')

    def tearDown(self):
        self.tmp.cleanup()

    def login(self, phone):
        return self.m.login(phone, self.m.request_code(phone)['demo_code'])['user']['id']

    def pending_id(self, requester, target):
        return self.m.row('SELECT id FROM friendships WHERE requester=? AND target=?',
                          (requester, target))['id']

    def befriend(self, x, y, message='你好'):
        self.m.friend_request(x, y, message)
        return self.m.friend_decide(y, self.pending_id(x, y), True)

    def test_request_accept_then_chat(self):
        self.assertEqual(self.m.friend_state(self.a, self.b), 'none')
        self.m.friend_request(self.a, self.b, '同班同学')
        self.assertEqual(self.m.friend_state(self.a, self.b), 'pending_out')
        self.assertEqual(self.m.friend_state(self.b, self.a), 'pending_in')
        box = self.m.friends(self.b)
        self.assertEqual([x['nickname'] for x in box['incoming']], [self.m.profile(self.a)['nickname']])
        self.assertEqual(box['incoming'][0]['message'], '同班同学')
        self.m.friend_decide(self.b, box['incoming'][0]['id'], True)
        self.assertEqual(self.m.friend_state(self.a, self.b), 'accepted')
        self.assertEqual(len(self.m.friends(self.a)['friends']), 1)
        room = self.m.private_room(self.a, self.b)
        self.m.send_message(self.a, room['id'], '现在可以聊了', 'f1')

    def test_message_before_accept_is_blocked(self):
        room = self.m.private_room(self.a, self.b)
        with self.assertRaises(DomainError) as ctx:
            self.m.send_message(self.a, room['id'], '先聊两句', 'f2')
        self.assertEqual(ctx.exception.status, 403)
        self.assertIn('好友', str(ctx.exception))

    def test_message_after_reject_is_blocked(self):
        self.m.friend_request(self.a, self.b, '')
        self.m.friend_decide(self.b, self.pending_id(self.a, self.b), False)
        self.assertEqual(self.m.friend_state(self.a, self.b), 'none')      # 被拒后可再申请
        room = self.m.private_room(self.a, self.b)
        with self.assertRaises(DomainError):
            self.m.send_message(self.a, room['id'], '还在吗', 'f3')

    def test_message_limit_is_15_chars(self):
        self.m.friend_request(self.a, self.b, '一二三四五六七八九十一二三四五')   # 15 字
        with self.assertRaises(DomainError) as ctx:
            self.m.friend_request(self.b, self.a, '一二三四五六七八九十一二三四五六')  # 16 字
        self.assertIn('15', str(ctx.exception))

    def test_cannot_add_self_or_duplicate(self):
        with self.assertRaises(DomainError):
            self.m.friend_request(self.a, self.a, '')
        self.m.friend_request(self.a, self.b, '一次')
        again = self.m.friend_request(self.a, self.b, '又一次')
        self.assertEqual(again['state'], 'pending_out')
        self.assertEqual(self.m.row('SELECT COUNT(*) n FROM friendships')['n'], 1)

    def test_want_response_records_want_id(self):
        w = self.m.create_want(self.b, dict(keyword='高等数学', budget=200000, description=''))
        self.m.friend_request(self.a, self.b, '我有一本', w['id'])
        box = self.m.friends(self.b)
        self.assertEqual(box['incoming'][0]['want_id'], w['id'])

    def test_support_room_not_gated_by_friendship(self):
        """客服会话必须豁免好友门槛，否则售后走不通。"""
        # demo 模式初始化时已建好「转角客服」(19065322759)，support_room 按昵称找接待人。
        self.m.create_ticket(self.a, dict(type='report', subject='测试', body='需要帮助'))
        room = self.m.support_room(self.a)
        self.m.send_message(self.a, room['id'], '客服你好', 'f4')

    def test_only_target_can_decide(self):
        self.m.friend_request(self.a, self.b, '')
        fid = self.pending_id(self.a, self.b)
        with self.assertRaises(DomainError) as ctx:
            self.m.friend_decide(self.a, fid, True)
        self.assertEqual(ctx.exception.status, 403)


if __name__ == '__main__':
    unittest.main()
