import sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Backend mission'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.market import Market, DomainError
from chat_fixture import befriend


class AdminChatViewTests(unittest.TestCase):
    """管理端查看某人会话：列表 + 只读正文 + 审计 + 越权拒绝。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.m = Market(self.tmp.name)
        self.admin = self.login('19065322759')   # 演示模式播种的 admin
        self.alice = self.login('13800000011')
        self.bob = self.login('13800000012')

    def tearDown(self):
        self.tmp.cleanup()

    def login(self, phone):
        code = self.m.request_code(phone)['demo_code']
        return self.m.login(phone, code)['user']['id']

    def test_list_and_read_with_audit(self):
        # 私聊发送有好友门禁，前置先建好友关系。
        befriend(self.m, self.alice, self.bob)
        room = self.m.private_room(self.alice, self.bob)
        self.m.send_message(self.alice, room['id'], '在吗？这本高数还在', 'k-a-1')
        self.m.send_message(self.bob, room['id'], '在的，明天中午A1楼下', 'k-b-1')
        self.m.join_room(self.alice, 'general')
        self.m.send_message(self.alice, 1, '总聊打个招呼', 'k-a-2')

        data = self.m.admin_chats(self.admin, self.alice)
        rooms = data['rooms']
        self.assertTrue(rooms, '应该至少有一个会话')
        private = next(r for r in rooms if r['kind'] == 'private')
        # 私聊名称改成「对着谁」，而不是 rooms.name 里建会话时的旧昵称。
        self.assertEqual(private['name'], self.m.profile(self.bob)['nickname'])
        self.assertEqual(private['message_count'], 2)
        self.assertTrue(private['last']['body'])
        self.assertIn('general', [r['kind'] for r in rooms])

        chat = self.m.admin_chat(self.admin, self.alice, room['id'])
        bodies = [x['body'] for x in chat['messages']]
        self.assertEqual(bodies, ['在吗？这本高数还在', '在的，明天中午A1楼下'])

        audit = self.m.row("SELECT * FROM audit WHERE type='chat_view' AND target=?", (self.alice,))
        self.assertIsNotNone(audit, '读取正文必须写审计')
        self.assertEqual(audit['actor'], self.admin)

    def test_non_admin_cannot_read(self):
        room = self.m.private_room(self.alice, self.bob)
        with self.assertRaises(DomainError) as ctx:
            self.m.admin_chats(self.bob, self.alice)
        self.assertEqual(ctx.exception.status, 403)
        with self.assertRaises(DomainError) as ctx:
            self.m.admin_chat(self.bob, self.alice, room['id'])
        self.assertEqual(ctx.exception.status, 403)

    def test_target_must_be_member(self):
        room = self.m.private_room(self.alice, self.bob)
        with self.assertRaises(DomainError):
            self.m.admin_chat(self.admin, self.login('13800000013'), room['id'])


if __name__ == '__main__':
    unittest.main()
