"""好友系统（本地试用版）：申请、同意、私聊门禁。

背景：好友功能一开始只做在 Cloudflare Worker（`app/cloudflare/friend_api.py`），
本地 `server.py` 完全没有这 4 个接口，前端按钮一点就 404。
这组用例把本地实现钉住，规则与线上保持一致：
  1. 申请附言 ≤15 字；不能加自己；重复申请幂等；
  2. 同意之前私聊发不出去，同意之后可以；
  3. 客服会话豁免——顾客与客服无需互为好友。

运行：
    cd "E:\\zi\\huali-corner-trial"
    PYTHONPATH="Backend mission" python -m unittest tests.test_friends_local
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
        self.m = Market(self.tmp.name, trial=True)
        self.a = self.reg('13800000071', '同学A')
        self.b = self.reg('13800000072', '同学B')

    def tearDown(self):
        self.tmp.cleanup()

    def reg(self, phone, nickname):
        return self.m.register_password(phone, 'Passw0rd!123', nickname)['user']['id']

    def test_request_then_accept(self):
        r = self.m.friend_request(self.a, self.b, '想买你的书')
        self.assertEqual(r['state'], 'pending_out')
        incoming = self.m.friends(self.b)['incoming']
        self.assertEqual(len(incoming), 1)
        self.assertEqual(incoming[0]['user_id'], self.a)
        self.m.friend_decide(self.b, incoming[0]['id'], True)
        self.assertTrue(self.m.is_friend(self.a, self.b))
        self.assertEqual(len(self.m.friends(self.a)['friends']), 1)

    def test_message_blank_before_accept(self):
        """没同意之前私聊发不出去——这是好友系统的核心约束。"""
        room = self.m.private_room(self.a, self.b)['id']
        with self.assertRaises(DomainError) as ctx:
            self.m.send_message(self.a, room, '你好', 'k1')
        self.assertIn('好友', str(ctx.exception))

    def test_message_after_accept(self):
        self.m.friend_request(self.a, self.b, '')
        fid = self.m.friends(self.b)['incoming'][0]['id']
        self.m.friend_decide(self.b, fid, True)
        room = self.m.private_room(self.a, self.b)['id']
        self.m.send_message(self.a, room, '你好', 'k2')
        self.assertIn('你好', [x['body'] for x in self.m.messages(self.b, room)])

    def test_reject_keeps_them_strangers(self):
        self.m.friend_request(self.a, self.b, '')
        fid = self.m.friends(self.b)['incoming'][0]['id']
        self.m.friend_decide(self.b, fid, False)
        self.assertFalse(self.m.is_friend(self.a, self.b))
        self.assertEqual(self.m.friend_state(self.a, self.b)['state'], 'none')

    def test_reply_length_limit(self):
        with self.assertRaises(DomainError):
            self.m.friend_request(self.a, self.b, '一' * 16)

    def test_cannot_add_self(self):
        with self.assertRaises(DomainError):
            self.m.friend_request(self.a, self.a, '')

    def test_repeat_request_is_idempotent(self):
        first = self.m.friend_request(self.a, self.b, '第一次')
        second = self.m.friend_request(self.a, self.b, '第二次')
        self.assertEqual(second['state'], 'pending_out')
        self.assertEqual(len(self.m.friends(self.b)['incoming']), 1, '重复申请不应产生第二条')
        self.assertIn('等对方处理', second['message'])

    def test_support_room_exempt(self):
        """客服会话不要求好友：否则顾客和客服互相发不出消息。"""
        room = self.m.private_room(self.a, self.b)['id']
        self.m.rows('SELECT 1')  # 保持连接
        with self.m.tx() as c:
            c.execute("UPDATE rooms SET support=1 WHERE id=?", (room,))
        self.m.send_message(self.a, room, '客服你好', 'k3')


if __name__ == '__main__':
    unittest.main()
