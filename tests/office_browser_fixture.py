"""仅绑定回环地址的浏览器验收夹具：真实办公路由 + 内存 D1 + 构建后的前端。"""
import argparse
import asyncio
import json
import sqlite3
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

from cloudflare_test_support import Binding, MemoryBucket, ROOT
from app.cloudflare.api import Api
from app.cloudflare.crypto import session_digest
from app.cloudflare.http import guard


class Fixture:
    """完全隔离的合成数据，不读取 var、var-trial、Worker secrets 或远程绑定。"""

    def __init__(self):
        """创建仅用于单进程浏览器验收的内存数据库。"""
        self.db = sqlite3.connect(':memory:', check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript((ROOT / 'Backend mission/app/cloudflare/schema.sql').read_text(encoding='utf-8'))
        self.db.execute("INSERT INTO users(id,phone,nickname,role) VALUES(5,'owner@test.invalid','合成所有者','owner'),(2,'user@test.invalid','合成同学','user')")
        self.db.execute('INSERT INTO sessions VALUES(?,?,?)', (session_digest('test-5'), 5, 9999999999))
        self.api = Api(SimpleNamespace(DB=Binding(self.db), MEDIA=MemoryBucket(), HC_OFFICE_BATCH_LIMIT='20'))
        self.reset()

    def reset(self):
        """只重置本夹具内存库，供各个浏览器场景独立运行。"""
        for table in ('tickets', 'ticket_messages', 'audit', 'notifications', 'ai_office_jobs'):
            self.db.execute('DELETE FROM ' + table)
        for tid, typ, subject in ((11, 'other', '图片上传失败'), (12, 'other', '如何补充商品介绍'), (13, 'refund', '商品不符申请退款')):
            self.db.execute('INSERT INTO tickets(id,user_id,type,subject,body,status,created) VALUES(?,2,?,?,?,\'open\',?)',
                            (tid, typ, subject, '请帮忙核对具体情况，谢谢。', time.time()))
        self.db.execute("INSERT INTO ticket_messages(ticket_id,user_id,body,internal,created) VALUES(11,5,'不能展示的内部备注',1,?)", (time.time(),))
        self.db.commit()


HARNESS = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="stylesheet" href="/styles.css"><link rel="stylesheet" href="/market.css"><link rel="stylesheet" href="/ai-pet.css">
<title>隔离办公验收</title><body><main style="padding:24px"><h1>华立转角 · 隔离工单验收</h1><p>全部为合成数据。</p></main><div id="overlay"></div>
<script type="module">
import {state} from '/src/core/state.js';
import {aiPet} from '/src/components/ai-pet.js';
import {registerActions} from '/src/actions/index.js';
import {clearAccount} from '/src/auth/login.js';
state.token='test-5';state.me={id:5,role:'owner',nickname:'合成所有者'};
document.body.insertAdjacentHTML('beforeend',aiPet());
document.querySelector('#ai-pet-panel').hidden=false;
registerActions();
/** 仅测试页提供退出动作，用于验证面板不会跨账号保留资料。 */
window.testLogout=()=>clearAccount();
</script></body></html>'''


class Handler(SimpleHTTPRequestHandler):
    """仅在验收夹具中暴露状态观察入口，生产入口不导入本模块。"""

    def __init__(self, *args, **kwargs):
        """静态资源直接来自当前检出，包含实际构建的 Vue 面板。"""
        super().__init__(*args, directory=str(ROOT / 'web 7M'), **kwargs)

    def send_json(self, body, status=200):
        """统一返回本地测试数据，不打印客户正文或合成 token。"""
        encoded = json.dumps(body, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(encoded)))
        self.end_headers(); self.wfile.write(encoded)

    def do_GET(self):
        """提供测试页、只读观测及现有静态资源。"""
        if self.path == '/__office_test__':
            self.send_response(200); self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers(); self.wfile.write(HARNESS.encode('utf-8')); return
        if self.path == '/__office_state__':
            return self.send_json(dict(
                replies=self.server.fixture.db.execute('SELECT count(*) FROM ticket_messages WHERE internal=0').fetchone()[0],
                states=[dict(r) for r in self.server.fixture.db.execute('SELECT id,status FROM tickets ORDER BY id')]))
        return super().do_GET()

    def do_POST(self):
        """把浏览器请求转给真实业务 Api，测试专用重置只作用于内存库。"""
        if self.path == '/__office_reset__':
            self.server.fixture.reset(); return self.send_json(dict(ok=True))
        body = self.rfile.read(int(self.headers.get('Content-Length', 0))).decode('utf-8')

        async def request_text():
            """提供与 Worker request.text 相同的已读取请求体。"""
            return body

        request = SimpleNamespace(url='http://127.0.0.1' + self.path, method='POST',
                                  headers=dict(self.headers), text=request_text)
        result = asyncio.run(guard(lambda: self.server.fixture.api.dispatch(request)))
        self.send_json(result.body, result.status)

    def log_message(self, *args):
        """避免日志记录测试会话或请求正文。"""


if __name__ == '__main__':
    # 只监听回环地址，不连接真实数据库、不运行生产定时任务。
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8137)
    options = parser.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', options.port), Handler)
    server.fixture = Fixture()
    print('isolated-office-fixture-ready', flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close(); server.fixture.db.close()
