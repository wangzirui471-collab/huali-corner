"""本地 AI 客服 HTTP 服务（只绑定 127.0.0.1）。

接口：
  GET  /health   -> 索引与模型状态
  POST /reply    -> {"question": "..."} 返回 {answer, action, sources, mode, ...}
  POST /reload   -> 重新载入 index.json（改完知识库后不用重启进程）

启动：
  python ai_service/server.py
  HC_AI_MOCK=1 python ai_service/server.py   # 没有 GPU/Ollama 时先用摘录模式
"""
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config
import rag


class Handler(BaseHTTPRequestHandler):
    server_version = 'HualiAI/1.0'

    def _send(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def _auth_ok(self):
        if not config.TOKEN:
            return True
        got = self.headers.get('Authorization', '')
        return got == 'Bearer ' + config.TOKEN

    def _read_json(self):
        try:
            length = int(self.headers.get('Content-Length') or 0)
        except ValueError:
            length = 0
        if length <= 0 or length > 64 * 1024:
            return None
        try:
            return json.loads(self.rfile.read(length).decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None

    def _history(self, raw):
        """对话历史：只留最近 4 句，并放行闲聊标签（口径与 Worker 端一致）。

        标签是「上一轮属于哪种闲聊」——「嗯」「是啊」这种接话本身判不出情绪，
        不给标签的话第三轮必断，接话会被当成查询失败。
        """
        out = []
        if not isinstance(raw, list):
            return out
        for h in raw[-4:]:
            if not isinstance(h, dict):
                continue
            role = h.get('role')
            content = str(h.get('content') or '').strip()[:300]
            if role not in ('user', 'assistant') or not content:
                continue
            item = {'role': role, 'content': content}
            if role == 'user':
                soc = h.get('social')
                if soc in rag.SOCIAL_REPLIES:
                    item['social'] = soc
                depth = h.get('depth')
                if isinstance(depth, int) and 0 < depth < 99:
                    item['depth'] = depth
            out.append(item)
        return out

    def do_GET(self):
        if self.path.split('?', 1)[0] != '/health':
            return self._send({'error': 'not found'}, 404)
        try:
            idx = rag.load_index()
        except Exception as exc:  # noqa: BLE001
            return self._send({'ok': False, 'error': str(exc)}, 503)
        return self._send({
            'ok': True,
            'chunks': len(idx.get('chunks') or []),
            'provider': 'mock' if (config.MOCK or (config.PROVIDER == 'api' and not config.API_KEY)) else config.PROVIDER,
            'model': config.OLLAMA_MODEL if config.PROVIDER == 'ollama' else config.CHAT_MODEL,
            'embed_model': idx.get('embed_model'),
            'embed_ok': bool(idx.get('embed_ok')),
            'api_configured': bool(config.API_KEY),
            'mode': 'mock' if (config.MOCK or (config.PROVIDER == 'api' and not config.API_KEY)) else 'llm',
            'index_created': idx.get('created'),
        })

    def do_POST(self):
        if not self._auth_ok():
            return self._send({'error': 'unauthorized'}, 401)
        path = self.path.split('?', 1)[0]
        if path == '/reload':
            rag.reload_index()
            return self._send({'ok': True})
        if path == '/describe':
            data = self._read_json()
            if not isinstance(data, dict):
                return self._send({'error': '请求体必须是 JSON'}, 400)
            title = str(data.get('title') or '').strip()
            if not title:
                return self._send({'error': '缺少 title'}, 400)
            try:
                return self._send(rag.describe(
                    title, str(data.get('category') or '')[:20],
                    str(data.get('condition') or '')[:20], str(data.get('extra') or '')[:300]))
            except Exception as exc:  # noqa: BLE001 - 边界处返回可读错误
                return self._send({'error': f'AI 服务内部错误：{type(exc).__name__}'}, 500)
        if path == '/price':
            data = self._read_json()
            if not isinstance(data, dict):
                return self._send({'error': '请求体必须是 JSON'}, 400)
            title = str(data.get('title') or '').strip()
            if not title:
                return self._send({'error': '缺少 title'}, 400)
            raw = data.get('samples')
            samples = [int(p) for p in raw[:60] if str(p).lstrip('-').isdigit()] if isinstance(raw, list) else []
            try:
                return self._send(rag.price(
                    title, str(data.get('category') or '')[:20],
                    str(data.get('condition') or '')[:20],
                    int(data.get('original_price') or 0), samples))
            except Exception as exc:  # noqa: BLE001 - 边界处返回可读错误
                return self._send({'error': f'AI 服务内部错误：{type(exc).__name__}'}, 500)
        if path != '/reply':
            return self._send({'error': 'not found'}, 404)
        data = self._read_json()
        if not isinstance(data, dict):
            return self._send({'error': '请求体必须是 JSON'}, 400)
        question = str(data.get('question') or '').strip()
        if not question:
            return self._send({'error': '缺少 question'}, 400)
        history = self._history(data.get('history'))
        try:
            return self._send(rag.answer(question, history))
        except Exception as exc:  # noqa: BLE001 - 边界处返回可读错误，不抛堆栈
            return self._send({'error': f'AI 服务内部错误：{type(exc).__name__}'}, 500)

    def log_message(self, fmt, *args):
        # 只记状态行，不记问题正文（客户内容不落日志）
        sys.stderr.write('[ai] %s %s\n' % (self.command, self.path.split('?', 1)[0]))


def main():
    if not config.INDEX.exists() and not config.MOCK:
        print('缺少 index.json：请先运行 python ai_service/ingest.py')
        sys.exit(1)
    httpd = ThreadingHTTPServer(('127.0.0.1', config.PORT), Handler)
    mode = 'mock（知识库摘录）' if config.MOCK else f'Ollama {config.CHAT_MODEL}'
    print(f'AI 客服已启动：http://127.0.0.1:{config.PORT}  mode={mode}')
    print('按 Ctrl+C 停止。')
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print('\n已停止')
    finally:
        httpd.server_close()


if __name__ == '__main__':
    main()
