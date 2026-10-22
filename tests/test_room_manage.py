"""会话级增强：置顶 / 删除聊天记录 / 屏蔽切换。

覆盖：
  · rooms() 返回里 pinned / blocked / peer_id 字段正确；
  · pin_room 写库并能 toggle（先置顶后取消）；
  · clear_room 只动自己的 message_hides，对方仍能拉全量；
  · clear_room 不在非成员身上调用；
  · block(enabled=False) 走与 unblock-room 同一接口（前端 toggle）。

运行：
    cd "E:\\zi\\huali-corner-trial"
    PYTHONPATH="Backend mission" python -m unittest tests.test_room_manage
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Backend mission'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.market import Market, DomainError
from chat_fixture import private_chat


class RoomManageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.m = Market(self.tmp.name)
        self.a = self.login('13800000021')
        self.b = self.login('13800000022')
        self.c = self.login('13800000023')

    def tearDown(self):
        self.tmp.cleanup()

    def login(self, phone):
        return self.m.login(phone, self.m.request_code(phone)['demo_code'])['user']['id']

    def say(self, uid, room, body, key):
        self.m.send_message(uid, room, body, key)

    # 置顶：写库后 rooms() 立刻返回 pinned=true；
    # 取消置顶再 rooms() 回去要降回 false。
    def test_pin_toggle_round_trip(self):
        # 私聊发送有好友门禁，前置先建好友关系。
        room = private_chat(self.m, self.a, self.b)
        self.say(self.a, room, 'hi', 'kp1')
        self.say(self.b, room, 'hello', 'kp2')

        before = self.m.rooms(self.a)['joined']
        target = next(r for r in before if r['id'] == room)
        self.assertFalse(target['pinned'])
        self.assertEqual(target['peer_id'], self.b)
        self.assertFalse(target['blocked'])

        # 置顶：返回 pinned=True，并落库。
        r = self.m.pin_room(self.a, room, True)
        self.assertTrue(r['pinned'])
        after = self.m.rooms(self.a)['joined']
        target = next(r for r in after if r['id'] == room)
        self.assertTrue(target['pinned'])
        # 置顶后位置要排到未置顶之前。
        self.assertEqual(after[0]['id'], room, '置顶后应排到列表首位')

        # 取消置顶：返回 pinned=False，列表回到原顺序。
        r = self.m.pin_room(self.a, room, False)
        self.assertFalse(r['pinned'])
        again = self.m.rooms(self.a)['joined']
        self.assertFalse(next(r for r in again if r['id'] == room)['pinned'])

    # 删除聊天记录：清完自己这边 message_hides 都有，对方仍能拉到全部。
    # 这是"删除"和"撤回"的根本区别——撤回让所有人看到撤回提示，
    # 删除只抹自己眼里的。
    def test_clear_room_only_affects_self(self):
        room = private_chat(self.m, self.a, self.b)
        self.say(self.a, room, '1', 'kc1')
        self.say(self.b, room, '2', 'kc2')
        self.say(self.a, room, '3', 'kc3')

        before_self = self.m.messages(self.a, room)
        before_peer = self.m.messages(self.b, room)
        self.assertEqual(len(before_self), 3)
        self.assertEqual(len(before_peer), 3)

        r = self.m.clear_room(self.a, room)
        self.assertTrue(r['ok'])

        # 自己：消息应该全部隐藏（空集合）。
        self.assertEqual(self.m.messages(self.a, room), [])
        # 对方：依然三条完整消息，一条不差。
        after_peer = self.m.messages(self.b, room)
        self.assertEqual(len(after_peer), 3, 'clear_room 不影响对方的聊天记录')
        self.assertEqual([m['body'] for m in after_peer], ['1', '2', '3'])

        # 已读位点也拨到当下，避免「记录没了角标还在」。
        member = self.m.row('SELECT last_read_id FROM members WHERE room_id=? AND user_id=?', (room, self.a))
        max_id = self.m.row('SELECT MAX(id) m FROM messages WHERE room_id=?', (room,))['m']
        self.assertEqual(member['last_read_id'], max_id, '清完要顺带把已读位点拨到当下')

    # 群聊没有"屏蔽"，pinned / blocked 字段要按预期填充。
    def test_group_room_blocked_is_always_false(self):
        room = self.m.join_room(self.a, 'general')['id']
        self.m.join_room(self.b, 'general')
        self.say(self.a, room, '组里 hello', 'kg1')
        rooms = self.m.rooms(self.a)['joined']
        target = next(r for r in rooms if r['id'] == room)
        self.assertFalse(target['blocked'])
        self.assertEqual(target['peer_id'], 0)
        # 群聊置顶也照常工作。
        self.m.pin_room(self.a, room, True)
        rooms = self.m.rooms(self.a)['joined']
        self.assertTrue(next(r for r in rooms if r['id'] == room)['pinned'])

    # 屏蔽 toggle：enabled=True 写入，enabled=False 删除，与 rooms() 里的 blocked 联动。
    def test_block_toggle_and_rooms_reflect(self):
        room = private_chat(self.m, self.a, self.b)
        self.say(self.a, room, '看一下', 'kb1')
        self.m.block(self.a, self.b, True)
        self.assertTrue(next(r for r in self.m.rooms(self.a)['joined'] if r['id'] == room)['blocked'])
        # 取消屏蔽
        self.m.block(self.a, self.b, False)
        self.assertFalse(next(r for r in self.m.rooms(self.a)['joined'] if r['id'] == room)['blocked'])

    # 非成员不能 pin / clear 别人的房间。
    def test_non_member_cannot_pin_or_clear(self):
        room = self.m.private_room(self.a, self.b)['id']
        with self.assertRaises(DomainError):
            self.m.pin_room(self.c, room, True)
        with self.assertRaises(DomainError):
            self.m.clear_room(self.c, room)
