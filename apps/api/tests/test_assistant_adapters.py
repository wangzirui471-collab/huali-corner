"""真实回环 HTTP 的 FAQ 适配合同；只使用合成服务凭据，不访问供应商。"""

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from huali.infrastructure.assistant import ApprovedKnowledge, LocalFaqModel
from huali.shared.errors import ApplicationError
from huali.shared.settings import Settings


class FaqStub(BaseHTTPRequestHandler):
    """记录已解析的内部请求，模拟已有 FAQ 服务而非模型供应商。"""

    received: list[dict[str, object]] = []
    mime = "application/json"
    status = 200
    output: bytes = b'{"answer_text":"synthetic answer","mode":"mock"}'

    def do_POST(self) -> None:
        """只记录测试所需字段并发送有界响应。"""
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        type(self).received.append(
            {
                "path": self.path,
                "authorization": self.headers["Authorization"],
                "body": body,
            }
        )
        self.send_response(type(self).status)
        self.send_header("Content-Type", type(self).mime)
        self.end_headers()
        self.wfile.write(type(self).output)

    def log_message(self, fmt: str, *args: object) -> None:
        """禁止把测试凭据或上下文写入日志。"""


class FaqAdapterTests(unittest.IsolatedAsyncioTestCase):
    """核实内部服务边界、可信来源和配置拒绝行为。"""

    def setUp(self) -> None:
        """使用随机回环端口，既有8081及正式服务不受测试影响。"""
        FaqStub.received = []
        FaqStub.status = 200
        FaqStub.mime = "application/json"
        FaqStub.output = b'{"answer_text":"synthetic answer","mode":"mock"}'
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), FaqStub)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.model = LocalFaqModel(
            f"http://127.0.0.1:{self.server.server_port}", "synthetic-service-only"
        )

    def tearDown(self) -> None:
        """关闭并等待合成服务，不遗留测试端口或线程。"""
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)

    async def test_internal_request_has_only_approved_context(self) -> None:
        """服务 token 只用于内部认证，正文没有用户ID、历史、原Bearer或动作。"""
        result = await self.model.answer("付款规则", "公开支付均为模拟。")
        self.assertEqual(result.mode, "mock")
        self.assertEqual(
            FaqStub.received,
            [
                {
                    "path": "/faq/answer",
                    "authorization": "Bearer synthetic-service-only",
                    "body": {"question": "付款规则", "context": "公开支付均为模拟。"},
                }
            ],
        )

    async def test_html_and_vendor_citations_are_rejected_without_retry(self) -> None:
        """代理HTML和供应商伪造来源均不变成成功回答，也不自动第二次调用。"""
        for mime, output in (
            ("text/html", b"<!DOCTYPE html>"),
            (
                "application/json",
                b'{"answer_text":"x","mode":"mock","sources":["fake"]}',
            ),
            ("application/json", b'{"answer_text":" ","mode":"mock"}'),
        ):
            FaqStub.mime = mime
            FaqStub.output = output
            before = len(FaqStub.received)
            with self.assertRaises(ApplicationError) as error:
                await self.model.answer("付款规则", "公开资料")
            self.assertEqual(error.exception.status, 503)
            self.assertEqual(len(FaqStub.received), before + 1)

    def test_knowledge_matches_only_approved_records(self) -> None:
        """可信来源和版本从当前清单读取，旧未审核FAQ索引不自动启用。"""
        knowledge = ApprovedKnowledge()
        documents = knowledge.search("付款会真实扣款吗")
        self.assertTrue(documents)
        self.assertEqual(documents[0].document_id, "public-faq-simulated-payment")
        self.assertEqual(documents[0].version, "2026-10-24-c92567d")
        self.assertEqual(knowledge.search("量子火星旅行签证"), ())

    def test_configuration_forbids_remote_or_production_faq(self) -> None:
        """模型源站只能来自显式本机配置，不能通过URL窃取服务认证。"""
        for origin in (
            "https://example.invalid",
            "http://127.0.0.1:8001",
            "http://user:secret@127.0.0.1:8093",
            "http://127.0.0.1:8093/path",
            "http://127.0.0.1:8093?redirect=elsewhere",
        ):
            with self.assertRaises(ValueError):
                Settings("test", assistant_origin=origin, assistant_token="synthetic")
        with self.assertRaises(ValueError):
            Settings(
                "production",
                assistant_origin="http://127.0.0.1:8093",
                assistant_token="synthetic",
            )
        with self.assertRaises(ValueError):
            Settings("local", assistant_origin="http://127.0.0.1:8093")
        self.assertNotIn(
            "synthetic-secret",
            repr(Settings("test", assistant_token="synthetic-secret")),
        )
