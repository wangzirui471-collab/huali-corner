"""2026-10-22 测试发现的问题的回归用例（BUG-01/02/04/05/06）。

放在独立文件里，便于「修复是否真的生效」被单独重跑：
    .venv-trial\\Scripts\\python.exe -m unittest test_regression_20261022
"""

import json
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

# 与 test_market 一致：从仓库根跑 discover 时，后端目录不在 sys.path 里。
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Backend mission'))

from server import make_server  # noqa: E402


class Regression20261022Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.server = make_server(self.tmp.name, 0, trial=True,
                                  admin=('13900000000', 'AdminPass2026!'),
                                  public_origin='https://campus.example')
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = 'http://127.0.0.1:' + str(self.server.server_port)
        self.market = self.server.market

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def req(self, path, data=None, token=None):
        headers = {'Content-Type': 'application/json', 'Origin': 'https://campus.example'}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        request = urllib.request.Request(
            self.base + path, data=json.dumps(data).encode() if data is not None else None,
            headers=headers)
        try:
            with urllib.request.urlopen(request) as response:
                return response.status, json.loads(response.read() or b'{}')
        except urllib.error.HTTPError as error:
            payload = error.read()
            try:
                return error.code, json.loads(payload or b'{}')
            except ValueError:
                return error.code, {'raw': payload[:200].decode('utf-8', 'replace')}

    def register(self, phone='13900000011', college='计算机工程学院', grade='2024级',
                 major='软件工程', nickname='注册同学'):
        return self.req('/api/auth/register', {
            'phone': phone, 'password': 'TrialPassword2026!', 'nickname': nickname,
            'college': college, 'grade': grade, 'major': major})

    # BUG-01：注册页年级下拉的数据源必须由 /api/config 提供
    def test_config_exposes_grades(self):
        status, config = self.req('/api/config')
        self.assertEqual(status, 200)
        self.assertIn('grades', config)
        self.assertIn('2024级', config['grades'])
        self.assertGreater(len(config['grades']), 1)

    # BUG-02：学院/年级/专业必须落库，并在自己的资料里读得到
    def test_register_persists_college_grade_major(self):
        status, result = self.register()
        self.assertEqual(status, 200, result)
        self.assertEqual(result['user']['grade'], '2024级')
        self.assertEqual(result['user']['major'], '软件工程')
        self.assertEqual(result['user']['college'], '计算机工程学院')
        status, me = self.req('/api/me', token=result['token'])
        self.assertEqual(status, 200)
        self.assertEqual(me['grade'], '2024级')
        self.assertEqual(me['major'], '软件工程')

    def test_register_rejects_unknown_college_or_grade(self):
        status, body = self.register(phone='13900000012', college='不存在学院')
        self.assertEqual(status, 400, body)
        status, body = self.register(phone='13900000013', grade='1999级')
        self.assertEqual(status, 400, body)
        # 失败后不应留下半个账号
        row = self.market.row('SELECT 1 FROM users WHERE phone=?', ('13900000012',))
        self.assertIsNone(row)

    def test_register_without_new_fields_still_works(self):
        # 命令行建号、老客户端只传三个参数时不能被新校验拦死
        status, result = self.req('/api/auth/register', {
            'phone': '13900000014', 'password': 'TrialPassword2026!', 'nickname': '老客户端'})
        self.assertEqual(status, 200, result)
        self.assertEqual(result['user']['college'], '计算机工程学院')
        self.assertEqual(result['user']['grade'], '')

    # BUG-04：审计 CSV 的公式前缀必须转义
    def test_audit_csv_neutralises_formula_prefixes(self):
        admin = self.market.row('SELECT id FROM users WHERE phone=?', ('13900000000',))['id']
        now = time.time()
        with self.market.tx() as c:
            for reason in ('=1+1', '+1+1', '-1+1', '@SUM(1)', '正常理由'):
                c.execute(
                    'INSERT INTO audit(actor,target,type,delta,reason,ticket_id,created) VALUES(?,?,?,?,?,?,?)',
                    (admin, admin, 'formula_probe', -1, reason, 0, now))
        payload = self.market.audit_csv(admin).decode('utf-8')
        self.assertTrue(payload.startswith('\ufeff'))
        self.assertIn("'=1+1", payload)
        self.assertIn("'+1+1", payload)
        self.assertIn("'-1+1", payload)
        self.assertIn("'@SUM(1)", payload)
        self.assertIn('正常理由', payload)
        for line in payload.splitlines()[1:]:
            for cell in line.split(','):
                self.assertFalse(cell.strip('"').startswith(('=', '+', '@')),
                                 '存在未转义的公式单元格: %r' % cell)

    # BUG-05：before 游标能取到更早一页，且不影响已读位点
    def test_messages_before_cursor_pages_older_history(self):
        status, a = self.register(phone='13900000015', nickname='甲')
        self.assertEqual(status, 200, a)
        status, b = self.register(phone='13900000016', nickname='乙')
        self.assertEqual(status, 200, b)
        ua = a['user']['id']
        ub = b['user']['id']
        # 直接入库造 210 条，避免触发发送限流；时间递增保证顺序确定
        connection = sqlite3.connect(str(self.market.root) + '/market.sqlite3')
        with connection:
            room = connection.execute(
                "INSERT INTO rooms(kind,name,pair) VALUES('private','乙',?)", (':'.join(map(str, sorted([ua, ub]))),)).lastrowid
            for uid in (ua, ub):
                connection.execute('INSERT INTO members(room_id,user_id) VALUES(?,?)', (room, uid))
            now = time.time()
            for i in range(210):
                connection.execute(
                    'INSERT INTO messages(room_id,user_id,body,created,request_key) VALUES(?,?,?,?,?)',
                    (room, ua, '历史 %03d' % i, now - 500 + i, 'seed%d' % i))
        connection.close()

        status, latest = self.req('/api/messages?room_id=%d' % room, token=b['token'])
        self.assertEqual(status, 200)
        self.assertEqual(len(latest), 200)
        oldest_loaded = latest[0]['id']
        self.assertEqual(latest[-1]['body'], '历史 209')

        status, older = self.req('/api/messages?room_id=%d&before=%d' % (room, oldest_loaded),
                                 token=b['token'])
        self.assertEqual(status, 200)
        self.assertEqual(len(older), 10)
        self.assertEqual(older[-1]['body'], '历史 009')
        self.assertTrue(older[-1]['id'] < oldest_loaded)
        # 不重叠、不遗漏
        self.assertFalse({m['id'] for m in latest} & {m['id'] for m in older})

        # 读更早一页不应把已读位点往回拨
        read = self.market.row('SELECT last_read_id FROM members WHERE room_id=? AND user_id=?',
                               (room, ub))['last_read_id']
        self.assertEqual(read, latest[-1]['id'])

    # BUG-06：超限请求要能读到明确的 413，而不是连接被重置
    def test_oversized_body_returns_readable_413(self):
        status, result = self.register()
        self.assertEqual(status, 200, result)
        limit = 4 * ((2 * 1024 * 1024 + 2) // 3) + 65536
        body = b'{"content":"' + b'A' * (limit + 1024) + b'"}'
        request = urllib.request.Request(
            self.base + '/api/user/avatar/upload', data=body,
            headers={'Content-Type': 'application/json', 'Origin': 'https://campus.example',
                     'Authorization': 'Bearer ' + result['token'],
                     'Content-Length': str(len(body))})
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request)
        self.assertEqual(caught.exception.code, 413)
        payload = json.loads(caught.exception.read())
        self.assertIn('头像过大', payload.get('error', ''))


if __name__ == '__main__':
    unittest.main()
