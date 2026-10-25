"""受控公开 FAQ 内部服务；复用旧 provider，不导入 agent 或业务工具。

从项目根执行 ``python ai_service/faq_server.py``，只监听 127.0.0.1。
必须设置 HC_AI_TOKEN；默认无模型密钥时仅摘录调用方传入的公开资料。
"""

import hmac
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import config
import rag

MAX_BODY_BYTES = 256 * 1024
MAX_QUESTION = 800
MAX_CONTEXT = 12000


def answer(question: str, context: str) -> dict[str, str]:
    """只使用已审核上下文生成文本；供应商异常交给 HTTP 边界返回失败。"""
    provider = config.PROVIDER
    if provider not in ("mock", "api"):
        raise ValueError("未批准的模型供应商")
    if config.MOCK or provider == "mock" or not config.API_KEY:
        # 不执行旧检索：上下文的发布审核、版本和来源均由本站 KnowledgePort 管理。
        text = rag.extractive([(1.0, {"text": context})])
        mode = "mock"
    else:
        # 保留原 TLS 与超时实现；任何失败都不自动发起第二次付费请求。
        text = rag.call_api(question, context)
        mode = "llm"
    text = rag.trim(rag.strip_thinking(text), 300)
    if not text:
        raise RuntimeError("模型未返回可展示内容")
    return {"answer_text": text, "mode": mode}


class Handler(BaseHTTPRequestHandler):
    """内部 HTTP 边界只接收 question/context，不接收用户身份或对话历史。"""

    server_version = "HualiFaq/1.0"

    def setup(self) -> None:
        """限制接收请求的等待时间，避免不完整请求长期占用线程。"""
        super().setup()
        self.connection.settimeout(10)

    def send_json(self, status: int, data: dict[str, str]) -> None:
        """发送纯 JSON 和禁止缓存头，不回显输入、凭据或异常详情。"""
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        """不公开健康、索引或配置读取接口。"""
        self.send_json(404, {"error": "NOT_FOUND"})

    def do_POST(self) -> None:
        """认证服务令牌、严格校验字段，再执行一次受控 FAQ 生成。"""
        if self.path != "/faq/answer":
            self.send_json(404, {"error": "NOT_FOUND"})
            return
        if not config.TOKEN:
            self.send_json(503, {"error": "SERVICE_NOT_CONFIGURED"})
            return
        expected = ("Bearer " + config.TOKEN).encode("utf-8")
        actual = self.headers.get("Authorization", "").encode("utf-8")
        if not hmac.compare_digest(actual, expected):
            self.send_json(401, {"error": "UNAUTHORIZED"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_BODY_BYTES:
            self.send_json(
                413 if length > MAX_BODY_BYTES else 400, {"error": "INVALID_BODY_SIZE"}
            )
            return
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeError, OSError):
            self.send_json(400, {"error": "INVALID_JSON"})
            return
        if not isinstance(data, dict) or set(data) != {"question", "context"}:
            self.send_json(422, {"error": "INVALID_FIELDS"})
            return
        for name, limit in (("question", MAX_QUESTION), ("context", MAX_CONTEXT)):
            value = data[name]
            if not isinstance(value, str) or not value.strip() or len(value) > limit:
                self.send_json(422, {"error": "INVALID_FIELDS"})
                return
        if config.PROVIDER not in ("mock", "api"):
            self.send_json(503, {"error": "PROVIDER_NOT_APPROVED"})
            return
        try:
            result = answer(data["question"].strip(), data["context"].strip())
        except Exception:  # noqa: BLE001 - HTTP边界统一隐藏供应商异常，明确返回502
            # 失败不能伪装为成功摘录，也不回显可能包含问题或密钥的异常文本。
            self.send_json(502, {"error": "MODEL_UNAVAILABLE"})
            return
        self.send_json(200, result)

    def log_message(self, fmt: str, *args: object) -> None:
        """不记录问题、上下文、服务令牌或请求全文。"""


def create_server(*, port: int | None = None) -> ThreadingHTTPServer:
    """创建仅回环监听的内部服务；测试可传 0 使用系统分配端口。"""
    server = ThreadingHTTPServer(
        ("127.0.0.1", config.PORT if port is None else port), Handler
    )
    server.daemon_threads = True
    return server


def main() -> None:
    """检查服务认证配置后启动 FAQ 入口，不加载旧索引或真实业务数据。"""
    if not config.TOKEN:
        raise SystemExit("必须设置 HC_AI_TOKEN 才能启动内部 FAQ 服务")
    server = create_server()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
