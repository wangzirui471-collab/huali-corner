"""客服会话生命周期回归：结束、自动结束、重新开启与接待台。

覆盖 2026-10-19 新增能力：
  1. 用户/客服结束会话后，双方会话列表都不再出现，消息归档不可见；
  2. 重新咨询开新一轮，上一轮聊天记录不展示（数据库仍留档，removed=3）；
  3. 30 分钟无新消息由 tick() 自动结束；关联工单结案时同步结束；
  4. 客服接待台：待接入排序、认领后显示接待人、等待时长。
运行：python -m unittest discover -s tests -p "test_support_sessions.py"
"""
import sys, tempfile, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Backend mission'))
from app.market import Market, DomainError


class SupportSessionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.m = Market(self.tmp.name, trial=True)
        self.user = self.m.register_password('13800000041', 'Passw0rd!123', '同学')['user']['id']
        self.other = self.m.register_password('13800000042', 'Passw0rd!123', '路人')['user']['id']
        self.staff = self.m.register_password('13800000043', 'Passw0rd!123', '转角客服')['user']['id']
        self.m.set_role_operator('13800000043', 'support')
        self.ticket = self.m.create_ticket(self.user, {'type': 'other', 'subject': '咨询', 'body': '书还能便宜吗'})
        self.room = self.m.support_room(self.user, self.ticket['id'])['id']

    def tearDown(self):
        self.tmp.cleanup()

    def status(self):
        return self.m.row('SELECT support_status,support_closed_by FROM rooms WHERE id=?', (self.room,))

    def test_close_hides_room_from_both_sides(self):
        self.m.send_message(self.user, self.room, '在吗', 'k1')
        self.m.close_support_room(self.user, self.room)
        self.assertEqual(self.status()['support_status'], 'closed')
        self.assertEqual(self.status()['support_closed_by'], 'customer')
        self.assertFalse(any(r['id'] == self.room for r in self.m.rooms(self.user)['joined']))
        self.assertFalse(any(r['id'] == self.room for r in self.m.rooms(self.staff)['joined']))
        self.assertEqual(self.m.messages(self.user, self.room, 0), [])

    def test_reopen_starts_fresh_session(self):
        self.m.send_message(self.user, self.room, '第一轮问题', 'k1')
        self.m.close_support_room(self.user, self.room)
        reopened = self.m.support_room(self.user, self.ticket['id'])
        self.assertEqual(reopened['support_status'], 'open')
        self.assertEqual(self.m.messages(self.user, self.room, 0), [])
        self.m.send_message(self.user, self.room, '第二轮问题', 'k2')
        bodies = [x['body'] for x in self.m.messages(self.user, self.room, 0)]
        self.assertEqual(bodies, ['第二轮问题'])

    def test_message_to_closed_room_reopens_it(self):
        self.m.close_support_room(self.user, self.room)
        self.m.send_message(self.user, self.room, '又想问了', 'k3')
        self.assertEqual(self.status()['support_status'], 'open')
        self.assertEqual([x['body'] for x in self.m.messages(self.user, self.room, 0)], ['又想问了'])

    def test_idle_session_closed_by_tick(self):
        self.m.send_message(self.user, self.room, '在吗', 'k1')
        row = self.m.row('SELECT MAX(created) t FROM messages WHERE room_id=?', (self.room,))
        with self.m.tx() as c:
            c.execute('UPDATE messages SET created=? WHERE room_id=?', (row['t'] - 1900, self.room))
        self.m.tick()
        self.assertEqual(self.status()['support_status'], 'closed')
        self.assertEqual(self.status()['support_closed_by'], 'timeout')

    def test_ticket_resolution_closes_session(self):
        self.m.send_message(self.user, self.room, '处理下', 'k1')
        self.m.resolve_ticket(self.staff, self.ticket['id'], {'outcome': 'resolved', 'reason': '已解答'})
        self.assertEqual(self.status()['support_status'], 'closed')
        self.assertEqual(self.status()['support_closed_by'], 'ticket')

    def test_staff_can_close_any_support_room(self):
        self.m.close_support_room(self.staff, self.room)
        self.assertEqual(self.status()['support_closed_by'], 'agent')

    def test_outsider_cannot_close_room(self):
        with self.assertRaises(DomainError):
            self.m.close_support_room(self.other, self.room)

    def test_reception_lists_unclaimed_first(self):
        self.m.send_message(self.user, self.room, '有人吗', 'k1')
        sessions = self.m.support_sessions(self.staff)
        mine = [s for s in sessions if s['id'] == self.room]
        self.assertTrue(mine)
        self.assertEqual(mine[0]['customer_name'], '同学')
        self.assertEqual(mine[0]['subject'], '咨询')
        self.assertEqual(mine[0]['assignee'], 0)
        self.assertEqual(mine[0]['online_hint'], '等待接入')
        self.m.claim_support_room(self.staff, self.room)
        sessions = self.m.support_sessions(self.staff)
        mine = [s for s in sessions if s['id'] == self.room][0]
        self.assertEqual(mine['assignee'], self.staff)
        self.assertIn('转角客服', mine['online_hint'])

    def test_closed_session_not_in_reception(self):
        self.m.close_support_room(self.user, self.room)
        self.assertEqual(self.m.support_sessions(self.staff), [])

    def test_user_cannot_see_reception(self):
        with self.assertRaises(DomainError):
            self.m.support_sessions(self.user)


if __name__ == '__main__':
    unittest.main()
