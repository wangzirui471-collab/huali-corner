"""已读回执回归：/api/messages/receipts 的位点语义。

设计约束（前端据此算「几人已读」）：
  · total 只数「除自己以外」的成员，群聊 3 人时是 2；
  · readers 给出每个成员的 last_read_id，前端按 last_read_id >= 消息 id 判断；
  · 拉取消息会把已读位点前移（messages() 里的 _mark_room_read），
    所以「对方打开过这个会话」等价于「位点越过了这条消息」；
  · 非成员不能查回执。

运行：
    cd "E:\\zi\\huali-corner-trial"
    PYTHONPATH="Backend mission" python -m unittest tests.test_message_receipts
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Backend mission'))
from app.market import Market, DomainError


class MessageReceiptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.m = Market(self.tmp.name)
        self.a = self.login('13800000011')
        self.b = self.login('13800000012')
        self.c = self.login('13800000013')

    def tearDown(self):
        self.tmp.cleanup()

    def login(self, phone):
        return self.m.login(phone, self.m.request_code(phone)['demo_code'])['user']['id']

    def say(self, uid, room, body, key):
        self.m.send_message(uid, room, body, key)
        return self.m.row('SELECT id FROM messages WHERE room_id=? AND user_id=? ORDER BY id DESC LIMIT 1',
                          (room, uid))['id']

    def reader_of(self, receipts, uid):
        return next(x for x in receipts['readers'] if x['user_id'] == uid)

    def test_private_receipt_marks_read_only_after_peer_pulls(self):
        room = self.m.private_room(self.a, self.b)['id']
        mid = self.say(self.a, room, '在吗', 'k1')

        r = self.m.message_receipts(self.a, room)
        self.assertEqual(r['total'], 1)
        self.assertLess(self.reader_of(r, self.b)['last_read_id'], mid, '对方还没拉取，不该算已读')

        self.m.messages(self.b, room)   # 对方打开会话 = 已读位点前移
        r = self.m.message_receipts(self.a, room)
        self.assertGreaterEqual(self.reader_of(r, self.b)['last_read_id'], mid)

    def test_group_receipt_counts_each_member(self):
        room = self.m.join_room(self.a, 'general')['id']
        self.m.join_room(self.b, 'general')
        self.m.join_room(self.c, 'general')
        mid = self.say(self.a, room, '今晚有人打球吗', 'k2')

        r = self.m.message_receipts(self.a, room)
        self.assertEqual(r['total'], 2, '总数只算除自己以外的成员')
        self.assertLess(self.reader_of(r, self.b)['last_read_id'], mid)
        self.assertLess(self.reader_of(r, self.c)['last_read_id'], mid)

        self.m.messages(self.b, room)
        r = self.m.message_receipts(self.a, room)
        self.assertGreaterEqual(self.reader_of(r, self.b)['last_read_id'], mid)
        self.assertLess(self.reader_of(r, self.c)['last_read_id'], mid, 'C 没打开，仍算未读')

    def test_non_member_cannot_read_receipts(self):
        room = self.m.private_room(self.a, self.b)['id']
        with self.assertRaises(DomainError):
            self.m.message_receipts(self.c, room)


if __name__ == '__main__':
    unittest.main()
