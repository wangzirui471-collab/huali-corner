"""所有者办公助手：办公模式真跑数据查询（ office_lookup ），并检查面板不裁底。

本地演示后端（server.py）没有挂 /api/ai/office——那是 Cloudflare 专属路由。
所以这里自带一个静态服务：web 7M 原样Serve，/api/ai/office 用真实 schema.sql
建内存库、灌种子行，再调真实的 office_lookup。这样测的是从意图解析到
SQL 到拼答案的整条链路，而不是一份写死的 JSON。

跑法：python tests/office_mode_browser_smoke.py
"""
import asyncio
import json
import os
import sqlite3
import sys
import tempfile
import threading
import time
from pathlib import Path
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend mission'))
WEB = ROOT / 'web 7M'

from app.cloudflare.office_data import office_lookup, day_start  # noqa: E402


def build_db():
    """内存库 + 真实 schema + 种子行（与 tests/test_ai_support.OfficeDataTests 同一套）。"""
    # check_same_thread=False：库建在主线程，查询跑在 HTTP 服务线程
    conn = sqlite3.connect(':memory:', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript((ROOT / 'Backend mission/app/cloudflare/schema.sql').read_text(encoding='utf-8'))
    now = time.time()
    today = day_start(0) + 3600
    conn.executemany(
        'INSERT INTO users(id,phone,nickname,role,status,score,college,grade,last_login) '
        'VALUES(?,?,?,?,?,?,?,?,?)',
        [(1, '13800000001', '张三', 'owner', 'active', 100, '计算机工程学院', '2024级', now - 60),
         (2, '13800000002', '李四', 'admin', 'active', 96, '计算机工程学院', '2023级', now - 3600),
         (3, '13800000003', '王五', 'user', 'active', 100, '计算机工程学院', '2024级', now - 7200),
         (4, '13800000004', '赵六', 'user', 'banned', 40, '计算机工程学院', '2022级', 0)])
    conn.executemany(
        'INSERT INTO products(id,seller_id,title,category,price,status,data,created) '
        'VALUES(?,?,?,?,?,?,?,?)',
        [(1, 3, '青轴机械键盘', 'electronics', 19900, 'available', '{}', today),
         (2, 2, '护眼台灯', 'living', 4900, 'removed', '{}', now - 86400 * 3)])
    conn.executemany(
        'INSERT INTO orders(id,buyer_id,seller_id,items,subtotal,delivery_fee,total,status,created) '
        'VALUES(?,?,?,?,?,?,?,?,?)',
        [(1, 3, 2, '[]', 19900, 0, 19900, 'paid', today),
         (2, 4, 3, '[]', 4900, 0, 4900, 'completed', now - 86400 * 10)])
    conn.execute('INSERT INTO tickets(id,user_id,type,subject,status,created) '
                 "VALUES(1,3,'refund','退款申请','open',?)", (now - 600,))
    conn.execute('INSERT INTO audit(id,actor,target,type,reason,created) '
                 "VALUES(1,1,2,'staff_role','把李四调整为管理员',?)", (now - 120,))
    conn.execute('INSERT INTO wants(id,user_id,keyword,budget,status,created) '
                 "VALUES(1,3,'机械键盘',20000,'open',?)", (now - 900,))
    conn.commit()
    return conn


class Db:
    """office_lookup 需要的 D1 形状：all/first/scalar/run。"""

    def __init__(self, conn):
        self.conn = conn

    def _rows(self, sql, params):
        cur = self.conn.execute(sql, tuple(params or ()))
        return [dict(x) for x in cur.fetchall()] if cur.description else []

    async def all(self, sql, params=None):
        return self._rows(sql, params)

    async def first(self, sql, params=None):
        rows = self._rows(sql, params)
        return rows[0] if rows else None

    async def scalar(self, sql, params=None):
        row = await self.first(sql, params)
        return list(row.values())[0] if row else None

    async def run(self, sql, params=None):
        self.conn.execute(sql, tuple(params or ()))
        self.conn.commit()


CONFIG = {'ai': True, 'support_hours': '08:00–20:00', 'trial': True,
          'auth_mode': 'password', 'colleges': [], 'grades': [], 'categories': []}
ME = {'id': 1, 'phone': '13900000001', 'nickname': '测试所有者',
      'role': 'owner', 'avatar': '', 'credit': 100, 'grade': '2024'}


def make_server(db):
    """静态服务 + 三个 mock 接口；/api/ai/office 走真实 office_lookup。"""
    loop = asyncio.new_event_loop()

    class H(SimpleHTTPRequestHandler):
        # Windows 注册表里没有 .js 的 MIME，不写死所有 ES 模块都会加载失败
        extensions_map = {**SimpleHTTPRequestHandler.extensions_map,
                          '.js': 'text/javascript', '.mjs': 'text/javascript',
                          '.css': 'text/css', '.json': 'application/json'}

        def __init__(self, *a, **k):
            super().__init__(*a, directory=str(WEB), **k)

        def log_message(self, *a):
            pass

        def _json(self, obj):
            body = json.dumps(obj, ensure_ascii=False).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = self.path.split('?')[0]
            if path == '/api/config':
                return self._json(CONFIG)
            if path == '/api/me':
                return self._json(ME)
            if path == '/':
                self.path = '/index.html'
            return super().do_GET()

        def do_POST(self):
            n = int(self.headers.get('Content-Length') or 0)
            body = self.rfile.read(n) if n else b''
            if '/api/ai/office' in self.path:
                q = json.loads(body.decode('utf-8')).get('question', '')
                data = loop.run_until_complete(office_lookup(db, q))
                if not data:      # 没识别成数据查询：线上会交给模型，这里只回空壳
                    return self._json({'answer': '', 'proposal': None,
                                       'mode': 'rule', 'stats': None, 'items': []})
                return self._json({'answer': data['answer'], 'proposal': None,
                                   'mode': 'rule', 'stats': data.get('stats'),
                                   'items': data.get('items') or []})
            return self._json({})

    server = ThreadingHTTPServer(('127.0.0.1', 0), H)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def main():
    db = Db(build_db())
    server = make_server(db)
    base = 'http://127.0.0.1:%d' % server.server_port
    fails = []

    def check(cond, msg):
        print(('  OK   ' if cond else '  FAIL ') + msg)
        if not cond:
            fails.append(msg)

    errors = []
    try:
        with sync_playwright() as p:
            chrome = os.environ.get('CHROME_PATH', r'C:\Program Files\Google\Chrome\Application\chrome.exe')
            kw = {'headless': True, 'args': ['--no-sandbox']}
            if os.path.exists(chrome):
                kw['executable_path'] = chrome
            browser = p.chromium.launch(**kw)
            page = browser.new_page(viewport={'width': 1366, 'height': 768})
            page.on('pageerror', lambda e: errors.append(str(e)))
            # 免登录：直接塞一个未过期的会话，页面就当已登录的所有者
            page.add_init_script("localStorage.setItem('hc-token','smoke-token');"
                                 "localStorage.setItem('hc-token-expires', String(Date.now()+86400000));")
            page.goto(base + '/index.html', wait_until='domcontentloaded')
            page.wait_for_selector('#ai-pet')
            page.wait_for_timeout(700)
            page.evaluate("document.querySelector('#ai-pet-body').click()")
            page.wait_for_timeout(300)

            # 办公快捷按钮：所有者才看得到，且换行后 7 个都点得着
            chips = page.query_selector_all('.ai-pet-office button')
            check(len(chips) == 7, '办公快捷按钮 7 个（实际 %d）' % len(chips))
            row = page.evaluate("""() => { const r=document.querySelector('.ai-pet-office');
                return {scrollW:r.scrollWidth, clientW:r.clientWidth}; }""")
            check(row['scrollW'] <= row['clientW'] + 1,
                  '快捷问行不横向溢出（scrollWidth %d / 可视 %d）' % (row['scrollW'], row['clientW']))

            def ask(q, expect, rows):
                page.evaluate("""(q) => {
                  const b=[...document.querySelectorAll('.ai-pet-office button')].find(x=>x.dataset.q===q);
                  if (b) b.click();
                }""", q)
                page.wait_for_timeout(600)
                bots = page.query_selector_all('#ai-pet-log .ai-pet-msg.bot')
                last = bots[-1].inner_text() if bots else ''
                # 只数最后一条回答里的行：消息日志是累积的
                got = bots[-1].query_selector_all('.ai-pet-row') if bots else []
                print('     Q: %s → %s' % (q, last.replace('\n', ' / ')[:90]))
                check(expect in last, '「%s」的答案包含「%s」' % (q, expect))
                check(len(got) == rows, '「%s」渲染 %d 行列表（实际 %d）' % (q, rows, len(got)))
                return last

            users = ask('把所有用户列出来', '共 4 个账号', 4)
            check('138****0001' in users and '13800000001' not in users, '手机号打码')
            ask('最近 10 笔订单', '平台共 2 笔订单', 2)
            ask('待处理工单', '待处理 1 张', 1)
            ask('平台数据概览', '用户 4（24h 活跃 3）', 0)

            # 自由输入：用户详情
            page.fill('#ai-pet-q', '王五的用户详情')
            page.press('#ai-pet-q', 'Enter')
            page.wait_for_timeout(600)
            bots = page.query_selector_all('#ai-pet-log .ai-pet-msg.bot')
            last = bots[-1].inner_text() if bots else ''
            print('     Q: 王五的用户详情 → %s' % last.replace('\n', ' / ')[:90])
            check('账号 #3' in last, '自由输入也能查到用户详情')

            # 面板底部不裁：输入框和隐私提示都在面板内
            m = page.evaluate("""() => {
              const p=document.querySelector('#ai-pet-panel');
              return {panelB:p.getBoundingClientRect().bottom,
                      formB:document.querySelector('#ai-pet-form').getBoundingClientRect().bottom,
                      noteB:document.querySelector('.ai-pet-note').getBoundingClientRect().bottom};
            }""")
            check(m['formB'] <= m['panelB'] + 1, '输入框在面板内')
            check(m['noteB'] <= m['panelB'] + 1, '隐私提示在面板内（底部不裁）')
            # 视口临时缩小只夹显示尺寸，放大后恢复用户保存的原始尺寸。
            page.evaluate("localStorage.setItem('hc-pet-panel-size', JSON.stringify({w:580,h:620}))")
            page.reload(wait_until='domcontentloaded')
            page.wait_for_selector('#ai-pet')
            page.evaluate("document.querySelector('#ai-pet-body').click()")
            page.wait_for_function("Math.abs(document.querySelector('#ai-pet-panel').offsetWidth-580)<2")
            page.set_viewport_size({'width': 390, 'height': 700})
            page.wait_for_function("document.querySelector('#ai-pet-panel').offsetWidth<=366")
            page.set_viewport_size({'width': 1366, 'height': 768})
            page.wait_for_function("Math.abs(document.querySelector('#ai-pet-panel').offsetWidth-580)<2")
            check(True, '视口缩小后恢复用户原尺寸')
            check(not errors, '无 JS 报错' + ('：' + '; '.join(errors[:3]) if errors else ''))
            browser.close()
    finally:
        server.shutdown()
        server.server_close()

    print('')
    if fails:
        print('办公模式浏览器验证失败 %d 项：%s' % (len(fails), fails))
        return 1
    print('办公模式浏览器验证通过：数据查询真实查库、手机号打码、列表渲染、底部不裁。')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
