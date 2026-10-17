"""社区通知与聊天未读的回归测试。

覆盖 2026-10-17 新增的三块能力：
  1. 聊天未读：members.last_read_id 位点、拉取即已读、入会话不计历史；
  2. 帖子回复通知：评论他人的帖子时作者收到 post_reply，带 post_id；
  3. @提及通知：评论 / 帖子正文里的 @昵称 解析成用户并发 mention 通知，
     自己 @ 自己、帖子作者被 @（已有 post_reply）不重复通知。
运行：python -m unittest discover -s tests -p "test_social_notifications.py"
"""
import sys, tempfile, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Backend mission'))
from app.market import Market


class SocialNotificationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.m = Market(self.tmp.name, trial=True)
        self.alice = self.m.register_password('13800000021', 'Passw0rd!123', '阿甲')['user']['id']
        self.bob = self.m.register_password('13800000022', 'Passw0rd!123', '阿乙')['user']['id']
        self.carol = self.m.register_password('13800000023', 'Passw0rd!123', '阿丙')['user']['id']

    def tearDown(self):
        self.tmp.cleanup()

    # --- 聊天未读 ----------------------------------------------------------

    def test_private_message_creates_chat_unread(self):
        room = self.m.private_room(self.bob, self.alice)
        self.m.send_message(self.bob, room['id'], '书还在吗', 'k1')
        self.assertEqual(self.m.chat_unread(self.alice), 1)
        self.assertEqual(self.m.badges(self.alice)['chat'], 1)

    def test_fetching_messages_marks_room_read(self):
        room = self.m.private_room(self.bob, self.alice)
        self.m.send_message(self.bob, room['id'], '在吗', 'k1')
        self.m.messages(self.alice, room['id'], 0)
        self.assertEqual(self.m.chat_unread(self.alice), 0)
        # 对方再发一条，未读重新出现；已读位点只前进不后退。
        self.m.send_message(self.bob, room['id'], '平另一半', 'k2')
        self.assertEqual(self.m.chat_unread(self.alice), 1)

    def test_rooms_carry_per_room_unread(self):
        room = self.m.private_room(self.bob, self.alice)
        self.m.send_message(self.bob, room['id'], '你好', 'k1')
        joined = {r['id']: r for r in self.m.rooms(self.alice)['joined']}
        self.assertEqual(joined[room['id']]['unread'], 1)

    def test_own_messages_do_not_count_as_unread(self):
        room = self.m.private_room(self.bob, self.alice)
        self.m.send_message(self.alice, room['id'], '我先说', 'k1')
        self.assertEqual(self.m.chat_unread(self.alice), 0)
        self.assertEqual(self.m.chat_unread(self.bob), 1)

    def test_joining_room_does_not_count_history(self):
        self.m.join_room(self.alice, 'general')
        self.m.send_message(self.alice, 1, '历史消息', 'k-his')  # 总聊里先有历史
        self.m.join_room(self.bob, 'general')
        self.assertEqual(self.m.chat_unread(self.bob), 0)
        # 加入之后的新消息才计未读。
        self.m.send_message(self.alice, 1, '新消息', 'k-new')
        self.assertEqual(self.m.chat_unread(self.bob), 1)

    def test_recalled_message_does_not_count_as_unread(self):
        room = self.m.private_room(self.bob, self.alice)
        self.m.send_message(self.bob, room['id'], '发错了', 'k1')
        mid = self.m.rows('SELECT id FROM messages WHERE room_id=?', (room['id'],))[0]['id']
        self.m.recall_message(self.bob, mid)
        self.assertEqual(self.m.chat_unread(self.alice), 0)

    # --- 帖子回复 / @提及 ---------------------------------------------------

    def test_comment_notifies_post_author_with_post_id(self):
        pid = self.m.add_post(self.alice, {'body': '出一本数据结构', 'topic': '毕业季'})['id']
        self.m.comment(self.bob, pid, '我想要')
        notes = self.m.notifications(self.alice)
        self.assertEqual(notes['unread'], 1)
        n = notes['items'][0]
        self.assertEqual(n['kind'], 'post_reply')
        self.assertEqual(n['post_id'], pid)
        self.assertIn('阿乙', n['body'])

    def test_commenting_own_post_does_not_notify_self(self):
        pid = self.m.add_post(self.alice, {'body': '自问自答', 'topic': '交流'})['id']
        self.m.comment(self.alice, pid, '补充一句')
        self.assertEqual(self.m.notifications(self.alice)['unread'], 0)

    def test_mention_notifies_named_user(self):
        pid = self.m.add_post(self.bob, {'body': '有人一起拼单吗 @阿丙', 'topic': '交流'})['id']
        notes = self.m.notifications(self.carol)
        self.assertEqual(notes['unread'], 1)
        n = notes['items'][0]
        self.assertEqual(n['kind'], 'mention')
        self.assertEqual(n['post_id'], pid)

    def test_mention_in_comment_skips_duplicate_for_post_author(self):
        # 帖子作者被 @ 时只收一条 post_reply，不再叠加 mention。
        pid = self.m.add_post(self.alice, {'body': '出书', 'topic': '交流'})['id']
        self.m.comment(self.bob, pid, '@阿甲 我要这本')
        notes = self.m.notifications(self.alice)
        self.assertEqual(notes['unread'], 1)
        self.assertEqual(notes['items'][0]['kind'], 'post_reply')

    def test_mention_does_not_notify_author_self(self):
        pid = self.m.add_post(self.alice, {'body': '我自己 @阿甲 一下', 'topic': '交流'})['id']
        self.assertEqual(self.m.notifications(self.alice)['unread'], 0)

    def test_mention_unknown_nickname_is_silently_ignored(self):
        pid = self.m.add_post(self.alice, {'body': '@不存在的同学 在吗', 'topic': '交流'})['id']
        self.assertEqual(self.m.notifications(self.alice)['unread'], 0)
        self.assertEqual(self.m.notifications(self.bob)['unread'], 0)


if __name__ == '__main__':
    unittest.main()
