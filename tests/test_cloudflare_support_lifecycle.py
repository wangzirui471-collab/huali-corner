"""Cloudflare/D1 版客服会话生命周期：结束消失、重开清空、自动结束、工单联动。

与本地 SQLite 版（tests/test_support_sessions.py）保持同一套语义，
防止公网部署与本地试用出现行为分叉。
运行：python -m unittest discover -s tests -p "test_cloudflare_support_lifecycle.py"
"""
import json
import sqlite3
import sys
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend mission'))


class Response:
    def __init__(self, value, status=200, **kw):
        self.body = value
        self.status = status

    @classmethod
    def from_json(cls, value, status=200, **kw):
        return cls(value, status=status)


sys.modules.setdefault('workers', SimpleNamespace(Response=Response))

from app.cloudflare.community_api import CommunityApi, COMMUNITY_ROUTES
from app.cloudflare.http import guard
from app.cloudflare.d1 import Database
from app.cloudflare.crypto import session_digest
from cloudflare_test_support import Binding
from app.cloudflare.api import Api as BaseApi


class Api(BaseApi):
    pass


class CloudflareSupportLifecycle(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.c = sqlite3.connect(':memory:')
        self.c.row_factory = sqlite3.Row
        self.addCleanup(self.c.close)
        self.c.executescript((ROOT / 'Backend mission/app/cloudflare/schema.sql').read_text(encoding='utf-8'))
        for u, role, nick in [(1, 'user', '小周'), (2, 'support', '转角客服'), (3, 'user', '路人')]:
            self.c.execute('INSERT INTO users(id,phone,nickname,role,college) VALUES(?,?,?,?,?)', (u, str(u), nick, role, '测试学院'))
        self.c.execute("INSERT INTO rooms(id,kind,name) VALUES(1,'general','总聊')")
        self.c.executemany('INSERT INTO sessions VALUES(?,?,?)', [(session_digest(f'test-{u}'), u, 9999999999) for u in range(1, 4)])
        # 工单（D1 版工单号是随机 48 位，这里用固定值便于断言）
        self.tid = 2689535234118433
        self.c.execute("INSERT INTO tickets(id,user_id,type,subject,body,status,created) VALUES(?,?,?,?,?,?,?)",
                       (self.tid, 1, 'other', '咨询', '能退吗', 'open', time.time()))
        self.c.commit()
        self.api = Api(SimpleNamespace(DB=Binding(self.c), MEDIA=object(), ASSETS=None))

    async def req(self, path, body=None, uid=1):
        method = 'POST' if body is not None else 'GET'

        async def text():
            return json.dumps(body)

        r = SimpleNamespace(url='https://test.invalid' + path, method=method, text=text,
                            uid=uid, headers={'Authorization': f'Bearer test-{uid}'} if uid else {})
        return await guard(lambda: getattr(self.api, COMMUNITY_ROUTES[path.split('?')[0]][1])(r))

    async def open_room(self, uid=1):
        res = await self.req('/api/support/room', {'ticket_id': self.tid}, uid)
        self.assertEqual(res.status, 200, res.body)
        return res.body['id'] if isinstance(res.body, dict) else res.body

    async def send(self, rid, body, key, uid=1):
        res = await self.req('/api/messages', {'room_id': rid, 'body': body, 'key': key}, uid)
        self.assertEqual(res.status, 200, res.body)

    async def test_close_hides_room_and_archives_messages(self):
        rid = await self.open_room()
        await self.send(rid, '在吗', 'k1')
        res = await self.req('/api/support/close', {'room_id': rid}, 1)
        self.assertEqual(res.status, 200)
        row = self.c.execute('SELECT support_status,support_closed_by FROM rooms WHERE id=?', (rid,)).fetchone()
        self.assertEqual(row['support_status'], 'closed')
        self.assertEqual(row['support_closed_by'], 'customer')
        rooms = (await self.req('/api/rooms', uid=1)).body['joined']
        self.assertFalse(any(x['id'] == rid for x in rooms))
        msgs = (await self.req(f'/api/messages?room_id={rid}', uid=1)).body
        self.assertEqual(msgs, [])

    async def test_reopen_starts_fresh_session(self):
        rid = await self.open_room()
        await self.send(rid, '第一轮', 'k1')
        await self.req('/api/support/close', {'room_id': rid}, 1)
        rid2 = await self.open_room()
        self.assertEqual(rid2, rid)
        msgs = (await self.req(f'/api/messages?room_id={rid}', uid=1)).body
        self.assertEqual(msgs, [])
        await self.send(rid, '第二轮', 'k2')
        msgs = (await self.req(f'/api/messages?room_id={rid}', uid=1)).body
        self.assertEqual([m['body'] for m in msgs], ['第二轮'])

    async def test_message_to_closed_room_reopens(self):
        rid = await self.open_room()
        await self.req('/api/support/close', {'room_id': rid}, 1)
        await self.send(rid, '又想问了', 'k3')
        row = self.c.execute('SELECT support_status FROM rooms WHERE id=?', (rid,)).fetchone()
        self.assertEqual(row['support_status'], 'open')
        msgs = (await self.req(f'/api/messages?room_id={rid}', uid=1)).body
        self.assertEqual([m['body'] for m in msgs], ['又想问了'])

    async def test_tick_closes_idle_session(self):
        rid = await self.open_room()
        await self.send(rid, '在吗', 'k1')
        self.c.execute('UPDATE messages SET created=? WHERE room_id=?', (time.time() - 1900, rid))
        self.c.commit()
        await self.api.cf_trade_tick(time.time())
        row = self.c.execute('SELECT support_status,support_closed_by FROM rooms WHERE id=?', (rid,)).fetchone()
        self.assertEqual(row['support_status'], 'closed')
        self.assertEqual(row['support_closed_by'], 'timeout')

    @unittest.skipIf(sqlite3.sqlite_version_info < (3, 38, 0),
                     '本机 sqlite 缺 json_each；D1 支持，结案联动由本地 SQLite 版测试覆盖')
    async def test_ticket_resolution_closes_session(self):
        rid = await self.open_room()
        await self.send(rid, '处理下', 'k1')

        async def text():
            return json.dumps({'id': self.tid, 'outcome': 'resolved', 'reason': '已解答'})

        await self.api.cf_staff_resolve(SimpleNamespace(
            url='https://test.invalid/api/admin/ticket/resolve', method='POST',
            headers={'Authorization': 'Bearer test-2'}, text=text))
        row = self.c.execute('SELECT support_status,support_closed_by FROM rooms WHERE id=?', (rid,)).fetchone()
        self.assertEqual(row['support_status'], 'closed')
        self.assertEqual(row['support_closed_by'], 'ticket')

    async def test_reception_lists_open_sessions(self):
        rid = await self.open_room()
        await self.send(rid, '有人吗', 'k1')
        res = await self.req('/api/support/sessions', uid=2)
        self.assertEqual(res.status, 200)
        rows = res.body
        self.assertTrue(any(x['id'] == rid and x['customer_name'] == '小周' for x in rows))
        await self.req('/api/support/close', {'room_id': rid}, 1)
        rows = (await self.req('/api/support/sessions', uid=2)).body
        self.assertFalse(any(x['id'] == rid for x in rows))

    # --- 工单 SLA：与本地 tests/test_ticket_sla.py 同一套语义 -------------
    async def staff_tickets(self, uid=2):
        async def text():
            return ''
        r = SimpleNamespace(url='https://test.invalid/api/tickets', method='GET', text=text,
                            headers={'Authorization': f'Bearer test-{uid}'} if uid else {})
        return await guard(lambda: self.api.cf_staff_tickets(r))

    def backdate_ticket(self, age):
        self.c.execute('UPDATE tickets SET created=? WHERE id=?', (time.time() - age, self.tid))
        self.c.commit()

    async def test_ticket_sla_flags_overdue_and_reminds_once(self):
        self.backdate_ticket(3 * 3600)
        res = await self.staff_tickets()
        self.assertEqual(res.status, 200)
        ticket = next(x for x in res.body if x['id'] == self.tid)
        self.assertEqual(ticket['sla']['stage'], 'first_reply')
        self.assertTrue(ticket['sla']['overdue'])

        self.assertGreaterEqual(await self.api.cf_ticket_sla_notices(), 1)
        rows = self.c.execute("SELECT user_id FROM notifications WHERE ticket_id=? AND kind='ticket_overdue'",
                              (self.tid,)).fetchall()
        self.assertTrue(any(r['user_id'] == 2 for r in rows))   # 客服收到
        self.assertFalse(any(r['user_id'] == 1 for r in rows))  # 用户不该收到内部提醒
        before = len(rows)

        self.assertEqual(await self.api.cf_ticket_sla_notices(), 0)
        after = self.c.execute("SELECT COUNT(*) n FROM notifications WHERE ticket_id=? AND kind='ticket_overdue'",
                               (self.tid,)).fetchone()['n']
        self.assertEqual(after, before)

    async def test_ticket_sla_stall_only_notifies_assignee(self):
        self.backdate_ticket(20 * 3600)
        self.c.execute("UPDATE tickets SET status='processing',assignee=2 WHERE id=?", (self.tid,))
        self.c.execute('INSERT INTO ticket_messages(ticket_id,user_id,body,internal,created) VALUES(?,?,?,?,?)',
                       (self.tid, 2, '已收到', 0, time.time() - 13 * 3600))
        self.c.commit()

        ticket = next(x for x in (await self.staff_tickets()).body if x['id'] == self.tid)
        self.assertEqual(ticket['sla']['stage'], 'progress')
        self.assertTrue(ticket['sla']['overdue'])

        self.assertGreaterEqual(await self.api.cf_ticket_sla_notices(), 1)
        rows = self.c.execute("SELECT user_id FROM notifications WHERE ticket_id=? AND kind='ticket_stalled'",
                              (self.tid,)).fetchall()
        self.assertEqual([r['user_id'] for r in rows], [2])

    async def test_ticket_sla_closed_ticket_has_none(self):
        self.backdate_ticket(3 * 3600)
        self.c.execute("UPDATE tickets SET status='resolved' WHERE id=?", (self.tid,))
        self.c.commit()
        ticket = next(x for x in (await self.staff_tickets()).body if x['id'] == self.tid)
        self.assertIsNone(ticket['sla'])
        self.assertEqual(await self.api.cf_ticket_sla_notices(), 0)

    async def test_ticket_sla_stale_ticket_stays_silent(self):
        self.backdate_ticket(10 * 86400)
        ticket = next(x for x in (await self.staff_tickets()).body if x['id'] == self.tid)
        self.assertTrue(ticket['sla']['overdue'])
        self.assertEqual(await self.api.cf_ticket_sla_notices(), 0)
        rows = self.c.execute("SELECT COUNT(*) n FROM notifications WHERE ticket_id=?", (self.tid,)).fetchone()['n']
        self.assertEqual(rows, 0)


if __name__ == '__main__':
    unittest.main()
