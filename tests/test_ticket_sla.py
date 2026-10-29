"""工单超时（SLA）：判定规则与一次性提醒。

规则见 app/support/sla.py：待处理 2 小时无人认领、处理中/待复核 12 小时没有
客服新的动作。这里锁住三件事——阈值、用户补话不算客服动作、同一阶段只提醒一次。

运行：
    cd "E:\\zi\\huali-corner-trial"
    PYTHONPATH="Backend mission" python -m unittest tests.test_ticket_sla
"""
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Backend mission'))
from app.market import Market
from app.support.sla import FIRST_REPLY_SECONDS, STALL_SECONDS


class TicketSlaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.m = Market(self.tmp.name)
        self.user = self.login('13800000021')
        self.staff = self.login('13800000022')
        self.other_staff = self.login('13800000023')
        with self.m.tx() as c:
            c.execute("UPDATE users SET role='support' WHERE id IN (?,?)", (self.staff, self.other_staff))
        self.addCleanup(self.tmp.cleanup)

    def login(self, phone):
        return self.m.login(phone, self.m.request_code(phone)['demo_code'])['user']['id']

    def open_ticket(self, age=0):
        tid = self.m.create_ticket(self.user, dict(type='other', subject='咨询', body='能退吗'))['id']
        if age:
            with self.m.tx() as c:
                c.execute('UPDATE tickets SET created=? WHERE id=?', (time.time() - age, tid))
        return tid

    def staff_says(self, tid, age, uid=None):
        with self.m.tx() as c:
            c.execute('INSERT INTO ticket_messages(ticket_id,user_id,body,internal,created) VALUES(?,?,?,?,?)',
                      (tid, uid or self.staff, '已收到', 0, time.time() - age))

    def set_ticket(self, tid, **fields):
        with self.m.tx() as c:
            c.execute('UPDATE tickets SET %s WHERE id=?' % ','.join('%s=?' % k for k in fields),
                      (*fields.values(), tid))

    def tick(self):
        with self.m.tx() as c:
            return self.m.ticket_sla_notices(c, time.time())

    def notices(self, kind):
        with self.m.tx() as c:
            return [dict(r) for r in c.execute('SELECT * FROM notifications WHERE kind=?', (kind,)).fetchall()]

    def test_fresh_ticket_is_not_overdue(self):
        tid = self.open_ticket()
        sla = self.m.ticket(self.staff, tid)['sla']
        self.assertEqual(sla['stage'], 'first_reply')
        self.assertFalse(sla['overdue'])
        self.assertEqual(self.tick(), 0)

    def test_unclaimed_ticket_past_two_hours_is_overdue_and_notified_once(self):
        tid = self.open_ticket(age=FIRST_REPLY_SECONDS + 600)
        sla = self.m.ticket(self.staff, tid)['sla']
        self.assertTrue(sla['overdue'])
        self.assertGreaterEqual(sla['overdue_seconds'], 600)

        self.assertEqual(self.tick(), 1)
        first = self.notices('ticket_overdue')
        targets = {r['user_id'] for r in first}
        # 未认领 → 全部在岗客服；种子数据里可能还有管理员/开发者，只校验这两人在内
        self.assertTrue({self.staff, self.other_staff} <= targets)
        self.assertIn('#%d' % tid, first[0]['body'])

        # 同一次超时只提醒一次；重复跑定时任务不能刷屏
        self.assertEqual(self.tick(), 0)
        self.assertEqual(len(self.notices('ticket_overdue')), len(first))

    def test_claim_after_notice_does_not_repeat(self):
        tid = self.open_ticket(age=FIRST_REPLY_SECONDS + 600)
        self.tick()
        sent = len(self.notices('ticket_overdue'))
        self.set_ticket(tid, status='processing', assignee=self.staff)
        self.staff_says(tid, age=0)
        self.tick()
        self.assertEqual(len(self.notices('ticket_overdue')), sent)
        self.assertEqual(self.notices('ticket_stalled'), [])

    def test_processing_stall_uses_last_staff_message(self):
        tid = self.open_ticket(age=STALL_SECONDS + 7200)
        self.set_ticket(tid, status='processing', assignee=self.staff)
        self.staff_says(tid, age=STALL_SECONDS + 600)

        sla = self.m.ticket(self.staff, tid)['sla']
        self.assertEqual(sla['stage'], 'progress')
        self.assertTrue(sla['overdue'])

        self.assertEqual(self.tick(), 1)
        rows = self.notices('ticket_stalled')
        self.assertEqual([r['user_id'] for r in rows], [self.staff])  # 已认领 → 只找受理人

    def test_user_reply_does_not_reset_stall_clock(self):
        tid = self.open_ticket(age=STALL_SECONDS + 7200)
        self.set_ticket(tid, status='processing', assignee=self.staff)
        self.staff_says(tid, age=STALL_SECONDS + 600)
        with self.m.tx() as c:
            c.execute('INSERT INTO ticket_messages(ticket_id,user_id,body,internal,created) VALUES(?,?,?,?,?)',
                      (tid, self.user, '补充一下', 0, time.time() - 60))

        self.assertTrue(self.m.ticket(self.staff, tid)['sla']['overdue'])

    def test_recent_staff_reply_clears_stall(self):
        tid = self.open_ticket(age=STALL_SECONDS + 7200)
        self.set_ticket(tid, status='processing', assignee=self.staff)
        self.staff_says(tid, age=60)

        self.assertFalse(self.m.ticket(self.staff, tid)['sla']['overdue'])
        self.assertEqual(self.tick(), 0)

    def test_closed_ticket_has_no_sla(self):
        tid = self.open_ticket(age=FIRST_REPLY_SECONDS + 600)
        self.set_ticket(tid, status='resolved')
        self.assertIsNone(self.m.ticket(self.staff, tid)['sla'])
        self.assertEqual(self.tick(), 0)


if __name__ == '__main__':
    unittest.main()
