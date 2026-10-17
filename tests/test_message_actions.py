"""聊天消息操作回归：撤回（对所有人）与仅自己删除（message_hides）。

两个操作的差别是这组用例的核心：
  撤回 —— 2 分钟内、自己的消息，改为系统提示，双方都看不到正文；
  删除 —— 任意消息，只从「我」的聊天记录里消失，对方仍能看到。

运行：
    cd "E:\\zi\\huali-corner-trial"
    PYTHONPATH="Backend mission" python -m unittest tests.test_message_actions
"""
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Backend mission'))
from app.market import Market, DomainError


class MessageActionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.m = Market(self.tmp.name)
        self.a = self.login('13800000011')
        self.b = self.login('13800000012')
        self.room = self.m.private_room(self.a, self.b)['id']

    def tearDown(self):
        self.tmp.cleanup()

    def login(self, phone):
        return self.m.login(phone, self.m.request_code(phone)['demo_code'])['user']['id']

    def say(self, uid, body, key):
        self.m.send_message(uid, self.room, body, key)
        return self.m.row('SELECT id FROM messages WHERE room_id=? AND user_id=? ORDER BY id DESC LIMIT 1',
                          (self.room, uid))['id']

    def visible(self, uid):
        return [r['body'] for r in self.m.messages(uid, self.room)]

    def test_hide_only_affects_me(self):
        """删除只影响自己：我这边消失，对方还能看到。"""
        mid = self.say(self.a, '这条我要删掉', 'k-hide')
        self.m.hide_message(self.a, mid)
        self.assertNotIn('这条我要删掉', self.visible(self.a))
        self.assertIn('这条我要删掉', self.visible(self.b))

    def test_hide_survives_reload(self):
        """刷新后再拉一次（after=0 全量）也不能再冒出来。"""
        mid = self.say(self.a, '删完不能复活', 'k-reload')
        self.m.hide_message(self.a, mid)
        self.assertEqual(self.visible(self.a), [])
        self.assertIn('删完不能复活', self.visible(self.b))

    def test_hide_is_idempotent(self):
        """重复删除不报错（INSERT OR IGNORE），也不会影响别人。"""
        mid = self.say(self.a, '重复删除', 'k-twice')
        self.m.hide_message(self.a, mid)
        self.m.hide_message(self.a, mid)
        self.assertNotIn('重复删除', self.visible(self.a))

    def test_any_member_can_hide_others_message(self):
        """对方发来的消息也能从我的记录里删掉（微信语义），对方不受影响。"""
        mid = self.say(self.a, '对方的消息', 'k-other')
        self.m.hide_message(self.b, mid)
        self.assertNotIn('对方的消息', self.visible(self.b))
        self.assertIn('对方的消息', self.visible(self.a))

    def test_recall_clears_body_for_everyone(self):
        """撤回对双方生效：removed=2，正文清空，只剩系统提示。"""
        mid = self.say(self.a, '说错话了', 'k-recall')
        self.m.recall_message(self.a, mid)
        for uid in (self.a, self.b):
            row = [r for r in self.m.messages(uid, self.room) if r['id'] == mid][0]
            self.assertEqual(row['removed'], 2)
            self.assertEqual(row['body'], '')

    def test_recall_rejects_others_message(self):
        """不能撤回别人发的消息。"""
        mid = self.say(self.a, '别人的话', 'k-foreign')
        with self.assertRaises(DomainError):
            self.m.recall_message(self.b, mid)

    def test_recall_expires_after_two_minutes(self):
        """超过 2 分钟不能撤回，但删除仍然可以（删除没有时限）。"""
        mid = self.say(self.a, '老消息', 'k-old')
        with self.m.tx() as c:
            c.execute('UPDATE messages SET created=? WHERE id=?', (time.time() - 121, mid))
        with self.assertRaises(DomainError):
            self.m.recall_message(self.a, mid)
        self.m.hide_message(self.a, mid)
        self.assertNotIn('老消息', self.visible(self.a))


if __name__ == '__main__':
    unittest.main()
